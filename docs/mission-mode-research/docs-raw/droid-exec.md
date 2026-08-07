# Droid Exec (Headless)

Non-interactive execution mode for CI/CD pipelines and automation scripts.

Droid Exec is Factory's headless execution mode designed for automation workflows. Unlike the interactive CLI, `droid exec` runs as a one-shot command that completes a task and exits, making it ideal for CI/CD pipelines, shell scripts, and batch processing.

<Tip>
  Explore the [Droid Exec cookbooks](/software-factory/code-review-ci).
</Tip>

## Summary and goals

Droid Exec is a one-shot task runner: it produces readable logs (and structured artifacts when requested), keeps mutations and command execution opt-in so runs are secure by default, fails fast on permission violations with clear errors, and composes simply for batch and parallel work.

<CardGroup cols={2}>
  <Card title="Non-Interactive" icon="terminal">
    Single run execution that writes to stdout/stderr for CI/CD integration
  </Card>
  <Card title="Secure by Default" icon="lock">
    Read-only by default with explicit opt-in for mutations via autonomy levels
  </Card>
  <Card title="Composable" icon="puzzle">
    Designed for shell scripting, parallel execution, and pipeline integration
  </Card>
  <Card title="Clean Output" icon="file-export">
    Structured output formats and artifacts for automated processing
  </Card>
</CardGroup>

## Execution model

Each run is a single non-interactive pass that writes to stdout/stderr. The default is spec-mode, where the agent is only allowed to execute read-only operations; add `--auto` to enable edits and commands, with risk tiers gating what can run.

CLI help (excerpt):

```text
Usage: droid exec [options] [prompt]

Execute a single command (non-interactive mode)

Arguments:
  prompt                          The prompt to execute

Options:
  -o, --output-format <format>          Output format (default: "text")
  --input-format <format>               Input format: stream-json for multi-turn sessions; stream-jsonrpc is controlled via JSON-RPC requests
  -f, --file <path>                     Read prompt from file
  --auto <level>                        Autonomy level: low|medium|high
  --skip-permissions-unsafe             Skip ALL permission checks - allows all permissions (unsafe)
  -s, --session-id <id>                 Existing session to continue (requires a prompt)
  --fork <id>                           Fork an existing session and continue from it
  -m, --model <id>                      Model ID to use
  -r, --reasoning-effort <level>        Reasoning effort (defaults per model)
  --spec-model <id>                     Model ID to use for spec mode
  --spec-reasoning-effort <level>       Reasoning effort for spec mode
  --use-spec                            Start in spec mode
  --restrict-tools <ids>                Restrict the run to only the specified tools (comma or space separated list)
  --additional-tools <ids>              Enable additional tools beyond the defaults (comma or space separated list)
  --disabled-tools <ids>                Disable specific tools (comma or space separated list)
  --disable-builtin-skills              Disable Factory-provided builtin skills for this session
  --list-tools                          List available tools for the selected model and exit
  --cwd <path>                          Working directory path
  -w, --worktree [name]                 Run in a git worktree
  --worktree-dir <path>                 Directory for worktree creation
  --tag <spec>                          Session tag (name or JSON, repeatable)
  --log-group-id <id>                   Log group ID for filtering logs
  --append-system-prompt <text>         Append custom text to end of system prompt
  --append-system-prompt-file <path>    Append file contents to end of system prompt
  --mission                             Run in mission mode (multi-agent orchestration)
  --worker-model <id>                   Model for mission workers
  --worker-reasoning-effort <level>     Reasoning effort for mission workers
  --validator-model <id>                Model for mission validators
  --validator-reasoning-effort <level>  Reasoning effort for mission validators
  -h, --help                            display help for command
```

Use any [available model ID](/models) with `--model` or `--spec-model`. For custom models, see [Custom Models (BYOK)](/model-independence/byok).

