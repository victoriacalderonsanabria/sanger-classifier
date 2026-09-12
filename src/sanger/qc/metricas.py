"""Métricas de calidad de una secuencia y diagnóstico de cada lectura."""

from collections.abc import Sequence
from dataclasses import dataclass

from sanger.modelos import Lectura, Senal
from sanger.qc.recorte import recorte_mott

ACGT = frozenset("ACGT")

# Una lectura con menos bases que esto, aunque sean buenas, no se considera
# señal: en un amplicón de ~260 pb es casi seguro una falla de secuenciación.
LARGO_CRUDO_MIN = 150


@dataclass(frozen=True)
class Metricas:
    largo: int
    q_media: float
    pct_q20: float
    n_amb: int  # bases que no son A/C/G/T (N, R, Y…): el secuenciador dudó


def metricas(seq: str, qual: Sequence[int]) -> Metricas:
    """Largo, Q media, % de bases Q≥20 y ambigüedades, redondeados como en los informes."""
    n = len(qual)
    if n == 0:
        return Metricas(largo=0, q_media=0.0, pct_q20=0.0, n_amb=0)
    return Metricas(
        largo=n,
        q_media=round(sum(qual) / n, 1),
        pct_q20=round(100.0 * sum(1 for q in qual if q >= 20) / n, 1),
        n_amb=sum(1 for c in seq.upper() if c not in ACGT),
    )


def cumple_estandar(
    seq: str,
    qual: Sequence[int],
    *,
    largo_min: int,
    q_media_min: float,
    pct_q20_min: float,
) -> tuple[bool, Metricas]:
    """
    Criterio CONFIABLE sobre una secuencia ya recortada.

    Se piden las tres cosas a la vez: la Q media garantiza pocos errores en
    conjunto, y el porcentaje de bases Q≥20 evita que un bloque de bases pésimas
    se esconda detrás de muchas bases excelentes.
    """
    m = metricas(seq, qual)
    ok = m.largo >= largo_min and m.q_media >= q_media_min and m.pct_q20 >= pct_q20_min
    return ok, m


def clasificar_senal(
    largo_crudo: int, bases_q20: int, largo_estricto: int, *, largo_min: int, min_bases_q20: int
) -> Senal:
    """
    BUENA: ya sola alcanza el largo tras el recorte estricto.
    PARCIAL: tiene señal pero no alcanza sola (puede aportar a un consenso).
    SIN_SEÑAL: no hay nada que rescatar.
    """
    if largo_crudo < LARGO_CRUDO_MIN or bases_q20 < min_bases_q20:
        return Senal.SIN_SENAL
    if largo_estricto >= largo_min:
        return Senal.BUENA
    return Senal.PARCIAL


def evaluar_lectura(
    archivo: str,
    muestra: str,
    sentido: str,
    seq: str,
    qual: list[int],
    *,
    umbral_q: int,
    umbral_q_laxo: int,
    largo_min: int,
    min_bases_q20: int,
    error: str | None = None,
) -> Lectura:
    """
    Todas las métricas de una lectura cruda, con los dos recortes.

    Se recorta con dos umbrales porque cada uno responde una pregunta distinta:
    el estricto (Q20) dice si la lectura sirve para un resultado reportable; el
    laxo (Q15) dice si al menos hay algo que valga la pena revisar a mano.
    """
    mc = metricas(seq, qual)
    bases_q20 = sum(1 for q in qual if q >= 20)
    ie, fe = recorte_mott(qual, umbral_q)
    il, fl = recorte_mott(qual, umbral_q_laxo)
    largo_estricto = fe - ie
    return Lectura(
        archivo=archivo,
        muestra=muestra,
        sentido=sentido,
        seq=seq,
        qual=qual,
        largo_crudo=mc.largo,
        q_media_cruda=mc.q_media,
        amb_cruda=mc.n_amb,
        bases_q20=bases_q20,
        largo_estricto=largo_estricto,
        q_media_estricto=metricas(seq[ie:fe], qual[ie:fe]).q_media,
        largo_laxo=fl - il,
        senal=clasificar_senal(
            mc.largo, bases_q20, largo_estricto, largo_min=largo_min, min_bases_q20=min_bases_q20
        ),
        error=error,
    )
