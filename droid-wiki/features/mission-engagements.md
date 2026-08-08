# Mission engagements

Active contributors: Saboor

## Purpose

Factory mission engagements execute several compatible graph nodes in one multi-agent mission while preserving the node as the unit of intent, evidence, retry, evaluation, and review.

## Engagement batching

`scripts/runtime/heartbeat/runner.py` asks each selected adapter whether it supports engagements. Engagement-capable jobs are grouped by executor and expected base, so one mission never mixes incompatible git bases.

The node limit is twice the smaller of `execution_policy.mission_engagement_size` and `execution_policy.mission_max_pairs`. Groups and ordinary single-job dispatches run concurrently after all jobs have durable `dispatching` reservations. `scripts/runtime/heartbeat/graph_reader.py` validates mission sizing as positive integers and provides stable defaults.

`scripts/adapters/mission_adapter.py` rejects empty engagements, duplicate node ids, multiple expected bases, and checkout/base mismatch. It projects the packets into `mission.md`, creates a unique `gddp/<engagement-id>` branch, launches `droid exec --mission`, and persists process identity, mission paths, feature ids, receipts, logs, and push audit paths under the adapter's session root.

## One feature, one node

Mission feature ids are graph node ids. During collection, the adapter compares the generated `features.json` with the exact demanded id sequence and writes one evidence manifest per demanded node through `scripts/adapters/mission_evidence.py`.

`scripts/runtime/heartbeat/reconciler.py` polls a shared engagement once and fans results back out by `feature_id`. The returned feature-id set must match the reserved node-id set one-to-one: duplicates, missing ids, or extras route every affected reservation to human review. A successful result must also have a commit, engagement ref, valid base ancestry, and reachability from that ref before evaluation.

This mapping prevents a successful engagement summary from laundering a missing node result.

## Evidence quarantine

The collector cross-checks mission progress, handoffs, receipts, git observations, branch history, and push audit records. Missing channels may require review; contradictions such as conflicting receipts, receipt identity mismatch, invalid history, protected-branch pollution, or conflicting completion envelopes produce quarantine reasons.

Completion ids and digests make exact replay idempotent. A conflicting duplicate quarantines involved sessions. Replaying a previously quarantined completion preserves its review disposition rather than turning it into an evaluable success.

## Push defense

`scripts/adapters/mission_push_guard.py` installs two controls in the mission environment:

- a `git` executable shim at the front of `PATH`;
- a command-scoped Git `pre-push` hook.

The only accepted push shape is `git push origin HEAD:refs/heads/gddp/<engagement-id>`. Force options, leading `+` refspecs, other remotes, and shared or protected destinations are rejected and audited.

An absolute Git invocation with `-c core.hooksPath=/dev/null` can bypass both process-level controls. The defense therefore has a post-hoc layer: `scripts/adapters/mission_evidence.py` checks live remote containment and quarantines a feature commit reachable from a protected branch.

## Key files and modification points

- `scripts/runtime/heartbeat/runner.py` — grouping and concurrent engagement dispatch.
- `scripts/adapters/mission_adapter.py` — mission lifecycle and collection.
- `scripts/adapters/mission_projection.py` — packet-to-feature projection and worker instructions.
- `scripts/adapters/mission_evidence.py` — per-node evidence slicing and quarantine.
- `scripts/adapters/mission_push_guard.py` — preventive push policy and audit log.
- `scripts/runtime/heartbeat/reconciler.py` — one-to-one fan-out and review/evaluation routing.
- `scripts/runtime/heartbeat/completion_discipline.py` — replay and conflicting-completion handling.

Tune batching in graph `execution_policy`; change mission rendering in `mission_projection.py`; add evidence checks in `mission_evidence.py`. Do not weaken one-to-one feature mapping or rely on the preventive push guard without post-hoc verification.

See [Factory mission](../systems/factory-mission.md), [Executor adapters](../systems/executor-adapters.md), [Engagement](../primitives/engagement.md), and [Parallel dispatch](parallel-dispatch.md).
