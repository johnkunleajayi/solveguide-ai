import sys
from unittest.mock import patch

from app import config


def test_frozen_configuration_ignores_dotenv_and_uses_writable_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with patch.object(sys, "frozen", True, create=True):
        env, storage = config.runtime_paths()
    assert env is None
    assert storage == tmp_path / "SolveGuide AI" / "backend" / "context-library"


def test_development_configuration_is_unchanged():
    with patch.object(sys, "frozen", False, create=True):
        env, storage = config.runtime_paths()
    assert env == config.BACKEND_ROOT / ".env"
    assert storage == config.BACKEND_ROOT.parent / ".cache" / "context-library"
    assert config.Settings(_env_file=None).answer_timeout_seconds == 120


def test_entry_point_keeps_localhost_and_windows_loop(monkeypatch):
    import packaged_entry

    captured = {}
    monkeypatch.setattr(sys, "argv", ["solveguide-backend", "--port", "8801"])
    monkeypatch.setattr(
        packaged_entry.uvicorn, "run", lambda app, **kwargs: captured.update(app=app, **kwargs)
    )
    packaged_entry.main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8801
    assert captured["app"] == "app.main:app"
    assert captured["loop"] == "app.runtime:event_loop"
