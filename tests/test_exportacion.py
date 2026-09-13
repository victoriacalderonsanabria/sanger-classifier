"""
Exportación bajo demanda (FEEDBACK_FASE3 punto 3).

Lo que se prueba acá es la condición más dura del pedido: los archivos que
exporta la ventana tienen que ser **byte a byte** los mismos que escribe la
línea de comandos. Por eso los dos caminos usan el mismo escritor.
"""

import filecmp
import io
from contextlib import redirect_stdout

import pytest

from sanger.cli import main as cli_main
from sanger.config import Parametros
from sanger.io.informes import ARCHIVOS, TODOS, escribir_informes
from sanger.modelos import Grupo
from sanger.pipeline import ejecutar
from tests.sintetico.corrida import armar_corrida, preparar_cache_blast


@pytest.fixture(scope="module")
def entrada(tmp_path_factory):
    return armar_corrida(tmp_path_factory.mktemp("corrida") / "ab1")


# ----------------------------------------------------------------------------
# Correr sin escribir
# ----------------------------------------------------------------------------


def test_sin_carpeta_de_salida_no_se_escribe_nada(entrada, tmp_path):
    params = Parametros(entrada=entrada, salida=None, no_blast=True)
    resultado = ejecutar(params)
    assert list(tmp_path.iterdir()) == []
    assert len(resultado.muestras) == 16


def test_el_resultado_queda_completo_en_memoria(entrada, tmp_path, fixtures_blast):
    # hace falta para poder exportar después: secuencias y hits incluidos
    cache = tmp_path / "cache"
    preparar_cache_blast(cache.parent, fixtures_blast)
    (cache.parent / "blast_xml").rename(cache)
    params = Parametros(entrada=entrada, salida=None, carpeta_cache=cache, no_blast=False)
    resultado = ejecutar(params)

    confiables = resultado.del_grupo(Grupo.CONFIABLE)
    assert all(m.secuencia for m in confiables)
    assert all(len(lec.qual) == lec.largo_crudo for lec in resultado.lecturas)
    con_hits = [m for m in resultado.muestras if m.hits]
    assert con_hits and all(m.hits[0].especie for m in con_hits)
    assert resultado.con_blast is True


def test_el_cache_vive_donde_se_le_diga(entrada, tmp_path, fixtures_blast):
    cache = tmp_path / "otro_lado" / "cache"
    cache.mkdir(parents=True)
    preparar_cache_blast(tmp_path, fixtures_blast)
    for archivo in (tmp_path / "blast_xml").iterdir():
        archivo.rename(cache / archivo.name)
    params = Parametros(entrada=entrada, salida=None, carpeta_cache=cache, no_blast=False)
    resultado = ejecutar(params)
    assert [m for m in resultado.muestras if m.hits]  # se leyó de ahí


def test_sin_salida_y_sin_cache_no_se_puede_hacer_blast(entrada):
    with pytest.raises(ValueError, match="carpeta_cache"):
        Parametros(entrada=entrada, salida=None)


def test_sin_salida_y_sin_blast_no_hace_falta_cache(entrada):
    params = Parametros(entrada=entrada, salida=None, no_blast=True)
    assert params.cache is None and not params.escribe_informes


def test_con_salida_el_cache_va_adentro_como_siempre(entrada):
    params = Parametros(entrada=entrada, salida="resultados")
    assert params.cache.as_posix().endswith("resultados/blast_xml")
    assert params.escribe_informes


# ----------------------------------------------------------------------------
# Exportar
# ----------------------------------------------------------------------------


def test_exportar_produce_los_mismos_bytes_que_la_linea_de_comandos(entrada, tmp_path, capsys):
    """
    La condición 3.4 del feedback: mismo `;`, mismo BOM, mismos decimales con
    coma, mismo orden de columnas, mismo ` | ` interno.
    """
    por_consola = tmp_path / "por_consola"
    cli_main(["-i", str(entrada), "-o", str(por_consola), "--no-blast"])
    capsys.readouterr()

    # la ventana: corre sin escribir y exporta después
    resultado = ejecutar(Parametros(entrada=entrada, salida=None, no_blast=True))
    exportado = tmp_path / "exportado"
    escritos = escribir_informes(resultado, exportado)

    assert [r.name for r in escritos] == [ARCHIVOS[c] for c in TODOS]
    for cual in TODOS:
        nombre = ARCHIVOS[cual]
        assert filecmp.cmp(por_consola / nombre, exportado / nombre, shallow=False), nombre


def test_exportar_con_blast_tambien_da_lo_mismo(entrada, tmp_path, fixtures_blast, capsys):
    por_consola = tmp_path / "por_consola"
    preparar_cache_blast(por_consola, fixtures_blast)
    cli_main(["-i", str(entrada), "-o", str(por_consola)])
    capsys.readouterr()

    cache = tmp_path / "cache"
    preparar_cache_blast(tmp_path / "tmp", fixtures_blast)
    (tmp_path / "tmp" / "blast_xml").rename(cache)
    consola = io.StringIO()
    with redirect_stdout(consola):
        resultado = ejecutar(Parametros(entrada=entrada, salida=None, carpeta_cache=cache))
    exportado = tmp_path / "exportado"
    escribir_informes(resultado, exportado)

    for cual in ("01", "02", "03", "04", "05"):
        nombre = ARCHIVOS[cual]
        assert filecmp.cmp(por_consola / nombre, exportado / nombre, shallow=False), nombre

    # el resumen solo difiere en la línea del tiempo de ejecución
    def sin_tiempo(ruta):
        return [x for x in ruta.read_text(encoding="utf-8").splitlines() if "Tiempo total" not in x]

    assert sin_tiempo(por_consola / ARCHIVOS["00"]) == sin_tiempo(exportado / ARCHIVOS["00"])


def test_se_puede_exportar_solo_algunos(entrada, tmp_path):
    resultado = ejecutar(Parametros(entrada=entrada, salida=None, no_blast=True))
    destino = tmp_path / "solo_dos"
    escritos = escribir_informes(resultado, destino, cuales=("04", "00"))
    assert [r.name for r in escritos] == ["04_resultados.csv", "00_resumen.txt"]
    assert sorted(p.name for p in destino.iterdir()) == [
        "00_resumen.txt",
        "04_resultados.csv",
    ]


def test_el_formato_internacional_tambien_se_respeta(entrada, tmp_path):
    resultado = ejecutar(Parametros(entrada=entrada, salida=None, no_blast=True))
    destino = tmp_path / "internacional"
    escribir_informes(resultado, destino, sep=",", decimal_coma=False, cuales=("04",))
    crudo = (destino / "04_resultados.csv").read_bytes()
    assert not crudo.startswith(b"\xef\xbb\xbf")  # sin BOM
    assert b";" not in crudo.split(b"\r\n")[0]


def test_un_informe_que_no_existe(entrada, tmp_path):
    resultado = ejecutar(Parametros(entrada=entrada, salida=None, no_blast=True))
    with pytest.raises(KeyError):
        escribir_informes(resultado, tmp_path / "x", cuales=("99",))
