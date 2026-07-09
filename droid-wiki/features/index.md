# Features

GDDP Runtime is built around a set of cross-cutting capabilities that keep human control intact while agents do bounded work. These features sit on top of the core dispatch-and-verify loop described in [Architecture](../overview/architecture.md): they govern how authorization is checked before a tool fires, how failed verdicts get a second chance, and how a merged PR becomes evidence rather than an automatic graph advancement. Each one exists because the runtime's central rule, that it never mutates graph truth, needs enforcement at multiple levels, from the agent's own tool calls to the final review gate.

| Feature | What it does |
|---|---|
| [Natural guard](natural-guard.md) | Paste-marker authorization hook that splits user text into operator vs pasted context, classifies tool calls, and blocks mutations the operator never asked for. |
| [Retry loop](retry-loop.md) | Evaluator-to-executor retry budget that re-dispatches a node when a non-pass verdict carries evidence-referenced findings the executor can act on. |
| [Receipt-based return](receipt-based-return.md) | The pattern that converts a merged PR into a structured receipt, runs verification, and routes to a human review gate instead of silently advancing graph truth. |

## Related pages

- [Architecture](../overview/architecture.md)
- [Return router system](../systems/return-router.md)
- [Verification system](../systems/verification.md)
- [Patterns and conventions](../how-to-contribute/patterns-and-conventions.md)
