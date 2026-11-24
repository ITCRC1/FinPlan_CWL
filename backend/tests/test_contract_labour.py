"""Contract Labour (cuenta 6031).

Owner, 2026-11-22: «necesito crear una cuenta que se llame Contract Labour que no
forme parte del cálculo de la CCSS y Aguinaldo pero que agrupe en Salaries»; «debe
existir en todos los departamentos, y usualmente son en USD»; «cuando se crea la
posición debe haber un check donde se indique que es contract labour»; y una
columna en el Excel que lo diga.

Decisiones del owner: cuenta 6031; se marca por posición; y la posición de contrato
queda fuera de TODO (CCSS, aguinaldo, vacaciones, INS, beneficios).
"""
import io
from decimal import Decimal
from types import SimpleNamespace

import openpyxl

from app.engine import pl_engine
from app.engine.payroll_calculator import (calc_base, recalculate_entry, repartir_beneficio,
                                           summarize_dept, total_entry)
from app.export.payroll_excel import (COL_CL, HEADER_ROW, export_payroll_to_excel,
                                      import_payroll_from_excel)
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_position import PayrollPosition, a_bool, es_contrato

MESES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
CERO = Decimal("0")


def _pos(cl, salario="2500", moneda="USD"):
    return PayrollPosition(id="p", dept_code="0230", position_name="IT Support",
                           salary_amount=Decimal(salario), salary_currency=moneda,
                           contract_labour=cl, **{f"fte_{m}": Decimal("1") for m in MESES})


def _fila():
    return PayrollConceptEntry(**{c.name: CERO for c in PayrollConceptEntry.__table__.columns
                                  if c.name.startswith("c60")})


def _params():
    return SimpleNamespace(overtime_pct=Decimal("0.05"), bonus_pct=CERO, vacaciones_rate=Decimal("0.04"),
                           severance_annual_rate=Decimal("0.05"), transport_monthly_crc=Decimal("10000"),
                           housing_monthly_crc=CERO, other_monthly_crc=CERO,
                           mes=lambda k, m: {"calendar_days": 31, "holidays": 1, "days_off": 0}[k])


def test_la_posicion_de_contrato_va_a_6031_y_no_genera_cargas():
    e = recalculate_entry(_fila(), _pos(True), 1, Decimal("500"), params=_params())
    assert e.c6031_contract_labour == Decimal("2500.00")
    assert e.c6000_sw == CERO and e.c6020_ccss == CERO and e.c6021_aguinaldo == CERO
    assert e.c6023_vacation_prov == CERO and e.c6026_severance == CERO
    assert e.c6001_overtime == CERO and e.c6003_working_holiday == CERO
    assert e.c6029_transport == CERO
    assert calc_base(e) == CERO               # fuera de la BASE
    assert total_entry(e) == Decimal("2500.00")


def test_en_colones_tambien_se_convierte_con_el_tc():
    e = recalculate_entry(_fila(), _pos(True, "500000", "CRC"), 1, Decimal("500"))
    assert e.c6031_contract_labour == Decimal("1000.00")


def test_la_posicion_normal_sigue_igual_y_6031_queda_en_cero():
    e = _fila()
    e.c6031_contract_labour = Decimal("99")
    recalculate_entry(e, _pos(False), 1, Decimal("500"))
    assert e.c6000_sw == Decimal("2500.00") and e.c6031_contract_labour == CERO
    assert e.c6020_ccss > CERO and e.c6021_aguinaldo > CERO


def test_desmarcar_el_check_devuelve_el_salario_a_6000():
    e = recalculate_entry(_fila(), _pos(True), 1, Decimal("500"))
    recalculate_entry(e, _pos(False), 1, Decimal("500"))
    assert e.c6031_contract_labour == CERO and e.c6000_sw == Decimal("2500.00")


def test_el_contratista_no_recibe_reparto_de_ins():
    normal, contrato = _pos(False), _pos(True)
    fn, fc = _fila(), _fila()
    fn.month = fc.month = 1
    repartido = repartir_beneficio([(fn, normal), (fc, contrato)], "c6022_occ_hazard",
                                   Decimal("1000"), {1: Decimal("1")})
    assert fc.c6022_occ_hazard == CERO
    assert fn.c6022_occ_hazard == Decimal("1000.00") == repartido


