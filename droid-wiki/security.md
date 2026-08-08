# Security boundaries

GDDP protects ingress, secret resolution, executor git behavior, and the separation between evidence and graph truth. Active contributor: Saboor.

## Webhook authentication

`/Users/sab-mini/repos/gddp-runtime/scripts/intake_server.py` verifies GitHub's `X-Hub-Signature-256` as HMAC-SHA256 over the raw request body and compares it with `hmac.compare_digest`. A bad signature returns 401 before payload persistence or database insertion.

The intake resolves its secret in this order:

1. `GITHUB_WEBHOOK_SECRET`, primarily an interactive override.
2. `GDDP_WEBHOOK_SECRET_CMD`.
3. Default command `pass show gddp/webhook-secret`.

Production on `sab-mini` keeps the password store under `~/.password-store` with GPG encryption. A command resolver keeps secret values out of checked-in env files and rendered deployment templates. In headless launchd, the production command may use `gpg --decrypt` directly because `pass` can block waiting for interaction.

Intake fails closed. If no secret resolves, startup exits and `/health` reports 503 unless `GDDP_INTAKE_INSECURE=1` is explicitly set. That override is for localhost development only; it disables signature verification and must never be exposed through Funnel or a tunnel.

## Mission push protection

Factory mission workers are allowed one push shape: `git push origin HEAD:refs/heads/<engagement-branch>`. `/Users/sab-mini/repos/gddp-runtime/scripts/adapters/mission_push_guard.py` applies two controls:

- A `git` executable placed first on `PATH` rejects force options, alternate remotes, and alternate refspecs, and writes an audit record.
- An inherited `core.hooksPath` installs a pre-push hook, so an absolute Git executable still encounters policy.

These controls have a known residual bypass: an absolute Git invocation with `-c core.hooksPath=/dev/null`. Collection therefore verifies again after execution. `/Users/sab-mini/repos/gddp-runtime/scripts/adapters/mission_evidence.py` reads live protected branch tips with `git ls-remote`, checks whether a feature result is reachable from `main` or `master`, and records `completion_quarantine_reason`. A polluted protected branch is quarantined for human review rather than laundered into a valid completion.

## Secret and image rules

- Commit resolver commands and paths, never secret values, password stores, private keys, or API-key files.
- Do not print resolver output in logs or smoke tests.
- Do not bake GPG keys, password stores, GitHub tokens, webhook secrets, or model API keys into VM or container images. Provision them after image creation through the host's secret mechanism.
- `/Users/sab-mini/repos/gddp-runtime/deploy/mini-heartbeat/env/gddp.env.example` and service templates are intentionally secret-free.
- Runtime state (`db/`, `events/`, `jobs/`) is not image content and is excluded from Git.

See [Production hosts](deployment/production-hosts.md) and [Monitoring](how-to-monitor/index.md).
