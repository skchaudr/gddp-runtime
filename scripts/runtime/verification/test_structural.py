"""Tests for the structural validator — pure, no mocking required."""

import pytest

from scripts.runtime.verification.structural import (
    check_acceptance_not_weakened,
    check_acyclic,
    check_artifacts_exist,
    check_files_in_scope,
    check_graph_legality,
    run_structural_validator,
)
from scripts.runtime.verification.invariant_schema import (
    InvariantResult,
    StructuralOutput,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture()
def valid_graph():
    return {
        "nodes": {
            "spec": {
                "depends_on": [],
                "artifacts": ["docs/spec.md"],
                "allowed_paths": ["docs/"],
            },
            "parser": {
                "depends_on": ["spec"],
                "artifacts": ["src/parser.py"],
                "allowed_paths": ["src/"],
            },
        }
    }


@pytest.fixture()
def valid_node(valid_graph):
    return valid_graph["nodes"]["parser"]


# ── check_graph_legality ──────────────────────────────────────────────────

class TestCheckGraphLegality:
    def test_valid_graph_passes(self, valid_graph):
        r = check_graph_legality(valid_graph)
        assert r.check == "graph_legality"
        assert r.passed is True

    def test_missing_dependency_fails(self):
        graph = {"nodes": {"a": {"depends_on": ["b"]}}}
        r = check_graph_legality(graph)
        assert r.passed is False
        assert "b" in r.evidence

    def test_empty_graph_passes(self):
        r = check_graph_legality({"nodes": {}})
        assert r.passed is True


# ── check_acyclic ─────────────────────────────────────────────────────────

class TestCheckAcyclic:
    def test_valid_graph_passes(self, valid_graph):
        r = check_acyclic(valid_graph)
        assert r.check == "graph_acyclic"
        assert r.passed is True

    def test_cyclic_graph_fails(self):
        graph = {
            "nodes": {
                "a": {"depends_on": ["b"]},
                "b": {"depends_on": ["a"]},
            }
        }
        r = check_acyclic(graph)
        assert r.passed is False
        assert "Cycle" in r.evidence

    def test_three_node_cycle_fails(self):
        graph = {
            "nodes": {
                "a": {"depends_on": ["c"]},
                "b": {"depends_on": ["a"]},
                "c": {"depends_on": ["b"]},
            }
        }
        r = check_acyclic(graph)
        assert r.passed is False

    def test_empty_graph_passes(self):
        r = check_acyclic({"nodes": {}})
        assert r.passed is True


# ── check_artifacts_exist ─────────────────────────────────────────────────

class TestCheckArtifactsExist:
    def test_all_present_passes(self):
        r = check_artifacts_exist(["docs/spec.md"], ["docs/spec.md", "src/main.py"])
        assert r.check == "artifacts_exist"
        assert r.passed is True

    def test_missing_artifact_fails(self):
        r = check_artifacts_exist(["docs/spec.md", "docs/plan.md"], ["docs/spec.md"])
        assert r.passed is False
        assert "docs/plan.md" in r.evidence

    def test_empty_declared_passes_vacuously(self):
        r = check_artifacts_exist([], ["anything"])
        assert r.passed is True


# ── check_files_in_scope ──────────────────────────────────────────────────

class TestCheckFilesInScope:
    def test_in_scope_passes(self):
        r = check_files_in_scope(["src/parser.py", "src/lexer.py"], ["src/"])
        assert r.check == "files_in_scope"
        assert r.passed is True

    def test_out_of_scope_fails(self):
        r = check_files_in_scope(["src/parser.py", "secret/key.pem"], ["src/"])
        assert r.passed is False
        assert "secret/key.pem" in r.evidence

    def test_multiple_prefixes(self):
        r = check_files_in_scope(
            ["src/parser.py", "docs/spec.md", "secret/key.pem"],
            ["src/", "docs/"],
        )
        assert r.passed is False

    def test_no_changed_files_vacuously_passes(self):
        r = check_files_in_scope([], ["src/"])
        assert r.passed is True

    def test_no_allowed_paths_fails(self):
        r = check_files_in_scope(["src/parser.py"], [])
        assert r.passed is False


# ── check_acceptance_not_weakened ─────────────────────────────────────────

class TestCheckAcceptanceNotWeakened:
    def test_no_removal_passes(self):
        r = check_acceptance_not_weakened(
            ["must parse JSON", "must handle errors"],
            ["must parse JSON", "must handle errors", "new criterion"],
        )
        assert r.check == "acceptance_not_weakened"
        assert r.passed is True

    def test_removed_criterion_fails(self):
        r = check_acceptance_not_weakened(
            ["must parse JSON", "must handle errors"],
            ["must parse JSON"],
        )
        assert r.passed is False
        assert "must handle errors" in r.evidence

    def test_empty_before_vacuously_passes(self):
        r = check_acceptance_not_weakened([], ["anything"])
        assert r.passed is True


# ── run_structural_validator (integration) ────────────────────────────────

class TestRunner:
    def test_valid_graph_all_passed(self, valid_graph, valid_node):
        out = run_structural_validator(
            graph=valid_graph,
            node=valid_node,
            changed_files=["src/parser.py"],
            present_paths=["src/parser.py", "docs/spec.md"],
            acceptance_before=["must parse JSON"],
            acceptance_after=["must parse JSON", "new criterion"],
        )
        assert isinstance(out, StructuralOutput)
        assert out.all_passed is True
        assert len(out.results) == 5
        assert all(isinstance(r, InvariantResult) for r in out.results)

    def test_cyclic_graph_all_passed_false(self, valid_node):
        cyclic_graph = {
            "nodes": {
                "a": {"depends_on": ["b"], "artifacts": [], "allowed_paths": []},
                "b": {"depends_on": ["a"], "artifacts": [], "allowed_paths": []},
            }
        }
        out = run_structural_validator(
            graph=cyclic_graph,
            node=cyclic_graph["nodes"]["a"],
            changed_files=[],
            present_paths=[],
            acceptance_before=[],
            acceptance_after=[],
        )
        assert out.all_passed is False
        acyclic_results = [r for r in out.results if r.check == "graph_acyclic"]
        assert acyclic_results[0].passed is False

    def test_missing_artifact_all_passed_false(self, valid_graph, valid_node):
        out = run_structural_validator(
            graph=valid_graph,
            node=valid_node,
            changed_files=["src/parser.py"],
            present_paths=["docs/spec.md"],  # missing src/parser.py (parser's artifact)
            acceptance_before=[],
            acceptance_after=[],
        )
        assert out.all_passed is False

    def test_out_of_scope_all_passed_false(self, valid_graph, valid_node):
        out = run_structural_validator(
            graph=valid_graph,
            node=valid_node,
            changed_files=["src/parser.py", "secret/key.pem"],
            present_paths=["src/parser.py", "docs/spec.md"],
            acceptance_before=[],
            acceptance_after=[],
        )
        assert out.all_passed is False

    def test_acceptance_weakening_all_passed_false(self, valid_graph, valid_node):
        out = run_structural_validator(
            graph=valid_graph,
            node=valid_node,
            changed_files=["src/parser.py"],
            present_paths=["src/parser.py", "docs/spec.md"],
            acceptance_before=["must parse JSON", "must handle errors"],
            acceptance_after=["must parse JSON"],
        )
        assert out.all_passed is False
