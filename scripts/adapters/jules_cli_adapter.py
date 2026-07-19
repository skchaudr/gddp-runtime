"""
jules_cli_adapter.py — Direct CLI dispatch adapter.

Dispatches a job to Jules via the Jules CLI (`jules remote ...`). This is the
GDDP-pure path: the runtime decision loop explicitly dispatches the job packet
to Jules and polls for completion, rather than relying on GitHub label events
to trigger the Jules action.

CLI surface (verified against installed `/opt/homebrew/bin/jules`):
    jules remote new --repo <repo> --session "<instructions>"  -> session ID
    jules remote list --session                                -> status table
    jules remote pull --session <id>                           -> patch (no apply)
    jules remote pull --session <id> --apply                   -> apply patch

This adapter implements the executor-neutral protocol defined in
``adapters.executor_protocol``. The runtime talks to it through
dispatch/status/collect/cancel without knowing it is Jules.

Requires:
    - jules CLI on PATH (or at /opt/homebrew/bin/jules)
    - jules authenticated

Usage:
    from adapters.jules_cli_adapter import JulesCliAdapter
    adapter = JulesCliAdapter(repo="owner/repo")
    result = adapter.dispatch(job)   # -> DispatchResult(session_ref=SessionRef(...))
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from adapters.executor_protocol import (
    DispatchResult,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)

# Long numeric session IDs (pattern borrowed from the AA CLI: grep -oE '[0-9]{15,}').
_SESSION_ID_RE = re.compile(r"[0-9]{15,}")

# Default jules binary. Resolved via PATH at call time, but fall back to the
# known homebrew location if the user's PATH does not expose it.
_JULES_BIN = "jules"

# Status keyword -> normalized SessionStatus.state. Order matters: more
# specific terminal states are checked before generic running states.
_STATUS_MAP = (
    ("complete", "completed"),
    ("failed", "failed"),
    ("queued", "running"),
    ("running", "running"),
)


def _flatten(item) -> str:
    """Convert an immutable packet value to readable text."""
    if isinstance(item, Mapping):
        return " — ".join(f"{key}: {value}" for key, value in item.items())
    if isinstance(item, Sequence) and not isinstance(item, str | bytes | bytearray):
        return ", ".join(str(value) for value in item)
    return str(item)


class JulesCliAdapter:
    """
    Dispatches a job to Jules via the Jules CLI.

    Implements the ExecutorAdapter protocol (dispatch/status/collect/cancel).
    """

    def __init__(self, repo: str, jules_bin: str = _JULES_BIN, timeout: int = 30):
        self.repo = repo
        self.jules_bin = jules_bin
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Instruction body construction
    # ------------------------------------------------------------------ #

    def _build_session_instructions(self, packet: NodePacket) -> str:
        """Build the --session instruction string sent to Jules."""
        constraints_text = "\n".join(
            f"- {_flatten(constraint)}" for constraint in packet.constraints
        )
        criteria_text = "\n".join(
            f"- [ ] {_flatten(criterion)}"
            for criterion in packet.acceptance_criteria
        )

        artifacts_section = ""
        if packet.required_artifacts:
            artifacts_text = "\n".join(
                f"- `{artifact}`" for artifact in packet.required_artifacts
            )
            artifacts_section = (
                "\n## Required Artifacts\n"
                "The result must include:\n"
                f"{artifacts_text}\n"
            )

        findings_section = ""
        findings = packet.previous_findings
        if findings:
            raw_findings = findings.get("findings", ())
            findings_list = "\n".join(
                (
                    f"- [{finding.get('severity', '?')}] "
                    f"{finding.get('summary', '')}"
                )
                for finding in raw_findings
                if isinstance(finding, Mapping)
            )
            findings_section = (
                f"\n## Previous Attempt Findings (attempt {packet.attempt_index})\n"
                f"**Verdict:** {findings.get('verdict', 'unknown')}\n"
                f"**Integrity verdict:** "
                f"{findings.get('integrity_verdict', 'unknown')}\n"
                f"**Reasoning:** {findings.get('reasoning', '')}\n\n"
                f"### Findings\n{findings_list}\n"
            )

        header = f"[GDDP] {packet.title}" if packet.title else "GDDP task"
        return (
            f"{header}\n\n"
            f"## Goal\n{packet.goal}\n\n"
            f"## Why\n{packet.why}\n\n"
            f"## Constraints\n{constraints_text}\n\n"
            f"## Acceptance Criteria\n{criteria_text}\n"
            f"{artifacts_section}"
            f"{findings_section}\n"
            f"---\n"
            f"node: {packet.node_id}\n"
            f"job: {packet.job_id}\n"
            f"attempt: {packet.attempt_index}\n"
        )

    # ------------------------------------------------------------------ #
    # ExecutorAdapter: dispatch
    # ------------------------------------------------------------------ #

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        """Dispatch a job to Jules via `jules remote new`.

        Returns a DispatchResult whose session_ref holds the parsed Jules
        session ID. Failures return success=False with an explanatory error.
        """
        instructions = self._build_session_instructions(packet)
        cmd = [
            self.jules_bin, "remote", "new",
            "--repo", self.repo,
            "--session", instructions,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                success=False,
                error=f"jules remote new timed out after {self.timeout}s",
            )
        except FileNotFoundError:
            return DispatchResult(
                success=False,
                error=f"jules binary not found: {self.jules_bin}",
            )
        except Exception as e:
            return DispatchResult(success=False, error=f"jules dispatch failed: {e}")

        if result.returncode != 0:
            return DispatchResult(
                success=False,
                error=(result.stderr or result.stdout or "jules remote new failed").strip(),
            )

        # Parse the session ID from output. Jules prints a long numeric ID.
        match = _SESSION_ID_RE.search(result.stdout or "")
        if not match:
            return DispatchResult(
                success=False,
                error=(
                    "jules remote new succeeded but no session ID found in output: "
                    f"{(result.stdout or '').strip()!r}"
                ),
            )
        session_id = match.group(0)
        return DispatchResult(
            success=True,
            session_ref=SessionRef(executor="jules_cli", session_id=session_id),
        )

    # ------------------------------------------------------------------ #
    # ExecutorAdapter: status
    # ------------------------------------------------------------------ #

    def status(self, session_ref: SessionRef) -> SessionStatus:
        """Poll session status via `jules remote list --session`.

        Fails closed: any unfamiliar output, missing session, or CLI failure
        is reported as ``failed`` with a descriptive error.
        """
        session_id = session_ref.session_id
        cmd = [self.jules_bin, "remote", "list", "--session"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return SessionStatus(state="failed", error=f"jules list timed out after {self.timeout}s")
        except FileNotFoundError:
            return SessionStatus(state="failed", error=f"jules binary not found: {self.jules_bin}")
        except Exception as e:
            return SessionStatus(state="failed", error=f"jules list failed: {e}")

        if result.returncode != 0:
            return SessionStatus(
                state="failed",
                error=(result.stderr or result.stdout or "jules remote list failed").strip(),
            )

        # Find the line that mentions this session. Jules list output is a
        # table; the session ID column is the durable handle.
        stdout = result.stdout or ""
        session_lines = [
            line for line in stdout.splitlines() if session_id in line
        ]
        if not session_lines:
            return SessionStatus(
                state="failed",
                error="session not found in jules list",
            )

        # Inspect the matching line(s) for known status keywords.
        line_blob = "\n".join(session_lines).lower()
        for keyword, state in _STATUS_MAP:
            if keyword in line_blob:
                return SessionStatus(state=state)  # type: ignore[arg-type]

        # "Awaiting User Feedback" (truncated as "Awaiting User F" in the
        # table) means the executor is blocked waiting for a human. Map to
        # needs_operator rather than letting it fall through to running.
        if "awaiting" in line_blob:
            return SessionStatus(state="needs_operator")

        # Session line exists but we do not recognize the status keyword.
        # Treat as still running rather than guessing a terminal state.
        return SessionStatus(state="running")

    # ------------------------------------------------------------------ #
    # ExecutorAdapter: collect
    # ------------------------------------------------------------------ #

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        """Retrieve the patch from a completed session via `jules remote pull`.

        Runs WITHOUT --apply: this only fetches the patch text. The patch is
        saved to dest_path and returned as patch_text. It is never applied or
        committed by this method.
        """
        session_id = session_ref.session_id
        cmd = [
            self.jules_bin, "remote", "pull",
            "--session", session_id,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return PatchResult(success=False, error=f"jules pull timed out after {self.timeout}s")
        except FileNotFoundError:
            return PatchResult(success=False, error=f"jules binary not found: {self.jules_bin}")
        except Exception as e:
            return PatchResult(success=False, error=f"jules pull failed: {e}")

        if result.returncode != 0:
            return PatchResult(
                success=False,
                error=(result.stderr or result.stdout or "jules remote pull failed").strip(),
            )

        patch_text = result.stdout or ""
        try:
            dest_path = Path(dest_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(patch_text)
        except Exception as e:
            return PatchResult(
                success=False,
                patch_text=patch_text,
                error=f"failed to write patch to {dest_path}: {e}",
            )

        return PatchResult(
            success=True,
            patch_text=patch_text,
            patch_path=str(dest_path),
        )

    # ------------------------------------------------------------------ #
    # ExecutorAdapter: cancel
    # ------------------------------------------------------------------ #

    def cancel(self, session_ref: SessionRef) -> bool:
        """Best-effort cancellation. Jules CLI does not yet support cancel."""
        return False
