import plistlib
import subprocess
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent
COMMON_SH = KIT_ROOT / "bin" / "common.sh"
HEARTBEAT_TEMPLATE = KIT_ROOT / "launchd" / "com.gddp.rig1.heartbeat.plist"


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


def _render_heartbeat_plist(env: dict[str, str]) -> dict:
    return _render_plist(HEARTBEAT_TEMPLATE, env)


def _base_render_env(**overrides: str) -> dict[str, str]:
    env = {
        "RIG1_HEARTBEAT_ENV": "/dev/null",
        "GDDP_RUNTIME_ROOT": "/tmp/gddp-runtime",
        "GDDP_CONFIG_PATH": "/tmp/gddp-config",
        "GDDP_REPOS_ROOT": "/tmp/repos",
        "GDDP_PYTHON": "/usr/bin/python3",
        "HOME": "/Users/sab-air",
        "USER": "saboor",
        # override default so tests are deterministic without Keychain
        "GDDP_JULES_KEY_CMD": "security find-generic-password -w -s jules-api-key -a saboor",
    }
    env.update(overrides)
    return env


def test_render_heartbeat_invokes_real_runner_module():
    plist = _render_heartbeat_plist(_base_render_env())
    args = plist["ProgramArguments"]

    assert plist["Label"] == "com.gddp.rig1.heartbeat"
    assert args[0] == "/usr/bin/python3"
    assert args[1:3] == ["-m", "scripts.runtime.heartbeat.runner"]
    assert args[3:6] == ["--project", "gddp-runtime", "--repo"]
    assert args[6] == "skchaudr/gddp-runtime"
    assert args[7:9] == ["--config-path", "/tmp/gddp-config"]
    assert plist["StartInterval"] == 300
    assert plist["RunAtLoad"] is False
    assert plist["WorkingDirectory"] == "/tmp/gddp-runtime"


def test_render_heartbeat_log_paths_are_rig1_specific():
    plist = _render_heartbeat_plist(_base_render_env())

    assert plist["StandardOutPath"] == "/Users/sab-air/Library/Logs/gddp-rig1-heartbeat.log"
    assert plist["StandardErrorPath"] == "/Users/sab-air/Library/Logs/gddp-rig1-heartbeat.err.log"
    assert "gddp-heartbeat.log" not in plist["StandardOutPath"]


def test_render_heartbeat_default_jules_key_cmd():
    # Drop override so common.sh default expands USER
    env = _base_render_env()
    del env["GDDP_JULES_KEY_CMD"]
    plist = _render_heartbeat_plist(env)

    assert (
        plist["EnvironmentVariables"]["GDDP_JULES_KEY_CMD"]
        == "security find-generic-password -w -s jules-api-key -a saboor"
    )
    assert "$USER" not in plist["EnvironmentVariables"]["GDDP_JULES_KEY_CMD"]


def test_render_heartbeat_substitutes_jules_key_cmd_with_special_chars():
    jules = 'security find-generic-password -w -s "jules & key" -a saboor'
    plist = _render_heartbeat_plist(_base_render_env(GDDP_JULES_KEY_CMD=jules))

    assert plist["EnvironmentVariables"]["GDDP_JULES_KEY_CMD"] == jules


def test_render_heartbeat_substitutes_runtime_paths():
    plist = _render_heartbeat_plist(
        _base_render_env(
            GDDP_RUNTIME_ROOT="/opt/gddp/runtime",
            GDDP_CONFIG_PATH="/opt/gddp/config",
            GDDP_REPOS_ROOT="/opt/gddp/repos",
            GDDP_PYTHON="/opt/gddp/runtime/.venv/bin/python",
            HOME="/Users/tester",
        )
    )
    env = plist["EnvironmentVariables"]
    args = plist["ProgramArguments"]

    assert args[0] == "/opt/gddp/runtime/.venv/bin/python"
    assert env["GDDP_RUNTIME_ROOT"] == "/opt/gddp/runtime"
    assert env["GDDP_CONFIG_PATH"] == "/opt/gddp/config"
    assert env["GDDP_REPOS_ROOT"] == "/opt/gddp/repos"
    assert env["GDDP_REPO_ROOT"] == "/opt/gddp/repos"
    assert env["HOME"] == "/Users/tester"
    assert "/Users/tester/.local/bin" in env["PATH"]
    assert env["PYTHONPATH"] == "/opt/gddp/runtime"


def test_label_does_not_collide_with_mini():
    plist = _render_heartbeat_plist(_base_render_env())
    assert plist["Label"] != "com.gddp.heartbeat"
    assert plist["Label"] == "com.gddp.rig1.heartbeat"
