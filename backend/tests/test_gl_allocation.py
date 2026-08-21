"""Regla de ALLOCATION (queda ESCRITA y blindada): aplica a todo mes/año/escenario.

- 0220 (Employee Dining / comida): allocation TOTAL → su costo(5)/planilla(6)/opex(7)
  NO entran a los totales operativos (netean a 0 vía Distribución).
- 0161 (Laundry): SPLIT → la lavandería interna (planilla 6 + insumos 7) es allocation;
  el Laundry Services que vende afuera (ingreso 4 + costo de venta 5) SE QUEDA operativo.

Si alguien cambia ALLOCATION_EXCLUDE y rompe esto, este test falla.
"""
import io
import openpyxl
from app.importers.gl_detail_importer import (
    parse_gl_detail, ALLOCATION_EXCLUDE, ALLOC_EXCL_COST,
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
