"""
Lo que la ventana recuerda entre corridas: el mail, las últimas carpetas y el preset.

Vive en `~/.sanger/config.json`, fuera del repositorio: el mail de NCBI es un
dato personal y no se versiona nunca. Si el archivo no existe o está roto, se
arranca con los valores por defecto; no es algo que deba frenar el programa.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CARPETA = Path.home() / ".sanger"
ARCHIVO = CARPETA / "config.json"
CLAVES = ("email", "entrada", "exportacion", "preset", "db", "taxon")


def cargar(archivo: Path | None = None) -> dict:
    # la ruta se resuelve al llamar, no al importar: así se puede redirigir
    archivo = Path(archivo) if archivo else ARCHIVO
    try:
        datos = json.loads(Path(archivo).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as e:
        log.warning("no se pudo leer %s: %s", archivo, e)
        return {}
    return {k: v for k, v in datos.items() if k in CLAVES and isinstance(v, str)}


def guardar(datos: dict, archivo: Path | None = None) -> None:
    archivo = Path(archivo) if archivo else ARCHIVO
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        guardables = {k: v for k, v in datos.items() if k in CLAVES and isinstance(v, str)}
        archivo.write_text(json.dumps(guardables, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        # no poder guardar las preferencias no es motivo para molestar a nadie
        log.warning("no se pudieron guardar las preferencias en %s: %s", archivo, e)
