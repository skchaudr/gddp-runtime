# GDDP Runtime overview

GDDP Runtime is the execution control plane for graph-driven agentic development. It reads project graphs (DAGs of work nodes) from a separate config repository, dispatches bounded work to executor agents, records state in SQLite, runs a two-lane evaluator on returned work, and halts at a human review gate. The system never auto-advances graph truth.

## What it does

GDDP turns software projects into explicit maps of work, then uses agents to traverse those maps without losing human control. The runtime's job is to:

1. Receive GitHub webhooks and normalize them into events
2. Read the project graph to find ready nodes (dependencies complete, no active jobs)
3. Classify events, scope-check them against ready nodes, and build job payloads
4. Dispatch jobs to executor adapters (Jules via GitHub issues today, agent-agnostic by design)
5. When a PR merges, convert it into a structured receipt with a verification verdict
6. Run a two-lane evaluator (deterministic probes + semantic LLM agent + integrity review) on returned work
7. Route the job to `awaiting_review` for a human to accept, retry, block, or defer

No automatic node advancement. No automatic review. No automatic graph writeback.

## Who uses it

- **Operators** running multi-month, multi-repo projects with agent assistance
- **Agents** (Jules, Codex, local harnesses) that execute bounded work packets
- **Reviewers** who inspect receipts and decide whether graph truth advances

## Tech stack

Python 3.11+ with Flask, PyYAML, Pydantic, and Anthropic SDK. SQLite for state. GitHub CLI (`gh`) for dispatch. Deployed on a Raspberry Pi control plane with systemd services and cron-based heartbeat.

## Quick links

- [Architecture](architecture.md)
- [Getting started](getting-started.md)
- [Glossary](glossary.md)
- [Heartbeat system](../systems/heartbeat.md)
- [Verification system](../systems/verification.md)
- [Decision loop](../systems/decision-loop.md)
- [Deployment](../deployment.md)
