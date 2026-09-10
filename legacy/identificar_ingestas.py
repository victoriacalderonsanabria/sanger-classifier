#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
identificar_ingestas.py
=======================
Pipeline para identificar el hospedador de ingestas sanguíneas de mosquitos
a partir de cromatogramas Sanger (.ab1) del gen COI.

Pasos:
  1. Lee todos los .ab1 de la carpeta de entrada.
  2. Recorta cada lectura por calidad (algoritmo de Mott, el mismo que usa
     Phred/Biopython) y calcula métricas de calidad.
  3. Clasifica cada lectura: PASS / FALLA_CORTA / FALLA_CALIDAD / FALLA_VACIA.
  4. Agrupa las lecturas por muestra (detecta F/R por el nombre del archivo).
     Si hay forward y reverse aprobadas, arma una secuencia consenso.
  5. Envía las secuencias aprobadas a BLAST (NCBI, base nt) y anota el
     mejor hit: especie, % identidad, cobertura, e-value.
  6. Escribe informes CSV, un FASTA con las secuencias limpias y un resumen.

Uso mínimo:
    python identificar_ingestas.py --input carpeta_ab1 --output resultados --email tu@mail.com

Ver todas las opciones:
    python identificar_ingestas.py --help

Requisitos:  pip install biopython
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from Bio import SeqIO, Align
    from Bio.Seq import Seq
    from Bio.SeqRecord import SeqRecord
    from Bio.Blast import NCBIWWW, NCBIXML
except ImportError:
    sys.exit("Falta Biopython. Instalá con:  pip install biopython")


# ----------------------------------------------------------------------------
# 1. Lectura de .ab1 y recorte por calidad
# ----------------------------------------------------------------------------

def leer_ab1(ruta):
    """Devuelve (secuencia, lista de Phred) del cromatograma."""
    rec = SeqIO.read(ruta, "abi")
    seq = str(rec.seq)
    qual = list(rec.letter_annotations.get("phred_quality", []))
    return seq, qual


def recorte_mott(qual, umbral_q):
    """
    Algoritmo de Mott (el que usa phred / Biopython abi-trim).
    Convierte cada Q en una puntuación (umbral - p_error) acumulada y se queda
    con la ventana de suma máxima. Devuelve (inicio, fin) 0-based, fin exclusivo.
    """
    if not qual:
        return 0, 0
    cutoff = 10 ** (-umbral_q / 10.0)         # p. ej. Q20 -> 0.01
    puntaje = 0.0
    mejor = 0.0
    inicio = 0
    mejor_ini, mejor_fin = 0, 0
    for i, q in enumerate(qual):
        p_err = 10 ** (-q / 10.0)
        puntaje += cutoff - p_err
        if puntaje < 0:
            puntaje = 0.0
            inicio = i + 1
        elif puntaje > mejor:
            mejor = puntaje
            mejor_ini, mejor_fin = inicio, i + 1
    return mejor_ini, mejor_fin


def metricas(seq, qual):
    n = len(qual)
    if n == 0:
        return dict(largo=0, q_media=0.0, pct_q20=0.0, n_N=0)
    return dict(
        largo=n,
        q_media=round(sum(qual) / n, 1),
        pct_q20=round(100.0 * sum(1 for q in qual if q >= 20) / n, 1),
        n_N=seq.upper().count("N"),
    )


def evaluar_lectura(ruta, umbral_q, largo_min, q_media_min, pct_q20_min):
    """Lee, recorta y clasifica un .ab1. Devuelve un dict con todo."""
    info = dict(archivo=ruta.name)
    try:
        seq, qual = leer_ab1(ruta)
    except Exception as e:  # archivo corrupto o no es ab1
        info.update(estado="FALLA_VACIA", motivo=f"no se pudo leer: {e}",
                    largo_crudo=0, largo_recortado=0, q_media=0, pct_q20=0, n_N=0,
                    seq_recortada="", qual_recortada=[], seq_cruda="", qual_cruda=[])
        return info

    m_crudo = metricas(seq, qual)
    ini, fin = recorte_mott(qual, umbral_q)
    seq_r, qual_r = seq[ini:fin], qual[ini:fin]
    m = metricas(seq_r, qual_r)

    info.update(largo_crudo=m_crudo["largo"], q_media_cruda=m_crudo["q_media"],
                recorte_ini=ini, recorte_fin=fin,
                largo_recortado=m["largo"], q_media=m["q_media"],
                pct_q20=m["pct_q20"], n_N=m["n_N"],
                seq_recortada=seq_r, qual_recortada=qual_r, seq_cruda=seq, qual_cruda=qual)

    if m_crudo["largo"] == 0:
        info.update(estado="FALLA_VACIA", motivo="cromatograma sin bases")
    elif m["largo"] < largo_min:
        info.update(estado="FALLA_CORTA",
                    motivo=f"solo {m['largo']} pb con calidad tras recorte (mínimo {largo_min})")
    elif m["q_media"] < q_media_min or m["pct_q20"] < pct_q20_min:
        info.update(estado="FALLA_CALIDAD",
                    motivo=f"Q media {m['q_media']} / {m['pct_q20']}% bases >=Q20")
    else:
        info.update(estado="PASS", motivo="")
    return info


