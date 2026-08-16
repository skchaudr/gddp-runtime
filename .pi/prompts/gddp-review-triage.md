---
description: Triage provisional nodes, evaluation coverage, and verdicts via Sweep & Steward
argument-hint: "<project>"
---

Run evaluation sweep and review-queue triage for project "${1:-myapi-part1}".
1. Dispatch `sweep` agent to run `gddp verify node` on completed jobs lacking evaluation receipts.
2. Dispatch `steward` agent to collect receipts, summarize lane verdicts, and rank provisional nodes.
3. Present decision-ready review queue (`~/repos/gddp-config/reports/review-queue.md`) for human acceptance.
