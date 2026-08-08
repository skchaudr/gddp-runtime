# VM mission / persistent-pi executor readiness

- **Host:** khoj-38
- **Captured at:** 2026-08-08T02:54:14Z (UTC)
- **Uptime:** 4:31 (load average 0.58, 0.29, 0.21)
- **Node:** `node-02-mission-readiness`
- **Job:** `job_20260808T025248469a5761775f38` (attempt 0)
- **Base commit:** `fb1f10ddb06d60d2f800369dd8725fdb72e7ecce`

## Summary

| Surface | State |
| --- | --- |
| `droid` | **0.189.0** at `/home/sab-mini/.local/bin/droid` |
| `pi` | **0.83.0** at `/usr/bin/pi` (current local_subprocess worker) |
| Docker daemon | **active (running)**, enabled; 26.1.5+dfsg1 |
| Memory | 23 Gi total, ~20 Gi available |
| Root disk `/` | 99G total, 55G avail (43% used) |
| Auto-shutdown timers | **disabled / inactive** (no pending scheduled shutdown) |
| Model auth (`pi`) | **xai/grok-4.5 works**; deepseek / zai / openai-codex **broken** |

**Verdict:** Host is ready for droid missions and persistent pi executors on the
working `xai/grok-4.5` path. Do not pin workers to deepseek, zai, or openai-codex
until their credentials are repaired on this host.

## `droid --version`

```text
0.189.0
```

Path: `/home/sab-mini/.local/bin/droid`.

Mission-oriented check (catalog reachability for configured Grok Hermes custom
model via `droid exec --list-tools -m 'custom:Grok-4.5-sub-(Hermes)-0'`):

```text
Available tools for Grok 4.5 sub (Hermes)
Autonomy: read-only
...
  • ProposeMission (Propose Mission) - status: allowed
  • StartMissionRun (Start Mission Run) - status: allowed
```

## Docker

### `docker --version`

```text
Docker version 26.1.5+dfsg1, build a72d7cd
```

### Daemon status

```text
systemctl is-active docker  → active
systemctl is-enabled docker → enabled
```

```text
● docker.service - Docker Application Container Engine
     Loaded: loaded (/usr/lib/systemd/system/docker.service; enabled; preset: enabled)
     Active: active (running) since Sat 2026-08-08 00:59:56 UTC; 1h 53min ago
TriggeredBy: ● docker.socket
   Main PID: 23727 (dockerd)
      Tasks: 11
     Memory: 37.2M (peak: 41.2M)
```

```text
docker info --format ...
ServerVersion=26.1.5+dfsg1 Containers=0 Running=0 Images=1
```

## Resources

### `free -h`

```text
               total        used        free      shared  buff/cache   available
Mem:            23Gi       3.0Gi        16Gi        44Mi       4.4Gi        20Gi
Swap:             0B          0B          0B
```

### `df -h /`

```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        99G   40G   55G  43% /
```

## Model auth matrix (`pi --print --no-session --no-tools`)

Prompt used for each row: `Reply with exactly the single word READY and nothing else.`
Timeout budget: 90s. Credentials probed via `pi auth print-api-key` /
`print-bearer-token` (presence only; secrets not recorded).

| Model | Credential probe | Live smoke | Notes |
| --- | --- | --- | --- |
| `xai/grok-4.5` | PRESENT (oauth/token material) | **exit 0 → `READY`** | Works. Matches current `GDDP_LOCAL_SUBPROCESS_ARGV` pin. |
| `deepseek/deepseek-v4-flash` | ABSENT | **exit 1** | `Failed to resolve API key for provider "deepseek" from shell command: pass show api/deepseek` (`pass` not installed on this host). |
| `zai/glm-5.2` | ABSENT | **exit 1** | Resolves a macOS keychain command: `security find-generic-password -s 'zai-glm-api-key' ... /Users/sab-mini/Library/Keychains/...` — not valid on Linux VM. |
| `openai-codex/gpt-5.6-sol` | ABSENT / invalid refresh | **exit 1** | `OAuth refresh failed ... Could not validate your refresh token. Please try signing in again.` (401 `invalid_refresh_token`). |

