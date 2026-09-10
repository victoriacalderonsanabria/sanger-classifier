#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clasificar_sanger.py
====================
Pipeline genérico para cromatogramas Sanger (.ab1) de cualquier marcador y
organismo. Cada muestra termina en uno de tres grupos:

  RECHAZADA   : sin señal utilizable. No se construye secuencia ni se hace BLAST.
  CONFIABLE   : la secuencia (consenso F+R o mejor lectura) cumple el criterio
                estándar de calidad. Se hace BLAST (megablast) y el resultado se
                puede reportar directamente.
  DUDOSA : hay señal pero no alcanza el estándar. Se construye la mejor
                secuencia posible con un recorte más laxo, se hace BLAST con el
                algoritmo más sensible (blastn) y el resultado sale marcado para
                revisión manual, con las métricas que explican por qué.

Pasos:
  1. Lee los .ab1, detecta muestra y sentido (F/R) por el nombre del archivo.
  2. Recorta cada lectura por calidad (Mott) con dos umbrales: estricto (Q20)
     y laxo (Q15), y calcula métricas.
  3. Por muestra: intenta consenso F+R sobre lecturas crudas; si no, usa la
     mejor lectura. Clasifica en CONFIABLE / DUDOSA / RECHAZADA.
  4. Compara las DUDOSAS contra las CONFIABLES de la misma corrida
     (identidad sobre bases de buena calidad) para detectar "misma especie
     leída con ruido".
  5. BLAST remoto (NCBI nt) de ambos grupos; parseo del mejor hit y de hasta
     dos alternativas de especie distinta.
  6. Informes CSV/FASTA/JSON y resumen.

Uso:
    python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --email tu@mail.com
    python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --no-blast      # solo QC y grupos
    python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --taxon "Vertebrata[Organism]" --email ...

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

ACGT = set("ACGT")

# ----------------------------------------------------------------------------
# Lectura, recorte y métricas
# ----------------------------------------------------------------------------

def leer_ab1(ruta):
    rec = SeqIO.read(ruta, "abi")
    return str(rec.seq), list(rec.letter_annotations.get("phred_quality", []))


def recorte_mott(qual, umbral_q):
    """Ventana contigua de puntaje máximo (Phred/Mott). Devuelve (ini, fin)."""
    if not qual:
        return 0, 0
    cutoff = 10 ** (-umbral_q / 10.0)
    puntaje = mejor = 0.0
    inicio = 0
    mejor_ini = mejor_fin = 0
    for i, q in enumerate(qual):
        puntaje += cutoff - 10 ** (-q / 10.0)
        if puntaje < 0:
            puntaje, inicio = 0.0, i + 1
        elif puntaje > mejor:
            mejor, mejor_ini, mejor_fin = puntaje, inicio, i + 1
    return mejor_ini, mejor_fin


def metricas(seq, qual):
    n = len(qual)
    if n == 0:
        return dict(largo=0, q_media=0.0, pct_q20=0.0, n_amb=0)
    return dict(largo=n, q_media=round(sum(qual) / n, 1),
                pct_q20=round(100.0 * sum(1 for q in qual if q >= 20) / n, 1),
                n_amb=sum(1 for c in seq.upper() if c not in ACGT))


def cumple_estandar(seq, qual, p):
    """Criterio estándar sobre una secuencia + calidades."""
    m = metricas(seq, qual)
    return (m["largo"] >= p.largo_min and m["q_media"] >= p.q_media_min
            and m["pct_q20"] >= p.pct_q20_min), m


# ----------------------------------------------------------------------------
# Escritura de CSV (formato Excel en español o estándar internacional)
# ----------------------------------------------------------------------------

# Separador usado DENTRO de un campo de texto (listas de archivos, motivos).
# Nunca debe coincidir con el separador de columnas del CSV.
SEP_INTERNO = " | "


