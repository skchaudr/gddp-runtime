import plistlib
import subprocess
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent
COMMON_SH = KIT_ROOT / "bin" / "common.sh"
INTAKE_TEMPLATE = KIT_ROOT / "launchd" / "com.gddp.intake.plist"
HEARTBEAT_TEMPLATE = KIT_ROOT / "launchd" / "com.gddp.heartbeat.plist"
PLIST_BOOL_SETTER = KIT_ROOT / "bin" / "set_plist_bools.py"


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
        # Pin secret cmds so host shell exports (e.g. Rig 1 Keychain) cannot leak.
        "GDDP_JULES_KEY_CMD": "pass show api/jules",
        "GDDP_DEEPSEEK_KEY_CMD": "pass show api/deepseek",
        "GDDP_WEBHOOK_SECRET_CMD": "pass show gddp/webhook-secret",
    }
    env.update(overrides)
    return env


def test_render_plist_default_secret_cmds():
    env = _render_intake_plist(_base_render_env())

    assert env["GDDP_DEEPSEEK_KEY_CMD"] == "pass show api/deepseek"
    assert env["GDDP_WEBHOOK_SECRET_CMD"] == "pass show gddp/webhook-secret"


def test_arm_helper_enables_intake_restart_flags(tmp_path):
    installed_plist = tmp_path / "com.gddp.intake.plist"
    installed_plist.write_bytes(INTAKE_TEMPLATE.read_bytes())

    subprocess.run(
        [
            sys.executable,
            str(PLIST_BOOL_SETTER),
            str(installed_plist),
            "RunAtLoad",
            "KeepAlive",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    with installed_plist.open("rb") as source:
        armed_plist = plistlib.load(source)
    assert armed_plist["RunAtLoad"] is True
    assert armed_plist["KeepAlive"] is True


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
    env = plist["EnvironmentVariables"]

    assert args[0] == "/usr/bin/python3"
    assert args[1:3] == ["-m", "scripts.runtime.heartbeat.runner"]
    assert args[3:] == ["--all-active", "--config-path", "/tmp/gddp-config"]
    assert env["GDDP_REPO_ROOT"] == "/tmp/repos"
    assert env["GDDP_JULES_KEY_CMD"] == "pass show api/jules"
    assert plist["StartInterval"] == 300


def test_render_heartbeat_plist_substitutes_jules_key_cmd():
    jules = '/opt/homebrew/bin/gpg --decrypt "/tmp/jules & api.gpg"'
    plist = _render_heartbeat_plist(
        _base_render_env(GDDP_JULES_KEY_CMD=jules)
    )

    assert plist["EnvironmentVariables"]["GDDP_JULES_KEY_CMD"] == jules


def test_render_heartbeat_plist_substitutes_local_executor_config():
    argv = '["/usr/bin/python3","/tmp/local_agent_executor.py","--","pi"]'
    spool = "/tmp/gddp spool"
    plist = _render_heartbeat_plist(
        _base_render_env(
            GDDP_LOCAL_SUBPROCESS_ARGV=argv,
            GDDP_LOCAL_SUBPROCESS_SPOOL_DIR=spool,
        )
    )
    env = plist["EnvironmentVariables"]

    assert env["GDDP_LOCAL_SUBPROCESS_ARGV"] == argv
    assert env["GDDP_LOCAL_SUBPROCESS_SPOOL_DIR"] == spool


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
