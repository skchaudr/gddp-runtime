from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.runtime.verification import cli
from scripts.runtime.verification.schemas import VerdictReceipt


def test_cli_writes_receipt_with_required_contract_fields(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
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
