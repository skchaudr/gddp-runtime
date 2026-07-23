# node_status_history

Human-owned reasons for graph (and optional queue) status changes.

## Human purpose

When you change a node’s status — especially to `deferred`, `complete`, or
`cancelled` — the **reason** is the real decision. Status alone is a label;
agents and future-you will misread it without why.

Record the reason at change time. Prefer a full sentence:

- good: `deferred: waiting on Jules API quota until Monday; work is fine, do not block unlocks`
- bad: `deferred` / `not now` / empty

## Layout

```
node_status_history/
  README.md          # this file
  AGENTS.md          # how agents must use this tree
  <project_id>/
    <node_id>.jsonl  # append-only transition records
```

Each JSONL line is one transition (schema in `scripts/node_status_history.py`).
Entry files are **local runtime state** — gitignored. This README and AGENTS.md
are the only committed files in this directory.

## CLI

Written by:

- `gddp node set-status … --reason "…"` (graph truth change; reason required)
- `gddp jobs set … --reason "…"` (queue state change; also appends here)

Read by `gddp node show` (latest reason + short history).
