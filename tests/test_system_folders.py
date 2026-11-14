import app.system_folders as system_folders


def test_category_mapping():
    assert system_folders.CATEGORY_TO_FOLDER == {
        "Images": "Pictures",
        "Videos": "Videos",
        "Documents": "Documents",
        "Audio": "Music",
    }


def test_known_folder_keys():
    assert set(system_folders.KNOWN_FOLDERS) == {
        "Pictures",
        "Videos",
        "Documents",
        "Music",
    }


def test_get_system_destination_uses_mapping(tmp_path, monkeypatch):
    requested: list[str] = []

    def fake_get_known_folder_path(folder_key):
        requested.append(folder_key)
        return tmp_path / folder_key

    monkeypatch.setattr(system_folders, "_get_known_folder_path", fake_get_known_folder_path)

    assert system_folders.get_system_destination("Images") == tmp_path / "Pictures"
    assert system_folders.get_system_destination("Audio") == tmp_path / "Music"
    assert system_folders.get_system_destination("Videos") == tmp_path / "Videos"
    assert system_folders.get_system_destination("Documents") == tmp_path / "Documents"


def test_unmapped_categories_go_to_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(
        system_folders,
        "_get_known_folder_path",
        lambda folder_key: tmp_path / folder_key,
    )

    assert system_folders.get_system_destination("Archives") == tmp_path / "Documents"
    assert system_folders.get_system_destination("Other") == tmp_path / "Documents"
    assert system_folders.get_system_destination("SomethingElse") == tmp_path / "Documents"
