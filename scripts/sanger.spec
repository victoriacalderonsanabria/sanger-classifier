# -*- mode: python ; coding: utf-8 -*-
"""
Receta de PyInstaller para armar ClasificadorSanger.exe.

Reemplaza al construir_exe.bat, que tenía las opciones sueltas en la línea de
comandos: acá quedan versionadas y se revisan como cualquier otro cambio.

Se usa desde scripts/construir_exe.ps1, o a mano:
    pyinstaller scripts/sanger.spec --noconfirm --clean
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

RAIZ = Path(SPECPATH).parent  # noqa: F821  (SPECPATH lo define PyInstaller)
SRC = RAIZ / "src"
RECURSOS = SRC / "sanger_ui" / "recursos"

a = Analysis(  # noqa: F821
    [str(SRC / "sanger_ui" / "app.py")],
    pathex=[str(SRC)],
    binaries=[],
    # el icono de la ventana viaja adentro del .exe
    datas=[(str(RECURSOS), "sanger_ui/recursos")],
    # Biopython carga varios módulos de forma dinámica: sin esto faltan
    hiddenimports=collect_submodules("Bio"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.testing", "PySide6.QtQml", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ClasificadorSanger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # es una ventana: sin consola negra atrás
    icon=str(RECURSOS / "logo_mosquito.ico"),
)
