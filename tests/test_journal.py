import json
import shutil
import threading

import pytest

from app.journal import (
    default_journal_path,
    list_runs,
    read_journal,
    undo_last_run,
    write_journal,
)


def test_write_and_read_journal(tmp_path):
    journal = tmp_path / "journal.json"
    source = tmp_path / "a.txt"
    destination = tmp_path / "sub" / "a.txt"

    path = write_journal([(source, destination)], journal)

    assert path == journal
    entries = read_journal(journal)
    assert len(entries) == 1
    assert entries[0].source == source
    assert entries[0].destination == destination
    assert entries[0].moved_at


def test_write_journal_stores_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    journal = tmp_path / "journal.json"

    write_journal([("relative/a.txt", "relative/dest/a.txt")], journal)

    entry = read_journal(journal)[0]
    assert entry.source.is_absolute()
    assert entry.destination.is_absolute()
    assert entry.source == (tmp_path / "relative" / "a.txt").resolve()


def test_undo_skips_when_moved_path_is_a_directory(tmp_path):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    destination.mkdir(parents=True)
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    preview = undo_last_run(journal, dry_run=True)

    assert preview.restored == []
    assert len(preview.skipped) == 1


def test_read_missing_journal(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_journal(tmp_path / "missing.json")


def test_read_invalid_journal(tmp_path):
    journal = tmp_path / "journal.json"
    journal.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError):
        read_journal(journal)


def test_read_journal_with_invalid_entry(tmp_path):
    journal = tmp_path / "journal.json"
    journal.write_text('{"entries": [{}]}', encoding="utf-8")

    with pytest.raises(ValueError):
        read_journal(journal)


def test_undo_skips_missing_moved_file(tmp_path):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    result = undo_last_run(journal)

    assert result.ok
    assert len(result.skipped) == 1
    assert journal.exists()


def test_undo_dry_run_reports_missing_moved_file_as_skipped(tmp_path):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    preview = undo_last_run(journal, dry_run=True)

    assert preview.restored == []
    assert len(preview.skipped) == 1
    assert journal.exists()


def test_undo_dry_run_reports_existing_original_as_skipped(tmp_path):
    source = tmp_path / "photo.jpg"
    destination = tmp_path / "dest" / "photo.jpg"
    destination.parent.mkdir()
    source.write_text("original", encoding="utf-8")
    destination.write_text("moved", encoding="utf-8")

    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    preview = undo_last_run(journal, dry_run=True)

    assert preview.restored == []
    assert len(preview.skipped) == 1
    assert journal.exists()


def test_read_journal_rejects_non_list_entries(tmp_path):
    journal = tmp_path / "journal.json"
    journal.write_text('{"entries": null}', encoding="utf-8")

    with pytest.raises(ValueError):
        read_journal(journal)


def test_read_journal_rejects_empty_paths(tmp_path):
    journal = tmp_path / "journal.json"
    journal.write_text('{"entries": [{"source": "", "destination": "x"}]}', encoding="utf-8")

    with pytest.raises(ValueError):
        read_journal(journal)


def test_undo_restores_files(tmp_path):
    source = tmp_path / "source" / "photo.jpg"
    destination = tmp_path / "dest" / "photo.jpg"
    source.parent.mkdir()
    destination.parent.mkdir()
    source.write_text("data", encoding="utf-8")
    shutil.move(str(source), str(destination))

    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    preview = undo_last_run(journal, dry_run=True)
    assert len(preview) == 1
    assert destination.exists()
    assert journal.exists()

    result = undo_last_run(journal)

    assert result.ok
    assert len(result) == 1
    assert source.read_text(encoding="utf-8") == "data"
    assert not destination.exists()
    assert not journal.exists()


def test_undo_skips_when_original_exists(tmp_path):
    source = tmp_path / "photo.jpg"
    destination = tmp_path / "dest" / "photo.jpg"
    destination.parent.mkdir()
    source.write_text("original", encoding="utf-8")
    destination.write_text("moved", encoding="utf-8")

    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    result = undo_last_run(journal)

    assert result.ok
    assert len(result.skipped) == 1
    assert source.read_text(encoding="utf-8") == "original"
    assert destination.exists()
    assert journal.exists()


def test_default_journal_path_honors_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert default_journal_path() == tmp_path / "FileOrganizer" / "last-run.json"


