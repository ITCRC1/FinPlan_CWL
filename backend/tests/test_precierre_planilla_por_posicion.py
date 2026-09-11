# -*- coding: utf-8 -*-
"""LA PLANILLA DEL MES, ABIERTA POR POSICION.

Owner, 2026-09-10: *«le metemos departamento, cuenta y posicion — la posicion
en las cuentas 6 es el tercer nivel»* · *«eso solo para actuales del mes»* ·
*«y pones el nombre de la posicion»*.

En Integrity una cuenta de planilla es `6000-0111-501-013-015-00-00`: concepto,
departamento y POSICION (CLAUDE.md §12.1). El lector guardaba solo el nivel
`concepto-departamento` y sumaba el resto sin conservar el codigo, asi que no
habia forma de contestar «cuanto costaron los Room Attendants este mes».

El dato SIEMPRE estuvo en el archivo. Lo que faltaba era guardarlo.
"""
import io

import openpyxl
import pytest
from decimal import Decimal

from app.importers import integrity_final as m

TC = Decimal("500")
PUENTE = {"0111": {"nombre_integrity": "Front Desk", "destino_finplan": "0110"},
          "0113": {"nombre_integrity": "Housekeeping", "destino_finplan": "0110"}}


def _libro(filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Cuenta", "Descripción", "Mes Actual", "Acumulado"])
    for f in filas:
        ws.append(f)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


#: El padre y sus dos posiciones, como los entrega Integrity: el padre YA suma
#: a los hijos, y los hijos repiten el mismo dinero abierto.
LIBRO = [
    ["6000-0111", "SALARIES AND WAGES FRONT DESK", "300000", "300000"],
    ["6000-0111-501", "SALARIES AND WAGES FRONT DESK AGENT", "200000", "200000"],
    ["6000-0111-503", "SALARIES AND WAGES FRONT DESK SUPERVISOR", "100000", "100000"],
    ["6000-0113", "SALARIES AND WAGES HOUSEKEEPING", "50000", "50000"],
    ["6000-0113-508", "SALARIES AND WAGES ROOM ATTENDANT", "50000", "50000"],
]


def test_la_posicion_es_el_tercer_nivel_y_trae_su_nombre():
    r = m.leer(_libro(LIBRO), TC, PUENTE)
    pos = r["posiciones"]
    assert len(pos) == 3

    agente = next(p for p in pos if p["posicion"] == "501")
    assert agente["cuenta"] == "6000-0111-501"
    assert agente["cuenta_base"] == 6000          # el concepto de nomina
    assert agente["depto"] == "0111"              # el de Integrity
    assert agente["destino_finplan"] == "0110"    # traducido a FinPlan
    # El codigo `501` solo no le dice nada a nadie: el nombre viene con el.
    assert "FRONT DESK AGENT" in agente["descripcion"]


def test_las_posiciones_suman_EXACTAMENTE_su_cuenta():
    """No es un total nuevo: es el mismo, abierto.

    Si el nivel de posicion no sumara su cuenta, el reporte nuevo y el de
    planilla por departamento dirian cosas distintas — y cada uno cuadraria
    consigo mismo, que es como este sistema falla caro.
    """
    r = m.leer(_libro(LIBRO), TC, PUENTE)
    por_posicion = sum(p["mes_usd"] for p in r["posiciones"])
    por_cuenta = sum(f["mes_usd"] for f in r["filas"]
                     if str(f["cuenta_base"]).startswith("6"))
    assert por_posicion == por_cuenta == Decimal("700")   # 350000 / 500


def test_el_nivel_de_posicion_no_entra_a_los_totales():
    """El padre ya lo suma. Si las filas de posicion tambien entraran a
    `filas`, la planilla del mes saldria al doble y cuadraria consigo misma."""
    r = m.leer(_libro(LIBRO), TC, PUENTE)
    cuentas = [f["cuenta"] for f in r["filas"]]
    assert cuentas == ["6000-0111", "6000-0113"]
    assert all(c.count("-") == 1 for c in cuentas)


def test_solo_las_cuentas_6_traen_posicion():
    """En una 4xxx el tercer nivel es el SEGMENTO DE MERCADO, no una posicion.
    Llamarlo «posicion» pondria un nombre falso sobre un dato real."""
    libro = LIBRO + [
        ["4000-0110", "ROOMS", "900000", "-900000"],
        ["4000-0110-001", "ROOMS RETAIL TRANSIENT", "900000", "-900000"],
    ]
    puente = {**PUENTE, "0110": {"nombre_integrity": "Hab",
                                 "destino_finplan": "0110"}}
    r = m.leer(_libro(libro), TC, puente)
    assert all(p["cuenta"].startswith("6") for p in r["posiciones"])
    assert len(r["posiciones"]) == 3


def test_la_ruta_lleva_anio_y_mes_en_el_path():
    """`/precierre/{precierre_id}/` se registra ANTES. Con el año y el mes en
    el query, la ruta habria entrado por ahi con
    `precierre_id="planilla-por-posicion"` y contestado 404 sin decir por que.
    """
    from app.api.precierre_api import router
    rutas = [getattr(r, "path", "") for r in router.routes]
    assert "/precierre/planilla-por-posicion/{anio}/{mes}/" in rutas
    assert "/precierre/planilla-por-posicion/" not in rutas


def test_vive_en_su_propia_tabla():
    """Todo lo que consume `precierre_fila` SUMA `mes_usd`. El subdetalle en la
    misma tabla duplicaria cada monto y la consulta que se olvidara de filtrar
    no fallaria: daria un numero mas alto y cuadraria consigo misma."""
    from app.models.precierre import PrecierreFila, PrecierrePosicion
    assert PrecierrePosicion.__tablename__ != PrecierreFila.__tablename__
    cols = set(PrecierrePosicion.__table__.columns.keys())
    assert {"posicion", "cuenta", "depto", "destino_finplan", "descripcion",
            "mes_usd"} <= cols
    # No lleva acumulado: es el detalle DEL MES (owner: «solo para actuales
    # del mes»), y un acumulado por posicion invitaria a sumarlo con el otro.
    assert "acumulado_usd" not in cols


# ── El NOMBRE de la posicion ─────────────────────────────────────────────────

def test_el_catalogo_traduce_el_codigo_de_posicion():
    """Owner, 2026-09-10: *«en algun lugar tienes el nombre de la posicion»*.

    Lo tenia: la hoja `Planning` del catalogo del grupo. `501` es
    «FRONT DESK AGENT / RECEPTIONIST». El codigo solo no le dice nada a nadie.
    """
    from app.api.precierre_api import _catalogo_de_posiciones
    cat = _catalogo_de_posiciones()
    assert len(cat) >= 100
    assert cat["501"] == "FRONT DESK AGENT / RECEPTIONIST"
    assert cat["508"].startswith("ROOM ATTENDANT")


def test_no_se_puede_cruzar_por_codigo_con_el_checkbook():
    """Owner: *«aca en planning se nombra la posicion pero tiene otro
    control»*. El checkbook usa `0112-01`; Integrity usa `501`. Por eso el
    nombre se declara en un archivo y no sale de un join — un join por codigo
    emparejaria puestos distintos sin fallar."""
    from app.api.precierre_api import _catalogo_de_posiciones
    assert all(c.isdigit() for c in _catalogo_de_posiciones())


def test_le_saca_el_concepto_a_la_descripcion():
    """El mayor repite el concepto en cada fila; el concepto ya tiene su
    columna. Lo que queda es el puesto — y cuando no queda nada, nada."""
    from app.api.precierre_api import _sin_el_concepto
    assert _sin_el_concepto("SALARIES AND WAGES FRONT DESK AGENT") == "FRONT DESK AGENT"
    assert _sin_el_concepto("SALARY AND WAGES NATURALIST GUIDE") == "NATURALIST GUIDE"
    assert _sin_el_concepto("OVERTIME") == ""
    # Integrity escribe el mismo concepto de varias formas: por eso la lista
    # se declara y no se deduce de un prefijo comun (se probo: da vacio).
    assert _sin_el_concepto("WAGES AND SALARIES ROOM ATTENDANT") == "ROOM ATTENDANT"


def test_el_respaldo_del_mayor_sale_SOLO_de_la_linea_de_salario():
    """La 6000 es la que nombra el puesto. Las demas repiten el concepto o
    traen variantes que no son un puesto —«13th Sal Mandatory»— y esa, por ser
    mas larga, le ganaria al nombre de verdad."""
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    i = src.index("del_mayor: dict[str, str] = {}")
    assert "if f.cuenta_base != 6000:" in src[i:i + 400]


# ── El gemelo del gasto: el tercer nivel de las 7xxx ─────────────────────────

def test_el_tercer_nivel_tambien_se_guarda_para_el_gasto():
    """Owner, 2026-09-10: *«te vas al tercer nivel de gastos, 7310-0110-800
    ROOMS / LAUNDRY AND DRY CLEANING»*.

    Es el MISMO segmento que la posicion: en las 6 es el puesto, en las 7 es el
    detalle del gasto. Una sola lectura, un solo lugar donde guardarlo.
    """
    libro = [
        ["7310-0110", "ROOMS / LAUNDRY AND DRY CLEANING", "600000", "600000"],
        ["7310-0110-800", "ROOMS / LAUNDRY AND DRY CLEANING", "600000", "600000"],
        ["6000-0111", "SALARIES AND WAGES FRONT DESK", "100000", "100000"],
        ["6000-0111-501", "SALARIES AND WAGES FRONT DESK AGENT", "100000", "100000"],
    ]
    puente = {**PUENTE, "0110": {"nombre_integrity": "Hab",
                                 "destino_finplan": "0110"}}
    r = m.leer(_libro(libro), TC, puente)
    clases = {str(p["cuenta_base"])[0] for p in r["posiciones"]}
    assert clases == {"6", "7"}
    gasto = next(p for p in r["posiciones"] if str(p["cuenta_base"]) == "7310")
    assert gasto["posicion"] == "800"
    assert gasto["destino_finplan"] == "0110"
    assert gasto["mes_usd"] == Decimal("1200")     # 600000 / 500


def test_el_gasto_por_detalle_cierra_contra_el_total_de_la_cuenta():
    """El endpoint agrega «(sin detalle)» cuando el detalle no da su cuenta.

    Hoy no hay ningun caso: las 1.020 relaciones padre-hijo del archivo de
    agosto 2026 cuadran al centavo. El renglon es una RED, no un hallazgo.

    Un primer barrido dijo que ocho no cuadraban —entre ellas `7105-0180` por
    US$11.196,00— y estaba MAL MEDIDO: sumaba la columna del mes en crudo, sin
    la regla de signo. Un ingreso viene con el acumulado en negativo y una
    DEVOLUCION en positivo, asi que en crudo se contaba al reves. Con
    `monto_mes` las ocho desaparecen.
    """
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    i = src.index("async def gasto_por_detalle")
    cuerpo = src[i:]
    assert '"(sin detalle)"' in cuerpo
    # El total manda el nivel que suma el P&L, no la suma del detalle.
    assert "totales_cuenta.get((dep_code, base), cta[\"detalle\"])" in cuerpo
    # Y las cuentas sin detalle entran igual, o el total por departamento
    # dejaria de ser el del P&L.
    assert "Las cuentas del P&L que NO tienen detalle" in cuerpo
