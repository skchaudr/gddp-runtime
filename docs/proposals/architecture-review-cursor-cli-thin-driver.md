# Architecture review — is cursor_cli_adapter.py a thin driver?

Reviewer: architecture-reviewer subagent (Opus 5), 2026-08-29.
Scope: `git diff 6f12d37..HEAD` (capability-contract scaffold + cursor_cli
transport). Question posed by the operator: is `cursor_cli_adapter.py` actually
a thin driver over a generic executor runtime, or does generic execution
behavior remain trapped inside Cursor/Pi-specific adapters — and exactly what
should move upward, if anything. Read-only review; no code changed.

---

## Verdict

**Partially sound — thin where the wave actually built shared modules, still a
third hand-rolled copy of the local-execution runtime everywhere else.**

The direct answer: `cursor_cli_adapter.py` is **not yet a thin driver over a
generic executor runtime**, because there is no generic executor runtime for it
to be thin over. Four things did move up and are genuinely reused
(`session_prompt.build_turn_prompt`, `executor_events`, `events_cursor_cli` as
a pure translator, `runtime/context_coverage`). Everything else that is
generic — attempt identity, spool layout, durable exit-state schema, status
derivation, plumbing classification, handoff→`PatchResult` mapping, worktree
keep/remove durability policy, evidence writing, supervisor process
lifecycle — was written a third time inside a transport file. Roughly 350 of
the file's 867 lines are execution behavior with nothing cursor-specific in
them.

Separately and more seriously: the capability contract this wave exists to
establish has **zero runtime consumers**, and the continuity policy it
introduces is **structurally unreachable**, not merely unwired.

---

## Findings

### Critical

**C1 — The capability declaration has no consumer; the contract is currently
documentation plus a bug-catcher.**
`executor_protocol.py:280-292` (`adapter_capabilities`, zero callers);
`dispatcher.py:80-95` still `getattr`-probes; `dispatcher.py:213-225`
`cancel_remote_session` still emits transport-blind text ("remote may continue"
for a transport that just SIGKILLed a local subprocess). Two adapters declare
`ExecutorCapabilities`; the only reader of a declaration is each adapter
reading its own. Consequences: declarations silently rot into inaccuracy, and
inaccurate declarations are worse than none.
Solution class: one authoritative runtime read point for capabilities; route
every existing feature-probe through it; no new capability fields until a
policy call site consumes the existing ones. **Confidence: High.**

**C2 — The continuity decision cannot be made, because the transport owns the
identity the policy needs.**
`continuity_policy.py:144-176` reads `attempt_dir/resume.requested`, but
`attempt_dir` is minted inside `dispatch()` with a uuid suffix
(`cursor_cli_adapter.py:199-212`) and `dispatcher.py:122` calls
`adapter.dispatch(packet)` with no continuity argument. The marker cannot exist
where the policy looks — not for the current attempt, not for a retry (fresh
uuid). This is not "unwired"; as designed it cannot be wired. Shipped
docstrings assert the behavior in present tense anyway
(`cursor_cli_adapter.py:19-23`, `continuity_policy.py:16-17`) — the AGENTS.md
failure pattern. (Note: the marker-in-attempt-dir design traces to the lane-2
spec, not just the build.)
Solution class: attempt identity moves to the runtime ahead of dispatch
(`execution_attempt_id` is already on the packet); key the operator's
continuity request to something that exists before dispatch (job or node).
**Confidence: High on unreachability; Medium on which side owns identity.**

**C3 — Proliferation: coverage and the event vocabulary now exist twice, and
`events.jsonl` means two different things depending on executor.**
`runtime/context_coverage.py` (canonical) vs the still-live pi copy at
`pi_rpc_adapter.py:504-660`; usage extraction likewise forked
(`prompt_topology.extract_actual_cached_tokens` over raw pi events vs
`executor_events.turn_usage` over canonical). A pi attempt's `events.jsonl` is
raw pi schema; a cursor attempt's is canonical — consumers must branch on
executor to know the schema, under one invisible filename. The planned
`events_pi_rpc.py` (`executor-event-vocabulary.md:328-330`) was not built.
Solution class: complete the migration (pi-side translator, delete the
duplicated coverage/usage, read-time upconverter for old spools if needed);
if pi migration stays out of scope, give the two schemas distinct filenames.
**Confidence: High on the finding; Medium on urgency.**

### Warnings

**W1 — Attempt supervisor, spool layout, and durable exit record are a third
hand-rolled copy.** `cursor_cli_adapter.py:386-427,754-849` vs
`pi_rpc_adapter.py:401-449,1418-1468` vs `local_subprocess_adapter.py:210-486`.
None of it is cursor-specific; `local_subprocess`'s two-field `exit.json` shows
the convention has already drifted once. Solution class: extract a
local-attempt runtime (spool, exit record, status derivation, supervisor
lifecycle, signal escalation) that transports call. **High on duplication;
Medium on the seam** (pi's session-scoped orchestrator vs cursor's per-turn
process have genuinely different lifetimes).

