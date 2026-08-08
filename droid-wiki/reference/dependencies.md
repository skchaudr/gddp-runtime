# Dependencies

## Python

`/Users/sab-mini/repos/gddp-runtime/requirements.txt` declares:

| Package | Minimum | Use |
| --- | ---: | --- |
| Flask | 3.0 | Webhook intake and health HTTP server |
| PyYAML | 6.0 | Project graph, node, and configuration YAML |
| Pydantic | 2.0 | Typed runtime/evaluator contracts |
| Anthropic | 0.40 | Optional semantic model integration |

Use Python 3.11 or newer. A fresh host commonly creates a virtualenv and installs the requirements; the verified `khoj-38` config CLI environment also installed `rich`.

## Required host tools

| Tool | Why |
| --- | --- |
| `git` | Repository identity, worktrees, commit/ref evidence, mission verification, protected-branch checks |
| `sqlite3` | Queue inspection, integrity checks, and online backup during cutover |
| `droid` | Direct Droid and Factory mission execution when those adapters are selected |
| `gh` | Authenticated GitHub/Jules-mediated operations and webhook administration |
| `bash` | Mini-heartbeat scripts and rendered systemd service command |
| `curl` | Intake health and invalid-HMAC smoke probes |
| `pass` and `gpg` | Mini secret resolution; unattended launchd may use GPG directly |
| Tailscale | Production Funnel and stable host addressing |

Linux heartbeat hosts additionally need systemd user services and `loginctl enable-linger`. macOS hosts need launchd, `launchctl`, and `plutil`.

## Executor-specific tools

Only install the executors a graph may select: Droid, Jules CLI/API authentication, Pi evaluator harness, model proxies, or other argv targets. Verify each binary and model route before arming. The fresh-host guide records Droid 0.186.0 on `khoj-38`; version-specific behavior should be tested rather than assumed.

No API key, GPG key, password store, queue database, job spool, or event archive belongs in a machine/container image.
