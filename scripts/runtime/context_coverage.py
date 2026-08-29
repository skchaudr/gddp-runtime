"""Context coverage over canonical ExecutorEvents — transport-neutral.

Were the pointers the project zone offered actually opened? The rating is
GDDP policy (docs/proposals/executor-capability-contract.md, P3), so it lives
here rather than inside one transport's file, and it reads only the canonical
vocabulary (adapters/executor_events.py) so a second transport is a reuse
rather than a copy.

Semantics are ported verbatim from the pi implementation
(scripts/adapters/pi_rpc_adapter.py:497-650): same doc/neighbor pointer keys,
same base resolution, same none/low/medium/high rating, same "None when
nothing ratable was offered" rule. The pi adapter keeps its own copy this
wave; only the event shape changes here.

The start/end join that implementation needs is gone: canonical
``tool_completed`` is self-contained (carries tool and paths alongside ok, per
docs/proposals/executor-event-vocabulary.md §4), so coverage is a one-pass
filter and a start with no completion cannot count.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from adapters.executor_events import CONTENT_TOOLS, ExecutorEvent

# Mirrors scripts/runtime/verification/orchestrator.py: "invariants" is
# optional per project, so it is offered to the model but never rated —
# counting it would penalize a project that simply has no invariant doc.
DOC_POINTER_KEYS = frozenset({"readme", "project_brief"})


def extract_read_paths(
    events: Sequence[ExecutorEvent], *, base: Path | None = None
) -> set[str]:
    """Resolved paths of successful read/grep calls in one canonical stream.

    read/grep examine content. ls/find only prove awareness that a path
    exists, which is not evidence the pointer was consumed — hence
    ``CONTENT_TOOLS`` rather than every tool that carries a path.

    A failed call (``ok`` False) is excluded rather than counted as coverage,
    and a tool call that never completed emits no ``tool_completed`` at all,
    so both exclusions the pi two-pass loop made by joining on toolCallId fall
    out of the filter. Relative paths are real and resolve against ``base``,
    which is the cwd the harness resolved them against.
    """
    accessed: set[str] = set()
    for event in events:
        if event.type != "tool_completed" or not event.ok:
            continue
        if event.tool not in CONTENT_TOOLS:
            continue
        for path in event.paths:
            if path:
                accessed.add(resolve_read_path(path, base))
    return accessed


def compute_turn_context_coverage(
    *,
    pointers: Mapping[str, str],
    events: Sequence[ExecutorEvent],
    base: Path | None = None,
) -> dict | None:
    """Coverage record for ONE executor turn: offered pointers vs reads.

      none   — no offered pointer was read
      low    — something offered was read, but no canonical doc
      medium — a doc was read, no neighbor read while neighbors were offered
      high   — a doc was read and (a neighbor was read, or none were offered)

    ``outside_pointers`` is the research-drift signal: read paths that were
    never offered. An executor rediscovering the project shows up as a long
    list here regardless of its rating.

    Returns None when nothing ratable was offered, so a packet with no
    pointers produces no artifact instead of a misleading "none".
    """
    offered_docs: set[str] = set()
    offered_neighbors: set[str] = set()
    unavailable: list[str] = []
    for raw_key, value in pointers.items():
        key = str(raw_key)
        if not isinstance(value, str) or value.startswith("UNAVAILABLE"):
            unavailable.append(key)
            continue
        resolved = resolve_read_path(value, None)
        if key in DOC_POINTER_KEYS:
            offered_docs.add(resolved)
        elif key == "foundational_node" or key.startswith("neighbor:"):
            offered_neighbors.add(resolved)

    all_offered = offered_docs | offered_neighbors
    if not all_offered:
        return None

    read_paths = extract_read_paths(events, base=base)
    accessed = read_paths & all_offered
    accessed_docs = read_paths & offered_docs
    accessed_neighbors = read_paths & offered_neighbors

    if not accessed:
        rating = "none"
    elif not accessed_docs:
        rating = "low"
    elif not accessed_neighbors and offered_neighbors:
        rating = "medium"
    else:
        rating = "high"

    return {
        "rating": rating,
        "offered": len(all_offered),
        "content_accessed": len(accessed),
        "not_observed": len(all_offered - accessed),
        "offered_paths": sorted(all_offered),
        "accessed_paths": sorted(accessed),
        "not_observed_paths": sorted(all_offered - accessed),
        "groups": {
            "docs": _pointer_group(offered_docs, read_paths),
            "neighbors": _pointer_group(offered_neighbors, read_paths),
        },
        "read_paths": sorted(read_paths),
        "outside_pointers": sorted(read_paths - all_offered),
        "unavailable_pointer_keys": sorted(unavailable),
    }


def _pointer_group(offered: set[str], read_paths: set[str]) -> dict:
    accessed = offered & read_paths
    return {
        "offered": len(offered),
        "content_accessed": len(accessed),
        "accessed_paths": sorted(accessed),
        "not_observed_paths": sorted(offered - accessed),
    }


def resolve_read_path(path: str, base: Path | None) -> str:
    candidate = Path(path)
    if not candidate.is_absolute() and base is not None:
        candidate = base / candidate
    try:
        return str(candidate.resolve())
    except OSError:
        return str(candidate)
