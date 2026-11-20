from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(*, verbose: bool = False, log_to_file: bool = False) -> Path | None:
    """Configure root logging for the CLI or GUI.

    Without ``verbose`` only warnings and errors reach the console. The GUI has
    no console, so it also writes informational logs to a file.

    Returns the log file path when one was configured, otherwise ``None``.
    """
    console_level = logging.DEBUG if verbose else logging.WARNING
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=console_level, format=_LOG_FORMAT)
    elif root.level == logging.NOTSET or root.level > console_level:
        root.setLevel(console_level)

    for handler in root.handlers:
        if not isinstance(handler, logging.FileHandler):
            handler.setLevel(console_level)

    if not log_to_file:
        return None

    file_level = logging.DEBUG if verbose else logging.INFO
    if root.level == logging.NOTSET or root.level > file_level:
        root.setLevel(file_level)

    log_path = default_log_path()
    if _attach_file_handler(root, log_path, file_level):
        return log_path
    return None


def default_log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "FileOrganizer" / "file-organizer.log"


def _attach_file_handler(root: logging.Logger, path: Path, level: int) -> bool:
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == path:
            handler.setLevel(level)
            return True

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("No se pudo crear el log %s: %s", path, exc)
        return False

    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.setLevel(level)
    root.addHandler(handler)
    return True
