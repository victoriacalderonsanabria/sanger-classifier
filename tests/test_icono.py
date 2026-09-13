"""
El icono del programa: que siga siendo el archivo que nos dieron.

Por qué un test para un `.ico`: adentro tiene siete imágenes dibujadas una por
una (16, 24, 32, 48, 64, 128 y 256 px), con distinto encuadre y grosor de trazo
según el tamaño. Cualquier herramienta que lo "rearme" a partir del PNG grande
—PIL, ImageMagick, un conversor online— produce un archivo que abre bien, se ve
bien en grande y se ve mal en la barra de tareas. Ese error es silencioso: nadie
lo nota hasta que el icono ya está distribuido.

Así que se verifica lo único que lo detecta: que el archivo del repo sea, byte
por byte, el que se aprobó. Si hay que cambiar el icono a propósito, este test
falla y se actualiza el hash **a mano**, mirando el icono nuevo.

No importa PySide6: corre también en el CI, que no lo instala.
"""

import hashlib
import struct
from pathlib import Path

RECURSOS = Path(__file__).resolve().parents[1] / "src" / "sanger_ui" / "recursos"
ICONO = RECURSOS / "icono_sanger_v2.ico"

# sha256 del .ico aprobado por Victoria (13/09/2026). Ver el docstring antes de
# tocar este valor.
SHA256_APROBADO = "dde61b4e683b6fe6266b070b74011cfc06818d0a07e173e9e4cdd859322f0920"

# Los siete tamaños, del más grande al más chico, en el orden en que vienen.
TAMANOS = (256, 128, 64, 48, 32, 24, 16)


def _imagenes(datos: bytes) -> list[tuple[int, int, int]]:
    """Lee el índice del .ico: (ancho, alto, bits por pixel) de cada imagen."""
    reservado, tipo, cantidad = struct.unpack_from("<HHH", datos, 0)
    assert (reservado, tipo) == (0, 1), "no es un .ico válido"
    imagenes = []
    for i in range(cantidad):
        ancho, alto, _cols, _rsv, _planos, bpp, tam, off = struct.unpack_from(
            "<BBBBHHII", datos, 6 + i * 16
        )
        # 0 significa 256: el campo es de un byte y no le entra
        imagenes.append((ancho or 256, alto or 256, bpp))
        assert off + tam <= len(datos), f"la imagen {i} apunta fuera del archivo"
    return imagenes


def test_el_icono_es_el_archivo_aprobado():
    assert ICONO.exists(), f"falta {ICONO.name}"
    assert hashlib.sha256(ICONO.read_bytes()).hexdigest() == SHA256_APROBADO, (
        "el .ico no es el aprobado: si alguien lo regeneró o lo reconvirtió, "
        "los tamaños chicos dejaron de estar dibujados a mano"
    )


def test_el_icono_conserva_los_siete_tamanos():
    imagenes = _imagenes(ICONO.read_bytes())
    assert tuple(ancho for ancho, _, _ in imagenes) == TAMANOS
    assert all(ancho == alto for ancho, alto, _ in imagenes)  # todos cuadrados
    assert all(bpp == 32 for *_, bpp in imagenes)  # con transparencia


def test_esta_la_version_grande_para_reimprimir():
    # el PNG de 512 no lo usa el programa: está para volver a exportar el .ico
    # o para usarlo en un póster sin partir de una captura de pantalla
    png = RECURSOS / "icono_sanger_v2_512.png"
    assert png.exists() and png.read_bytes().startswith(b"\x89PNG")


def test_el_icono_viejo_sigue_estando():
    # todavía no se borra: hasta que el .exe nuevo esté distribuido y probado,
    # poder volver atrás es gratis
    assert (RECURSOS / "logo_mosquito.ico").exists()
