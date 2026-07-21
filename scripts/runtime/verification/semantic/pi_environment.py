"""Build a provider-locked environment for evaluator Pi subprocesses."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path


APPROVED_PI_PROVIDERS = {"deepseek", "openai-codex"}

_ROUTING_ENV_NAMES = {
    "ANTHROPIC_OAUTH_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_PROFILE",
    "AWS_SECRET_ACCESS_KEY",
    "AZURE_OPENAI_DEPLOYMENT_NAME_MAP",
    "AZURE_OPENAI_RESOURCE_NAME",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_GATEWAY_ID",
    "PI_CODING_AGENT_DIR",
}


def build_pi_environment(
    provider: str,
    sandbox_home: Path,
    *,
    source_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Expose exactly one approved auth route to Pi.

    DeepSeek receives only ``DEEPSEEK_API_KEY``. ChatGPT uses Pi's
    ``openai-codex`` OAuth credential through an auth-only agent directory.
    Competing API keys and inherited Pi config paths are removed so provider
    selection cannot silently fall through to ambient configuration.
    """
    if provider not in APPROVED_PI_PROVIDERS:
        raise RuntimeError(
            f"unsupported evaluator Pi provider {provider!r}; "
            "approved providers are deepseek and openai-codex"
        )

    ambient = dict(os.environ if source_env is None else source_env)
    env = dict(ambient)
    for name in list(env):
        if (
            name in _ROUTING_ENV_NAMES
            or name.endswith("_API_KEY")
            or name.endswith("_BASE_URL")
            or name.endswith("_OAUTH_TOKEN")
            or name.endswith("_TOKEN_FILE")
        ):
            env.pop(name, None)

    agent_dir = sandbox_home / "agent"
    env["HOME"] = str(sandbox_home)
    # HOME alone is insufficient when a parent process exports this override.
    env["PI_CODING_AGENT_DIR"] = str(agent_dir)

    if provider == "deepseek":
        api_key = ambient.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required for evaluator Pi provider deepseek")
        env["DEEPSEEK_API_KEY"] = api_key
        return env

    auth_file = _chatgpt_auth_file(ambient)
    _require_chatgpt_oauth(auth_file)
    agent_dir.mkdir(parents=True, exist_ok=True)
    # Pi may refresh OAuth during a run. A symlink keeps refreshes in the
    # operator-owned auth store while withholding models/settings/extensions.
    (agent_dir / "auth.json").symlink_to(auth_file)
    return env


def has_chatgpt_oauth(source_env: Mapping[str, str] | None = None) -> bool:
    ambient = dict(os.environ if source_env is None else source_env)
    try:
        _require_chatgpt_oauth(_chatgpt_auth_file(ambient))
    except RuntimeError:
        return False
    return True


def _chatgpt_auth_file(ambient: Mapping[str, str]) -> Path:
    configured = ambient.get("GDDP_PI_AUTH_FILE")
    if configured:
        return Path(configured).expanduser().resolve()
    home = Path(ambient.get("HOME", str(Path.home()))).expanduser()
    return (home / ".pi" / "agent" / "auth.json").resolve()


def _require_chatgpt_oauth(auth_file: Path) -> None:
    try:
        credentials = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read evaluator Pi auth file: {auth_file}") from exc
    credential = credentials.get("openai-codex") if isinstance(credentials, dict) else None
    if not isinstance(credential, dict) or credential.get("type") != "oauth":
        raise RuntimeError(
            f"openai-codex OAuth is not configured in evaluator Pi auth file: {auth_file}"
        )
