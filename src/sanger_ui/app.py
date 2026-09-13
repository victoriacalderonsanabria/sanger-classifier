"""
Punto de entrada de la ventana.

    python -m sanger_ui        (desde el repositorio, con PySide6 instalado)
    ClasificadorSanger.exe     (lo que usa Victoria; ver INSTRUCCIONES_exe.md)
"""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from sanger_ui.ventana import Ventana, icono


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Clasificador de secuencias Sanger")
    app.setWindowIcon(icono())
    try:
        import Bio  # noqa: F401
    except ImportError:
        QMessageBox.critical(
            None,
            "Falta Biopython",
            "Este programa necesita Biopython.\n\nInstalalo con:  pip install biopython",
        )
        return 1
    ventana = Ventana()
    ventana.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
