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

Si la paridad falla en las fases 1 a 3, el cambio está mal. En la fase 4 va a
fallar a propósito: se documenta qué cambió y por qué.

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
  `vs_confiables` y `archivos` al final.

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

**Sin presets por ahora.** La ventana tuvo un combo de presets por marcador
(COI Folmer, 16S bacteriano, ITS hongos); Victoria decidió sacarlo el
12/09/2026 hasta definirlo con más calma. La ventana arranca con los valores por
defecto del pipeline, que son los validados con el ensayo de ingestas. Si se
repone, está en el historial de git (PR #4 y #5).

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

## Bugs conocidos — no arreglar en silencio

Van todos a la fase 4, con PR propio.

**BUG-1 (impacto científico).** Si los 3 reintentos de un lote de BLAST fallan,
se marca `resultados[n] = []`, que `interpretar()` traduce a `"sin_hit"`. Un
fallo de red se ve idéntico a "no matcheó con nada en GenBank".

**BUG-2.** `NCBIWWW.email = args.email` probablemente no hace nada.

**BUG-3.** `write_text(xml_txt)` sin `encoding=` → cp1252 en Windows.

**BUG-4.** Reintentos con `sleep(30)` fijo, sin backoff.

---

## Estilo

Type hints en todo el core. Docstrings que expliquen **el porqué**, no el qué:
Victoria maneja los conceptos biológicos, no los de programación.
