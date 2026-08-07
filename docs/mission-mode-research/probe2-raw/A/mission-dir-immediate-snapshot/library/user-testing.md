# User Testing

Testing surface, required testing skills/tools, and resource cost classification per surface.

---

## Validation Surface

This mission has **no interactive surface** — no UI, no CLI, no API, no TUI. The only "user testing" is read-only inspection of the two append-only chains the mission produces:

1. **Git chain** — `git log`, `git reflog`, `git show`, `git diff-tree` to inspect commits, trailers, linearity, and file scope.
2. **Receipt ledger** — `jq`, `wc`, `python3` to inspect `receiptsA.jsonl` for line count, JSON validity, canonical serialization, contiguity, and cross-consistency with the git chain.
3. **Code behavior** — `python3 -c` for numeric probes, monkeypatch delegation checks, and AST call-graph verification. `python3 -m pytest -q` for the test suite.

**Tools used:** `python3`, `pytest`, `git`, `jq`, `diff`, file reads. No `agent-browser`, no `tuistory`.

## Validation Prerequisites

| Prerequisite | How verified | Allowlist needed? |
|---|---|---|
| `python3` 3.14.6 | `python3 --version` | No |
| `pytest` 9.1.1 | `python3 -m pytest --version` | No |
| `gddp-node-receipt` on PATH | `command -v gddp-node-receipt` | No |
| `GDDP_RECEIPTS_PATH` set | `env` — inherited from shell | No |
| `jq` for ledger inspection | `jq --version` | No |
| Git worktree clean on `probe2a` | `git status`, `git worktree list` | No |
| Baseline suite green | `python3 -m pytest -q` → 1 passed | No |

All prerequisites verified during mission readiness check. No credentials, no network, no external services.

## Validation Concurrency

- **Surface:** code/ledger inspection (no running services)
- **Resource per validator:** negligible — a Python process + git commands, <100 MB RAM, <1s execution
- **Machine:** 8 CPU cores, 16 GB RAM, baseline usage low
- **Max concurrent validators:** 5 (capped by tool limit; resources are not a constraint here)
- **Rationale:** no dev server, no database, no browser. Each validator is a few shell commands. Concurrency is limited only by the tool's own cap.

## Critical Constraint for Validators

**Validators must NEVER run `gddp-node-receipt`**, not even with a redirected `GDDP_RECEIPTS_PATH`. The ledger must contain exactly 8 lines. A stray receipt is unrecoverable. Validators must also never commit, never modify `calc.py`/`test_calc.py`, and never create fixtures or seed data. Validation is strictly read-only. See `AGENTS.md` → Testing & Validation Guidance.
