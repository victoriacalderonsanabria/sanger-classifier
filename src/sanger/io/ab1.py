"""Lectura de cromatogramas .ab1."""

from pathlib import Path

from Bio import SeqIO


def leer_ab1(ruta: Path) -> tuple[str, list[int]]:
    """
    Secuencia y calidades Phred de un cromatograma.

    Ojo: Biopython toma la secuencia de la etiqueta PBAS2 (la que llamó el
    basecaller del secuenciador), no de PBAS1 (la editada a mano). Si alguien
    corrige bases en un editor de cromatogramas, esas correcciones no se ven acá.
    """
    rec = SeqIO.read(ruta, "abi")
    return str(rec.seq), list(rec.letter_annotations.get("phred_quality", []))


def descubrir_archivos(entrada: Path) -> list[Path]:
    """Todos los .ab1 de la carpeta y sus subcarpetas, en orden alfabético."""
    return sorted(p for p in Path(entrada).rglob("*") if p.suffix.lower() == ".ab1")
