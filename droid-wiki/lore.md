# gddp-runtime lore

A chronological narrative of the project's major eras, from initial commit through mission mode. Dates come from commit history on `origin/main`.

---

## Era 1: GDAD skeleton (Mar 13-19, 2026)

The project began on **2026-03-13** with a single commit: `feat: initial commit — GDAD runtime scripts`. The first Python files were adapter stubs under `scripts/adapters/`. Within a week, the modular heartbeat graph-driven event processor landed (PR #1, Mar 13), followed by an `OPCLAW_ROOT` environment variable fix (Mar 13) and early database/job path wiring.

This era established the foundational shape: Python scripts in `scripts/`, deploy configs in `deploy/`, runtime state in `db/`, `jobs/`, `events/` (later gitignored). The architecture was event-driven from day one.

**Longest-standing code:** The adapter layer and heartbeat runner have been continuously present since the first week, though heavily refactored.

---

## Era 2: CLI and evaluator (Jun-Jul 2026)

After a quiet spring, development accelerated in July. The first evaluator harness appeared on **Jul 4** (`verification: pi harness for visible semantic evaluation`), establishing the two-lane verification pass (deterministic + semantic) that remains the evaluator's shape today.

The interactive CLI landed on **Jul 22** (`feat(cli): interactive menu on bare 'gddp' in a terminal`), giving operators a single entry point for job review, queue inspection, and node status. By **Jul 24**, the jobs status backend was separated into its own module, and by **Jul 31**, the CLI contract tests were aligned with production offline behavior.

The CLI and evaluator were developed in parallel but served different purposes: the evaluator produced verdicts, the CLI surfaced them to humans.

---

## Era 3: Doctrine (Jul 4, 2026)

On **Jul 4**, a single commit (`docs: canonize intent/architecture doctrine and point to it from AGENTS.md`) landed two foundational documents:

- `docs/Tests-can-fail-nodes-can-pass.md` -- node status reflects accepted graph progress, not temporary implementation perfection. Tests are evidence, not graph truth.
- `docs/GDDP-becomes-small-and-real.md` -- GDDP is the intent-preservation and graph-integrity layer around work, not the executor and not the agent harness.

These documents were written in response to observed failure modes (see `AGENTS.md` opening warning) and have governed all subsequent design. The doctrine was not retroactively applied; it was extracted from patterns that had already caused failures.

**Why this matters:** The doctrine prevents the most common agent failure mode -- assuming a behavior exists, designing around it, then discovering the assumption was false after the system has failed. The evaluator produces evidence; only humans accept nodes.

---

## Era 4: Executor transport (mid-Jul 2026)

The executor era began in earnest around **Jul 31** with `heartbeat: active executor sessions keep a project alive under --all-active`, establishing that the heartbeat runner must track external executor sessions (Droid, Jules, Codex) as first-class entities, not opaque subprocesses.

By early August, the executor layer had matured: **Aug 3** brought `feat(executor): droid exec as a first-class local executor transport`, treating Droid sessions as a replaceable transport rather than a bespoke integration. **Aug 8** closed the era with the `factory_mission` executor adapter merge, enabling mission-built execution modes.

**Design principle:** Executors are replaceable transports. They do not own graph truth. The runtime must tolerate any executor that can produce a node receipt.

---

## Era 5: Topology cutover (Jul 12-13, 2026)

On **Jul 12**, the project's production topology shifted from `pi-big` to `sab-mini`. Commits that day (`docs: rewrite TOPOLOGY as GDDP runtime map (post mini cutover)`, `feat: migration-aware topology + mini cutover kit hardening`) reflect a deliberate migration, not an ad-hoc move. Secrets were migrated to a mini-local pass store with GPG key (**Jul 13**), and a canary scope postmortem was written the same day after a scope goose chase.

**Why chronological order matters:** The cutover preceded the rig1 overnight run and the rebuild. Understanding this sequence is essential -- the topology was stabilized before the scheduler was tested under load.

**Archived artifacts:** `setup.sh`, `gddp-intake.service`, and `BIGPI_RUNBOOK` were archived on **Aug 5** as dead-topology artifacts, marking the end of pi-big's role.

---

## Era 6: Rig1 overnight and rebuild (Jul 29, 2026)

On **Jul 29**, the `feat/rig1-scheduler` branch was merged into main, bringing the overnight scheduler that would run the first multi-node pipeline. The same day, a rebuild was documented (`docs: current task state and the rebuild that replaces patch-return`), replacing an earlier patch-return mechanism with a blocking-review foundation.

The rig1 overnight run was the first test of the full loop under sustained load. It exposed integration gaps between the heartbeat runner, executor sessions, and the verification pipeline, but did not expose doctrine violations.

---

## Era 7: Provisional flow and smoke green (Jul 30, 2026)

On **Jul 30**, the provisional flow landed: `feat: provisional flow -- evaluator-passed nodes unblock dependents` and `feat: provisional base-chaining -- dependents build on dep's result commit`. This established that a node passing evaluation could unblock downstream work before human acceptance, reducing latency in the pipeline.

The same day, the evaluator gained its third gate: `evaluator: provisional satisfies dependency edges`. The first provisional smoke run went green by **Jul 31 00:27** (`handoff 006: provisional smoke run 1 green`).

**Why provisional matters:** It decouples evaluator verdicts from human acceptance temporally while preserving the doctrine that only humans accept nodes. The provisional flow is evidence that the system is working; acceptance is still a human decision.

---

## Era 8: The reckoning (Jul 31, 2026)

On **Jul 31**, `docs: the reckoning -- per-piece evidence worksheet (aligned/contradicts/ceremony)` landed. This document was a systematic audit of every piece of evidence in the system, categorized as:

- **Aligned:** evidence that supports the current graph state
- **Contradicts:** evidence that challenges a node's acceptance
- **Ceremony:** process steps that add no evidentiary value

The reckoning was not a failure postmortem; it was a deliberate inventory taken after the provisional flow went green. It established that the system had sufficient evidence to support its current state, or identified gaps that needed to be closed before further progression.

---

## Era 9: VM harness canary (Aug 4-5, 2026)

On **Aug 4**, a canary run of the VM harness audit node failed. The postmortem (`docs: postmortem -- vm-harness-audit canary run`) documented the failure mode and was rewritten the same day to follow a new convention after a doctrine review. **Aug 5** brought corrective actions: key rotation and an executor wall-clock timeout (`docs: postmortem actions -- key rotation, executor wall-clock timeout`).

The canary failure was instructive: it exposed that the executor layer did not yet tolerate agent-created attempt refs on the same chain, which was fixed on **Aug 2** (retroactively applied). The canary run validated that the failure detection and postmortem machinery was working as designed.

---

## Era 10: Mission mode (Aug 6-8, 2026)

On **Aug 6**, a draft two-mode executor architecture was written, distinguishing between direct-executor and mission-built execution modes. **Aug 7** brought the implementation: `feat(gates): per-node gate-token writer for mission-mode admission` and `feat(adapters): register factory mission execution mode`. **Aug 8** closed with the `factory_mission` executor adapter merge.

Mission mode represents the current state of the art: the runtime can now dispatch nodes to external mission-built executors (Factory Droid missions) while preserving the same evidence and verification contract as direct-executor runs.

---

## Growth summary

| Date | Milestone |
|------|-----------|
| 2026-03-13 | Initial commit, GDAD skeleton |
| 2026-07-04 | Doctrine canonized, evaluator harness |
| 2026-07-12-13 | Topology cutover pi-big to sab-mini |
| 2026-07-22 | Interactive CLI lands |
| 2026-07-29 | Rig1 overnight scheduler merge |
| 2026-07-30-31 | Provisional flow, smoke green, reckoning |
| 2026-08-04-05 | VM harness canary and postmortem |
| 2026-08-06-08 | Mission mode architecture and implementation |

**Longest-standing features:** The adapter layer, heartbeat runner, and event-driven architecture have been present since day one, though heavily refactored. The doctrine documents (Tests-can-fail, GDDP-becomes-small-and-real) have governed design since Jul 4 without revision.

**Major rewrites:** The executor transport layer was rewritten multiple times (Jul 31, Aug 2, Aug 3) as the team learned what "replaceable transport" meant in practice. The CLI underwent a major refactor on Jul 24 to separate the jobs status backend. The topology was rewritten on Jul 12 post-cutover to reflect the new production reality.

**Current state (Aug 8):** The system is in mission mode, with the factory_mission executor adapter merged and operational. The runtime can dispatch nodes to external mission-built executors while preserving the evidence and verification contract.
