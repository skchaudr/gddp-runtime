# Lore

GDDP Runtime did not start as a control plane. It started as a single webhook listener and a heartbeat script, and it grew outward from there. This page is the narrative history of how that happened, told in eras.

## Eras

### OpenClaw heartbeat era (Mar 2026)

24 commits in March 2026. The project began as a webhook intake plus a heartbeat dispatch loop. `scripts/heartbeat.py` was the original entry point: a single script that polled for events, matched them to work, and dispatched. `scripts/intake_server.py` and `scripts/init_db.py` were created in this era, and both are still actively used today. The state model was minimal: an `events` table and a `jobs` table, enough to keep the loop running without losing work.

The shape of the system was already there in embryo: webhook in, normalize, classify, scope-check, dispatch, record. But every step was hardcoded into one script.

### Modular heartbeat and return path (Apr-May 2026)

33 commits across April and May 2026. April was a quiet month (5 commits), mostly handoff and setup for the rewrite. May was where the work landed (28 commits).

The hardcoded dispatcher was replaced with modular components: `graph_reader.py`, `classifier.py`, `scope_checker.py`, `job_factory.py`, `state_recorder.py`, and `dispatcher.py`. Each got a single responsibility and its own test surface. The return router was added in this era, establishing the receipt-based return flow that the rest of the system now depends on. A merged PR became a structured receipt rather than a silent writeback, which is the invariant that lets the human review gate mean anything.

`scripts/heartbeat.py` was superseded by `scripts/runtime/heartbeat/runner.py` around this time. The original file is still present in the repo, kept as legacy.

### Verification system (Jun 2026)

28 commits in June 2026. The two-lane evaluator was built in this era.

Lane 1 (criteria) came first: deterministic probes that check acceptance criteria using regex, file existence, command execution, and tier configuration. Indeterminate criteria get escalated to a semantic LLM agent with read-only tools. A 12-row decision matrix combines deterministic and semantic results into a criteria verdict.

Lane 2 (integrity) came next: a fresh-eyes drift review that asks whether the work preserves the node's intended role in the project graph. The integrity combiner takes the worst-of the two lanes, so integrity can only worsen a verdict, never upgrade it.

The bridge wired verification into the return path as a subprocess, so an evaluator crash, hang, or timeout cannot take down the return router. The verification system grew from a single `verify_node.py` into a multi-module system with deterministic, semantic, and integrity lanes, each with its own tests.

### Integrity lane and live deployment (Jul 2026)

79 commits in July 2026, the busiest month by a wide margin. This is where everything from the spring went live.

Two-lane evaluation went into production. The integrity harness runner was added. The retry loop was implemented: when a verdict comes back non-pass with evidence-referenced findings and the retry budget has room, the return router re-dispatches with findings injected into the issue body. The decision loop (`decision_loop/engine.py`) was wired in as a reasoning layer on top of the heartbeat, waking on cron or webhook to decide whether to verify, dispatch, escalate, or no-op.

Live Pi deployment was hardened in this era. The terminology was locked: the GDAD-to-GDDP rename touched code, PR-body templates, and issue titles. Canon documents were declared, settling which sources are authoritative when prose and code disagree.

### Retry proof, incident, and the mini cutover (mid-Jul 2026)

Three days that moved production off the Raspberry Pi and proved the retry loop with a live run.

**The canary retry proof (Jul 11–12).** A deliberately booby-trapped node, `canary-retry-proof` (`job_20260711T17104259`), was dispatched: its third acceptance criterion required a `docs/echo-usage.md` file that was intentionally omitted from the goal and required-artifacts list, so the executor would miss it on attempt one. It did. The evaluator failed the criterion with a file-path evidence reference, the retry loop fired, and attempt two landed with all three criteria met — two result rows in the `results` table (2026-07-11T17:35Z, 2026-07-12T07:16Z). First live proof of the retry mechanism described in [Retry loop](features/retry-loop.md).

**The canary-scope incident (Jul 12).** Intake resolved its webhook secret by ssh-ing to pi-big at startup; that ssh dependency failed silently and took webhook verification down. Full analysis in `docs/postmortem-canary-scope-2026-07-12.md`. During the recovery, a hot-patch was applied to production via `scp` without a matching commit/pull, leaving the mini's checkout desynced from origin — a second, quieter failure discovered only the next day. Both failure classes now have standing countermeasures: `AGENTS.md` mandates git-pull-first (no remote file patches) on production hosts, and `deploy/mini-heartbeat/bin/baseline.sh` checks git sync and secret-resolver locality on every run.

**The pi-big → sab-mini cutover (Jul 12–13).** Production moved from the Pi's systemd/cron model to a Mac Mini running two launchd agents (`com.gddp.intake`, `com.gddp.heartbeat`) behind a Tailscale Funnel URL, with 12 repo webhooks repointed. Runbook: `deploy/mini-heartbeat/CUTOVER.md`; verified state: `TOPOLOGY.md`; session trail: `.handoffs/036-mini-production-docs-baseline.md` and `.handoffs/037-mini-clean-baseline-startup.md`. The secrets migration completed the cutover on Jul 13: the `pass` store and automation GPG key `F0928E218506BB29` moved onto the mini, killing the ssh-to-pi-big resolver. The migration surfaced a platform gotcha worth remembering: Homebrew's `pass` resolves GNU getopt by shelling out to `brew --prefix` at runtime, which hangs forever under launchd — so the production secret commands call `gpg --batch --quiet --decrypt` directly (see the comment in `deploy/mini-heartbeat/env/gddp.env`).

**Human-gate tooling (Jul 13).** Two operator tools landed the same day: `scripts/node_status.py`, the first CLI for the human review gate (list/show/set across all eleven canon queue states, every change writing an audit row to `decision_results` — a table that had zero rows until a human used it), and `deploy/mini-heartbeat/bin/baseline.sh`, a tiered production verifier (OK / DEGRADED / BROKEN) that makes "the baseline is green" an exit code instead of a claim.

## Longest-standing features

`intake_server.py` and `init_db.py` date from March 2026 and are still actively used. The webhook intake and the SQLite schema they establish have outlived every rewrite around them. `heartbeat.py` is still present in the repo as legacy, replaced by `heartbeat/runner.py` but not deleted.

## Deprecated features

- `scripts/heartbeat.py` was replaced by the modular `scripts/runtime/heartbeat/runner.py`. The original file is kept as legacy.
- The `~/opclaw` legacy execution surface is retired. `deploy.sh` still snapshots there, but nothing runs from it.
- The `OPCLAW_ROOT` environment variable is a dead fallback. `GDDP_RUNTIME_ROOT` is the canonical root path resolution variable.

## Major rewrites

The phase 2 modular heartbeat replaced the hardcoded dispatcher, splitting one script into six modules with distinct responsibilities. The integrity lane draft merge restructured the verification system, moving it from a single script to a multi-lane architecture. The GDAD-to-GDDP terminology rename touched code, PR-body templates, and issue titles in one coordinated pass.

## Growth trajectory

The project started as a single-repo webhook intake. It grew into a two-repo system: `gddp-config` holds human-owned project truth (schemas, templates, project graphs as YAML), and `gddp-runtime` holds the execution machinery. The verification system grew from a single `verify_node.py` into a multi-module system with deterministic, semantic, and integrity lanes. The decision loop was added as a reasoning layer on top of the heartbeat, turning the runtime from a dispatch loop into something that can reason about what to do next.
