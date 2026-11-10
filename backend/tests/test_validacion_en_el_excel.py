# -*- coding: utf-8 -*-
"""El bloque de validación del P&L baja con FÓRMULAS, y resueltas.

## De dónde sale (2026-11-09)

Owner, mandando el tab que había armado a mano sobre el P&L por categoría:
*«favor implementar todas estas fórmulas de validación en el excel con fórmulas
y todo. toma el tab y construye dentro el archivo todo lo que está abajo»*.

Debajo del P&L, en la misma hoja, el libro ahora vuelve a calcular la cascada
con fórmulas vivas y la compara contra lo que escribió el motor. Las filas
`CHECK` tienen que dar **0**.

## El defecto que esto impide

El tab del owner apuntaba a filas FIJAS de otras hojas —`'Checkbook
Planilla'!B12`, `'Detalle Planilla'!N217:N221`—. Esas filas dependen de cuántos
departamentos y cuentas traiga el escenario y de si está activo «esconder las
líneas en cero». Copiarlas al generador es garantizar que se corran solas, y el
modo de falla es el caro: el exportador compara la fórmula contra el número,
no cuadra, y **la descarta en silencio**.

Por eso acá no hay un solo número de fila: dentro de la hoja van ordinales que
resuelve el exportador, y a otra hoja va el RÓTULO. Esta prueba exige las dos
cosas.

## Lo que NO cubre

Que los CHECK den cero de verdad lo probó Excel recalculando el libro —ver
`scratchpad/recalcular_v2.py`—, no esto: acá no hay Excel para evaluar
fórmulas. Lo que se cubre acá es que las fórmulas se escriban, que apunten a
filas que existen, y que el bloque degrade diciéndolo cuando le falta una hoja.
"""
import io

import pytest

from ._rutas import FRONT, sin_comentarios

openpyxl = pytest.importorskip("openpyxl")

from app.export.cuadro_excel import _formula, build_cuadros_workbook  # noqa: E402

FUENTE = "lib/validacionPL.ts"


def _src() -> str:
    return sin_comentarios((FRONT / FUENTE).read_text(encoding="utf-8"))


# ── La resolución de la plantilla ───────────────────────────────────────────

def _filas(n: int):
    return [{"label": f"f{i}"} for i in range(n)]


def test_el_ordinal_se_vuelve_la_fila_real():
    f = {"valores": [0, 0], "formula_tpl": "={c}{r:3}"}
    # primera=5 → el ordinal 3 cae en la fila 8.
    assert _formula({}, f, _filas(5), 2, 9, 5) == "=B8"
    assert _formula({}, f, _filas(5), 3, 9, 5) == "=C8"


def test_el_ordinal_absoluto_ya_trae_el_signo():
    """⚠️ `$B{R:1}` da `$B$6`. Escribir `$B${R:1}` daría `$B$$6`, que Excel no
    abre — y es el error fácil de cometer."""
    f = {"valores": [0], "formula_tpl": "=$B{R:1}"}
    assert _formula({}, f, _filas(5), 2, 9, 5) == "=$B$6"


def test_un_ordinal_fuera_de_rango_NO_escribe_nada():
    """Antes que una fórmula rota, ninguna: una celda vacía se nota."""
    f = {"valores": [0], "formula_tpl": "={c}{r:99}"}
    assert _formula({}, f, _filas(5), 2, 9, 5) is None


def test_una_celda_vacia_sigue_vacia():
    f = {"valores": [None], "formula_tpl": "={c}{r:1}"}
    assert _formula({}, f, _filas(5), 2, 9, 5) is None


# ── El libro entero ─────────────────────────────────────────────────────────

COLS = [{"label": "Line Item", "formato": "texto"},
        {"label": "Ene", "formato": "usd2"},
        {"label": "Feb", "formato": "usd2"}]


def _libro(cuadros):
    return openpyxl.load_workbook(
        io.BytesIO(build_cuadros_workbook(cuadros)), data_only=False)


def test_la_referencia_a_otra_hoja_se_resuelve_por_ROTULO():
    """Y la hoja destino puede venir DESPUÉS en el libro: el P&L va adelante y
    los checkbooks atrás, así que una sola pasada no alcanzaba."""
    apunta = {"titulo": "V", "hoja": "V", "columnas": COLS, "filas": [
        {"label": "Trae el total", "valores": [0, 0],
         "formula_tpl": "={h:Chk:Total 0110}"}]}
    destino = {"titulo": "Chk", "hoja": "Chk", "columnas": COLS, "filas": [
        {"label": "0110 · Rooms"},
        {"label": "6000 · Salary and Wages", "valores": [10, 20]},
        {"label": "Total 0110", "valores": [10, 20], "es_total": True}]}
    ws = _libro([apunta, destino])["V"]
    assert ws.cell(5, 2).value == "='Chk'!B7"      # «Total 0110» es la 3ª fila
    assert ws.cell(5, 3).value == "='Chk'!C7"


