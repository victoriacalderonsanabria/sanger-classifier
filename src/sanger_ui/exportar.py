"""
Diálogo de exportación: a dónde y qué guardar.

La ventana no escribe nada mientras corre; los informes se generan acá, a
pedido, y con el mismo código que usa la línea de comandos
(`sanger.io.informes.escribir_informes`). Un exportador aparte terminaría
produciendo archivos distintos.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from sanger.io.informes import ARCHIVO_FILTRADO, ARCHIVOS

# Qué es cada archivo, en criollo, para que no haya que acordarse de los números.
DESCRIPCIONES = {
    "04": "resultados por muestra (lo principal)",
    "01": "control de calidad de cada cromatograma",
    "02": "secuencias confiables (FASTA)",
    "03": "secuencias dudosas (FASTA)",
    "05": "hits completos de BLAST (JSON)",
    "00": "resumen de la corrida",
}
ORDEN = ("04", "01", "02", "03", "05", "00")


class DialogoExportar(QDialog):
    """Pregunta dónde guardar y qué guardar. Todo marcado por defecto."""

    def __init__(self, parent=None, destino_sugerido: str = "", visibles: int = 0, total: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Exportar resultados")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        fila = QHBoxLayout()
        self.v_destino = QLineEdit(destino_sugerido)
        self.v_destino.setPlaceholderText("carpeta donde guardar los archivos")
        boton = QPushButton("Elegir…")
        boton.clicked.connect(self._elegir)
        fila.addWidget(QLabel("Guardar en:"))
        fila.addWidget(self.v_destino, 1)
        fila.addWidget(boton)
        layout.addLayout(fila)

        grupo = QGroupBox("Qué exportar")
        columna = QVBoxLayout(grupo)
        self.casillas = {}
        for cual in ORDEN:
            casilla = QCheckBox(f"{ARCHIVOS[cual]} — {DESCRIPCIONES[cual]}")
            casilla.setChecked(True)
            self.casillas[cual] = casilla
            columna.addWidget(casilla)
        layout.addWidget(grupo)

        # Solo afecta a 04_resultados: el QC por lectura, los FASTA y el resumen
        # son de la corrida entera y filtrarlos cambiaría lo que significan.
        self.solo_visibles = QCheckBox(
            f"Exportar solo las {visibles} filas visibles de la tabla (de {total}), "
            "en el orden en que están"
        )
        self.solo_visibles.setEnabled(bool(total) and visibles != total)
        if not self.solo_visibles.isEnabled():
            self.solo_visibles.setToolTip("No hay ningún filtro puesto: se ven todas las muestras.")
        ayuda = QLabel(
            f"Se guarda como <b>{ARCHIVO_FILTRADO}</b>, con otro nombre porque no es "
            "la corrida completa. Los demás archivos salen enteros."
        )
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet("color: gray;")
        layout.addWidget(self.solo_visibles)
        layout.addWidget(ayuda)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def _elegir(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(
            self, "Carpeta donde guardar los resultados", self.v_destino.text()
        )
        if carpeta:
            self.v_destino.setText(carpeta)

    def destino(self) -> Path | None:
        texto = self.v_destino.text().strip()
        return Path(texto) if texto else None

    def elegidos(self) -> list[str]:
        """Los informes marcados, en el orden en que se escriben."""
        return [cual for cual in ARCHIVOS if self.casillas[cual].isChecked()]

    def filtrar_resultados(self) -> bool:
        """Si 04 sale con solo las filas visibles de la tabla."""
        return self.solo_visibles.isEnabled() and self.solo_visibles.isChecked()
