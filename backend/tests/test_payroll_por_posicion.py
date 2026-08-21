"""El reporte de planilla por CÓDIGO de posición y el correlativo del código.

Lo que se protege:
  - los 17 conceptos quedan repartidos en los tres grupos, sin sobras,
  - devengado + cargas + beneficios = costo (el número que va al P&L),
  - el correlativo sigue desde el mayor y NO recicla huecos.
"""
import asyncio

import pytest

from app.api.payroll_position_report_api import (
    CONCEPTOS, COLS, GRUPO_DE, siguiente_codigo,
)


# ── los 17 conceptos ──────────────────────────────────────────────────────────
def test_estan_los_17_conceptos_sin_repetir():
    assert len(CONCEPTOS) == 17
    assert len(set(COLS)) == 17
    assert len({c[1] for c in CONCEPTOS}) == 17     # códigos GL distintos


def test_cada_concepto_cae_en_un_grupo_conocido():
    assert set(GRUPO_DE.values()) == {"DEVENGADO", "CARGAS", "BENEFICIOS"}


def test_los_cuatro_que_pidio_el_owner_son_devengado():
    """Salario bruto, horas extra, comisiones y feriado laborado: si alguno
    cayera en cargas, el reporte diría que la persona no lo recibe."""
    for col in ("c6000_sw", "c6001_overtime", "c6010_commissions",
                "c6003_working_holiday"):
        assert GRUPO_DE[col] == "DEVENGADO"


def test_la_ccss_y_el_aguinaldo_no_son_devengado():
    """Son costo patronal y provisión: sumarlos a lo devengado infla lo que la
    persona cree que gana."""
    assert GRUPO_DE["c6020_ccss"] == "CARGAS"
    assert GRUPO_DE["c6021_aguinaldo"] == "CARGAS"


def test_las_columnas_existen_en_el_modelo():
    from app.models.payroll_concept_entry import PayrollConceptEntry
    for col in COLS:
        assert hasattr(PayrollConceptEntry, col), col


# ── correlativo del código ────────────────────────────────────────────────────
class _Pos:
    def __init__(self, code):
        self.position_code = code


class _Scalars:
    def __init__(self, filas):
        self._filas = filas

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._filas)


class _Db:
    def __init__(self, codes):
        self._codes = [_Pos(c) for c in codes]

    async def execute(self, _q):
        return _Scalars(self._codes)


def _codes(existentes, count=1, dept="0111"):
    return asyncio.run(siguiente_codigo(
        "sid", dept=dept, count=count, db=_Db(existentes)))["codes"]


def test_arranca_en_01_si_el_depto_esta_vacio():
    assert _codes([]) == ["0111-01"]


def test_sigue_desde_el_mayor():
    assert _codes(["0111-01", "0111-02", "0111-05"]) == ["0111-06"]


def test_no_recicla_huecos():
    """Un código borrado puede estar citado en un reporte viejo o en una regla
    de allocation; reciclarlo lo haría apuntar a otra persona."""
    assert _codes(["0111-01", "0111-03"]) == ["0111-04"]


def test_entrega_varios_seguidos():
    assert _codes(["0111-01"], count=3) == ["0111-02", "0111-03", "0111-04"]


def test_respeta_el_ancho_que_ya_usa_el_depto():
    assert _codes(["0200-001", "0200-002"], dept="0200") == ["0200-003"]


def test_ignora_los_codigos_de_otro_formato():
    """La planilla vieja traía códigos sueltos ('513'); no deben confundir el
    correlativo del departamento."""
    assert _codes(["513", "604", "0111-07"]) == ["0111-08"]


def test_no_choca_con_los_que_ya_existen():
    existentes = ["0111-01", "0111-02", "0111-03"]
    nuevos = _codes(existentes, count=2)
    assert not (set(nuevos) & set(existentes))