def test_un_rotulo_que_no_existe_deja_la_celda_VACIA():
    """⚠️ No se inventa una fila. Una celda en blanco se nota; una fórmula que
    apunta a la cuenta equivocada no."""
    apunta = {"titulo": "V", "hoja": "V", "columnas": COLS, "filas": [
        {"label": "x", "valores": [0, 0], "formula_tpl": "={h:Chk:NO EXISTE}"}]}
    destino = {"titulo": "Chk", "hoja": "Chk", "columnas": COLS,
               "filas": [{"label": "otra cosa", "valores": [1, 2]}]}
    ws = _libro([apunta, destino])["V"]
    assert ws.cell(5, 2).value is None


# ── Las invariantes del bloque ──────────────────────────────────────────────

def test_NINGUNA_referencia_a_otra_hoja_lleva_numero_de_fila():
    """⚠️ La razón de ser de todo esto.

    Si alguien vuelve a escribir `'Checkbook Planilla'!B12`, la fórmula queda
    bien hoy y apunta a otra cuenta en cuanto el escenario cambie de tamaño."""
    import re

    src = _src()
    fijas = re.findall(r"'[^']*Checkbook[^']*'!\$?[A-Z]{1,2}\$?\d+", src)
    fijas += re.findall(r"'[^']*(?:Detalle|Plantilla)[^']*'!\$?[A-Z]{1,2}\$?\d+", src)
    assert not fijas, f"referencias con número de fila fijo: {fijas[:5]}"


def test_toda_hoja_externa_se_nombra_con_h_o_con_SUMIF():
    """Las dos formas válidas: `{h:Hoja:Rótulo}`, que resuelve el exportador, o
    `SUMIF` por rótulo, que se autocorrige dentro de Excel."""
    import re

    src = _src()
    # Toda hoja externa que se nombre tiene que aparecer dentro de `H(...)` o
    # de `SUMIF(...)`, nunca suelta en una cadena con una celda al lado.
    nombradas = set(re.findall(r'H\("([^"]+)"', src)) | set(
        re.findall(r'SUMIF\("([^"]+)"', src))
    assert "Checkbook Planilla" in nombradas, nombradas
    assert len(nombradas) >= 3, f"se esperaban varias hojas: {nombradas}"
    assert "IFERROR(SUMIF(" in src, (
        "el SUMIF tiene que ir dentro de IFERROR: un libro sin los checkbooks "
        "—«Sólo esta vista»— daría #REF! y dejaría media hoja en rojo")


def test_cada_CHECK_dice_cuando_NO_pudo_comprobar():
    """⚠️ Sin esto, un CHECK cuya contraparte quedó vacía da `valor − vacío =
    valor`: la fila dice «−6.517.247,39» y se lee como un descuadre
    catastrófico cuando lo que pasó es que faltaba la hoja."""
    src = _src()
    assert 'const chk = (ref: string, resta: string) =>' in src
    assert '"sin hoja"' in src
    # Los cinco CHECK contra otra hoja usan el ayudante, no un ROUND pelado.
    for clave in ("kIng", "kCos", "kPay", "kCcss", "kAgui"):
        bloque = src.split(f'push("{clave}"')[1].split("});")[0]
        assert "chk(" in bloque, f"{clave} no dice cuándo no pudo comprobar"


def test_si_al_P_y_L_le_falta_un_renglon_NO_se_emite_media_validacion():
    """Media validación es peor que ninguna: los checks que sí salen dan cero y
    se leen como «todo bien»."""
    src = _src()
    assert "const faltan = Object.values(ARRIBA).filter" in src
    assert "if (faltan.length) return [];" in src


def test_el_cuadro_por_categoria_lo_engancha():
    src = sin_comentarios(
        (FRONT / "lib/planningReport.ts").read_text(encoding="utf-8"))
    bloque = src.split("export function cuadroPlanningPorCategoria")[1]
    bloque = bloque.split("export function")[0]
    assert "filasDeValidacion(" in bloque
    # ⚠️ ANTES de las fórmulas: sus ordinales se cuentan sobre el arreglo final.
    assert bloque.index("filasDeValidacion(") < bloque.index("componentesDelPL("), (
        "el bloque se agrega DESPUÉS de calcular las fórmulas: los ordinales "
        "quedarían contados sobre una lista más corta que la que se escribe")
