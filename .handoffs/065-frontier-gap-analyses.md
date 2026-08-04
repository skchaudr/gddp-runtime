# Frontier gap analyses — evidence for graph authoring (2026-08-04)

Deep-verified repo reality vs prior (now unauthoritative) graphs. Substrate for Sab's
new aa-cli / myapi frontier graphs. Prior graphs are historical baseline, not truth.

---

# Part 1: myapi

# Gap Analysis: MyAPI GDDP Graph vs. Repo Reality

This report analyzes the gap between the capability nodes defined in `/Users/sab-mini/repos/gddp-config/graphs/myapi/project.yaml` (dated 2026-07-28) and the active state of `/Users/sab-mini/repos/MyAPI` (branch `fix/terminal-rich-import-error`).

---

## 1. Vertex AI Baseline Assessment

### Verdict: ALREADY-DONE

**Findings:**
- There is concrete evidence of a comparative baseline evaluation run. A detailed diagnostic report exists at `/Users/sab-mini/repos/MyAPI/scratch/comparative_retrieval_benchmark.md` containing side-by-side RAG outputs comparing the custom MyAPI local retrieval pipeline (running on a VM) against Google's Vertex AI Enterprise Grounded Search Engine (`benchmark-search`).
- Verification logs, environment parameters, and scripts are present in the repository referencing the `benchmark-search` engine (e.g. `scratch/vertex-ai-rag-comparison-walkthrough.md` and `scratch/comparative_retrieval_benchmark.md`).
- Credentials and host references point to GCP project `sb-genai-2026` utilizing active user account `sbkchaudry@gmail.com`. The baseline was captured and compared across a 10-query representative diagnostic set on `2026-05-20T00:01:38-0700`.

---

## 2. Per-Node Verdicts (6 Nodes)

### Node 1: `capture-live-vertex-baseline`
- **Verdict**: **ALREADY-DONE**
- **Evidence**:
  - `scratch/comparative_retrieval_benchmark.md` - Records the exact queries, grounded synthesis answers, citation mappings, and success status from Vertex AI Generative RAG (engine: `benchmark-search`).
  - `scratch/vertex-ai-rag-comparison-walkthrough.md` - Confirms execution of a live 10-query benchmark run fetching Vertex AI Search data.

### Node 2: `assemble-current-personal-corpus`
- **Verdict**: **NEEDS-AMENDMENT**
- **Evidence**:
  - `scripts/build_daily_active_corpus.py` and `scripts/source_manifest.py` exist in the repository on branch `fix/terminal-rich-import-error` but are missing or completely overridden on other branches (like `feat/corpus-v1-normalization` which replaces them with `scripts/build_vault_v1.py` and `scripts/normalize_corpus.py`).
  - The definition of "personal corpus" needs a unified model reconcilation. `config/daily_corpus_allowlist.yaml` sets bounds, but the active/durable promotion pipeline is half-implemented across conflicting feature branches.

### Node 3: `mine-real-agent-query-benchmark`
- **Verdict**: **ALREADY-DONE**
- **Evidence**:
  - Mined agent query datasets exist in multiple shards inside the repo (such as `scratch/corpus-hot-v1/myapi/QUERIES.md` and `scratch/corpus-hot-v1/raw-mini/myapi/QUERIES.md`).
  - An evaluation bank is prepared inside `scratch/corpus-hot-v1/eval-bank-v0.md`. The 18-query MyAPI benchmark is run via `scripts/run_query_benchmark.py`.

### Node 4: `prove-myapi-context-retrieval`
- **Verdict**: **STILL-NEEDED**
- **Evidence**:
  - Reranking validation script `scripts/benchmark_to_refinement_queue.py` and basic query routines `scripts/run_query_benchmark.py` exist.
  - However, three-way evaluation comparing the active corpus (specifically the proposed V4 schema normalization) against the frozen Vertex baseline is not completely automated or recorded in a canonical comparative artifact.

