# Cleanup opportunities

This is a conditional inventory of real cleanup seams, not authorization to delete or refactor them.

## Scan result

No `TODO` or `FIXME` markers were found in non-test or test Python under `/Users/sab-mini/repos/gddp-runtime/scripts/`. Cleanup debt is architectural and size-related rather than marker-driven.

## Large modules

The largest non-test source files in the current worktree are:

| File | Lines | Opportunity |
| --- | ---: | --- |
| `scripts/runtime/heartbeat/reconciler.py` | 1,478 | Separate polling/collection, evaluation finalization, retry routing, and provisional transition only where existing contracts permit |
| `scripts/runtime/verification/deterministic/probes.py` | 1,021 | Group probes by evidence domain while preserving one deterministic result contract |
| `scripts/adapters/mission_evidence.py` | 889 | Isolate artifact parsing, git verification, and quarantine-reason assembly |
| `scripts/runtime/heartbeat/runner.py` | 821 | Keep orchestration visible; extract only cohesive phases, not another scheduler |
| `scripts/adapters/mission_adapter.py` | 707 | Separate process/session persistence from mission-specific projection where seams are already proven |

Line count is a navigation signal, not proof of bad design. Refactor only with characterization tests and a demonstrated deep-module boundary.

## Inherited and legacy surfaces

- `/Users/sab-mini/repos/gddp-runtime/scripts/runtime/decision_loop/` is an older control plane. The heartbeat does not use it as its live dispatcher, and its historical complete-only assumptions can disagree with provisional flow. Decide whether any powers remain useful before archiving or converging it.
- `/Users/sab-mini/repos/gddp-runtime/scripts/adapters/jules_cli_adapter.py` is described inconsistently: older docs call it a stub or superseded, while the current file contains a protocol implementation. Verify against the installed Jules CLI before changing its status.
- `/Users/sab-mini/repos/gddp-runtime/deploy/_archive/` intentionally preserves dead Big Pi topology. Keep it visibly archived and never use it for fresh-host setup.
- `/Users/sab-mini/repos/gddp-runtime/docs/archive/` contains prior designs. It is useful history but should not outrank canonical documents.
- Dependency-satisfaction policy has historically appeared in multiple places (`scope_checker`, config-side frontier, verification, and old decision-loop code). A future convergence should first inventory current consumers rather than assume the July 2026 list remains exact.

The repository warning applies here: do not add a compatibility layer around inherited machinery until verifying whether the inherited mechanism should continue to exist.
