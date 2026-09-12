"""
La tabla de resultados: una fila por muestra, coloreada por grupo.

Es lo que más cambia el día a día: hasta ahora, para ver cómo salió una corrida
había que abrir el CSV en Excel.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from sanger.modelos import Grupo, Muestra

NCBI_NUCCORE = "https://www.ncbi.nlm.nih.gov/nuccore/"

# Qt pide estos métodos con un índice "padre"; en una tabla plana no hay padre.
SIN_PADRE = QModelIndex()

# Colores suaves: tienen que distinguirse de un vistazo sin tapar el texto.
COLOR_GRUPO = {
    Grupo.CONFIABLE: QColor(226, 245, 229),
    Grupo.DUDOSA: QColor(255, 243, 214),
    Grupo.RECHAZADA: QColor(238, 238, 238),
}


@dataclass(frozen=True)
class Columna:
    titulo: str
    valor: object  # Callable[[Muestra], object]
    ayuda: str = ""


def _hit(m: Muestra, campo: str):
    return getattr(m.hits[0], campo) if m.hits else ""


COLUMNAS = (
    Columna("Muestra", lambda m: m.nombre),
    Columna("Grupo", lambda m: m.grupo.value, "CONFIABLE / DUDOSA / RECHAZADA"),
    Columna("Origen", lambda m: m.origen, "consenso F+R, o cuál lectura se usó"),
    Columna("Largo", lambda m: m.largo, "pares de bases de la secuencia final"),
    Columna("Q media", lambda m: m.q_media),
    Columna("% Q20", lambda m: m.pct_q20, "porcentaje de bases con Q ≥ 20"),
    Columna("Conflictos", lambda m: m.conflictos, "discrepancias F/R con buena calidad"),
    Columna("Especie", lambda m: _hit(m, "especie")),
    Columna("Identidad", lambda m: _hit(m, "identidad"), "% de identidad del mejor hit"),
    Columna("Cobertura", lambda m: _hit(m, "cobertura"), "% de la secuencia que cubre el hit"),
    Columna("Accession", lambda m: _hit(m, "accession"), "doble clic: abre el registro en NCBI"),
    Columna("Interpretación", lambda m: m.interpretacion or ""),
    Columna("Motivo", lambda m: m.motivo, "por qué no llegó a CONFIABLE"),
    Columna("vs confiables", lambda m: m.vs_confiables or "", "segunda opinión, sin BLAST"),
)
COLUMNA_ACCESSION = next(i for i, c in enumerate(COLUMNAS) if c.titulo == "Accession")


class ModeloMuestras(QAbstractTableModel):
    def __init__(self, muestras: Sequence[Muestra] = (), parent=None):
        super().__init__(parent)
        self.muestras = list(muestras)

    def poner(self, muestras: Sequence[Muestra]) -> None:
        self.beginResetModel()
        self.muestras = list(muestras)
        self.endResetModel()

    def rowCount(self, parent=SIN_PADRE) -> int:
        return 0 if parent.isValid() else len(self.muestras)

    def columnCount(self, parent=SIN_PADRE) -> int:
        return 0 if parent.isValid() else len(COLUMNAS)

    def muestra_en(self, fila: int) -> Muestra:
        return self.muestras[fila]

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        m = self.muestras[index.row()]
        valor = COLUMNAS[index.column()].valor(m)
        if role == Qt.ItemDataRole.DisplayRole:
            return "" if valor is None else str(valor)
        if role == Qt.ItemDataRole.UserRole:
            # para ordenar: los números como números, no como texto
            return valor if valor != "" else None
        if role == Qt.ItemDataRole.BackgroundRole:
            return COLOR_GRUPO.get(m.grupo)
        if role == Qt.ItemDataRole.ToolTipRole and m.grupo == Grupo.DUDOSA:
            return m.motivo
        return None

    def headerData(self, seccion: int, orientacion, role=Qt.ItemDataRole.DisplayRole):
        if orientacion != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[seccion].titulo
        if role == Qt.ItemDataRole.ToolTipRole:
            return COLUMNAS[seccion].ayuda or None
        return None


def url_ncbi(accession: str) -> str:
    return NCBI_NUCCORE + accession
