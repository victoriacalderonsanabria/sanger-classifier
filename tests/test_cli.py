"""
La línea de comandos reproduce la del script original, argumento por argumento,
y `clasificar_sanger.py` de la raíz sigue funcionando (lo usa la ventana actual).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sanger.cli import construir_parser, parametros_desde_args
from sanger.config import Parametros
from tests.sintetico.corrida import armar_corrida

RAIZ = Path(__file__).resolve().parent.parent


def _params(*argv):
    return parametros_desde_args(construir_parser().parse_args(["-i", "ab1", *argv]))


def test_sin_opciones_da_los_mismos_valores_que_parametros():
    assert _params() == Parametros(entrada="ab1")


def test_cada_opcion_llega_a_su_parametro():
    p = _params(
        "-o", "res", "--email", "a@b.c", "--largo-min", "300", "--q-media-min", "30",
        "--pct-q20-min", "90", "--umbral-q", "25", "--umbral-q-laxo", "12",
        "--largo-min-laxo", "50", "--min-bases-q20", "40", "--min-solap", "60",
        "--db", "mito", "--lote", "20", "--taxon", "Vertebrata[Organism]",
        "--blast-local", "base", "--no-blast", "--ident-min", "98.7", "--cob-min", "70",
        "--separador", "coma", "--primers-f", "MiF", "OtroF", "--primers-r", "MiR",
    )  # fmt: skip
    assert p == Parametros(
        entrada="ab1", salida="res", email="a@b.c", largo_min=300, q_media_min=30.0,
        pct_q20_min=90.0, umbral_q=25, umbral_q_laxo=12, largo_min_laxo=50,
        min_bases_q20=40, min_solap=60, db="mito", lote=20, taxon="Vertebrata[Organism]",
        blast_local="base", no_blast=True, ident_min=98.7, cob_min=70.0,
        separador="coma", primers_f=("MiF", "OtroF"), primers_r=("MiR",),
    )  # fmt: skip


def test_input_es_obligatorio():
    with pytest.raises(SystemExit):
        construir_parser().parse_args([])


def test_separador_solo_acepta_las_dos_opciones():
    with pytest.raises(SystemExit):
        construir_parser().parse_args(["-i", "x", "--separador", "tab"])


def test_la_ventana_actual_encuentra_main_en_el_script_de_la_raiz():
    import clasificar_sanger
    from sanger.cli import main

    assert clasificar_sanger.main is main


def _correr_raiz(*argv, cwd):
    return subprocess.run(
        [sys.executable, str(RAIZ / "clasificar_sanger.py"), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_script_de_la_raiz_corre_de_punta_a_punta(tmp_path):
    entrada = armar_corrida(tmp_path / "ab1")
    r = _correr_raiz("-i", str(entrada), "-o", str(tmp_path / "res"), "--no-blast", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "CONFIABLE:   10" in r.stdout
    assert (tmp_path / "res" / "04_resultados.csv").exists()


def test_carpeta_sin_ab1_termina_con_error(tmp_path):
    (tmp_path / "vacia").mkdir()
    r = _correr_raiz("-i", str(tmp_path / "vacia"), "--no-blast", cwd=tmp_path)
    assert r.returncode == 1
    assert "No encontré .ab1 en" in r.stderr
