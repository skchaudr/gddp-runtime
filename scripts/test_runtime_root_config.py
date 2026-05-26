import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock


def _reload_module(name):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_legacy_scripts_prefer_gddp_runtime_root(monkeypatch, tmp_path):
    monkeypatch.setenv("GDDP_RUNTIME_ROOT", str(tmp_path / "runtime-root"))
    monkeypatch.setenv("OPCLAW_ROOT", str(tmp_path / "legacy-root"))
    sys.modules["flask"] = MagicMock()

    for module_name in (
        "scripts.dry_run",
        "scripts.heartbeat",
        "scripts.intake_server",
        "scripts.rollback",
    ):
        module = _reload_module(module_name)

        assert module.RUNTIME_ROOT == Path(tmp_path / "runtime-root")
        assert module.DB_PATH == Path(tmp_path / "runtime-root" / "db" / "queue.db")


def test_legacy_scripts_keep_opclaw_root_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("GDDP_RUNTIME_ROOT", raising=False)
    monkeypatch.setenv("OPCLAW_ROOT", str(tmp_path / "legacy-root"))
    sys.modules["flask"] = MagicMock()

    for module_name in (
        "scripts.dry_run",
        "scripts.heartbeat",
        "scripts.intake_server",
        "scripts.rollback",
    ):
        module = _reload_module(module_name)

        assert module.RUNTIME_ROOT == Path(tmp_path / "legacy-root")
        assert module.DB_PATH == Path(tmp_path / "legacy-root" / "db" / "queue.db")
