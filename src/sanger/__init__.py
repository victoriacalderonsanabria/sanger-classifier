"""
sanger: control de calidad, consenso F/R y BLAST de cromatogramas Sanger.

El núcleo (este paquete) no sabe que existe una interfaz: la línea de comandos
(`sanger.cli`) y la ventana son dos clientes del mismo `sanger.pipeline`.
"""

import logging

# La versión del programa, y la única fuente: `pyproject.toml` la lee de acá
# (versión dinámica) y la ventana la muestra en el título. Cuando estaba escrita
# en los dos lados se desincronizaron: 0.2.0 acá contra 0.1.0 en pyproject.
__version__ = "1.0.0"

# Una librería no decide adónde van sus mensajes de log: si nadie configuró
# logging, no se muestran (sin esto Python los mandaría a la salida de error y
# ensuciaría la consola del programa).
logging.getLogger(__name__).addHandler(logging.NullHandler())
