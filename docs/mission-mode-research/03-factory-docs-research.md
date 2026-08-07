# Factory Droid mission, daemon, hooks, and SDK research

Research date: 2026-08-07. Installed CLI baseline supplied by the caller: Droid v0.189.0. Evidence policy: statements below are documented facts unless marked **INFERRED**; unanswered questions say **not documented**. Factory documentation index: https://docs.factory.ai/llms.txt.

## 1. Documentation sweep

### Official pages reviewed

- Missions: [overview](https://docs.factory.ai/missions/overview.md), [planning and validation](https://docs.factory.ai/missions/planning.md), [running in CLI](https://docs.factory.ai/missions/running-cli.md), and [configuration/reference](https://docs.factory.ai/missions/reference.md).
- Headless/programmatic: [Droid Exec](https://docs.factory.ai/droid-exec/overview.md), [CLI reference](https://docs.factory.ai/droid-cli/cli-reference.md), [Sessions REST API](https://docs.factory.ai/api-reference/sessions.md), and [settings](https://docs.factory.ai/droid-cli/settings.md).
- Safety/modes: [autonomy](https://docs.factory.ai/autonomy-and-safety/auto-run.md) and [interaction modes](https://docs.factory.ai/autonomy-and-safety/specification-mode.md).
- Harness: [hooks](https://docs.factory.ai/harness/hooks.md), [skills](https://docs.factory.ai/harness/skills.md), and [custom droids](https://docs.factory.ai/harness/subagents.md).
- Stability/history: [feature maturity](https://docs.factory.ai/changelog/feature-maturity.md) and [full changelog](https://docs.factory.ai/changelog/release-notes.md).
- SDK/protocol: [TypeScript SDK reference](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md), [Python SDK README](https://github.com/Factory-AI/droid-sdk-python), and [ACP](https://agentclientprotocol.com/protocol/v1/overview.md).

### Documented lifecycle

1. `/missions` (also `/mission`) begins a collaborative planning conversation; the orchestrator asks questions and produces features grouped into milestones ([overview](https://docs.factory.ai/missions/overview.md)). Headless runs instead use `droid exec --mission -f mission.md`; proposals auto-approve per installed help, while the web reference only says it plans and executes without a live TUI ([reference](https://docs.factory.ai/missions/reference.md)).
2. Before implementation, the orchestrator writes a validation contract, decomposes features, and creates shared state. A programmatic runner executes features in order with fresh worker contexts ([architecture article](https://factory.ai/news/missions-architecture)).
3. Each feature is worked by a worker; milestone boundaries trigger scrutiny and user-testing validators. The orchestrator turns findings into fix features and repeats validation until pass ([architecture article](https://factory.ai/news/missions-architecture)).
4. If blocked, the orchestrator halts and returns control to the user ([architecture article](https://factory.ai/news/missions-architecture)). Interactive users monitor Mission Control, pause, prompt the orchestrator, re-plan, or direct it to move on ([CLI running](https://docs.factory.ai/missions/running-cli.md), [troubleshooting](https://docs.factory.ai/missions/overview.md)).

### Observed artifact coverage

The product article explicitly names shared artifacts `validation-contract.md`, `features.json`, `services.yaml`, and `AGENTS.md`, plus “research notes, operational guidelines, and an evolving knowledge base” ([architecture article](https://factory.ai/news/missions-architecture)). Official skills docs document `{missionDir}/skills/**/SKILL.md` ([skills](https://docs.factory.ai/harness/skills.md)). The official release notes say only that Missions files were consolidated under `~/.factory` in v0.108.0, without a layout contract ([changelog](https://docs.factory.ai/changelog/release-notes.md)).

| Observed item | Documented at all? | Contract status |
|---|---|---|
| `state.json` / `missionId: mis_*` | No | **not documented** |
| `features.json` | Yes, as shared state; no current public schema/path contract | Name/purpose documented, local shape internal |
| `handoffs/*.json` | No | **not documented** |
| `progress_log.jsonl` | No | **not documented** |
| `worker-transcripts.jsonl` | No | **not documented** |
| `validation/` | Validation phase documented; directory is not | Directory **not documented** |
| `validation-state.json` | No in current official docs | **not documented** |
| `library/` | Evolving knowledge base documented conceptually; directory is not | Directory **not documented** |
| `skills/` | Yes, `{missionDir}/skills/**/SKILL.md` | Documented skill source |
| `AGENTS.md` | Yes | Documented inherited worker guidance |
| `services.yaml` | Named in architecture article | Name/purpose documented; schema/path not contractual |
| `init.sh` | No | **not documented** |

A reverse-engineered v0.84.0 prompt reports more paths and schemas, but it is third-party interception, not a Factory contract and predates 0.189.0 ([gist](https://gist.github.com/V1ki/356b121038722ebf32b5aac85482c113)).

## 2. Mission mode

- **Directory layout:** **not documented** as a contractual interface. Factory documents selected shared-state names and only a broad `~/.factory` consolidation note; it does not promise `~/.factory/missions/<session-uuid>/` or JSON/JSONL schemas ([architecture](https://factory.ai/news/missions-architecture), [v0.108.0 changelog](https://docs.factory.ai/changelog/release-notes.md)).
- **External observation:** Interactive Mission Control documents feature/milestone progress and active agents ([running CLI](https://docs.factory.ai/missions/running-cli.md)). The TypeScript SDK says partial streams can contain “mission events,” but gives no event names or payload schemas ([SDK reference](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#partial-events)). `MultiMissionStateManager` is exported only as a low-level advanced resource, again without mission state schema ([SDK reference](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#low-level-daemon-integration)). A supported per-feature external status API is **not documented**.
- **Submit/cancel one feature:** **not documented.** The stable daemon API includes `sessions.killWorker`; the Python JSON-RPC SDK has `kill_worker_session(worker_session_id)`, but neither says a worker maps one-to-one to a mission feature or that killing it cancels that feature ([TS SDK](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#stable-daemon-resources), [Python README](https://github.com/Factory-AI/droid-sdk-python)). Do not equate worker kill with feature cancellation.
- **Resume/restart:** Interactive docs advise pausing and prompting the orchestrator to recover ([overview troubleshooting](https://docs.factory.ai/missions/overview.md)). Changelog v0.177.0 says interrupt now pauses missions; v0.131.0 says active missions keep running across network reconnects ([changelog](https://docs.factory.ai/changelog/release-notes.md)). Exact headless process-death restart, mission-ID resume, replay, and idempotency semantics are **not documented**.
- **Headless vs interactive:** Headless `droid exec --mission` has no live TUI and auto-plans/executes, requires High/unsafe, and accepts worker/validator model overrides ([mission reference](https://docs.factory.ai/missions/reference.md), [exec](https://docs.factory.ai/droid-exec/overview.md)). Interactive `/missions` explicitly collaborates on and requires approval of the plan, then exposes Mission Control for pause/intervention ([overview](https://docs.factory.ai/missions/overview.md)). Whether all other lifecycle details are identical is **not documented**.
- **Commits/branches/worktrees:** Marketing says workers coordinate handoffs through git ([Introducing Missions](https://factory.ai/news/missions)). Worker commit shape, branch names, base/result SHAs, and merge semantics are **not documented**. `--worktree` is documented for the top-level session: one sibling worktree and dedicated branch; clean exec worktrees auto-remove, dirty ones persist ([CLI worktrees](https://docs.factory.ai/droid-cli/cli-reference.md#git-worktrees)). Whether mission workers share that worktree or each receive their own is **not documented**.
- **Completion/exit signal:** Generic `droid exec` exit codes are 0 success, 1 runtime error, 2 invalid arguments; exec docs also say non-zero for permission/tool/unmet objective ([CLI](https://docs.factory.ai/droid-cli/cli-reference.md#exit-codes), [exec](https://docs.factory.ai/droid-exec/overview.md#exit-behavior)). Mission-specific finished vs paused vs returned-to-orchestrator exit codes are **not documented**.
- **Attempts/automatic pause:** Planning estimates one worker run per feature but calls that a floor; follow-up/fix features can be added ([planning](https://docs.factory.ai/missions/planning.md)). No attempt cap is documented. Blocking causes the orchestrator to halt/return control, but exact automatic-pause thresholds and retry policy are **not documented** ([architecture](https://factory.ai/news/missions-architecture)).
- **Commit ancestry requirement:** No official mission event/artifact guarantees per-feature base and result commit IDs. Therefore base→result ancestry verification from mission internals is currently **not supportable from a documented contract**.

## 3. stream-jsonrpc, ACP, and output formats

### Output values and schemas

The CLI documents exactly `text`, `json`, `stream-json`, and `stream-jsonrpc` ([CLI reference](https://docs.factory.ai/droid-cli/cli-reference.md)).

- `text`: human-readable final/log output; no machine schema ([exec](https://docs.factory.ai/droid-exec/overview.md#text-default)).
- `json`: one result object. Documented example fields: `type: "result"`, `subtype: "success"`, `is_error`, `duration_ms`, `num_turns`, `result`, `session_id` ([exec](https://docs.factory.ai/droid-exec/overview.md#json)). A complete formal JSON Schema and mission extensions are **not documented**.
- `stream-json`: valid output and legacy input value. Older input mode is deprecated. Changelog says `session_id` was added in v0.21.3 and reasoning output was fixed in v0.94.0 ([exec](https://docs.factory.ai/droid-exec/overview.md), [changelog](https://docs.factory.ai/changelog/release-notes.md)). Full event union/schema, terminal event, and mission event behavior are **not documented**.
- `stream-jsonrpc`: newline-delimited JSON-RPC 2.0 responses, notifications, and server requests, paired with the matching input format ([exec](https://docs.factory.ai/droid-exec/overview.md#build-custom-flows-on-raw-json-rpc)). The TypeScript/Python SDKs are the published typed references; there is no standalone versioned wire-protocol specification.

### Proprietary raw JSON-RPC

Factory documents core operations: initialize/load a session, add a user message, receive assistant/tool/token/error/turn-complete notifications, answer `droid.ask_user`, interrupt, settings, MCP/tool controls, context, fork, compact ([exec](https://docs.factory.ai/droid-exec/overview.md#build-custom-flows-on-raw-json-rpc)). The Python v0.1.3 client explicitly lists `initialize_session`, `load_session`, `add_user_message`, `interrupt_session`, `kill_worker_session`, `update_session_settings`, `close_session`, `compact_session`, `fork_session`, `rename_session`, tool/command discovery, rewind, MCP, skills, and bug reports ([Python SDK README](https://github.com/Factory-AI/droid-sdk-python#api-reference)). Exact low-level method strings beyond shown `droid.initialize_session` / `droid.load_session`, every parameter/result schema, compatibility negotiation, and protocol version are not collected in one official wire document.

**Mission key question:** TypeScript 0.7 exposes `DroidInteractionMode.Mission`, allows `interactionMode` on `run()`/session creation, and says partial streams may contain mission events ([SDK reference](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#one-shot-runs)). This is documented evidence that the session API can start/stream a mission-mode session. However, mission-event names/shapes, feature state/control, artifact references, and commit IDs are **not documented**. The SDK's daemon `droid.unstable.missions` exposes only readiness inspection/acknowledgment, not lifecycle control ([SDK reference](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#unstable-daemon-resources)).

### ACP

ACP does mean **Agent Client Protocol**. ACP is JSON-RPC 2.0 with `initialize`, `session/new` or `session/load`, `session/prompt`, `session/update`, and `session/cancel` ([ACP overview](https://agentclientprotocol.com/protocol/v1/overview.md)). Factory Droid is listed as an ACP agent ([ACP agents](https://agentclientprotocol.com/get-started/agents.md)). Factory's raw stream-jsonrpc uses proprietary `droid.*` methods, so it is not the same method surface as ACP. Factory's docs mention that `--disable-builtin-skills` is unsupported “in ACP mode,” but do not document an ACP launch flag, Factory capability matrix, or whether Factory exposes Mission as an ACP session mode ([exec skill controls](https://docs.factory.ai/droid-exec/overview.md#skill-controls)). ACP's generic session modes are agent-advertised; this does not prove Mission support ([ACP modes](https://agentclientprotocol.com/protocol/v1/session-modes.md)). **Can ACP drive/observe a Factory Mission? not documented.**

## 4. Daemon

The CLI command is documented only as “Run the Factory daemon server”; the installed help supplies websocket/IPC flags ([CLI reference](https://docs.factory.ai/droid-cli/cli-reference.md)). The public TypeScript 0.7 SDK is the substantive supported client documentation:

- `connectToDaemon({url, auth:{apiKey}})` over WebSocket, example `ws://127.0.0.1:37643`; trusted-local-browser warning because API key is visible ([SDK](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#connect-to-a-daemon)).
- Stable namespaces include sessions, workspace, settings, custom models, SSH, updates, relay, terminals, MCP, skills, commands, plugins, marketplaces, automations, git, and feedback. Sessions include create/resume/list/messages/search/archive/settings/killWorker/rewind/compact/fork/context ([SDK stable resources](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#stable-daemon-resources)).
- Advanced public exports include `DaemonClient`, controllers/state managers, WebSocket transport, daemon events/types; `/node` adds IPC/in-process transports ([SDK low-level daemon](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#low-level-daemon-integration)).
- Socket discovery conventions, IPC path convention, auth handshake wire schema, raw method names, compatibility/version negotiation, and `--enable-child-ipc` semantics are **not documented** in Factory docs/SDK guide.
- Installed help says mission workers spawn via `factoryd`; official mission reference says workers are spawned but does not name/prove daemon routing. Whether all mission worker spawning goes through the public daemon protocol is **not documented**.

Assessment: the SDK facade is a supported public integration point; raw socket/protocol details not exposed by the SDK are internal. `droid.unstable.*` explicitly may change between SDK releases ([SDK](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md#unstable-daemon-resources)).

## 5. Hooks

Source: full [Hooks reference](https://docs.factory.ai/harness/hooks.md).

### Configuration and precedence

- User `~/.factory/hooks.json`; project `.factory/hooks.json`; enterprise managed settings; legacy `.factory/hooks/hooks.json` migrates to `.factory/hooks.json`.
- If `hooks.json` is absent, the matching `settings.json` `hooks` key is read. Plugins contribute `<plugin>/hooks/hooks.json`. Enterprise hooks always load unless globally disabled; `allowManagedHooksOnly` can exclude user/project hooks.
- Exact merge ordering among user, project, plugin, legacy, and nested-folder configurations is **not fully enumerated** on the hooks page; it delegates managed hierarchy to enterprise settings.
- Hooks are snapshotted at startup. Commands run from current `cwd`; use `$FACTORY_PROJECT_DIR` or absolute paths.

### Events and documented stdin additions

All events receive common stdin JSON: `session_id`, `transcript_path`, `cwd`, `permission_mode` (`off|spec|auto-low|auto-medium|auto-high`), `hook_event_name`, optional `message_id`.

| Event | When | Added fields documented |
|---|---|---|
| `PreToolUse` | Parameters built, before tool | `tool_name`, `tool_input` |
| `PostToolUse` | Immediately after tool | `tool_name`, `tool_input`, `tool_response` |
| `UserPromptSubmit` | Before prompt processing | `prompt`, `has_images` |
| `Notification` | Notification emitted | `message`, `notification_type`: `permission_prompt|idle_prompt|auth_success|elicitation_dialog` |
| `Stop` | Main Droid about to finish response | `stop_hook_active`, `tool_execution_count`, `elapsed_time` |
| `SubagentStop` | Task-launched sub-droid ends | `task_name`, `task_result`, `task_error`, `stop_hook_active` |
| `PreCompact` | Before manual/auto compaction | `trigger: manual|auto`, `custom_instructions`, `message_count`, `estimated_tokens` |
| `SessionStart` | startup/resume/clear/compact | `source: startup|resume|clear|compact`, optional prior session IDs (names not specified) |
| `SessionEnd` | session ends | `reason: clear|logout|prompt_input_exit|other`, `session_duration_ms`, `message_count` |

The exact exhaustive payload schema for every event is **not documented**: tool input/response are tool-dependent; optional prior-session field names and nullability are not specified.

### Environment variables

The docs say common scalar fields are also exposed as environment variables, but do **not document their exact environment-variable names or casing transformation**. Explicitly named variables are `$FACTORY_PROJECT_DIR`; plugin hooks additionally get `DROID_PLUGIN_ROOT` and compatibility alias `CLAUDE_PLUGIN_ROOT`. Hooks inherit the local environment/credentials. No mission ID, feature ID, worker role, parent session ID, branch, worktree, or commit SHA environment variable is documented.

### Exit/output semantics

- 0 succeeds. `UserPromptSubmit` and `SessionStart` stdout can add context; elsewhere stdout is transcript-visible.
- 2 is corrective/blocking: `PreToolUse` blocks; `PostToolUse` and `Stop` feed stderr to Droid; `UserPromptSubmit` blocks; other lifecycle events only surface stderr.
- Other non-zero is non-blocking where the event permits.
- JSON `continue:false` stops processing (`stopReason` optional); `suppressOutput:true` hides successful output in main chat.
- `PreToolUse` JSON supports permission `allow|deny|ask` and `updatedInput`; `PostToolUse`, prompt, Stop/SubagentStop support block decisions as documented; `SessionEnd` cannot block.

### Can hooks capture per-mission-worker evidence?

Missions explicitly inherit hooks and “lifecycle hooks fire during mission execution” ([mission reference](https://docs.factory.ai/missions/reference.md)). That sentence does not say which worker processes/sessions fire which hooks. `SubagentStop` is explicitly only for **Task-launched** sub-droids, not mission workers ([hooks](https://docs.factory.ai/harness/hooks.md)). Therefore: **whether `SessionStart`/`SessionEnd` fire for every mission worker is not documented**.

If live probing proves they do, `SessionEnd` is the best candidate: it carries `session_id`, transcript path, cwd, duration, message count, and reason. It misses mission/feature identity, worker role, parent session, base/result commits, branch/worktree, and structured handoff. **INFERRED:** a capture script could independently record Git HEAD at start/end keyed by session ID, but mapping that session to a feature would still require an undocumented channel. Do not architect around this before probing.

## 6. SDKs and public repositories

The organization page showed 21 public repositories on 2026-08-07: `droid-action`, `droid-code-review`, `droid-sdk-typescript`, `droid-sdk-python`, `factory-plugins`, `legacy-bench`, `eslint-plugin`, `factory`, `vfs`, `sentry-incident-response`, `simple-chatapp`, `tui-test`, `examples`, `bun-pty`, `factory-zed-extension`, `cursed-plugins`, `terraform-provider-snyk`, `SERA`, `nanobanana-cli`, `skills`, and `terminal-bench-leaderboard` ([organization repositories](https://github.com/orgs/Factory-AI/repositories)).

### TypeScript

`@factory/droid-sdk` version 0.7.0, Apache-2.0 guide/examples repo, updated 2026-08-06 ([package.json](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/package.json)). Node mode spawns `droid exec` by default; daemon mode connects via WebSocket; custom framed transports are allowed. It supports one-shot and multi-turn sessions, typed streaming/partial events, result states, permissions/AskUser, tool controls, hooks in streams, MCP, session resume/fork/compact/rewind, daemon session management, and observability ([SDK reference](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md)). Mission mode and mission events exist in the types/guide, but no per-feature mission API or event schema is documented. Stable daemon resources are labeled; mission readiness APIs live under explicitly unstable resources. No GitHub releases/tags were published on the repository page despite npm versioning ([repo](https://github.com/Factory-AI/droid-sdk-typescript)).

### Python

`droid-sdk` version 0.1.3, Python 3.10+, Apache-2.0, updated 2026-08-05 ([pyproject](https://github.com/Factory-AI/droid-sdk-python/blob/main/pyproject.toml)). `ProcessTransport` spawns `droid exec`; communication is JSON-RPC 2.0 over JSONL stdin/stdout. It provides asyncio typed events, direct session lifecycle, interruption, generic worker kill, settings, tools, MCP, skills, structured output, permission and AskUser handlers ([README](https://github.com/Factory-AI/droid-sdk-python)). Mission mode/event types are **not documented** in its README. It has only five commits and no GitHub releases/tags on the observed page, so stability is materially weaker than TypeScript ([repo](https://github.com/Factory-AI/droid-sdk-python)).

## 7. Changelog and release cadence

Installed 0.189.0 is newer than the newest documented changelog entry retrieved, 0.186.0 (2026-07-31), so changes in 0.187–0.189 are **not documented in the retrieved changelog**. Recent cadence is nearly daily: 0.167 (Jul 7) through 0.186 (Jul 31) contains 18 listed releases, often skipping numbers ([changelog](https://docs.factory.ai/changelog/release-notes.md)).

Relevant volatility evidence:

- Missions: v0.177 fixed interrupt→pause; v0.179 fixed approvals; v0.173 fixed Mission Control; v0.172 added app panel; v0.171 fixed settings/notifications; v0.131 made active missions survive reconnects; v0.123 changed usage accounting; v0.113 added Mission Control shortcuts; v0.109.1 added artifact schema validation; v0.108 consolidated mission files; v0.94 fixed stream-json reasoning; v0.92 redesigned `/missions` and added per-worker tokens; v0.72 added subagent streaming; v0.64 split enter/exit commands ([changelog](https://docs.factory.ai/changelog/release-notes.md)).
- Hooks: v0.173 fixed duplicate firing, v0.168 fixed cancelled-turn notification, v0.167 fixed hung SessionStart and sandbox execution, v0.161 overhauled manager, v0.156.2 added org governance, v0.152 fixed event merging, v0.129 added streamed hook events ([changelog](https://docs.factory.ai/changelog/release-notes.md)).
- Worktrees: introduced v0.70, renamed flag behavior v0.71, config directory v0.74, and subsequent branch/error fixes ([changelog](https://docs.factory.ai/changelog/release-notes.md)).
- JSON streams: stream-json input arrived v0.19.8; `session_id` added v0.21.3; permissions in stream-jsonrpc v0.22.9; reasoning init data v0.33; later JSON-RPC error and stream reasoning fixes ([changelog](https://docs.factory.ai/changelog/release-notes.md)).

**LOUD STABILITY WARNING:** Factory says untagged docs are generally available and “stable, supported, and safe to build on,” but Missions itself says “still evolving” and publishes open design questions ([maturity](https://docs.factory.ai/changelog/feature-maturity.md), [missions overview](https://docs.factory.ai/missions/overview.md#open-questions)). The rapid CLI cadence and repeated mission/hook/daemon fixes mean only documented, typed SDK facades should be treated as integration candidates. Pin CLI and SDK versions; standalone installs auto-update unless disabled ([CLI auto-updates](https://docs.factory.ai/droid-cli/cli-reference.md#auto-updates)).

## 8. Prior art

- Factory's own architecture uses a programmatic runner and shared artifact files, but exposes no public runner API or schemas ([architecture article](https://factory.ai/news/missions-architecture)).
- A March 2026 gist intercepted v0.84.0 traffic and reverse-engineered mission prompts/tools/artifacts ([gist](https://gist.github.com/V1ki/356b121038722ebf32b5aac85482c113)). It demonstrates that internals could be observed at that version; it does **not** demonstrate a stable external integration and is now 105 CLI versions behind 0.189.0.
- Searches found no public repository/blog that documents a working external controller which launches a current headless mission, tracks each feature through a supported API, and extracts per-feature commit ancestry. Search results mainly returned Factory docs/articles, the reverse-engineering gist, and generic orchestration discussion. Therefore successful prior art for the target design is **not documented/found**.

## Stability assessment

Factory's maturity policy calls untagged documented features GA. Ratings below are narrower: whether the exact integration surface needed by GDDP is documented and contractual.

| Surface | Rating | Reasoning |
|---|---|---|
| Mission directory artifacts | **Undocumented-internal** | No layout/schema contract; only selected artifact concepts/names ([architecture](https://factory.ai/news/missions-architecture)) |
| `progress_log.jsonl` | **Undocumented-internal** | Never named in official docs |
| `handoffs/*.json` | **Undocumented-internal** | Handoff concept exists in marketing, path/schema do not |
| Hooks | **Documented-and-contractual** for listed lifecycle contract; worker coverage gap | Full config/events/control docs, but per-mission-worker firing is not promised ([hooks](https://docs.factory.ai/harness/hooks.md)) |
| `stream-jsonrpc` | **Documented-but-unstable** | Official and SDK-backed, but proprietary unversioned wire protocol; SDKs changed immediately before research ([exec](https://docs.factory.ai/droid-exec/overview.md), [Python 0.1.3](https://github.com/Factory-AI/droid-sdk-python)) |
| `stream-json` output | **Documented-but-unstable** | Valid value, but schema absent and legacy input deprecated; history shows additive/fix changes ([CLI](https://docs.factory.ai/droid-cli/cli-reference.md)) |
| Daemon via TS SDK facade | **Documented-and-contractual** for stable namespaces | Public SDK explicitly labels stable vs unstable; raw protocol/socket conventions remain internal ([SDK](https://github.com/Factory-AI/droid-sdk-typescript/blob/main/docs/typescript-sdk-reference.md)) |
| SDK | **Documented-but-unstable** | Public/typed, but TS 0.7 and Python 0.1.3, no repo releases/tags, active changes Aug 5–6 |
| Worktree top-level behavior | **Documented-and-contractual** | Branch/worktree lifecycle is explicit ([CLI](https://docs.factory.ai/droid-cli/cli-reference.md#git-worktrees)) |
| Worktree behavior inside Missions | **Undocumented-internal** | Worker sharing/isolation/merge behavior not stated |

## Recommended integration surfaces

1. **Pinned TypeScript SDK 0.7 + pinned Droid 0.189, through high-level Node `DroidSession`/daemon stable facade.** Best available typed streaming, interruption, terminal result, and documented Mission interaction mode. Tradeoff: mission event payloads are not documented, so use only generic session/result events until Factory documents mission events. Breakage: SDK/CLI compatibility or event union changes; contain behind a GDDP adapter and contract tests.
2. **Top-level process supervision of `droid exec --mission` plus documented generic exit codes.** Treat exit 0/nonzero and stdout/stderr as coarse run evidence only. Tradeoff: cannot distinguish pause/return states or per-feature completion. Breakage: mission-specific exit semantics may emerge/change.
3. **Documented hooks for policy/audit, not feature completion.** Use Pre/PostToolUse and top-level SessionStart/End only for what payloads prove. Tradeoff: no feature/mission/commit identity and mission worker coverage unpromised. Breakage: hook schema is documented, but event delivery bugs have been frequent.
4. **Top-level `--worktree` as a mission-wide isolation boundary.** The single top-level worktree lifecycle is documented. Do not assume per-worker worktrees. Breakage: dirty/clean cleanup behavior or mission worker cwd inheritance; latter needs probe.
5. **REST Sessions API only if organization-enabled.** It can list/get/messages/interrupt ordinary sessions, but is selected-org-only and has no mission endpoints ([Sessions API](https://docs.factory.ai/api-reference/sessions.md)).
6. **Avoid:** direct parsing/mutation of `state.json`, `features.json`, `progress_log.jsonl`, handoffs, worker transcripts, validation state, raw daemon IPC, or reverse-engineered tools. These are the exact unstable/internal surfaces that can turn an assumption into architecture.

For base→result ancestry, require workers to emit a GDDP-owned signed/validated receipt through a documented external tool or repository artifact under GDDP's contract; do not infer SHAs from Factory mission internals. Whether mission workers can reliably call such a tool per feature still requires probing.

## Documentation gaps requiring live probes

Run probes only in a disposable repository with pinned v0.189.0 and capture stdout/stderr, SDK events, hook inputs, process exit, worktrees, and git graph:

1. Exact TypeScript partial mission event discriminants and payloads; whether they include mission ID, feature ID/state, worker session ID, handoff, or commits.
2. Whether `createSession({interactionMode: Mission})` is behaviorally equivalent to `droid exec --mission`, including auto-approval and required autonomy.
3. Whether `stream-json` or `stream-jsonrpc` with `--mission` is accepted by v0.189.0 and what the complete terminal/result sequence is.
4. Mission-specific process exit behavior for completed, paused by interrupt, blocked, waiting for orchestrator/user, and worker/validator failure.
5. Resume after Ctrl-C/process kill/host reboot: invocation, mission-ID linkage, idempotency, and artifact recovery.
6. Whether SessionStart/SessionEnd hooks fire in orchestrator, every feature worker, every validator, and Task subagents; capture exact env names and stdin payloads.
7. Whether worker hook `session_id` can be mapped to feature ID using any documented SDK notification. If not, hooks cannot provide per-node evidence.
8. With top-level `--worktree`, whether all mission workers use one worktree, nested worktrees, branches, or daemon-owned copies; how commits are integrated.
9. Per-feature Git behavior: starting HEAD, result HEAD, author, branch, merge/cherry-pick strategy, handling of no-commit/dirty returns, concurrent features, and fix features.
10. Whether stable `sessions.killWorker` pauses/retries/fails a mission feature or merely kills a generic child session; do not test against valuable work.
11. Attempts/retries cap and automatic pause thresholds.
12. Daemon default websocket host/port, IPC socket paths/permissions, authentication/version negotiation, and child IPC behavior.
13. ACP launch mode and advertised Factory modes/capabilities; specifically whether Mission is advertised and whether updates expose mission state.
14. Formal `json` and `stream-json` schemas for a mission at 0.189.0, including error/interruption/result records.
15. Confirm whether 0.187–0.189 contain mission/daemon/hooks/JSON-RPC changes absent from the current public changelog.

## Raw downloads

Full text saved under `/Users/sab-mini/mission-recon-gddp/docs-raw/`:

- `mission-overview.md`
- `mission-planning.md`
- `mission-running-cli.md`
- `mission-reference.md`
- `droid-exec.md`
- `cli-reference-worktrees-output.md`
- `hooks.md`
- `sessions-api.md`
- `settings.md`
- `autonomy.md`
- `interaction-modes.md`
- `feature-maturity.md`
- `acp-overview.md`
- `acp-session-modes.md`
- `sdk-typescript-reference.md`
- `sdk-python-readme.md`
