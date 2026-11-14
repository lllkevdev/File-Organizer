from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app import __version__
from app.journal import default_journal_path, undo_last_run
from app.logging_setup import configure_logging
from app.organizer import OrganizeResult, execute_plan, organize_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file-organizer",
        description=(
            "Organize files from a folder into Windows user folders "
            "(Pictures/Videos/Documents/Music). Unmapped files go to Documents."
        ),
    )
    parser.add_argument("folder", type=Path, nargs="?", help="folder to organize")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="organize into category subfolders inside the source folder instead of system folders",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would happen without moving any file",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="also organize files inside subdirectories",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="extra filename pattern to ignore (can be repeated)",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="do not ask for confirmation",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="restore the files moved by the last run recorded in the journal",
    )
    parser.add_argument(
        "--journal",
        type=Path,
        default=None,
        help="journal file to read/write (default: user state directory)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(verbose=args.verbose)

    journal = args.journal if args.journal is not None else default_journal_path()

    if args.undo:
        return _run_undo(journal, assume_yes=args.yes, dry_run=args.dry_run)

    if args.folder is None:
        parser.error("the following arguments are required: folder")

    to_system = not args.in_place

    try:
        if not args.dry_run and not args.yes:
            preview = organize_files(
                args.folder,
                to_system=to_system,
                dry_run=True,
                recursive=args.recursive,
                excludes=args.exclude,
            )
            if not preview.moved:
                if preview.errors:
                    for source, message in preview.errors:
                        print(f"error: {source}: {message}", file=sys.stderr)
                    print(f"{len(preview.errors)} error(s).", file=sys.stderr)
                    return 1
                for skipped in preview.skipped:
                    print(f"skip: {skipped.path}: {skipped.reason}", file=sys.stderr)
                if preview.skipped:
                    print(f"{len(preview.skipped)} skipped.", file=sys.stderr)
                print("Nothing to organize.")
                return 0
            print(_format_preview(preview))
            if not _confirm(f"Move {len(preview.moved)} file(s)?"):
                print("Aborted.")
                return 0
            result = execute_plan(preview, journal_path=journal)
        else:
            result = organize_files(
                args.folder,
                to_system=to_system,
                dry_run=args.dry_run,
                recursive=args.recursive,
                excludes=args.exclude,
                journal_path=journal,
            )
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _print_result(result)
    return 0 if result.ok else 1


def _run_undo(journal: Path, *, assume_yes: bool, dry_run: bool) -> int:
    try:
        preview = undo_last_run(journal, dry_run=True)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    for destination, reason in preview.skipped:
        print(f"would skip: {destination}: {reason}", file=sys.stderr)

    if not preview.restored:
        print("Nothing to undo.")
        return 0

    for destination, source in preview.restored:
        print(f"would restore: {destination} -> {source}")
    print(f"\n{len(preview.restored)} file(s) would be restored.")

    if dry_run:
        print("Dry run: no files were restored.")
        return 0

    if not assume_yes and not _confirm(f"Restore {len(preview.restored)} file(s)?"):
        print("Aborted.")
        return 0

    result = undo_last_run(journal)

    for destination, source in result.restored:
        print(f"restored: {destination} -> {source}")
    for destination, reason in result.skipped:
        print(f"skipped: {destination}: {reason}", file=sys.stderr)
    for destination, message in result.errors:
        print(f"error: {destination}: {message}", file=sys.stderr)

    print(f"\n{len(result.restored)} file(s) restored.")
    if result.skipped:
        print(f"{len(result.skipped)} skipped.", file=sys.stderr)
    if result.errors:
        print(f"{len(result.errors)} error(s).", file=sys.stderr)

    return 0 if result.ok else 1


def _format_preview(result: OrganizeResult) -> str:
    lines = [f"  {move.source} -> {move.destination}" for move in result.moved]
    for skipped in result.skipped:
        lines.append(f"  skip: {skipped.path}: {skipped.reason}")
    for source, message in result.errors:
        lines.append(f"  error: {source}: {message}")
    lines.append("")
    lines.append(f"{len(result.moved)} file(s) would be moved.")
    if result.skipped:
        lines.append(f"{len(result.skipped)} skipped.")
    if result.errors:
        lines.append(f"{len(result.errors)} error(s).")
    return "\n".join(lines)


def _print_result(result: OrganizeResult) -> None:
    for move in result.moved:
        action = "would move" if result.dry_run else "moved"
        print(f"{action}: {move.source} -> {move.destination}")

    for skipped in result.skipped:
        print(f"skipped: {skipped.path}: {skipped.reason}", file=sys.stderr)

    for source, message in result.errors:
        print(f"error: {source}: {message}", file=sys.stderr)

    if result.dry_run:
        print(f"\n{len(result.moved)} file(s) would be moved.")
    else:
        print(f"\n{len(result.moved)} file(s) moved.")

    if result.skipped:
        print(f"{len(result.skipped)} skipped.", file=sys.stderr)
    if result.errors:
        print(f"{len(result.errors)} error(s).", file=sys.stderr)


def _confirm(message: str) -> bool:
    try:
        answer = input(f"{message} [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False

    return answer.strip().lower() in {"y", "yes", "s", "si", "sí"}


if __name__ == "__main__":
    raise SystemExit(main())
