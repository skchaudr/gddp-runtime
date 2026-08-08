# Glossary

Project vocabulary used across docs, code, and operator practice. Prefer these terms over near-synonyms when writing patches or handoffs.

## Core truth model

| Term | Definition |
| --- | --- |
| **Node** | Unit of project intent: a YAML contract (goal, criteria, constraints, dependencies, status) in `gddp-config`. |
| **Graph / DAG** | Human-authored dependency graph of nodes. |
| **Canon** | Invariants and architectural boundaries that must remain true. |
| **Graph truth** | Human-accepted node status. Only the operator writes `complete`. |
| **Evidence** | Commits, tests, artifacts, receipts, verdicts — observations of attempts, not completion. |
| **Human acceptance** | The act that turns sufficient evidence into updated graph truth. |
| **Drift** | Work that violates intended meaning or structural integrity even if local tests pass. |

## Runtime objects

| Term | Definition |
| --- | --- |
| **Event** | Normalized intake row (often from a GitHub webhook) waiting to be claimed. |
| **Job** | Bounded node work packet persisted in SQLite for one dispatch cycle. |
| **Queue record** | Lease/queue lifecycle row paired with a job. |
| **NodePacket** | Immutable executor-neutral description of one attempt (goal, criteria, base SHA, artifacts). |
| **Execution attempt** | One try at a node: packet + durable evidence + optional verdict; stable `execution_attempt_id`. |
| **Executor session** | Durable adapter lifecycle row: dispatching → running → collected/failed/cancelled. |
| **PatchResult / commit-ref handoff** | Adapter return: a patch or a result commit SHA plus durable ref. |
| **Engagement** | One executor session spanning several ordered node attempts (Factory mission). |
| **Completion identity** | Stable completion ID plus SHA-256 digest of accepted completion content. |
| **Quarantine** | Hold conflicting/malformed completion evidence for humans; do not silently promote. |
| **Result** | Structured return/evaluator receipt row in `results`. |
| **Decision result** | Audited runtime/operator action record. |

## Evaluation and status

| Term | Definition |
| --- | --- |
| **Evaluator** | Two-lane verifier: criteria (deterministic + conditional semantic) and integrity. |
| **Criteria lane** | Did the attempt satisfy acceptance criteria? |
| **Integrity lane** | Did the attempt preserve project canon, intent, and structural health? |
| **VerdictReceipt** | Combined evaluator output. Evidence for review; never graph truth. |
| **Provisional** | Node status: work finished, evaluator passed, operator not yet accepted. May unblock dependents. |
| **human_gate** | Per-node flag that parks for review and blocks dependents until accept. |
| **awaiting_review** | Runtime job status after evidence return; counts as active for scope checks. |
| **Context coverage** | How much canonical context (README, brief, foundational node, neighbors) the lane actually read. |
| **Subject mismatch** | Evaluator could not pin or materialize the claimed commit. |

## Scheduling and dispatch

| Term | Definition |
| --- | --- |
| **Heartbeat tick** | One reconcile / frontier / claim / plan / dispatch / finalize cycle. |
| **Frontier** | Currently unblocked graph layer eligible for promotion or dispatch. |
| **Scope checker** | Gate: dependencies satisfied and no active job for the node. |
| **Base chaining** | Dispatch a dependent from a provisional dependency’s result commit, not arbitrary HEAD. |
| **Dispatch reservation** | Session row created under lock before external launch. |
| **Plumbing retry** | Retry for missing durable exit state that does not consume a work attempt. |
| **Work retry** | Retry that counts against the node/job attempt budget. |
| **Retry fix-list** | Prior evaluator findings injected into the same unchanged node scope. |
| **Gate token** | `.gddp/gates/<node>.token` provisional admission evidence for dependents. |

## Executors and deploy

| Term | Definition |
| --- | --- |
| **Executor adapter** | `dispatch` / `status` / `collect` / `cancel` (plus engagement variants). |
| **Mediated adapter** | Creates external work (e.g. Jules issue) and waits on PR return. |
| **Direct adapter** | Owns local process lifecycle and commit-ref return. |
| **local_subprocess / droid** | One packet per durable subprocess; Droid specialization of local adapter. |
| **factory_mission** | Multi-node Factory headless mission engagement adapter. |
| **Feature ID drift** | Factory-planned feature IDs differ from demanded node IDs; parks for review. |
| **Push audit** | Append-only record of mission push attempts and reachability evidence. |
| **Spool** | Per-attempt directory: packet, command, pid, stdout/stderr, exit.json. |
| **gddp receipt** | Worker-facing CLI recording node, base, result, and observed git context. |
| **Mini-heartbeat kit** | Deploy pack: env, arm/smoke/disarm, launchd/systemd. |
| **Rig** | Named runtime host used for overnight or specialized runs. |

## Repo split

| Term | Definition |
| --- | --- |
| **gddp-config** | Human-owned truth repo. Runtime reads; does not write completion. |
| **gddp-runtime** | This repository: execution machinery. |
| **gddp CLI** | Operator control plane (typically from config `bin/gddp`) that routes job ops through runtime backends. |

## Related

- [Doctrine](../background/doctrine.md)
- [Primitives](../primitives/index.md)
- [Architecture](architecture.md)
