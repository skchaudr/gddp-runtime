# OpenClaw v0 Spec

**Status:** Draft — v0
**Last updated:** 2026-03-15
**Module location:** `scripts/runtime/openclaw/`

---

## Purpose

OpenClaw is the reasoning and control layer for the GDAD system. It is the part of the system that wakes up, reads the current state of the world, decides what to do next, acts, and goes back to sleep.

Without OpenClaw, the GDAD system has no persistent intelligence. Jules executes work. The gddp-runtime dispatches jobs and records results. But nothing is deciding *what to do next* or *whether the work was good enough*. OpenClaw fills that gap.

**System roles:**
- Jules = hands (executes coding work, cannot run in a loop)
- gddp-runtime = nervous system (dispatch, webhook intake, SQLite, graph reads/writes)
- OpenClaw = brain (reads state, reasons, decides, acts, escalates)

---

## Trigger Model

OpenClaw is **event-driven, not always-on**. It wakes up, makes a decision, acts, and exits.

Two trigger sources:

1. **Webhook trigger** — fires immediately when Jules opens or merges a PR
   - Event type: `pull_request.opened` or `pull_request.closed` (merged)
   - Routed by the classifier with `route="openclaw"`
   - Fastest path: OpenClaw responds to Jules's actions in near-real-time

2. **Cron fallback** — runs every 15–30 minutes
   - Detects stuck or stalled Jules sessions
   - Handles cases the webhook missed (delivery failure, Pi was offline)
   - Should be idempotent: safe to run even when nothing is stalled

**Wake cycle:** receive trigger → read context → decide → act → write result → exit

---

## Context Window

When OpenClaw wakes, it reads three sources to build its context:

### 1. gddp-config graph YAML

Reads the project graph file for the active project(s). Extracts:
- Which nodes are `pending`, `blocked`, `in_progress`, or `complete`
- Node dependencies (`depends_on`)
- Node acceptance criteria and constraints
- Node type and priority

### 2. SQLite recent rows

Reads the last N rows from the `events`, `jobs`, and `results` tables. Extracts:
- Recent Jules activity (what jobs were dispatched, when)
- Recent PR results (what nodes completed, what failed)
- How long the current active job has been running
- Whether there are stale "running" jobs from before the system restarted

### 3. Current event

The trigger itself — either:
- A webhook payload: `{"event": "pull_request.closed", "repo": "skchaudr/vault-doctor", "pr": 51, "merged": true, "node": "triage-cli-core"}`
- A cron signal: `{"event": "cron", "reason": "scheduled_check", "timestamp": "..."}`

---

## Decision Logic

OpenClaw reads context and selects exactly one action per cycle. The decision follows this priority order:

1. **Is there a stale state to clean up?** (jobs showing "running" for > 6 hours, events showing "received" for > 6 hours) → mark them failed/expired in SQLite, then re-evaluate
2. **Did a PR just merge?** → run `review_pr` to validate it, then `accept_node` if it passes
3. **Is there a node ready to dispatch?** (status=pending, all depends_on complete) → run `dispatch_next`
4. **Is there a node that has been in_progress too long?** (> 24 hours with no result) → run `escalate`
5. **Is everything either complete or blocked with no obvious action?** → run `escalate` or exit cleanly

OpenClaw must not dispatch if a Jules job is already in_progress for that project (one active job per project at a time).

---

## Powers (v0 scope — exactly 4)

### 1. `dispatch_next`

Selects the next eligible node and creates a GitHub issue for Jules.

**Eligible node criteria:**
- `status: pending`
- All nodes in `depends_on` have `status: complete`
- No other job currently `in_progress` for this project

**Action:**
- Write a GitHub issue to the target repo using the dispatch template
- Include the node spec, acceptance criteria, constraints, and PR body contract
- Add the `jules` label
- Write a job row to SQLite with `status=dispatched`

**Output:**
```json
{"action": "dispatch_next", "node_id": "...", "issue_number": 42, "ok": true}
```

### 2. `review_pr`

Reads Jules's submitted PR via GitHub API and evaluates whether it meets the node's acceptance criteria.

**Inputs:** PR number, repo, node_id, node acceptance criteria from YAML

**Checks (v0 — lightweight):**
- Did the PR touch the expected files? (based on acceptance criteria keywords)
- Are there any files that were explicitly forbidden in constraints?
- Did the PR include the required `node: <id>` metadata block?
- Did tests pass? (read from PR check status via GitHub API)

**Output:**
```json
{"action": "review_pr", "node_id": "...", "pr": 51, "verdict": "pass"|"fail", "reason": "...", "ok": true}
```

If verdict is `pass`, OpenClaw proceeds to `accept_node`.
If verdict is `fail`, OpenClaw posts a review comment on the PR with specific feedback and writes a result row with `status=review_failed`.

### 3. `accept_node`

Marks a node complete after validating the PR met expectations.

**Prerequisite:** `review_pr` returned `verdict: pass`

