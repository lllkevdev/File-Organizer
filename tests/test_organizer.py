import shutil
from pathlib import Path

import pytest

from app.organizer import (
    OrganizeResult,
    _collect_files,
    execute_plan,
    get_category,
    get_destination,
    get_unique_destination,
    move_file,
    organize_files,
)


@pytest.fixture
def system_folders(tmp_path, monkeypatch):
    roots = {
        "Images": tmp_path / "SystemPictures",
        "Audio": tmp_path / "SystemMusic",
        "Videos": tmp_path / "SystemVideos",
        "Documents": tmp_path / "SystemDocuments",
    }

    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)

    def fake_get_system_destination(category):
        key = category if category in roots else "Documents"
        return roots[key]

    monkeypatch.setattr("app.system_folders.get_system_destination", fake_get_system_destination)
    return roots


def test_valid_folder(tmp_path):
    result = organize_files(tmp_path, to_system=False)

    assert isinstance(result, OrganizeResult)
    assert result.moved == []
    assert result.ok


def test_invalid_folder():
    with pytest.raises(FileNotFoundError):
        organize_files("this_folder_does_not_exist", to_system=False)


def test_path_is_not_a_directory(tmp_path):
    file = tmp_path / "file.txt"
    file.touch()

    with pytest.raises(NotADirectoryError):
        organize_files(file, to_system=False)


def test_file_categories():
    assert get_category(Path("photo.jpg")) == "Images"
    assert get_category(Path("song.mp3")) == "Audio"
    assert get_category(Path("video.mp4")) == "Videos"
    assert get_category(Path("document.pdf")) == "Documents"
    assert get_category(Path("archive.zip")) == "Archives"
    assert get_category(Path("unknown.xyz")) == "Other"


def test_uppercase_extension():
    assert get_category(Path("photo.JPG")) == "Images"


def test_file_without_extension():
    assert get_category(Path("README")) == "Other"


def test_destination_in_place(tmp_path):
    destination = get_destination(tmp_path, "Images", to_system=False)

    assert destination.exists()
    assert destination.is_dir()
    assert destination.name == "Images"


def test_destination_not_created_when_disabled(tmp_path):
    destination = get_destination(tmp_path, "Images", to_system=False, create=False)

    assert not destination.exists()


def test_unique_destination(tmp_path):
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()

    result = get_unique_destination(destination)

    assert result == destination


def test_duplicate_destination(tmp_path):
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()
    destination.touch()

    result = get_unique_destination(destination)

    assert result.name == "photo_1.jpg"


def test_multiple_duplicate_destination(tmp_path):
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()

    destination.touch()
    (destination.parent / "photo_1.jpg").touch()
    (destination.parent / "photo_2.jpg").touch()

    result = get_unique_destination(destination)

    assert result.name == "photo_3.jpg"


def test_compound_suffix_duplicate(tmp_path):
    destination = tmp_path / "Archives" / "backup.tar.gz"
    destination.parent.mkdir()
    destination.touch()

    result = get_unique_destination(destination)

    assert result.name == "backup_1.tar.gz"


def test_reserved_destination(tmp_path):
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()
    reserved = {destination}

    result = get_unique_destination(destination, reserved=reserved)

    assert result.name == "photo_1.jpg"


def test_move_file(tmp_path):
    source = tmp_path / "photo.jpg"
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()
    source.touch()

    result = move_file(source, destination)

    assert not source.exists()
    assert destination.exists()
    assert result == destination


