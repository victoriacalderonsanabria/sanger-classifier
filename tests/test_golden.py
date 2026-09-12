"""
Test golden de regresión (BRIEFING §5.4).

Corre el pipeline sobre la corrida sintética estándar (tests/sintetico/corrida.py)
y compara TODA la salida contra los snapshots de tests/golden/, incluida la
consola. Los snapshots de la fase 1 los produjo el clasificar_sanger.py
ORIGINAL: que este test pase prueba que el paquete nuevo hace lo mismo.

Si falla, algo cambió la salida. Actualizar un golden es un acto deliberado
(scripts/generar_goldens.py, a mano) que se explica en el PR; nunca en el CI.
"""

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

import paridad
from generar_goldens import normalizar_salida
from sanger.cli import main
from tests.sintetico.corrida import armar_corrida, preparar_cache_blast

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(scope="module")
def entrada(tmp_path_factory):
    return armar_corrida(tmp_path_factory.mktemp("corrida") / "ab1")


@pytest.mark.parametrize("variante", ["sin_blast", "con_blast"])
def test_salida_identica_al_golden(variante, entrada, tmp_path, fixtures_blast):
    salida = tmp_path / variante
    if variante == "con_blast":
        # el BLAST remoto usa el caché y no consulta a NCBI (y la red está bloqueada)
        preparar_cache_blast(salida, fixtures_blast)
    argv = ["-i", str(entrada), "-o", str(salida)]
    if variante == "sin_blast":
        argv.append("--no-blast")

    # se corre por la línea de comandos porque es la que imprime: desde la
    # fase 2 el núcleo no imprime, avisa
    consola = io.StringIO()
    with redirect_stdout(consola):
        main(argv)
    normalizar_salida(salida, entrada, consola.getvalue())

    referencia = GOLDEN / variante
    diferencias = paridad.comparar_carpetas(referencia, salida)
    diferencias += paridad.comparar_consolas(referencia / "consola.txt", salida / "consola.txt")
    assert diferencias == []
