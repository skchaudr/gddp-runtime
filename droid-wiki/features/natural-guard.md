# Natural guard

> Restored from the 2026-07-13 wiki. This is a peripheral/historical feature: its implementation is no longer in the active runtime source tree and is retained only in archived documentation. Do not treat it as an installed GDDP control.

The natural guard was a pre-tool-use authorization hook that treated natural language as the control plane for what an agent was allowed to do. It was borrowed from the `.pi` project and adapted for Antigravity and warp-like agent harnesses. The core idea was that pasted logs, code, or quoted output should never authorize a mutation; only the operator's own words outside paste markers carried intent.

The historical implementation lived in `.agents/hooks/ag_natural_guard.py` and was wired through `.agents/hooks.json`. Those paths are not active source files in the current tree.

## Paste-marker splitting

The guard's first job is to separate operator intent from inert context. It uses `>>>` and `<<<` as paste markers:

- Text inside `>>> ... <<<` is pasted context: logs, file contents, quoted agent output, or evidence. It is never an instruction and never authorizes action.
- Text outside the markers is operator intent. The bottom-most operator segment (text after the last closing `<<<`) refines or overrides earlier operator text.

The function `split_paste_marked_user_turn()` walks the user's turn line by line, toggling between `operator` and `paste` modes whenever it hits a marker, and returns a list of `(kind, text, start_line)` segments. `operator_segments()` and `operator_text()` are thin wrappers that extract just the operator-authored portions.

This matters because a user might paste a stack trace that contains the word "delete" or a code snippet that says `rm -rf build/`. Without the split, a naive keyword match would treat that as authorization. The guard ignores everything inside the markers.

## Tool call classification

When a tool is about to fire, `evaluate_pre_tool_use()` decides whether to allow, ask, or deny. It first checks the tool name against two sets:

- **Read tools** (`list_permissions`, `list_dir`, `view_file`, `find_by_name`, `search_text`, `grep`, `read_file`) are always allowed.
- **Write tools** (`write_to_file`, `replace_file_content`, `multi_replace_file_content`, `edit`) are classified as `write-edit` unless the target is an artifact write (which is allowed without operator authorization).

For `run_command`, the guard parses the command string with `classify_command()` and inspects it against several mutation classes:

| Class | Trigger examples |
|---|---|
| `write-edit` | `tee`, `sponge`, shell redirection (`>>`), in-place `sed -i`/`perl -i`, `awk -i inplace`, interpreter write calls (`write_text`, `writeFileSync`, etc.) |
| `remove` | `rm` anywhere in the command |
| `move` | `mv` anywhere in the command |
| `copy` | `cp` anywhere in the command |
| `git-reset-hard` | `git reset --hard` sequence |
| `git-restore` | `git restore` sequence |
| `git-checkout` | `git checkout` followed by a path or non-flag branch name |
| `external-infra` | `ssh`, `gcloud`, `gsutil` |
| `install` | `pip`/`uv`/`npm`/`pnpm`/`yarn`/`brew` paired with `install` |

Read-only git commands (`git status`, `git diff`, `git log`) are explicitly allowed. Anything the classifier cannot place falls through to `read-only command` and is allowed.

## Authorization verb matching

Once a mutation class is established, the guard checks whether the operator's text actually authorizes it. Each class has a set of `AUTH_VERBS`:

- **write-edit**: write, edit, change, update, fix, add, create, apply, implement, build
- **remove**: delete, remove, rm
- **move**: move, rename, mv
- **copy**: copy, cp
- **git-reset-hard**: reset, restore, revert
- **install**: install, upgrade, add dependency, dependency
- **external-infra**: ssh, gcloud, gsutil, vm, gcs, upload, deploy, reindex, remote, khoj

The function `has_authorization()` collects all operator segments, then:

1. Checks the tail segment for negating phrases (`"do not change"`, `"read-only"`, `"plan only"`, `"just review"`, etc.). If the tail negates, authorization fails.
2. Checks the combined operator text for negation. If the combined text negates but the tail does not re-authorize the specific mutation class, authorization fails.
3. Searches the combined operator text for any authorization verb matching the mutation class using word-boundary regex.

The decision matrix then applies class-specific rules:

- **Destructive classes** (`remove`, `git-reset-hard`): denied if unauthorized; `force_ask` even if authorized (the operator must confirm a destructive action).
- **Infra/install classes** (`external-infra`, `install`): denied if unauthorized; `force_ask` if authorized (external side effects need confirmation).
- **write-edit**: `force_ask` if unauthorized, listing the expected verbs so the operator knows what signal is missing.

A target path outside the workspace or artifact roots is denied outright, regardless of authorization.

## Git safety: auto-checkpoint before first write

Before allowing any write, `_ensure_git_safety()` enforces two rules:

1. **The target must be inside a git repository.** If `git rev-parse --show-toplevel` fails, the write is denied with a message telling the operator to `git init` and commit a baseline first.
2. **The repo gets an auto-checkpoint once per conversation.** If the repo has uncommitted changes and no checkpoint marker exists yet for this conversation, the guard runs `git add -A` and `git commit -m "checkpoint: pre-agent snapshot"`. A marker file (`.natural-guard-checkpoint-{conversationId}-{repoRoot}`) is written to the artifact directory so the checkpoint only fires once. If the commit fails, the guard falls back to `ask` so the operator can commit or stash manually.

This guarantees that every agent write is reversible via git, without relying on the operator to remember.

## Pre-invocation reminder injection

At the start of each invocation, the `pre_invocation()` hook injects an ephemeral reminder into the agent's context. The reminder reinforces the paste-marker rule, the bounded-chunk execution model, and the evidence-citation requirement: any claim about user intent, topology, infra, or repo state must cite observed evidence or say "not established from evidence." This is not a decision gate, it is a nudge that keeps the agent aligned before any tool fires.

## Audit trail

Every hook event (pre-invocation, pre-tool-use, post-tool-use, stop) is written to `natural-harness-audit.jsonl` in the artifact directory. Each record includes a timestamp, conversation ID, step index, tool name, decision, reason, and the redacted tool arguments. The `_redact()` function scrubs environment variables matching `KEY`/`SECRET`/`TOKEN`/`PASSWORD` patterns, GitHub tokens (`ghp_...`), and API keys (`sk-...`) before they hit the log.

## Key source files

| File | Purpose |
|---|---|
| `.agents/hooks/ag_natural_guard.py` | The guard implementation: paste-marker splitting, tool classification, authorization checks, git safety, audit logging. |
| `.agents/hooks.json` | Hook registration: maps lifecycle events (PreInvocation, PreToolUse, PostToolUse, Stop) to guard invocations. |
| `.agents/rules/natural-bounded-autonomy.md` | The rule document the guard enforces: paste markers, planning mode, autonomous chunks, version control as safety net, receipts. |

## Related pages

- [Features](index.md)
- [Architecture](../overview/architecture.md)
- [Patterns and conventions](../how-to-contribute/patterns-and-conventions.md)
