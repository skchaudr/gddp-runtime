# Evaluator capture

Every live verification CLI invocation creates a private, unique directory beside
its receipt: `<receipt-stem>.capture-<unique suffix>/`. The existing bridge invokes
this CLI on executor return. Capture starts and ends within that invocation.

Contents:

- `node.yaml`, `project.yaml`, optional `shape-profile.yaml`: source snapshots.
- `input.json`: parsed definitions, job/attempt identity, repo path, base/subject
  commit and observed checkout HEAD.
- `criteria-*/request.json`, `integrity-*/request.json`: exact initial prompts
  supplied to Pi, selected provider/model and thinking setting.
- Each lane's `command.json`: Pi argv; environment credentials stay outside capture.
- Each lane's `events.jsonl`: stdout JSON events, including the tool-result content
  emitted by Pi; flushed after each line. `stderr.log` retains diagnostics.
- Each lane's `verdict.json` and `tool-trace.jsonl`: raw extension output.
- `receipt.json`: final combined receipt, including typed lane failures.
- `error.json`: a CLI exception, when evaluation exits before receipt creation.

The canonical receipt and CLI summary expose `evaluation_capture_path` and
`evaluation_capture_errors`. Repeated evaluations preserve separate captures.
Capture setup/write failures are reported to stderr and, when a receipt is
produced, its capture-errors field. Earlier complete files remain available.

This captures Pi's initial invocation and emitted event stream. Tool-side
truncation still applies; provider HTTP payloads and arbitrary runtime state
require separate instrumentation. A stopped process can leave a partial final
event. An incomplete capture remains useful evidence with its limits explicit.

For a later Jev comparison, use the node criteria and captured observations as
input; keep the evaluator verdict separate until comparing judgments. Retain
Jev's request and response alongside that comparison. Jev scoring is a separate
follow-up operation.
