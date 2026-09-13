# clasificar_sanger.py — QC, consenso y BLAST de cromatogramas Sanger

Script genérico: sirve para cualquier marcador (COI, 16S, ITS, cytb, 18S…) y
cualquier organismo. Toma una carpeta de `.ab1` y deja cada muestra en uno de
tres grupos, con la secuencia y el resultado de BLAST cuando corresponde.

| Grupo | Qué significa | Qué hace el script |
|---|---|---|
| **CONFIABLE** | La secuencia (consenso F+R o mejor lectura) cumple el criterio estándar: ≥ 100 pb tras recorte Q20, Q media ≥ 25, ≥ 80 % de bases con Q ≥ 20. | BLAST (megablast). El resultado se reporta directamente. |
| **DUDOSA** | Hay señal real pero no alcanza el estándar. | Arma la mejor secuencia posible con recorte laxo (Q15), la compara con las confiables de la misma corrida y hace BLAST con el algoritmo sensible (blastn). El resultado sale marcado para revisión manual, con el motivo. |
| **RECHAZADA** | Sin señal utilizable (menos de 150 bases, menos de 30 con Q ≥ 20, o ni con recorte laxo se llega a 60 pb). | Nada. No vale la pena mirarla; si la muestra importa, repetir PCR. |

## Instalación

```bash
pip install biopython          # o: conda install -c conda-forge biopython
```

## Uso

```bash
# solo QC y clasificación (instantáneo; correrlo primero)
python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --no-blast

# con BLAST remoto (NCBI pide un e-mail)
python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --email tu@mail.com

# restringiendo el BLAST a un grupo taxonómico (más rápido y menos ruido)
python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --email tu@mail.com --taxon "Vertebrata[Organism]"
python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --email tu@mail.com --taxon "Fungi[Organism]"
python3 clasificar_sanger.py -i carpeta_ab1 -o resultados --email tu@mail.com --taxon "Bacteria[Organism]"
```

Si el script se corta a mitad del BLAST, se relanza igual: los resultados ya
obtenidos (`blast_xml/<muestra>.hits.json`) se reutilizan y solo se envían las
que faltan.

## Cómo hacer más rápido el BLAST

El tiempo del BLAST remoto es casi todo espera en la cola de NCBI, no cómputo.
Tres palancas, de mayor a menor efecto:

1. **Envío en lote (ya activado).** El script manda hasta 50 secuencias en un
   solo envío (`--lote`), así que se espera la cola una vez por lote y no una
   vez por secuencia. Para 60 muestras: unos pocos minutos en vez de una hora.
   Si NCBI devuelve error por tamaño, bajá a `--lote 20`.
2. **Base de datos chica y específica (`--db`).** `nt` tiene todo y es la más
   lenta. NCBI ofrece bases pequeñas por marcador, mucho más rápidas y con
   menos ruido:
   * `mito` — genomas mitocondriales RefSeq (COI, cytb, 12S/16S mitocondrial,
     control region). Ideal para identificar vertebrados e insectos.
   * `16S_ribosomal_RNA` — 16S de bacterias y arqueas (secuencias curadas).
   * `ITS_RefSeq_Fungi` e `ITS_eukaryote_sequences` — ITS de hongos / eucariotas.
   * `18S_fungal_sequences`, `28S_fungal_sequences`.
   * `core_nt` — como `nt` pero sin secuencias redundantes; algo más rápida.
   Ojo: una base específica solo encuentra lo que contiene. `mito` tiene un
   genoma por especie, no todas las variantes poblacionales, así que las
   identidades pueden ser 0,5–1 punto más bajas que contra `nt`; para el corte
   del 97 % no cambia nada.
3. **Filtro taxonómico (`--taxon`).** Reduce el espacio de búsqueda dentro de
   la base. Combinable con la anterior: `--db mito --taxon "Vertebrata[Organism]"`.

Ejemplos:

```bash
# ingestas / identificación de vertebrados por COI, cytb o 16S mitocondrial
python3 clasificar_sanger.py -i ab1 -o res --email ... --db mito --taxon "Vertebrata[Organism]"

# 16S bacteriano
python3 clasificar_sanger.py -i ab1 -o res --email ... --db 16S_ribosomal_RNA --ident-min 98.7

# ITS de hongos
python3 clasificar_sanger.py -i ab1 -o res --email ... --db ITS_RefSeq_Fungi
```

Y la opción definitiva si vas a correr esto muchas veces: **BLAST local**.
Esas mismas bases chicas se descargan de NCBI con `update_blastdb.pl` (viene
con BLAST+) y ocupan poco:

```bash
sudo apt install ncbi-blast+
mkdir -p ~/blastdb && cd ~/blastdb
update_blastdb.pl --decompress mito              # ~100 MB
update_blastdb.pl --decompress 16S_ribosomal_RNA # ~30 MB
python3 clasificar_sanger.py -i ab1 -o res --blast-local ~/blastdb/mito
```

