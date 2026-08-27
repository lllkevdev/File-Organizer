# File Organizer

A Python utility that automatically organizes files into categorized folders based on their file extensions.

## Description

File Organizer is a Python application designed to simplify file management by sorting files into categorized folders.

The application detects each file's extension, determines its category, creates the corresponding destination folder, safely handles duplicate filenames, and moves the files automatically.

## Project Status

**Version:** `1.0.0`
**Status:** Stable
**Tests:** `12/12 passing`
**License:** MIT

The current version provides the core file organization functionality with automated testing and modular project structure.

## Features

* Automatically organize files by extension
* Categorize images, audio, videos, documents, and archives
* Move unknown file types to an `Other` category
* Prevent filename conflicts by generating unique filenames
* Validate input paths before processing
* Modular code structure
* Automated testing with pytest

## Technologies

* Python 3.12
* pytest
* pathlib

## Project Structure

```text
File Organizer/
├── app/
│   ├── __init__.py
│   ├── config.py
│   └── organizer.py
├── tests/
│   ├── __init__.py
│   └── test_organizer.py
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

### Main Components

* `app/organizer.py` — Core file organization logic.
* `app/config.py` — File extension categories.
* `tests/` — Automated tests for the application.

## Architecture

The project follows a modular architecture that separates configuration, application logic, and testing.

```text
                 File Organizer
                       │
          ┌────────────┴────────────┐
          │                         │
       app/                       tests/
          │                         │
    ┌─────┴─────┐             ┌─────┴─────┐
    │           │             │           │
config.py  organizer.py   Unit Tests  Workflow Tests
    │           │
    │      ┌────┴─────┐
    │      │          │
    └──► Categories  File Operations
```

The main workflow is handled by `organizer.py`, while `config.py` contains the supported file extensions and their categories.

## Installation

### Requirements

* Python 3.12 or compatible version
* pip
* Git

### 1. Clone the repository

```bash
git clone https://github.com/lllkevdev/File-Organizer.git
cd File-Organizer
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

#### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
source .venv/bin/activate
```

### 4. Install development dependencies

```bash
pip install -r requirements-dev.txt
```

## Usage

The organizer can be used by calling the `organize_files()` function with the path of the folder to organize.

```python
from app.organizer import organize_files

result = organize_files("path/to/folder")

for file in result:
    print(file)
```

### Example

Before:

```text
Downloads/
├── photo.jpg
├── song.mp3
└── document.pdf
```

After:

```text
Downloads/
├── Images/
│   └── photo.jpg
├── Audio/
│   └── song.mp3
└── Documents/
    └── document.pdf
```

## Testing

The project uses pytest for automated testing.

Run the test suite with:

```bash
pytest
```

### Test Coverage

The test suite currently contains **12 automated tests**, covering:

* Input path validation
* File categorization
* Destination folder creation
* Duplicate filename handling
* File movement
* Complete file organization workflow
* Unknown file types

Current test result:

```text
12 passed
```

The tests use temporary directories and files to avoid modifying real user data during execution.

## How It Works

The application follows a simple workflow:

1. Validate the selected folder.
2. Find the files contained in the folder.
3. Determine the category of each file based on its extension.
4. Create the corresponding destination folder.
5. Generate a unique filename if a file with the same name already exists.
6. Move the file to its destination.
7. Return the paths of the organized files.

## Roadmap

### v1.0.0 — Stable Release ✅

* [x] Core file organization
* [x] File categorization
* [x] Duplicate filename handling
* [x] Input validation
* [x] Automated testing
* [x] Documentation
* [x] Git/GitHub integration
* [x] MIT License

### v1.1.0 — CLI & Reliability

* [ ] Add command-line interface
* [ ] Add logging
* [ ] Add dry-run mode
* [ ] Improve error handling
* [ ] Add more test cases

### v1.2.0 — Customization

* [ ] Support custom categories
* [ ] Allow users to configure file extensions
* [ ] Add configurable destination folders
* [ ] Add exclusion rules

### v2.0.0 — Graphical Interface

* [ ] Add graphical user interface
* [ ] Add folder selection
* [ ] Add progress indicator
* [ ] Add operation cancellation
* [ ] Display organization statistics

### Future

* [ ] Recursive organization of subfolders
* [ ] Undo file movements
* [ ] Package as a standalone Windows executable
* [ ] Improve configuration management

## License

This project is licensed under the MIT License. See the `LICENSE` file for more information.