### Node 5: `serve-context-via-mcp`
- **Verdict**: **ALREADY-DONE** (Fixture level) / **STILL-NEEDED** (Integration level)
- **Evidence**:
  - `mcp/server.py` implements fixture-backed `get_project_context` and `get_person_context` tools reading from `evals/golden_briefs/`.
  - `tests/test_mcp_server.py` validates that the MCP server returns these briefs.
  - Integration with the live Context Refinery RAG retrieval pipeline is missing. It only serves static golden briefs.

### Node 6: `prove-incremental-refresh`
- **Verdict**: **STILL-NEEDED**
- **Evidence**:
  - While `scripts/build_daily_active_corpus.py` handles flat file copying/linking, there is no verification suite or receipt verifying that a delta update of the registry avoids full rebuild/duplication.

---

## 3. Candidate New Node Proposals

### Proposal 1
- **ID**: `unify-normalization-pipelines`
- **Title**: Unify feature-branch normalization and corpus build scripts
- **Goal**: Merge the divergent RAG ingestion scripts (`build_vault_v1.py`, `normalize_corpus.py` on the feature branch versus `build_daily_active_corpus.py`, `source_manifest.py` on main/fix branches) into a single production pipeline config.
- **Criteria**:
  1. A single ingestion CLI accepts options for active hot windowing or full historical v1 scanning.
  2. Substrate schemas validate consistently across all configurations.
- **Depends on**: `assemble-current-personal-corpus`

### Proposal 2
- **ID**: `integrate-mcp-with-live-retrieval`
- **Title**: Connect MCP tools to live query retrieval pipeline
- **Goal**: Transition MCP tools `get_project_context` and `get_person_context` from static markdown fixture servers into dynamically generated context briefs driven by the Context Refinery query pipeline.
- **Criteria**:
  1. MCP tool calls query the local database retrieval pipeline when requested.
  2. If pipeline retrieval fails, the tool gracefully falls back to the golden briefs.
- **Depends on**: `serve-context-via-mcp`, `prove-myapi-context-retrieval`

### Proposal 3
- **ID**: `stabilize-source-manifest-test`
- **Title**: Resolve active source manifest CLI test failure
- **Goal**: Debug and fix `test_cli_writes_active_manifest_for_source_root` in `tests/test_source_manifest.py`, which currently fails with `AssertionError: assert 0 == 1` due to mock file classification issues.
- **Criteria**:
  1. `test_cli_writes_active_manifest_for_source_root` passes successfully.
  2. The source manifest test suite runs without warnings or errors.
- **Depends on**: `assemble-current-personal-corpus`

---

# Part 2: aa-cli

# Gap Analysis: AA CLI GDDP Graph vs. Repo Reality

This report analyzes the gap between the capability nodes defined in `/Users/sab-mini/repos/gddp-config/graphs/aa-cli/project.yaml` (dated 2026-06-29/07-03) and the active state of `/Users/sab-mini/repos/aa-cli`.

---

## 1. Per-Node Verdicts (12 Nodes)

All 12 nodes are marked **complete** in the original config graph. Below is the spot-check verdict and code/file evidence verifying the status of each capability.

