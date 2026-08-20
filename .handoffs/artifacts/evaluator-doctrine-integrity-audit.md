# Evaluator Doctrine & Integrity Audit

Date: 2026-08-19 · Branch: `feat/organize-docs-hierarchy` @ `4f06879` · Auditor: Pi
Scope: doctrine-vs-executable-behavior audit of the GDDP evaluator. No code changed.
Evidence labels: **[confirmed]** = read in code/live artifacts; **[inferred]** = from code structure; **[doctrine]** = conflict with canonical docs; **[opportunity]** = design opening.

---

## 1. What evaluator exists today

### Trigger [confirmed]
- Evaluation is **event-driven off job return only**. Heartbeat `reconcile_sessions` polls executor sessions (`scripts/runtime/heartbeat/runner.py:191`); on `completed` → `_handle_completed` → collect result commit → `EvaluationBatch.add` (`reconciler.py:770`) → up to 2 worker threads (`DEFAULT_MAX_CONCURRENT_EVALUATIONS = 2`, `reconciler.py:48`) run `verify_job_return` (`scripts/runtime/verification/bridge.py`).
- A "collected but not yet evaluated" session is resumed into evaluation (`reconciler.py:463`). There is **no state-driven sweep** of unevidenced work that never reached reconcile — `docs/proposals/LOOP.md` itself admits this ("the state-driven sweep … is the known missing half").
- The mediated path (`scripts/runtime/return_router.py`) also calls `verify_job_return` for webhook/PR returns.

### Admission gates before evaluation [confirmed]
- `bridge._verify_once` requires `merge_commit_sha` ("required to pin the evaluation subject") and a materializable worktree at that SHA; otherwise it returns `subject_mismatch` and **no verdict is produced**. This is the one remaining admission gate after the GDDP-rebuild deletions. It binds the subject (legitimate) but can refuse judgment on work that exists without a commit ref.
- Node + project YAML must exist in `gddp-config/graphs/<project>/` or evaluation errors out.

### What the evaluator receives [confirmed]
Both lanes are `pi --print` subprocesses (`pi_runner.py`, `integrity_runner.py`) with `--no-context-files --no-skills --no-extensions --no-session`, a sandboxed HOME, the guard extension `gddp_verifier_guard.ts` (hard-blocks edit/write/multi_edit, destructive bash, git mutation, network; logs every tool call to `$GDDP_TOOL_TRACE`), and one typed terminal tool each. Live defaults (`bridge.DEFAULT_SEMANTIC_ARGS`): `--semantic-harness pi --semantic-provider deepseek --semantic-pi-model deepseek-v4-flash --thinking medium`; integrity lane ON (`GDDP_INTEGRITY_MODE` unset → on). Per-lane timeout 1200s (`semantic/timeouts.py`).

- **Lane 1 (criteria)** — `PI_SYSTEM_PROMPT` (`pi_runner.py:54`). User prompt is four cache zones (`prompt.py:build_turn_prompt`): framing + `graph:` (full project.yaml JSON) / `node:` (node YAML JSON) / `deterministic_result:` + `shape_profile:` / stable `canonical_pointers` (README, PROJECT-BRIEF, foundational node) + volatile `neighbor_pointers` (depends_on + unlocks YAML paths). Tools: pi built-in read/grep/find/ls/bash + terminal `submit_verdict`.
- **Lane 1 runs conditionally**: `orchestrator._should_run_semantic` — only when deterministic evidence has ≥1 `indeterminate` criterion AND no incomplete deps AND no violated constraint AND no failed criterion. Deterministic pass-clean, fail, blocked, or constraint-violated all skip lane 1.
- **Lane 2 (integrity)** — `INTEGRITY_SYSTEM_PROMPT` (`integrity_runner.py:38`). User prompt: node, graph, `neighbor_node_files` pointers, `deterministic_result`, canonical pointers, plus an explicit line that the full graph config at `config_root` is readable "if you need nodes beyond the neighbors". Same tools + terminal `submit_integrity_verdict`. **Always runs** when wired (orchestrator.py comment: "a green deterministic run must not bypass it").
- **Deterministic floor** (`verification/deterministic/`): `command_proof` (declared command executed, exit code is evidence), per-node hardcoded probes (`probe_for`), keyword/path heuristics (`probes.py`), artifact presence, constraint file checks, dep statuses from graph YAML, and `subject_diff` — a valence-free files-touched list for base..HEAD.

