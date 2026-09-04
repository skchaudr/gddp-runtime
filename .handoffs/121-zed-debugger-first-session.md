# 121 — Zed first session (VM turnover)

Date: 2026-09-04 · gddp-runtime `main` `4f445a6` · khoj-38 will turn over

## Situation
Zed debug profiles live in this repo (`.zed/debug.json`). The beginner kit does **not**: it is on Sab Air at `~/docs/zed-debugging/` (docs `8e9272b`). Interactive `subagent_wait` is fleet-disabled; parents return and resume on completion.

## First live session
1. Open `~/docs/zed-debugging/zed-debugging-visual-guide.html`, then this repo in Zed.
2. Select project `.venv` in the status bar.
3. Breakpoint `scripts/runtime/verification/retry_budget.py:96` (`has_evidence = …`).
4. F4 → `GDDP: five-minute debugger tour` (one pytest node).
5. Coach **one UI action**, wait for what Sab sees, then the next.

## Help I will need
**Pre-run:** confirm `.venv` is selected; re-read line 96 before Start (insertions shift it); F-keys may need Fn; empty last-failed cache → pytest exit 5 is expected.
**During:** if the stop/locals/stack mismatch the worksheet, Stop and recover — do not keep stepping. Never invoke the heartbeat runner directly.

Resume: `~/docs/zed-debugging/README.md` · profile `GDDP: five-minute debugger tour`.