# ----------------------------------------------------------------------------
# 2. Nombre de muestra y sentido (F / R) a partir del nombre de archivo
# ----------------------------------------------------------------------------

# Tokens habituales de primers COI y de sentido. Se puede ampliar con --primers.
TOKENS_F = ["LCO1490", "LCO", "VF1", "VF1d", "VF1i", "BCV-F", "COIF", "COI-F", "FWD", "FORWARD", "F"]
TOKENS_R = ["HCO2198", "HCO", "VR1", "VR1d", "VR1i", "BCV-R", "COIR", "COI-R", "REV", "REVERSE", "R"]


def muestra_y_sentido(nombre, extra_f=(), extra_r=()):
    """
    Intenta separar 'ID_de_muestra' y sentido ('F', 'R' o '?') del nombre.
    Ejemplos que reconoce:
        M12_F.ab1, M12-R.ab1, M12_LCO1490.ab1, M12_HCO2198.ab1,
        Mosq07_COI-F_A03.ab1, 2024-05_M3_VF1.ab1
    Si no reconoce nada, la muestra es el nombre completo y el sentido '?'.
    """
    base = re.sub(r"\.ab1$", "", nombre, flags=re.I)
    tokens = re.split(r"[_\-\s\.]+", base)
    tf = {t.upper() for t in list(TOKENS_F) + list(extra_f)}
    tr = {t.upper() for t in list(TOKENS_R) + list(extra_r)}
    sentido, idx = "?", None
    for i, t in enumerate(tokens):
        T = t.upper()
        if T in tf:
            sentido, idx = "F", i
            break
        if T in tr:
            sentido, idx = "R", i
            break
    if idx is None:
        return base, "?"
    # la muestra es todo lo que está antes del token de sentido
    muestra = "_".join(tokens[:idx]) if idx > 0 else "_".join(tokens[idx + 1:])
    return muestra or base, sentido


# ----------------------------------------------------------------------------
# 3. Consenso forward + reverse
# ----------------------------------------------------------------------------

ACGT = set("ACGT")


