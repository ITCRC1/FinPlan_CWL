# -*- coding: utf-8 -*-
"""
EL ADR NO PUEDE DEPENDER DE CUÁNDO SE APRETÓ RECALCULAR.

Owner, 2026-09-05: *«necesito que derives el ADR y todos los kpi que dependen de
recalculo»*.

`scenario_stats.adr` es una columna guardada que sólo se refresca en el
recálculo (`_persist_room_stats`). Entre que se mueve una tarifa y que se
recalcula, el P&L de doce meses mostraba un ADR viejo **al lado del ingreso
nuevo** — y el endpoint mensual, que sí deriva, mostraba otro número para el
mismo mes.

Estas pruebas fijan las cuatro reglas de `engine/kpis.py`. Ver
`docs/PENDIENTES.md` A4 para por qué el numerador nunca es la línea del P&L.
"""
from decimal import Decimal

from app.engine.kpis import kpis_de_habitaciones


def test_el_adr_sale_del_ingreso_y_no_del_guardado():
    """Con ingreso y noches, se deriva: el guardado queda ignorado.

    Es el caso que motivó todo — el guardado ($400) es de un recálculo viejo y
    el ingreso ya se movió.
    """
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
        ingreso_habitaciones=Decimal("100000"), adr_guardado=Decimal("400"),
    )
    assert k["adr"] == 500.0, "debía derivar 100.000 / 200, no arrastrar el 400"


def test_sin_ingreso_queda_el_guardado_y_no_un_cero():
    """El ACTUAL: la estadística viene del PMS y el ingreso puro no existe.

    ⚠️ Lo importante no es que respete el número: es que **no ponga cero**. Un
    cero se lee como dato, no como dato que falta. Es la regla de la casa —no
    inventar— aplicada al revés: tampoco borrar.
    """
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
        ingreso_habitaciones=None, adr_guardado=Decimal("477.34"),
    )
    assert k["adr"] == 477.34


def test_sin_noches_ocupadas_tampoco_se_fabrica_una_tarifa():
    """Sin denominador no hay tarifa: se respeta el guardado en vez de dividir."""
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("0"), guests=Decimal("0"),
        ingreso_habitaciones=Decimal("100000"), adr_guardado=Decimal("450"),
    )
    assert k["adr"] == 450.0
    assert k["occupancy_pct"] == 0.0


def test_la_ocupacion_sale_de_las_noches_aunque_la_columna_diga_otra_cosa():
    """`occupancy_pct` guardada podía no coincidir con las dos noches de SU MISMA
    fila. Mandan las noches."""
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("150"), guests=Decimal("300"),
        ingreso_habitaciones=Decimal("75000"),
        occupancy_guardada=Decimal("0.9"),   # vieja, de otro recálculo
    )
    assert k["occupancy_pct"] == 0.5


def test_el_revpar_sale_del_ingreso_TOTAL_y_ya_no_de_la_identidad():
    """⚠️ **La identidad `RevPAR = ADR × ocupación` se rompió A PROPÓSITO.**

    Owner, 2026-09-08: *«revpar es total revenue per available room»* · *«total
    revenue by total rooms available»*. Esta prueba comprobaba lo contrario —que
    los tres números cerraran entre ellos— y tenía razón mientras el RevPAR
    midiera ingreso DE HABITACIONES. Ahora mide todo lo que el hotel factura, así
    que ya no son el mismo indicador y no tienen por qué cerrar.
    """
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
        ingreso_habitaciones=Decimal("100000"), ingreso_total=Decimal("180000"),
    )
    assert k["adr"] == 500.0                     # 100.000 / 200 noches
    assert k["revpar"] == 600.0                  # 180.000 / 300 disponibles
    # Y NO la identidad vieja, que aquí habría dado 333,33.
    assert abs(k["revpar"] - k["adr"] * k["occupancy_pct"]) > 1


def test_sin_ingreso_total_el_revpar_da_CERO_y_no_el_numero_viejo():
    """⚠️ El respaldo NO cae al ingreso de habitaciones.

    Sería un número con el nombre del indicador nuevo y el valor del viejo, que
    es peor que no tenerlo: un cero se lee como «falta el dato», y un RevPAR
    calculado con la fórmula anterior se lee como un RevPAR.
    """
    k = kpis_de_habitaciones(
        rooms_available=300, rooms_occupied=Decimal("200"), guests=Decimal("380"),
        ingreso_habitaciones=Decimal("100000"),
    )
    assert k["adr"] == 500.0        # el ADR sí se deriva
    assert k["revpar"] == 0.0


def test_un_mes_cerrado_no_revienta():
    """Escenario vacío / mes cerrado: todo en cero y sin división por cero."""
    k = kpis_de_habitaciones(
        rooms_available=0, rooms_occupied=0, guests=0,
        ingreso_habitaciones=None, adr_guardado=None, occupancy_guardada=None,
    )
    assert k == {"rooms_available": 0, "rooms_occupied": 0.0, "guests": 0.0,
                 "occupancy_pct": 0.0, "adr": 0.0, "revpar": 0.0}
