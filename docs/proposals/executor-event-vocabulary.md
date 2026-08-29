# Executor event vocabulary — canonical `ExecutorEvent` for all transports

Status: proposal. Read-only analysis; no code changed.
Scope: harness-agnostic event/observability normalization ahead of
`scripts/adapters/cursor_cli_adapter.py`.

Empirical basis: 72 real `events.jsonl` files under
`jobs/local-subprocess-spool/*/events.jsonl` (241,585 events), the cursor-agent
spike results at `scripts/runtime/spike/cursor_cli_spike_results.json`, and the
pi spike record at `scripts/runtime/spike/pi_rpc_persistent_spike_results.json`.

---

## 1. What pi_rpc emits today

**There is no GDDP event vocabulary today.** `_RpcClient._record`
(`scripts/adapters/pi_rpc_adapter.py:1314`) appends every line pi writes to its
RPC stdout, verbatim and unfiltered, to `events.jsonl`. The de-facto vocabulary
*is* pi's internal event schema. Every field any consumer reads is a pi field.

Measured across all 72 spools:

| pi event type | count | keys | consumed by |
|---|---|---|---|
| `message_update` | 221,271 | `assistantMessageEvent`, `type`, `usage` | `extract_actual_cached_tokens` (unintentionally — see §1.2) |
| `entry_appended` | 7,833 | `entry{type,customType,data,id,parentId,timestamp}` | nobody |
| `extension_ui_request` | 2,933 | `id`, `method`, `statusKey`, `statusText`, `type` | nobody |
| `message_start` | 2,477 | `message{role,content,timestamp,usage}` | skipped explicitly (`scripts/prompt_topology.py:237`) |
| `message_end` | 2,476 | `message{role,content,timestamp,usage}` | `extract_actual_cached_tokens` (`scripts/prompt_topology.py:227`) |
| `tool_execution_update` | 1,458 | `toolCallId`, `toolName`, `args`, `partialResult` | nobody |
| `tool_execution_start` | 1,413 | `toolCallId`, `toolName`, `args` | `extract_read_paths` (`scripts/adapters/pi_rpc_adapter.py:541`) |
| `tool_execution_end` | 1,401 | `toolCallId`, `toolName`, `result`, `isError` | `extract_read_paths` (`scripts/adapters/pi_rpc_adapter.py:527`) |
| `turn_start` | 778 | `type` only | nobody |
| `turn_end` | 765 | `message{...,usage,stopReason,model,provider}`, `toolResults` | skipped explicitly (`scripts/prompt_topology.py:237`) |
| `response` | 122 | `id`, `command`, `success`, `data{sessionFile,sessionId,model,...}` | `_RpcClient.send` correlation (`scripts/adapters/pi_rpc_adapter.py:1232`) |
| `agent_start` | 74 | `type` only | nobody |
| `agent_end` | 61 | `messages`, `willRetry` | turn boundary (`scripts/adapters/pi_rpc_adapter.py:1274-1283`) |
| `agent_settled` | 21 | `type` only | nobody |

`message_update.assistantMessageEvent.type` distribution (the 221k):
`toolcall_delta` 140,088 · `thinking_delta` 62,047 · `text_delta` 14,295 ·
`toolcall_start` 1,414 · `toolcall_end` 1,413 · `thinking_start`/`end` 756 each ·
`text_start`/`end` 251 each.

**91.6% of the spool is `message_update` deltas that no consumer parses for
content.** They are read only as an aggregate byte stream by `tail -F`
(`gddp-config/scripts/gddp.py:4690`) and as an mtime liveness proxy
(`gddp-config/scripts/gddp.py:4439`).

Observed `args` keys per `toolName` (start events):

| toolName | n | args keys observed |
|---|---|---|
| `read` | 452 | `path` (452), `limit` (104), `offset` (58) |
| `bash` | 378 | `command` (378), `timeout` (208) |
| `subagent` | 257 | 34 distinct keys (`action`, `model`, `task`, `mission`, …) |
| `grep` | 86 | `pattern` (86), `path` (**83** — 3 calls carry no path), `glob`, `limit`, `context`, … |
| `write` | 79 | `path` (79), `content` (79) |
| `ls` | 65 | `path` (65) |
| `find` | 62 | `pattern` (62), `path` (57), `limit` (3) |
| `edit` | 34 | `path` (34), `edits` (34) |

