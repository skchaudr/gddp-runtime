# Executor capability contract

Status: proposal / analysis. Read-only pass over the executor surface ahead of
`cursor_cli_adapter.py`. No code changed.

Scope: what GDDP code assumes about an executor today, which of those
assumptions are contract vs capability vs transport vs policy, and a concrete
capability structure + protocol sketch to keep the second transport from
becoming a second runtime.

Sources inspected: `scripts/adapters/executor_protocol.py`,
`scripts/adapters/pi_rpc_adapter.py`, `scripts/adapters/session_prompt.py`,
`scripts/runtime/heartbeat/dispatcher.py`, `scripts/runtime/heartbeat/runner.py`,
`scripts/runtime/heartbeat/reconciler.py`, `scripts/runtime/heartbeat/graph_reader.py`,
`scripts/prompt_topology.py`, `scripts/local_agent_executor.py`,
`scripts/runtime/spike/cursor_cli_spike.py`,
`scripts/runtime/spike/cursor_cli_spike_results.json`,
`scripts/runtime/spike/pi_rpc_persistent_spike_results.json`,
`scripts/adapters/test_executor_contract.py`, `scripts/adapters/test_pi_rpc_adapter.py`,
`scripts/adapters/test_pi_rpc_steer.py`, and the operator surface
`../gddp-config/scripts/gddp.py`.

---

## 1. Assumption inventory

Each item: what is assumed, the code that assumes it, and exactly one
classification.

### 1.1 Persistent process

**T1 — one long-lived process per project is the unit of execution.**
`dispatch()` does not start work; it enqueues into a per-project orchestrator
inbox and spawns the loop only if no live pid holds the project.

```207:219:scripts/adapters/pi_rpc_adapter.py
            with _orchestrator_lock(orchestrator_dir):
                live_pid = _read_pid(orchestrator_dir / "pid")
                if live_pid is not None and _pid_is_running(live_pid):
                    # A session for this project is already live (idle or
                    # mid-turn) — queue behind it instead of spawning a
                    # second `pi` process for the same project.
                    _enqueue_attempt(orchestrator_dir, attempt_dir)
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL.** Nothing outside the
adapter reads `orchestrator_dir`, the inbox, or the flock.

**T2 — session state is derived from pid liveness.**

```388:400:scripts/adapters/pi_rpc_adapter.py
    pid = _read_pid(attempt_dir / "pid")
    if pid is not None and _pid_is_running(pid):
        return SessionStatus(state="running")
    supervisor_pid = _read_pid(attempt_dir / "supervisor.pid")
    if supervisor_pid is not None and _pid_is_running(supervisor_pid):
        return SessionStatus(state="dispatched")
    return SessionStatus(
        state="failed",
        error="pi_rpc exited without durable exit state",
    )
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL.** A per-turn subprocess
transport has no equivalent long-lived pid; the states it must produce are
contract (R3), the pid mechanism is not.

**T3 — the idle grace assumes a session outlives a working day.**

```69:scripts/adapters/pi_rpc_adapter.py
_DEFAULT_IDLE_TIMEOUT_S = 43200.0  # 12h
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL.**

**R1 — a session must survive the process that created it, and status/cancel
must work from a freshly constructed adapter.** The reconciler and the cancel
path both rebuild adapters from scratch:

```471:474:scripts/runtime/heartbeat/reconciler.py
    if adapter is None:
        adapter = adapter_cls(repo=job_row["repo"] or "")
    session_ref = SessionRef(executor=executor, session_id=session_id)
```

```216:219:scripts/runtime/heartbeat/dispatcher.py
        adapter = _build_adapter(adapter_cls, session_ref.executor, repo, None)
        accepted = adapter.cancel(session_ref)
    except Exception as exc:
        return False, f"late session cancellation failed: {exc}; remote may continue"
