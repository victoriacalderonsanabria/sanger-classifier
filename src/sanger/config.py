"""
Parámetros de una corrida.

Por qué un objeto aparte: hasta ahora los umbrales viajaban dentro del objeto
que arma argparse, así que cualquier otra forma de lanzar el análisis (la
ventana, un test) tenía que fingir que venía de la línea de comandos.
`Parametros` es el mismo conjunto de valores, venga de donde venga.

Es inmutable (frozen) a propósito: una vez que arranca la corrida nadie puede
cambiar un umbral a mitad de camino y dejar muestras clasificadas con
criterios distintos dentro del mismo informe.
"""

from dataclasses import dataclass
from pathlib import Path

SEPARADORES = ("punto_y_coma", "coma")

_ENTEROS = (
    "largo_min",
    "umbral_q",
    "umbral_q_laxo",
    "largo_min_laxo",
    "min_bases_q20",
    "min_solap",
    "lote",
)
_DECIMALES = ("q_media_min", "pct_q20_min", "ident_min", "cob_min")


@dataclass(frozen=True)
class Parametros:
    """Todo lo que define una corrida. Los valores por defecto son los validados."""

    entrada: Path
    salida: Path = Path("resultados")
    email: str | None = None

    # Criterio estándar (grupo CONFIABLE). El amplicón del ensayo mide ~260 pb:
    # por eso 100 y no 300. Para COI Folmer o 16S completo conviene subirlo.
    largo_min: int = 100
    q_media_min: float = 25.0
    pct_q20_min: float = 80.0
    umbral_q: int = 20

    # Criterio laxo (grupo DUDOSA)
    umbral_q_laxo: int = 15
    largo_min_laxo: int = 60
    min_bases_q20: int = 30
    min_solap: int = 50

    # BLAST
    db: str = "nt"
    lote: int = 50
    taxon: str | None = None
    blast_local: str | None = None
    no_blast: bool = False
    ident_min: float = 97.0
    cob_min: float = 80.0

    # Salida
    separador: str = "punto_y_coma"
    primers_f: tuple[str, ...] = ()
    primers_r: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Los tipos se fijan acá porque los umbrales aparecen escritos en los
        # informes: "Q media 22.1 < 25.0" no es lo mismo que "... < 25". Así el
        # texto sale idéntico venga el valor de la consola o de la ventana.
        # (object.__setattr__ es la forma de asignar dentro de un frozen.)
        object.__setattr__(self, "entrada", Path(self.entrada))
        object.__setattr__(self, "salida", Path(self.salida))
        for nombre in _ENTEROS:
            object.__setattr__(self, nombre, int(getattr(self, nombre)))
        for nombre in _DECIMALES:
            object.__setattr__(self, nombre, float(getattr(self, nombre)))
        object.__setattr__(self, "primers_f", tuple(self.primers_f))
        object.__setattr__(self, "primers_r", tuple(self.primers_r))
        if self.separador not in SEPARADORES:
            raise ValueError(f"separador tiene que ser uno de {SEPARADORES}, no {self.separador!r}")

    @property
    def sep_csv(self) -> str:
        """Separador de columnas: ';' para Excel en español, ',' para pandas/R."""
        return ";" if self.separador == "punto_y_coma" else ","

    @property
    def decimal_coma(self) -> bool:
        """Excel en español espera '99,38'; pandas y R esperan '99.38'."""
        return self.separador == "punto_y_coma"