Con base local, 100 secuencias tardan segundos y no dependés de internet ni
de la cola de NCBI.

### Opciones

| Opción | Default | Qué controla |
|---|---|---|
| `--largo-min` | 100 | Largo mínimo para CONFIABLE. Para amplicones largos (COI Folmer ~650, 16S ~1400) conviene subirlo a 300–400. |
| `--q-media-min` | 25 | Q media mínima para CONFIABLE. |
| `--pct-q20-min` | 80 | % mínimo de bases Q ≥ 20 para CONFIABLE. |
| `--umbral-q` | 20 | Q del recorte estricto (Mott). |
| `--umbral-q-laxo` | 15 | Q del recorte laxo, usado para DUDOSAS. |
| `--largo-min-laxo` | 60 | Largo mínimo (con recorte laxo) para entrar en DUDOSA en vez de RECHAZADA. Bajalo a 50 si querés mirar más casos límite. |
| `--min-bases-q20` | 30 | Bases con Q ≥ 20 que necesita una lectura para no ser considerada sin señal. |
| `--min-solap` | 50 | Solapamiento mínimo F/R para armar consenso. |
| `--taxon` | – | Filtro Entrez para BLAST remoto, p. ej. `"Vertebrata[Organism]"`. |
| `--ident-min` | 97 | Identidad mínima para marcar `identificado`. Para 16S bacteriano se usa 98.7–99; para ITS de hongos 97–98. |
| `--cob-min` | 80 | Cobertura mínima del hit sobre la secuencia. |
| `--blast-local RUTA_DB` | – | Usar `blastn` local contra una base propia (`makeblastdb`). |
| `--primers-f` / `--primers-r` | – | Tokens extra para reconocer F/R en el nombre del archivo. |
| `--separador` | `punto_y_coma` | Formato de los CSV. `punto_y_coma`: pensado para Excel en español — abre en columnas con doble clic, decimales con coma y acentos correctos. `coma`: estándar internacional, para leerlo con pandas o R. |

### Nombres de archivo

Muestra y sentido se leen del nombre. Se reconocen `F`, `R`, `FWD`, `REV` y
los primers habituales (LCO1490/HCO2198, VF1/VR1, 27F/1492R, 515F/806R,
ITS1/ITS4, ITS5/ITS2, M13F/M13R, T7/T3/SP6, NS1/NS8) separados por `_`, `-`,
espacio o punto: `M12_F.ab1`, `M12-R.ab1`, `Cepa3_27F_A01.ab1`, `H7-ITS4.ab1`.
Un archivo sin token reconocible se toma como muestra única de sentido `?`
(se procesa igual, sin consenso). Para otros primers: `--primers-f MiF --primers-r MiR`.

## Formato de los CSV

Por defecto los CSV salen con **punto y coma** como separador de columnas, marca
de codificación UTF-8 y **decimales con coma** (`99,38`). Es lo que espera Excel
en español: hacés doble clic y se abre en columnas, con los acentos bien y con
los números tratados como números (ordenables y filtrables).

Ningún campo contiene punto y coma: las listas dentro de una celda (archivos de
una muestra, motivos por los que una muestra quedó dudosa) se separan con ` | `.
Eso evita que el archivo se rompa si alguien lo vuelve a separar por columnas a
mano.

Si vas a leer los resultados con pandas, R u otra herramienta, usá
`--separador coma` para obtener el formato internacional (coma como separador,
punto como decimal, sin BOM).

## Qué devuelve

| Archivo | Contenido |
|---|---|
| `00_resumen.txt` | Conteos por grupo y por resultado de BLAST, y tiempo de ejecución (total, BLAST, resto). |
| `01_QC_lecturas.csv` | Una fila por cromatograma: largo crudo, Q media cruda, bases ambiguas, bases con Q ≥ 20, largo tras recorte estricto y laxo, y `senal` (BUENA / PARCIAL / SIN_SEÑAL). Es la tabla que justifica cada rechazo. |
| `02_confiables.fasta` | Secuencias del grupo CONFIABLE, orientadas como forward. |
| `03_dudosas.fasta` | Secuencias del grupo DUDOSA, con el motivo en la descripción, listas para revisar o pegar en BLAST web. |
| `04_resultados.csv` | **Una fila por muestra**, ordenadas CONFIABLE → DUDOSA → RECHAZADA. Columnas, en orden: identificación de la muestra (grupo, origen `CONSENSO_F+R` / `SOLO_F` / `SOLO_R`, largo, Q media, % Q20, solapamiento, discrepancias y conflictos F/R), resultado de BLAST (mejor hit con especie, identidad, cobertura, e-value y accession, más dos hits alternativos, e `interpretacion`) y al final los textos explicativos: `motivo` (por qué la muestra no llegó a CONFIABLE), `coincide_con` (ver abajo) y `archivos`. |
| `05_hits_completos.json` | Títulos completos de GenBank de cada hit. |
| `blast_xml/` | Respuestas crudas de BLAST (permiten reanudar). |

