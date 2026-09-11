"""Nombre de la muestra y sentido de lectura (F/R) a partir del nombre del archivo."""

import re
from collections.abc import Iterable

TOKENS_F = [
    "F", "FWD", "FORWARD", "LCO1490", "LCO", "VF1", "VF1D", "VF1I", "COIF", "COI-F",
    "27F", "515F", "ITS1", "ITS1F", "ITS5", "M13F", "T7", "SP6", "NS1", "1F",
]  # fmt: skip
TOKENS_R = [
    "R", "REV", "REVERSE", "HCO2198", "HCO", "VR1", "VR1D", "VR1I", "COIR", "COI-R",
    "1492R", "806R", "ITS4", "ITS2", "M13R", "T3", "NS8", "1R",
]  # fmt: skip


def muestra_y_sentido(
    nombre: str, extra_f: Iterable[str] = (), extra_r: Iterable[str] = ()
) -> tuple[str, str]:
    """
    Separa el nombre del archivo en muestra y sentido.

    El nombre se corta por '_', '-', espacio o punto, y el primer pedazo que sea
    un token conocido (F, R, un primer…) define el sentido. La muestra es lo que
    está antes de ese token (o lo que está después, si el token va primero).
    Si no hay ningún token reconocible, la muestra es el nombre entero y el
    sentido '?': se procesa igual, pero sin consenso.
    """
    base = re.sub(r"\.ab1$", "", nombre, flags=re.I)
    tokens = re.split(r"[_\-\s\.]+", base)
    tf = {t.upper() for t in list(TOKENS_F) + list(extra_f)}
    tr = {t.upper() for t in list(TOKENS_R) + list(extra_r)}
    for i, t in enumerate(tokens):
        mayus = t.upper()
        if mayus in tf or mayus in tr:
            sentido = "F" if mayus in tf else "R"
            muestra = "_".join(tokens[:i]) if i > 0 else "_".join(tokens[i + 1 :])
            return muestra or base, sentido
    return base, "?"
