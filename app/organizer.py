from __future__ import annotations

import fnmatch
import logging
import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.config import CATEGORIES, COMPOUND_SUFFIXES, DEFAULT_EXCLUDES, UNCATEGORIZED

logger = logging.getLogger(__name__)


class OperationCancelledError(Exception):
    """Raised when cancellation is observed during a file copy."""


CATEGORY_DIRS = frozenset(CATEGORIES) | {UNCATEGORIZED}
_CATEGORY_DIR_NAMES = {name.casefold() for name in CATEGORY_DIRS}


@dataclass(frozen=True)
class Move:
    """A file move, from its original path to its destination."""

    source: Path
    destination: Path


@dataclass(frozen=True)
class SkippedFile:
    """A file that was intentionally left in place, with the reason."""

    path: Path
    reason: str


@dataclass
class OrganizeResult:
    """Summary of an organize run.

    ``moved`` contains ``Move`` entries with both source and destination. In a
    dry run these are the moves that would happen, but no file is touched.
    """

    moved: list[Move] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    dry_run: bool = False
    cancelled: bool = False

    def __len__(self) -> int:
        return len(self.moved)

    @property
    def ok(self) -> bool:
        return not self.errors


def organize_files(
    folder: str | Path,
    *,
    to_system: bool = True,
    dry_run: bool = False,
    recursive: bool = False,
    excludes: Iterable[str] | None = None,
    journal_path: str | Path | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> OrganizeResult:
    """Validate the folder and move its files to category destinations.

    Args:
        folder: Folder whose files will be organized.
        to_system: When true (default), move files to Windows user folders
            (Pictures/Videos/Documents/Music). Unmapped categories go to Documents.
            When false, organize in-place into category subfolders under ``folder``.
        dry_run: When true, report planned moves without moving anything.
        recursive: Also process files inside subdirectories. In in-place mode,
            category folders are skipped to avoid reorganizing classified files.
        excludes: Extra filename patterns to ignore, on top of ``DEFAULT_EXCLUDES``.
        journal_path: When set, write the performed moves to this journal file so
            they can be reverted with :func:`app.journal.undo_last_run`.
        should_cancel: Optional callback checked before each file. When it returns
            true the run stops and the result is marked as ``cancelled``; files
            already moved stay moved and are still journaled.
    """
    folder = Path(folder).resolve()
    _validate_folder(folder)

    result = OrganizeResult(dry_run=dry_run)
    patterns = (*DEFAULT_EXCLUDES, *(excludes or ()))
    try:
        files = _collect_files(
            folder,
            recursive=recursive,
            excludes=patterns,
            skip_category_dirs=not to_system,
        )
    except OSError as exc:
        logger.warning("Could not enumerate %s: %s", folder, exc)
        result.errors.append((folder, f"No se pudo enumerar la carpeta: {exc}"))
        return result
    logger.info("Organizing %d file(s) from %s", len(files), folder)

    reserved: set[Path] = set()

    for file in files:
        if should_cancel is not None and should_cancel():
            result.cancelled = True
            logger.info("Organize run cancelled before %s", file)
            break

        category = get_category(file)

        try:
            destination_dir = get_destination(
                folder, category, to_system=to_system, create=not dry_run
            )
            if _is_same_folder(file.parent, destination_dir):
                result.skipped.append(
                    SkippedFile(file, "El archivo ya está en la carpeta de destino.")
                )
                continue

            destination = get_unique_destination(destination_dir / file.name, reserved=reserved)

            if dry_run:
                result.moved.append(Move(file, destination))
                reserved.add(destination)
                continue

            moved_to = move_file(file, destination, should_cancel=should_cancel)
            result.moved.append(Move(file, moved_to))
            reserved.add(moved_to)
        except OperationCancelledError:
            result.cancelled = True
            logger.info("Organize run cancelled during copy of %s", file)
            break
        except Exception as exc:
            logger.warning("Could not move %s: %s", file, exc)
            result.errors.append((file, str(exc)))

    logger.info(
        "Done: %d moved, %d skipped, %d error(s)",
        len(result.moved),
        len(result.skipped),
        len(result.errors),
    )

    if not dry_run and journal_path is not None and result.moved:
        _record_journal(result, journal_path)

    return result


def execute_plan(
    plan: OrganizeResult,
    *,
    journal_path: str | Path | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> OrganizeResult:
    """Execute a plan produced by a dry run without rescanning the source folder.

    Destinations are revalidated before each move so a file created in the
    meantime is never overwritten.
    """
    if not plan.dry_run:
        raise ValueError("execute_plan expects a dry-run plan.")

    result = OrganizeResult(dry_run=False)
    result.skipped.extend(plan.skipped)
    result.errors.extend(plan.errors)
    reserved: set[Path] = set()

    for move in plan.moved:
        if should_cancel is not None and should_cancel():
            result.cancelled = True
            logger.info("Plan execution cancelled before %s", move.source)
            break

        source = move.source

        try:
            if not source.is_file():
                result.errors.append((source, "El archivo de origen ya no existe."))
                continue
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            destination = get_unique_destination(move.destination, reserved=reserved)
            moved_to = move_file(source, destination, should_cancel=should_cancel)
            result.moved.append(Move(source, moved_to))
            reserved.add(moved_to)
        except OperationCancelledError:
            result.cancelled = True
            logger.info("Plan execution cancelled during copy of %s", source)
            break
        except Exception as exc:
            logger.warning("Could not move %s: %s", source, exc)
            result.errors.append((source, str(exc)))

    if journal_path is not None and result.moved:
        _record_journal(result, journal_path)

    return result


def _record_journal(result: OrganizeResult, journal_path: str | Path) -> None:
    try:
        _write_journal(result.moved, journal_path)
    except (OSError, ValueError, TypeError) as exc:
        logger.error("Could not write journal %s: %s", journal_path, exc)
        result.errors.append(
            (Path(journal_path), f"No se pudo escribir el journal; no se puede deshacer: {exc}")
        )


def _write_journal(moves: Iterable[Move], journal_path: str | Path) -> None:
    from app.journal import write_journal

    write_journal(((move.source, move.destination) for move in moves), journal_path)


def _is_same_folder(left: Path, right: Path) -> bool:
    """Return True when both paths point to the same directory."""
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def _validate_folder(folder: Path) -> None:
    if not folder.exists():
        raise FileNotFoundError(f"The selected folder does not exist: {folder}")

    if not folder.is_dir():
        raise NotADirectoryError(f"The selected path is not a directory: {folder}")


def _collect_files(
    folder: Path,
    *,
    recursive: bool,
    excludes: tuple[str, ...],
    skip_category_dirs: bool,
) -> list[Path]:
    candidates = folder.rglob("*") if recursive else folder.iterdir()
    files: list[Path] = []

    for item in candidates:
        try:
            if item.is_symlink() or not item.is_file():
                continue
        except OSError:
            continue
        relative = item.relative_to(folder)
        if skip_category_dirs and _is_in_category_dir(item, folder):
            continue
        if any(_is_excluded(part, excludes) for part in relative.parts):
            continue
        files.append(item)

    return sorted(files, key=lambda path: str(path).casefold())


def _is_in_category_dir(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False

    return len(relative.parts) > 1 and relative.parts[0].casefold() in _CATEGORY_DIR_NAMES


def _is_excluded(name: str, excludes: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in excludes)


def get_category(file: str | Path) -> str:
    """Return the category associated with a file extension."""
    file = Path(file)
    extension = _effective_extension(file.name.lower())

    for category, extensions in CATEGORIES.items():
        if extension in extensions:
            return category

    return UNCATEGORIZED


def _effective_extension(name: str) -> str:
    """Return the extension to classify by, unwrapping compound suffixes."""
    for suffix in COMPOUND_SUFFIXES:
        if name.endswith(suffix):
            return f".{suffix.rsplit('.', 1)[-1]}"

    return Path(name).suffix.lower()


def get_destination(
    folder: str | Path,
    category: str,
    *,
    to_system: bool = True,
    create: bool = True,
) -> Path:
    """Return the destination folder for a category.

    In system mode this resolves to a Windows known folder (unmapped categories go
    to Documents). In in-place mode it returns a category subfolder under ``folder``.
    """
    if to_system:
        from app.system_folders import get_system_destination

        destination = get_system_destination(category)
        if create:
            destination.mkdir(parents=True, exist_ok=True)
        return destination

    destination = Path(folder) / category
    if create:
        destination.mkdir(parents=True, exist_ok=True)
    return destination


def get_unique_destination(destination: Path, *, reserved: set[Path] | None = None) -> Path:
    """Return a unique destination path if the file already exists or is reserved."""
    reserved = reserved if reserved is not None else set()
    destination = Path(destination)
    original_name, extension = _split_name(destination.name)

    counter = 1
    candidate = destination

    while candidate.exists() or candidate in reserved:
        candidate = destination.parent / f"{original_name}_{counter}{extension}"
        counter += 1

    return candidate


def _split_name(name: str) -> tuple[str, str]:
    """Split a filename into base and extension, keeping compound suffixes intact."""
    lowered = name.lower()

    for suffix in COMPOUND_SUFFIXES:
        if lowered.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)], name[-len(suffix) :]

    base, dot, extension = name.rpartition(".")
    if not dot or not base:
        return name, ""

    return base, f".{extension}"


def move_file(
    file: str | Path,
    destination: str | Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> Path:
    """Move a regular file without ever overwriting an existing destination.

    Same-device moves use an atomic hard link plus unlink. Cross-device moves
    create the destination with ``O_EXCL`` and copy into it, so a concurrent
    file appearing at the destination causes an error instead of data loss.
    """
    source = Path(file)
    target = Path(destination)

    if source.is_symlink() or not source.is_file():
        raise FileNotFoundError(f"El archivo de origen no existe o no es regular: {source}")
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"El destino ya existe: {target}")

    try:
        same_device = source.stat().st_dev == target.parent.stat().st_dev
    except OSError:
        same_device = False

    if same_device:
        try:
            os.link(source, target)
        except OSError:
            _copy_and_unlink(source, target, should_cancel=should_cancel)
        else:
            _unlink_source(source, target)
    else:
        _copy_and_unlink(source, target, should_cancel=should_cancel)

    if target.is_symlink() or not target.is_file():
        raise OSError(f"El movimiento no produjo un archivo regular en: {target}")
    return target


def _unlink_source(source: Path, target: Path) -> None:
    try:
        source.unlink()
    except OSError:
        _cleanup_partial_target(target)
        raise


def _cleanup_partial_target(target: Path) -> None:
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not remove partial destination %s: %s", target, exc)


def _copy_and_unlink(
    source: Path,
    target: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    with source.open("rb") as src:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        descriptor = os.open(target, flags, 0o666)
        try:
            with os.fdopen(descriptor, "wb") as dst:
                while True:
                    if should_cancel is not None and should_cancel():
                        raise OperationCancelledError()
                    chunk = src.read(1_048_576)
                    if not chunk:
                        break
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            shutil.copystat(source, target)
        except BaseException:
            _cleanup_partial_target(target)
            raise
    _unlink_source(source, target)
