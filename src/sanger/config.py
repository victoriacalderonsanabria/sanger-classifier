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
    """Un punto de partida sugerido para un marcador. No es una regla."""

    nombre: str
    descripcion: str
    cambios: dict


# QUÉ SON Y QUÉ NO SON (decisión de Victoria, 13/09/2026)
#
# Son perfiles ORIENTATIVOS: cargan valores razonables en los campos para no
# arrancar de cero con cada marcador, y después se ajustan a mano. No son
# criterios de identificación taxonómica. En particular, el 98,7 % de identidad
# del 16S es un valor SUGERIDO y de uso frecuente en la literatura, no un
# umbral que defina una especie: eso depende del gen, del grupo y del contexto
# del ensayo.
#
# El perfil principal es Default: el programa está pensado sobre todo
# para el laboratorio (Sanger de virus e identificación de ingestas de
# mosquitos), y esos valores son los validados con el ensayo de ingestas
# (amplicón corto de ~260 pb; por eso largo mínimo 100 y no 300).
#
# Los valores de los otros perfiles salen de README_clasificar_sanger.md.
PRESET_DEFAULT = "Default"

PRESETS = (
    Preset(
        PRESET_DEFAULT,
        "La configuración habitual del programa, validada con el ensayo de ingestas "
        "(amplicones de 200–400 pb). Es el punto de partida para el trabajo del laboratorio.",
        {},
    ),
    Preset(
        "COI Folmer (~650 pb)",
        "Amplicón largo: se sugiere subir el largo mínimo a 300 pb. Ajustalo según "
        "cuánta secuencia útil deje tu corrida.",
        {"largo_min": 300},
    ),
    Preset(
        "16S bacteriano",
        "Base curada de 16S y una identidad sugerida de 98,7 %, un valor de uso frecuente "
        "en la literatura. NO es un umbral que defina especie: tomalo como punto de partida "
        "y decidí con el contexto del ensayo.",
        {"largo_min": 300, "ident_min": 98.7, "db": "16S_ribosomal_RNA"},
    ),
    Preset(
        "ITS hongos",
        "Base de ITS de hongos de RefSeq; el resto de los valores queda como estaba.",
        {"db": "ITS_RefSeq_Fungi"},
    ),
)

AVISO_PRESETS = (
    "Los perfiles son sugerencias de configuración, no criterios de identificación "
    "taxonómica: cargan valores de partida que después conviene ajustar al ensayo."
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


def normalizar_valores(valores) -> dict:
    """
    Deja un juego completo de valores de perfil a partir de lo que venga.

    Lo que llega puede estar incompleto o directamente mal (sale de un archivo
    de preferencias que alguien puede editar a mano). Lo que falta se completa
    con los valores del programa; si algo no se puede interpretar, se devuelve
    vacío y el programa sigue con su Default de siempre: una preferencia rota
    no puede impedir que el programa arranque.
    """
    if not isinstance(valores, dict):
        return {}
    limpios = {k: v for k, v in valores.items() if k in CAMPOS_PRESET}
    if not isinstance(limpios.get("db", ""), str):
        return {}
    try:
        p = Parametros(entrada=".").con(**limpios)
    except (TypeError, ValueError):
        return {}
    return {campo: getattr(p, campo) for campo in CAMPOS_PRESET}


def valores_de_preset(nombre: str, propios: dict | None = None) -> dict:
    """
    Qué valores deja ese perfil en los campos que se muestran.

    `propios` es el Default que se guardó en esta computadora (otro equipo de
    investigación puede tener criterios distintos a los del laboratorio). Pasa a
    ser la base de todos los perfiles, no solo del Default: los demás perfiles
    son unos pocos cambios sobre la configuración de base, así que lo que un
    perfil no toca tiene que seguir siendo lo que el equipo dejó puesto.
    """
    base = Parametros(entrada=".")
    propios = normalizar_valores(propios)
    if propios:
        base = base.con(**propios)
    p = base.con(**preset(nombre).cambios)
    return {campo: getattr(p, campo) for campo in CAMPOS_PRESET}
