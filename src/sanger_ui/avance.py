"""
Cuánto pesa cada etapa en la barra de progreso.

Por qué no se cuenta por ítems: el control de calidad procesa 192 cromatogramas
en segundos y el BLAST son 2 o 3 envíos que tardan minutos. Contando ítems, la
barra llegaría casi al final en dos segundos y después se quedaría clavada
durante el 90 % del tiempo real. Con pesos, el avance se parece al tiempo que
falta.

Los pesos son una estimación honesta del reparto del tiempo, no una medición:
adentro de la espera de un lote no hay forma de saber cuánto falta, porque NCBI
no informa progreso. Por eso, además de la barra, está el cronómetro: aunque la
barra no se mueva, el reloj corriendo dice que el programa está vivo.
"""

PESOS = {"qc": 10, "clasificacion": 5, "comparacion": 5, "blast": 75, "informes": 5}
ORDEN = ("qc", "clasificacion", "comparacion", "blast", "informes")


def porcentaje(etapa: str, hechos: int, total: int) -> int:
    """Avance global 0–100, interpolando dentro de la etapa con lo que haya."""
    if etapa not in PESOS:
        return 0
    anteriores = sum(PESOS[e] for e in ORDEN[: ORDEN.index(etapa)])
    fraccion = min(max(hechos / total, 0.0), 1.0) if total else 0.0
    return round(anteriores + PESOS[etapa] * fraccion)


def reloj(segundos: float) -> str:
    """Cronómetro corto para la línea de estado: 42s, 1m 42s, 21m 3s."""
    segundos = int(segundos)
    return f"{segundos // 60}m {segundos % 60}s" if segundos >= 60 else f"{segundos}s"
