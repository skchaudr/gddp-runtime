import subprocess
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent
SMOKE_SH = KIT_ROOT / "bin" / "smoke.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _setup_smoke_env(tmp_path: Path) -> dict[str, str]:
    runtime = tmp_path / "runtime"
    config = tmp_path / "config"
    (runtime / "scripts").mkdir(parents=True)
    (config / "graphs" / "gddp-runtime").mkdir(parents=True)
    (config / "graphs" / "gddp-runtime" / "project.yaml").write_text(
        "id: gddp-runtime\n"
    )

    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()

    _write_executable(
        stub_bin / "curl",
        "#!/bin/sh\n# stub: intake not listening\nexit 7\n",
    )
    _write_executable(
        stub_bin / "ssh",
        '#!/bin/sh\necho "live SSH must not run in smoke dry test" >&2\nexit 99\n',
    )
    _write_executable(
        stub_bin / "gh",
        "#!/bin/sh\n# stub: gh not authenticated\nexit 1\n",
    )
    _write_executable(
        stub_bin / "python3",
        "#!/bin/sh\n# stub heartbeat runner\nexit 0\n",
    )

    return {
        **subprocess.os.environ,
        "PATH": f"{stub_bin}:{subprocess.os.environ.get('PATH', '')}",
        "MINI_HEARTBEAT_ENV": "/dev/null",
        "GDDP_RUNTIME_ROOT": str(runtime),
        "GDDP_CONFIG_PATH": str(config),
        "GDDP_PROJECT_ID": "gddp-runtime",
        "GDDP_PROJECT_REPO": "skchaudr/gddp-runtime",
        "DEEPSEEK_API_KEY": "fake-deepseek-key",
        "GITHUB_WEBHOOK_SECRET": "fake-webhook-secret",
    }


def test_smoke_dry_run_reports_key_ok_lines(tmp_path):
    env = _setup_smoke_env(tmp_path)

    result = subprocess.run(
        ["bash", str(SMOKE_SH)],
        env=env,
        capture_output=True,
        text=True,
    )

    out = result.stdout
    assert result.returncode == 0, out + result.stderr
    assert "[ok] runtime scripts" in out
    assert "[ok] project.yaml" in out
    assert "[ok] DeepSeek key resolved" in out
    assert "[ok] webhook secret resolved" in out
    assert "[ok] heartbeat runner exited 0" in out
    assert "=== smoke: OK ===" in out
    assert "live SSH must not run" not in out + result.stderr


def test_smoke_dry_run_uses_env_keys_not_resolver_cmds(tmp_path):
    env = _setup_smoke_env(tmp_path)
    env["GDDP_DEEPSEEK_KEY_CMD"] = (
        'ssh -o BatchMode=yes sab-ssd@pi-big "pass show api/deepseek"'
    )
    env["GDDP_WEBHOOK_SECRET_CMD"] = (
        'ssh -o BatchMode=yes sab-ssd@pi-big "pass show gddp/webhook-secret"'
    )

    result = subprocess.run(
        ["bash", str(SMOKE_SH)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "live SSH must not run" not in result.stdout + result.stderr