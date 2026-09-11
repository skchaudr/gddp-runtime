# Cursor project-session boundary

Date: 2026-09-10
Authority: Sab's explicit correction in the interactive Cursor architecture review.
State: operator-selected direction; runtime implementation remains pending.

## Direction

One worktree per project session. Each packet becomes a commit in that tree.
Sab identified Cursor's per-attempt workspace lifecycle as a regression from the
August 16 session design. Agent-authored adapter comments, reviews, and capability
flags describe implementation choices; operator intent governs their correction.

Keep these lifetimes distinct:

- A node carries human-owned intent.
- An attempt identifies an effort and its evidence for that node.
- An invocation launches an executor process; successive invocations can use the same checkout.
- Conversational continuity belongs to the executor session and its supported resume mechanism.
- The project session owns the workspace across packets and their attempt records.

Each Cursor orchestrator belongs to one logical project session: one session,
one worktree, many nodes. That session can start, stop, and resume. Its identity,
Cursor conversation association, and worktree mapping survive those process
transitions. Attempts remain distinct records within the session. A stopped
process leaves the workspace available for the session's next invocation.

A packet return retains the workspace. Record attributable start/result commits
and an attempt ref for each packet. Preserve earlier work when handling retries;
retry packets retain the same node intent and carry the concrete findings.
Record planned-base and actual-base evidence distinctly, and treat their
differences as evaluation/integration concerns. Workspace retirement is an
explicit logical-session lifecycle operation, separate from process exit or
idle timeout, and preserves every piece of work before checkout removal.

## Verified implementation gap

- Commit `ed0407b` and `.handoffs/101-session-worktree.md` record the August 16
  session-worktree change. Current `scripts/adapters/pi_rpc_adapter.py` still
  creates `session_worktree` once in `run_orchestrator` and persists successive
  packet results in that tree. Its `finally` cleanup removes the checkout when
  the orchestrator process exits. Reuse its multi-packet behavior; change that
  cleanup to retain the logical session's workspace across process stops.
- Mini's preserved `aa-cli-tui-pass` spool provides a concrete reuse example,
  verified read-only on 2026-09-10. Twelve attempt directories from August 24–25
  reference the same `gddp-agent-wt-mf4i0xvw` checkout and the same session file,
  `2026-08-24T22-15-52-682Z_01a035d8-246a-7fbb-ad49-beec72119baf.jsonl` under
  `jobs/local-subprocess-spool/_orchestrators/aa-cli-tui-pass/pi-session/`.
  They cover five node IDs and record ten distinct result commits. This proves
  recorded multi-node/attempt reuse; cross-process restart persistence remains
  an implementation acceptance check.
- `scripts/adapters/cursor_cli_adapter.py::dispatch` calls
  `scripts/runtime/local_attempt.py::dispatch_worktree_attempt`, which creates a
  fresh tree. `_run_cursor_turn` supplies a singleton packet list;
  `persist_post_turn_result` removes a successfully persisted attempt's tree.
- Cursor's preamble requires solo execution, and its declaration sets
  `native_subagents=False`. The startup/resume and tool-format probes exercised
  other capabilities. Their limited coverage became an execution restriction.
- `scripts/runtime/heartbeat/continuity_policy.py` defaults to cold dispatch and
  limits resume to an operator marker. Its same-cwd guard is coupled to the
  fresh-attempt workspace arrangement. Restore session ownership before deciding
  how supported conversational continuity is selected.

## Correction scope

Reuse the existing project-session lifecycle and per-attempt evidence machinery.
Retain transport-specific Cursor argv, stream translation, cancellation, and
result handling where they fit. A new generic orchestration framework requires
separate justification.

Replace solo-only instructions with the intended execution role. Exercise Cursor's
[documented custom subagents](https://cursor.com/docs/context/subagents) on the
installed CLI and align capability declarations with that evidence. Package GDDP
working instructions in an explicitly loaded
[skill](https://cursor.com/docs/context/skills), keeping node intent and evidence
ownership in GDDP. Verify that the agent reads the skill and invokes the intended
custom subagent. Preserve explicit model selection through the existing resolver;
the particular test model and test-node batch remain operator choices.

Prove two packets produce distinct attributable commits in the same workspace,
with per-attempt results and events. Also check retry, cancellation, process
restart, and teardown preservation. These checks establish implementation
behavior; human acceptance continues to own graph truth.

## Graph placement and remaining work

The current `gddp-runtime` graph contains the executor-neutral contract and direct
round-trip nodes; their scope predates this Cursor correction. The bounded
implementation proposal is
[`cursor-project-session-restoration.yaml`](../proposals/cursor-project-session-restoration.yaml).
It stays outside graph discovery until human materialization.

Proposed dependencies: empty; reuse the existing contract and `pi_rpc` behavior
as evidence. Existing nodes and the current frontier retain their state. This
keeps the correction independent of accepting or reopening historical work.
The main implementation cost is routing packet returns and cancellation through
a session-owned workspace; overlapping writes and loss during teardown are the
principal risks. Start with serialized packet execution in one session and a
two-packet check. Keep model resolution, event translation, result refs, and
existing evidence readers usable throughout the correction.
