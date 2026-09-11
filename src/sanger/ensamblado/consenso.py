"""Consenso forward + reverse sobre lecturas crudas."""

from dataclasses import dataclass, field

from Bio import Align
from Bio.Seq import Seq

from sanger.qc.metricas import ACGT


def aligner_local(match=2, mismatch=-3, gap_open=-5, gap_ext=-2) -> Align.PairwiseAligner:
    """
    Alineador local (Smith-Waterman).

    Local y no global porque F y R solo se superponen en parte: cada una tiene
    un extremo que la otra no cubre.
    """
    a = Align.PairwiseAligner()
    a.mode = "local"
    a.match_score, a.mismatch_score = match, mismatch
    a.open_gap_score, a.extend_gap_score = gap_open, gap_ext
    return a


@dataclass(frozen=True)
class Consenso:
    seq: str = ""
    qual: list[int] = field(default_factory=list)
    solap: int = 0
    discrepancias: int = 0
    conflictos: int = 0  # discrepancias con ambas bases de buena calidad
    ok: bool = False


def consenso_fr(seq_f, qual_f, seq_r, qual_r, min_solap=50, q_conflicto=20) -> Consenso:
    """
    Alinea F contra el reverso-complemento de R y arma un consenso base a base.

    En cada posición gana la base de mayor calidad, y una base A/C/G/T le gana a
    un código de ambigüedad (N, R, Y…). Devuelve el consenso SIN recortar, con su
    vector de calidad: el recorte se hace después, sobre el consenso. Si se
    recortara cada lectura antes, en amplicones cortos se pierde el solapamiento
    (las F arrancan mal y las R terminan mal). Esto ya se probó y es deliberado.

    `conflictos` cuenta las discrepancias donde AMBAS lecturas tenían buena
    calidad: tres o más sugieren mezcla de plantillas (picos dobles).
    """
    rc = str(Seq(seq_r).reverse_complement())
    qual_rc = qual_r[::-1]
    aln = aligner_local().align(seq_f, rc)[0]
    bf, br = aln.aligned
    if len(bf) == 0:
        return Consenso()
    f_ini, f_fin = bf[0][0], bf[-1][1]
    r_ini, r_fin = br[0][0], br[-1][1]
    solap = f_fin - f_ini
    if solap < min_solap:
        return Consenso(solap=int(solap))

    def q_region(qual, a, b):
        # calidad de una inserción; si una lectura no tiene nada ahí se usa la
        # de sus bases vecinas: una inserción de Q=3 en F no debe imponerse
        # sobre una R de Q=35 que simplemente no la tiene
        if b > a:
            return sum(qual[a:b]) / (b - a)
        fl = qual[max(0, a - 1) : a + 1]
        return sum(fl) / max(1, len(fl))

    cons, qcons = list(seq_f[:f_ini]), list(qual_f[:f_ini])
    discrep = conflictos = 0
    pos_f, pos_r = f_ini, r_ini
    for (fa, fb), (ra, rb) in zip(bf, br, strict=False):
        gap_f, gap_r = seq_f[pos_f:fa], rc[pos_r:ra]
        if gap_f or gap_r:
            qf, qr = q_region(qual_f, pos_f, fa), q_region(qual_rc, pos_r, ra)
            if qf >= qr:
                cons += list(gap_f)
                qcons += list(qual_f[pos_f:fa])
            else:
                cons += list(gap_r)
                qcons += list(qual_rc[pos_r:ra])
            discrep += 1
            if min(qf, qr) >= q_conflicto:
                conflictos += 1
        for i, j in zip(range(fa, fb), range(ra, rb), strict=False):
            b1, b2, q1, q2 = seq_f[i], rc[j], qual_f[i], qual_rc[j]
            if b1 == b2:
                cons.append(b1)
                qcons.append(max(q1, q2))
            else:
                discrep += 1
                if min(q1, q2) >= q_conflicto and b1 in ACGT and b2 in ACGT:
                    conflictos += 1
                if b1 not in ACGT and b2 in ACGT:
                    cons.append(b2)
                    qcons.append(q2)
                elif b2 not in ACGT and b1 in ACGT:
                    cons.append(b1)
                    qcons.append(q1)
                elif q1 >= q2:
                    cons.append(b1)
                    qcons.append(q1 - q2)
                else:
                    cons.append(b2)
                    qcons.append(q2 - q1)
        pos_f, pos_r = fb, rb
    cons += list(rc[r_fin:])
    qcons += list(qual_rc[r_fin:])
    return Consenso(
        seq="".join(cons),
        qual=qcons,
        solap=int(solap),
        discrepancias=discrep,
        conflictos=conflictos,
        ok=True,
    )
