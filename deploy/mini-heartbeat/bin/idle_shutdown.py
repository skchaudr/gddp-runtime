#!/usr/bin/env python3
"""
GDDP Host Idle Shutdown Monitor

Monitors system activity (active SSH sessions, CPU load average, and running GDDP jobs).
If the host remains continuously idle for a configured threshold (default: 180 minutes / 3 hours),
triggers a system shutdown.

Intended to run periodically (e.g., every 15 minutes) via systemd timer or cron.
"""

import os
import sys
import time
import json
import subprocess
import argparse
from pathlib import Path

STATE_FILE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "gddp_idle_shutdown_state.json"
if not STATE_FILE.parent.exists():
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        STATE_FILE = Path("/tmp/gddp_idle_shutdown_state.json")

def check_active_ssh_users() -> int:
    """Returns number of logged-in SSH users via 'who'."""
    try:
        res = subprocess.run(["who"], capture_output=True, text=True, check=False)
        lines = [line for line in res.stdout.strip().splitlines() if line]
        return len(lines)
    except Exception:
        return 0

def check_cpu_load_5min() -> float:
    """Returns 5-minute CPU load average."""
    try:
        return os.getloadavg()[1]
    except Exception:
        return 0.0

def check_active_gddp_jobs() -> bool:
    """Checks if active heartbeat runner or droid/pi executor processes exist."""
    try:
        res = subprocess.run(["pgrep", "-f", "python3.*(heartbeat.runner|jobs_status|droid|pi)"], capture_output=True, text=True, check=False)
        return res.returncode == 0 and len(res.stdout.strip()) > 0
    except Exception:
        return False

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"accumulated_idle_minutes": 0, "last_check_ts": 0}

def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to save idle state file: {e}\n")

def main():
    parser = argparse.ArgumentParser(description="GDDP Idle Shutdown Monitor")
    parser.add_argument("--idle-minutes", type=int, default=180, help="Total idle minutes before shutdown (default: 180)")
    parser.add_argument("--interval-minutes", type=int, default=15, help="Check interval in minutes (default: 15)")
    parser.add_argument("--max-load", type=float, default=0.20, help="Maximum 5-min CPU load to consider idle (default: 0.20)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without actually issuing shutdown")
    args = parser.parse_args()

    # Environment override for idle minutes if present
    idle_limit = int(os.environ.get("GDDP_IDLE_SHUTDOWN_MINUTES", args.idle_minutes))

    ssh_users = check_active_ssh_users()
    cpu_load = check_cpu_load_5min()
    has_active_jobs = check_active_gddp_jobs()

    is_idle = (ssh_users == 0) and (cpu_load <= args.max_load) and (not has_active_jobs)

    state = load_state()

    if is_idle:
        state["accumulated_idle_minutes"] += args.interval_minutes
        state["last_check_ts"] = int(time.time())
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] System is IDLE. (SSH users: {ssh_users}, 5m Load: {cpu_load:.2f}, Active Jobs: {has_active_jobs})")
        print(f"Accumulated idle time: {state['accumulated_idle_minutes']} / {idle_limit} minutes.")

        if state["accumulated_idle_minutes"] >= idle_limit:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Idle limit of {idle_limit} minutes reached! Initiating auto-shutdown.")
            save_state({"accumulated_idle_minutes": 0, "last_check_ts": int(time.time())})
            
            if args.dry_run:
                print("[DRY-RUN] Would execute: sudo /sbin/shutdown -h now 'Auto-shutdown: Host idle for 3 hours'")
            else:
                try:
                    subprocess.run(["sudo", "/sbin/shutdown", "-h", "now", f"Auto-shutdown: Host idle for {idle_limit} minutes"], check=True)
                except Exception as e:
                    # Fallback to systemctl poweroff if shutdown command fails
                    subprocess.run(["sudo", "systemctl", "poweroff"], check=False)
        else:
            save_state(state)
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] System is ACTIVE. (SSH users: {ssh_users}, 5m Load: {cpu_load:.2f}, Active Jobs: {has_active_jobs}). Resetting idle timer.")
        state["accumulated_idle_minutes"] = 0
        state["last_check_ts"] = int(time.time())
        save_state(state)

if __name__ == "__main__":
    main()
