import pytest

from app.__main__ import main
from app.journal import write_journal
from app.organizer import get_destination


def test_cli_dry_run_in_place(tmp_path, capsys):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    code = main([str(folder), "--in-place", "--dry-run", "--yes"])

    out = capsys.readouterr().out
    assert code == 0
    assert "would move" in out
    assert str(photo) in out
    assert photo.exists()


def test_cli_moves_and_journal_enables_undo(tmp_path, capsys):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()
    journal = tmp_path / "journal.json"

    code = main([str(folder), "--in-place", "--yes", "--journal", str(journal)])
    assert code == 0
    moved = folder / "Images" / "photo.jpg"
    assert moved.exists()
    assert journal.exists()

    capsys.readouterr()
    code = main(["--undo", "--yes", "--journal", str(journal)])
    assert code == 0
    assert photo.exists()
    assert not moved.exists()
    assert not journal.exists()


def test_cli_aborts_without_confirmation(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()
    journal = tmp_path / "journal.json"

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    code = main([str(folder), "--in-place", "--journal", str(journal)])

    assert code == 0
    assert "Aborted" in capsys.readouterr().out
    assert photo.exists()
    assert not journal.exists()


def test_cli_nothing_to_organize(tmp_path, capsys):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    code = main([str(folder), "--in-place"])

    assert code == 0
    assert "Nothing to organize" in capsys.readouterr().out


def test_cli_preview_reports_skips_when_nothing_to_move(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "Documents"
    folder.mkdir()
    (folder / "document.pdf").touch()

    monkeypatch.setattr("app.system_folders.get_system_destination", lambda _category: folder)

    code = main([str(folder)])

    captured = capsys.readouterr()
    assert code == 0
    assert "skip:" in captured.err
    assert "Nothing to organize" in captured.out


def test_cli_preview_errors_return_1(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "photo.jpg").touch()

    def failing_get_destination(*args, **kwargs):
        raise OSError("access denied")

    monkeypatch.setattr("app.organizer.get_destination", failing_get_destination)

    code = main([str(folder), "--in-place"])

    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_cli_preview_with_mixed_errors_then_executes(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "photo.jpg").touch()
    (folder / "song.mp3").touch()
    journal = tmp_path / "journal.json"

    def mixed_get_destination(folder_path, category, **kwargs):
        if category == "Images":
            raise OSError("access denied")
        return get_destination(folder_path, category, **kwargs)

    monkeypatch.setattr("app.organizer.get_destination", mixed_get_destination)
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    code = main([str(folder), "--in-place", "--journal", str(journal)])

    captured = capsys.readouterr()
    assert code == 1
    assert "error:" in captured.out
    assert (folder / "Audio" / "song.mp3").exists()
    assert journal.exists()


def test_cli_undo_preview_reports_skips(tmp_path, capsys):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    code = main(["--undo", "--yes", "--journal", str(journal)])

    err = capsys.readouterr().err
    assert code == 0
    assert "would skip" in err
    assert journal.exists()


def test_cli_undo_aborts_without_confirmation(tmp_path, monkeypatch, capsys):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    destination.parent.mkdir()
    destination.write_text("moved", encoding="utf-8")
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    code = main(["--undo", "--journal", str(journal)])

    assert code == 0
    assert "Aborted" in capsys.readouterr().out
    assert destination.exists()
    assert journal.exists()


def test_cli_undo_dry_run_does_not_restore(tmp_path, capsys):
    source = tmp_path / "a.txt"
    destination = tmp_path / "dest" / "a.txt"
    destination.parent.mkdir()
    destination.write_text("moved", encoding="utf-8")
    journal = tmp_path / "journal.json"
    write_journal([(source, destination)], journal)

    code = main(["--undo", "--dry-run", "--yes", "--journal", str(journal)])

    out = capsys.readouterr().out
    assert code == 0
    assert "would restore" in out
    assert "Dry run" in out
    assert destination.exists()
    assert not source.exists()
    assert journal.exists()


def test_cli_undo_invalid_journal_returns_2(tmp_path, capsys):
    journal = tmp_path / "journal.json"
    journal.write_text("{not json", encoding="utf-8")

    code = main(["--undo", "--journal", str(journal)])

    assert code == 2
    assert "Error" in capsys.readouterr().err


def test_cli_missing_folder_returns_error(tmp_path):
    code = main([str(tmp_path / "missing"), "--in-place", "--yes"])

    assert code == 2


def test_cli_folder_is_required():
    with pytest.raises(SystemExit):
        main(["--dry-run"])
