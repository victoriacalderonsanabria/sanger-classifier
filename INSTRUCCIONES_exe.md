# Clasificador de secuencias Sanger — versión con ventana (.exe)

## Para quien construye el ejecutable

1. Tener Python 3.11 o más nuevo en Windows (python.org, marcando
   **"Add Python to PATH"**).
2. Tener una copia **completa** del repositorio **fuera de OneDrive** (por
   ejemplo `C:\Sanger\repo`). PyInstaller crea miles de archivos temporales y la
   sincronización de OneDrive los pelea; el script avisa si detecta eso.
3. Desde esa copia, en PowerShell:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\construir_exe.ps1
   ```

   Instala lo que falte (Biopython, PySide6, PyInstaller) y arma el ejecutable
   (1–3 minutos). Al terminar queda en `C:\Sanger\dist\ClasificadorSanger.exe`
   (unos 60 MB). Con `-Destino` se puede elegir otra carpeta.
4. Compartir **solo** ese `.exe`. En la máquina de destino no hace falta nada:
   ni Python, ni Biopython, ni PySide6.

Las opciones de la construcción están versionadas en `scripts\sanger.spec`, así
que se revisan como cualquier otro cambio. Cada vez que se modifique el
programa hay que volver a construir y redistribuir el `.exe`.

**Si Windows o el antivirus bloquean el .exe**: es habitual con programas hechos
con PyInstaller que no están firmados. En SmartScreen: "Más información" →
"Ejecutar de todas formas". Si el antivirus lo pone en cuarentena, hay que
agregar una excepción para el archivo. No es un virus; es Python empaquetado.

## Para quien lo usa

Doble clic en `ClasificadorSanger.exe` (la primera vez tarda unos segundos en
abrir). La ventana tiene tres pestañas.

### 1. Configuración

1. **Carpeta con los .ab1**: donde están los cromatogramas. No hace falta elegir
   carpeta de resultados: el programa **no escribe nada** mientras corre, y al
   final se exporta lo que se quiera guardar (ver más abajo).
2. **E-mail**: cualquiera propio. NCBI lo pide para el BLAST remoto. Queda
   guardado para la próxima vez, en tu computadora (`~/.sanger/config.json`).
3. **Preset**: carga de una los umbrales típicos de un marcador (COI Folmer,
   16S bacteriano, ITS de hongos). **Default** son los valores por defecto del
   pipeline, los validados con el ensayo de ingestas. Después de elegir uno se
   puede seguir ajustando a mano: si algún valor deja de ser el del preset, el
   combo lo avisa con `(modificado)`.
4. **Base de datos**: dejar `nt` salvo indicación contraria. Para marcadores
   mitocondriales (COI, cytb) `mito` es bastante más rápida.
5. **Restringir a**: opcional. `Vertebrata[Organism]` si se buscan hospedadores
   vertebrados; `(sin filtro)` si no se sabe qué esperar.
6. **Solo control de calidad**: una primera pasada instantánea, sin BLAST, para
   ver cómo quedan los grupos. Después se desmarca y se corre con BLAST.
7. **Caché de BLAST**: lo que ya se le preguntó a NCBI queda guardado, así una
   corrida cortada se retoma sin volver a esperar. Se guarda aparte de los datos
   (en la carpeta del sistema, no en la carpeta de los `.ab1`). La ventana
   muestra cuánto ocupa y tiene un botón para borrarlo; borrarlo no pierde
   resultados, solo hace que la próxima corrida vuelva a consultar.

### 2. Progreso

Muestra la barra de avance, en qué está trabajando y el registro completo.

- Con BLAST puede tardar varios minutos. Esa espera es la **cola de NCBI**, no
  la computadora: mientras dice "BLAST", está esperando la respuesta.
- **Cancelar** corta de verdad. Lo ya calculado queda en la carpeta de
  resultados, y al volver a correr sobre esa misma carpeta el BLAST retoma donde
  había quedado en vez de repetirlo.

### 3. Resultados

Una fila por muestra, con el color del grupo: verde CONFIABLE, amarillo DUDOSA,
gris RECHAZADA.

- Se puede **ordenar** por cualquier columna (clic en el título) y **filtrar**
  escribiendo (muestra, especie, interpretación…) o eligiendo un grupo.
- **Doble clic sobre un accession** abre ese registro en NCBI.
- Pasando el mouse sobre una fila DUDOSA se ve por qué quedó así.

### Guardar los resultados: "Exportar…"

Los archivos se escriben **cuando vos querés**, no en cada corrida. El botón
**Exportar…** pregunta dónde guardar y qué guardar (vienen todos marcados):

- `04_resultados.csv` — los resultados por muestra, lo principal
- `01_QC_lecturas.csv` — el control de calidad de cada cromatograma
- `02_confiables.fasta` / `03_dudosas.fasta` — las secuencias
- `05_hits_completos.json` — los hits completos de BLAST
- `00_resumen.txt` — el resumen de la corrida

Son exactamente los mismos archivos que genera la versión de línea de comandos.
Si cerrás la ventana (o arrancás otra corrida) con resultados sin exportar, el
programa avisa antes de perderlos.

Qué significa cada grupo y cada columna: ver `README_clasificar_sanger.md`.