### 1.1 Consumer inventory (who reads the spool, and what)

| Consumer | Path | Reads | Pi-coupled? |
|---|---|---|---|
| `extract_read_paths` | `scripts/adapters/pi_rpc_adapter.py:508-554` | `type`, `toolCallId`, `toolName`, `args.path`, `isError`, `result.isError` | **Yes — raw pi shape** |
| `compute_turn_context_coverage` | `scripts/adapters/pi_rpc_adapter.py:557-630` | via `extract_read_paths` only | Indirect |
| `extract_actual_cached_tokens` | `scripts/prompt_topology.py:205-249` | `type` ∈ {`message_end`,`message_start`,`turn_end`}, `message.usage.cacheRead` | **Yes — pi type names** |
| Turn-boundary wait | `scripts/adapters/pi_rpc_adapter.py:1274-1283` | `type == "agent_end"`, plus two nested-shape fallbacks | **Yes** |
| Turn windowing | `scripts/adapters/pi_rpc_adapter.py:833-839, 899-916` | Byte offset via `stat().st_size`, not events | **Yes (hack)** |
| Batch fan-out | `scripts/adapters/pi_rpc_adapter.py:874-883` | Copies the whole byte stream to sibling attempt dirs | Shape-agnostic |
| `gddp watch` liveness | `gddp-config/scripts/gddp.py:4439` | `events.jsonl` **mtime** only | Shape-agnostic |
| `gddp watch` recent-events | `gddp-config/scripts/gddp.py:4519-4543` | `type` \| `event.type`, then first of `name`/`command`/`path`/`tool` | **Broken for pi** (§1.3) |
| Evaluator lane coverage | `scripts/runtime/verification/orchestrator.py:370-400` | A *different* trace shape: `{event,tool,path,toolCallId,ok,blocked}` | **Yes — second vocabulary** |
| Evaluator usage | `scripts/runtime/verification/semantic/pi_runner.py:363-380` | `message_end` from pi `--mode json` stdout | **Yes** |
| `dispatcher.py` | `scripts/runtime/heartbeat/dispatcher.py` | **Nothing.** Routes packets; never touches the stream | No |
| `local_subprocess_adapter` | `scripts/adapters/local_subprocess_adapter.py:442-443` | Writes `stdout`/`stderr`, **no `events.jsonl`** | N/A |

Findings worth calling out:

- **Two independent tool-event vocabularies already exist in-repo.** The
  executor path parses pi's native `tool_execution_start`/`_end`
  (`scripts/adapters/pi_rpc_adapter.py:513-516`). The evaluator path parses a
  hand-rolled trace emitted by the pi extension guard
  (`scripts/runtime/verification/semantic/pi_harness/gddp_verifier_guard.ts:80-153`)
  with keys `{ts, tool, path, toolCallId, ok, blocked}`. Both implement the same
  none/low/medium/high coverage rating twice
  (`scripts/adapters/pi_rpc_adapter.py:606-613` vs
  `scripts/runtime/verification/orchestrator.py:411-419`). Unifying on a canonical
  event collapses these to one implementation.
- **`dispatcher.py` expects nothing from the event stream.** No dispatch-side
  constraint on the vocabulary.

### 1.2 Coupling bug: `extract_actual_cached_tokens` over-counts

`scripts/prompt_topology.py:237` skips `message_start` and `turn_end` when a
`message_end` is present, but does **not** skip `message_update`.
`_find_usage_dict` (`scripts/prompt_topology.py:252`) falls through to the
top-level `usage` key, which `message_update` carries.

Measured: 146,799 `message_update` events carry a `usage` dict, and **2,098 of
them carry a nonzero `cacheRead`** (max 260,288). Those are summed on top of the
777 authoritative `message_end` values. The `actual_cached_tokens` written into
`prompt_cache_report.json` (`scripts/adapters/pi_rpc_adapter.py:917-923`) is
therefore inflated on any turn where a streaming update carried usage.

