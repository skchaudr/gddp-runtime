"""Guards the cross-repo contract for scripts/node_status_history.py.

This module has zero importers in this repo and a live consumer in the other
one: gddp-config/scripts/node_cli.py loads it by *file path* via
importlib.util.spec_from_file_location, resolved from runtime_root() at call
time. Nothing in this repo's import graph names it, so ordinary orphan analysis
reports it as dead. It is not — it backs `node set-status`, the human
acceptance ledger, and node_cli fails closed without it.

It was deleted on exactly that reasoning in c4f0bab and restored in e77fec8.
This test exists so the next deletion turns a silent cross-repo break into a
red suite. See .handoffs/084.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "node_status_history.py"


def _load_the_way_node_cli_does():
    """Load by path, mirroring gddp-config node_cli._load_status_history_mod."""
    spec = importlib.util.spec_from_file_location(
        "node_status_history", _MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_exists_at_the_path_node_cli_resolves():
    """node_cli builds runtime_root()/"scripts"/"node_status_history.py"."""
    assert _MODULE_PATH.is_file(), (
        f"{_MODULE_PATH} is missing. gddp-config node_cli.py loads this by "
        "path for `node set-status`; without it the human acceptance path "
        "fails closed and no node can be moved to complete. It has no "
        "importers here by design — that is not evidence it is unused."
    )


def test_exposes_every_name_node_cli_calls():
    """The cross-repo surface, enumerated from node_cli's `hist_mod.` calls.

    node_cli.py:1770 append_status_change; :1010, :1532, :1541 latest_reason.
    Renaming either is a cross-repo break no import will flag.
    """
    module = _load_the_way_node_cli_does()
    for name in ("append_status_change", "latest_reason"):
        assert callable(getattr(module, name, None)), (
            f"{name} is called by gddp-config node_cli.py on a module it "
            "loaded by path. Renaming it here breaks that call at runtime "
            "with nothing in this repo referencing the old name."
        )


def test_appended_reason_comes_back_for_the_status_it_was_written_for(tmp_path):
    """The ledger's purpose is the reason, and node_cli reads it back filtered.

    latest_reason(matching_to_status=...) is how node_cli avoids attaching a
    stale reason to current graph truth — exercise that shape, not just append.
    """
    module = _load_the_way_node_cli_does()
    module.append_status_change(
        project_id="proj",
        node_id="node-01",
        from_status="in_progress",
        to_status="complete",
        reason="human accepted after review",
        kind="graph",
        source="test",
        runtime_root=tmp_path,
    )

    record = module.latest_reason(
        "proj", "node-01", runtime_root=tmp_path, matching_to_status="complete"
    )
    assert record is not None
    assert record["reason"] == "human accepted after review"

    # A reason written for a different transition must not be served up as the
    # justification for this one.
    assert (
        module.latest_reason(
            "proj",
            "node-01",
            runtime_root=tmp_path,
            matching_to_status="blocked",
        )
        is None
    )
