# Current Mission: Definition of Done

Date: 2026-07-16

## Outcome

Recover the two dispatched runtime nodes, land only evidence-backed fixes, finish
evaluator hardening, then define the next executor boundary. GDDP remains the
intent and graph-integrity layer; only Sab changes graph truth.

## Momentum Contract

- Root owns the plan, decisions, and conversation. GPT-5.3 Codex Spark handles
  bounded work after its success signal is defined.
- Workers run in the background and report results, not traces. Independent work
  runs concurrently; future architecture never blocks current recovery.
- Ordinary code and Git work proceeds. Live/system actions and merges stop at an
  explicit human gate.
- Every item ends in evidence, a clean pushed commit, or a recorded rejection.

## Checklist

- [x] **Foundation recovered:** concurrent dispatch proved; ID collisions, SQLite
  contention, and GitHub auth fixed; PR #107/#108 independently audited.
- [x] **PR #108 - state consistency:** undo `f01d5ba`'s regression; ensure a failed
  job cannot retain `queue_state=running`; restore direct tests and truthful
  artifacts; focused/full tests pass; commit and push for Sab's merge decision.
  Verified at `1f1e16d` (`2` focused and `269` full tests passed).
- [ ] **PR #107 - crash recovery:** reconfirm tests; with Sab's approval run the
  intake-only live drill; record PID replacement and `/health` HTTP 200 without
  dispatching unrelated events; commit and push for Sab's merge decision.
- [ ] **Land and reconcile:** Sab accepts/rejects both PRs; accepted work lands on
  main; full tests pass; main equals `origin/main`; after fresh inspection and
  approval, sanctioned SQL reconciles only stale runtime rows. Sab alone updates
  `gddp-config` node status.
- [ ] **Evaluator hardening:** update `evaluator-hardening` from decided main;
  preserve completed P1 fixes; resolve or explicitly defer known P2 gaps; pass
  focused/full tests; commit and push for Sab's merge decision.
- [ ] **Executor boundary:** accept a small contract for durable sessions,
  transcripts, message/pause/resume/cancel, structured results, model/effort and
  mutation policies, retries, and recovery. Git remains the artifact layer;
  Jules/relay remain optional. Convert the decision into graph node(s) before code.

## Mission Complete

All boxes checked; relevant branches and main clean and pushed; claims link to
reproducible evidence; live state reconciled; current handoff names no hidden work;
and no agent changed human-owned graph truth.
