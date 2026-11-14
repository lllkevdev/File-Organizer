[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "No se encontro .venv. Crea el entorno e instala dependencias: python -m venv .venv; pip install -e '.[dev]'"
}

& $python -c "import PySide6" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PySide6 no esta instalado. Ejecuta: pip install -e '.[gui]'"
}

& $python -m pip install --disable-pip-version-check -q pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo instalar PyInstaller."
}

if (-not $NoClean) {
    Remove-Item -LiteralPath "build", "dist" -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Compilando GUI (PyInstaller)..."
& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build installer\FileOrganizer.spec
if ($LASTEXITCODE -ne 0) {
    throw "Fallo la compilacion de la GUI."
}

Write-Host "Compilando CLI (PyInstaller)..."
& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build installer\file-organizer-cli.spec
if ($LASTEXITCODE -ne 0) {
    throw "Fallo la compilacion de la CLI."
}

$guiExe = Join-Path $root "dist\FileOrganizer\FileOrganizer.exe"
$cliExe = Join-Path $root "dist\file-organizer.exe"
if (-not (Test-Path -LiteralPath $guiExe) -or -not (Test-Path -LiteralPath $cliExe)) {
    throw "No se generaron los ejecutables esperados."
}

if ($SkipInstaller) {
    Write-Host "Listo. Version portable en dist\FileOrganizer"
    exit 0
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    $command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($command) {
        $iscc = $command.Source
    }
}
if (-not $iscc) {
    Write-Warning "Inno Setup 6 no esta instalado; se genero solo la version portable."
    Write-Warning "Instalalo con: winget install --id JRSoftware.InnoSetup -e"
    exit 0
}

Write-Host "Generando instalador con Inno Setup..."
& $iscc "installer\file-organizer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Fallo la creacion del instalador."
}

Write-Host "Listo. Instalador en dist\installer"
