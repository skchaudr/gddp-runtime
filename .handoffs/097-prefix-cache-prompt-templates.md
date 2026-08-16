# 097 — Prefix-cache-shaped prompt templates for K3 orchestrator + K2.7/Pi subagents

Status: draft (operator: sab)
Scope: `gddp-runtime` prompt construction, `litellm-gateway` model lanes, GDDP node contract
Related: 094-watch-steer-v1, 096-evaluation-timing

---

## 1. Why this handoff exists

GDDP currently builds every executor prompt as a fresh string per attempt. That is
correct for determinism but wrong for prefix caching: Moonshot (and DeepSeek, and
Anthropic) only discount a prompt prefix that is **byte-identical** to a previously
seen one. Two places in this repo break the prefix within the first ~150 bytes on
every single call, so K3-as-orchestrator would be billed at full cache-miss rate
forever.

The fix is structural, not semantic: same information, reordered into a
stable-prefix / volatile-suffix layout.

---

## 2. Confirmed defects in the current harness

### 2.1 `scripts/adapters/pi_rpc_adapter.py` — volatile ID in position 2

Current `run_attempt()` prompt assembly:

```python
prompt = (
    f"{_PACKET_PREAMBLE}\n\n"
    f"execution_attempt_id: {packet.get('execution_attempt_id')}\n\n"
    f"{packet_raw}"
)
```

`_PACKET_PREAMBLE` is the only stable text in the whole prompt (~330 bytes). The
`execution_attempt_id` line follows immediately, so the divergence point is
effectively "right after the preamble." Everything downstream — the entire
NodePacket JSON, which is the bulk of the tokens — is a guaranteed miss.

### 2.2 `NodePacket.to_json()` — volatile keys sort to the front

`to_json()` uses `json.dumps(..., sort_keys=True)`, which is good for determinism
and bad for caching, because alphabetical order puts the volatile fields first:

```
acceptance_criteria, attempt_index, constraints, execution_attempt_id,
expected_base_commit_sha, goal, job_id, node_id, previous_findings,
required_artifacts, title, why
```

`attempt_index` is key #2 and `execution_attempt_id` is key #4. Retry attempt 1 of
the same node diverges from attempt 0 at roughly byte 60 of the JSON blob, so even
identical node content re-bills in full.

### 2.3 `scripts/adapters/session_prompt.py` — right instinct, wrong header

`build_session_instructions()` already appends the volatile block last:

```
---
node: {node_id}
job: {job_id}
attempt: {attempt_index}
execution_attempt_id: {execution_attempt_id}
```

That part is correct and should be the model for everything else. The defect is
the first line, `[GDDP] {packet.title}`, which is per-node volatile and sits at
byte 0 — so no two nodes in a project ever share a cached prefix, and the shared
Goal/Why framing text below it is never reused.

### 2.4 No Kimi lane exists yet

`litellm-gateway/rendered/config.yaml` has lanes for `chatgpt/*`, `sub-gpt`,
`sub-codex`, `sub-claude`, `sub-claude-fast`, `anthropic-passthrough`,
`clinepass/*`, `grok-sub/*`, `openai/*`, `anthropic/*`, `deepseek/*`, `zai/*`,
`glm-coding/*`. Kimi appears only in `README.md` prose. `_DEFAULT_MODEL` in
`pi_rpc_adapter.py` is still `xai/grok-4.5`.

---

## 3. Target prompt layout

Four zones, in this exact order, for every executor prompt in the runtime:

```
ZONE A  ORCHESTRATOR POLICY      stable per runtime version   ~never changes
ZONE B  PROJECT CONTEXT          stable per graph project     changes on doctrine edits
ZONE C  NODE CONTENT             stable per node              changes when the node yaml changes
ZONE D  ATTEMPT ENVELOPE         volatile per attempt         changes every call
```

Rule: nothing in A–C may contain a timestamp, job id, attempt index, commit sha,
worktree path, session id, or receipt path. Those all live in D.

---

## 4. K3 orchestrator template (`ZONE A` + `ZONE B`)

Intended for a K3 session that reads receipts, decides the frontier, and dispatches
— not one that writes code.

