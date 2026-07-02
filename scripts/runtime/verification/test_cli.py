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
                "acceptance": [
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
    assert receipt.confidence == receipt.criteria_confidence
    assert receipt.completeness_status == output["completeness_status"]
    assert receipt.required_next_action == output["required_next_action"]
