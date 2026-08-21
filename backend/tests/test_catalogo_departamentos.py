# -*- coding: utf-8 -*-
"""
LOS NOMBRES DE DEPARTAMENTO SALEN DEL CATALOGO, NO DE UNA LISTA A MANO.

El frontend traía 22 departamentos escritos en código mientras la base tiene 36.
Catorce salían como números pelados en las pantallas de OPEX y Costos —Front Desk,
Housekeeping, Kitchen, Restaurant, Finance, Club Madresal, Área Recreativa— y
varios nombres se habían desviado: el 0220 decía «Employee Dining» y en el
catálogo es «Employee Dining (Cafetería)», así que buscar «Cafetería» no
encontraba nada. De ahí la pregunta del owner: «¿por qué no veo Cafetería?».
"""
import inspect
import pathlib
import re

from app.api import audit_api

from tests._rutas import FRONT as _FRONT_DIR
FRONT = _FRONT_DIR / "lib" / "cwl-depts.ts"


def test_hay_endpoint_de_departamentos():
    src = inspect.getsource(audit_api)
    assert '"/departments/"' in src or "'/departments/'" in src
    assert "DepartmentCatalog" in src


def test_la_pantalla_carga_el_catalogo_de_la_base():
    if not FRONT.exists():
        return
    s = FRONT.read_text(encoding="utf-8")
    assert "cargarDepartamentos" in s, "la pantalla no trae el catálogo de la base"
    assert "/departments/" in s
    # la lista escrita a mano queda solo como respaldo
    assert "CATALOGO" in s and "let CATALOGO" in s


def test_las_pantallas_de_opex_y_costos_lo_llaman():
    for f in ("app/opex/checkbook/page.tsx", "app/costs/checkbook/page.tsx"):
        p = _FRONT_DIR / f
        if not p.exists():
            continue
        s = p.read_text(encoding="utf-8")
        assert "cargarDepartamentos" in s, f"{f} sigue usando solo la lista a mano"
        # y lo carga ANTES de armar la lista, si no los nombres salen del respaldo
        assert s.index("cargarDepartamentos()") < s.index("mergeDepts(")


def test_el_respaldo_no_pretende_ser_el_catalogo():
    """Si alguien vuelve a tratar la lista local como fuente, esto avisa."""
    if not FRONT.exists():
        return
    s = FRONT.read_text(encoding="utf-8")
    codigos = re.findall(r'dept_code: "(\w+)"', s)
    assert len(codigos) < 40, "la lista local creció: ¿se está usando como catálogo?"
    assert "respaldo" in s.lower(), "falta decir que es respaldo y no la fuente"