### How the verdict is formed [confirmed]
- Lane 1 → 12-row decision matrix (`decision_engine.py`), pure function, deterministic+semantic → `criteria_verdict` ∈ {pass, fail, blocked, needs-more-evidence, needs-human-review, out-of-scope-change-detected} + signals (criteria_confidence, completeness, graph_readiness).
- Lane 2 → `IntegrityOutput`: verdict ∈ {pass, block, drift, insufficient, contradicted, unknown}, `intent_preserved`, `graph_integrity_preserved`, `required_human_review`, confidence, `findings[]`, optional `graph_observations[]`, `tool_trace`. Any non-pass forces `required_human_review` (enforced by the extension, `gddp_integrity.ts`).
- Combination (`integrity_combiner.py`): worst-of; integrity floors the combined verdict — insufficient → ≥ needs-more-evidence; unknown/drift/contradicted/block → ≥ needs-human-review; violated flags with a pass word → ≥ needs-human-review. **Neither lane upgrades the other. Integrity can never produce FAIL** — the halt is always "a human looks" (`_INTEGRITY_FLOOR`).

### What consumes evaluator output [confirmed]
- **Receipt file** — full `VerdictReceipt` JSON to `gddp-config/verification/<project>/<node>/<job>-attemptN.json` (`receipt_sink.py`), immutable per attempt.
- **CLI summary** (stdout JSON, `cli.py:main`) → bridge → `_finalize_evaluation` (`reconciler.py:1247`) → `results.acceptance_check` row, session → `evaluated`, job → `awaiting_review`.
- **Provisional advancement** (`heartbeat/provisional_status.py`): combined pass + intent_preserved + graph_integrity_preserved + !required_human_review + !human_gate → system writes node status `provisional` in gddp-config + gate token. `provisional` satisfies dependency edges (`gddp-config/scripts/frontier.py: SATISFIED_DEP_STATUSES = {complete, provisional}`), so dependents dispatch before human acceptance (mode 1 default).
- **Retry** (`return_router.py` + `verification/retry_budget.py`): non-pass verdict + findings containing a file-path regex match (in integrity findings/reasoning or criteria evidence/reasoning) or `affected_node_ids`, + project `retry_budget` room → re-dispatch same node with findings injected as the fix-list. Otherwise `awaiting_review`.
- **Human surfaces**: `scripts/jobs_status.py show` (`print_evaluation`) renders verdict, integrity reasoning, criteria findings, integrity findings, graph observations, coverage, timing; `gddp node browse` (gddp-config `node_cli.py`) resolves the receipt from the results row and shows evidence + verdict; human keypress `c/r/d` is the only graph-truth write.

### What evaluator findings can cause downstream [confirmed]
Exactly four effects: (1) retry with injected fix-list; (2) provisional advancement of this node + dependent unblocking; (3) cascade halt at needs-human-review; (4) operator-visible text in jobs show / browse / receipt. Nothing else.

### Where intelligence is currently discarded [confirmed]
- `SemanticOutput.risks` / `followup_candidates`: present in the receipt file; **absent from the CLI summary** → absent from `results.acceptance_check` → never rendered by `print_evaluation`. `_finalize_evaluation` reads `verification.get("risks")` / `.get("followup_candidates")` — keys the summary never carries — so the DB columns are NULL on the live path. (`init_db.py:145` comments even describe them as JSON arrays — a pre-str|None contract.)
- Lane-1 `overall_reasoning`: in the receipt, not in the summary; `print_evaluation` falls back to integrity reasoning for "why".
- `DeterministicResult.human_review_questions` (probes can emit e.g. "Is the criterion path stale…?"): receipt-only; not surfaced in summary or jobs show.
- `graph_observations`: preserved (summary → acceptance_check → jobs show) and deliberately combiner-ignored, but they have **no route into graph change** — no proposal ledger entry, no browse-TUI action, no notification beyond text on a job view.

---

## 2. What evaluator GDDP doctrine now implies

Distilled from `docs/decisions/A-more-complete-evaluator-7-14-26.md`, `GDDP-becomes-small-and-real.md`, `Tests-can-fail-nodes-can-pass.md`, `Thin-Graph-Rich-Project.md`, `GDDP-rebuild.md`, `docs/proposals/LOOP.md`, `docs/invariants/invariants.md`:

