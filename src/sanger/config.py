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

from dataclasses import dataclass, replace
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
    # None = no escribir informes (la ventana exporta a pedido; el CLI siempre
    # pasa una carpeta y escribe los cinco archivos, como siempre)
    salida: Path | None = Path("resultados")
    # dónde se guarda el caché de BLAST. Por defecto, salida/blast_xml, como
    # hasta ahora. El caché no es un resultado: es lo que permite retomar una
    # corrida cortada sin volver a pagar el BLAST, así que puede vivir aparte.
    carpeta_cache: Path | None = None
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
        if self.salida is not None:
            object.__setattr__(self, "salida", Path(self.salida))
        if self.carpeta_cache is not None:
            object.__setattr__(self, "carpeta_cache", Path(self.carpeta_cache))
        elif self.salida is None and not self.no_blast:
            raise ValueError(
                "sin carpeta de salida hay que indicar carpeta_cache: el caché de "
                "BLAST es lo que permite retomar una corrida cortada"
            )
        for nombre in _ENTEROS:
            object.__setattr__(self, nombre, int(getattr(self, nombre)))
        for nombre in _DECIMALES:
            object.__setattr__(self, nombre, float(getattr(self, nombre)))
        object.__setattr__(self, "primers_f", tuple(self.primers_f))
        object.__setattr__(self, "primers_r", tuple(self.primers_r))
        if self.separador not in SEPARADORES:
            raise ValueError(f"separador tiene que ser uno de {SEPARADORES}, no {self.separador!r}")

    def con(self, **cambios) -> "Parametros":
        """Una copia con algunos valores cambiados (no se modifica la original)."""
        return replace(self, **cambios)

    @property
    def cache(self) -> Path | None:
        """Dónde va el caché de BLAST: donde se pidió, o salida/blast_xml."""
        if self.carpeta_cache is not None:
            return self.carpeta_cache
        return self.salida / "blast_xml" if self.salida is not None else None

    @property
    def escribe_informes(self) -> bool:
        return self.salida is not None

    @property
    def sep_csv(self) -> str:
        """Separador de columnas: ';' para Excel en español, ',' para pandas/R."""
        return ";" if self.separador == "punto_y_coma" else ","

    @property
    def decimal_coma(self) -> bool:
        """Excel en español espera '99,38'; pandas y R esperan '99.38'."""
        return self.separador == "punto_y_coma"


@dataclass(frozen=True)
class Preset:
    """Un conjunto de valores pensado para un marcador concreto."""

    nombre: str
    descripcion: str
    cambios: dict


# Los valores salen de README_clasificar_sanger.md, que es la documentación
# revisada del pipeline; no son invenciones. PENDIENTE: que Victoria los
# confirme antes de darlos por buenos.
#
# Los valores POR DEFECTO (sin preset) son los del ensayo de ingestas: amplicón
# corto de ~260 pb, por eso largo mínimo 100 y no 300.
PRESETS = (
    Preset(
        "Default",
        "Los valores por defecto del pipeline, validados con el ensayo de ingestas.",
        {},
    ),
    Preset(
        "COI Folmer (~650 pb)",
        "Amplicón largo: se sube el largo mínimo a 300 pb.",
        {"largo_min": 300},
    ),
    Preset(
        "16S bacteriano",
        "Base curada de 16S e identidad 98,7 %, el corte habitual para bacterias.",
        {"largo_min": 300, "ident_min": 98.7, "db": "16S_ribosomal_RNA"},
    ),
    Preset(
        "ITS hongos",
        "Base de ITS de hongos de RefSeq.",
        {"db": "ITS_RefSeq_Fungi"},
    ),
)


def preset(nombre: str) -> Preset:
    for p in PRESETS:
        if p.nombre == nombre:
            return p
    raise KeyError(f"no existe el preset {nombre!r}")


def aplicar_preset(params: Parametros, nombre: str) -> Parametros:
    """Devuelve los parámetros con los valores del preset aplicados."""
    return params.con(**preset(nombre).cambios)


# Los campos que un preset puede tocar y que se ven en la ventana. Sirven para
# saber si lo que hay cargado sigue siendo el preset o el usuario lo modificó.
CAMPOS_PRESET = ("largo_min", "largo_min_laxo", "ident_min", "lote", "db")


def valores_de_preset(nombre: str) -> dict:
    """Qué valores deja ese preset en los campos que se muestran."""
    p = aplicar_preset(Parametros(entrada="."), nombre)
    return {campo: getattr(p, campo) for campo in CAMPOS_PRESET}