def escribir_csv(ruta, columnas, filas, sep=";", decimal_coma=True):
    """
    Escribe un CSV listo para abrir con doble clic.
      sep=";"  + decimal_coma=True  -> Excel en español: abre en columnas y toma
                                       los números como números. Se agrega BOM
                                       UTF-8 para que los acentos salgan bien.
      sep=","  + decimal_coma=False -> estándar internacional (pandas, R).
    Los campos que contuvieran el separador se entrecomillan solos (csv), pero
    igual evitamos meter separadores dentro del texto (ver SEP_INTERNO).
    """
    codificacion = "utf-8-sig" if sep == ";" else "utf-8"
    with open(ruta, "w", newline="", encoding=codificacion) as fh:
        w = csv.DictWriter(fh, fieldnames=columnas, delimiter=sep, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            if decimal_coma:
                fila = {k: (str(v).replace(".", ",") if isinstance(v, float) else v)
                        for k, v in fila.items()}
            w.writerow({k: fila.get(k, "") for k in columnas})


# ----------------------------------------------------------------------------
# Nombre de muestra y sentido
# ----------------------------------------------------------------------------

TOKENS_F = ["F", "FWD", "FORWARD", "LCO1490", "LCO", "VF1", "VF1D", "VF1I", "COIF", "COI-F",
            "27F", "515F", "ITS1", "ITS1F", "ITS5", "M13F", "T7", "SP6", "NS1", "1F"]
TOKENS_R = ["R", "REV", "REVERSE", "HCO2198", "HCO", "VR1", "VR1D", "VR1I", "COIR", "COI-R",
            "1492R", "806R", "ITS4", "ITS2", "M13R", "T3", "NS8", "1R"]


def muestra_y_sentido(nombre, extra_f=(), extra_r=()):
    base = re.sub(r"\.ab1$", "", nombre, flags=re.I)
    tokens = re.split(r"[_\-\s\.]+", base)
    tf = {t.upper() for t in list(TOKENS_F) + list(extra_f)}
    tr = {t.upper() for t in list(TOKENS_R) + list(extra_r)}
    for i, t in enumerate(tokens):
        T = t.upper()
        if T in tf or T in tr:
            sentido = "F" if T in tf else "R"
            muestra = "_".join(tokens[:i]) if i > 0 else "_".join(tokens[i + 1:])
            return muestra or base, sentido
    return base, "?"


# ----------------------------------------------------------------------------
# Consenso F + R sobre lecturas crudas
# ----------------------------------------------------------------------------

def _aligner_local(match=2, mismatch=-3, gap_open=-5, gap_ext=-2):
    a = Align.PairwiseAligner()
    a.mode = "local"
    a.match_score, a.mismatch_score = match, mismatch
    a.open_gap_score, a.extend_gap_score = gap_open, gap_ext
    return a


def consenso_fr(seq_f, qual_f, seq_r, qual_r, min_solap=50, q_conflicto=20):
    """
    Alinea F contra el reverso-complemento de R y arma un consenso base a base
    eligiendo la de mayor calidad (una base A/C/G/T gana a un código de
    ambigüedad). Devuelve la secuencia consenso SIN recortar, con su vector de
    calidad, para que el que llama decida el recorte.
    """
    rc = str(Seq(seq_r).reverse_complement())
    qual_rc = qual_r[::-1]
    aln = _aligner_local().align(seq_f, rc)[0]
    bf, br = aln.aligned
    vacio = dict(seq="", qual=[], solap=0, discrepancias=0, conflictos=0, ok=False)
    if len(bf) == 0:
        return vacio
    f_ini, f_fin = bf[0][0], bf[-1][1]
    r_ini, r_fin = br[0][0], br[-1][1]
    solap = f_fin - f_ini
    if solap < min_solap:
        vacio["solap"] = solap
        return vacio

    def q_region(qual, a, b):
        if b > a:
            return sum(qual[a:b]) / (b - a)
        fl = qual[max(0, a - 1):a + 1]
        return sum(fl) / max(1, len(fl))

    cons, qcons = list(seq_f[:f_ini]), list(qual_f[:f_ini])
    discrep = conflictos = 0
    pos_f, pos_r = f_ini, r_ini
    for (fa, fb), (ra, rb) in zip(bf, br):
        gap_f, gap_r = seq_f[pos_f:fa], rc[pos_r:ra]
        if gap_f or gap_r:
            qf, qr = q_region(qual_f, pos_f, fa), q_region(qual_rc, pos_r, ra)
            if qf >= qr:
                cons += list(gap_f); qcons += list(qual_f[pos_f:fa])
            else:
                cons += list(gap_r); qcons += list(qual_rc[pos_r:ra])
            discrep += 1
            if min(qf, qr) >= q_conflicto:
                conflictos += 1
        for i, j in zip(range(fa, fb), range(ra, rb)):
            b1, b2, q1, q2 = seq_f[i], rc[j], qual_f[i], qual_rc[j]
            if b1 == b2:
                cons.append(b1); qcons.append(max(q1, q2))
            else:
                discrep += 1
                if min(q1, q2) >= q_conflicto and b1 in ACGT and b2 in ACGT:
                    conflictos += 1
                if b1 not in ACGT and b2 in ACGT:
                    cons.append(b2); qcons.append(q2)
                elif b2 not in ACGT and b1 in ACGT:
                    cons.append(b1); qcons.append(q1)
                elif q1 >= q2:
                    cons.append(b1); qcons.append(q1 - q2)
                else:
                    cons.append(b2); qcons.append(q2 - q1)
        pos_f, pos_r = fb, rb
    cons += list(rc[r_fin:]); qcons += list(qual_rc[r_fin:])
    return dict(seq="".join(cons), qual=qcons, solap=int(solap), discrepancias=discrep,
                conflictos=conflictos, ok=True)


# ----------------------------------------------------------------------------
# Comparación de una secuencia dudosa contra las confiables de la corrida
# ----------------------------------------------------------------------------

def comparar_con_confiables(seq, qual, referencias, q_buena=20):
    """Mejor referencia por bases buenas coincidentes; separa desajustes por calidad."""
    al = _aligner_local(1, -1, -2, -1)
    mejor = None
    for orient, s, q in (("+", seq, qual), ("rc", str(Seq(seq).reverse_complement()), qual[::-1])):
        for ref in referencias:
            aln = al.align(s, ref["seq"])[0]
            hi = lo = mhi = mlo = 0
            for (fa, fb), (ra, rb) in zip(*aln.aligned):
                for i, j in zip(range(fa, fb), range(ra, rb)):
                    mm = s[i] != ref["seq"][j]
                    if q[i] >= q_buena:
                        hi += 1; mhi += mm
                    else:
                        lo += 1; mlo += mm
            if hi + lo == 0:
                continue
            res = dict(ref=ref["muestra"], bases_buenas=hi, desaj_buenas=mhi,
                       ident_buenas=round(100 * (hi - mhi) / hi, 1) if hi else 0.0,
                       bases_malas=lo, desaj_malas=mlo, orient=orient)
            if mejor is None or (hi - mhi) > (mejor["bases_buenas"] - mejor["desaj_buenas"]):
                mejor = res
    return mejor


def veredicto_comparacion(d, min_bases=40):
    if d is None or d["bases_buenas"] < min_bases:
        return "sin_coincidencia_util"
    if d["ident_buenas"] >= 98.0:
        return f"coincide con {d['ref']} ({d['ident_buenas']}% en {d['bases_buenas']} bases buenas)"
    if d["ident_buenas"] >= 95.0:
        return f"parecida a {d['ref']} ({d['ident_buenas']}% en bases buenas)"
    return f"distinta de las confiables (mejor: {d['ref']}, {d['ident_buenas']}%)"


# ----------------------------------------------------------------------------
# BLAST
# ----------------------------------------------------------------------------

def blast_remoto_lote(items, carpeta_cache, db="nt", megablast=True, n_hits=10,
                      entrez_query=None, tamano_lote=50):
    """
    BLAST remoto en LOTE: manda hasta `tamano_lote` secuencias en un solo
    envío (un FASTA multi-secuencia), así se espera la cola de NCBI una vez
    por lote y no una vez por secuencia. Los resultados se guardan por muestra
    en carpeta_cache/<muestra>.hits.json, de modo que si el script se corta,
    al relanzarlo solo se envían las que faltan.
    items: lista de (nombre, seq, largo). Devuelve dict nombre -> hits.
    """
    resultados = {}
    pendientes = []
    for nombre, seq, largo in items:
        cache = carpeta_cache / f"{nombre}.hits.json"
        if cache.exists():
            resultados[nombre] = json.loads(cache.read_text(encoding="utf-8"))
        else:
            pendientes.append((nombre, seq, largo))
    if not pendientes:
        return resultados

    largos = {n: l for n, _, l in pendientes}
    for i in range(0, len(pendientes), tamano_lote):
        lote = pendientes[i:i + tamano_lote]
        fasta = "".join(f">{n}\n{seq}\n" for n, seq, _ in lote)
        print(f"   enviando lote de {len(lote)} secuencias a NCBI ({db}, "
              f"{'megablast' if megablast else 'blastn'}) ...", end="", flush=True)
        t0 = time.time()
        kwargs = dict(program="blastn", database=db, sequence=fasta,
                      megablast=megablast, hitlist_size=n_hits)
        if entrez_query:
            kwargs["entrez_query"] = entrez_query
        registros = None
        for intento in range(3):
            try:
                h = NCBIWWW.qblast(**kwargs)
                xml_txt = h.read()
                h.close()
                (carpeta_cache / f"lote_{i // tamano_lote + 1}.xml").write_text(xml_txt)
                from io import StringIO
                registros = list(NCBIXML.parse(StringIO(xml_txt)))
                break
            except Exception as e:
                print(f"\n   [BLAST] intento {intento + 1} falló: {e}")
                time.sleep(30)
        print(f" {time.time() - t0:.0f} s")
        if registros is None:
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
                json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
        for n, _, _ in lote:
            if n not in vistos:
                resultados[n] = []
    return resultados


def blast_local(nombre, seq, carpeta_xml, db, megablast=True, n_hits=10):
    import subprocess
    xml = carpeta_xml / f"{nombre}.xml"
    if not xml.exists():
        fa = carpeta_xml / f"{nombre}.query.fa"
        fa.write_text(f">{nombre}\n{seq}\n")
        cmd = ["blastn", "-task", "megablast" if megablast else "blastn", "-query", str(fa),
               "-db", db, "-outfmt", "5", "-max_target_seqs", str(n_hits), "-out", str(xml)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            sys.exit("No encuentro 'blastn'. Instalá BLAST+ (sudo apt install ncbi-blast+).")
        except subprocess.CalledProcessError as e:
            print(f"   [BLAST local] falló para {nombre}: {e.stderr.strip()}")
            return None
    with open(xml) as fh:
        return NCBIXML.read(fh)


def resumir_hits(rec, largo_query, max_especies=3):
    hits, vistos = [], set()
    if rec is None:
        return hits
    for al in rec.alignments:
        hsp = al.hsps[0]
        titulo = al.hit_def or al.title
        m = re.match(r"([A-Z][a-z]+ [a-z]+)", titulo)
        especie = m.group(1) if m else titulo[:40]
        if especie in vistos:
            continue
        vistos.add(especie)
        hits.append(dict(especie=especie, accession=al.accession,
                         identidad=round(100.0 * hsp.identities / hsp.align_length, 2),
                         cobertura=round(100.0 * hsp.align_length / largo_query, 1),
                         evalue=hsp.expect, titulo=titulo))
        if len(hits) == max_especies:
            break
    return hits


def interpretar(hits, ident_min, cob_min):
    if not hits:
        return "sin_hit"
    top = hits[0]
    if top["cobertura"] < cob_min:
        return f"cobertura_baja ({top['cobertura']}%): hit parcial, revisar"
    if top["identidad"] < ident_min:
        return f"identidad_baja ({top['identidad']}% < {ident_min}%): especie no representada o secuencia con errores"
    if len(hits) > 1 and hits[0]["identidad"] - hits[1]["identidad"] < 1.0:
        g1, g2 = top["especie"].split()[0], hits[1]["especie"].split()[0]
        if g1 == g2:
            # dos especies del mismo género que el marcador no separa (p. ej.
            # Bos taurus / Bos indicus con COI): la identificación es firme a
            # nivel de género, no es una ambigüedad real
            return f"identificado a nivel de género ({top['especie']} / {hits[1]['especie']})"
        return "ambiguo: dos especies con identidad similar"
    if re.search(r"Homo sapiens", top["titulo"]):
        return "humano: verificar si es esperado o contaminación"
    return "identificado"


# ----------------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", required=True, help="carpeta con los .ab1")
    ap.add_argument("-o", "--output", default="resultados")
    ap.add_argument("--email", help="e-mail para el BLAST remoto de NCBI")
    # criterio estándar (grupo CONFIABLE)
    ap.add_argument("--largo-min", type=int, default=100, help="largo mínimo de la secuencia final (default 100)")
    ap.add_argument("--q-media-min", type=float, default=25.0, help="Q media mínima (default 25)")
    ap.add_argument("--pct-q20-min", type=float, default=80.0, help="%% mínimo de bases Q>=20 (default 80)")
    ap.add_argument("--umbral-q", type=int, default=20, help="Q del recorte de Mott estricto (default 20)")
    # criterio laxo (grupo DUDOSA)
    ap.add_argument("--umbral-q-laxo", type=int, default=15, help="Q del recorte laxo (default 15)")
    ap.add_argument("--largo-min-laxo", type=int, default=60, help="largo mínimo para entrar en DUDOSA (default 60)")
    ap.add_argument("--min-bases-q20", type=int, default=30,
                    help="bases con Q>=20 que necesita una lectura para no ser RECHAZADA (default 30)")
    ap.add_argument("--min-solap", type=int, default=50, help="solapamiento mínimo F/R para consenso (default 50)")
    # BLAST
    ap.add_argument("--db", default="nt",
                    help="base de NCBI: nt (todo, lenta), core_nt (sin redundancia), mito (genomas mitocondriales "
                         "RefSeq: rápida para COI/cytb/16S mito), 16S_ribosomal_RNA (bacterias/arqueas), "
                         "ITS_RefSeq_Fungi, ITS_eukaryote_sequences, 18S_fungal_sequences, 28S_fungal_sequences")
    ap.add_argument("--lote", type=int, default=50, help="secuencias por envío a NCBI (default 50)")
    ap.add_argument("--taxon", help='restringir BLAST, p. ej. "Vertebrata[Organism]" o "Fungi[Organism]"')
    ap.add_argument("--blast-local", metavar="RUTA_DB", help="usar blastn local contra esta base")
    ap.add_argument("--no-blast", action="store_true")
    ap.add_argument("--ident-min", type=float, default=97.0, help="identidad mínima para 'identificado' (default 97)")
    ap.add_argument("--cob-min", type=float, default=80.0, help="cobertura mínima del hit (default 80)")
    ap.add_argument("--separador", choices=["punto_y_coma", "coma"], default="punto_y_coma",
                    help="punto_y_coma (default): CSV para Excel en español, abre en columnas por "
                         "doble clic y con decimales con coma. coma: estándar internacional (pandas, R).")
    ap.add_argument("--primers-f", nargs="*", default=[])
    ap.add_argument("--primers-r", nargs="*", default=[])
    args = ap.parse_args()

    t_inicio = time.time()
    t_blast = 0.0
    sep_csv = ";" if args.separador == "punto_y_coma" else ","
    dec_coma = args.separador == "punto_y_coma"
    entrada, salida = Path(args.input), Path(args.output)
    salida.mkdir(parents=True, exist_ok=True)
    xml_dir = salida / "blast_xml"
    xml_dir.mkdir(exist_ok=True)
    if args.email:
        NCBIWWW.email = args.email

    archivos = sorted(p for p in entrada.rglob("*") if p.suffix.lower() == ".ab1")
    if not archivos:
        sys.exit(f"No encontré .ab1 en {entrada}")
    print(f"Encontré {len(archivos)} cromatogramas en {entrada}\n")

    # ---- 1. QC por lectura ------------------------------------------------
    lecturas = []
    for ruta in archivos:
        l = dict(archivo=ruta.name)
        l["muestra"], l["sentido"] = muestra_y_sentido(ruta.name, args.primers_f, args.primers_r)
        try:
            seq, qual = leer_ab1(ruta)
        except Exception as e:
            seq, qual = "", []
            l["error"] = str(e)
        l["seq"], l["qual"] = seq, qual
        mc = metricas(seq, qual)
        l.update(largo_crudo=mc["largo"], q_media_cruda=mc["q_media"], amb_cruda=mc["n_amb"],
                 bases_q20=sum(1 for q in qual if q >= 20))
        ie, fe = recorte_mott(qual, args.umbral_q)
        il, fl = recorte_mott(qual, args.umbral_q_laxo)
        l.update(estricto=(ie, fe), laxo=(il, fl),
                 largo_estricto=fe - ie, largo_laxo=fl - il,
                 q_media_estricto=metricas(seq[ie:fe], qual[ie:fe])["q_media"])
        if mc["largo"] < 150 or l["bases_q20"] < args.min_bases_q20:
            l["senal"] = "SIN_SEÑAL"
        elif l["largo_estricto"] >= args.largo_min:
            l["senal"] = "BUENA"
        else:
            l["senal"] = "PARCIAL"
        lecturas.append(l)
        print(f"  {l['archivo']:<38} {l['muestra']:<12} {l['sentido']}  crudo={l['largo_crudo']:>4} "
              f"Q={l['q_media_cruda']:<5} Q20={l['bases_q20']:>3}  recorte Q{args.umbral_q}={l['largo_estricto']:>3} "
              f"Q{args.umbral_q_laxo}={l['largo_laxo']:>3}  {l['senal']}")

    cols_qc = ["archivo", "muestra", "sentido", "largo_crudo", "q_media_cruda", "amb_cruda", "bases_q20",
               "largo_estricto", "q_media_estricto", "largo_laxo", "senal"]
    escribir_csv(salida / "01_QC_lecturas.csv", cols_qc, lecturas, sep_csv, dec_coma)

    # ---- 2. Por muestra: construir secuencia y clasificar -------------------
    por_muestra = defaultdict(list)
    for l in lecturas:
        por_muestra[l["muestra"]].append(l)

    muestras = []
    print("\nClasificación por muestra:")
    for nombre, ls in sorted(por_muestra.items()):
        m = dict(muestra=nombre, archivos=SEP_INTERNO.join(l["archivo"] for l in ls), n_lecturas=len(ls),
                 grupo="RECHAZADA", origen="", secuencia="", largo=0, q_media="", pct_q20="",
                 solapamiento="", discrepancias="", conflictos="", motivo="")
        con_senal = [l for l in ls if l["senal"] != "SIN_SEÑAL"]
        if not con_senal:
            m["motivo"] = "ninguna lectura con señal utilizable"
            muestras.append(m)
            print(f"  {nombre:<12} RECHAZADA    {m['motivo']}")
            continue

        # candidatos: (seq, qual, origen, extra, hay_que_invertir). El recorte se
        # hace SIEMPRE en la orientación original de la lectura (Mott no es
        # simétrico) y recién después se reverso-complementa la R.
        candidatos = []
        f = next((l for l in con_senal if l["sentido"] == "F"), None)
        r = next((l for l in con_senal if l["sentido"] == "R"), None)
        if f and r:
            c = consenso_fr(f["seq"], f["qual"], r["seq"], r["qual"], args.min_solap)
            if c["ok"]:
                candidatos.append((c["seq"], c["qual"], "CONSENSO_F+R",
                                   dict(solapamiento=c["solap"], discrepancias=c["discrepancias"],
                                        conflictos=c["conflictos"]), False))
        for l in con_senal:
            candidatos.append((l["seq"], l["qual"], f"SOLO_{l['sentido']}", {}, l["sentido"] == "R"))

        def recortar(seq, qual, umbral, invertir):
            a, b = recorte_mott(qual, umbral)
            s, q = seq[a:b], qual[a:b]
            if invertir:
                s, q = str(Seq(s).reverse_complement()), q[::-1]
            return s, q

        # 1) candidatos que cumplen el estándar con recorte estricto
        aprobados = []
        for seq, qual, origen, extra, inv in candidatos:
            s, q = recortar(seq, qual, args.umbral_q, inv)
            ok, met = cumple_estandar(s, q, args)
            if ok:
                aprobados.append((s, origen, extra, met, "CONFIABLE"))
        elegido = None
        if aprobados:
            mejor_sola = max((c for c in aprobados if c[1] != "CONSENSO_F+R"), key=lambda c: c[3]["largo"], default=None)
            cons = next((c for c in aprobados if c[1] == "CONSENSO_F+R"), None)
            # el consenso tiene prioridad si no es claramente más corto que la mejor lectura sola
            if cons and (mejor_sola is None or cons[3]["largo"] >= 0.9 * mejor_sola[3]["largo"]):
                elegido = cons
            else:
                elegido = mejor_sola
        # 2) si no: el mejor candidato con recorte laxo, si supera el largo laxo
        largo_estricto_max = 0
        if elegido is None:
            for seq, qual, origen, extra, inv in candidatos:
                s_e, _ = recortar(seq, qual, args.umbral_q, inv)
                largo_estricto_max = max(largo_estricto_max, len(s_e))
                s, q = recortar(seq, qual, args.umbral_q_laxo, inv)
                met = metricas(s, q)
                if met["largo"] >= args.largo_min_laxo and (elegido is None or met["largo"] > elegido[3]["largo"]):
                    elegido = (s, origen, extra, met, "DUDOSA")

        if elegido is None:
            m["motivo"] = (f"hay señal pero ni con recorte Q{args.umbral_q_laxo} se llega a "
                           f"{args.largo_min_laxo} pb")
            muestras.append(m)
            print(f"  {nombre:<12} RECHAZADA    {m['motivo']}")
            continue

        seq, origen, extra, met, grupo = elegido
        m.update(grupo=grupo, origen=origen, secuencia=seq, largo=met["largo"],
                 q_media=met["q_media"], pct_q20=met["pct_q20"], **extra)
        motivos = []
        if grupo == "DUDOSA":
            motivos.append(f"con recorte Q{args.umbral_q} quedaban {largo_estricto_max} pb - se usó recorte Q{args.umbral_q_laxo}")
            if met["largo"] < args.largo_min:
                motivos.append(f"largo {met['largo']} < {args.largo_min}")
            if met["q_media"] < args.q_media_min:
                motivos.append(f"Q media {met['q_media']} < {args.q_media_min}")
            if met["pct_q20"] < args.pct_q20_min:
                motivos.append(f"{met['pct_q20']}% bases Q20 < {args.pct_q20_min}%")
            if met["n_amb"]:
                motivos.append(f"{met['n_amb']} bases ambiguas")
        if extra.get("conflictos", 0) >= 3:
            motivos.append(f"{extra['conflictos']} conflictos F/R con buena calidad: posible mezcla")
        m["motivo"] = SEP_INTERNO.join(motivos)
        muestras.append(m)
        print(f"  {nombre:<12} {grupo:<12} {origen:<13} {met['largo']:>4} pb  Q={met['q_media']:<5} {m['motivo']}")

    confiables = [m for m in muestras if m["grupo"] == "CONFIABLE"]
    dudosas = [m for m in muestras if m["grupo"] == "DUDOSA"]
    rechazadas = [m for m in muestras if m["grupo"] == "RECHAZADA"]

    SeqIO.write([SeqRecord(Seq(m["secuencia"]), id=m["muestra"], description=f"{m['origen']} len={m['largo']}")
                 for m in confiables], salida / "02_confiables.fasta", "fasta")
    SeqIO.write([SeqRecord(Seq(m["secuencia"]), id=m["muestra"],
                           description=f"{m['origen']} len={m['largo']} REVISAR: {m['motivo']}")
                 for m in dudosas], salida / "03_dudosas.fasta", "fasta")

    # ---- 3. Cuestionadas vs confiables de la misma corrida ------------------
    refs = [dict(muestra=m["muestra"], seq=m["secuencia"]) for m in confiables]
    for m in dudosas:
        # se usa la lectura cruda más informativa (más bases Q20), no la recortada
        l = max(por_muestra[m["muestra"]], key=lambda x: x["bases_q20"])
        d = comparar_con_confiables(l["seq"], l["qual"], refs) if refs else None
        m["vs_confiables"] = veredicto_comparacion(d)

    # ---- 4. BLAST -----------------------------------------------------------
    if not args.no_blast:
        t0_blast = time.time()
        for grupo, lista, mega in (("CONFIABLE", confiables, True), ("DUDOSA", dudosas, False)):
            if not lista:
                continue
            modo = "megablast" if mega else "blastn (sensible)"
            if args.blast_local:
                print(f"\nBLAST local {modo} de {len(lista)} muestras {grupo}S contra {args.blast_local}")
                for k, m in enumerate(lista, 1):
                    rec = blast_local(m["muestra"], m["secuencia"], xml_dir, args.blast_local, mega)
                    m["hits"] = resumir_hits(rec, m["largo"])
            else:
                print(f"\nBLAST remoto {modo} de {len(lista)} muestras {grupo}S contra {args.db}"
                      + (f" [{args.taxon}]" if args.taxon else "") + f", lotes de {args.lote}")
                res = blast_remoto_lote([(m["muestra"], m["secuencia"], m["largo"]) for m in lista],
                                        xml_dir, args.db, mega, entrez_query=args.taxon, tamano_lote=args.lote)
                for m in lista:
                    m["hits"] = res.get(m["muestra"], [])
            for m in lista:
                m["interpretacion"] = interpretar(m["hits"], args.ident_min, args.cob_min)
                h = m["hits"][0] if m["hits"] else None
                print(f"  {m['muestra']:<12} {h['especie'] if h else 'sin hit':<28} "
                      f"{h['identidad'] if h else '-':>6}%  -> {m['interpretacion']}")
        t_blast = time.time() - t0_blast
    for m in muestras:
        m.setdefault("hits", [])
        m.setdefault("interpretacion", "sin_blast" if m["grupo"] != "RECHAZADA" and not args.no_blast else "")

    # ---- 5. Informes --------------------------------------------------------
    # Orden: identificación primero, textos explicativos al final, archivos último.
    cols = ["muestra", "grupo", "origen", "largo", "q_media", "pct_q20", "solapamiento", "discrepancias",
            "conflictos",
            "especie_1", "identidad_1", "cobertura_1", "evalue_1", "accession_1",
            "especie_2", "identidad_2", "especie_3", "identidad_3", "interpretacion",
            "motivo", "vs_confiables", "archivos"]
    orden = {"CONFIABLE": 0, "DUDOSA": 1, "RECHAZADA": 2}
    filas = []
    for m in sorted(muestras, key=lambda x: (orden[x["grupo"]], x["muestra"])):
        fila = {k: m.get(k, "") for k in cols}
        for n, h in enumerate(m["hits"], 1):
            fila[f"especie_{n}"], fila[f"identidad_{n}"] = h["especie"], h["identidad"]
            if n == 1:
                fila["cobertura_1"], fila["evalue_1"], fila["accession_1"] = h["cobertura"], h["evalue"], h["accession"]
        filas.append(fila)
    escribir_csv(salida / "04_resultados.csv", cols, filas, sep_csv, dec_coma)
    with open(salida / "05_hits_completos.json", "w", encoding="utf-8") as fh:
        json.dump({m["muestra"]: m["hits"] for m in muestras if m["hits"]}, fh, indent=2, ensure_ascii=False)

    resumen = [f"Cromatogramas: {len(lecturas)}  (BUENA: {sum(l['senal']=='BUENA' for l in lecturas)}, "
               f"PARCIAL: {sum(l['senal']=='PARCIAL' for l in lecturas)}, "
               f"SIN_SEÑAL: {sum(l['senal']=='SIN_SEÑAL' for l in lecturas)})",
               f"Muestras: {len(muestras)}",
               f"  CONFIABLE:   {len(confiables)}  (consenso F+R: {sum(m['origen']=='CONSENSO_F+R' for m in confiables)})",
               f"  DUDOSA:      {len(dudosas)}",
               f"  RECHAZADA:   {len(rechazadas)}"]
    if not args.no_blast:
        for grupo, lista in (("CONFIABLE", confiables), ("DUDOSA", dudosas)):
            cnt = defaultdict(int)
            for m in lista:
                cnt[m["interpretacion"].split(":")[0].split(" (")[0]] += 1
            resumen.append(f"BLAST {grupo}: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
    def fmt(seg):
        seg = int(round(seg))
        return f"{seg // 60} min {seg % 60} s" if seg >= 60 else f"{seg} s"
    t_total = time.time() - t_inicio
    resumen.append(f"Tiempo total: {fmt(t_total)}  (BLAST: {fmt(t_blast)}; QC, consenso e informes: {fmt(t_total - t_blast)})")
    texto = "\n".join(resumen)
    (salida / "00_resumen.txt").write_text(texto, encoding="utf-8")
    print("\n" + texto + f"\n\nListo. Resultados en {salida.resolve()}")


if __name__ == "__main__":
    main()
