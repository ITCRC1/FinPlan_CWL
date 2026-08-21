# -*- coding: utf-8 -*-
"""Un driver de ingreso llega al P&L esté el escenario en el modo que esté.

## De qué se cuida

De un fallo que no da error: se guarda bien, la pantalla muestra el ingreso, y el
estado de resultados sigue en cero. Se descubre semanas después, cuando no cuadra
un total. Pasó de verdad con el Club Madresal —$125.180 al año— y el Spa lo tenía
igual.

## Cómo era y cómo es

Antes esto vigilaba que cada driver **avisara**: `llega_al_pl` decía si el
escenario leía el checkbook, y si no, la pantalla ponía una bandera. El aviso
existía; la fuente, no.

Owner, 2026-08-15: «solo quiero que trabaje **estándar como todos los
departamentos**». Así que ya no se avisa: se tapó. Hay **dos** fuentes de ingreso
—`RevenueEntry` para el modo `checkbook`, `RevenueOther` para el modo `drivers`—
y todo driver deposita su resultado en las dos, por un único camino compartido
(`app/api/_ingreso_de_driver.py`). Un departamento no tiene que saber en qué modo
está su escenario.

Estas pruebas cuidan que ese camino siga siendo **uno solo**: el modo de romperlo
es que un driver nuevo se escriba su propia versión y vuelva a escribir en una
sola tabla.
"""
import inspect
from decimal import Decimal

from app.api import club_stats_api, revenue_api
from app.api._ingreso_de_driver import persistir_ingreso_de_driver
from app.api._llega_al_pl import llega_al_pl, modo_ingresos
from app.models.revenue_other import OTHER_REVENUE_LINES


class _Esc:
    def __init__(self, modo):
        self.revenue_source = modo


# ── La regla ─────────────────────────────────────────────────────────────────

def test_el_ingreso_de_un_driver_llega_en_los_dos_modos():
    """La afirmación central. Si algún día vuelve a haber una fuente que no se
    lea, esto se pone en `False` en un solo archivo y las pantallas se enteran."""
    assert llega_al_pl(_Esc("checkbook")) is True
    assert llega_al_pl(_Esc("drivers")) is True


def test_el_default_historico_sigue_siendo_drivers():
    """Un escenario viejo sin la columna arma el ingreso por drivers."""
    class _Viejo:
        pass
    assert modo_ingresos(_Viejo()) == "drivers"


def test_ningun_driver_se_escribe_su_propia_version_de_la_regla():
    """Dos copias de esto se separan tarde o temprano."""
    for mod in (club_stats_api, revenue_api):
        src = inspect.getsource(mod)
        assert "from app.api._llega_al_pl import" in src, (
            f"{mod.__name__} no importa la regla compartida")
        assert "def llega_al_pl" not in src, (
            f"{mod.__name__} se escribió su propia copia de la regla")


def test_los_dos_drivers_lo_dicen_en_su_respuesta():
    """De nada sirve la regla si la pantalla no la recibe."""
    for fn in (club_stats_api.leer_cuota,          # cuota del Club
               revenue_api.get_spa_budget,          # capture rate del Spa
               revenue_api.bulk_spa_budget):        # …y al guardar, no solo al abrir
        assert '"llega_al_pl"' in inspect.getsource(fn), (
            f"{fn.__name__} no publica llega_al_pl")


# ── El camino compartido ─────────────────────────────────────────────────────

def test_el_helper_escribe_en_las_dos_fuentes():
    """Que la lea el modo checkbook y la lea el modo drivers."""
    src = inspect.getsource(persistir_ingreso_de_driver)
    assert "RevenueEntry" in src, "no deja nada para el modo checkbook"
    assert "RevenueOther" in src, "no deja nada para el modo drivers"


def test_el_helper_no_pisa_una_linea_que_el_motor_deriva():
    """`ROOMS` o `FOOD` las calcula el motor con tarifas × ocupación. Meterlas en
    `revenue_other` sería pisar el cálculo con una copia vieja, y el escenario
    quedaría con un Room Revenue congelado sin que nada avise."""
    src = inspect.getsource(persistir_ingreso_de_driver)
    assert "OTHER_REVENUE_LINES" in src
    assert "ROOMS" not in OTHER_REVENUE_LINES


def test_los_dos_drivers_pasan_por_el_helper():
    for fn in (club_stats_api.guardar_cuota,        # cuota del Club
               club_stats_api.guardar_membresias,   # …y el conteo que la multiplica
               revenue_api.bulk_spa_budget):        # capture rate del Spa
        assert "persistir_ingreso_de_driver" in inspect.getsource(fn), (
            f"{fn.__name__} escribe el ingreso por su cuenta")


def test_el_conteo_de_socios_arrastra_la_cuota():
    """`socios × precio`: si se corrige el conteo y el ingreso se queda con el
    de antes, el driver muestra un número y el P&L otro. Callado, otra vez."""
    src = inspect.getsource(club_stats_api.guardar_membresias)
    assert "persistir_ingreso_de_driver" in src
    assert "hay_driver" in src, (
        "sin driver de cuota el precio vale 0 y volver a empujar borraría un "
        "ingreso digitado a mano")


def test_todo_el_que_escriba_una_linea_de_ingreso_pasa_por_aca():
    """El centinela: si mañana aparece un tercer driver que escribe una línea de
    ingreso, esta prueba lo obliga a usar el camino compartido.

    Los dos que no son drivers quedan fuera a propósito:
    `bulk_replace_revenue_checkbook` ES la pantalla del checkbook y
    `push_revenue_to_checkbook` es la migración deliberada de drivers a
    checkbook, que devuelve el diff línea por línea.
    """
    conocidos = {"bulk_replace_revenue_checkbook",   # no son drivers
                 "push_revenue_to_checkbook"}
    escritores = set()
    for mod in (club_stats_api, revenue_api):
        for nombre, fn in vars(mod).items():
            if callable(fn) and getattr(fn, "__module__", "") == mod.__name__:
                try:
                    src = inspect.getsource(fn)
                except (OSError, TypeError):
                    continue
                if "RevenueEntry(" in src or "RevenueOther(" in src:
                    escritores.add(nombre)
    nuevos = escritores - conocidos
    assert not nuevos, (
        f"escriben una línea de ingreso a mano: {sorted(nuevos)}. "
        "Si es un driver, usá persistir_ingreso_de_driver(); si no, agregalo a "
        "la lista de conocidos explicando por qué.")


# ── El contrato del helper ───────────────────────────────────────────────────

def test_el_helper_rechaza_una_linea_que_no_existe():
    """Una línea mal escrita se guardaría en silencio y no la leería nadie: el
    mismo fallo callado, por la puerta de al lado."""
    import asyncio

    import pytest

    class _E:
        id = "s"
        hotel_id = "CWL"

    with pytest.raises(ValueError, match="desconocidas"):
        asyncio.run(persistir_ingreso_de_driver(
            None, _E(), {"CLUV": [Decimal("0")] * 12}))


def test_el_helper_exige_los_doce_meses():
    import asyncio

    import pytest

    class _E:
        id = "s"
        hotel_id = "CWL"

    with pytest.raises(ValueError, match="12 montos"):
        asyncio.run(persistir_ingreso_de_driver(
            None, _E(), {"CLUB": [Decimal("1")] * 11}))
