# 030 — Terminology Lock, Canon Declaration, Fleet Sync

------------------------------------------------ Agent Section START

Date: 2026-07-08 (session ran into 07-09)
Worktree: /home/sab/gddp-runtime (+ /home/sab/gddp-config)
Branch: main (both repos)

## Empirical Reality (2-3 sentences max, anything more must be critically justifiable)

Total-system terminology audit executed and deployed: node field `acceptance:` renamed to `acceptance_criteria:` across both repos (schema, 53 node YAMLs, templates, authoring toolchain, runtime readers), canon documents declared and authored, GDAD purged from all evaluator-reachable surfaces. Both pis pulled, intake restarted, heartbeat live-verified with non-empty criteria (7/6/6 on 3 ready nodes). 212 tests green; system is vocabulary-stable and ready for the Factory Droid wiki snapshot.

### Scope touched (One file per line, +/- for only what was changed)

gddp-runtime (commits 68dc2f2..e267c16, all pushed):
- scripts/runtime/decision_loop/context_reader.py — buckets now pending/ready/complete/deferred (in_progress/blocked were dead vocab, always empty)
- scripts/runtime/verification/schemas.py — VerdictReceipt.confidence alias field removed; legacy-read shim kept (old receipt JSON still loads)
- scripts/runtime/verification/orchestrator.py — stops emitting the alias
- scripts/runtime/verification/test_schemas.py|test_orchestrator.py|test_cli.py|test_dry_run_e2e.py — alias assertions removed
- scripts/runtime/heartbeat/graph_reader.py — NodeData.acceptance → acceptance_criteria (attr + YAML key)
- scripts/runtime/heartbeat/job_factory.py, decision_loop/powers/dispatch_next.py, verification/deterministic/{__init__,constraints}.py + all test files — same rename
- README.md — NEW, canon; promoted from docs/README-v2.md with fixes (ready-node status prose, stale Status section, canon-list section)
- PROJECT-BRIEF.md — canon-list + vocabulary-doctrine section added
- AGENTS.md — stale "lacks an agentic evaluator" paragraph replaced with live two-lane description
- deploy/gddp-intake.service — renamed from opclaw-intake.service, content now matches live pi-big unit
- deploy/setup.sh, deploy/deploy.sh — GDAD→GDDP, gddp-intake service name
- deploy/BIGPI_RUNBOOK.md — rewritten to reality (see MAP below)
- .gitignore — +.aider*
- docs/archive/ — NEW; 10 superseded docs moved in (README drafts ×3, IMPLEMENTATION-PLAN, gdd-architectura-review, benchmark_matrix, verification-engine-spec, verification-parallel-build ×2, gdd-next)

