"""
Tests de scripts/paridad.py, el comparador que decide si una fase cambió la
ciencia. Si este comparador tuviera un falso "OK", todo el esquema de paridad
dejaría de proteger; por eso se prueba con carpetas sintéticas.
"""

import pytest

import paridad

CONTENIDO = {
    "01_QC_lecturas.csv": "archivo;muestra\r\nM1_F.ab1;M1\r\n",
    "02_confiables.fasta": ">M1 CONSENSO_F+R len=4\nACGT\n",
    "03_dudosas.fasta": "",
    "04_resultados.csv": "muestra;grupo\r\nM1;CONFIABLE\r\n",
    "05_hits_completos.json": "{}",
}
RESUMEN = "Muestras: 1\nTiempo total: {t}  (BLAST: 0 s; QC, consenso e informes: {t})"


def _corrida(carpeta, tiempo="3 s", **cambios):
    carpeta.mkdir()
    for nombre, texto in {**CONTENIDO, **cambios}.items():
        (carpeta / nombre).write_bytes(texto.encode("utf-8"))
    (carpeta / "00_resumen.txt").write_text(RESUMEN.format(t=tiempo), encoding="utf-8")
    return carpeta


def test_corridas_identicas_dan_paridad(tmp_path):
    ref, nue = _corrida(tmp_path / "ref"), _corrida(tmp_path / "nue")
    assert paridad.comparar_carpetas(ref, nue) == []


def test_el_tiempo_de_ejecucion_no_rompe_la_paridad(tmp_path):
    ref, nue = _corrida(tmp_path / "ref", "3 s"), _corrida(tmp_path / "nue", "1 min 34 s")
    assert paridad.comparar_carpetas(ref, nue) == []


def test_un_cambio_en_resultados_rompe_la_paridad(tmp_path):
    ref = _corrida(tmp_path / "ref")
    nue = _corrida(tmp_path / "nue", **{"04_resultados.csv": "muestra;grupo\r\nM1;DUDOSA\r\n"})
    diferencias = paridad.comparar_carpetas(ref, nue)
    assert len(diferencias) == 1
    assert diferencias[0].startswith("04_resultados.csv")
    assert "DUDOSA" in diferencias[0]


def test_un_cambio_invisible_de_fin_de_linea_rompe_la_paridad(tmp_path):
    ref = _corrida(tmp_path / "ref")
    nue = _corrida(tmp_path / "nue", **{"01_QC_lecturas.csv": "archivo;muestra\nM1_F.ab1;M1\n"})
    assert paridad.comparar_carpetas(ref, nue)


def test_un_cambio_en_el_resumen_rompe_la_paridad(tmp_path):
    ref = _corrida(tmp_path / "ref")
    nue = _corrida(tmp_path / "nue")
    (nue / "00_resumen.txt").write_text("Muestras: 2\nTiempo total: 3 s", encoding="utf-8")
    assert paridad.comparar_carpetas(ref, nue)[0].startswith("00_resumen.txt")


def test_un_archivo_faltante_rompe_la_paridad(tmp_path):
    ref, nue = _corrida(tmp_path / "ref"), _corrida(tmp_path / "nue")
    (nue / "03_dudosas.fasta").unlink()
    assert paridad.comparar_carpetas(ref, nue) == ["03_dudosas.fasta: falta en la corrida nueva"]


def test_consola_ignora_tiempo_y_ruta_de_salida(tmp_path):
    ref, nue = tmp_path / "ref.txt", tmp_path / "nue.txt"
    ref.write_text("M1 CONFIABLE\nTiempo total: 3 s\nListo. Resultados en C:\\a", encoding="utf-8")
    nue.write_text("M1 CONFIABLE\nTiempo total: 9 s\nListo. Resultados en C:\\b", encoding="utf-8")
    assert paridad.comparar_consolas(ref, nue) == []


def test_consola_detecta_mensaje_distinto(tmp_path):
    ref, nue = tmp_path / "ref.txt", tmp_path / "nue.txt"
    ref.write_text("M1 CONFIABLE\n", encoding="utf-8")
    nue.write_text("M1 DUDOSA\n", encoding="utf-8")
    assert paridad.comparar_consolas(ref, nue)


@pytest.mark.parametrize(("iguales", "codigo"), [(True, 0), (False, 1)])
def test_main_devuelve_codigo_de_salida(tmp_path, iguales, codigo):
    ref = _corrida(tmp_path / "ref")
    cambios = {} if iguales else {"02_confiables.fasta": ">M1\nAAAA\n"}
    nue = _corrida(tmp_path / "nue", **cambios)
    assert paridad.main([str(ref), str(nue)]) == codigo