This is exactly the failure the canonical vocabulary prevents: the consumer is
guessing at provider shapes instead of reading one event the driver promises to
emit once.

### 1.3 Coupling bug: `gddp watch` shows tool events with no detail

`_event_brief` (`gddp-config/scripts/gddp.py:4519-4527`) looks for detail under
top-level `name`/`command`/`path`/`tool`. Pi emits `toolName` and nests the path
at `args.path`. Replaying a real spool through that function yields:

```
'tool_execution_start'
'tool_execution_start'
'tool_execution_end'
```

The operator's primary observability surface — described in
`docs/proposals/LOOP.md:26-28` as the watch/steer surface — renders bare type
names for every tool call. This is the strongest argument that the vocabulary
matters: the field names the watch surface *guessed at* are what a canonical
event should actually define.

---

## 2. cursor-agent stream-json, as observed

From `scripts/runtime/spike/cursor_cli_spike_results.json` (7 turns, flags
`-p --trust --output-format stream-json --stream-partial-output`,
`scripts/runtime/spike/cursor_cli_spike.py:70-79`):

| `type`/`subtype` | shape (observed fields only) |
|---|---|
| `system`/`init` | `session_id` (uuid), `model` (display name, e.g. `"Kimi K3 Max"`) |
| `user` | 1 per turn, echo of the prompt |
| `thinking`/`delta`, `thinking`/`completed` | 6–39 deltas per turn |
| `assistant` | `message.content[].text` — partial + final, both emitted |
| `tool_call`/`started` | `call_id`, `tool_call.<name>ToolCall.args` |
| `tool_call`/`completed` | `call_id`, `tool_call.<name>ToolCall.args`, `.result` |
| `result`/`success` | `is_error`, `result`, `session_id`, `request_id`, `duration_ms`, `duration_api_ms`, `usage{inputTokens,outputTokens,cacheReadTokens,cacheWriteTokens}` |

Concrete `tool_call` record (`cursor_cli_spike_results.json:229-245`):

```json
{"call_id": "Read_0_10e6fbcd-558f1", "tool_key": "readToolCall",
 "path": "/tmp/cursor-cli-spike/spike-target.txt", "subtype": "started"}
{"call_id": "Read_0_10e6fbcd-558f1", "tool_key": "readToolCall",
 "path": "/tmp/cursor-cli-spike/spike-target.txt",
 "result_keys": ["success"], "subtype": "completed"}
```

Structural differences from pi that the normalizer must absorb:

1. **Tool name is a key, not a field.** `tool_call.readToolCall`, discovered by
   suffix match (`scripts/runtime/spike/cursor_cli_spike.py:98`). Pi has a flat
   `toolName` string.
2. **`tool_call/completed` carries `args` as well as `result`.** Pi's
   `tool_execution_end` carries only `toolCallId`/`toolName`/`result`/`isError` —
   no args. This asymmetry decides §6.