### La columna `coincide_con`

Es una **segunda opinión, independiente de BLAST**, que solo se calcula para las
DUDOSAS. La idea: si una muestra dudosa es en realidad la misma secuencia que
otra muestra que sí salió CONFIABLE, eso respalda su identificación aunque la
calidad sea baja.

Cómo se obtiene: se toma la lectura **cruda** de la dudosa (sin recortar) y se
alinea contra todas las secuencias CONFIABLES de la misma corrida. En cada
posición se mira si la base coincide y, sobre todo, **qué calidad tenía esa
base**. Los desajustes se separan en dos grupos: los que caen sobre bases de
buena calidad (Q ≥ 20) y los que caen sobre bases malas.

Los tres resultados posibles:

* `coincide con <muestra> (100.0% en 78 bases buenas)` — coincide con esa
  muestra confiable en el 100 % de sus 78 bases de buena calidad, y todos los
  desajustes restantes están en bases malas. Es decir: **es la misma secuencia,
  leída con ruido**. Podés asignarle la especie de esa muestra confiable. Cuantas
  más "bases buenas", más sólida la comparación (con menos de 40 no se informa).
* `distinta de las confiables (mejor: 191, 90.4%)` — ni siquiera en sus bases
  buenas se parece a nada de la corrida: es otra cosa, y ahí manda lo que diga
  BLAST.
* `sin_coincidencia_util` — hay tan pocas bases de buena calidad que la
  comparación no significa nada.

Por qué sirve: cuando BLAST y esta columna **coinciden**, tenés dos evidencias
independientes y podés reportar la muestra con confianza pese a la baja calidad.
Cuando **no coinciden**, sabés exactamente dónde mirar el cromatograma.
Si hay desajustes también en bases buenas, dice `distinta de las confiables`:
es otra cosa (o mezcla), y el BLAST sensible es el que manda.

### La columna `interpretacion`

* `identificado` — identidad ≥ `--ident-min`, cobertura ≥ `--cob-min`, sin otra especie a menos de 1 punto.
* `identificado a nivel de género (X / Y)` — dos especies del **mismo género** empatan en identidad. No es una ambigüedad real: el marcador no las separa (caso típico: *Bos taurus* / *Bos indicus* con COI). Se reporta el género con seguridad y la especie según el contexto.
* `ambiguo` — dos especies de **géneros distintos** con identidad casi igual: mirar distribución geográfica / contexto, o secuenciar más largo.
* `identidad_baja` — la especie no está en la base, o la secuencia tiene errores. En DUDOSAS es lo esperable.
* `cobertura_baja` — el hit cubre solo parte de la secuencia: posible quimera o secuencia con un tramo de basura.
* `humano` — verificar si es esperado o contaminación.
* `sin_hit` — se consultó y no hay nada parecido en la base: artefacto de PCR o secuencia de muy baja calidad.
* `ERROR_BLAST` — **no se pudo consultar** (se cayó la red, NCBI no respondió, falló `blastn`). No dice nada sobre la muestra: esa consulta no se hizo. No queda guardada en el caché, así que al relanzar sobre la misma carpeta de resultados se reintenta sola. Aparece contada aparte en `00_resumen.txt`.

## Cómo usar los tres grupos en un informe

Las CONFIABLES son el resultado. Las DUDOSAS se revisan una por una
(cromatograma + `coincide_con` + BLAST) y las que se acepten se reportan en
una categoría aparte, "identificación tentativa", indicando largo y calidad.
Las RECHAZADAS se cuentan como "sin amplificación / sin señal". Nunca se
mezclan los tres grupos en la misma tabla sin etiqueta.

## Criterios, en una frase cada uno

* **Recorte de Mott**: se queda con el tramo continuo de mejor calidad; tolera una base dudosa aislada pero corta en rachas malas. Q20 = 1 % de error por base.
* **Q media ≥ 25 y ≥ 80 % de bases Q20**: la media garantiza pocos errores en conjunto; el porcentaje evita que un bloque de bases pésimas se esconda detrás de bases excelentes.
* **Consenso sobre lecturas crudas**: se alinean F y R completas y se elige base a base la de mayor calidad; recién después se recorta. Recortar antes destruye el solapamiento cuando una lectura arranca mal.
* **Consenso con prioridad**: si consenso y lectura individual cumplen el estándar, se elige el consenso salvo que sea > 10 % más corto.
* **Conflictos F/R**: discrepancias donde ambas lecturas tenían buena calidad. Tres o más = posible mezcla de plantillas (picos dobles). La alerta aparece en `motivo` aunque al final se use una sola lectura: si hay mezcla, conviene mirar el cromatograma igual.
