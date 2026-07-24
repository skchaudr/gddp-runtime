"""local_agent_executor.py — Real GDDP_LOCAL_SUBPROCESS_ARGV target.

Reads a NodePacket JSON document on stdin, creates an isolated git worktree at
the packet's expected_base_commit_sha (or GDDP_EXPECTED_BASE_COMMIT_SHA / HEAD),
runs a pinned agent CLI inside that worktree only, then emits `git diff` of the
worktree changes to stdout and removes the worktree.

The live repo tree is never used as the agent cwd. The prompt includes the
absolute path to the live queue.db for read-only inspection; any reconcile SQL
must be written into decision.md, never executed against the live DB by the
agent.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Pin: Grok CLI non-interactive single-shot with auto-approve.
# Override whole argv template via GDDP_AGENT_ARGV (JSON array). Use
# {worktree} and {prompt_file} placeholders.
_DEFAULT_AGENT_ARGV = (
    "grok",
    "--cwd",
    "{worktree}",
    "--always-approve",
    "--permission-mode",
    "bypassPermissions",
    "--prompt-file",
    "{prompt_file}",
)

_REPO_ENV = "GDDP_REPO_PATH"
_BASE_ENV = "GDDP_EXPECTED_BASE_COMMIT_SHA"
_DB_ENV = "GDDP_QUEUE_DB"
_AGENT_ARGV_ENV = "GDDP_AGENT_ARGV"
_WORKTREE_PREFIX = "gddp-agent-wt-"


def default_repo_path() -> Path:
    """Repo root: env, else parent of scripts/."""
    configured = os.environ.get(_REPO_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def default_queue_db(repo: Path) -> Path:
    configured = os.environ.get(_DB_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (repo / "db" / "queue.db").resolve()


def load_packet(raw: str) -> dict[str, Any]:
    """Parse stdin JSON into a plain dict. Raises ValueError on bad shape."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("packet JSON must be an object")
    required = (
        "job_id",
        "node_id",
        "title",
        "goal",
        "execution_attempt_id",
        "attempt_index",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"packet missing required fields: {', '.join(missing)}")
    return data


def resolve_base_commit(packet: Mapping[str, Any], repo: Path) -> str:
    """Base SHA from packet, env, or live HEAD."""
    for candidate in (
        packet.get("expected_base_commit_sha"),
        os.environ.get(_BASE_ENV),
    ):
        if candidate:
            return str(candidate).strip()
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"could not resolve HEAD in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _flatten(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        # Prefer common criterion shapes.
        for key in ("criterion", "id", "text", "summary"):
            if key in value and value[key] is not None:
                rest = {
                    k: v
                    for k, v in value.items()
                    if k != key and v is not None
                }
                if rest:
                    return f"{value[key]} ({rest})"
                return str(value[key])
        return str(dict(value))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return ", ".join(_flatten(item) for item in value)
    return str(value)


def build_prompt(
    packet: Mapping[str, Any],
    *,
    worktree: Path,
    queue_db: Path,
) -> str:
    """Build the agent instruction from packet fields."""
    constraints = packet.get("constraints") or ()
    criteria = packet.get("acceptance_criteria") or ()
    artifacts = packet.get("required_artifacts") or ()

    constraints_text = "\n".join(f"- {_flatten(item)}" for item in constraints) or "- (none)"
    criteria_text = "\n".join(f"- [ ] {_flatten(item)}" for item in criteria) or "- (none)"
    artifacts_text = "\n".join(f"- `{item}`" for item in artifacts) or "- (none listed)"

    findings_section = ""
    findings = packet.get("previous_findings")
    if isinstance(findings, Mapping) and findings:
        findings_section = (
            f"\n## Previous Attempt Findings (attempt {packet.get('attempt_index')})\n"
            f"```json\n{json.dumps(findings, indent=2, sort_keys=True)}\n```\n"
        )

    title = packet.get("title") or "GDDP task"
    why = packet.get("why") or ""

    return f"""# [GDDP] {title}

You are the local executor for one GDDP node attempt. Work ONLY in this
directory (isolated worktree):

    {worktree}

Do not edit any other checkout of the repository.

## Goal
{packet.get("goal", "")}

## Why
{why}

## Constraints
{constraints_text}

## Acceptance Criteria
{criteria_text}

## Required Artifacts
{artifacts_text}
{findings_section}
## Live database (READ-ONLY)

Absolute path to the live queue DB (inspect with `sqlite3` SELECT only):

    {queue_db}

Rules:
- You may READ the live DB to diagnose state.
- You must NOT run UPDATE/INSERT/DELETE/REPLACE against the live DB.
- Any reconcile SQL belongs in `decision.md` as a documented, reversible step
  for a human to run later — never execute it yourself against the live DB.

## Deliverables in this worktree

1. Implement the fix for the goal/criteria.
2. Write `decision.md` with root cause, evidence, and any manual SQL.
3. Write `result-summary.md` summarizing what changed and why.
4. Include a self-run pytest transcript in `decision.md` when relevant
   (`python3 -m pytest -q scripts`); `.venv/bin/python` may be missing in
   worktrees — use `python3`.
5. Stop when the worktree changes satisfy the criteria as far as possible.

## Identity
- node: {packet.get("node_id")}
- job: {packet.get("job_id")}
- attempt: {packet.get("attempt_index")}
- execution_attempt_id: {packet.get("execution_attempt_id")}
"""


