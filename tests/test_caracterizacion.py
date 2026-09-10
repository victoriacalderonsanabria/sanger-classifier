"""
Tests de caracterización del script original clasificar_sanger.py.

Por qué existen: en la fase 0 el código no se toca, pero la fase 1 lo va a
partir en módulos. Estos tests fijan lo que el script hace HOY, con datos
sintéticos de semilla fija, para que cualquier cambio de comportamiento en la
fase 1 salte acá antes de llegar a los 192 .ab1 reales. Si un test de estos
falla después de un refactor, el refactor está mal, no el test.
"""

import csv
import random
from types import SimpleNamespace

import pytest
from Bio.Seq import Seq

import clasificar_sanger as cs

SEMILLA = 20260910


def _secuencia(largo: int, semilla: int = SEMILLA) -> str:
    """Secuencia de ADN al azar pero reproducible (siempre la misma)."""
    rng = random.Random(semilla)
    return "".join(rng.choice("ACGT") for _ in range(largo))


def _rc(seq: str) -> str:
    return str(Seq(seq).reverse_complement())


# ----------------------------------------------------------------------------
# recorte_mott
# ----------------------------------------------------------------------------


def test_recorte_mott_sin_calidades_devuelve_vacio():
    assert cs.recorte_mott([], 20) == (0, 0)


def test_recorte_mott_lectura_toda_buena_no_recorta():
    assert cs.recorte_mott([40] * 50, 20) == (0, 50)


def test_recorte_mott_saca_extremos_malos():
    qual = [5] * 10 + [40] * 30 + [5] * 10
    assert cs.recorte_mott(qual, 20) == (10, 40)


def test_recorte_mott_tolera_una_base_dudosa_aislada():
    # una Q10 suelta en medio de un tramo Q40 no corta la lectura
    qual = [40] * 20 + [10] + [40] * 20
    assert cs.recorte_mott(qual, 20) == (0, 41)


def test_recorte_mott_umbral_laxo_conserva_mas():
    qual = [5] * 5 + [17] * 20 + [40] * 30
    ini_estricto, fin_estricto = cs.recorte_mott(qual, 20)
    ini_laxo, fin_laxo = cs.recorte_mott(qual, 15)
    assert fin_laxo - ini_laxo > fin_estricto - ini_estricto


# ----------------------------------------------------------------------------
# metricas y cumple_estandar
# ----------------------------------------------------------------------------


def test_metricas_lectura_vacia():
    assert cs.metricas("", []) == dict(largo=0, q_media=0.0, pct_q20=0.0, n_amb=0)


def test_metricas_valores_y_redondeo():
    m = cs.metricas("ACGTN", [10, 20, 30, 40, 19])
    assert m == dict(largo=5, q_media=23.8, pct_q20=60.0, n_amb=1)


def test_metricas_ambiguedades_en_minuscula():
    assert cs.metricas("acgtr", [30] * 5)["n_amb"] == 1


def _umbrales(largo_min=100, q_media_min=25.0, pct_q20_min=80.0):
    # hoy cumple_estandar recibe el Namespace entero de argparse (ver BRIEFING
    # §2.1a); en la fase 1 esto pasa a ser Parametros
    return SimpleNamespace(largo_min=largo_min, q_media_min=q_media_min, pct_q20_min=pct_q20_min)


def test_cumple_estandar_en_el_limite():
    ok, m = cs.cumple_estandar("A" * 100, [25] * 100, _umbrales())
    assert ok and m["largo"] == 100


def test_cumple_estandar_un_pb_menos_no_alcanza():
    ok, _ = cs.cumple_estandar("A" * 99, [40] * 99, _umbrales())
    assert not ok


def test_cumple_estandar_q_media_baja_no_alcanza():
    ok, _ = cs.cumple_estandar("A" * 150, [24] * 150, _umbrales())
    assert not ok


def test_cumple_estandar_bloque_malo_escondido_no_alcanza():
    # media alta pero solo 70 % de bases Q>=20: el porcentaje la frena
    qual = [40] * 105 + [5] * 45
    ok, m = cs.cumple_estandar("A" * 150, qual, _umbrales())
    assert m["q_media"] >= 25 and m["pct_q20"] == 70.0 and not ok


