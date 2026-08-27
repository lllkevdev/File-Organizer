import pytest

from pathlib import Path

from app.organizer import organize_files, get_category, get_destination, get_unique_destination, move_file

def test_valid_folder():
    files = organize_files(".")

    assert isinstance(files, list)

def test_invalid_folder():
    with pytest.raises(FileNotFoundError):
        organize_files("this_folder_does_not_exist")

def test_file_categories():
    assert get_category(Path("photo.jpg")) == "Images"
    assert get_category(Path("song.mp3")) == "Audio"
    assert get_category(Path("video.mp4")) == "Videos"
    assert get_category(Path("document.pdf")) == "Documents"
    assert get_category(Path("archive.zip")) == "Archives"
    assert get_category(Path("unknown.xyz")) == "Other"

def test_uppercase_extension():
    assert get_category(Path("photo.JPG")) == "Images"

def test_destination(tmp_path):
    destination = get_destination(tmp_path, "Images")

    assert destination.exists()
    assert destination.is_dir()
    assert destination.name == "Images"

def test_unique_destination(tmp_path):
    destination = tmp_path / "Images" / "photo.jpg"
    destination.parent.mkdir()

    result = get_unique_destination(destination)

    assert result == destination

def test_duplicate_destination(tmp_path):
    destination = tmp_path / " Images" / "photo.jpg"
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

def test_move_file(tmp_path):
    source = tmp_path / "photo.jpg"
    destination = tmp_path / "Images" / "photo.jpg"

    destination.parent.mkdir()

    source.touch()

    result = move_file(source, destination)
    
    assert not source.exists()
    assert destination.exists()
    assert result == destination

def test_organize_files(tmp_path):
    folder = tmp_path / "Dowloads"
    folder.mkdir()

    photo = folder / "photo.jpg"
    document = folder / "document.pdf"
    song = folder / "song.mp3"

    photo.touch()
    document.touch()
    song.touch()

    result = organize_files(folder)

    assert (folder / "Images" / "photo.jpg").exists()
    assert (folder / "Documents" / "document.pdf"). exists()
    assert (folder / "Audio" / "song.mp3").exists()

    assert not photo.exists()
    assert not document.exists()
    assert not song.exists()

    assert len(result) == 3

def test_organize_duplicate_file(tmp_path):
    folder = tmp_path / "Downloads"
    folder.mkdir()

    photo = folder / "photo.jpg"
    photo.touch()

    images = folder / "Images"
    images.mkdir()

    photo_duplicate = images / "photo.jpg"
    photo_duplicate.touch()

    organize_files(folder)

    assert (folder / "Images" / "photo_1.jpg").exists()

def test_unknown_file_category():
    assert get_category(Path("file.xyz")) == "Other"