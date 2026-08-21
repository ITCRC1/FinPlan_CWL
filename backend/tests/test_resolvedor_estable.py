# -*- coding: utf-8 -*-
"""El resolvedor de cuentas no puede depender del orden de las filas.

`construir_resolvedor` busca la regla por `(depto, cuenta)`; si no la encuentra
cae a un FALLBACK por cuenta. Ese último paso agarraba *la primera fila que
viniera* — y el orden cambia cada vez que se recarga el mapeo, porque
`mapping_loader` borra todo el reporte y lo reinserta desde el Excel.

Con una sola regla por cuenta da igual. Con dos, la plata se mueve de línea sola
—sin que nadie toque nada y sin dejar rastro, porque el total sigue cuadrando—
y solo se ve mirando el P&L por departamento.

Hoy las 6 cuentas que caen por descarte (4700, 4701, 4800, 4860, 4880, 4890,
$1.4M entre todas) tienen exactamente una regla cada una. Esta prueba es para
que siga sin importar cuando dejen de tenerla.
"""
from app.engine.pl_engine import construir_resolvedor


def _regla(cuenta: str, dept: str, linea: str) -> dict:
    return {"account_code": cuenta, "dept_code": dept, "report_line_code": linea,
            "active_status": "YES", "rollup_operator": "SUM"}


def test_el_fallback_da_lo_mismo_venga_como_venga_la_lista():
    """La misma pregunta, dos órdenes de entrada, una sola respuesta."""
    reglas = [_regla("7380", "0120", "OPEX_FB"), _regla("7380", "0110", "OPEX_ROOMS")]
    a, _ = construir_resolvedor(reglas)("0999", "7380")
    b, _ = construir_resolvedor(list(reversed(reglas)))("0999", "7380")
    assert a["report_line_code"] == b["report_line_code"]


def test_gana_el_departamento_menor():
    reglas = [_regla("7380", "0200", "OH_MAINTENANCE"),
              _regla("7380", "0110", "OPEX_ROOMS"),
              _regla("7380", "0180", "OH_ADMIN")]
    m, como = construir_resolvedor(reglas)("0999", "7380")
    assert como == "FALLBACK"
    assert m["report_line_code"] == "OPEX_ROOMS"


def test_una_regla_sin_departamento_gana_antes_de_llegar_al_fallback():
    """Una regla sin depto se resuelve como `dept-agnostic`, que corre ANTES del
    descarte. Nunca llega al FALLBACK — por eso el desempate de allá no tiene
    que contemplarla."""
    sin = {"account_code": "7380", "dept_code": "", "report_line_code": "OPEX_MISC",
           "active_status": "YES", "rollup_operator": "SUM"}
    con = _regla("7380", "0110", "OPEX_ROOMS")
    for orden in ([sin, con], [con, sin]):
        m, como = construir_resolvedor(orden)("0999", "7380")
        assert como == "dept-agnostic"
        assert m["report_line_code"] == "OPEX_MISC"


def test_la_regla_exacta_siempre_le_gana_al_fallback():
    reglas = [_regla("7380", "0110", "OPEX_ROOMS"), _regla("7380", "0120", "OPEX_FB")]
    m, como = construir_resolvedor(reglas)("0120", "7380")
    assert como == "exact"
    assert m["report_line_code"] == "OPEX_FB"


def test_una_cuenta_sin_ninguna_regla_se_cae_y_se_avisa():
    """DROP: el monto NO llega al P&L. Es plata perdida y tiene que gritar."""
    m, como = construir_resolvedor([_regla("7380", "0110", "OPEX_ROOMS")])("0110", "9999")
    assert m is None and como == "DROP"


def test_las_reglas_inactivas_no_participan():
    inactiva = dict(_regla("7380", "0110", "OPEX_ROOMS"), active_status="NO")
    m, como = construir_resolvedor([inactiva, _regla("7380", "0120", "OPEX_FB")])("0999", "7380")
    assert m["report_line_code"] == "OPEX_FB"
