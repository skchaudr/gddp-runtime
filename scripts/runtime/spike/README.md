# Runtime spikes

## pi_rpc_persistent_spike.py

Go/no-go evidence for GDDP **persistent-pi** executor mode (`pi --mode rpc`).

### What it proves
1. Spawn `pi --mode rpc` and drive it over JSONL stdin/stdout
2. Multi-turn context in one process (prompt #2 recalls prompt #1)
3. Session identity via `get_state` → `sessionFile` / `sessionId`
4. Mid-turn `SIGKILL` of the process
5. Resume with `--session <sessionFile>` — history survives; model still answers from prior turns

### Run (on khoj-38)
```bash
cd ~/gddp-runtime
PI_SPIKE_MODEL=xai/grok-4.5 python3 scripts/runtime/spike/pi_rpc_persistent_spike.py
```

Results: `pi_rpc_persistent_spike_results.json` (gitignored if large/local; a redacted summary may be committed).

### Working command shapes
```text
pi --mode rpc --model <id> --session-dir <dir> --tools read
# resume after death:
pi --mode rpc --model <id> --session-dir <dir> --tools read --session <sessionFile.jsonl>
```

Turn boundary event: **`agent_end`** (also emits `turn_end`).
