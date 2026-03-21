# TMUX Protocol

This is the canonical protocol for any long-running SSH work on Big Pi, Small Pi, or related VMs.

## Rule Zero

Never start a cutover, deploy, service migration, or long-running agent session in a raw SSH shell.

If the SSH transport dies, the work must still be recoverable from `tmux`.

## Standard

- One persistent `tmux` session per host: `openclaw`
- Three default windows:
  - `ops` for notes, cwd, and recovery commands
  - `work` for the active task
  - `logs` for `journalctl`, `tail`, and `systemctl status`
- Use additional windows only when there is a concrete second task
- Rename non-default windows to the task name, for example `cutover`, `deploy`, or `rollback`

## Start Or Reattach

From the operator machine:

```bash
bash deploy/tmux-remote.sh sab-ssd@ssd-big
bash deploy/tmux-remote.sh sab-ssd@ssd-small
```

This will:

- create `openclaw` on the remote host if it does not exist
- create the standard `ops`, `work`, and `logs` windows once
- turn on `remain-on-exit` for that session
- attach to the session

If you prefer to do it manually:

```bash
ssh -t sab-ssd@ssd-big 'tmux new-session -A -s openclaw'
```

## Required Workflow

1. Attach to `openclaw` immediately after SSH.
2. In `ops`, leave a short note with the current objective, host, and intended next command.
3. Run the real work only in `work` or another explicitly named task window.
4. Keep `logs` reserved for `journalctl`, `tail -f`, and `systemctl status`.
5. Before detaching, update `ops` with current status, blocker, and the next safe resume command.

## Handoff Format

Leave this in the `ops` window before stepping away:

```text
Host: ssd-big
Task: small-pi cutover
Status: waiting for node registration
Next: journalctl -u openclaw-gateway -n 100 --no-pager
Risk: do not restart gateway until node token is confirmed
```

The point is not perfect prose. The point is that the next operator can attach and continue without guessing.

## Recovery Commands

List sessions:

```bash
tmux ls
```

Attach to the canonical session:

```bash
tmux attach -t openclaw
```

Capture the last 200 lines from the active task window:

```bash
tmux capture-pane -pt openclaw:work -S -200
```

Show window names:

```bash
tmux list-windows -t openclaw
```

## Operational Boundaries

- Do not use multiple unnamed sessions on the same host
- Do not leave the active command mixed into the same window as notes and status checks
- Do not rely on shell scrollback as the only audit trail
- Do not kill the session at the end of a disconnect-prone task; detach and leave it recoverable

## When To Create Another Window

Create another window only if one of these is true:

- the task has a second long-running command that should remain visible
- the current command is risky enough that a clean rollback window is justified
- you need a separate root shell and user shell at the same time

Otherwise, keep the session small and predictable.