For multi-turn sessions, use `--input-format stream-jsonrpc` with a matching `--output-format stream-jsonrpc` and drive the session over [raw JSON-RPC](#build-custom-flows-on-raw-json-rpc). The older `stream-json` input mode still parses but is deprecated and prints a warning.

## Installation

<Steps>
  <Step title="Install the Droid CLI">
    **macOS/Linux:** `curl -fsSL https://app.factory.ai/cli | sh`

**Homebrew:** `brew install --cask droid`

**Windows:** `irm https://app.factory.ai/cli/windows | iex`

**npm:** `npm install -g droid`
  </Step>

  <Step title="Get Factory API Key">
    Generate your API key from the <a href="https://app.factory.ai/settings/api-keys">Factory Settings Page</a>
  </Step>

  <Step title="Set Environment Variable">
    Export your API key as an environment variable:
    ```bash
    export FACTORY_API_KEY=fk-...
    ```
  </Step>
</Steps>

## Quickstart

### Direct prompt

```bash
droid exec "analyze code quality"
droid exec "fix the bug in src/main.js" --auto low
```

### From file

```bash
droid exec -f prompt.md
```

### Pipe

```bash
echo "summarize repo structure" | droid exec
```

### Session continuation

```bash
droid exec --session-id <session-id> "continue with next steps"
```

## Autonomy Levels

Droid exec uses tiered autonomy to control what operations can run without manual confirmation. It starts read-only by default; use explicit flags when an automation needs to modify files, install dependencies, or touch external systems.

<ComparisonTable label='Choosing an autonomy level'>

| Mode | Allows | Blocks or limits | Best for |
| :--- | :----- | :--------------- | :------- |
| Default, no flags | Read-only file inspection, directory listing, process and environment inspection, and git read operations such as `git status`, `git log`, and `git diff`. | File edits, package installs, git writes, system changes, and deployments. | Analysis, planning, architecture review, security review, and reports. |
| `--auto low` | Low-risk project file creation and edits. | System modifications, package installs, remote writes, and production changes. | Documentation updates, formatting, adding comments, and simple local edits. |
| `--auto medium` | Low-risk actions plus common local development operations such as trusted package installs, builds, tests, `git commit`, `git checkout`, and `git pull`. | `git push`, sudo commands, production changes, and sensitive or irreversible operations. | Local development, dependency updates, test fixes, and CI preparation. |
| `--auto high` | High-risk automation including remote writes, deployments, database migrations, and commands that may access sensitive data, subject to Droid's remaining hard safety checks. | Extreme destructive operations such as `sudo rm -rf /` and system-wide unsafe changes. | CI/CD pipelines, staging deployments, and fully automated workflows in controlled environments. |
| `--skip-permissions-unsafe` | All operations without confirmation. | Cannot be combined with `--auto` flags. Use only where the environment is disposable. | Throwaway containers, ephemeral CI runners, and temporary VMs. |

</ComparisonTable>

Examples:

```bash
# Analyze and plan without making changes
droid exec "Analyze the authentication system and list the files that would need changes for an OAuth2 migration."

# Allow simple file edits
droid exec --auto low "add JSDoc comments to all exported functions"

# Allow normal local development operations
droid exec --auto medium "install deps, run tests, and fix failing checks"

# Allow deployment-oriented automation in a controlled environment
droid exec --auto high "fix the bug, run tests, commit, and push the branch"
```

<Warning>
  `--skip-permissions-unsafe` bypasses all permission checks. Only use it in completely isolated environments such as Docker containers, throwaway VMs, or ephemeral CI runners that are destroyed after the job.
</Warning>

```bash
# In a disposable Docker container for CI testing
docker run --rm -v $(pwd):/workspace alpine:latest sh -c "
  apk add curl bash &&
  curl -fsSL https://app.factory.ai/cli | sh &&
  droid exec --skip-permissions-unsafe 'Install dependencies, modify system configs, run privileged integration tests, and clean up test databases'
"
```

### Fail-fast behavior

If a requested action exceeds the current autonomy level, droid exec stops immediately with a clear error message, returns a non-zero exit code, and performs no partial changes. This ensures predictable behavior in automation scripts and CI/CD pipelines.

## Output formats and artifacts

Droid exec supports three output formats for different use cases:

### text (default)

Human-readable output for direct consumption or logs:

```bash
$ droid exec --auto low "create a python file that prints 'hello world'"
Perfect! I've created a Python file named `hello_world.py` in your home directory that prints 'hello world' when executed.
```

### json

Structured JSON output for parsing in scripts and automation:

```bash
$ droid exec "summarize this repository" --output-format json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "duration_ms": 5657,
  "num_turns": 1,
  "result": "This is a Factory documentation repository containing guides for CLI tools, web platform features, and onboarding procedures...",
  "session_id": "8af22e0a-d222-42c6-8c7e-7a059e391b0b"
}
```

Use JSON format when you need to parse the result in a script, check success/failure programmatically, extract session IDs for continuation, or process results in a pipeline.

### Build custom flows on raw JSON-RPC

For custom integrations, you can run Droid as a long-lived subprocess and drive the full JSON-RPC control surface over stdin/stdout:

```bash
droid exec --input-format stream-jsonrpc --output-format stream-jsonrpc --auto low
```

This is the lowest-level integration path for building your own interaction model around Droid. Each stdin line is one JSON-RPC request; each stdout line is a JSON-RPC response, server request, or notification. Your client spawns `droid exec` with the project `cwd` and desired flags, writes newline-delimited requests with unique IDs, reads stdout line-by-line to match responses by `id`, and implements timeouts, process cleanup, and session persistence. The core methods and events:

<PropertyList>
  <Property name='droid.initialize_session'>
    Start a new session; a client calls this (or `droid.load_session` to resume
    an existing session) first.
  </Property>
  <Property name='droid.add_user_message'>
    Send a turn to the session.
  </Property>
  <Property name='droid.session_notification'>
    Event stream your client handles: assistant text deltas, tool events, token
    usage, errors, and turn completion.
  </Property>
  <Property name='droid.request_permission'>
    Server-to-client request your client must answer; `droid.ask_user` arrives
    the same way.
  </Property>
</PropertyList>

Further session methods interrupt work, update settings, manage MCP servers/tools, inspect context, fork sessions, or compact history.

On top of raw stdin/stdout you can build web, desktop, or IDE agent experiences with your own UX and controls; chat or copiloting surfaces that route user actions into Droid turns; CI and workflow runners that execute Droid tasks and surface progress in build logs; orchestrators that queue work, resume sessions, fork conversations, and persist results; policy layers that approve, deny, transform, or audit tool permission requests; and bridges from Droid events into your own protocol, message bus, telemetry, or storage layer.

To disable Factory-provided builtin skills, set `disableBuiltinSkills` when initializing or loading the session:

```json
{"jsonrpc":"2.0","id":"1","method":"droid.initialize_session","params":{"machineId":"my-machine","cwd":"/workspace","disableBuiltinSkills":true}}
{"jsonrpc":"2.0","id":"2","method":"droid.load_session","params":{"sessionId":"session-123","disableBuiltinSkills":true}}
```

In stream JSON-RPC mode, use the request field instead of the `--disable-builtin-skills` CLI flag. The TypeScript SDK exposes the same option through `createSession({ disableBuiltinSkills: true })` and `resumeSession(sessionId, { disableBuiltinSkills: true })`.

For protocol reference and implementation patterns, see the low-level client and process transport in the [TypeScript SDK](https://github.com/Factory-AI/droid-sdk-typescript).

Prefer an SDK when possible:

- **TypeScript**: [`@factory/droid-sdk`](https://github.com/Factory-AI/droid-sdk-typescript) for Node.js apps, streaming, multi-turn sessions, structured output, permissions, tool controls, and SDK-backed MCP tools
- **Python**: [`droid-sdk`](https://github.com/Factory-AI/droid-sdk-python) for asyncio apps, streaming, direct client control, notifications, permissions, and typed event handling

For automated pipelines, you can also direct the agent to write specific artifacts:

```bash
droid exec --auto low "Analyze dependencies and write to deps.json"
droid exec --auto low "Generate metrics report in CSV format to metrics.csv"
```

## Working directory

Use `--cwd` to scope execution:

```bash
droid exec --cwd /home/runner/work/repo "Map internal packages and dump graphviz DOT to deps.dot"
```

Use `-w, --worktree [name]` to run the task inside an isolated [git worktree](/droid-cli/cli-reference#git-worktrees) on its own branch. This is useful for fanning out parallel `droid exec` jobs against the same repo without file conflicts:

```bash
droid exec --worktree codemod-a --auto medium "apply codemod A" &
droid exec --worktree codemod-b --auto medium "apply codemod B" &
wait
```

Clean worktrees are auto-removed on exit; dirty ones are preserved so you can review and push the work.

## Models and reasoning effort

Choose a model with `-m` and adjust reasoning with `-r`. See the [Factory-Managed Inference](/models) for available models.

```bash
droid exec -m claude-sonnet-4-5-20250929 -r medium -f plan.md
```

Use `--use-spec` to start in specification mode, where the agent plans before executing:

```bash
droid exec --use-spec --auto low "refactor the auth module"
```

You can also use a different model for the spec phase:

```bash
droid exec --use-spec --spec-model claude-haiku-4-5-20251001 --auto medium "implement feature X"
```

### Tool controls

List available tools for a model:

```bash
droid exec --list-tools
droid exec --model gpt-5.3-codex --list-tools --output-format json
```

Enable or disable specific tools:

```bash
# Restrict to only specific tools
droid exec --auto low --restrict-tools ApplyPatch "refactor files"

# Enable additional tools
droid exec --additional-tools ApplyPatch "refactor files"

# Disable specific tools
droid exec --auto medium --disabled-tools execute-cli "run edits only"
```

### Skill controls

Use `--disable-builtin-skills` when an interactive or non-interactive session should expose only skills supplied outside the Droid CLI:

```bash
# Start the interactive TUI without builtin skills
droid --disable-builtin-skills

# Run one non-interactive session without builtin skills
droid exec --disable-builtin-skills "analyze this repository"
```

This removes Factory-provided builtin skills while preserving user, project, plugin, automation, mission, runtime, and dynamically supplied skills. For an interactive launch, the restriction remains active when you create, resume, or switch sessions. It is also inherited by child sessions, including subagents and mission workers.

<Note>
  The flag is not supported in Agent Client Protocol (ACP) mode. Use it with standard `droid` or `droid exec`, or set `disableBuiltinSkills` on `droid.initialize_session` and `droid.load_session` requests in stream JSON-RPC mode.
</Note>

### Custom models

You can configure custom models to use with droid exec by adding them to your `~/.factory/settings.json` file:

```json
{
  "customModels": [
    {
      "model": "my-codex-model",
      "displayName": "My Custom Model",
      "baseUrl": "https://api.openai.com/v1",
      "apiKey": "${OPENAI_API_KEY}",
      "provider": "openai"
    }
  ]
}
```

To use a custom model, use the `custom:` prefix followed by the display name (with spaces replaced by dashes) and the index:

```bash
droid exec --model "custom:My-Custom-Model-0" "analyze this codebase"
```

If you have multiple custom models configured:

```json
{
  "customModels": [
    {
      "model": "moonshotai/kimi-k2-instruct-0905",
      "displayName": "Kimi K2 [Groq]",
      "baseUrl": "https://api.groq.com/openai/v1",
      "apiKey": "${GROQ_API_KEY}",
      "provider": "generic-chat-completion-api",
      "maxOutputTokens": 16384
    },
    {
      "model": "openai/gpt-oss-20b",
      "displayName": "GPT-OSS-20B [OpenRouter]",
      "baseUrl": "https://openrouter.ai/api/v1",
      "apiKey": "YOUR_OPENROUTER_KEY",
      "provider": "generic-chat-completion-api",
      "maxOutputTokens": 32000
    }
  ]
}
```

You would reference them as:

- `--model "custom:Kimi-K2-[Groq]-0"`
- `--model "custom:GPT-OSS-20B-[OpenRouter]-1"`

The index corresponds to the position in the `customModels` array (0-based).

<Note>
Reasoning effort (`-r` / `--reasoning-effort`) does not apply to custom models; it is controlled by the model and provider you configure.
</Note>

## Sessions, tagging, and logs

Forking lets you branch off an existing session without disturbing the original; the new run starts from the forked session's history and is assigned a fresh session ID.

```bash
# Continue a session in-place
droid exec --session-id <session-id> "next steps"

# Branch off a session into a new run
droid exec --fork <session-id> --auto low "try an alternative refactor"
```

Use `--tag` to attach searchable labels to a run. The flag is repeatable and accepts either a plain name or a JSON object for structured metadata. Pair it with `--log-group-id` to bucket logs from related runs together for easier filtering and aggregation downstream.

```bash
droid exec \
  --tag release-v2 \
  --tag '{"name":"team","value":"platform"}' \
  --log-group-id ci-nightly \
  --auto low "run nightly checks and write report.md"
```

## Customizing the system prompt

Use `--append-system-prompt` to append additional text to the end of the system prompt for a single run, or `--append-system-prompt-file` to append the contents of a file. Both flags can be combined and are useful for injecting project-specific guidance, style guides, or invariants without modifying global settings.

```bash
droid exec \
  --append-system-prompt "Always prefer functional React components." \
  --auto low "review src/components for class-based components"

droid exec \
  --append-system-prompt-file ./docs/style-guide.md \
  --auto low "lint prose in README.md against the style guide"
```

## Mission Mode

Mission Mode runs `droid exec` as a multi-agent orchestrator that plans work, delegates to worker agents, and validates results. Enable it with `--mission` and optionally select dedicated models and reasoning effort levels for the worker and validator roles. Mission Mode requires `--auto high` or `--skip-permissions-unsafe` because the orchestrator needs high autonomy to manage workers.

```bash
droid exec --mission \
  --worker-model claude-sonnet-4-5-20250929 \
  --worker-reasoning-effort medium \
  --validator-model claude-sonnet-4-5-20250929 \
  --validator-reasoning-effort high \
  --auto high \
  "ship the new billing webhook end-to-end"
```

### Mission Mode flags

<PropertyList>
  <Property name='--mission'>
    Run in Mission Mode (multi-agent orchestration).
  </Property>
  <Property name='--worker-model <id>'>
    Model ID used by mission worker agents.
  </Property>
  <Property name='--worker-reasoning-effort <level>'>
    Reasoning effort for mission workers.
  </Property>
  <Property name='--validator-model <id>'>
    Model ID used by mission validator agents.
  </Property>
  <Property name='--validator-reasoning-effort <level>'>
    Reasoning effort for mission validators.
  </Property>
</PropertyList>

The top-level `-m, --model` and `-r, --reasoning-effort` flags still apply to the orchestrator itself; the worker and validator overrides only affect the agents the orchestrator spawns.

## Batch and parallel patterns

Shell loops (bounded concurrency):

```bash
# Process files in parallel (GNU xargs -P)
find src -name "*.ts" -print0 | xargs -0 -P 4 -I {} \
  droid exec --auto low "Refactor file: {} to use modern TS patterns"
```

Background job parallelization:

```bash
# Process multiple directories in parallel with job control
for path in packages/ui packages/models apps/factory-app; do
  (
    cd "$path" &&
    droid exec --auto low "Run targeted analysis and write report.md"
  ) &
done
wait  # Wait for all background jobs to complete
```

Chunked inputs:

```bash
# Split large file lists into manageable chunks
git diff --name-only origin/main...HEAD | split -l 50 - /tmp/files_
for f in /tmp/files_*; do
  list=$(tr '\n' ' ' < "$f")
  droid exec --auto low "Review changed files: $list and write to review.json"
done
rm /tmp/files_*  # Clean up temporary files
```

Workflow Automation (CI/CD):

```yaml
# Dead code detection and cleanup suggestions
name: Code Cleanup Analysis
on:
  schedule:
    - cron: '0 1 * * 0' # Weekly on Sundays
  workflow_dispatch:
jobs:
  cleanup-analysis:
    strategy:
      matrix:
        module: ['src/components', 'src/services', 'src/utils', 'src/hooks']
    steps:
      - uses: actions/checkout@v4
      - run: droid exec --cwd "${{ matrix.module }}" --auto low "Identify unused exports, dead code, and deprecated patterns. Generate cleanup recommendations in cleanup-report.md"
```

## Unique usage examples

License header enforcer:

```bash
git ls-files "*.ts" | xargs -I {} \
  droid exec --auto low "Ensure {} begins with the Apache-2.0 header; add it if missing"
```

API contract drift check (read-only):

```bash
droid exec "Compare openapi.yaml operations to our TypeScript client methods and write drift.md with any mismatches"
```

Security sweep:

```bash
droid exec --auto low "Run a quick audit for sync child_process usage and propose fixes; write findings to sec-audit.csv"
```

## Exit behavior

`droid exec` exits `0` on success and non-zero on failure (permission violation, tool error, unmet objective). Treat non-zero as failed in CI.

## Best practices

- Favor `--auto low`; keep mutations minimal and commit/push in scripted steps.
- Avoid `--skip-permissions-unsafe` unless fully sandboxed.
- Ask the agent to emit artifacts your pipeline can verify.
- Use `--cwd` to constrain scope in monorepos.

<RelatedLinks>
  <RelatedLink href="/missions/running-cli" title="Running in the CLI">
    Orchestrate multi-agent missions from the command line.
  </RelatedLink>
  <RelatedLink href="/software-factory/code-review-ci" title="Automated Code Review">
    Wire Droid Exec into GitHub Actions for automated PR review.
  </RelatedLink>
</RelatedLinks>
