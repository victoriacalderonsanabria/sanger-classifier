"""
El contrato del pipeline (BRIEFING §3.3): avisa el avance, se puede cancelar y
levanta excepciones en vez de terminar el proceso.

Lo de antes: la ventana tenía que pisar sys.argv, sys.stdout y sys.stderr para
enterarse de algo, no podía cancelar, y un sys.exit del núcleo le llegaba como
SystemExit.
"""

import pytest
from Bio import SeqIO

from sanger.blast.falso import MotorFalso
from sanger.config import Parametros
from sanger.errores import Cancelado, SinArchivosError
from sanger.modelos import Grupo, Progreso
from sanger.pipeline import ejecutar
from tests.sintetico.corrida import FIXTURE_POR_MUESTRA, armar_corrida

ETAPAS = ("qc", "clasificacion", "comparacion", "blast", "informes")


@pytest.fixture(scope="module")
def entrada(tmp_path_factory):
    return armar_corrida(tmp_path_factory.mktemp("corrida") / "ab1")


@pytest.fixture
def params(entrada, tmp_path):
    return Parametros(entrada=entrada, salida=tmp_path / "res", no_blast=True)


def _cancelar_en(n: int):
    """Devuelve un `cancelado` que dice que sí a partir de la n-ésima consulta."""
    consultas = []

    def cancelado() -> bool:
        consultas.append(1)
        return len(consultas) > n

    return cancelado


# ----------------------------------------------------------------------------
# Avisos de progreso
# ----------------------------------------------------------------------------


def test_avisa_el_avance_de_todas_las_etapas(params, entrada, fixtures_blast):
    avisos: list[Progreso] = []
    motor = MotorFalso(fixtures_blast, FIXTURE_POR_MUESTRA)
    con_blast = Parametros(entrada=entrada, salida=params.salida, no_blast=False)
    ejecutar(con_blast, progreso=avisos.append, motor=motor)

    assert [p.etapa for p in avisos[:1]] == ["qc"]
    assert avisos[-1].etapa == "informes"
    assert {p.etapa for p in avisos} == set(ETAPAS)
    # el orden de las etapas es el del pipeline, sin volver atrás
    vistas = list(dict.fromkeys(p.etapa for p in avisos))
    assert vistas == [e for e in ETAPAS if e in vistas]


def test_el_avance_del_qc_cuenta_los_cromatogramas(params):
    avisos: list[Progreso] = []
    ejecutar(params, progreso=avisos.append)
    qc = [p for p in avisos if p.etapa == "qc"]
    assert qc[0].hechos == 0 and "Encontré 26 cromatogramas" in qc[0].mensaje
    assert [p.hechos for p in qc] == list(range(27))
    assert {p.total for p in qc} == {26}


def test_el_avance_de_la_comparacion_no_tiene_texto(params):
    # solo mueve la barra: el script original no imprimía nada en este paso
    avisos: list[Progreso] = []
    ejecutar(params, progreso=avisos.append)
    comparacion = [p for p in avisos if p.etapa == "comparacion"]
    assert comparacion and all(p.mensaje == "" for p in comparacion)
    assert [p.hechos for p in comparacion] == [1, 2, 3]


def test_el_nucleo_no_imprime(params, capsys):
    ejecutar(params)
    assert capsys.readouterr() == ("", "")


def test_funciona_sin_que_nadie_escuche(params):
    # los callbacks son opcionales: sin ellos hace exactamente lo mismo
    resultado = ejecutar(params)
    assert (params.salida / "04_resultados.csv").exists()
    assert len(resultado.muestras) == 16


# ----------------------------------------------------------------------------
# Cancelación
# ----------------------------------------------------------------------------


def test_cancelar_mientras_lee_los_cromatogramas(params):
    with pytest.raises(Cancelado, match="cromatogramas"):
        ejecutar(params, cancelado=_cancelar_en(3))
    # no se escribió ningún informe: la corrida no llegó ni al QC completo
    assert not (params.salida / "01_QC_lecturas.csv").exists()
    assert not (params.salida / "04_resultados.csv").exists()


