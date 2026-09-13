"""Parametros: inmutable, con los valores validados por defecto y tipos fijos."""

import dataclasses
from pathlib import Path

import pytest

from sanger.config import Parametros


def test_valores_por_defecto_son_los_validados():
    p = Parametros(entrada="x")
    assert (p.largo_min, p.q_media_min, p.pct_q20_min, p.umbral_q) == (100, 25.0, 80.0, 20)
    assert (p.umbral_q_laxo, p.largo_min_laxo, p.min_bases_q20, p.min_solap) == (15, 60, 30, 50)
    assert (p.db, p.lote, p.ident_min, p.cob_min) == ("nt", 50, 97.0, 80.0)
    assert p.salida == Path("resultados") and not p.no_blast


def test_no_se_puede_cambiar_a_mitad_de_corrida():
    p = Parametros(entrada="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.largo_min = 300


def test_tipos_fijos_para_que_los_textos_salgan_iguales():
    # "Q media 22.1 < 25.0" tiene que salir igual venga de la consola o de la ventana
    p = Parametros(entrada="x", q_media_min=25, largo_min="100", primers_f=["MiF"])
    assert repr(p.q_media_min) == "25.0" and p.largo_min == 100
    assert isinstance(p.entrada, Path) and p.primers_f == ("MiF",)


def test_separador_define_formato_de_csv():
    excel = Parametros(entrada="x")
    internacional = Parametros(entrada="x", separador="coma")
    assert (excel.sep_csv, excel.decimal_coma) == (";", True)
    assert (internacional.sep_csv, internacional.decimal_coma) == (",", False)


def test_separador_invalido():
    with pytest.raises(ValueError, match="separador"):
        Parametros(entrada="x", separador="tab")


def test_con_devuelve_una_copia_sin_tocar_la_original():
    p = Parametros(entrada="x")
    otro = p.con(largo_min=300)
    assert (otro.largo_min, p.largo_min) == (300, 100)
    assert otro.entrada == p.entrada
