"""
Qué tiene que saber hacer un motor de BLAST.

Por qué una interfaz común: el pipeline no necesita saber si las secuencias van
a NCBI, a un blastn instalado en la máquina o, en los tests, a un archivo con
respuestas preparadas. Así la suite de tests corre sin internet y el día de
mañana se puede enchufar otro motor sin tocar la clasificación.
"""

from collections.abc import Sequence
from typing import Protocol

from sanger.modelos import Avisar, Hit, PreguntarCancelado

# (nombre de la muestra, secuencia, largo de la secuencia)
Consulta = tuple[str, str, int]


class MotorBlast(Protocol):
    def buscar(
        self,
        consultas: Sequence[Consulta],
        megablast: bool,
        progreso: Avisar = ...,
        cancelado: PreguntarCancelado = ...,
    ) -> dict[str, list[Hit]]:
        """
        Devuelve, por nombre de muestra, hasta tres hits de especies distintas.

        megablast=True es el algoritmo rápido, para secuencias buenas (CONFIABLES);
        False es blastn, más sensible, para secuencias con errores (DUDOSAS).

        `progreso` informa el avance (un envío, una respuesta) y `cancelado` se
        consulta entre lotes: si devuelve True, se levanta `Cancelado`.
        """
        ...
