
## Claude Hooks 

Incredible catalog and note with explicit worktree removal mentions 

/Users/sab-mini/Obsidian/SSD/00 Inbox/Official Claude Code Hooks Docs with Explanations and Full List.md

## Codex 


  Hooks
  Lifecycle hooks from config and enabled plugins.

  Event                 Installed   Active      Description
  PreToolUse            1           0           Before a tool executes
  PermissionRequest     0           0           When permission is requested
  PostToolUse           2           0           After a tool executes
  PreCompact            0           0           Before context compaction
  PostCompact           0           0           After context compaction
  SessionStart          4           0           When a new session starts
  SessionEnd            0           0           Right before a session ends
  UserPromptSubmit      1           0           When the user submits a prompt
  SubagentStart         0           0           When a subagent is created
  SubagentStop          0           0           Right before a subagent ends its turn
  Stop                  0           0           Right before Codex ends its turn

  Press enter to view hooks; esc to close



## Grok  

Highly tempted to install: https://github.com/DominikTobureto/awesome-grok-build

Complete docs on hooks  

/Users/sab-mini/Obsidian/SSD/03 Resources/AI/Grok Build docs - hooks.md

▎❯  grok -p "what hooks does grok support, like can I configure one that auto-runs a worktree commit and cleanup or other types of procedure like th
at atthe end each run?"
**Yes.** Grok hooks are command/HTTP scripts on lifecycle events. Config: `~/.grok/hooks/*.json` (global) or `<project>/.grok/hooks/*.json` (needs `
/hooks-trust`). Docs: `~/.grok/docs/user-guide/10-hooks.md`.

### Events
| Event | Fires when | Blocking? |
|---|---|---|
| `SessionStart` | session opens | no |
| `UserPromptSubmit` | you send a prompt | no |
| `PreToolUse` | before a tool | **yes — deny** |
| `PostToolUse` / `PostToolUseFailure` | after tool | no |
| `PermissionDenied` | perm system denies | no |
| `Stop` | turn completes (not Esc interrupt) | **yes — block stop / keep agent going** |
| `StopFailure` | API error end | no |
| `SubagentStart` / `SubagentStop` | subagent life | Stop can block |
| `PreCompact` / `PostCompact` | compaction | no |
| `SessionEnd` | session exits | no |
| `Notification` | agent notifies | no |

### End-of-run automation (your case)
Use **`SessionEnd`** for worktree commit + cleanup when the session dies, or **`Stop`** when a turn finishes.

`Stop` caveats:
- Filter `reason == "end_turn"` (also fires on session end as observe-only)
- Max 8 “keep working” blocks per turn, then forced stop
- Default timeout 600s for Stop gates

Minimal pattern:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bin/worktree-finish.sh",
            "timeout": 120
          }
        ]
      }
    ]
  }
}
```

Script gets JSON on stdin (`cwd`, `sessionId`, `workspaceRoot`, …) + env `GROK_SESSION_ID`, `GROK_WORKSPACE_ROOT`. Passive hooks: just exit 0.

Manage: `/hooks` modal, `/hooks-list`, reload with `r`.