```

Classification: **REQUIRED EXECUTOR CONTRACT.** Durable, process-independent
session identity is the load-bearing property — not persistence of a process.

### 1.2 Session exists

**R2 — every direct dispatch yields a `SessionRef`; its absence means
"mediated".** Both dispatch recorders branch on exactly this:

```660:676:scripts/runtime/heartbeat/runner.py
                finalized = finalize_executor_session_dispatch(
                    con,
                    ...
                    state="dispatched",
                    executor=outcome.session_ref.executor,
```

(mirrored at `scripts/runtime/heartbeat/reconciler.py:1104-1122` and `:1456-1474`).

Classification: **REQUIRED EXECUTOR CONTRACT.**

**R3 — the status vocabulary is closed and fail-closed.**

```158:172:scripts/adapters/executor_protocol.py
    state: Literal[
        "dispatched",
        "running",
        # Executor asked a question and is waiting on an answer. Distinct from
        # needs_operator: this one is answerable by machine via adapter.reply().
        "awaiting_reply",
        "needs_operator",
        "completed",
        "crashed",
        "failed",
        "missing",
        "poll_error",
    ]
```

Classification: **REQUIRED EXECUTOR CONTRACT.** Note `awaiting_reply` is a
required enum member describing an optional capability (see O1/O2).

**T4 — `session_id` is a filesystem path component.**

```342:349:scripts/adapters/pi_rpc_adapter.py
        session_id = session_ref.session_id
        if (
            not session_id
            or session_id in {".", ".."}
            or Path(session_id).name != session_id
        ):
            return None
        return self.spool_root / session_id
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL.** (Cursor's session ids are
UUIDs — `cursor_cli_spike_results.json:41` — so they happen to satisfy it, but
the guard belongs to the adapter, not the contract.)

**R4 — collect returns a commit-ref handoff that the reconciler verifies
against git.**

```864:879:scripts/runtime/heartbeat/reconciler.py
        if getattr(patch_result, "result_commit_sha", None):
            result_sha = patch_result.result_commit_sha
            result_ref = getattr(patch_result, "result_ref", None)
            if not result_ref:
                raise RuntimeError("commit-ref handoff missing result_ref")
            resolved = _resolve_ref(repo_path, result_ref)
            if resolved != result_sha:
                ...
            if not _is_ancestor(repo_path, base_commit, result_sha):
```

The handoff schema itself is `gddp.local_result.v1`
(`scripts/local_agent_executor.py:19`, `:163-168`).

Classification: **REQUIRED EXECUTOR CONTRACT.**

**R5 — a durable terminal exit record must exist, or the attempt is a plumbing
failure.** Absence is signalled by a specific error string
(`scripts/adapters/pi_rpc_adapter.py:396-400`) that the reconciler matches:

```979:989:scripts/runtime/heartbeat/reconciler.py
_PLUMBING_PATTERNS = (
    "exited without durable exit state",
    "invalid local subprocess exit state",
)


def classify_plumbing_failure(error: str | None) -> bool:
    """True when the session failed before the executor could report — infra
    noise, not evidence about the node's work."""
    text = (error or "").lower()
    return any(pattern in text for pattern in _PLUMBING_PATTERNS)
```

Classification: **REQUIRED EXECUTOR CONTRACT** (the durable-exit obligation).
The retry-budget consequence is P1.

### 1.3 Steering

**O3 — mid-turn steering exists, is file-driven, and is not in the protocol at
all.** There is no `steer` member on `ExecutorAdapter`
(`scripts/adapters/executor_protocol.py:263-320`). Delivery lives inside the pi
turn loop:

```779:796:scripts/adapters/pi_rpc_adapter.py
        # kind="steer": native RPC steer — delivered into the running turn
        # (accepted mid-turn, consumed before agent_end). kind="prompt":
        # used after agent_end while idle; starts a follow-up turn the
        # caller waits on. A bare "prompt" mid-turn is REJECTED by pi —
        # never use it for mid-turn delivery.
        for attempt_dir, _packet, _raw in active:
            ...
                    resp = client.send(
                        {
                            "type": kind,
                            "message": f"[operator steer for {attempt_dir.name}] {msg}",
                        },
```

Classification: **OPTIONAL CAPABILITY** — currently unmodeled, so no adapter
can advertise or refuse it.

**T5 — the operator surface writes directly into the pi spool layout.**
`gddp steer` appends to `steer.jsonl` inside an attempt dir it discovered by
scanning the spool (`../gddp-config/scripts/gddp.py:4937-4960`), and closes with
`"delivered on the supervisor's next read cycle (needs the steer-aware runtime)"`
(`:4960`). The parser contract is tested independently of any adapter
(`scripts/adapters/test_pi_rpc_steer.py:11`).

Classification: **TRANSPORT IMPLEMENTATION DETAIL** that has already leaked
into an operator-facing command.

**P7 — steering is only offered to a running attempt.**
`../gddp-config/scripts/gddp.py:4944-4947` refuses any other state.
Classification: **GDDP POLICY.**

**T6 — steer follow-up turns are bounded by an adapter constant.**
`_MAX_STEER_FOLLOWUPS = 10` (`scripts/adapters/pi_rpc_adapter.py:1329`), consumed
at `:852-859`. Classification: **TRANSPORT IMPLEMENTATION DETAIL.**

### 1.4 Reply / conversation

**O1 — `reply()` is the one existing capability negotiation, and it is
`hasattr`.**

```321:326:scripts/adapters/executor_protocol.py
    # Optional capability, probed with hasattr rather than declared above:
    # adding it to this Protocol would break runtime_checkable isinstance
    # checks for adapters that cannot hold a conversation at all.
    #
    #   def reply(self, session_ref: SessionRef, message: str) -> bool:
    #       """Answer a session parked in awaiting_reply."""
```

```1194:1205:scripts/runtime/heartbeat/reconciler.py
    if current_state == "awaiting_reply" or not hasattr(adapter, "reply"):
        _handle_needs_operator(
            con,
            session_db_id,
            job_id,
            "executor still asking after standing reply"
            if current_state == "awaiting_reply"
            else "executor asked a question but adapter cannot reply",
        )
        return

    if not adapter.reply(session_ref, _PROCEED_REPLY):
```

Classification: **OPTIONAL CAPABILITY.** The degrade path (escalate to human)
is already correct and is the template for every other optional capability.

**O2 — producing `awaiting_reply` at all.** Only `jules_api` maps a provider
state onto it (`scripts/adapters/test_executor_contract.py:365`); pi_rpc never
emits it (`scripts/adapters/pi_rpc_adapter.py:352-400`).
Classification: **OPTIONAL CAPABILITY.**

**P2 — the standing answer, and escalate-after-one-try.**

```1178:1187:scripts/runtime/heartbeat/reconciler.py
_PROCEED_REPLY = (
    "Proceed as specified in the node packet you were given; it carries full "
    "authority and no further approval is required. Do not ask whether to "
    ...
)
```

Classification: **GDDP POLICY.**

### 1.5 Resume

**T7 — resume is a constructor argument, not a dispatch decision.**

```132:133:scripts/adapters/pi_rpc_adapter.py
        resume_session_file: str | Path | None = None,
    ) -> None:
```

threaded into `command.json` (`:195-199`) and finally `--session`
(`:1042-1043`). The dispatcher never supplies it:

```198:208:scripts/runtime/heartbeat/dispatcher.py
def _build_adapter(adapter_cls, executor: str, repo: str, repo_path: str | None):
    """Give only local transports the checkout they execute inside."""
    kwargs: dict[str, object] = {"repo": repo}
    if executor in _LOCAL_TRANSPORT_EXECUTORS and repo_path:
        kwargs["cwd"] = repo_path
    if executor == "pi_rpc":
        # Named here so the orchestrator model is visible at the call site
        # rather than resolved by a default inside the adapter. Unset env
        # means the adapter raises, which surfaces as a configuration error.
        kwargs["model"] = os.environ.get("GDDP_PI_RPC_MODEL")
    return adapter_cls(**kwargs)
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL** today. It is unreachable
from the runtime: no caller passes `resume_session_file`.

**T8 — the resume token is captured and then never read.** `get_state`'s
`sessionFile` is persisted per attempt:

```1126:1127:scripts/adapters/pi_rpc_adapter.py
                if session_file_value:
                    _atomic_write(attempt_dir / "session_file", str(session_file_value))
```

Grep finds no reader of `session_file` outside `pi_rpc_adapter.py` and its
tests. Classification: **TRANSPORT IMPLEMENTATION DETAIL** (dead evidence).

**T9 — continuity is currently achieved by process persistence, not by a
token.** The module docstring is explicit:

```7:12:scripts/adapters/pi_rpc_adapter.py
Fork A (2026-08-16): one long-lived `pi --mode rpc` process is spawned PER
PROJECT, not per node — that process is the project's single executor.
dispatch() drops each NodePacket into that project's inbox.
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL.**

**P8 — "fresh turn = default, resume = explicit policy decision" has no
implementation.** There is no continuity field on `NodePacket`
(`scripts/adapters/executor_protocol.py:51-107`), no continuity column written
by `insert_executor_session` / `finalize_executor_session_dispatch`
(`scripts/runtime/heartbeat/state_recorder.py:205-235`, `:351-375`), and no
policy call site. Classification: **GDDP POLICY** (missing).

### 1.6 Event shape

**T10 — `agent_end` is the turn boundary.**

```1274:1282:scripts/adapters/pi_rpc_adapter.py
            et = evt.get("type") or evt.get("event")
            # Spike: agent_end is the durable turn boundary.
            if et == "agent_end" or (
                isinstance(evt.get("event"), dict)
                and evt["event"].get("type") == "agent_end"
            ):
                return
            # Nested shapes from some builds.
            if evt.get("type") == "agent_end":
                return
```

Cursor's analogue is the terminal `result` event
(`scripts/runtime/spike/cursor_cli_spike.py:112-113`;
`cursor_cli_spike_results.json:26-40`), and its absence after a kill
(`cursor_cli_spike_results.json:99-107`, `:143-160`, `result_event: null`) maps
cleanly onto R5's plumbing path. Classification: **TRANSPORT IMPLEMENTATION
DETAIL**; "an observed turn boundary exists" is R5.

**T11 — the tool-call event schema.**

```512:518:scripts/adapters/pi_rpc_adapter.py
    (``jobs/local-subprocess-spool/*/events.jsonl``), which carry the pair:

        {"type":"tool_execution_start","toolCallId":"call_..","toolName":"read",
         "args":{"path":"/abs/or/rel/path"}}
        {"type":"tool_execution_end","toolCallId":"call_..","toolName":"read",
         "result":{"content":[...]},"isError":false}
```

Cursor's shape is different in every field name:
`tool_call/started` + `tool_call/completed`, body under
`tool_call.readToolCall`, id at `call_id`, outcome at `result.success`
(`cursor_cli_spike_results.json:229-245`;
`scripts/runtime/spike/cursor_cli_spike.py:96-107`).
Classification: **TRANSPORT IMPLEMENTATION DETAIL.**

**P3 — the context-coverage rating computed from those events is GDDP's
metric.**

```601:613:scripts/adapters/pi_rpc_adapter.py
    read_paths = extract_read_paths(events, base=base)
    accessed = read_paths & all_offered
    accessed_docs = read_paths & offered_docs
    accessed_neighbors = read_paths & offered_neighbors

    if not accessed:
        rating = "none"
    elif not accessed_docs:
        rating = "low"
    elif not accessed_neighbors and offered_neighbors:
        rating = "medium"
    else:
        rating = "high"
```

Classification: **GDDP POLICY**, currently implemented inside a transport file
against one provider's event names.

**T12 — `events.jsonl` in the attempt dir is a de-facto cross-component
contract.** Written by the RPC client (`scripts/adapters/pi_rpc_adapter.py:1314-1319`),
re-read for usage (`:906-917`), copied across batch members (`:874-883`), and
consumed by the operator CLI for liveness, the "live stream" hint, and recent
events (`../gddp-config/scripts/gddp.py:4439`, `:4462`, `:4530-4531`, `:4911`).
Classification: **TRANSPORT IMPLEMENTATION DETAIL** — already load-bearing
outside the transport.

### 1.7 Usage reporting

**O4 — usage extraction is keyed to pi's event and field names.**

```205:220:scripts/prompt_topology.py
def extract_actual_cached_tokens(events: Sequence[dict]) -> int | None:
    """Extract actual cached input tokens reported across a sequence of RPC/LLM events.

    Inspects common provider usage formats:
      - Pi / openai-codex / xai (VERIFIED against live events.jsonl):
        message.usage.cacheRead  (camelCase, on type=message_end events)
      - Anthropic / OpenRouter: usage.cache_read_input_tokens
      - OpenAI API: usage.prompt_tokens_details.cached_tokens
      - Generic: usage.cached_tokens or usage.cache_read_tokens
```

```254:254:scripts/prompt_topology.py
    cache_keys = ("cacheRead", "cache_read_input_tokens", "cached_tokens", "cache_read_tokens", "prompt_tokens_details")
```

Cursor reports usage once, on the terminal `result` event, as
`cacheReadTokens` / `cacheWriteTokens` / `inputTokens` / `outputTokens`
(`cursor_cli_spike_results.json:34-39`). `cacheReadTokens` is not in
`cache_keys`, so a cursor stream returns `None` silently — no error, no report.
Classification: **OPTIONAL CAPABILITY** with a normalization gap.

**P4 — the prompt-cache report and coverage artifact are node evidence.**

```944:950:scripts/adapters/pi_rpc_adapter.py
        # Attach the structural cache report (now with actual_cached_tokens if present)
        # so it flows through collect() -> the operator loop as part of the node's evidence.
        if report_path.exists():
            try:
                handoff["prompt_cache_report"] = json.loads(report_path.read_text())
```

Classification: **GDDP POLICY** (what counts as evidence), delivered through a
transport-private file.

### 1.8 Cancellation

**R6 — `cancel()` exists on every adapter and returns a bool.**

```283:285:scripts/adapters/executor_protocol.py
    def cancel(self, session_ref: SessionRef) -> bool:
        """Best-effort cancellation. Not all executors support this."""
        ...
```

Classification: **REQUIRED EXECUTOR CONTRACT** (the method), with the *effect*
optional (O5).

**T13 — pi cancels by marker file and deliberately never signals.**

```326:337:scripts/adapters/pi_rpc_adapter.py
            _atomic_write(attempt_dir / "cancel.requested", "")
        except OSError:
            return False
        # That is the whole action. Under batch turns (fork A item 4) this
        # attempt's `pid` file may equal the SAME shared pi process running
        # up to N-1 other packets in the same turn right now — there is no
        # per-packet abort in the RPC protocol, so we never signal or kill
        # that process here. _run_one_turn checks this marker for THIS
        # attempt_dir twice: once before the packet is ever sent to pi
        # (skips it, never sends it to pi) and once more right before
        # persisting its result (skips persist). The session worktree and
        # every other packet stay up either way.
```

Cursor's mechanism is the opposite: signal the per-turn subprocess. The spike
measured SIGTERM → death in 1.16s and SIGKILL → 0.02s, with the session still
resumable afterwards (`cursor_cli_spike_results.json:156`, `:103`,
`sigterm_mid_turn_resume_check` / `sigkill_mid_turn_resume_check`).
Classification: **TRANSPORT IMPLEMENTATION DETAIL.**

**P5 — the truthful-outcome text is centrally owned.**

```211:223:scripts/runtime/heartbeat/dispatcher.py
def cancel_remote_session(session_ref: SessionRef, repo: str) -> tuple[bool, str]:
    """Best-effort cancel a known remote session with truthful outcome text."""
    ...
    if accepted:
        return True, "late session cancellation accepted"
    return False, "late session cancellation was not accepted; remote may continue"
```

Classification: **GDDP POLICY.** It is currently untruthful for pi: `cancel()`
returns `False` for an already-terminal session
(`scripts/adapters/pi_rpc_adapter.py:320-323`), which renders as "remote may
continue" for a session that has already exited.

### 1.9 Multi-node engagement

**R7 — `supports_engagement()` is a required protocol member with a defaults
mixin, a getattr probe, and a hard-error path.**

```287:289:scripts/adapters/executor_protocol.py
    def supports_engagement(self) -> bool:
        """Whether this adapter can dispatch multiple node attempts together."""
        ...
```

```88:91:scripts/runtime/heartbeat/dispatcher.py
        supports_engagement = getattr(
            adapter, "supports_engagement", lambda: False
        )
        return bool(supports_engagement())
```

```153:158:scripts/runtime/heartbeat/dispatcher.py
        if not adapter.supports_engagement():
            return EngagementDispatchResult(
                success=False,
                error=f"executor {executor} does not support engagements",
            )
```

Classification: **REQUIRED EXECUTOR CONTRACT** (declaration) — this is the
existing precedent to generalize. The *effect* is **OPTIONAL CAPABILITY** (O6).

### 1.10 Registration

**P6 — four surfaces must agree before an executor exists.**
`dispatcher.ADAPTERS` (`scripts/runtime/heartbeat/dispatcher.py:38-43`),
`_LOCAL_TRANSPORT_EXECUTORS` (`:48-50`),
`graph_reader.DEFAULT_EXECUTION_MODE_ALLOWLIST`
(`scripts/runtime/heartbeat/graph_reader.py:21-36`), and an exact-equality test
(`scripts/adapters/test_executor_contract.py:285-292`).
Classification: **GDDP POLICY.**

**T14 — per-executor config branching already lives in the dispatcher.**
The `if executor == "pi_rpc"` model branch at
`scripts/runtime/heartbeat/dispatcher.py:203-208`.
Classification: **TRANSPORT IMPLEMENTATION DETAIL** in the wrong file.

### 1.11 Prompt assembly

**O7 — the pi preamble assumes the harness has native subagents.**

```82:89:scripts/adapters/pi_rpc_adapter.py
    "2. Dispatch worker subagents to perform the actual execution: up to 5 concurrent, "
    "model xai/grok-4.6 via the subagent tool's model parameter. Workers "
    "investigate, build, and measure; you do not.\n"
    "3. While work is in flight, dispatch ONE watcher subagent (model "
    "deepseek/deepseek-v4-flash) that actively polls state with tools and "
    "reports changes. Never spend your own turns on sleep loops or polling "
    "scripts.\n"
```

backed by the tool allowlist `_DEFAULT_TOOLS = "read,bash,edit,write,grep,find,ls,subagent"`
(`scripts/adapters/pi_rpc_adapter.py:62`). Classification: **OPTIONAL
CAPABILITY** (`native_subagents`) currently written as if it were GDDP
execution semantics.

**P9 — the four-zone prompt topology and its prefix-cache stability rule are
GDDP's.**

```653:665:scripts/adapters/pi_rpc_adapter.py
def build_executor_turn_prompt(*, worktree: Path, packets: Sequence[dict]) -> TurnPrompt:
    """Four-zone TurnPrompt for one executor turn.

    protocol  = _PACKET_PREAMBLE (nearly immutable, shared by every turn)
    project   = canonical context pointers for this node's project (paths
               only, graph-stable — see build_project_zone); empty when the
               packet carries none
    node      = stable node JSON blocks (retry-stable per node)
    attempt   = volatile envelopes (attempt ids + worktree) + turn note
```

The zone split itself is already shared and transport-neutral
(`scripts/adapters/session_prompt.py:44-67`).
Classification: **GDDP POLICY.**

**R8 — pointers are resolved once at dispatch and must be byte-stable across
retries.**

```240:247:scripts/runtime/heartbeat/dispatcher.py
    """Return (unlocks, context_pointers) for one job.

    Pointers are built exactly once here, at dispatch, so every retry of the
    resulting packet renders a byte-identical project prompt zone. Both graph
    reads are best-effort: without a reachable gddp-config checkout or a local
    checkout there is nothing to point at, and dispatch must still proceed
    with an empty project zone rather than fail the job.
    """
```

Classification: **REQUIRED EXECUTOR CONTRACT** (packet-side; every adapter must
render pointers as paths, never contents).

### 1.12 Worktree ownership

**T15 — the pi orchestrator creates one worktree per session and holds it.**

```1099:1105:scripts/adapters/pi_rpc_adapter.py
                try:
                    session_worktree = create_worktree(
                        repo, str(packet["expected_base_commit_sha"])
                    )
                    record_worktree_correlation(session_worktree, packet)
                    _atomic_write(orchestrator_dir / "worktree_path", str(session_worktree))
```

Classification: **TRANSPORT IMPLEMENTATION DETAIL** — but see §5, because a
per-turn transport has no session to hang a worktree on.

---

## 2. Classification summary

| Class | Count | Items |
|---|---|---|
| REQUIRED EXECUTOR CONTRACT | 8 | R1 process-independent session identity · R2 SessionRef on direct dispatch · R3 closed status vocabulary · R4 verifiable commit-ref handoff · R5 durable terminal exit record · R6 `cancel()` exists · R7 capability declaration exists (`supports_engagement` precedent) · R8 dispatch-time byte-stable pointers |
| OPTIONAL CAPABILITY | 7 | O1 `reply()` · O2 emits `awaiting_reply` · O3 mid-turn steering · O4 usage reporting · O5 cancellation *effect* · O6 engagement *effect* · O7 native subagents |
| TRANSPORT IMPLEMENTATION DETAIL | 15 | T1 per-project process · T2 pid-derived status · T3 idle grace · T4 session_id as path · T5 spool-coupled steer surface · T6 steer follow-up bound · T7 resume as ctor arg · T8 captured-but-unread session_file · T9 continuity via process · T10 `agent_end` boundary · T11 tool-call schema · T12 `events.jsonl` layout · T13 marker-file cancel · T14 pi model branch in dispatcher · T15 session-owned worktree |
| GDDP POLICY | 9 | P1 plumbing vs work retry budget · P2 standing reply + escalate-once · P3 context-coverage rating · P4 cache report as node evidence · P5 truthful cancellation text · P6 executor registration surfaces · P7 steer only while running · P8 fresh-default / explicit resume (unimplemented) · P9 four-zone prompt topology |

Total: 39 assumptions. Of the 15 transport details, **4 have already leaked out
of the transport** (T5 and T12 into the operator CLI, T11/T10 into GDDP's
coverage and usage policy, T14 into the dispatcher). Those four are the
proliferation surface.

---

## 3. Proposed `ExecutorCapabilities`

Placement: `scripts/adapters/executor_protocol.py`, beside `SessionStatus`.
Declaration must be **pure, cheap, and callable without a live session** —
`executor_preflight_error` runs it before a job is reserved
(`scripts/runtime/heartbeat/dispatcher.py:57-75`).

```python
CancellationKind = Literal["none", "cooperative", "preemptive"]
ResumeKind = Literal["none", "token", "session_file"]

@dataclass(frozen=True)
class ExecutorCapabilities:
    executor: str

    # cold_turn is required of every adapter and therefore not a field:
    # an adapter that cannot run one turn from a NodePacket is not an adapter.

    streaming_events: bool = False
    # Adapter writes normalized ExecutorEvent records for the attempt while the
    # turn runs. False means observability is terminal-only (collect() and
    # status() are the only signals) and `gddp watch` must say so.

    partial_text: bool = False
    # Assistant text is observable before the turn boundary. Implies
    # streaming_events.

    cancellation: CancellationKind = "none"
    #   "none"        — cancel() is a no-op returning False.
    #   "cooperative" — cancel is honored at the next packet/turn boundary;
    #                   in-flight work continues. (pi_rpc marker file)
    #   "preemptive"  — cancel stops the in-flight turn. (signal to subprocess)
    # This is what makes cancel_remote_session's text truthful.

    resume: ResumeKind = "none"
    #   "token"        — opaque string resumes prior context (cursor --resume)
    #   "session_file" — a path on the executor host resumes it (pi --session)
    # Declares only that resume is POSSIBLE. Whether to resume is P8, decided
    # by the runtime, never by the adapter.

    midturn_steering: bool = False
    # Adapter accepts steer() while status() == "running" and the message
    # reaches the same turn. False must be visible to `gddp steer`.

    usage_reporting: bool = False
    # Adapter emits normalized TurnUsage (cached/input/output tokens) for each
    # turn, regardless of the provider's field names.

    native_subagents: bool = False
    # Harness can fan work out to child agents it manages itself. Gates the
    # orchestrator-shaped preamble (O7).

    structured_tool_calls: bool = False
    # Adapter normalizes tool calls into (tool, args, ok) so context coverage
    # (P3) can be computed without provider event names.

    engagement: bool = False
    # Existing supports_engagement(), folded in. supports_engagement() stays as
    # a thin shim returning this field so the current call sites keep working.

    reply: bool = False
    # Existing hasattr(adapter, "reply") probe, made declarative.

    def supports(self, name: str) -> bool:
        """True for bool fields; True for graded fields that are not the
        zero value ("none"). Single predicate for policy call sites."""
```

Semantics rules:

1. Every field defaults to the *least capable* value. A new adapter that
   declares nothing gets a correct, degraded contract.
2. Declaring a capability is a promise about the **normalized** surface, not
   about the provider. `structured_tool_calls=True` means the adapter emits
   GDDP-shaped tool records, not that the provider happens to have a tool
   event.
3. Capability declaration never touches the network, spawns a process, or
   reads a session. It may read env/config, because preflight already does
   (`scripts/runtime/heartbeat/dispatcher.py:66-74`).

---

## 4. Capability matrix

| Capability | `pi_rpc` | evidence | `cursor_cli` (proposed) | evidence |
|---|---|---|---|---|
| cold_turn (required) | yes | `pi_rpc_adapter.py:166-259`, `:1120-1139` | yes | `cursor_cli_spike_results.json:12-45` (exit 0, session_id, `result/success`) |
| streaming_events | yes | `pi_rpc_adapter.py:1314-1319` (`events.jsonl`) | yes | `--output-format stream-json`, `cursor_cli_spike.py:70-79` |
| partial_text | yes | `message_update` bursts, `pi_rpc_persistent_spike_results.json:45-71` | yes | `--stream-partial-output` (`cursor_cli_spike.py:73`); `thinking/delta`, `assistant` counts at `cursor_cli_spike_results.json:14-21` |
| cancellation | **cooperative** | `pi_rpc_adapter.py:326-337` — marker only, never signals; honored at packet boundary | **preemptive** | SIGTERM → death 1.16s (`cursor_cli_spike_results.json:156`), SIGKILL → 0.02s (`:103`); session survives (`:109-142`, `:162-195`) |
| resume | **session_file** (unreachable) | `pi_rpc_adapter.py:132`, `:1042-1043`; no caller passes it (`dispatcher.py:198-208`) | **token** | `--resume <session_id>` (`cursor_cli_spike.py:77-78`); token recall proven cross-process (`cursor_cli_spike_results.json:57-91`) |
| midturn_steering | yes | native RPC `{"type":"steer"}` accepted mid-turn, `pi_rpc_adapter.py:779-806` | **no** | per-turn subprocess; nothing in `cursor_cli_spike.py` provides an in-flight input channel |
| usage_reporting | yes | `message.usage.cacheRead` on `message_end`, `prompt_topology.py:205-249` | yes, **different keys** | `usage.cacheReadTokens/cacheWriteTokens/inputTokens/outputTokens` on the terminal `result` event (`cursor_cli_spike_results.json:34-39`); not in `prompt_topology.py:254` |
| native_subagents | yes | `subagent` in `_DEFAULT_TOOLS` (`pi_rpc_adapter.py:62`), preamble steps 2-5 (`:82-98`) | **no** (unproven) | not exercised by the spike; no subagent tool observed in `cursor_cli_spike_results.json` |
| structured_tool_calls | yes | `tool_execution_start`/`end` with `toolName`/`args.path`/`isError` (`pi_rpc_adapter.py:512-518`) | yes | `tool_call/started`+`completed`, `readToolCall.args.path`, `call_id`, `result.success` (`cursor_cli_spike_results.json:229-245`) |
| engagement | **no** | `PiRpcAdapter` defines no `supports_engagement` (whole class, `pi_rpc_adapter.py:116-349`) | no | per-turn subprocess, one packet per turn |
| reply | no | no `reply` on `PiRpcAdapter` | no | a "reply" is just a resumed turn; use `resume` |
| turn boundary | `agent_end` | `pi_rpc_adapter.py:1274-1282` | `result` event | `cursor_cli_spike.py:112-113`; null after kill (`cursor_cli_spike_results.json:102`, `:155`) |
| failure surface | non-zero exit + `exit.json` | `pi_rpc_adapter.py:364-386` | exit 1 + stderr model list, no `result` event | `cursor_cli_spike_results.json:46-57` (`invalid_model`) |

Unproven for cursor, carried forward from the spike's own risk list
(`cursor_cli_spike_results.json:4-9`): resume durability beyond one session,
provider/API failure classification, and non-read tool variants.

---

## 5. Protocol sketch

Doc-only. Signatures show how capabilities are declared, negotiated, and how an
unsupported call behaves.

### 5.1 Declaration (adapter side)

```python
class PiRpcAdapter:
    executor_name = "pi_rpc"

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            executor="pi_rpc",
            streaming_events=True,
            partial_text=True,
            cancellation="cooperative",
            resume="session_file",
            midturn_steering=True,
            usage_reporting=True,
            native_subagents=True,
            structured_tool_calls=True,
        )

    # supports_engagement() becomes a shim so existing call sites are untouched:
    def supports_engagement(self) -> bool:
        return self.capabilities().engagement


class CursorCliAdapter:
    executor_name = "cursor_cli"

    def capabilities(self) -> ExecutorCapabilities:
        return ExecutorCapabilities(
            executor="cursor_cli",
            streaming_events=True,
            partial_text=True,
            cancellation="preemptive",
            resume="token",
            usage_reporting=True,
            structured_tool_calls=True,
        )
```

### 5.2 Continuity — capability vs policy, kept separate

```python
@dataclass(frozen=True)
class Continuity:
    """The runtime's continuity decision for ONE dispatch. Packet-scoped."""
    mode: Literal["fresh", "resume"]
    token: str | None = None   # opaque to GDDP; adapter interprets it
    reason: str = ""           # recorded on the dispatch receipt

FRESH = Continuity(mode="fresh")
```

```python
def dispatch(
    self, packet: NodePacket, *, continuity: Continuity = FRESH
) -> DispatchResult: ...
```

`continuity` defaults to `FRESH` at the signature, so "fresh turn = DEFAULT" is
structural, not a convention. The token lives on the dispatch call and is
persisted per attempt beside `session_id`; it never becomes ambient adapter
state (which is what `resume_session_file` is today,
`scripts/adapters/pi_rpc_adapter.py:132`).

Policy lives outside the adapter:

```python
# scripts/runtime/heartbeat/continuity_policy.py (proposed, new)
def choose_continuity(
    job: Mapping[str, object],
    caps: ExecutorCapabilities,
    prior_sessions: Sequence[Mapping[str, object]],
) -> Continuity:
    """Return FRESH unless a named policy applies AND caps.resume != 'none'."""
```

### 5.3 Negotiation (dispatcher side)

```python
# scripts/runtime/heartbeat/dispatcher.py
def executor_capabilities(
    executor: str, repo: str, repo_path: str | None = None
) -> ExecutorCapabilities:
    """Build the adapter and return its declaration. Preflight-safe."""

def executor_supports_engagement(executor, repo, repo_path=None) -> bool:
    return executor_capabilities(executor, repo, repo_path).engagement
```

`executor_preflight_error` gains one check: the adapter must declare
capabilities and must satisfy `isinstance(adapter, ExecutorAdapter)` — a gate
`PiRpcAdapter` does not pass today (§6).

Runner caching stays as-is; it already caches per executor name
(`scripts/runtime/heartbeat/runner.py:579-585`) — the cached value becomes the
whole `ExecutorCapabilities` instead of one bool.

### 5.4 Behavior on an unsupported capability

Three tiers, chosen so a downgrade is never silent and never invisible in the
receipt.

**Tier 1 — lifecycle capability requested at dispatch: HARD ERROR.**
`resume` and `engagement` change what the executor is given. A silent
`resume → fresh` substitution produces a receipt that claims continuity the
turn never had.

```python
class CapabilityUnsupported(RuntimeError):
    """Raised when a call requires a capability the adapter did not declare."""
    capability: str
    executor: str
```

```python
# adapter side, first line of dispatch()
if continuity.mode == "resume" and self.capabilities().resume == "none":
    raise CapabilityUnsupported("resume", self.executor_name)
```

The runtime is responsible for not asking: `choose_continuity` receives `caps`
and cannot return `mode="resume"` for a `resume="none"` executor. The exception
is a bug-catcher, not a control-flow path. Precedent already in the tree:
`dispatch_engagement` refuses with an error result rather than degrading
(`scripts/runtime/heartbeat/dispatcher.py:153-158`), and the engagement mixin
raises `NotImplementedError`
(`scripts/adapters/executor_protocol.py:232`, `:235`).

**Tier 2 — interaction capability: TRUTHFUL NO-OP, never an exception.**
`steer()` and `reply()` return `False` when undeclared. The caller must surface
the refusal:

```python
def steer(self, session_ref: SessionRef, message: str) -> bool:
    """Deliver an operator message into a running turn.
    Returns False when caps.midturn_steering is False — the message is NOT
    queued, NOT deferred, and the operator surface must say so."""
```

This mirrors the existing `reply` degrade, which routes to a human rather than
pretending (`scripts/runtime/heartbeat/reconciler.py:1194-1202`). It fixes
`gddp steer`'s current unconditional `"steer queued for …"`
(`../gddp-config/scripts/gddp.py:4957-4960`), which would lie for `cursor_cli`.

**Tier 3 — observational capability: ABSENT EVIDENCE, not an error.**
`usage_reporting=False` or `structured_tool_calls=False` means the artifact is
not written at all — never written empty, never written with a fabricated
zero. This matches the existing coverage rule, which returns `None` rather than
a misleading `"none"` rating when nothing was offered
(`scripts/adapters/pi_rpc_adapter.py:578-581`).

**`cancel()` keeps its bool but gains truthful text from the declared kind:**

```python
def cancel_remote_session(session_ref, repo) -> tuple[bool, str]:
    # caps.cancellation == "preemptive"  -> "session terminated"
    # caps.cancellation == "cooperative" -> "cancellation queued; the in-flight
    #                                        turn continues to its boundary"
    # caps.cancellation == "none"        -> "executor cannot cancel; remote continues"
```

and `cancel()` should distinguish "already terminal" from "refused" so the
already-exited case stops rendering as "remote may continue"
(`scripts/adapters/pi_rpc_adapter.py:320-323` →
`scripts/runtime/heartbeat/dispatcher.py:223`).

### 5.5 Normalization boundary

The thin driver each adapter must satisfy, so P3/P4 stop living in
`pi_rpc_adapter.py`:

```python
@dataclass(frozen=True)
class ExecutorEvent:
    kind: Literal["turn_start", "text", "tool_start", "tool_end",
                  "usage", "turn_end", "error"]
    tool: str | None = None
    path: str | None = None
    ok: bool | None = None
    call_id: str | None = None
    raw: Mapping[str, object] | None = None   # provider event, unmodified

@dataclass(frozen=True)
class TurnUsage:
    cached_input_tokens: int | None
    input_tokens: int | None
    output_tokens: int | None
```

Adapter-owned, ~30 lines each, and the *only* place provider names appear:
pi maps `tool_execution_start` → `tool_start`, `agent_end` → `turn_end`,
`message.usage.cacheRead` → `cached_input_tokens`; cursor maps
`tool_call/started` → `tool_start`, `result` → `turn_end`,
`usage.cacheReadTokens` → `cached_input_tokens`. GDDP-owned code
(`compute_turn_context_coverage`, `extract_actual_cached_tokens`, `gddp watch`)
then consumes `ExecutorEvent` / `TurnUsage` only.

---

## 6. Findings that change the plan

1. **`PiRpcAdapter` does not satisfy `ExecutorAdapter`.** The class defines
   only `dispatch`, `status`, `collect`, `cancel`, `_attempt_dir`
   (`scripts/adapters/pi_rpc_adapter.py:116-349`) — no `supports_engagement`,
   no engagement methods. The conformance test asserts `isinstance(...,
   ExecutorAdapter)` for `jules_api`, `local_subprocess`, `droid`, and
   `factory_mission` and pointedly omits `pi_rpc`, while still asserting
   `pi_rpc` is in `ADAPTERS`
   (`scripts/adapters/test_executor_contract.py:280-291`). `dispatch_engagement`
   calls `adapter.supports_engagement()` inside a `try` that catches only
   `KeyError/TypeError/ValueError/JSONDecodeError`
   (`scripts/runtime/heartbeat/dispatcher.py:152-158`), so an `AttributeError`
   would escape. Unreachable today only because the runner probes via `getattr`
   first (`:88-91`, `runner.py:579-585`). The runtime's one live executor is
   outside its own protocol.

2. **The plumbing/work retry-budget split rides on substring matching.**
   `_PLUMBING_PATTERNS` matches adapter error prose
   (`scripts/runtime/heartbeat/reconciler.py:979-989`) against strings the
   adapter constructs (`scripts/adapters/pi_rpc_adapter.py:380-386`, `:396-400`).
   `cursor_cli` must reproduce the exact phrase "exited without durable exit
   state" to get a plumbing retry rather than burning a work attempt. This
   should be a `SessionStatus` field, not a phrase.

3. **Adapter reconstruction is env-dependent and can raise.** The reconciler
   rebuilds with `adapter_cls(repo=job_row["repo"] or "")`
   (`scripts/runtime/heartbeat/reconciler.py:472`), but `PiRpcAdapter.__init__`
   raises `ValueError` without a model
   (`scripts/adapters/pi_rpc_adapter.py:141-147`) and raises again without a
   spool root (`:1449-1451`). Polling therefore depends on the reconciler
   process carrying `GDDP_PI_RPC_MODEL` and a spool env var. `cursor_cli` should
   make `status`/`collect`/`cancel` constructible from `repo` alone.

4. **Resume is implemented and unreachable.** `resume_session_file` has no
   caller (`scripts/runtime/heartbeat/dispatcher.py:198-208` is the only adapter
   construction path), and the `sessionFile` captured per attempt
   (`scripts/adapters/pi_rpc_adapter.py:1126-1127`) has no reader anywhere in
   the repo. The doctrine's "resume is a capability, when-to-resume is policy"
   is currently *neither*: it is dead configuration.

5. **Cursor's usage would be silently dropped.** `cacheReadTokens`
   (`cursor_cli_spike_results.json:36`) is absent from `cache_keys`
   (`scripts/prompt_topology.py:254`), so `extract_actual_cached_tokens` returns
   `None` and the cache report keeps its structural-potential-only shape with no
   error raised (`scripts/adapters/pi_rpc_adapter.py:916-924` swallows only
   OSError/JSONDecodeError; this path just never fires).

6. **Two observability surfaces are already coupled to the pi spool.**
   `gddp watch` reads `events.jsonl`, `worktree_path`, `pid`, `supervisor.pid`,
   `result.json`, `exit.json` by path
   (`../gddp-config/scripts/gddp.py:4401-4463`), and `gddp steer` writes
   `steer.jsonl` into the same directory (`:4937-4960`). A cursor adapter either
   reproduces this exact directory layout or the operator loop silently loses
   `watch`/`steer` for every cursor node.
