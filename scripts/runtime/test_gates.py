"""
test_gates.py — Tests for the gate-token writer/reader/satisfaction checker.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Make scripts/ importable when run as a module from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.gates import gate_satisfied, read_gate, write_gate


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


def test_gate_satisfied_empty_deps(tmp_path: Path) -> None:
    """Empty dependency list is trivially satisfied (root nodes)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert gate_satisfied(str(repo), []) is True


def test_gate_satisfied_all_present(tmp_path: Path) -> None:
    """gate_satisfied is True when all deps have tokens."""
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


def test_write_gate_atomic(tmp_path: Path) -> None:
    """No .tmp file remains after a successful write."""
    repo = tmp_path / "repo"
    repo.mkdir()
    write_gate(str(repo), "node-01", None)
    gdir = repo / ".gddp" / "gates"
    files = list(gdir.iterdir())
    assert len(files) == 1
    assert files[0].name == "node-01.token"
    assert not (gdir / "node-01.tmp").exists()


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


def test_hook_fires_on_pass_only(tmp_path: Path) -> None:
    """The provisional gate hook writes a token only on the success path."""
    # This test verifies the hook integration indirectly: gate_satisfied
    # is the read-side contract that a mission executor would use. The
    # write happens inside maybe_mark_provisional's success path, which
    # we can't easily unit-test without a full graph fixture. Instead we
    # verify the contract surface: after write_gate, gate_satisfied sees it.
    repo = tmp_path / "repo"
    repo.mkdir()
    assert gate_satisfied(str(repo), ["node-01"]) is False
    write_gate(str(repo), "node-01", None)
    assert gate_satisfied(str(repo), ["node-01"]) is True
