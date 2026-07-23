# AGENTS — node_status_history

## Why this exists

**Status without reason is a trap.** Seeing `deferred` alone does **not** mean
the work was bad, that dependents must stay blocked forever, or that the node is
dead. The reason is more important than the status enum for how you act next.

## Required behavior

1. Before interpreting a non-`ready` / non-`complete` graph status, read the
   latest reason for that node:
   - CLI: `gddp node show --project <p> <node-id>`
   - Files: `node_status_history/<project_id>/<node_id>.jsonl` (last line)
2. Treat `reason` as operator intent. Act on the reason, not on folklore about
   what the status word “usually” means.
3. Never invent a quality failure, graph freeze, or permanent block from a bare
   `deferred` / `cancelled` / `complete` label.
4. When *you* propose a status change for a human, draft a concrete `--reason`.
   Do not propose status-only changes.
5. Do not rewrite or delete history files. Append only via the CLI / library.
6. Do not put reasons into node YAML. This directory is the durable reason store
   for B-path (graph body stays status-only).

## File contract

JSONL, one object per line. Required keys: `ts`, `project_id`, `node_id`,
`from_status`, `to_status`, `reason`, `kind` (`graph` | `queue`), `source`.
See `scripts/node_status_history.py`.
