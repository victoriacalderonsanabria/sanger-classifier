"""
Errores del núcleo.

Por qué existen: una librería no debe terminar el proceso. Antes, tres
situaciones llamaban a `sys.exit` (Biopython ausente, carpeta sin `.ab1`,
`blastn` no encontrado), y eso le llegaba a la ventana como un `SystemExit` que
había que atrapar a mano. Ahora el núcleo levanta estas excepciones y cada
cliente decide qué hacer: la línea de comandos las convierte en un mensaje y un
código de salida, la ventana las muestra en un cartel.
"""


class SangerError(Exception):
    """Cualquier error previsto del análisis. Su texto es para mostrarle a quien usa el programa."""


class SinArchivosError(SangerError):
    """No hay cromatogramas .ab1 en la carpeta de entrada."""


class BlastError(SangerError):
    """No se pudo hacer BLAST (falta blastn, la base no existe, etc.)."""


class Cancelado(SangerError):
    """Quien pidió el análisis lo canceló. No es una falla."""
