"""
El orquestador: el único módulo que conoce el orden de los pasos.

  1. Lee los .ab1 y evalúa la calidad de cada lectura.
  2. Por muestra: arma la mejor secuencia posible y la clasifica.
  3. Compara las DUDOSAS contra las CONFIABLES de la misma corrida.
  4. BLAST (megablast para CONFIABLES, blastn sensible para DUDOSAS).
  5. Escribe los informes.

Fase 1: los mensajes siguen saliendo por print() y los errores fatales por
sys.exit(), exactamente como en el script original. En la fase 2 esto pasa a
un callback de progreso y a excepciones, para que la ventana pueda mostrar una
barra de progreso y cancelar.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

from sanger.blast.base import MotorBlast
from sanger.blast.interpretacion import interpretar
from sanger.blast.local import MotorLocal
from sanger.blast.remoto import MotorRemoto, configurar_email
from sanger.clasificacion import asignar_grupo
from sanger.config import Parametros
from sanger.ensamblado.comparacion import comparar_con_confiables, veredicto_comparacion
from sanger.io.ab1 import descubrir_archivos, leer_ab1
from sanger.io.informes import (
    COLUMNAS_QC,
    COLUMNAS_RESULTADOS,
    escribir_csv,
    escribir_fasta,
    escribir_hits_json,
    filas_qc,
    filas_resultados,
    texto_resumen,
)
from sanger.io.nombres import muestra_y_sentido
from sanger.modelos import Grupo, Lectura, Resultado
from sanger.qc.metricas import evaluar_lectura


def _leer_y_evaluar(ruta: Path, params: Parametros) -> Lectura:
    muestra, sentido = muestra_y_sentido(ruta.name, params.primers_f, params.primers_r)
    error = None
    try:
        seq, qual = leer_ab1(ruta)
    except Exception as e:
        # un archivo corrupto no frena la corrida: queda como lectura vacía
        # (SIN_SEÑAL) y el resto sigue
        seq, qual, error = "", [], str(e)
    return evaluar_lectura(
        ruta.name,
        muestra,
        sentido,
        seq,
        qual,
        umbral_q=params.umbral_q,
        umbral_q_laxo=params.umbral_q_laxo,
        largo_min=params.largo_min,
        min_bases_q20=params.min_bases_q20,
        error=error,
    )


def motor_por_defecto(params: Parametros, carpeta_xml: Path) -> MotorBlast:
    if params.blast_local:
        return MotorLocal(carpeta_xml, params.blast_local)
    return MotorRemoto(carpeta_xml, params.db, params.taxon, params.lote)


def ejecutar(params: Parametros, motor: MotorBlast | None = None) -> Resultado:
    """
    Corre el análisis completo y escribe los informes en params.salida.

    `motor` permite reemplazar el BLAST (los tests usan uno falso); si no se
    pasa, se usa NCBI o blastn local según los parámetros.
    """
    t_inicio = time.time()
    t_blast = 0.0
    entrada, salida = params.entrada, params.salida
    salida.mkdir(parents=True, exist_ok=True)
    xml_dir = salida / "blast_xml"
    xml_dir.mkdir(exist_ok=True)
    if params.email:
        configurar_email(params.email)

    archivos = descubrir_archivos(entrada)
    if not archivos:
        sys.exit(f"No encontré .ab1 en {entrada}")
    print(f"Encontré {len(archivos)} cromatogramas en {entrada}\n")

    # ---- 1. QC por lectura ------------------------------------------------
    lecturas = []
    for ruta in archivos:
        lec = _leer_y_evaluar(ruta, params)
        lecturas.append(lec)
        print(
            f"  {lec.archivo:<38} {lec.muestra:<12} {lec.sentido}  crudo={lec.largo_crudo:>4} "
            f"Q={lec.q_media_cruda:<5} Q20={lec.bases_q20:>3}  "
            f"recorte Q{params.umbral_q}={lec.largo_estricto:>3} "
            f"Q{params.umbral_q_laxo}={lec.largo_laxo:>3}  {lec.senal.value}"
        )
    escribir_csv(
        salida / "01_QC_lecturas.csv",
        COLUMNAS_QC,
        filas_qc(lecturas),
        params.sep_csv,
        params.decimal_coma,
    )

    # ---- 2. Por muestra: construir secuencia y clasificar -------------------
    por_muestra = defaultdict(list)
    for lec in lecturas:
        por_muestra[lec.muestra].append(lec)

    muestras = []
    print("\nClasificación por muestra:")
    for nombre, ls in sorted(por_muestra.items()):
        m = asignar_grupo(nombre, ls, params)
        muestras.append(m)
        if m.grupo == Grupo.RECHAZADA:
            print(f"  {nombre:<12} RECHAZADA    {m.motivo}")
        else:
            print(
                f"  {nombre:<12} {m.grupo.value:<12} {m.origen:<13} {m.largo:>4} pb  "
                f"Q={m.q_media:<5} {m.motivo}"
            )

    confiables = [m for m in muestras if m.grupo == Grupo.CONFIABLE]
    dudosas = [m for m in muestras if m.grupo == Grupo.DUDOSA]
    escribir_fasta(salida / "02_confiables.fasta", confiables)
    escribir_fasta(salida / "03_dudosas.fasta", dudosas, revisar=True)

    # ---- 3. Dudosas vs confiables de la misma corrida -----------------------
    refs = [(m.nombre, m.secuencia) for m in confiables]
    for m in dudosas:
        # se usa la lectura cruda más informativa (más bases Q20), no la recortada
        lec = max(por_muestra[m.nombre], key=lambda x: x.bases_q20)
        d = comparar_con_confiables(lec.seq, lec.qual, refs) if refs else None
        m.vs_confiables = veredicto_comparacion(d)

    # ---- 4. BLAST -----------------------------------------------------------
    if not params.no_blast:
        t0_blast = time.time()
        motor = motor or motor_por_defecto(params, xml_dir)
        for grupo, lista, mega in (
            (Grupo.CONFIABLE, confiables, True),
            (Grupo.DUDOSA, dudosas, False),
        ):
            if not lista:
                continue
            modo = "megablast" if mega else "blastn (sensible)"
            if params.blast_local:
                print(
                    f"\nBLAST local {modo} de {len(lista)} muestras {grupo.value}S "
                    f"contra {params.blast_local}"
                )
            else:
                print(
                    f"\nBLAST remoto {modo} de {len(lista)} muestras {grupo.value}S "
                    f"contra {params.db}"
                    + (f" [{params.taxon}]" if params.taxon else "")
                    + f", lotes de {params.lote}"
                )
            hits = motor.buscar([(m.nombre, m.secuencia, m.largo) for m in lista], mega)
            for m in lista:
                m.hits = hits.get(m.nombre, [])
            for m in lista:
                m.interpretacion = interpretar(m.hits, params.ident_min, params.cob_min)
                h = m.hits[0] if m.hits else None
                print(
                    f"  {m.nombre:<12} {h.especie if h else 'sin hit':<28} "
                    f"{h.identidad if h else '-':>6}%  -> {m.interpretacion}"
                )
        t_blast = time.time() - t0_blast
    for m in muestras:
        if m.interpretacion is None:
            con_blast = m.grupo != Grupo.RECHAZADA and not params.no_blast
            m.interpretacion = "sin_blast" if con_blast else ""

    # ---- 5. Informes --------------------------------------------------------
    escribir_csv(
        salida / "04_resultados.csv",
        COLUMNAS_RESULTADOS,
        filas_resultados(muestras),
        params.sep_csv,
        params.decimal_coma,
    )
    escribir_hits_json(salida / "05_hits_completos.json", muestras)

    t_total = time.time() - t_inicio
    texto = texto_resumen(lecturas, muestras, not params.no_blast, t_total, t_blast)
    (salida / "00_resumen.txt").write_text(texto, encoding="utf-8")
    print("\n" + texto + f"\n\nListo. Resultados en {salida.resolve()}")
    return Resultado(lecturas, muestras, segundos_total=t_total, segundos_blast=t_blast)