def test_el_resumen_del_depto_la_suma_al_total_pero_no_a_la_base():
    e = recalculate_entry(_fila(), _pos(True), 1, Decimal("500"))
    s = summarize_dept([e], "0230", 1, 2027)
    assert s.c6031 == Decimal("2500.00") and s.base == CERO and s.total == Decimal("2500.00")


def test_en_el_pl_va_donde_va_6000_del_mismo_depto():
    """Sin el alias, la 6031 (que solo tiene regla en Tours) caía por descarte en
    Tours para TODOS los deptos."""
    reglas = [
        {"dept_code": "0230", "account_code": "6000", "report_line_code": "OH_IT"},
        {"dept_code": "0110", "account_code": "6000", "report_line_code": "OPEX_ROOMS"},
        {"dept_code": "0150", "account_code": "6031", "report_line_code": "OPEX_TOURS"},
    ]
    resolve = pl_engine.construir_resolvedor(reglas)
    assert resolve("0230", "6031")[0]["report_line_code"] == "OH_IT"
    assert resolve("0110", "6031")[0]["report_line_code"] == "OPEX_ROOMS"
    assert resolve("0150", "6031")[0]["report_line_code"] == "OPEX_TOURS"   # la regla propia manda


def test_el_check_y_lo_que_se_escribe_en_el_excel():
    assert es_contrato(_pos(True)) and not es_contrato(_pos(False))
    for si in ("Sí", "si", "x", "1", True, "Yes"):
        assert a_bool(si)
    for no in ("No", "", None, False, "0"):
        assert not a_bool(no)


def test_el_excel_trae_la_columna_x_y_vuelve_a_subir():
    def p(nombre, cl):
        return {"dept_name": "", "position_code": "0230-01", "position_name": nombre,
                "employee_name": "VACANTE", "employee_type": "1-Permanente",
                "salary_amount": 2500, "salary_currency": "USD", "categoria": None,
                "subcategoria": None, "contract_labour": cl, **{f"fte_{m}": 1.0 for m in MESES}}
    xlsx = export_payroll_to_excel({"0230": [p("IT Support", True), p("IT Manager", False)]},
                                   "CWL Working", 2027, tc_por_mes=[500.0] * 12)
    ws = openpyxl.load_workbook(io.BytesIO(xlsx)).worksheets[0]
    assert ws.cell(HEADER_ROW, COL_CL).value == "Contract Labour"
    filas = {r["position_name"]: r["contract_labour"] for r in import_payroll_from_excel(xlsx)}
    assert filas == {"IT Support": True, "IT Manager": False}


def test_la_moneda_del_excel_se_puede_cambiar_y_entra():
    """«Cómo le cambio la moneda y el monto del salario»: la H estaba bloqueada."""
    from app.export.payroll_excel import COL_CUR
    p = {"dept_name": "", "position_code": "0190-02", "position_name": "Director",
         "employee_name": "X", "employee_type": "1-Permanente", "salary_amount": 2000000,
         "salary_currency": "CRC", "contract_labour": True, **{f"fte_{m}": 1.0 for m in MESES}}
    wb = openpyxl.load_workbook(io.BytesIO(export_payroll_to_excel(
        {"0190": [p]}, "CWL Working", 2027, tc_por_mes=[500.0] * 12)))
    ws = wb.worksheets[0]
    fila = HEADER_ROW + 1
    assert ws.cell(fila, COL_CUR).protection.locked is False
    ws.cell(fila, COL_CUR).value = "USD"
    ws.cell(fila, 7).value = 4000
    buf = io.BytesIO(); wb.save(buf)
    r = import_payroll_from_excel(buf.getvalue())[0]
    assert r["salary_currency"] == "USD" and float(r["salary_amount"]) == 4000