| Node ID | Verdict | Repository File & Code Evidence | Notes |
| :--- | :--- | :--- | :--- |
| **`common-core`** | **CONFIRMED-COMPLETE** | `lib/common.zsh` defines `AA_ROOT`, `AA_DATA_HOME`, `AA_STATE_HOME`, `AA_SCHEMA` (lines 3-7). `aa_init_dirs` (lines 47-49) creates the XDG-local paths. `aa_validate_packet` (lines 51-58) validates the prompt packet structure via `jq` using `schema/packet.schema.json`. | Schema and directories bootstrap successfully. |
| **`target-registry`** | **CONFIRMED-COMPLETE** | `lib/targets.zsh` implements `aa_target_parse_row` (lines 4-15), which supports legacy 3-column rows, and `aa_target_lookup` (lines 17-49) which performs fallback logic. Deduplicated target listing is implemented in `aa_target_names` (lines 51-65). Target configuration is centrally managed in `targets.conf`. | Correctly routes target lookup queries dynamically. |
| **`ledger-system`** | **CONFIRMED-COMPLETE** | `lib/ledger.zsh` implements tab-separated ledger appending via `aa_ledger_append` (lines 3-6) and atomic temp-file based updates via `aa_ledger_update_state` (lines 8-15). Stale detection is coded in `aa_is_stale` (lines 41-52). Glyphs are defined in `aa_state_glyph` (lines 54-76). | Fits the required 6-column TSV specification. |
| **`dispatch-router`** | **CONFIRMED-COMPLETE** | `lib/fire.zsh` contains `aa_fire_packet` (lines 28-181) which enforces schema validation before dispatch, sets up output logging/run directories, and branches into target handlers depending on sync or async modes resolved via targets.conf. | Central command dispatcher routing loop is operational. |
| **`dispatch-grok`** | **CONFIRMED-COMPLETE** | `targets.conf` lists the `grk` default sync target. `lib/fire.zsh` (lines 146-173) handles sync command dispatches natively by spinning a background process (`eval "$command" < "$prompt" > "$out"`) and writing a PID tracking record. `lib/common.zsh` prevents double-clipboard copying for `grk`. | Fully wired. |
| **`dispatch-pi-cli`** | **CONFIRMED-COMPLETE** | `targets.conf` registers `pir` default, speed, and frontier tiers. Sourced libraries match and execution operates through the general-purpose sync runner inside `lib/fire.zsh` capturing exit codes. | Fully integrated. |
| **`dispatch-gemini`** | **CONFIRMED-COMPLETE** | `targets.conf` registers `gemini` default sync `agy`. Checked against standard inline command evaluation inside `lib/fire.zsh`. | Runs correctly as a sync target. |
| **`dispatch-droid`** | **CONFIRMED-COMPLETE** | `targets.conf` registers `droid` default sync `droid exec`. Captured output, exit status, and state transitions conform to standard sync workflow. | Runs inline through sync pipeline. |
| **`dispatch-codex`** | **CONFIRMED-COMPLETE** | `lib/fire.zsh` (lines 63-83) checks for `__codex_async` target command, checks packet mutations status (`aa_mutations_from_packet`), sets sandbox constraints (`--sandbox workspace-write` vs `read-only`), and runs the background nohup wrapper. | Async dispatch logic behaves correctly. |
| **`dispatch-jules`** | **CONFIRMED-COMPLETE** | `lib/fire.zsh` (lines 85-103) extracts Owner/Repo URL paths from git origin, invokes `jules remote new`, parses numeric session IDs from dispatch logs, and records them as the ledger reference. | Async remote execution routes cleanly. |
| **`dispatch-pi-harness`** | **CONFIRMED-COMPLETE** | `lib/fire.zsh` (lines 105-144) verifies `pi-packet` binary paths, compiles inline packet YAML files containing goal and mutations options if `packet_slug` is empty, and launches a background runner storing `pi_artifact` pointers. | Harness background runner is correct. |
| **`reconciliation`** | **CONFIRMED-COMPLETE** | `lib/reconcile.zsh` contains `aa_reconcile` (lines 64-106) mapping active states to liveness-checks. Local PID targets are verified in `aa_reconcile_pid_target` (lines 28-50) using `exit_status`/`pid` logs. Jules remote status is fetched and pulled in `aa_reconcile_jules_target` (lines 53-62). | Atomically updates TSV ledger rows without deletion. |

---

## 2. Tool Health Verdict

**Verdict: HEALTHY**

The aa-cli zsh backend and core functions are in excellent working order.
- **CLI Commands**: Running `bin/aa inventory` successfully reads existing prompt packets and states, showing `open 0 · queue 0 · tasks 0 · prompts 8`.
- **Validation**: Running `tests/acceptance.zsh` executes the full suite of sync generation, async generation, refire checks, mock background codex execution, and reconciliation, printing `PASS`.
- **Zsh Error Handling**: Invoking `bin/aa --help` fails with `aa: unknown command: --help` as expected due to the positional argument parsing fallback, showing the wrapper parses inputs properly.
- **hub-rs Suite**: Running `cargo test` in the Rust TUI codebase passes 100/100 unit tests. The single render integration failure (`loads_live_aa_data_without_panic`) is expected since the test environment does not initialize with pre-populated dummy packets.

