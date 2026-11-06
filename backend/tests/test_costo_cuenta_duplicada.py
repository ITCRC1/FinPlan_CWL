# -*- coding: utf-8 -*-
"""Agregar una cuenta que el departamento ya tiene se explica, no se cae.

Owner, 2026-11-05: *«NO ME DEJA AGREGAR ESTE COSTO»* — quería meter CAR RENTAL
en la cuenta 5350 de 0152 Transportation, que ya tenía esa cuenta con driver
por huéspedes y $20.881,30 al año. El botón «Agregar» no hacía nada y la
pantalla no decía por qué.

`cost_entries` tiene `UniqueConstraint(scenario_id, dept_code, account_code)`
—**sin código de detalle**, a diferencia del OPEX, así que una cuenta lleva una
sola línea por departamento—. El endpoint insertaba sin mirar, el commit
reventaba con IntegrityError y la excepción salía sin atrapar: el servidor
moría sin responder y el navegador no tenía nada que mostrar.

Es el mismo final que el bug del OPEX de este mismo día
(`test_opex_detail_codes.py`): una llave única violada que llega al usuario
como silencio.
"""
import pytest

from app.api.costs_api import create_cost_entry
from app.errores import MENSAJES


def test_la_clave_del_error_existe_en_los_dos_idiomas():
    """Sin esto el 409 llega como texto crudo, o peor, sin texto."""
    assert "costos.cuenta_ya_existe" in MENSAJES
    m = MENSAJES["costos.cuenta_ya_existe"]
    assert set(m) >= {"es", "en"}
    for idioma in ("es", "en"):
        # Los tres datos que hacen útil el mensaje: qué cuenta, qué
        # departamento, y cómo se llama la línea que ya está.
        for campo in ("{cuenta}", "{dept}", "{nombre}"):
            assert campo in m[idioma], f"falta {campo} en {idioma}"


def test_el_endpoint_mira_antes_de_insertar():
    """La defensa es un SELECT previo, no atrapar el IntegrityError después.

    Atraparlo también funcionaría, pero deja la sesión en estado de rollback y
    cualquier cosa que venga después en la misma petición falla sin relación
    aparente con la causa.
    """
    import inspect
    fuente = inspect.getsource(create_cost_entry)
    assert "costos.cuenta_ya_existe" in fuente
    i_select = fuente.index("CostEntry.account_code == body.account_code")
    i_add = fuente.index("db.add(entry)")
    assert i_select < i_add, "el chequeo tiene que ir ANTES del insert"


def test_la_llave_unica_no_incluye_el_detalle():
    """Si algún día se le agrega `detail_code` —como tiene el OPEX— este
    chequeo pasa a estar de más y hay que quitarlo, no dejarlo frenando
    líneas legítimas."""
    from app.models.cost_entry import CostEntry
    uniques = [c for c in CostEntry.__table__.constraints
               if c.__class__.__name__ == "UniqueConstraint"]
    assert uniques, "cost_entries perdió su UniqueConstraint"
    cols = {c.name for c in uniques[0].columns}
    assert cols == {"scenario_id", "dept_code", "account_code"}, cols
