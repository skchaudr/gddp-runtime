from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.runtime.verification.semantic.pi_environment import (
    build_pi_environment,
    evaluator_pi_argv0,
    resolve_real_pi_bin,
)


def _write_exec(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_deepseek_environment_removes_competing_routes(tmp_path: Path) -> None:
    inherited_agent_dir = tmp_path / "inherited-agent"
    real_pi = _write_exec(tmp_path / "real" / "pi")
    env = build_pi_environment(
        "deepseek",
        tmp_path / "sandbox",
        source_env={
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "OPENAI_API_KEY": "wrong-openai-key",
            "OPENROUTER_API_KEY": "wrong-openrouter-key",
            "OPENAI_BASE_URL": "https://wrong.example",
            "PI_CODING_AGENT_DIR": str(inherited_agent_dir),
            "PI_REAL_BIN": str(real_pi),
        },
    )

    assert env["DEEPSEEK_API_KEY"] == "deepseek-key"
    assert env["PATH"] == "/usr/bin"
    assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "sandbox" / "agent")
    assert env["PI_REAL_BIN"] == str(real_pi)
    assert "OPENAI_API_KEY" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env


def test_chatgpt_environment_keeps_pi_login_and_drops_api_keys(tmp_path: Path) -> None:
    real_pi = _write_exec(tmp_path / "real" / "pi")
    home = tmp_path / "home"
    env = build_pi_environment(
        "openai-codex",
        tmp_path / "sandbox",
        source_env={
            "HOME": str(home),
            "PATH": "/usr/bin",
            "DEEPSEEK_API_KEY": "wrong-deepseek-key",
            "OPENROUTER_API_KEY": "wrong-openrouter-key",
            "PI_REAL_BIN": str(real_pi),
        },
    )

    assert env["HOME"] == str(home)
    assert "PI_CODING_AGENT_DIR" not in env
    assert "DEEPSEEK_API_KEY" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert env["PI_REAL_BIN"] == str(real_pi)


def test_missing_approved_auth_fails_before_pi_starts(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        build_pi_environment("deepseek", tmp_path / "deepseek", source_env={})


def test_openrouter_environment_removes_competing_routes(tmp_path: Path) -> None:
    inherited_agent_dir = tmp_path / "inherited-agent"
    real_pi = _write_exec(tmp_path / "real" / "pi")
    env = build_pi_environment(
        "openrouter",
        tmp_path / "sandbox",
        source_env={
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin",
            "OPENROUTER_API_KEY": "openrouter-key",
            "DEEPSEEK_API_KEY": "wrong-deepseek-key",
            "OPENAI_API_KEY": "wrong-openai-key",
            "PI_CODING_AGENT_DIR": str(inherited_agent_dir),
            "PI_REAL_BIN": str(real_pi),
            "PI_MODEL": "leaked-model",
            "PI_PROVIDER": "leaked-provider",
        },
    )

    assert env["HOME"] == str(tmp_path / "home")
    assert env["PATH"] == "/usr/bin"
    assert env["PI_CODING_AGENT_DIR"] == str(inherited_agent_dir)
    assert env["PI_REAL_BIN"] == str(real_pi)
    assert "OPENROUTER_API_KEY" not in env
    assert "DEEPSEEK_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "PI_MODEL" not in env
    assert "PI_PROVIDER" not in env


def test_clinepass_environment_keeps_pi_home(tmp_path: Path) -> None:
    real_pi = _write_exec(tmp_path / "real" / "pi")
    home = tmp_path / "home"
    env = build_pi_environment(
        "clinepass",
        tmp_path / "sandbox",
        source_env={
            "HOME": str(home),
            "PATH": "/usr/bin",
            "OPENROUTER_API_KEY": "ambient-key",
            "PI_REAL_BIN": str(real_pi),
        },
    )

    assert env["HOME"] == str(home)
    assert env["HOME"] != str(tmp_path / "sandbox")
    assert "OPENROUTER_API_KEY" not in env
    assert env["PI_REAL_BIN"] == str(real_pi)


def test_unapproved_provider_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="approved providers"):
        build_pi_environment("anthropic", tmp_path / "sandbox", source_env={})


def test_symlinked_agent_wrapper_is_skipped(tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = _write_exec(home / ".pi" / "harness" / "bin" / "pi-profile")
    lite = home / ".pi" / "harness" / "bin" / "pi-lite"
    lite.symlink_to(profile)
    agent_pi = home / ".pi" / "agent" / "bin" / "pi"
    agent_pi.parent.mkdir(parents=True, exist_ok=True)
    agent_pi.symlink_to(lite)
    real_pi = _write_exec(tmp_path / "opt" / "pi")

    env = build_pi_environment(
        "deepseek",
        tmp_path / "sandbox",
        source_env={
            "HOME": str(home),
            "PATH": os_path(agent_pi.parent, lite.parent, real_pi.parent),
            "DEEPSEEK_API_KEY": "deepseek-key",
            "PI_CODING_AGENT_DIR": str(home / ".pi" / "agent"),
        },
    )

    assert Path(env["PI_REAL_BIN"]) == real_pi


def test_wrapper_first_path_pins_real_pi(tmp_path: Path) -> None:
    home = tmp_path / "home"
    wrapper = _write_exec(home / ".pi" / "agent" / "bin" / "pi")
    harness = _write_exec(home / ".pi" / "harness" / "bin" / "pi-lite")
    real_pi = _write_exec(tmp_path / "opt" / "pi")
    env = build_pi_environment(
        "deepseek",
        tmp_path / "sandbox",
        source_env={
            "HOME": str(home),
            "PATH": os_path(wrapper.parent, harness.parent, real_pi.parent),
            "DEEPSEEK_API_KEY": "deepseek-key",
            "PI_CODING_AGENT_DIR": str(home / ".pi" / "agent"),
        },
    )

    assert Path(env["PI_REAL_BIN"]) == real_pi
    assert Path(env["HOME"]) == tmp_path / "sandbox"
    assert evaluator_pi_argv0("pi", env) == str(real_pi)


def test_configured_pi_real_bin_is_honored(tmp_path: Path) -> None:
    pinned = _write_exec(tmp_path / "pinned" / "pi")
    assert resolve_real_pi_bin({"PI_REAL_BIN": str(pinned), "PATH": "/usr/bin"}) == pinned


def test_missing_real_pi_fails_before_spawn(tmp_path: Path) -> None:
    home = tmp_path / "home"
    wrapper = _write_exec(home / ".pi" / "agent" / "bin" / "pi")
    with pytest.raises(RuntimeError, match="no real Pi binary"):
        resolve_real_pi_bin(
            {
                "HOME": str(home),
                "PATH": str(wrapper.parent),
                "PI_CODING_AGENT_DIR": str(home / ".pi" / "agent"),
            }
        )


def test_invalid_pi_real_bin_fails_before_spawn(tmp_path: Path) -> None:
    missing = tmp_path / "missing-pi"
    with pytest.raises(RuntimeError, match="PI_REAL_BIN is not executable"):
        resolve_real_pi_bin({"PI_REAL_BIN": str(missing)})


def os_path(*dirs: Path) -> str:
    return os.pathsep.join(str(directory) for directory in dirs)
