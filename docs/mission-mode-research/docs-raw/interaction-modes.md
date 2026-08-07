# Interaction Modes

Choose Normal, Spec, or Mission Mode, then set Autonomy Level for how much Droid can do without approval.

Interaction Modes set the shape of a session. **Normal Mode** works directly, **Spec Mode** plans before implementation, and Mission Mode coordinates larger work with an orchestrator.

Autonomy Level is separate. It controls which actions Droid can run without pausing for approval. Some CLI and IDE surfaces combine the labels as `Auto (Off)`, `Auto (Low)`, `Auto (Medium)`, or `Auto (High)`, which means Normal Mode plus the selected Autonomy Level.

## Choose a mode

| Mode | Use it when | What Droid can do | How to enter |
| ---- | ----------- | ----------------- | ------------ |
| **Normal Mode** | You want Droid to answer, edit, run commands, or implement now. | Uses the enabled tools for the session. Approval prompts are governed by Autonomy Level, command policy, sandbox rules, and org controls. | Default mode. Select **Normal Mode** from the mode menu, or press <Kbd keys='Shift+Tab' /> from Spec Mode in the CLI. |
| **Spec Mode** | You want Droid to investigate and propose a plan before any code changes. | Uses read-only planning behavior, then calls `ExitSpecMode` to ask for approval. | Select **Spec Mode**, press <Kbd keys='Shift+Tab' /> from Normal Mode in the CLI, or start with `--use-spec`. |
| **Mission Mode** | You want Droid to coordinate a larger effort with worker agents and validation. | Runs a mission orchestrator session with Mission Control. Mission workers use their own configured model and autonomy settings. | Start from the [Missions](/missions/overview) workflow, or use `droid exec --mission --auto high`. |

<Note>
  In the CLI, <Kbd keys='Shift+Tab' /> toggles between Normal Mode and Spec Mode. Mission Mode is not part of the <Kbd keys='Shift+Tab' /> cycle.
</Note>

## Set Autonomy Level separately

Autonomy Level applies in Normal Mode and after you approve a Spec Mode plan.

| Autonomy Level | What can run without approval |
| -------------- | ----------------------------- |
| **Off** | Built-in read tools and allowlisted commands. Other actions ask first. |
| **Low** | File edits plus low-risk commands and MCP tools. |
| **Medium** | Everything in Low plus reversible workspace changes such as installs, builds, and local commits. |
| **High** | High-risk actions, unless a blocklist, denylist, sandbox rule, or org control requires a stop or prompt. |

Press <Kbd keys='Ctrl+L' /> in the CLI to cycle `Off → Low → Medium → High → Off`. Organization policy can cap the highest available level. See [Autonomy Level](/autonomy-and-safety/auto-run) for the full approval model.

## Use Spec Mode

Spec Mode is for research and planning before implementation. Use it for architecture changes, migrations, security-sensitive work, or any task where you want to review the plan before Droid edits files.

<Steps>
  <Step title="Enter Spec Mode">
    Select **Spec Mode** from the mode menu, press <Kbd keys='Shift+Tab' /> in the CLI, or start a session with `--use-spec`.
  </Step>
  <Step title="Describe the outcome">
    Explain what should change, the constraints that matter, and how Droid should verify the work.
  </Step>
  <Step title="Review the plan">
    Droid researches the repo, reads relevant files, and proposes a concrete implementation plan.
  </Step>
  <Step title="Approve or keep iterating">
    Approve the plan to return to Normal Mode for implementation, choose a higher Autonomy Level for implementation, or keep iterating in Spec Mode.
  </Step>
</Steps>

During Spec Mode, Droid should not edit files, change configuration, make commits, start services, or write to external systems. It can read files, search the repo, inspect linked artifacts, and ask clarifying questions.

### Make the request specific

Include the outcome, constraints, verification steps, and relevant existing patterns:

```text
Users need to reset passwords using email verification.
The reset link should expire after 24 hours.
Include rate limiting and tests for invalid or expired links.
Follow the background job pattern used by report generation.
```

### After the plan

After Droid proposes a plan, choose one of the approval options: proceed with manual approvals, proceed with Low/Medium/High Autonomy Level, or keep iterating on the spec. Organization Maximum Autonomy Level can hide higher approval options.

## Use Mission Mode for orchestrated work

Mission Mode is for multi-step work that benefits from orchestration, worker agents, validation, and progress tracking. Use Mission Mode when a task is too large for a single linear session, or when you want explicit validation milestones.

Mission Mode is not a planning toggle. Starting a Mission upgrades the session into an orchestrator workflow, and Mission workers run with the model, reasoning, and autonomy settings configured for Missions. See [Factory Missions](/missions/overview).

## Change controls and defaults

- Press <Kbd keys='Shift+Tab' /> to switch between Normal Mode and Spec Mode.
- Press <Kbd keys='Ctrl+L' /> to cycle Autonomy Level.
- Use `/settings` to change session defaults.
- Use `/model` and the Spec Mode model setting when planning should use a different model.
- In the Factory App, use the mode selector for **Normal Mode**, **Spec Mode**, or **Mission Mode**, and the Autonomy selector for `Auto Off`, `Auto Low`, `Auto Medium`, or `Auto High`.

```bash
droid --use-spec
droid --auto medium
droid exec --use-spec "Plan the migration, then ask for approval"
droid exec --auto high "Run the approved release checklist"
droid exec --mission --auto high "Coordinate the migration"
```

Set defaults in [settings.json](/droid-cli/settings):

```json
{
  "sessionDefaultSettings": {
    "interactionMode": "spec",
    "autonomyLevel": "low",
    "specModeModel": "<model-id>",
    "specModeReasoningEffort": "high"
  }
}
```

Use:

- `sessionDefaultSettings.interactionMode`: `auto` for Normal Mode or `spec` for Spec Mode.
- `sessionDefaultSettings.autonomyLevel`: `off`, `low`, `medium`, or `high`.
- `sessionDefaultSettings.specModeModel`: optional planning model for Spec Mode.
- `sessionDefaultSettings.specModeReasoningEffort`: optional reasoning effort for the Spec Mode model.
- `sessionDefaultSettings.autonomyMode`: deprecated legacy field. Prefer `interactionMode` plus `autonomyLevel`.

Enterprise administrators can set `maxAutonomyLevel` to cap available autonomy. See [Enterprise Controls & Managed Settings](/enterprise/hierarchical-settings-and-org-control).

## Save Spec Mode plans

Spec Mode can save approved plans as Markdown. Open the CLI settings and enable **Save spec as Markdown**.

- By default, plans are saved to `.factory/docs` inside the nearest project-level `.factory` directory. If none exists, the CLI falls back to `~/.factory/docs`.
- Use **Spec save directory** to choose a project directory, your home directory, or a custom path.
- Custom values support absolute paths, `~` expansion, `.factory/...` shortcuts, and relative paths from the current workspace.
- Files are named `YYYY-MM-DD-slug.md`, with a counter appended when needed.

<RelatedLinks>
  <RelatedLink href='/droid-cli/settings' title='Settings'>
    Full settings reference.
  </RelatedLink>
  <RelatedLink href='/droid-exec/overview' title='Droid Exec'>
    Run non-interactive sessions with `--auto`, `--use-spec`, and `--spec-model`.
  </RelatedLink>
</RelatedLinks>
