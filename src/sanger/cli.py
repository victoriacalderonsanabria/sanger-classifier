"""
Línea de comandos: argparse → Parametros → pipeline.

Es un cliente fino: no tiene lógica de análisis propia. Reproduce argumento por
argumento la interfaz del script original, incluido el texto de --help.
"""

import argparse
import sys

from sanger.config import Parametros
from sanger.modelos import Progreso

# Texto de --help: es el docstring del clasificar_sanger.py original, sin cambios.
DESCRIPCION = """
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


def construir_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=DESCRIPCION, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-i", "--input", required=True, help="carpeta con los .ab1")
    ap.add_argument("-o", "--output", default="resultados")
    ap.add_argument("--email", help="e-mail para el BLAST remoto de NCBI")
    # criterio estándar (grupo CONFIABLE)
    ap.add_argument(
        "--largo-min",
        type=int,
        default=100,
        help="largo mínimo de la secuencia final (default 100)",
    )
    ap.add_argument("--q-media-min", type=float, default=25.0, help="Q media mínima (default 25)")
    ap.add_argument(
        "--pct-q20-min", type=float, default=80.0, help="%% mínimo de bases Q>=20 (default 80)"
    )
    ap.add_argument(
        "--umbral-q", type=int, default=20, help="Q del recorte de Mott estricto (default 20)"
    )
    # criterio laxo (grupo DUDOSA)
    ap.add_argument("--umbral-q-laxo", type=int, default=15, help="Q del recorte laxo (default 15)")
    ap.add_argument(
        "--largo-min-laxo",
        type=int,
        default=60,
        help="largo mínimo para entrar en DUDOSA (default 60)",
    )
    ap.add_argument(
        "--min-bases-q20",
        type=int,
        default=30,
        help="bases con Q>=20 que necesita una lectura para no ser RECHAZADA (default 30)",
    )
    ap.add_argument(
        "--min-solap",
        type=int,
        default=50,
        help="solapamiento mínimo F/R para consenso (default 50)",
    )
    # BLAST
    ap.add_argument(
        "--db",
        default="nt",
        help="base de NCBI: nt (todo, lenta), core_nt (sin redundancia), mito (genomas mitocondriales "
        "RefSeq: rápida para COI/cytb/16S mito), 16S_ribosomal_RNA (bacterias/arqueas), "
        "ITS_RefSeq_Fungi, ITS_eukaryote_sequences, 18S_fungal_sequences, 28S_fungal_sequences",
    )
    ap.add_argument("--lote", type=int, default=50, help="secuencias por envío a NCBI (default 50)")
    ap.add_argument(
        "--taxon", help='restringir BLAST, p. ej. "Vertebrata[Organism]" o "Fungi[Organism]"'
    )
    ap.add_argument("--blast-local", metavar="RUTA_DB", help="usar blastn local contra esta base")
    ap.add_argument("--no-blast", action="store_true")
    ap.add_argument(
        "--ident-min",
        type=float,
        default=97.0,
        help="identidad mínima para 'identificado' (default 97)",
    )
    ap.add_argument(
        "--cob-min", type=float, default=80.0, help="cobertura mínima del hit (default 80)"
    )
    ap.add_argument(
        "--separador",
        choices=["punto_y_coma", "coma"],
        default="punto_y_coma",
        help="punto_y_coma (default): CSV para Excel en español, abre en columnas por "
        "doble clic y con decimales con coma. coma: estándar internacional (pandas, R).",
    )
    ap.add_argument("--primers-f", nargs="*", default=[])
    ap.add_argument("--primers-r", nargs="*", default=[])
    return ap


def parametros_desde_args(args: argparse.Namespace) -> Parametros:
    """Traduce la línea de comandos a Parametros, argumento por argumento."""
    return Parametros(
        entrada=args.input,
        salida=args.output,
        email=args.email,
        largo_min=args.largo_min,
        q_media_min=args.q_media_min,
        pct_q20_min=args.pct_q20_min,
        umbral_q=args.umbral_q,
        umbral_q_laxo=args.umbral_q_laxo,
        largo_min_laxo=args.largo_min_laxo,
        min_bases_q20=args.min_bases_q20,
        min_solap=args.min_solap,
        db=args.db,
        lote=args.lote,
        taxon=args.taxon,
        blast_local=args.blast_local,
        no_blast=args.no_blast,
        ident_min=args.ident_min,
        cob_min=args.cob_min,
        separador=args.separador,
        primers_f=args.primers_f,
        primers_r=args.primers_r,
    )


def imprimir(progreso: Progreso) -> None:
    """
    Muestra en pantalla lo que informa el núcleo.

    El núcleo ya no imprime: avisa. Esta función es la que hace que la consola
    salga exactamente igual que en el script original. Los avisos sin texto son
    solo avance (sirven para una barra de progreso) y no se muestran.
    """
    if progreso.mensaje:
        print(progreso.mensaje, end=progreso.fin, flush=True)


def main(argv: list[str] | None = None) -> None:
    try:
        import Bio  # noqa: F401
    except ImportError:
        sys.exit("Falta Biopython. Instalá con:  pip install biopython")
    from sanger.errores import SangerError
    from sanger.pipeline import ejecutar

    args = construir_parser().parse_args(argv)
    try:
        ejecutar(parametros_desde_args(args), progreso=imprimir)
    except SangerError as e:
        # errores previstos: un mensaje claro y código de salida 1, sin traceback
        sys.exit(str(e))


if __name__ == "__main__":
    main()
