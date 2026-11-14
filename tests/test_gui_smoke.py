import sys
import threading
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app import __version__  # noqa: E402
from app.gui import MainWindow  # noqa: E402
from app.journal import write_journal  # noqa: E402
from app.organizer import OrganizeResult  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="GUI smoke runs on Windows")


def _wait_for_worker(qapp, window, timeout=10):
    deadline = time.monotonic() + timeout
    while window._thread is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert window._thread is None


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def test_main_window_renders_and_runs_preview(qapp, tmp_path):
    window = MainWindow()
    window.show()
    qapp.processEvents()

    assert window.isVisible()
    assert __version__ in window.windowTitle()

    window.folder_input.setText(str(tmp_path))
    window.run_preview()
    assert window._thread is not None

    deadline = time.monotonic() + 10
    while window._thread is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert window._thread is None
    assert "0 archivo" in window.log.toPlainText()

    window.close()
    qapp.processEvents()


def test_new_buttons_initial_state(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("app.gui.default_journal_path", lambda: tmp_path / "missing.json")
    window = MainWindow()
    window.show()
    qapp.processEvents()

    assert window.undo_button.text() == "Deshacer último run"
    assert not window.undo_button.isEnabled()
    assert window.cancel_button.text() == "Cancelar"
    assert not window.cancel_button.isEnabled()
    assert window.logs_button.text() == "Abrir carpeta de logs"
    assert window.journal_button.text() == "Abrir journal"

    window.close()
    qapp.processEvents()


def test_undo_button_restores_last_run(qapp, tmp_path, monkeypatch):
    source = tmp_path / "photo.jpg"
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()
    destination.write_text("data", encoding="utf-8")
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    monkeypatch.setattr("app.gui.default_journal_path", lambda: journal)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert window.undo_button.isEnabled()

    window.undo_button.click()
    _wait_for_worker(qapp, window)

    assert source.read_text(encoding="utf-8") == "data"
    assert not destination.exists()
    assert not journal.exists()
    assert "Restaurado" in window.log.toPlainText()
    assert not window.undo_button.isEnabled()

    window.close()
    qapp.processEvents()


def test_cancel_button_stops_worker(qapp, tmp_path, monkeypatch):
    started = threading.Event()

    def fake_organize(folder, **kwargs):
        started.set()
        should_cancel = kwargs.get("should_cancel")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if should_cancel is not None and should_cancel():
                return OrganizeResult(cancelled=True)
            time.sleep(0.01)
        return OrganizeResult()

    monkeypatch.setattr("app.gui.organize_files", fake_organize)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window = MainWindow()
    window.show()
    window.folder_input.setText(str(tmp_path))
    window.run_organize()
    assert started.wait(2)

    qapp.processEvents()
    assert window.cancel_button.isEnabled()
    window.cancel_button.click()
    assert "Cancelando" in window.status.text()

    _wait_for_worker(qapp, window)

    assert window.status.text() == "Cancelado."
    assert not window.cancel_button.isEnabled()

    window.close()
    qapp.processEvents()


def test_open_buttons_target_logs_and_journal(qapp, tmp_path, monkeypatch):
    logs = tmp_path / "logs" / "file-organizer.log"
    journal = tmp_path / "journal.json"
    journal.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.gui.default_log_path", lambda: logs)
    monkeypatch.setattr("app.gui.default_journal_path", lambda: journal)

    window = MainWindow()
    opened = []
    monkeypatch.setattr(window, "_open_path", lambda path: opened.append(path))

    window.open_logs_folder()
    window.open_journal()

    assert logs.parent.is_dir()
    assert opened == [logs.parent, journal]

    window.close()
    qapp.processEvents()
