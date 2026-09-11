"""BLAST con blastn instalado en la máquina (BLAST+), contra una base propia."""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from Bio.Blast import NCBIXML

from sanger.blast.base import Consulta
from sanger.blast.interpretacion import resumir_hits
from sanger.modelos import Hit


def blast_local(nombre: str, seq: str, carpeta_xml: Path, db: str, megablast=True, n_hits=10):
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
        except FileNotFoundError:
            # (fase 2: esto pasa a ser una excepción, no un sys.exit)
            sys.exit("No encuentro 'blastn'. Instalá BLAST+ (sudo apt install ncbi-blast+).")
        except subprocess.CalledProcessError as e:
            print(f"   [BLAST local] falló para {nombre}: {e.stderr.strip()}")
            return None
    with open(xml) as fh:
        return NCBIXML.read(fh)


class MotorLocal:
    """blastn local, una secuencia por vez (con base local tarda segundos)."""

    def __init__(self, carpeta_xml: Path, db: str):
        self.carpeta_xml = carpeta_xml
        self.db = db

    def buscar(self, consultas: Sequence[Consulta], megablast: bool) -> dict[str, list[Hit]]:
        return {
            nombre: resumir_hits(
                blast_local(nombre, seq, self.carpeta_xml, self.db, megablast), largo
            )
            for nombre, seq, largo in consultas
        }