def test_journal_history_and_undo_specific_run(tmp_path):
    journal = tmp_path / "journal.json"
    pairs = [
        (tmp_path / "a.txt", tmp_path / "dest_a" / "a.txt", "a"),
        (tmp_path / "b.txt", tmp_path / "dest_b" / "b.txt", "b"),
    ]
    for source, destination, content in pairs:
        destination.parent.mkdir()
        source.write_text(content, encoding="utf-8")
        shutil.move(str(source), str(destination))
        write_journal([(source, destination)], journal)

    runs = list_runs(journal)
    assert [run.id for run in runs] == [1, 2]
    assert len(read_journal(journal, run_id=1)) == 1

    first = undo_last_run(journal, run_id=1)
    assert first.ok
    assert len(first) == 1
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a"
    assert (tmp_path / "dest_b" / "b.txt").exists()
    assert [run.id for run in list_runs(journal)] == [2]

    second = undo_last_run(journal)
    assert second.ok
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "b"
    assert not journal.exists()


def test_read_journal_rejects_unknown_run(tmp_path):
    journal = tmp_path / "journal.json"
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    write_journal([(source, destination)], journal)

    with pytest.raises(ValueError):
        read_journal(journal, run_id=99)


def test_legacy_journal_can_be_undone_by_run_id(tmp_path):
    journal = tmp_path / "journal.json"
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    destination.parent.mkdir()
    source.write_text("legacy", encoding="utf-8")
    shutil.move(str(source), str(destination))
    journal.write_text(
        json.dumps(
            {
                "created_at": "old",
                "entries": [{"source": str(source), "destination": str(destination)}],
            }
        ),
        encoding="utf-8",
    )

    assert [run.id for run in list_runs(journal)] == [1]
    result = undo_last_run(journal, run_id=1)

    assert result.ok
    assert source.read_text(encoding="utf-8") == "legacy"
    assert not journal.exists()


def test_undo_can_be_cancelled(tmp_path):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    destination.parent.mkdir()
    destination.write_text("data", encoding="utf-8")
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    result = undo_last_run(journal, should_cancel=lambda: True)

    assert result.cancelled
    assert result.restored == []
    assert destination.exists()
    assert journal.exists()


def test_write_journal_migrates_legacy_without_losing_entries(tmp_path):
    journal = tmp_path / "journal.json"
    legacy_source = tmp_path / "legacy.txt"
    legacy_destination = tmp_path / "legacy_dest" / "legacy.txt"
    new_source = tmp_path / "new.txt"
    new_destination = tmp_path / "new_dest" / "new.txt"
    journal.write_text(
        json.dumps(
            {
                "created_at": "old",
                "entries": [
                    {"source": str(legacy_source), "destination": str(legacy_destination)}
                ],
            }
        ),
        encoding="utf-8",
    )

    write_journal([(new_source, new_destination)], journal)

    runs = list_runs(journal)
    assert [run.id for run in runs] == [1, 2]
    assert read_journal(journal, run_id=1)[0].source == legacy_source
    assert read_journal(journal, run_id=2)[0].source == new_source


def test_concurrent_writes_keep_every_run(tmp_path):
    journal = tmp_path / "journal.json"
    barrier = threading.Barrier(8)

    def write_run(index: int) -> None:
        barrier.wait()
        source = tmp_path / f"file-{index}.txt"
        destination = tmp_path / "dest" / source.name
        write_journal([(source, destination)], journal)

    threads = [threading.Thread(target=write_run, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()

    runs = list_runs(journal)
    assert len(runs) == 8
    assert [run.id for run in runs] == list(range(1, 9))


def test_undo_pinned_run_ignores_newer_writes(tmp_path):
    journal = tmp_path / "journal.json"
    pairs = [
        (tmp_path / "a.txt", tmp_path / "dest_a" / "a.txt", "a"),
        (tmp_path / "b.txt", tmp_path / "dest_b" / "b.txt", "b"),
    ]
    for source, destination, content in pairs:
        destination.parent.mkdir()
        source.write_text(content, encoding="utf-8")
        shutil.move(str(source), str(destination))
        write_journal([(source, destination)], journal)

    preview = undo_last_run(journal, dry_run=True, run_id=1)
    assert preview.run_id == 1

    write_journal([(tmp_path / "c.txt", tmp_path / "dest_c" / "c.txt")], journal)

    result = undo_last_run(journal, run_id=preview.run_id)

    assert result.ok
    assert result.run_id == 1
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "a"
    assert (tmp_path / "dest_b" / "b.txt").exists()
    assert [run.id for run in list_runs(journal)] == [2, 3]
