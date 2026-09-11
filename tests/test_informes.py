"""Formato de los informes: CSV para Excel en español, FASTA, JSON y resumen."""

import csv
import json

from sanger.io.informes import (
    COLUMNAS_RESULTADOS,
    escribir_csv,
    escribir_fasta,
    escribir_hits_json,
    filas_resultados,
    formatear_duracion,
    texto_resumen,
)
from sanger.modelos import SEP_INTERNO, Grupo, Hit, Muestra


def test_escribir_csv_formato_excel_en_espanol(tmp_path):
    ruta = tmp_path / "x.csv"
    filas = [dict(a="M1", b=1.5, c=2, sobra="no va"), dict(a="M2")]
    escribir_csv(ruta, ["a", "b", "c"], filas)
    # \ufeff es la marca BOM: sin ella Excel no reconoce los acentos
    assert ruta.read_bytes() == "\ufeffa;b;c\r\nM1;1,5;2\r\nM2;;\r\n".encode()


def test_escribir_csv_formato_internacional(tmp_path):
    ruta = tmp_path / "x.csv"
    escribir_csv(ruta, ["a", "b"], [dict(a="M1", b=1.5)], sep=",", decimal_coma=False)
    assert ruta.read_bytes() == b"a,b\r\nM1,1.5\r\n"


def test_escribir_csv_lista_interna_no_rompe_columnas(tmp_path):
    ruta = tmp_path / "x.csv"
    archivos = SEP_INTERNO.join(["M1_F.ab1", "M1_R.ab1"])
    escribir_csv(ruta, ["muestra", "archivos"], [dict(muestra="M1", archivos=archivos)])
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh, delimiter=";"))
    assert filas == [["muestra", "archivos"], ["M1", "M1_F.ab1 | M1_R.ab1"]]


def _muestras():
    hit = Hit("Bos taurus", "XX1", 99.5, 100.0, 2e-100, "Bos taurus COI")
    return [
        Muestra("Z9", ("Z9_F.ab1",), motivos=["ninguna lectura con señal utilizable"]),
        Muestra(
            "B2", ("B2_F.ab1",), Grupo.DUDOSA, "SOLO_F", "ACGT", 4, 20.1, 50.0,
            motivos=["uno", "dos"], vs_confiables="sin_coincidencia_util", hits=[hit],
        ),
        Muestra(
            "A1", ("A1_F.ab1", "A1_R.ab1"), Grupo.CONFIABLE, "CONSENSO_F+R", "ACGT", 4, 38.2,
            100.0, 180, 2, 0, hits=[hit, hit], interpretacion="identificado",
        ),
    ]  # fmt: skip


def test_filas_resultados_orden_por_grupo_y_celdas_vacias():
    filas = filas_resultados(_muestras())
    assert [f["muestra"] for f in filas] == ["A1", "B2", "Z9"]
    assert list(filas[0]) == COLUMNAS_RESULTADOS
    a1, b2, z9 = filas
    assert (a1["solapamiento"], a1["accession_1"], a1["especie_2"]) == (180, "XX1", "Bos taurus")
    assert (b2["solapamiento"], b2["motivo"], b2["especie_2"]) == ("", "uno | dos", "")
    assert (z9["q_media"], z9["largo"], z9["vs_confiables"]) == ("", 0, "")
    assert a1["archivos"] == "A1_F.ab1 | A1_R.ab1"


def test_fasta_de_dudosas_lleva_el_motivo(tmp_path):
    ruta = tmp_path / "d.fasta"
    escribir_fasta(ruta, [_muestras()[1]], revisar=True)
    assert ruta.read_text().splitlines() == [">B2 SOLO_F len=4 REVISAR: uno | dos", "ACGT"]


def test_hits_json_solo_muestras_con_hits(tmp_path):
    ruta = tmp_path / "h.json"
    escribir_hits_json(ruta, _muestras())
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert list(datos) == ["B2", "A1"]
    assert datos["B2"][0]["especie"] == "Bos taurus"


def test_formatear_duracion():
    assert [formatear_duracion(s) for s in (0.4, 59.4, 60, 94.6)] == [
        "0 s",
        "59 s",
        "1 min 0 s",
        "1 min 35 s",
    ]


def test_resumen_cuenta_interpretaciones_sin_el_detalle():
    muestras = _muestras()
    muestras[1].interpretacion = "identidad_baja (91.2% < 97.0%): especie no representada"
    texto = texto_resumen([], muestras, True, 95.0, 60.0)
    assert "BLAST CONFIABLE: identificado=1" in texto
    assert "BLAST DUDOSA: identidad_baja=1" in texto
    assert texto.endswith(
        "Tiempo total: 1 min 35 s  (BLAST: 1 min 0 s; QC, consenso e informes: 35 s)"
    )
