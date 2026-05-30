# AGENTS.md — gddp-runtime

GitHub webhook intake → classify → scope → queue → execute pipeline.
Python scripts in `scripts/`, deploy configs in `deploy/`, docs in `docs/`.
No requirements.txt — scripts use stdlib + Flask (see `deploy/setup.sh`).

## Operator relay

This task may have a live operator on the other end of an HTTPS relay
(see https://github.com/skchaudr/jules-relay).

Env vars (set per-session):
- `RELAY_URL` — base URL of the relay
- `RELAY_TOKEN` — bearer token

On session start, open an SSE subscription:

```bash
curl -N "$RELAY_URL/events" -H "Authorization: Bearer $RELAY_TOKEN" &
```

Behavior rules:
- Post `STATE:` before any high-risk or irreversible step (deploy, migration,
  destructive file ops, network calls with side effects).
- If a message arrives with `from=m1` and `kind=ASK`, **pause the specific
  gated decision it refers to** until an `ACK` arrives from `m1`, or until
  the relay becomes unreachable. Continue everything else.
- If the relay is unreachable (connection refused, 5xx, timeout): proceed
  per the original task brief, EXCEPT for actions explicitly marked
  "operator-gated" in the task.
- NEVER place secrets, credentials, private URLs, tokens, SSH details, or
  sensitive repo contents in relay messages. Coordination text only.

### Message envelope

`POST $RELAY_URL/msg` with `Authorization: Bearer $RELAY_TOKEN`:

```json
{ "from": "jules", "kind": "STATE" | "ASK" | "ACK", "text": "..." }
```

`text` must be ≤ 4096 chars, non-empty.

## Environment

| Var | Purpose | Set by |
|---|---|---|
| `RELAY_URL` | Relay endpoint | Jules session env |
| `RELAY_TOKEN` | Relay auth | Jules session env |
| `GDDP_RUNTIME_ROOT` | Override default runtime root path | Optional |
| `GITHUB_WEBHOOK_SECRET` | Validate incoming webhook signatures | Operator |

## Project snapshot

- **Language:** Python 3.11+ (stdlib + Flask)
- **Install:** `pip install flask` (see `deploy/setup.sh` for full pi-big setup)
- **Test:** `python3 scripts/dry_run.py` (end-to-end fake flow, SQLite only)
- **Lint:** none configured
- **Heavy dirs excluded from git:** `db/`, `jobs/`, `events/` (runtime state, never committed)
- **Key files:** `scripts/intake_server.py`, `scripts/dry_run.py`, `scripts/runtime/`
