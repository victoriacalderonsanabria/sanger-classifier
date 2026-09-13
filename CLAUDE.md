# CLAUDE.md — Proyecto Sanger

Reglas permanentes para cualquier agente que trabaje en este repo.
El encargo completo está en `BRIEFING.md`, en la carpeta del proyecto (fuera de
este repo, porque es un documento interno). Esto es el resumen operativo.

---

## Qué es esto

Pipeline de análisis de cromatogramas Sanger (`.ab1`) que identifica especies por
BLAST contra NCBI. Validado sobre 192 cromatogramas reales (96 muestras).
Lo usa Victoria Calderón, bióloga, no programadora.

## Idioma

Todo en **español rioplatense**: nombres de funciones y variables, docstrings,
mensajes al usuario, commits, PRs, comentarios. El código existente ya es así.

---

## Las tres reglas duras

### 1. Nunca mergear a `main`

Abrí el PR y detenete ahí. El merge lo hace Sergio, después de probarlo a mano
en su máquina. CI verde **no** es autorización para mergear.

Todo PR incluye:

```markdown
## Cómo probarlo a mano
1. <comando exacto o clic exacto>
2. <qué tenés que ver>
3. <qué NO debería pasar>

## Tests sintéticos agregados
- <archivo>::<test> — <qué comportamiento cubre>

## Paridad
- [ ] Salida idéntica a la del script original sobre los 192 .ab1
      (o, si cambia: qué cambió y por qué está bien)
```

### 2. Cada modificación viene con pruebas sintéticas

Sin excepción. Los datos de prueba se generan con `tests/sintetico/`, con semilla
fija. La suite corre **offline**: ningún test toca NCBI. Un test que necesita
internet está mal escrito.

### 3. Consultar antes de cambiar comportamiento observable

Describir el cambio, esperar el visto bueno, después editar. Victoria corre los
scripts en su máquina mientras se conversa: un cambio no consultado puede pisar
una versión en uso.

Los **originales** (la carpeta del proyecto en OneDrive, fuera de este repo) no
se tocan nunca desde acá: ni editar, ni mover, ni borrar. El repo trabaja sobre
copias.

---

## Flujo de trabajo

- **Una fase por PR**, en el orden del `BRIEFING.md` §9 (tabla de fases en el
  `README.md`). Antes de arrancar cada fase: resumir en tres líneas qué se va a
  hacer y esperar el OK.
- Ramas: `feat/<n>-descripcion`, `fix/<n>-descripcion`, `chore/<n>-descripcion`.
- `main` está protegida: nada de push directo ni force-push.

## Dónde está cada cosa

