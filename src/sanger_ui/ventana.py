"""
Ventana principal: tres pestañas (Configuración, Progreso, Resultados).

La novedad frente a la ventana vieja es la tercera pestaña: la tabla de
resultados, ordenable y filtrable, coloreada por grupo, con doble clic sobre el
accession para abrir el registro en NCBI. Antes había que abrir el CSV en Excel
para saber cómo había salido la corrida.
"""

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sanger.config import PRESETS, Parametros, preset
from sanger.errores import Cancelado
from sanger.modelos import Grupo, Progreso, Resultado
from sanger_ui import preferencias
from sanger_ui.modelo_tabla import COLUMNA_ACCESSION, ModeloMuestras, url_ncbi
from sanger_ui.worker import Worker

RECURSOS = Path(__file__).resolve().parent / "recursos"

BASES = [
    "nt", "core_nt", "mito", "16S_ribosomal_RNA", "ITS_RefSeq_Fungi",
    "ITS_eukaryote_sequences", "18S_fungal_sequences", "28S_fungal_sequences",
]  # fmt: skip
TAXONES = [
    "(sin filtro)", "Vertebrata[Organism]", "Mammalia[Organism]", "Aves[Organism]",
    "Insecta[Organism]", "Bacteria[Organism]", "Fungi[Organism]", "Viridiplantae[Organism]",
]  # fmt: skip

ETAPAS = {
    "qc": "Leyendo cromatogramas y evaluando calidad",
    "clasificacion": "Clasificando muestras",
    "comparacion": "Comparando las dudosas con las confiables",
    "blast": "BLAST: la espera es la cola de NCBI, puede tardar varios minutos",
    "informes": "Escribiendo los informes",
}


def icono() -> QIcon:
    ico = RECURSOS / "logo_mosquito.ico"
    return QIcon(str(ico)) if ico.exists() else QIcon()