3. **Usage is terminal and singular.** One `usage` on the `result` event, with
   `cacheReadTokens` (not pi's per-message `cacheRead`). No per-model-call usage
   stream.
4. **Assistant text is duplicated.** `assistant_text` reads
   `"SPIKE7-COLDSPIKE7-COLD"` (`cursor_cli_spike_results.json:13`) — partial and
   final content both accumulate. Naive concatenation doubles output.
5. **No terminal event on death.** `sigterm_mid_turn` and `sigkill_mid_turn`
   both have `"result_event": null` (`cursor_cli_spike_results.json:102, 155`).
   `invalid_model` produced **zero** stream events, exit 1, stderr only
   (`cursor_cli_spike_results.json:47-56`).
6. **Session id appears twice** — `system/init.session_id` and
   `result.session_id` — and is stable across resume
   (`cursor_cli_spike_results.json:41, 87`).

**Not observed, must not be assumed** (`cursor_cli_spike_results.json:5-8`, and
per the failure pattern in `AGENTS.md:6-13`): write/edit/shell `tool_call`
variants, their arg key names, error/failure `tool_call` subtypes, and any
`result` subtype other than `success`. Only `readToolCall` was exercised.

---

## 3. Proposed canonical vocabulary — 7 types

Every event shares one envelope; the type-specific fields are additive.

```
ExecutorEvent = {
  "v": 1,
  "ts": "2026-08-29T21:14:03.221Z",   # ISO-8601 UTC, driver-stamped
  "executor": "pi_rpc" | "cursor_cli",
  "session_id": str,
  "turn_id": str,                      # stable within one turn
  "seq": int,                          # monotonic within one turn
  "type": <one of the 7 below>,
  ...type fields...,
  "raw_type": str                      # harness type, for forensics only
}
```

| canonical type | fields | why it earns its place |
|---|---|---|
| `session_started` | `session_id`, `model`, `resume_token` | Both harnesses' resume story depends on it. Pi obtains it out-of-band via a `get_state` RPC and writes a sidecar file (`scripts/adapters/pi_rpc_adapter.py:1076-1080, 1127`); cursor gets it from `system/init`. Making it an event removes the sidecar. |
| `turn_started` | `turn_id`, `prompt_tokens_estimate?` | Replaces the byte-offset windowing hack at `scripts/adapters/pi_rpc_adapter.py:838-839`. A session-cumulative spool becomes windowable by `turn_id` instead of `stat().st_size`. |
| `assistant_message` | `text`, `role` | Final text only, never deltas. Not machine-consumed today, but it is what a human reads in `gddp watch`; §1.3 shows the watch surface currently renders nothing useful. Collapsing 221k deltas into one event per message is the single biggest volume win. |
| `tool_started` | `call_id`, `tool`, `paths[]`, `command?`, `args_digest` | Liveness only: an operator must see a long `bash` start before it ends. |
| `tool_completed` | `call_id`, `tool`, `paths[]`, `ok`, `error?`, `duration_ms?` | **Self-contained** — carries `tool` and `paths` again, so coverage reads one event type (§4). |
| `usage` | `input`, `output`, `cache_read`, `cache_write`, `cost?`, `scope` | Emitted **once per completed model call** (`scope: "message"`) or once per turn (`scope: "turn"`), never both. Directly fixes §1.2: the consumer stops sniffing provider shapes. |
| `turn_ended` | `turn_id`, `status` ∈ {`completed`,`failed`,`cancelled`}, `error?`, `stop_reason?` | Replaces three-way `agent_end` string matching (`scripts/adapters/pi_rpc_adapter.py:1274-1283`). Must be **driver-synthesized** when the harness emits nothing — cursor emits no terminal event on SIGKILL or invalid model (§2.5). |

### Candidates rejected

| candidate | verdict | reason |
|---|---|---|
| `turn_completed` + `turn_failed` as separate types | Merge into `turn_ended{status}` | Mirrors the existing `exit.json` contract (`scripts/adapters/pi_rpc_adapter.py:1430-1435`), which is already a single record with `returncode`/`cancelled`/`plumbing` fields, not three record types. |
| `assistant_output` (streaming) | Renamed, deltas dropped | 221,271 delta events; zero consumers parse their content. Keep the raw stream for `tail -F` if wanted (§6), not in the canonical spool. |
| `file_read` | **Drop** | Fully derivable from `tool_completed` where `tool ∈ {read, grep}` — which is exactly what `_CONTENT_TOOLS` already does (`scripts/adapters/pi_rpc_adapter.py:504`). A second event asserting the same fact creates two places to keep in sync. |
| `file_changed` | **Drop** | Same derivation from `tool ∈ {write, edit}`. And `gddp watch` reads changed files from **git**, not events (`gddp-config/scripts/gddp.py:4492-4507`), so no consumer wants it. |
| `process_started` / `process_completed` | **Drop** | `bash` is a tool: 378 `tool_execution_start` events with `toolName: "bash"`. Modeling shell separately duplicates `tool_started`/`tool_completed` for one tool name. Put `command` on the tool events instead. |

Net: 11 candidates → 7 types, with `session_started` added.

---

## 4. HARD CONSTRAINT — fields context coverage requires

`extract_read_paths` (`scripts/adapters/pi_rpc_adapter.py:508-554`) needs exactly
four facts per content-tool call. Read from the current implementation:

| fact | current pi source | line | canonical field |
|---|---|---|---|
| tool name, matchable against `{read, grep}` | `event["toolName"]` | `:544` | `tool_completed.tool` |
| file path (relative paths are real and resolve against `base`) | `event["args"]["path"]` | `:547` | `tool_completed.paths[]` |
| the call **succeeded** (`isError` false) | `event["isError"]` / `result.isError` | `:535-537` | `tool_completed.ok` |
| the call **completed** (a start with no end must not count) | start/end join on `toolCallId` | `:550-552` | implicit — `tool_completed` only exists on completion |
| correlation across the pair | `toolCallId` | `:530, 550` | `tool_completed.call_id` |

**Required contract:** `tool_completed` MUST carry `tool` and `paths` in addition
to `ok`. If `paths` lived only on `tool_started`, every consumer would have to
re-implement the start/end join — the two-pass loop at
`scripts/adapters/pi_rpc_adapter.py:525-554` — and the cursor driver's advantage
(cursor's `tool_call/completed` already carries `args`, per
`cursor_cli_spike_results.json:236-244`) would be thrown away.

With a self-contained `tool_completed`, coverage becomes a one-pass filter:

```
paths = { resolve(p, base)
          for e in events
          if e.type == "tool_completed" and e.ok and e.tool in CONTENT_TOOLS
          for p in e.paths }
```

Two further requirements:

- `paths` is a **list**, possibly empty. Measured: 3 of 86 `grep` calls carry no
  `path` arg. A scalar `path` field would force a null convention.
- `paths` entries stay **as the harness reported them** (relative or absolute).
  Resolution against `base` is the consumer's job
  (`scripts/adapters/pi_rpc_adapter.py:643-650`); the driver must not resolve,
  because it may not know the consumer's `base` (pi's cwd is the repo, not the
  session worktree — `scripts/adapters/pi_rpc_adapter.py:104-107`).
