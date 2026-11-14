from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JournalEntry:
    source: Path
    destination: Path
    moved_at: str


@dataclass
class UndoResult:
    """Summary of an undo run."""

    restored: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)

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
    """Write the performed moves to a JSON journal, replacing any previous one."""
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

    payload = {"created_at": created_at, "entries": entries}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)

    logger.info("Wrote journal with %d entr(ies) to %s", len(entries), target)
    return target


def read_journal(path: str | Path | None = None) -> list[JournalEntry]:
    """Read a journal file, returning its entries in the recorded order."""
    target = Path(path) if path is not None else default_journal_path()
    if not target.exists():
        raise FileNotFoundError(f"No se encontró journal en: {target}")

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        raw_entries = payload["entries"]
        if not isinstance(raw_entries, list):
            raise TypeError("journal entries must be a list")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Journal inválido: {target}") from exc

    entries: list[JournalEntry] = []
    for raw in raw_entries:
        try:
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


def undo_last_run(
    path: str | Path | None = None,
    *,
    dry_run: bool = False,
) -> UndoResult:
    """Move files back to their original locations using a journal."""
    target = Path(path) if path is not None else default_journal_path()
    entries = read_journal(target)

    result = UndoResult()

    for entry in reversed(entries):
        destination = entry.destination
        source = entry.source

        if dry_run:
            if not destination.is_file():
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
            if not destination.is_file():
                result.skipped.append((destination, "El archivo movido ya no existe."))
                continue
            if source.exists():
                result.skipped.append(
                    (destination, f"El destino original ya existe: {source}")
                )
                continue

            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source))
            result.restored.append((destination, source))
        except Exception as exc:
            logger.warning("Could not undo move of %s: %s", destination, exc)
            result.errors.append((destination, str(exc)))

    if not dry_run and not result.errors and not result.skipped:
        try:
            target.unlink()
        except OSError as exc:
            logger.warning("Could not remove journal %s: %s", target, exc)

    return result