```
### GDDP ORCHESTRATOR POLICY  v1  (ZONE A — byte-stable, do not edit mid-project)

You are the GDDP orchestrator. You own graph decisions, not implementation.

Authority:
- Choose the next frontier node from the graph and dispatch it.
- Review returned receipts and issue pass / retry / block verdicts.
- Summarize a returned result into the next node's input.

Prohibited:
- You never edit files in a worktree yourself.
- You never modify graph truth (~/GDDP/graphs/**) or the queue DB
  (~/repos/gddp-runtime/db/queue.db).
- You never merge to main. Results land on gddp/result branches (D10 doctrine).

Stopping conditions:
- Emit exactly one decision object per turn, then stop.
- If evidence is insufficient, emit status "blocked" with the missing evidence
  named. Do not guess.

Output contract (single JSON object, no prose outside it):
{
  "decision": "dispatch | verdict | block",
  "node_id": "...",
  "executor": "pi_rpc | mission | jules_api | local_subprocess",
  "subagent_plan": [{"role": "...", "model": "...", "task": "..."}],
  "verdict": "pass | retry | fail | null",
  "reasoning": "...",
  "evidence_refs": ["..."]
}

### GDDP PROJECT CONTEXT  (ZONE B — stable per project, reset cache when edited)

project: myapi-part1
graph_root: ~/GDDP/graphs/myapi-part1
node_specs: ~/GDDP/graphs/myapi-part1/nodes/*.yaml
receipts: ~/GDDP/receipts/<project>/
verification: ~/repos/gddp-config/verification/myapi-part1/
runtime_repo: ~/repos/gddp-runtime
governing_memo: /Users/sab-mini/repos/GDDP v MyAPI Part 1 - the first slice.md

doctrine in force:
- Flow-on-provisional (D12): a provisional upstream node does not block downstream
  dispatch.
- No-merge-to-main (D10): every result is a commit on a gddp/result branch.
- Raw-before-normalized: Stage B nodes extract verbatim; normalization is Stage C.

executor capability map:
- pi_rpc            durable RPC session, tools read,bash,edit,write,grep,find,ls,subagent
- mission           Droid mission mode, git-verified evidence
- jules_api         remote session, no local worktree
- local_subprocess  deterministic scripted steps, no model call
```

Zone B is the block worth pinning hardest — it is a few hundred tokens reused on
every orchestrator turn of a project, and it is the block most likely to get
"helpfully" regenerated by a harness.

---

## 5. Attempt envelope (`ZONE D`) — the only volatile block

Move every id out of the head of the prompt into a single trailing block, using
the shape `session_prompt.py` already uses:

```
### ATTEMPT ENVELOPE (volatile — always last)
node: node-03-extract-decisions
job: job_20260814T122823299bbc0d0b374d
attempt: 0
execution_attempt_id: ...
expected_base_commit_sha: 989a62b
worktree: /Users/sab-mini/repos/worktrees/...
```

---

## 6. Concrete patches

### 6.1 `pi_rpc_adapter.py` — reorder, don't rewrite

```python
prompt = (
    f"{_PACKET_PREAMBLE}\n\n"                      # ZONE A  stable
    f"{project_context_block}\n\n"                 # ZONE B  stable per project
    f"{node_content_block}\n\n"                    # ZONE C  stable per node
    f"### ATTEMPT ENVELOPE (volatile)\n"           # ZONE D  volatile, last
    f"execution_attempt_id: {packet.get('execution_attempt_id')}\n"
    f"attempt: {packet.get('attempt_index')}\n"
    f"job: {packet.get('job_id')}\n"
    f"expected_base_commit_sha: {packet.get('expected_base_commit_sha')}\n"
)
```

### 6.2 `executor_protocol.py` — split the serialization

Keep `to_json()` as-is for the durable transport record (tests and receipts depend
on `sort_keys=True`). Add a second, prompt-only serializer that partitions fields
by volatility, with explicit key order rather than alphabetical:

```python
_STABLE_PROMPT_KEYS = (
    "node_id", "title", "goal", "why",
    "constraints", "acceptance_criteria", "required_artifacts",
)
_VOLATILE_PROMPT_KEYS = (
    "job_id", "execution_attempt_id", "attempt_index",
    "expected_base_commit_sha", "previous_findings",
)

def to_prompt_parts(self) -> tuple[str, str]:
    """Return (stable_zone_json, volatile_zone_json) for cache-friendly prompts."""
    stable = {k: _thaw_json(getattr(self, k)) for k in _STABLE_PROMPT_KEYS}
    volatile = {k: _thaw_json(getattr(self, k)) for k in _VOLATILE_PROMPT_KEYS}
    dump = lambda d: json.dumps(d, sort_keys=False, separators=(",", ":"))
    return dump(stable), dump(volatile)
```

Note `node_id` and `title` stay in the stable zone: they change per node but not
per attempt, so they belong in Zone C — retries of the same node then reuse the
whole Zone A+B+C prefix.

