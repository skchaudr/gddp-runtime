"""Pi-harness runner for the integrity lane (lane 2: fresh-eyes drift review).

Sibling of pi_runner.py. Spawns `pi --print` with gddp_integrity.ts loaded and
an integrity-specific system prompt. The model's mandate: fresh-eyes review —
given the node's why, constraints, depends_on/unlocks neighbor YAML, and the
work under review, does the change preserve the node's intended role in the
project? It is NOT re-adjudicating acceptance criteria (that is lane 1's job).

Returns IntegrityOutput (schemas.py), which the orchestrator feeds into
integrity_combiner.combine().
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scripts.runtime.verification.schemas import IntegrityOutput, LaneExecutionStatus
from scripts.runtime.verification.semantic.context_builder import build_canonical_pointers
from scripts.runtime.verification.semantic.pi_environment import build_pi_environment
from scripts.runtime.verification.semantic.subprocess_utils import (
    read_tail as _read_tail,
    read_trace as _read_trace,
    tee_subprocess as _tee_subprocess,
)
from scripts.runtime.verification.semantic.timeouts import PI_TIMEOUT_SECONDS


EXTENSION_PATH = Path(__file__).resolve().parent / "pi_harness" / "gddp_integrity.ts"
GUARD_EXTENSION_PATH = Path(__file__).resolve().parent / "pi_harness" / "gddp_verifier_guard.ts"
INTEGRITY_SYSTEM_PROMPT = """You are the GDDP integrity reviewer (lane 2: fresh-eyes drift review).

Your job: evaluate whether the work in this repo preserves the node's intended
role in the project, and whether it preserves the graph's integrity. You are
NOT re-adjudicating acceptance criteria — that is lane 1's job. Lane 1 already
answered whether the criteria were met. Your job is different: given the full
picture — the node's why, constraints, depends_on/unlocks neighbor YAML, and
the work under review — does the change preserve the node's intended role?
Does it preserve the project's graph integrity (dependencies, structure)?

Think like a fresh pair of eyes, not a spec enforcer. Ask: does this change
make sense for what this node promised to deliver? Could it inadvertently
break something a dependent node relies on? Is the intent still recognizable?

Tools: you have read, grep, find, ls, bash, and submit_integrity_verdict
available. edit/write/multi_edit are hard-blocked by the harness (the integrity
reviewer is read-only). bash is allowed for read-only inspection only;
destructive verbs, git mutation, and network are hard-blocked.

Investigate the repo against the node's intent and graph integrity. Prefer cheap
tools (read, grep, find) before bash. When finished, call submit_integrity_verdict
with arguments matching IntegrityOutput:

  verdict: "pass" | "block" | "drift" | "insufficient" | "contradicted" | "unknown"
  intent_preserved: true/false
  graph_integrity_preserved: true/false
  required_human_review: true/false
  confidence: 0.0-1.0
  findings: [{severity: "low"|"medium"|"high", summary: "...", affected_node_ids: [...]}]
  reasoning: "..."
  graph_observations: [{severity, summary, affected_node_ids}] (optional — see below)

Findings vs graph_observations:
  - findings: affect the CURRENT node's verdict. If you put a finding here and
    set intent_preserved=false or graph_integrity_preserved=false, the combined
    verdict floors to needs-human-review. Use findings for current-node problems.
  - graph_observations: forward-looking observations about graph trajectory,
    upcoming convergence risk, or execution strategy. These do NOT affect the
    current verdict. Use them when the current work is fine but you notice
    something about the graph's future. Example: "Upcoming nodes converge on
    the scheduler; serialize this region." The current node still passes.

Call submit_integrity_verdict exactly once; it ends the run.

Vocabulary comes from the evaluator-intent-integrity-verdict node, not this repo:
- pass: the change preserves intent and graph integrity as stated
- block: the change actively harms intent or graph integrity; do not proceed
- drift: the change subtly veers from the node's intended role
- insufficient: not enough evidence to reach a clear verdict
- contradicted: evidence contradicts the stated intent
- unknown: unable to determine (missing context, ambiguous)

