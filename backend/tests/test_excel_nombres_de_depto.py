# -*- coding: utf-8 -*-
"""Las pestañas del Excel llevan el nombre del departamento, y vuelven a entrar.

«¿Por qué estos departamentos en el Excel no tienen el nombre y otros sí?»
(owner, 2026-08-12, mirando las pestañas «260 260» y «270 270» al lado de
«0230 IT»).

Los tres exportadores tenían cada uno su propia lista de ~16 departamentos
mientras `department_catalog` tiene 38: lo que no estuviera en la lista salía con
el código repetido. Tres copias parciales de la misma verdad, envejeciendo por
separado — la de OPEX ni siquiera coincidía con la de costos.

**Y debajo del defecto cosmético había uno que perdía datos:** el importador
reconocía la hoja con `^(\\d{4})`, exactamente cuatro dígitos. El Club Madresal
es `260` y el Área Recreativa `270`, de tres. Sus hojas se saltaban en silencio:
se podía llenar el OPEX del Club en el Excel, subirlo, ver «importado» y que no
entrara una sola línea.
"""
import inspect
import re

from app.export.excel_base import nombre_de_hoja


def test_el_nombre_de_hoja_saca_lo_que_excel_prohibe():
    """El catálogo dice «Rooms / Habitaciones». La barra tumba el libro ENTERO
    al guardarlo — no es una hoja fea, es un export que no se genera."""
    usados: set[str] = set()
    assert nombre_de_hoja("0110 Rooms / Habitaciones", usados) == "0110 Rooms  Habitaciones"
    for prohibido in r':\/?*[]':
        assert prohibido not in nombre_de_hoja(f"x{prohibido}y", set())


def test_el_nombre_de_hoja_no_se_repite():
    """Dos departamentos de nombre largo colapsan en los mismos 31 caracteres y
    el libro no abre."""
    usados: set[str] = set()
    largo = "Administración de la Propiedad y Servicios Generales"
    a = nombre_de_hoja(largo, usados, sufijo="0180")
    b = nombre_de_hoja(largo, usados, sufijo="0184")
    assert a != b
    assert len(a) <= 31 and len(b) <= 31


def test_el_nombre_de_hoja_nunca_pasa_de_31():
    assert len(nombre_de_hoja("x" * 80, set())) == 31


def test_los_importadores_aceptan_codigos_de_tres_digitos():
    """El Club es 260 y el Área Recreativa 270. Con `\\d{4}` sus hojas se
    saltaban sin decir nada."""
    from app.export import costs_excel, opex_excel
    for mod, fn in ((opex_excel, "import_opex_from_excel"),
                    (costs_excel, "import_costs_from_excel")):
        src = inspect.getsource(getattr(mod, fn))
        assert r"\d{3,4}" in src, f"{fn} sigue pidiendo cuatro dígitos"
        assert r"^(\d{4})" not in src


def test_el_patron_agarra_tres_y_cuatro_digitos():
    patron = re.compile(r"^(\d{3,4})(?!\d)")
    assert patron.match("0110 Rooms  Habitaciones").group(1) == "0110"
    assert patron.match("260 Club Madresal").group(1) == "260"
    assert patron.match("270 Área Recreativa").group(1) == "270"
    assert patron.match("Resumen") is None


def test_los_exportadores_reciben_los_nombres_de_afuera():
    """El nombre sale del catálogo, no de una lista adentro del exportador."""
    from app.export import costs_excel, opex_excel, payroll_excel
    for mod, fn in ((opex_excel, "export_opex_to_excel"),
                    (costs_excel, "export_costs_to_excel"),
                    (payroll_excel, "export_payroll_to_excel")):
        firma = inspect.signature(getattr(mod, fn))
        assert "dept_names" in firma.parameters, f"{fn} no recibe los nombres"


def test_los_endpoints_pasan_el_catalogo():
    """Un parámetro que nadie llena no sirve de nada."""
    from app.api import costs_api, opex_api, payroll_api
    for mod, fn in ((opex_api, "export_opex_excel"),
                    (costs_api, "export_costs_excel"),
                    (payroll_api, "export_payroll_excel")):
        src = inspect.getsource(getattr(mod, fn))
        assert "nombres_de_depto(db)" in src, f"{fn} no pasa el catálogo"
