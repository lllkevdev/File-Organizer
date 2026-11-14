import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

from app import __version__
from app.gui import MainWindow

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="GUI smoke runs on Windows")


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