def consenso_fr(seq_f, qual_f, seq_r, qual_r, umbral_q=20, min_solap=50, q_conflicto=20):
    """
    Consenso F + R a partir de las lecturas CRUDAS (sin recortar):
      1. alinea F contra el reverso-complemento de R (alineamiento local);
      2. en cada posición solapada elige la base con mayor Phred (si una es un
         código de ambigüedad como R/Y/N, gana la base A/C/G/T de la otra);
         la calidad del consenso es la mayor de las dos si coinciden, o la
         diferencia si discrepan;
      3. fuera del solapamiento conserva los extremos de cada lectura;
      4. recorta el consenso con Mott según su calidad.
    Recortar cada lectura por separado antes de unirlas destruye el
    solapamiento cuando una de las dos arranca mal (típico en amplicones cortos).
    Devuelve dict(seq, solap, discrepancias, conflictos, ok).
    'conflictos' cuenta las discrepancias en que AMBAS lecturas tenían Q >=
    q_conflicto: esas son las sospechosas de ingesta mixta (picos dobles).
    """
    rc = str(Seq(seq_r).reverse_complement())
    qual_rc = qual_r[::-1]

    aligner = Align.PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 2
    aligner.mismatch_score = -3
    aligner.open_gap_score = -5
    aligner.extend_gap_score = -2
    aln = aligner.align(seq_f, rc)[0]

    bloques_f, bloques_r = aln.aligned
    vacio = dict(seq="", solap=0, discrepancias=0, conflictos=0, ok=False)
    if len(bloques_f) == 0:
        return vacio
    f_ini, f_fin = bloques_f[0][0], bloques_f[-1][1]
    r_ini, r_fin = bloques_r[0][0], bloques_r[-1][1]
    solap = f_fin - f_ini
    if solap < min_solap:
        vacio["solap"] = solap
        return vacio

    cons, qcons = list(seq_f[:f_ini]), list(qual_f[:f_ini])   # extremo 5' solo de F
    discrep = conflictos = 0
    pos_f, pos_r = f_ini, r_ini
    for (fa, fb), (ra, rb) in zip(bloques_f, bloques_r):
        # región no alineada (indel) antes del bloque: gana la lectura con mejor Q
        gap_f, gap_r = seq_f[pos_f:fa], rc[pos_r:ra]
        if gap_f or gap_r:
            # calidad de la inserción; si una lectura no tiene nada ahí, se usa
            # la calidad de sus bases flanqueantes (una inserción de Q=3 en F no
            # debe imponerse sobre una R de Q=35 que simplemente no la tiene)
            def q_region(qual, a, b):
                if b > a:
                    return sum(qual[a:b]) / (b - a)
                flancos = qual[max(0, a - 1):a + 1]
                return sum(flancos) / max(1, len(flancos))
            qf = q_region(qual_f, pos_f, fa)
            qr = q_region(qual_rc, pos_r, ra)
            if qf >= qr:
                cons += list(gap_f); qcons += list(qual_f[pos_f:fa])
            else:
                cons += list(gap_r); qcons += list(qual_rc[pos_r:ra])
            discrep += 1
            if min(qf, qr) >= q_conflicto:
                conflictos += 1
        for i, j in zip(range(fa, fb), range(ra, rb)):
            bf, br, qf, qr = seq_f[i], rc[j], qual_f[i], qual_rc[j]
            if bf == br:
                cons.append(bf); qcons.append(max(qf, qr))
            else:
                discrep += 1
                if min(qf, qr) >= q_conflicto and bf in ACGT and br in ACGT:
                    conflictos += 1
                if bf not in ACGT and br in ACGT:
                    cons.append(br); qcons.append(qr)
                elif br not in ACGT and bf in ACGT:
                    cons.append(bf); qcons.append(qf)
                elif qf >= qr:
                    cons.append(bf); qcons.append(qf - qr)
                else:
                    cons.append(br); qcons.append(qr - qf)
        pos_f, pos_r = fb, rb
    cons += list(rc[r_fin:]); qcons += list(qual_rc[r_fin:])   # extremo 3' solo de R

    ini, fin = recorte_mott(qcons, umbral_q)
    return dict(seq="".join(cons[ini:fin]), solap=solap, discrepancias=discrep,
                conflictos=conflictos, ok=True)


# ----------------------------------------------------------------------------
# 3b. Diagnóstico de lecturas que fallan el QC pero tienen señal
# ----------------------------------------------------------------------------

def diagnostico_lectura(seq, qual, referencias, q_buena=20):
    """
    Compara una lectura CRUDA (que no pasó el QC) contra las secuencias ya
    identificadas en la corrida, en ambas orientaciones, y separa los desajustes
    según la calidad de la base:
      - si la lectura coincide al 100 % en sus bases de buena calidad y los
        desajustes están todos en bases malas, es esa especie leída con ruido;
      - si hay desajustes también en bases buenas, es otra cosa (o mezcla).
    referencias: lista de dicts con 'muestra', 'especie', 'seq'.
    Devuelve el mejor match como dict.
    """
    aligner = Align.PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 1
    aligner.mismatch_score = -1
    aligner.open_gap_score = -2
    aligner.extend_gap_score = -1
    mejor = None
    for orient, s, q in (("+", seq, qual),
                         ("rc", str(Seq(seq).reverse_complement()), qual[::-1])):
        for ref in referencias:
            aln = aligner.align(s, ref["seq"])[0]
            hi = lo = mhi = mlo = 0
            for (fa, fb), (ra, rb) in zip(*aln.aligned):
                for i, j in zip(range(fa, fb), range(ra, rb)):
                    mm = s[i] != ref["seq"][j]
                    if q[i] >= q_buena:
                        hi += 1; mhi += mm
                    else:
                        lo += 1; mlo += mm
            total = hi + lo
            if total == 0:
                continue
            res = dict(ref_muestra=ref["muestra"], ref_especie=ref["especie"], orientacion=orient,
                       alineado=total, ident_total=round(100 * (total - mhi - mlo) / total, 1),
                       bases_buenas=hi, desajustes_buenas=mhi,
                       ident_buenas=round(100 * (hi - mhi) / hi, 1) if hi else 0.0,
                       bases_malas=lo, desajustes_malas=mlo)
            # criterio de "mejor": más bases buenas coincidentes
            if mejor is None or (hi - mhi) > (mejor["bases_buenas"] - mejor["desajustes_buenas"]):
                mejor = res
    return mejor


