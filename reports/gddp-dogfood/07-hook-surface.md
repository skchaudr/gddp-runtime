# Hook surface inventory — git commit / push side effects

Node: `node-07-hook-surface`  
Job: `job_20260811T055756457be8b25accfc` (attempt 0)  
Base: `450eca1cffe1113b3af15db0b2ab65b7c0eb5b61`  
Inventory date: 2026-08-11  
Worktree: `/tmp/gddp-agent-wt-su9z28sl` (gitdir → `/data/repos/gddp-runtime/.git/worktrees/gddp-agent-wt-su9z28sl`)  
Scope: repo-local hook surfaces named by the node (`.agents/`, `.git/hooks`, graphify config), plus adjacent push-side machinery found while inventorying.

## Method

1. List `.agents/`, `.git/hooks` (common dir), and search for graphify config / install paths.
2. Read install/config files and quote the lines that wire each hook.
3. Check live git config for `core.hooksPath` (local/global/system) and whether non-sample hooks exist.
4. Confirm `graphify` CLI / Python module presence in this environment.
5. Run `python3 -m pytest -q` and quote the suite tail line under Validation.

## Executive finding

**Nothing in this worktree fires on `git commit` or `git push` today.**

| Surface | Present in repo? | Fires on git commit/push? | Live in this worktree? |
|---|---|---|---|
| `.agents/` Antigravity hooks | yes | **no** (agent lifecycle only) | config present; host must load `.agents/hooks.json` |
| `.git/hooks` | sample templates only | **no** (samples are not executable hooks Git runs) | only `*.sample` |
| graphify post-commit | **no config / no hook installed** | would fire post-commit **if** installed | CLI + module absent; no hook file |
| mission push guard pre-push | archived code only | would fire on push **during a guarded mission env** | not installed; module under `scripts/_archive/` |

---

## 1. `.agents/` — Antigravity / agent lifecycle hooks

### Layout

```text
.agents/
├── hooks.json                          # install/wiring config
├── hooks/
│   ├── ag_natural_guard.py             # hook implementation (executable)
│   └── test_ag_natural_guard.py
└── rules/
    └── natural-bounded-autonomy.md     # companion policy text (not a hook runner)
```

### What triggers it

These hooks fire when an **agent host** that understands `.agents/hooks.json` runs a session — not when a human or script runs `git commit` / `git push`.

| Event key | Trigger | Command | Side effect class |
|---|---|---|---|
| `PreInvocation` | session / invocation start | `python3 ./hooks/ag_natural_guard.py pre-invocation` | injects ephemeral intent reminder |
| `PreToolUse` | before matched tools (read/search/run/write/edit) | `… pre-tool-use` | allow / ask / deny mutating tools from operator intent |
| `PostToolUse` | after any tool (`matcher: "*"`) | `… post-tool-use` | audit only |
| `Stop` | agent turn stop | `… stop` | allow stop + audit |

Implementation entrypoints (`.agents/hooks/ag_natural_guard.py`):

```text
mode == "pre-invocation"  → inject reminder JSON
mode == "pre-tool-use"    → evaluate_pre_tool_use (intent gate)
mode == "post-tool-use"   → audit, empty result
mode == "stop"            → audit, {"decision": "allow"}
```

### Config lines that install each hook

From `.agents/hooks.json` (entire install surface):

```json
{
  "natural-bounded-autonomy": {
    "enabled": true,
    "PreInvocation": [
      {
        "type": "command",
        "command": "python3 ./hooks/ag_natural_guard.py pre-invocation",
        "timeout": 5
      }
    ],
    "PreToolUse": [
      {
        "matcher": "list_permissions|list_dir|view_file|find_by_name|search_text|run_command|write_to_file|replace_file_content|multi_replace_file_content|edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ./hooks/ag_natural_guard.py pre-tool-use",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ./hooks/ag_natural_guard.py post-tool-use",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python3 ./hooks/ag_natural_guard.py stop",
        "timeout": 5
      }
    ]
  }
}
```

