# N4 heterogeneous attempt 1

## Outcome

Two independent real nodes were reserved at configured capacity `2`, dispatched
in parallel through different executors, and reconciled independently to
`awaiting_review`. Graph truth was not changed.

| Lane | Job | Result | Evaluator |
|---|---|---|---|
| Jules API | `job_20260726T1059546235f910ffd05c` — `heartbeat-crash-recovery` | `4c0d5ae3b060e56221c5172b4a4dbfdf5ac57816` | **fail** criteria / **pass** integrity |
| Local Pi | `job_20260726T1059546275a44bb7bbd0` — `pi-evaluator-harness` | `21ced0c2f11926e87dd85d9d6c5733b497d7ac44` | **fail** criteria / **pass** integrity |

Both adapters reported `running` at `2026-07-26T11:00:16Z`. The local lane later
completed evaluation and moved to review while Jules remained `running`, proving
that one node's failing verdict did not pause or alter the independent peer.

## Why the verdicts failed

- **Local Pi:** the deterministic evaluator ran the node's literal
  `.venv/bin/python ...` command inside an isolated evaluation worktree where
  `.venv` is not versioned, so `suite-green` failed before semantic criteria
  ran. The agent claimed 199 tests passed, but that claim and the evaluator's
  command evidence conflict and require human review. Integrity also found
  pre-existing contract drift around the optional harness fallback.
- **Jules API:** four semantic criteria passed. `intake-restart-proven` failed
  because the remote Jules environment had no `launchctl` and its artifact
  explicitly simulated success. The returned code/tests may be useful, but the
  required live Mac restart proof is absent.

## What this proves—and does not

Proven:

- capacity-limited parallel reservation and heterogeneous dispatch;
- both workers running simultaneously;
- durable local commit-ref return and base-bound Jules patch return;
- per-node reconciliation/evidence isolation;
- one failed evaluation does not stop an unrelated running executor.

Not yet proven:

- two evaluators executing simultaneously;
- human acceptance unblocking downstream work while peer activity continues;
- either work-subject node satisfying all of its own acceptance criteria.

No retry was dispatched automatically.
