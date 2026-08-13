"""Build a provider-locked environment for evaluator Pi subprocesses."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path


APPROVED_PI_PROVIDERS = {"deepseek", "openai-codex"}

_WRAPPER_BASENAMES = ("pi", "pi-lite", "pi-full", "pi-studio")

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
    else:
        auth_file = _chatgpt_auth_file(ambient)
        _require_chatgpt_oauth(auth_file)
        agent_dir.mkdir(parents=True, exist_ok=True)
        # Pi may refresh OAuth during a run. A symlink keeps refreshes in the
        # operator-owned auth store while withholding models/settings/extensions.
        (agent_dir / "auth.json").symlink_to(auth_file)

    # Resolve against ambient HOME/PATH before the sandbox remap. pi-lite's
    # skip list is derived from those vars, so a remapped HOME makes the
    # managed wrapper look like the real binary and exec itself forever.
    env["PI_REAL_BIN"] = str(resolve_real_pi_bin(ambient))
    return env


def resolve_real_pi_bin(source_env: Mapping[str, str] | None = None) -> Path:
    """Return the non-wrapper Pi executable from ambient PATH or ``PI_REAL_BIN``."""
    ambient = dict(os.environ if source_env is None else source_env)
    configured = str(ambient.get("PI_REAL_BIN", "")).strip()
    if configured:
        path = Path(configured).expanduser()
        if not _is_executable(path):
            raise RuntimeError(f"PI_REAL_BIN is not executable: {configured}")
        return path

    home = Path(ambient.get("HOME", str(Path.home()))).expanduser()
    agent_dir = Path(
        ambient.get("PI_CODING_AGENT_DIR", str(home / ".pi" / "agent"))
    ).expanduser()
    skip = _wrapper_paths(home, agent_dir)
    harness_bin = home / ".pi" / "harness" / "bin"

    for directory in str(ambient.get("PATH", os.defpath)).split(os.pathsep):
        if not directory:
            continue
        candidate = Path(directory).expanduser() / "pi"
        if not _is_executable(candidate):
            continue
        if _is_managed_wrapper(candidate, skip, harness_bin):
            continue
        return candidate

    raise RuntimeError(
        "no real Pi binary on PATH; set PI_REAL_BIN to the non-wrapper executable"
    )


def evaluator_pi_argv0(requested: str, env: Mapping[str, str]) -> str:
    """Choose argv[0] so a managed wrapper never starts the evaluator Pi."""
    if requested in _WRAPPER_BASENAMES:
        pinned = str(env.get("PI_REAL_BIN", "")).strip()
        if not pinned:
            raise RuntimeError("evaluator environment missing PI_REAL_BIN")
        return pinned
    return requested


def _is_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def _wrapper_paths(home: Path, agent_dir: Path) -> set[Path]:
    names = ("pi", "pi-lite", "pi-full", "pi-studio")
    raw = [agent_dir / "bin" / "pi", home / ".pi" / "agent" / "bin" / "pi"]
    raw.extend(home / ".pi" / "harness" / "bin" / name for name in names)
    return {_normalized(path) for path in raw}


def _is_managed_wrapper(candidate: Path, skip: set[Path], harness_bin: Path) -> bool:
    normalized = _normalized(candidate)
    if normalized in skip:
        return True
    harness = _normalized(harness_bin)
    try:
        normalized.relative_to(harness)
    except ValueError:
        return False
    return True


def _normalized(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


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
