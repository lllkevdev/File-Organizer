from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any
from uuid import UUID

KNOWN_FOLDERS = {
    "Pictures": UUID("{33E28130-4E1E-4676-835A-98395C3BC3BB}"),
    "Videos": UUID("{18989B1D-99B5-455B-841C-AB7C74E4DDFC}"),
    "Documents": UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"),
    "Music": UUID("{4BD8D571-6D19-48D3-BE97-422220080E43}"),
}

CATEGORY_TO_FOLDER = {
    "Images": "Pictures",
    "Videos": "Videos",
    "Documents": "Documents",
    "Audio": "Music",
}

FALLBACK_NAMES = {
    "Pictures": "Pictures",
    "Videos": "Videos",
    "Documents": "Documents",
    "Music": "Music",
}


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

    @classmethod
    def from_uuid(cls, value: UUID) -> _GUID:
        return cls.from_buffer_copy(value.bytes_le)


def _windows_shell_functions() -> tuple[Any, Any]:
    windll = getattr(ctypes, "windll")  # noqa: B009 - typeshed only exposes windll on win32
    shell32 = windll.shell32
    ole32 = windll.ole32

    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    return shell32, ole32


def _get_known_folder_path(folder_key: str) -> Path:
    if sys.platform != "win32":
        return _fallback_path(folder_key)

    try:
        shell32, ole32 = _windows_shell_functions()
        guid = _GUID.from_uuid(KNOWN_FOLDERS[folder_key])
        path_ptr = ctypes.c_wchar_p()
        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(guid),
            0,
            None,
            ctypes.byref(path_ptr),
        )
        if result != 0 or not path_ptr.value:
            raise OSError(result)
        try:
            return Path(path_ptr.value)
        finally:
            ole32.CoTaskMemFree(ctypes.cast(path_ptr, ctypes.c_void_p))
    except Exception:
        return _fallback_path(folder_key)


def _fallback_path(folder_key: str) -> Path:
    name = FALLBACK_NAMES[folder_key]
    home = Path(os.environ.get("USERPROFILE") or Path.home())

    candidates: list[Path] = []
    onedrive = os.environ.get("OneDrive")
    if onedrive:
        candidates.append(Path(onedrive) / name)
    candidates.append(home / name)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return home / name


def get_system_destination(category: str) -> Path:
    """Return the system destination folder for a category.

    Mapped categories go to their known Windows user folders. Unmapped categories
    (Archives, Other, etc.) are sent to Documents.
    """
    folder_key = CATEGORY_TO_FOLDER.get(category, "Documents")
    return _get_known_folder_path(folder_key)
