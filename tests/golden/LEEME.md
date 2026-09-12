# Snapshots de regresión (golden)

Salida completa del pipeline sobre la corrida sintética estándar
(`tests/sintetico/corrida.py`, 16 muestras / 26 cromatogramas), en dos variantes:

- `sin_blast/`: con `--no-blast`.
- `con_blast/`: con BLAST remoto, respondido desde un caché armado con
  `tests/fixtures/blast/` (no se consulta a NCBI).

Cada carpeta tiene los seis informes (`00` a `05`) y `consola.txt`, lo que se
imprimió en pantalla. `tests/test_golden.py` corre el pipeline y compara todo;
solo se ignora la línea del tiempo de ejecución.

## De dónde salieron

Los generó el `clasificar_sanger.py` **original** (SHA-256 `4A23B7A0…114D1`,
el de la fase 0), con:

```
python scripts/generar_goldens.py --script <ruta al clasificar_sanger.py original>
```

Por eso que `test_golden.py` pase prueba que el paquete de la fase 1 produce
exactamente lo mismo que el script de antes del refactor.

## Normalizaciones (para que valgan en Windows y en Linux)

- En `consola.txt`, las rutas de entrada y salida aparecen como `<ENTRADA>` y
  `<SALIDA>`.
- `.txt`, `.fasta` y `.json` se guardan con fin de línea LF. Python los escribe
  con CRLF en Windows y con LF en Linux; el test normaliza igual antes de comparar.
  Los CSV no se tocan: el módulo `csv` los escribe con CRLF en cualquier sistema.
- Los `.fasta` se guardan en UTF-8. Biopython los escribe con la codificación
  del sistema (cp1252 en Windows, UTF-8 en Linux), y el motivo de las DUDOSAS
  lleva acentos ("se usó recorte"). Así lo hace el script original.

## Cuándo se actualizan

Solo cuando la salida **tiene que** cambiar (la fase 4, por ejemplo). Es un
acto deliberado: se corre `python scripts/generar_goldens.py` a mano, se revisa
el diff y se explica en el PR qué cambió y por qué. Nunca en el CI.
