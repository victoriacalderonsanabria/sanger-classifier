"""
BLAST: interpretación de los hits, motores y caché. Todo offline.

El motor remoto se prueba sin tocar NCBI: con caché ya armado, o reemplazando
la llamada a NCBI por una que falla (pytest-socket además bloquea la red).
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from sanger.blast import local, remoto
from sanger.blast.falso import MotorFalso, cargar_fixture
from sanger.blast.interpretacion import interpretar, resumir_hits
from sanger.errores import BlastError, Cancelado
from sanger.modelos import Hit

# ----------------------------------------------------------------------------
# interpretar, con las respuestas preparadas del §5.3
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "esperado"),
    [
        ("hit_claro", "identificado"),
        ("genero_empatado", "identificado a nivel de género (Bos taurus / Bos indicus)"),
        ("generos_distintos", "ambiguo: dos especies con identidad similar"),
        ("cobertura_baja", "cobertura_baja (42.3%): hit parcial, revisar"),
        (
            "identidad_baja",
            "identidad_baja (89.74% < 97.0%): especie no representada o secuencia con errores",
        ),
        ("humano", "humano: verificar si es esperado o contaminación"),
        ("sin_hits", "sin_hit"),
    ],
)
def test_interpretar_fixtures(fixture, esperado, fixtures_blast):
    hits = cargar_fixture(fixtures_blast / f"{fixture}.json")
    assert interpretar(hits, 97.0, 80.0) == esperado


def _hit(especie, identidad, cobertura=100.0, titulo=None):
    return Hit(especie, "XX1", identidad, cobertura, 1e-50, titulo or especie)


@pytest.mark.parametrize(
    ("hits", "esperado"),
    [
        # diferencia de exactamente 1 punto: ya no es empate
        ([_hit("Canis lupus", 100.0), _hit("Vulpes vulpes", 99.0)], "identificado"),
        ([_hit("Canis lupus", 99.0)], "identificado"),
        # la cobertura se mira antes que la identidad
        ([_hit("Canis lupus", 50.0, 10.0)], "cobertura_baja (10.0%): hit parcial, revisar"),
        # el empate se mira antes que "humano"
        (
            [_hit("Homo sapiens", 100.0), _hit("Homo neanderthalensis", 99.8)],
            "identificado a nivel de género (Homo sapiens / Homo neanderthalensis)",
        ),
    ],
)
def test_interpretar_orden_de_las_reglas(hits, esperado):
    assert interpretar(hits, 97.0, 80.0) == esperado


# ----------------------------------------------------------------------------
# resumir_hits
# ----------------------------------------------------------------------------


def _alineamiento(titulo, accession, identidades, largo_aln, evalue=1e-50):
    hsp = SimpleNamespace(identities=identidades, align_length=largo_aln, expect=evalue)
    return SimpleNamespace(hit_def=titulo, title=titulo, accession=accession, hsps=[hsp])


def test_resumir_hits_una_fila_por_especie_y_maximo_tres():
    rec = SimpleNamespace(
        alignments=[
            _alineamiento("Bos taurus isolate A cytochrome oxidase I", "AC1", 198, 200),
            _alineamiento("Bos taurus isolate B cytochrome oxidase I", "AC2", 197, 200),
            _alineamiento("Bos indicus voucher X", "AC3", 196, 200),
            # sin "Género especie" al principio: se usan los primeros 40 caracteres
            _alineamiento("uncultured eukaryote clone MX12 mitochondrial COI", "AC4", 150, 200),
            _alineamiento("Bubalus bubalis mitochondrion", "AC5", 190, 200),
        ]
    )
    hits = resumir_hits(rec, largo_query=250)
    assert [h.especie for h in hits] == [
        "Bos taurus",
        "Bos indicus",
        "uncultured eukaryote clone MX12 mitochon",
    ]
    assert hits[0] == Hit(
        especie="Bos taurus",
        accession="AC1",
        identidad=99.0,
        cobertura=80.0,
        evalue=1e-50,
        titulo="Bos taurus isolate A cytochrome oxidase I",
    )


def test_resumir_hits_sin_registro():
    assert resumir_hits(None, 100) == []


def test_hit_como_dict_mantiene_el_orden_del_original():
    h = _hit("Bos taurus", 99.0)
    assert list(h.como_dict()) == [
        "especie",
        "accession",
        "identidad",
        "cobertura",
        "evalue",
        "titulo",
    ]


# ----------------------------------------------------------------------------
# Motor falso
# ----------------------------------------------------------------------------


def test_motor_falso_responde_por_muestra_y_registra_las_llamadas(fixtures_blast):
    motor = MotorFalso(fixtures_blast, {"M1": "hit_claro", "M2": "sin_hits"})
    res = motor.buscar([("M1", "ACGT", 4), ("M2", "ACGT", 4), ("M3", "ACGT", 4)], megablast=True)
    assert res["M1"][0].especie == "Bos taurus"
    assert res["M2"] == [] and res["M3"] == []
    assert motor.llamadas == [(("M1", "M2", "M3"), True)]


# ----------------------------------------------------------------------------
# Motor remoto (NCBI) sin red
# ----------------------------------------------------------------------------


def _qblast_prohibido(**kwargs):
    raise AssertionError("no debería consultar a NCBI: estaba todo en caché")


def test_remoto_con_cache_completo_no_consulta_ncbi(tmp_path, fixtures_blast, monkeypatch):
    monkeypatch.setattr(remoto.NCBIWWW, "qblast", _qblast_prohibido)
    hits = json.loads((fixtures_blast / "hit_claro.json").read_text(encoding="utf-8"))
    (tmp_path / "M1.hits.json").write_text(json.dumps(hits), encoding="utf-8")
    res = remoto.blast_remoto_lote([("M1", "ACGT", 4)], tmp_path)
    assert res["M1"] == cargar_fixture(fixtures_blast / "hit_claro.json")


def test_remoto_error_de_motor_hoy_se_ve_como_sin_hit_bug1(tmp_path, monkeypatch):
    """
    BUG-1, comportamiento ACTUAL (se corrige en la fase 4, con el OK de Victoria).

    Si NCBI falla los 3 intentos, las muestras del lote quedan con lista vacía y
    `interpretar` lo informa como "sin_hit": un fallo de red se ve igual que "no
    matcheó con nada en GenBank". Este test fija el comportamiento de hoy; en la
    fase 4 pasa a esperar un estado ERROR_BLAST distinguible.
    """
    intentos = []

    def qblast_que_falla(**kwargs):
        intentos.append(kwargs)
        raise ConnectionError("NCBI no responde")

    monkeypatch.setattr(remoto.NCBIWWW, "qblast", qblast_que_falla)
    monkeypatch.setattr(remoto.time, "sleep", lambda s: None)
    avisos = []
    res = remoto.blast_remoto_lote(
        [("M1", "ACGT", 4), ("M2", "ACGT", 4)], tmp_path, progreso=avisos.append
    )
    assert len(intentos) == 3
    assert res == {"M1": [], "M2": []}
    assert interpretar(res["M1"], 97.0, 80.0) == "sin_hit"
    assert not (tmp_path / "M1.hits.json").exists()  # al menos no queda cacheado
    assert any("intento 3 falló: NCBI no responde" in p.mensaje for p in avisos)


def test_remoto_manda_en_lotes_del_tamano_pedido(tmp_path, monkeypatch):
    lotes = []

    def qblast(**kwargs):
        lotes.append(kwargs["sequence"].count(">"))
        raise ConnectionError("sin red en tests")

    monkeypatch.setattr(remoto.NCBIWWW, "qblast", qblast)
    monkeypatch.setattr(remoto.time, "sleep", lambda s: None)
    items = [(f"M{i}", "ACGT", 4) for i in range(5)]
    remoto.blast_remoto_lote(items, tmp_path, tamano_lote=2, entrez_query="Vertebrata[Organism]")
    assert lotes == [2, 2, 2, 2, 2, 2, 1, 1, 1]  # 3 lotes (2+2+1), 3 intentos cada uno


def test_motor_remoto_pasa_sus_parametros(tmp_path, monkeypatch):
    recibido = {}

    def falso(items, carpeta, db, megablast, entrez_query=None, tamano_lote=50, **kwargs):
        recibido.update(db=db, megablast=megablast, entrez=entrez_query, lote=tamano_lote)
        return {}

    monkeypatch.setattr(remoto, "blast_remoto_lote", falso)
    remoto.MotorRemoto(tmp_path, "mito", "Vertebrata[Organism]", 20).buscar([], megablast=False)
    assert recibido == dict(db="mito", megablast=False, entrez="Vertebrata[Organism]", lote=20)


# ----------------------------------------------------------------------------
# Motor local (blastn) sin blastn instalado
# ----------------------------------------------------------------------------


def test_local_sin_blastn_instalado_levanta_blast_error(tmp_path, monkeypatch):
    # antes era un sys.exit dentro de la librería (BRIEFING §2.1c)
    def no_existe(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(local.subprocess, "run", no_existe)
    with pytest.raises(BlastError, match="No encuentro 'blastn'"):
        local.blast_local("M1", "ACGT", tmp_path, "base")


def test_local_si_blastn_falla_la_muestra_queda_sin_hits(tmp_path, monkeypatch):
    def falla(cmd, **k):
        raise subprocess.CalledProcessError(2, cmd, stderr="BLAST Database error\n")

    monkeypatch.setattr(local.subprocess, "run", falla)
    avisos = []
    res = local.MotorLocal(tmp_path, "base").buscar(
        [("M1", "ACGT", 4)], megablast=True, progreso=avisos.append
    )
    assert res == {"M1": []}
    assert any("[BLAST local] falló para M1: BLAST Database error" in p.mensaje for p in avisos)


def test_remoto_se_puede_cancelar_antes_de_enviar_un_lote(tmp_path, monkeypatch):
    monkeypatch.setattr(remoto.NCBIWWW, "qblast", _qblast_prohibido)
    with pytest.raises(Cancelado):
        remoto.blast_remoto_lote([("M1", "ACGT", 4)], tmp_path, cancelado=lambda: True)


def test_local_se_puede_cancelar_entre_muestras(tmp_path, monkeypatch):
    def no_deberia_correr(*a, **k):
        raise AssertionError("no debería llamar a blastn después de cancelar")

    monkeypatch.setattr(local.subprocess, "run", no_deberia_correr)
    with pytest.raises(Cancelado):
        local.MotorLocal(tmp_path, "base").buscar(
            [("M1", "ACGT", 4)], megablast=True, cancelado=lambda: True
        )


def test_local_arma_el_comando_de_blastn(tmp_path, monkeypatch):
    comandos = []

    def captura(cmd, **k):
        comandos.append(cmd)
        raise subprocess.CalledProcessError(1, cmd, stderr="")

    monkeypatch.setattr(local.subprocess, "run", captura)
    local.blast_local("M1", "ACGT", tmp_path, "mi_base", megablast=False)
    cmd = comandos[0]
    assert cmd[:3] == ["blastn", "-task", "blastn"]
    assert cmd[cmd.index("-db") + 1] == "mi_base"
    assert (tmp_path / "M1.query.fa").read_text() == ">M1\nACGT\n"
