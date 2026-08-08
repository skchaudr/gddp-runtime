# Gate token

Active contributors: Saboor

A gate token is per-node admission evidence for mission-mode execution. It says that a dependency has qualifying provisional evidence and may admit dependent work; it is not node lifecycle state, human acceptance, or graph truth.

## Shape and location

`/Users/sab-mini/repos/gddp-runtime/scripts/runtime/gates.py` stores tokens at:

```text
<target-repo>/.gddp/gates/<node-id>.token
```

The JSON object always includes `node_id` and UTC `issued_at`. When a verdict receipt path is supplied, it also records `receipt_path` and the receipt's SHA-256 digest. A missing receipt path is represented by an empty digest rather than invented evidence.

## Operations

| Operation | Meaning |
|---|---|
| `write_gate()` | Atomically writes a token with a unique same-directory temporary file and `os.replace()` |
| `read_gate()` | Returns the object only when it is valid JSON and its `node_id` matches the requested node |
| `gate_satisfied()` | Requires a valid token for every dependency; an empty dependency list passes |
| `revoke_gate()` | Removes a token when a human rejects or defers provisional work |

Writes and revocations are best effort and do not raise into the caller. A failed write leaves the node provisional and under-admits dependent work. A failed revocation can temporarily over-admit, so the warning requires operator attention.

## Authority boundary

A token is derived scheduling evidence. It does not:

- mark a node `provisional` or `complete`;
- prove that a receipt or commit is correct merely because a file exists;
- replace evaluator evidence;
- authorize runtime code to mutate `gddp-config`.

The return and review path may write a token after qualifying evaluation evidence places a node in `provisional`. Only a human can accept the node as complete, and human rejection or deferral should revoke the token.

## Related pages

- [Node and graph truth](node-and-graph.md)
- [Verdict receipt](verdict-receipt.md)
- [Engagement](engagement.md)
- [Provisional status and frontier advance](../features/provisional-and-frontier.md)
- [Return and review](../systems/return-and-review.md)
