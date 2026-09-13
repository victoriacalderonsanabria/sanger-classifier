"""
Qué secuencia representa a cada muestra y en qué grupo queda.

Cada perfil sintético del BRIEFING §5.1 contra el grupo esperado, más las
reglas finas (prioridad del consenso, desempates, textos de los motivos).
"""

from pathlib import Path

import pytest

from sanger.clasificacion import Candidato, Elegida, asignar_grupo, elegir_secuencia, motivos
from sanger.config import Parametros
from sanger.modelos import Grupo
from sanger.qc.metricas import Metricas
from tests.sintetico.generador import Perfil, leer, par_fr, reverso_complemento, verdad
from tests.sintetico.lecturas import lectura

V = verdad()


def _sola(perfil, params):
    return asignar_grupo("X", [lectura("X", "F", leer(V, perfil))], params)


def _par(perfil_f, perfil_r, params, solap=200, plantilla=V):
    f, r = par_fr(plantilla, solap, perfil_f, perfil_r)
    return asignar_grupo("P", [lectura("P", "F", f), lectura("P", "R", r)], params)


# ----------------------------------------------------------------------------
# Perfiles del §5.1 → grupo esperado
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("perfil", "grupo"),
    [
        (Perfil.BUENA, Grupo.CONFIABLE),
        (Perfil.PARCIAL, Grupo.DUDOSA),
        (Perfil.SIN_SENAL, Grupo.RECHAZADA),
        (Perfil.CORTA, Grupo.RECHAZADA),
        (Perfil.AMBIGUA, Grupo.DUDOSA),
    ],
)
def test_perfil_de_una_lectura_sola(perfil, grupo, params):
    assert _sola(perfil, params).grupo == grupo


def test_buena_sola_usa_la_lectura_entera(params):
    m = _sola(Perfil.BUENA, params)
    assert (m.origen, m.largo, m.secuencia, m.motivo) == ("SOLO_F", 260, V, "")
    assert m.solapamiento is None  # sin consenso, la celda queda vacía


def test_par_bueno_arma_consenso(params):
    m = _par(Perfil.BUENA, Perfil.BUENA, params)
    assert (m.grupo, m.origen, m.secuencia) == (Grupo.CONFIABLE, "CONSENSO_F+R", V)
    assert (m.solapamiento, m.discrepancias, m.conflictos) == (200, 0, 0)


def test_par_parcial_mas_buena_el_consenso_rescata_la_f(params):
    m = _par(Perfil.PARCIAL, Perfil.BUENA, params, solap=150)
    assert (m.grupo, m.origen, m.largo) == (Grupo.CONFIABLE, "CONSENSO_F+R", 260)


def test_par_parcial_parcial_queda_dudosa_con_motivos(params):
    m = _par(Perfil.PARCIAL, Perfil.PARCIAL, params, solap=100)
    assert m.grupo == Grupo.DUDOSA
    assert m.motivos[0] == "con recorte Q20 quedaban 80 pb - se usó recorte Q15"
    assert any(t.endswith("% bases Q20 < 80.0%") for t in m.motivos)


def test_sin_senal_en_una_sola_lectura_usa_la_otra(params):
    m = _par(Perfil.SIN_SENAL, Perfil.BUENA, params, solap=150)
    assert (m.grupo, m.origen) == (Grupo.CONFIABLE, "SOLO_R")
    # la R se da vuelta: queda orientada como forward
    assert m.secuencia in V


def test_ambas_sin_senal_es_rechazada_con_motivo(params):
    m = _par(Perfil.SIN_SENAL, Perfil.SIN_SENAL, params)
    assert m.grupo == Grupo.RECHAZADA
    assert m.motivo == "ninguna lectura con señal utilizable"
    assert (m.origen, m.largo, m.secuencia) == ("", 0, "")


def test_senal_que_ni_con_recorte_laxo_llega(params):
    lec = lectura("X", "F", (V, [35] * 50 + [4] * 210))
    m = asignar_grupo("X", [lec], params)
    assert m.grupo == Grupo.RECHAZADA
    assert m.motivo == "hay señal pero ni con recorte Q15 se llega a 60 pb"


def test_ambigua_informa_las_bases_ambiguas(params):
    assert "4 bases ambiguas" in _sola(Perfil.AMBIGUA, params).motivos


def test_umbrales_mas_exigentes_bajan_de_grupo():
    exigente = Parametros(entrada=Path("."), largo_min=300)
    assert _sola(Perfil.BUENA, exigente).grupo == Grupo.DUDOSA


def test_min_solap_decide_si_hay_consenso(params):
    larga = verdad(400)
    con = _par(Perfil.BUENA, Perfil.BUENA, params, solap=50, plantilla=larga)
    sin = _par(Perfil.BUENA, Perfil.BUENA, params, solap=49, plantilla=larga)
    assert con.origen == "CONSENSO_F+R"
    assert sin.origen.startswith("SOLO_")


def test_archivos_de_la_muestra_en_orden(params):
    m = _par(Perfil.BUENA, Perfil.BUENA, params)
    assert m.archivos == ("P_F.ab1", "P_R.ab1")


