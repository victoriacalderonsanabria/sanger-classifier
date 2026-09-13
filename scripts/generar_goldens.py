"""
Genera los snapshots de tests/golden/ a partir de la corrida sintética.

Actualizar un golden es un acto deliberado: se corre esto a mano, se revisa el
diff y se explica en el PR por qué cambió la salida. Nunca se corre en el CI.

Uso:
    # con el paquete actual (p. ej. en la fase 4, cuando la salida cambia a propósito)
    python scripts/generar_goldens.py

    # con otro script, p. ej. el clasificar_sanger.py ORIGINAL (así se hicieron
    # los goldens de la fase 1: los produjo el código de antes del refactor)
    python scripts/generar_goldens.py --script ruta/al/clasificar_sanger.py

Tres normalizaciones, para que los goldens valgan en Windows y en Linux:
  - En la consola, las rutas de entrada y salida se reemplazan por <ENTRADA> y
    <SALIDA> (además, así no queda la ruta de nadie en el repo).
  - Los .txt/.fasta/.json se guardan con fin de línea LF: Python escribe CRLF en
    Windows y LF en Linux (los CSV no, esos siempre salen con CRLF).
(Desde la fase 4 los .fasta ya salen en UTF-8 y con LF desde el propio
programa, así que no hay nada que normalizar ahí.)
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ)]

from tests.sintetico.corrida import armar_corrida, preparar_cache_blast  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures" / "blast"
DESTINO = RAIZ / "tests" / "golden"
VARIANTES = {"sin_blast": ["--no-blast"], "con_blast": []}
TEXTO_LF = (".txt", ".fasta", ".json")


def normalizar_consola(consola: str, entrada: Path, salida: Path) -> str:
    consola = consola.replace("\r\n", "\n")
    return consola.replace(str(Path(salida).resolve()), "<SALIDA>").replace(
        str(entrada), "<ENTRADA>"
    )


def normalizar_salida(carpeta: Path, entrada: Path, consola: str) -> None:
    """Deja la carpeta comparable entre sistemas (ver docstring del módulo)."""
    for archivo in carpeta.iterdir():
        if archivo.suffix in TEXTO_LF:
            # los .fasta ya salen en UTF-8 y con LF desde la fase 4; el resumen
            # y el JSON todavía usan el fin de línea del sistema
            archivo.write_bytes(archivo.read_bytes().replace(b"\r\n", b"\n"))
    shutil.rmtree(carpeta / "blast_xml", ignore_errors=True)
    consola = normalizar_consola(consola, entrada, carpeta)
    (carpeta / "consola.txt").write_bytes(consola.encode("utf-8"))


def correr(entrada: Path, salida: Path, extra: list[str], script: Path | None) -> str:
    """Corre una variante y devuelve lo que imprimió en pantalla."""
    argv = ["-i", str(entrada), "-o", str(salida), *extra]
    if script:
        r = subprocess.run(
            [sys.executable, str(script), *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=True,
        )
        return r.stdout
    from sanger.cli import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(argv)
    return buffer.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser(description="Regenera tests/golden/ (a mano, nunca en CI).")
    ap.add_argument("--script", type=Path, help="correr este script en vez del paquete")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        entrada = armar_corrida(Path(tmp) / "ab1")
        for variante, extra in VARIANTES.items():
            salida = args.destino / variante
            shutil.rmtree(salida, ignore_errors=True)
            salida.mkdir(parents=True)
            if variante == "con_blast":
                preparar_cache_blast(salida, FIXTURES)
            consola = correr(entrada, salida, extra, args.script)
            normalizar_salida(salida, entrada, consola)
            print(f"{variante}: {sorted(p.name for p in salida.iterdir())}")


if __name__ == "__main__":
    main()
