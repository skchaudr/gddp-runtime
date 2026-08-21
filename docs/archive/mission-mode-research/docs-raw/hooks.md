# Hooks

Run deterministic shell commands at Droid lifecycle events for validation, policy, context injection, and automation.

Hooks are shell commands that run at defined points in a Droid
session. Use them for deterministic behavior that should happen every time, such as
validating tool calls, formatting changed files, injecting local context, logging activity,
or enforcing team policy.

<Warning>
  Hooks run automatically with your local environment and credentials. Review every hook command before registering it, use absolute script paths, and test in a safe environment first.
</Warning>

## Configuration

Hooks live alongside settings at each scope:

| Scope | File | Notes |
| :---- | :--- | :---- |
| User | `~/.factory/hooks.json` | Applies across your projects. |
| Project | `.factory/hooks.json` | Commit to share with teammates. |
| Enterprise | Org-managed settings | Loaded from Enterprise Controls and managed settings. |
| Legacy | `.factory/hooks/hooks.json` | Still loads. The next save writes `.factory/hooks.json` and archives the old file as `hooks/hooks.migrated.json`. |

If `hooks.json` is absent, Droid also reads hook declarations from the `hooks` key in the matching `settings.json`.

<Note>
  Always use absolute paths in hook commands. Hooks execute from Droid's current working directory, which can differ from your repository root. Use `"$FACTORY_PROJECT_DIR"/path/to/script.sh` for project scripts or a full path such as `/usr/local/bin/script.sh` for global scripts.
</Note>

### Structure

Hook files are keyed by event name. Each event contains matcher groups, and each group contains one or more shell commands.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Execute",
        "commandRegex": "^git ",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/local/bin/audit-git-command.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

| Field | Required | Source-validated behavior |
| :---- | :------- | :------------------------ |
| `matcher` | No | Empty, omitted, or `*` matches everything. Exact strings match one tool or lifecycle matcher. Regex patterns are supported and are case-sensitive. |
| `commandRegex` | No | Additional regex filter for Execute commands. It matches the actual shell command string when Droid has one. Invalid regex values are skipped. |
| `hooks` | Yes | Array of hook commands for the matcher group. |
| `type` | Yes | Currently only `"command"` is supported. |
| `command` | Yes | Shell command executed with JSON hook input on stdin. |
| `timeout` | No | Per-command timeout in seconds. Defaults to `60`. |

Common tool matchers include `Execute`, `Read`, `Edit`, `Create`, `ApplyPatch`, `LS`, `Glob`, `Grep`, `Task`, `FetchUrl`, and `WebSearch`. MCP tools use the `mcp__<server>__<tool>` naming pattern, so `mcp__.*` matches all MCP tools.

## Quickstart

This example logs every shell command Droid runs.

<Steps>
  <Step title="Open the hooks manager">
    In Droid, run:

    ```text
    /hooks
    ```

    Select `PreToolUse`.
  </Step>
  <Step title="Add an Execute matcher">
    Add a new matcher and enter:

    ```text
    Execute
    ```
  </Step>
  <Step title="Add the hook command">
    Add a command hook:

    ```bash
    jq -r '.tool_input.command' >> ~/.factory/bash-command-log.txt
    ```
  </Step>
  <Step title="Save and verify">
    Save to user settings, ask Droid to run a simple command, then inspect the log:

    ```bash
    cat ~/.factory/bash-command-log.txt
    ```
  </Step>
</Steps>

