"""
Regla de dependencias del BRIEFING §3.2, verificada automáticamente.

- qc/, ensamblado/ y clasificacion.py son funciones puras sobre secuencias y
  calidades: no importan nada de io/, blast/, del pipeline ni de la interfaz.
- Nada del núcleo (src/sanger) importa la interfaz.
- pipeline.py es el único que orquesta: solo la línea de comandos lo importa.

Esto es lo que después permite enchufar otra interfaz (PySide6, Streamlit) sin
tocar una línea de ciencia. Se revisa leyendo el código (AST), sin ejecutarlo.
"""

import ast
import sys
from pathlib import Path

import pytest

SANGER = Path(__file__).resolve().parent.parent / "src" / "sanger"

PUROS = [*sorted((SANGER / "qc").glob("*.py")), *sorted((SANGER / "ensamblado").glob("*.py"))]
PUROS.append(SANGER / "clasificacion.py")

# lo único del proyecto que pueden usar los módulos puros
PERMITIDOS_PUROS = ("sanger.qc", "sanger.ensamblado", "sanger.modelos", "sanger.config")
INTERFAZ = ("sanger_ui", "PySide6", "tkinter", "streamlit")


def _modulo_de(ruta: Path) -> str:
    partes = ruta.relative_to(SANGER.parent).with_suffix("").parts
    return ".".join(partes[:-1] if partes[-1] == "__init__" else partes)


def imports_de(codigo: str, modulo: str) -> set[str]:
    """Todos los módulos que importa `codigo`, con los imports relativos resueltos."""
    paquete = modulo.rsplit(".", 1)[0]
    encontrados = set()
    for nodo in ast.walk(ast.parse(codigo)):
        if isinstance(nodo, ast.Import):
            encontrados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                base = paquete.split(".")[: len(paquete.split(".")) - nodo.level + 1]
                nombre = ".".join(base + ([nodo.module] if nodo.module else []))
            else:
                nombre = nodo.module
            encontrados.add(nombre)
    return encontrados


def _es_de(nombre: str, prefijos) -> bool:
    return any(nombre == p or nombre.startswith(p + ".") for p in prefijos)


def prohibidos_en_puro(imports: set[str]) -> set[str]:
    return {
        n
        for n in imports
        if not (
            n.split(".")[0] in sys.stdlib_module_names
            and not _es_de(n, INTERFAZ)
            or _es_de(n, ("Bio",))
            or _es_de(n, PERMITIDOS_PUROS)
        )
    }


@pytest.mark.parametrize("ruta", PUROS, ids=lambda r: r.relative_to(SANGER).as_posix())
def test_modulos_puros_no_importan_efectos_ni_interfaz(ruta):
    imports = imports_de(ruta.read_text(encoding="utf-8"), _modulo_de(ruta))
    assert prohibidos_en_puro(imports) == set()


def test_ningun_modulo_del_nucleo_importa_la_interfaz():
    for ruta in SANGER.rglob("*.py"):
        imports = imports_de(ruta.read_text(encoding="utf-8"), _modulo_de(ruta))
        assert not {n for n in imports if _es_de(n, INTERFAZ)}, ruta


def test_solo_la_linea_de_comandos_usa_el_pipeline():
    usan = {
        _modulo_de(r)
        for r in SANGER.rglob("*.py")
        if "sanger.pipeline" in imports_de(r.read_text(encoding="utf-8"), _modulo_de(r))
    }
    assert usan == {"sanger.cli"}


def test_existen_los_modulos_puros():
    # si alguien mueve los archivos, este test tiene que seguir revisando algo
    nombres = {r.relative_to(SANGER).as_posix() for r in PUROS}
    assert {
        "qc/recorte.py",
        "qc/metricas.py",
        "ensamblado/consenso.py",
        "clasificacion.py",
    } <= nombres


# El detector también se prueba: si no detectara nada, los tests de arriba
# pasarían siempre y no protegerían nada.


@pytest.mark.parametrize(
    ("codigo", "prohibido"),
    [
        ("from sanger.io.informes import escribir_csv", "sanger.io.informes"),
        ("import sanger.blast.remoto", "sanger.blast.remoto"),
        ("from ..io import ab1", "sanger.io"),
        ("from ..blast.remoto import MotorRemoto", "sanger.blast.remoto"),
        ("from sanger import pipeline", "sanger"),
        ("import tkinter", "tkinter"),
        ("from PySide6.QtCore import QThread", "PySide6.QtCore"),
        ("import numpy", "numpy"),
    ],
)
def test_el_detector_encuentra_imports_prohibidos(codigo, prohibido):
    assert prohibido in prohibidos_en_puro(imports_de(codigo, "sanger.qc.metricas"))


@pytest.mark.parametrize(
    "codigo",
    [
        "import re",
        "from collections.abc import Sequence",
        "from Bio.Seq import Seq",
        "from sanger.qc.recorte import recorte_mott",
        "from .recorte import recorte_mott",
        "from sanger.modelos import Lectura",
    ],
)
def test_el_detector_deja_pasar_lo_permitido(codigo):
    assert prohibidos_en_puro(imports_de(codigo, "sanger.qc.metricas")) == set()