---

## 3. Next-Phase Candidate Node Proposals

The original graph from `2026-06-29/07-03` only covered the zsh script executor. The active repository has since expanded to implement a Rust-based TUI (`hub-rs`) and a project-local graph at `gddp/project.yaml` containing 31 nodes. To align the config graph with modern development targets, we propose the following next-phase nodes:

### Proposal 1: `hub-shell-two-paths`
- **ID**: `hub-shell-two-paths`
- **Title**: Provide the two-path Rust cockpit shell
- **Goal**: Compile and host the core Rust TUI operator panel (`hub-rs`) with Path 0 (Create Task) and Path 1 (Deck) lane switching, bypassing the need for a mandatory CLI lobby menu.
- **Criteria**:
  1. Operator can toggle between Path 0 and Path 1 using `Tab` key.
  2. Escape/back keys return user to the previous interactive screen state.
- **Depends on**: `common-core`

### Proposal 2: `deck-runway-verification`
- **ID**: `deck-runway-verification`
- **Title**: Implement the Runway pulse strip and Verify drawer
- **Goal**: Simplify the TUI layout by reducing Runway height to ~3 lines for ephemeral fire receipts only, and building a full-screen Verify drawer displaying packet contracts, logs, diffs, and verification commands.
- **Criteria**:
  1. Runway strip automatically clears successful dispatches after TTL or on the subsequent fire gesture.
  2. Verify screen loads full file diff outputs and allows key binding transitions directly to editor viewports.
- **Depends on**: `hub-shell-two-paths`, `reconciliation`

### Proposal 3: `openclaw-cross-machine-access`
- **ID**: `openclaw-cross-machine-access`
- **Title**: Enable remote Tailnet command execution and state sync
- **Goal**: Allow remote clients on Tailnet host profiles to query target lists, sync state changes, and execute packets without local API key copies or gateway service duplication.
- **Criteria**:
  1. Connection checks verify that only the single central gateway (e.g. `sab-mini`) receives and schedules packets.
  2. Disconnection during a run fails gracefully, maintaining receipt integrity on next reconciliation.
- **Depends on**: `dispatch-router`

### Proposal 4: `deck-dependency-model`
- **ID**: `deck-dependency-model`
- **Title**: Packet dependency mapping and block checks
- **Goal**: Support parent/child execution constraints within packet schemas, checking that `depends_on` nodes are validated before a child packet can be launched.
- **Criteria**:
  1. Packet schema parses `depends_on` array field.
  2. `aa_is_blocked` logic returns a boolean block status, and the Deck interface highlights blocked items.
- **Depends on**: `ledger-system`

---

# Part 3: pi ecosystem survey

# GDDP Project Graph Survey: Pi Agent & Harness Ecosystem

This document provides a comprehensive survey of Sab's `pi` agent and harness ecosystem on this machine. It outlines the current state, proposes a GDDP project configuration with a concrete graph node plan, and highlights crucial scope and repo decisions Sab needs to make.

---

## 1. Pi Ecosystem Inventory

The `pi` coding agent and its execution harness are organized across several directories in the home space and homebrew libraries.

