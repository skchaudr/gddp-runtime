## Review

- **Blocker — N04-W02A owns the wrong enforcement surface.** `compiled-five-node-ledger.yaml:411-418` limits the capacity writer to `heartbeat/dispatcher.py` and helpers. Live code shows `dispatcher.py:34-56` receives only one job and a repo, with no DB connection or project policy; all events are classified and job/session reservations are created in `heartbeat/runner.py:157-301` before `dispatch()` is called. **Impact:** `max_concurrent_jobs: 2` cannot be durably enforced across existing plus newly reserved jobs within the declared packet scope, so the N04 live proof can exceed capacity. **Smallest fix:** move W02A ownership to the reservation/planning transaction in `runner.py` plus the exact config/DB helper and tests needed to atomically cap active + planned jobs; keep adapter dispatch unchanged.

- **Blocker — Node 4 never proves its fourth acceptance criterion.** `gddp-config/graphs/gddp-runtime/nodes/concurrent-node-flow.yaml:27-28` requires acceptance to unblock downstream work while unrelated execution/evaluation continues. N04-W05A explicitly stops both jobs at review (`compiled-five-node-ledger.yaml:452-460`), N04-W06A then audits all four criteria (`:472-484`), and N04-W07A only records the later decision on Node 4 itself (`:486-493`). Naming an acceptance candidate in W01B is not an acceptance trace. **Impact:** N04 can reach Sab review with no evidence for `acceptance-unblocks-downstream`. **Smallest fix:** add a Sab-gated acceptance packet inside the observed two-job window, then capture the newly unblocked job beginning while the second independent job is still executing/evaluating; make W06A depend on that receipt.

- **High — graph epochs do not fingerprint the graph they claim to freeze.** The epoch rule records only `project.yaml` before/after proof actions (`compiled-five-node-ledger.yaml:67-70`), while definitions, criteria, constraints, and node-local status live in separate node YAMLs. N03 closes by rehashing only `project.yaml` (`:381-388`), and N05's before/after proof likewise records only old/new `project.yaml` hashes (`:529-536`). **Impact:** a relevant node YAML can drift without changing the epoch identity, allowing validators or receipts to be attributed to the wrong contract revision. **Smallest fix:** define one epoch manifest hash over `project.yaml` plus every relevant node YAML (preferably all project node YAMLs), and record/compare that manifest before and after every proof and Sab graph decision.

- **High — production restoration is an unnecessary global dependency edge.** N00-W03A depends on N00-W01B (`compiled-five-node-ledger.yaml:176-184`), and every N01+ packet is transitively behind W03A. Live inspection confirms intake is registered but not running, while the failure policy says an unhealthy production baseline should still allow read-only definition work (`:726-727`). **Impact:** a non-code intake blocker can deadlock definition decisions, Node 1 audits, and inherited-evidence synthesis that do not consume the service. **Smallest fix:** remove N00-W01B from N00-W03A's dependencies; attach service-health/authorization dependencies only to live dispatch packets (N02-W01C/W02A and later live proofs).

- **High — the ledger is not executable at checkpoint granularity.** The canonical workflow requires the minimum packet fields at `node-task-packet-workflow.md:90-179` and one packet file, routing table, worktree/retirement table, and Herdr manifest at `:321-340`. Ledger packets instead generally provide only `run`, a prose boundary, an artifact name, and prose verification; for example N00-W01A says to confirm “four intake criticals” without a command or expected output (`compiled-five-node-ledger.yaml:127-135`), and N04-W05A asks the parent to prove interval overlap without the DB query, clock source, or overlap threshold (`:452-459`). **Impact:** checkpoint success is operator-interpreted rather than reproducible, and attempts cannot be deterministically resumed or independently attested. **Smallest fix:** materialize one minimum-contract packet record/file per packet with exact inputs/hashes, scale/route, worktree/mutation fields, verification commands and expected assertions, return schema, retry state, and retirement conditions.

- **Medium — N04-W06A is too large to checkpoint safely.** It both builds the Node 4 bundle and launches three audits in one packet (`compiled-five-node-ledger.yaml:472-484`); the schedule confirms “Bundle then triple audit lanes” inside that packet (`:688-690`). **Impact:** bundle generation is a dependency of the auditors but has no separate verified state, and one provider failure forces an ambiguous retry of a composite attempt. **Smallest fix:** split bundle assembly, Pi/Codex/Claude audit siblings, and reconciliation into separate packets with explicit edges and immutable inputs.

