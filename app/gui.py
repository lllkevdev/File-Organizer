from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
from app.journal import default_journal_path
from app.logging_setup import configure_logging
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
    ) -> None:
        super().__init__()
        self.folder = folder
        self.to_system = to_system
        self.dry_run = dry_run
        self.recursive = recursive
        self.excludes = excludes
        self.journal_path = journal_path

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
            )
            self.finished.emit(result)
        except Exception as exc:  # pragma: no cover - surfaced in UI
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"File Organizer {__version__}")
        self.resize(760, 520)
        self._thread: QThread | None = None
        self._worker: OrganizeWorker | None = None
        self._run_id = 0

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
        self.preview_button.clicked.connect(self.run_preview)
        self.organize_button.clicked.connect(self.run_organize)
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.organize_button)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.status = QLabel("Listo.")
        layout.addWidget(self.status)

    def browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta")
        if folder:
            self.folder_input.setText(folder)

    def _selected_folder(self) -> Path | None:
        text = self.folder_input.text().strip()
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

    def _start_worker(self, folder: Path, *, dry_run: bool) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        self._set_busy(True)
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

        self.log.setPlainText("\n".join(lines) if lines else "Nada para organizar.")
        self.status.setText("Completado con errores." if result.errors else "Completado.")
        self._set_busy(False)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.log.setPlainText(f"Error: {message}")
        self.status.setText("Error.")
        self._set_busy(False)
        QMessageBox.critical(self, "Error", message)

    def _cleanup_worker_refs(self, run_id: int) -> None:
        if run_id != self._run_id:
            return
        self._thread = None
        self._worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait()
        super().closeEvent(event)

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.preview_button,
            self.organize_button,
            self.folder_input,
            self.system_radio,
            self.inplace_radio,
            self.dry_run_check,
            self.recursive_check,
            self.exclude_input,
        ):
            widget.setDisabled(busy)


def main() -> int:
    configure_logging(log_to_file=True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
