# Evaluation pipeline

Active contributors: Saboor

## Purpose

The evaluation pipeline turns a returned commit into a provenance-bearing receipt for human review. It checks both whether the node's criteria are supported and whether the work preserves project intent and graph integrity. Its verdict is evidence, never graph truth.

## Pinned evaluation subject

`scripts/runtime/verification/bridge.py` requires a `merge_commit_sha` for both direct commit-ref results and mediated merged-PR returns. It resolves the project checkout from the graph's declared repository, fetches the commit, creates an isolated detached worktree at that exact SHA, and runs the verifier CLI as a subprocess.

Missing or unmaterializable commit identity returns `subject_mismatch`; mutable checkout state is never allowed to produce a valid-looking receipt. The receipt records `evaluated_commit_sha`, `evaluated_tree_sha`, the claimed merge/result commit, expected base, job and attempt identity, and optional PR, evidence-manifest, and mission-receipt provenance.

The subprocess boundary contains verifier crashes and timeouts. Transient invocation failures receive one bridge retry; missing graph/config paths and subject mismatch go directly to review.

## Criteria lane

`scripts/runtime/verification/orchestrator.py` first assembles deterministic evidence from node criteria, constraints, dependencies, artifacts, and the pinned repository. The semantic criteria harness runs only when criteria remain indeterminate and no dependency, constraint, or explicit criterion failure already decides the floor.

The semantic harness receives the node, project graph, deterministic result, repository, and optional shape profile. Its criterion judgments feed `scripts/runtime/verification/decision_engine.py`, which produces a criteria verdict and confidence signals. Semantic judgment does not replace deterministic failures.

## Integrity lane and combination

The integrity lane runs whenever wired, including when deterministic evidence is green. It evaluates intent preservation, graph-integrity preservation, findings, graph observations, confidence, and any required human review.

`scripts/runtime/verification/integrity_combiner.py` is the small deterministic authority boundary. Integrity can preserve or worsen the criteria verdict but can never upgrade it. `insufficient` floors the result at `needs-more-evidence`; unknown, drift, contradiction, block, or violated preservation flags floor it at human review. The combined result is the worse lane outcome.

## Context coverage

The orchestrator builds canonical pointers to project documents, the foundational node, and neighboring graph nodes. It compares those offered paths with successful `read` and `grep` calls in each lane's tool trace; listing or finding a file does not count as reading its content.

Each lane receives a coverage rating:

- `none` — no offered canonical content was accessed;
- `low` — some canonical content, but no canonical project document;
- `medium` — a project document was read but offered neighbor context was not;
- `high` — a project document and neighbor were read, or no neighbors were offered.

Overall coverage is the worse rating among lanes that ran. Coverage describes the basis of the judgment; it does not itself grant permission or complete the node.

## Receipt and integration

The resulting `VerdictReceipt` includes deterministic and semantic evidence, integrity output, lane status and errors, combined verdict, confidence, required next action, provenance, canonical context, and context coverage. Direct results are finalized in `scripts/runtime/heartbeat/reconciler.py`; mediated returns use `scripts/runtime/return_router.py`. Both persist the summary for `scripts/jobs_status.py` and route the job to review or an evidence-qualified retry.

## Key files and modification points

- `scripts/runtime/verification/bridge.py` — subject pinning, worktree isolation, subprocess containment, and retry.
- `scripts/runtime/verification/orchestrator.py` — lane orchestration, receipt assembly, and coverage.
- `scripts/runtime/verification/deterministic.py` — deterministic evidence.
- `scripts/runtime/verification/semantic/` — read-only semantic criteria harness.
- `scripts/runtime/verification/integrity_runner.py` — read-only integrity harness.
- `scripts/runtime/verification/decision_engine.py` — criteria verdict matrix.
- `scripts/runtime/verification/integrity_combiner.py` — worst-of combination.
- `scripts/runtime/verification/schemas.py` — receipt and lane schemas.

Add evidence kinds in deterministic assembly, not in the bridge. Change lane prompts or tools within their harness directories while preserving read-only subject access. Any verdict ordering change belongs in the deterministic combiner with exhaustive matrix tests. Extend canonical context and coverage together so offered paths and observed accesses remain comparable.

See [Verification](../systems/verification.md), [Return and review](../systems/return-and-review.md), [Verdict receipt](../primitives/verdict-receipt.md), and [Human review](human-review.md).
