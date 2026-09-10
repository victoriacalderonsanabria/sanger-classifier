# `legacy/` — congelado

Este script produjo los resultados del informe del ensayo de ingestas.
Se conserva por trazabilidad. **No se desarrolla, no se refactoriza, no se
"mejora".** Todo lo nuevo va en `src/sanger/`.

## Qué hay acá

- `identificar_ingestas.py`: copia byte a byte del script original, específico
  del ensayo de ingestas de mosquitos por COI. Es el antecesor de
  `clasificar_sanger.py`, que es el genérico y el que se sigue usando.

## Qué no está, y por qué

La documentación de este script (`README_ingestas.md`) y el informe de
resultados (`Informe_ingestas_COI_Sanger.md`) **no se suben a este repositorio**.
Contienen resultados del ensayo que todavía no están publicados (identificadores
de muestra, especies identificadas, conteos) y el repositorio es público. Los dos
se conservan fuera del repo, en la carpeta de trabajo del proyecto.

## Cómo se garantiza que no cambie

- `tests/test_legacy_congelado.py` compara la huella SHA-256 del archivo con la
  del original. Cualquier modificación, aunque sea un espacio, hace fallar el CI.
  Si ese test falla, no se actualiza la huella: se deshace el cambio.
- `.gitattributes` fija los finales de línea en LF, así el archivo queda
  idéntico también cuando se descarga en Windows.
- Está excluido de `ruff` y de la medición de cobertura.
