"""
Tests de la ventana, con Qt en modo "offscreen" (sin pantalla).

El briefing dice que la UI no se testea automáticamente, y estos tests **no
corren en el CI**: PySide6 pesa unos 100 MB y no se instala ahí, así que se
saltean solos. Pero acá, en la máquina donde se desarrolla, cubren lo barato y
útil: que la ventana se arme, que los campos se traduzcan bien a Parametros,
que la tabla muestre lo que tiene que mostrar y que el hilo de trabajo avise y
se pueda cancelar. Lo que sigue siendo manual es mirar la ventana de verdad.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="la ventana necesita PySide6 (pip install -e .[ui])")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import paridad  # noqa: E402
from sanger.cli import main as cli_main  # noqa: E402
from sanger.config import PRESETS, Parametros  # noqa: E402
from sanger.errores import Cancelado  # noqa: E402
from sanger.io.informes import ARCHIVOS, TODOS  # noqa: E402
from sanger.modelos import Grupo, Hit, Muestra, Progreso, Resultado  # noqa: E402
from sanger_ui import cache_local, preferencias  # noqa: E402
from sanger_ui.exportar import DialogoExportar  # noqa: E402
from sanger_ui.modelo_tabla import (  # noqa: E402
    COLUMNA_ACCESSION,
    COLUMNAS,
    ModeloMuestras,
    url_ncbi,
)
from sanger_ui.ventana import FiltroMuestras, Ventana  # noqa: E402
from sanger_ui.worker import Worker  # noqa: E402
from tests.sintetico.corrida import armar_corrida  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def muestras():
    hit = Hit("Bos taurus", "XX000001.1", 99.5, 100.0, 2e-100, "Bos taurus COI")
    return [
        Muestra("A1", ("A1_F.ab1",), Grupo.CONFIABLE, "CONSENSO_F+R", "ACGT", 260, 38.2, 99.0,
                200, 1, 0, hits=[hit], interpretacion="identificado"),
        Muestra("B2", ("B2_F.ab1",), Grupo.DUDOSA, "SOLO_F", "ACGT", 90, 21.0, 55.0,
                motivos=["largo 90 < 100"], vs_confiables="coincide con A1 (100.0% en 70 bases)"),
        Muestra("C3", ("C3_F.ab1",), motivos=["ninguna lectura con señal utilizable"]),
    ]  # fmt: skip


@pytest.fixture
def ventana(app, tmp_path, monkeypatch):
    # las preferencias no se tocan en el disco de quien corre los tests
    monkeypatch.setattr(preferencias, "ARCHIVO", tmp_path / "config.json")
    # el caché tampoco: cada test usa el suyo
    monkeypatch.setattr(cache_local, "raiz", lambda: tmp_path / "cache")
    v = Ventana(prefs={})
    yield v
    # cerrar con resultados sin exportar pregunta: en los tests nadie contesta
    v.exportado = True
    v.close()


# ----------------------------------------------------------------------------
# Tabla de resultados
# ----------------------------------------------------------------------------


def test_la_tabla_muestra_una_fila_por_muestra(app, muestras):
    modelo = ModeloMuestras(muestras)
    assert (modelo.rowCount(), modelo.columnCount()) == (3, len(COLUMNAS))
    fila = {COLUMNAS[c].titulo: modelo.index(0, c).data() for c in range(modelo.columnCount())}
    assert fila["Muestra"] == "A1"
    assert fila["Grupo"] == "CONFIABLE"
    assert fila["Especie"] == "Bos taurus"
    assert fila["Accession"] == "XX000001.1"


def test_las_muestras_sin_blast_dejan_las_celdas_vacias(app, muestras):
    modelo = ModeloMuestras(muestras)
    fila = {COLUMNAS[c].titulo: modelo.index(2, c).data() for c in range(modelo.columnCount())}
    assert fila["Especie"] == "" and fila["Identidad"] == "" and fila["Q media"] == ""
    assert fila["Motivo"] == "ninguna lectura con señal utilizable"


def test_cada_grupo_tiene_su_color(app, muestras):
    modelo = ModeloMuestras(muestras)
    colores = {modelo.index(f, 0).data(Qt.ItemDataRole.BackgroundRole).name() for f in range(3)}
    assert len(colores) == 3  # CONFIABLE, DUDOSA y RECHAZADA se distinguen


def test_los_numeros_se_ordenan_como_numeros(app, muestras):
    modelo = ModeloMuestras(muestras)
    largo = next(i for i, c in enumerate(COLUMNAS) if c.titulo == "Largo")
    assert modelo.index(0, largo).data(Qt.ItemDataRole.UserRole) == 260


def test_el_filtro_por_texto_y_por_grupo(app, muestras):
    proxy = FiltroMuestras()
    proxy.setSourceModel(ModeloMuestras(muestras))
    assert proxy.rowCount() == 3
    proxy.setFilterFixedString("bos")  # sin importar mayúsculas, en cualquier columna
    assert proxy.rowCount() == 1
    proxy.setFilterFixedString("")
    proxy.poner_grupo(Grupo.DUDOSA)
    assert proxy.rowCount() == 1 and proxy.index(0, 0).data() == "B2"
    proxy.poner_grupo(None)
    assert proxy.rowCount() == 3


def test_el_accession_lleva_al_registro_de_ncbi():
    assert url_ncbi("XX000001.1") == "https://www.ncbi.nlm.nih.gov/nuccore/XX000001.1"
    assert COLUMNAS[COLUMNA_ACCESSION].titulo == "Accession"


# ----------------------------------------------------------------------------
# Configuración → Parametros
# ----------------------------------------------------------------------------


def test_los_campos_se_traducen_a_parametros(ventana, tmp_path):
    ventana.v_entrada.setText(str(tmp_path))
    ventana.v_email.setText("alguien@ejemplo.com")
    ventana.v_largo.setValue(300)
    ventana.v_largo_laxo.setValue(50)
    ventana.v_ident.setValue(98.7)
    ventana.v_lote.setValue(20)
    ventana.v_db.setCurrentText("mito")
    ventana.v_taxon.setCurrentText("Vertebrata[Organism]")
    p = ventana.parametros()
    assert p == Parametros(
        entrada=tmp_path, salida=None, carpeta_cache=cache_local.carpeta_para(tmp_path),
        email="alguien@ejemplo.com", largo_min=300, largo_min_laxo=50, ident_min=98.7,
        lote=20, db="mito", taxon="Vertebrata[Organism]",
    )  # fmt: skip


def test_sin_filtro_taxonomico_no_se_manda_taxon(ventana, tmp_path):
    ventana.v_entrada.setText(str(tmp_path))
    assert ventana.v_taxon.currentText().startswith("(")
    assert ventana.parametros().taxon is None


def test_la_ventana_no_escribe_nada_al_disco(ventana, tmp_path):
    # los informes se exportan a pedido: correr no ensucia el disco
    ventana.v_entrada.setText(str(tmp_path))
    assert ventana.parametros().salida is None
    assert not hasattr(ventana, "v_salida")


def test_el_cache_se_muestra_y_se_puede_limpiar(ventana, tmp_path):
    ventana.v_entrada.setText(str(tmp_path))
    assert "vacío" in ventana.etiqueta_cache.text()
    assert not ventana.b_limpiar_cache.isEnabled()

    carpeta = cache_local.preparar(tmp_path)
    (carpeta / "M1.hits.json").write_text("[]" * 600, encoding="utf-8")
    ventana._refrescar_cache()
    assert "KB" in ventana.etiqueta_cache.text()
    assert ventana.b_limpiar_cache.isEnabled()

    ventana.limpiar_cache()
    assert not carpeta.exists()
    assert "liberados" in ventana.estado.text()


def _indice_preset(ventana, nombre: str) -> int:
    return [p.nombre for p in PRESETS].index(nombre)


def test_el_preset_carga_los_umbrales(ventana):
    ventana.v_preset.setCurrentIndex(_indice_preset(ventana, "16S bacteriano"))
    assert (ventana.v_largo.value(), ventana.v_ident.value()) == (300, 98.7)
    assert ventana.v_db.currentText() == "16S_ribosomal_RNA"


def test_al_abrir_el_preset_es_default_sin_marca(ventana):
    assert ventana.v_preset.currentText() == "Default"
    assert ventana.preset_elegido() == "Default"


def test_volver_a_default_repone_todos_los_valores(ventana):
    ventana.v_preset.setCurrentIndex(_indice_preset(ventana, "16S bacteriano"))
    ventana.v_preset.setCurrentIndex(_indice_preset(ventana, "Default"))
    assert ventana.valores_cargados() == {
        "largo_min": 100,
        "largo_min_laxo": 60,
        "ident_min": 97.0,
        "lote": 50,
        "db": "nt",
    }


def test_tocar_un_umbral_marca_el_preset_como_modificado(ventana):
    ventana.v_largo.setValue(250)
    assert ventana.v_preset.currentText() == "Default (modificado)"
    assert ventana.preset_elegido() == "Default"  # el preset elegido no cambia


def test_la_marca_se_va_sola_si_se_vuelve_al_valor_del_preset(ventana):
    ventana.v_ident.setValue(95.0)
    assert "(modificado)" in ventana.v_preset.currentText()
    ventana.v_ident.setValue(97.0)
    assert ventana.v_preset.currentText() == "Default"


def test_la_marca_vale_para_cualquier_preset(ventana):
    ventana.v_preset.setCurrentIndex(_indice_preset(ventana, "COI Folmer (~650 pb)"))
    assert ventana.v_preset.currentText() == "COI Folmer (~650 pb)"
    ventana.v_db.setCurrentText("mito")
    assert ventana.v_preset.currentText() == "COI Folmer (~650 pb) (modificado)"


def test_elegir_otro_preset_limpia_la_marca(ventana):
    ventana.v_largo.setValue(250)
    ventana.v_preset.setCurrentIndex(_indice_preset(ventana, "ITS hongos"))
    assert ventana.v_preset.currentText() == "ITS hongos"
    assert ventana.v_largo.value() == 100  # se repusieron los valores del preset


def test_se_recuerda_el_preset_sin_el_sufijo(ventana):
    ventana.v_preset.setCurrentIndex(_indice_preset(ventana, "16S bacteriano"))
    ventana.v_lote.setValue(20)  # queda modificado
    assert ventana.preferencias_actuales()["preset"] == "16S bacteriano"


def test_analizar_sin_carpeta_no_arranca(ventana, monkeypatch):
    avisos = []
    monkeypatch.setattr(
        "sanger_ui.ventana.QMessageBox.critical", lambda *a, **k: avisos.append(a[1])
    )
    ventana.correr()
    assert avisos == ["Falta la carpeta"] and ventana.worker is None


def test_analizar_con_blast_pide_el_mail(ventana, tmp_path, monkeypatch):
    avisos = []
    monkeypatch.setattr(
        "sanger_ui.ventana.QMessageBox.critical", lambda *a, **k: avisos.append(a[1])
    )
    ventana.v_entrada.setText(str(tmp_path))
    ventana.correr()
    assert avisos == ["Falta el e-mail"] and ventana.worker is None


# ----------------------------------------------------------------------------
# Progreso, resultado y cancelación en la ventana
# ----------------------------------------------------------------------------


def test_la_barra_reparte_el_avance_por_etapa(ventana):
    # el QC entero son 10 puntos de 100, aunque sean 26 de 26 cromatogramas:
    # el BLAST es el que se lleva el tiempo
    ventana.en_progreso(Progreso("qc", 13, 26, "  archivo.ab1 ..."))
    assert ventana.barra.value() == 5
    assert "calidad" in ventana.etiqueta_etapa.text()
    ventana.en_progreso(Progreso("qc", 26, 26))
    assert ventana.barra.value() == 10
    ventana.en_progreso(Progreso("blast", 48, 96))
    assert ventana.barra.value() == 58
    assert "NCBI" in ventana.etiqueta_etapa.text()
    ventana.en_progreso(Progreso("informes", 1, 1))
    assert ventana.barra.value() == 100


def test_la_linea_de_estado_dice_que_esta_haciendo_y_desde_cuando(ventana):
    ventana.en_progreso(
        Progreso("blast", 44, 96, detalle="lote 2 de 3 · esperando respuesta de NCBI")
    )
    assert ventana.etiqueta_estado.text() == (
        "BLAST · lote 2 de 3 · esperando respuesta de NCBI · 0s"
    )


def test_el_cronometro_corre_aunque_la_barra_no_se_mueva(ventana, monkeypatch):
    # es lo que dice que el programa está vivo durante la espera de NCBI
    reloj = iter([100.0, 100.0, 142.0, 142.0])
    monkeypatch.setattr("sanger_ui.ventana.time.monotonic", lambda: next(reloj))
    ventana.en_progreso(
        Progreso("blast", 0, 96, detalle="lote 1 de 2 · esperando respuesta de NCBI")
    )
    ventana._refrescar_estado()
    assert ventana.etiqueta_estado.text().endswith("· 42s")
    assert ventana.barra.value() == 20  # la barra no se movió, el reloj sí


def test_el_cronometro_vuelve_a_cero_cuando_empieza_otra_cosa(ventana, monkeypatch):
    reloj = iter([10.0, 10.0, 70.0, 70.0])
    monkeypatch.setattr("sanger_ui.ventana.time.monotonic", lambda: next(reloj))
    ventana.en_progreso(
        Progreso("blast", 0, 96, detalle="lote 1 de 2 · esperando respuesta de NCBI")
    )
    ventana.en_progreso(
        Progreso("blast", 48, 96, detalle="lote 2 de 2 · esperando respuesta de NCBI")
    )
    assert ventana.etiqueta_estado.text().endswith("lote 2 de 2 · esperando respuesta de NCBI · 0s")


def test_al_terminar_se_informa_cuanto_tardo(ventana, muestras):
    ventana.en_terminado(Resultado([], muestras, 165.0, 142.0))
    assert ventana.barra.value() == 100
    assert ventana.etiqueta_estado.text() == "Terminó en 2m 45s, de los cuales 2m 22s de BLAST"


def test_el_log_va_mostrando_lo_que_avisa_el_nucleo(ventana):
    ventana.en_log("primera línea\n")
    ventana.en_log("   enviando lote de 49 secuencias a NCBI (nt, megablast) ...")
    ventana.en_log(" 143 s\n")
    assert ventana.log.toPlainText().splitlines() == [
        "primera línea",
        "   enviando lote de 49 secuencias a NCBI (nt, megablast) ... 143 s",
    ]


def test_al_terminar_se_llena_la_tabla_y_se_resume(ventana, muestras):
    ventana.en_terminado(Resultado([], muestras, 12.0, 0.0))
    assert ventana.modelo.rowCount() == 3
    assert ventana.tabs.currentIndex() == 2  # pasa a la pestaña de resultados
    assert ventana.estado.text() == "Listo: 1 confiables, 1 dudosas, 1 rechazadas."
    assert ventana.b_analizar.isEnabled() and not ventana.b_cancelar.isEnabled()


def test_cancelar_no_es_un_error(ventana, monkeypatch):
    monkeypatch.setattr(
        "sanger_ui.ventana.QMessageBox.critical",
        lambda *a, **k: pytest.fail("cancelar no tiene que mostrar un cartel de error"),
    )
    ventana.en_error(Cancelado("cancelado mientras se leían los cromatogramas"))
    assert "Cancelado" in ventana.estado.text()
    assert ventana.b_analizar.isEnabled()


def test_un_error_de_verdad_se_muestra(ventana, monkeypatch):
    mostrados = []
    monkeypatch.setattr(
        "sanger_ui.ventana.QMessageBox.critical", lambda *a, **k: mostrados.append(a[2])
    )
    ventana.en_error(RuntimeError("se rompió algo"))
    assert mostrados == ["se rompió algo"]


def test_las_preferencias_se_guardan_y_se_vuelven_a_cargar(app, tmp_path, monkeypatch):
    archivo = tmp_path / "config.json"
    monkeypatch.setattr(preferencias, "ARCHIVO", archivo)
    v = Ventana(prefs={})
    v.v_email.setText("alguien@ejemplo.com")
    v.v_entrada.setText(str(tmp_path / "ab1"))
    v.v_preset.setCurrentText("ITS hongos")
    v.guardar_preferencias()
    v.close()

    guardadas = preferencias.cargar(archivo)
    assert guardadas["email"] == "alguien@ejemplo.com"
    otra = Ventana(prefs=guardadas)
    assert otra.v_email.text() == "alguien@ejemplo.com"
    assert otra.v_preset.currentText() == "ITS hongos"
    otra.close()


def test_preferencias_rotas_no_frenan_el_programa(tmp_path):
    roto = tmp_path / "config.json"
    roto.write_text("{ esto no es json", encoding="utf-8")
    assert preferencias.cargar(roto) == {}
    assert preferencias.cargar(tmp_path / "no_existe.json") == {}


# ----------------------------------------------------------------------------
# El hilo de trabajo
# ----------------------------------------------------------------------------


def test_el_worker_avisa_y_termina(app, tmp_path):
    entrada = armar_corrida(tmp_path / "ab1")
    worker = Worker(Parametros(entrada=entrada, salida=tmp_path / "res", no_blast=True))
    avisos, lineas, terminados = [], [], []
    worker.progreso.connect(avisos.append)
    worker.log.connect(lineas.append)
    worker.terminado.connect(terminados.append)
    worker.error.connect(lambda e: pytest.fail(f"no debería fallar: {e}"))
    worker.run()  # sin start(): corre acá mismo, sin hilo, para poder verificarlo

    assert len(terminados) == 1 and len(terminados[0].muestras) == 16
    assert {a.etapa for a in avisos} >= {"qc", "clasificacion", "informes"}
    assert "Encontré 26 cromatogramas" in "".join(lineas)


def test_la_ventana_produce_lo_mismo_que_la_linea_de_comandos(app, tmp_path, monkeypatch, capsys):
    """
    La prueba que pide el BRIEFING §9 para esta fase, automatizada: la ventana
    no puede producir otra cosa que la línea de comandos, porque las dos son
    clientes del mismo pipeline.
    """
    monkeypatch.setattr(preferencias, "ARCHIVO", tmp_path / "config.json")
    entrada = armar_corrida(tmp_path / "ab1")
    cli_main(["-i", str(entrada), "-o", str(tmp_path / "por_consola"), "--no-blast"])
    capsys.readouterr()  # lo que imprimió la consola no interesa acá

    monkeypatch.setattr(cache_local, "raiz", lambda: tmp_path / "cache")
    v = Ventana(prefs={})
    v.v_entrada.setText(str(entrada))
    v.v_noblast.setChecked(True)
    v.correr()
    assert v.worker.wait(120_000), "el análisis de la ventana no terminó"
    app.processEvents()  # entrega las señales que quedaron en la cola

    assert v.modelo.rowCount() == 16  # la tabla quedó cargada
    assert "10 confiables, 3 dudosas, 3 rechazadas" in v.estado.text()

    # y exportando desde la ventana salen los mismos archivos que por consola
    _exportar_a(monkeypatch, v, tmp_path / "por_ventana")
    assert paridad.comparar_carpetas(tmp_path / "por_consola", tmp_path / "por_ventana") == []
    v.exportado = True
    v.close()


def _exportar_a(monkeypatch, ventana, destino, cuales=None):
    """Aprieta 'Exportar…' respondiendo el diálogo sin abrirlo."""
    from PySide6.QtWidgets import QDialog

    class DialogoFalso:
        DialogCode = QDialog.DialogCode

        def __init__(self, *a, **k):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def destino(self):
            return destino

        def elegidos(self):
            return list(cuales) if cuales else list(TODOS)

    monkeypatch.setattr("sanger_ui.ventana.DialogoExportar", DialogoFalso)
    ventana.exportar()


def test_exportar_sin_resultados_avisa(ventana, monkeypatch):
    avisos = []
    monkeypatch.setattr(
        "sanger_ui.ventana.QMessageBox.information", lambda *a, **k: avisos.append(a[1])
    )
    ventana.exportar()
    assert avisos == ["Todavía no hay resultados"]


def test_exportar_escribe_lo_elegido_y_lo_recuerda(ventana, muestras, tmp_path, monkeypatch):
    ventana.params = Parametros(entrada=tmp_path, salida=None, no_blast=True)
    ventana.en_terminado(Resultado([], muestras, 1.0, 0.0))
    assert not ventana.exportado  # hay algo sin guardar

    destino = tmp_path / "exportado"
    _exportar_a(monkeypatch, ventana, destino, cuales=("04", "00"))
    assert sorted(p.name for p in destino.iterdir()) == ["00_resumen.txt", "04_resultados.csv"]
    assert ventana.exportado
    assert ventana.ultima_exportacion == str(destino)
    assert ventana.preferencias_actuales()["exportacion"] == str(destino)
    assert "2 archivos exportados" in ventana.etiqueta_exportacion.text()


def test_avisa_antes_de_perder_resultados_sin_exportar(ventana, muestras, tmp_path, monkeypatch):
    """Una corrida con BLAST puede costar veinte minutos: no se pierde por un clic."""
    ventana.en_terminado(Resultado([], muestras, 1.0, 0.0))
    preguntas = []

    def responder(*a, **k):
        preguntas.append(a[1])
        return QMessageBox.StandardButton.No  # "no, no quiero perderlos"

    monkeypatch.setattr("sanger_ui.ventana.QMessageBox.question", responder)
    ventana.v_entrada.setText(str(tmp_path))
    ventana.v_noblast.setChecked(True)
    ventana.correr()
    assert preguntas == ["Hay resultados sin exportar"]
    assert ventana.worker is None  # no arrancó otra corrida

    evento = _EventoFalso()
    ventana.closeEvent(evento)
    assert evento.ignorado and len(preguntas) == 2


def test_despues_de_exportar_ya_no_pregunta(ventana, muestras, tmp_path, monkeypatch):
    ventana.params = Parametros(entrada=tmp_path, salida=None, no_blast=True)
    ventana.en_terminado(Resultado([], muestras, 1.0, 0.0))
    _exportar_a(monkeypatch, ventana, tmp_path / "exportado")
    monkeypatch.setattr(
        "sanger_ui.ventana.QMessageBox.question",
        lambda *a, **k: pytest.fail("no debería preguntar: ya está exportado"),
    )
    evento = _EventoFalso()
    ventana.closeEvent(evento)
    assert not evento.ignorado


class _EventoFalso:
    def __init__(self):
        self.ignorado = False

    def ignore(self):
        self.ignorado = True

    def accept(self):
        pass


def test_el_dialogo_de_exportacion_viene_todo_marcado(app, tmp_path):
    dialogo = DialogoExportar(destino_sugerido=str(tmp_path))
    assert dialogo.elegidos() == list(TODOS)
    assert dialogo.destino() == tmp_path
    dialogo.casillas["05"].setChecked(False)
    assert "05" not in dialogo.elegidos()
    assert dialogo.casillas["04"].text().startswith(ARCHIVOS["04"])
    dialogo.close()


def test_el_dialogo_sin_carpeta_no_devuelve_destino(app):
    dialogo = DialogoExportar()
    assert dialogo.destino() is None
    dialogo.close()


def test_el_worker_se_cancela(app, tmp_path):
    entrada = armar_corrida(tmp_path / "ab1")
    worker = Worker(Parametros(entrada=entrada, salida=tmp_path / "res", no_blast=True))
    errores = []
    worker.error.connect(errores.append)
    worker.terminado.connect(lambda r: pytest.fail("no debería terminar: se canceló"))
    worker.cancelar()
    worker.run()

    assert len(errores) == 1 and isinstance(errores[0], Cancelado)
    assert not (tmp_path / "res" / "04_resultados.csv").exists()
