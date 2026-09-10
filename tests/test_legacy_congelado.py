"""
legacy/identificar_ingestas.py produjo los resultados del informe del ensayo
de ingestas. Tiene que quedar idéntico al original, byte a byte, para siempre:
si cambia, ya no es el script que generó ese informe.

Este test falla ante cualquier modificación, aunque sea un espacio o un salto
de línea. Si falla, no se actualiza el hash: se deshace el cambio.
"""

import hashlib
from pathlib import Path

SHA256_ORIGINAL = "7942b7dbe9cacd6d3d60a70833ffc8182a14b53396f07fc9b9e6e7041ff20170"
LEGACY = Path(__file__).resolve().parent.parent / "legacy" / "identificar_ingestas.py"


def test_identificar_ingestas_sigue_identico_al_original():
    assert hashlib.sha256(LEGACY.read_bytes()).hexdigest() == SHA256_ORIGINAL
