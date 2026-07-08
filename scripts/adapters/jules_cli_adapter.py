"""
jules_cli_adapter.py — Option B dispatch adapter (stub).

Dispatches a job to Jules via the Jules Tools CLI.
Swap this in once Jules CLI is installed and its interface is confirmed stable.

Install: pip install jules-tools  (or brew / npm — verify current method)
Check:   jules --version

This adapter is NOT active in Phase 3. It is a stub for Phase 4+.
"""

from dataclasses import dataclass


@dataclass
class DispatchResult:
    success: bool
    session_id: str | None
    error: str | None


class JulesCliAdapter:
    """
    Dispatches a job to Jules via the Jules CLI.
    More GDDP-pure than Option A: the runtime decision loop explicitly dispatches the job packet
    rather than relying on GitHub label events to trigger Jules.
    """

    def __init__(self, repo: str):
        self.repo = repo

    def dispatch(self, job: dict) -> DispatchResult:
        # Stub — not implemented until Jules CLI is installed and interface confirmed
        raise NotImplementedError(
            "JulesCliAdapter is not active in Phase 3.\n"
            "Install Jules CLI, verify `jules --version`, then implement dispatch here.\n"
            "Expected interface: jules remote new --repo <repo> --session '<instructions>'"
        )

    def poll(self, session_id: str) -> dict:
        raise NotImplementedError("JulesCliAdapter not implemented yet.")

    def collect_result(self, session_id: str) -> dict:
        raise NotImplementedError("JulesCliAdapter not implemented yet.")
