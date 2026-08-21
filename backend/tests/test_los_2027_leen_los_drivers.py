# -*- coding: utf-8 -*-
"""«El mix aplica de 2027 en adelante» — ya sin la excepción del Club.

Owner, 2026-08-15: el mix y los cambios de agosto aplican **de 2027 en
adelante**, y el Club Madresal «solo quiero que trabaje **estándar como todos los
departamentos**» (`docs/DECISIONES_DEL_OWNER.md`).

La migración 116 pasó cinco de los seis presupuestos 2027 de `checkbook` a
`drivers` y dejó afuera al `BUDGET Working 2027`: era el único con Club cargado,
y el camino de `drivers` no tenía de dónde sacar ese ingreso —$125.180 al año que
se habrían ido a cero sin un solo error—. **La 117 cierra el agujero y saca la
excepción.**

La versión anterior de este archivo tenía dos centinelas que vigilaban que la
excepción no se olvidara ni se quedara de más. Ya cumplieron: la excepción se fue
el día que el motor aprendió a producir el ingreso del Club. Lo que queda vigilado
es lo de después — que **ningún 2027 vuelva a quedarse afuera**, y que el ingreso
plano de un departamento llegue al P&L **sin** que su driver tenga que saber en
qué modo está el escenario.
"""
import pathlib
import re
from decimal import Decimal

from app.engine.revenue_calculator import calculate_revenue
from app.models.revenue_other import OTHER_REVENUE_LINES, RevenueOther

VERSIONES = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
MIG_116 = VERSIONES / "116_los_2027_leen_los_drivers.py"
MIG_117 = VERSIONES / "117_el_club_trabaja_estandar.py"


def test_la_117_no_deja_ningun_2027_en_checkbook():
    """La exclusión de la 116 era por año Y versión. Acá no hay exclusión: si
    alguien vuelve a escribir una, es porque hay un departamento que otra vez no
    llega al P&L — y eso se arregla en el motor, no esquivando el escenario."""
    sql = MIG_117.read_text(encoding="utf-8")
    assert re.search(r"UPDATE scenarios\s+SET revenue_source = 'drivers'", sql)
    assert re.search(r"year\s*>=\s*2027", sql), "la migración ya no arranca en 2027"
    assert not re.search(r"NOT\s*\(\s*year\s*=\s*2027", sql), (
        "volvió la exclusión del Working 2027. Si un departamento no llega al P&L "
        "en modo drivers, dale una fuente en el motor; no dejes el escenario en "
        "checkbook.")


def test_la_117_copia_el_club_ANTES_de_cambiar_el_modo():
    """El orden importa: primero la fuente, después el modo. Al revés hay un
    momento —aunque sea dentro de la transacción— en que el escenario ya lee por
    drivers y todavía no tiene de dónde."""
    sql = MIG_117.read_text(encoding="utf-8")
    cuerpo = sql[sql.index("def upgrade"):]
    assert cuerpo.index("COPIAR") < cuerpo.index("A_DRIVERS")
    assert "INSERT INTO revenue_other" in sql
    assert "'CLUB', 'CLUB_ACTIVIDAD', 'CLUB_VISITANTES'" in sql


def test_la_116_sigue_contando_su_historia():
    """No se reescribe: explica por qué el Club era la excepción y cuánto costaba.
    La 117 se apoya en ese relato."""
    assert MIG_116.exists()
    assert 'down_revision = "116"' in MIG_117.read_text(encoding="utf-8")


def test_el_motor_de_drivers_ya_produce_el_ingreso_del_club():
    """Lo que la prueba vieja esperaba ver fallar algún día.

    No hace falta ninguna rama de Club en el motor: las tres líneas son montos
    mensuales, igual que Spa o Retail, y el motor las lee por la lista derivada.
    Eso es «estándar como todos los departamentos».
    """
    otros = [
        RevenueOther(id="x1", scenario_id="s", hotel_id="CWL",
                     line="CLUB", month=1, amount_usd=Decimal("10240")),
        RevenueOther(id="x2", scenario_id="s", hotel_id="CWL",
                     line="CLUB_ACTIVIDAD", month=1, amount_usd=Decimal("1500")),
        RevenueOther(id="x3", scenario_id="s", hotel_id="CWL",
                     line="CLUB_VISITANTES", month=1, amount_usd=Decimal("800")),
    ]
    r = calculate_revenue(
        month=1, year=2027,
        rate_cards=[], occ_budgets=[], channels=[],
        pkg_configs=[], other_revenues=otros, room_type_units={},
    )
    assert r.club == Decimal("10240")
    assert r.club_actividad == Decimal("1500")
    assert r.club_visitantes == Decimal("800")
    assert r.total_revenue == Decimal("12540")


def test_sin_datos_de_club_el_ingreso_es_cero_y_nadie_se_mueve():
    """El otro lado de la moneda: los diecinueve escenarios sin Club tienen que
    quedar exactamente donde estaban."""
    r = calculate_revenue(
        month=1, year=2027,
        rate_cards=[], occ_budgets=[], channels=[],
        pkg_configs=[], other_revenues=[], room_type_units={},
    )
    assert r.club == r.club_actividad == r.club_visitantes == Decimal("0")


def test_la_lista_de_lineas_planas_se_deriva_y_no_se_escribe():
    """La causa raíz, dicha como prueba.

    El Club no llegaba al P&L porque la lista de líneas planas estaba escrita a
    mano y él no figuraba. Mientras se derive de las líneas canónicas, un
    departamento nuevo llega solo — y esta prueba falla si alguien la vuelve a
    escribir a mano.
    """
    import inspect

    from app.models import revenue_other as mod
    src = inspect.getsource(mod)
    assert "OTHER_REVENUE_LINES = tuple(" in src, (
        "la lista volvió a ser literal: el próximo departamento se pierde igual "
        "que el Club")
    for ln in ("CLUB", "CLUB_ACTIVIDAD", "CLUB_VISITANTES", "SPA"):
        assert ln in OTHER_REVENUE_LINES
    for ln in ("ROOMS", "FOOD", "BEVERAGE"):
        assert ln not in OTHER_REVENUE_LINES, (
            f"{ln} la DERIVA el motor; leerla de revenue_other pisaría el cálculo")
