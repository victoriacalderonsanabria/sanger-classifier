"""
Motor de BLAST para tests: responde con hits preparados, sin internet.

Cada fixture es un archivo JSON con la lista de hits que devolvería BLAST para
un caso típico (hit claro, dos especies del mismo género empatadas, etc.). El
test decide qué fixture le toca a cada muestra.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from sanger.blast.base import Consulta
from sanger.errores import Cancelado
from sanger.modelos import Avisar, Hit, PreguntarCancelado, Progreso, nunca_cancelado, sin_aviso


def cargar_fixture(ruta: Path) -> list[Hit]:
    return [Hit(**h) for h in json.loads(Path(ruta).read_text(encoding="utf-8"))]


class MotorFalso:
    """
    asignaciones: nombre de muestra -> nombre de fixture (sin .json).
    Una muestra sin asignación recibe una lista vacía, como una sin hits.
    """

    def __init__(self, carpeta_fixtures: Path, asignaciones: Mapping[str, str]):
        self.carpeta_fixtures = Path(carpeta_fixtures)
        self.asignaciones = dict(asignaciones)
        self.llamadas: list[tuple[tuple[str, ...], bool]] = []  # para verificar en tests

    def buscar(
        self,
        consultas: Sequence[Consulta],
        megablast: bool,
        progreso: Avisar = sin_aviso,
        cancelado: PreguntarCancelado = nunca_cancelado,
    ) -> dict[str, list[Hit]]:
        self.llamadas.append((tuple(n for n, _, _ in consultas), megablast))
        resultado = {}
        for hechas, (nombre, _, _) in enumerate(consultas):
            if cancelado():
                raise Cancelado("cancelado durante el BLAST")
            fixture = self.asignaciones.get(nombre)
            resultado[nombre] = (
                cargar_fixture(self.carpeta_fixtures / f"{fixture}.json") if fixture else []
            )
            progreso(Progreso("blast", hechas + 1, len(consultas)))
        return resultado
