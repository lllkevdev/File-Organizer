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


def test_read_missing_journal(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_journal(tmp_path / "missing.json")


def test_read_invalid_journal(tmp_path):
    journal = tmp_path / "journal.json"
    journal.write_text("{not json", encoding="utf-8")

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
