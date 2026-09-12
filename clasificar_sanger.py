#!/usr/bin/env python3
"""
clasificar_sanger.py: punto de entrada histórico.

Desde la fase 1 el programa vive en el paquete src/sanger/. Este archivo se
conserva para que sigan funcionando exactamente igual:

  - python clasificar_sanger.py -i carpeta_ab1 -o resultados ...
  - sanger_gui.py (la ventana actual), que lo importa y llama a main().

Se elimina cuando la ventana nueva de la fase 3 reemplace a sanger_gui.py.
"""

import sys
from pathlib import Path

# Así funciona sin instalar el paquete: basta con tener la carpeta del repo.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from sanger.cli import main  # noqa: E402

__all__ = ["main"]

if __name__ == "__main__":
    main()
