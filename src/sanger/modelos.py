"""
Las piezas de información que recorren el pipeline.

Por qué clases con nombre y no diccionarios sueltos: en el script original cada
lectura y cada muestra eran un diccionario al que se le iban agregando claves en
distintos lugares. Funcionaba, pero para saber qué contenía una muestra había
que leer todo el programa. Acá cada campo está declarado una vez, con su tipo.
"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum

# Separador usado DENTRO de un campo de texto (listas de archivos, motivos).
# Nunca debe coincidir con el separador de columnas del CSV (';' o ','), así el
# archivo no se rompe si alguien lo vuelve a separar en columnas a mano.
SEP_INTERNO = " | "


class Grupo(StrEnum):
    """En qué grupo queda cada muestra (ver README_clasificar_sanger.md)."""

    CONFIABLE = "CONFIABLE"
    DUDOSA = "DUDOSA"
    RECHAZADA = "RECHAZADA"


class Senal(StrEnum):
    """Diagnóstico de una lectura individual, antes de mirar la muestra entera."""

    BUENA = "BUENA"
    PARCIAL = "PARCIAL"
    SIN_SENAL = "SIN_SEÑAL"


@dataclass(frozen=True)
class Hit:
    """Un resultado de BLAST: la mejor coincidencia de una especie en GenBank."""

    especie: str
    accession: str
    identidad: float
    cobertura: float
    evalue: float
    titulo: str

    def como_dict(self) -> dict:
        """Para el JSON de salida y el caché. El orden de las claves es el del original."""
        return asdict(self)


@dataclass(frozen=True)
class Lectura:
    """Un cromatograma (.ab1) ya leído y evaluado por calidad."""

    archivo: str
    muestra: str
    sentido: str  # "F", "R" o "?" si el nombre no lo dice
    seq: str  # lectura CRUDA, sin recortar: el consenso se arma sobre esto
    qual: list[int]
    largo_crudo: int
    q_media_cruda: float
    amb_cruda: int
    bases_q20: int
    largo_estricto: int
    q_media_estricto: float
    largo_laxo: int
    senal: Senal
    error: str | None = None  # si el archivo no se pudo leer


@dataclass
class Muestra:
    """
    Una muestra (normalmente dos lecturas, F y R) y todo lo que se concluyó de ella.

    Los campos que no aplican quedan en None (p. ej. `solapamiento` cuando no hubo
    consenso) y salen como celda vacía en el CSV.
    """

    nombre: str
    archivos: tuple[str, ...]
    grupo: Grupo = Grupo.RECHAZADA
    origen: str = ""  # "CONSENSO_F+R", "SOLO_F", "SOLO_R", "SOLO_?"
    secuencia: str = ""
    largo: int = 0
    q_media: float | None = None
    pct_q20: float | None = None
    solapamiento: int | None = None
    discrepancias: int | None = None
    conflictos: int | None = None
    motivos: list[str] = field(default_factory=list)
    vs_confiables: str | None = None
    hits: list[Hit] = field(default_factory=list)
    interpretacion: str | None = None

    @property
    def motivo(self) -> str:
        """Los motivos en un solo texto, como aparecen en el CSV y en el FASTA."""
        return SEP_INTERNO.join(self.motivos)


@dataclass
class Resultado:
    """Lo que devuelve una corrida completa."""

    lecturas: list[Lectura]
    muestras: list[Muestra]
    segundos_total: float = 0.0
    segundos_blast: float = 0.0

    def del_grupo(self, grupo: Grupo) -> list[Muestra]:
        return [m for m in self.muestras if m.grupo == grupo]
