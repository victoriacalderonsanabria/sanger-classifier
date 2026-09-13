"""BLAST con blastn instalado en la máquina (BLAST+), contra una base propia."""

import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

from Bio.Blast import NCBIXML

from sanger.blast.base import Consulta
from sanger.blast.interpretacion import resumir_hits
from sanger.errores import BlastError, Cancelado
from sanger.modelos import Avisar, Hit, PreguntarCancelado, Progreso, nunca_cancelado, sin_aviso

log = logging.getLogger(__name__)


def blast_local(
    nombre: str,
    seq: str,
    carpeta_xml: Path,
    db: str,
    megablast=True,
    n_hits=10,
    progreso: Avisar = sin_aviso,
):
    """
    Corre blastn y devuelve el registro de Biopython (o None si falló).

    El XML queda en carpeta_xml y se reutiliza si ya existe, igual que el
    caché del remoto.
    """
    xml = carpeta_xml / f"{nombre}.xml"
    if not xml.exists():
        fa = carpeta_xml / f"{nombre}.query.fa"
        fa.write_text(f">{nombre}\n{seq}\n")
        cmd = [
            "blastn", "-task", "megablast" if megablast else "blastn", "-query", str(fa),
            "-db", db, "-outfmt", "5", "-max_target_seqs", str(n_hits), "-out", str(xml),
        ]  # fmt: skip
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise BlastError(
                "No encuentro 'blastn'. Instalá BLAST+ (sudo apt install ncbi-blast+)."
            ) from e
        except subprocess.CalledProcessError as e:
            # una muestra que falla no corta la corrida: queda sin hits
            log.warning("blastn falló para %s: %s", nombre, e.stderr.strip())
            progreso(
                Progreso("blast", 0, 0, f"   [BLAST local] falló para {nombre}: {e.stderr.strip()}")
            )
            return None
    with open(xml) as fh:
        return NCBIXML.read(fh)


class MotorLocal:
    """blastn local, una secuencia por vez (con base local tarda segundos)."""

    def __init__(self, carpeta_xml: Path, db: str):
        self.carpeta_xml = carpeta_xml
        self.db = db

    def buscar(
        self,
        consultas: Sequence[Consulta],
        megablast: bool,
        progreso: Avisar = sin_aviso,
        cancelado: PreguntarCancelado = nunca_cancelado,
    ) -> dict[str, list[Hit] | None]:
        resultados: dict[str, list[Hit] | None] = {}
        for hechas, (nombre, seq, largo) in enumerate(consultas):
            if cancelado():
                raise Cancelado("cancelado durante el BLAST local")
            rec = blast_local(nombre, seq, self.carpeta_xml, self.db, megablast, progreso=progreso)
            # si blastn falló, no se pudo consultar: no es "sin coincidencias"
            resultados[nombre] = resumir_hits(rec, largo) if rec is not None else None
            progreso(Progreso("blast", hechas + 1, len(consultas)))
        return resultados