The integrity review is a guardrail, not a gatekeeper. A pass means proceed
with confidence; a non-pass means a human should look before dependents fire.
"""


class IntegrityHarnessRunner:
    """Drives `pi` as the integrity reviewer. Implements the Runner protocol."""

    def __init__(
        self,
        *,
        provider: str,
        model: str | None = None,
        thinking: str = "medium",
        extra_args: list[str] | None = None,
        pi_binary: str = "pi",
    ) -> None:
        self.provider = provider
        self.model = model
        self.thinking = thinking
        self.extra_args = extra_args or []
        self.pi_binary = pi_binary

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:  # noqa: ARG002
        """Runner protocol shim. Actual execution happens via run()."""
        raise NotImplementedError("IntegrityHarnessRunner uses run(), not chat()")

    def run(
        self,
        *,
        node: dict[str, Any],
        graph: dict[str, Any],
        deterministic_result: Any,
        repo: Path,
        config_root: Path | None = None,
        system_prompt: str | None = None,
    ) -> IntegrityOutput:
        if not shutil.which(self.pi_binary):
            raise RuntimeError(f"pi binary not found on PATH: {self.pi_binary}")
        if not EXTENSION_PATH.exists():
            raise RuntimeError(f"gddp_integrity extension missing: {EXTENSION_PATH}")

        sys_prompt = system_prompt or INTEGRITY_SYSTEM_PROMPT
        # Phase 2: use the same canonical baseline as the semantic lane
        # (README, PROJECT-BRIEF, foundational node, DAG neighbors) instead of
        # only neighbor pointers. Both lanes must be offered the same menu.
        canonical = build_canonical_pointers(
            node=node, graph=graph, repo=repo, config_root=config_root,
        )
        neighbors = _neighbor_pointers(node, graph, config_root)
        user_prompt = _build_integrity_prompt(
            node, graph, deterministic_result, neighbors, config_root, canonical,
        )

        with tempfile.NamedTemporaryFile(
            prefix="gddp-integrity-", suffix=".json", delete=False
        ) as vf:
            verdict_path = vf.name
        os.unlink(verdict_path)

        with tempfile.NamedTemporaryFile(
            prefix="gddp-integrity-trace-", suffix=".jsonl", delete=False
        ) as tf:
            trace_path = tf.name
        os.unlink(trace_path)

        sandbox_home = tempfile.mkdtemp(prefix="gddp-pi-integrity-home-")
        try:
            env = build_pi_environment(self.provider, Path(sandbox_home))
            env["GDDP_INTEGRITY_OUT"] = verdict_path
            env["GDDP_TOOL_TRACE"] = trace_path
            cmd = self._build_command(sys_prompt, user_prompt, repo)
            # Tee the investigator stream while preserving failure evidence.
            stdout_path = tempfile.mktemp(prefix="gddp-integrity-stdout-")
            stderr_path = tempfile.mktemp(prefix="gddp-integrity-stderr-")
            try:
                proc = _tee_subprocess(
                    cmd, env, str(repo), stdout_path, stderr_path, PI_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                trace = _read_trace(trace_path)
                return _empty_integrity(
                    f"pi timed out after {PI_TIMEOUT_SECONDS}s",
                    tool_trace=trace,
                    lane_status=LaneExecutionStatus.TIMED_OUT,
                    harness_error=_harness_error_with_logs(
                        f"pi timed out after {PI_TIMEOUT_SECONDS}s", stdout_path, stderr_path,
                    ),
                )
        finally:
            shutil.rmtree(sandbox_home, ignore_errors=True)

        if proc.returncode != 0:
            stderr_tail = _read_tail(stderr_path, 500)
            trace = _read_trace(trace_path)
            return _empty_integrity(
                f"pi exited with code {proc.returncode}: {stderr_tail}",
                tool_trace=trace,
                lane_status=LaneExecutionStatus.CRASHED,
                harness_error=_harness_error_with_logs(
                    f"pi exited with code {proc.returncode}: {stderr_tail}",
                    stdout_path, stderr_path,
                ),
            )

        if not Path(verdict_path).exists():
            trace = _read_trace(trace_path)
            return _empty_integrity(
                "pi completed without calling submit_integrity_verdict; no verdict recorded.",
                tool_trace=trace,
                lane_status=LaneExecutionStatus.NO_VERDICT,
                harness_error=_harness_error_with_logs(
                    "pi completed without calling submit_integrity_verdict",
                    stdout_path, stderr_path,
                ),
            )
        raw = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
        # Phase 2: attach ground-truth tool trace to the integrity output.
        trace = _read_trace(trace_path)
        if trace:
            raw["tool_trace"] = trace
        raw["lane_status"] = LaneExecutionStatus.COMPLETED.value
        # Success: the verdict was recorded, so the temp stdout/stderr logs are
        # no longer needed. Best-effort cleanup; never raise. On failure paths
        # the logs are preserved and linked into harness_error instead.
        _cleanup_logs(stdout_path, stderr_path)
        return IntegrityOutput.model_validate(raw)

    def _build_command(self, system_prompt: str, user_prompt: str, repo: Path) -> list[str]:
        cmd: list[str] = [
            self.pi_binary,
            "--print",
            "--mode", "text",
            "--no-approve",
            "--no-context-files",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-extensions",
            "--no-session",
            "-e", str(EXTENSION_PATH),
            "-e", str(GUARD_EXTENSION_PATH),
            "--provider", self.provider,
            "--thinking", self.thinking,
            "--system-prompt", system_prompt,
            user_prompt,
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd += self.extra_args
        return cmd


def _neighbor_pointers(
    node: dict[str, Any],
    graph: dict[str, Any],
    config_root: Path | None,
) -> dict[str, str]:
    """Map depends_on/unlocks neighbor ids to their YAML file paths.

    Pointers, not contents: the evaluator reads what it decides it needs, and
    the tool trace then records which neighbors were actually investigated —
    a read call is evidence, an embedded blob is not. Missing files are
    reported as missing rather than silently dropped, so absence itself is
    reviewable evidence.
    """
    neighbor_ids = list(node.get("depends_on") or []) + list(node.get("unlocks") or [])
    if not neighbor_ids:
        return {}
    if config_root is None:
        return {nid: "UNAVAILABLE: no config_root provided" for nid in neighbor_ids}

    project_id = graph.get("project_id", "")
    nodes_dir = Path(config_root) / "graphs" / project_id / "nodes"
    pointers: dict[str, str] = {}
    for nid in neighbor_ids:
        path = nodes_dir / f"{nid}.yaml"
        pointers[nid] = str(path) if path.exists() else f"UNAVAILABLE: {path} does not exist"
    return pointers


def _build_integrity_prompt(
    node: dict[str, Any],
    graph: dict[str, Any],
    deterministic_result: Any,
    neighbors: dict[str, str],
    config_root: Path | None,
    canonical: dict[str, str] | None = None,
) -> str:
    context = {
        "node": node,
        "graph": graph,
        "neighbor_node_files": neighbors,
        "deterministic_result": deterministic_result,
    }
    graph_access = (
        f"The full graph config lives at {config_root} (read-only; "
        f"graphs/<project>/nodes/*.yaml) if you need nodes beyond the neighbors.\n\n"
        if config_root
        else ""
    )
    canonical_block = ""
    if canonical:
        canonical_block = (
            "\n\n--- Canonical Context (file pointers — read what you need) ---\n"
            + json.dumps(canonical, indent=2, sort_keys=True)
        )
    return (
        "Perform a fresh-eyes integrity review of the following GDDP verification context. "
        "Your focus: does the work preserve the node's intended role in the project and "
        "the project's graph integrity? You are NOT re-adjudicating acceptance criteria "
        "(that is lane 1's job). neighbor_node_files maps this node's depends_on/unlocks "
        "neighbors to their YAML files — read the ones relevant to your review; upstream "
        "files state what this node was allowed to assume, downstream files state what "
        "depends on it. Then evaluate: does the change preserve the node's intended role? "
        "Does it preserve graph integrity?\n\n"
        f"{graph_access}"
        f"{json.dumps(context, indent=2, sort_keys=True, default=str)}"
        f"{canonical_block}"
    )


def _empty_integrity(reason: str, tool_trace: list[dict[str, Any]] | None = None, lane_status: LaneExecutionStatus | None = None, harness_error: str | None = None) -> IntegrityOutput:
    return IntegrityOutput(
        verdict="unknown",
        intent_preserved=False,
        graph_integrity_preserved=False,
        required_human_review=True,
        confidence=0.0,
        findings=[],
        reasoning=reason,
        tool_trace=tool_trace,
        lane_status=lane_status,
        harness_error=harness_error,
    )


def _harness_error_with_logs(harness_error: str, stdout_path: str, stderr_path: str) -> str:
    """Append preserved temp log paths to harness_error so operators can find them.

    Used on failure paths (crash / no-verdict / timeout) where the stdout/stderr
    log files are intentionally left on disk for post-mortem inspection instead
    of being cleaned up by _cleanup_logs.
    """
    return f"{harness_error} (preserved logs: stdout={stdout_path} stderr={stderr_path})"


def _cleanup_logs(stdout_path: str, stderr_path: str) -> None:
    """Best-effort unlink of temp stdout/stderr log files. Never raise.

    Called on the success (COMPLETED) path — the logs are not needed once a
    verdict was recorded. On failure paths the logs are preserved and their
    paths are linked into harness_error via _harness_error_with_logs.
    """
    for p in (stdout_path, stderr_path):
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass
