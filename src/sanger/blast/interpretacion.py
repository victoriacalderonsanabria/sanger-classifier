"""De la respuesta de BLAST a una conclusión: qué especie es y con cuánta seguridad."""

import re

from sanger.modelos import Hit


def resumir_hits(rec, largo_query: int, max_especies: int = 3) -> list[Hit]:
    """
    Los mejores hits de especies DISTINTAS (hasta tres).

    Se descartan los hits repetidos de una misma especie porque lo que importa
    es si hay otra especie cerca: eso es lo que define si la identificación es
    firme o ambigua. La especie son las dos primeras palabras del título
    ("Género especie"); si el título no empieza así, sus primeros 40 caracteres.
    """
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
        hits.append(
            Hit(
                especie=especie,
                accession=al.accession,
                identidad=round(100.0 * hsp.identities / hsp.align_length, 2),
                cobertura=round(100.0 * hsp.align_length / largo_query, 1),
                evalue=hsp.expect,
                titulo=titulo,
            )
        )
        if len(hits) == max_especies:
            break
    return hits


def interpretar(hits: list[Hit], ident_min: float, cob_min: float) -> str:
    """El texto de la columna `interpretacion` (ver README_clasificar_sanger.md)."""
    if not hits:
        return "sin_hit"
    top = hits[0]
    if top.cobertura < cob_min:
        return f"cobertura_baja ({top.cobertura}%): hit parcial, revisar"
    if top.identidad < ident_min:
        return (
            f"identidad_baja ({top.identidad}% < {ident_min}%): "
            "especie no representada o secuencia con errores"
        )
    if len(hits) > 1 and hits[0].identidad - hits[1].identidad < 1.0:
        g1, g2 = top.especie.split()[0], hits[1].especie.split()[0]
        if g1 == g2:
            # Regla de género: dos especies del mismo género que el marcador no
            # separa (p. ej. Bos taurus / Bos indicus con COI). La identificación
            # es firme a nivel de género; no es una ambigüedad real.
            return f"identificado a nivel de género ({top.especie} / {hits[1].especie})"
        return "ambiguo: dos especies con identidad similar"
    if re.search(r"Homo sapiens", top.titulo):
        return "humano: verificar si es esperado o contaminación"
    return "identificado"
