# -*- coding: utf-8 -*-
"""El candado del presupuesto no frena al On the Books.

**La regla (owner, 2026-08-18).** «El escenario es solo una referencia
comparativa, pero no tiene nada que ver con las subidas.»

Lo que entra por las rutas de OTB son las reservas que YA existen en Opera: un
hecho observado, no una cifra que alguien presupuestó. Enllavar un escenario
congela SUS números — y el candado se había quedado puesto por inercia sobre
las cinco rutas de OTB.

El síntoma que lo destapó: con el «Budget 2026 · Final» elegido (locked), subir
el XML moría con

    409 {"detail":"El escenario 'BUDGET Final 2026' está bloqueado
         (status=locked). Crea una nueva versión para editar."}

…cuando la subida no tocaba ni una cifra de ese presupuesto. La pantalla ni
siquiera avisaba: dejaba apretar el botón para que reventara contra la API.

⚠️ Esta prueba cuida las CINCO rutas. Volver a poner `candado` en cualquiera de
ellas rompe la regla del owner, no solo la de la que se tocó.
"""
import inspect

import pytest

from app.api import revenue_api

#: Las cinco rutas por las que entra el On the Books.
RUTAS_OTB = [
    "import_otb_xml",       # POST /import-otb-xml/  — el XML de Opera
    "put_otb_entry",        # PUT  /onthebooks-entry/ — carga manual por mes
    "put_daily_occ_entry",  # PUT  /daily-occ-entry/  — heatmap diario
    "put_otb_param",        # PUT  /otb-params/       — % de venta en propiedad
    "clear_otb",            # DEL  /otb/              — reset para volver a subir
]


@pytest.mark.parametrize("nombre", RUTAS_OTB)
def test_la_ruta_de_otb_no_pasa_por_el_candado(nombre):
    fn = getattr(revenue_api, nombre)
    src = inspect.getsource(fn)
    assert "await candado(" not in src, (
        f"`{nombre}` volvió a pasar por el candado del presupuesto. El On the "
        f"Books no es parte del presupuesto: enllavar congela las cifras del "
        f"escenario, no las reservas que ya existen en Opera.")


def test_el_candado_sigue_puesto_donde_SI_va():
    """El contrapeso: esto no es «sacar el candado», es sacarlo de donde no iba.

    Las rutas que escriben cifras del presupuesto tienen que seguir frenadas.
    Sin esta prueba, el arreglo de arriba se puede 'lograr' borrando `candado`
    del módulo entero.
    """
    modulo = inspect.getsource(revenue_api)
    assert modulo.count("await candado(db, scenario_id)") >= 6, (
        "quedaron menos candados de los esperados — se sacó de más")
