# Decision: neutral-executor-contract

Date: 2026-07-18
Node: neutral-executor-contract
Disposition: ready for human review; not accepted or complete

## Decision

Use one immutable, JSON-serializable `NodePacket` for every executor transport, with an explicit executor-independent `execution_attempt_id`. Keep direct lifecycle adapters (`JulesCliAdapter`, `LocalSubprocessAdapter`) separate from the inherited mediated GitHub-action transport while returning common typed dispatch and collection receipts.

Persist every execution attempt before dispatch. Preserve failed and cancelled attempts as evidence, retry only authoritative terminal failures within the existing cap, and prevent cancellation, transient polling failures, or controller restarts from creating duplicate work. Jules CLI v0.1.42 has no remote-cancel command, so its truthful cancellation semantics are local and durable: stop polling and integration without claiming the remote compute stopped.

The local subprocess proof runs without a shell, stores packet/output/status under an attempt-specific spool, defaults to an isolated attempt workspace, survives adapter re-instantiation, and makes cancellation terminal and non-collectable.

## Boundary

This evidence does not mutate `gddp-config`, accept the node, or mark it complete. Passing tests and evaluator receipts remain evidence for Sab's review.
