"""
Escritor mínimo de archivos .ab1 (formato ABIF de Applied Biosystems).

Por qué existe: Biopython lee .ab1 pero no los escribe, y la regla del proyecto
es probar `leer_ab1` contra archivos de verdad, no contra una imitación de la
función. Esto arma un archivo ABIF válido con lo mínimo que lee Biopython.

Estructura de un ABIF:
  - Cabecera de 128 bytes: la marca "ABIF", la versión y una entrada de
    directorio ("tdir") que dice dónde está el directorio y cuántas entradas tiene.
  - Los datos de cada etiqueta.
  - El directorio: una entrada de 28 bytes por etiqueta (nombre, número, tipo,
    tamaño y dónde están sus datos). Si los datos ocupan 4 bytes o menos, van
    dentro de la propia entrada en vez de afuera.

Etiquetas que se escriben:
  - PBAS2 / PCON2: bases y calidades según el basecaller. Son las que lee
    Biopython (SeqIO "abi").
  - PBAS1 / PCON1: la versión "editada por el usuario". Biopython no las usa,
    pero todo .ab1 real las tiene y el briefing las pide.

Todo en big-endian, como manda la especificación del formato.
"""

import struct
from pathlib import Path

_TIPO_CHAR = 2  # arreglo de bytes
_TAM_ENTRADA = 28
_TAM_CABECERA = 128


def _entrada_directorio(nombre: str, numero: int, datos: bytes, offset: int) -> bytes:
    """Una entrada de 28 bytes. Datos de ≤4 bytes van adentro, rellenados con ceros."""
    if len(datos) <= 4:
        (campo_offset,) = struct.unpack(">I", datos.ljust(4, b"\0"))
    else:
        campo_offset = offset
    return struct.pack(
        ">4sI2H4I",
        nombre.encode("ascii"),
        numero,
        _TIPO_CHAR,
        1,  # tamaño de cada elemento: 1 byte
        len(datos),  # cantidad de elementos
        len(datos),  # tamaño total
        campo_offset,
        0,  # "data handle", sin uso
    )


def contenido_ab1(seq: str, qual: list[int]) -> bytes:
    """Los bytes de un .ab1 con esa secuencia y esas calidades Phred."""
    if len(seq) != len(qual):
        raise ValueError(f"seq ({len(seq)}) y qual ({len(qual)}) tienen que medir lo mismo")
    if any(not 0 <= q <= 127 for q in qual):
        # Biopython decodifica las calidades como texto UTF-8: más de 127 no se lee bien
        raise ValueError("las calidades tienen que estar entre 0 y 127")
    bases = seq.encode("ascii")
    calidades = bytes(qual)
    etiquetas = [
        ("PBAS", 1, bases),
        ("PBAS", 2, bases),
        ("PCON", 1, calidades),
        ("PCON", 2, calidades),
    ]

    bloque_datos = b""
    entradas = []
    for nombre, numero, datos in etiquetas:
        offset = _TAM_CABECERA + len(bloque_datos)
        if len(datos) > 4:
            bloque_datos += datos
        entradas.append(_entrada_directorio(nombre, numero, datos, offset))
    directorio = b"".join(entradas)
    offset_directorio = _TAM_CABECERA + len(bloque_datos)

    cabecera = b"ABIF" + struct.pack(
        ">H4sI2H4I",
        101,  # versión del formato
        b"tdir",
        1,
        1023,  # tipo "directorio"
        _TAM_ENTRADA,
        len(etiquetas),
        len(directorio),
        offset_directorio,
        0,
    )
    cabecera = cabecera.ljust(_TAM_CABECERA, b"\0")
    return cabecera + bloque_datos + directorio


def escribir_ab1(ruta: Path, seq: str, qual: list[int]) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido_ab1(seq, qual))
    return ruta
