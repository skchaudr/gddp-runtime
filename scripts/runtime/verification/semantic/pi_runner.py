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

from scripts.runtime.verification.schemas import SemanticOutput
from scripts.runtime.verification.semantic.prompt import build_prompt_messages


EXTENSION_PATH = Path(__file__).resolve().parent / "pi_harness" / "gddp_verifier.ts"
EVIDENCE_TOOLS = ("read", "grep", "find", "ls", "submit_verdict")
EXCLUDED_TOOLS = ("edit", "write", "multi_edit", "bash")


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
    ) -> None:
        self.provider = provider
        self.model = model
        self.thinking = thinking
        self.extra_args = extra_args or []
        self.pi_binary = pi_binary

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
        sys_prompt = system_prompt or _extract_system_prompt(messages)
        user_prompt = _extract_user_prompt(messages)

        with tempfile.NamedTemporaryFile(
            prefix="gddp-verdict-", suffix=".json", delete=False
        ) as vf:
            verdict_path = vf.name
        os.unlink(verdict_path)  # pi extension writes it; absence = no verdict

        env = dict(os.environ)
        env["GDDP_VERDICT_OUT"] = verdict_path

        cmd = self._build_command(sys_prompt, user_prompt, repo)
        proc = subprocess.run(
            cmd,
            env=env,
            cwd=str(repo),
            stdin=None,
            stdout=None,
            stderr=None,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pi exited with code {proc.returncode}")

        if not Path(verdict_path).exists():
            return _empty_verdict(
                "pi completed without calling submit_verdict; no verdict recorded."
            )
        raw = json.loads(Path(verdict_path).read_text(encoding="utf-8"))
        return SemanticOutput.model_validate(raw)

    def _build_command(self, system_prompt: str, user_prompt: str, repo: Path) -> list[str]:
        cmd: list[str] = [
            self.pi_binary,
            "--print",
            "--mode", "text",
            # Keep the run clean: only our explicit -e extension, no discovered
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
            "--tools", ",".join(EVIDENCE_TOOLS),
            "--exclude-tools", ",".join(EXCLUDED_TOOLS),
            "--provider", self.provider,
            "--thinking", self.thinking,
            "--system-prompt", system_prompt,
            user_prompt,
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd += self.extra_args
        return cmd


def _extract_system_prompt(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") == "system":
            return str(m.get("content", ""))
    return ""


def _extract_user_prompt(messages: list[dict[str, Any]]) -> str:
    for m in messages:
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _empty_verdict(reason: str) -> SemanticOutput:
    return SemanticOutput(
        judgments=[],
        overall_reasoning=reason,
        risks=None,
        followup_candidates=None,
        budget_exhausted=True,
        budget_trace=None,
    )
