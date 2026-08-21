# -*- coding: utf-8 -*-
"""
LA MISMA CUENTA EN CUATRO OUTLETS NO SE PISA.

El GL de A&B trae la misma cuenta una vez por punto de venta:

    4110  Food1   Outlet 1   Ingreso Food   Departamento de A&B
    4110  Food    Outlet 2   Ingreso Food   Departamento de A&B
    4110  Food    Outlet 3   …
    4110  Food    Outlet 4   …

`actual_entries` no podía representarlo: la llave única era
`(scenario_id, dept_code, account_code)`, así que las cuatro filas colisionaban
en una sola. Y los dos escritores **asignan** el mes en vez de acumularlo, o sea
que sobrevivía la última y la plata de los otros tres outlets desaparecía **sin
dar error**.

Hoy no se rompía porque los Outlets 2, 3 y 4 vienen en CERO (confirmado con el
owner el 2026-08-12) y el importador salta las filas sin monto. Esto es la
previsión para el día que se llenen — decisión de contabilidad, no del sistema.

Ningún reporte lee `outlet` todavía: se guarda para que el dato entre con su
dimensión sin re-importar y sin perder el arranque del histórico.
"""
from app.models.actual_entry import ActualEntry


def test_el_outlet_esta_en_la_llave_unica():
    """Sin esto, cuatro outlets de la misma cuenta son una sola fila."""
    uq = next(c for c in ActualEntry.__table__.constraints
              if getattr(c, "name", "") == "uq_actual_entry")
    columnas = [c.name for c in uq.columns]
    assert columnas == ["scenario_id", "dept_code", "account_code", "outlet"], columnas


def test_el_outlet_por_defecto_es_vacio():
    """Todo lo que no sea A&B no se abre por outlet — y lo ya cargado tampoco."""
    col = ActualEntry.__table__.columns["outlet"]
    assert col.default.arg == ""
    assert not col.nullable
    # 'Outlet 1'..'Outlet 4' entran de sobra
    assert col.type.length >= 40


def test_el_importador_detecta_la_columna_outlet():
    """Se busca por RÓTULO. Si nadie la trae, no se inventa nada."""
    from app.importers.gl_detail_importer import _detect_outlet_col, VERSION_ROW

    def hoja(rotulos):
        def cell(r0, c1):
            if r0 != VERSION_ROW - 1:
                return None
            return rotulos.get(c1)
        return cell

    # archivo con la columna
    assert _detect_outlet_col(hoja({1: "Cuenta", 2: "Nombre", 3: "Outlet"}), 5) == 3
    assert _detect_outlet_col(hoja({2: "OUTLET / Venue"}), 5) == 2
    # archivo sin la columna → None, y el importador guarda ''
    assert _detect_outlet_col(hoja({1: "Cuenta", 2: "Departamento"}), 5) is None
