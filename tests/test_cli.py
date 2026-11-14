import pytest

from app.__main__ import main


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


def test_cli_missing_folder_returns_error(tmp_path):
    code = main([str(tmp_path / "missing"), "--in-place", "--yes"])

    assert code == 2


def test_cli_folder_is_required():
    with pytest.raises(SystemExit):
        main(["--dry-run"])
