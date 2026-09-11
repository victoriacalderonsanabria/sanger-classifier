"""Muestra y sentido (F/R) a partir del nombre del archivo."""

import pytest

from sanger.io.nombres import muestra_y_sentido


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("M12_F.ab1", ("M12", "F")),
        ("M12-R.ab1", ("M12", "R")),
        ("Cepa3_27F_A01.ab1", ("Cepa3", "F")),
        ("H7-ITS4.ab1", ("H7", "R")),
        ("999-F-2026-01-01-00-00-00.ab1", ("999", "F")),  # formato del secuenciador
        ("F_M12.ab1", ("M12", "F")),
        ("M3_R.AB1", ("M3", "R")),
        ("M5_T7.ab1", ("M5", "F")),
        ("M5 SP6.ab1", ("M5", "F")),
        ("A-B_F.ab1", ("A_B", "F")),
        ("R2_F.ab1", ("R2", "F")),
        ("M_R_F.ab1", ("M", "R")),
        ("S16_LCO1490.ab1", ("S16", "F")),
        ("S16_HCO2198.ab1", ("S16", "R")),
        ("muestra_sola.ab1", ("muestra_sola", "?")),
        ("F.ab1", ("F", "F")),  # solo el token: la muestra es el nombre entero
    ],
)
def test_muestra_y_sentido(nombre, esperado):
    assert muestra_y_sentido(nombre) == esperado


def test_muestra_y_sentido_primers_extra():
    assert muestra_y_sentido("X_MiF.ab1") == ("X_MiF", "?")
    assert muestra_y_sentido("X_MiF.ab1", extra_f=["MiF"]) == ("X", "F")
    assert muestra_y_sentido("X_mir.ab1", extra_r=["MiR"]) == ("X", "R")
