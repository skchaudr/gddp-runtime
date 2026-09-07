from __future__ import annotations

import hashlib
import re

import pytest

from scripts.adapters.mission_evidence import _manifest_name


def test_manifest_name_preserves_allowed_characters():
    feature_id = "Feature_123-abc_def"
    name = _manifest_name(feature_id)
    assert name.startswith(f"{feature_id}--")


def test_manifest_name_sanitizes_unsafe_characters_and_strips_dashes():
    name = _manifest_name("--feat/name with spaces@123!!--")
    assert name.startswith("feat-name-with-spaces-123--")


@pytest.mark.parametrize("feature_id", ["", "---", "###", "///"])
def test_manifest_name_fallback_on_empty_or_stripped_id(feature_id):
    name = _manifest_name(feature_id)
    assert name.startswith("feature--")


def test_manifest_name_deterministic_12_hex_digest():
    feature_id = "node-11-test-manifest-name"
    expected_digest = hashlib.sha256(feature_id.encode()).hexdigest()[:12]
    first = _manifest_name(feature_id)
    second = _manifest_name(feature_id)

    assert first == second
    assert first == f"{feature_id}--{expected_digest}.json"
    match = re.fullmatch(r"node-11-test-manifest-name--([0-9a-f]{12})\.json", first)
    assert bool(match)
    assert match.group(1) == expected_digest
