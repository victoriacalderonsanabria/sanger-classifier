# Arma ClasificadorSanger.exe (Windows).
#
# Reemplaza a construir_exe.bat. Se corre desde una copia completa del
# repositorio, en PowerShell:
#
#     powershell -ExecutionPolicy Bypass -File scripts\construir_exe.ps1
#
# El .exe queda en C:\Sanger\dist\ClasificadorSanger.exe y es lo único que hay
# que compartir: en la máquina de destino no hace falta ni Python ni Biopython.
param(
    [string]$Destino = "C:\Sanger",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$raiz = (Resolve-Path "$PSScriptRoot\..").Path

# PyInstaller crea miles de archivos temporales y OneDrive los pelea mientras
# los sincroniza: por eso se construye afuera.
if ($raiz -like "*OneDrive*") {
    Write-Host "El repositorio está dentro de OneDrive." -ForegroundColor Red
    Write-Host "Copialo a una carpeta fuera de OneDrive (por ejemplo C:\Sanger\repo) y construí desde ahí."
    exit 1
}

if (-not $Python) {
    $Python = if (Test-Path "$raiz\.venv\Scripts\python.exe") { "$raiz\.venv\Scripts\python.exe" } else { "python" }
}
Write-Host "Python: $Python"
Write-Host "Repositorio: $raiz"
Write-Host "Salida: $Destino`n"

Write-Host "Instalando dependencias (Biopython, PySide6, PyInstaller)..." -ForegroundColor Cyan
& $Python -m pip install --upgrade pip
& $Python -m pip install -e "$raiz[ui]" pyinstaller
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudieron instalar las dependencias." -ForegroundColor Red
    exit 1
}

Write-Host "`nConstruyendo el ejecutable (tarda 1-3 minutos)..." -ForegroundColor Cyan
Set-Location $raiz
& $Python -m PyInstaller "$raiz\scripts\sanger.spec" --noconfirm --clean `
    --distpath "$Destino\dist" --workpath "$Destino\build"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falló la construcción. Revisar los mensajes de arriba." -ForegroundColor Red
    exit 1
}

$exe = "$Destino\dist\ClasificadorSanger.exe"
$mb = "{0:N1}" -f ((Get-Item $exe).Length / 1MB)
Write-Host "`nListo: $exe ($mb MB)" -ForegroundColor Green
Write-Host "Ese archivo es lo único que hay que compartir."
