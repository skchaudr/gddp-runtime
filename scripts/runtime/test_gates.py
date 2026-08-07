"""
test_gates.py — Tests for the gate-token writer/reader/satisfaction checker.

These tests prove the actual contracts: atomic concurrent writes never
produce invalid JSON, hook fires on pass (not fail), schema validation
rejects empty objects, and revocation works.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

# Make scripts/ importable when run as a module from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.gates import gate_satisfied, read_gate, revoke_gate, write_gate


def test_write_gate_roundtrip(tmp_path: Path) -> None:
    """write_gate then read_gate returns the same content."""
    repo = tmp_path / "repo"
    repo.mkdir()
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"verdict": "pass"}')

    path = write_gate(str(repo), "node-01", str(receipt))
    assert path is not None
    assert path.exists()

    data = read_gate(str(repo), "node-01")
    assert data is not None
    assert data["node_id"] == "node-01"
    assert "issued_at" in data
    assert "verdict_receipt_sha256" in data
    assert len(data["verdict_receipt_sha256"]) == 64  # sha256 hex


def test_write_gate_no_receipt(tmp_path: Path) -> None:
    """write_gate without a receipt path still works."""
    repo = tmp_path / "repo"
    repo.mkdir()

    path = write_gate(str(repo), "node-02", None)
    assert path is not None
    data = read_gate(str(repo), "node-02")
    assert data is not None
    assert data["node_id"] == "node-02"
    assert "verdict_receipt_sha256" not in data


def test_read_gate_absent(tmp_path: Path) -> None:
    """read_gate returns None when no token exists."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert read_gate(str(repo), "node-99") is None


def test_read_gate_rejects_empty_object(tmp_path: Path) -> None:
    """An arbitrary {} must NOT satisfy a dependency (schema validation)."""
    repo = tmp_path / "repo"
    gdir = repo / ".gddp" / "gates"
    gdir.mkdir(parents=True)
    (gdir / "node-01.token").write_text("{}")
    assert read_gate(str(repo), "node-01") is None
    assert gate_satisfied(str(repo), ["node-01"]) is False


def test_read_gate_rejects_wrong_node_id(tmp_path: Path) -> None:
    """A token with a mismatched node_id does not satisfy."""
    repo = tmp_path / "repo"
    gdir = repo / ".gddp" / "gates"
    gdir.mkdir(parents=True)
    (gdir / "node-01.token").write_text(
        json.dumps({"node_id": "node-99"})
    )
    assert read_gate(str(repo), "node-01") is None


def test_gate_satisfied_empty_deps(tmp_path: Path) -> None:
    """Empty dependency list is trivially satisfied (root nodes)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert gate_satisfied(str(repo), []) is True


def test_gate_satisfied_all_present(tmp_path: Path) -> None:
    """gate_satisfied is True when all deps have valid tokens."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_gate(str(repo), "node-a", None)
    write_gate(str(repo), "node-b", None)
    assert gate_satisfied(str(repo), ["node-a", "node-b"]) is True


def test_gate_satisfied_partial(tmp_path: Path) -> None:
    """gate_satisfied is False when any dep lacks a token."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_gate(str(repo), "node-a", None)
    assert gate_satisfied(str(repo), ["node-a", "node-b"]) is False


def test_write_gate_concurrent_no_corrupt(tmp_path: Path) -> None:
    """Concurrent writers for the SAME node never produce invalid final JSON.

    Each write uses a unique tempfile (tempfile.mkstemp), so two threads
    racing on write_gate('node-01') must not share an inode or corrupt the
    final .token. We verify by reading the result after all writers finish.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    errors = []

    def writer():
        try:
            for _ in range(20):
                result = write_gate(str(repo), "node-01", None)
                if result is None:
                    errors.append("write_gate returned None")
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent errors: {errors[:3]}"
    # Final token must be valid JSON with the right node_id
    data = read_gate(str(repo), "node-01")
    assert data is not None
    assert data["node_id"] == "node-01"
    # No leftover .tmp files
    gdir = repo / ".gddp" / "gates"
    tmp_files = [f for f in gdir.iterdir() if f.suffix == ".tmp"]
    assert not tmp_files, f"leftover tempfiles: {[f.name for f in tmp_files]}"


def test_write_gate_no_tempfile_remains(tmp_path: Path) -> None:
    """No .tmp file remains after a single successful write."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_gate(str(repo), "node-01", None)
    gdir = repo / ".gddp" / "gates"
    files = list(gdir.iterdir())
    assert len(files) == 1
    assert files[0].name == "node-01.token"


def test_write_gate_idempotent_overwrite(tmp_path: Path) -> None:
    """Second write overwrites the first cleanly."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_gate(str(repo), "node-01", None)
    first = read_gate(str(repo), "node-01")
    assert first is not None
    write_gate(str(repo), "node-01", None)
    second = read_gate(str(repo), "node-01")
    assert second is not None
    assert second["node_id"] == "node-01"
    # Only one file on disk.
    gdir = repo / ".gddp" / "gates"
    assert len(list(gdir.iterdir())) == 1


