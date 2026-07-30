---
type: 
format: 
status: 
tags: 
created: 2026/04/10, 20:04:38
modified: 2026/04/10, 20:04:45
title: GDDO - operator practice manual run checklist
---

```md
# GDDP Operator Practice Checklist

## Purpose

Use this checklist to learn the current boundary by running small, 

Current model:

- `gddp-config` = human-owned project truth
- `gddp-runtime` = execution machinery
- executor/agent = produces work and receipts
- human review = decides whether truth changes

The goal is to stop relying on a fuzzy mental model and instead answer questions from files, DB rows, and receipts.

---

## Core Questions

Before moving on from any run, be able to answer:

- What created this job?
- Why was this node selected?
- What exactly was dispatched?
- What did the executor return?
- Where is the receipt?
- Why is this job in `awaiting_review`?
- What exact human action would change graph truth next?

---

## Common Inspection Commands

Adjust paths as needed.

### Runtime DB

```bash
cd ~/repos/gddp-runtime

sqlite3 db/queue.db "select event_id,status,scope_status,classification from events;"
sqlite3 db/queue.db "select job_id,node_id,executor,status,queue_state from jobs;"
sqlite3 db/queue.db "select job_id,queue from queue_records;"
sqlite3 db/queue.db "select result_id,job_id,status,outcome,received_at from results;"
```

## Job Artifacts

```bash
ls -la jobs/
ls -la jobs/<job_id>/
find jobs/<job_id> -maxdepth 2 -type f | sort
```

## Graph Truth

```bash
cd ~/repos/gddp-config

find graphs/<project-id> -maxdepth 3 -type f | sort
sed -n '1,240p' graphs/<project-id>/project.yaml
sed -n '1,240p' graphs/<project-id>/nodes/<node-id>.yaml
```

---

## Run 1: Synthetic Receipt Drill

### Goal

Understand the filesystem and DB shape without involving a real repo or executor.

### Commands

```bash
cd ~/repos/gddp-runtime
python3 scripts/init_db.py

# scripts/dry_run.py was removed (797ce86)
# Use verifier dry-run E2E tests as the synthetic receipt check.
python3 -m pytest -q scripts/runtime/verification/test_dry_run_e2e.py
```

### Inspect

```bash
cd ~/repos/gddp-runtime

sqlite3 db/queue.db "select event_id,status from events;"
sqlite3 db/queue.db "select job_id,node_id,status,queue_state from jobs;"
sqlite3 db/queue.db "select result_id,job_id,status,outcome from results;"
find jobs -maxdepth 2 -type f | sort
```

### Checkpoints

- Confirm the verifier dry-run E2E test passes and prints no repo-write assertions.
- Confirm the synthetic flow returns a valid receipt object in the test assertions.
- Confirm no graph truth changed automatically (`gddp-config` untouched).

### Write Down

- What files made the flow legible?
- What still felt abstract?

---

## Run 2: Forward Dispatch On A Tiny Real Repo

### Goal

Watch the forward path create a real job from graph truth.

### Suggested Task Shapes

Pick one:

- add `--dry-run` to a CLI
- add one missing unit test
- rename a confusing function
- extract one small duplicated helper
- add a basic healthcheck endpoint

### Setup

1. Pick a boring, low-risk repo.
2. Add a small ready node in `gddp-config`.
3. Make sure the node has:
 - title
 - why
 - constraints
 - acceptance
 - allowed execution modes

### Commands

```bash
cd ~/repos/gddp-runtime
python3 -m runtime.heartbeat.runner \
--project <project-id> \
--repo <owner/repo> \
--config-path ~/repos/gddp-config
```

### Inspect

```bash
cd ~/repos/gddp-runtime

