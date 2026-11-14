import shutil

import pytest

from app.journal import (
    default_journal_path,
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
