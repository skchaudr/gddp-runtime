# Fleet — a standalone live view + steering surface for every agent process

Status: vision for handoff. Author: Pi + Sab direction, 2026-08-13.
Working title: **fleet** (pi-fleet). Implementation language open; Rust
(pi-hub-rs lineage) or Python are both viable — decide on build cost vs.
the operator's preference for a single binary.

## What it is

A separate tool — **not** part of pi, not a pi extension, not dependent on
any pi process running — that answers two questions at any moment, from any
terminal (including over SSH):

1. **What are my agents doing right now?** Every GDDP-dispatched attempt and
   every loose pi session on the host, live: phase, worktree diff, last
   action, silence detection, cost where available.
2. **I need to redirect one.** Type a message, it lands mid-run in that
   agent's session. Proven mechanism, already working in production today.

The subagents-fleet view inside pi proved the *shape*; fleet takes that shape
out of pi so the operator's observability never dies with a pi process, a TUI
crash, or a closed laptop lid on the wrong machine.

## Hard requirements (operator-specified)

- **Separate process from pi.** Zero pi internals imported. It reads files,
  sqlite, and process state. If every pi process on the host died, fleet
  still shows what they were doing when they died.
- **Accessible anywhere.** Terminal-first; must work over a bare SSH session.
  A read-only web page is an acceptable later milestone, never a requirement.
- **Resource-cheap.** Poll-based, sub-second local reads, no model calls, no
  heavy daemons. This is the "glance at what's running" tool.
- **Read-only except two sanctioned write channels** (below). Fleet can never
  gate, block, or corrupt the loop. If fleet crashes, the loop notices nothing.

## Data plane (all exists today — no new instrumentation needed)

| Source | Path / mechanism | Yields |
|---|---|---|
| Attempt spool | `~/repos/gddp-runtime/jobs/local-subprocess-spool/<job>-<node>-attempt-N-<uuid>/` | one dir per running/recent attempt |
| `packet.json` | in each attempt dir | node id, job id, project, goal |
| `pid` + `result.json`/`exit.json` | attempt dir | liveness + phase (running / returned / failed) |
| `worktree_path` | attempt dir | `git -C <wt> diff --stat HEAD` → live work evidence |
| `events.jsonl` | attempt dir | full RPC event stream: turns, tool calls, messages — the **agent trace** |
| `pi-session/` | attempt dir | the raw pi session file |
| queue.db | `~/repos/gddp-runtime/db/queue.db` (sqlite, read-only) | job/queue states, results, verdict bindings |
| Verdict receipts | `~/repos/gddp-config/verification*/<project>/<node>/` | evaluator verdicts |
| Graph truth | `~/repos/gddp-config/graphs/**` node yamls | node status, frontier |
| Loose pi sessions | `~/.pi/agent/sessions/**.jsonl` | non-GDDP interactive agents |

Polling cadence: 1–2s for the live view is plenty; events.jsonl tails give
near-real-time traces.

## Steering plane (proven 2026-08-13, do not reinvent)

- **Steer a GDDP attempt:** append one JSON line `{"ts":…,"message":…}` to
  `<attempt>/steer.jsonl`. The supervisor drains it ~1s cycles and delivers
  `{"type":"steer"}` into the live pi RPC session — the agent incorporates it
  mid-turn. Verified live: agent obeyed, clean agent_end, receipt reflected
  the steered work. (Runtime commits 57ca4ec, bb88be5.)
- **Cancel an attempt:** `touch <attempt>/cancel.requested` — the supervisor's
  cancel watcher aborts and terminates.
- **Steer a loose pi session:** via pi-intercom transport (message to a named
  session). Lower priority than the GDDP path; mark as milestone-optional.

Both GDDP channels are plain files — fleet needs no RPC client, no protocol
implementation, no pi library.

## Views (milestones, each binary-verifiable)

**M1 — fleet list.** One line per live agent: project/node, phase
(dispatch/running/evaluating/done), age, worktree `Nf +X/-Y`, last-write age
with >3min silence flag. This is tonight's `gddp watch` fleet view, lifted
out of the gddp CLI into the standalone tool. Verify: running `fleet` during
a live attempt shows it within one poll cycle.

**M2 — agent trace.** Select an agent → live-scrolling render of its
events.jsonl: turn boundaries, tool calls (name + target), steer insertions
marked. Verify: during a live attempt, a `git commit` tool call appears in
the trace within 2s of hitting events.jsonl.

**M3 — steer/cancel.** From the trace view, `s` opens a message line →
appends to steer.jsonl; `x` → cancel.requested (with confirm). Verify: steer
a soak node mid-run; the attempt's events.jsonl shows the steer accepted and
the final receipt reflects it.

**M4 — verdicts and receipts.** Per node: latest verdict, lane breakdown,
receipt path, linked from the fleet/trace view. Verify: after an evaluation
completes, the verdict shows without restart.

**M5 — multi-host (later).** Same views over SSH against khoj-38. Cheap
because everything above is files.

## Non-goals

- Not a dispatcher. No node authoring, no graph writes, no job state writes.
- Not a replacement for `gddp node browse` (human acceptance stays there).
- No web framework, no account system, no remote control beyond the file
  channels above.

## Why this shape

Today proved both halves: the data plane carried a full 4-node soak loop
(every phase reconstructible from files alone), and the steer channel moved
a live agent mid-turn from a plain file append. Fleet is those two proven
mechanisms behind one pane of glass — the operator's window into the loop
that never shares fate with any agent process.
