"""
Qué secuencia representa a cada muestra y en qué grupo queda.

Funciones puras: reciben lecturas ya evaluadas y devuelven la muestra
clasificada. No leen archivos ni hablan con BLAST.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from Bio.Seq import Seq

from sanger.config import Parametros
from sanger.ensamblado.consenso import consenso_fr
from sanger.modelos import Grupo, Lectura, Muestra, Senal
from sanger.qc.metricas import Metricas, cumple_estandar, metricas
from sanger.qc.recorte import recorte_mott

ORIGEN_CONSENSO = "CONSENSO_F+R"

# El consenso tiene prioridad sobre la mejor lectura sola salvo que sea
# claramente más corto: si mide menos del 90 % de ella, se prefiere la lectura.
PROPORCION_MIN_CONSENSO = 0.9

# Desde cuántos conflictos F/R con buena calidad se sospecha mezcla de plantillas.
CONFLICTOS_MEZCLA = 3


@dataclass(frozen=True)
class Candidato:
    """Una secuencia posible para la muestra: el consenso o una lectura sola."""

    seq: str
    qual: list[int]
    origen: str
    extra: dict = field(default_factory=dict)  # solapamiento/discrepancias/conflictos
    invertir: bool = False  # las R se dan vuelta DESPUÉS de recortar


@dataclass(frozen=True)
class Elegida:
    seq: str
    origen: str
    extra: dict
    met: Metricas
    grupo: Grupo


def recortar(seq: str, qual: Sequence[int], umbral: int, invertir: bool) -> tuple[str, list]:
    """
    Recorta y, si es una R, la da vuelta para dejarla orientada como forward.

    El recorte se hace SIEMPRE en la orientación original de la lectura, porque
    Mott no es simétrico (la calidad cae distinto al principio y al final).
    """
    a, b = recorte_mott(qual, umbral)
    s, q = seq[a:b], qual[a:b]
    if invertir:
        s, q = str(Seq(s).reverse_complement()), q[::-1]
    return s, q


def candidatos(con_senal: Sequence[Lectura], min_solap: int) -> list[Candidato]:
    """El consenso F+R (si se puede armar) primero, después cada lectura sola."""
    lista = []
    f = next((lec for lec in con_senal if lec.sentido == "F"), None)
    r = next((lec for lec in con_senal if lec.sentido == "R"), None)
    if f and r:
        c = consenso_fr(f.seq, f.qual, r.seq, r.qual, min_solap)
        if c.ok:
            extra = dict(
                solapamiento=c.solap, discrepancias=c.discrepancias, conflictos=c.conflictos
            )
            lista.append(Candidato(c.seq, c.qual, ORIGEN_CONSENSO, extra))
    for lec in con_senal:
        lista.append(Candidato(lec.seq, lec.qual, f"SOLO_{lec.sentido}", {}, lec.sentido == "R"))
    return lista


def elegir_secuencia(cands: Sequence[Candidato], params: Parametros) -> tuple[Elegida | None, int]:
    """
    Primero busca candidatos que cumplan el estándar con recorte estricto
    (CONFIABLE). Si ninguno cumple, el más largo con recorte laxo (DUDOSA),
    siempre que llegue al largo mínimo laxo.

    Devuelve también el largo máximo que se conseguía con recorte estricto,
    que se informa en el motivo de las DUDOSAS.
    """
    aprobados = []
    for c in cands:
        s, q = recortar(c.seq, c.qual, params.umbral_q, c.invertir)
        ok, met = cumple_estandar(
            s,
            q,
            largo_min=params.largo_min,
            q_media_min=params.q_media_min,
            pct_q20_min=params.pct_q20_min,
        )
        if ok:
            aprobados.append(Elegida(s, c.origen, c.extra, met, Grupo.CONFIABLE))
    if aprobados:
        # max() se queda con el primero en caso de empate, igual que el original
        mejor_sola = max(
            (e for e in aprobados if e.origen != ORIGEN_CONSENSO),
            key=lambda e: e.met.largo,
            default=None,
        )
        cons = next((e for e in aprobados if e.origen == ORIGEN_CONSENSO), None)
        if cons and (
            mejor_sola is None or cons.met.largo >= PROPORCION_MIN_CONSENSO * mejor_sola.met.largo
        ):
            return cons, 0
        return mejor_sola, 0

    elegido = None
    largo_estricto_max = 0
    for c in cands:
        s_e, _ = recortar(c.seq, c.qual, params.umbral_q, c.invertir)
        largo_estricto_max = max(largo_estricto_max, len(s_e))
        s, q = recortar(c.seq, c.qual, params.umbral_q_laxo, c.invertir)
        met = metricas(s, q)
        # '>' estricto: ante empate se queda el primero (el consenso va primero)
        if met.largo >= params.largo_min_laxo and (
            elegido is None or met.largo > elegido.met.largo
        ):
            elegido = Elegida(s, c.origen, c.extra, met, Grupo.DUDOSA)
    return elegido, largo_estricto_max


def motivos(elegida: Elegida, largo_estricto_max: int, params: Parametros) -> list[str]:
    """Por qué una muestra no llegó a CONFIABLE, y alertas que aplican a cualquiera."""
    met, lista = elegida.met, []
    if elegida.grupo == Grupo.DUDOSA:
        lista.append(
            f"con recorte Q{params.umbral_q} quedaban {largo_estricto_max} pb"
            f" - se usó recorte Q{params.umbral_q_laxo}"
        )
        if met.largo < params.largo_min:
            lista.append(f"largo {met.largo} < {params.largo_min}")
        if met.q_media < params.q_media_min:
            lista.append(f"Q media {met.q_media} < {params.q_media_min}")
        if met.pct_q20 < params.pct_q20_min:
            lista.append(f"{met.pct_q20}% bases Q20 < {params.pct_q20_min}%")
        if met.n_amb:
            lista.append(f"{met.n_amb} bases ambiguas")
    conflictos = elegida.extra.get("conflictos", 0)
    if conflictos >= CONFLICTOS_MEZCLA:
        lista.append(f"{conflictos} conflictos F/R con buena calidad: posible mezcla")
    return lista


def asignar_grupo(nombre: str, lecturas: Sequence[Lectura], params: Parametros) -> Muestra:
    """Toda la decisión para una muestra: qué secuencia la representa y en qué grupo queda."""
    m = Muestra(nombre=nombre, archivos=tuple(lec.archivo for lec in lecturas))
    con_senal = [lec for lec in lecturas if lec.senal != Senal.SIN_SENAL]
    if not con_senal:
        m.motivos = ["ninguna lectura con señal utilizable"]
        return m

    elegida, largo_estricto_max = elegir_secuencia(candidatos(con_senal, params.min_solap), params)
    if elegida is None:
        m.motivos = [
            f"hay señal pero ni con recorte Q{params.umbral_q_laxo} se llega a "
            f"{params.largo_min_laxo} pb"
        ]
        return m

    m.grupo = elegida.grupo
    m.origen = elegida.origen
    m.secuencia = elegida.seq
    m.largo = elegida.met.largo
    m.q_media = elegida.met.q_media
    m.pct_q20 = elegida.met.pct_q20
    m.solapamiento = elegida.extra.get("solapamiento")
    m.discrepancias = elegida.extra.get("discrepancias")
    m.conflictos = elegida.extra.get("conflictos")
    m.motivos = motivos(elegida, largo_estricto_max, params)
    return m