- The evaluator is an **integrity-preserving project observer**. It adjudicates criteria when necessary, but its defining question is: *"What does this evidence imply about the health and trajectory of the project?"* Its time horizon is broader than its adjudication scope.
- It reads **canonical intent + DAG neighborhood**, never the executor's AGENTS.md. Executor asks "what do I do?"; evaluator asks "does what was done still preserve the project's intended meaning?"
- It is explicitly a **source of graph intelligence**: "not the authority that rewrites the graph, but the observer that provides the human or orchestrator with evidence about what the graph is becoming" (A-more-complete-evaluator). It must be able to report emerging risk, useful opportunities, and conditions of health — including findings that do not touch the current verdict.
- **No mechanism may block the evaluator from rendering a judgment** (GDDP-rebuild design rule): admission control decides what gets merged, never what gets evaluated.
- Tests/criteria/verdicts are **evidence; only human-accepted node status is graph truth**. Evaluator is second-to-last gate, never last. Automated action (retry) requires cited concrete evidence; uncited findings route to human.
- Discovered work beyond node scope becomes a **continuation proposal** (node YAML in the proposals ledger, human-materialized) — this object is defined in doctrine (`entities/node.md`, vocabulary.md) as *the* place discovered work goes.
- Thin graph: the project is navigable; nodes are not giant context packets.

---

## 3. Where those differ