**Action:**
- Call `graph_updater.update_graph_node_complete()` — sets status=complete in the graph YAML via GitHub Contents API
- Write a result row to SQLite with `status=completed`
- Optionally trigger the next dispatch cycle immediately (within same wake cycle)

**Output:**
```json
{"action": "accept_node", "node_id": "...", "commit_sha": "...", "ok": true}
```

### 4. `escalate`

Flags a blocked or unexpected state. Notifies the human and writes a record.

**Triggers:**
- A node has been in_progress > 24 hours with no PR
- `review_pr` failed twice for the same node
- No eligible nodes exist but the project is not complete
- OpenClaw cannot parse the graph or context (data integrity issue)
- Unexpected error during any action

**Action (v0):**
- Write a result row to SQLite with `status=escalated` and a human-readable `reason`
- Print a structured log message that can be read via `journalctl`
- (Future: post to Telegram or GitHub issue)

**Output:**
```json
{"action": "escalate", "reason": "...", "node_id": "...|null", "ok": true}
```

---

## Output Format

Every OpenClaw decision is written as a structured JSON object. This is the contract between OpenClaw and gddp-runtime.

```json
{
  "action": "dispatch_next" | "review_pr" | "accept_node" | "escalate",
  "node_id": "<node_id> | null",
  "ok": true | false,
  "reason": "<human-readable string on failure>",
  "<action-specific fields>": "..."
}
```

The result is:
1. Written to the `results` table in SQLite (always)
2. Logged to stdout/journalctl (always)
3. Returned to the caller (webhook router or cron handler) as a JSON response

---

## Failure Modes

| Failure | OpenClaw behavior |
|---|---|
| Cannot read graph YAML | `escalate` with reason: graph_read_failed |
| Graph YAML malformed | `escalate` with reason: graph_parse_failed |
| SQLite unreadable | `escalate` with reason: db_read_failed |
| GitHub API call fails | Retry once, then `escalate` with reason: github_api_failed |
| `review_pr` verdict: fail | Post comment on PR, write result row, exit |
| Node not found in graph | `escalate` with reason: node_not_found |
| Two jobs dispatched simultaneously | Should not happen — checked before dispatch. If detected: `escalate` |
| Unexpected exception | Catch at top level, `escalate` with traceback in reason |

OpenClaw must never silently swallow errors. Every failure writes a result row and a log line.

---

## Human Escalation Rules

Escalate immediately (do not attempt recovery) when:

1. The graph YAML cannot be read or parsed
2. SQLite is inaccessible
3. The same node has failed review more than once
4. A job has been in_progress for more than 24 hours
5. OpenClaw detects conflicting state (e.g., a node marked complete but a job still in_progress for it)
6. Any unhandled exception in the decision loop

Escalate after retry when:
1. A GitHub API call fails (retry once, then escalate)

Do not escalate for:
1. Normal "nothing to do" states (all nodes complete, or all pending nodes are blocked on dependencies)

---

## Stale State Handling (First Boot)

The SQLite database may contain stale rows from before the webhook was live:
- Jobs with `status=running` that were never completed
- Events with `status=received` that were never processed

On first wake, OpenClaw should:
1. Query for any jobs with `status=running` and `created_at < now - 6 hours`
2. Mark them `status=expired` with `reason=stale_on_boot`
3. Query for any events with `status=received` and `created_at < now - 6 hours`
4. Mark them `status=expired`
5. Then proceed with normal decision logic

This ensures stale state doesn't trigger false dispatches or reviews.

---

## Runtime Architecture

**Module location:** `scripts/runtime/openclaw/`

```
scripts/runtime/openclaw/
  __init__.py
  engine.py          — main decision loop: read context, decide, act
  context_reader.py  — reads graph YAML + SQLite state + current event
  powers/
    __init__.py
    dispatch_next.py  — creates GitHub issue for Jules
    review_pr.py      — reads PR via GitHub API, evaluates acceptance
    accept_node.py    — calls graph_updater, writes result row
    escalate.py       — writes escalation record, logs
```

**Entry points:**
- Called by webhook router: `from runtime.openclaw.engine import handle_event; handle_event(event_payload)`
- Called by cron handler: `from runtime.openclaw.engine import handle_cron; handle_cron()`

**Environment variables required:**
- `GITHUB_TOKEN` — PAT scoped to gddp-config contents:write
- `OPCLAW_ROOT` — path to SQLite DB and jobs directory (~/opclaw/ on Pi)
- `GDDP_CONFIG_PATH` — path to gddp-config repo clone on Pi

---

## Scope Discipline (v0 hard limits)

- **Exactly 4 powers.** Do not add a fifth.
- **One active job per project.** No parallel dispatch.
- **One PR closes one node.** No multi-node PR handling.
- **No retries inside a power.** Retry logic belongs in escalate at the engine level only.
- **No always-on loop.** OpenClaw wakes, decides, acts, exits.
- **No UI.** Output is JSON + logs only.
- **No Telegram/WhatsApp in v0.** Escalate writes to SQLite and logs. Notifications are future scope.
