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

**En modularización (fase 2 lista).** El programa vive en el paquete
`src/sanger/`. `clasificar_sanger.py` quedó en la raíz como punto de entrada,
así que se usa exactamente igual que antes, y la ventana actual
(`sanger_gui.py`) sigue funcionando. Los resultados son idénticos a los del
script original.

| Fase | Qué | Cambia la salida |
|---|---|---|
| 0 | Repositorio, CI, tests de caracterización, referencia de paridad | No |
| 1 | ✅ Partir el script en módulos (`src/sanger/`) + suite sintética | No |
| 2 | ✅ Pipeline con progreso y cancelación, sin `print` ni `sys.exit` | No |
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

En Windows, `activate` puede fallar con "la ejecución de scripts está
deshabilitada en este sistema". No hace falta activar nada: se llama al Python
del entorno directamente, que es exactamente lo mismo.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\python.exe clasificar_sanger.py -i carpeta_ab1 -o resultados --no-blast
```

(La otra opción es habilitar los scripts para tu usuario con
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, pero eso ya es una
decisión sobre la configuración de tu Windows.)

Reglas de trabajo para quien contribuya (personas o agentes): ver
[`CLAUDE.md`](CLAUDE.md).

### Estructura

```
src/sanger/
  config.py          Parametros: todos los umbrales de una corrida (inmutable)
  modelos.py         Lectura, Muestra, Hit, Resultado, Grupo
  qc/                recorte de Mott y métricas de calidad        ┐
  ensamblado/        consenso F+R y comparación entre muestras    ├ funciones puras
  clasificacion.py   qué secuencia representa a cada muestra      ┘
  io/                lectura de .ab1, nombres de archivo, informes
  blast/             NCBI remoto, blastn local, motor falso para tests, interpretación
  pipeline.py        el único que orquesta los pasos
  cli.py             la línea de comandos
clasificar_sanger.py punto de entrada histórico (llama a sanger.cli)
tests/
  sintetico/         generador de lecturas por perfil, escritor de .ab1, corrida estándar
  fixtures/blast/    respuestas de BLAST preparadas
  golden/            salida esperada de la corrida estándar (ver su LEEME.md)
```

Los módulos marcados como funciones puras no leen archivos ni hablan con BLAST;
un test (`tests/test_arquitectura.py`) lo verifica leyendo sus `import`.

### Cómo se usa desde otro programa

El núcleo no imprime ni corta el proceso: avisa del avance y levanta
excepciones. Eso es lo que permite que la ventana muestre una barra de progreso
y tenga un botón de cancelar.

```python
from sanger.config import Parametros
from sanger.errores import Cancelado, SangerError
from sanger.pipeline import ejecutar


def mostrar(p):  # p.etapa, p.hechos, p.total, p.mensaje
    print(f"[{p.etapa}] {p.hechos}/{p.total} {p.mensaje}")


try:
    resultado = ejecutar(
        Parametros(entrada="carpeta_ab1", salida="resultados", no_blast=True),
        progreso=mostrar,
        cancelado=lambda: False,  # True para cortar la corrida
    )
except Cancelado:
    ...  # lo cancelaron: no es una falla
except SangerError as e:
    print(e)  # error previsto, con mensaje para mostrar
```

Los dos callbacks son opcionales. `cancelado` se consulta entre lecturas, entre
muestras y entre lotes de BLAST; al cancelar queda en la carpeta de salida lo
que ya estaba escrito (sirve para relanzar) y no se escribe nada más.

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

El camino **con BLAST** se verifica igual, sin consultar a NCBI: se copia a la
carpeta de salida un caché con respuestas inventadas para las 96 muestras, y el
programa lo reutiliza en vez de enviar las secuencias.

```powershell
New-Item -ItemType Directory -Force C:\Sanger\paridad\nueva_blast\blast_xml | Out-Null
Copy-Item C:\Sanger\paridad\cache_blast_sintetico\*.hits.json C:\Sanger\paridad\nueva_blast\blast_xml\
cmd /c "python clasificar_sanger.py -i `"$ab1`" -o C:\Sanger\paridad\nueva_blast > C:\Sanger\paridad\nueva_blast.consola.txt 2>&1"
python scripts\paridad.py C:\Sanger\paridad\referencia_blast_cache C:\Sanger\paridad\nueva_blast `
    --consola C:\Sanger\paridad\referencia_blast_cache.consola.txt C:\Sanger\paridad\nueva_blast.consola.txt
```

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
