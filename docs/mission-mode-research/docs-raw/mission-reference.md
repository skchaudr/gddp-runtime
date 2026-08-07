# Missions Configuration & Reference

Configuration inheritance, headless execution with droid exec --mission, mission settings, and enterprise access policy.

## Configuration inheritance

Missions inherit your existing Droid configuration:

{/* sweep-allow: term-bullets */}

- **MCP integrations**: Workers can use your connected tools (Linear, Sentry, Notion, etc.)
- **Custom skills**: Your existing skills are available and new ones can be developed during planning.
- **Hooks**: Lifecycle hooks fire during mission execution.
- **Custom droids**: Subagents configured in your project are available to workers.
- **AGENTS.md**: Workers follow your project conventions and coding standards.

## Headless mission execution

Missions can also run non-interactively via `droid exec --mission`. This is useful for CI, scheduled jobs, and any environment where you want the orchestrator to plan and execute without a live TUI.

```bash
droid exec --mission -f mission.md
```

You can override the models and reasoning effort used by the orchestrator's worker and validator agents:

```bash
droid exec --mission \
  --worker-model claude-sonnet-4-6 \
  --worker-reasoning-effort medium \
  --validator-model claude-opus-4-7 \
  --validator-reasoning-effort high \
  -f mission.md
```

| Flag                                | Description                                                  |
| ----------------------------------- | ------------------------------------------------------------ |
| `--mission`                         | Run `droid exec` in Mission Mode (multi-agent orchestration). |
| `--worker-model <id>`               | Model used for mission worker agents.                        |
| `--worker-reasoning-effort <level>` | Reasoning effort for mission worker agents.                  |
| `--validator-model <id>`            | Model used for mission validator agents.                     |
| `--validator-reasoning-effort <level>` | Reasoning effort for mission validator agents.            |

See [`droid exec`](/droid-exec/overview) for the full headless reference.

## Configuration

Missions are tuned through the `missionModelSettings` object and a few top-level keys. Set these in your global or project [settings](/droid-cli/settings) file.

| Setting                                                | Description                                                                  |
| ------------------------------------------------------ | ---------------------------------------------------------------------------- |
| `missionModelSettings.workerModel`                     | Default model used by mission worker subagents.                              |
| `missionModelSettings.workerReasoningEffort`           | Reasoning effort for mission workers (`off`, `none`, `low`, `medium`, `high`). |
| `missionModelSettings.validationWorkerModel`           | Model used by validation workers (scrutiny and user-testing).                |
| `missionModelSettings.validationWorkerReasoningEffort` | Reasoning effort for validation workers.                                     |
| `missionModelSettings.skipScrutiny`                    | Skip scrutiny validation milestones during missions.                         |
| `missionModelSettings.skipUserTesting`                 | Skip user-testing validation milestones during missions.                     |
| `missionOrchestratorModel`                             | Model used by the mission orchestrator.                                      |
| `missionOrchestratorReasoningEffort`                   | Reasoning effort for the mission orchestrator.                               |
| `keepSystemAwakeDuringMissions`                        | Prevent the OS from sleeping while a mission is running. Defaults to `true`. |

<Tip>
  Pairing a strong orchestrator model with a faster worker model is a common cost-quality tradeoff: planning and validation benefit most from extra reasoning, while routine worker tasks can use a lighter model.
</Tip>

## Enterprise: restricting mission access

Organizations can restrict who is allowed to launch missions through the `missionPolicy` org-level setting:

```json
{
  "missionPolicy": {
    "restrictedAccess": true,
    "allowedUserIds": ["user_123", "user_456"]
  }
}
```

When `restrictedAccess` is `true`, only members listed in `allowedUserIds` can start new missions. See the [settings reference](/droid-cli/settings) for the full enterprise policy surface.

<RelatedLinks>
  <RelatedLink href='/droid-exec/overview' title='Droid Exec (Headless)'>
    Run missions non-interactively with `droid exec --mission`.
  </RelatedLink>
  <RelatedLink href='/enterprise/hierarchical-settings-and-org-control' title='Enterprise Controls & Managed Settings'>
    Govern mission access and model policy at the organization level.
  </RelatedLink>
</RelatedLinks>
