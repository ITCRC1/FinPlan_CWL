# -*- coding: utf-8 -*-
"""EL EXCEL BAJA TODOS LOS SUB-TABS QUE SE VEN.

Owner, 2026-08-27: *«el excel no baja lo que esta viendo»*.

La pantalla de cierre tiene 20 sub-tabs y un boton que baja TODO a un libro.
El mapa `CAPITULOS` dice como se arma cada hoja; un sub-tab que no este ahi
sale de la pantalla y NO sale del archivo — y nadie lo nota hasta que alguien
busca ese cuadro en el Excel de la reunion.

Paso el 2026-09-10: se agregaron `planillaCuentas` y `planillaPosicion` y el
libro siguio saliendo con 18 hojas. La pantalla mostraba 20.

Este guard compara las dos listas y falla con el nombre del que falta.
"""
import io
import os
import re

PANTALLA = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "month-end", "pl", "Pantalla.tsx")

#: Sub-tabs que a proposito NO tienen hoja en el Excel. Vacio hoy: si alguno
#: se agrega aca, tiene que venir con la razon escrita al lado.
SIN_HOJA_A_PROPOSITO: dict[str, str] = {}


def _fuente() -> str:
    return io.open(PANTALLA, encoding="utf-8").read()


def _vistas(src: str) -> list[str]:
    bloque = src[src.index("const VISTAS = ["):src.index("] as const;")]
    return re.findall(r'\{\s*key:\s*"(\w+)"', bloque)


def _capitulos(src: str) -> set[str]:
    i = src.index("const CAPITULOS")
    bloque = src[i:src.index("async function bajarExcel")]
    return set(re.findall(r"^\s{4}(\w+):\s*(?:async|\()", bloque, re.M))


def test_cada_sub_tab_tiene_su_hoja_en_el_excel():
    src = _fuente()
    vistas, capitulos = _vistas(src), _capitulos(src)
    assert len(vistas) >= 18, f"solo se leyeron {len(vistas)} sub-tabs"
    faltan = [v for v in vistas
              if v not in capitulos and v not in SIN_HOJA_A_PROPOSITO]
    assert not faltan, (
        "estos sub-tabs se ven en la pantalla y NO bajan al Excel: "
        + ", ".join(faltan))


def test_los_dos_tabs_de_planilla_estan():
    """Los que motivaron el guard, por nombre: si alguien los saca, que se vea
    en el diff de la prueba y no en la reunion."""
    capitulos = _capitulos(_fuente())
    assert "planillaCuentas" in capitulos
    assert "planillaPosicion" in capitulos


def test_los_capitulos_de_planilla_piden_su_dato():
    """Los sub-tabs de planilla cargan al abrirse, y el Excel se baja sin
    abrirlos: leyendo el estado de la pantalla saldrian dos hojas vacias."""
    src = _fuente()
    i = src.index("async function cuadroPlanillaCuentas")
    assert "await getPlanillaPorCuenta(" in src[i:i + 500]
    j = src.index("async function cuadroPlanillaPosicion")
    assert "await getPlanillaPorPosicion(" in src[j:j + 500]