def veredicto_diagnostico(d, min_bases_buenas=40):
    if d is None:
        return "SIN_SEÑAL", "no alinea con ninguna secuencia de la corrida"
    if d["bases_buenas"] < min_bases_buenas:
        return "SEÑAL_INSUFICIENTE", (f"solo {d['bases_buenas']} bases de buena calidad alineadas "
                                       f"(mínimo {min_bases_buenas}); no se puede afirmar nada")
    if d["ident_buenas"] >= 98.0:
        return "COMPATIBLE", (f"{d['ident_buenas']}% de identidad en {d['bases_buenas']} bases de buena calidad "
                              f"con {d['ref_especie']} (muestra {d['ref_muestra']}); los {d['desajustes_malas']} "
                              f"desajustes restantes caen en bases de baja calidad -> lectura ruidosa de esa especie")
    if d["ident_buenas"] >= 95.0:
        return "DUDOSO", (f"{d['ident_buenas']}% en bases buenas con {d['ref_especie']}: "
                          f"{d['desajustes_buenas']} desajustes en bases de buena calidad; revisar cromatograma")
    return "DIVERGENTE", (f"solo {d['ident_buenas']}% en bases buenas con {d['ref_especie']}: "
                          f"no es esa especie; hacer BLAST manual de la secuencia cruda")


# ----------------------------------------------------------------------------
# 4. BLAST remoto (NCBI)
# ----------------------------------------------------------------------------

def blast_remoto(nombre, seq, carpeta_xml, db="nt", n_hits=10, entrez_query=None,
                 pausa=3):
    """
    Corre megablast contra `db` en NCBI. Guarda el XML en carpeta_xml y lo
    reutiliza si ya existe (así se puede reanudar sin repetir consultas).
    """
    xml = carpeta_xml / f"{nombre}.xml"
    if not xml.exists():
        kwargs = dict(program="blastn", database=db, sequence=seq,
                      megablast=True, hitlist_size=n_hits)
        if entrez_query:
            kwargs["entrez_query"] = entrez_query
        for intento in range(3):
            try:
                h = NCBIWWW.qblast(**kwargs)
                xml.write_text(h.read())
                h.close()
                break
            except Exception as e:
                print(f"   [BLAST] intento {intento + 1} falló para {nombre}: {e}")
                time.sleep(20)
        else:
            return None
        time.sleep(pausa)   # cortesía con el servidor de NCBI
    with open(xml) as fh:
        return NCBIXML.read(fh)


