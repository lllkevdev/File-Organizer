from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JournalEntry:
    source: Path
    destination: Path
    moved_at: str


@dataclass(frozen=True)
class JournalRun:
    """A recorded organize run, identified by a sequential id."""

    id: int
    created_at: str
    entries: tuple[JournalEntry, ...]

    def __len__(self) -> int:
        return len(self.entries)


@dataclass
class UndoResult:
    """Summary of an undo run."""

    restored: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False
    run_id: int | None = None

    def __len__(self) -> int:
        return len(self.restored)

    @property
    def ok(self) -> bool:
        return not self.errors


def default_journal_path() -> Path:
    """Return the default journal location for the current user."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "FileOrganizer" / "last-run.json"


def write_journal(
    moves: Iterable[tuple[str | Path, str | Path]],
    path: str | Path | None = None,
) -> Path:
    """Append a run with the performed moves to the journal."""
    target = Path(path) if path is not None else default_journal_path()
    created_at = datetime.now(timezone.utc).isoformat()
    entries = [
        {
            "source": str(Path(source).resolve()),
            "destination": str(Path(destination).resolve()),
            "moved_at": created_at,
        }
        for source, destination in moves
    ]

    with _journal_lock(target):
        payload = _load_payload(target) if target.exists() else {}
        history = _history_from_payload(payload)
        if not history:
            legacy_entries = payload.get("entries")
            if isinstance(legacy_entries, list) and legacy_entries:
                history.append(
                    {
                        "id": 1,
                        "created_at": str(payload.get("created_at", "")),
                        "entries": legacy_entries,
                    }
                )

        next_id = max((run["id"] for run in history), default=0) + 1
        history.append({"id": next_id, "created_at": created_at, "entries": entries})

        new_payload: dict[str, Any] = {
            "created_at": created_at,
            "entries": entries,
            "history": history,
        }
        _atomic_write_json(target, new_payload)

    logger.info("Wrote journal run %d with %d entr(ies) to %s", next_id, len(entries), target)
    return target


def list_runs(path: str | Path | None = None) -> list[JournalRun]:
    """Return all recorded runs, oldest first."""
    target = Path(path) if path is not None else default_journal_path()
    payload = _load_payload(target)
    history = _history_from_payload(payload)

    if not history:
        created_at = str(payload.get("created_at", ""))
        entries = _parse_entries(payload.get("entries", []), target)
        return [JournalRun(id=1, created_at=created_at, entries=tuple(entries))]

    return [
        JournalRun(
            id=run["id"],
            created_at=run["created_at"],
            entries=tuple(_parse_entries(run["entries"], target)),
        )
        for run in history
    ]


def read_journal(
    path: str | Path | None = None,
    *,
    run_id: int | None = None,
) -> list[JournalEntry]:
    """Read the entries of a run, returning them in the recorded order."""
    target = Path(path) if path is not None else default_journal_path()
    _resolved_id, entries = _resolve_run(target, run_id)
    return entries


def undo_last_run(
    path: str | Path | None = None,
    *,
    dry_run: bool = False,
    run_id: int | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> UndoResult:
    """Move files back to their original locations using a journal run."""
    from app.organizer import OperationCancelledError, move_file

    target = Path(path) if path is not None else default_journal_path()
    resolved_id, entries = _resolve_run(target, run_id)

    result = UndoResult(run_id=resolved_id)

    for entry in reversed(entries):
        if should_cancel is not None and should_cancel():
            result.cancelled = True
            logger.info("Undo cancelled before %s", entry.destination)
            break

        destination = entry.destination
        source = entry.source

        if dry_run:
            if destination.is_symlink() or not destination.is_file():
                result.skipped.append((destination, "El archivo movido ya no existe."))
                continue
            if source.exists():
                result.skipped.append(
                    (destination, f"El destino original ya existe: {source}")
                )
                continue
            result.restored.append((destination, source))
            continue

        try:
            if destination.is_symlink() or not destination.is_file():
                result.skipped.append((destination, "El archivo movido ya no existe."))
                continue
            if source.exists():
                result.skipped.append(
                    (destination, f"El destino original ya existe: {source}")
                )
                continue

            source.parent.mkdir(parents=True, exist_ok=True)
            restored_to = move_file(
                destination,
                source,
                should_cancel=should_cancel,
            )
            result.restored.append((destination, restored_to))
        except OperationCancelledError:
            result.cancelled = True
            logger.info("Undo cancelled during copy of %s", destination)
            break
        except Exception as exc:
            logger.warning("Could not undo move of %s: %s", destination, exc)
            result.errors.append((destination, str(exc)))

    complete = not result.errors and not result.skipped and not result.cancelled
    if not dry_run and complete:
        try:
            _remove_run(target, resolved_id)
        except (OSError, ValueError) as exc:
            logger.warning("Could not update journal %s: %s", target, exc)
            result.errors.append((target, f"No se pudo actualizar el journal: {exc}"))

    return result


def _load_payload(target: Path) -> dict[str, Any]:
    if not target.exists():
        raise FileNotFoundError(f"No se encontró journal en: {target}")

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Journal inválido: {target}") from exc
    except OSError as exc:
        raise ValueError(f"No se pudo leer el journal {target}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Journal inválido: {target}")
    return payload


def _history_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_history = payload.get("history", [])
    if not isinstance(raw_history, list):
        raise ValueError("El historial del journal debe ser una lista")

    history: list[dict[str, Any]] = []
    for raw in raw_history:
        if not isinstance(raw, dict):
            raise ValueError("Entrada de historial inválida")
        identifier = raw.get("id")
        if not isinstance(identifier, int) or isinstance(identifier, bool):
            raise ValueError("Id de run inválido")
        history.append(
            {
                "id": identifier,
                "created_at": str(raw.get("created_at", "")),
                "entries": raw.get("entries", []),
            }
        )
    return sorted(history, key=lambda run: run["id"])


def _parse_entries(raw_entries: object, target: Path) -> list[JournalEntry]:
    if not isinstance(raw_entries, list):
        raise ValueError(f"Journal entries must be a list: {target}")

    entries: list[JournalEntry] = []
    for raw in raw_entries:
        try:
            if not isinstance(raw, dict):
                raise TypeError("journal entry must be an object")
            source = raw["source"]
            destination = raw["destination"]
            if not isinstance(source, str) or not isinstance(destination, str):
                raise TypeError("journal paths must be strings")
            if not source or not destination:
                raise ValueError("journal paths must not be empty")
            entries.append(
                JournalEntry(
                    source=Path(source),
                    destination=Path(destination),
                    moved_at=str(raw.get("moved_at", "")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Entrada de journal inválida en: {target}") from exc

    return entries


@contextmanager
def _journal_lock(target: Path) -> Iterator[None]:
    lock_path = target.with_name(f".{target.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 5.0

    while True:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > 30.0:
                try:
                    lock_path.unlink()
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"No se pudo bloquear el journal: {lock_path}") from None
            time.sleep(0.02)
            continue
        try:
            os.write(descriptor, str(os.getpid()).encode("ascii"))
        finally:
            os.close(descriptor)
        break

    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not release journal lock %s: %s", lock_path, exc)


def _resolve_run(target: Path, run_id: int | None) -> tuple[int, list[JournalEntry]]:
    payload = _load_payload(target)
    history = _history_from_payload(payload)

    if run_id is None:
        if history:
            run = history[-1]
            return run["id"], _parse_entries(run["entries"], target)
        return 1, _parse_entries(payload.get("entries", []), target)

    for run in history:
        if run["id"] == run_id:
            return run["id"], _parse_entries(run["entries"], target)

    if run_id == 1 and not history:
        return 1, _parse_entries(payload.get("entries", []), target)
    raise ValueError(f"No existe el run {run_id} en: {target}")


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _remove_run(target: Path, run_id: int) -> None:
    with _journal_lock(target):
        payload = _load_payload(target)
        history = _history_from_payload(payload)

        if not history:
            target.unlink(missing_ok=True)
            return

        remaining = [run for run in history if run["id"] != run_id]
        if not remaining:
            target.unlink(missing_ok=True)
            return

        latest = remaining[-1]
        payload["history"] = remaining
        payload["entries"] = latest["entries"]
        payload["created_at"] = latest["created_at"]
        _atomic_write_json(target, payload)
