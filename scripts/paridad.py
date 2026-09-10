"""
Compara la salida de dos corridas del pipeline, archivo por archivo.

Por qué existe: la regla que manda en la modularización es que la ciencia no
cambie. La única forma de demostrarlo es correr el script original y el nuevo
sobre los mismos 192 .ab1 y verificar que los informes salen idénticos, byte a
byte. Hacerlo a ojo sobre CSV de cien filas no es confiable; esto sí.

Qué se compara:
  - 01 a 05: idénticos byte a byte. Cualquier diferencia, aunque sea un espacio
    o un decimal, cuenta como cambio de resultado.
  - 00_resumen.txt: idéntico salvo la línea "Tiempo total", que mide cuánto
    tardó la corrida y por lo tanto nunca va a coincidir entre dos corridas.
  - Consola (opcional): lo que el script imprimió en pantalla, sin la línea de
    tiempo ni la de "Listo. Resultados en ...", que depende de la carpeta.

Uso:
    python scripts/paridad.py C:\\Sanger\\paridad\\referencia_original C:\\Sanger\\paridad\\nueva
    python scripts/paridad.py REF NUEVA --consola REF.consola.txt NUEVA.consola.txt

Sale con código 0 si hay paridad y 1 si no, así se puede usar en un script.
"""

import argparse
import sys
from pathlib import Path

ARCHIVOS_EXACTOS = (
    "01_QC_lecturas.csv",
    "02_confiables.fasta",
    "03_dudosas.fasta",
    "04_resultados.csv",
    "05_hits_completos.json",
)
RESUMEN = "00_resumen.txt"

# Líneas que cambian en cada corrida sin que cambie ningún resultado.
IGNORAR_EN_RESUMEN = ("Tiempo total:",)
IGNORAR_EN_CONSOLA = ("Tiempo total:", "Listo. Resultados en")


def _sin_lineas_variables(texto: str, prefijos: tuple[str, ...]) -> list[str]:
    """Quita las líneas que varían entre corridas (tiempo, rutas)."""
    return [linea for linea in texto.splitlines() if not linea.startswith(prefijos)]


def _primera_diferencia(a: list[str], b: list[str]) -> str:
    """Describe la primera línea distinta, para saber dónde mirar."""
    # strict=False a propósito: si una tiene más líneas, se avisa abajo
    for n, (la, lb) in enumerate(zip(a, b, strict=False), 1):
        if la != lb:
            return f"línea {n}:\n      antes: {la!r}\n      ahora: {lb!r}"
    return f"cantidad de líneas distinta ({len(a)} antes, {len(b)} ahora)"


def comparar_carpetas(referencia: Path, nueva: Path) -> list[str]:
    """Devuelve la lista de diferencias; vacía significa paridad."""
    diferencias = []
    for nombre in ARCHIVOS_EXACTOS:
        ref, nue = referencia / nombre, nueva / nombre
        if not ref.exists():
            diferencias.append(f"{nombre}: falta en la referencia")
            continue
        if not nue.exists():
            diferencias.append(f"{nombre}: falta en la corrida nueva")
            continue
        a, b = ref.read_bytes(), nue.read_bytes()
        if a != b:
            detalle = _primera_diferencia(
                a.decode("utf-8", "replace").splitlines(),
                b.decode("utf-8", "replace").splitlines(),
            )
            diferencias.append(f"{nombre}: distinto en {detalle}")

    ref, nue = referencia / RESUMEN, nueva / RESUMEN
    if not ref.exists() or not nue.exists():
        diferencias.append(f"{RESUMEN}: falta en alguna de las dos carpetas")
    else:
        a = _sin_lineas_variables(ref.read_text(encoding="utf-8"), IGNORAR_EN_RESUMEN)
        b = _sin_lineas_variables(nue.read_text(encoding="utf-8"), IGNORAR_EN_RESUMEN)
        if a != b:
            diferencias.append(f"{RESUMEN}: distinto en {_primera_diferencia(a, b)}")
    return diferencias


def comparar_consolas(referencia: Path, nueva: Path) -> list[str]:
    """Compara lo impreso en pantalla; vacía significa paridad."""
    a = _sin_lineas_variables(referencia.read_text(encoding="utf-8"), IGNORAR_EN_CONSOLA)
    b = _sin_lineas_variables(nueva.read_text(encoding="utf-8"), IGNORAR_EN_CONSOLA)
    if a != b:
        return [f"consola: distinta en {_primera_diferencia(a, b)}"]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verifica paridad entre dos corridas.")
    ap.add_argument("referencia", type=Path, help="carpeta de salida del script original")
    ap.add_argument("nueva", type=Path, help="carpeta de salida de la versión nueva")
    ap.add_argument(
        "--consola",
        nargs=2,
        type=Path,
        metavar=("REF", "NUEVA"),
        help="archivos con lo impreso en pantalla por cada corrida",
    )
    args = ap.parse_args(argv)

    diferencias = comparar_carpetas(args.referencia, args.nueva)
    if args.consola:
        diferencias += comparar_consolas(*args.consola)

    if diferencias:
        print("SIN PARIDAD. Diferencias encontradas:")
        for d in diferencias:
            print(f"  - {d}")
        return 1
    revisados = len(ARCHIVOS_EXACTOS) + 1 + (1 if args.consola else 0)
    print(f"PARIDAD OK: {revisados} salidas idénticas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
