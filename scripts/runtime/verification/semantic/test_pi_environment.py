from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.runtime.verification.semantic.pi_environment import (
    build_pi_environment,
    evaluator_pi_argv0,
    has_chatgpt_oauth,
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


def test_chatgpt_environment_exposes_oauth_without_api_keys(tmp_path: Path) -> None:
    auth_file = tmp_path / "operator-auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "openai-codex": {"type": "oauth", "access": "test-access"},
                "openrouter": {"type": "api_key", "key": "wrong-key"},
            }
        ),
        encoding="utf-8",
    )
    sandbox = tmp_path / "sandbox"
    real_pi = _write_exec(tmp_path / "real" / "pi")
    env = build_pi_environment(
        "openai-codex",
        sandbox,
        source_env={
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin",
            "GDDP_PI_AUTH_FILE": str(auth_file),
            "DEEPSEEK_API_KEY": "wrong-deepseek-key",
            "OPENROUTER_API_KEY": "wrong-openrouter-key",
            "PI_REAL_BIN": str(real_pi),
        },
    )

    linked_auth = Path(env["PI_CODING_AGENT_DIR"]) / "auth.json"
    assert linked_auth.is_symlink()
    assert linked_auth.resolve() == auth_file.resolve()
    assert "DEEPSEEK_API_KEY" not in env
    assert "OPENROUTER_API_KEY" not in env
    assert has_chatgpt_oauth(
        {"HOME": str(tmp_path / "home"), "GDDP_PI_AUTH_FILE": str(auth_file)}
    )


def test_missing_approved_auth_fails_before_pi_starts(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        build_pi_environment("deepseek", tmp_path / "deepseek", source_env={})

    with pytest.raises(RuntimeError, match="openai-codex OAuth"):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text("{}", encoding="utf-8")
        build_pi_environment(
            "openai-codex",
            tmp_path / "chatgpt",
            source_env={"GDDP_PI_AUTH_FILE": str(auth_file)},
        )


def test_unapproved_provider_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="approved providers"):
        build_pi_environment("openrouter", tmp_path / "sandbox", source_env={})


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