### 6.3 `session_prompt.py` — demote the title

Replace the `[GDDP] {title}` header with a fixed banner and move the title into
the Zone C body:

```python
header = "[GDDP] node execution request"     # byte-stable across all nodes
```

`previous_findings` is already rendered late; keep it inside Zone D, since attempt
1 of a node must not invalidate the Zone C prefix that attempt 0 established.

### 6.4 `litellm-gateway` — add the Kimi lanes

Append to `config.template.yaml`, matching existing lane naming:

```yaml
  - model_name: kimi-orch
    litellm_params:
      model: moonshot/kimi-k3
      api_base: https://api.moonshot.ai/v1
      api_key: os.environ/MOONSHOT_API_KEY

  - model_name: sub-kimi
    litellm_params:
      model: moonshot/kimi-k2.7-code
      api_base: https://api.moonshot.ai/v1
      api_key: os.environ/MOONSHOT_API_KEY

  - model_name: moonshot/*
    litellm_params:
      model: moonshot/*
      api_key: os.environ/MOONSHOT_API_KEY
```

Add `MOONSHOT_API_KEY` to `~/litellm-gateway/secrets/keys.env`, then
`bin/reload.sh` and confirm with `bin/roster.sh`.

Caveat: LiteLLM's proxy layer does not reliably surface Moonshot's cache-hit
accounting, and its own request normalization can perturb the prefix. For the K3
orchestrator lane specifically, prefer a direct Moonshot client and keep the
gateway for subagent fan-out where cache economics matter less.

### 6.5 Executor defaults

```
_DEFAULT_MODEL = "xai/grok-4.5"    # unchanged for pi worker sessions
```

Set the orchestrator model by env rather than editing the default, so the worker
lane is untouched:

```sh
export GDDP_PI_RPC_MODEL=sub-kimi          # K2.7 Code as the pi worker
# orchestrator runs outside pi_rpc, against kimi-orch
```

---

## 7. K2.7 / Pi subagent template

Pi already exposes `subagent` in `_DEFAULT_TOOLS`, and node-03's constraints show
the pattern in use ("main pi session runs gpt-5.6-sol; delegate with up to 5
subagents ... via the subagent tool's model parameter"). Formalize that dispatch
payload so it is byte-stable per project:

```
### SUBAGENT ROLE  (stable — one block per role, never edited mid-project)
role: worker
You execute exactly the task given. You do not plan, re-scope, or review.
You do not touch files outside the worktree you were started in.
Only your final message is returned to the orchestrator — if you did the work but
did not report it, the work is lost.

### REPO CONTEXT  (stable per project — identical bytes across all subagent calls)
<same Zone B block as the orchestrator, verbatim>

### TASK  (volatile — last)
{"task": "...", "constraints": ["..."], "expected_output_format": "..."}
```

Return contract, matching the verdict fields the evaluator already writes into
node yaml (`verdict`, `intent_preserved`, `graph_integrity_preserved`,
`evaluator_note`, `evidence_refs`):

```json
{
  "agent": "sub-kimi",
  "status": "complete | blocked | needs_review",
  "artifacts": ["01-decisions/output/decisions-raw.jsonl"],
  "output": "...",
  "assumptions": ["..."],
  "flags": ["..."]
}
```

---

## 8. Harness invariants to enforce

- `reasoning_effort` is chosen once per session. Changing it mid-session
  invalidates the cache; `tool_choice` and `response_format` do not.
- The `steer.jsonl` drain in `pi_rpc_adapter.run_attempt()` sends operator steers
  as fresh prompts. Those are appends, which is correct — do not "helpfully"
  fold a steer back into the original instruction block.
- Prompt caching only engages above a minimum prefix length (256 tokens on
  Moonshot). Zone A + Zone B together clear that; Zone A alone may not.
- Zone B edits are a deliberate cache reset. Batch doctrine changes into one
  commit per work session rather than trickling them in.
- Add a receipt field for observability: log the reported cached-token count per
  attempt alongside the existing evidence, so a template regression shows up as a
  measurable hit-rate drop instead of a silent bill increase.

---

## 9. Suggested verification

1. Dispatch node-03 twice with unchanged node yaml; confirm attempt 1 reports a
   cached-prefix hit covering Zones A–C.
2. Edit one word of Zone B; confirm the next attempt reports a miss, and the one
   after that a hit.
3. Dispatch two different nodes in the same project; confirm both hit on Zone A+B
   and miss only from Zone C onward.
