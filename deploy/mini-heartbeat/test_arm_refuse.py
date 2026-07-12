import subprocess
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent
ARM_SH = KIT_ROOT / "bin" / "arm.sh"


def _darwin_path_entry(tmp_path: Path) -> str:
    """Stub uname so arm.sh passes require_mac on Linux CI."""
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    uname = stub_bin / "uname"
    uname.write_text("#!/bin/sh\necho Darwin\n")
    uname.chmod(0o755)
    return str(stub_bin)


def test_arm_sh_exits_2_without_mini_heartbeat_arm(tmp_path):
    stub_path = _darwin_path_entry(tmp_path)
    env = {
        **subprocess.os.environ,
        "PATH": f"{stub_path}:{subprocess.os.environ.get('PATH', '')}",
        "MINI_HEARTBEAT_ENV": "/dev/null",
    }
    env.pop("MINI_HEARTBEAT_ARM", None)

    result = subprocess.run(
        ["bash", str(ARM_SH)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Refusing to arm" in result.stderr
    assert "MINI_HEARTBEAT_ARM=1" in result.stderr


def test_arm_sh_does_not_refuse_when_arm_flag_set(tmp_path):
    stub_path = _darwin_path_entry(tmp_path)
    env = {
        **subprocess.os.environ,
        "PATH": f"{stub_path}:{subprocess.os.environ.get('PATH', '')}",
        "MINI_HEARTBEAT_ENV": "/dev/null",
        "MINI_HEARTBEAT_ARM": "1",
        "LAUNCH_AGENTS_DIR": str(tmp_path / "LaunchAgents"),
    }

    result = subprocess.run(
        ["bash", str(ARM_SH)],
        env=env,
        capture_output=True,
        text=True,
    )

    # Past the refuse gate; missing plists is the expected next failure.
    assert result.returncode == 1
    assert "Refusing to arm" not in result.stderr
    assert "Plists missing" in result.stderr