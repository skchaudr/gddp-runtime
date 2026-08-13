# MWP Remap — gddp-runtime against the Model Workspace Protocol shape

Date: 2026-08-12 · Post-demolition state (work orders 089–093) · main @ 21c4ac2

MWP shape: numbered folders = stages · markdown = role/context · local scripts =
mechanical work · one agent reads the right file at the right moment · human
reviews each step. GDDP adds exactly one thing MWP doesn't have, and it's the
thing the project exists for: **the evaluator verdict as evidence before human
acceptance**. That piece was earned. Almost everything else that felt
incompatible was already stripped or demoted in the 089 demolition.

## The loop that survives (MWP-shaped, already working)

1. **Packet** — node yaml/markdown carries role, context, criteria (the markdown file)
2. **Dispatch** — one agent executes via pi transport (direct, not mediated)
3. **Receipt** — `gddp_node_receipt.py` + results store (the stage folder)
4. **Evaluate** — two-lane verification → verdict receipt (evidence, not truth)
5. **Human** — `gddp node browse`: c=accept, r=reject→retry with findings, d=defer

Proven: 22-node dogfood run, 4.5h unattended, 2026-08-11.

## Tag map — every top-level entry

**CORE LOOP** (the product — touch these, keep them lean)

| Path | Role |
|---|---|
| `AGENTS.md` | Operating contract + doctrine; already encodes the failure pattern |
| `PROJECT-BRIEF.md` | Intent anchor |
| *Ideally*: `docs/GDDP-becomes-small-and-real.md` | Doctrine: GDDP constrains/verifies the loop, doesn't rebuild it |
| *Ideally*: `docs/Tests-can-fail-nodes-can-pass.md` | Doctrine: only human acceptance is graph truth |
| `scripts/jobs_status.py` | Job/queue state backend (mechanical work, script-shaped) |
| `scripts/gddp_node_receipt.py` | The receipt — unit of returned evidence |
| `scripts/runtime/verification/` | The evaluator. The one justified thing MWP lacks. |
| `scripts/runtime/results_store.py` | Durable return of receipts/verdicts |
| `scripts/runtime/return_router.py` | Routes results back to the graph |

**JUSTIFIED SUPPORT** (earned by the dogfood run — keep, freeze feature growth)

| Path | Role |
|---|---|
| `scripts/runtime/heartbeat/` | The unattended runner; justified by overnight runs only |
| `scripts/runtime/graph_updater.py`, `repo_resolver.py` | Frontier bookkeeping |
| `scripts/adapters/executor_protocol.py`, `pi_rpc_adapter.py`, `local_subprocess_adapter.py`, `session_prompt.py` | The pi transport (the one executor you actually use) |
| `scripts/adapters/mission_*` (post-demolition) | Droid transport, demoted to evidence-collection; keep as one spare transport |
| `scripts/init_db.py`, `db/` | State schema + sqlite |
| `scripts/node_status_history.py` | Provisional-status audit trail |
| `deploy/mini-heartbeat/` | The armed control-plane kit (the only sanctioned entrypoint) |
| `LICENSE`, `pytest.ini`, `requirements.txt`, `setup.sh` | Plumbing |

**PREMATURE — FREEZE** (exists, harmless if quiet, no new investment)

| Path | Why |
|---|---|
| `scripts/intake_server.py` | GitHub webhook intake — the loop you run doesn't enter through webhooks |
| `scripts/adapters/jules_*` | Second external executor transport, unused in practice |
| `deploy/rig1-heartbeat/`, `deploy/deploy.sh` | Multi-host ambition ahead of single-host proof |
| `scripts/rollback.py`, `scripts/export_evaluations.py` | Built ahead of need; keep only if a node demands it |
| `scripts/runtime/decision_loop/` (empty), `spike/` | Exploratory; archive |
| `graphify-out/` | Regenerable analysis artifact |
| `TOPOLOGY.md` | Describes the bigger machine; rewrite to describe the small one |

**ARCHIVE** (dogfood/scratch artifacts — history value only; move under `_archive/` or `docs/archive/`)

`scripts/echo.py`, `decision.md`, `result-summary.md`, `readiness-report-2026-07-18.md`,
`arxiv_search.py`, `search_github.py`, `missions/001-harden-semantic-verification.md`,
most of `docs/` (plans, postmortems, reckoning docs — keep in git history, out of the top level).

## Keep this repo or start fresh?

**Keep this repo.** The fresh-repo instinct is right about the *feeling* and
wrong about the *state*: the demolition already removed the machinery that made
this incompatible with you, and the surviving core ran a real 22-node loop last
week. A greenfield repo would (a) lose the evaluator — the one piece a
folder-of-markdown can never give you, (b) strand the 22-node dogfood review
queue and 9-node pi-harness queue waiting on your c/r/d, and (c) invite the
exact failure pattern on record: rebuilding ahead of justification, this time
with a cleaner slate and the same appetite.

The cheaper move that gets you the MWP feeling inside this repo:

1. **`LOOP.md` at root** — one page, the five-step loop above, written as the
   protocol. This becomes the file you (and agents) actually orient by; the
   repo *is* the loop, everything else is appendix.
2. **Archive sweep** — move the ARCHIVE rows under `docs/archive/` +
   `scripts/_archive/` (pattern already exists in `deploy/_archive`).
3. **Freeze list in AGENTS.md** — one line: intake server, jules adapters,
   rig1 deploy are frozen infrastructure, revived only by a node that names them.
4. Then bring your actual workflows: each becomes a small graph of packets run
   through the loop — the runtime stays the drift detector around *your*
   folders-of-markdown, not a replacement for them.

Your workflows, when you write them down, are the missing input: they decide
whether anything on the FREEZE list earns revival, and whether the loop needs
anything it doesn't have. The map above is the menu; your workflows are the order.
