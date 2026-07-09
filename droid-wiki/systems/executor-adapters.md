# Executor adapters

The runtime does not call executors directly. It hands a job packet to an adapter, and the adapter turns that packet into whatever the executor expects. Today there is one live adapter (Jules via GitHub issues) and one stub (Jules via CLI). The point of the pattern is that swapping executors, or adding a new one, does not touch the heartbeat loop, the decision loop, or the return router. They all speak the same dispatch contract.

## The adapter contract

An adapter exposes a `dispatch(job: dict) -> DispatchResult` method. The job dict is the row from the `jobs` table (plus a few injected fields like `_previous_findings` on retry). The return value is a `DispatchResult` dataclass. Everything downstream of dispatch, including the return router and the verification bridge, reads from the `results` table, not from the adapter, so adapters are executor-specific but the rest of the runtime is executor-agnostic.

## DispatchResult

Both adapters declare their own `DispatchResult`, but the live shape (from `JulesActionAdapter`) is:

```python
@dataclass
class DispatchResult:
    success: bool
    issue_url: str | None
    issue_number: int | None
    error: str | None
```

`success` is the only field the dispatcher branches on. `issue_url` and `issue_number` get recorded against the job for traceability. `error` is the human-readable failure reason when `success` is false.

The CLI stub uses a slightly different shape (`session_id` instead of `issue_url`/`issue_number`) because the Jules CLI returns a session handle, not a GitHub issue. When that adapter goes live, the contract will need a small reconciliation, likely by giving `DispatchResult` an opaque `handle` field plus a `handle_type` discriminator.

## JulesActionAdapter (live)

`scripts/adapters/jules_action_adapter.py` is the active adapter. It dispatches a job by creating a GitHub issue in the target repo with the `jules` label. The `jules-action` workflow in that repo detects the label and hands the issue body to Jules as its task instructions.

### Requirements

- `gh` CLI installed and on `PATH`
- `GITHUB_TOKEN` or `GH_TOKEN` set to a PAT with issue write access on the target repo

The constructor takes the target repo slug, e.g. `JulesActionAdapter(repo="skchaudr/test-project")`.

### dispatch

`_github_token()` reads `GITHUB_TOKEN` then `GH_TOKEN` and returns immediately with a `DispatchResult(success=False)` if neither is set. This is the only auth path; the adapter does not depend on ambient `gh` login state.

When a token is present, the adapter builds the issue body, then runs:

```
gh issue create --repo <repo> --title "[GDDP] <title>" --body <body> --label jules
```

with `GH_TOKEN` injected into the subprocess environment explicitly. The subprocess has a 30-second timeout. On success, `gh issue create` prints the issue URL on stdout, which the adapter parses into `issue_url` and `issue_number`. On non-zero exit, timeout, or any other exception, the adapter returns a `DispatchResult` with the error string and no URL.

### build_issue_body

This is the meat of the adapter. It formats the job packet as a structured markdown issue body that Jules reads as its task instructions. The body has fixed sections:

- **Goal** and **Why** from the job row, verbatim
- **Constraints**, flattened through `_flatten` (dicts become `k — v`, lists become comma-joined)
- **Acceptance Criteria**, rendered as unchecked markdown checkboxes
- **Previous Attempt Findings** (only on retry, see below)
- **Output Requirements**, including the verbatim metadata block

### The node: / job: metadata block

The output requirements section tells Jules to include this block at the end of the PR description, verbatim:

```
node: <node_id>
job: <job_id>
```

The body text is explicit that this block is parsed by the GDDP return router to create a structured review receipt when the PR merges, that it does not advance graph truth automatically, and that missing or malformed metadata prevents the runtime from linking the PR back to the job for review. This is the contract that makes the return router's `node:` / `job:` parsing reliable.

The body closes with a footer line identifying the dispatch origin: `*Dispatched by GDDP control plane — job_id: <id> — node: <id>*`.

### _previous_findings on retry

When the return router gets a non-pass verdict with evidence-referenced findings and the job's retry budget still has room, it re-dispatches the job and injects a `_previous_findings` dict into the job before handing it to the adapter. `build_issue_body` detects that field and appends a **Previous Attempt Findings** section:

- The verdict and integrity verdict from the prior attempt
- The reasoning text
- A bulleted list of findings, each prefixed with its severity

The section ends with `Please address these findings in your implementation.` This is how retry attempts carry forward what the evaluator found, without the runtime re-running the evaluator or mutating the original receipt.

## JulesCliAdapter (stub)

`scripts/adapters/jules_cli_adapter.py` is the Option B adapter, kept as a stub for a later phase. The intent is to dispatch directly through the Jules CLI (`jules remote new --repo <repo> --session '<instructions>'`) instead of going through GitHub label events. The docstring calls this "more GDDP-pure" because the runtime decision loop would explicitly dispatch the job packet rather than relying on a GitHub Action to trigger Jules.

Every method raises `NotImplementedError` with a message pointing at the install and verify steps (`pip install jules-tools`, `jules --version`). It is not wired into the dispatcher. When the Jules CLI interface is confirmed stable, the dispatch, poll, and collect_result methods get implemented and the adapter gets swapped in behind the same dispatch contract.

## Adapter-agnostic design

The dispatcher calls `adapter.dispatch(job)` and records the `DispatchResult`. It does not know whether the adapter opened a GitHub issue, started a CLI session, or queued a Vertex job. The return router reads from the `results` table, not from the adapter. The verification bridge reads from the `results` table. Adding a Codex adapter, a Vertex adapter, or a custom in-process executor means writing a new class with a `dispatch` method that returns a `DispatchResult`; nothing upstream changes.

## Key source files

| File | Role |
|---|---|
| `scripts/adapters/jules_action_adapter.py` | Live adapter: GitHub issue with `jules` label, `build_issue_body`, retry findings injection |
| `scripts/adapters/jules_cli_adapter.py` | Stub adapter for direct Jules CLI dispatch |

## Related pages

- [overview/architecture.md](../overview/architecture.md) for where adapters sit in the system flow
- [systems/return-router.md](return-router.md) for who consumes the `node:` / `job:` metadata block
- [systems/verification.md](verification.md) for how retry findings get produced
- [systems/replay.md](replay.md) for re-dispatching a job through the same adapter