# ----------------------------------------------------------------------------
# MEZCLA: comportamiento actual, documentado (hallazgo para la fase 4)
# ----------------------------------------------------------------------------


def test_con_mezcla_la_alerta_aparece_aunque_gane_la_lectura_sola(params):
    """
    Corregido en la fase 4, por decisión de Victoria.

    Con dos plantillas mezcladas el consenso detecta los conflictos F/R, pero en
    cada conflicto su calidad queda baja (la diferencia de Q entre las dos
    bases), el recorte lo achica y termina ganando la lectura sola. Antes, ahí
    se perdía la alerta y la muestra salía CONFIABLE sin ninguna marca: la señal
    de posible mezcla desaparecía justo cuando más importaba.

    El grupo no cambia: la secuencia elegida sigue siendo buena. Lo que cambia
    es que queda dicho que hay que mirarla.
    """
    m = _par(Perfil.MEZCLA, Perfil.BUENA, params)
    assert m.grupo == Grupo.CONFIABLE
    assert m.origen.startswith("SOLO_")
    assert "conflictos F/R con buena calidad: posible mezcla" in m.motivo


def test_sin_mezcla_no_se_inventa_ninguna_alerta(params):
    assert "posible mezcla" not in _par(Perfil.BUENA, Perfil.BUENA, params).motivo
    assert "posible mezcla" not in _sola(Perfil.BUENA, params).motivo


# ----------------------------------------------------------------------------
# elegir_secuencia: prioridad del consenso y desempates
# ----------------------------------------------------------------------------


def _cand(largo, origen, extra=None, q=40):
    return Candidato(V[:largo], [q] * largo, origen, extra or {})


@pytest.mark.parametrize(("largo_consenso", "gana"), [(108, "CONSENSO_F+R"), (107, "SOLO_R")])
def test_consenso_tiene_prioridad_salvo_que_sea_mas_de_10_por_ciento_mas_corto(
    largo_consenso, gana, params
):
    # 0,9 × 120 = 108: con 108 gana el consenso, con 107 la lectura sola
    cands = [_cand(largo_consenso, "CONSENSO_F+R"), _cand(120, "SOLO_R")]
    elegida, _ = elegir_secuencia(cands, params)
    assert elegida.origen == gana and elegida.grupo == Grupo.CONFIABLE


def test_empate_entre_lecturas_solas_gana_la_primera(params):
    elegida, _ = elegir_secuencia([_cand(150, "SOLO_F"), _cand(150, "SOLO_R")], params)
    assert elegida.origen == "SOLO_F"


def test_dudosa_elige_la_mas_larga_con_recorte_laxo(params):
    cands = [_cand(90, "SOLO_F", q=17), _cand(120, "SOLO_R", q=17)]
    elegida, largo_estricto_max = elegir_secuencia(cands, params)
    assert (elegida.origen, elegida.grupo, elegida.met.largo) == ("SOLO_R", Grupo.DUDOSA, 120)
    assert largo_estricto_max == 0  # con Q17 el recorte estricto no deja nada


def test_dudosa_empate_gana_el_primero(params):
    cands = [_cand(90, "CONSENSO_F+R", q=17), _cand(90, "SOLO_R", q=17)]
    elegida, _ = elegir_secuencia(cands, params)
    assert elegida.origen == "CONSENSO_F+R"


def test_la_r_se_recorta_antes_de_darla_vuelta(params):
    # R con los primeros 20 ciclos malos (en SU orientación): el recorte los saca
    # y recién después se reverso-complementa
    seq_r = reverso_complemento(V)
    qual_r = [5] * 20 + [40] * (len(V) - 20)
    elegida, _ = elegir_secuencia([Candidato(seq_r, qual_r, "SOLO_R", {}, True)], params)
    assert elegida.seq == V[: len(V) - 20]


# ----------------------------------------------------------------------------
# motivos
# ----------------------------------------------------------------------------


def test_motivos_de_una_dudosa_con_todo_mal(params):
    met = Metricas(largo=70, q_media=18.5, pct_q20=40.0, n_amb=2)
    elegida = Elegida("A" * 70, "SOLO_F", {}, met, Grupo.DUDOSA)
    assert motivos(elegida, 55, params) == [
        "con recorte Q20 quedaban 55 pb - se usó recorte Q15",
        "largo 70 < 100",
        "Q media 18.5 < 25.0",
        "40.0% bases Q20 < 80.0%",
        "2 bases ambiguas",
    ]


@pytest.mark.parametrize(("conflictos", "alerta"), [(2, False), (3, True)])
def test_alerta_de_mezcla_desde_tres_conflictos(conflictos, alerta, params):
    met = Metricas(largo=200, q_media=38.0, pct_q20=100.0, n_amb=0)
    elegida = Elegida("A" * 200, "CONSENSO_F+R", {"conflictos": conflictos}, met, Grupo.CONFIABLE)
    esperado = [f"{conflictos} conflictos F/R con buena calidad: posible mezcla"] if alerta else []
    assert motivos(elegida, 0, params) == esperado
