"""Parametros: inmutable, con los valores validados por defecto y tipos fijos."""

import dataclasses
from pathlib import Path

import pytest

from sanger.config import (
    CAMPOS_PRESET,
    PRESET_DEFAULT,
    PRESETS,
    Parametros,
    aplicar_preset,
    normalizar_valores,
    valores_de_preset,
)


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


# ----------------------------------------------------------------------------
# Presets (los valores salen de README_clasificar_sanger.md)
# ----------------------------------------------------------------------------


def test_el_preset_default_son_los_valores_por_defecto():
    # se llama "Default" y no "Personalizado": el usuario no configuró nada,
    # son los valores validados del pipeline
    assert PRESETS[0].nombre == "Default"
    assert valores_de_preset("Default") == {
        "largo_min": 100,
        "largo_min_laxo": 60,
        "ident_min": 97.0,
        "lote": 50,
        "db": "nt",
    }


def test_el_preset_default_no_cambia_nada():
    p = Parametros(entrada="x", largo_min=123)
    assert aplicar_preset(p, "Default") == p


def test_valores_de_preset_incluye_los_campos_que_el_preset_no_toca():
    # ITS solo cambia la base: el resto tiene que venir con los valores por defecto
    assert valores_de_preset("ITS hongos") == {
        "largo_min": 100,
        "largo_min_laxo": 60,
        "ident_min": 97.0,
        "lote": 50,
        "db": "ITS_RefSeq_Fungi",
    }


def test_preset_coi_folmer_sube_el_largo_minimo():
    p = aplicar_preset(Parametros(entrada="x"), "COI Folmer (~650 pb)")
    assert p.largo_min == 300
    assert (p.ident_min, p.db) == (97.0, "nt")  # lo demás queda como estaba


def test_preset_16s_bacteriano():
    p = aplicar_preset(Parametros(entrada="x"), "16S bacteriano")
    assert (p.largo_min, p.ident_min, p.db) == (300, 98.7, "16S_ribosomal_RNA")


def test_preset_its_hongos_solo_cambia_la_base():
    p = aplicar_preset(Parametros(entrada="x"), "ITS hongos")
    assert p.db == "ITS_RefSeq_Fungi"
    assert (p.largo_min, p.ident_min) == (100, 97.0)


def test_los_presets_solo_tocan_campos_que_existen():
    campos = {f.name for f in dataclasses.fields(Parametros)}
    for p in PRESETS:
        assert set(p.cambios) <= campos, p.nombre


def test_los_presets_solo_tocan_campos_que_se_ven_en_la_ventana():
    # si un preset cambiara algo que no se muestra, el usuario no podría saber
    # que está activo ni que lo modificó
    for p in PRESETS:
        assert set(p.cambios) <= set(CAMPOS_PRESET), p.nombre


# ----------------------------------------------------------------------------
# El Default propio: otro equipo deja guardados sus criterios de partida
# ----------------------------------------------------------------------------


def test_un_default_propio_reemplaza_a_los_valores_del_programa():
    propios = {"largo_min": 250, "largo_min_laxo": 80, "ident_min": 99.0, "lote": 20, "db": "mito"}
    assert valores_de_preset(PRESET_DEFAULT, propios) == propios


def test_un_default_propio_incompleto_se_completa_con_los_del_programa():
    valores = valores_de_preset(PRESET_DEFAULT, {"ident_min": 99.0})
    assert valores["ident_min"] == 99.0
    assert (valores["largo_min"], valores["db"]) == (100, "nt")


def test_los_otros_perfiles_se_arman_sobre_el_default_propio():
    # ITS solo cambia la base: el largo tiene que seguir siendo el del equipo y
    # no el del programa, o el perfil le pisaría criterios que eligió a propósito
    valores = valores_de_preset("ITS hongos", {"largo_min": 250})
    assert (valores["largo_min"], valores["db"]) == (250, "ITS_RefSeq_Fungi")


def test_un_perfil_le_gana_al_default_propio_en_lo_que_toca():
    valores = valores_de_preset("16S bacteriano", {"largo_min": 250, "ident_min": 99.0})
    assert (valores["largo_min"], valores["ident_min"]) == (300, 98.7)


def test_un_default_propio_roto_se_ignora_y_el_programa_sigue():
    # el archivo de preferencias se puede editar a mano: que esté mal no puede
    # impedir que el programa abra
    for basura in (None, "300", 7, {"largo_min": "trescientos"}, {"db": 5}):
        assert normalizar_valores(basura) == {}
    assert valores_de_preset(PRESET_DEFAULT, {"largo_min": "x"}) == valores_de_preset(
        PRESET_DEFAULT
    )


def test_el_default_propio_solo_guarda_campos_que_se_ven():
    # no puede cambiar nada que la ventana no muestre: nadie sabría que está puesto
    assert set(normalizar_valores({"largo_min": 250, "cob_min": 10.0})) == set(CAMPOS_PRESET)


def test_preset_inexistente():
    with pytest.raises(KeyError):
        aplicar_preset(Parametros(entrada="x"), "Marcador inventado")