gddp-config (commits c8333c5..642a663, all pushed):
- schemas/v1/node.yaml — acceptance:→acceptance_criteria: with doctrine comment; status comment "verdict"→"decision"
- graphs/*/nodes/*.yaml (53) + templates + exports — field renamed
- templates/draft-node-prompt.md — model-facing prompt updated to new field name
- scripts/*.py (16 files: validate, import_node, new_node, batch_fill, rapid_add, llm_draft, verify_node, obsidian_export, etc.) — YAML key "acceptance"→"acceptance_criteria"
- graphs/gddp-runtime/project.yaml — project_name "GDAD Runtime Engine"→"GDDP Runtime Engine" (was evaluator-reachable stale vocab)
- graphs/gddp-runtime/nodes/decision-loop-spec.yaml + exports — GDAD→GDDP in why-text
- _archive/ — graphify-out/ (generated, stale GDAD) and ACTION_PACKET_HANDOFF.md moved in

### Constrained areas touched (none / list + justification)

- Live pi-big state: rebased pi-big's diverged run-main (local "Graphify output noise" commit rode on top), restarted gddp-intake.service, ran one manual heartbeat. Justification: the schema rename has NO back-compat — old runtime + new config silently yields empty criteria lists; window had to be closed within one cron tick.
- pi-small local work: stashed (MIT-license README edit, .aider gitignore) and moved untracked MIT LICENSE + readme-v2.md to ~/archive/pi-small-gddp-local-2026-07-08/. Justification: conflicted with Apache 2.0 canon on origin; preserved, not destroyed. Sab confirmed Apache is intended.

### Current Git state (2-3 sentences max, anything more must be critically justifiable)

Both repos clean and pushed. Fleet: local sab-dev = pi-small = runtime e267c16 / config 642a663; pi-big = same + its graphify commit rebased on top (9cedac8). sab-air and sab-mini were unreachable (Tailscale SSH not enabled) — they still need a manual `git pull` on both repos.

### Artifacts (Filepath - Description, 1 line max per artifact)

- README.md — canon: high-level idea + canonical-documents list
- PROJECT-BRIEF.md §"Canonical documents" — canon list + vocab doctrine (verdict/acceptance/decision, audience split, matrix row order)
- deploy/BIGPI_RUNBOOK.md — corrected operational map of pi-big
- ~/archive/pi-small-gddp-local-2026-07-08/ (on pi-small) — preserved MIT-license draft evidence

### Resume point (2-3 sentences max, anything more must be critically justifiable)

Vocabulary is locked and fleet-synced; run the Factory Droid auto-wiki whenever (treat output as generated reference capturing canon — never canon itself, never evaluator-reachable). Next implementation: remove the dead OPCLAW_ROOT fallback (confirmed unset on pi-big; 8 files), then the deferred murky pile: receipt overwrite/no-verdict-history, evidence-reference regex in retry_budget.py, retiring deploy.sh's ~/opclaw snapshot step. Pull both repos manually on sab-air and sab-mini.

## MAP — canonical paths, canon docs, and why (requested by Sab for next instance)

### Canon documents (the list; small, human-owned, wins over all other prose)
1. Foundational node — FIRST node listed in each project's `gddp-config/graphs/<project>/project.yaml` (node order there is semantically meaningful)
2. `gddp-runtime/README.md` — high-level idea, every audience
3. `gddp-runtime/PROJECT-BRIEF.md` — doctrine, direction, known gaps
4. `gddp-runtime/AGENTS.md` — executor-canon ONLY; deliberately excluded from evaluator context
Everything else (handoffs, specs, wikis, receipts, docs/archive/) = disposable reference.

### Vocabulary doctrine (now enforced in schema + code)
- verdict = evaluator output (criteria lane enum: pass/fail/blocked/needs-human-review/needs-more-evidence/out-of-scope-change-detected; integrity lane: pass/block/drift/insufficient/contradicted/unknown — graph YAML owns integrity vocab)
- acceptance = the HUMAN act that advances graph truth (accept_node); never an evaluator capability — hence the field rename
- decision = human's status call on a node (pending/ready/complete/deferred; execution state lives on jobs/queue_records only)
- semantic judgments stay judged_pass/judged_fail/indeterminate — deliberately un-confusable with verdicts
- block vs blocked across lanes: known blur, left as-is per Sab

### Live topology (pi-big — the runbook now matches this)
- `~/repos/gddp-runtime` = source AND live execution surface AND state root (db/queue.db, jobs/, events/ inside it)
- intake: `gddp-intake.service` (systemd, runs scripts/intake_server.py from the repo; restart after pulls — it loads code at start)
- heartbeat: user crontab, */5, `python3 -m scripts.runtime.heartbeat.runner --project gddp-runtime --repo skchaudr/gddp-runtime --config-path ~/repos/gddp-config`
- `~/opclaw` = retired husk; deploy.sh still snapshots there pointlessly (retirement pending); NO env sets GDDP_RUNTIME_ROOT/OPCLAW_ROOT anywhere
- deploy rule: BOTH repos pull together (schema/reader coupling), pi-big runtime pulls with --rebase (graphify commit rides on top)

### Coupling hazard for the next agent
`acceptance:` no longer exists as a node field. Any tool, prompt, or machine still using it gets an EMPTY criteria list silently — no crash. If jobs ever dispatch with empty "Acceptance Criteria" sections, check repo sync first.

------------------------------------------------ Agent Section END

------------------------ Do NOT edit this file past this point

## Narrative / Trajectory (SAB ONLY)

### Intent going into/at start of session

### Interpretation of how the session went

### Friction experienced or anticipated

### What's Next (Momentum or Lack Thereof)
