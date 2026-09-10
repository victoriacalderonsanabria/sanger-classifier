@echo off
REM ============================================================
REM  Construye ClasificadorSanger.exe a partir de sanger_gui.py
REM  Requiere: Python 3 instalado en Windows (con "Add to PATH").
REM  Se corre UNA vez, en la máquina que arma el .exe.
REM  Los compañeros solo necesitan el .exe resultante.
REM ============================================================
cd /d "%~dp0"

echo Instalando/actualizando dependencias...
python -m pip install --upgrade pip >nul
python -m pip install biopython pyinstaller
if errorlevel 1 (
    echo.
    echo ERROR: no se pudieron instalar las dependencias. ¿Python esta instalado y en el PATH?
    pause
    exit /b 1
)

REM Si el logo esta en la carpeta, se usa como icono del .exe y de la ventana.
set ICONO=
if exist logo_mosquito.ico set ICONO=--icon logo_mosquito.ico --add-data "logo_mosquito.ico;."
if not exist logo_mosquito.ico echo AVISO: no encuentro logo_mosquito.ico, el .exe saldra con el icono generico.

echo.
echo Construyendo el ejecutable (tarda 1-3 minutos)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name ClasificadorSanger ^
    %ICONO% ^
    --collect-submodules Bio ^
    sanger_gui.py
if errorlevel 1 (
    echo.
    echo ERROR: fallo la construccion. Revisar los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo Listo. El ejecutable esta en:  %~dp0dist\ClasificadorSanger.exe
echo Ese archivo solo es lo que hay que compartir.
pause
