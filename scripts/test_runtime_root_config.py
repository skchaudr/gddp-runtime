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
    monkeypatch.setitem(sys.modules, "flask", MagicMock())

    for module_name in (
        "scripts.init_db",
        "scripts.intake_server",
        "scripts.rollback",
    ):
        module = _reload_module(module_name)

        assert module.RUNTIME_ROOT == Path(tmp_path / "runtime-root")
        assert module.DB_PATH == Path(tmp_path / "runtime-root" / "db" / "queue.db")


def test_legacy_scripts_keep_opclaw_root_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("GDDP_RUNTIME_ROOT", raising=False)
    monkeypatch.setenv("OPCLAW_ROOT", str(tmp_path / "legacy-root"))
    monkeypatch.setitem(sys.modules, "flask", MagicMock())

    for module_name in (
        "scripts.init_db",
        "scripts.intake_server",
        "scripts.rollback",
    ):
        module = _reload_module(module_name)

        assert module.RUNTIME_ROOT == Path(tmp_path / "legacy-root")
        assert module.DB_PATH == Path(tmp_path / "legacy-root" / "db" / "queue.db")


def test_init_db_creates_missing_db_directory(monkeypatch, tmp_path):
    """A fresh rig checkout has no db/; init_db must not require one."""
    runtime_root = tmp_path / "fresh-rig"
    monkeypatch.setenv("GDDP_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.delenv("OPCLAW_ROOT", raising=False)

    init_db = _reload_module("scripts.init_db")
    assert not init_db.DB_PATH.parent.exists()

    init_db.init_db()

    assert init_db.DB_PATH.exists()
