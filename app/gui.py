from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.journal import UndoResult, default_journal_path, list_runs, undo_last_run
from app.logging_setup import configure_logging, default_log_path
from app.organizer import OrganizeResult, organize_files


class OrganizeWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        folder: Path,
        *,
        to_system: bool,
        dry_run: bool,
        recursive: bool,
        excludes: list[str],
        journal_path: Path | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.folder = folder
        self.to_system = to_system
        self.dry_run = dry_run
        self.recursive = recursive
        self.excludes = excludes
        self.journal_path = journal_path
        self.should_cancel = should_cancel

    @Slot()
    def run(self) -> None:
        try:
            result = organize_files(
                self.folder,
                to_system=self.to_system,
                dry_run=self.dry_run,
                recursive=self.recursive,
                excludes=self.excludes,
                journal_path=self.journal_path,
                should_cancel=self.should_cancel,
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self.failed.emit(str(exc))


class UndoWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        journal_path: Path,
        *,
        run_id: int | None = None,
        should_cancel: Callable[[], bool] | None = None,
        dry_run: bool = False,
    ) -> None:
        super().__init__()
        self.journal_path = journal_path
        self.run_id = run_id
        self.should_cancel = should_cancel
        self.dry_run = dry_run

    @Slot()
    def run(self) -> None:
        try:
            result = undo_last_run(
                self.journal_path,
                run_id=self.run_id,
                should_cancel=self.should_cancel,
                dry_run=self.dry_run,
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"File Organizer {__version__}")
        self.resize(760, 560)
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._run_id = 0
        self._cancel_event: threading.Event | None = None
        self._close_requested = False
        self._close_deadline = 0.0
        self._pending_undo: tuple[Path, int | None] | None = None
        self._start_undo_after_cleanup: tuple[Path, int | None] | None = None

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        folder_row = QHBoxLayout()
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Selecciona la carpeta a organizar...")
        browse_button = QPushButton("Examinar")
        browse_button.clicked.connect(self.browse_folder)
        folder_row.addWidget(QLabel("Carpeta:"))
        folder_row.addWidget(self.folder_input)
        folder_row.addWidget(browse_button)
        layout.addLayout(folder_row)

        mode_row = QHBoxLayout()
        self.system_radio = QRadioButton("Carpetas del sistema (predeterminado)")
        self.inplace_radio = QRadioButton("En la misma carpeta (in-place)")
        self.system_radio.setChecked(True)
        mode_row.addWidget(self.system_radio)
        mode_row.addWidget(self.inplace_radio)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        options_row = QHBoxLayout()
        self.dry_run_check = QCheckBox("Vista previa (dry-run)")
        self.recursive_check = QCheckBox("Recursivo")
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("Excluir patrones separados por ; (ej: *.tmp;*.bak)")
        options_row.addWidget(self.dry_run_check)
        options_row.addWidget(self.recursive_check)
        options_row.addWidget(QLabel("Excluir:"))
        options_row.addWidget(self.exclude_input)
        layout.addLayout(options_row)

        action_row = QHBoxLayout()
        self.preview_button = QPushButton("Vista previa")
        self.organize_button = QPushButton("Organizar")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setToolTip("Detiene la operación en curso entre archivos.")
        self.cancel_button.setEnabled(False)
        self.undo_button = QPushButton("Deshacer último run")
        self.undo_button.setToolTip(
            "Restaura los archivos movidos en el último run registrado en el journal."
        )
        self.preview_button.clicked.connect(self.run_preview)
        self.organize_button.clicked.connect(self.run_organize)
        self.cancel_button.clicked.connect(self.cancel_current_run)
        self.undo_button.clicked.connect(self.run_undo)
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.organize_button)
        action_row.addWidget(self.cancel_button)
        action_row.addStretch()
        action_row.addWidget(self.undo_button)
        layout.addLayout(action_row)

        tools_row = QHBoxLayout()
        self.logs_button = QPushButton("Abrir carpeta de logs")
        self.logs_button.clicked.connect(self.open_logs_folder)
        self.journal_button = QPushButton("Abrir journal")
        self.journal_button.clicked.connect(self.open_journal)
        tools_row.addWidget(self.logs_button)
        tools_row.addWidget(self.journal_button)
        tools_row.addStretch()
        tools_row.addWidget(QLabel("Run:"))
        self.run_combo = QComboBox()
        self.run_combo.setToolTip("Run del journal que se restaurará con Deshacer.")
        tools_row.addWidget(self.run_combo)
        layout.addLayout(tools_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.status = QLabel("Listo.")
        layout.addWidget(self.status)

        self._refresh_undo_button()

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta")
        if folder:
            self.folder_input.setText(folder)

    def _selected_folder(self) -> Path | None:
        text = self.folder_input.text().strip().strip('"').strip()
        if not text:
            QMessageBox.warning(self, "Carpeta requerida", "Selecciona una carpeta.")
            return None
        folder = Path(text)
        if not folder.exists() or not folder.is_dir():
            QMessageBox.warning(self, "Carpeta inválida", "La ruta no existe o no es una carpeta.")
            return None
        return folder

    def _excludes(self) -> list[str]:
        raw = self.exclude_input.text().strip()
        if not raw:
            return []
        return [part.strip() for part in raw.split(";") if part.strip()]

    def run_preview(self) -> None:
        folder = self._selected_folder()
        if folder is None:
            return
        self._start_worker(folder, dry_run=True)

    def run_organize(self) -> None:
        folder = self._selected_folder()
        if folder is None:
            return
        to_system = self.system_radio.isChecked()
        dry_run = self.dry_run_check.isChecked()
        if not dry_run:
            mode = (
                "carpetas del sistema de Windows"
                if to_system
                else "subcarpetas dentro del origen"
            )
            scope = (
                "todas las subcarpetas (recursivo)"
                if self.recursive_check.isChecked()
                else "el primer nivel"
            )
            answer = QMessageBox.question(
                self,
                "Confirmar organización",
                f"Se moverán los archivos de {scope} a {mode}.\n¿Continuar?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._start_worker(folder, dry_run=dry_run)

    def run_undo(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        journal = default_journal_path()
        if not journal.exists():
            QMessageBox.information(
                self, "Deshacer último run", "No hay ningún run para deshacer."
            )
            self._refresh_undo_button()
            return

        run_id: int | None = self.run_combo.currentData()
        self._pending_undo = (journal, run_id)
        self.log.clear()
        self.status.setText("Calculando vista previa...")
        self._start_undo_worker(journal, run_id, dry_run=True)

    @Slot(object)
    def _on_undo_preview_finished(self, result: UndoResult) -> None:
        pending = self._pending_undo
        self._pending_undo = None

        if result.cancelled:
            self.status.setText("Cancelado.")
            return
        if not result.restored:
            message = "No hay archivos para restaurar."
            if result.skipped:
                message += f"\n{len(result.skipped)} archivo(s) se omitirían."
            QMessageBox.information(self, "Deshacer último run", message)
            self.status.setText("Listo.")
            return
        if pending is None:
            return

        message = f"Se restaurarán {len(result.restored)} archivo(s)."
        if result.skipped:
            message += f"\n{len(result.skipped)} archivo(s) se omitirán."
        answer = QMessageBox.question(
            self,
            "Deshacer último run",
            f"{message}\n¿Continuar?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status.setText("Listo.")
            return

        journal, selected_id = pending
        pinned_id = selected_id if selected_id is not None else result.run_id
        self.status.setText("Deshaciendo...")
        self._start_undo_after_cleanup = (journal, pinned_id)

    def cancel_current_run(self) -> None:
        event = self._cancel_event
        if event is None or event.is_set():
            return
        event.set()
        self.cancel_button.setDisabled(True)
        self.status.setText("Cancelando...")

    def open_logs_folder(self) -> None:
        folder = default_log_path().parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self, "Abrir carpeta de logs", f"No se pudo crear la carpeta:\n{exc}"
            )
            return
        self._open_path(folder)

    def open_journal(self) -> None:
        journal = default_journal_path()
        if not journal.exists():
            QMessageBox.information(
                self, "Abrir journal", "Todavía no hay un journal. Organizá archivos primero."
            )
            self._refresh_undo_button()
            return
        self._open_path(journal)

    def _open_path(self, path: Path) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(self, "No se pudo abrir", f"No se pudo abrir:\n{path}")

    def _start_undo_worker(
        self,
        journal: Path,
        journal_run_id: int | None,
        *,
        dry_run: bool = False,
    ) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        self._close_requested = False
        self._cancel_event = threading.Event()
        self._set_busy(True, cancellable=True)
        self._run_id += 1
        worker_id = self._run_id

        thread = QThread(self)
        worker = UndoWorker(
            journal,
            run_id=journal_run_id,
            should_cancel=self._cancel_event.is_set,
            dry_run=dry_run,
        )
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        if dry_run:
            worker.finished.connect(self._on_undo_preview_finished)
        else:
            worker.finished.connect(self._on_undo_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._cleanup_worker_refs(worker_id))
        thread.start()

    def _start_worker(self, folder: Path, *, dry_run: bool) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        self._close_requested = False
        self._cancel_event = threading.Event()
        self._set_busy(True, cancellable=True)
        self.log.clear()
        self.status.setText("Procesando...")

        self._run_id += 1
        run_id = self._run_id

        thread = QThread(self)
        worker = OrganizeWorker(
            folder,
            to_system=self.system_radio.isChecked(),
            dry_run=dry_run,
            recursive=self.recursive_check.isChecked(),
            excludes=self._excludes(),
            journal_path=default_journal_path(),
            should_cancel=self._cancel_event.is_set,
        )
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._cleanup_worker_refs(run_id))
        thread.start()

    @Slot(object)
    def _on_finished(self, result: OrganizeResult) -> None:
        lines: list[str] = []
        for move in result.moved:
            action = "Se movería" if result.dry_run else "Movido"
            lines.append(f"{action}: {move.source} -> {move.destination}")
        for skipped in result.skipped:
            lines.append(f"Omitido: {skipped.path}: {skipped.reason}")
        for source, message in result.errors:
            lines.append(f"Error: {source}: {message}")

        if result.dry_run:
            lines.append(f"\n{len(result.moved)} archivo(s) se moverían.")
        else:
            lines.append(f"\n{len(result.moved)} archivo(s) movidos.")

        if result.skipped:
            lines.append(f"{len(result.skipped)} omitido(s).")
        if result.errors:
            lines.append(f"{len(result.errors)} error(es).")
        if result.cancelled:
            lines.append("\nOperación cancelada por el usuario.")

        self.log.setPlainText("\n".join(lines) if lines else "Nada para organizar.")
        if result.errors:
            self.status.setText("Completado con errores.")
        elif result.cancelled:
            self.status.setText("Cancelado.")
        else:
            self.status.setText("Completado.")

    @Slot(object)
    def _on_undo_finished(self, result: UndoResult) -> None:
        self._pending_undo = None
        lines: list[str] = []
        for destination, source in result.restored:
            lines.append(f"Restaurado: {destination} -> {source}")
        for destination, reason in result.skipped:
            lines.append(f"Omitido: {destination}: {reason}")
        for destination, message in result.errors:
            lines.append(f"Error: {destination}: {message}")

        lines.append(f"\n{len(result.restored)} archivo(s) restaurados.")
        if result.skipped:
            lines.append(f"{len(result.skipped)} omitido(s).")
        if result.errors:
            lines.append(f"{len(result.errors)} error(es).")
        if result.cancelled:
            lines.append("\nOperación cancelada por el usuario.")

        self.log.setPlainText("\n".join(lines))
        if result.errors:
            self.status.setText("Deshecho con errores.")
        elif result.cancelled:
            self.status.setText("Cancelado.")
        elif result.restored:
            self.status.setText("Deshecho.")
        else:
            self.status.setText("Nada restaurado.")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._pending_undo = None
        self._start_undo_after_cleanup = None
        self.log.setPlainText(f"Error: {message}")
        self.status.setText("Error.")
        QMessageBox.critical(self, "Error", message)

    def _cleanup_worker_refs(self, run_id: int) -> None:
        if run_id != self._run_id:
            return
        self._thread = None
        self._worker = None
        self._set_busy(False)
        self._refresh_undo_button()

        pending = self._start_undo_after_cleanup
        if pending is not None:
            self._start_undo_after_cleanup = None
            journal, journal_run_id = pending
            self._start_undo_worker(journal, journal_run_id)

    def _refresh_undo_button(self) -> None:
        selected: int | None = self.run_combo.currentData()
        self.run_combo.clear()
        self.run_combo.addItem("Último run", None)

        try:
            runs = list_runs(default_journal_path())
        except (OSError, ValueError):
            runs = []

        for run in runs:
            label = f"Run #{run.id} — {len(run)} archivo(s)"
            if run.created_at:
                label += f" — {run.created_at[:19]}"
            self.run_combo.addItem(label, run.id)

        if selected is not None:
            index = self.run_combo.findData(selected)
            if index >= 0:
                self.run_combo.setCurrentIndex(index)

        self.undo_button.setEnabled(self._thread is None and bool(runs))

    def closeEvent(self, event: QCloseEvent) -> None:
        thread = self._thread
        if thread is not None and thread.isRunning():
            if self._cancel_event is not None:
                self._cancel_event.set()
            self.cancel_button.setDisabled(True)
            self.status.setText("Cancelando...")
            self._close_requested = True
            self._close_deadline = time.monotonic() + 10.0
            QTimer.singleShot(100, self._finish_close)
            event.ignore()
            return
        super().closeEvent(event)

    def _finish_close(self) -> None:
        if not self._close_requested:
            return
        thread = self._thread
        if thread is not None and thread.isRunning():
            if time.monotonic() < self._close_deadline:
                QTimer.singleShot(100, self._finish_close)
            else:
                self._close_requested = False
                QMessageBox.information(
                    self,
                    "Operación en curso",
                    "La operación todavía está terminando. Esperá unos segundos "
                    "y volvé a cerrar.",
                )
            return
        self._close_requested = False
        self.close()

    def _set_busy(self, busy: bool, *, cancellable: bool = False) -> None:
        for widget in (
            self.preview_button,
            self.organize_button,
            self.folder_input,
            self.system_radio,
            self.inplace_radio,
            self.dry_run_check,
            self.recursive_check,
            self.exclude_input,
            self.logs_button,
            self.journal_button,
            self.run_combo,
        ):
            widget.setDisabled(busy)

        self.undo_button.setDisabled(busy)
        self.cancel_button.setEnabled(busy and cancellable)
        if not busy:
            self._cancel_event = None


def main() -> int:
    configure_logging(log_to_file=True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
