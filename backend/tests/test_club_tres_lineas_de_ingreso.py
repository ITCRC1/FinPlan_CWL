# -*- coding: utf-8 -*-
"""Las tres líneas de ingreso del Club, amarradas a su cuenta.

    4500  Ingreso Madresal Club    ← la cuota (driver: socios × precio)
    4501  Actividad fin de año     ← se digita
    4502  Visitantes               ← se digita

El riesgo que vigila este archivo no es que el total salga mal —las tres suman
en `REV_CLUB` y el total cuadra igual— sino que los **rótulos del checkbook se
separen del catálogo**. Si alguien renombra una línea acá y no en
`mapping_pl.json`, el reporte cuenta por cuenta dice una cosa y la pantalla de
carga otra, y nadie se entera hasta que no cuadra contra la contabilidad.
"""
import io
import json
import os

from app.models.revenue_entry import (
    REVENUE_LINE_ACCOUNT, REVENUE_LINE_LABELS, REVENUE_LINES)

DEPTO_CLUB_EN_EL_MAPEO = "Departamento de Club Madresal"
LINEAS = ("CLUB", "CLUB_ACTIVIDAD", "CLUB_VISITANTES")


def _mapeo():
    ruta = os.path.join(os.path.dirname(__file__), "..", "app", "seed_data",
                        "mapping_pl.json")
    return json.loads(io.open(ruta, encoding="utf-8").read())["account_mapping"]


def test_las_tres_lineas_existen_en_el_checkbook():
    for ln in LINEAS:
        assert ln in REVENUE_LINES, f"{ln} no está en el checkbook de ingresos"


def test_cada_linea_declara_su_cuenta():
    assert REVENUE_LINE_ACCOUNT["CLUB"] == ("260", "4500")
    assert REVENUE_LINE_ACCOUNT["CLUB_ACTIVIDAD"] == ("260", "4501")
    assert REVENUE_LINE_ACCOUNT["CLUB_VISITANTES"] == ("260", "4502")


def test_los_nombres_son_los_del_catalogo_no_una_invencion():
    """El rótulo que ve el owner al cargar tiene que ser el mismo que sale en el
    reporte cuenta por cuenta. La fuente es `mapping_pl.json`, no este código."""
    delmapeo = {
        r["account_code"]: r["account_name_example"]
        for r in _mapeo()
        if r.get("source_department") == DEPTO_CLUB_EN_EL_MAPEO
        and str(r.get("account_code")) in ("4500", "4501", "4502")
    }
    assert len(delmapeo) == 3, f"el mapeo no tiene las tres cuentas: {delmapeo}"
    for ln in LINEAS:
        cuenta = REVENUE_LINE_ACCOUNT[ln][1]
        assert REVENUE_LINE_LABELS[ln] == delmapeo[cuenta], (
            f"{ln}: el checkbook dice «{REVENUE_LINE_LABELS[ln]}» y el catálogo "
            f"«{delmapeo[cuenta]}»")


def test_las_tres_van_a_la_misma_linea_del_pl():
    """Partir la línea es para el detalle por cuenta, no para partir el P&L:
    las tres caen en REV_CLUB igual que food/beverage/fnb_misc caen en REV_FB."""
    from app.engine.pl_engine import (
        REVENUE_LINE_TO_GROUP, REVENUE_LINE_TO_REPORT_LINE)
    for campo in ("club", "club_actividad", "club_visitantes"):
        assert REVENUE_LINE_TO_REPORT_LINE[campo] == "REV_CLUB"
        assert REVENUE_LINE_TO_GROUP[campo] == "CLUB"


def test_partir_la_linea_no_cambia_el_total():
    """La prueba de que esto es cosmético para el P&L: mismo dinero, repartido
    en tres, tiene que dar el mismo REV_CLUB."""
    from decimal import Decimal

    from app.engine.pl_engine import revenue_seed_from_lines
    junto = revenue_seed_from_lines({"club": Decimal("30000")})
    partido = revenue_seed_from_lines({
        "club": Decimal("12000"), "club_actividad": Decimal("13000"),
        "club_visitantes": Decimal("5000")})
    assert junto["REV_CLUB"] == partido["REV_CLUB"] == Decimal("30000")


def test_la_cadena_del_checkbook_al_pl_esta_completa_para_las_tres():
    """Cada línea del checkbook tiene que aterrizar en su campo de
    RevenueResult; si falta uno, ese ingreso se digita y se pierde en silencio."""
    from app.engine.recalculate import _REVENUE_LINE_TO_FIELD, revenue_line_dict
    from app.engine.revenue_calculator import RevenueResult

    r = RevenueResult(month=1, year=2027)
    for ln in LINEAS:
        campo = _REVENUE_LINE_TO_FIELD[ln]
        assert hasattr(r, campo), f"RevenueResult no tiene {campo}"
        setattr(r, campo, 1000)
    d = revenue_line_dict(r)
    assert d["club"] == d["club_actividad"] == d["club_visitantes"] == 1000


def test_el_club_cuenta_en_el_total_de_ingresos():
    """Antes quedaba fuera de `total_revenue`: el P&L lo sumaba (vía REV_CLUB) y
    la pantalla de ingresos no, así que las dos cifras se contradecían."""
    from app.engine.revenue_calculator import RevenueResult
    r = RevenueResult(month=1, year=2027)
    base = r.total_revenue
    r.club, r.club_actividad, r.club_visitantes = 100, 200, 300
    assert r.total_revenue == base + 600
