"""Regla de ALLOCATION (queda ESCRITA y blindada): aplica a todo mes/año/escenario.

- 0220 (Employee Dining / comida): allocation TOTAL → su costo(5)/planilla(6)/opex(7)
  NO entran a los totales operativos (netean a 0 vía Distribución).
- 0161 (Laundry): SPLIT → la lavandería interna (planilla 6 + insumos 7) es allocation;
  el Laundry Services que vende afuera (ingreso 4 + costo de venta 5) SE QUEDA operativo.

Si alguien cambia ALLOCATION_EXCLUDE y rompe esto, este test falla.

La ÚNICA excepción es el espejo del Pre-Cierre (owner, 2026-09-10: «los
allocations en overhead […] esta regla es solo para este tab»): ahí el gasto SÍ
entra, en su línea de overhead, porque esa pantalla existe para revisar y no se
puede permitir que se escape plata mientras la 4999 no está posteada. El P&L de
verdad no cambia. Lo blindan `test_precierre_ve_el_allocation_como_overhead` y
`test_el_modo_overhead_no_se_puede_pedir_desde_afuera`.
"""
import io
import openpyxl
from pathlib import Path
from app.importers.gl_detail_importer import (
    parse_gl_detail, allocation_en_overhead, ALLOCATION_EXCLUDE, ALLOC_EXCL_COST,
    ALLOC_EXCL_PAYROLL, ALLOC_EXCL_OPEX,
)


def _gl_book(rows):
    """rows: (clase_lbl, dept_name, account_code, account_name, valor_enero)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    # Fila 15 = rótulo del bloque · Fila 14 = mes (el parser detecta por ambos).
    ws.cell(row=15, column=5, value="Actual 2099")
    ws.cell(row=14, column=5, value="January")
    r = 17
    for cls_lbl, dept, code, name, jan in rows:
        ws.cell(row=r, column=1, value=cls_lbl)
        ws.cell(row=r, column=2, value=dept)
        ws.cell(row=r, column=3, value=code)
        ws.cell(row=r, column=4, value=name)
        ws.cell(row=r, column=5, value=jan)   # mes 1
        r += 1
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_allocation_rule_locked():
    """La regla exacta queda fijada en código."""
    assert ALLOCATION_EXCLUDE == {"0220": {"5", "6", "7"}, "0161": {"6", "7"}}
    assert ALLOC_EXCL_COST == {"0220"}
    assert ALLOC_EXCL_PAYROLL == {"0220", "0161"}
    assert ALLOC_EXCL_OPEX == {"0220", "0161"}


def test_allocation_applied_on_parse():
    data = _gl_book([
        ("Rev",  "Lavanderia",                  "4700", "Laundry Services rev", 100),
        ("Cost", "Lavanderia",                  "5603", "Laundry Services cost", 50),
        ("Pay",  "Lavanderia",                  "6000", "Laundry payroll",      200),
        ("Opex", "Lavanderia",                  "7320", "Laundry supplies",      80),
        ("Cost", "Cafeteria Empleados",         "5700", "Dining cost",          300),
        ("Pay",  "Cafeteria Empleados",         "6000", "Dining payroll",       150),
        ("Opex", "Cafeteria Empleados",         "7065", "Dining opex",           20),
        ("Pay",  "Departamento de Habitaciones", "6000", "Rooms payroll",       500),
    ])
    blk = parse_gl_detail(data)[0]
    def depts(key):
        return {r["dept_code"] for r in blk[key]}

    # 0220 (Cafeteria) — allocation TOTAL: nada en costo/planilla/opex
    assert "0220" not in depts("costs")
    assert "0220" not in depts("payroll")
    assert "0220" not in depts("opex")

    # 0161 (Laundry) — split: planilla/opex FUERA; ingreso/costo de venta DENTRO
    assert "0161" not in depts("payroll")
    assert "0161" not in depts("opex")
    assert "0161" in depts("revenue")
    assert "0161" in depts("costs")

    # Control: un depto operativo normal entra en planilla
    assert "0110" in depts("payroll")


# ── La excepción del Pre-Cierre ──────────────────────────────────────────────

class _Esc:
    def __init__(self, es_precierre):
        self.es_precierre = es_precierre


def test_el_modo_overhead_solo_lo_abre_el_espejo_del_precierre():
    """Ningún otro escenario —ni la ausencia de escenario— lo enciende."""
    assert allocation_en_overhead(_Esc(True)) is True
    assert allocation_en_overhead(_Esc(False)) is False
    assert allocation_en_overhead(None) is False       # sin destino explícito
    assert allocation_en_overhead(object()) is False   # escenario sin el campo


def test_precierre_ve_el_allocation_como_overhead():
    """Con `en_overhead` el gasto de 0220/0161 ENTRA, y el resto no se mueve."""
    data = _gl_book([
        ("Rev",  "Lavanderia",                  "4700", "Laundry Services rev", 100),
        ("Cost", "Lavanderia",                  "5603", "Laundry Services cost", 50),
        ("Pay",  "Lavanderia",                  "6000", "Laundry payroll",      200),
        ("Opex", "Lavanderia",                  "7320", "Laundry supplies",      80),
        ("Cost", "Cafeteria Empleados",         "5700", "Dining cost",          300),
        ("Pay",  "Cafeteria Empleados",         "6000", "Dining payroll",       150),
        ("Opex", "Cafeteria Empleados",         "7065", "Dining opex",           20),
        ("Pay",  "Departamento de Habitaciones", "6000", "Rooms payroll",       500),
    ])
    blk = parse_gl_detail(data, en_overhead=True)[0]
    def depts(key):
        return {r["dept_code"] for r in blk[key]}

    # Lo que en el P&L de verdad desaparece, acá se ve:
    assert "0220" in depts("costs")
    assert "0220" in depts("payroll")
    assert "0220" in depts("opex")
    assert "0161" in depts("payroll")
    assert "0161" in depts("opex")
    # Y no se descartó ni una fila por allocation.
    assert blk["skipped"].get("allocation", 0) == 0
    # El operativo normal sigue igual: el modo no reacomoda nada más.
    assert "0110" in depts("payroll")
    assert "0161" in depts("revenue") and "0161" in depts("costs")


def test_el_modo_overhead_no_se_puede_pedir_desde_afuera():
    """El modo lo decide el DESTINO, no quien llama.

    Si algún día se expone como parámetro de la ruta, cualquier curl podría
    meter el gasto de allocation al Actual y el P&L seguiría cuadrando consigo
    mismo — el modo de falla más caro del sistema. Por eso se deriva del
    escenario y por eso este test mira el código fuente.
    """
    src = Path("app/api/scenarios_api.py").read_text(encoding="utf-8")
    assert "parse_gl_detail(data, en_overhead=allocation_en_overhead(forced))" in src
    assert "en_overhead: bool = Query" not in src
    assert "en_overhead=True" not in src   # nadie lo fija a mano
