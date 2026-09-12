"""
El análisis corre en un hilo aparte, para que la ventana no se congele.

Antes, la ventana llamaba al script pisando `sys.argv` y `sys.stdout`, y se
enteraba de lo que pasaba leyendo el texto que el script imprimía. Ahora el
núcleo avisa y este hilo reenvía esos avisos como señales de Qt, que es la
forma segura de mandar algo desde un hilo a la ventana.
"""

from PySide6.QtCore import QThread, Signal

from sanger.config import Parametros
from sanger.errores import Cancelado
from sanger.modelos import Progreso
from sanger.pipeline import ejecutar


class Worker(QThread):
    """Corre `pipeline.ejecutar` y avisa por señales."""

    progreso = Signal(object)  # Progreso: para la barra y el estado
    log = Signal(str)  # el texto tal cual, para el registro en pantalla
    terminado = Signal(object)  # Resultado
    error = Signal(object)  # Exception (incluye Cancelado, que no es una falla)

    def __init__(self, params: Parametros, parent=None):
        super().__init__(parent)
        self.params = params
        self._cancelar = False

    def cancelar(self) -> None:
        """Pide cortar. El núcleo lo consulta entre lecturas, muestras y lotes."""
        self._cancelar = True

    def _avisar(self, progreso: Progreso) -> None:
        self.progreso.emit(progreso)
        if progreso.mensaje:
            self.log.emit(progreso.mensaje + progreso.fin)

    def run(self) -> None:
        try:
            resultado = ejecutar(
                self.params, progreso=self._avisar, cancelado=lambda: self._cancelar
            )
        except Cancelado as e:
            self.error.emit(e)
        except Exception as e:  # que un error no se lleve puesta la ventana
            self.error.emit(e)
        else:
            self.terminado.emit(resultado)