# ----------------------------------------------------------------------------
# muestra_y_sentido
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("M12_F.ab1", ("M12", "F")),
        ("M12-R.ab1", ("M12", "R")),
        ("Cepa3_27F_A01.ab1", ("Cepa3", "F")),
        ("H7-ITS4.ab1", ("H7", "R")),
        ("999-F-2026-01-01-00-00-00.ab1", ("999", "F")),
        ("F_M12.ab1", ("M12", "F")),
        ("M3_R.AB1", ("M3", "R")),
        ("M5_T7.ab1", ("M5", "F")),
        ("A-B_F.ab1", ("A_B", "F")),
        ("R2_F.ab1", ("R2", "F")),
        ("M_R_F.ab1", ("M", "R")),
        ("muestra_sola.ab1", ("muestra_sola", "?")),
    ],
)
def test_muestra_y_sentido(nombre, esperado):
    assert cs.muestra_y_sentido(nombre) == esperado


def test_muestra_y_sentido_primers_extra():
    assert cs.muestra_y_sentido("X_MiF.ab1") == ("X_MiF", "?")
    assert cs.muestra_y_sentido("X_MiF.ab1", extra_f=["MiF"]) == ("X", "F")
    assert cs.muestra_y_sentido("X_mir.ab1", extra_r=["MiR"]) == ("X", "R")


# ----------------------------------------------------------------------------
# consenso_fr
# ----------------------------------------------------------------------------


def test_consenso_fr_reconstruye_la_secuencia_completa():
    verdad = _secuencia(300)
    f, r = verdad[:250], _rc(verdad[50:])
    c = cs.consenso_fr(f, [40] * len(f), r, [40] * len(r))
    assert c["ok"]
    assert c["seq"] == verdad
    assert len(c["qual"]) == 300
    assert (c["solap"], c["discrepancias"], c["conflictos"]) == (200, 0, 0)


def test_consenso_fr_gana_la_base_de_mayor_calidad():
    verdad = _secuencia(300)
    f = list(verdad[:250])
    f[100] = next(b for b in "ACGT" if b != verdad[100])  # error de F en una base mala
    qual_f = [40] * 250
    qual_f[100] = 10
    r = _rc(verdad[50:])
    c = cs.consenso_fr("".join(f), qual_f, r, [40] * len(r))
    assert c["seq"] == verdad
    assert c["qual"][100] == 30  # Q de la ganadora menos Q de la perdedora
    assert (c["discrepancias"], c["conflictos"]) == (1, 0)


def test_consenso_fr_cuenta_conflicto_si_ambas_bases_son_buenas():
    verdad = _secuencia(300)
    f = list(verdad[:250])
    f[100] = next(b for b in "ACGT" if b != verdad[100])
    r = _rc(verdad[50:])
    c = cs.consenso_fr("".join(f), [40] * 250, r, [40] * len(r))
    assert (c["discrepancias"], c["conflictos"]) == (1, 1)


def test_consenso_fr_solapamiento_insuficiente():
    verdad = _secuencia(300)
    f, r = verdad[:150], _rc(verdad[120:])
    c = cs.consenso_fr(f, [40] * len(f), r, [40] * len(r), min_solap=50)
    assert not c["ok"]
    assert c["solap"] == 30
    assert c["seq"] == ""


# ----------------------------------------------------------------------------
# comparar_con_confiables y veredicto_comparacion
# ----------------------------------------------------------------------------


def test_comparar_con_confiables_detecta_lectura_invertida():
    verdad = _secuencia(200)
    dudosa = list(_rc(verdad[20:180]))
    qual = [30] * len(dudosa)
    dudosa[80] = next(b for b in "ACGT" if b != dudosa[80])  # desajuste en base mala
    qual[80] = 8
    refs = [dict(muestra="REF1", seq=verdad), dict(muestra="OTRA", seq=_secuencia(200, 7))]
    d = cs.comparar_con_confiables("".join(dudosa), qual, refs)
    assert d["ref"] == "REF1" and d["orient"] == "rc"
    assert (d["bases_buenas"], d["desaj_buenas"], d["ident_buenas"]) == (159, 0, 100.0)
    assert (d["bases_malas"], d["desaj_malas"]) == (1, 1)


@pytest.mark.parametrize(
    ("d", "esperado"),
    [
        (None, "sin_coincidencia_util"),
        (dict(ref="M9", bases_buenas=39, ident_buenas=100.0), "sin_coincidencia_util"),
        (
            dict(ref="M9", bases_buenas=78, ident_buenas=100.0),
            "coincide con M9 (100.0% en 78 bases buenas)",
        ),
        (
            dict(ref="M9", bases_buenas=40, ident_buenas=98.0),
            "coincide con M9 (98.0% en 40 bases buenas)",
        ),
        (
            dict(ref="M9", bases_buenas=78, ident_buenas=95.0),
            "parecida a M9 (95.0% en bases buenas)",
        ),
        (
            dict(ref="M9", bases_buenas=78, ident_buenas=90.4),
            "distinta de las confiables (mejor: M9, 90.4%)",
        ),
    ],
)
def test_veredicto_comparacion(d, esperado):
    assert cs.veredicto_comparacion(d) == esperado


