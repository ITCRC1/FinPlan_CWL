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


# ── Budget y Forecast al lado, apareados por NOMBRE ──────────────────────────

def test_el_apareo_es_por_nombre_y_no_por_codigo():
    """Owner, 2026-09-10: *«hay una forma de poner el detalle a la par de
    Budget y Forecast; estos fueron SUBIDOS, no se generaron por auxiliares»*.

    Tenia razon: su planilla esta por puesto en `PayrollConceptEntry`. Pero el
    codigo NO se puede usar: el Actual trae la posicion de Integrity (`501`) y
    el presupuesto la del checkbook (`0112-01`). Aparear por numero
    emparejaria puestos distintos SIN FALLAR, que es el modo de falla mas caro
    de esta app. Lo unico que comparten es como se llama el puesto.
    """
    from app.api.precierre_api import _llave_de_puesto as k
    # El mismo puesto escrito de dos maneras es el mismo puesto...
    assert k("Reservations Agent") == k("RESERVATIONS AGENT")
    assert k("FRONT DESK AGENT / RECEPTIONIST") == k("Front Desk Agent - Receptionist")
    assert k("Capitan de Barco") == k("CAPITÁN DE BARCO")
    # ...y uno distinto tiene que seguir siendo distinto.
    assert k("Reservations Agent Supervisora") != k("Reservations Agent")
    assert k("") == ""


def test_la_posicion_sintetica_del_gl_no_se_aparea():
    """`GL` es la posicion que inventa el importador del mayor para los
    actuales: no nombra a nadie. Aparearla metería toda la planilla de un
    departamento en una sola fila, con un nombre que no existe."""
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    i = src.index("async def _planilla_por_puesto")
    assert '== "GL"' in src[i:i + 1200]


def test_lo_que_no_aparea_se_muestra():
    """Un puesto presupuestado que este mes no se pago es justo lo que hay que
    ver. Y un nombre que no aparea delata que el puesto se llama distinto en
    los dos lados — esconderlo dejaria el total sin explicar."""
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    assert '"sin_pareja"' in src
    pant = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "..", "frontend",
                                  "app", "month-end", "pl", "Pantalla.tsx"),
                    encoding="utf-8").read()
    assert "d.sin_pareja.length > 0" in pant


def test_el_gasto_se_aparea_por_CODIGO_de_detalle():
    """Acá sí se aparea por código, y la diferencia importa.

    El checkbook de gasto usa las subcuentas 800-810 (CLAUDE.md §19.2) y el
    tercer nivel de Integrity usa la MISMA numeracion: es la misma llave en los
    dos sistemas, no dos que se parecen. (En planilla no se puede: el Actual
    trae `501` y el presupuesto `0112-01`.)
    """
    from app.api.precierre_api import _llave_detalle
    assert _llave_detalle("800") == "800"
    assert _llave_detalle(" 0800 ") == "800"     # el cero de adelante no cambia el detalle
    assert _llave_detalle(800) == "800"
    assert _llave_detalle("") == ""
    assert _llave_detalle("80A") == "80A"        # lo que no es numero se respeta


def test_el_total_de_la_cuenta_comparada_sale_de_la_cuenta_entera():
    """No de las filas que aparearon.

    El checkbook puede tener detalles que el mes no trajo. Sumar solo lo que
    apareo haria que la columna del presupuesto NO fuera el presupuesto — un
    numero mas chico, sin nada que lo delate.
    """
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    i = src.index("otros_cta = {sid: round(sum(")
    assert "if dc == dep_code and ac == cta[\"cuenta\"]" in src[i:i + 400]


def test_el_total_incluye_lo_que_ninguna_posicion_cobra():
    """Owner, 2026-09-10: *«que pegue a un vistazo»*.

    El detalle por posicion sale del mayor —US$227.497,60 en agosto—; Payroll
    x Cuenta dice US$251.819,00. La diferencia son los US$24.321,93 de la 6025
    Cafeteria, que NO EXISTE en el archivo de Integrity: no es planilla
    posteada, es el reparto que el sistema carga a cada departamento. Nadie la
    cobra, asi que no tiene posicion.

    Se agrega como linea rotulada en vez de repartirla entre los puestos:
    repartirla haria que el total pegara INVENTANDO plata que nadie cobro.

    El faltante se mide contra la MISMA fuente que usa Payroll x Cuenta
    —`PayrollConceptEntry` del espejo— asi que los dos tabs cierran en el mismo
    numero por construccion, no por coincidencia.
    """
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    i = src.index("sin_posicion: list[dict] = []")
    cuerpo = src[i:i + 2500]
    # Mide contra el espejo, que es de donde sale Payroll x Cuenta.
    assert "Scenario.es_precierre.is_(True)" in cuerpo
    assert "PayrollConceptEntry.month == mes" in cuerpo
    # El total suma las dos partes, y el desglose viaja para poder explicarlo.
    assert '"total_con_posicion"' in src and '"total_sin_posicion"' in src
    j = src.index('"total": round(float(sum(f.mes_usd for f in filas))')
    assert 'sum(r["monto"] for r in sin_posicion)' in src[j:j + 220]


def test_la_linea_del_reparto_se_rotula_y_no_se_reparte():
    """Una fila sin puesto tiene que DECIR que es un reparto. Dejarla con el
    nombre en blanco la haria pasar por un puesto sin nombre, que es otra cosa
    —esa existe y se llama «(sin nombre en el catalogo)»."""
    import io as _io
    import os as _os
    pant = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "..", "frontend",
                                  "app", "month-end", "pl", "Pantalla.tsx"),
                    encoding="utf-8").read()
    assert 'f.sin_posicion ? (' in pant
    assert 't("sinPosicion")' in pant
    assert 't("posicionSinNombre")' in pant     # la otra sigue existiendo


def test_una_cuenta_que_solo_tiene_el_presupuesto_igual_aparece():
    """Owner, 2026-09-10: *«si no tiene detalle, al menos pongamos el total»*.

    Una cuenta presupuestada que este mes no se movio no aparecia en ningun
    lado: ni su linea ni su plata. Eso hacia que la columna de Budget del
    DEPARTAMENTO fuera menor que el presupuesto de verdad — un numero mas
    chico, sin nada que lo delatara.

    Un gasto presupuestado que no se ejecuto es justo lo que una revision tiene
    que ver, asi que entra con el mes en cero y su total al lado.
    """
    import io as _io
    import os as _os
    src = _io.open(_os.path.join(_os.path.dirname(__file__), "..", "app", "api",
                                 "precierre_api.py"), encoding="utf-8").read()
    i = src.index("# ── Y las cuentas que SOLO tiene el presupuesto")
    cuerpo = src[i:i + 1400]
    # Recorre las versiones comparadas y siembra la cuenta que falte.
    assert "for mapa in comparar.values():" in cuerpo
    assert 'dep["cuentas"].setdefault(int(cta_code)' in cuerpo
    # Con `filas` vacia: no se inventa un detalle que el mes no trajo.
    assert '"filas": [], "detalle": Decimal("0")' in cuerpo
