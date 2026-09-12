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
from PySide6.QtWidgets import QApplication  # noqa: E402

import paridad  # noqa: E402
from sanger.cli import main as cli_main  # noqa: E402
from sanger.config import Parametros  # noqa: E402
from sanger.errores import Cancelado  # noqa: E402
from sanger.modelos import Grupo, Hit, Muestra, Progreso, Resultado  # noqa: E402
from sanger_ui import preferencias  # noqa: E402
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
    v = Ventana(prefs={})
    yield v
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
    ventana.v_salida.setText(str(tmp_path / "res"))
    ventana.v_email.setText("alguien@ejemplo.com")
    ventana.v_largo.setValue(300)
    ventana.v_largo_laxo.setValue(50)
    ventana.v_ident.setValue(98.7)
    ventana.v_lote.setValue(20)
    ventana.v_db.setCurrentText("mito")
    ventana.v_taxon.setCurrentText("Vertebrata[Organism]")
    p = ventana.parametros()
    assert p == Parametros(
        entrada=tmp_path, salida=tmp_path / "res", email="alguien@ejemplo.com",
        largo_min=300, largo_min_laxo=50, ident_min=98.7, lote=20, db="mito",
        taxon="Vertebrata[Organism]",
    )  # fmt: skip


def test_sin_filtro_taxonomico_no_se_manda_taxon(ventana, tmp_path):
    ventana.v_entrada.setText(str(tmp_path))
    assert ventana.v_taxon.currentText().startswith("(")
    assert ventana.parametros().taxon is None


def test_la_carpeta_de_resultados_se_propone_sola(ventana, tmp_path):
    ventana.v_entrada.setText(str(tmp_path / "ab1"))
    assert ventana.v_salida.text() == str(tmp_path / "ab1" / "resultados")


def test_el_preset_carga_los_umbrales(ventana):
    ventana.v_preset.setCurrentText("16S bacteriano")
    assert (ventana.v_largo.value(), ventana.v_ident.value()) == (300, 98.7)
    assert ventana.v_db.currentText() == "16S_ribosomal_RNA"


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


def test_la_barra_sigue_el_avance(ventana):
    ventana.en_progreso(Progreso("qc", 3, 26, "  archivo.ab1 ..."))
    assert (ventana.barra.value(), ventana.barra.maximum()) == (3, 26)
    assert "calidad" in ventana.etiqueta_etapa.text()
    ventana.en_progreso(Progreso("blast", 0, 0))
    assert ventana.barra.maximum() == 0  # sin total: barra indeterminada
    assert "NCBI" in ventana.etiqueta_etapa.text()


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

    v = Ventana(prefs={})
    v.v_entrada.setText(str(entrada))
    v.v_salida.setText(str(tmp_path / "por_ventana"))
    v.v_noblast.setChecked(True)
    v.correr()
    assert v.worker.wait(120_000), "el análisis de la ventana no terminó"
    app.processEvents()  # entrega las señales que quedaron en la cola

    assert paridad.comparar_carpetas(tmp_path / "por_consola", tmp_path / "por_ventana") == []
    assert v.modelo.rowCount() == 16  # y la tabla quedó cargada
    assert "10 confiables, 3 dudosas, 3 rechazadas" in v.estado.text()
    v.close()


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