| Qué | Dónde | Por qué |
|---|---|---|
| Este repo | fuera de OneDrive (`%USERPROFILE%\repos\sanger-classifier`) | OneDrive pelea con los miles de archivos chicos de `.git` |
| Build del `.exe` | `C:\Sanger` (`scripts\construir_exe.ps1`) | Mismo motivo, con los temporales de PyInstaller |
| Preferencias de la ventana | `~/.sanger/config.json` | Tiene el mail de NCBI: nunca se versiona |
| Caché de BLAST de la ventana | `%LOCALAPPDATA%\Sanger\cache\<hash de la entrada>` | No es un resultado: es lo que permite retomar. No escribe en las carpetas de datos (OneDrive, discos de solo lectura) |
| Referencia de paridad | `C:\Sanger\paridad\` | Contiene resultados del ensayo: nunca al repo |
| Los 192 `.ab1` reales | carpeta del ensayo, fuera del repo | Datos sin publicar |

## Cómo verificar antes de abrir un PR

```bash
pip install -e ".[dev]"     # dentro de un .venv
ruff check
ruff format --check
pytest                      # corre con --disable-socket: sin red
```

Las tres tienen que dar OK localmente; el CI corre lo mismo en Ubuntu y Windows,
Python 3.11 y 3.12.

`sanger_gui.py` (la ventana original, sin tocar) está excluido de `ruff` hasta
que la fase 3 la reemplace. En `cli.py` se ignora el largo de línea porque los
textos de `--help` están copiados literal del original.

El CI además exige cobertura ≥ 80 % en `qc/`, `ensamblado/` y `clasificacion.py`.

## Goldens

`tests/golden/` tiene la salida esperada de la corrida sintética estándar (con
y sin BLAST, más la consola). Los de la fase 1 los generó el script original.
Si un golden deja de coincidir, el cambio está mal. Solo se regeneran a
propósito (`python scripts/generar_goldens.py`, a mano) cuando la salida tiene
que cambiar, y se explica en el PR. Ver `tests/golden/LEEME.md`.

## Paridad

Dos referencias en `C:\Sanger\paridad\`, las dos generadas con el script
original sobre los 192 `.ab1` (los detalles están en `LEEME_referencia.txt`):

- `referencia_original` (+ `.consola.txt`): con `--no-blast`.
- `referencia_blast_cache` (+ `.consola.txt`): con BLAST, respondido desde el
  caché sintético `cache_blast_sintetico\` (hits inventados que cubren las 7
  interpretaciones). Antes de correr, se copian esos `.hits.json` a
  `<salida>\blast_xml\`: así no se consulta a NCBI.

El comando exacto está en el `README.md`.

- `01` a `05`: idénticos byte a byte.
- `00_resumen.txt` y consola: idénticos salvo la línea "Tiempo total" (y en
  consola, "Listo. Resultados en …").
- Se compara con `python scripts/paridad.py REF NUEVA --consola REF.txt NUEVA.txt`.
- Correr con la **misma ruta** de `-i` que la referencia, capturando la consola
  con `cmd /c "... > archivo"` y `PYTHONIOENCODING=utf-8`: el `>` de
  PowerShell 5.1 la reescribe en UTF-16.

Si la paridad falla, el cambio está mal, **salvo** que se esté cambiando la
salida a propósito (como la fase 4): ahí se documenta qué cambió y por qué.

Desde la fase 4 hay dos referencias más, `referencia_fase4` y
`referencia_fase4_blast_cache`, que son contra las que se compara de ahora en
adelante. Las dos originales quedan como registro de cómo era la salida del
script antes de la modularización.

---

## Lo que NO se toca sin preguntar

Decisiones tomadas y validadas. No son accidentes.

- **El consenso se arma sobre lecturas crudas y se recorta después.** Si se
  recorta antes, en amplicones cortos se pierde el solapamiento. Ya se probó.
- **Umbrales CONFIABLE**: ≥100 pb tras recorte Q20, Q media ≥25, ≥80 % de bases
  Q≥20. El amplicón de este ensayo mide ~260 pb; por eso 100 y no 300.
- **El grupo se llama DUDOSA**, no CUESTIONADA. Victoria lo eligió el 10/09/2026.
- **Regla de género**: si las dos mejores especies empatan en identidad y son del
  mismo género (*Bos taurus* / *Bos indicus* con COI), se informa "identificado a
  nivel de género". No es ambigüedad real: el marcador no separa esas especies.
- **Formato CSV**: `;` como separador, BOM UTF-8, decimales con coma (su Excel
  está en español). Dentro de un campo nunca hay `;`: las listas internas usan
  ` | `. Existe `--separador coma` para pandas/R.
- **Orden de columnas**: identificación y BLAST primero; `motivo`,
  `coincide_con` y `archivos` al final.

---

## Arquitectura

`clasificar_sanger.py` en la raíz es solo un punto de entrada que llama a
`sanger.cli.main`, para que la línea de comandos histórica siga funcionando.

**Un solo escritor de informes**: `io/informes.py::escribir_informes`. Lo usan
el pipeline (línea de comandos) y la exportación de la ventana. Dos caminos de
escritura que tienen que producir lo mismo terminan divergiendo; hay un test que
los compara byte a byte.

**La ventana no escribe informes**: corre con `salida=None` y exporta a pedido.
El CLI no cambió: `-o` sigue siendo obligatorio y sigue escribiendo los cinco
archivos.

La ventana (`src/sanger_ui/`, desde la fase 3) es un cliente más del pipeline:
`worker.py` lo corre en un hilo y reenvía los avisos como señales de Qt. No
tiene lógica de análisis. Sus tests (`tests/test_ui.py`) corren en modo
"offscreen" y **se saltean en el CI**, que no instala PySide6; mirar la ventana
de verdad sigue siendo una prueba manual.

**Presets** (`config.py`): los valores salen de `README_clasificar_sanger.md`.
**Están pendientes de que Victoria los confirme**; hasta entonces, el que viene
elegido es "Default", que son los valores por defecto del pipeline. Si el
usuario edita un umbral, el combo muestra `(modificado)` en vez de cambiar de
preset: así se ve cuál eligió y que además tocó algo.

```
src/sanger/        CORE. No sabe que existe una UI.
  qc/ ensamblado/ clasificacion.py    ← funciones puras
  io/ blast/                          ← efectos
  pipeline.py                         ← el único que orquesta
  cli.py
