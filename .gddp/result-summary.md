# Result Summary: runtime-receipt-proves-node

The attached live verifier receipt was generated for
`verification-receipt-contract` and shows the receipt contract fields populated:

- `project_id`: `gddp-runtime`
- `node_id`: `verification-receipt-contract`
- `verdict`: `needs-more-evidence`
- `confidence`: `0.19`
- `criteria_confidence`: `0.19`
- `completeness_status`: `complete`
- `deterministic`: present
- `semantic`: present with 10 judgments
- `decision_reasoning`: present
- `required_next_action`: `Provide missing required artifacts and re-run semantic investigation.`
- `generated_at`: present in the attached receipt

After this evidence bundle was added, a fresh offline verifier run wrote
`/tmp/gddp-runtime-receipts-018-offline/gddp-runtime/verification-receipt-contract.json`
and reported all required artifact flags as present:

- `decision.md`: `true`
- `result-summary.md`: `true`
- `patch.diff`: `true`

The receipt also records that the graph truth boundary stayed intact: runtime
emitted a receipt and required next action, while `gddp-config` remains
human-owned and unchanged in this completion round.
