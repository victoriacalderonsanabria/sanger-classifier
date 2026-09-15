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
import time
from pathlib import Path

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, QUrl
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from sanger import __version__
from sanger.config import (
    AVISO_PRESETS,
    PRESET_DEFAULT,
    PRESETS,
    Parametros,
    normalizar_valores,
    valores_de_preset,
)
from sanger.errores import Cancelado
from sanger.io.informes import escribir_informes, escribir_resultados_filtrados
from sanger.modelos import Grupo, Progreso, Resultado
from sanger_ui import avance, cache_local, preferencias
from sanger_ui.exportar import DialogoExportar
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

ETAPAS_CORTAS = {
    "qc": "Control de calidad",
    "clasificacion": "Clasificación",
    "comparacion": "Comparación",
    "blast": "BLAST",
    "informes": "Informes",
}

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
        # con la versión a la vista: cuando alguien avisa que algo le falla, lo
        # primero que hay que saber es qué versión tiene
        self.setWindowTitle(f"Clasificador de secuencias Sanger {__version__}")
        self.setWindowIcon(icono())
        self.resize(1000, 700)
        self.worker: Worker | None = None
        self.resultado: Resultado | None = None
        self.params: Parametros | None = None
        self.exportado = True  # no hay nada que perder todavía
        self.ultima_exportacion = ""
        # Los umbrales que este equipo dejó guardados como su Default. Vacío =
        # se usan los del programa. Se carga en _cargar_preferencias, pero tiene
        # que existir antes: armar la pestaña ya consulta el perfil.
        self.default_propio: dict = {}
        self.etapa_actual = ""
        self.detalle = ""
        self.desde = time.monotonic()

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
        self._refrescar_cache()
        self._actualizar_botones(corriendo=False)

    # ---------------- armado de la interfaz ----------------

    def _tab_configuracion(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        carpetas = QFormLayout()
        self.v_entrada, fila_entrada = self._campo_carpeta("Carpeta con los cromatogramas .ab1")
        self.v_entrada.textChanged.connect(self._refrescar_cache)
        carpetas.addRow("Carpeta con los .ab1:", fila_entrada)
        self.v_email = QLineEdit()
        self.v_email.setPlaceholderText("NCBI lo pide para el BLAST remoto")
        carpetas.addRow("E-mail:", self.v_email)

        # El caché es invisible (vive fuera de las carpetas de datos), así que
        # se muestra cuánto ocupa y se puede borrar desde acá.
        fila_cache = QWidget()
        caja = QHBoxLayout(fila_cache)
        caja.setContentsMargins(0, 0, 0, 0)
        self.etiqueta_cache = QLabel("")
        self.etiqueta_cache.setStyleSheet("color: gray;")
        self.b_limpiar_cache = QPushButton("Limpiar caché")
        self.b_limpiar_cache.clicked.connect(self.limpiar_cache)
        caja.addWidget(self.etiqueta_cache, 1)
        caja.addWidget(self.b_limpiar_cache)
        carpetas.addRow("Caché de BLAST:", fila_cache)
        layout.addLayout(carpetas)

        grupo_blast = QGroupBox("Búsqueda en GenBank")
        form = QFormLayout(grupo_blast)
        # El perfil, su aviso y los botones del Default son UNA cosa: con el
        # interlineado de formulario quedaban tan separados que no se leían
        # juntos. Las líneas de ayuda van pegadas a lo que explican.
        form.setVerticalSpacing(4)
        fila_preset = QWidget()
        caja_preset = QHBoxLayout(fila_preset)
        caja_preset.setContentsMargins(0, 0, 0, 0)
        self.v_preset = QComboBox()
        self.v_preset.addItems([p.nombre for p in PRESETS])
        # por índice y no por texto: al marcar "(modificado)" cambia el texto,
        # y buscar el preset por ese texto no encontraría nada
        self.v_preset.currentIndexChanged.connect(self._elegir_preset)
        # La explicación de cada perfil es larga y no se necesita todo el
        # tiempo: pasando el mouse por el combo aparece, y este botón la deja
        # fija para leerla con calma. Permanente ocupaba media pestaña.
        self.b_info_preset = QToolButton()
        self.b_info_preset.setText("?")
        self.b_info_preset.setCheckable(True)
        self.b_info_preset.setToolTip("Qué es este perfil")
        self.b_info_preset.toggled.connect(self._mostrar_detalle_preset)
        caja_preset.addWidget(self.v_preset, 1)
        caja_preset.addWidget(self.b_info_preset)
        form.addRow("Perfil:", fila_preset)

        # Esto sí queda siempre a la vista, y es una línea: un umbral de
        # identidad no define una especie y el combo no puede dar a entender
        # que sí.
        # sin etiqueta a la izquierda (addRow de un solo argumento): ocupan el
        # ancho entero y no dejan una columna vacía al costado
        self.etiqueta_preset = QLabel(AVISO_PRESETS)
        self.etiqueta_preset.setWordWrap(True)
        self.etiqueta_preset.setStyleSheet("color: gray;")
        form.addRow(self.etiqueta_preset)

        self.detalle_preset = QLabel("")
        self.detalle_preset.setWordWrap(True)
        self.detalle_preset.setStyleSheet("color: gray; margin-top: 4px;")
        self.detalle_preset.setVisible(False)
        form.addRow(self.detalle_preset)

        # Cada equipo que use el programa puede tener criterios distintos a los
        # del laboratorio. En vez de pedirle que los cargue a mano en cada
        # corrida, los deja guardados una vez y quedan como su Default.
        fila_default = QWidget()
        caja_default = QHBoxLayout(fila_default)
        caja_default.setContentsMargins(0, 0, 0, 0)
        self.b_guardar_default = QPushButton("Guardar estos valores como mi Default")
        self.b_guardar_default.setToolTip(
            "Los valores que tenés cargados pasan a ser el Default de esta computadora.\n"
            "No cambia nada para los demás: se guarda en tus preferencias."
        )
        self.b_guardar_default.clicked.connect(self.guardar_como_default)
        self.b_restaurar_default = QPushButton("Volver al Default del programa")
        self.b_restaurar_default.setToolTip(
            "Descarta el Default guardado y vuelve a los valores validados con el ensayo."
        )
        self.b_restaurar_default.clicked.connect(self.restaurar_default_programa)
        caja_default.addWidget(self.b_guardar_default)
        caja_default.addWidget(self.b_restaurar_default)
        caja_default.addStretch()
        form.addRow(fila_default)
        self.v_db = QComboBox()
        self.v_db.setEditable(True)
        self.v_db.addItems(BASES)
        self.v_db.currentTextChanged.connect(self._refrescar_marca_preset)
        form.addRow("Base de datos:", self.v_db)
        self.v_taxon = QComboBox()
        self.v_taxon.setEditable(True)
        self.v_taxon.addItems(TAXONES)
        form.addRow("Restringir a:", self.v_taxon)
        self.v_noblast = QCheckBox(
            "Solo control de calidad y clasificación (sin BLAST; es instantáneo)"
        )
        form.addRow(self.v_noblast)
        layout.addWidget(grupo_blast)

        grupo_umbrales = QGroupBox(
            "Umbrales (los valores por defecto sirven para amplicones de 200–400 pb)"
        )
        form = QFormLayout(grupo_umbrales)
        self.v_largo = self._entero(1, 5000, 100)
        self.v_largo_laxo = self._entero(1, 5000, 60)
        self.v_ident = self._decimal(50.0, 100.0, 97.0)
        self.v_lote = self._entero(1, 100, 50)
        for campo in (self.v_largo, self.v_largo_laxo, self.v_ident, self.v_lote):
            campo.valueChanged.connect(self._refrescar_marca_preset)
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
        self.barra.setRange(0, 100)
        self.barra.setTextVisible(True)
        # Línea viva: qué está haciendo y desde hace cuánto. Es lo que dice que
        # el programa está trabajando cuando la barra no se mueve (la espera de
        # NCBI puede ser de minutos).
        self.etiqueta_estado = QLabel("")
        self.etiqueta_estado.setStyleSheet("color: gray;")
        self.cronometro = QTimer(self)
        self.cronometro.setInterval(1000)
        self.cronometro.timeout.connect(self._refrescar_estado)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setStyleSheet("font-family: Consolas, monospace; font-size: 9pt;")
        layout.addWidget(self.etiqueta_etapa)
        layout.addWidget(self.barra)
        layout.addWidget(self.etiqueta_estado)
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
        # sin ordenar por ninguna columna: la tabla abre en el mismo orden que
        # 04_resultados.csv (CONFIABLE → DUDOSA → RECHAZADA, y por nombre)
        self.tabla.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.tabla.setAlternatingRowColors(False)
        self.tabla.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabla.doubleClicked.connect(self._doble_clic)
        layout.addWidget(self.tabla)

        pie = QHBoxLayout()
        self.b_exportar = QPushButton("Exportar…")
        self.b_exportar.clicked.connect(self.exportar)
        self.b_abrir = QPushButton("Abrir carpeta exportada")
        self.b_abrir.clicked.connect(self.abrir_exportado)
        self.etiqueta_exportacion = QLabel(
            "Doble clic sobre un accession abre el registro en NCBI."
        )
        self.etiqueta_exportacion.setStyleSheet("color: gray;")
        pie.addWidget(self.b_exportar)
        pie.addWidget(self.b_abrir)
        pie.addWidget(self.etiqueta_exportacion, 1)
        layout.addLayout(pie)
        return w

    def _barra_botones(self) -> QHBoxLayout:
        barra = QHBoxLayout()
        self.b_analizar = QPushButton("Analizar")
        self.b_analizar.clicked.connect(self.correr)
        self.b_cancelar = QPushButton("Cancelar")
        self.b_cancelar.clicked.connect(self.cancelar)
        self.estado = QLabel("")
        barra.addWidget(self.b_analizar)
        barra.addWidget(self.b_cancelar)
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

    def _refrescar_cache(self) -> None:
        """Cuánto ocupa el caché de BLAST de esta carpeta de entrada."""
        entrada = self.v_entrada.text().strip()
        if not entrada:
            self.etiqueta_cache.setText("se crea al hacer el primer BLAST")
            self.b_limpiar_cache.setEnabled(False)
            return
        carpeta = cache_local.carpeta_para(entrada)
        ocupa = cache_local.tamano(carpeta)
        self.etiqueta_cache.setText(
            f"{cache_local.formatear_tamano(ocupa)} · {carpeta}"
            if ocupa
            else f"vacío · se guardará en {carpeta}"
        )
        self.b_limpiar_cache.setEnabled(bool(ocupa))

    def limpiar_cache(self) -> None:
        """
        Borra el caché de esta carpeta de entrada.

        Lo único que se pierde es tiempo: la próxima corrida vuelve a consultar
        a NCBI en vez de reusar lo ya consultado.
        """
        entrada = self.v_entrada.text().strip()
        if not entrada:
            return
        liberado = cache_local.limpiar(cache_local.carpeta_para(entrada))
        self._refrescar_cache()
        self.estado.setText(f"Caché borrado: {cache_local.formatear_tamano(liberado)} liberados.")

    def preset_elegido(self) -> str:
        """El nombre del preset seleccionado, sin el sufijo de modificado."""
        return PRESETS[max(self.v_preset.currentIndex(), 0)].nombre

    def _mostrar_detalle_preset(self, visible: bool) -> None:
        """Muestra u oculta la explicación del perfil (el botón '?')."""
        self.detalle_preset.setVisible(visible)

    def valores_del_perfil(self, nombre: str) -> dict:
        """Los valores de ese perfil, sobre el Default guardado si hay uno."""
        return valores_de_preset(nombre, self.default_propio)

    def _elegir_preset(self, indice: int) -> None:
        """Carga en los campos los valores del perfil (todos, no solo los que cambia)."""
        elegido = PRESETS[indice]
        descripcion = elegido.descripcion
        if self.default_propio:
            descripcion += (
                "\n\nEstá en uso un Default propio, guardado en esta computadora: "
                "los valores de partida son los que guardó este equipo, no los que "
                "trae el programa."
            )
        self.detalle_preset.setText(descripcion)
        # también en el globo del combo: es donde uno lo busca primero
        self.v_preset.setToolTip(descripcion)
        self.b_info_preset.setToolTip(descripcion)
        valores = self.valores_del_perfil(elegido.nombre)
        self.v_largo.setValue(valores["largo_min"])
        self.v_largo_laxo.setValue(valores["largo_min_laxo"])
        self.v_ident.setValue(valores["ident_min"])
        self.v_lote.setValue(valores["lote"])
        self.v_db.setCurrentText(valores["db"])
        self.b_restaurar_default.setEnabled(bool(self.default_propio))
        self._refrescar_marca_preset()

    def guardar_como_default(self) -> None:
        """Deja lo que está cargado como Default de esta computadora."""
        valores = normalizar_valores(self.valores_cargados())
        if not valores:
            return
        self.default_propio = valores
        self._volver_al_default()
        self.estado.setText(
            "Guardado: estos valores son, de ahora en más, el Default de esta computadora."
        )

    def restaurar_default_programa(self) -> None:
        """Descarta el Default guardado y vuelve a los valores validados."""
        self.default_propio = {}
        self._volver_al_default()
        self.estado.setText("Listo: volvieron los valores con los que viene el programa.")

    def _volver_al_default(self) -> None:
        indice = [p.nombre for p in PRESETS].index(PRESET_DEFAULT)
        # setCurrentIndex no avisa si el índice ya era ese, así que los valores
        # se recargan a mano: si no, cambiar el Default no se vería en pantalla.
        self.v_preset.setCurrentIndex(indice)
        self._elegir_preset(indice)
        self.guardar_preferencias()

    def valores_cargados(self) -> dict:
        return {
            "largo_min": self.v_largo.value(),
            "largo_min_laxo": self.v_largo_laxo.value(),
            "ident_min": self.v_ident.value(),
            "lote": self.v_lote.value(),
            "db": self.v_db.currentText().strip(),
        }

    def _refrescar_marca_preset(self) -> None:
        """
        Marca el preset como modificado si algún valor ya no es el suyo.

        Se muestra "Default (modificado)" en vez de cambiar de preset: así el
        usuario ve cuál eligió y que además tocó algo. Vuelve solo si los
        valores coinciden de nuevo.
        """
        indice = max(self.v_preset.currentIndex(), 0)
        nombre = PRESETS[indice].nombre
        modificado = self.valores_cargados() != self.valores_del_perfil(nombre)
        self.v_preset.setItemText(indice, f"{nombre} (modificado)" if modificado else nombre)

    def parametros(self) -> Parametros:
        """
        Lo cargado en la pestaña de configuración, como Parametros del núcleo.

        `salida=None`: corriendo desde la ventana no se escribe nada al disco.
        Los informes se generan después, con el botón Exportar. El caché de
        BLAST sí se guarda, en su carpeta estable.
        """
        entrada = self.v_entrada.text().strip()
        taxon = self.v_taxon.currentText().strip()
        return Parametros(
            entrada=entrada,
            salida=None,
            carpeta_cache=cache_local.carpeta_para(entrada),
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

        if not self._confirmar_perder_resultados("analizar de nuevo"):
            return

        self.guardar_preferencias()
        self.log.clear()
        self.modelo.poner([])
        self.resultado = None
        self.exportado = True  # no hay nada sin exportar hasta que termine
        self.barra.setValue(0)
        self.etapa_actual, self.detalle, self.desde = "", "", time.monotonic()
        self.cronometro.start()
        self.tabs.setCurrentIndex(1)
        self._actualizar_botones(corriendo=True)
        self.estado.setText("Analizando…")

        self.params = self.parametros()
        self.worker = Worker(self.params, self)
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
        self.barra.setValue(avance.porcentaje(progreso.etapa, progreso.hechos, progreso.total))
        if progreso.detalle and progreso.detalle != self.detalle:
            # empezó algo nuevo: el cronómetro cuenta desde acá
            self.detalle = progreso.detalle
            self.desde = time.monotonic()
        self.etapa_actual = progreso.etapa
        self._refrescar_estado()

    def _refrescar_estado(self) -> None:
        """La línea viva: etapa · qué está haciendo · desde hace cuánto."""
        if not self.etapa_actual:
            self.etiqueta_estado.setText("")
            return
        partes = [ETAPAS_CORTAS.get(self.etapa_actual, self.etapa_actual)]
        if self.detalle:
            partes.append(self.detalle)
        partes.append(avance.reloj(time.monotonic() - self.desde))
        self.etiqueta_estado.setText(" · ".join(partes))

    def en_log(self, texto: str) -> None:
        self.log.moveCursor(self.log.textCursor().MoveOperation.End)
        self.log.insertPlainText(texto)
        self.log.ensureCursorVisible()

    def en_terminado(self, resultado: Resultado) -> None:
        self.cronometro.stop()
        self.resultado = resultado
        self.exportado = False  # hay resultados en memoria que nadie guardó
        self.modelo.poner(resultado.muestras)
        self.tabla.resizeColumnsToContents()
        self.tabs.setCurrentIndex(2)
        self.barra.setValue(100)
        self.etiqueta_etapa.setText("Listo.")
        self.etiqueta_estado.setText(
            f"Terminó en {avance.reloj(resultado.segundos_total)}"
            + (
                f", de los cuales {avance.reloj(resultado.segundos_blast)} de BLAST"
                if resultado.segundos_blast
                else ""
            )
        )
        confiables = len(resultado.del_grupo(Grupo.CONFIABLE))
        dudosas = len(resultado.del_grupo(Grupo.DUDOSA))
        rechazadas = len(resultado.del_grupo(Grupo.RECHAZADA))
        self.estado.setText(
            f"Listo: {confiables} confiables, {dudosas} dudosas, {rechazadas} rechazadas."
        )
        self._actualizar_botones(corriendo=False)

    def en_error(self, error: Exception) -> None:
        self.cronometro.stop()
        self.etiqueta_estado.setText("")
        self._actualizar_botones(corriendo=False)
        if isinstance(error, Cancelado):
            self.etiqueta_etapa.setText("Cancelado.")
            self.estado.setText("Cancelado. El BLAST ya hecho queda en el caché para la próxima.")
            return
        self.etiqueta_etapa.setText("Terminó con error.")
        self.estado.setText("Terminó con error (ver el mensaje).")
        QMessageBox.critical(self, "El análisis no pudo terminar", str(error))

    def muestras_visibles(self) -> list:
        """Las muestras que se están viendo, en el orden en que se ven."""
        return [
            self.modelo.muestra_en(self.proxy.mapToSource(self.proxy.index(fila, 0)).row())
            for fila in range(self.proxy.rowCount())
        ]

    def exportar(self) -> None:
        """Escribe los informes elegidos, con el mismo código que la línea de comandos."""
        if self.resultado is None:
            QMessageBox.information(self, "Todavía no hay resultados", "Primero corré un análisis.")
            return
        visibles = self.muestras_visibles()
        dialogo = DialogoExportar(
            self,
            destino_sugerido=self.ultima_exportacion,
            visibles=len(visibles),
            total=self.modelo.rowCount(),
        )
        if dialogo.exec() != DialogoExportar.DialogCode.Accepted:
            return
        destino, cuales = dialogo.destino(), dialogo.elegidos()
        if destino is None or not cuales:
            QMessageBox.critical(
                self, "Falta elegir", "Indicá una carpeta y al menos un archivo para exportar."
            )
            return
        filtrar = dialogo.filtrar_resultados()
        sep, decimal_coma = self.params.sep_csv, self.params.decimal_coma
        try:
            escritos = escribir_informes(
                self.resultado,
                destino,
                sep,
                decimal_coma,
                [c for c in cuales if not (filtrar and c == "04")],
            )
            if filtrar and "04" in cuales:
                # solo esta salida se filtra, y sale con otro nombre
                escritos.append(escribir_resultados_filtrados(visibles, destino, sep, decimal_coma))
        except OSError as e:
            QMessageBox.critical(self, "No se pudo exportar", str(e))
            return
        self.exportado = True
        self.ultima_exportacion = str(destino)
        self.b_abrir.setEnabled(True)
        self.etiqueta_exportacion.setText(f"{len(escritos)} archivos exportados en {destino}")
        self.estado.setText(f"Exportado en {destino}")

    def abrir_exportado(self) -> None:
        ruta = self.ultima_exportacion
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

    def _confirmar_perder_resultados(self, accion: str) -> bool:
        """
        Avisa si hay resultados en memoria que nadie exportó.

        Una corrida con BLAST puede costar veinte minutos: perderla por un clic
        sería feo.
        """
        if self.resultado is None or self.exportado:
            return True
        respuesta = QMessageBox.question(
            self,
            "Hay resultados sin exportar",
            f"Los resultados de la última corrida todavía no se guardaron.\n\n¿{accion} igual?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return respuesta == QMessageBox.StandardButton.Yes

    def _actualizar_botones(self, corriendo: bool) -> None:
        self.b_analizar.setEnabled(not corriendo)
        self.b_cancelar.setEnabled(corriendo)
        self.b_exportar.setEnabled(not corriendo and self.resultado is not None)
        self.b_abrir.setEnabled(bool(self.ultima_exportacion))

    # ---------------- preferencias ----------------

    def _cargar_preferencias(self, prefs: dict) -> None:
        self.default_propio = normalizar_valores(prefs.get(preferencias.CLAVE_DEFAULT))
        self.v_email.setText(prefs.get("email", ""))
        self.v_entrada.setText(prefs.get("entrada", ""))
        self.ultima_exportacion = prefs.get("exportacion", "")
        nombres = [p.nombre for p in PRESETS]
        indice = nombres.index(prefs["preset"]) if prefs.get("preset") in nombres else 0
        self.v_preset.setCurrentIndex(indice)
        # explícito: con el perfil ya en ese índice la señal no sale, y el
        # Default guardado quedaría sin cargarse
        self._elegir_preset(indice)
        # la base y el filtro que se usaron la última vez van por encima del
        # perfil: son lo más específico que dijo esta persona
        if prefs.get("db"):
            self.v_db.setCurrentText(prefs["db"])
        if prefs.get("taxon"):
            self.v_taxon.setCurrentText(prefs["taxon"])

    def preferencias_actuales(self) -> dict:
        datos = {
            "email": self.v_email.text().strip(),
            "entrada": self.v_entrada.text().strip(),
            "exportacion": self.ultima_exportacion,
            "preset": self.preset_elegido(),
            "db": self.v_db.currentText().strip(),
            "taxon": self.v_taxon.currentText().strip(),
        }
        if self.default_propio:
            datos[preferencias.CLAVE_DEFAULT] = self.default_propio
        return datos

    def guardar_preferencias(self) -> None:
        preferencias.guardar(self.preferencias_actuales())

    def closeEvent(self, evento) -> None:
        if not self._confirmar_perder_resultados("Cerrar"):
            evento.ignore()
            return
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
