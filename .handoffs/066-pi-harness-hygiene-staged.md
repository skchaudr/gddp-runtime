# 066 — pi-harness-hygiene staged; run nodes A LOT

------------------------------------------------ Agent Section START

Date: 2026-08-05
Worktree: /Users/sab-mini/repos/gddp-runtime (primary); ~/repos/gddp-config; ~/.pi (target repo)
Branch: main (all repos)

## Empirical Reality

`pi-harness-audit` canary on khoj-38 completed 5/5 provisional (droid executor, first fully autonomous run; reports substance-verified strong, incl. the two flagged ones). `pi-harness-hygiene` (two concurrent droid nodes on sab-mini's `~/.pi`) is authored, validated, and staged for dispatch — **waiting only on Sab's "go"**. khoj-38 is DOWN for ~24h; all near-term runs are sab-mini-local. **Sab's directive for the next phase: run nodes A LOT — dispatch volume is the immediate goal; the post-dispatch pause is for assessing graph shape, not for stopping.**

### Scope touched (gddp-runtime)

- `scripts/runtime/repo_resolver.py` + wiring (bridge/runner/engine) — one resolver, graph id ≠ dirname (`09eb58e`)
- `scripts/runtime/verification/deterministic/constraints.py` — tolerate non-string YAML items, warn+skip (`185e6fe`)
- `scripts/runtime/heartbeat/runner.py` — frontier re-check after finalize (`66f4ae5`) + reader-cache invalidate (`9991c8e`)
- `scripts/adapters/local_subprocess_adapter.py` — `executor_name` class attr; droid retries stay droid (`727bb7a`)
- `scripts/runtime/heartbeat/{state_recorder,reconciler}.py` + `scripts/init_db.py` — plumbing retry budget split 3+3 (`afebfda`)
- `deploy/mini-heartbeat/systemd/` — Linux heartbeat units, `KillMode=process` (`d45afaf`)
- `deploy/mini-heartbeat/FRESH-HOST-STANDUP.md` (`985165f`); `deploy/_archive/` — dead Big Pi artifacts archived (`536a2d8`)
- `docs/postmortem-2026-08-05-vm-harness-audit-canary.md` + `docs/artifacts/2026-08-05-yaml-dict-verifier-crash.html`

### Scope touched (gddp-config)

- `graphs/vm-harness-audit/` — 5 nodes provisional (`d6051d1`); quoted `Read-only:` scalars (`e68ed45`)
- `graphs/pi-harness-hygiene/` — NEW: project.yaml + 2 nodes, repo `/Users/sab-mini/.pi` (`c7e0ba1`)
- `scripts/validate.py` + `import_node.py` — `implicit_mapping_in_list` promoted to ERROR (`4794390`); `VALID_EXEC_MODES` += `droid` (`c7e0ba1`); `scripts/test_validate.py` regression pins
- `bin/gddp` — launcher resolves config root from own path (`ebeeb8e`)

### Constrained areas touched

- sab-mini `gddp.env` (gitignored, local): droid argv model pinned to `custom:Grok-4.5-sub-(Hermes)-0` — Hermes-routed, unambiguous.

### Current Git state

All repos clean and synced with origin (gddp-runtime `afebfda`, gddp-config `c7e0ba1`). VM checkouts frozen mid-run until host returns (runtime had all fixes through `d45afaf`-era pulls; needs `git pull` on return).

### Artifacts

- `.handoffs/066-pi-harness-hygiene-staged.md` — this file
- `docs/postmortem-2026-08-05-vm-harness-audit-canary.md` — action table; #3 validator done, #4 retry split done
- `docs/artifacts/2026-08-05-yaml-dict-verifier-crash.html` — glm-5.2-built incident explainer
- gddp-config `deploy/mini-heartbeat/FRESH-HOST-STANDUP.md` (runtime repo) — verified fresh-host path

### Resume point

On Sab's "go": inject dispatch events for BOTH `pi-harness-hygiene` nodes concurrently (local heartbeat, local droid, worktrees of `~/.pi`), then hands-off watch per fire protocol (I observe; delegates fix from written repros). After both land provisional: full pause; Sab assesses whether the machinery earned daily-driver status; then scale node throughput per his directive. Outstanding non-blocking items: Sab rotates DEEPSEEK_API_KEY (appeared in transcripts); on VM return — `git pull` both repos there, Sab reviews/accepts the 5 provisional `vm-harness-audit` nodes (`gddp review` on khoj-38), then the mission-mode graph (settings already configured on sab-mini: Sol orchestrator/worker, Terra validator).

### Key facts the next session must not relearn

- **sab-mini**: `~/.pi` IS the Pi-Coding-Agent checkout (repo-as-home, origin skchaudr/Pi-Coding-Agent). **khoj-38**: repo at `/data/repos/Pi-Coding-Agent`, home is symlink overlay. Never invent a working repo — the canonical tree always already exists.
- Validator errors now bite: quote any scalar containing `:` in node yamls; valid node types are capability/milestone/constraint; exec modes include `droid`.
- Retry semantics: 3 work attempts + 3 plumbing retries, independent counters (`jobs.plumbing_attempt`); plumbing = died before durable exit state.
- droid flags verified live: use `--enabled-tools` (NOT `--restrict-tools`, doesn't exist); `--tag`, `--log-group-id`, `-o stream-json`, `--session-id` continue / `--fork` exist for future observability/retry work.
- Evaluator receipts carry `context_coverage`; `low` = lanes judged without reading offered canonical docs — fine for binary audits, watch it on intent-heavy nodes.
- Fire protocol + per-report reviewer fanout are standing practice (postmortem lessons), as audit evidence only — no new authority layers.

------------------------------------------------ Agent Section END

Do NOT edit this file past this point.
