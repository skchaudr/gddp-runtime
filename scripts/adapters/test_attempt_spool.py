"""Canonical local attempt spool defaults for cursor/pi/local adapters."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.cursor_cli_adapter import CursorCliAdapter
from adapters.local_subprocess_adapter import LocalSubprocessAdapter
from adapters.pi_rpc_adapter import PiRpcAdapter
from runtime.local_attempt import resolve_attempt_spool_root


def test_cursor_and_local_defaults_converge(monkeypatch, tmp_path):
    monkeypatch.setenv("GDDP_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.delenv("GDDP_ATTEMPT_SPOOL_DIR", raising=False)
    monkeypatch.delenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", raising=False)
    monkeypatch.delenv("GDDP_CURSOR_CLI_SPOOL_DIR", raising=False)
    monkeypatch.delenv("GDDP_PI_RPC_SPOOL_DIR", raising=False)
    expected = resolve_attempt_spool_root(runtime_root=tmp_path)

    cursor = CursorCliAdapter(repo="owner/repo")
    local = LocalSubprocessAdapter(
        repo="owner/repo", argv=["/bin/true"]
    )

    assert cursor.spool_root == expected
    assert local.spool_root == expected
    assert expected == tmp_path / "jobs" / "local-subprocess-spool"


def test_canonical_env_wins_over_family_overlay(monkeypatch, tmp_path):
    canonical = tmp_path / "attempts"
    monkeypatch.setenv("GDDP_ATTEMPT_SPOOL_DIR", str(canonical))
    monkeypatch.setenv("GDDP_CURSOR_CLI_SPOOL_DIR", str(tmp_path / "cursor"))
    monkeypatch.setenv("GDDP_LOCAL_SUBPROCESS_SPOOL_DIR", str(tmp_path / "shared"))
    monkeypatch.setenv("GDDP_PI_RPC_SPOOL_DIR", str(tmp_path / "pi"))
    monkeypatch.setenv("GDDP_PI_RPC_MODEL", "m")

    cursor = CursorCliAdapter(repo="owner/repo")
    local = LocalSubprocessAdapter(repo="owner/repo", argv=["/bin/true"])
    pi = PiRpcAdapter(repo="owner/repo", model="m")

    assert cursor.spool_root == canonical.resolve()
    assert local.spool_root == canonical.resolve()
    assert pi.spool_root == canonical.resolve()


def test_explicit_spool_root_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GDDP_ATTEMPT_SPOOL_DIR", str(tmp_path / "canonical"))
    explicit = tmp_path / "override"

    cursor = CursorCliAdapter(repo="owner/repo", spool_root=explicit)
    local = LocalSubprocessAdapter(
        repo="owner/repo", argv=["/bin/true"], spool_root=explicit
    )

    assert cursor.spool_root == explicit.resolve()
    assert local.spool_root == explicit.resolve()
