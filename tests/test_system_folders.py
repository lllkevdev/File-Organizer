import sys

import pytest

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


def test_fallback_path_uses_existing_home_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("OneDrive", raising=False)
    (tmp_path / "Pictures").mkdir()

    assert system_folders._fallback_path("Pictures") == tmp_path / "Pictures"


def test_fallback_path_prefers_onedrive(tmp_path, monkeypatch):
    home = tmp_path / "home"
    onedrive = tmp_path / "onedrive"
    home.mkdir()
    (onedrive / "Pictures").mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OneDrive", str(onedrive))

    assert system_folders._fallback_path("Pictures") == onedrive / "Pictures"


def test_fallback_path_defaults_under_home(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("OneDrive", raising=False)

    assert system_folders._fallback_path("Music") == tmp_path / "Music"


def test_get_known_folder_path_non_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(system_folders.sys, "platform", "linux")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("OneDrive", raising=False)
    (tmp_path / "Videos").mkdir()

    assert system_folders._get_known_folder_path("Videos") == tmp_path / "Videos"


def test_get_known_folder_path_falls_back_on_error(monkeypatch):
    def boom():
        raise OSError("boom")

    monkeypatch.setattr(system_folders.sys, "platform", "win32")
    monkeypatch.setattr(system_folders, "_windows_shell_functions", boom)

    assert system_folders._get_known_folder_path("Documents").name == "Documents"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_windows_shell_functions_configure_signatures():
    shell32, ole32 = system_folders._windows_shell_functions()

    assert shell32.SHGetKnownFolderPath.restype is not None
    assert ole32.CoTaskMemFree.argtypes is not None
