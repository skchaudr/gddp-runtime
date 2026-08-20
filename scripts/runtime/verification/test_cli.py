from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.runtime.verification import cli
from scripts.runtime.verification.schemas import (
    DeterministicResult,
    HumanReviewQuestion,
    SemanticOutput,
    Verdict,
    VerdictReceipt,
)


def test_cli_writes_receipt_with_required_contract_fields(tmp_path: Path, capsys, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    (repo / "PROJECT-BRIEF.md").write_text("Brief\n", encoding="utf-8")
    node_yaml = tmp_path / "node.yaml"
    project_yaml = tmp_path / "project.yaml"
    receipt_dir = tmp_path / "receipts"

    node_yaml.write_text(
        yaml.safe_dump(
            {
                "node_id": "contract-node",
                "acceptance_criteria": [
                    {"id": "contract-doc-exists", "criterion": "docs/contract.md exists"},
                ],
                "depends_on": ["dep-a"],
                "required_artifacts": ["decision.md"],
            }
        ),
        encoding="utf-8",
    )
    project_yaml.write_text(
        yaml.safe_dump(
            {
                "project_id": "project-a",
                "nodes": [{"id": "dep-a", "status": "complete"}],
            }
        ),
        encoding="utf-8",
    )

    # Offline (default) mode wires _offline_semantic_skip: the semantic lane
    # is intentionally not run and decide() sees no semantic input. No mock
    # harness is needed — the stub is the production offline behavior.
    assert cli.main(
        [
            "--node-yaml",
            str(node_yaml),
            "--project-yaml",
            str(project_yaml),
            "--repo",
            str(repo),
            "--receipt-dir",
            str(receipt_dir),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    receipt_path = Path(output["receipt_path"])
    assert receipt_path == receipt_dir / "project-a" / "contract-node.json"
    receipt = VerdictReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    assert receipt.verdict.value == output["verdict"]
    assert receipt.completeness_status == output["completeness_status"]
    assert receipt.required_next_action == output["required_next_action"]
    assert output["context_coverage"] == {
        "criteria": "not_run", "integrity": "none", "overall": "none",
    }
    assert output["lane_status"] == {"criteria": "not_run", "integrity": "not_run"}
    assert output["harness_error"] == {"criteria": None, "integrity": None}
    timing = output["evaluation_timing"]
    assert timing["criteria"]["status"] == "not_run"
    assert timing["integrity"]["status"] == "not_run"
    assert timing["wall_s"] >= 0
    assert receipt.evaluation_timing is not None
    assert receipt.evaluation_timing.wall_s == timing["wall_s"]


def test_live_runner_auto_prefers_deepseek(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("GLM_API_KEY", "glm-key")

    args = cli.build_parser().parse_args(
        [
            "--node-yaml",
            "node.yaml",
            "--project-yaml",
            "project.yaml",
            "--repo",
            ".",
            "--semantic-mode",
            "live",
        ]
    )

    runner = cli._build_runner(args)

    assert runner.model == "deepseek-chat"
    assert runner.base_url == "https://api.deepseek.com"
    assert runner.max_tokens == 4096


def test_live_runner_can_target_glm_with_env_overrides(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("GLM_API_KEY", "glm-key")
    monkeypatch.setenv("GLM_BASE_URL", "https://example.test/v4")
    monkeypatch.setenv("GLM_MODEL", "glm-test")

    args = cli.build_parser().parse_args(
        [
            "--node-yaml",
            "node.yaml",
            "--project-yaml",
            "project.yaml",
            "--repo",
            ".",
            "--semantic-mode",
            "live",
            "--semantic-provider",
            "glm",
        ]
    )

    runner = cli._build_runner(args)

    assert runner.model == "glm-test"
    assert runner.base_url == "https://example.test/v4"


def test_live_runner_uses_provider_response_limit(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")

    args = cli.build_parser().parse_args(
        [
            "--node-yaml",
            "node.yaml",
            "--project-yaml",
            "project.yaml",
            "--repo",
            ".",
            "--semantic-mode",
            "live",
            "--semantic-provider-max-tokens",
            "8192",
        ]
    )

    runner = cli._build_runner(args)

    assert runner.max_tokens == 8192


def test_semantic_budget_args_parse_env_and_cli(monkeypatch) -> None:
    monkeypatch.setenv("GDDP_SEMANTIC_MAX_TURNS", "21")
    monkeypatch.setenv("GDDP_SEMANTIC_MAX_TOOL_CALLS", "77")
    monkeypatch.setenv("GDDP_SEMANTIC_MAX_TOOL_RESULT_CHARS", "12345")

    args = cli.build_parser().parse_args(
        [
            "--node-yaml",
            "node.yaml",
            "--project-yaml",
            "project.yaml",
            "--repo",
            ".",
            "--semantic-max-tokens",
            "96000",
        ]
    )

    assert args.semantic_max_turns == 21
    assert args.semantic_max_tool_calls == 77
    assert args.semantic_max_tokens == 96000
    assert args.semantic_max_tool_result_chars == 12345


def test_live_runner_requires_selected_provider_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    args = cli.build_parser().parse_args(
        [
            "--node-yaml",
            "node.yaml",
            "--project-yaml",
            "project.yaml",
            "--repo",
            ".",
            "--semantic-mode",
            "live",
            "--semantic-provider",
            "deepseek",
        ]
    )

    try:
        cli._build_runner(args)
    except RuntimeError as exc:
        assert "DEEPSEEK_API_KEY" in str(exc)
    else:
        raise AssertionError("expected missing provider key to fail")


def test_pi_provider_supports_chatgpt_oauth(monkeypatch, tmp_path: Path) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps({"openai-codex": {"type": "oauth", "access": "test"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GDDP_PI_AUTH_FILE", str(auth_file))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    args = cli.build_parser().parse_args(
        [
            "--node-yaml", "node.yaml",
            "--project-yaml", "project.yaml",
            "--repo", ".",
            "--semantic-mode", "live",
            "--semantic-harness", "pi",
            "--semantic-provider", "chatgpt",
        ]
    )

    assert cli._pi_provider(args) == "openai-codex"


def test_pi_provider_auto_falls_back_to_chatgpt_oauth(monkeypatch, tmp_path: Path) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps({"openai-codex": {"type": "oauth", "access": "test"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GDDP_PI_AUTH_FILE", str(auth_file))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    args = cli.build_parser().parse_args(
        ["--node-yaml", "node.yaml", "--project-yaml", "project.yaml", "--repo", "."]
    )

    assert cli._pi_provider(args) == "openai-codex"


def test_pi_provider_rejects_glm() -> None:
    args = cli.build_parser().parse_args(
        [
            "--node-yaml", "node.yaml",
            "--project-yaml", "project.yaml",
            "--repo", ".",
            "--semantic-provider", "glm",
        ]
    )

    try:
        cli._pi_provider(args)
    except RuntimeError as exc:
        assert "does not allow GLM" in str(exc)
    else:
        raise AssertionError("expected evaluator Pi to reject GLM")


def test_cli_summary_includes_orphaned_intelligence_fields(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """risks/followups/human_review_questions reach the operator summary."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    node_yaml = tmp_path / "node.yaml"
    project_yaml = tmp_path / "project.yaml"
    receipt_dir = tmp_path / "receipts"
    node_yaml.write_text(
        yaml.safe_dump({"node_id": "orphan-node", "acceptance_criteria": []}),
        encoding="utf-8",
    )
    project_yaml.write_text(
        yaml.safe_dump({"project_id": "project-orphan", "nodes": []}),
        encoding="utf-8",
    )

    receipt = VerdictReceipt(
        project_id="project-orphan",
        node_id="orphan-node",
        verdict=Verdict.PASS,
        confidence=0.9,
        criteria_confidence=0.9,
        completeness=1.0,
        graph_readiness=0.9,
        completeness_status="complete",
        deterministic=DeterministicResult(
            criteria=[],
            constraints=[],
            artifacts_present={},
            deps_status={},
            criteria_mismatches=[],
            missing_evidence=[],
            human_review_questions=[
                HumanReviewQuestion(
                    criterion_id="c1", question="Is this criterion path stale?"
                )
            ],
        ),
        semantic=SemanticOutput(
            judgments=[],
            overall_reasoning="done",
            risks="Risk: queries rely on self-reported timestamps.",
            followup_candidates="Human clarification: is X part of the criteria?",
            budget_exhausted=False,
        ),
        decision_reasoning="pass",
        required_next_action="accept",
        generated_at="2026-01-01T00:00:00+00:00",
    )

    monkeypatch.setattr(cli, "verify", lambda **kwargs: receipt)
    monkeypatch.setattr(cli, "write_receipt", lambda *a, **kw: tmp_path / "fake.json")

    assert cli.main(
        [
            "--node-yaml", str(node_yaml),
            "--project-yaml", str(project_yaml),
            "--repo", str(repo),
            "--receipt-dir", str(receipt_dir),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["semantic_risks"] == "Risk: queries rely on self-reported timestamps."
    assert (
        output["followup_candidates"]
        == "Human clarification: is X part of the criteria?"
    )
    assert output["human_review_questions"] == [
        {"criterion_id": "c1", "question": "Is this criterion path stale?"}
    ]


def test_cli_summary_omits_orphaned_fields_when_empty(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Empty/None intelligence fields are absent, not null, in the summary."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    node_yaml = tmp_path / "node.yaml"
    project_yaml = tmp_path / "project.yaml"
    receipt_dir = tmp_path / "receipts"
    node_yaml.write_text(
        yaml.safe_dump({"node_id": "orphan-node", "acceptance_criteria": []}),
        encoding="utf-8",
    )
    project_yaml.write_text(
        yaml.safe_dump({"project_id": "project-orphan", "nodes": []}),
        encoding="utf-8",
    )

    receipt = VerdictReceipt(
        project_id="project-orphan",
        node_id="orphan-node",
        verdict=Verdict.PASS,
        confidence=0.9,
        criteria_confidence=0.9,
        completeness=1.0,
        graph_readiness=0.9,
        completeness_status="complete",
        deterministic=DeterministicResult(
            criteria=[],
            constraints=[],
            artifacts_present={},
            deps_status={},
            criteria_mismatches=[],
            missing_evidence=[],
            human_review_questions=[],
        ),
        semantic=SemanticOutput(
            judgments=[],
            overall_reasoning="done",
            risks=None,
            followup_candidates=None,
            budget_exhausted=False,
        ),
        decision_reasoning="pass",
        required_next_action="accept",
        generated_at="2026-01-01T00:00:00+00:00",
    )

    monkeypatch.setattr(cli, "verify", lambda **kwargs: receipt)
    monkeypatch.setattr(cli, "write_receipt", lambda *a, **kw: tmp_path / "fake.json")

    assert cli.main(
        [
            "--node-yaml", str(node_yaml),
            "--project-yaml", str(project_yaml),
            "--repo", str(repo),
            "--receipt-dir", str(receipt_dir),
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert "semantic_risks" not in output
    assert "followup_candidates" not in output
    assert "human_review_questions" not in output
