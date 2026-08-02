from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.runtime.decision_loop import engine
from scripts.runtime.verification.schemas import Verdict


def _write_graph(config_root: Path, project_id: str, node_id: str) -> None:
    graph_root = config_root / "graphs" / project_id
    (graph_root / "nodes").mkdir(parents=True)
    (graph_root / "project.yaml").write_text(
        f"project_id: {project_id}\nrepo: org/missing-repo\n",
        encoding="utf-8",
    )
    (graph_root / "nodes" / f"{node_id}.yaml").write_text(
        f"node_id: {node_id}\nstatus: complete\n",
        encoding="utf-8",
    )


def test_run_verification_unresolved_repo_writes_escalation_receipt_without_verify_or_repo_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_id = "project-a"
    node_id = "done-node"
    config_root = tmp_path / "gddp-config"
    repo_parent = tmp_path / "repos"
    repo_parent.mkdir()
    _write_graph(config_root, project_id, node_id)

    verify = MagicMock(side_effect=AssertionError("verify must not run without a repo checkout"))
    build_toolbox = MagicMock(side_effect=AssertionError("toolbox must not be built without a repo checkout"))
    receipts = []

    monkeypatch.delenv("GDDP_REPO_ROOT", raising=False)
    monkeypatch.delenv("GDDP_REPOS_ROOT", raising=False)
    monkeypatch.setattr(engine.verification_orchestrator, "verify", verify)
    monkeypatch.setattr(engine, "_build_toolbox", build_toolbox)
    monkeypatch.setattr(engine, "write_receipt", lambda receipt, project_id: receipts.append(receipt))

    ctx = SimpleNamespace(
        config_path=config_root,
        project=SimpleNamespace(repo=str(repo_parent / "missing-repo")),
    )
    node = SimpleNamespace(node_id=node_id)

    before = sorted(path.relative_to(repo_parent) for path in repo_parent.rglob("*"))

    result = engine._run_verification(ctx, node, project_id)

    after = sorted(path.relative_to(repo_parent) for path in repo_parent.rglob("*"))
    assert before == after
    verify.assert_not_called()
    build_toolbox.assert_not_called()
    assert result.action == "escalate"
    assert result.reason == "repo_unresolved: resolve_repo_checkout"
    assert result.node_id == node_id
    assert result.project_id == project_id

    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt.project_id == project_id
    assert receipt.node_id == node_id
    assert receipt.verdict == Verdict.NEEDS_HUMAN_REVIEW
    assert receipt.criteria_confidence == 0.0
    assert receipt.semantic is None
    assert receipt.decision_reasoning == "repo checkout unresolved"
    assert receipt.required_next_action == "resolve_repo_checkout"
    assert receipt.deterministic.criteria == []
    assert receipt.deterministic.constraints == []
    assert receipt.deterministic.artifacts_present == {}
    assert receipt.deterministic.deps_status == {}
