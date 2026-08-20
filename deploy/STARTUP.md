# GDDP Runtime Operations & Startup Runbook

This is the canonical operational guide for starting, inspecting, monitoring, steering, and stopping the GDDP runtime.

---

## 1. Fast Reference: Common Operations

| Action | Host | Command |
|---|---|---|
| **Smoke / Preflight Check** | `sab-mini` | `bash deploy/mini-heartbeat/bin/smoke.sh` |
| **Arm & Start Services** | `sab-mini` | `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh` |
| **Disarm / Stop Services** | `sab-mini` | `bash deploy/mini-heartbeat/bin/disarm.sh` |
| **View Heartbeat Log** | `sab-mini` | `tail -f ~/Library/Logs/gddp-heartbeat.log` |
| **View Intake Log** | `sab-mini` | `tail -f ~/Library/Logs/gddp-intake.log` |
| **Check Runtime Queue** | Any | `python3 scripts/jobs_status.py --summary` |
| **Fleet Watch View** | Any | `gddp watch` |
| **Watch Single Node** | Any | `gddp watch <node_id>` |
| **Steer Live Session** | Any | `gddp steer <node_id> "<guidance message>"` |
| **Operator Node Review** | Any | `gddp node browse --project <project_id>` |

---

## 2. Production Host Startup (`sab-mini`)

Production runs under macOS launchd on `sab-mini` (Tailscale host).

### Step 1: Preflight Verification
Confirm runtime dependencies and secrets resolution before arming:
```bash
cd ~/repos/gddp-runtime
bash deploy/mini-heartbeat/bin/smoke.sh
```
The smoke test verifies:
- Python environment and `scripts/` directory
- `project.yaml` presence in `gddp-config`
- API key resolution (DeepSeek via pass/env for evaluator semantic lane)
- Webhook secret resolution
- Intake service health and HMAC signature rejection (401)
- Plist configuration synchronization with `gddp.env`
- One dry heartbeat execution tick

### Step 2: One-Time Dormant Registration (if new install)
```bash
bash deploy/mini-heartbeat/bin/install-dormant.sh
```

### Step 3: Arm & Start the Services
```bash
MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh
```
This renders the launchd plists with current `gddp.env` values, enables `com.gddp.intake` (port 5050) and `com.gddp.heartbeat`, kicks off the initial interval tick, and outputs confirmation.

### Step 4: Verify Live Operations
Check running logs:
```bash
tail -n 50 -f ~/Library/Logs/gddp-heartbeat.log
```
Check queue status:
```bash
python3 scripts/jobs_status.py --summary
```

### Step 5: Parking / Disarming
When taking the control plane offline or transferring control:
```bash
bash deploy/mini-heartbeat/bin/disarm.sh
```

---

## 3. Live Monitoring & Steer Control

During autonomous execution, operators and supervisory agents observe and guide sessions without interrupting the queue:

- **Fleet Overview (`gddp watch`):** Displays all active attempts, worktree diffs, and silence flags.
- **Node Inspection (`gddp watch <node_id>`):** Shows live worktree git diff against HEAD, newly created files, and recent lifecycle events.
- **Mid-Turn Guidance (`gddp steer <node_id> "<message>"`):** Delivers an operator message into an active executor session mid-turn. The executor receives the guidance before completing, and the return receipt captures the steer message and response.

---

## 4. Fresh Host Stand-up (Linux / systemd)

For deploying the GDDP runtime on a new Linux host (e.g. `khoj-38`, VM, or container):

1. **Checkouts at `$HOME`:**
   ```bash
   git clone <gddp-runtime-url> ~/gddp-runtime
   git clone <gddp-config-url> ~/gddp-config
   ```
2. **Virtual Environment for GDDP CLI:**
   ```bash
   python3 -m venv ~/gddp-config/.venv
   ~/gddp-config/.venv/bin/pip install flask pyyaml rich
   ```
3. **Configure Environment (`gddp.env`):**
   Copy `deploy/mini-heartbeat/env/gddp.env.example` to `deploy/mini-heartbeat/env/gddp.env` and set VM-absolute paths, executor command argv (e.g. `GDDP_DROID_SUBPROCESS_ARGV` or `GDDP_LOCAL_SUBPROCESS_ARGV`), and `DEEPSEEK_API_KEY`.
4. **Install systemd User Units:**
   Copy `deploy/mini-heartbeat/systemd/gddp-heartbeat.service` and `deploy/mini-heartbeat/systemd/gddp-heartbeat.timer` to `~/.config/systemd/user/`.
   ```bash
   loginctl enable-linger $USER
   systemctl --user daemon-reload
   systemctl --user enable --now gddp-heartbeat.timer
   ```
   > ⚠️ **Mandatory systemd Invariant:** Ensure `KillMode=process` is set in the service unit so systemd does not reap child executor sessions when the heartbeat runner tick exits.
5. **Full Reference:** See [`deploy/mini-heartbeat/FRESH-HOST-STANDUP.md`](mini-heartbeat/FRESH-HOST-STANDUP.md).

---

## 5. Queue State Snapshots & Backup

`db/queue.db` operates in SQLite WAL mode. To take a consistent snapshot without shutting down readers:

```bash
repo="$HOME/repos/gddp-runtime"
stamp="$(date +%Y%m%d-%H%M%S)"
queue_snapshot="/tmp/queue-$stamp.db"

# Online SQLite backup (captures WAL)
sqlite3 "$repo/db/queue.db" ".backup '$queue_snapshot'"
sqlite3 "$queue_snapshot" 'PRAGMA journal_mode=DELETE;' >/dev/null
test "$(sqlite3 "$queue_snapshot" 'PRAGMA integrity_check;')" = ok

# Tar ephemeral jobs and events
tar czf "/tmp/gddp-runtime-files-$stamp.tar.gz" -C "$repo" jobs events
```

---

## 6. Critical Invariants & Operational Pitfalls

1. **NEVER Invoke Heartbeat Runner Directly:** Always invoke via `deploy/mini-heartbeat/bin/arm.sh` or `smoke.sh` (or source `deploy/mini-heartbeat/env/gddp.env` via `common.sh`). Direct Python runner calls skip the environment setup, missing `GDDP_LOCAL_SUBPROCESS_ARGV` and spool paths, creating failed jobs.
2. **Launchd Environment Caching:** Editing `gddp.env` does not update running launchd services automatically. You must re-run `MINI_HEARTBEAT_ARM=1 bash deploy/mini-heartbeat/bin/arm.sh` to re-render and reload plists.
3. **Dead Big Pi Artifacts:** Do NOT execute `deploy/_archive/setup.sh` or `deploy/_archive/gddp-intake.service`. Those reference retired topologies (`$HOME/opclaw`, `sab-ssd`).
4. **Git-Only Production Updates:** Production host files update strictly via `git pull --ff-only`. Never use `scp` or direct remote file mutations.
