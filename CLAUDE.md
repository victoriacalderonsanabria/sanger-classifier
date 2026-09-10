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
| Build del `.exe` | `C:\Sanger` | Mismo motivo, con los temporales de PyInstaller |
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

En la fase 0, `clasificar_sanger.py` y `sanger_gui.py` están excluidos de
`ruff` porque todavía son los originales sin tocar. En la fase 1 salen de la
exclusión (ver `pyproject.toml`).

## Paridad

La referencia está en `C:\Sanger\paridad\referencia_original` (+ `.consola.txt`),
generada con el script original sobre los 192 `.ab1` con `--no-blast`. Los
detalles están en `C:\Sanger\paridad\LEEME_referencia.txt`, y el comando exacto
en el `README.md`.

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

Objetivo a partir de la fase 1. En la fase 0 el código son todavía los scripts
originales de la raíz.

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

Contrato:

```python
def ejecutar(params, progreso=..., cancelado=...) -> Resultado
```

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