class FiltroMuestras(QSortFilterProxyModel):
    """Filtra por texto (en cualquier columna) y por grupo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grupo = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def poner_grupo(self, grupo: Grupo | None) -> None:
        self.grupo = grupo
        self.invalidate()

    def filterAcceptsRow(self, fila: int, padre) -> bool:
        if self.grupo is not None:
            muestra = self.sourceModel().muestra_en(fila)
            if muestra.grupo != self.grupo:
                return False
        return super().filterAcceptsRow(fila, padre)


class Ventana(QMainWindow):
    def __init__(self, prefs: dict | None = None):
        super().__init__()
        self.setWindowTitle("Clasificador de secuencias Sanger")
        self.setWindowIcon(icono())
        self.resize(1000, 700)
        self.worker: Worker | None = None
        self.resultado: Resultado | None = None

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_configuracion(), "Configuración")
        self.tabs.addTab(self._tab_progreso(), "Progreso")
        self.tabs.addTab(self._tab_resultados(), "Resultados")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.tabs)
        layout.addLayout(self._barra_botones())
        self.setCentralWidget(central)
        self._cargar_preferencias(prefs if prefs is not None else preferencias.cargar())
        self._actualizar_botones(corriendo=False)

    # ---------------- armado de la interfaz ----------------

    def _tab_configuracion(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        carpetas = QFormLayout()
        self.v_entrada, fila_entrada = self._campo_carpeta("Carpeta con los cromatogramas .ab1")
        self.v_salida, fila_salida = self._campo_carpeta("Carpeta donde guardar los resultados")
        self.v_entrada.textChanged.connect(self._proponer_salida)
        carpetas.addRow("Carpeta con los .ab1:", fila_entrada)
        carpetas.addRow("Carpeta de resultados:", fila_salida)
        self.v_email = QLineEdit()
        self.v_email.setPlaceholderText("NCBI lo pide para el BLAST remoto")
        carpetas.addRow("E-mail:", self.v_email)
        layout.addLayout(carpetas)

        grupo_blast = QGroupBox("Búsqueda en GenBank")
        form = QFormLayout(grupo_blast)
        self.v_preset = QComboBox()
        self.v_preset.addItems([p.nombre for p in PRESETS])
        self.v_preset.currentTextChanged.connect(self._aplicar_preset)
        form.addRow("Preset:", self.v_preset)
        self.v_db = QComboBox()
        self.v_db.setEditable(True)
        self.v_db.addItems(BASES)
        form.addRow("Base de datos:", self.v_db)
        self.v_taxon = QComboBox()
        self.v_taxon.setEditable(True)
        self.v_taxon.addItems(TAXONES)
        form.addRow("Restringir a:", self.v_taxon)
        self.v_noblast = QCheckBox(
            "Solo control de calidad y clasificación (sin BLAST; es instantáneo)"
        )
        form.addRow("", self.v_noblast)
        layout.addWidget(grupo_blast)

        grupo_umbrales = QGroupBox(
            "Umbrales (los valores por defecto sirven para amplicones de 200–400 pb)"
        )
        form = QFormLayout(grupo_umbrales)
        self.v_largo = self._entero(1, 5000, 100)
        self.v_largo_laxo = self._entero(1, 5000, 60)
        self.v_ident = self._decimal(50.0, 100.0, 97.0)
        self.v_lote = self._entero(1, 100, 50)
        form.addRow(
            "Largo mínimo CONFIABLE (pb):",
            self._con_ayuda(self.v_largo, "300–400 para COI Folmer / 16S completo"),
        )
        form.addRow(
            "Largo mínimo DUDOSA (pb):",
            self._con_ayuda(self.v_largo_laxo, "bajar a 50 para ver más casos límite"),
        )
        form.addRow(
            "% identidad para 'identificado':",
            self._con_ayuda(self.v_ident, "98,7 para 16S bacteriano"),
        )
        form.addRow(
            "Secuencias por envío a NCBI:",
            self._con_ayuda(self.v_lote, "bajar a 20 si NCBI rechaza el lote"),
        )
        layout.addWidget(grupo_umbrales)
        layout.addStretch()
        return w

    def _tab_progreso(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.etiqueta_etapa = QLabel("Listo para empezar.")
        self.barra = QProgressBar()
        self.barra.setTextVisible(True)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setStyleSheet("font-family: Consolas, monospace; font-size: 9pt;")
        layout.addWidget(self.etiqueta_etapa)
        layout.addWidget(self.barra)
        layout.addWidget(self.log)
        return w

    def _tab_resultados(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        filtros = QHBoxLayout()
        self.v_filtro = QLineEdit()
        self.v_filtro.setPlaceholderText("Filtrar: muestra, especie, interpretación…")
        self.v_grupo = QComboBox()
        self.v_grupo.addItem("Todos los grupos", None)
        for g in Grupo:
            self.v_grupo.addItem(g.value, g)
        filtros.addWidget(self.v_filtro, 1)
        filtros.addWidget(self.v_grupo)
        layout.addLayout(filtros)

        self.modelo = ModeloMuestras()
        self.proxy = FiltroMuestras()
        self.proxy.setSourceModel(self.modelo)
        self.v_filtro.textChanged.connect(self.proxy.setFilterFixedString)
        self.v_grupo.currentIndexChanged.connect(
            lambda i: self.proxy.poner_grupo(self.v_grupo.itemData(i))
        )

        self.tabla = QTableView()
        self.tabla.setModel(self.proxy)
        self.tabla.setSortingEnabled(True)
        self.tabla.setAlternatingRowColors(False)
        self.tabla.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabla.doubleClicked.connect(self._doble_clic)
        layout.addWidget(self.tabla)
        layout.addWidget(QLabel("Doble clic sobre un accession abre el registro en NCBI."))
        return w

    def _barra_botones(self) -> QHBoxLayout:
        barra = QHBoxLayout()
        self.b_analizar = QPushButton("Analizar")
        self.b_analizar.clicked.connect(self.correr)
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self.cancelar)
        self.b_abrir = QPushButton("Abrir carpeta de resultados")
        self.b_abrir.clicked.connect(self.abrir_resultados)
        self.estado = QLabel("")
        barra.addWidget(self.b_analizar)
        barra.addWidget(self.b_cancelar)
        barra.addWidget(self.b_abrir)
        barra.addWidget(self.estado, 1)
        return barra

    def _campo_carpeta(self, titulo: str) -> tuple[QLineEdit, QWidget]:
        contenedor = QWidget()
        fila = QHBoxLayout(contenedor)
        fila.setContentsMargins(0, 0, 0, 0)
        campo = QLineEdit()
        boton = QPushButton("Elegir…")
        boton.clicked.connect(lambda: self._elegir_carpeta(campo, titulo))
        fila.addWidget(campo, 1)
        fila.addWidget(boton)
        return campo, contenedor

    def _con_ayuda(self, widget: QWidget, ayuda: str) -> QWidget:
        contenedor = QWidget()
        fila = QHBoxLayout(contenedor)
        fila.setContentsMargins(0, 0, 0, 0)
        etiqueta = QLabel(ayuda)
        etiqueta.setStyleSheet("color: gray;")
        fila.addWidget(widget)
        fila.addWidget(etiqueta, 1)
        return contenedor

    @staticmethod
    def _entero(minimo: int, maximo: int, valor: int) -> QSpinBox:
        w = QSpinBox()
        w.setRange(minimo, maximo)
        w.setValue(valor)
        return w

    @staticmethod
    def _decimal(minimo: float, maximo: float, valor: float) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(minimo, maximo)
        w.setDecimals(1)
        w.setValue(valor)
        return w

    # ---------------- acciones ----------------

    def _elegir_carpeta(self, campo: QLineEdit, titulo: str) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, titulo, campo.text())
        if carpeta:
            campo.setText(carpeta)

    def _proponer_salida(self, entrada: str) -> None:
        if entrada and not self.v_salida.text():
            self.v_salida.setText(str(Path(entrada) / "resultados"))

    def _aplicar_preset(self, nombre: str) -> None:
        cambios = preset(nombre).cambios
        if "largo_min" in cambios:
            self.v_largo.setValue(cambios["largo_min"])
        if "ident_min" in cambios:
            self.v_ident.setValue(cambios["ident_min"])
        if "db" in cambios:
            self.v_db.setCurrentText(cambios["db"])

    def parametros(self) -> Parametros:
        """Lo cargado en la pestaña de configuración, como Parametros del núcleo."""
        entrada = self.v_entrada.text().strip()
        salida = self.v_salida.text().strip() or str(Path(entrada) / "resultados")
        taxon = self.v_taxon.currentText().strip()
        return Parametros(
            entrada=entrada,
            salida=salida,
            email=self.v_email.text().strip() or None,
            largo_min=self.v_largo.value(),
            largo_min_laxo=self.v_largo_laxo.value(),
            ident_min=self.v_ident.value(),
            lote=self.v_lote.value(),
            db=self.v_db.currentText().strip() or "nt",
            taxon=None if taxon.startswith("(") or not taxon else taxon,
            no_blast=self.v_noblast.isChecked(),
        )

    def correr(self) -> None:
        entrada = self.v_entrada.text().strip()
        if not entrada or not Path(entrada).is_dir():
            QMessageBox.critical(
                self, "Falta la carpeta", "Elegí la carpeta que contiene los archivos .ab1."
            )
            return
        if not self.v_noblast.isChecked() and "@" not in self.v_email.text():
            QMessageBox.critical(
                self,
                "Falta el e-mail",
                "NCBI pide un e-mail para el BLAST remoto.\n"
                "Escribí uno, o marcá 'Solo control de calidad'.",
            )
            return

        self.guardar_preferencias()
        self.log.clear()
        self.modelo.poner([])
        self.barra.setRange(0, 0)
        self.tabs.setCurrentIndex(1)
        self._actualizar_botones(corriendo=True)
        self.estado.setText("Analizando…")

        self.worker = Worker(self.parametros(), self)
        self.worker.progreso.connect(self.en_progreso)
        self.worker.log.connect(self.en_log)
        self.worker.terminado.connect(self.en_terminado)
        self.worker.error.connect(self.en_error)
        self.worker.start()

    def cancelar(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancelar()
            self.estado.setText("Cancelando… (termina el paso en curso)")
            self.b_cancelar.setEnabled(False)

    def en_progreso(self, progreso: Progreso) -> None:
        self.etiqueta_etapa.setText(ETAPAS.get(progreso.etapa, progreso.etapa))
        if progreso.total:
            self.barra.setRange(0, progreso.total)
            self.barra.setValue(progreso.hechos)
        else:
            self.barra.setRange(0, 0)  # sin total conocido: barra indeterminada

    def en_log(self, texto: str) -> None:
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(texto)
        self.log.ensureCursorVisible()

    def en_terminado(self, resultado: Resultado) -> None:
        self.resultado = resultado
        self.modelo.poner(resultado.muestras)
        self.tabla.resizeColumnsToContents()
        self.tabs.setCurrentIndex(2)
        self.barra.setRange(0, 1)
        self.barra.setValue(1)
        self.etiqueta_etapa.setText("Listo.")
        confiables = len(resultado.del_grupo(Grupo.CONFIABLE))
        dudosas = len(resultado.del_grupo(Grupo.DUDOSA))
        rechazadas = len(resultado.del_grupo(Grupo.RECHAZADA))
        self.estado.setText(
            f"Listo: {confiables} confiables, {dudosas} dudosas, {rechazadas} rechazadas."
        )
        self._actualizar_botones(corriendo=False)

    def en_error(self, error: Exception) -> None:
        self.barra.setRange(0, 1)
        self.barra.setValue(0)
        self._actualizar_botones(corriendo=False)
        if isinstance(error, Cancelado):
            self.etiqueta_etapa.setText("Cancelado.")
            self.estado.setText("Cancelado. Lo que ya se escribió quedó en la carpeta de salida.")
            return
        self.etiqueta_etapa.setText("Terminó con error.")
        self.estado.setText("Terminó con error (ver el mensaje).")
        QMessageBox.critical(self, "El análisis no pudo terminar", str(error))

    def abrir_resultados(self) -> None:
        ruta = self.v_salida.text().strip()
        if not ruta or not Path(ruta).exists():
            return
        if sys.platform.startswith("win"):
            os.startfile(ruta)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])

    def _doble_clic(self, indice) -> None:
        if indice.column() != COLUMNA_ACCESSION:
            return
        accession = indice.data()
        if accession:
            QDesktopServices.openUrl(QUrl(url_ncbi(accession)))

    def _actualizar_botones(self, corriendo: bool) -> None:
        self.b_analizar.setEnabled(not corriendo)
        self.b_cancelar.setEnabled(corriendo)
        self.b_abrir.setEnabled(not corriendo and bool(self.v_salida.text().strip()))

    # ---------------- preferencias ----------------

    def _cargar_preferencias(self, prefs: dict) -> None:
        self.v_email.setText(prefs.get("email", ""))
        self.v_entrada.setText(prefs.get("entrada", ""))
        self.v_salida.setText(prefs.get("salida", ""))
        if prefs.get("db"):
            self.v_db.setCurrentText(prefs["db"])
        if prefs.get("taxon"):
            self.v_taxon.setCurrentText(prefs["taxon"])
        if prefs.get("preset"):
            self.v_preset.setCurrentText(prefs["preset"])

    def preferencias_actuales(self) -> dict:
        return {
            "email": self.v_email.text().strip(),
            "entrada": self.v_entrada.text().strip(),
            "salida": self.v_salida.text().strip(),
            "preset": self.v_preset.currentText(),
            "db": self.v_db.currentText().strip(),
            "taxon": self.v_taxon.currentText().strip(),
        }

    def guardar_preferencias(self) -> None:
        preferencias.guardar(self.preferencias_actuales())

    def closeEvent(self, evento) -> None:
        if self.worker and self.worker.isRunning():
            respuesta = QMessageBox.question(
                self,
                "Hay un análisis corriendo",
                "¿Cancelar el análisis y cerrar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                evento.ignore()
                return
            self.worker.cancelar()
            self.worker.wait(5000)
        self.guardar_preferencias()
        evento.accept()