# ── FTE 0 = no hay nadie ese mes ─────────────────────────────────────────────
# Owner, 2026-11-24, por el JORNALERO de 0205 (salario 0, FTE 0, con $3,408 de
# horas extra y cargas): «el headcount es 0, no debería tomarse en cuenta».

def test_un_mes_con_fte_cero_queda_todo_en_cero_aunque_traiga_horas_extra():
    p = _pos(False, "430000", "CRC")
    p.fte_may = CERO
    e = _fila()
    e.c6001_overtime = Decimal("382.65")
    recalculate_entry(e, p, 5, Decimal("500"))
    assert total_entry(e) == CERO
    assert e.c6020_ccss == CERO and e.c6001_overtime == CERO


def test_la_posicion_sintetica_gl_no_se_toca():
    """La planilla real importada vive en la posición «GL» con FTE 0: no es una vacante."""
    from app.engine.payroll_calculator import sin_gente
    gl = _pos(False, "0")
    gl.position_code = "GL"
    gl.fte_jan = CERO
    assert not sin_gente(gl, 1)


# ── 2026-11-24: comisiones, headcount y cafetería de los externos ───────────
# Owner: «yo había puesto comisiones al departamento 0190 en payroll pero ya no
# están» (el Director de Ventas es de contrato) y «tienen FTE, cuentan, pero son
# externos».

def test_contrato_respeta_comisiones_y_bono():
    from decimal import Decimal as D
    from unittest.mock import MagicMock
    from app.engine.payroll_calculator import recalculate_entry, CONCEPT_COLS
    pos = MagicMock()
    pos.contract_labour = True
    pos.position_code = "0190-02"
    pos.salary_amount = D("8763"); pos.salary_currency = "USD"
    for m in ("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"):
        setattr(pos, f"fte_{m}", D("1"))
    entry = MagicMock()
    for c in CONCEPT_COLS:
        setattr(entry, c, D("0"))
    entry.c6010_commissions = D("1500")
    entry.c6027_incentive_bonus = D("200")
    entry.c6001_overtime = D("99")
    recalculate_entry(entry, pos, month=1, tc=D("500"))
    assert entry.c6010_commissions == D("1500")
    assert entry.c6027_incentive_bonus == D("200")
    assert entry.c6001_overtime == 0
    assert entry.c6020_ccss == 0 and entry.c6021_aguinaldo == 0
    assert entry.c6031_contract_labour == D("8763")


def test_reporte_fte_pone_los_externos_aparte():
    from decimal import Decimal as D
    from types import SimpleNamespace
    from app.engine.payroll_calculator import build_fte_report
    meses = ("jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec")
    def pos(code, cl):
        return SimpleNamespace(scenario_id="s", dept_code="0190", position_code=code,
                               contract_labour=cl, **{f"fte_{m}": D("1") for m in meses})
    r = build_fte_report([pos("0190-01", False), pos("0190-02", True), pos("0190-03", True)])
    assert r.by_dept["0190"][1] == D("1")
    assert r.totals[1] == D("1")
    assert r.externos_by_dept["0190"][1] == D("2")
    assert r.externos_totals[1] == D("2")


def test_cafeteria_no_reparte_a_externos():
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate._recalc_allocations)
    i = src.index("# cafetería distributed by FTE")
    assert "fuera_del_hotel(p)" in src[i:i + 600]


def test_uniformes_no_se_reparten_a_los_de_afuera():
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate._recalc_allocations)
    i = src.index("uni_fte: dict[str, Decimal] = {}")
    assert "fuera_del_hotel(p)" in src[i:i + 400]


def test_fuera_del_hotel():
    from types import SimpleNamespace as N
    from app.models.payroll_position import fuera_del_hotel
    # contrato, aunque su depto sea On Property
    assert fuera_del_hotel(N(contract_labour=True, subcategoria=None, dept_code="0111"))
    # Sistemas: no es contrato, pero Outside
    assert fuera_del_hotel(N(contract_labour=False, subcategoria="Outside", dept_code="0230"))
    # gente de planta en el hotel
    assert not fuera_del_hotel(N(contract_labour=False, subcategoria="On Property", dept_code="0111"))
