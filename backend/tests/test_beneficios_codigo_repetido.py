"""Excel de beneficios: un código de puesto repetido no puede pisar a los demás.

Owner, 2026-11-28, al cargar el overtime del B27 Working: 0150-13 tiene tres
personas (Aldo, María del Mar, un Nature Guide) y 0183-02 dos. Con la llave
depto + código, las tres filas caían en la misma posición y cada una pisaba a la
anterior: US$ 2,715 de overtime se perdían sin aviso.
"""
from decimal import Decimal
from types import SimpleNamespace as P

from app.api.payroll_api import posicion_de_la_fila
from app.export.beneficios_excel import export_beneficios, import_beneficios

POS = [
    P(id="a", dept_code="0150", position_code="0150-13", position_name="DIVEMASTER", employee_name="ALDO"),
    P(id="b", dept_code="0150", position_code="0150-13", position_name="VIDEMASTER", employee_name="MARIA DEL MAR"),
    P(id="c", dept_code="0150", position_code="0150-13", position_name="NATURE GUIDE", employee_name="TBD"),
    P(id="d", dept_code="0183", position_code="0183-02", position_name="WAREHOUSE CLERK", employee_name="TBD"),
    P(id="e", dept_code="0183", position_code="0183-02", position_name="WAREHOUSE CLERK", employee_name="TBD"),
    P(id="f", dept_code="0111", position_code="0111-01", position_name="FRONT DESK AGENT", employee_name="GINA"),
]


def _fila(p, monto):
    return {"dept_code": p.dept_code, "dept_name": "", "position_code": p.position_code,
            "position_name": p.position_name, "employee_name": p.employee_name,
            "meses": [Decimal(monto)] * 12}


def test_cada_fila_va_a_su_persona_aunque_el_codigo_se_repita():
    xlsx = export_beneficios({"c6001_overtime": [_fila(p, i + 1) for i, p in enumerate(POS)]},
                             "CWL Working", 2027)
    filas = import_beneficios(xlsx)[0]["c6001_overtime"]
    usadas, destino = set(), {}
    for f in filas:
        p = posicion_de_la_fila(f, POS, usadas)
        assert p is not None, f
        usadas.add(p.id)
        destino[p.id] = f["meses"][0]
    # Seis filas, seis posiciones distintas, cada monto en la suya.
    assert destino == {p.id: Decimal(i + 1) for i, p in enumerate(POS)}


def test_el_codigo_unico_sigue_amarrando_solo_por_llave():
    f = {"dept_code": "0111", "position_code": "0111-01", "meses": [Decimal(1)] * 12}
    assert posicion_de_la_fila(f, POS, set()).id == "f"      # archivos viejos sin nombre


def test_repetido_sin_forma_de_desempatar_no_adivina():
    f = {"dept_code": "0150", "position_code": "0150-13", "position_name": "OTRO",
         "employee_name": "NADIE", "meses": [Decimal(1)] * 12}
    assert posicion_de_la_fila(f, POS, set()) is None        # va a «filas sin puesto»
