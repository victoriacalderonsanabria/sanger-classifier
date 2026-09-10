# Clasificador de secuencias Sanger — versión con ventana (.exe)

## Para quien construye el ejecutable (una sola vez)

1. Tener Python 3 instalado en Windows (python.org, marcando **"Add Python to PATH"**).
2. Poner en una misma carpeta estos tres archivos:
   `clasificar_sanger.py`, `sanger_gui.py`, `construir_exe.bat`.
3. Doble clic en `construir_exe.bat`. Instala Biopython y PyInstaller y arma el
   ejecutable (1–3 minutos). Al terminar queda en `dist\ClasificadorSanger.exe`
   (unos 40–60 MB).
4. Compartir **solo** `ClasificadorSanger.exe`. No hace falta nada más en la
   máquina de destino: ni Python, ni Biopython.

Cada vez que se modifique `clasificar_sanger.py`, hay que volver a correr
`construir_exe.bat` y redistribuir el `.exe`.

**Si Windows o el antivirus bloquean el .exe**: es habitual con programas hechos
con PyInstaller que no están firmados. En SmartScreen: "Más información" →
"Ejecutar de todas formas". Si el antivirus lo pone en cuarentena, hay que
agregar una excepción para el archivo. No es un virus; es Python empaquetado.

## Para quien lo usa

1. Doble clic en `ClasificadorSanger.exe` (la primera vez tarda unos segundos en abrir).
2. **Carpeta con los .ab1**: elegir la carpeta donde están los cromatogramas.
   La carpeta de resultados se propone sola (`resultados` dentro de la misma);
   se puede cambiar.
3. **E-mail**: cualquiera propio. NCBI lo pide para el BLAST remoto; no manda nada.
4. **Base de datos**: dejar `nt` salvo indicación contraria. Para acelerar
   con marcadores mitocondriales (COI, cytb) se puede usar `mito`.
5. **Restringir a**: opcional. `Vertebrata[Organism]` si se buscan hospedadores
   vertebrados; `(sin filtro)` si no se sabe qué esperar.
6. **Umbrales**: los valores por defecto sirven para amplicones de 200–400 pb.
   Para COI Folmer (~650 pb) o 16S completo, subir "Largo mínimo CONFIABLE"
   a 300–400. Para 16S bacteriano, poner 98.7 en identidad.
7. Marcar **"Solo control de calidad"** para una primera pasada instantánea sin
   BLAST y ver cómo quedan los grupos; después desmarcar y correr con BLAST.
8. **Analizar**. El progreso se ve en la ventana. Con BLAST puede tardar varios
   minutos (es la cola de NCBI, no la computadora). Si se cierra la ventana a
   mitad, al volver a correr sobre la misma carpeta de resultados retoma donde
   quedó.
9. Al terminar, **"Abrir carpeta de resultados"**. Lo importante está en
   `04_resultados.csv` (una fila por muestra, con grupo CONFIABLE /
   DUDOSA / RECHAZADA, especie, identidad e interpretación) y en
   `00_resumen.txt`.

Qué significa cada grupo y cada columna: ver `README_clasificar_sanger.md`.