def agent_argv(worktree: Path, prompt_file: Path) -> list[str]:
    """Pinned agent CLI argv (env override allowed)."""
    raw = os.environ.get(_AGENT_ARGV_ENV)
    if raw:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{_AGENT_ARGV_ENV} must be a JSON argv array") from exc
        if not isinstance(decoded, list) or not decoded:
            raise ValueError(f"{_AGENT_ARGV_ENV} must be a non-empty JSON argv array")
        template = [str(item) for item in decoded]
    else:
        template = list(_DEFAULT_AGENT_ARGV)

    mapping = {
        "{worktree}": str(worktree),
        "{prompt_file}": str(prompt_file),
    }
    return [_expand(item, mapping) for item in template]


def _expand(item: str, mapping: Mapping[str, str]) -> str:
    out = item
    for key, value in mapping.items():
        out = out.replace(key, value)
    return out


def create_worktree(repo: Path, base_sha: str) -> Path:
    tmpdir = tempfile.mkdtemp(prefix=_WORKTREE_PREFIX)
    # git worktree add wants to create the path itself
    os.rmdir(tmpdir)
    proc = subprocess.run(
        ["git", "worktree", "add", "--detach", tmpdir, base_sha],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed at {base_sha}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return Path(tmpdir)


def remove_worktree(repo: Path, path: Path) -> None:
    proc = subprocess.run(
        ["git", "worktree", "remove", str(path), "--force"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode == 0:
        return
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(
        ["git", "worktree", "prune", "--expire", "now"],
        cwd=str(repo),
        capture_output=True,
        timeout=15,
        check=False,
    )


def emit_diff(worktree: Path) -> str:
    """Stage all worktree changes and return unified diff text."""
    add = subprocess.run(
        ["git", "add", "-A"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if add.returncode != 0:
        raise RuntimeError(f"git add failed: {add.stderr.strip()}")
    diff = subprocess.run(
        ["git", "diff", "--cached", "--binary"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if diff.returncode != 0:
        raise RuntimeError(f"git diff failed: {diff.stderr.strip()}")
    return diff.stdout


def run_agent(argv: Sequence[str], worktree: Path) -> int:
    """Run the pinned agent. Stdout/stderr go to stderr so stdout stays patch-only."""
    print(f"[local_agent_executor] running: {argv!r}", file=sys.stderr)
    proc = subprocess.run(
        list(argv),
        cwd=str(worktree),
        stdin=subprocess.DEVNULL,
        timeout=None,
        check=False,
    )
    return proc.returncode


def run(
    packet_raw: str,
    *,
    repo: Path | None = None,
    run_agent_fn=run_agent,
) -> int:
    """Full pipeline. Returns process exit code. Diff printed to stdout."""
    repo = repo or default_repo_path()
    packet = load_packet(packet_raw)
    base_sha = resolve_base_commit(packet, repo)
    queue_db = default_queue_db(repo)

    worktree: Path | None = None
    try:
        worktree = create_worktree(repo, base_sha)
        prompt = build_prompt(packet, worktree=worktree, queue_db=queue_db)
        prompt_file = worktree / ".gddp-agent-prompt.md"
        prompt_file.write_text(prompt)

        argv = agent_argv(worktree, prompt_file)
        agent_code = run_agent_fn(argv, worktree)
        if agent_code != 0:
            print(
                f"[local_agent_executor] agent exited {agent_code}",
                file=sys.stderr,
            )
            # Still emit whatever diff exists so collect can salvage partial work.

        patch = emit_diff(worktree)
        # Do not ship the prompt file as part of the node patch.
        if ".gddp-agent-prompt.md" in patch:
            # Re-diff excluding the prompt file.
            subprocess.run(
                ["git", "reset", "HEAD", "--", ".gddp-agent-prompt.md"],
                cwd=str(worktree),
                capture_output=True,
                timeout=15,
                check=False,
            )
            prompt_file.unlink(missing_ok=True)
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(worktree),
                capture_output=True,
                timeout=15,
                check=False,
            )
            patch = emit_diff(worktree)

        sys.stdout.write(patch)
        if not patch.strip():
            print(
                "[local_agent_executor] warning: empty diff after agent run",
                file=sys.stderr,
            )
            return 1 if agent_code != 0 else 0
        return 0 if agent_code == 0 else agent_code
    finally:
        if worktree is not None:
            remove_worktree(repo, worktree)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-prompt",
        action="store_true",
        help="Parse stdin packet, print prompt to stdout, do not run agent",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help=f"Live repo path (default: {_REPO_ENV} or scripts/..)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    raw = sys.stdin.read()
    if args.dry_prompt:
        packet = load_packet(raw)
        repo = args.repo or default_repo_path()
        queue_db = default_queue_db(repo)
        # Worktree path is hypothetical for dry-prompt.
        fake_wt = Path("/tmp/gddp-agent-wt-dry")
        sys.stdout.write(build_prompt(packet, worktree=fake_wt, queue_db=queue_db))
        return 0
    return run(raw, repo=args.repo)


if __name__ == "__main__":
    raise SystemExit(main())
