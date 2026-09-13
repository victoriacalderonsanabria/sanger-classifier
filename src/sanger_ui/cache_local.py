"""
Dónde guarda la ventana el caché de BLAST.

El caché **no es un resultado, es infraestructura**: es lo que hace que una
corrida cortada se retome sin volver a pagar veinte minutos de BLAST. Cuando la
ventana dejó de escribir una carpeta de resultados, el caché se quedó sin casa.

Vive en una carpeta estable del sistema (`%LOCALAPPDATA%\\Sanger\\cache` en
Windows), con una subcarpeta por carpeta de entrada. Así sobrevive a todo y no
escribe dentro de las carpetas de datos, que pueden estar en OneDrive, en un
pendrive o en un disco de solo lectura.

Como es invisible, la ventana muestra cuánto ocupa y ofrece limpiarlo.
"""

import hashlib
import os
import shutil
from pathlib import Path

MARCA = "_de_que_carpeta_es.txt"


def raiz() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Sanger" / "cache"
    return Path.home() / ".cache" / "sanger"


def carpeta_para(entrada: Path | str) -> Path:
    """Una subcarpeta por carpeta de entrada, identificada por su ruta."""
    ruta = os.path.normcase(str(Path(entrada).resolve()))
    return raiz() / hashlib.sha256(ruta.encode("utf-8")).hexdigest()[:16]


def preparar(entrada: Path | str) -> Path:
    """La carpeta de caché, creada y con una marca que dice de qué corrida es."""
    carpeta = carpeta_para(entrada)
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        (carpeta / MARCA).write_text(str(Path(entrada).resolve()), encoding="utf-8")
    except OSError:
        pass  # la marca es una ayuda para mirar la carpeta a mano, no es crítica
    return carpeta


def tamano(carpeta: Path) -> int:
    """Cuánto ocupa, en bytes (0 si no existe)."""
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return 0
    return sum(p.stat().st_size for p in carpeta.rglob("*") if p.is_file())


def limpiar(carpeta: Path) -> int:
    """Borra el caché de esa carpeta. Devuelve cuántos bytes se liberaron."""
    liberado = tamano(carpeta)
    shutil.rmtree(carpeta, ignore_errors=True)
    return liberado


def formatear_tamano(bytes_: int) -> str:
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} KB".replace(".", ",")
    return f"{bytes_ / 1024 / 1024:.1f} MB".replace(".", ",")