The saved configuration looks like this:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Execute",
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '.tool_input.command' >> ~/.factory/bash-command-log.txt"
          }
        ]
      }
    ]
  }
}
```

<LabeledDivider label='Event reference' />

## Hook events

| Event | Runs when | Matcher or key fields | Common use |
| :---- | :-------- | :-------------------- | :--------- |
| `PreToolUse` | After Droid builds tool parameters and before the tool runs. | `tool_name`, `tool_input`; matcher usually targets a tool such as `Execute` or `Edit`. | Block risky operations, approve safe tools, rewrite tool input. |
| `PostToolUse` | Immediately after a tool completes. | `tool_name`, `tool_input`, `tool_response`; same tool matchers as `PreToolUse`. | Format files, run validation, add feedback after an edit. |
| `UserPromptSubmit` | Before Droid processes a submitted user prompt. | `prompt`, `has_images`. | Validate prompts or inject extra context. |
| `Notification` | When Droid sends a notification. | `message`, `notification_type` (`permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_dialog`). | Desktop alerts or compliance logging. |
| `Stop` | When the main Droid is about to finish responding. | `stop_hook_active`, `tool_execution_count`, `elapsed_time`. | Require final checks or continue with follow-up instructions. |
| `SubagentStop` | When a Task-launched sub-droid finishes. | `task_name`, `task_result`, `task_error`, `stop_hook_active`. | Validate subagent output or request more work. |
| `PreCompact` | Before manual or automatic compaction. | `trigger` (`manual` or `auto`), `custom_instructions`, `message_count`, `estimated_tokens`. | Save context or add compaction guidance. |
| `SessionStart` | When Droid starts, resumes, clears, or starts after compaction. | `source` (`startup`, `resume`, `clear`, `compact`), plus optional prior session IDs. | Load local context at session start. |
| `SessionEnd` | When a Droid session ends. | `reason` (`clear`, `logout`, `prompt_input_exit`, `other`), `session_duration_ms`, `message_count`. | Cleanup, audit logs, session summaries. |

## Hook input

Every hook receives JSON on stdin. Common fields are also exposed as environment variables when their values are strings, booleans, or numbers.

```typescript
{
  session_id: string
  transcript_path: string
  cwd: string
  permission_mode: "off" | "spec" | "auto-low" | "auto-medium" | "auto-high"
  hook_event_name: string
  message_id?: string
}
```

Tool hooks add tool-specific fields:

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.factory/projects/.../session.jsonl",
  "cwd": "/Users/me/project",
  "permission_mode": "off",
  "hook_event_name": "PreToolUse",
  "tool_name": "Create",
  "tool_input": {
    "file_path": "/Users/me/project/file.txt",
    "content": "file content"
  }
}
```

`PostToolUse` includes `tool_response` as well. The exact shape of `tool_input` and `tool_response` depends on the tool.

## Hook output

Hooks communicate through exit codes, stderr, stdout, and optional JSON emitted on stdout.

| Output | Effect |
| :----- | :----- |
| Exit code `0` | Success. For `UserPromptSubmit` and `SessionStart`, stdout can add context. For other events, stdout is visible in transcript views. |
| Exit code `2` | Blocking or corrective feedback. `PreToolUse` blocks the tool call, `PostToolUse` and `Stop` feed stderr back to Droid, and `UserPromptSubmit` blocks prompt processing. Other lifecycle events surface stderr to the user. |
| Any other non-zero exit | Non-blocking error. Droid records stderr and continues where the event permits. |
| JSON `continue: false` | Stops processing after the hook. `stopReason` can explain why to the user. |
| JSON `suppressOutput: true` | Hides successful hook output from the main chat view while preserving it in the detailed transcript. |

### PreToolUse control