def test_cancelar_mientras_clasifica_las_muestras(params):
    with pytest.raises(Cancelado, match="muestras"):
        ejecutar(params, cancelado=_cancelar_en(30))
    # el QC ya estaba terminado y escrito; los informes finales no
    assert (params.salida / "01_QC_lecturas.csv").exists()
    assert not (params.salida / "04_resultados.csv").exists()


def test_cancelar_durante_el_blast(params, entrada, fixtures_blast):
    con_blast = Parametros(entrada=entrada, salida=params.salida, no_blast=False)
    motor = MotorFalso(fixtures_blast, FIXTURE_POR_MUESTRA)
    with pytest.raises(Cancelado):
        ejecutar(con_blast, cancelado=_cancelar_en(45), motor=motor)
    assert (params.salida / "02_confiables.fasta").exists()
    assert not (params.salida / "04_resultados.csv").exists()


def test_cancelar_no_deja_archivos_a_medio_escribir(params, entrada, fixtures_blast):
    """
    Regresión del punto 4 del FEEDBACK_FASE3: cancelar corta la corrida y lo que
    quedó escrito está completo.

    Importa porque esos archivos parciales son los que alguien puede abrir
    creyendo que son el resultado: un CSV cortado a la mitad sería peor que no
    tener nada.
    """
    con_blast = Parametros(entrada=entrada, salida=params.salida, no_blast=False)
    motor = MotorFalso(fixtures_blast, FIXTURE_POR_MUESTRA)
    with pytest.raises(Cancelado):
        ejecutar(con_blast, cancelado=_cancelar_en(45), motor=motor)

    # lo que alcanzó a escribirse está entero
    qc = (params.salida / "01_QC_lecturas.csv").read_text(encoding="utf-8-sig")
    assert len(qc.strip().splitlines()) == 27  # encabezado + 26 cromatogramas
    confiables = list(SeqIO.parse(params.salida / "02_confiables.fasta", "fasta"))
    assert len(confiables) == 10 and all(len(r.seq) > 0 for r in confiables)
    assert list(SeqIO.parse(params.salida / "03_dudosas.fasta", "fasta"))

    # y lo que no llegó a escribirse, no existe: nadie va a confundirlo con el resultado
    for informe in ("04_resultados.csv", "05_hits_completos.json", "00_resumen.txt"):
        assert not (params.salida / informe).exists(), informe


def test_sin_cancelar_no_se_cancela(params):
    resultado = ejecutar(params, cancelado=lambda: False)
    assert len(resultado.muestras) == 16


# ----------------------------------------------------------------------------
# Errores
# ----------------------------------------------------------------------------


def test_carpeta_sin_ab1_levanta_sin_archivos_error(tmp_path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    params = Parametros(entrada=vacia, salida=tmp_path / "res", no_blast=True)
    with pytest.raises(SinArchivosError, match="No encontré .ab1"):
        ejecutar(params)


def test_un_ab1_corrupto_no_frena_la_corrida(params):
    resultado = ejecutar(params)
    # S13 tiene la F corrupta y la R buena: la muestra se resuelve con la R
    s13 = next(m for m in resultado.muestras if m.nombre == "S13")
    assert (s13.grupo, s13.origen) == (Grupo.CONFIABLE, "SOLO_R")
    corrupta = next(lec for lec in resultado.lecturas if lec.archivo == "S13_F.ab1")
    assert corrupta.error and corrupta.largo_crudo == 0


def test_devuelve_el_resultado_completo(params):
    resultado = ejecutar(params)
    assert len(resultado.lecturas) == 26
    assert len(resultado.del_grupo(Grupo.CONFIABLE)) == 10
    assert len(resultado.del_grupo(Grupo.DUDOSA)) == 3
    assert len(resultado.del_grupo(Grupo.RECHAZADA)) == 3
    assert resultado.segundos_blast == 0.0 and resultado.segundos_total > 0
