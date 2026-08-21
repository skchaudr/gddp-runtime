# Decision — Multi-heartbeat execution is the approved direction

**Date:** 2026-08-12 · **Source:** Sab, post-dogfood review · **Status:** direction-setting, pre-design

> "Multi-machine architecture is built into how I work. If the architecture
> prevents that, that's not approved architecture."

> "If there are algorithms that handle many writes to one location, there's no
> reason we should say 'one heartbeat, one graph per machine.'"

> "If we could handle one graph, one machine, many heartbeats, subgraph
> checkouts with unique identities tied to unique heartbeats, then
> multi-machine is just servicing infrastructure."

## Context

The dogfood run proved the single-host loop. During review it surfaced that
dispatch authority today is: a graph is inert on a host until explicitly
seeded into that host's local DB (`bin/gddp <graph> <executor>` → events →
heartbeat claims). Single-host operation is an assumption of the current
code, not an enforced mechanism — and per this ruling, that assumption is
unapproved as a permanent property. The pre-droid plan included multi-machine
execution; the governance era displaced it.

## Direction

Prove the coordination primitive locally, then let distribution be transport:

1. **One machine, one graph, many heartbeats.** Multiple heartbeat processes
   with unique identities claim work from one queue atomically. Subgraph
   checkouts (worktrees) carry unique identities tied to the claiming
   heartbeat.
2. **Then multi-machine** is moving heartbeat processes to other hosts — the
   claim algorithm is location-agnostic. What crosses machines is the shared
   coordination store, a servicing concern.

Subgraph isolation by physically removing graphs from checkouts is a
workaround, not the design.

## What exists today (verified 2026-08-12)

- Unique session/job/completion ids; attempt branches namespaced per session
- Completion-id/digest conflict detection at collection (loud failure on
  genuine double-execution)
- Claim/scope/reserve machinery in the runner — but written assuming one
  claimant (systemd timer serialization, per-host DB)
- Per-host SQLite queue; no cross-host visibility anywhere

## What the primitive needs

- **Atomic claim**: transactional `UPDATE … WHERE unclaimed` (SQLite supports
  this; the current claim path must be audited for check-then-act races)
- **Claimant identity + lease**: `claimed_by`, heartbeat expiry, reclaim of a
  dead claimant's reservations (intersects BM-021–023 capacity-release work)
- **Overlap removal**: today the systemd timer serializes heartbeat runs;
  many-heartbeats means the queue, not the timer, is the serializer

## Convergence with the provisional-status doctrine ruling

If `provisional` lives in the jobs layer (ruling option A), graph YAMLs
become human-only and the git-divergence axis of multi-writer disappears:
all runtime coordination concentrates in one transactional store — exactly
where many-writer algorithms apply. The doctrine ruling and the
multi-heartbeat direction are the same decision seen from two sides.