Use `hookSpecificOutput.permissionDecision` for tool-call control:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Documentation reads are safe",
    "updatedInput": {
      "file_path": "/Users/me/project/README.md"
    }
  }
}
```

| Decision | Effect |
| :------- | :----- |
| `allow` | Allows the tool call and can bypass the normal permission prompt. |
| `deny` | Blocks the tool call and sends the reason to Droid. |
| `ask` | Forces a user confirmation prompt. |

`updatedInput` can modify tool parameters before execution. Use it carefully and only for fields you understand.

### PostToolUse, prompt, and stop control

| Event | JSON fields |
| :---- | :---------- |
| `PostToolUse` | `decision: "block"` sends `reason` back to Droid after the tool ran. `hookSpecificOutput.additionalContext` adds more context. |
| `UserPromptSubmit` | `decision: "block"` prevents the prompt from being processed and shows `reason` to the user. `additionalContext` is appended when not blocked. |
| `Stop` and `SubagentStop` | `decision: "block"` prevents stopping. Include `reason` so Droid knows what to do next. |
| `SessionStart` | `hookSpecificOutput.additionalContext` is appended to the new session context. |
| `SessionEnd` | Cannot block session termination. Use it for cleanup and logging. |

<LabeledDivider label='Plugins and policy' />

## Plugin hooks

Installed plugins can provide hooks. Droid loads hooks from `hooks/hooks.json` in the plugin root and merges them with user, project, and managed hooks when the plugin is enabled.

```text
my-plugin/
├── .factory-plugin/
│   └── plugin.json
├── hooks/
│   ├── hooks.json
│   └── format.sh
└── ...
```

```json
{
  "PostToolUse": [
    {
      "matcher": "Create|Edit|ApplyPatch",
      "hooks": [
        {
          "type": "command",
          "command": "${DROID_PLUGIN_ROOT}/hooks/format.sh",
          "timeout": 30
        }
      ]
    }
  ]
}
```

Plugin hook commands may use `${DROID_PLUGIN_ROOT}`, `$DROID_PLUGIN_ROOT`, `${CLAUDE_PLUGIN_ROOT}`, or `$CLAUDE_PLUGIN_ROOT`. Droid expands those variables to the installed plugin cache path when loading plugin hooks. Outside plugins, use `$FACTORY_PROJECT_DIR` or an absolute path.

## Org-managed hooks

Organizations can define authoritative hooks in Enterprise Controls through managed settings. Org hooks always load unless hooks are globally disabled, and lower levels cannot remove them.

| Field | Description |
| :---- | :---------- |
| `hooks` | Org-defined hook settings keyed by event name, using the same structure as `hooks.json`. |
| `allowManagedHooksOnly` | When `true`, only org-managed hooks and hooks from org-enabled plugins load. User and project hooks are ignored. |

```json
{
  "allowManagedHooksOnly": true,
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Execute",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/local/bin/audit-command.sh",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

See [Enterprise Controls & Managed Settings](/enterprise/hierarchical-settings-and-org-control) for how org, project, folder, and user settings merge.

<LabeledDivider label='In practice' />

## Examples

### Format changed TypeScript files

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Create|Edit|ApplyPatch",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$FACTORY_PROJECT_DIR\"/.factory/hooks/format_changed_file.py"
          }
        ]
      }
    ]
  }
}
```

### Block edits to sensitive files

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Create|Edit|ApplyPatch",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$FACTORY_PROJECT_DIR\"/.factory/hooks/protect_paths.py"
          }
        ]
      }
    ]
  }
}
```

A blocking script exits `2` and writes the reason to stderr.

### Add context before each prompt

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$FACTORY_PROJECT_DIR\"/.factory/hooks/add_ticket_context.py"
          }
        ]
      }
    ]
  }
}
```

## Security considerations

- Treat hook input as untrusted JSON. Validate and sanitize paths, prompts, and command strings.
- Quote shell variables, for example `"$FACTORY_PROJECT_DIR"`, to avoid word splitting.
- Block path traversal and sensitive paths such as `.env`, `.git/`, credentials, and deployment secrets.
- Prefer small scripts checked into `.factory/hooks/` over long inline one-liners.
- Test hooks manually before enabling them for a team or organization.
- Remember that hooks inherit your local environment. Avoid commands that exfiltrate data or mutate systems unexpectedly.

Droid snapshots hooks at startup and warns when hooks are modified externally. Review changes in the `/hooks` UI before relying on them in the current session.

## Debugging

| Symptom | What to check |
| :------ | :------------ |
| Hook does not run | Confirm the event key, matcher casing, and that hooks are not disabled. Use `/hooks` to inspect the active configuration. |
| Hook runs for the wrong tool | Matchers are case-sensitive and can be regexes. Use exact names like `Execute`, or a narrow regex. |
| Script cannot be found | Use an absolute path or `"$FACTORY_PROJECT_DIR"/relative/path`. Do not rely on the shell's current directory. |
| JSON parsing fails | Remember that hook input arrives on stdin. Test with sample JSON before registering the command. |
| Hook hangs | Set a shorter `timeout`, inspect external network or process calls, and test the script outside Droid. |

Run `droid --debug` to inspect hook matching and execution details.

<RelatedLinks>
  <RelatedLink href='/harness/subagents' title='Custom droids (subagents)'>
    Fire hooks on Task-launched subagent lifecycle events.
  </RelatedLink>
  <RelatedLink href='/autonomy-and-safety/auto-run' title='Autonomy Level'>
    Combine hooks with autonomy levels for layered safety controls.
  </RelatedLink>
</RelatedLinks>
