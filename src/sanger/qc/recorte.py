"""Recorte por calidad con el algoritmo de Mott (el mismo que usa Phred)."""

from collections.abc import Sequence


def recorte_mott(qual: Sequence[int], umbral_q: int) -> tuple[int, int]:
    """
    Ventana contigua de puntaje máximo. Devuelve (inicio, fin), fin exclusivo.

    Cada base suma según qué tan lejos está su probabilidad de error del umbral
    (Q20 = 1 % de error): las buenas suman un poco, las malas restan mucho. Se
    conserva el tramo de suma máxima. Por eso tolera una base dudosa aislada
    dentro de un tramo bueno, pero corta donde empieza una racha de bases malas.
    """
    if not qual:
        return 0, 0
    cutoff = 10 ** (-umbral_q / 10.0)
    puntaje = mejor = 0.0
    inicio = 0
    mejor_ini = mejor_fin = 0
    for i, q in enumerate(qual):
        puntaje += cutoff - 10 ** (-q / 10.0)
        if puntaje < 0:
            puntaje, inicio = 0.0, i + 1
        elif puntaje > mejor:
            mejor, mejor_ini, mejor_fin = puntaje, inicio, i + 1
    return mejor_ini, mejor_fin
