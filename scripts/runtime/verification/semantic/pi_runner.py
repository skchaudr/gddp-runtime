"""Pi-harness runner: drives the `pi` coding agent as the semantic evaluator.

Why this exists
---------------
The hand-rolled SemanticAgent loop (semantic/agent.py) is correct but opaque:
the operator only sees a final receipt. Running the evaluator through `pi`
gives live visibility into the model's text, thinking, and tool calls, while
preserving the GDDP contract:

  - criteria come from the gddp-config node YAML (unchanged)
  - submit_verdict stays a TYPED terminal tool (registered by the
    gddp_verifier.ts pi extension), so free-text JSON parsing is still gone
  - the 12-row decision_engine and VerdictReceipt are unchanged
  - the harness is read-only: pi's edit/write/multi_edit/bash are excluded

The runner spawns `pi --print --mode text -e gddp_verifier.ts ...` with the
operator's terminal inherited, so the investigator's stream is visible live.
On exit it reads the verdict JSON written by the extension and returns a
SemanticOutput, which orchestrator.verify() feeds into decision_engine.decide().
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from scripts.runtime.verification.schemas import LaneExecutionStatus, SemanticOutput
from scripts.runtime.verification.semantic.context_builder import build_canonical_pointers
from scripts.runtime.verification.semantic.prompt import build_prompt_messages
from scripts.runtime.verification.semantic.subprocess_utils import (
    read_tail as _read_tail,
    read_trace as _read_trace,
    tee_subprocess as _tee_subprocess,
)
from scripts.runtime.verification.semantic.timeouts import PI_TIMEOUT_SECONDS


EXTENSION_PATH = Path(__file__).resolve().parent / "pi_harness" / "gddp_verifier.ts"
GUARD_EXTENSION_PATH = Path(__file__).resolve().parent / "pi_harness" / "gddp_verifier_guard.ts"
# Broad inputs: pi's built-in read/grep/find/ls/bash are available; the guard
# extension mechanistically blocks mutations, dangerous bash, and network.
# submit_verdict is the typed terminal tool registered by gddp_verifier.ts.

PI_SYSTEM_PROMPT = """You are the GDDP semantic verification investigator.

Your job: determine whether the work in this repo satisfies the acceptance
criteria of the current node, AND whether it preserves the project's intent
and integrity. You are not checking that tests pass; you are checking that the
code matches the node's criteria and the project's stated intent. You do NOT
decide the final node status; a human does. You produce evidence and a typed
verdict only.

Tools: you have read, grep, find, ls, bash, and submit_verdict available.
edit/write/multi_edit are hard-blocked by the harness (the evaluator is
read-only). bash is allowed for read-only inspection only; destructive verbs,
git mutation (commit/push/reset/...), and network are hard-blocked. If you
call a blocked tool the harness will refuse and tell you why.

Investigate the repo against the node's acceptance criteria. Prefer cheap
tools (read, grep, find) before bash. When finished, call submit_verdict
with arguments matching SemanticOutput: per-criterion judgments
(judged_pass | judged_fail | indeterminate + confidence + evidence refs +
reasoning), overall_reasoning, risks, followup_candidates, and
budget_exhausted. Call submit_verdict exactly once; it ends the run.

Evidence scope: evaluate ONLY against the node's stated acceptance criteria.
Tests passing are useful context, but unless the node explicitly lists the
suite as acceptance evidence, do not count it as proof of node completion,
intent preservation, graph integrity, or implementation correctness. If tests
are not in the criteria, report them as observed/contextual evidence only and
let the verdict stand on the stated criteria. The same rule applies to ANY
evidence not bound to a stated criterion: extra evidence cannot rewrite the
definition of success. When you observe unlisted-but-notable evidence, add a
followup_candidate phrased as a human clarification, e.g.: "Observed: test
suite passed. Not listed in the node's acceptance criteria, so not counted
toward the verdict. Was it intended to be part of the criteria? If yes, update
the node criteria and rerun; otherwise this verdict stands." You are not
re-doing the executor's full due diligence from scratch; judge whether the
submitted evidence supports the stated criteria, inspecting strategically.

Canonical context: README, PROJECT-BRIEF, the foundational/first node, and
your DAG neighbors (depends_on + unlocks) are provided as file pointers in
the prompt. Read the ones relevant to your criteria evaluation. Upstream
node files state what this node was allowed to assume; downstream files
state what depends on it. The target repo's AGENTS.md is NOT provided — it
is executor-facing, not evaluator-facing.

