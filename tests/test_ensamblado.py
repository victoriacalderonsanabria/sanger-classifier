"""Consenso F+R y comparación de las DUDOSAS contra las CONFIABLES de la corrida."""

import pytest

from sanger.ensamblado.comparacion import (
    Comparacion,
    comparar_con_confiables,
    veredicto_comparacion,
)
from sanger.ensamblado.consenso import consenso_fr
from tests.sintetico.generador import Perfil, leer, par_fr, reverso_complemento, verdad

# ----------------------------------------------------------------------------
# consenso_fr
# ----------------------------------------------------------------------------


def test_consenso_fr_reconstruye_la_secuencia_completa():
    v = verdad(300)
    f, r = v[:250], reverso_complemento(v[50:])
    c = consenso_fr(f, [40] * len(f), r, [40] * len(r))
    assert c.ok
    assert c.seq == v
    assert len(c.qual) == 300
    assert (c.solap, c.discrepancias, c.conflictos) == (200, 0, 0)


def test_consenso_fr_gana_la_base_de_mayor_calidad():
    v = verdad(300)
    f = list(v[:250])
    f[100] = next(b for b in "ACGT" if b != v[100])  # error de F en una base mala
    qual_f = [40] * 250
    qual_f[100] = 10
    r = reverso_complemento(v[50:])
    c = consenso_fr("".join(f), qual_f, r, [40] * len(r))
    assert c.seq == v
    assert c.qual[100] == 30  # Q de la ganadora menos Q de la perdedora
    assert (c.discrepancias, c.conflictos) == (1, 0)


def test_consenso_fr_cuenta_conflicto_si_ambas_bases_son_buenas():
    v = verdad(300)
    f = list(v[:250])
    f[100] = next(b for b in "ACGT" if b != v[100])
    r = reverso_complemento(v[50:])
    c = consenso_fr("".join(f), [40] * 250, r, [40] * len(r))
    assert (c.discrepancias, c.conflictos) == (1, 1)


def test_consenso_fr_una_base_definida_le_gana_a_un_codigo_ambiguo():
    v = verdad(300)
    f = list(v[:250])
    f[100] = "N"  # el secuenciador dudó, aunque con calidad alta
    r = reverso_complemento(v[50:])
    qual_r = [15] * len(r)  # R con calidad más baja, pero con base definida
    c = consenso_fr("".join(f), [40] * 250, r, qual_r)
    assert c.seq[100] == v[100]
    assert c.conflictos == 0  # una N no cuenta como conflicto


@pytest.mark.parametrize(("solapamiento", "hay_consenso"), [(49, False), (50, True), (51, True)])
def test_consenso_fr_umbral_de_solapamiento_en_los_dos_lados(solapamiento, hay_consenso):
    (sf, qf), (sr, qr) = par_fr(verdad(400), solapamiento)
    c = consenso_fr(sf, qf, sr, qr, min_solap=50)
    assert c.ok is hay_consenso
    assert c.solap == solapamiento


def test_consenso_fr_sin_consenso_devuelve_vacio():
    (sf, qf), (sr, qr) = par_fr(verdad(400), 30)
    c = consenso_fr(sf, qf, sr, qr, min_solap=50)
    assert (c.ok, c.solap, c.seq, c.qual) == (False, 30, "", [])


def test_consenso_fr_con_parcial_se_arma_sobre_lecturas_crudas():
    # F con cola degradada: recortada sola perdería el solapamiento, pero el
    # consenso se arma sobre las crudas y recupera la plantilla entera
    v = verdad()
    (sf, qf), (sr, qr) = par_fr(v, 150, Perfil.PARCIAL, Perfil.BUENA)
    c = consenso_fr(sf, qf, sr, qr)
    assert c.ok and len(c.seq) == len(v)


def test_consenso_fr_mezcla_de_plantillas_da_conflictos():
    (sf, qf), (sr, qr) = par_fr(verdad(), 200, Perfil.MEZCLA, Perfil.BUENA)
    c = consenso_fr(sf, qf, sr, qr)
    assert c.ok and c.conflictos >= 3


# ----------------------------------------------------------------------------
# comparar_con_confiables y veredicto_comparacion
# ----------------------------------------------------------------------------


def test_comparar_con_confiables_detecta_lectura_invertida():
    v = verdad(200)
    dudosa = list(reverso_complemento(v[20:180]))
    qual = [30] * len(dudosa)
    dudosa[80] = next(b for b in "ACGT" if b != dudosa[80])  # desajuste en base mala
    qual[80] = 8
    refs = [("REF1", v), ("OTRA", verdad(200, 7))]
    d = comparar_con_confiables("".join(dudosa), qual, refs)
    assert d.ref == "REF1" and d.orient == "rc"
    assert (d.bases_buenas, d.desaj_buenas, d.ident_buenas) == (159, 0, 100.0)
    assert (d.bases_malas, d.desaj_malas) == (1, 1)


def test_comparar_con_confiables_parcial_contra_su_especie():
    # la lectura PARCIAL de la especie A coincide al 100 % en sus bases buenas
    a, b = verdad(260, 1), verdad(260, 2)
    seq, qual = leer(a, Perfil.PARCIAL)
    d = comparar_con_confiables(seq, qual, [("B", b), ("A", a)])
    assert d.ref == "A" and d.ident_buenas == 100.0


def _cmp(bases_buenas, ident_buenas):
    return Comparacion("M9", bases_buenas, 0, ident_buenas, 0, 0, "+")


@pytest.mark.parametrize(
    ("d", "esperado"),
    [
        (None, "sin_coincidencia_util"),
        (_cmp(39, 100.0), "sin_coincidencia_util"),
        (_cmp(78, 100.0), "coincide con M9 (100.0% en 78 bases buenas)"),
        (_cmp(40, 98.0), "coincide con M9 (98.0% en 40 bases buenas)"),
        (_cmp(78, 95.0), "parecida a M9 (95.0% en bases buenas)"),
        (_cmp(78, 90.4), "distinta de las confiables (mejor: M9, 90.4%)"),
    ],
)
def test_veredicto_comparacion(d, esperado):
    assert veredicto_comparacion(d) == esperado
