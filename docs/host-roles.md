# Host Roles — OpenClaw Topology

Last updated: 2026-03-21

---

## Intended Roles

| Host | Tailscale Name | Role | OpenClaw Service |
|---|---|---|---|
| Big Pi (SSD) | `ssd-big` | **Sole gateway** | `openclaw-gateway.service` |
| Small Pi (SSD) | `ssd-small` | Worker node | `openclaw-node.service` (planned) |
| Mac (M1 Air) | — | Operator host, optional node | None by default |

---

## ssd-big — Sole Gateway

**Purpose**: Central OpenClaw gateway. All routing, channel dispatch, and agent coordination flows through here.

**Expected state**:
- `openclaw-gateway.service` enabled and running
- No node or tunnel services
- `gateway.bind = loopback`
- `gateway.auth.mode = token`
- `gateway.tailscale.mode = serve` (tailnet-only, not Funnel)
- Single `openclaw` binary at `/usr/bin/openclaw`

**Verification**:
```bash
ssh sab-ssd@100.73.28.125
openclaw --version                                    # expect 2026.3.13+
systemctl --user status openclaw-gateway.service      # expect active (running)
systemctl --user list-unit-files | grep openclaw      # expect only gateway
ss -tlnp | grep 18789                                # expect 127.0.0.1 only
```

---

## ssd-small — Worker Node

**Purpose**: Remote execution node. Receives targeted work from the gateway. Does not run its own gateway or channels.

**Expected state** (after cutover):
- `openclaw-node.service` enabled and running
- `openclaw-gateway.service` disabled or removed
- `openclaw-ssh-tunnel.service` disabled or removed
- Node configured to connect to `ssd-big` gateway

**Verification**:
```bash
ssh sab-ssd@100.87.206.30
openclaw --version                                    # expect 2026.3.13+
systemctl --user status openclaw-node.service         # expect active (running)
systemctl --user list-unit-files | grep openclaw      # expect only node
```

**Current state** (pre-cutover): Running as standalone gateway. Cutover pending.

---

## mac — Operator Host

**Purpose**: Human operator workstation. Runs Claude Code, manages repos, reviews PRs. Not part of the always-on topology.

**Expected state**:
- No persistent OpenClaw services
- `openclaw` CLI available for ad-hoc commands and node targeting
- Optional: temporary node mode for local tool execution

**Verification**:
```bash
which openclaw                                        # expect on PATH
openclaw --version                                    # expect 2026.3.13+
```

---

## Topology Rules

1. **One gateway**: Only `ssd-big` runs `openclaw-gateway.service`. No second gateway.
2. **Node targeting**: Work lands on `ssd-big` by default. Use explicit node targeting for `ssd-small` or `mac`.
3. **No tunnels**: The old SSH tunnel topology is retired. Nodes connect directly over Tailscale.
4. **Channel ownership**: All messaging channels (WhatsApp, Telegram) run on the gateway (`ssd-big`).

---

## Remote Access Path

Big Pi uses `bind: loopback` + `tailscale.mode: serve` (tailnet-only, not Funnel).

- Tailscale Serve URL: `https://ssd-big.tail02ac6f.ts.net`
- Proxies to: `http://127.0.0.1:18789`
- Auth: token (explicit, not tokenless Tailscale identity)
- Gateway is never directly exposed on the network

Nodes connect via the Tailscale Serve URL with the gateway token.

---

## Pre-Cutover Blockers

- [x] Big Pi: sole gateway running with Tailscale Serve enabled
- [ ] Small Pi: disable `openclaw-gateway.service`, configure as node pointing to `ssd-big`
- [ ] Validate node connection: `openclaw nodes list` from `ssd-big` shows `ssd-small`
