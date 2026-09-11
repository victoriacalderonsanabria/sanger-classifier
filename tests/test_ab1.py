"""
Lectura de .ab1 contra archivos reales (escritos por tests/sintetico/ab1_writer.py).

El escritor se validó además, fuera del repo, contra los 192 cromatogramas
reales del ensayo: leer → reescribir → volver a leer dio idéntico en los 192.
"""

import pytest

from sanger.io.ab1 import descubrir_archivos, leer_ab1
from tests.sintetico.ab1_writer import contenido_ab1, escribir_ab1
from tests.sintetico.generador import Perfil, leer, verdad


@pytest.mark.parametrize("perfil", list(Perfil))
def test_leer_ab1_devuelve_lo_que_se_escribio(tmp_path, perfil):
    seq, qual = leer(verdad(), perfil)
    ruta = escribir_ab1(tmp_path / "x.ab1", seq, qual)
    assert leer_ab1(ruta) == (seq, qual)


@pytest.mark.parametrize("largo", [0, 1, 4, 5])
def test_leer_ab1_lecturas_minimas(tmp_path, largo):
    # hasta 4 bytes los datos van dentro del directorio del archivo, no afuera
    ruta = escribir_ab1(tmp_path / "x.ab1", "ACGTA"[:largo], [30] * largo)
    assert leer_ab1(ruta) == ("ACGTA"[:largo], [30] * largo)


def test_leer_ab1_archivo_que_no_es_ab1(tmp_path):
    ruta = tmp_path / "x.ab1"
    ruta.write_bytes(b"esto no es un cromatograma")
    with pytest.raises(ValueError, match="ABIF"):
        leer_ab1(ruta)


def test_escritor_rechaza_datos_inconsistentes():
    with pytest.raises(ValueError):
        contenido_ab1("ACGT", [30, 30])
    with pytest.raises(ValueError):
        contenido_ab1("A", [200])


def test_descubrir_archivos_recursivo_y_sin_importar_mayusculas(tmp_path):
    for nombre in ("b_F.ab1", "a_R.AB1", "sub/c_F.Ab1", "notas.txt", "d.ab1.bak"):
        destino = tmp_path / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"")
    nombres = [p.relative_to(tmp_path).as_posix() for p in descubrir_archivos(tmp_path)]
    assert nombres == ["a_R.AB1", "b_F.ab1", "sub/c_F.Ab1"]
