# GDDP — Brief

Graph-driven agentic development control plane. Turns projects into maps of work; agents traverse them without losing human control.

## Narrative

GDDP is a two-repo system for preserving agentic forward momentum by turning a software project into an explicit,
traversable map of work, then driving agents across that map with a human
review gate feature by feature, mutation by mutation. `gddp-config` is the source of truth —
schemas, graphs, nodes, constraints, and acceptance criteria as declarative
YAML. `gddp-runtime` is the execution engine: it reads that truth, runs a
heartbeat decision loop, dispatches bounded jobs to executors (Jules via
GitHub issues today, but agent agnostic), records jobs/results/receipts in SQLite, and converts merged PRs into review receipts — never silently rewriting the graph. The
inversion that matters: the runtime is forbidden from mutating config
truth; `scripts/runtime/graph_updater.py` exists only as a disabled stub.
Graph state moves only after human review. GDDP is one of three portfolio
pieces (with .pi and MyAPI-rebuild) demonstrating 2026 agent-era
infrastructure built solo.

## Ground state

Pulled from `graphify-out/GRAPH_REPORT.md` (2026-06-18, commit `bb1997ed`).

- **Languages:** Python 3.11+ (runtime — stdlib + Flask), YAML (config graph
  truth + schemas), Bash (`deploy/setup.sh`, `deploy/deploy.sh`), Markdown
- **Graph:** 539 nodes · 833 edges · 48 communities (39 shown) · 71 files ·
  ~32.5k words · 97% EXTRACTED / 3% INFERRED
- **Top god nodes:** GraphReader (19), handle_merged_pr() (16),
  _plan_dispatches() (14), GDDP Runtime (14), evaluate_pre_tool_use() (13),
  JulesActionAdapter (13), TestJulesActionAdapter (13), handle_event() (12),
  run() (12), NodeData (12)
- **Structure:** webhook intake → classify → scope → queue → dispatch →
  execute → return_router → receipt → human review. Layers visible as
  communities: decision-loop/context reader, heartbeat classifier +
  dispatcher, Jules adapter, return router + results store, intake server,
  replay, rollback, paste-marker guard hooks (borrowed from .pi)
- **Executor adapters:** JulesActionAdapter (Option A, GitHub issues — live),
  JulesCliAdapter (Option B, CLI — stub)

## Current direction

Operational trials and production trials-ready. 

Done means: overnight runs are stable, boringly reliable 

In order to accomplish this, the deterministic evaluators  and *semantic evaluator* has to be fully implemented. The verification loop amounts to creating an agentic harness for verification, observing graph state and invariants, and catching project drift and flagging to the human operator the state of the graph node-by-node.  

That frames the control-plane idea honestly for mixed senior-engineer /
recruiter / lay audiences; the "runtime cannot mutate config truth" rule
visible as architecture, not accident; the receipt-based return path and
review gate explained end-to-end; both repos cross-referenced; v1 schemas
documented. Drafts only — no push until Sab signs off.

## Known gaps / risks

- `docs/host-roles.md` and handoffs leak operator topology (ssd-big,
  ssd-small, mac, SSH paths, Big Pi `~/opclaw` execution surface) — scrub
  before public
- `scripts/runtime/graph_updater.py` is an intentional disabled stub —
  README must explain WHY or it reads as broken code
- Decision-loop review/accept powers are draft/future, not the stable
  contract — must be labeled as such
- `gddp-config` active branch is `feat/openclaw-nodes` (historical; objects
  now use decision-loop naming) — confusing for a first-time reader
- `.agents/hooks/ag_natural_guard.py` (paste-marker guard) is borrowed from
  .pi — needs attribution or a clarifying note on the cross-project reuse

## Deeper docs

- README (v2 draft): [`docs/README-v2.md`](docs/README-v2.md)
- Pi README handoff: [`docs/HANDOFF-PI-README.md`](docs/HANDOFF-PI-README.md)
- Decision-loop spec: [`docs/decision-loop-spec.md`](docs/decision-loop-spec.md)
- Big Pi runbook: [`deploy/BIGPI_RUNBOOK.md`](deploy/BIGPI_RUNBOOK.md)
- Handoffs: [`docs/handoffs/`](docs/handoffs/) (001 reality-check, 002 return-path vocabulary lock)
- Config repo (source of truth): [`../gddp-config/`](../gddp-config/)
