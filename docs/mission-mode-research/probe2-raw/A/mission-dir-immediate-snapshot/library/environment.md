# Environment

Environment variables, external dependencies, and setup notes.

**What belongs here:** Required env vars, external API keys/services, dependency quirks, platform-specific notes.
**What does NOT belong here:** Service ports/commands (use `services.yaml`).

---

## GDDP_RECEIPTS_PATH

- **Value:** `/Users/sab-mini/probe2-gddp/receiptsA.jsonl`
- **Set in:** the shell environment; inherited by worker sessions.
- **Used by:** `gddp-node-receipt` — the tool hard-fails if this variable is unset.
- **The file does not exist yet.** It is created on first append by the receipt tool.
- **Critical:** This file is append-only. It must end up with exactly 8 lines, one per node, in dictated order. Never hand-edit, never rewrite, never run the receipt tool outside the per-node protocol.

## gddp-node-receipt

- **Location:** `/Users/sab-mini/probe2-gddp/bin/gddp-node-receipt` (on `PATH`)
- **Interface:** `gddp-node-receipt --node-id <id> --base <sha> --result <sha>`
- **Behavior:** Appends one JSON line to `$GDDP_RECEIPTS_PATH`. The line is `json.dumps(record, sort_keys=True)` — canonical, alphabetical keys. Records: `node_id`, `base`, `result`, `git_head` (live `git rev-parse HEAD`), `git_branch` (live), `git_toplevel` (live), `timestamp_utc` (ISO-8601 UTC).
- **Critical ordering:** Must be invoked AFTER the commit (so `git_head == result`) and FROM the worktree root (so `git_toplevel` is correct).

## Python / pytest

- `python3` 3.14.6 at `/opt/homebrew/bin/python3`
- `pytest` 9.1.1 via `python3 -m pytest`
- No virtual environment needed; no `requirements.txt`; stdlib + pytest only.

## Git

- Git 2.54.0
- Worktree: `/Users/sab-mini/probe2-gddp/repoA-wt-probe2a` (branch `probe2a`)
- Shared object store with `/Users/sab-mini/probe2-gddp/repoA/.git` — repoA and the worktree share objects and refs.
- Baseline: `a96356a50f173d98731b9944e65ff593c81333f0` (matches `baseA.sha`)

## jq

- Available at `/opt/homebrew/bin/jq` — used by validators for receipt ledger inspection.