Criteria confidence is your confidence the code satisfies the criterion,
INDEPENDENT of whether required execution artifacts/trail are present. If the
code clearly satisfies a criterion but a required artifact is missing, judge
that criterion judged_pass at high confidence; the missing artifact is a
completeness concern, not a criteria concern.
"""


class PiHarnessRunner:
    """Drives `pi` as the semantic verifier. Implements the Runner protocol."""

    def __init__(
        self,
        *,
        provider: str,
        model: str | None = None,
        thinking: str = "medium",
        extra_args: list[str] | None = None,
        pi_binary: str = "pi",
        config_root: Path | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.thinking = thinking
        self.extra_args = extra_args or []
        self.pi_binary = pi_binary
        self.config_root = config_root

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:  # noqa: ARG002
        """Runner protocol shim.

        The pi harness owns its own tool loop, so the orchestrator/agent loop
        never calls this. It is here so PiHarnessRunner is structurally
        compatible with the Runner type. Actual execution happens via run().
        """
        raise NotImplementedError("PiHarnessRunner uses run(), not chat()")

    def run(
        self,
        *,
        node: dict[str, Any],
        graph: dict[str, Any],
        deterministic_result: Any,
        shape_profile: dict[str, Any] | None = None,
        repo: Path,
        system_prompt: str | None = None,
    ) -> SemanticOutput:
        if not shutil.which(self.pi_binary):
            raise RuntimeError(f"pi binary not found on PATH: {self.pi_binary}")
        if not EXTENSION_PATH.exists():
            raise RuntimeError(f"gddp_verifier extension missing: {EXTENSION_PATH}")

        messages = build_prompt_messages(node, graph, deterministic_result, shape_profile)
        sys_prompt = system_prompt or PI_SYSTEM_PROMPT
        # Canonical context: file pointers to README, PROJECT-BRIEF, foundational
        # node, and DAG neighbors. The evaluator reads what it needs; the tool
        # trace proves what was read. AGENTS.md is never included.
        canonical = build_canonical_pointers(
            node=node, graph=graph, repo=repo, config_root=self.config_root,
        )
        canonical_block = (
            "\n\n--- Canonical Context (file pointers — read what you need) ---\n"
            + json.dumps(canonical, indent=2, sort_keys=True)
        )
        user_prompt = _extract_user_prompt(messages) + canonical_block

        with tempfile.NamedTemporaryFile(
            prefix="gddp-verdict-", suffix=".json", delete=False
        ) as vf:
            verdict_path = vf.name
        os.unlink(verdict_path)  # pi extension writes it; absence = no verdict

        with tempfile.NamedTemporaryFile(
            prefix="gddp-tool-trace-", suffix=".jsonl", delete=False
        ) as tf:
            trace_path = tf.name
        os.unlink(trace_path)  # guard extension writes/appends it

        env = dict(os.environ)
        env["GDDP_VERDICT_OUT"] = verdict_path
        env["GDDP_TOOL_TRACE"] = trace_path
        # Sandbox: point HOME at a throwaway directory so pi cannot discover
        # ~/.pi/agent/ (models.json, extensions, context files) even if future
        # pi versions add new auto-discovery paths. The evaluator must run with
        # zero ambient config.
        sandbox_home = tempfile.mkdtemp(prefix="gddp-pi-home-")
        env["HOME"] = sandbox_home

        cmd = self._build_command(sys_prompt, user_prompt, repo)
        # Phase 4: tee stdout/stderr to terminal + durable log. Do NOT raise
        # on non-zero exit — return a typed fallback so partial evidence
        # from the other lane is preserved in the receipt.
        stdout_path = tempfile.mktemp(prefix="gddp-pi-stdout-")
        stderr_path = tempfile.mktemp(prefix="gddp-pi-stderr-")
        try:
            proc = _tee_subprocess(cmd, env, str(repo), stdout_path, stderr_path, PI_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            trace = _read_trace(trace_path)
            return _empty_verdict(
                f"pi timed out after {PI_TIMEOUT_SECONDS}s",
                trace,
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
            return _empty_verdict(
                f"pi exited with code {proc.returncode}: {stderr_tail}",
                trace,
                lane_status=LaneExecutionStatus.CRASHED,
                harness_error=_harness_error_with_logs(
                    f"pi exited with code {proc.returncode}: {stderr_tail}",
                    stdout_path, stderr_path,
                ),
            )

        trace = _read_trace(trace_path)
        if not Path(verdict_path).exists():
            return _empty_verdict(
                "pi completed without calling submit_verdict; no verdict recorded.",
                trace,
                lane_status=LaneExecutionStatus.NO_VERDICT,
                harness_error=_harness_error_with_logs(
                    "pi completed without calling submit_verdict",
                    stdout_path, stderr_path,
                ),
            )
        raw = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
        # Ground-truth trace wins over whatever the model put in budget_trace
        # (submit_verdict always includes the key, usually null, so setdefault
        # would never fire).
        if trace:
            raw["budget_trace"] = {"tool_calls": trace}
        else:
            raw.setdefault("budget_trace", None)
        raw["lane_status"] = LaneExecutionStatus.COMPLETED.value
        # Success: the verdict was recorded, so the temp stdout/stderr logs are
        # no longer needed. Best-effort cleanup; never raise. On failure paths
        # the logs are preserved and linked into harness_error instead.
        _cleanup_logs(stdout_path, stderr_path)
        return SemanticOutput.model_validate(raw)

    def _build_command(self, system_prompt: str, user_prompt: str, repo: Path) -> list[str]:
        cmd: list[str] = [
            self.pi_binary,
            "--print",
            "--mode", "text",
            # Keep the run clean: only our explicit -e extensions, no discovered
            # project-local resources (AGENTS.md/CLAUDE.md/skills/themes) from
            # the target repo, no session persistence. cwd is set on the
            # subprocess so pi operates inside the target repo.
            "--no-approve",
            "--no-context-files",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-extensions",
            "--no-session",
            "-e", str(EXTENSION_PATH),
            "-e", str(GUARD_EXTENSION_PATH),
            # Broad tool access: no --tools allowlist, no --exclude-tools cripple.
            # The guard extension mechanistically blocks mutations, dangerous
            # bash, and network at the tool_call hook.
            "--provider", self.provider,
            "--thinking", self.thinking,
            "--system-prompt", system_prompt,
            user_prompt,
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd += self.extra_args
        return cmd


def _extract_user_prompt(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _empty_verdict(reason: str, trace: list[dict[str, Any]] | None = None, lane_status: LaneExecutionStatus | None = None, harness_error: str | None = None) -> SemanticOutput:
    return SemanticOutput(
        judgments=[],
        overall_reasoning=reason,
        risks=None,
        followup_candidates=None,
        budget_exhausted=True,
        budget_trace={"tool_calls": trace} if trace else None,
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