There is no separate installer script in-repo: presence of `.agents/hooks.json` **is** the install. Paths are relative (`./hooks/…`), so the host must run with `.agents/` as the hooks root (or equivalent resolution).

### Does **not** mutate the tree on git events

The guard can block/ask on agent tool use (writes, destructive git via agent `run_command`, etc.). It does not register a git hook and does not run when git itself commits or pushes.

---

## 2. `.git/hooks` — native Git hooks

### Live state (this clone / worktree)

- Worktree gitfile: `gitdir: /data/repos/gddp-runtime/.git/worktrees/gddp-agent-wt-su9z28sl`
- Common hooks dir: `/data/repos/gddp-runtime/.git/hooks/`
- `git config --get core.hooksPath` → **unset** (exit 1) at local, global, and system scopes checked from this worktree
- Active (non-`.sample`) hooks: **none**

Contents of the common hooks directory (all stock Git samples):

```text
applypatch-msg.sample
commit-msg.sample
fsmonitor-watchman.sample
post-update.sample
pre-applypatch.sample
pre-commit.sample
pre-merge-commit.sample
pre-push.sample
pre-rebase.sample
pre-receive.sample
prepare-commit-msg.sample
push-to-checkout.sample
update.sample
```

### What would trigger them

Git only executes a hook file when it is named without `.sample` and is executable (or pointed at via `core.hooksPath`). Samples are documentation templates; **they never run**.

| Sample name | Would fire if activated | Typical purpose |
|---|---|---|
| `pre-commit.sample` | before commit object is written | lint/test gate |
| `prepare-commit-msg.sample` / `commit-msg.sample` | commit message edit/validate | message policy |
| `post-commit` (not present even as sample in some installs; **absent here**) | after commit succeeds | rebuilds, notifications |
| `pre-push.sample` | before refs are sent | push policy |
| others | merge/rebase/receive/applypatch paths | as named |

### Config lines that install each hook

**None in this repo.** `setup.sh` does not install hooks. No `.githooks/`, no `core.hooksPath` assignment in committed config, no husky/lefthook/pre-commit framework files.

Verified absence:

```text
find . -name '.pre-commit-config.yaml' -o -name 'lefthook.yml' -o -name '.husky'  → empty
```

---

## 3. Graphify — commit-hook product (not installed here)

### Live state

| Check | Result |
|---|---|
| `graphify-out/` in worktree | missing |
| graphify config files (`.graphify*`, `graphify.toml/yaml/json`) under repo | **none** |
| `command -v graphify` | not found |
| `python3 -c 'import graphify'` | `ModuleNotFoundError` |
| non-sample `post-commit` under `.git/hooks` | **absent** |
| `## graphify` section in `AGENTS.md` | **absent** |
| `.agents/rules/graphify.md` | **absent** |

### Repo evidence that the surface is *expected* elsewhere

`.gitignore` is the only in-repo install-adjacent evidence:

```gitignore
# Graphify rebuild cache
graphify-out/cache/
graphify-out.pi-local-backup
…
# generated by graphify commit hook — rebuildable, never commit
graphify-out/
```

Operational mentions (not install config):

- `readiness-report-2026-07-18.md` — notes stale `graphify-out` and suggests `graphify update .`
- `deploy/_archive/BIGPI_RUNBOOK.md` — “local graphify commits ride on top”

### What would trigger it (when installed)

Documented external installer (skill reference `graphify/references/hooks.md`, not vendored in this repo):

```bash
graphify hook install    # install
graphify hook uninstall  # remove
graphify hook status     # check
```

**Trigger:** after every successful `git commit` (`post-commit`).  
**Behavior (documented):** `git diff HEAD~1` → re-AST-extract changed **code** files → rebuild `graphify-out/graph.json` and `GRAPH_REPORT.md`. Doc/image-only commits ignored by the hook. Appends to an existing `post-commit` rather than replacing it.

