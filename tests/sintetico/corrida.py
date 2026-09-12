"""
Una corrida sintética completa: una carpeta de .ab1 que cubre todos los casos.

La usan los tests golden (tests/golden/) y scripts/generar_goldens.py. Si se
cambia algo acá, los goldens dejan de coincidir: hay que regenerarlos a
propósito y explicarlo en el PR.

Muestras (A, B y C son tres "especies", o sea tres secuencias verdad distintas):

  S01  F+R BUENA, especie A, solapan 200        → CONFIABLE por consenso
  S02  F PARCIAL + R BUENA, especie A           → CONFIABLE por consenso
  S03  solo F BUENA, especie B                  → CONFIABLE, SOLO_F
  S04  F SIN_SENAL + R BUENA, especie B         → CONFIABLE, SOLO_R
  S05  F+R PARCIAL, especie A                   → DUDOSA; coincide con una confiable
  S06  solo F PARCIAL, especie B                → DUDOSA; coincide con una confiable
  S07  F+R SIN_SENAL                            → RECHAZADA (sin señal)
  S08  F+R CORTA                                → RECHAZADA (cromatogramas cortos)
  S09  F MEZCLA + R BUENA, especie A            → conflictos F/R (ver test_clasificacion)
  S10  solo F AMBIGUA, especie C                → DUDOSA con bases ambiguas; coincide con S13
  S11  señal pero ni el recorte laxo llega a 60 → RECHAZADA
  S12  nombre sin F/R ("S12.ab1"), especie B    → CONFIABLE, SOLO_?
  S13  F corrupto + R BUENA, especie C          → el archivo roto no frena la corrida
  S14  R BUENA en una subcarpeta, especie A     → se buscan .ab1 en subcarpetas
  S15  F+R BUENA que solapan solo 30            → sin consenso, gana la lectura más larga
  S16  primers LCO1490/HCO2198, especie C       → sentido por nombre de primer
"""

import json
from pathlib import Path

from tests.sintetico.ab1_writer import escribir_ab1
from tests.sintetico.generador import Perfil, leer, par_fr, reverso_complemento, verdad

A, B, C = verdad(260, 1), verdad(260, 2), verdad(260, 3)
LARGA = verdad(400, 4)

# Qué respuesta de BLAST (tests/fixtures/blast/*.json) le toca a cada muestra
# en la variante con BLAST. Todas tienen una, así nunca se consulta a NCBI.
FIXTURE_POR_MUESTRA = {
    "S01": "hit_claro",
    "S02": "genero_empatado",
    "S03": "generos_distintos",
    "S04": "cobertura_baja",
    "S05": "identidad_baja",
    "S06": "humano",
    "S07": "sin_hits",
    "S08": "sin_hits",
    "S09": "sin_hits",
    "S10": "hit_claro",
    "S11": "sin_hits",
    "S12": "genero_empatado",
    "S13": "hit_claro",
    "S14": "generos_distintos",
    "S15": "identidad_baja",
    "S16": "hit_claro",
}


def _par(carpeta: Path, nombre: str, par) -> None:
    (sf, qf), (sr, qr) = par
    escribir_ab1(carpeta / f"{nombre}_F.ab1", sf, qf)
    escribir_ab1(carpeta / f"{nombre}_R.ab1", sr, qr)


def armar_corrida(carpeta: Path) -> Path:
    """Escribe los .ab1 de la corrida estándar en `carpeta` y la devuelve."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    _par(carpeta, "S01", par_fr(A, 200))
    _par(carpeta, "S02", par_fr(A, 150, Perfil.PARCIAL, Perfil.BUENA))
    escribir_ab1(carpeta / "S03_F.ab1", *leer(B, Perfil.BUENA, 3))
    _par(carpeta, "S04", par_fr(B, 150, Perfil.SIN_SENAL, Perfil.BUENA))
    _par(carpeta, "S05", par_fr(A, 100, Perfil.PARCIAL, Perfil.PARCIAL, 5))
    escribir_ab1(carpeta / "S06_F.ab1", *leer(B, Perfil.PARCIAL, 6))
    _par(carpeta, "S07", par_fr(C, 150, Perfil.SIN_SENAL, Perfil.SIN_SENAL))
    _par(carpeta, "S08", par_fr(C, 150, Perfil.CORTA, Perfil.CORTA))
    _par(carpeta, "S09", par_fr(A, 200, Perfil.MEZCLA, Perfil.BUENA))
    escribir_ab1(carpeta / "S10_F.ab1", *leer(C, Perfil.AMBIGUA, 10))
    # 50 bases buenas y el resto pésimo: hay señal, pero ni con Q15 llega a 60 pb
    escribir_ab1(carpeta / "S11_F.ab1", A[:260], [35] * 50 + [4] * 210)
    escribir_ab1(carpeta / "S12.ab1", *leer(B, Perfil.BUENA, 12))
    (carpeta / "S13_F.ab1").write_bytes(b"esto no es un cromatograma")
    escribir_ab1(carpeta / "S13_R.ab1", *leer(reverso_complemento(C), Perfil.BUENA, 13))
    escribir_ab1(carpeta / "sub" / "S14_R.ab1", *leer(reverso_complemento(A), Perfil.BUENA, 14))
    _par(carpeta, "S15", par_fr(LARGA, 30))
    (sf, qf), (sr, qr) = par_fr(C, 180, semilla=16)
    escribir_ab1(carpeta / "S16_LCO1490.ab1", sf, qf)
    escribir_ab1(carpeta / "S16_HCO2198.ab1", sr, qr)
    return carpeta


def preparar_cache_blast(salida: Path, carpeta_fixtures: Path) -> None:
    """
    Deja un <muestra>.hits.json por muestra en salida/blast_xml.

    El BLAST remoto, igual que en el script original, reutiliza ese caché y no
    consulta a NCBI: así se prueba todo el camino con BLAST sin internet.
    """
    cache = Path(salida) / "blast_xml"
    cache.mkdir(parents=True, exist_ok=True)
    for muestra, fixture in FIXTURE_POR_MUESTRA.items():
        hits = json.loads((Path(carpeta_fixtures) / f"{fixture}.json").read_text(encoding="utf-8"))
        (cache / f"{muestra}.hits.json").write_text(
            json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8"
        )
