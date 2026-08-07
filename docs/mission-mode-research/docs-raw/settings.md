# Settings

Configure how droid behaves and integrates with your workflow.

This is the reference for `settings.json`, the personal CLI configuration file. It covers the settings you control as an individual developer. Settings that are typically managed by an organization (model policy, network restrictions, autonomy ceilings, and similar hard controls) are listed in a [clearly labeled section](#enterprise-and-org-level-settings) below and documented in full in [Enterprise Controls & Managed Settings](/enterprise/hierarchical-settings-and-org-control). For personal session defaults managed in the Factory App, see [App settings](/factory-app/settings).

## Accessing settings

To configure droid settings:

1. Run `droid`
2. Enter `/settings`
3. Adjust your preferences interactively

Changes take effect immediately and are saved to your settings file.

## Where settings live

| OS            | Location                               |
| ------------- | -------------------------------------- |
| macOS / Linux | `~/.factory/settings.json`             |
| Windows       | `%USERPROFILE%\.factory\settings.json` |

If the file doesn't exist, it's created with defaults the first time you run **droid**.

### Local overrides

You can create a `settings.local.json` alongside `settings.json` in any `.factory/` folder:

- `~/.factory/settings.local.json` (user-level)
- `<project>/.factory/settings.local.json` (project-level)

Local overrides merge on top of the corresponding `settings.json` at the same level and follow the same hierarchy precedence. Add `settings.local.json` to `.gitignore` if you want to keep machine-specific preferences out of version control.

## Legacy Droid YAML configuration

`.droid.yaml` was an older project configuration surface. Use the current `.factory/` files instead:

- Use `settings.json` and `settings.local.json` for Droid preferences and local overrides.
- Use [AGENTS.md](/harness/agents-md) for repository instructions, conventions, and validation commands.
- Use [MCP servers](/harness/mcp), [hooks](/harness/hooks), and [skills](/harness/skills) for integrations, automation, and reusable workflows.

## Available settings

| Setting                    | Options                                                                                                                                                                                                                                                                  | Default                       | Description                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------- | -------------------------------------------------------------------------- |
| `model`                    | Any [available model ID](/models)                                                                                                                                                                                                                                        | Product default               | The default AI model used by droid                                         |
| `reasoningEffort`          | Model-dependent: `none`, `dynamic`, `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` (see [per-model options](/models))                                                                                                                                                                                        | Model-dependent default       | Controls how much structured thinking the model performs.                  |
| `sessionDefaultSettings.interactionMode` | `auto`, `spec`                                                                                                                                                                                                                                                           | `auto`                        | Sets whether new sessions start in Auto or Spec Mode.                      |
| `sessionDefaultSettings.autonomyLevel`   | `off`, `low`, `medium`, `high`                                                                                                                                                                                                                                           | `off`                         | Sets the default [Autonomy Level](/autonomy-and-safety/auto-run) for new sessions. |
| `cloudSessionSync`         | `true`, `false`                                                                                                                                                                                                                                                          | `true`                        | Mirror CLI sessions to Factory web.                                        |
| `diffMode`                 | `github`, `unified`                                                                                                                                                                                                                                                      | `github`                      | Choose between split GitHub-style diffs and a single-column view.          |
| `completionSound`          | `off`, `bell`, `fx-ok01`, `fx-ack01`, or custom file path                                                                                                                                                                                                                | `fx-ok01`                     | Audio cue when a response finishes.                                        |
| `awaitingInputSound`       | `off`, `bell`, `fx-ok01`, `fx-ack01`, or custom file path                                                                                                                                                                                                                | `fx-ack01`                    | Audio cue when droid is waiting for user input.                            |
| `soundFocusMode`           | `always`, `focused`, `unfocused`                                                                                                                                                                                                                                         | `always`                      | When to play sound notifications.                                          |
| `commandAllowlist`         | Array of commands                                                                                                                                                                                                                                                        | Safe defaults provided        | Commands that run without extra confirmation.                              |
| `commandDenylist`          | Array of commands                                                                                                                                                                                                                                                        | Restrictive defaults provided | Commands that always require confirmation.                                 |
| `commandBlocklist`         | Array of commands                                                                                                                                                                                                                                                        | `[]` (none)                   | Commands that can never run, even when approvals are skipped.              |
| `includeCoAuthoredByDroid` | `true`, `false`                                                                                                                                                                                                                                                          | `true`                        | Automatically append the Droid co-author trailer to commits.               |
| `enableDroidShield`        | `true`, `false`                                                                                                                                                                                                                                                          | `true`                        | Enable secret scanning and git guardrails.                                 |
| `hooksDisabled`            | `true`, `false`                                                                                                                                                                                                                                                          | `false`                       | Globally disable all hooks execution.                                      |
| `disabledSkills`           | Array of skill names                                                                                                                                                                                                                                                     | `[]`                          | Disable discovered skills without deleting their files.                    |
| `ideAutoConnect`           | `true`, `false`                                                                                                                                                                                                                                                          | `false`                       | Auto-connect to IDE from external terminals.                               |
| `showThinkingInMainView`   | `true`, `false`                                                                                                                                                                                                                                                          | `false`                       | Display AI thinking/reasoning blocks in the main chat view.                |
| `customModels`             | Array of model configs                                                                                                                                                                                                                                                   | `[]`                          | Custom model configurations for BYOK. See [BYOK docs](/model-independence/byok). |
| `blockOnMcpLoad`           | `true`, `false`                                                                                                                                                                                                                                                          | `false`                       | Wait for MCP servers to finish loading before starting an agent turn. |

### Model

Set `model` to a [model ID from Factory-Managed Inference](/models). For custom models, see [Custom Models (BYOK)](/model-independence/byok).

### Reasoning effort

`reasoningEffort` adjusts how much structured thinking the model performs before replying. The available levels and the default are **set by each model**, so the [Available Models](/models) table is the source of truth for what a given model accepts. Across the catalog they range from least to most deliberation:

{/* sweep-allow: term-bullets */}

- **`off` / `none`**: no structured reasoning (fastest).
- **`dynamic`**: use the model's dynamic reasoning behavior.
- **`minimal`**, **`low`**, **`medium`**, **`high`**: progressively more deliberation.
- **`xhigh`**, **`max`**: the deepest reasoning, where a model offers it.

Each model accepts only the subset shown in its [Available Models](/models) row, and its default sits within that subset (for example, Claude Opus 4.8 defaults to `high`, while Claude Sonnet 4.5 defaults to `off`).

### Autonomy level

Use `sessionDefaultSettings.interactionMode` to choose whether new sessions start in Auto or Spec Mode, and `sessionDefaultSettings.autonomyLevel` to set the default [Autonomy Level](/autonomy-and-safety/auto-run). `off` keeps manual approvals; `low`, `medium`, and `high` pre-authorize work at or below that risk level.

`sessionDefaultSettings.autonomyMode` is deprecated and retained for older configurations.

### Diff mode

Control how droid displays code changes:

- **`github`**: Side-by-side, higher fidelity render (recommended).
- **`unified`**: Traditional single-column diff format.

### Cloud session sync

When this switch is on, every CLI session is mirrored to Factory web so you can revisit conversations in the browser:

- **`true`**: Sync sessions to the web app.
- **`false`**: Keep sessions local only.

### Sound notifications

Configure audio feedback for droid events:

**Completion sound** (`completionSound`) - plays when a response finishes:

<PropertyList>
  <Property name='fx-ok01'>
    Built-in completion sound (default) - soft success bloop.
  </Property>
  <Property name='fx-ack01'>
    Alternative built-in sound effect - tactile ripple feedback.
  </Property>
  <Property name='bell'>
    Use the system terminal bell.
  </Property>
  <Property name='off'>
    No sound notifications.
  </Property>
  <Property name='Custom path'>
    Provide a file path to your own sound file (e.g., `"/path/to/sound.wav"`).
  </Property>
</PropertyList>

**Awaiting input sound** (`awaitingInputSound`) - plays when droid is waiting for user input. Same options as completion sound, defaults to `fx-ack01`.

**Sound focus mode** (`soundFocusMode`) - controls when sounds play:

<PropertyList>
  <Property name='always'>
    Play sounds regardless of window focus (default).
  </Property>
  <Property name='focused'>
    Only play sounds when the terminal is focused.
  </Property>
  <Property name='unfocused'>
    Only play sounds when the terminal is not focused.
  </Property>
</PropertyList>

<Note>Access sound settings via `/settings` or <Kbd keys='Shift+Tab' /> → **Settings** in the TUI.</Note>

### Hooks

The `hooksDisabled` setting provides a global toggle to disable all hooks execution without removing your hook configurations:

- **`false`**: Hooks are enabled and will execute normally (default)
- **`true`**: All hooks are disabled globally

You can also toggle this from the `/hooks` menu or `/settings`.

Set `showHookOutput` to `true` when you want hook stdout and stderr to appear in the session transcript for debugging.

### Disabled skills

`disabledSkills` is a ledger of skill names that Droid should not invoke. Configure it
from the `/skills` manager or edit the user or project settings file directly:

```json
{
  "disabledSkills": ["deploy-production", "summarize-diff"]
}
```

User and project arrays are combined, so a skill disabled at either level remains
disabled. Stale entries are safe: a name has no effect until Droid discovers a matching
skill. See [Skills](/harness/skills#manage-skills) for the manager, source precedence,
and `SKILL.md` controls.

### IDE auto-connect

The `ideAutoConnect` setting controls whether droid automatically connects to your IDE when running from external terminals (outside the IDE's built-in terminal):

- **`false`**: Only auto-connect when running inside IDE terminal (default)
- **`true`**: Auto-connect to IDE from any terminal

## Command allowlist, denylist & blocklist

Use these settings to control which commands droid can execute automatically and which it must never run:

<PropertyList>
  <Property name='commandAllowlist'>
    Commands in this array are treated as safe and run without additional
    confirmation, regardless of autonomy prompts. Include only low-risk
    utilities you rely on frequently (for example `ls`, `pwd`, `dir`).
  </Property>
  <Property name='commandDenylist'>
    Commands in this array always require confirmation and are typically
    blocked because they are destructive or unsafe (for example recursive
    `rm`, `mkfs`, or privileged system operations). A denied command can still
    be run if you explicitly approve it.
  </Property>
  <Property name='commandBlocklist'>
    Commands in this array can **never** run. Unlike the denylist, there is no
    prompt and no way to approve them: the block applies even under full
    autonomy, auto-run, or `--skip-permissions-unsafe`. droid also resolves
    the actual program being invoked, so a blocked command cannot be slipped
    through with a wrapper shell, an absolute path, quoting tricks, or command
    substitution.
  </Property>
</PropertyList>

Commands that appear in both the allowlist and denylist default to the denylist behavior. The blocklist always takes precedence over both. Any command that is in none of the lists falls back to the autonomy level you selected for the session.

### Example allow/deny/block configuration

```json
{
  "commandAllowlist": ["ls", "pwd", "dir"],
  "commandDenylist": ["rm -rf /", "mkfs", "shutdown"],
  "commandBlocklist": ["shutdown", "mkfs", "curl"]
}
```

Use `commandBlocklist` for commands that should be hard-stopped regardless of approvals; use `commandDenylist` for commands that are allowed only after explicit confirmation. Review and update these arrays periodically to match your workflow and security posture, especially when sharing configurations across teams.

## Session defaults

Defaults applied when a new session starts. See also `sessionDefaultSettings.interactionMode` and `sessionDefaultSettings.autonomyLevel` in the table above.

| Setting                                          | Type   | Options                                  | Default        | Description                                                |
| ------------------------------------------------ | ------ | ---------------------------------------- | -------------- | ---------------------------------------------------------- |
| `sessionDefaultSettings.specModeModel`           | string | Any [available model ID](/models)        | Inherits model | Override the model used when sessions start in Spec Mode.  |
| `sessionDefaultSettings.specModeReasoningEffort` | string | Model-dependent (see [/models](/models))   | Model default  | Reasoning effort applied to the spec model.                |

## Display and UI

Tune how droid renders content in the terminal.

<PropertyList>
  <Property name='toolResultDisplay' type='string' defaultValue='expanded'>
    How tool results are rendered in the transcript. Options: `expanded`,
    `compact`.
  </Property>
  <Property name='showTokenUsageIndicator' type='boolean' defaultValue='false'>
    Show the live token usage indicator at the bottom of the input.
  </Property>
  <Property name='todoDisplayMode' type='string' defaultValue='Product default'>
    Control how the todo list is shown in the terminal UI.
  </Property>
  <Property name='logoAnimation' type='string' defaultValue='once'>
    Animate the droid logo on startup. Options: `once`, `always`, `off`.
  </Property>
  <Property name='theme' type='string' defaultValue='System theme'>
    Color theme used by the TUI. Accepts a theme ID (see `/themes`).
  </Property>
  <Property name='overrideTerminalColors' type='boolean' defaultValue='false'>
    Force droid's theme to override the terminal's color scheme.
  </Property>
  <Property name='nerdFont' type='boolean' defaultValue='false'>
    Enable Nerd Font glyphs in the UI (requires a Nerd Font in your terminal).
  </Property>
</PropertyList>

## Additional sound and notification settings

Extends the [Sound notifications](#sound-notifications) section with toggles for the bell, per-event focus modes, and subagent activity.

| Setting                          | Type    | Options                                | Default   | Description                                                          |
| -------------------------------- | ------- | -------------------------------------- | --------- | -------------------------------------------------------------------- |
| `subagentSounds`                 | string  | `on`, `off`                            | `off`     | Play sounds for subagent lifecycle events (start, complete, error).  |
| `completionSoundFocusMode`       | string  | `always`, `focused`, `unfocused`       | Inherits `soundFocusMode` | Override focus behavior for completion sounds. |
| `awaitingInputSoundFocusMode`    | string  | `always`, `focused`, `unfocused`       | Inherits `soundFocusMode` | Override focus behavior for awaiting-input sounds. |

## Mission settings

Configure [Missions](/missions/overview), multi-agent orchestration runs.

<PropertyList>
  <Property name='missionModelSettings.workerModel' type='string' defaultValue='Inherits'>
    Default model used by mission worker subagents. Accepts any
    [available model ID](/models).
  </Property>
  <Property name='missionModelSettings.workerReasoningEffort' type='string' defaultValue='Model default'>
    Reasoning effort for mission workers. Options are model-dependent (see
    [/models](/models)).
  </Property>
  <Property name='missionModelSettings.validationWorkerModel' type='string' defaultValue='Inherits'>
    Model used by mission validators (scrutiny / user-testing workers).
    Accepts any [available model ID](/models).
  </Property>
  <Property name='missionModelSettings.validationWorkerReasoningEffort' type='string' defaultValue='Model default'>
    Reasoning effort for validation workers. Options are model-dependent (see
    [/models](/models)).
  </Property>
  <Property name='missionModelSettings.skipScrutiny' type='boolean' defaultValue='false'>
    Skip scrutiny validation milestones during missions.
  </Property>
  <Property name='missionModelSettings.skipUserTesting' type='boolean' defaultValue='false'>
    Skip user-testing validation milestones during missions.
  </Property>
  <Property name='missionOrchestratorModel' type='string' defaultValue='Inherits'>
    Model used by the mission orchestrator. Accepts any
    [available model ID](/models).
  </Property>
  <Property name='missionOrchestratorReasoningEffort' type='string' defaultValue='Model default'>
    Reasoning effort for the mission orchestrator. Options are model-dependent
    (see [/models](/models)).
  </Property>
  <Property name='keepSystemAwakeDuringMissions' type='boolean' defaultValue='true'>
    Prevent the OS from sleeping while a mission is running.
  </Property>
</PropertyList>

## Subagent settings

Configure the autonomy and models used by subagents spawned by the Task tool. These appear in the **Subagents** tab of `/settings`.

| Setting                 | Type   | Options                                   | Default   | Description                                                                          |
| ----------------------- | ------ | ----------------------------------------- | --------- | ------------------------------------------------------------------------------------ |
| `subagentAutonomyLevel` | string | `inherit`, `off`, `low`, `medium`, `high` | `inherit` | [Autonomy Level](/autonomy-and-safety/auto-run) applied to subagents spawned by the Task tool. |

### Subagent autonomy level

`subagentAutonomyLevel` controls how much subagents can do without approval:

{/* sweep-allow: term-bullets */}

- **`inherit`**: Subagents use the parent session's autonomy level (default).
- **`off`**: Subagents require manual approval for every action.
- **`low`**, **`medium`**, **`high`**: Pre-authorize subagent work at or below that risk level.

An explicit level is still clamped to the org-managed `maxAutonomyLevel`, so it can never exceed the enterprise cap. Mission workers do not use this setting.

### Subagent model settings

Subagents are routed by a complexity tier (`light`, `medium`, `heavy`). Each tier can pin its own model and reasoning effort under `subagentModelSettings`.

| Setting                                       | Type   | Options                                                                                  | Default              | Description                                                          |
| --------------------------------------------- | ------ | ---------------------------------------------------------------------------------------- | -------------------- | -------------------------------------------------------------------- |
| `subagentModelSettings.lightModel`            | string | Any [available model ID](/models) or `inherit`                                           | `inherit`            | Model for light-complexity subagents (e.g. the built-in `explorer`). |
| `subagentModelSettings.lightReasoningEffort`  | string | Model-dependent: `none`, `dynamic`, `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` | Parent/model default | Reasoning effort for light-complexity subagents.                     |
| `subagentModelSettings.mediumModel`           | string | Any [available model ID](/models) or `inherit`                                           | `inherit`            | Model for medium-complexity subagents (e.g. the built-in `worker`).  |
| `subagentModelSettings.mediumReasoningEffort` | string | Model-dependent: `none`, `dynamic`, `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` | Parent/model default | Reasoning effort for medium-complexity subagents.                    |
| `subagentModelSettings.heavyModel`            | string | Any [available model ID](/models) or `inherit`                                           | `inherit`            | Model for heavy-complexity subagents.                                |
| `subagentModelSettings.heavyReasoningEffort`  | string | Model-dependent: `none`, `dynamic`, `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` | Parent/model default | Reasoning effort for heavy-complexity subagents.                     |

How the tiers are chosen:

- The built-in `worker` subagent runs at `medium` complexity and `explorer` at `light`. Custom droids and the Task tool can request a specific tier.
- **`inherit`** (the default) means the subagent uses the spawning session's active model and reasoning effort. Upgrading the parent session's model does not retroactively change a tier pinned to a specific model.
- A custom droid with an explicit `model` in its configuration uses that model directly and bypasses complexity routing.
- Without an explicit reasoning effort, a routed tier preserves the parent's active effort when it uses the same model; if it switches models, it uses the routed model's default. Explicit efforts are clamped to what the selected model supports.

## Context and compaction

Controls when and how droid compacts the conversation to stay within the model's context window.

<PropertyList>
  <Property name='compactionTokenLimit' type='number' defaultValue='Model-dependent'>
    Token threshold that triggers automatic compaction of the current session.
  </Property>
  <Property name='compactionTokenLimitPerModel' type='object' defaultValue='{}'>
    Per-model overrides for `compactionTokenLimit`, as a
    `{ "<modelId>": number }` map.
  </Property>
  <Property name='compactionModel' type='string' defaultValue='same'>
    Which model performs compaction: `same` uses the current session model, or
    specify a model ID.
  </Property>
  <Property name='modelFallbacks' type='object' defaultValue='{}'>
    Per-model fallback routing when a selected model is unavailable, as a
    `{ "<modelId>": "<fallbackModelId>" }` map.
  </Property>
</PropertyList>

## Spec mode settings

Controls the persistent spec store created by Spec Mode.

| Setting           | Type    | Options                  | Default                       | Description                                                                |
| ----------------- | ------- | ------------------------ | ----------------------------- | -------------------------------------------------------------------------- |
| `specSaveDir`     | string  | Directory path           | `~/.factory/specs`            | Directory where saved specs are written. Supports `~` expansion.           |

## Infrastructure

System-level settings for status line, worktrees, and request timeouts.

<PropertyList>
  <Property name='statusLine' type='object' defaultValue='unset'>
    Custom status line configuration. Accepts
    `{ "command": string, "padding"?: number, "maxRows"?: number }`. The
    `command` is executed and its stdout rendered above the input. Configure
    interactively with `/statusline`.
  </Property>
  <Property name='worktreeDirectory' type='string' defaultValue='~/.factory/worktrees'>
    Default parent directory for git worktrees created with `--worktree` /
    `-w`.
  </Property>
  <Property name='llmRequestTimeout' type='number' defaultValue='Product default'>
    Timeout in milliseconds for individual LLM requests before they are
    aborted.
  </Property>
  <Property name='subagentInactivityTimeout' type='number' defaultValue='Product default'>
    Timeout in milliseconds for subagent inactivity before Droid treats the
    worker as stalled.
  </Property>
  <Property name='remoteAccessEnabled' type='boolean' defaultValue='false'>
    Allow this machine to be used for remote Droid Computer access.
  </Property>
</PropertyList>

## Enterprise and org-level settings

<Note>
**These keys are org-managed, not personal preferences.** They are typically configured by an organization Manager or Owner and pushed to members through the Factory App or a managed `settings.json`. They appear here so the `settings.json` schema is complete in one place, but individual users should not expect to change them. See [Enterprise Controls & Managed Settings](/enterprise/hierarchical-settings-and-org-control) for hierarchy, merge semantics, and admin enforcement details. Usage alert preferences are Factory App controls; individual users control their own threshold alerts.
</Note>

| Setting                              | Type    | Options                                                                                                                | Default      | Description                                                                                                                          |
| ------------------------------------ | ------- | ---------------------------------------------------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `maxAutonomyLevel`                   | string  | `off`, `low`, `medium`, `high`                                                                                         | `high`       | **Enterprise.** Maximum [Autonomy Level](/autonomy-and-safety/auto-run) any session may use. Higher levels selected by users are clamped. |
| `subagentAutonomyLevel`              | string  | `low`, `medium`, `high`, `inherit`                                                                                     | `inherit`    | **Enterprise.** Default autonomy ceiling for subagent workers.                                                                    |
| `modelPolicy`                        | object  | `{ "allowedModelIds"?: string[], "blockedModelIds"?: string[], "allowCustomModels"?: boolean, "allowedBaseUrls"?: string[] }` | unset        | **Enterprise.** Restrict which models members can select, control whether custom models are permitted, and allowlist base URLs for custom model providers. |
| `mcpPolicy`                          | object  | `{ "enabled"?: boolean, "allowlist"?: string[] }`                                                                      | unset        | **Enterprise.** Control whether MCP servers can run and which servers are permitted. See [MCP](/harness/mcp).              |
| `mcpAutonomyOverrides`               | object  | Per-server and per-tool autonomy map                                                                                   | unset        | **Enterprise.** Set default autonomy levels for specific MCP servers or tools.                                                     |
| `mcpAutonomyUrlOverrides`            | array   | URL pattern autonomy rules                                                                                             | unset        | **Enterprise.** Set autonomy defaults for MCP tools that target matching URLs.                                                     |
| `missionPolicy`                      | object  | `{ "restrictedAccess"?: boolean, "allowedUserIds"?: string[] }`                                                        | unset        | **Enterprise.** Restrict who can launch [Missions](/missions/overview).                                                          |
| `networkPolicy`                      | object  | `{ "allowedIps": string[] }`                                                                                           | unset        | **Enterprise.** Restrict outbound network access from droid sessions to the specified IPs or CIDR ranges in `allowedIps`.            |
| `sandbox`                            | object  | `{ "enabled"?: boolean, "mode"?: string, "filesystem"?: object, "network"?: object }`                                  | unset        | Sandbox configuration controlling filesystem and network isolation for tool execution. See [Sandbox](/autonomy-and-safety/sandbox).                               |
| `restrictMemberVisibility`           | boolean | `true`, `false`                                                                                                        | `false`      | **Org-level.** Hide other org members from non-admin users.                                                                          |
| `restrictApiKeyCreationToManagers`   | boolean | `true`, `false`                                                                                                        | `false`      | **Org-level.** Only org managers may create API keys.                                                                                |
| `sessionRetentionDays`               | number  | `14`–`365`                                                                                                             | Org default  | **Org-level.** How long synced session history is retained before deletion.                                                          |
| `wikiCloudSync`                      | boolean | `true`, `false`                                                                                                        | `true`       | **Org-level.** Sync generated [Wiki](/software-factory/wiki/overview) content to Factory cloud.                                                                |
| `voiceDictationEnabled`              | boolean | `true`, `false`                                                                                                        | Org default  | **Org-level.** Control whether voice dictation is available as an input method to organization members.                              |
| `disableWeeklyUsageSummary`          | boolean | `true`, `false`                                                                                                        | `false` (summary on) | **Enterprise/org-level.** Opt out of the weekly usage-cap summary email sent to Managers and Owners for users and active service accounts at or above 80% of their monthly credit cap. Set `true` to suppress. |
| `managedComputersEnabled`            | boolean | `true`, `false`                                                                                                        | `false`      | **Enterprise.** Enable Factory-managed remote computers for the org.                                                                 |
| `managedComputersAllowedEmails`      | array   | Email allowlist                                                                                                        | unset        | **Enterprise.** Limit Factory-managed Droid Computers to specific members.                                                          |
| `byomComputersEnabled`               | boolean | `true`, `false`                                                                                                        | `false`      | **Enterprise.** Allow members to register their own machines via `droid computer register` (BYOM).                                   |
| `byomComputersAllowedEmails`         | array   | Email allowlist                                                                                                        | unset        | **Enterprise.** Limit BYOM Droid Computer registration to specific members.                                                         |
| `factoryRouterGuidance`              | string  | Routing guidance text                                                                                                  | unset        | **Enterprise.** Organization-wide guidance for Factory Router model selection.                                                      |
| `factoryRouterRules`                 | array   | Routing rule objects                                                                                                   | unset        | **Enterprise.** Conditional Factory Router guidance rules.                                                                          |
| `allowManagedHooksOnly`              | boolean | `true`, `false`                                                                                                        | `false`      | **Enterprise.** Require hooks to come from managed settings rather than local configuration.                                        |
| `disableAutoUpdate`                  | boolean | `true`, `false`                                                                                                        | `false`      | **Enterprise.** Disable automatic Droid CLI updates where managed deployment controls updates.                                      |

## Factory App usage alert preferences

The following preference is stored in each user's Factory App profile. It cannot be configured in `settings.json`.

| Preference                | Type    | Options         | Default             | Description                                                                                                                          |
| ------------------------- | ------- | --------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `disableUsageLimitAlerts` | boolean | `true`, `false` | `false` (alerts on) | Opt out of the emails sent when you reach 80% and 100% of your monthly credit cap. Set `true` to stop these alerts.                   |

## Example configuration

```json
{
  "model": "claude-opus-4-7",
  "reasoningEffort": "low",
  "diffMode": "github",
  "cloudSessionSync": true,
  "completionSound": "fx-ok01",
  "awaitingInputSound": "fx-ack01",
  "soundFocusMode": "always"
}
```

<RelatedLinks>
  <RelatedLink href='/droid-cli/overview' title='CLI overview'>
    See the main TUI workflow.
  </RelatedLink>
  <RelatedLink href='/droid-cli/cli-reference' title='CLI reference'>
    Command flags and options.
  </RelatedLink>
  <RelatedLink href='/ide-integrations' title='IDE integrations'>
    Editor-specific setup.
  </RelatedLink>
  <RelatedLink href='/model-independence/byok' title='Custom models & BYOK'>
    Add custom models and API keys.
  </RelatedLink>
</RelatedLinks>
