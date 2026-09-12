"""BLAST remoto contra NCBI, en lotes y con caché por muestra."""

import json
import logging
import time
from collections.abc import Sequence
from io import StringIO
from pathlib import Path

from Bio.Blast import NCBIWWW, NCBIXML

from sanger.blast.base import Consulta
from sanger.blast.interpretacion import resumir_hits
from sanger.errores import Cancelado
from sanger.modelos import Avisar, Hit, PreguntarCancelado, Progreso, nunca_cancelado, sin_aviso

log = logging.getLogger(__name__)

INTENTOS = 3
ESPERA_ENTRE_INTENTOS = 30  # BUG-4 (fase 4): fija, sin backoff


def configurar_email(email: str) -> None:
    # BUG-2 (se corrige en la fase 4): probablemente no tiene efecto, Biopython
    # no lee el mail de este atributo. Se conserva tal cual hasta entonces.
    NCBIWWW.email = email


def blast_remoto_lote(
    items: Sequence[Consulta],
    carpeta_cache: Path,
    db: str = "nt",
    megablast: bool = True,
    n_hits: int = 10,
    entrez_query: str | None = None,
    tamano_lote: int = 50,
    progreso: Avisar = sin_aviso,
    cancelado: PreguntarCancelado = nunca_cancelado,
) -> dict[str, list[Hit]]:
    """
    Manda hasta `tamano_lote` secuencias en un solo envío.

    El tiempo de BLAST remoto es casi todo espera en la cola de NCBI: mandando un
    FASTA con muchas secuencias se espera la cola una vez por lote y no una vez
    por secuencia. Los resultados se guardan por muestra en
    carpeta_cache/<muestra>.hits.json, así si la corrida se corta, al relanzarla
    solo se envían las que faltan.
    """
    resultados: dict[str, list[Hit]] = {}
    pendientes = []
    for nombre, seq, largo in items:
        cache = carpeta_cache / f"{nombre}.hits.json"
        if cache.exists():
            resultados[nombre] = [Hit(**h) for h in json.loads(cache.read_text(encoding="utf-8"))]
        else:
            pendientes.append((nombre, seq, largo))
    log.info("BLAST remoto: %d en caché, %d por enviar", len(resultados), len(pendientes))
    if not pendientes:
        return resultados

    largos = {n: lg for n, _, lg in pendientes}
    total_lotes = (len(pendientes) + tamano_lote - 1) // tamano_lote
    for i in range(0, len(pendientes), tamano_lote):
        if cancelado():
            raise Cancelado("cancelado antes de enviar el lote a NCBI")
        n_lote = i // tamano_lote + 1
        lote = pendientes[i : i + tamano_lote]
        fasta = "".join(f">{n}\n{seq}\n" for n, seq, _ in lote)
        progreso(
            Progreso(
                "blast",
                n_lote - 1,
                total_lotes,
                f"   enviando lote de {len(lote)} secuencias a NCBI ({db}, "
                f"{'megablast' if megablast else 'blastn'}) ...",
                fin="",
            )
        )
        t0 = time.time()
        kwargs = dict(
            program="blastn", database=db, sequence=fasta, megablast=megablast, hitlist_size=n_hits
        )
        if entrez_query:
            kwargs["entrez_query"] = entrez_query
        registros = None
        for intento in range(INTENTOS):
            try:
                h = NCBIWWW.qblast(**kwargs)
                xml_txt = h.read()
                h.close()
                # BUG-3 (fase 4): sin encoding=, en Windows usa cp1252
                (carpeta_cache / f"lote_{n_lote}.xml").write_text(xml_txt)
                registros = list(NCBIXML.parse(StringIO(xml_txt)))
                break
            except Exception as e:
                log.warning("BLAST remoto, intento %d de %d falló: %s", intento + 1, INTENTOS, e)
                progreso(
                    Progreso(
                        "blast",
                        n_lote - 1,
                        total_lotes,
                        f"\n   [BLAST] intento {intento + 1} falló: {e}",
                    )
                )
                time.sleep(ESPERA_ENTRE_INTENTOS)
        progreso(Progreso("blast", n_lote, total_lotes, f" {time.time() - t0:.0f} s"))
        if registros is None:
            # BUG-1 (fase 4): un fallo de red queda igual que "sin hits"
            for n, _, _ in lote:
                resultados[n] = []
            continue
        vistos = set()
        for rec in registros:
            nombre = rec.query.split()[0]
            vistos.add(nombre)
            hits = resumir_hits(rec, largos.get(nombre, rec.query_length))
            resultados[nombre] = hits
            (carpeta_cache / f"{nombre}.hits.json").write_text(
                json.dumps([h.como_dict() for h in hits], ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        for n, _, _ in lote:
            if n not in vistos:
                resultados[n] = []
    return resultados


class MotorRemoto:
    """NCBI, en lotes y con caché en la carpeta de salida."""

    def __init__(self, carpeta_cache: Path, db: str, entrez_query: str | None, tamano_lote: int):
        self.carpeta_cache = carpeta_cache
        self.db = db
        self.entrez_query = entrez_query
        self.tamano_lote = tamano_lote

    def buscar(
        self,
        consultas: Sequence[Consulta],
        megablast: bool,
        progreso: Avisar = sin_aviso,
        cancelado: PreguntarCancelado = nunca_cancelado,
    ) -> dict[str, list[Hit]]:
        return blast_remoto_lote(
            consultas,
            self.carpeta_cache,
            self.db,
            megablast,
            entrez_query=self.entrez_query,
            tamano_lote=self.tamano_lote,
            progreso=progreso,
            cancelado=cancelado,
        )
