# 033 — aa-cli Reality Survey

Surveyed: `/home/sab/aa-cli` (pre-existing local checkout).
Correction applied mid-task: local checkout was 25-55 commits stale on both
branches it had (`feat/tui-fixes`, `main`). Ran `git fetch origin`, then
`git checkout main && git pull --ff-only`.

**Source of truth for this report: branch `main`, HEAD `cfb326a`
(2026-07-11, "feat(hub-rs): runway ≥ half screen as live fire confirmation
strip").** `feat/tui-fixes` (HEAD `6b31230`, 2026-07-06) has diverged from
`main` — 35 commits on tui-fixes not in main, 55 commits on main not in
tui-fixes. `main` has the latest commit date and is the branch carrying the
repo's own `gddp/` graph updates, so it's treated as trunk here.

**Important finding: the repo carries its own local GDDP graph** at
`gddp/project.yaml` + `gddp/nodes/*.yaml` (33 nodes, `last_updated:
2026-07-09`) — separate from and much more current than the 12-node graph at
`/home/sab/gddp-config/graphs/aa-cli/`. The gddp-config graph describes an
older architecture (pure-zsh sync/async dispatch, ledger states
open/done/error). The repo has since grown a Rust TUI frontend (`hub-rs/`)
and changed the ledger state machine to
`queued → in_progress → to_be_verified → done/validated` (see
`lib/reconcile.zsh` header comment, dated "post-2026-07-04"). This means
several of the 12 gddp-config nodes' acceptance criteria are now stale
against actual code, not just their `status` field. Details in section 2.

---

## 1. Repo snapshot

**Languages:** zsh (bin/aa + lib/*.zsh, ~4600 lines across 16 modules) and
Rust (hub-rs/, ~7200 lines across 21 files, ratatui TUI, edition 2021).

**Entry points:**
- `bin/aa` — zsh CLI, sources all `lib/*.zsh`, dispatches subcommands (gen,
  fire, deck, ledger, reconcile, vault, inventory, jules, pi, verify,
  audit/recon/brief/explain/study verbs, generate-path).
- `hub-rs` binary `aa-hub` (`hub-rs/Cargo.toml` bin name) — standalone Rust
  TUI cockpit, NOT invoked from `bin/aa` (no `hub-rs` or `aa-hub` reference
  in `bin/aa`). Two parallel UIs currently coexist: legacy zsh
  `lib/deck.zsh` (857 lines, still wired into `bin/aa`'s `deck` subcommand)
  and the new Rust cockpit (7200 lines, all of the last 10 commits touch
  only this side).

**Test suite state:**
- `tests/acceptance.zsh` (821 lines, zsh, no external framework — asserts +
  `fail()` + final `print PASS`): ran it, exit 0, printed `PASS`. Single
  aggregate result — the script doesn't report per-case pass/fail counts,
  it aborts on first `fail` via `set -euo pipefail`. All assertions in the
  script currently pass.
- `hub-rs/tests/render.rs` (577 lines) — could NOT run. No `cargo`/`rustc`
  on this machine (`command not found: cargo`). Can't confirm the Rust side
  compiles or its tests pass — repo-side code looks structurally complete
  (see section 2), but this is unverified.

**Last 10 commits (main, most recent first):**
```
cfb326a 2026-07-11 feat(hub-rs): runway ≥ half screen as live fire confirmation strip
e11d3fa 2026-07-11 fix(hub-rs): runway shows only queued/in_progress/launching
f278af3 2026-07-11 fix(hub-rs): stop aa reconcile on every fire/refresh (A3 freeze)
2ff4663 2026-07-10 docs(gddp): executor-receipt convention (one-file H2 form)
a7c6ea9 2026-07-10 feat(hub-rs): Phase C linear create — command/insert, f/s on prepare
36c80ab 2026-07-10 docs(handoff): 002 VM Pi structure worker for sab-dev-2
95692a3 2026-07-10 docs: add cross-machine portability guide
fd5278f 2026-07-10 feat(hub-rs): Phase B auto evals — footers, no silent c-quit, collision suite
a221a33 2026-07-10 chore: ignore host-local .pi/ and .vectorcode/ dirs
e278956 2026-07-10 docs(hub-rs): align Verify keymap comment with f=fire ;=fzf
```
All active development in the last two days is on hub-rs (the Rust
cockpit); zsh `lib/*.zsh` hasn't moved in that window.

**TODOs/FIXMEs:** zero literal `TODO`/`FIXME`/`XXX` markers in executable
code (`*.zsh`, `*.rs`). All grep hits are either docs describing a
"todo-harvest" skill concept, or `mktemp ...XXXXXX` template strings
(false positive on `XXX`). Clean in that narrow sense.

---

## 2. Per-node reality check (12 nodes, `/home/sab/gddp-config/graphs/aa-cli/`)

All 12 read `status: complete`. Reality against current `main`:

**common-core** — EXISTS. `lib/common.zsh` has `AA_ROOT`/`AA_DATA_HOME`/
`AA_STATE_HOME`/`AA_SCHEMA` env-override defaults, `aa_init_dirs`,
`aa_validate_packet` (jq -e -f against schema), `aa_require_jq`, `aa_slug`/
`aa_now_iso`/`aa_now_id`/`aa_title_from_prompt`. One drift: acceptance
criterion text says these live "in lib/fire.zsh" — they're actually in
`lib/common.zsh` (constraints section allows both files, so functionally
fine, just a documentation nit).

**target-registry** — EXISTS. `lib/targets.zsh`: `aa_target_parse_row`
(4-col + legacy 3-col), `aa_target_lookup` (exact tier + default fallback),
`aa_target_names`, `aa_die` on unknown target. Matches criteria as written.

**ledger-system** — PARTIAL / EVOLVED. `lib/ledger.zsh` still does
TSV append/update/atomic-mv/stale-detection/print exactly as specified —
but the *state vocabulary* the node was written against
(`open`/`done`/`error`) has been superseded by
`queued`/`in_progress`/`to_be_verified`/`done`/`validated`/`error` (see
`lib/reconcile.zsh:1-22` state-machine comment, and `lib/ledger.zsh:61-114`
`aa_state_glyph`). The 6-column TSV shape and helper function names the
node cites are all still true; the semantics the node assumed for "done"
("state written directly on completion") are not — `done` is now reserved
for after a human/machine verify pass (`lib/validate.zsh:63-72`).

**dispatch-router** — PARTIAL. `validate-before-fire`, `run-dir-artifacts`,
`target-lookup-branch`, `async-placeholder-branch`, `receipt-and-toast`
criteria all still hold in `lib/fire.zsh`. The `sync-inline-path` criterion
("sync targets run ... and record done or error in the ledger") is now
**false**: sync dispatch is backgrounded via a `nohup zsh -c` wrapper that
writes a `queued` row with the background pid as ref
(`lib/fire.zsh:169-189`); `done`/`error` are decided later by
`aa_reconcile` + `aa_validate_result`, not by `aa_fire_packet` inline. This
is a deliberate, documented change (repo-local node
`sync-target-backgrounding`, status complete, added ~2026-07-04), not a
regression — but it means the gddp-config node's stated acceptance
criterion is stale.

**dispatch-grok / dispatch-pir / dispatch-gemini / dispatch-droid** — all
PARTIAL for the same reason. Each gddp-config node explicitly constrains
its target to stay sync with "no pid file", e.g. dispatch-droid: "droid
remains sync — no pid file or reconcile hook"; dispatch-gemini: "no
background pid tracking"; dispatch-pi-cli: "pir stays sync — background
dispatch belongs to dispatch-pi-harness." All four are now contradicted by
`lib/fire.zsh`'s generic sync branch (lines 169-189), which nohup-backgrounds
*every* sync target uniformly and writes a pid file + `queued` ledger row.
targets.conf entries themselves (grk/pir/gemini/droid rows) are unchanged
and still resolve correctly through `aa_target_lookup` — the routing layer
these nodes describe is intact, only the "stays sync/blocking, no pid"
constraints are violated by design.

**dispatch-codex** — EXISTS, matches. `lib/fire.zsh:69-91`: async
`__codex_async` branch, nohup wrapper, pid + exit_status files, mutations
gate on `--sandbox workspace-write`/`read-only`, receipt with run dir. One
change: ledger row now written as `queued` (was `open` per the node text) —
functionally the async-codex row model is otherwise unchanged.

**dispatch-jules** — EXISTS, matches. `lib/fire.zsh:93-115`: origin
parsing via sed transform, `jules remote new`, session id extraction,
error path writes `error`/`ref -`, success writes `queued` (node text says
`open`, same drift as above).

**dispatch-pi-harness** — EXISTS, matches. `lib/fire.zsh:117-167`:
`AA_PI_PACKET_BIN` existence check, inline packet.yaml generation from
prompt when no `packet_slug`, referenced-slug path, nohup background run,
`pi_artifact` ref file, `queued` ledger row.

**reconciliation** — EXISTS and substantially exceeds the node spec.
`lib/reconcile.zsh` (163 lines) reconciles codex/cdx/pi via pid+exit_status
liveness (`aa_reconcile_pid_target`), jules via `remote list`/`remote pull`
+ diff extraction (`aa_reconcile_jules_target`), and — new — any sync
target that left run-local pid/exit_status evidence (the generic branch at
`reconcile.zsh:140-148`), atomically rewrites the ledger via temp+mv, and
now lands terminal outcomes at `to_be_verified` rather than `done` directly
(the node's acceptance criteria describe the old two-state
open→done/error terminal model). The node's own constraint
("pi-harness reconciliation may remain future scope") is obsolete — it's
implemented.

**Overall for the 12-node graph:** every capability described genuinely
exists in code. The `status: complete` claim is directionally right for
"was this built," but several nodes' specific acceptance-criteria wording
(the sync/async state model, "done"/"error" vs
"queued/in_progress/to_be_verified") no longer matches the shipped state
machine. None of this is regression — it's forward evolution the
gddp-config graph didn't get updated for.

---

## 3. Genuinely unbuilt

The repo tracks its own gap list better than I can reconstruct one — its
local graph at `gddp/nodes/*.yaml` currently has **15 of 33 nodes not
`complete`** (8 `in_progress`, 6 `planned`, 1 `structure-ready`). I spot
checked several of the `in_progress` ones against code rather than trusting
the status field blindly; findings below (code evidence, not just YAML
claims).

1. **cockpit-keymap** (`in_progress`) — goal: shared f=fire/v=verify/a=accept/
   o=output/;=fzf key grammar across Deck and Verify. Evidence: mostly
   built — `hub-rs/src/keymap.rs:25-68` implements `map_deck`/`map_verify`
   with exactly this grammar, and has unit tests (`keymap.rs:222-232`)
   asserting `f`→fire, `;`→fzf submenu, not confused with each other. What's
   plausibly left: eval B4 (human triple-fire walkthrough) and B6 human
   review are process/eval items, not code. Size: S (mostly eval/sign-off
   remaining).

2. **deck-runway** (`in_progress`) — goal: bottom "runway" region on Deck
   showing active/queued fires live. Evidence: `hub-rs/src/ui/dashboard.rs:25,31,48`
   wires `crate::ui::runway::height`/`render` into the layout; last 3
   commits (`cfb326a`, `e11d3fa`, `f278af3`) are all runway/reconcile-freeze
   fixes dated today, suggesting this is actively being iterated, not
   stalled. Size: S-M (active).

3. **deck-verification-review** (`in_progress`) — goal: to_be_verified
   packets surfaced distinctly, verify pass marks done/validated. Evidence:
   `hub-rs/src/app.rs` has a `Screen::Verify`, `Path1Mode::Verify`, and a
   test `enter_on_to_be_verified_opens_verify` (app.rs:975-990) confirming
   Enter on a `to_be_verified` row opens the Verify screen. Backend side
   (`lib/validate.zsh`) is fully built (verify commands run, validation.json
   written, done/validated transition). What's plausibly incomplete: the
   node's own "human-decision... accept/refire/defer" UI framing — I saw
   `a`=accept wired in keymap.rs but no refire/defer action distinct from
   plain refire-via-fire. Size: M.

4. **create-baseline-flow / create-recon-tools / create-task-authoring**
   (all `in_progress`) — Path 0 "Create Task" guided lane (recon tools,
   packet authoring, preview-before-save). Evidence of partial build:
   `hub-rs/src/ui/recon.rs` (66 lines) and `hub-rs/src/task_draft.rs`
   (236 lines per node's required_artifacts) exist; `lib/recon.zsh` grew to
   342 lines (was ~76 lines under the old spec). Not verified line-by-line
   against each acceptance bullet (r=recon, ask-a-question, files/editor/tree,
   clipboard-brief) — would need a live TUI walkthrough to confirm. Size: M
   each, likely mostly built given file sizes.

5. **deck-action-wiring / deck-baseline-ui** (`in_progress`) — focused
   packet actions (f/o/Enter/v) and header/full-width readability. Evidence:
   keymap.rs coverage above suggests action wiring is largely done;
   dashboard.rs (316 lines) is sizeable. "full-width-reading" /
   "readable-empty-states" acceptance bullets are UI-polish and not
   independently verifiable without running the TUI. Size: S-M.

6. **create-converge-fire-or-deck / create-fzf-everywhere /
   create-prompt-skill-reuse / deck-fzf-navigation / deck-polish-hardening /
   packet-schema-align** (`planned`) — no code evidence searched for these
   beyond what's cited above; genuinely queued, not started per the repo's
   own graph. `packet-schema-align` is notable: `schema/packet.schema.json`
   is still only 19 lines/one `state` enum
   (`["open","done","error"]` — schema/packet.schema.json line 19) that has
   **not** been updated for the new `queued/in_progress/to_be_verified/
   validated` states used everywhere else in the codebase. This is a real,
   concrete drift: `aa_validate_packet` validates against a schema whose
   `state` enum no longer matches what `lib/ledger.zsh`/`lib/reconcile.zsh`
   actually write. Evidence: `schema/packet.schema.json:19` vs
   `lib/ledger.zsh:61-85`. Size: S (one enum to widen, but touches whatever
   else reads `.state` off packets).

7. **create-linear-surface** (`structure-ready`, its own status tier, not
   `in_progress`/`planned`) — per node file, structural scaffolding exists
   but isn't wired end to end; commit `a7c6ea9` ("Phase C linear create —
   command/insert, f/s on prepare") suggests active work. Size: M.

Not independently re-derived beyond the repo's own list — Sab, this list is
me reading and spot-verifying the repo's own `gddp/nodes/*.yaml`
`status != complete` set (15 nodes), not a from-scratch invention. Treat the
"Evidence:" lines as what I actually checked; the rest of each node's
acceptance bullets are unverified claims from the YAML.

---

## 4. Loop-readiness (repo-side only)

- **Test runner:** zsh side has one — `tests/acceptance.zsh`, runs clean,
  no framework needed (`zsh tests/acceptance.zsh`). Rust side has
  `hub-rs/tests/render.rs` but **no cargo/rustc available in this
  environment** to invoke it; whatever executor lane runs GDDP verify
  against this repo needs a Rust toolchain reachable, or Rust-side nodes
  can't be verified by running tests, only by code inspection.
- **No CI config found** — no `.github/workflows/`, no `.gitlab-ci.yml`,
  nothing under repo root that looks like CI. Test suite must be invoked by
  hand or by the executor's own runbook.
- **Two parallel UIs (zsh deck.zsh vs hub-rs)** — not a blocker, but any
  node whose `required_artifacts` point at `hub-rs/src/*` needs a Rust-aware
  executor; nodes pointing at `lib/*.zsh` need only zsh+jq. Mixing both in
  one node (e.g. `deck-verification-review` lists both `lib/validate.zsh`
  and `hub-rs/src/app.rs`) means an executor lane needs both toolchains.
- **Repo carries its own `gddp/` directory** (project.yaml, nodes/,
  executor-receipts/, CANONICAL.md, README.md) that already implements a
  local receipt convention (`gddp/docs/executor-receipts.md`,
  `gddp/executor-receipts/TEMPLATE.md`) and a `.gddp/` scratch dir at repo
  root with `decision.md`/`patch.diff`/`result-summary.md` from a prior run.
  This is a second GDDP surface independent of `gddp-config`/
  `gddp-runtime` — worth being aware of so work isn't duplicated or graphs
  don't collide, but it's not a technical blocker to the executor loop.
- **`lib/validate.zsh`'s `aa_gddp_verify`** actively shells out to
  `python -m scripts.runtime.verification.cli` inside
  `$AA_GDDP_RUNTIME_ROOT` (defaults to `$HOME/gddp-runtime`) — i.e. this
  repo already has a live integration point calling back into
  gddp-runtime's verifier. Confirmed present at `lib/validate.zsh:100-180`.
- No unusual repo layout otherwise — standard `bin/`, `lib/`, `tests/`,
  `schema/`, `docs/`, plus the Rust crate under `hub-rs/`. jq is the only
  external zsh-side dependency (`aa_require_jq`).
