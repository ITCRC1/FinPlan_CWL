# -*- coding: utf-8 -*-
"""El archivo no puede borrar lo que el archivo no puede traer.

**El defecto (owner, 2026-08-14).** Bajo la plantilla del Detalle del Actual 2025
y le faltaban dos filas: `4900 Distribucion` (Lavanderia 0161) y `4901`
(Cafeteria 0220), **−$196.326,17**.

Que no bajen es CORRECTO y a proposito: son el credito del asiento con que esos
departamentos reparten su costo. Son clase 4 pero no son ingreso — contarlas como
tal duplicaria el reparto—, asi que el parser las excluye.

El problema era el **viaje de vuelta**. La importacion en modo completo borraba
todo el detalle del escenario y lo reinsertaba desde el archivo; como el archivo
nunca las trae, se perdian. Bajar la plantilla, corregir una celda y volver a
subir se llevaba $196 mil por delante — **y el P&L seguia cuadrando consigo
mismo**, asi que la diferencia solo aparecia despues, comparando contra el
auxiliar. Es el mismo patron que los $40.613 del Actual 2024.

**El riesgo real que vigila esta prueba:** la regla esta dicha DOS VECES —en
Python para el parser y en SQL para el borrado—. Si se separan, el reemplazo
vuelve a borrarlas y nada avisa.
"""
from decimal import Decimal

import pytest

from app.importers.gl_detail_importer import es_contrapartida_de_allocation

#: Las de verdad, tal como estaban en produccion el 2026-08-14.
REALES = [
    ("4900", "Distribución", "0161"),
    ("4901", "Distribución", "0220"),
]

#: Ingreso de verdad: NO puede confundirse con una contrapartida.
INGRESOS = [
    ("4000", "Rooms"),
    ("4100", "Food"),
    ("4900", "Rooms Revenue"),        # clase 4 con otro nombre
    ("7080", "Distribución"),         # el nombre solo no alcanza: no es clase 4
    ("6025", "Distribución cafetería"),
]


@pytest.mark.parametrize("code,name,_dept", REALES)
def test_reconoce_las_contrapartidas(code, name, _dept):
    assert es_contrapartida_de_allocation(code, name)


@pytest.mark.parametrize("code,name", INGRESOS)
def test_no_se_lleva_puesto_al_ingreso_de_verdad(code, name):
    """Excluir de mas seria peor que el bug: dejaria ingreso real fuera del P&L."""
    assert not es_contrapartida_de_allocation(code, name)


def test_aguanta_nulos():
    """Una fila sin nombre o sin cuenta no puede tumbar una importacion entera."""
    assert not es_contrapartida_de_allocation(None, None)
    assert not es_contrapartida_de_allocation("", "")
    assert not es_contrapartida_de_allocation("4900", None)


def test_la_regla_de_python_y_la_de_sql_dicen_lo_mismo():
    """Las dos definiciones tienen que coincidir, o el agujero vuelve.

    Se compara ejecutando el SQL de verdad contra SQLite en memoria: comparar los
    textos de las dos reglas no probaria nada — lo que importa es que
    seleccionen las mismas filas.
    """
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from app.api.scenarios_api import ES_CONTRAPARTIDA_DE_ALLOCATION
    from app.db import Base
    from app.models.actual_entry import ActualEntry

    casos = [(c, n) for c, n, _ in REALES] + list(INGRESOS)

    motor = sa.create_engine("sqlite://")
    ActualEntry.__table__.create(motor)
    with Session(motor) as ses:
        for i, (code, name) in enumerate(casos):
            ses.add(ActualEntry(scenario_id="s", hotel_id="CWL",
                                dept_code=f"d{i}", account_code=code,
                                account_name=name or ""))
        ses.commit()
        segun_sql = {
            (e.account_code, e.account_name)
            for e in ses.execute(
                sa.select(ActualEntry).where(ES_CONTRAPARTIDA_DE_ALLOCATION)
            ).scalars()
        }

    segun_python = {(c, n or "") for c, n in casos
                    if es_contrapartida_de_allocation(c, n)}
    assert segun_sql == segun_python, (
        "La regla de Python y la de SQL no seleccionan las mismas filas. "
        "Si se separan, el reemplazo completo vuelve a borrar los allocations "
        "y nada avisa.\n"
        f"  solo SQL:    {segun_sql - segun_python}\n"
        f"  solo Python: {segun_python - segun_sql}")


def test_el_delete_del_reemplazo_las_excluye():
    """Que la condicion este REALMENTE puesta en el borrado.

    Sin esto, alguien podria dejar la constante definida y sin usar, y la prueba
    de arriba seguiria en verde mientras el reemplazo borra igual.
    """
    import inspect

    from app.api import scenarios_api

    fuente = inspect.getsource(scenarios_api)
    bloque = fuente[fuente.index("sa_delete(ActualEntry)"):][:400]
    assert "ES_CONTRAPARTIDA_DE_ALLOCATION" in bloque, (
        "El DELETE de ActualEntry ya no excluye las contrapartidas: un archivo "
        "subido en modo completo vuelve a borrar los allocations.")
    assert "~" in bloque, "La condicion tiene que ir NEGADA (se borra todo MENOS esas)."


# ── La misma cuenta en dos idiomas ──────────────────────────────────────────

def test_reconoce_la_distribucion_en_ingles():
    """Owner (2026-08-14), viendo la plantilla: «hay 2 cuentas, debe haber una
    que es la que hace negativa o deja en 0 el departamento».

    Eran la MISMA cuenta rotulada en dos idiomas: «Distribuciòn» (4900/4901) y
    «Expense Distribution» (4999). La regla decia «distribuci», asi que la
    inglesa no calificaba y salia bajo INGRESO, aparentando ser un ingreso mas
    del departamento.
    """
    assert es_contrapartida_de_allocation("4999", "Expense Distribution")
    assert es_contrapartida_de_allocation("4900", "Distribuciòn")


def test_ensanchar_la_regla_no_se_lleva_ingreso_real():
    """El error opuesto seria peor: dejaria ingreso de verdad fuera del P&L.

    Verificado contra el catalogo — ninguna cuenta de ingreso real lleva
    «distribu» en el nombre.
    """
    for code, name in (("4000", "Rooms"), ("4700", "Lavandería 1"),
                       ("4100", "Food"), ("4301", "Ingreso Tienda #1")):
        assert not es_contrapartida_de_allocation(code, name)
    # Y sigue sin aplicar fuera de la clase 4.
    assert not es_contrapartida_de_allocation("7080", "Distribution")