# ----------------------------------------------------------------------------
# resumir_hits e interpretar
# ----------------------------------------------------------------------------


def _alineamiento(titulo, accession, identidades, largo_aln, evalue=1e-50):
    hsp = SimpleNamespace(identities=identidades, align_length=largo_aln, expect=evalue)
    return SimpleNamespace(hit_def=titulo, title=titulo, accession=accession, hsps=[hsp])


def test_resumir_hits_una_fila_por_especie_y_maximo_tres():
    rec = SimpleNamespace(
        alignments=[
            _alineamiento("Bos taurus isolate A cytochrome oxidase I", "AC1", 198, 200),
            _alineamiento("Bos taurus isolate B cytochrome oxidase I", "AC2", 197, 200),
            _alineamiento("Bos indicus voucher X", "AC3", 196, 200),
            # sin "Género especie" al principio: se usan los primeros 40 caracteres
            _alineamiento("uncultured eukaryote clone MX12 mitochondrial COI", "AC4", 150, 200),
            _alineamiento("Bubalus bubalis mitochondrion", "AC5", 190, 200),
        ]
    )
    hits = cs.resumir_hits(rec, largo_query=250)
    assert [h["especie"] for h in hits] == [
        "Bos taurus",
        "Bos indicus",
        "uncultured eukaryote clone MX12 mitochon",
    ]
    assert hits[0] == dict(
        especie="Bos taurus",
        accession="AC1",
        identidad=99.0,
        cobertura=80.0,
        evalue=1e-50,
        titulo="Bos taurus isolate A cytochrome oxidase I",
    )


def test_resumir_hits_sin_registro():
    assert cs.resumir_hits(None, 100) == []


def _hit(especie, identidad, cobertura=100.0, titulo=None):
    return dict(especie=especie, identidad=identidad, cobertura=cobertura, titulo=titulo or especie)


@pytest.mark.parametrize(
    ("hits", "esperado"),
    [
        ([], "sin_hit"),
        ([_hit("Bos taurus", 99.5, 50.0)], "cobertura_baja (50.0%): hit parcial, revisar"),
        (
            [_hit("Bos taurus", 90.0)],
            "identidad_baja (90.0% < 97.0%): especie no representada o secuencia con errores",
        ),
        (
            [_hit("Bos taurus", 99.6), _hit("Bos indicus", 99.4)],
            "identificado a nivel de género (Bos taurus / Bos indicus)",
        ),
        (
            [_hit("Bos taurus", 99.6), _hit("Bubalus bubalis", 99.0)],
            "ambiguo: dos especies con identidad similar",
        ),
        (
            [_hit("Homo sapiens", 100.0, titulo="Homo sapiens mitochondrion, complete genome")],
            "humano: verificar si es esperado o contaminación",
        ),
        ([_hit("Canis lupus", 100.0), _hit("Vulpes vulpes", 99.0)], "identificado"),
        ([_hit("Canis lupus", 99.0)], "identificado"),
    ],
)
def test_interpretar(hits, esperado):
    assert cs.interpretar(hits, 97.0, 80.0) == esperado


# ----------------------------------------------------------------------------
# escribir_csv
# ----------------------------------------------------------------------------


def test_escribir_csv_formato_excel_en_espanol(tmp_path):
    ruta = tmp_path / "x.csv"
    filas = [dict(a="M1", b=1.5, c=2, sobra="no va"), dict(a="M2")]
    cs.escribir_csv(ruta, ["a", "b", "c"], filas)
    # \ufeff es la marca BOM: sin ella Excel no reconoce los acentos
    assert ruta.read_bytes() == "\ufeffa;b;c\r\nM1;1,5;2\r\nM2;;\r\n".encode()


def test_escribir_csv_formato_internacional(tmp_path):
    ruta = tmp_path / "x.csv"
    cs.escribir_csv(ruta, ["a", "b"], [dict(a="M1", b=1.5)], sep=",", decimal_coma=False)
    assert ruta.read_bytes() == b"a,b\r\nM1,1.5\r\n"


def test_escribir_csv_lista_interna_no_rompe_columnas(tmp_path):
    ruta = tmp_path / "x.csv"
    archivos = cs.SEP_INTERNO.join(["M1_F.ab1", "M1_R.ab1"])
    cs.escribir_csv(ruta, ["muestra", "archivos"], [dict(muestra="M1", archivos=archivos)])
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.reader(fh, delimiter=";"))
    assert filas == [["muestra", "archivos"], ["M1", "M1_F.ab1 | M1_R.ab1"]]