src/sanger_ui/     PySide6. Depende del pipeline; el pipeline nunca de ella.
tests/
legacy/            congelado, no se toca
```

**Regla de imports, verificada por test:** `qc/`, `ensamblado/` y
`clasificacion.py` no importan nada de `io/`, `blast/` ni de la UI.

**En el core:** cero `print` (logging + callback de progreso), cero `sys.exit`
(excepciones de `errores.py`), `Parametros` es `frozen`.

Contrato (desde la fase 2):

```python
def ejecutar(params, progreso=..., cancelado=..., motor=None) -> Resultado
```

- `progreso` recibe un `Progreso(etapa, hechos, total, mensaje, fin)`. La línea
  de comandos imprime `mensaje` tal cual: por eso la consola sigue idéntica a la
  del script original. Un aviso sin texto es solo avance.
- `cancelado` se consulta entre lecturas, entre muestras y entre lotes de BLAST;
  si devuelve `True` se levanta `Cancelado` y no se escribe nada más.
- Los mensajes de `logging` no se muestran salvo que el programa que lo usa
  configure logging (el paquete instala un `NullHandler`). Si se configurara a
  mano, saldrían por la salida de error y la consola dejaría de ser idéntica.

---

## `legacy/`

`identificar_ingestas.py` produjo los resultados del informe ya emitido. Se
conserva por trazabilidad. **No se desarrolla, no se refactoriza, no se
"mejora".** Excluido de cobertura, linting y refactor.
`tests/test_legacy_congelado.py` verifica su SHA-256: si falla, se deshace el
cambio, no se actualiza el hash.

Su documentación (`README_ingestas.md`) y el informe
(`Informe_ingestas_COI_Sanger.md`) quedan **fuera del repo** porque contienen
resultados sin publicar.

---

## Nunca commitear

`*.ab1` · `*.exe` · `resultados/` · `blast_xml/` · `build/` · `dist/` ·
el mail de NCBI de nadie · cualquier dato del ensayo sin publicar (incluye
`Informe_ingestas_COI_Sanger.md`, `README_ingestas.md` y la referencia de
paridad).

Antes de cada push, revisar `git status` y `git diff --cached --stat`.

El repo es **público**. Si algo sensible se coló en un commit, avisá antes de
reescribir historia.

---

## Bugs conocidos — resueltos en la fase 4

Quedan acá anotados porque explican por qué el código es como es.

**BUG-1 (impacto científico). Corregido.** Si fallaban los 3 reintentos de un
lote, esas muestras quedaban con lista vacía y se informaban como `sin_hit`: un
fallo de red se veía idéntico a "no matcheó con nada en GenBank". Ahora un motor
devuelve `None` cuando no se pudo consultar, se informa como `ERROR_BLAST`, se
cuenta aparte en el resumen y **no se cachea**, así al relanzar se reintenta.
Auditoría de la corrida real: las dos muestras con `sin_hit` (MC38 y MC42) lo
eran de verdad —estaban en lotes donde el resto sí trajo resultados—, así que el
informe ya emitido no estaba afectado.

**BUG-2. No era un bug.** `NCBIWWW.email` sí funciona en la versión instalada de
Biopython: `qblast` arma el pedido leyendo esa variable del módulo. Se agregó
además `NCBIWWW.tool`, que NCBI también pide.

**BUG-3. Corregido.** El XML crudo se escribe con `encoding="utf-8"`; antes, en
Windows, se escribía en cp1252 y reventaba con títulos de GenBank fuera de esa
codificación. Los FASTA tenían el mismo problema y ahora salen siempre en UTF-8
con fin de línea LF, iguales en cualquier sistema.

**BUG-4. Corregido.** Los reintentos esperan 30, 60 y 120 segundos, con ±25 % de
variación para que varias corridas que fallan a la vez no vuelvan todas juntas.

**Pendiente, con decisión tomada:** la alerta de "posible mezcla" ahora aparece
aunque la secuencia elegida no sea el consenso (antes se perdía). El grupo no
cambia: lo que cambia es que queda dicho que hay que mirar el cromatograma.

---

## Estilo

Type hints en todo el core. Docstrings que expliquen **el porqué**, no el qué:
Victoria maneja los conceptos biológicos, no los de programación.
