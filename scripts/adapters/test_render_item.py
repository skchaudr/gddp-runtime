"""Unit tests for mission_projection._render_item."""

from __future__ import annotations

import json
from types import MappingProxyType

from scripts.adapters.executor_protocol import _freeze_json
from scripts.adapters.mission_projection import _render_item


def test_render_item_passes_through_plain_string():
    assert _render_item("Commit on the result ref only") == (
        "Commit on the result ref only"
    )


def test_render_item_serializes_plain_dict_as_sorted_json():
    rendered = _render_item({"id": "report-exists", "criterion": "report exists"})

    assert rendered == json.dumps(
        {"criterion": "report exists", "id": "report-exists"},
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "report-exists" in rendered
    assert "mappingproxy" not in rendered.casefold()


def test_render_item_nested_frozen_mapping_criteria_readable_without_crash():
    """NodePacket freezes criteria as MappingProxyType + tuples; rendering
    must thaw and emit readable JSON text, not raise TypeError."""
    frozen_criterion = _freeze_json(
        {
            "id": "evidence-cited",
            "criterion": "every finding cites a path",
            "nested": {"paths": ["scripts/adapters", "docs"], "required": True},
        }
    )

    assert isinstance(frozen_criterion, MappingProxyType)
    assert isinstance(frozen_criterion["nested"], MappingProxyType)
    assert isinstance(frozen_criterion["nested"]["paths"], tuple)

    rendered = _render_item(frozen_criterion)

    assert isinstance(rendered, str)
    assert rendered.startswith("{")
    assert '"id": "evidence-cited"' in rendered
    assert '"criterion": "every finding cites a path"' in rendered
    assert '"paths": ["scripts/adapters", "docs"]' in rendered
    assert '"required": true' in rendered
    assert "mappingproxy" not in rendered.casefold()
    # Round-trip proves the text is real JSON, not a repr leak.
    assert json.loads(rendered) == {
        "criterion": "every finding cites a path",
        "id": "evidence-cited",
        "nested": {"paths": ["scripts/adapters", "docs"], "required": True},
    }


def test_render_item_frozen_tuple_of_mixed_items_without_crash():
    frozen = _freeze_json(
        (
            {"id": "a", "criterion": "first"},
            "plain constraint",
            {"id": "b", "nested": {"ok": True}},
        )
    )
    assert isinstance(frozen, tuple)
    assert isinstance(frozen[0], MappingProxyType)

    rendered = _render_item(frozen)

    assert isinstance(rendered, str)
    parsed = json.loads(rendered)
    assert parsed == [
        {"criterion": "first", "id": "a"},
        "plain constraint",
        {"id": "b", "nested": {"ok": True}},
    ]
    assert "mappingproxy" not in rendered.casefold()