- **Medium — N05 has two real isolated writers, but not two independently checkpointable prototype packets.** N05-W01B does launch two distinct sessions/worktrees/branches (`compiled-five-node-ledger.yaml:506-516`), satisfying physical writer isolation, but stores both prototypes and two receipts under one packet status. **Impact:** if one prototype is blocked-capability or fails verification, the successful prototype has no independently verified packet state and retry scope is unclear. **Smallest fix:** split prototype A and B into parallel sibling packets, then make a separate bakeoff/selection packet depend on both before integration.

- **Medium — the claimed count of four intake criticals lacks reviewable provenance.** `compiled-five-node-ledger.yaml:33-36` states `intake_health_criticals: 4`, but `five-node-current-state.md:21-61` provides no health command, output, or four-item list. Live checks confirm runtime HEAD/clean status, 379 passing tests, graph hash/statuses, dirty config, DB anchors, and intake registered/not-running, but there is no repository health command that reproduces the number four. **Impact:** N00-W01B is scoped around an unsupported count and may measure a different baseline. **Smallest fix:** mark the count unverified until N00-W01A, or attach the exact timestamped command/output and enumerate the four criticals.

```acceptance-report
{
  "criteriaSatisfied": [
    {
      "id": "criterion-1",
      "status": "satisfied",
      "evidence": "Eight concrete findings cite the compiled ledger, canonical workflow, node YAML, and live runtime code with severity, impact, and smallest fix."
    }
  ],
  "changedFiles": [
    "/Users/sab-mini/.config/hermes-proxies/.pi-subagents/artifacts/outputs/9709c5af-1a89-4958-bd8b-2b099e4af447/five-node-ledger-review.md"
  ],
  "testsAddedOrUpdated": [],
  "commandsRun": [
    {
      "command": "cd /Users/sab-mini/repos/gddp-runtime && python3 -m pytest -q",
      "result": "passed",
      "summary": "379 passed in 5.98s."
    },
    {
      "command": "git status/rev-parse/worktree list; shasum -a 256 project and node YAMLs; launchctl print intake/heartbeat; sqlite3 live DB queries",
      "result": "passed",
      "summary": "Confirmed runtime/config commits and status, graph hashes/statuses, dirty job-state-consistency YAML, live DB anchors, six residual worktrees, and both launchd jobs not running."
    },
    {
      "command": "Python YAML dependency validation for compiled-five-node-ledger.yaml",
      "result": "passed",
      "summary": "45 unique packets, no missing dependency IDs, packet DAG acyclic."
    }
  ],
  "validationOutput": [
    "Current runtime truth was rechecked live; all ledger baseline claims tested were accurate except the unsupported count of four intake criticals.",
    "N04 uses two separate writer packets/worktrees; N05 uses two separate writer sessions/worktrees but combines their checkpoint state.",
    "Existing Node 2/3 evidence reuse, provider-failure classification, human graph authority, and final Sab completion authority are present."
  ],
  "residualRisks": [
    "The four-intake-critical baseline remains unverified because no reproducing command or enumerated output was available.",
    "Live DB/service/worktree state can drift after this read-only review."
  ],
  "noStagedFiles": true,
  "diffSummary": "Review artifact only; no project, runtime, or gddp-config files were edited.",
  "reviewFindings": [
    "blocker: compiled-five-node-ledger.yaml:411-418 - capacity enforcement is assigned to dispatcher.py, which lacks DB/config context and runs after reservations.",
    "blocker: compiled-five-node-ledger.yaml:452-493 - N04 has no acceptance-during-overlap proof for acceptance-unblocks-downstream.",
    "high: compiled-five-node-ledger.yaml:67-70 - epoch identity hashes project.yaml but not node definition files.",
    "high: compiled-five-node-ledger.yaml:176-184 - intake restoration unnecessarily blocks all definition and evidence work.",
    "high: compiled-five-node-ledger.yaml:127-135 - packet checkpoints omit canonical executable verification contracts.",
    "medium: compiled-five-node-ledger.yaml:472-484 - N04 bundle and triple audit are one composite checkpoint.",
    "medium: compiled-five-node-ledger.yaml:506-516 - N05 dual prototypes are isolated but share one packet checkpoint.",
    "medium: compiled-five-node-ledger.yaml:33-36 - four intake criticals are asserted without reproducible evidence."
  ],
  "manualNotes": "Read-only review; only the required output artifact was written."
}
```
