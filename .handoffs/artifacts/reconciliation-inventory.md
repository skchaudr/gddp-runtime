# Reconciliation Inventory — raw vocabulary sweep (2026-07-07)

Purpose: input for Sab's reconciliation phase. Every term below EXISTS in config or
runtime today. Bucket assignments marked PROPOSED are suggestions only — Sab assigns
final buckets. Nothing here is doctrine until he says so.

Buckets: **Accepted doctrine** | **Schema** | **Non-canonical** | **Deprecated** | **Reserved**

## Node YAML schema (53 nodes, 6 graphs, perfectly uniform — every node has all 15 fields)

schema_version, schema_type, node_id, title, type, why, depends_on, acceptance
(entries: id, criterion, optional command), constraints, allowed_execution_modes,
required_artifacts, status, priority, unlocks

→ Bucket: **Schema**. Structural existence only; none of these imply doctrine by themselves.

## Flagged fields

- `type:` — value is `capability` in ALL 53 nodes. It is a constant, not a taxonomy.
  No runtime code branches on it (verify during reconciliation). Labels like
  `design`, `implementation-plan` appeared only in agent chatter, never in data.
  PROPOSED: field → **Reserved**; labels `capability/design/implementation-plan` →
  **Non-canonical** until a controlled taxonomy is defined. Agents must not infer
  behavior from node.type.
- `status:` values in the wild: `complete` (24), `pending` (26), `ready` (3).
  Doctrine says status flips are human-only via accept_node, and zero nodes have
  ever been accepted through that path — so the 24 `complete` predate the doctrine.
  PROPOSED: `complete` → **Deprecated pending re-audit** (grandfathered or re-verified,
  Sab's call; "graphs are baseline" suggests grandfather). `ready`/`pending` → **Schema**.

## Runtime vocabularies (all in active code — Schema at minimum; doctrine status is Sab's call)

- Verdict enum: `pass, fail, indeterminate, needs-more-evidence, needs-human-review, blocked`
  PROPOSED: **Accepted doctrine** (the 12-row matrix is the trust anchor).
- Criterion judgment: `judged_pass, judged_fail, indeterminate`
- `completeness_status: complete | partial | not-run` — KNOWN naming collision:
  measures semantic investigation budget, NOT artifact completeness.
  PROPOSED: rename candidate (e.g. `semantic_budget_status`) — receipt-contract
  change, so it needs the impact scan (Pi) before touching.
- Deterministic probe methods: `command_proof, command_proof_error,
  keyword_scan_source, no_probe, path_mentioned_missing, tier_distinct` + registered probes
- Job statuses: `ready, running, awaiting_review, done, failed`
  (awaiting_review counts as active — X2 doctrine)
- Event statuses: `received, claimed, classified, mapped, ignored, scope_blocked`
- Bridge: `verification_status: ok | error`, retryable flag

## Doctrine terms currently binding (from session decisions — confirm as Accepted)

- verdict ≠ acceptance; accept_node is the only status-flip path (human-only)
- evidence-scope rule: unlisted evidence is contextual, cannot rescue verdicts
- graph truth is human-owned; runtime produces evidence only
- criteria lane / integrity lane (NEW 2026-07-07, pending spec sign-off —
  see integrity-lane-spec.md)

## Known Non-canonical (agent-invented, never approved)

- "clean pass" as acceptance language (corrected 2026-07-06)
- node.type labels as behavioral hints
- (append here as reconciliation finds more)

## Impact-scan surfaces (for Sab's Pi, if schema/validation changes land)

- gddp-config: node creation/representation/validation (graph_reader parses these fields)
- executor pipeline: job_factory/dispatcher read node fields into work packets
- evaluator pipeline: schemas.py receipt contract, decision_engine, bridge summary keys
