# gddp-runtime

Execution and orchestration code for the Graph-Driven Agentic Development (GDDP) system.

This repository is the runtime/control-plane layer. It reads human-owned project
truth from `gddp-config`, dispatches bounded work to executors, persists runtime
state and receipts, and stops at review.

It does not define project truth, and it does not automatically mutate graph
state on the return path.

---

## Boundary

- `gddp-config`: human-owned project truth
- `gddp-runtime`: execution machinery
- executors/agents: produce work and structured receipts
- human review: decides whether graph truth changes

Current return-path rule:

- merged PRs and executor outputs may create structured receipts
- runtime may move jobs into review-needed state
- runtime may not write completion into `gddp-config`

---

## Structure

| Path | Purpose |
|---|---|
| `scripts/runtime/heartbeat/` | Canonical graph-driven heartbeat runner |
| `scripts/runtime/return_router.py` | Receipt-only merged-PR return handling |
| `scripts/runtime/results_store.py` | Receipt persistence into the canonical `results` table |
| `scripts/init_db.py` | SQLite schema initialization |
| `scripts/intake_server.py` | Webhook intake and event normalization |
| `scripts/dry_run.py` | Local dry-run flow for practicing the runtime loop |
| `scripts/rollback.py` | Job rollback utility |
| `scripts/adapters/` | Executor adapters |
| `deploy/` | Deployment scripts and operator runbooks |

---

## Manual Review Workflow

Runtime stops at receipts. When a job lands in `awaiting_review`, the operator
reviews the `results` row plus job artifacts and then takes exactly one manual
action:

- `accept`: update graph truth manually in `gddp-config`
- `retry`: re-dispatch the job from persisted state
- `block`: leave graph truth unchanged and record the blocker outside runtime
- `defer`: leave the receipt/job in review-needed state for later
- `reopen` or `supersede`: revisit or replace the work later if downstream evidence invalidates it

There is no automatic node advancement, automatic review, or automatic graph
writeback in this phase.

---

## Replay

Replay reuses persisted runtime state rather than re-receiving or re-classifying
events.

- `python3 -m runtime.replay --result-id <result-id>`
  Recreates the receipt/state routing for a recorded return event.
- `python3 -m runtime.replay --job-id <job-id>`
  Re-dispatches a specific job after explicit operator confirmation.

---

## Local Development

Initialize the DB:

```bash
python3 scripts/init_db.py
```

Run the dry run:

```bash
python3 scripts/dry_run.py
```

Run the heartbeat:

```bash
python3 -m runtime.heartbeat.runner \
  --project <project-id> \
  --repo <owner/repo> \
  --config-path /path/to/gddp-config
```

---

## Operator Notes

Environment-specific deployment details, machine paths, and service procedures
belong in the operator runbook, not in this README.

See:

- [deploy/BIGPI_RUNBOOK.md](/work/repos/gddp-runtime/deploy/BIGPI_RUNBOOK.md)

---

## Related Repos

| Repo | Purpose |
|---|---|
| `gddp-config` | Schemas, graphs, templates, doctrine |
| `gddp-runtime` | Runtime/orchestration layer |
| project repos | Where executor work and PRs actually happen |

---

## Phase Freeze

This phase is intentionally frozen at receipt routing plus human review.

Do not add:

- richer graph states
- auto-review logic
- automatic return-path graph mutation
- fully autonomous graph state machines
