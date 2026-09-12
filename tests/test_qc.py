"""
Recorte de Mott, métricas, criterio estándar y diagnóstico de cada lectura.

Casos chicos armados a mano: acá se ve con números exactos qué hace cada regla.
Los que vienen de la fase 0 fijan el comportamiento del script original.
"""

from sanger.modelos import Senal
from sanger.qc.metricas import Metricas, clasificar_senal, cumple_estandar, metricas
from sanger.qc.recorte import recorte_mott
from tests.sintetico.generador import Perfil, leer, verdad
from tests.sintetico.lecturas import lectura

UMBRALES = dict(largo_min=100, q_media_min=25.0, pct_q20_min=80.0)

# ----------------------------------------------------------------------------
# recorte_mott
# ----------------------------------------------------------------------------


def test_recorte_mott_sin_calidades_devuelve_vacio():
    assert recorte_mott([], 20) == (0, 0)


def test_recorte_mott_lectura_toda_buena_no_recorta():
    assert recorte_mott([40] * 50, 20) == (0, 50)


def test_recorte_mott_saca_extremos_malos():
    qual = [5] * 10 + [40] * 30 + [5] * 10
    assert recorte_mott(qual, 20) == (10, 40)


def test_recorte_mott_tolera_una_base_dudosa_aislada():
    # una Q10 suelta en medio de un tramo Q40 no corta la lectura
    qual = [40] * 20 + [10] + [40] * 20
    assert recorte_mott(qual, 20) == (0, 41)


def test_recorte_mott_umbral_laxo_conserva_mas():
    qual = [5] * 5 + [17] * 20 + [40] * 30
    ini_estricto, fin_estricto = recorte_mott(qual, 20)
    ini_laxo, fin_laxo = recorte_mott(qual, 15)
    assert fin_laxo - ini_laxo > fin_estricto - ini_estricto


def test_recorte_mott_acepta_tuplas():
    assert recorte_mott((5, 40, 40, 5), 20) == (1, 3)


# ----------------------------------------------------------------------------
# metricas y cumple_estandar
# ----------------------------------------------------------------------------


def test_metricas_lectura_vacia():
    assert metricas("", []) == Metricas(largo=0, q_media=0.0, pct_q20=0.0, n_amb=0)


def test_metricas_valores_y_redondeo():
    assert metricas("ACGTN", [10, 20, 30, 40, 19]) == Metricas(
        largo=5, q_media=23.8, pct_q20=60.0, n_amb=1
    )


def test_metricas_ambiguedades_en_minuscula():
    assert metricas("acgtr", [30] * 5).n_amb == 1


def test_cumple_estandar_en_el_limite():
    ok, m = cumple_estandar("A" * 100, [25] * 100, **UMBRALES)
    assert ok and m.largo == 100


def test_cumple_estandar_un_pb_menos_no_alcanza():
    ok, _ = cumple_estandar("A" * 99, [40] * 99, **UMBRALES)
    assert not ok


def test_cumple_estandar_q_media_baja_no_alcanza():
    ok, _ = cumple_estandar("A" * 150, [24] * 150, **UMBRALES)
    assert not ok


def test_cumple_estandar_bloque_malo_escondido_no_alcanza():
    # media alta pero solo 70 % de bases Q>=20: el porcentaje la frena
    qual = [40] * 105 + [5] * 45
    ok, m = cumple_estandar("A" * 150, qual, **UMBRALES)
    assert m.q_media >= 25 and m.pct_q20 == 70.0 and not ok


def test_cumple_estandar_ya_no_necesita_argparse():
    # antes recibía el Namespace entero de la línea de comandos (BRIEFING §2.1a)
    ok, _ = cumple_estandar("A" * 300, [30] * 300, largo_min=300, q_media_min=25, pct_q20_min=80)
    assert ok


# ----------------------------------------------------------------------------
# clasificar_senal y evaluar_lectura
# ----------------------------------------------------------------------------


def test_senal_lectura_corta_es_sin_senal_aunque_sea_buena():
    assert clasificar_senal(149, 149, 149, largo_min=100, min_bases_q20=30) == Senal.SIN_SENAL


def test_senal_pocas_bases_q20_es_sin_senal():
    assert clasificar_senal(300, 29, 0, largo_min=100, min_bases_q20=30) == Senal.SIN_SENAL


def test_senal_buena_y_parcial_segun_el_recorte_estricto():
    assert clasificar_senal(300, 200, 100, largo_min=100, min_bases_q20=30) == Senal.BUENA
    assert clasificar_senal(300, 200, 99, largo_min=100, min_bases_q20=30) == Senal.PARCIAL


def test_evaluar_lectura_buena():
    lec = lectura("X", "F", leer(verdad(), Perfil.BUENA))
    assert (lec.largo_crudo, lec.bases_q20, lec.largo_estricto, lec.largo_laxo) == (
        260,
        260,
        260,
        260,
    )
    assert lec.senal == Senal.BUENA


def test_evaluar_lectura_parcial_el_recorte_laxo_conserva_el_tramo_flojo():
    lec = lectura("X", "F", leer(verdad(), Perfil.PARCIAL))
    assert (lec.largo_estricto, lec.largo_laxo) == (80, 150)
    assert lec.senal == Senal.PARCIAL


def test_evaluar_lectura_sin_senal_y_corta():
    assert lectura("X", "F", leer(verdad(), Perfil.SIN_SENAL)).senal == Senal.SIN_SENAL
    corta = lectura("X", "F", leer(verdad(), Perfil.CORTA))
    assert corta.largo_crudo == 120 and corta.senal == Senal.SIN_SENAL


def test_evaluar_lectura_cuenta_ambiguedades_crudas():
    assert lectura("X", "F", leer(verdad(), Perfil.AMBIGUA)).amb_cruda == 4


def test_evaluar_lectura_vacia():
    lec = lectura("X", "F", ("", []))
    assert (lec.largo_crudo, lec.q_media_cruda, lec.q_media_estricto) == (0, 0.0, 0.0)
    assert lec.senal == Senal.SIN_SENAL