- `tool` is the **canonical** lowercase name, not the harness spelling. See §5's
  name column and the open question in §7.2.

---

## 5. Mapping tables

### 5.1 pi RPC → canonical

| pi event | canonical | field mapping | notes |
|---|---|---|---|
| `response` (`command: get_state`) | `session_started` | `data.sessionId` → `session_id`; `data.sessionFile` → `resume_token`; `data.model` → `model` | Today an RPC round-trip, not a stream event (`scripts/adapters/pi_rpc_adapter.py:1236-1243`). |
| `turn_start` | `turn_started` | driver assigns `turn_id` | Pi carries no id; driver mints it. |
| `agent_start` | *(drop)* | — | No fields, no consumer. |
| `message_start` | *(drop)* | — | Its `usage` is a zero stub (verified: all-zero example, §1). |
| `message_update` | *(drop from canonical)* | — | 221k events. `assistantMessageEvent.text_delta` may be re-derived into `assistant_message` text if the driver prefers deltas over `message_end.content`. |
| `message_end` | `assistant_message` + `usage{scope:"message"}` | `message.content[].text` → `text`; `message.usage.{input,output,cacheRead,cacheWrite}` → `{input,output,cache_read,cache_write}`; `message.usage.cost` → `cost` | The **only** authoritative usage source. Fixes §1.2. |
| `tool_execution_start` | `tool_started` | `toolCallId`→`call_id`; `toolName`→`tool`; `args.path`→`paths[0]`; `args.command`→`command` | |
| `tool_execution_update` | *(drop)* | — | 1,458 events, zero consumers. |
| `tool_execution_end` | `tool_completed` | `toolCallId`→`call_id`; `toolName`→`tool`; `isError`→`not ok`; `result.isError`→`not ok` | **Driver must inject `paths`** from a `call_id → args` map held since `tool_execution_start`. Pi's end event has no args. |
| `turn_end` | `usage{scope:"turn"}` | `message.usage.*`; `message.stopReason`→`stop_reason` | Cumulative — emit as `scope:"turn"` and never sum with `scope:"message"`. |
| `agent_end` | `turn_ended{status:"completed"}` | `willRetry` → `stop_reason` hint | |
| *(no event — process died)* | `turn_ended{status:"failed"}` | driver-synthesized from `_PlumbingError` (`scripts/adapters/pi_rpc_adapter.py:1268`) | |
| *(no event — `cancel.requested`)* | `turn_ended{status:"cancelled"}` | driver-synthesized (`scripts/adapters/pi_rpc_adapter.py:891-896`) | |
| `entry_appended`, `extension_ui_request`, `agent_settled` | *(drop)* | — | 10,787 events, zero consumers. |

