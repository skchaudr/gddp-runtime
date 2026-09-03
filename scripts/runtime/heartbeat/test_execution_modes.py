"""Executor mode registry: what dispatch can route, and what a node omitting
a transport declaration means.

`allowed_execution_modes` was a day-one schema field (2026-03-12) that never
had a design discussion, and it conflates two unrelated questions: whether a
machine may do the work at all (`human` vs `agent` — genuine graph truth) and
which binary runs it (`droid`, `pi_rpc`, ... — evidence, not intent). These
tests pin the parts of that shape the runtime owns.
"""

from __future__ import annotations

from types import SimpleNamespace

from scripts.runtime.heartbeat import dispatcher
from scripts.runtime.heartbeat.frontier import _auto_dispatch_routing
from scripts.runtime.heartbeat.graph_reader import (
    ABSTRACT_EXECUTION_MODES,
    EXECUTION_MODE_ADAPTERS,
    GraphReader,
)


def _write_node(config_root, body: str = "") -> None:
    nodes_dir = config_root / "graphs" / "proj" / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    (nodes_dir / "node-1.yaml").write_text(
        f"node_id: node-1\ntitle: Node one\n{body}"
    )


# --------------------------------------------------------------------------- #
# The registry must not drift from the adapters that actually exist
# --------------------------------------------------------------------------- #


def test_execution_mode_adapters_match_dispatch_registry():
    """graph_reader cannot import dispatcher (dispatcher imports graph_reader),
    so the mode registry is a hand-kept copy. This test is the only thing
    keeping the copy honest.

    It rotted before: `jules_cli`, `pi_worker`, `vertex`, and `vm_worker` were
    registered as valid execution modes with no adapter behind any of them and
    no usage in any graph, while `cursor_cli` had to be hand-added when its
    adapter landed. A node declaring a phantom mode passed validation and then
    failed at dispatch with "Unknown executor", losing the job.
    """
    routable = set(dispatcher.ADAPTERS) | set(dispatcher.MEDIATED_ADAPTERS)

    assert EXECUTION_MODE_ADAPTERS == routable | ABSTRACT_EXECUTION_MODES, (
        "execution mode registry drifted from the adapter registry; "
        f"only in modes: {sorted(EXECUTION_MODE_ADAPTERS - routable - ABSTRACT_EXECUTION_MODES)}, "
        f"only in adapters: {sorted(routable - EXECUTION_MODE_ADAPTERS)}"
    )


def test_abstract_modes_have_no_adapter_and_must_not_get_one():
    """`agent` and `human` name who may do the work, not which binary does it.

    If either ever acquires an adapter entry it has stopped being abstract,
    and _executor_allowed's refusal to accept it as a concrete choice becomes
    wrong rather than protective.
    """
    routable = set(dispatcher.ADAPTERS) | set(dispatcher.MEDIATED_ADAPTERS)

    assert ABSTRACT_EXECUTION_MODES.isdisjoint(routable)


def test_no_phantom_modes_remain():
    """Regression pin on the four names that were registered with no adapter."""
    for phantom in ("jules_cli", "pi_worker", "vertex", "vm_worker"):
        assert phantom not in EXECUTION_MODE_ADAPTERS


# --------------------------------------------------------------------------- #
# An omitted declaration means "any agent", not a brand
# --------------------------------------------------------------------------- #


def test_omitted_execution_modes_default_to_neutral_agent(tmp_path):
    """The old default was ["jules"]: a node whose author made no transport
    decision was silently brand-locked to a dead executor.
    """
    _write_node(tmp_path)

    node = GraphReader(str(tmp_path)).load_node("proj", "node-1")

    assert node.allowed_execution_modes == ["agent"]


def test_neutral_default_accepts_any_registered_executor(tmp_path):
    """The point of the neutral default: a preselected concrete executor is
    permitted without naming a brand in graph truth."""
    from scripts.runtime.heartbeat.classifier import _executor_allowed

    _write_node(tmp_path)
    node = GraphReader(str(tmp_path)).load_node("proj", "node-1")

    for executor in sorted(dispatcher.ADAPTERS):
        assert _executor_allowed(executor, node.allowed_execution_modes)


def test_an_explicit_declaration_is_still_honored(tmp_path):
    """Neutral-by-default must not become neutral-always: a node that names a
    transport keeps that constraint."""
    _write_node(tmp_path, "allowed_execution_modes:\n  - local_subprocess\n")

    node = GraphReader(str(tmp_path)).load_node("proj", "node-1")

    assert node.allowed_execution_modes == ["local_subprocess"]


# --------------------------------------------------------------------------- #
# Auto-advance must not inject a default the operator never set
# --------------------------------------------------------------------------- #


def _project(policy: dict):
    return SimpleNamespace(execution_policy=policy)


def test_auto_advance_routing_uses_the_configured_default():
    routing = _auto_dispatch_routing(_project({"default_executor": "pi_rpc"}))

    assert routing == {"selected_executor": "pi_rpc"}


def test_auto_advance_routing_is_empty_without_a_configured_default():
    """Previously this fell back to "jules". The classifier then refused the
    event outright (returning None) unless the node happened to list jules,
    so auto-advance died silently on a brand nobody configured.
    """
    assert _auto_dispatch_routing(_project({})) == {}


def test_auto_advance_without_a_default_lets_the_node_decide(tmp_path):
    """With no preselection, _pick_executor falls through to the node's own
    declaration rather than a synthesized brand."""
    from scripts.runtime.heartbeat.classifier import _pick_executor

    _write_node(tmp_path, "allowed_execution_modes:\n  - droid\n")
    node = GraphReader(str(tmp_path)).load_node("proj", "node-1")

    assert _auto_dispatch_routing(_project({})) == {}
    assert _pick_executor(node) == "droid"
