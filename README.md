# File Organizer

Mueve los archivos sueltos de una carpeta indicada por el usuario a las carpetas
predeterminadas de Windows (Imágenes, Vídeos, Documentos y Música), o a
subcarpetas dentro del origen (modo in-place).

> Solo Windows. Solo procesa el **primer nivel** de la carpeta indicada por defecto.

## Mapeo de categorías

| Categoría | Extensiones | Destino por defecto |
| --- | --- | --- |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` | Imágenes (`Pictures`) |
| Audio | `.mp3`, `.wav`, `.flac` | Música (`Music`) |
| Videos | `.mp4`, `.avi`, `.mkv`, `.mov` | Vídeos (`Videos`) |
| Documents | `.pdf`, `.docx`, `.txt`, `.xlsx`, `.pptx` | Documentos (`Documents`) |
| Archives | `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.bz2`, `.xz`, `.zst` (también `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tar.zst`) | Documentos |
| Other | cualquier otra extensión | Documentos |

Las carpetas del sistema se resuelven con `SHGetKnownFolderPath`, respetando las
rutas configuradas por cada usuario (incluidos perfiles con carpetas redirigidas).

## Uso (CLI)

```bash
# Mover a las carpetas del sistema con confirmación previa (predeterminado)
file-organizer "C:\Users\kev\Downloads"

# Ver qué se movería sin tocar nada
file-organizer "C:\Users\kev\Downloads" --dry-run

# Organizar dentro de la propia carpeta (subcarpetas por categoría)
file-organizer "C:\Users\kev\Downloads" --in-place

# Incluir subcarpetas, ignorar patrones y no pedir confirmación
file-organizer "C:\Users\kev\Downloads" --recursive --exclude "*.bak" --yes

# Deshacer el último run (lee el journal de la última ejecución)
file-organizer --undo

# Revisar qué se restauraría sin mover nada
file-organizer --undo --dry-run
```

Opciones:

- `--in-place`: crea subcarpetas por categoría dentro de la carpeta origen.
- `--dry-run`: muestra los movimientos planeados sin mover archivos.
- `--recursive`: procesa también archivos dentro de subcarpetas (omite las carpetas de categoría del primer nivel).
- `--exclude PATTERN`: patrón de nombre a ignorar; se puede repetir.
- `-y`, `--yes`: no pide confirmación.
- `--undo`: restaura los archivos movidos en el último run registrado en el journal.
- `--journal PATH`: ruta del journal a leer/escribir (por defecto en `%LOCALAPPDATA%\FileOrganizer\last-run.json`).
- `-v`, `--verbose`: logging detallado.

Cada ejecución que mueve archivos escribe un journal con los pares origen→destino.
`--undo` los restaura en orden inverso, sin sobrescribir archivos existentes.

Por defecto se ignoran archivos y carpetas ocultos (`.DS_Store`, `.git/`, etc.),
`Thumbs.db`, `desktop.ini`, `~$*` y `*.tmp`.

Los nombres duplicados se resuelven añadiendo un sufijo numérico
(`foto.jpg` → `foto_1.jpg`). Las carpetas no se mueven.

## Interfaz gráfica (PySide6)

```bash
pip install -e ".[gui]"
file-organizer-gui
# o
python -m app.gui
```

La ventana permite elegir la carpeta, alternar entre carpetas del sistema e
in-place, activar la vista previa (dry-run), excluir patrones y ver el resultado
o los errores. Las operaciones se ejecutan en segundo plano.

Botones adicionales:
- **Deshacer último run**: restaura los archivos del último journal, con
  confirmación previa e informe de omitidos/errores.
- **Cancelar**: detiene la operación en curso entre archivo y archivo (no
  interrumpe una copia ya iniciada); los movimientos hechos quedan en el
  journal y se pueden deshacer.
- **Abrir carpeta de logs** y **Abrir journal**: abren el explorador en la
  carpeta de logs o el archivo del último run.

## Instalador para Windows

Requisitos: Windows 10/11, Python 3.10+ y
[Inno Setup 6](https://jrsoftware.org/isinfo.php) para generar el instalador
(`winget install --id JRSoftware.InnoSetup -e`).

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# Compila GUI + CLI y genera el instalador
powershell -ExecutionPolicy Bypass -File installer\build.ps1

# Solo los ejecutables (sin instalador)
powershell -ExecutionPolicy Bypass -File installer\build.ps1 -SkipInstaller
```

También puedes hacer doble clic en `installer\build.bat`.

Salidas:

- `dist\FileOrganizer\FileOrganizer.exe`: GUI portable.
- `dist\file-organizer.exe`: CLI portable.
- `dist\installer\FileOrganizer-Setup-<versión>.exe`: instalador (si Inno Setup está disponible). La versión se toma de `app.__version__`.

El instalador agrega la app al menú Inicio, crea opcionalmente un acceso directo
en el escritorio e incluye la CLI en la carpeta de instalación.

## Uso como librería

```python
from app.organizer import organize_files

result = organize_files("C:/Users/kev/Downloads", dry_run=True)

for move in result.moved:
    print(move.source, "->", move.destination)
print(result.skipped)  # [SkippedFile(path, reason), ...]
print(result.errors)   # [(archivo, mensaje), ...]

# Modo in-place
result = organize_files("C:/Users/kev/Downloads", to_system=False)

# Ejecutar un plan de dry-run sin volver a escanear
from app.organizer import execute_plan

plan = organize_files("C:/Users/kev/Downloads", dry_run=True)
result = execute_plan(plan, journal_path="C:/tmp/journal.json")
```

## Desarrollo

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

pytest
pytest --cov=app --cov-report=term-missing
ruff check .
mypy app
```

La versión se define en `app/__init__.py` (`__version__`) y se propaga a
`pyproject.toml` (dinámica), la GUI, la CLI (`--version`) y el instalador.
La CI prueba Python 3.10–3.13 en Linux y Windows, exige cobertura mínima del
85% (excluyendo la GUI) y genera el build portable en Windows.

## Limitaciones

- Solo Windows para el destino en carpetas del sistema.
- Solo primer nivel por defecto; usa `--recursive` si lo necesitas.
- `--undo` solo revierte el último run (un journal); usa `--dry-run` para revisar antes.
- Las categorías están definidas en `app/config.py`.
