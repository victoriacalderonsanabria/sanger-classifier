# sanger-classifier

Herramientas para identificar especies a partir de cromatogramas Sanger (`.ab1`)
por BLAST. Sirve para cualquier marcador (COI, 16S, ITS, cytb…) y cualquier
organismo.

El pipeline lee una carpeta de `.ab1`, recorta cada lectura por calidad
(algoritmo de Mott), arma un consenso forward + reverse cuando puede y deja cada
muestra en uno de tres grupos:

| Grupo | Qué significa |
|---|---|
| **CONFIABLE** | Cumple el criterio estándar. BLAST (megablast); el resultado se reporta. |
| **DUDOSA** | Hay señal pero no alcanza. Recorte laxo, BLAST sensible, marcada para revisión manual. |
| **RECHAZADA** | Sin señal utilizable. |

Está validado sobre 192 cromatogramas reales (96 muestras).

## Estado

**En modularización.** Hoy el código es el script original, copiado sin
cambios: `clasificar_sanger.py` (línea de comandos) y `sanger_gui.py` (ventana).
El plan lo convierte en un paquete Python con tests y una interfaz nueva, sin
cambiar ningún resultado:

| Fase | Qué | Cambia la salida |
|---|---|---|
| 0 | Repositorio, CI, tests de caracterización, referencia de paridad | No |
| 1 | Partir el script en módulos (`src/sanger/`) + suite sintética | No |
| 2 | Pipeline con progreso y cancelación, sin `print` ni `sys.exit` | No |
| 3 | Ventana nueva en PySide6 con tabla de resultados | No |
| 4 | Corrección de errores conocidos del BLAST | **Sí**, documentado |
| 5 | Vista web con Streamlit (opcional) | No |

## Uso (hoy)

```bash
pip install biopython

# solo control de calidad y clasificación (instantáneo; correrlo primero)
python clasificar_sanger.py -i carpeta_ab1 -o resultados --no-blast

# con BLAST remoto (NCBI pide un e-mail)
python clasificar_sanger.py -i carpeta_ab1 -o resultados --email tu@mail.com
```

- [`README_clasificar_sanger.md`](README_clasificar_sanger.md): documentación
  completa: opciones, criterios, qué significa cada columna de la salida.
- [`INSTRUCCIONES_exe.md`](INSTRUCCIONES_exe.md): cómo construir y usar el
  ejecutable de Windows.

## Desarrollo

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -e ".[dev]"

pytest                          # tests; corren sin internet
ruff check                      # errores y estilo
ruff format --check             # formato
```

Reglas de trabajo para quien contribuya (personas o agentes): ver
[`CLAUDE.md`](CLAUDE.md).

### Paridad: cómo se verifica que la ciencia no cambió

Antes de tocar el código se corrió el script original sobre los 192 `.ab1`
reales y se guardó la salida **fuera del repo** (contiene resultados del ensayo).
Después de cada fase se corre la versión nueva sobre los mismos archivos y se
compara:

```powershell
# PowerShell, desde la raíz del repo, con el .venv activado
$env:PYTHONIOENCODING = "utf-8"
$ab1 = "<ruta absoluta a la carpeta de los 192 .ab1>"   # la MISMA que en la referencia
cmd /c "python clasificar_sanger.py -i `"$ab1`" -o C:\Sanger\paridad\nueva --no-blast > C:\Sanger\paridad\nueva.consola.txt 2>&1"
python scripts\paridad.py C:\Sanger\paridad\referencia_original C:\Sanger\paridad\nueva `
    --consola C:\Sanger\paridad\referencia_original.consola.txt C:\Sanger\paridad\nueva.consola.txt
```

Los informes `01` a `05` tienen que salir idénticos byte a byte; `00_resumen.txt`
y la consola, idénticos salvo la línea del tiempo de ejecución.

Dos detalles que parecen caprichosos pero no lo son:

- **`cmd /c "... > archivo"`** y no `> archivo` directo en PowerShell: Windows
  PowerShell 5.1 reescribe en UTF-16 lo que redirige, y la consola dejaría de
  coincidir aunque el resultado fuera el mismo.
- **La misma ruta de `.ab1`**: la primera línea de la consola la incluye
  ("Encontré 192 cromatogramas en …").

`C:\Sanger\paridad\LEEME_referencia.txt` dice con qué versión de Python y
Biopython se generó la referencia.

## Qué nunca entra a este repositorio

Es público. No se suben: cromatogramas (`*.ab1`), ejecutables (`*.exe`),
carpetas de resultados, el caché de BLAST (`blast_xml/`), el mail de NCBI de
nadie ni ningún dato del ensayo sin publicar. El `.gitignore` lo cubre desde el
primer commit.

## Licencia

MIT. Ver [`LICENSE`](LICENSE).