**D1 — Graph intelligence has no home (the central gap).** [confirmed + doctrine]
The integrity lane can discover graph-level facts (doctrine's exact examples are in its prompt), and `graph_observations` preserves them in the receipt/DB. But the output contract offers no way to say *what should change* — no split/supersede/insert-prerequisite/rewire/revise-criteria vocabulary, no continuation-proposal channel, no graph-amendment object — and no consumption surface routes such intelligence to the human as a decision item. It lands as free text inside a job view. Doctrine says the evaluator exists to produce exactly this intelligence; the system preserves it weakly and acts on it never.

**D2 — Lane 1's prompt promises intent/integrity its contract forbids.** [confirmed]
`PI_SYSTEM_PROMPT` opens: "determine whether the work … satisfies the acceptance criteria … **AND whether it preserves the project's intent and integrity**." `SemanticOutput` has no intent/integrity fields; lane 2 is declared the owner of that question. Any intent observation lane 1 makes can only leak into `risks`/`followup_candidates` free text — which is then lost at the summary boundary (D1's discarded channels). The instruction either wastes budget or produces silently-dropped findings.

**D3 — Deterministic heuristic fail is final.** [confirmed, tension with doctrine]
`_should_run_semantic` skips semantic adjudication on any deterministic `fail`. For `command_proof` failures (declared command, exit code) that finality is defensible evidence. But probes also fail criteria via keyword/path heuristics (`probes.py` fallbacks), and no lane may re-adjudicate: lane 1 doesn't run, lane 2 is told criteria adjudication "is lane 1's job" (×3). A heuristic misfire becomes a FAIL verdict with only the integrity lane's drift vocabulary available to contest it. integrity-lane-spec says deterministic evidence "CAN be sufficient" — it does not establish that heuristic failure always is.

**D4 — Continuation proposals are unwired.** [confirmed + doctrine]
Doctrine defines the continuation proposal as the destination for discovered work; invariants §2 requires out-of-scope discoveries be recorded as such. No code path creates one from evaluator output — `followup_candidates` is a `str|None`, never parsed, never proposed. The evaluator has nowhere to put "there is missing work that has no node" except a findings summary.

**D5 — `docs/current/` contains a spec for a module that does not exist.** [confirmed]
`docs/current/decision-loop-spec.md` (GDAD/Jules/webhook decision loop, "module location scripts/runtime/decision_loop/") describes a system whose source is gone: `scripts/runtime/decision_loop/powers/` contains only stale `.pyc` files, zero `.py`. Tier-2 "current truth" carrying tier-8 content violates the epistemic hierarchy this branch was built to enforce. Related: `docs/current/dispatch-checklist.md` says node YAML lives "in the project's own repo … gddp-config is not its warehouse", contradicting `current-architecture.md`/`LOOP.md`/`bridge.py` (`config_root/graphs/<project>/nodes/`). Either a stale statement or an unannounced migration intent — as written, current truth is self-contradictory.

**D6 — Stale evaluator docs.** [confirmed]
`scripts/runtime/context.md` describes verification as "Two-lane automated evaluator (deterministic + semantic criteria)" (no integrity lane) and lists `decision_loop/` as an active module. `entities/evaluator.md` is accurate. `gddp_verifier.ts`'s header still claims the runner excludes bash — superseded by the broad-inputs guard design.

**D7 — Graph staleness about the evaluator itself.** [confirmed, illustrative]
`gddp-config/graphs/gddp-runtime/nodes/evaluator-intent-integrity-verdict.yaml` is `status: pending` and specifies an *upgraded `submit_verdict`*; the capability actually shipped as a separate lane with its own tool. The node no longer describes what should happen next. This is the very failure class the evaluator is meant to detect, sitting in GDDP's own graph.

---

## 4. System-instruction findings

Classification key: **(1)** consistent · **(2)** implementation-specific, harmless · **(3)** stale/historical · **(4)** unnecessarily constraining · **(5)** actively contradictory · **(6)** missing.

### Lane 1 — `PI_SYSTEM_PROMPT` (`pi_runner.py:54`) [live]
| Instruction | Class | Likely behavioral effect |
|---|---|---|
| "You are the GDDP semantic verification investigator." | 1 | Correct role anchor. |
| "…satisfies the acceptance criteria, AND … preserves the project's intent and integrity." | 5 | Contract has no intent/integrity channel; invites effort the schema discards (see D2). |
| "You do NOT decide the final node status; a human does. You produce evidence and a typed verdict only." | 1 | Enforces evidence-only doctrine; suppresses verdict grandiosity. Good. |
| Tool list + "edit/write/multi_edit are hard-blocked … destructive verbs … hard-blocked." | 1 | Truthful (guard); sets expectations the harness mechanically keeps. |
| "Prefer cheap tools (read, grep, find) before bash." | 2 | Cost discipline; harmless. |
| Evidence-scope block: "evaluate ONLY against the node's stated acceptance criteria … extra evidence cannot rewrite the definition of success." | 1+4 | Correct lane separation and Tests-can-fail doctrine. Side effect: "the criterion itself is wrong/obsolete" is out of scope by construction — it can only surface as a followup string, which is then dropped at the summary boundary. |
| Followup instruction: log unlisted evidence as a human clarification ("Was it intended to be part of the criteria?"). | 1, but lost | Produces exactly the right artifact — and the pipeline discards it after the receipt file (D1/§8). |
| "You are not re-doing the executor's full due diligence from scratch." | 2 | Budget discipline. |
| Canonical context paragraph (README/PROJECT-BRIEF/foundational node/neighbors; AGENTS.md withheld). | 1 | Directly implements GDDP-becomes-small-and-real. |
| "Criteria confidence … INDEPENDENT of whether required artifacts are present." | 1 | Required for the matrix's completeness dimension; prevents double-counting. |
| — no statement that the full graph config is readable | 6 | Lane 2 gets the `config_root` line; lane 1 doesn't, so its horizon is the embedded zones + repo unless it guesses paths. |
| — no sufficiency/stopping guidance | 6 | Model may over-investigate to the 1200s timeout or under-investigate; nothing tells it when evidence is enough. |
| — no "cite repo paths" consequence statement | 6 | Retry depends on a file-path regex in evidence/reasoning; the model is never told cited paths are what make a finding actionable vs. human-only. |

### Lane 2 — `INTEGRITY_SYSTEM_PROMPT` (`integrity_runner.py:38`) [live]
| Instruction | Class | Likely behavioral effect |
|---|---|---|
| Role: fresh-eyes drift review; "You are NOT re-adjudicating acceptance criteria — that is lane 1's job." | 1+4 | Right division of labor, repeated three times (system + user prompt ×2). Suppression becomes real when lane 1 never ran (deterministic fail path): the only live model is barred from the criteria question by instruction. |
| "Think like a fresh pair of eyes, not a spec enforcer. … Could it inadvertently break something a dependent node relies on? Is the intent still recognizable?" | 1 | These are precisely the doctrine's questions; they license downstream-impact investigation. |
| findings vs graph_observations block, with the "current node still passes" example. | 1 | The cleanest expression of A-more-complete-evaluator in the codebase. Makes pass-with-concerns a legitimate output instead of a disguised failure. |
| Vocabulary block (pass/block/drift/insufficient/contradicted/unknown). | 1 | Matches the node-YAML source of truth cited in `schemas.py`. |
| "The integrity review is a guardrail, not a gatekeeper." | 1 | Matches the combiner: non-pass floors to human review, never FAIL; matches provisional-flow doctrine. |
| — no graph-mutation vocabulary | 6 | Findings/observations carry `severity + summary + affected_node_ids` only. "Split X / supersede Y / insert prerequisite Z / revise criteria W" has no typed expression — everything collapses to prose. |
| — no invariants/doctrine feed | 6 | The evaluator must infer what must remain true from README/PROJECT-BRIEF/node YAML. `docs/invariants/invariants.md` (or a project equivalent) is never offered, so invariant violations are discoverable only if the invariant happens to be written into offered docs. |
| — no longitudinal context | 6 | No prior verdicts, no history of accepted nodes, no "what earlier attempts revealed". Collective drift across several passing nodes is structurally invisible (see §7 case 9). |
| — no continuation-proposal concept | 6 | Doctrine's named destination for discovered work is not mentioned anywhere in either prompt. |

### Legacy — `prompt.py:SYSTEM_PROMPT` [dead on the live path]
| Instruction | Class | Effect |
|---|---|---|
| "Do not choose the final project verdict." | 3 | Pre-integrity wording; harmless but superseded. |
| Example output literally shows `"risks": null, "followup_candidates": null` | 5 (if used) / 3 (as-is) | Actively instructs the model to null the only two free-intelligence fields in its schema. `pi_runner.run` builds messages with this system prompt and then discards it in favor of `PI_SYSTEM_PROMPT`, so live runs never see it — but `build_prompt_messages` still emits it, cache-topology tests still treat it as the protocol zone, and any revival of the built-in agent path inherits the suppressive prompt. This is the clearest historical scar in the evaluator: a field-nulling instruction outliving the era that wrote it. |

---

## 5. Context / evidence-horizon findings

- **Static preselection with dynamic escape hatches.** Both lanes receive a fixed menu (node, project.yaml, deterministic result, canonical/neighbor pointers). Navigation beyond it is possible: read/grep/find/bash work over the worktree, and lane 2 is explicitly told where `config_root` lives ("if you need nodes beyond the neighbors") — so **graph-directed investigation exists for lane 2, weakly for lane 1** [confirmed]. The evaluator can follow an unexpected implication into an adjacent node (lane 2), can stop whenever it calls its terminal tool, and is not force-fed content — pointers-not-blobs is the right shape ("a read call is evidence, an embedded blob is not", `context_builder.py` docstring) and honors Thin-Graph.
- **Context assembly substitutes for navigation in two places.** (a) The `graph:` zone embeds the entire project.yaml — fine for 7–22 node graphs, a scaling cliff later, and it puts volatility placement ahead of the model choosing. (b) The canonical menu is hardcoded to `README.md`/`PROJECT-BRIEF.md`/first-node — pre-ICM assumptions. A project whose intent now lives in `context.md`/`entities/`/`docs/invariants/` (as this repo does after the reorganization) offers the evaluator a stale menu. **[opportunity]** Point the builder at the project's own context map instead of two fixed filenames.
- **Foundational node = first entry in project.yaml's node list** (`context_builder.py`) — ordering heuristic, not doctrine; fragile if lists get resorted.
- **Coverage metric measures menu consumption, not sufficiency.** `_compute_context_coverage` rates none/low/medium/high by whether offered canonical files were actually read (read/grep success only). Operator-visible, never verdict-gating — good. But "high" means "read README + a neighbor", not "established enough evidence"; a diff+node+one-neighbor integrity proof could legitimately rate "low". Keep it as observability; don't let it drift into a quality gate. **[confirmed]**
- **Lane asymmetry:** lane 1 lacks the config_root pointer; lane 2 lacks the cache-zone discipline (single prompt string). Minor, but the two lanes are siblings with diverging context contracts. **[confirmed]**

---

## 6. Invariant findings

### Current `docs/invariants/invariants.md` assessed
| Item | System doctrine? | Evaluator utility | Assessment |
|---|---|---|---|
| §1 Human authority on graph truth (sole acceptance; gates are second-to-last; status ≠ implementation state) | Yes — core. | High: this is the frame that makes findings proposals rather than commands. | Keep; **give it to the evaluator** (never currently supplied). |
| §2 Unit of intent; retry immutability; continuation proposals | Yes. | High: explains why findings become fix-lists and where discovered work goes. | Keep; retry immutability deserves a wording check against §7 case 4 below. |
| §3 Files are truth; receipts prove execution; citations required for automated action | Yes. | Citations rule is *operationally load-bearing* (`retry_budget.py` regex) yet invisible to the model that must produce the citations. | Keep; add the citation consequence to the prompts. |
| §4 Worktree isolation | Executor doctrine, not evaluator/system semantics. | Low. | Fine to keep, but it's an execution-boundary rule, borderline for "inviolable system law". |
| §4 Frozen infrastructure discipline (names `scripts/intake_server.py`, `scripts/adapters/jules_*`, `deploy/rig1-heartbeat/`, …) | **No — this fossilizes a file list and a prioritization policy as a system law.** | None for the evaluator. | **Demote.** The frozen list already lives in LOOP.md where it belongs as operational policy; paths in an invariant rot the moment a node renames a file. |
| §5 No direct main commits; atomic commits; clean handoff | Agent-workflow discipline for this repo. | None. | **Wrong tier.** This is AGENTS.md material (where it also lives); it governs agents editing gddp-runtime, not GDDP's runtime semantics. |

### Missing invariants the evaluator must currently infer
1. **"No mechanism may block the evaluator from rendering a judgment; admission control decides what gets merged, never what gets evaluated."** — GDDP-rebuild's explicit design rule, arguably *the* evaluator invariant, absent from invariants.md. The `merge_commit_sha` gate in bridge.py is its only live tension point.
2. **The evidence hierarchy sentence** Tests-can-fail-nodes-can-pass asked to canonize: "Tests are evidence, not graph truth. Criteria are evidence… Only human-accepted node status is graph truth." Present in AGENTS.md, partially in §1, never in the evaluator's own context.
3. **Dependency-edge vs evidence-link distinction** (vocabulary.md, entities/graph.md) — exactly what the integrity lane needs to reason about "graph integrity" correctly; currently left to inference.

### Contradictions / unclear
- **vocabulary.md `provisional` = "Unverified intermediate status"** contradicts the implemented meaning: *evaluator-verified, human-unaccepted* (provisional_status.py). A vocabulary bug with doctrine weight — "unverified" invites the wrong reasoning everywhere the term is read.
- **Retry immutability vs cross-node findings:** `retry_budget.py` counts a finding's `affected_node_ids` as actionable evidence, so a finding about *another* node can be injected into *this* node's retry fix-list. Tension with "a retry re-attempts the exact same node definition unchanged" — the right remedy for a cross-node finding is usually a new/prerequisite node, i.e. a graph proposal, not a fix-list item.
- **§1 says only a human can transition a node to `accepted`**, while the system writes `provisional` (graph-adjacent status, dependency-satisfying) automatically. GDDP-rebuild sanctions this explicitly, but invariants.md never mentions provisional — a reader of tier-1 docs cannot reconstruct tier-2 behavior.

### Should NOT be promoted to invariants
The two-review-modes policy (mode 1 default) — operator dial, decision-tier. The 12-row matrix and worst-of combiner mechanics — implementation. The pi-only evaluator path — implementation detail (and note: a *model capability assumption* is baked in: both lanes default to `deepseek-v4-flash`; doctrine never said integrity review must run on the cheapest model — that's budget policy wearing architecture's clothes).

---

## 7. Graph-intelligence findings — the central distinction, case by case

Can the evaluator **discover / express / see preserved+acted upon** each class of finding?

| # | Case | Discover | Express | Preserved & acted on |
|---|---|---|---|---|
| 1 | All criteria pass; implementation breaks a downstream node | **Yes** — lane 2 gets neighbor YAMLs + repo, prompt asks exactly this | **Yes** — finding + non-pass verdict | **Yes** — provisional blocked, cascade halts at needs-human-review, finding rendered in jobs show. *The system's strongest case.* |
| 2 | Criteria encode an obsolete/wrong assumption | Partial — lane 1's evidence-scope rule forbids judging beyond criteria; can only file a followup string; lane 2 may see intent mismatch | **Weak** — followup string (lane 1) or drift verdict (lane 2); no "criterion is wrong" expression | **Mostly no** — followup dropped at summary boundary; drift path reaches human |
| 3 | Evidence shows an upcoming node is unnecessary | Yes (lane 2 reads downstream YAML) | Free-text `graph_observation` only | Preserved (receipt+DB, jobs show); **no route to graph change** — human must notice prose and hand-author |
| 4 | Missing work that has no node | Yes (fresh eyes) | Free-text finding/observation; **no continuation-proposal channel** | With a file ref it can become a *retry fix-list* — the wrong remedy (retries the same node); without, human review only. Doctrine's actual remedy (continuation proposal) is unwired |
| 5 | Two downstream nodes mutually incompatible | Only if both are direct neighbors or lane 2 navigates config_root (it is told it can) | Free-text observation listing both ids | As #3 — preserved, unrouted |
| 6 | New architectural constraint should reorder dependencies | Possible; but with no invariants/decisions fed, "architectural law" is inferred from README/BRIEF | Free-text only | As #3 |
| 7 | Node should be split / superseded / prerequisite inserted | Yes | **No typed vocabulary** — prose in a summary field | No channel; human must translate prose into graph surgery |
| 8 | Locally passing change violates a project invariant | Only if the invariant appears in offered docs; invariants.md is never offered | Yes — drift/contradicted verdict is built for this | Yes — human-review halt. Works when discoverable |
| 9 | Several individually passing changes produce collective drift | **Structurally no** — evaluation is per-node, stateless, with no prior-verdict history or accumulated graph state supplied | n/a | n/a. *The one case the harness cannot even see without new context plumbing* |

### The central question, answered stage by stage
> If work perfectly satisfied the node but revealed the graph itself was now wrong — would the evaluator recognize it, investigate it, preserve it, and put it before the human with enough specificity to reshape the graph?

- **Recognize: conditionally yes.** Lane 2's mandate ("does the change preserve the node's intended role … graph integrity") plus neighbor YAMLs makes recognition plausible — but "graph integrity" is framed as integrity *of the existing graph's structure*, not correspondence between graph and reality. No prompt asks "is this graph still the right plan?"
- **Investigate: partially.** Lane 2 may read any node in config_root (told where) and the repo; it is not shown prior verdicts, review history, or rationale beyond YAML.
- **Preserve: yes.** findings/graph_observations survive in receipt + acceptance_check.
- **Act upon: no.** No proposal object, no graph-amendment vocabulary, no surface that presents "evaluator thinks the graph should change" as a decision item. The intelligence ends as prose inside a job view, competing with verdict detail. **The pipeline fails at the last stage — surfacing with actionable specificity.**

---

## 8. Information currently lost by the output contract

What GDDP fundamentally needs from evaluation, vs what the contract can represent:

| Need | Representable today? | Where it goes / dies |
|---|---|---|
| Node criteria verdict | Yes — typed, per-criterion | receipt + summary + DB |
| Evidence/confidence/completeness | Yes | receipt + summary (`context_coverage`, signals) |
| Intent/integrity verdict | Yes — lane 2 typed | receipt + summary + DB; floors combined verdict |
| Integrity findings (current node) | Yes — severity/summary/node-ids | retry fix-list if cited; else human view |
| Forward-looking graph observations | Partially — severity/summary/node-ids, no action shape | receipt + DB + jobs show; **terminates there** |
| Graph implications (split/supersede/insert/rewire/revise) | **No** — collapses into prose | dies as unstructured text |
| Criterion meta-judgments (obsolete/mis-specified criteria) | **No** — judgments are pass/fail/indeterminate *against* the criterion | lane-1 followup string → dropped at summary |
| Invariant conflicts | **No field** — must ride inside findings | only if cited, retry; else human view |
| Discovered missing work (continuation proposals) | **No** — doctrine defines the object, schema has no slot | nowhere |
| Semantic risks / followups | In schema, in receipt | **dropped by CLI summary → invisible in DB and operator views** |
| Deterministic human_review_questions | In receipt | not surfaced anywhere downstream |

The terminal shape forces everything back through `pass/fail/blocked/needs-*/out-of-scope` + two finding lists. That is the exact "information loss" the audit prompt hypothesizes — confirmed at two independent seams: the typed schema (no graph-action vocabulary) and the summary bridge (drops the free-text intelligence that does exist).

---

## 9. Historical machinery that may now be unnecessary

1. **`prompt.py:SYSTEM_PROMPT` with nulled risks/followups** — predates the integrity lane and the pi harness; dead on the live path, preserved by cache-topology tests. Delete or rewire; its continued existence is a trap for the next agent.
2. **Built-in `SemanticAgent` stack** (`semantic/agent.py` 572L, `semantic/tools.py` 317L, Anthropic/OpenAI runners) — the orchestrator hard-fails without a pi harness; `cli.py --semantic-harness runner` resolves to a path that raises. ~900 lines + 495 lines of tests guarding a corpse. GDDP-rebuild's standing rule: prefer deleting a mechanism to guarding it.
3. **`scripts/runtime/decision_loop/`** — zero source files, stale `.pyc`s, and a tier-2 spec doc describing it. Archive the doc, remove the dir.
4. **Heuristic-fail finality** (D3) — pre-integrity-lane inheritance, re-endorsed for command_proof but not evidently examined for keyword probes.
5. **Static canonical menu** (README/PROJECT-BRIEF only) — predates ICM; the "more context = better" era is over, but the menu still assumes two fixed filenames are where intent lives.
6. **`init_db.py` risks/followups columns** with stale comments, never populated live.
7. **`VerdictReceipt.evaluated_tree_sha`** — self-described wrong-type comparison kept "for receipts already written"; migration debt, minor.
8. **`gddp_verifier.ts` header comment** claiming bash is excluded — stale vs the guard model.

---

## 10. Highest-leverage changes, ranked

1. **[opportunity — central fix] Give graph intelligence a home.** Extend lane 2 with a typed graph-implication channel (e.g. action class ∈ {split, supersede, insert-prerequisite, revise-criteria, rewire, depose-ordering, missing-work} + affected nodes + rationale + optional draft node-YAML) and route non-empty entries to a durable, human-facing surface (proposals ledger entry and/or a dedicated section in `gddp node browse`). Smallest change that converts today's prose-terminating intelligence into graph-amendment proposals. Needs a node; touches schemas, integrity extension, combiner-adjacent plumbing, gddp-config display.
2. **[confirmed bug-class] Stop discarding paid-for intelligence.** Add `risks`/`followup_candidates` (and `human_review_questions`) to the CLI summary → acceptance_check → `print_evaluation`; reconcile the stale DB column comments. Small, mechanical, restores channels the prompts already instruct the model to use.
3. **[doctrine alignment] Feed the evaluator its own doctrine.** Offer `docs/invariants/` (or the project's equivalent) in the canonical menu; give lane 1 the config_root pointer lane 2 has; add the citation-consequence instruction ("findings with cited repo paths can become automated retries; uncited findings go to a human"). Prompt/context-builder only.
4. **[doctrine hygiene] Fix tier-2 truth.** Move `docs/current/decision-loop-spec.md` to archive; correct `scripts/runtime/context.md` (three-lane verification; no decision_loop); resolve dispatch-checklist's "project repo owns the graph" statement against actual gddp-config ownership. Cheap, and this audit's epistemic framework demands it.
5. **[doctrine hygiene] Rebuild the invariant tier.** Demote frozen-infrastructure and agent-workflow items (LOOP/AGENTS tier); canonize the missing evaluator-relevant invariants (§6 list); fix vocabulary.md `provisional` ("evaluator-passed, human-unaccepted", not "unverified"); mention provisional in invariants §1.
6. **[doctrine question for Sab] Re-examine heuristic-fail finality.** Either let lane 1 adjudicate deterministic *heuristic* fails (keeping command_proof fails final) or have lane 2 explicitly acknowledge skipped criteria adjudication. The current state makes keyword-probe verdicts the one unreviewable judgment in the system.
7. **[opportunity — larger] Longitudinal context for drift.** Supply lane 2 prior verdicts for the node + recent accepted-neighbor evidence (the `verification/` tree is already on disk), enabling case 9 (collective drift) — currently structurally invisible.
8. **[hygiene] Delete dead machinery** (§9 items 1–3): legacy agent stack + broken `runner` harness path, stale SYSTEM_PROMPT, decision_loop dir. By the rebuild's own rule: removal over guardianship.

---

## Appendix: key files referenced

| Area | File |
|---|---|
| Trigger/reconcile | `scripts/runtime/heartbeat/reconciler.py` (`_finalize_evaluation:1247`, `EvaluationBatch`), `runner.py:191` |
| Admission/bridge | `scripts/runtime/verification/bridge.py` (`_verify_once`, `DEFAULT_SEMANTIC_ARGS`) |
| Orchestration | `scripts/runtime/verification/orchestrator.py` (`verify`, `_should_run_semantic`, `_compute_context_coverage`) |
| Criteria decision | `scripts/runtime/verification/decision_engine.py` (12-row matrix) |
| Integrity combination | `scripts/runtime/verification/integrity_combiner.py` |
| Schemas | `scripts/runtime/verification/schemas.py` (`SemanticOutput`, `IntegrityOutput`, `VerdictReceipt`) |
| Lane 1 prompt/runner | `scripts/runtime/verification/semantic/pi_runner.py` (`PI_SYSTEM_PROMPT`), `prompt.py` (legacy `SYSTEM_PROMPT`) |
| Lane 2 prompt/runner | `scripts/runtime/verification/semantic/integrity_runner.py` (`INTEGRITY_SYSTEM_PROMPT`) |
| Canonical context | `scripts/runtime/verification/semantic/context_builder.py` |
| Terminal tools/guard | `semantic/pi_harness/gddp_verifier.ts`, `gddp_integrity.ts`, `gddp_verifier_guard.ts` |
| Retry | `scripts/runtime/return_router.py`, `scripts/runtime/verification/retry_budget.py` |
| Provisional | `scripts/runtime/heartbeat/provisional_status.py`, `gddp-config/scripts/frontier.py` |
| Human surfaces | `scripts/jobs_status.py` (`print_evaluation`), gddp-config `scripts/node_cli.py` |
| Doctrine | `docs/decisions/{A-more-complete-evaluator-7-14-26, GDDP-becomes-small-and-real, Tests-can-fail-nodes-can-pass, GDDP-rebuild, Thin-Graph-Rich-Project}.md`, `docs/invariants/invariants.md`, `docs/proposals/LOOP.md` |
| Live evidence | `gddp-config/verification/myapi-part1/node-11-…/job_…-attempt0.json` (populated `graph_observations`, `risks`, `followup_candidates`) |
