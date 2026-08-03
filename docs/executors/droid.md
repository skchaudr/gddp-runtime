# Droid executor transport

Factory Droid (`droid exec`) is a first-class local executor transport in
gddp-runtime. It uses the same executor-neutral node packet, worktree,
commit-ref handoff, spool, and receipt contract as `local_subprocess`. Only
the adapter default argv and its host env override differ.

## How a node selects droid

A node opts into this transport with:

```yaml
allowed_execution_modes: [droid]
```

The dispatcher maps the `droid` execution mode to `DroidSubprocessAdapter`.
There is no per-project argv coupling and no special packet shape: the node
declares the mode; the host supplies the command line.

## Host config: model and autonomy

Model choice and autonomy level are **host config**, not node or project
fields. They ride the subprocess argv via:

```bash
GDDP_DROID_SUBPROCESS_ARGV
```

The value is a JSON argv array. Example (paths must be absolute on the host):

```bash
export GDDP_DROID_SUBPROCESS_ARGV='["/usr/bin/python3","/absolute/path/to/local_agent_executor.py","--","droid","exec","--auto","high","-m","<model-id>"]'
```

Without `GDDP_DROID_SUBPROCESS_ARGV`, the adapter uses its built-in default:

- `droid exec --auto high`
- droid's own configured default model
- the GDDP packet preamble on `--append-system-prompt` (stdin carries the
  NodePacket JSON)

`--auto high` matches the pi `--approve` profile so agents can commit and
push when the node instructs them to. Pin model and autonomy in host env
when you need a specific route for smoke or production.

Shared spool root (same as other local transports):

```bash
GDDP_LOCAL_SUBPROCESS_SPOOL_DIR
```

See `deploy/mini-heartbeat/env/gddp.env.example` for the deploy-kit defaults.

## Contract boundary

- Packet in, durable session out; collect yields a `gddp.local_result.v1`
  commit-ref handoff when the attempt succeeds.
- Runtime does not treat executor success as graph truth. Evidence returns
  for evaluation and human review only.
- Do not modify graph truth or runtime databases from the agent session.
