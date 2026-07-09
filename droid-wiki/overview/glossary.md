# Glossary

## Core terms

| Term | Definition |
|---|---|
| **GDDP** | Graph-Driven agentic Development control Plane. The system that turns projects into maps of work and drives agents across them with a human review gate. |
| **Node** | A bounded unit of work in the project graph. Each node has a goal, acceptance criteria, constraints, dependencies, and required artifacts. |
| **Project graph** | A DAG of nodes in `gddp-config`, authored as YAML. The runtime reads it but never writes it. |
| **Receipt** | A structured record of an executor's return. Contains the merged PR reference, verification verdict, and review-routing status. Written to the `results` table. |
| **Verdict** | The evaluator's output. One of: pass, fail, blocked, needs-human-review, needs-more-evidence, out-of-scope-change-detected. |
| **Acceptance** | The human act that advances graph truth. Only a human can move a node to complete. |
| **Decision** | The human's status call on a node (accept, retry, block, defer, reopen, supersede). |
| **Canon** | The four foundational human-owned documents: the foundational node, README, PROJECT-BRIEF, and AGENTS.md. Canon wins over any other prose when they disagree. |

## Verification terms

| Term | Definition |
|---|---|
| **Criteria lane** | Lane 1 of the evaluator. Deterministic probes check acceptance criteria; indeterminate criteria escalate to a semantic LLM agent. |
| **Integrity lane** | Lane 2 of the evaluator. A fresh-eyes drift review that asks whether the work preserves the node's intended role in the project graph. |
| **Deterministic probe** | A regex, file-existence, or command-execution check that verifies a specific acceptance criterion without an LLM. |
| **Semantic agent** | An LLM-based agent that investigates indeterminate criteria using read-only tools (read, grep, find, bash) against the repo. |
| **Integrity combiner** | The worst-of rule that combines the criteria verdict and integrity verdict into the final receipt verdict. Integrity can only worsen, never upgrade. |
| **Decision matrix** | A 12-row priority-ordered table that maps deterministic + semantic results to a verdict. Row order encodes intentional severity. |
| **Shape profile** | A YAML file that describes the expected shape of a project (CLI tool, runtime orchestrator) to guide the semantic agent's investigation. |

## Runtime terms

| Term | Definition |
|---|---|
| **Heartbeat** | The dispatch loop that reads the project graph, finds ready nodes, classifies events, and dispatches jobs. Runs on a 5-minute cron. |
| **Ready node** | A node with `status=ready` in `project.yaml` that has a node YAML file. Scope checking verifies dependencies are complete and no active jobs exist. |
| **Scope check** | Verifies that an event maps to a ready node and that dispatching is safe (dependencies met, no active job). |
| **Claim** | An atomic SQLite UPDATE that reserves an event for one heartbeat process. Prevents concurrent heartbeats from processing the same event. |
| **Return router** | Converts merged PRs into review receipts. Parses `node:` and `job:` tags from PR bodies, runs verification, writes the receipt. |
| **Decision loop** | An event-driven reasoning layer that wakes, reads context, and decides what to do next (verify, dispatch, escalate, no-op). |
| **Retry budget** | A project-level dial in `project.yaml` that controls how many times a non-pass verdict with evidence-referenced findings triggers an executor retry before routing to human review. |
| **Paste marker** | Text between `>>>` and `<<<` that is treated as inert context by the natural guard. Operator text outside markers controls authorization. |
