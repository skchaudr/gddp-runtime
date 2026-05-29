# Wave 3 · Task 5 — Shape Profiles (task packet)

**Intended executor:** Cline driven by GLM5-Turbo. Explicit and tightly scoped on purpose — an
under-specified packet wandering scope is what burned the last session.
**Repo:** `~/repos/gddp-config` (the **separate config repo — NOT gddp-runtime**).
**Branch:** `feature/t5-shape-profiles`.

> Setup (this is the *other* repo; it has its own git):
> ```bash
> cd ~/repos/gddp-config
> git worktree add ../gddp-config-t5 -b feature/t5-shape-profiles
> cd ../gddp-config-t5
> ```

## Your job, in one sentence
Author four shape-profile YAML files that conform to the existing schema, and add one **optional**
`shape_profile` field to the project graph template. Content only — no code, no runtime.

## Create ONLY these files
- `profiles/cli-tool.yaml`
- `profiles/runtime-orchestrator.yaml`
- `profiles/web-app.yaml`
- `profiles/automation.yaml`

## Modify ONLY this file (one field, optional)
- `graphs/_template/project.yaml` — add a single optional top-level field `shape_profile:` with a
  commented example. Also set it on `graphs/gddp-runtime/project.yaml` as the live example
  (`shape_profile: runtime-orchestrator`). It MUST be optional — when absent, behavior stays generic.

## DO NOT modify or create anything else
- `schemas/` (the schema is frozen — you conform to it, never change it)
- `graphs/*/nodes/`, any other `graphs/*/project.yaml`, `templates/`, README/CHANGELOG
- **The entire `~/repos/gddp-runtime` repo is out of scope** — this task is config-only.

If you think you need to touch anything else, **STOP and report it.**

## The schema you must conform to (`schemas/v1/shape_profile.yaml` — read it, do not edit)
Each profile file has exactly these keys:
```yaml
schema_version: "1.0"
schema_type: shape_profile
profile_id: <kebab-case id matching the filename>
description: <one line: what project type this profile describes>
expected_node_chain:   # ordered list of node role labels this project type expects
  - <role>
invariant_rules:       # rules that must hold across all nodes of this type
  - <rule>
anti_patterns:         # patterns that signal drift/misuse — the semantic evaluator flags these
  - <pattern>
```

## Exact content to write (this IS the spec — transcribe it; tighten wording only)

**`profiles/cli-tool.yaml`**
```yaml
profile_id: cli-tool
description: Command-line tool — parses input, validates, executes, returns output.
expected_node_chain: [spec, parser, validator, executor, tests]
invariant_rules:
  - Graph legality must be preserved.
  - Acceptance criteria must not weaken.
anti_patterns:
  - Runtime silently mutates the source graph.
  - Acceptance criteria removed without replacement.
```

**`profiles/runtime-orchestrator.yaml`** (this is what gddp-runtime itself is)
```yaml
profile_id: runtime-orchestrator
description: Orchestration runtime — dispatches jobs, ingests webhooks, records results, decides next action.
expected_node_chain: [spec, schema, dispatch, return-handler, decision-logic, tests]
invariant_rules:
  - Runtime proposes graph mutations via evidence PR; it never writes source-of-truth graph directly.
  - At most one active job per project.
  - The decision/verdict layer is deterministic — no LLM in the verdict path.
anti_patterns:
  - An LLM placed in the decision or verdict path.
  - Direct graph writes that bypass the evidence-PR proposal model.
  - A module reaching across into another module's internals (boundary violation).
```

**`profiles/web-app.yaml`**
```yaml
profile_id: web-app
description: Web application — data model, API, UI, and an auth boundary.
expected_node_chain: [spec, data-model, api, ui, auth, tests]
invariant_rules:
  - Authentication is enforced at the request boundary, not inside UI components.
  - API contract changes stay backward-compatible or are versioned.
  - Acceptance criteria must not weaken.
anti_patterns:
  - Auth enforcement coupled to UI components.
  - Breaking API change shipped without versioning.
  - Tests deleted or skipped to make a build pass.
```

**`profiles/automation.yaml`**
```yaml
profile_id: automation
description: Automation/pipeline — triggered, fetches, transforms, acts, notifies.
expected_node_chain: [trigger, fetch, transform, action, notify, tests]
invariant_rules:
  - Actions are idempotent — safe to retry.
  - Failures are observable (logged or escalated), never silently swallowed.
  - Secrets are never hardcoded.
anti_patterns:
  - Silent error-swallowing (e.g. bare except that hides failures).
  - Non-idempotent side effects that double-apply on retry.
  - Hardcoded credentials or tokens.
```

## `graphs/_template/project.yaml` edit
Add this block (optional field + guidance comment), e.g. just after `repo:`:
```yaml
# Optional. One of: cli-tool | runtime-orchestrator | web-app | automation.
# Omit for generic behavior — the semantic evaluator only uses this when present.
shape_profile:            # e.g. cli-tool
```

## Acceptance
- Four profile files exist under `profiles/`, each conforming to `schemas/v1/shape_profile.yaml`.
- `graphs/_template/project.yaml` has the optional `shape_profile` field; `graphs/gddp-runtime/project.yaml` sets it to `runtime-orchestrator`.
- The field is genuinely optional — nothing breaks or is required when it is absent.
- Each YAML parses (`python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('profiles/*.yaml')]"`).

## Termination contract — stop only when ALL are true
- Only the listed files were created/modified (`git status` confirms scope).
- All four YAML files parse cleanly.
- `git diff` reviewed; branch `feature/t5-shape-profiles` committed in the gddp-config repo.
- Final summary: files changed, parse check result, any ambiguity you hit.