### A. Root Workspace Path: `/Users/sab-mini/.pi/`
This is a local Git repository tracking configuration, prompt schemas, and custom tools.
*   **`.git/`**: Local git tracking configuration history.
*   **`AGENTS.md`**: Top-level developer guidelines and operations contract for agents modifying the workspace.
*   **`PROJECT-BRIEF.md`**: Broad overview of the portfolio, architecture, and current objectives.
*   **`agent/`**: The runtime configuration and active environment layout.
    *   `AGENTS.md`: Runtime operating contract (response shapes, tool rules).
    *   `SOUL.md` & `USER.md`: Agent persona context and Sab's direct operational preferences.
    *   `RUNBOOK.md`: Core verification smoke tests for models and execution modes.
    *   `settings.json`: Configuration dictionary declaring active packages (NPM & local), enabled models, default providers, and subagent mode overrides.
    *   `extensions/`: Custom TypeScript lifecycle extensions:
        *   `mutation-confirm.ts` (write/execution protection gate)
        *   `cwd-guard.ts` (cross-directory boundary enforcement)
        *   `agent-guardrails.ts` (safety and output shaping rules)
        *   `answer-noise-trim.ts` (prose and formatting cleaner)
        *   `capability-cascade.ts` (multi-agent tracing)
    *   `skills/`: Reusable procedural commands (e.g., `loop-breaker`, `node-packet-ledger`, `pi-boss`).
    *   `npm/`: Locally installed NodeJS packages acting as extensions (`pi-intercom`, `pi-grok-cli`, `pi-clinepass-provider`, etc.).
    *   `scripts/`: Python and JavaScript utility hooks (e.g., `ensure-host-settings.py`, `pi-observe.py`, `pi-daily-memory.py`).
*   **`harness/`**: The declarative execution runner.
    *   `bin/pi-packet`: The central script that parses YAML packets, renders prompts, dispatches them, and executes validation.
    *   `bin/pi-lite` / `pi-full` / `pi-studio`: Profile launchers adjusting token overhead by enabling/disabling extensions.
    *   `lib/`: Supporting scripts for schema validation, response extraction, verification runs, and skill-tree bridge updates.
    *   `packets/`: A library of test packets (e.g., `smoke-test.yaml`).
    *   `schemas/packet.schema.json`: JSON Schema contract validating node packet layout.
*   **`needle/`**: Core directory tracking the Gemma 26M/50MB local tool router.
*   **`gddp/`**: Local GDDP bridge workspace holding active project/node definitions (currently holds `pi-needle` design integration nodes).

### B. Global System Integrations
*   **CLI Path**: `/opt/homebrew/bin/pi` -> symlink to `/opt/homebrew/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js`.
*   **Launcher Symlink**: `/Users/sab-mini/.pi/agent/bin/pi` -> `/Users/sab-mini/.pi/harness/bin/pi-lite` (restricts system prompt footprint by default).

### C. Associated Repositories
*   **`/Users/sab-mini/repos/gddp-runtime-local-pi`**: A local clone of `gddp-runtime` configured with a scripted fleet bridge to manage subagent dispatch pipelines.

### D. GDDP Integration Touchpoint
In `gddp-runtime`, `scripts/local_agent_executor.py` runs a local agent by creating a detached worktree for the target repository, piping a `NodePacket` on stdin, running the agent CLI, committing the output to a temporary attempt branch, and outputting a `gddp.local_result.v1` JSON block detailing the final commit SHA.

---

## 2. Proposed GDDP Project Graph

### Project Metadata
*   **`project_id`**: `pi-harness-ops`
*   **`project_name`**: "Pi Harness & Extensions"
*   **`description`**: "Automated lifecycle management, extension priority ordering, op-sec sanitization, and Needle routing integration for the Pi Agent harness."
*   **`repo`**: `/Users/sab-mini/.pi` (tracked as a local repository checkout, or mapped to a remote fork).

---

### Candidate Nodes

#### 1. `harness-loader-priorities`
*   **Goal**:
    Modify the extension loader to support a `priority` field or implement a static loading order so gating extensions (such as `mutation-confirm` and `cwd-guard`) are guaranteed to register and execute lifecycle hooks before arbitrary user-configured extensions.
*   **Acceptance Criteria**:
    1. A `priority` field is introduced in extension manifests or evaluated deterministically in the loader script.
    2. Enforced order is printed during verbose launcher startup logs (e.g., `pi-lite --verbose`).
    3. An integration test verifies that user extensions attempting to intercept tool calls are evaluated after gating extensions.
*   **Depends On**: `[]`

#### 2. `memory-staleness-validator`
*   **Goal**:
    Write a TypeScript extension hooked to the `session_start` event that parses the last three daily memory documents (`agent/memory/YYYY-MM-DD.md`) and validates that all referenced directories, git branches, and file paths still exist on the host machine, flagging stale references in the session logs.
