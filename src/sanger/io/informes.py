"""
Escritura de los informes: CSV, FASTA, JSON y resumen.

Los nombres, el orden de las columnas y el formato son decisiones tomadas con
Victoria (ver CLAUDE.md): no se cambian sin preguntar.
"""

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from sanger.modelos import SEP_INTERNO, Grupo, Lectura, Muestra, Senal

COLUMNAS_QC = [
    "archivo", "muestra", "sentido", "largo_crudo", "q_media_cruda", "amb_cruda", "bases_q20",
    "largo_estricto", "q_media_estricto", "largo_laxo", "senal",
]  # fmt: skip

# Identificación primero, textos explicativos al final, archivos último.
COLUMNAS_RESULTADOS = [
    "muestra", "grupo", "origen", "largo", "q_media", "pct_q20", "solapamiento", "discrepancias",
    "conflictos",
    "especie_1", "identidad_1", "cobertura_1", "evalue_1", "accession_1",
    "especie_2", "identidad_2", "especie_3", "identidad_3", "interpretacion",
    "motivo", "vs_confiables", "archivos",
]  # fmt: skip

ORDEN_GRUPOS = {Grupo.CONFIABLE: 0, Grupo.DUDOSA: 1, Grupo.RECHAZADA: 2}


def escribir_csv(ruta, columnas, filas, sep=";", decimal_coma=True) -> None:
    """
    Escribe un CSV listo para abrir con doble clic.

      sep=";"  + decimal_coma=True  -> Excel en español: abre en columnas y toma
                                       los números como números. Se agrega BOM
                                       UTF-8 para que los acentos salgan bien.
      sep=","  + decimal_coma=False -> estándar internacional (pandas, R).
    """
    codificacion = "utf-8-sig" if sep == ";" else "utf-8"
    with open(ruta, "w", newline="", encoding=codificacion) as fh:
        w = csv.DictWriter(fh, fieldnames=columnas, delimiter=sep, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            if decimal_coma:
                fila = {
                    k: (str(v).replace(".", ",") if isinstance(v, float) else v)
                    for k, v in fila.items()
                }
            w.writerow({k: fila.get(k, "") for k in columnas})


def _celda(valor):
    """None (el dato no aplica) sale como celda vacía."""
    return "" if valor is None else valor


def filas_qc(lecturas: Iterable[Lectura]) -> list[dict]:
    return [
        dict(
            archivo=lec.archivo,
            muestra=lec.muestra,
            sentido=lec.sentido,
            largo_crudo=lec.largo_crudo,
            q_media_cruda=lec.q_media_cruda,
            amb_cruda=lec.amb_cruda,
            bases_q20=lec.bases_q20,
            largo_estricto=lec.largo_estricto,
            q_media_estricto=lec.q_media_estricto,
            largo_laxo=lec.largo_laxo,
            senal=Senal(lec.senal).value,
        )
        for lec in lecturas
    ]


def filas_resultados(muestras: Iterable[Muestra]) -> list[dict]:
    """Una fila por muestra, ordenadas CONFIABLE → DUDOSA → RECHAZADA y por nombre."""
    filas = []
    for m in sorted(muestras, key=lambda x: (ORDEN_GRUPOS[x.grupo], x.nombre)):
        fila = {k: "" for k in COLUMNAS_RESULTADOS}
        fila.update(
            muestra=m.nombre,
            grupo=m.grupo.value,
            origen=m.origen,
            largo=m.largo,
            q_media=_celda(m.q_media),
            pct_q20=_celda(m.pct_q20),
            solapamiento=_celda(m.solapamiento),
            discrepancias=_celda(m.discrepancias),
            conflictos=_celda(m.conflictos),
            interpretacion=_celda(m.interpretacion),
            motivo=m.motivo,
            vs_confiables=_celda(m.vs_confiables),
            archivos=SEP_INTERNO.join(m.archivos),
        )
        for n, h in enumerate(m.hits, 1):
            fila[f"especie_{n}"], fila[f"identidad_{n}"] = h.especie, h.identidad
            if n == 1:
                fila["cobertura_1"], fila["evalue_1"], fila["accession_1"] = (
                    h.cobertura,
                    h.evalue,
                    h.accession,
                )
        filas.append(fila)
    return filas


def escribir_fasta(ruta: Path, muestras: Sequence[Muestra], revisar: bool = False) -> None:
    """
    Secuencias finales, orientadas como forward.

    Con revisar=True (las DUDOSAS) el motivo va en la descripción, así se ven
    al pegarlas en BLAST web o al abrir el archivo.
    """
    registros = []
    for m in muestras:
        descripcion = f"{m.origen} len={m.largo}"
        if revisar:
            descripcion += f" REVISAR: {m.motivo}"
        registros.append(SeqRecord(Seq(m.secuencia), id=m.nombre, description=descripcion))
    SeqIO.write(registros, ruta, "fasta")


def escribir_hits_json(ruta: Path, muestras: Iterable[Muestra]) -> None:
    """Títulos completos de GenBank de cada hit, por muestra."""
    datos = {m.nombre: [h.como_dict() for h in m.hits] for m in muestras if m.hits}
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, indent=2, ensure_ascii=False)


def formatear_duracion(seg: float) -> str:
    seg = int(round(seg))
    return f"{seg // 60} min {seg % 60} s" if seg >= 60 else f"{seg} s"


def texto_resumen(
    lecturas: Sequence[Lectura],
    muestras: Sequence[Muestra],
    con_blast: bool,
    segundos_total: float,
    segundos_blast: float,
) -> str:
    """El contenido de 00_resumen.txt: conteos por grupo, por resultado de BLAST y tiempos."""
    confiables = [m for m in muestras if m.grupo == Grupo.CONFIABLE]
    dudosas = [m for m in muestras if m.grupo == Grupo.DUDOSA]
    rechazadas = [m for m in muestras if m.grupo == Grupo.RECHAZADA]
    n_senal = {s: sum(lec.senal == s for lec in lecturas) for s in Senal}
    n_consenso = sum(m.origen == "CONSENSO_F+R" for m in confiables)
    resumen = [
        f"Cromatogramas: {len(lecturas)}  (BUENA: {n_senal[Senal.BUENA]}, "
        f"PARCIAL: {n_senal[Senal.PARCIAL]}, "
        f"SIN_SEÑAL: {n_senal[Senal.SIN_SENAL]})",
        f"Muestras: {len(muestras)}",
        f"  CONFIABLE:   {len(confiables)}  (consenso F+R: {n_consenso})",
        f"  DUDOSA:      {len(dudosas)}",
        f"  RECHAZADA:   {len(rechazadas)}",
    ]
    if con_blast:
        for grupo, lista in ((Grupo.CONFIABLE, confiables), (Grupo.DUDOSA, dudosas)):
            cnt = defaultdict(int)
            for m in lista:
                # "identidad_baja (91.2% < 97.0%): ..." se cuenta como "identidad_baja"
                cnt[m.interpretacion.split(":")[0].split(" (")[0]] += 1
            conteos = ", ".join(f"{k}={v}" for k, v in sorted(cnt.items()))
            resumen.append(f"BLAST {grupo.value}: " + conteos)
    resumen.append(
        f"Tiempo total: {formatear_duracion(segundos_total)}  "
        f"(BLAST: {formatear_duracion(segundos_blast)}; "
        f"QC, consenso e informes: {formatear_duracion(segundos_total - segundos_blast)})"
    )
    return "\n".join(resumen)
