"""
Generador determinístico de lecturas Sanger sintéticas.

A partir de una secuencia "verdad" produce pares (seq, qual) que imitan los
casos que aparecen en una corrida real. Semilla fija: la misma llamada da
siempre el mismo resultado, en cualquier máquina.

Perfiles (grupo esperado para una lectura sola, con los umbrales por defecto):

  BUENA      lectura limpia, Q alto y parejo                       → CONFIABLE
  PARCIAL    buen arranque, tramo intermedio flojo, cola degradada → DUDOSA
  SIN_SENAL  Q uniformemente bajo (< 30 bases Q≥20)                → RECHAZADA
  CORTA      Q alto pero pocas bases (< 150)                       → RECHAZADA
  MEZCLA     dos plantillas superpuestas (se ve en el par F/R)     → conflictos F/R ≥ 3
  AMBIGUA    como PARCIAL, con códigos N/R/Y intercalados          → ambigüedades contadas
"""

import random
from enum import StrEnum

from Bio.Seq import Seq

BASES = "ACGT"
AMBIGUOS = "NRYKMSW"
SEMILLA = 20260910


class Perfil(StrEnum):
    BUENA = "BUENA"
    PARCIAL = "PARCIAL"
    SIN_SENAL = "SIN_SENAL"
    CORTA = "CORTA"
    MEZCLA = "MEZCLA"
    AMBIGUA = "AMBIGUA"


# Tramos del perfil PARCIAL/AMBIGUA, en posiciones de la lectura:
# [0, 80) bueno (Q30-40), [80, 150) flojo (Q16-19: pasa el recorte laxo Q15
# pero no el estricto Q20), [150, ...) degradado (Q2-8, con errores de base).
PARCIAL_BUENO = 80
PARCIAL_FLOJO = 150
LARGO_CORTA = 120


def verdad(largo: int = 260, semilla: int = SEMILLA) -> str:
    """Secuencia de referencia al azar pero reproducible (~260 pb, como el amplicón del ensayo)."""
    rng = random.Random(semilla)
    return "".join(rng.choice(BASES) for _ in range(largo))


def reverso_complemento(seq: str) -> str:
    return str(Seq(seq).reverse_complement())


def mutar(seq: str, posiciones: list[int]) -> str:
    """Cambia la base en cada posición por otra distinta (una segunda plantilla)."""
    s = list(seq)
    for p in posiciones:
        s[p] = BASES[(BASES.index(s[p]) + 1) % 4]
    return "".join(s)


def _ruido(base: str, rng: random.Random, prob: float) -> str:
    """Con probabilidad `prob`, el secuenciador leyó mal esta base."""
    return rng.choice(BASES) if rng.random() < prob else base


def leer(plantilla: str, perfil: Perfil, semilla: int = SEMILLA) -> tuple[str, list[int]]:
    """
    Simula leer `plantilla` (ya en la orientación de la lectura) con un perfil.

    Donde la calidad es mala la base puede estar mal leída, como en un
    cromatograma real: por eso las calidades importan.
    """
    rng = random.Random(semilla)
    n = len(plantilla)
    if perfil in (Perfil.BUENA, Perfil.MEZCLA):
        return plantilla, [rng.randint(30, 45) for _ in range(n)]
    if perfil == Perfil.CORTA:
        return plantilla[:LARGO_CORTA], [rng.randint(30, 45) for _ in range(min(n, LARGO_CORTA))]
    if perfil == Perfil.SIN_SENAL:
        qual = [rng.randint(2, 12) for _ in range(n)]
        return "".join(_ruido(b, rng, 0.5) for b in plantilla), qual

    # PARCIAL y AMBIGUA
    seq, qual = [], []
    for i, b in enumerate(plantilla):
        if i < PARCIAL_BUENO:
            q = rng.randint(30, 40)
        elif i < PARCIAL_FLOJO:
            q = rng.randint(16, 19)
        else:
            q = rng.randint(2, 8)
        seq.append(_ruido(b, rng, 0.4) if q < 10 else b)
        qual.append(q)
    if perfil == Perfil.AMBIGUA:
        # códigos de ambigüedad dentro del tramo bueno, con Q moderado (típico)
        for p in (15, 30, 45, 60):
            seq[p] = rng.choice(AMBIGUOS)
            qual[p] = 18
    return "".join(seq), qual


def par_fr(
    plantilla: str,
    solapamiento: int,
    perfil_f: Perfil = Perfil.BUENA,
    perfil_r: Perfil = Perfil.BUENA,
    semilla: int = SEMILLA,
) -> tuple[tuple[str, list[int]], tuple[str, list[int]]]:
    """
    Un par F/R que se superpone exactamente `solapamiento` bases.

    F cubre el principio de la plantilla y R el final (leída al revés, como en
    el secuenciador). Con MEZCLA en cualquiera de las dos, R sale de una segunda
    plantilla que difiere en 6 posiciones dentro del solapamiento: son picos
    que ambas lecturas ven con buena calidad pero en bases distintas.
    """
    largo = len(plantilla)
    fin_f = (largo + solapamiento) // 2
    ini_r = fin_f - solapamiento
    plantilla_r = plantilla
    if Perfil.MEZCLA in (perfil_f, perfil_r):
        paso = max(1, solapamiento // 7)
        plantilla_r = mutar(plantilla, [ini_r + paso * k for k in range(1, 7)])
    f = leer(plantilla[:fin_f], perfil_f, semilla)
    r = leer(reverso_complemento(plantilla_r[ini_r:]), perfil_r, semilla + 1)
    return f, r