### 5.2 cursor stream-json → canonical

| cursor event | canonical | field mapping | notes |
|---|---|---|---|
| `system`/`init` | `session_started` | `session_id`→`session_id` and `resume_token`; `model`→`model` | Same value serves `--resume` (`scripts/runtime/spike/cursor_cli_spike.py:77`). |
| *(process spawn)* | `turn_started` | driver mints `turn_id` | No cursor equivalent; one process = one turn. |
| `user` | *(drop)* | — | Prompt echo; GDDP already holds the prompt. |
| `thinking`/`delta`, `thinking`/`completed` | *(drop)* | — | No consumer. |
| `assistant` | `assistant_message` | `message.content[].text` → `text` | **Must dedupe**: partial + final both stream (§2.4). Emit once at turn end, or track and replace. |
| `tool_call`/`started` | `tool_started` | `call_id`→`call_id`; `<key>ToolCall` key stem → `tool`; `.args.path`→`paths[]`; `.args.command`→`command` | Tool name by suffix-strip of `ToolCall` (`scripts/runtime/spike/cursor_cli_spike.py:98`). |
| `tool_call`/`completed` | `tool_completed` | same as above, plus `.result` | `ok` derivation is **unverified**: only `result_keys: ["success"]` was observed on a successful read (`cursor_cli_spike_results.json:239-241`). No failing tool call was exercised. |
| `result`/`success` | `usage{scope:"turn"}` + `turn_ended{status:"completed"}` | `usage.inputTokens`→`input`; `outputTokens`→`output`; `cacheReadTokens`→`cache_read`; `cacheWriteTokens`→`cache_write`; `is_error`→`status`; `duration_ms`→`duration_ms`; `request_id`→`request_id` | Cursor has **no** per-message usage. Its only `usage` is `scope:"turn"`. |
| `result` with `is_error: true` | `turn_ended{status:"failed"}` | `result`→`error` | Subtype other than `success` unobserved. |
| *(no events at all, exit≠0)* | `turn_ended{status:"failed"}` | stderr tail → `error` | Required: `invalid_model` produced zero events (`cursor_cli_spike_results.json:47-53`). |
| *(SIGTERM/SIGKILL)* | `turn_ended{status:"cancelled"\|"failed"}` | driver-synthesized from returncode | `result_event: null` in both kill turns (`cursor_cli_spike_results.json:102, 155`). |

Asymmetries the canonical layer absorbs:

- pi gives per-message usage; cursor gives one terminal usage. The `scope` field
  keeps them from being summed together.
- pi's completion event lacks args; cursor's carries them. The `paths`-on-
  `tool_completed` contract (§4) puts the buffering burden in the pi driver,
  where the data already exists, rather than in every consumer.

---

## 6. Recommended placement

**Shared normalization module, thin per-transport drivers.**

```
scripts/adapters/executor_events.py     # NEW — ExecutorEvent, envelope,
                                        #   CONTENT_TOOLS / WRITE_TOOLS name
                                        #   vocabulary, spool writer + reader
scripts/adapters/events_pi_rpc.py       # NEW — dict -> ExecutorEvent, pure,
                                        #   holds the call_id->args map
scripts/adapters/events_cursor_cli.py   # NEW — dict -> ExecutorEvent, pure
scripts/runtime/context_coverage.py     # NEW — extract_read_paths +
                                        #   compute_turn_context_coverage,
                                        #   over ExecutorEvent only
```

Rationale, each grounded in something measured above:

