"""Direct Jules REST API executor adapter."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from adapters.executor_protocol import (
    DispatchResult,
    NodePacket,
    PatchResult,
    SessionRef,
    SessionStatus,
)
from adapters.jules_cli_adapter import JulesCliAdapter

_DEFAULT_BASE_URL = "https://jules.googleapis.com/v1alpha"


class JulesApiAdapter:
    """Dispatch, poll, and collect Jules sessions through the REST API."""

    def __init__(
        self,
        repo: str,
        *,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        starting_branch: str | None = None,
        timeout: int = 30,
    ):
        self.repo = repo
        self.api_key = api_key or self._load_api_key()
        self.base_url = base_url.rstrip("/")
        self.starting_branch = (
            starting_branch
            or os.environ.get("GDDP_JULES_STARTING_BRANCH")
            or "main"
        )
        self.timeout = timeout

    def dispatch(self, packet: NodePacket) -> DispatchResult:
        """Create one asynchronous Jules API session."""
        if not self.api_key:
            return DispatchResult(
                success=False,
                error=(
                    "Jules API key unavailable; set JULES_API_KEY or "
                    "GDDP_JULES_KEY_CMD"
                ),
            )

        try:
            source_name = self._find_source()
            # Reuse the proven neutral packet rendering without invoking the CLI.
            prompt = JulesCliAdapter(self.repo)._build_session_instructions(packet)
            session = self._request_json(
                "POST",
                "/sessions",
                {
                    "prompt": prompt,
                    "title": packet.title or f"GDDP: {packet.node_id}",
                    "sourceContext": {
                        "source": source_name,
                        "githubRepoContext": {
                            "startingBranch": self.starting_branch,
                        },
                    },
                    # Without automationMode Jules has no way to land work, so
                    # it stops and asks whether to commit. AUTO_CREATE_PR gives
                    # the session a terminal action and yields a real PR.
                    "automationMode": "AUTO_CREATE_PR",
                },
            )
        except RuntimeError as exc:
            return DispatchResult(success=False, error=str(exc))

        session_id = session.get("id")
        if not isinstance(session_id, str) or not session_id:
            name = session.get("name")
            if isinstance(name, str) and name.startswith("sessions/"):
                session_id = name.split("/", 1)[1]
        if not isinstance(session_id, str) or not session_id:
            return DispatchResult(
                success=False,
                error="Jules API created a session without a usable ID",
            )
        return DispatchResult(
            success=True,
            session_ref=SessionRef(executor="jules_api", session_id=session_id),
        )

    def status(self, session_ref: SessionRef) -> SessionStatus:
        """Map documented Jules session states to the neutral lifecycle."""
        try:
            session = self._request_json(
                "GET", f"/sessions/{self._quoted_session_id(session_ref)}"
            )
        except RuntimeError as exc:
            return SessionStatus(state="poll_error", error=str(exc))

        state = str(session.get("state") or "").upper()
        if state == "QUEUED":
            return SessionStatus(state="dispatched")
        if state in {"PLANNING", "IN_PROGRESS"}:
            return SessionStatus(state="running")
        # A question is answerable over sendMessage; a paused or plan-gated
        # session is not. Collapsing them is what made needs_operator terminal.
        if state == "AWAITING_USER_FEEDBACK":
            return SessionStatus(state="awaiting_reply")
        if state in {"AWAITING_PLAN_APPROVAL", "PAUSED"}:
            return SessionStatus(state="needs_operator")
        if state == "COMPLETED":
            return SessionStatus(state="completed")
        if state == "FAILED":
            return SessionStatus(
                state="failed",
                error=str(session.get("error") or "Jules API session failed"),
            )
        return SessionStatus(
            state="poll_error",
            error=f"unrecognized Jules API session state: {state or 'missing'}",
        )

    def collect(self, session_ref: SessionRef, dest_path: Path) -> PatchResult:
        """Collect the final Jules ChangeSet artifact as a base-bound patch."""
        session_id = self._quoted_session_id(session_ref)
        page_token = ""
        patches: list[tuple[str | None, str]] = []

        try:
            while True:
                query = {"pageSize": "100"}
                if page_token:
                    query["pageToken"] = page_token
                response = self._request_json(
                    "GET",
                    f"/sessions/{session_id}/activities?"
                    f"{urllib.parse.urlencode(query)}",
                )
                for activity in response.get("activities", []):
                    if not isinstance(activity, dict):
                        continue
                    for artifact in activity.get("artifacts", []):
                        if not isinstance(artifact, dict):
                            continue
                        change_set = artifact.get("changeSet")
                        if not isinstance(change_set, dict):
                            continue
                        git_patch = change_set.get("gitPatch")
                        if not isinstance(git_patch, dict):
                            continue
                        patch_text = git_patch.get("unidiffPatch")
                        if isinstance(patch_text, str) and patch_text:
                            base_commit = git_patch.get("baseCommitId")
                            patches.append(
                                (
                                    base_commit
                                    if isinstance(base_commit, str)
                                    else None,
                                    patch_text,
                                )
                            )
                next_token = response.get("nextPageToken")
                if not isinstance(next_token, str) or not next_token:
                    break
                page_token = next_token
        except RuntimeError as exc:
            return PatchResult(success=False, error=str(exc))

        if not patches:
            return PatchResult(
                success=False,
                error="Jules API completed without a git patch artifact",
            )

        base_commit_sha, patch_text = patches[-1]
        destination = Path(dest_path)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(patch_text)
        except OSError as exc:
            return PatchResult(
                success=False,
                patch_text=patch_text,
                base_commit_sha=base_commit_sha,
                error=f"failed to write Jules API patch: {exc}",
            )

        return PatchResult(
            success=True,
            patch_text=patch_text,
            patch_path=str(destination),
            base_commit_sha=base_commit_sha,
        )

    def reply(self, session_ref: SessionRef, message: str) -> bool:
        """Answer a session parked in AWAITING_USER_FEEDBACK."""
        try:
            self._request_json(
                "POST",
                f"/sessions/{self._quoted_session_id(session_ref)}:sendMessage",
                {"prompt": message},
            )
        except RuntimeError:
            return False
        return True

    def cancel(self, session_ref: SessionRef) -> bool:
        """The documented API has no non-destructive cancel operation."""
        return False

    def _find_source(self) -> str:
        """Resolve the API source by its owner/repo fields; never guess its ID."""
        try:
            owner, repo_name = self.repo.split("/", 1)
        except ValueError as exc:
            raise RuntimeError(f"invalid Jules repository name: {self.repo!r}") from exc

        page_token = ""
        while True:
            query = {"pageSize": "100"}
            if page_token:
                query["pageToken"] = page_token
            response = self._request_json(
                "GET", f"/sources?{urllib.parse.urlencode(query)}"
            )
            for source in response.get("sources", []):
                if not isinstance(source, dict):
                    continue
                github_repo = source.get("githubRepo")
                if (
                    isinstance(github_repo, dict)
                    and github_repo.get("owner") == owner
                    and github_repo.get("repo") == repo_name
                    and isinstance(source.get("name"), str)
                ):
                    return source["name"]
            next_token = response.get("nextPageToken")
            if not isinstance(next_token, str) or not next_token:
                break
            page_token = next_token
        raise RuntimeError(f"Jules API source not found for {self.repo}")

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> dict:
        if not self.api_key:
            raise RuntimeError("Jules API key unavailable")
        body = (
            json.dumps(payload, separators=(",", ":")).encode()
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Jules API HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Jules API request failed: {exc}") from exc
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Jules API returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("Jules API returned a non-object response")
        return decoded

    @staticmethod
    def _quoted_session_id(session_ref: SessionRef) -> str:
        return urllib.parse.quote(session_ref.session_id, safe="")

    @staticmethod
    def _load_api_key() -> str:
        direct = os.environ.get("JULES_API_KEY", "").strip()
        if direct:
            return direct
        command = os.environ.get("GDDP_JULES_KEY_CMD", "").strip()
        if not command:
            return ""
        try:
            parts = shlex.split(command)
            if not parts:
                return ""
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""
