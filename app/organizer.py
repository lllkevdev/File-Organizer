from pathlib import Path

from app.config import CATEGORIES

def organize_files(folder: str | Path) -> list[Path]:
    """Validates folders, finds and classifies files, creates a destination, resolves duplicates, and moves them."""
    folder = Path(folder)

    if not folder.exists():
        raise FileNotFoundError("The selected folder does not exist.")

    if not folder.is_dir():
        raise NotADirectoryError("The selected path is not a directory.")

    files = []

    for item in folder.iterdir():
        if item.is_file():
            files.append(item)

    organized_files = []

    for file in files:
        category = get_category(file)
        destination = get_destination(folder, category)
        destination = destination / file.name
        destination = get_unique_destination(destination)
        result = move_file(file, destination)
        organized_files.append(result)

    return organized_files

def get_category(file) -> str:
    """Return the category associated with a file extension."""


    extension = file.suffix.lower()

    for category, extensions in CATEGORIES.items():
        if extension in extensions:
            return category
        
    return "Other"

def get_destination(folder: str | Path, category: str) -> Path:
    """Create and return the destination folder for a category."""

    destination = Path(folder) / category

    destination.mkdir(parents=True, exist_ok=True)

    return destination

def get_unique_destination(destination: Path) -> Path:
    """Return a unique destination path if the file already exists."""

    counter = 1

    original_name = destination.stem
    extension = destination.suffix
    parent = destination.parent 

    while destination.exists():
        destination = parent / f"{original_name}_{counter}{extension}"
        counter += 1

    return destination

def move_file(file: str | Path, destination: str | Path) -> Path:
    """Move the files to the specifed folder."""
    destination = Path(destination)
    file = Path(file)

    file.rename(destination)

    return destination