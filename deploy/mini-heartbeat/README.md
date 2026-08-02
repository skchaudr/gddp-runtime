# mini-heartbeat

Dormant control-plane pack for **sab-mini** (macOS). Install anytime; nothing
ticks until you explicitly arm.

Primary plane today: **pi-big** (transitioning to **sab-mini** per `TOPOLOGY.md`).
Cutover steps: **`CUTOVER.md`**. This kit does not replace pi-big until armed.

## What this is

| Piece | Role |
|---|---|
| `bin/install-dormant.sh` | Clone layout, write env, load LaunchAgents **disabled** |
| `bin/arm.sh` | Enable + start intake + heartbeat (requires `MINI_HEARTBEAT_ARM=1`) |
| `bin/disarm.sh` | Stop + disable LaunchAgents on mini |
| `bin/disarm-source.sh` | Stop big-ssd intake + comment heartbeat cron (run on big-ssd) |
| `bin/smoke.sh` | DeepSeek via pass, intake process, one dry heartbeat |
| `launchd/*.plist` | macOS services; default `RunAtLoad=false` |
| `env/gddp.env.example` | Paths + secret resolver commands — no secrets |

**Not in git:** `pass` store, GPG keys, live `db/queue.db`, webhook secrets.

## Dormancy contract

1. `install-dormant` may place files and register plists that do **not** start.
2. `arm.sh` exits unless `MINI_HEARTBEAT_ARM=1`.
3. Only one plane should run heartbeat + intake at a time. Arm mini only after
   `disarm-source` on big-ssd (or accept split-brain).

## Suggested flow

Full checklist: **`CUTOVER.md`**. Short version:

```bash
# On sab-mini — once, anytime
cd ~/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/install-dormant.sh

# When you want mini live
# 1) On big-ssd:
bash deploy/mini-heartbeat/bin/disarm-source.sh
# 2) Optional: transfer the SQLite-native state snapshot described below
# 3) On sab-mini:
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh
bash deploy/mini-heartbeat/bin/smoke.sh
# 4) Repoint GitHub webhook / tunnel at mini

# Park mini again
bash deploy/mini-heartbeat/bin/disarm.sh
# Re-enable big-ssd intake + cron manually if needed
```

## State snapshots

Runtime state stays out of git (`db/`, `jobs/`, `events/`). `queue.db` uses
SQLite WAL mode: the main file's mtime advances at checkpoint rather than every
commit, so monitor freshness with application timestamps queried from SQLite.
Copying the main file alone can also omit uncheckpointed WAL data.

Use SQLite's online backup command for a consistent queue snapshot, including
committed WAL content. Archive `jobs/` and `events/` separately:

```bash
# on the active plane
repo="$HOME/repos/gddp-runtime"
stamp="$(date +%Y%m%d-%H%M%S)"
queue_snapshot="/tmp/queue-$stamp.db"
sqlite3 "$repo/db/queue.db" ".backup '$queue_snapshot'"
sqlite3 "$queue_snapshot" 'PRAGMA journal_mode=DELETE;' >/dev/null
test "$(sqlite3 "$queue_snapshot" 'PRAGMA integrity_check;')" = ok
tar czf "/tmp/gddp-runtime-files-$stamp.tar.gz" -C "$repo" jobs events
# copy both artifacts; restore the queue snapshot as db/queue.db before arm
```

The queue backup and the `jobs/`/`events/` archive complete at different times;
together they are not one application-consistent snapshot while writers are
active. When cross-store consistency matters (including control-plane cutover),
disarm intake and heartbeat writers first and run both captures while they stay
quiesced; follow `CUTOVER.md` for the canonical order.

Refresh at arm time if you care about queue continuity.

## Secrets on mini

- `pass show api/deepseek` (bridge default) or export `DEEPSEEK_API_KEY`
- `pass show api/jules` (Jules API adapter default) or export `JULES_API_KEY`
- `GDDP_LOCAL_SUBPROCESS_ARGV` + `GDDP_LOCAL_SUBPROCESS_SPOOL_DIR` for local execution
- `pass show gddp/webhook-secret` (or `GDDP_WEBHOOK_SECRET_CMD`)
- `gh auth login` for Jules dispatch (`GITHUB_TOKEN` / `GH_TOKEN`)
- Import the headless GPG key used for `pass` on big-ssd if you sync the store