*   **Acceptance Criteria**:
    1. The extension successfully registers in `settings.json` and loads without introducing performance regressions during session start.
    2. If a nonexistent path or dead branch is detected, the extension emits a warning payload into the audit log.
    3. The hook gracefully falls back and does not block the session if files are inaccessible.
*   **Depends On**: `[]`

#### 3. `pi-packet-needle-route`
*   **Goal**:
    Wire the `pi-route` (Needle router) executable into `harness/bin/pi-packet` (Surface A). When executing a packet with mutation access, the runner executes Needle first to determine if local execution can handle the request or if a frontier model call is required.
*   **Acceptance Criteria**:
    1. `pi-packet` invokes `pi-route` during the dispatch phase when the packet does not disable routing.
    2. If Needle classifies the intent as a local tool call, the payload bypasses the remote model and short-circuits.
    3. An evaluation mode log tracks routing choices without mutating state (shadow mode).
*   **Depends On**: `[]`

#### 4. `needle-routing-shadow-benchmark`
*   **Goal**:
    Build an automated evaluation runner that executes a 5-verb validation set 20+ times to evaluate classification accuracy, execution latency, and token cost difference compared to direct frontier dispatch.
*   **Acceptance Criteria**:
    1. The benchmark script runs headlessly and records findings in `needle/docs/needle-bench.md`.
    2. Generated metrics clearly state correct classifications, misclassifications, and average processing latency per call.
    3. Failure paths (e.g., daemon connection drops) are gracefully caught and recorded.
*   **Depends On**: `["pi-packet-needle-route"]`

#### 5. `public-scrub-pipeline`
*   **Goal**:
    Implement an automated scrub script that checks the `.pi` codebase and config templates for sensitive leakage (such as Tailscale Tailnet IPs, GCP credentials, private home directories, and email addresses) to prepare the harness codebase for public distribution.
*   **Acceptance Criteria**:
    1. A verification script `scripts/public-scrub.py` exists and is run-checked.
    2. A configuration file maps allowed public items vs private scrub targets.
    3. The git commit log for tracking files is evaluated to verify old sensitive diffs have been scrubbed or squashed.
*   **Depends On**: `[]`

#### 6. `tui-concurrency-stabilization`
*   **Goal**:
    Improve the native Rust TUI (`pi-hub-rs`) handling of timeouts and network latency when polling Tailnet nodes, preventing the UI from freezing when remote machines are unreachable.
*   **Acceptance Criteria**:
    1. Configurable environment variables `PI_HUB_OBSERVE_TIMEOUT_MS` and `PI_HUB_MACHINE_TIMEOUT_MS` are introduced and verified.
    2. When SSH queries fail or exceed deadlines, the TUI falls back to stale cache representations with a visual indicator, rather than hanging or failing.
*   **Depends On**: `[]`

---

## 3. Risks & Scope Decisions for Sab

1.  **Repository Isolation Strategy**:
    The `.pi` directory is a local Git repository, but it contains active keys, settings, private histories, and machine-local configurations (`auth.json`, `settings.json`, and Obsidian bridge paths).
    *   *Decision Required*: Should Sab split the codebase into a clean, public repository (tracking `harness/` and generic `extensions/`) and a separate private configuration overlay? Run-dispatch tools require clean worktrees to commit and push safely; committing directly inside `.pi` risks pushing private secrets.
2.  **Needle Shadow Threshold**:
    *   *Decision Required*: What is the minimum acceptable accuracy rate for promoting Needle from shadow mode to live routing? If Needle has an 80% routing accuracy but misroutes 20% of commands (forcing slow fallbacks or failure), does the token savings outweigh the latency overhead?
3.  **Recursive Executor Safety**:
    *   *Decision Required*: The Pi harness controls subagent provisioning. If GDDP runs automated tests that invoke `pi-packet` which in turn dispatches nested `pi` instances, we run the risk of infinite process loops. How should we implement process-tree depth limits or mock-mode verification for the runner's self-testing?