def blast_local(nombre, seq, carpeta_xml, db, n_hits=10):
    """
    Alternativa sin internet: blastn instalado localmente (BLAST+) contra una
    base propia (p. ej. secuencias COI de vertebrados descargadas de BOLD/GenBank
    y formateadas con `makeblastdb -in coi.fasta -dbtype nucl -out coi_db`).
    Produce el mismo XML que el BLAST remoto.
    """
    import subprocess
    xml = carpeta_xml / f"{nombre}.xml"
    if not xml.exists():
        fa = carpeta_xml / f"{nombre}.query.fa"
        fa.write_text(f">{nombre}\n{seq}\n")
        cmd = ["blastn", "-task", "megablast", "-query", str(fa), "-db", db,
               "-outfmt", "5", "-max_target_seqs", str(n_hits), "-out", str(xml)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            sys.exit("No encuentro 'blastn'. Instalá BLAST+ (sudo apt install ncbi-blast+) o usá BLAST remoto.")
        except subprocess.CalledProcessError as e:
            print(f"   [BLAST local] falló para {nombre}: {e.stderr.strip()}")
            return None
    with open(xml) as fh:
        return NCBIXML.read(fh)


def resumir_hits(rec, largo_query):
    """Extrae hasta 3 hits con especie distinta, para detectar ambigüedad."""
    hits = []
    vistos = set()
    if rec is None:
        return hits
    for al in rec.alignments:
        hsp = al.hsps[0]
        titulo = al.hit_def or al.title
        # especie = primeras dos palabras del título (Género especie)
        m = re.match(r"([A-Z][a-z]+ [a-z]+)", titulo)
        especie = m.group(1) if m else titulo[:40]
        if especie in vistos:
            continue
        vistos.add(especie)
        ident = round(100.0 * hsp.identities / hsp.align_length, 2)
        cob = round(100.0 * hsp.align_length / largo_query, 1)
        hits.append(dict(especie=especie, accession=al.accession,
                         identidad=ident, cobertura=cob, evalue=hsp.expect,
                         titulo=titulo))
        if len(hits) == 3:
            break
    return hits


def interpretar(hits, ident_min=97.0):
    """Regla simple de decisión para la columna 'interpretacion'."""
    if not hits:
        return "sin_hit"
    top = hits[0]
    if top["identidad"] < ident_min:
        return f"identidad_baja (<{ident_min}%) - revisar a mano"
    if len(hits) > 1 and abs(hits[0]["identidad"] - hits[1]["identidad"]) < 1.0:
        return "ambiguo - dos especies con identidad similar"
    if re.search(r"Aedes|Culex|Anopheles|Culicidae|Ochlerotatus|Psorophora|Mansonia|Haemagogus", top["titulo"], re.I):
        return "ADN del mosquito (no del hospedador)"
    if re.search(r"Homo sapiens", top["titulo"]):
        return "humano - verificar posible contaminación"
    return "hospedador_identificado"


# ----------------------------------------------------------------------------
# 5. Programa principal
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", "-i", required=True, help="carpeta con los .ab1")
    ap.add_argument("--output", "-o", default="resultados", help="carpeta de salida")
    ap.add_argument("--email", help="tu e-mail (NCBI lo pide para BLAST remoto)")
    ap.add_argument("--umbral-q", type=int, default=20, help="Q usado en el recorte de Mott (default 20)")
    ap.add_argument("--largo-min", type=int, default=100,
                    help="largo mínimo de la secuencia final (lectura recortada o consenso), pb (default 100)")
    ap.add_argument("--min-util", type=int, default=50,
                    help="pb con calidad que necesita una lectura para aportar al consenso F+R (default 50)")
    ap.add_argument("--q-media-min", type=float, default=25.0, help="Q media mínima tras recorte (default 25)")
    ap.add_argument("--pct-q20-min", type=float, default=80.0, help="%% mínimo de bases >=Q20 (default 80)")
    ap.add_argument("--min-solap", type=int, default=50, help="solapamiento mínimo F/R para consenso (default 50)")
    ap.add_argument("--db", default="nt", help="base de BLAST (default nt; alternativa: core_nt)")
    ap.add_argument("--solo-vertebrados", action="store_true",
                    help="restringe BLAST a Vertebrata (más rápido, evita hits del mosquito)")
    ap.add_argument("--blast-local", metavar="RUTA_DB",
                    help="usar blastn local contra esta base (creada con makeblastdb) en vez de NCBI remoto")
    ap.add_argument("--no-blast", action="store_true", help="solo QC y consenso, sin BLAST")
    ap.add_argument("--primers-f", nargs="*", default=[], help="tokens extra para reconocer forward")
    ap.add_argument("--primers-r", nargs="*", default=[], help="tokens extra para reconocer reverse")
    ap.add_argument("--perfil", choices=["estandar", "flexible"], default="estandar",
                    help="'flexible' = largo-min 80, umbral-q 15, min-util 30 (las opciones explícitas mandan)")
    ap.add_argument("--sin-diagnostico", action="store_true",
                    help="no generar la etapa de revisión manual (05_revision_manual.*)")
    args = ap.parse_args()

    if args.perfil == "flexible":
        # solo pisa los valores que el usuario no fijó explícitamente
        if "--largo-min" not in sys.argv: args.largo_min = 80
        if "--umbral-q" not in sys.argv: args.umbral_q = 15
        if "--min-util" not in sys.argv: args.min_util = 30
        print(f"Perfil flexible: largo-min={args.largo_min}, umbral-q={args.umbral_q}, min-util={args.min_util}")

    t_inicio = time.time()
    t_blast = 0.0
    entrada = Path(args.input)
    salida = Path(args.output)
    salida.mkdir(parents=True, exist_ok=True)
    xml_dir = salida / "blast_xml"
    xml_dir.mkdir(exist_ok=True)

    if args.email:
        NCBIWWW.email = args.email

    archivos = sorted(p for p in entrada.rglob("*") if p.suffix.lower() == ".ab1")
    if not archivos:
        sys.exit(f"No encontré archivos .ab1 en {entrada}")
    print(f"Encontré {len(archivos)} cromatogramas en {entrada}\n")

    # --- Paso 1-2: QC lectura por lectura ---------------------------------
    lecturas = []
    for ruta in archivos:
        info = evaluar_lectura(ruta, args.umbral_q, args.largo_min, args.q_media_min, args.pct_q20_min)
        info["muestra"], info["sentido"] = muestra_y_sentido(ruta.name, args.primers_f, args.primers_r)
        lecturas.append(info)
        print(f"  {info['archivo']:<40} {info['muestra']:<15} {info['sentido']}  "
              f"{info['largo_crudo']:>4} -> {info['largo_recortado']:>4} pb  "
              f"Q={info['q_media']:<5} {info['estado']}")

    cols_qc = ["archivo", "muestra", "sentido", "largo_crudo", "q_media_cruda", "recorte_ini",
               "recorte_fin", "largo_recortado", "q_media", "pct_q20", "n_N", "estado", "motivo"]
    with open(salida / "01_QC_lecturas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_qc, extrasaction="ignore")
        w.writeheader()
        for l in lecturas:
            w.writerow({k: l.get(k, "") for k in cols_qc})

    # --- Paso 3: agrupar por muestra y armar consenso ---------------------
    por_muestra = defaultdict(list)
    for l in lecturas:
        por_muestra[l["muestra"]].append(l)

    muestras = []
    registros_fasta = []
    print("\nArmado de secuencias por muestra:")
    for nombre, ls in sorted(por_muestra.items()):
        ok = [l for l in ls if l["estado"] == "PASS"]
        # lecturas con algo de señal (>= min_util pb con calidad): sirven para consenso
        # aunque solas no lleguen al largo mínimo
        utiles = [l for l in ls if l["largo_recortado"] >= args.min_util]
        f = next((l for l in utiles if l["sentido"] == "F"), None)
        r = next((l for l in utiles if l["sentido"] == "R"), None)
        m = dict(muestra=nombre, n_archivos=len(ls), n_pass=len(ok),
                 archivos=";".join(l["archivo"] for l in ls),
                 secuencia="", largo=0, solapamiento="", discrepancias="", conflictos="", nota="")

        if f and r:
            c = consenso_fr(f["seq_cruda"], f["qual_cruda"], r["seq_cruda"], r["qual_cruda"],
                            args.umbral_q, args.min_solap)
            mejor_sola = max((l["largo_recortado"] for l in ok), default=0)
            if c["ok"] and len(c["seq"]) >= args.largo_min and len(c["seq"]) >= 0.9 * mejor_sola:
                notas = []
                if c["conflictos"] >= 3:
                    notas.append(f"{c['conflictos']} posiciones donde F y R discrepan con buena calidad: "
                                 "posible ingesta mixta (picos dobles), revisar cromatogramas")
                elif c["conflictos"] > 0:
                    notas.append(f"{c['conflictos']} discrepancia F/R con buena calidad: revisar esa posición")
                m.update(origen="CONSENSO_F+R", secuencia=c["seq"], largo=len(c["seq"]),
                         solapamiento=c["solap"], discrepancias=c["discrepancias"],
                         conflictos=c["conflictos"], nota="; ".join(notas))
            elif not c["ok"]:
                m["nota"] = f"F y R no solapan (solap={c['solap']}); "
            else:
                m["nota"] = f"consenso F+R de solo {len(c['seq'])} pb tras recorte; "

        if not m["secuencia"]:
            if ok:
                mejor = max(ok, key=lambda l: l["largo_recortado"])
                seq = mejor["seq_recortada"]
                if mejor["sentido"] == "R":
                    seq = str(Seq(seq).reverse_complement())   # orientamos todo como forward
                m.update(origen=f"SOLO_{mejor['sentido']}", secuencia=seq, largo=len(seq))
                m["nota"] += "se usa la lectura individual más larga"
            else:
                m.update(origen="NINGUNA")
                m["nota"] += "ninguna lectura pasó el QC: " + "; ".join(
                    f"{l['archivo']}: {l['motivo']}" for l in ls)
        muestras.append(m)
        print(f"  {nombre:<15} {m['origen']:<14} {m['largo']:>4} pb  {m['nota']}")
        if m["secuencia"]:
            registros_fasta.append(SeqRecord(Seq(m["secuencia"]), id=nombre,
                                             description=f"{m['origen']} len={m['largo']}"))

    SeqIO.write(registros_fasta, salida / "02_secuencias_limpias.fasta", "fasta")

    # --- Paso 4: BLAST ----------------------------------------------------
    if not args.no_blast:
        t0_blast = time.time()
        entrez = "Vertebrata[Organism]" if args.solo_vertebrados else None
        a_blastear = [m for m in muestras if m["secuencia"]]
        if args.blast_local:
            print(f"\nBLAST local de {len(a_blastear)} secuencias contra {args.blast_local}")
        else:
            print(f"\nBLAST remoto de {len(a_blastear)} secuencias contra {args.db} "
                  f"(puede tardar ~1 min por secuencia; los XML se guardan en {xml_dir})")
        for k, m in enumerate(a_blastear, 1):
            print(f"  [{k}/{len(a_blastear)}] {m['muestra']} ...", end="", flush=True)
            if args.blast_local:
                rec = blast_local(m["muestra"], m["secuencia"], xml_dir, args.blast_local)
            else:
                rec = blast_remoto(m["muestra"], m["secuencia"], xml_dir, args.db, entrez_query=entrez)
            hits = resumir_hits(rec, m["largo"])
            m["hits"] = hits
            m["interpretacion"] = interpretar(hits)
            print(f" {hits[0]['especie'] if hits else 'sin hit'} "
                  f"({hits[0]['identidad'] if hits else '-'}%)  -> {m['interpretacion']}")
        for m in muestras:
            if not m["secuencia"]:
                m["hits"], m["interpretacion"] = [], "sin_secuencia"
        t_blast = time.time() - t0_blast

    # --- Paso 4b: diagnóstico de las muestras sin secuencia ----------------
    # Para cada lectura que no pasó el QC pero tiene señal, se compara la
    # lectura cruda contra las secuencias ya identificadas en esta corrida y se
    # informa si es "esa especie con ruido", "otra cosa" o "nada".
    if not args.sin_diagnostico:
        referencias = []
        for m in muestras:
            if not m["secuencia"]:
                continue
            hits = m.get("hits", [])
            especie = hits[0]["especie"] if hits else f"haplotipo de {m['muestra']}"
            referencias.append(dict(muestra=m["muestra"], especie=especie, seq=m["secuencia"]))
        # una referencia por especie/haplotipo (la más larga) para no repetir alineamientos
        por_especie = {}
        for r in referencias:
            if r["especie"] not in por_especie or len(r["seq"]) > len(por_especie[r["especie"]]["seq"]):
                por_especie[r["especie"]] = r
        referencias = list(por_especie.values())

        revision = []
        fasta_rev = []
        sin_seq = [m for m in muestras if not m["secuencia"]]
        print(f"\nDiagnóstico de {len(sin_seq)} muestras sin secuencia "
              f"(contra {len(referencias)} secuencias de referencia de esta corrida):")
        for m in sin_seq:
            for l in por_muestra[m["muestra"]]:
                fila = dict(muestra=m["muestra"], archivo=l["archivo"], sentido=l["sentido"],
                            largo_crudo=l["largo_crudo"], q_media_cruda=l.get("q_media_cruda", 0),
                            bases_q20=sum(1 for q in l["qual_cruda"] if q >= 20))
                # ¿hay algo que mirar? largo razonable y al menos 30 bases con calidad
                if l["largo_crudo"] < 150 or fila["bases_q20"] < 30 or not referencias:
                    fila.update(veredicto="SIN_SEÑAL", detalle="cromatograma sin señal utilizable",
                                ref_especie="", ident_buenas="", bases_buenas="", desajustes_buenas="",
                                ident_total="", alineado="")
                else:
                    d = diagnostico_lectura(l["seq_cruda"], l["qual_cruda"], referencias)
                    v, det = veredicto_diagnostico(d)
                    fila.update(veredicto=v, detalle=det)
                    if d:
                        fila.update(ref_especie=d["ref_especie"], ident_buenas=d["ident_buenas"],
                                    bases_buenas=d["bases_buenas"], desajustes_buenas=d["desajustes_buenas"],
                                    ident_total=d["ident_total"], alineado=d["alineado"])
                    if v != "SIN_SEÑAL":
                        seq = l["seq_cruda"]
                        if l["sentido"] == "R":
                            seq = str(Seq(seq).reverse_complement())
                        fasta_rev.append(SeqRecord(Seq(seq), id=f"{m['muestra']}_{l['sentido']}",
                                                   description=f"{v} cruda len={len(seq)} Qmedia={fila['q_media_cruda']}"))
                revision.append(fila)
                if fila["veredicto"] != "SIN_SEÑAL":
                    print(f"  {fila['archivo']:<40} {fila['veredicto']:<18} {fila['detalle']}")

        cols_rev = ["muestra", "archivo", "sentido", "largo_crudo", "q_media_cruda", "bases_q20", "veredicto",
                    "ref_especie", "ident_buenas", "bases_buenas", "desajustes_buenas", "ident_total",
                    "alineado", "detalle"]
        with open(salida / "05_revision_manual.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols_rev)
            w.writeheader()
            for fila in revision:
                w.writerow({k: fila.get(k, "") for k in cols_rev})
        SeqIO.write(fasta_rev, salida / "05_revision_manual.fasta", "fasta")
        n_comp = sum(1 for f in revision if f["veredicto"] == "COMPATIBLE")
        n_rev = sum(1 for f in revision if f["veredicto"] in ("DUDOSO", "DIVERGENTE", "SEÑAL_INSUFICIENTE"))
        print(f"  -> {n_comp} lecturas compatibles con una especie ya identificada, "
              f"{n_rev} para mirar a mano; secuencias crudas en 05_revision_manual.fasta")

    # --- Paso 5: informe final -------------------------------------------
    cols = ["muestra", "n_archivos", "n_pass", "origen", "largo", "solapamiento", "discrepancias", "conflictos",
            "especie_1", "identidad_1", "cobertura_1", "evalue_1", "accession_1",
            "especie_2", "identidad_2", "especie_3", "identidad_3",
            "interpretacion", "nota", "archivos"]
    with open(salida / "03_identificacion.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for m in muestras:
            fila = {k: m.get(k, "") for k in cols}
            hits = m.get("hits", [])
            for n, h in enumerate(hits, 1):
                fila[f"especie_{n}"] = h["especie"]
                fila[f"identidad_{n}"] = h["identidad"]
                if n == 1:
                    fila["cobertura_1"], fila["evalue_1"], fila["accession_1"] = h["cobertura"], h["evalue"], h["accession"]
            w.writerow(fila)

    with open(salida / "04_hits_completos.json", "w", encoding="utf-8") as fh:
        json.dump({m["muestra"]: m.get("hits", []) for m in muestras}, fh, indent=2, ensure_ascii=False)

    # resumen
    estados = defaultdict(int)
    for l in lecturas:
        estados[l["estado"]] += 1
    n_seq = sum(1 for m in muestras if m["secuencia"])
    resumen = [
        f"Cromatogramas leídos: {len(lecturas)}",
        *[f"  {e}: {n}" for e, n in sorted(estados.items())],
        f"Muestras: {len(muestras)}  ->  con secuencia utilizable: {n_seq}",
        f"  consenso F+R: {sum(1 for m in muestras if m['origen'] == 'CONSENSO_F+R')}",
        f"  una sola lectura: {sum(1 for m in muestras if m['origen'].startswith('SOLO'))}",
        f"  sin secuencia: {sum(1 for m in muestras if m['origen'] == 'NINGUNA')}",
    ]
    if not args.no_blast:
        interp = defaultdict(int)
        for m in muestras:
            interp[m.get("interpretacion", "")] += 1
        resumen.append("Interpretación BLAST:")
        resumen += [f"  {k}: {v}" for k, v in sorted(interp.items())]
    if not args.sin_diagnostico:
        vered = defaultdict(int)
        for f in revision:
            vered[f["veredicto"]] += 1
        resumen.append("Diagnóstico de lecturas sin secuencia (05_revision_manual.csv):")
        resumen += [f"  {k}: {v}" for k, v in sorted(vered.items())]
    def fmt(seg):
        seg = int(round(seg))
        return f"{seg // 60} min {seg % 60} s" if seg >= 60 else f"{seg} s"
    t_total = time.time() - t_inicio
    resumen.append(f"Tiempo total: {fmt(t_total)}  (BLAST: {fmt(t_blast)}; QC, consenso e informes: {fmt(t_total - t_blast)})")
    texto = "\n".join(resumen)
    (salida / "00_resumen.txt").write_text(texto, encoding="utf-8")
    print("\n" + texto)
    print(f"\nListo. Resultados en: {salida.resolve()}")


if __name__ == "__main__":
    main()
