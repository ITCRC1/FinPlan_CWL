# -*- coding: utf-8 -*-
"""El GL que jala Excel sale del MISMO armado que el botón de la pantalla.

Owner, 2026-11-10: *«necesito formatear esto para poder desde excel bajar
estos datos con refresh, con varias versiones»*.

⚠️ La tentación es escribir una segunda lectura «que hace lo mismo». Termina
dando otra cifra el día que una de las dos cambia, y la diferencia aparece en
un archivo que alguien ya mandó afuera. Por eso el endpoint del consolidado
reusa `gl_api._grilla`.
"""
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"


def _fuente(nombre: str) -> str:
    return (RAIZ / nombre).read_text(encoding="utf-8")


def _cuerpo(src: str, nombre: str) -> str:
    i = src.index(f"async def {nombre}(")
    j = src.find("\n@router", i + 1)
    return src[i: j if j > 0 else len(src)]


def test_el_endpoint_de_excel_reusa_la_grilla_de_la_pantalla():
    cuerpo = _cuerpo(_fuente("consolidado_api.py"), "consolidado_gl")
    assert "gl_api._grilla(" in cuerpo, (
        "si arma la grilla por su cuenta, el Excel y la pantalla van a "
        "divergir sin que nada avise")


def test_resuelve_por_ANIO_TIPO_VERSION_y_no_por_uuid():
    """En el Excel la versión se escribe como se llama ("Working", "Final"),
    que es lo que el usuario sabe. Un UUID en una celda no se puede escribir
    ni revisar."""
    cuerpo = _cuerpo(_fuente("consolidado_api.py"), "consolidado_gl")
    for p in ("year", "tipo", "version"):
        assert f"{p}:" in cuerpo or f"{p} " in cuerpo, f"falta el parámetro {p}"
    assert "_escoger_escenario(" in cuerpo, (
        "tiene que usar el mismo criterio del resto del consolidado: el ★ "
        "Current del forecast y nunca el espejo del Pre-Cierre")


def test_va_con_la_llave_de_solo_lectura():
    """Sin esto el libro pide sesión y se vence a los 7 días: el tablero queda
    en blanco sin avisar (es la razón por la que la llave existe)."""
    cuerpo = _cuerpo(_fuente("consolidado_api.py"), "consolidado_gl")
    assert "lector_del_consolidado" in cuerpo


def test_dice_el_signo_que_usa():
    """El ingreso va NEGATIVO. Sin decirlo, quien arme un pivot afuera lo suma
    al revés y el total le da la utilidad cambiada de signo sin entender por
    qué."""
    cuerpo = _cuerpo(_fuente("consolidado_api.py"), "consolidado_gl")
    assert '"signo": "revenue_credit"' in cuerpo
