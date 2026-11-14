"""File extension categories and organizer defaults."""

CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    "Audio": [".mp3", ".wav", ".flac"],
    "Videos": [".mp4", ".avi", ".mkv", ".mov"],
    "Documents": [".pdf", ".docx", ".txt", ".xlsx", ".pptx"],
    "Archives": [
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".zst",
    ],
}

UNCATEGORIZED = "Other"

DEFAULT_EXCLUDES = (
    ".*",
    "Thumbs.db",
    "desktop.ini",
    "~$*",
    "*.tmp",
)

COMPOUND_SUFFIXES = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tar.zst",
)
