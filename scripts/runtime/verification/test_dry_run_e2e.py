"""End-to-end dry-run tests for verify() — no network, no SQLite, zero repo writes."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from scripts.runtime.verification.orchestrator import verify
from scripts.runtime.verification.schemas import SemanticOutput, Verdict, VerdictReceipt
from scripts.runtime.verification.semantic.agent import LLMResponse
from scripts.runtime.verification.semantic.tools import SemanticToolbox


class MockRunner:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content=self.content, tool_calls=[], finish_reason="stop")


def _repo_fingerprint(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(repo.rglob("*"))
        if path.is_file()
    }


def _assert_zero_repo_writes(repo: Path, action) -> VerdictReceipt:
    before = _repo_fingerprint(repo)
    receipt = action()
    after = _repo_fingerprint(repo)
    assert before == after, "verify() must not modify any file in the temp repo"
    return receipt


def _assert_valid_receipt(receipt: VerdictReceipt, *, project_id: str, node_id: str) -> None:
    assert isinstance(receipt, VerdictReceipt)
    assert isinstance(receipt.verdict, Verdict)
    assert receipt.project_id == project_id
    assert receipt.node_id == node_id
    assert 0.0 <= receipt.confidence <= 1.0
    assert receipt.required_next_action
    assert receipt.generated_at


def _clean_pass_fixtures(tmp_path: Path) -> tuple[dict, dict]:
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "common.zsh").write_text(
        "AA_ROOT=/x\nAA_DATA_HOME=/d\nAA_STATE_HOME=/s\nAA_SCHEMA=1\n"
    )
    (tmp_path / "module.py").write_text("VALUE = 1\n")
    (tmp_path / "decision.md").write_text("dry-run evidence\n")

    node_yaml = {
        "node_id": "dry-run-clean",
        "acceptance": [
            {"id": "aa-root-and-state-paths", "criterion": "roots exist"},
        ],
        "constraints": ["preserve targets.conf wiring"],
        "depends_on": ["dep-a"],
        "required_artifacts": ["decision.md"],
    }
    project_yaml = {
        "project_id": "dry-run-project",
        "repo": str(tmp_path),
        "nodes": [{"id": "dep-a", "status": "complete"}],
    }
    return node_yaml, project_yaml


def _indeterminate_fixtures(tmp_path: Path) -> tuple[dict, dict]:
    (tmp_path / "module.py").write_text("# tiny source file for dry-run e2e\n")

    node_yaml = {
        "node_id": "dry-run-indeterminate",
        "acceptance": [
            {
                "id": "acceptance-test-covers-grk",
                "criterion": "acceptance test covers grk sync target",
            },
        ],
        "constraints": ["stay within node scope"],
        "depends_on": ["dep-a"],
    }
    project_yaml = {
        "project_id": "dry-run-project",
        "repo": str(tmp_path),
        "nodes": [{"id": "dep-a", "status": "complete"}],
    }
    return node_yaml, project_yaml


def test_verify_e2e_clean_pass_returns_receipt_without_repo_writes(tmp_path: Path) -> None:
    node_yaml, project_yaml = _clean_pass_fixtures(tmp_path)
    runner = MockRunner("{}")

    receipt = _assert_zero_repo_writes(
        tmp_path,
        lambda: verify(
            node_yaml=node_yaml,
            project_yaml=project_yaml,
            repo=tmp_path,
            runner=runner,
            toolbox=SemanticToolbox(tmp_path),
            now=lambda: "2026-06-30T00:00:00+00:00",
        ),
    )

    _assert_valid_receipt(
        receipt,
        project_id="dry-run-project",
        node_id="dry-run-clean",
    )
    assert runner.calls == 0
    assert receipt.semantic is None
    assert receipt.verdict == Verdict.PASS


def test_verify_e2e_indeterminate_invokes_semantic_without_repo_writes(tmp_path: Path) -> None:
    node_yaml, project_yaml = _indeterminate_fixtures(tmp_path)
    semantic_json = SemanticOutput(
        judgments=[
            {
                "criterion_id": "acceptance-test-covers-grk",
                "judgment": "judged_pass",
                "confidence": 0.75,
                "evidence": ["module.py:1"],
                "reasoning": "Dry-run mock resolved the indeterminate criterion.",
            }
        ],
        overall_reasoning="Dry-run semantic investigation complete.",
        risks=None,
        followup_candidates=None,
        budget_exhausted=False,
    ).model_dump_json()
    runner = MockRunner(semantic_json)

    receipt = _assert_zero_repo_writes(
        tmp_path,
        lambda: verify(
            node_yaml=node_yaml,
            project_yaml=project_yaml,
            repo=tmp_path,
            runner=runner,
            toolbox=SemanticToolbox(tmp_path),
            now=lambda: "2026-06-30T00:00:00+00:00",
        ),
    )

    _assert_valid_receipt(
        receipt,
        project_id="dry-run-project",
        node_id="dry-run-indeterminate",
    )
    assert runner.calls == 1
    assert receipt.semantic is not None
    assert receipt.verdict == Verdict.PASS
