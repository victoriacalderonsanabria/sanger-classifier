"""Atajo para convertir un par (seq, qual) sintético en una Lectura evaluada."""

from pathlib import Path

from sanger.config import Parametros
from sanger.modelos import Lectura
from sanger.qc.metricas import evaluar_lectura


def lectura(nombre: str, sentido: str, seq_qual, p: Parametros | None = None) -> Lectura:
    """Una Lectura evaluada igual que la arma el pipeline, sin pasar por un .ab1."""
    p = p or Parametros(entrada=Path("."))
    seq, qual = seq_qual
    return evaluar_lectura(
        f"{nombre}_{sentido}.ab1",
        nombre,
        sentido,
        seq,
        qual,
        umbral_q=p.umbral_q,
        umbral_q_laxo=p.umbral_q_laxo,
        largo_min=p.largo_min,
        min_bases_q20=p.min_bases_q20,
    )
