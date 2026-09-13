"""
Segunda opinión para las DUDOSAS, independiente de BLAST.

Si una muestra dudosa es en realidad la misma secuencia que otra muestra que sí
salió CONFIABLE en la misma corrida, eso respalda su identificación aunque la
calidad sea baja. La clave es mirar la calidad de cada base: un desajuste sobre
una base mala es ruido; un desajuste sobre una base buena es una diferencia real.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from Bio.Seq import Seq

from sanger.ensamblado.consenso import aligner_local


@dataclass(frozen=True)
class Comparacion:
    ref: str  # nombre de la muestra CONFIABLE más parecida
    bases_buenas: int
    desaj_buenas: int
    ident_buenas: float
    bases_malas: int
    desaj_malas: int
    orient: str  # "+" o "rc" (la lectura estaba invertida)


def comparar_con_confiables(
    seq: str,
    qual: Sequence[int],
    referencias: Sequence[tuple[str, str]],
    q_buena: int = 20,
) -> Comparacion | None:
    """
    Alinea la lectura CRUDA contra cada confiable, en las dos orientaciones.

    `referencias` son pares (nombre de muestra, secuencia). Gana la referencia
    con más bases buenas coincidentes. Devuelve None si no alinea con nada.
    """
    al = aligner_local(1, -1, -2, -1)
    mejor = None
    rc = str(Seq(seq).reverse_complement())
    for orient, s, q in (("+", seq, qual), ("rc", rc, qual[::-1])):
        for nombre_ref, seq_ref in referencias:
            aln = al.align(s, seq_ref)[0]
            hi = lo = mhi = mlo = 0
            for (fa, fb), (ra, rb) in zip(*aln.aligned, strict=False):
                for i, j in zip(range(fa, fb), range(ra, rb), strict=False):
                    mm = s[i] != seq_ref[j]
                    if q[i] >= q_buena:
                        hi += 1
                        mhi += mm
                    else:
                        lo += 1
                        mlo += mm
            if hi + lo == 0:
                continue
            res = Comparacion(
                ref=nombre_ref,
                bases_buenas=hi,
                desaj_buenas=mhi,
                ident_buenas=round(100 * (hi - mhi) / hi, 1) if hi else 0.0,
                bases_malas=lo,
                desaj_malas=mlo,
                orient=orient,
            )
            if mejor is None or (hi - mhi) > (mejor.bases_buenas - mejor.desaj_buenas):
                mejor = res
    return mejor


def veredicto_comparacion(d: Comparacion | None, min_bases: int = 40) -> str:
    """
    El texto de la columna `coincide_con`.

    Con menos de `min_bases` bases buenas la comparación no significa nada y no
    se informa: un 100 % sobre 15 bases puede ser casualidad.
    """
    if d is None or d.bases_buenas < min_bases:
        return "sin_coincidencia_util"
    if d.ident_buenas >= 98.0:
        return f"coincide con {d.ref} ({d.ident_buenas}% en {d.bases_buenas} bases buenas)"
    if d.ident_buenas >= 95.0:
        return f"parecida a {d.ref} ({d.ident_buenas}% en bases buenas)"
    return f"distinta de las confiables (mejor: {d.ref}, {d.ident_buenas}%)"
