# LOOP — the GDDP operating loop

The system in one page. Everything else in this repo is appendix.

## The loop

1. **Packet** — a node yaml in `gddp-config/graphs/<project>/nodes/` carries
   the intent: goal, constraints, acceptance criteria. Only humans author or
   approve nodes.
2. **Dispatch** — the armed heartbeat (`deploy/mini-heartbeat/bin/arm.sh`)
   claims ready nodes and hands each to one executor as one packet.
3. **Return** — the executor works in a worktree; receipts land as files
   (`GDDP_RECEIPTS_PATH`), results in `db/queue.db`. Files are truth; the db
   is an index over them.
4. **Evaluate** — the reconciler queues every returned job onto the
   `gddp-evaluator` worker pool: deterministic + semantic + integrity lanes,
   combined worst-of into a verdict receipt in
   `gddp-config/verification/<project>/`. Verdicts are evidence, never truth.
   Measured cost: ~3–6 min per node.
5. **Human** — `gddp node browse --project <p>`: `c` accept (graph truth
   changes — only here), `r` reject (back to ready, findings become the
   retry's fix-list), `d` defer.

## While a node runs

- `gddp watch` — fleet view: every attempt, live worktree diff, silence flag.
- `gddp watch <node>` — one node: diff vs HEAD, new files, recent events.
- `gddp steer <node> <message>` — operator message into the live session,
  delivered mid-turn; the receipt reflects the steered work.

## Standing rules

- Truth lives in files (packets, receipts, verdicts, node yamls). sqlite is a
  rebuildable index; nothing valuable dies with `db/queue.db`.
- Only human acceptance moves a node to complete. Evaluator verdicts,
  passing tests, and executor success are all just evidence for that keypress.
- A `provisional` label without a verdict receipt behind it is unevidenced —
  the record must say which it is (evaluation provenance, 2026-08-13).
- Evaluation is event-driven off job returns today; the state-driven sweep
  (evaluate anything sitting unevidenced) is the known missing half.

## Frozen infrastructure (do not invest; revive only via a named node)

`scripts/intake_server.py` (webhook intake) · `scripts/adapters/jules_*` ·
`deploy/rig1-heartbeat/`, `deploy/deploy.sh` · `scripts/rollback.py`,
`scripts/export_evaluations.py` · `graphify-out/` (regenerable).
