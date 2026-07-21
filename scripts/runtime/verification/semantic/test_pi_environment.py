from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.runtime.verification.semantic.pi_environment import (
    build_pi_environment,
    has_chatgpt_oauth,
)


def test_deepseek_environment_removes_competing_routes(tmp_path: Path) -> None:
    inherited_agent_dir = tmp_path / "inherited-agent"
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
        },
    )

    assert env["DEEPSEEK_API_KEY"] == "deepseek-key"
    assert env["PATH"] == "/usr/bin"
    assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "sandbox" / "agent")
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
    env = build_pi_environment(
        "openai-codex",
        sandbox,
        source_env={
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin",
            "GDDP_PI_AUTH_FILE": str(auth_file),
            "DEEPSEEK_API_KEY": "wrong-deepseek-key",
            "OPENROUTER_API_KEY": "wrong-openrouter-key",
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
