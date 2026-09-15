"""
La versión: una sola fuente.

Existía escrita en dos lados y se desincronizó (`0.2.0` en `sanger/__init__.py`
contra `0.1.0` en `pyproject.toml`). Nadie lo notó porque hasta ahora no la
miraba nadie; desde que la ventana la muestra y hay releases numeradas, un
número equivocado hace perder tiempo: alguien reporta un problema de "la 1.0.0"
que en realidad es otra versión.

Así que la fuente es `sanger.__version__` y `pyproject.toml` la lee de ahí.
Estos tests verifican que siga siendo así.
"""

import re
import tomllib
from pathlib import Path

import sanger

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _proyecto() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def test_la_version_es_un_numero_de_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", sanger.__version__), sanger.__version__


def test_pyproject_no_repite_la_version():
    # si alguien vuelve a escribirla acá, vuelven a poder decir cosas distintas
    proyecto = _proyecto()
    assert "version" not in proyecto, "la versión se declara solo en sanger/__init__.py"
    assert "version" in proyecto.get("dynamic", [])


def test_pyproject_la_lee_del_paquete():
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dinamica = config["tool"]["setuptools"]["dynamic"]["version"]
    assert dinamica == {"attr": "sanger.__version__"}
