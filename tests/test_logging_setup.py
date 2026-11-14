import logging

import pytest

from app.logging_setup import configure_logging, default_log_path


def _remove_file_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            root.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def clean_file_handlers():
    _remove_file_handlers()
    yield
    _remove_file_handlers()


def test_configure_logging_default():
    assert configure_logging() is None


def test_configure_logging_verbose():
    assert configure_logging(verbose=True) is None


def test_configure_logging_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    path = configure_logging(log_to_file=True)

    assert path == tmp_path / "FileOrganizer" / "file-organizer.log"
    logging.getLogger("test").warning("hola")
    assert path is not None
    assert "hola" in path.read_text(encoding="utf-8")


def test_configure_logging_attaches_one_file_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    first = configure_logging(log_to_file=True)
    second = configure_logging(log_to_file=True)

    file_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.FileHandler)
    ]
    assert first == second
    assert len(file_handlers) == 1


def test_default_log_path_honors_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert default_log_path() == tmp_path / "FileOrganizer" / "file-organizer.log"
