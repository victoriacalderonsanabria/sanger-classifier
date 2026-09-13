"""BLAST remoto contra NCBI, en lotes y con caché por muestra."""

import json
import logging
import random
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
# Esperas crecientes entre reintentos: si NCBI está saturado, insistir cada 30
# segundos no ayuda; darle más aire sí (BUG-4). El jitter evita que varias
# corridas simultáneas vuelvan a golpear todas juntas.
ESPERAS = (30, 60, 120)
JITTER = 0.25  # ±25 % sobre la espera


def espera_con_jitter(intento: int, azar=None) -> float:
    """Cuánto esperar antes del siguiente intento."""
    # se resuelve acá y no en el valor por defecto, para poder reemplazarlo
    azar = azar or random.random
    base = ESPERAS[min(intento, len(ESPERAS) - 1)]
    return base * (1 + JITTER * (2 * azar() - 1))


def configurar_email(email: str, herramienta: str = "sanger-classifier") -> None:
    """
    Le dice a NCBI quién consulta.

    BUG-2 revisado en la fase 4: **sí funciona**. En la versión instalada de
    Biopython, `qblast` arma el pedido con `parameters.update({"email": email,
    "tool": tool})` leyendo estas variables del módulo. NCBI pide los dos datos
    para poder avisar antes de bloquear a alguien que consulta de más.
    """
    NCBIWWW.email = email
    NCBIWWW.tool = herramienta


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
    etiqueta: str = "",
) -> dict[str, list[Hit] | None]:
    """
    Manda hasta `tamano_lote` secuencias en un solo envío.

    El tiempo de BLAST remoto es casi todo espera en la cola de NCBI: mandando un
    FASTA con muchas secuencias se espera la cola una vez por lote y no una vez
    por secuencia. Los resultados se guardan por muestra en
    carpeta_cache/<muestra>.hits.json, así si la corrida se corta, al relanzarla
    solo se envían las que faltan.

    `etiqueta` distingue los XML crudos de cada llamada: sin ella, la llamada de
    las DUDOSAS pisaba el `lote_1.xml` que había dejado la de las CONFIABLES,
    porque la numeración de lotes arranca de nuevo en cada llamada.
    """
    resultados: dict[str, list[Hit] | None] = {}
    pendientes = []
    for nombre, seq, largo in items:
        cache = carpeta_cache / f"{nombre}.hits.json"
        if cache.exists():
            resultados[nombre] = [Hit(**h) for h in json.loads(cache.read_text(encoding="utf-8"))]
        else:
            pendientes.append((nombre, seq, largo))
    log.info("BLAST remoto: %d en caché, %d por enviar", len(resultados), len(pendientes))
    total_lotes = (len(pendientes) + tamano_lote - 1) // tamano_lote

    # Lo que está en caché se resuelve al instante: se avisa aparte de lo que hay
    # que consultar, así en un relanzamiento la barra avanza de verdad.
    if pendientes:
        cuantos = f"{len(pendientes)} a consultar en {total_lotes} "
        cuantos += "lote" if total_lotes == 1 else "lotes"
    else:
        cuantos = "nada para consultar"
    progreso(
        Progreso(
            "blast",
            len(resultados),
            len(items),
            detalle=f"{len(items)} muestras · {len(resultados)} en caché · {cuantos}",
        )
    )
    if not pendientes:
        return resultados

    largos = {n: lg for n, _, lg in pendientes}
    for i in range(0, len(pendientes), tamano_lote):
        if cancelado():
            raise Cancelado("cancelado antes de enviar el lote a NCBI")
        n_lote = i // tamano_lote + 1
        cual_lote = f"lote {n_lote} de {total_lotes}"
        lote = pendientes[i : i + tamano_lote]
        fasta = "".join(f">{n}\n{seq}\n" for n, seq, _ in lote)
        progreso(
            Progreso(
                "blast",
                len(resultados),
                len(items),
                f"   enviando lote de {len(lote)} secuencias a NCBI ({db}, "
                f"{'megablast' if megablast else 'blastn'}) ...",
                fin="",
                detalle=f"{cual_lote} · esperando respuesta de NCBI",
            )
        )
        t0 = time.time()
        kwargs = dict(
            program="blastn", database=db, sequence=fasta, megablast=megablast, hitlist_size=n_hits
        )
        if entrez_query:
            kwargs["entrez_query"] = entrez_query
        registros = None
        ultimo_error: Exception | None = None
        for intento in range(INTENTOS):
            try:
                h = NCBIWWW.qblast(**kwargs)
                xml_txt = h.read()
                h.close()
                nombre_xml = f"lote_{etiqueta}_{n_lote}.xml" if etiqueta else f"lote_{n_lote}.xml"
                # BUG-3 corregido: sin encoding=, en Windows se escribía en
                # cp1252 y reventaba con caracteres que no existen ahí (nombres
                # de GenBank con tildes o letras de otros alfabetos)
                (carpeta_cache / nombre_xml).write_text(xml_txt, encoding="utf-8")
                registros = list(NCBIXML.parse(StringIO(xml_txt)))
                break
            except Exception as e:
                log.warning("BLAST remoto, intento %d de %d falló: %s", intento + 1, INTENTOS, e)
                ultimo_error = e
                progreso(
                    Progreso(
                        "blast",
                        len(resultados),
                        len(items),
                        f"\n   [BLAST] intento {intento + 1} falló: {e}",
                        detalle=f"{cual_lote} · reintento {intento + 1} de {INTENTOS}",
                    )
                )
                time.sleep(espera_con_jitter(intento))
        # el tiempo se mide en el mismo punto que el original, para que el
        # número impreso sea el mismo
        segundos = time.time() - t0
        progreso(
            Progreso(
                "blast",
                len(resultados),
                len(items),
                f" {segundos:.0f} s",
                detalle=f"{cual_lote} · "
                + ("respuesta recibida" if registros is not None else "sin respuesta"),
            )
        )
        if registros is None:
            # BUG-1 corregido: no se pudo consultar, y eso NO es "no hubo
            # coincidencias". Queda como None (error) y sin cachear, así al
            # relanzar la corrida se reintenta.
            log.error(
                "lote %d: sin respuesta tras %d intentos (%s)", n_lote, INTENTOS, ultimo_error
            )
            for n, _, _ in lote:
                resultados[n] = None
            progreso(
                Progreso(
                    "blast",
                    len(resultados),
                    len(items),
                    detalle=f"{cual_lote} · no se pudo consultar",
                )
            )
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
                # la respuesta llegó pero sin esta consulta: tampoco es "no hubo
                # coincidencias", es que no se sabe qué pasó con ella
                log.error("la respuesta de NCBI no trajo la consulta %s", n)
                resultados[n] = None
        # aviso mudo (no se imprime): mueve la barra al cerrar el lote
        progreso(Progreso("blast", len(resultados), len(items), detalle=f"{cual_lote} · resuelto"))
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
    ) -> dict[str, list[Hit] | None]:
        return blast_remoto_lote(
            consultas,
            self.carpeta_cache,
            self.db,
            megablast,
            entrez_query=self.entrez_query,
            tamano_lote=self.tamano_lote,
            progreso=progreso,
            cancelado=cancelado,
            # CONFIABLES y DUDOSAS son dos llamadas: sin esto la segunda pisaba
            # el XML crudo de la primera
            etiqueta="megablast" if megablast else "blastn",
        )
