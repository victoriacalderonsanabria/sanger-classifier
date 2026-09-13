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
    ) -> dict[str, list[Hit] | None]:
        """
        Devuelve, por nombre de muestra, hasta tres hits de especies distintas.

        Una lista vacía significa "se consultó y no hubo coincidencias".
        **None significa que no se pudo consultar** (se cayó la red, falló
        blastn): eso no es un resultado y no se confunde con lo anterior
        (BUG-1). Tampoco se guarda en el caché, así al relanzar se reintenta.

        megablast=True es el algoritmo rápido, para secuencias buenas (CONFIABLES);
        False es blastn, más sensible, para secuencias con errores (DUDOSAS).

        `progreso` informa el avance (un envío, una respuesta) y `cancelado` se
        consulta entre lotes: si devuelve True, se levanta `Cancelado`.
        """
        ...