sqlite3 db/queue.db "select event_id,status,classification from events;"
sqlite3 db/queue.db "select job_id,node_id,executor,status,queue_state from jobs;"
sqlite3 db/queue.db "select job_id,queue from queue_records;"
find jobs -maxdepth 2 -type f | sort
```

Also inspect:

- the node in `gddp-config`
- the dispatched issue body or packet
- the selected executor

### Checkpoints

- Explain why that exact node was selected.
- Explain why that executor was selected.
- Explain what exact packet was dispatched.
- Confirm the job is `running` or `failed`, not magically "complete".

### Write Down

- Which field in the graph most strongly drove dispatch?
- What part of the packet still felt too executor-specific?

---

## Run 3: Receipt From Merged PR

### Goal

See the return path create a review receipt without touching graph truth.

### Setup

Use the job from Run 2.

Create or merge a PR with the required metadata block:

```text
node: <node-id>
job: <job-id>
```

### Commands

If you have the merged PR event captured in the DB, run the receipt path manually through the runtime flow you are using now.

If replay is easier in your environment:

```bash
cd ~/repos/gddp-runtime
python3 -m runtime.replay --result-id <result-id>
```

### Inspect

```bash
cd ~/repos/gddp-runtime

sqlite3 db/queue.db "select result_id,job_id,status,outcome,github_action from results;"
sqlite3 db/queue.db "select job_id,node_id,status,queue_state from jobs;"
sqlite3 db/queue.db "select job_id,queue from queue_records;"
```

Inspect the PR body too.

### Checkpoints

- Confirm a structured receipt was written.
- Confirm receipt `status` is `needs_review`.
- Confirm the job moved to `awaiting_review`.
- Confirm no graph files changed.

### Write Down

- What fields make the receipt traceable?
- What would make review easier next time?

---

## Run 4: Human Accept Drill

### Goal

Practice the truth boundary explicitly.

### Setup

Use a clean PR/receipt from Run 3.

### Review Inputs

Inspect:

- PR diff
- tests
- `results` row
- job artifacts
- node acceptance criteria in `gddp-config`

### Human Action

Manually update graph truth yourself in `gddp-config` only after review.

### Inspect

```bash
cd ~/repos/gddp-config
git diff -- graphs/<project-id>/project.yaml graphs/<project-id>/nodes/<node-id>.yaml
```

### Checkpoints

- You can state why the receipt was not enough by itself.
- You can state what human judgment made the graph update valid.
- You can describe exactly what changed in graph truth.

### Write Down

- What evidence made you comfortable accepting?
- What evidence would have made you reject?

---

## Run 5: Human Reject Or Defer Drill

### Goal

Internalize that executor success is not truth acceptance.

### Setup

Use a PR that is:

- incomplete
- weakly tested
- locally correct but globally risky
- missing clarity in summary/evidence

Still create the merged PR receipt if you want to practice the full path.

### Commands

Use the same inspection commands as Run 3.

### Human Action

Do not update `gddp-config`.

Leave the result as review evidence only.

### Checkpoints

- You can explain why the work is not accepted into truth.
- You can name the missing evidence or unresolved risk.
- You can choose one of:
- accept later
- retry
- defer
- reopen/supersede

### Write Down

- What exact condition blocked acceptance?
- What minimum next action would unblock it?

---

## Suggested Tiny Projects

Use side projects that are useful but safe.

### Good Candidates

- a one-file CLI
- a tiny Flask/FastAPI app
- a simple static-site helper
- a script repo
- a toy internal utility

### Good Task Examples

- add `--dry-run`
- add `--verbose`
- add one health endpoint
- add one test for an existing helper
- refactor a tiny duplicated function
- improve one error message path
- add logging around one command
- rename one ambiguous function and update tests

### Avoid For Practice

- auth
- database migrations
- external payment or auth APIs
- multi-service changes
- anything you would regret breaking

---

## Practice Log Template

### Run Log

- Date:
- Run Number:
- Repo:
- Project ID:
- Node ID:
- Job ID:
- Result ID:

### What Happened

- Event:
- Selected node:
- Selected executor:
- Job state after dispatch:
- Result state after return:
- Human decision:

### What I Verified

- Dispatch packet matched graph truth:
- Receipt linked correctly to job and node:
- Job moved to `awaiting_review`:
- Graph truth changed only by human action:

### What Felt Fuzzy

-
-
-

### What I Understand Better Now

-
-
-

### Next Improvement

-

```text

If you want, I can also turn this into a shorter “Pi terminal version” with just command blocks and checkboxes.
