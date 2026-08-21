# -*- coding: utf-8 -*-
"""
LOS OUTLETS DE A&B NO SE PIERDEN AL IMPORTAR.

`gl_detail_importer.dept_code_from_name` asigna el departamento por el NOMBRE
que trae el archivo. Su tabla mandaba «a&b» y «alimentos» al `0120` y nada más,
así que un GL que dijera «Restaurante» o «Cocina» caía en «sin departamento» y
se omitía — la Vista previa lo avisa, pero omitido igual.

Ahora rutean al `0123` Restaurant y al `0122` Kitchen, que **ya existen y cuelgan
del `0120`**: la plata sigue cayendo en A&B exactamente como hoy, y lo que se
gana es que el detalle por outlet no se pierde el día que la contabilidad lo
mande.

Bar y Room Service NO están en la tabla a propósito: todavía no existen como
departamento, y apuntar una palabra clave a un código inexistente sería peor que
omitir. Entran con el diseño de B2 (ver `docs/PENDIENTES.md`).
"""
from app.engine import pl_engine
from app.importers.gl_detail_importer import dept_code_from_name


def test_restaurante_y_cocina_ya_no_se_omiten():
    assert dept_code_from_name("Restaurante") == "0123"
    assert dept_code_from_name("RESTAURANT") == "0123"
    assert dept_code_from_name("Cocina") == "0122"
    assert dept_code_from_name("Kitchen") == "0122"


def test_lo_especifico_le_gana_a_lo_generico():
    """La tabla devuelve la PRIMERA que pega. «Restaurante A&B» es el outlet."""
    assert dept_code_from_name("Restaurante A&B") == "0123"
    assert dept_code_from_name("Cocina - Alimentos") == "0122"
    # y A&B a secas sigue siendo el bloque
    assert dept_code_from_name("A&B") == "0120"
    assert dept_code_from_name("Departamento de Alimentos y Bebidas") == "0120"


def test_los_outlets_caen_igual_en_ayb():
    """Lo que se gana es detalle, NO un cambio de plata: ambos son hijos del 0120."""
    for code in ("0122", "0123"):
        assert pl_engine.consolidate_dept(code) == "0120"
        assert pl_engine.group_for_dept(code) == "FB"


def test_bar_y_room_service_todavia_no_se_inventan():
    """Si alguien los agrega, que sea con departamento de verdad, no con un código al aire."""
    assert dept_code_from_name("Room Service") is None
    # «Bar» a secas no debe resolver al Private Bar: son outlets distintos
    assert dept_code_from_name("Bar") != "0121"