### Smoke transcripts (stdout/stderr)

**xai/grok-4.5** — success:

```text
exit=0
stdout:
READY
stderr:
(empty)
```

**deepseek/deepseek-v4-flash** — broken:

```text
exit=1
stderr:
API key auth failed for provider deepseek: Failed to resolve API key for provider "deepseek" from shell command: pass show api/deepseek
```

**zai/glm-5.2** — broken:

```text
exit=1
stderr:
API key auth failed for provider zai: Failed to resolve API key for provider "zai" from shell command: security find-generic-password -s 'zai-glm-api-key' -a ssd -w /Users/sab-mini/Library/Keychains/login.keychain-db
```

**openai-codex/gpt-5.6-sol** — broken:

```text
exit=1
stderr:
OAuth refresh failed for openai-codex: OpenAI Codex token refresh failed (401): {
  "error": {
    "message": "Could not validate your refresh token. Please try signing in again.",
    "type": "invalid_request_error",
    "param": null,
    "code": "invalid_refresh_token"
  }
}
```

`~/.pi/agent/auth.json` provider slots present (names only): `openai-codex`, `xai`, `clinepass`.

Active executor pin from `deploy/mini-heartbeat/env/gddp.env`:

- local_subprocess → `pi --model xai/grok-4.5`
- droid subprocess → `droid exec ... -m custom:Grok-4.5-sub-(Hermes)-0`

## Auto-shutdown timers

### `systemctl list-timers --all` (shutdown-related)

No shutdown/halt/poweroff/idle timers are scheduled. Full timer list at capture
time had 10 entries (oslogin cache, apt, tmpfiles, dpkg backup, exim, logrotate,
e2scrub, man-db, fstrim) — none auto-shutdown.

### Unit status

| Unit | `is-enabled` | `is-active` | Notes |
| --- | --- | --- | --- |
| `auto-shutdown.timer` | **disabled** | **inactive** | Stopped 2026-08-07 23:59:30 UTC; Trigger: n/a |
| `auto-shutdown.service` | static | **inactive** | oneshot monitor (8h hard / 6h idle); not running |
| `auto-shutdown-12h.service` | **disabled** | **inactive** | Would `shutdown -h +720`; disabled so not armed at boot |

```text
○ auto-shutdown.timer - Run Auto Shutdown Monitor every 5 minutes
     Loaded: loaded (/etc/systemd/system/auto-shutdown.timer; disabled; preset: enabled)
     Active: inactive (dead)
    Trigger: n/a

○ auto-shutdown.service - Auto Shutdown Monitor (8h hard / 6h idle)
     Loaded: loaded (/etc/systemd/system/auto-shutdown.service; static)
     Active: inactive (dead)

○ auto-shutdown-12h.service - Auto shutdown 12 hours after boot
     Loaded: loaded (/etc/systemd/system/auto-shutdown-12h.service; disabled; preset: enabled)
     Active: inactive (dead)
```

### Pending shutdown

```text
/run/systemd/shutdown/scheduled → absent
busctl ... ScheduledShutdown → (st) "" 18446744073709551615   # empty string, no deadline
```

`hibernate.target`, `suspend.target`, `sleep.target`, `shutdown.target`,
`poweroff.target` are all inactive/dead. `poweroff.target` is disabled.

## Readiness implications

1. **OK to run** droid missions and persistent `pi` executors on this VM with the
   current Grok 4.5 pins.
2. **Docker is up** for any containerized mission/worker needs (1 image present,
   0 containers).
3. **Headroom is adequate** (~20 Gi mem available, ~55G disk free, no swap).
4. **Auto-shutdown will not kill long runs** while the timer/services remain
   disabled/inactive (verify again before multi-day unattended runs).
5. **Auth debt:** repair deepseek (`pass` or direct env key), zai (Linux-native
   secret source — not macOS keychain), and openai-codex (re-login / refresh
   token) before those providers are usable as executor backends here.