def test_revoke_gate_removes_token(tmp_path: Path) -> None:
    """revoke_gate deletes a token and returns True; absent returns False."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_gate(str(repo), "node-01", None)
    assert gate_satisfied(str(repo), ["node-01"]) is True

    revoked = revoke_gate(str(repo), "node-01")
    assert revoked is True
    assert gate_satisfied(str(repo), ["node-01"]) is False

    # Second revoke on absent token returns False (no-op)
    revoked_again = revoke_gate(str(repo), "node-01")
    assert revoked_again is False


def test_hook_fires_on_pass_and_writes_gate(tmp_path: Path) -> None:
    """On a pass verdict, the gate token IS written to the repo checkout.

    Exercises the full pass path through maybe_mark_provisional: verdict
    eligibility → node status rewrite → gate token write. The fail-path
    only test (below) covers the negative case.
    """
    from unittest.mock import patch, MagicMock
    from runtime.heartbeat.provisional_gate import maybe_mark_provisional

    config = tmp_path / "config"
    proj_dir = config / "graphs" / "test-proj" / "nodes"
    proj_dir.mkdir(parents=True)
    node_yaml = (
        "node_id: node-pass\n"
        "status: ready\n"
        "type: capability\n"
    )
    (proj_dir / "node-pass.yaml").write_text(node_yaml)
    project_yaml = (
        "project_id: test-proj\n"
        "nodes:\n"
        "  - id: node-pass\n"
        "    status: ready\n"
        "    type: capability\n"
    )
    (config / "graphs" / "test-proj" / "project.yaml").write_text(project_yaml)

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (tmp_path / "receipt.json").write_text('{"verdict": "pass"}')

    # Mock the surgical rewriters (real node_cli is in gddp-config, not
    # available in a runtime test fixture)
    mock_cli = MagicMock()
    mock_cli.replace_node_status.return_value = (
        node_yaml.replace("status: ready", "status: provisional"),
        "ready",
    )
    mock_cli.replace_project_index_status.return_value = (
        project_yaml.replace("status: ready", "status: provisional"),
        "ready",
    )

    with patch(
        "runtime.heartbeat.provisional_gate.resolve_project_repo_checkout",
        return_value=repo,
    ), patch(
        "runtime.heartbeat.provisional_gate._load_node_cli",
        return_value=mock_cli,
    ):
        result = maybe_mark_provisional(
            project_id="test-proj",
            node_id="node-pass",
            verification={
                "verdict": "pass",
                "integrity": {
                    "intent_preserved": True,
                    "graph_integrity_preserved": True,
                },
                "receipt_path": str(tmp_path / "receipt.json"),
            },
            evidence_ref="res_test",
            config_path=str(config),
        )

    assert result is True
    gate = read_gate(str(repo), "node-pass")
    assert gate is not None
    assert gate["node_id"] == "node-pass"
    assert len(gate.get("verdict_receipt_sha256", "")) == 64


def test_hook_does_not_write_gate_on_fail(tmp_path: Path) -> None:
    """A fail verdict never writes a gate token."""
    from unittest.mock import patch
    from runtime.heartbeat.provisional_gate import maybe_mark_provisional

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".gddp" / "gates").mkdir(parents=True, exist_ok=True)

    with patch(
        "runtime.heartbeat.provisional_gate.resolve_project_repo_checkout",
        return_value=repo,
    ):
        result = maybe_mark_provisional(
            project_id="test-proj",
            node_id="node-fail",
            verification={"verdict": "fail"},
            evidence_ref="res_fail",
            config_path=str(tmp_path / "config"),
        )

    assert result is False
    assert read_gate(str(repo), "node-fail") is None


def test_frontier_self_heal_rewrites_missing_gate(tmp_path: Path) -> None:
    """advance_frontier's _ensure_dependency_gates rewrites a missing token
    when a dependent is about to dispatch."""
    import sqlite3
    from runtime.heartbeat.frontier import _ensure_dependency_gates

    config = tmp_path / "config"
    config.mkdir()
    # Minimal project structure so resolve_project_repo_checkout can find it
    proj_dir = config / "graphs" / "heal-proj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        "project_id: heal-proj\n"
        "repo: /fake/repo\n"
        "nodes: []\n"
    )

    # Mock the repo checkout to a real temp dir with .git
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    # A stored receipt for the dep node
    verif_dir = config / "verification" / "heal-proj" / "node-a"
    verif_dir.mkdir(parents=True)
    receipt_file = verif_dir / "job1-attempt0.json"
    receipt_file.write_text('{"verdict": "pass"}')

    from unittest.mock import patch
    with patch(
        "runtime.heartbeat.frontier.resolve_project_repo_checkout",
        return_value=repo,
    ):
        _ensure_dependency_gates(config, "heal-proj", ["node-a"])

    gate = read_gate(str(repo), "node-a")
    assert gate is not None
    assert gate["node_id"] == "node-a"
    assert len(gate.get("verdict_receipt_sha256", "")) == 64


def test_frontier_self_heal_skips_existing_gate(tmp_path: Path) -> None:
    """If the gate already exists, _ensure_dependency_gates is a no-op."""
    config = tmp_path / "config"
    config.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    write_gate(str(repo), "node-a", None)

    from unittest.mock import patch
    from runtime.heartbeat.frontier import _ensure_dependency_gates

    with patch(
        "runtime.heartbeat.frontier.resolve_project_repo_checkout",
        return_value=repo,
    ):
        _ensure_dependency_gates(config, "heal-proj", ["node-a"])

    # Token is unchanged
    gate = read_gate(str(repo), "node-a")
    assert gate is not None
    assert "verdict_receipt_sha256" not in gate  # original write had no receipt
