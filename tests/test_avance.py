"""
Cómo se reparte la barra de progreso entre las etapas.

No necesita PySide6: es aritmética, así que corre también en el CI.
"""

import pytest

from sanger_ui.avance import ORDEN, PESOS, porcentaje, reloj


def test_los_pesos_suman_cien():
    assert sum(PESOS.values()) == 100
    assert tuple(PESOS) == ORDEN


def test_el_blast_pesa_mas_que_todo_lo_demas_junto():
    # es el 90 % del tiempo real de una corrida; si la barra contara ítems,
    # el QC la llenaría en dos segundos
    assert PESOS["blast"] > sum(v for k, v in PESOS.items() if k != "blast")


@pytest.mark.parametrize(
    ("etapa", "hechos", "total", "esperado"),
    [
        ("qc", 0, 26, 0),
        ("qc", 13, 26, 5),
        ("qc", 26, 26, 10),
        ("clasificacion", 0, 16, 10),
        ("clasificacion", 16, 16, 15),
        ("comparacion", 3, 3, 20),
        ("blast", 0, 96, 20),  # arranca el BLAST: la barra queda en 20
        ("blast", 48, 96, 58),  # la mitad de las muestras resueltas
        ("blast", 96, 96, 95),
        ("informes", 1, 1, 100),
    ],
)
def test_porcentaje_por_etapa(etapa, hechos, total, esperado):
    assert porcentaje(etapa, hechos, total) == esperado


def test_sin_total_la_etapa_recien_arranca():
    assert porcentaje("blast", 0, 0) == 20


def test_valores_fuera_de_rango_no_rompen_la_barra():
    assert porcentaje("blast", 200, 96) == 95
    assert porcentaje("blast", -1, 96) == 20
    assert porcentaje("etapa_que_no_existe", 1, 1) == 0


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [(0, "0s"), (5.4, "5s"), (59, "59s"), (60, "1m 0s"), (102, "1m 42s"), (1263, "21m 3s")],
)
def test_reloj(segundos, esperado):
    assert reloj(segundos) == esperado
