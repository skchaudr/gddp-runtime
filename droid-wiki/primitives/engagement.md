# Engagement

Active contributors: Saboor

An engagement is one durable executor session that may carry one or more ordered node attempts. It is a transport and execution boundary, not a graph node and not graph truth.

## Contract

`EngagementDispatchResult` in `/Users/sab-mini/repos/gddp-runtime/scripts/adapters/executor_protocol.py` is the dispatch receipt. It records:

- whether dispatch succeeded;
- the engagement ID and durable `SessionRef`;
- the Factory mission directory and process PID when applicable;
- the isolated `gddp/<engagement-id>` branch;
- the ordered node IDs as `feature_ids`;
- an error when launch fails.

Adapters opt in through `supports_engagement()`, `dispatch_engagement()`, and `collect_engagement()`. One-node adapters inherit defaults that reject engagement operations. The `factory_mission` adapter implements the extension and also maps single-node `dispatch()` and `collect()` through it.

## Factory mission lifecycle

`/Users/sab-mini/repos/gddp-runtime/scripts/adapters/mission_adapter.py` requires at least one immutable `NodePacket`, unique node IDs, one common expected base, and a target checkout at that base. It projects the packets into `mission.md`, installs a push guard, launches `droid exec --mission`, and persists `session.json`, stdout, stderr, receipts, and push-audit paths under `db/mission-sessions/<engagement-id>/`.

Status is based on the durable process identity, exit state, and the last Factory progress event. A dead process is complete only when the progress log ends in `mission_completed`; otherwise it is failed or crashed. Factory `state.json` alone is not trusted as liveness evidence.

## Per-node return

Collection never treats an engagement as one undifferentiated success. `/Users/sab-mini/repos/gddp-runtime/scripts/adapters/mission_evidence.py` emits one manifest and one `PatchResult` per demanded feature ID. Each result can carry:

- base and result commit SHAs;
- the engagement result ref;
- feature and completion identity;
- manifest path and completion digest;
- review and quarantine reasons.

Receipts, Factory handoffs, progress events, git history, push audit, worktree state, and protected-branch reachability are cross-checked. Missing or conflicting evidence routes the affected node to human review; it does not complete that node or launder another feature's evidence.

## Boundaries

- Engagement ordering does not create graph dependencies.
- A successful mission process does not imply every feature succeeded.
- A collected commit or evaluator verdict is evidence only.
- Only a human changes node status to `complete`.

## Related pages

- [Node packet](node-packet.md)
- [Executor session](executor-session.md)
- [Gate token](gate-token.md)
- [Factory mission system](../systems/factory-mission.md)
- [Mission engagements feature](../features/mission-engagements.md)