1. **Drivers are pure and do no IO.** `_RpcClient._record`
   (`scripts/adapters/pi_rpc_adapter.py:1314`) already owns the write; the driver
   should be a `translate(raw_event) -> list[ExecutorEvent]` function so it is
   testable without a live harness — the pattern
   `scripts/adapters/test_pi_rpc_adapter.py:1028-1047` already uses for coverage.
2. **The name vocabulary must be shared, not per-driver.** Coverage's
   `_CONTENT_TOOLS` gate (`scripts/adapters/pi_rpc_adapter.py:504`) is a
   *semantic* claim about tool names. If each driver invents its own spelling,
   the gate silently stops matching on a new transport and coverage reports
   `none` for a session that read everything — a silent-zero failure, not a
   loud one.
3. **Coverage moves out of the pi adapter.** It is currently defined in
   `scripts/adapters/pi_rpc_adapter.py:497-650` — 150 lines of transport-agnostic
   measurement inside one transport's file. Moving it to
   `scripts/runtime/context_coverage.py` and having the adapter call it
   (`scripts/adapters/pi_rpc_adapter.py:932-935` is the only call site) makes
   `cursor_cli_adapter.py` a one-line reuse instead of a copy.
4. **The evaluator should call the same module.** `_tool_results` /
   `_successful_content_access` / `_rate_lane`
   (`scripts/runtime/verification/orchestrator.py:377-419`) are the same
   algorithm over the guard-extension trace shape
   (`scripts/runtime/verification/semantic/pi_harness/gddp_verifier_guard.ts:80-153`).
   If the guard emits canonical `tool_started`/`tool_completed`, one
   implementation serves both lanes and the duplicate rating disappears.
5. **`extract_actual_cached_tokens` shrinks to a canonical read.**
   `scripts/prompt_topology.py:205-295` is 90 lines of provider-shape sniffing
   across four vendors. Against canonical events it is
   `sum(e.cache_read for e in events if e.type == "usage" and e.scope == "message")`,
   with the vendor knowledge moved into the drivers where the vendor is known.
   The §1.2 over-count cannot recur, because `message_update` never becomes a
   canonical `usage` event.
6. **Keep the raw stream beside the canonical one.** Write
   `events.jsonl` (canonical) and `raw.jsonl` (verbatim harness output). The raw
   file preserves `tail -F` (`gddp-config/scripts/gddp.py:4690`) and forensic
   recovery; the canonical file is what code parses. Both are append-only, so
   the batch fan-out copy (`scripts/adapters/pi_rpc_adapter.py:874-883`) is
   unchanged.

---

## 7. Open decisions requiring cross-lane synthesis

### 7.1 Does `tool_completed` carry `paths`?
Recommended yes (§4). Cost: the pi driver must hold a `call_id → args` map for
the life of a turn (bounded — max 1,413 tool calls across 72 sessions, so tens
per turn). Benefit: every consumer becomes one-pass, and cursor's richer
completion event is used rather than discarded. The cursor-adapter lane should
confirm `call_id` is stable across `started`/`completed` beyond the single
observed pair (`cursor_cli_spike_results.json:232, 238` — same id, n=1).

### 7.2 Canonical tool-name table, with cursor's write/edit/bash shapes unverified
`read`/`grep` are the load-bearing names (coverage). Pi spells them `read`,
`grep`; cursor spells the read tool `readToolCall`. **No cursor write, edit,
grep, or shell tool call was ever observed** — the spike exercised read only and
says so (`cursor_cli_spike_results.json:7`). Per `AGENTS.md:6-13`, the mapping
for those must be measured before the table is written, not inferred from the
read case. Someone must run a cursor turn that writes a file and greps.

### 7.3 Canonical spool vs. raw spool, and who migrates
`gddp watch` and `gddp steer` live in a **different repo**
(`gddp-config/scripts/gddp.py:4386-4691`), and 72 existing spools hold raw pi
events. Decide: (a) canonical `events.jsonl` + `raw.jsonl` with a `gddp-config`
change to `_event_brief` to read canonical fields — fixes §1.3; (b) canonical in
a new `canonical.jsonl`, leaving `events.jsonl` raw — zero cross-repo change but
the watch surface stays detail-less; (c) reader shim that upconverts old raw
spools on read. This is the only decision that touches a repo outside this lane.