Optional agent wiring (not a git hook):

```bash
graphify agents install   # writes ## graphify section into AGENTS.md
```

### Config lines that install each hook **in this repo**

**None.** There is no checked-in graphify hook script, no committed `post-commit`, and no project graphify config file. Install is an out-of-band CLI action that would mutate `.git/hooks/` (untracked by design).

---

## 4. Adjacent surfaces (not git hooks; recorded for push/commit confusion)

### 4a. Archived mission push guard (would install a real `pre-push`)

Path: `scripts/_archive/mission_push_guard.py`  
Live path `scripts/adapters/mission_push_guard.py`: **gone** (archived in `204148e` Stage 1 / handoff 089).  
README still lists the live path — documentation drift.

When a mission runner called `install_git_push_guard`, it wrote a PATH `git` shim **and** a `pre-push` hook, then pointed env git config at that directory:

```python
hook = directory / "pre-push"
hook.write_text(
    "#!/bin/sh\n"
    f"exec {shlex.quote(sys.executable)} "
    f"{shlex.quote(str(Path(__file__).resolve()))} "
    f"{_PRE_PUSH_HOOK_ARG} \"$@\"\n"
)
…
_append_git_config(guarded, "core.hooksPath", str(directory.resolve()))
```

**Trigger if active:** `git push` under the guarded environment.  
**Not active** in ordinary interactive commits/pushes on this worktree (`core.hooksPath` unset; no mission guard dir on PATH).

### 4b. GitHub Actions — issue label, not commit/push

`.github/workflows/jules.yml`:

```yaml
name: Jules
on:
  issues:
    types: [labeled]
jobs:
  jules:
    if: github.event.label.name == 'jules'
    uses: google/jules/.github/workflows/jules.yml@main
    secrets: inherit
```

**Trigger:** GitHub `issues` event with label `jules`. Does not run on `push` / `pull_request`.

### 4c. GitHub → intake webhooks (remote ops, not repo hooks)

`scripts/intake_server.py` + deploy docs: external GitHub repo webhooks POST to the control-plane intake URL. Those are **remote webhook subscriptions**, not files under `.git/hooks` or `.agents/`.

### 4d. `setup.sh`

Installs Flask and prints a snapshot. **No hook installation.**

---

## Commit / push side-effect map (this worktree, 2026-08-11)

| Operator action | What runs |
|---|---|
| `git commit` | Git only. No pre-commit / commit-msg / post-commit active. No graphify rebuild. |
| `git push` | Git only. No pre-push active. No mission push guard. |
| Agent tool use (host loading `.agents/hooks.json`) | `ag_natural_guard.py` on PreInvocation / PreToolUse / PostToolUse / Stop |
| `git commit` after someone runs `graphify hook install` | (future) graphify post-commit rebuild of `graphify-out/` |
| Mission worker with archived guard re-enabled | (future/historical) PATH git shim + `pre-push` via temp `core.hooksPath` |

---

## Validation

Command: `python3 -m pytest -q` (this worktree, no Flask installed in the environment).

Suite tail line:

```text
4 failed, 622 passed in 36.53s
```

Failure class (all four): `ModuleNotFoundError: No module named 'flask'` from `scripts/intake_server.py` import during intake tests, plus one `deploy/rig1-heartbeat/test_rig1_render_plist.py` failure observed in the same run. No code or test changes were made by this node; inventory-only.

---

## Acceptance checklist

| ID | Criterion | Status |
|---|---|---|
| `report-exists` | `reports/gddp-dogfood/07-hook-surface.md` exists and non-empty | met |
| `hooks-listed` | every hook surface (`.agents/`, `.git/hooks`, graphify) listed with trigger | met |
| `evidence` | config/install lines quoted per surface | met (agents full JSON; git hooks = none; graphify = gitignore + external install CLI; archived pre-push installer quoted) |