**W2 — Retry-budget policy still travels as an English substring, now copied
into a second adapter.** `cursor_cli_adapter.py:84-88` reproduces the exact
phrase `reconciler.py:979-989` matches. Solution class: move classification
onto the structured status record — the `plumbing` boolean already exists in
`exit.json` and is re-encoded into text purely to survive `SessionStatus.error`.
**High.**

**W3 — `collect()`'s handoff→PatchResult mapping and the worktree keep/remove
rule are each implemented twice.** `cursor_cli_adapter.py:304-353,565-575` vs
`pi_rpc_adapter.py:313-365,1173-1177`. "A persisted result licenses removing
the worktree" is GDDP durability policy, not transport code. Solution class:
one decoder beside `persist_result`; the keep/remove rule expressed once as a
runtime-owned post-turn step. **High on duplication; Medium on placement.**

**W4 — GDDP execution doctrine is forked into two prose preambles.**
`cursor_cli_adapter.py:94-120` vs `pi_rpc_adapter.py:85-127` each restate
graph-integrity constraints in different words. Solution class: split the
protocol zone into a shared invariant fragment + per-transport capability
fragment; pi byte-stability constrains how, not whether. **Medium-high.**

**W5 — cursor_cli is the only transport doing git work in the dispatcher's
process.** `create_worktree` inside `dispatch()` (`cursor_cli_adapter.py:220-222`)
blocks the heartbeat runner on `git worktree add` and can leak a worktree if
the runner dies before the supervisor's first durable write. The fast-fail
benefit is real — a trade-off, not an oversight. Solution class: validate the
base SHA without materializing, or make the worktree recoverable from a durable
record written first. **Medium.**

**W6 — Evidence writing implemented twice with divergent mechanics.**
`cursor_cli_adapter.py:709-746` mutates the persisted report dict;
`pi_rpc_adapter.py:895-941` recomputes. Equivalent only by accident of the
current dataclass. Solution class: one post-turn evidence step both
supervisors call; folds into W1. **Medium-high.**

### Observations

- **O1** — cursor_cli still not constructible from `repo` alone: spool root
  env required (`cursor_cli_adapter.py:764-773`); design finding #3 half-met.
- **O2** — default spool root falls back to the local_subprocess dir, so one
  directory now holds three `exit.json` shapes and two `events.jsonl` schemas.
- **O3** — `midturn_steering=False` is declared but nothing refuses a steer;
  `steer.jsonl` on a cursor node is written and never read, and `gddp steer`
  still reports it queued. C1 made concrete.
- **O4** — C3's asymmetry traces to one omitted file: `events_pi_rpc.py`.
- **O5** — Correctly placed and genuinely reusable: `events_cursor_cli.py`
  (pure, fixture-tested, evidence-cited), `context_coverage.py`,
  `session_prompt.build_turn_prompt` (byte-stability test protects pi),
  `executor_events.turn_usage`. These are the model for the rest of the
  extraction.

## Alternatives considered

- "pi is the outlier; cursor is already the thin one" — partly true (867 vs
  1482 lines, no RPC client/inbox/orchestrator), but measured against the
  contract's own target the file is roughly half generic.
- "C1/C2 are just not-wired-yet" — the strongest counter, and the handoff says
  so honestly; kept Critical because shipped docstrings assert present-tense
  behavior, and C2's marker location cannot work as designed.
- "C3 only Critical if observably broken" — nothing broken today; kept
  Critical because the shared filename makes divergence invisible and the cost
  of closing it grows monotonically.
- A shared abstract base class for adapters — considered and rejected;
  composition against a runtime the drivers call is the direction.

## What should move upward

Ordered by integrity-protected-to-work ratio; confidence is in the direction.

1. **Capability reads → dispatcher/runner policy layer.** One authoritative
   accessor; convert `getattr` probes and cancel-text to read it. *(High)*
2. **Attempt identity → the runtime, ahead of dispatch.** The prerequisite
   that unblocks continuity. *(High that it must move; Medium on owner.)*
3. **Plumbing-vs-work classification → the structured status record, out of
   error prose.** *(High)*
4. **Pi's event translation → a driver; delete pi's coverage/usage copies.**
   Finishes the migration; collapses two schemas to one. *(High)*
5. **The local-attempt runtime (spool, exit record, status, supervisor
   lifecycle, signals) → a shared module transports call.** The largest piece;
   the one that actually makes "thin driver" true. *(High; Medium on seam.)*
6. **Commit-ref handoff decoder + worktree keep/remove rule → one owner beside
   `persist_result`.** *(High on duplication; Medium on placement.)*
7. **Post-turn evidence writing → one runtime step.** Folds into 5.
   *(Medium-high)*
8. **GDDP-invariant half of the protocol zone → `session_prompt`.**
   *(Medium-high)*

What should **stay** in `cursor_cli_adapter.py`: `build_argv`, the translator
wiring, the SIGTERM/SIGKILL choice as the declared `preemptive` mechanism, and
reading the session id off the first stream line — about 80 lines. That set is
what "thin" should mean here.
