"""Tests for the read-only shape profile loader."""

from __future__ import annotations

from .shape_profiles import load_shape_profile

REQUIRED_KEYS = frozenset(
    {
        "profile_id",
        "description",
        "expected_node_chain",
        "invariant_rules",
        "anti_patterns",
    }
)


def _assert_valid_profile(profile: dict, expected_id: str) -> None:
    assert isinstance(profile, dict)
    assert REQUIRED_KEYS.issubset(profile.keys())
    assert profile["profile_id"] == expected_id
    assert isinstance(profile["description"], str) and profile["description"]
    assert isinstance(profile["expected_node_chain"], list) and profile["expected_node_chain"]
    assert isinstance(profile["invariant_rules"], list) and profile["invariant_rules"]
    assert isinstance(profile["anti_patterns"], list) and profile["anti_patterns"]


def test_load_cli_tool_profile():
    profile = load_shape_profile("cli_tool")
    assert profile is not None
    _assert_valid_profile(profile, "cli_tool")
    joined = " ".join(profile["invariant_rules"] + profile["anti_patterns"]).lower()
    assert "console-scripts" in joined or "console-script" in joined


def test_load_runtime_orchestrator_profile():
    profile = load_shape_profile("runtime_orchestrator")
    assert profile is not None
    _assert_valid_profile(profile, "runtime_orchestrator")
    joined = " ".join(profile["invariant_rules"] + profile["anti_patterns"]).lower()
    assert "executor-specific" in joined or "executor specific" in joined


def test_load_nonexistent_profile_returns_none():
    assert load_shape_profile("nonexistent") is None
