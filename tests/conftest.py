from pathlib import Path

import pytest

from sanger.config import Parametros

FIXTURES_BLAST = Path(__file__).parent / "fixtures" / "blast"


@pytest.fixture
def params():
    """Parámetros por defecto (los validados), con carpetas de mentira."""
    return Parametros(entrada=Path("entrada"), salida=Path("salida"))


@pytest.fixture
def fixtures_blast():
    return FIXTURES_BLAST
