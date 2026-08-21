# Reflection — gddp-dogfood run, 2026-08-10/11

**Session:** first full dogfood run on the post-demolition runtime. 22 nodes
(4 tranches), local one-shot executor (pi `xai/grok-4.5`), post-hoc + runtime
evaluation (DeepSeek semantic lane). Result: 19 pass · 2 needs-human-review ·
1 fail (miswritten criterion; work verified good). ~4.5 h unattended at
capacity 1, 5-min timer. Executors: Kimi (orchestrator), Codex (co-advisor,
live observer), Sab (operator, mobile).

This document is organized per Sab's three-part frame: friction points,
genuine mistakes, and proportionality (*does the consequence fit the
infraction?*). It is written before Sab's blind-transcript review (a fresh
agent reading both transcripts without this diagnosis) — the comparison is
the validation.

## 1. Friction points (operator-interface defects)

Places where the tooling stalled the orchestrator — each would stall an
operator worse. These are the *pilot-readiness* list.

- **F1 — skeleton defaults nobody chose.** `gddp project new` generates
  `default_executor: jules` (a dead executor) and `max_concurrent_jobs: 1`.
  The night's throughput ceiling was a scaffold default, not a decision.
- **F2 — registry/file status desync.** `project.yaml`'s node index mirrors
  node status; flipping node files without the index (or vice versa) silently
  desyncs dispatch ("no ready nodes" while files said `ready`).
- **F3 — priority enum surprise.** Validator rejects `priority: normal`;
  enum is `critical/high/medium/low`. Discovered only by a failed import.
- **F4 — import cannot update.** Re-importing an existing node id hard-rejects
  (`node_exists`); corrections require hand-editing node YAML, which the
  authoring rule forbids in spirit. There is no sanctioned fix path.
- **F5 — artifact gate path semantics.** `required_artifacts` resolves against
  repo root / `.gddp/` / `docs/` only. Bare filenames silently fail the gate;
  full paths required. Undocumented; caught pre-flight by code reading.
- **F6 — dispatch confirm aborts without a TTY.** `gddp <graph> <executor>`
  prompts `(n):` and auto-aborts on non-TTY stdin. No `--yes` flag. Blocks
  scripted/remote dispatch.
- **F7 — brittle host-specific criteria (mine).** "only the 3 known
  flask-import failures" broke when the host drifted to 4 (a pre-existing
  rig1 plist assert). Criteria must be host-agnostic.

## 2. Genuine mistakes (orchestrator, with mechanism)

None were caught by a guardrail; all were caught by a second set of eyes.

- **M1 — truncated-evidence miss.** `pi --help | grep … | head -6` cut off
  `--no-extensions`; I reported it absent. Codex found it by reading the full
  output. *Truncated output is a silence artifact; absence claims require
  full reads.* (This exact guardrail was already written down.)
- **M2 — false-stall alarm.** Compared my local poll clock to VM UTC and
  reported "no dispatch in 25 minutes" for events seeded 90 seconds prior.
  Codex corrected with timestamps. *Cross-machine time comparisons need the
  remote clock read first.*
- **M3 — commit sweep.** `git add graphs/gddp-dogfood/` swept the runtime's
  ready→provisional write-through mutations (and a `project.yaml.bak`) into
  my T2 import commit. The exact failure I had flagged in a peer's session
  hours earlier. *Read the diff before every add, especially shared trees.*
- **M4 — capacity silence.** Recognized `max_concurrent_jobs: 1` as the
  throughput limiter and held the math instead of offering the operator the
  knob. Sab's rule, now logged: **surface leverage, not permission.**
- **M5 — existence-vs-readiness.** Reported the canonical target clone
  "ready" because `/data/repos/gddp-runtime` existed; it was 4 behind
  origin/main. Codex's independent preflight caught it pre-dispatch.
  *Existence checks are not state checks.*

## 3. Proportionality — does the consequence fit the infraction?

| # | Infraction | Mechanism | Consequence | Proportionate? |
|---|---|---|---|---|
| P1 | node-16 suite showed 4 failures where the criterion allowed 3 | evaluator criteria lane | fail verdict → human review, **work preserved**, evidence cited the pre-existing 4th failure and verified the new test 5/5 | **Yes** — the fail was correct (criterion said 3), and grace was preserved: the human gets the full picture and can accept |
| P2 | node-01 attempt 0 exited 254 (SIGINT after hang) with result already durable | adapter maps nonzero exit → failed → auto-retry | ~13 min redundant rework; result never at risk | **Disproportionate but recoverable** — BM-026 already in the register backlog: retrievable commits should be evaluated, durability repaired separately |
| P3 | pi one-shot completed work but never exited (extension inotify watcher held the event loop) | `process.wait()` with no timeout; reconciler stale-handling covers only missing sessions | indefinite capacity deadlock absent intervention | **Disproportionate** — no timeout floor exists. Mitigated by `--no-extensions` in the executor argv (3 clean exits after); root fix belongs in pi (one-shot should drain the loop on completion) |
| P4 | my criterion text vs host drift (3→4 known failures) | evaluator judged against the letter | node-16 fail | **System absorbed it gracefully** — the evaluator's evidence made the correct human call obvious. The lesson is authoring-side (F7), not mechanism-side |
| P5 | heartbeat pass-handling rewrites canonical node YAMLs ready→provisional (unstaged, every pass) | `provisional_status.py` — designed write-through per `docs/GDDP-rebuild.md`, contradicting AGENTS.md "runtime must never update graph/node status" | working-tree drift between commits; provenance laundering risk when later commits sweep the mutations (M3) | **Unresolved doctrine conflict — operator ruling needed.** Either provisional write-through is legitimate graph truth (then it should be committed by an identifiable path, not left as unstaged drift) or it violates the boundary (then it dies). Evidence packaged; no prejudgment here |

## 4. Meta-lesson

Every guardrail-class failure tonight was caught by a second reader (Codex
caught M1/M2/M5 and the P5 evidence; the validator caught F3; code reading
caught F5). Zero failures lost work. The post-demolition shape — preserve
evidence, route judgment to humans — absorbed every infraction without
collateral damage. The open question set is small and named: P5's doctrine
conflict, P3's missing timeout floor, P2's register-known fix.

## 5. Artifacts of record

- Package: `.handoffs/092-dogfood-package-v2-draft.md` (22 nodes, executed)
- Backlog (unapproved): `.handoffs/091-dogfood-node-package.md`
- Receipts: VM `~/gddp-config/verification/gddp-dogfood/`
- Result branches: `origin/gddp/attempt-*` (22), one artifact each
- Register: `docs/blocking-mechanisms-register.md` (BM-026 live-confirmed)
