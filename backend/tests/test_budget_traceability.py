# -*- coding: utf-8 -*-
"""
AUDITORÍA DE TRAZABILIDAD DEL BUDGET — cada auxiliar debe aterrizar en la línea
correcta del P&L, y las fórmulas (CCSS, aguinaldo) deben recalcular solas.

Usa el mapeo REAL del archivo de configuración y el motor REAL del P&L, así que
si alguien rompe el ruteo o el recálculo, estos tests fallan.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from app.engine import pl_engine
from app.engine.payroll_calculator import calc_base, recalculate_entry
from app.importers.gl_detail_importer import dept_code_from_name
from app.importers.mapping_loader import parse_mapping_upload, parse_report_config
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_position import PayrollPosition

from tests._rutas import DATOS
MAPPING_XLSX = DATOS / "data" / "formato_mapping_reporte_app.xlsx"
pytestmark = pytest.mark.skipif(not MAPPING_XLSX.exists(),
                                reason="archivo de mapeo no disponible")


# ─── fixtures: mapeo real, con dept_code resuelto (como lo deja la mig. 070) ───
@pytest.fixture(scope="module")
def report_lines():
    return [{"line_code": r["line_code"], "line_name": r["line_name"],
             "section": r["section"], "line_type": r["line_type"],
             "display_order": r["display_order"],
             "calculation_logic": r["calculation_logic"],
             "active": str(r.get("active_status", "YES")).upper() == "YES"}
            for r in parse_report_config(str(MAPPING_XLSX))]


@pytest.fixture(scope="module")
def mappings():
    out = []
    for m in parse_mapping_upload(str(MAPPING_XLSX)):
        if not m["account_code"] or str(m.get("active_status", "YES")).upper() != "YES":
            continue
        name = (m.get("source_department") or "").strip()
        out.append({"account_code": m["account_code"].strip(),
                    "dept_code": (dept_code_from_name(name) or "") if name else "",
                    "report_line_code": m["report_line_code"],
                    "active_status": "YES",
                    "rollup_operator": m.get("rollup_operator", "SUM")})
    return out


def _pl(rows, mappings, report_lines, **kw):
    res = pl_engine.calculate_pl_from_mapping(rows, mappings, report_lines, **kw)
    return {L.line_code: float(L.amount_usd) for L in res}


def _row(acct, dept, amount):
    return {"account_code": acct, "dept_code": dept, "amount": Decimal(str(amount))}


# ══════════════════════════════════════════════════════════════════════════════
# 1. GASTO POR DEPARTAMENTO → LA LÍNEA CORRECTA
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("dept,linea", [
    ("0110", "OPEX_ROOMS"),
    ("0120", "OPEX_FB"),
    ("0140", "OPEX_SPA"),
    ("0150", "OPEX_TOURS"),
    # ⚠️ Acá decía `("0151", "OPEX_RETAIL")` y la prueba pasaba POR EL BUG.
    # El fixture resuelve el departamento con `dept_code_from_name` del
    # importador del GL, que mandaba «gift» al 0151. Desde la separación
    # Tienda/Gift Shop (2026-08-13) el 0151 es la TIENDA y el 0165 el Gift Shop;
    # al corregir el importador (2026-08-14) el error salió a la luz.
    #
    # No se agrega el caso del 0151: el libro de referencia de este fixture
    # (`formato_mapping_reporte_app.xlsx`) es ANTERIOR a esa separación y no
    # tiene ni una regla de Tienda. Lo cubre `test_tienda_no_cae_en_private_bar`,
    # que lee el mapeo vigente.
    ("0165", "OPEX_RETAIL"),
    ("0152", "OPEX_TRANSPORTATION"),
    ("0180", "OH_ADMIN"),
    ("0190", "OH_SALES_MARKETING"),
    ("0200", "OH_MAINTENANCE"),
    ("0230", "OH_INFORMATION_SYSTEM"),
])
def test_opex_cae_en_el_departamento_correcto(dept, linea, mappings, report_lines):
    """$100 de planilla (6000) en un depto debe caer en la línea de ESE depto."""
    base = _pl([], mappings, report_lines)
    con = _pl([_row("6000", dept, 100)], mappings, report_lines)
    assert round(con.get(linea, 0) - base.get(linea, 0), 2) == 100.0, (
        f"$100 en depto {dept} no llegó a {linea}")


def test_admin_va_a_overhead_no_a_operativos(mappings, report_lines):
    """La planilla de Administración es OVERHEAD: no debe inflar los gastos
    operativos departamentales (si lo hiciera, el GOP quedaría deformado)."""
    base = _pl([], mappings, report_lines)
    con = _pl([_row("6000", "0180", 100)], mappings, report_lines)
    d_op = con.get("TOTAL_OPERATING_EXPENSES", 0) - base.get("TOTAL_OPERATING_EXPENSES", 0)
    d_oh = con.get("TOTAL_OVERHEAD_EXPENSES", 0) - base.get("TOTAL_OVERHEAD_EXPENSES", 0)
    assert round(d_oh, 2) == 100.0, "Admin no sumó a overhead"
    assert round(d_op, 2) == 0.0, "Admin se coló en gastos operativos"


def test_cinco_departamentos_no_colapsan_en_rooms(mappings, report_lines):
    """Regresión del misruteo: $1,000 en 5 deptos NO puede terminar todo en Rooms."""
    rows = [_row("6000", d, 1000) for d in ("0110", "0120", "0140", "0150", "0180")]
    con = _pl(rows, mappings, report_lines)
    assert round(con.get("OPEX_ROOMS", 0), 2) == 1000.0
    for linea in ("OPEX_FB", "OPEX_SPA", "OPEX_TOURS", "OH_ADMIN"):
        assert round(con.get(linea, 0), 2) == 1000.0, f"{linea} quedó vacía (misruteo)"


# ══════════════════════════════════════════════════════════════════════════════
# 2. EL GASTO LLEGA AL GOP (la cadena completa)
# ══════════════════════════════════════════════════════════════════════════════
def test_cien_dolares_de_gasto_bajan_el_gop_en_cien(mappings, report_lines):
    base = _pl([], mappings, report_lines)
    con = _pl([_row("7065", "0110", 100)], mappings, report_lines)
    assert round(con["TOTAL_OPERATING_EXPENSES"] - base["TOTAL_OPERATING_EXPENSES"], 2) == 100.0
    assert round(con["TOTAL_GOP"] - base["TOTAL_GOP"], 2) == -100.0


def test_ingreso_sube_revenue_y_gop(mappings, report_lines):
    """El ingreso entra como semilla por línea (viene de tarifas × ocupación)."""
    base = _pl([], mappings, report_lines)
    con = _pl([], mappings, report_lines, seed_amounts={"REV_ROOMS": Decimal("1000")})
    assert round(con["TOTAL_REVENUES"] - base["TOTAL_REVENUES"], 2) == 1000.0
    assert round(con["TOTAL_GOP"] - base["TOTAL_GOP"], 2) == 1000.0


def test_acumulacion_incremental(mappings, report_lines):
    """Meter $100 dos veces deja el saldo en $200 (lo que el owner verifica en Control)."""
    uno = _pl([_row("7065", "0110", 100)], mappings, report_lines)
    dos = _pl([_row("7065", "0110", 100), _row("7065", "0110", 100)], mappings, report_lines)
    assert round(uno["OPEX_ROOMS"], 2) == 100.0
    assert round(dos["OPEX_ROOMS"], 2) == 200.0


# ══════════════════════════════════════════════════════════════════════════════
# 2b. CADENA DE INGRESOS: Rack Rates + Ocupación + Canales → P&L
# ══════════════════════════════════════════════════════════════════════════════
def test_cadena_de_ingresos_llega_completa_al_pl(mappings, report_lines):
    """Auxiliares de ingreso (tarifa × ocupación) → línea de ingreso → TOTAL_REVENUES.
    Verifica que subir la tarifa suba el ingreso y que llegue íntegro al P&L."""
    from app.engine.revenue_calculator import calculate_revenue
    from app.models.occupancy_budget import OccupancyBudget
    from app.models.rate_card import RateCard

    RT = "rt-1"

    def correr(rack, ocupadas):
        rc = RateCard(room_type_id=RT, month=1, rack_rate=Decimal(str(rack)),
                      net_rate=Decimal(str(rack)), pax_per_room=Decimal("2"))
        ob = OccupancyBudget(room_type_id=RT, month=1,
                             rooms_occupied=Decimal(str(ocupadas)))
        return calculate_revenue(1, 2027, [rc], [ob], [], [], [], {RT: 10})

    base = correr(100, 10)
    assert base.rooms == Decimal("1000"), "tarifa × noches no dio el ingreso de rooms"

    # El doble de tarifa → el doble de ingreso de habitaciones
    doble = correr(200, 10)
    assert doble.rooms == base.rooms * 2

    # …y ese ingreso llega íntegro al P&L
    from app.engine.recalculate import revenue_line_dict
    res = pl_engine.calculate_budget_pl_from_mapping(
        [], mappings, report_lines, revenue_by_line=revenue_line_dict(base))
    tot = {L.line_code: float(L.amount_usd) for L in res}
    assert round(tot["REV_ROOMS"], 2) == 1000.0
    assert round(tot["TOTAL_REVENUES"], 2) == float(base.total_revenue)


def test_management_fee_e_impuesto_sobre_la_base_correcta(mappings, report_lines):
    """El fee se calcula sobre INGRESOS (no sobre gastos) y el impuesto sobre el EBT,
    con piso en cero cuando hay pérdida."""
    from app.engine.pl_engine import ManualInputs

    manual = ManualInputs(mgmt_fee_pct_3=Decimal("0.03"), income_tax_rate=Decimal("0.30"))
    res = pl_engine.calculate_budget_pl_from_mapping(
        [], mappings, report_lines,
        revenue_by_line={"rooms": Decimal("100000")}, manual=manual)
    tot = {L.line_code: float(L.amount_usd) for L in res}
    assert round(tot["MGMT_FEE_3"], 2) == 3000.0, "el fee no es el 3% de los ingresos"
    assert round(tot["INCOME_TAXES"], 2) == round(max(0.0, tot["EBT"]) * 0.30, 2)
    assert round(tot["NET_PROFIT"], 2) == round(tot["EBT"] - tot["INCOME_TAXES"], 2)


def test_sin_fee_fantasma_por_defecto(mappings, report_lines):
    """Sin porcentaje configurado NO debe aparecer un management fee inventado."""
    res = pl_engine.calculate_budget_pl_from_mapping(
        [], mappings, report_lines, revenue_by_line={"rooms": Decimal("100000")})
    tot = {L.line_code: float(L.amount_usd) for L in res}
    assert round(tot.get("MGMT_FEE_3", 0), 2) == 0.0


def test_perdida_no_genera_impuesto(mappings, report_lines):
    """Con pérdida el impuesto debe ser 0 (no un crédito que infle la utilidad)."""
    from app.engine.pl_engine import ManualInputs
    res = pl_engine.calculate_budget_pl_from_mapping(
        [_row("6000", "0110", 50000)], mappings, report_lines,
        revenue_by_line={"rooms": Decimal("1000")},
        manual=ManualInputs(income_tax_rate=Decimal("0.30")))
    tot = {L.line_code: float(L.amount_usd) for L in res}
    assert tot["EBT"] < 0, "el escenario de prueba debería dar pérdida"
    assert round(tot["INCOME_TAXES"], 2) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 2c. REGLA: EL INGRESO SALE SOLO DEL CHECKBOOK
# ══════════════════════════════════════════════════════════════════════════════
def test_el_gasto_no_puede_generar_ingreso(mappings, report_lines):
    """Regla del owner: el ingreso del presupuesto sale ÚNICAMENTE del checkbook de
    ingresos. Este test documenta la única rendija posible — meter una cuenta 4xxx
    dentro del checkbook de gastos — para que quede visible: el tab de Control la
    marca como «ingreso por otra vía»."""
    solo_gasto = _pl([_row("7065", "0110", 100)], mappings, report_lines)
    assert round(solo_gasto.get("TOTAL_REVENUES", 0), 2) == 0.0, (
        "un gasto normal generó ingreso")

    # Una cuenta de ingreso metida en el lado del gasto SÍ entraría al P&L como
    # ingreso: por eso el Control la denuncia en vez de dejarla pasar callada.
    colada = _pl([_row("4000", "0110", 100)], mappings, report_lines)
    assert round(colada.get("TOTAL_REVENUES", 0), 2) == 100.0, (
        "cambió el comportamiento: revisá el aviso 'ingreso_por_otra_via' del Control")


def test_el_ingreso_del_checkbook_llega_completo(mappings, report_lines):
    """Las 11 líneas del checkbook de ingresos suman exacto en TOTAL_REVENUES."""
    from app.engine.recalculate import revenue_line_dict
    from app.engine.revenue_calculator import RevenueResult
    import dataclasses

    campos = {f.name for f in dataclasses.fields(RevenueResult)}
    montos = {"rooms": 1000, "food": 200, "beverage": 100, "spa": 50, "activities": 300,
              "transport": 80, "retail": 40, "laundry": 10, "innoceana": 20,
              "sustainability": 60, "fnb_misc": 5}
    r = RevenueResult(**{**{c: 0 for c in campos},
                         **{k: Decimal(str(v)) for k, v in montos.items()}})
    res = pl_engine.calculate_budget_pl_from_mapping(
        [], mappings, report_lines, revenue_by_line=revenue_line_dict(r))
    tot = {L.line_code: float(L.amount_usd) for L in res}
    assert round(tot["TOTAL_REVENUES"], 2) == float(sum(montos.values())), (
        "se perdió ingreso del checkbook en el camino al P&L")


# ══════════════════════════════════════════════════════════════════════════════
# 3. FÓRMULAS: CCSS Y AGUINALDO SE MUEVEN SOLOS
# ══════════════════════════════════════════════════════════════════════════════
def _pos(salary):
    p = PayrollPosition(dept_code="0110", position_code="X", position_name="Test",
                        salary_amount=Decimal(str(salary)), salary_currency="USD")
    for f in ("fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
              "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec"):
        setattr(p, f, Decimal("1"))
    return p


def _entry():
    e = PayrollConceptEntry(dept_code="0110", month=1, year=2027)
    for c in ("c6000_sw", "c6001_overtime", "c6002_day_off", "c6003_working_holiday",
              "c6004_disabilities", "c6010_commissions", "c6020_ccss", "c6021_aguinaldo",
              "c6022_occ_hazard", "c6023_vacation_prov", "c6024_vacations_taken",
              "c6025_cafeteria", "c6026_severance", "c6027_incentive_bonus",
              "c6028_housing", "c6029_transport", "c6030_other"):
        setattr(e, c, Decimal("0"))
    return e


CCSS = Decimal("0.2667")
AGU = Decimal("12")


def test_ccss_sube_cuando_sube_el_salario():
    e1, e2 = _entry(), _entry()
    recalculate_entry(e1, _pos(1000), 1, Decimal("1"), CCSS, AGU)
    recalculate_entry(e2, _pos(2000), 1, Decimal("1"), CCSS, AGU)
    assert e2.c6000_sw == e1.c6000_sw * 2, "el salario no se duplicó"
    assert e2.c6020_ccss == e1.c6020_ccss * 2, "la CCSS no siguió al salario"
    # el aguinaldo se redondea a céntimos en cada mes → tolerancia de 1 céntimo
    assert abs(e2.c6021_aguinaldo - e1.c6021_aguinaldo * 2) <= Decimal("0.01"), (
        "el aguinaldo no siguió al salario")


def test_ccss_sube_cuando_se_agrega_comision():
    """Las comisiones entran a la base de CCSS y aguinaldo."""
    pos = _pos(1000)
    sin = _entry()
    recalculate_entry(sin, pos, 1, Decimal("1"), CCSS, AGU)
    con = _entry()
    con.c6010_commissions = Decimal("500")
    recalculate_entry(con, pos, 1, Decimal("1"), CCSS, AGU)
    assert calc_base(con) == calc_base(sin) + Decimal("500")
    assert con.c6020_ccss > sin.c6020_ccss, "la CCSS ignoró la comisión"
    esperado = (calc_base(con) * CCSS).quantize(Decimal("0.01"))
    assert con.c6020_ccss == esperado


def test_ccss_es_exactamente_la_tasa_sobre_la_base():
    from decimal import ROUND_HALF_UP
    e = _entry()
    e.c6001_overtime = Decimal("100")
    e.c6027_incentive_bonus = Decimal("50")
    recalculate_entry(e, _pos(1000), 1, Decimal("1"), CCSS, AGU)
    cent = Decimal("0.01")
    assert e.c6020_ccss == (calc_base(e) * CCSS).quantize(cent, ROUND_HALF_UP)
    assert e.c6021_aguinaldo == (calc_base(e) / AGU).quantize(cent, ROUND_HALF_UP)


def test_beneficios_no_inflan_la_base_de_ccss():
    """Cafetería/transporte/vivienda NO cotizan: no deben mover la CCSS."""
    a = _entry()
    recalculate_entry(a, _pos(1000), 1, Decimal("1"), CCSS, AGU)
    b = _entry()
    b.c6025_cafeteria = Decimal("300")
    b.c6029_transport = Decimal("200")
    recalculate_entry(b, _pos(1000), 1, Decimal("1"), CCSS, AGU)
    assert b.c6020_ccss == a.c6020_ccss


def test_la_planilla_completa_llega_al_pl(mappings, report_lines):
    """Los 17 conceptos de un depto deben sumar íntegros en su línea del P&L."""
    e = _entry()
    e.c6010_commissions = Decimal("200")
    e.c6025_cafeteria = Decimal("100")
    recalculate_entry(e, _pos(1000), 1, Decimal("1"), CCSS, AGU)
    rows, total = [], Decimal("0")
    from app.engine.recalculate import PAYROLL_ALL_COLS
    for col in PAYROLL_ALL_COLS:
        v = getattr(e, col, None) or Decimal("0")
        if v:
            rows.append(_row(pl_engine.payroll_account_for_column(col), "0110", v))
            total += v
    con = _pl(rows, mappings, report_lines)
    assert round(con.get("OPEX_ROOMS", 0), 2) == float(round(total, 2)), (
        "se perdieron conceptos de planilla en el camino al P&L")


# ══════════════════════════════════════════════════════════════════════════════
# 4. NADA SE PIERDE EN SILENCIO
# ══════════════════════════════════════════════════════════════════════════════
def test_cuenta_inexistente_no_se_traga_la_plata_en_silencio(mappings, report_lines):
    """Una cuenta sin regla NO llega al P&L. El tab de Control debe marcarla como
    DROP: este test documenta el comportamiento para que no sorprenda."""
    base = _pl([], mappings, report_lines)
    con = _pl([_row("9999", "0110", 5000)], mappings, report_lines)
    assert con["TOTAL_OPERATING_EXPENSES"] == base["TOTAL_OPERATING_EXPENSES"], (
        "una cuenta sin mapeo entró al P&L por una ruta inesperada")


# La migración 071 cierra este hueco en la BD; el archivo de configuración
# (fuente de estos tests) todavía no lo trae.
HUECO_CERRADO_POR_MIG_071 = {"6004"}   # Incapacidades


def test_todos_los_ingresos_del_motor_llegan_al_pl(report_lines):
    """Cada línea de ingreso que produce el motor de revenue (tarifas × ocupación)
    debe tener destino en el P&L; si no, ese ingreso se perdería."""
    import dataclasses
    from app.engine.recalculate import revenue_line_dict
    from app.engine.revenue_calculator import RevenueResult

    campos = {f.name for f in dataclasses.fields(RevenueResult)}
    try:
        r = RevenueResult(**{c: 0 for c in campos})
    except Exception:                                    # pragma: no cover
        r = RevenueResult()
    expuestos = set(revenue_line_dict(r))
    no_mapeadas = expuestos - set(pl_engine.REVENUE_LINE_TO_REPORT_LINE)
    assert not no_mapeadas, f"ingresos sin línea de destino: {sorted(no_mapeadas)}"


def test_ningun_ingreso_se_pierde_aunque_falte_su_linea(mappings, report_lines):
    """El Sustainability Fee apuntaba a REV_SUSTAINABILITY, línea que NO existe en el
    reporte (ahí se llama REV_MISC_OTHER) → ese ingreso desaparecía del P&L.
    El motor ahora repliega cualquier ingreso huérfano a «otros ingresos»: el total
    de ingresos nunca puede perder plata."""
    import dataclasses
    from app.engine.revenue_calculator import RevenueResult

    campos = {f.name for f in dataclasses.fields(RevenueResult)}
    base_kwargs = {c: 0 for c in campos}
    r = RevenueResult(**{**base_kwargs, "sustainability": Decimal("750")})
    res = pl_engine.calculate_budget_pl_from_mapping(
        [], mappings, report_lines,
        revenue_by_line={"rooms": Decimal("0"), "sustainability": Decimal("750")})
    tot = {L.line_code: float(L.amount_usd) for L in res}
    assert round(tot["TOTAL_REVENUES"], 2) == 750.0, (
        "el ingreso de Sustainability Fee se perdió en el camino al P&L")
    assert round(tot.get("REV_MISC_OTHER", 0), 2) == 750.0, (
        "no se replegó a la línea de otros ingresos")


def test_below_gop_con_linea_inexistente_no_llega(mappings, report_lines):
    """Gastos del propietario siembran la línea por código. Si el código no existe,
    el monto NO llega al P&L — el tab de Control lo marca como «se pierde»."""
    codigos = {r["line_code"] for r in report_lines}
    assert "RENT" in codigos, "cambió el catálogo de líneas: revisá esta prueba"
    base = _pl([], mappings, report_lines)
    bueno = _pl([], mappings, report_lines, seed_amounts={"RENT": Decimal("500")})
    malo = _pl([], mappings, report_lines, seed_amounts={"LINEA_QUE_NO_EXISTE": Decimal("500")})
    assert round(bueno.get("RENT", 0) - base.get("RENT", 0), 2) == 500.0
    assert "LINEA_QUE_NO_EXISTE" not in malo, "una línea inexistente apareció en el P&L"


def test_todas_las_cuentas_de_planilla_tienen_regla_en_cada_depto(mappings, report_lines):
    """Los conceptos de planilla × cada depto con nómina deben resolver por regla
    EXACTA (si no, el monto cae en otra línea o se pierde)."""
    from app.engine.recalculate import PAYROLL_ALL_COLS
    exact = {(m["dept_code"], m["account_code"]) for m in mappings if m["dept_code"]}
    faltan = []
    for dept in ("0110", "0120", "0140", "0150", "0180", "0190", "0200"):
        for col in PAYROLL_ALL_COLS:
            acct = pl_engine.payroll_account_for_column(col)
            if acct in HUECO_CERRADO_POR_MIG_071:
                continue
            if (dept, acct) not in exact:
                faltan.append(f"{dept}/{acct}")
    assert not faltan, f"sin regla exacta (depto/cuenta): {faltan[:20]}"


def test_el_hueco_de_incapacidades_esta_documentado(mappings):
    """6004 (Incapacidades) se captura en la planilla pero no venía mapeado: sin la
    migración 071 ese monto no llega al P&L. Este test vigila que, si alguien
    quita la migración, el hueco se vuelva visible en vez de pasar desapercibido."""
    exact = {(m["dept_code"], m["account_code"]) for m in mappings if m["dept_code"]}
    sin_regla = {a for a in HUECO_CERRADO_POR_MIG_071
                 if ("0110", a) not in exact}
    assert sin_regla == HUECO_CERRADO_POR_MIG_071, (
        "el archivo de configuración ya trae estas cuentas: actualizá "
        "HUECO_CERRADO_POR_MIG_071 y revisá que la migración siga siendo idempotente")
