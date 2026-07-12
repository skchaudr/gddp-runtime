import plistlib
import subprocess
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent
COMMON_SH = KIT_ROOT / "bin" / "common.sh"
INTAKE_TEMPLATE = KIT_ROOT / "launchd" / "com.gddp.intake.plist"
HEARTBEAT_TEMPLATE = KIT_ROOT / "launchd" / "com.gddp.heartbeat.plist"


def _render_plist(template: Path, env: dict[str, str]) -> dict:
    out = KIT_ROOT / ".pytest-render.plist"
    try:
        cmd = f"""
set -euo pipefail
source "{COMMON_SH}"
render_plist "{template}" "{out}"
"""
        subprocess.run(
            ["bash", "-c", cmd],
            check=True,
            env={**subprocess.os.environ, **env},
            capture_output=True,
            text=True,
        )
        with out.open("rb") as fh:
            return plistlib.load(fh)
    finally:
        out.unlink(missing_ok=True)


def _render_intake_plist(env: dict[str, str]) -> dict:
    return _render_plist(INTAKE_TEMPLATE, env)["EnvironmentVariables"]


def _render_heartbeat_plist(env: dict[str, str]) -> dict:
    return _render_plist(HEARTBEAT_TEMPLATE, env)


def _base_render_env(**overrides: str) -> dict[str, str]:
    env = {
        "MINI_HEARTBEAT_ENV": "/dev/null",
        "GDDP_RUNTIME_ROOT": "/tmp/gddp-runtime",
        "GDDP_CONFIG_PATH": "/tmp/gddp-config",
        "GDDP_REPOS_ROOT": "/tmp/repos",
        "GDDP_PYTHON": "/usr/bin/python3",
        "HOME": "/Users/sab-mini",
    }
    env.update(overrides)
    return env


def test_render_plist_default_secret_cmds():
    env = _render_intake_plist(_base_render_env())

    assert env["GDDP_DEEPSEEK_KEY_CMD"] == "pass show api/deepseek"
    assert env["GDDP_WEBHOOK_SECRET_CMD"] == "pass show gddp/webhook-secret"


def test_render_plist_substitutes_runtime_paths():
    env = _render_intake_plist(
        _base_render_env(
            GDDP_RUNTIME_ROOT="/opt/gddp/runtime",
            GDDP_CONFIG_PATH="/opt/gddp/config",
            GDDP_REPOS_ROOT="/opt/gddp/repos",
            HOME="/Users/tester",
        )
    )

    assert env["GDDP_RUNTIME_ROOT"] == "/opt/gddp/runtime"
    assert env["GDDP_CONFIG_PATH"] == "/opt/gddp/config"
    assert env["GDDP_REPOS_ROOT"] == "/opt/gddp/repos"
    assert env["HOME"] == "/Users/tester"
    assert "/Users/tester/.local/bin" in env["PATH"]


def test_render_heartbeat_plist_default_project_args():
    plist = _render_heartbeat_plist(_base_render_env())
    args = plist["ProgramArguments"]

    assert args[0] == "/usr/bin/python3"
    assert args[1:3] == ["-m", "scripts.runtime.heartbeat.runner"]
    assert args[3:6] == ["--project", "gddp-runtime", "--repo"]
    assert args[6] == "skchaudr/gddp-runtime"
    assert args[7:9] == ["--config-path", "/tmp/gddp-config"]
    assert plist["EnvironmentVariables"]["GDDP_REPO_ROOT"] == "/tmp/repos"
    assert plist["StartInterval"] == 300


def test_webhook_secret_cmd_with_quotes_survives_plist_render():
    webhook = 'ssh -o BatchMode=yes sab-ssd@pi-big "pass show gddp/webhook-secret"'
    deepseek = 'ssh -o BatchMode=yes sab-ssd@pi-big "pass show api/deepseek"'

    env = _render_intake_plist(
        _base_render_env(
            GDDP_WEBHOOK_SECRET_CMD=webhook,
            GDDP_DEEPSEEK_KEY_CMD=deepseek,
        )
    )

    assert env["GDDP_WEBHOOK_SECRET_CMD"] == webhook
    assert env["GDDP_DEEPSEEK_KEY_CMD"] == deepseek
    assert '"quot;' not in env["GDDP_WEBHOOK_SECRET_CMD"]


def test_xml_special_chars_survive_plist_render():
    webhook = 'pass show gddp/webhook-secret & echo "ok" <done>'

    env = _render_intake_plist(
        _base_render_env(
            GDDP_WEBHOOK_SECRET_CMD=webhook,
            GDDP_DEEPSEEK_KEY_CMD="pass show api/deepseek",
        )
    )

    assert env["GDDP_WEBHOOK_SECRET_CMD"] == webhook