def test_organize_files_in_place(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    photo = folder / "photo.jpg"
    document = folder / "document.pdf"
    song = folder / "song.mp3"

    photo.touch()
    document.touch()
    song.touch()

    result = organize_files(folder, to_system=False)

    assert (folder / "Images" / "photo.jpg").exists()
    assert (folder / "Documents" / "document.pdf").exists()
    assert (folder / "Audio" / "song.mp3").exists()

    assert not photo.exists()
    assert not document.exists()
    assert not song.exists()

    assert len(result.moved) == 3
    assert result.ok


def test_organize_duplicate_file_in_place(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    photo = folder / "photo.jpg"
    photo.touch()

    images = folder / "Images"
    images.mkdir()

    photo_duplicate = images / "photo.jpg"
    photo_duplicate.touch()

    organize_files(folder, to_system=False)

    assert (folder / "Images" / "photo_1.jpg").exists()


def test_duplicate_names_in_same_run_in_place(tmp_path):
    folder = tmp_path / "Downloads"
    (folder / "a").mkdir(parents=True)
    (folder / "b").mkdir(parents=True)

    (folder / "a" / "photo.jpg").touch()
    (folder / "b" / "photo.jpg").touch()

    result = organize_files(folder, to_system=False, recursive=True)

    names = {move.destination.name for move in result.moved}
    assert names == {"photo.jpg", "photo_1.jpg"}
    assert (folder / "Images" / "photo.jpg").exists()
    assert (folder / "Images" / "photo_1.jpg").exists()


def test_dry_run_in_place_does_not_move_or_create(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    result = organize_files(folder, to_system=False, dry_run=True)

    assert result.dry_run
    assert [move.destination for move in result.moved] == [folder / "Images" / "photo.jpg"]
    assert [move.source for move in result.moved] == [photo]
    assert photo.exists()
    assert not (folder / "Images").exists()


def test_recursive_skips_category_folders_in_place(tmp_path):
    folder = tmp_path / "Downloads"
    (folder / "Images").mkdir(parents=True)
    (folder / "nested").mkdir()

    existing = folder / "Images" / "photo.jpg"
    existing.touch()
    (folder / "nested" / "song.mp3").touch()

    result = organize_files(folder, to_system=False, recursive=True)

    assert existing.exists()
    assert (folder / "Audio" / "song.mp3").exists()
    assert len(result.moved) == 1


def test_excluded_files_are_ignored(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    hidden = folder / ".DS_Store"
    thumbs = folder / "Thumbs.db"
    temp = folder / "~$document.docx"
    lock = folder / "data.log"

    for file in (hidden, thumbs, temp, lock):
        file.touch()

    result = organize_files(folder, to_system=False, excludes=["*.log"])

    assert result.moved == []
    for file in (hidden, thumbs, temp, lock):
        assert file.exists()


def test_move_error_is_reported_and_batch_continues(tmp_path, monkeypatch):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    photo = folder / "photo.jpg"
    song = folder / "song.mp3"
    photo.touch()
    song.touch()

    real_move = shutil.move

    def failing_move(source, destination):
        if str(source).endswith(".jpg"):
            raise OSError("file is locked")
        return real_move(source, destination)

    monkeypatch.setattr("app.organizer.shutil.move", failing_move)

    result = organize_files(folder, to_system=False)

    assert not result.ok
    assert len(result.moved) == 1
    assert len(result.errors) == 1
    assert result.errors[0][0] == photo
    assert photo.exists()
    assert (folder / "Audio" / "song.mp3").exists()


def test_destination_error_is_reported_and_batch_continues(tmp_path, monkeypatch):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "photo.jpg").touch()
    (folder / "song.mp3").touch()

    real_get_destination = get_destination

    def failing_get_destination(folder_path, category, **kwargs):
        if category == "Images":
            raise OSError("access denied")
        return real_get_destination(folder_path, category, **kwargs)

    monkeypatch.setattr("app.organizer.get_destination", failing_get_destination)

    result = organize_files(folder, to_system=False)

    assert not result.ok
    assert len(result.errors) == 1
    assert len(result.moved) == 1
    assert (folder / "Audio" / "song.mp3").exists()


def test_unknown_file_category():
    assert get_category(Path("file.xyz")) == "Other"


def test_organize_to_system_default(tmp_path, system_folders):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    (folder / "photo.jpg").touch()
    (folder / "song.mp3").touch()
    (folder / "video.mp4").touch()
    (folder / "document.pdf").touch()
    (folder / "archive.zip").touch()
    (folder / "unknown.xyz").touch()

    result = organize_files(folder)

    assert (system_folders["Images"] / "photo.jpg").exists()
    assert (system_folders["Audio"] / "song.mp3").exists()
    assert (system_folders["Videos"] / "video.mp4").exists()
    assert (system_folders["Documents"] / "document.pdf").exists()
    assert (system_folders["Documents"] / "archive.zip").exists()
    assert (system_folders["Documents"] / "unknown.xyz").exists()
    assert not any(folder.iterdir())
    assert len(result.moved) == 6
    assert result.ok


def test_dry_run_to_system_does_not_move(tmp_path, system_folders):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    result = organize_files(folder, dry_run=True)

    assert result.dry_run
    assert [move.destination for move in result.moved] == [system_folders["Images"] / "photo.jpg"]
    assert photo.exists()
    assert not (system_folders["Images"] / "photo.jpg").exists()


def test_system_collision_uses_unique_name(tmp_path, system_folders):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "photo.jpg").touch()
    (system_folders["Images"] / "photo.jpg").touch()

    organize_files(folder)

    assert (system_folders["Images"] / "photo_1.jpg").exists()


def test_top_level_only_by_default(tmp_path, system_folders):
    folder = tmp_path / "Downloads"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    (nested / "photo.jpg").touch()

    result = organize_files(folder)

    assert result.moved == []
    assert (nested / "photo.jpg").exists()

def test_compound_suffix_categorized_as_archive():
    assert get_category(Path("backup.tar.gz")) == "Archives"
    assert get_category(Path("backup.tar.bz2")) == "Archives"
    assert get_category(Path("backup.tar.xz")) == "Archives"
    assert get_category(Path("backup.tar.zst")) == "Archives"
    assert get_category(Path("data.gz")) == "Archives"
    assert get_category(Path("data.zst")) == "Archives"


def test_recursive_skips_lowercase_category_folder(tmp_path):
    folder = tmp_path / "Downloads"
    (folder / "images").mkdir(parents=True)
    existing = folder / "images" / "photo.jpg"
    existing.touch()

    result = organize_files(folder, to_system=False, recursive=True)

    assert existing.exists()
    assert result.moved == []


def test_recursive_system_mode_processes_category_named_subfolder(tmp_path, system_folders):
    folder = tmp_path / "Downloads"
    nested = folder / "Documents"
    nested.mkdir(parents=True)
    (nested / "photo.jpg").touch()

    result = organize_files(folder, recursive=True)

    assert (system_folders["Images"] / "photo.jpg").exists()
    assert len(result.moved) == 1
    assert result.ok


def test_collect_files_is_sorted(tmp_path):
    folder = tmp_path / "Downloads"
    (folder / "b").mkdir(parents=True)
    (folder / "a").mkdir()
    (folder / "b" / "z.txt").touch()
    (folder / "a" / "y.txt").touch()
    (folder / "a" / "x.txt").touch()

    files = _collect_files(folder, recursive=True, excludes=(), skip_category_dirs=True)
    names = [path.relative_to(folder).as_posix() for path in files]

    assert names == ["a/x.txt", "a/y.txt", "b/z.txt"]


def test_system_folder_same_as_source_does_not_rename(tmp_path, system_folders):
    folder = system_folders["Images"]
    photo = folder / "photo.jpg"
    photo.touch()

    result = organize_files(folder)

    assert photo.exists()
    assert not (folder / "photo_1.jpg").exists()
    assert result.moved == []
    assert [item.path for item in result.skipped] == [photo]
    assert result.skipped[0].reason


def test_system_folder_same_as_source_dry_run_does_not_rename(tmp_path, system_folders):
    folder = system_folders["Images"]
    photo = folder / "photo.jpg"
    photo.touch()

    result = organize_files(folder, dry_run=True)

    assert result.moved == []
    assert [item.path for item in result.skipped] == [photo]


def test_unexpected_error_is_reported_and_batch_continues(tmp_path, monkeypatch):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    (folder / "photo.jpg").touch()
    (folder / "song.mp3").touch()

    real_move = shutil.move

    def failing_move(source, destination):
        if str(source).endswith(".jpg"):
            raise ValueError("boom")
        return real_move(source, destination)

    monkeypatch.setattr("app.organizer.shutil.move", failing_move)

    result = organize_files(folder, to_system=False)

    assert not result.ok
    assert len(result.errors) == 1
    assert len(result.moved) == 1
    assert (folder / "Audio" / "song.mp3").exists()


def test_moved_includes_source_and_destination(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    result = organize_files(folder, to_system=False)

    assert result.moved[0].source == photo
    assert result.moved[0].destination == folder / "Images" / "photo.jpg"


def test_execute_plan_uses_dry_run_result(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    plan = organize_files(folder, to_system=False, dry_run=True)
    assert photo.exists()
    assert not (folder / "Images").exists()

    result = execute_plan(plan)

    assert not result.dry_run
    assert (folder / "Images" / "photo.jpg").exists()
    assert [move.source for move in result.moved] == [photo]


def test_execute_plan_reports_missing_source(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    plan = organize_files(folder, to_system=False, dry_run=True)
    photo.unlink()

    result = execute_plan(plan)

    assert not result.ok
    assert result.moved == []
    assert result.errors[0][0] == photo


def test_execute_plan_avoids_overwriting_new_file(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()
    photo = folder / "photo.jpg"
    photo.touch()

    plan = organize_files(folder, to_system=False, dry_run=True)

    images = folder / "Images"
    images.mkdir()
    (images / "photo.jpg").write_text("new", encoding="utf-8")

    result = execute_plan(plan)

    assert (images / "photo.jpg").read_text(encoding="utf-8") == "new"
    assert (images / "photo_1.jpg").exists()
    assert result.moved[0].destination == images / "photo_1.jpg"
