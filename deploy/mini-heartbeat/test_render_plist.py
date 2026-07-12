import plistlib
import subprocess
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent
COMMON_SH = KIT_ROOT / "bin" / "common.sh"
INTAKE_TEMPLATE = KIT_ROOT / "launchd" / "com.gddp.intake.plist"


def _render_intake_plist(env: dict[str, str]) -> dict:
    out = KIT_ROOT / ".pytest-render.plist"
    try:
        cmd = f"""
set -euo pipefail
source "{COMMON_SH}"
render_plist "{INTAKE_TEMPLATE}" "{out}"
"""
        subprocess.run(
            ["bash", "-c", cmd],
            check=True,
            env={**subprocess.os.environ, **env},
            capture_output=True,
            text=True,
        )
        with out.open("rb") as fh:
            return plistlib.load(fh)["EnvironmentVariables"]
    finally:
        out.unlink(missing_ok=True)


def test_webhook_secret_cmd_with_quotes_survives_plist_render():
    webhook = 'ssh -o BatchMode=yes sab-ssd@pi-big "pass show gddp/webhook-secret"'
    deepseek = 'ssh -o BatchMode=yes sab-ssd@pi-big "pass show api/deepseek"'

    env = _render_intake_plist(
        {
            "MINI_HEARTBEAT_ENV": "/dev/null",
            "GDDP_WEBHOOK_SECRET_CMD": webhook,
            "GDDP_DEEPSEEK_KEY_CMD": deepseek,
            "GDDP_RUNTIME_ROOT": "/tmp/gddp-runtime",
            "GDDP_CONFIG_PATH": "/tmp/gddp-config",
            "GDDP_PYTHON": "/usr/bin/python3",
        }
    )

    assert env["GDDP_WEBHOOK_SECRET_CMD"] == webhook
    assert env["GDDP_DEEPSEEK_KEY_CMD"] == deepseek
    assert '"quot;' not in env["GDDP_WEBHOOK_SECRET_CMD"]


def test_xml_special_chars_survive_plist_render():
    webhook = 'pass show gddp/webhook-secret & echo "ok" <done>'

    env = _render_intake_plist(
        {
            "MINI_HEARTBEAT_ENV": "/dev/null",
            "GDDP_WEBHOOK_SECRET_CMD": webhook,
            "GDDP_DEEPSEEK_KEY_CMD": "pass show api/deepseek",
            "GDDP_RUNTIME_ROOT": "/tmp/gddp-runtime",
            "GDDP_CONFIG_PATH": "/tmp/gddp-config",
            "GDDP_PYTHON": "/usr/bin/python3",
        }
    )

    assert env["GDDP_WEBHOOK_SECRET_CMD"] == webhook