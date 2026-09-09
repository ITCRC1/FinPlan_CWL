# -*- coding: utf-8 -*-
"""La plantilla de clasificación del punto de equilibrio: baja, se llena, sube.

Owner, 2026-09-09: *«necesito que revises la configuración, la forma de asignar
el % de fijo o variable. Veo esa asignación muy complicada, debe ser muy fácil.
Inclusive que se baje a Excel y ahí se haga la asignación y se vuelva a subir;
veo que en la pantalla es muy difícil»*.

## Por qué la pantalla no alcanzaba

La configuración va **departamento por departamento**: entrar a uno, marcar
filas con casillas, teclear un porcentaje, salir, entrar al siguiente. Con 798
reglas repartidas en 22 departamentos eso son 22 pantallas y cientos de clics
para una decisión que el owner toma de corrido, mirando todo junto.

En Excel lo hace como lo piensa: ordena, filtra, arrastra una celda hacia abajo,
compara departamentos entre sí. Y queda un archivo que puede revisar con otro
antes de subirlo — cosa que una pantalla de autosave no permite.

## Las reglas del archivo

**Una sola columna se edita: `% Variable`.** El `% Fijo` es su complemento y va
como FÓRMULA (`=100-G8`), no como número: dos columnas editables que tienen que
sumar 100 son dos formas de decir lo mismo y una oportunidad de que discrepen.

**La hoja va protegida** con todo bloqueado menos esa columna. No es
desconfianza: es que el archivo se sube de vuelta y se aparea por `id`. Una
columna corrida a mano rompe el apareo, y el que sube no se entera.

⚠️ **Una celda vacía NO es un cero.** Vacío significa «no toqué esta fila» y la
regla se queda como está. Tratarlo como cero convertiría un descuido —borrar una
celda, filtrar y no darse cuenta— en volver 100% fija una cuenta variable, sin
que nada avise. Para poner cero hay que escribir `0`.

**El MONTO viaja en el archivo, aunque no se edite.** Sin él la clasificación se
hace a ciegas: da lo mismo equivocarse en una cuenta de $80.000 que en una de
$12, y no da lo mismo. Es la misma razón por la que la pantalla lo trae.

## ⚠️ La clasificación NO tiene mes, y el archivo tampoco

Owner, 2026-09-09: *«el criterio no debe ser por mes; debe ser completo, uno
solo sin diferencial mes»*.

Y el modelo ya era así: la llave de `be_cost_classification` es
`(propiedad, departamento, cuenta, línea)` — **no hay columna de mes**. Una
cuenta es variable o fija por su naturaleza, no según el mes que se mire.

Lo que sí tenía mes era la PANTALLA, y sólo para mostrar el monto. Acá el monto
va del **año completo**, que es la escala a la que se decide: doce meses de una
cuenta dicen si el gasto sigue a la venta; un mes suelto puede ser un accidente.
"""
from __future__ import annotations

from decimal import Decimal

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from openpyxl.styles import Protection

from app.export.excel_base import (align, fill, font, protect_sheet,
                                   set_col_widths, unlock, workbook_to_bytes)

#: Para volver a bloquear una celda que ya se desbloqueó.
_BLOQUEADA = Protection(locked=True)

#: El orden de las columnas. La posición importa: el lector de vuelta busca por
#: ENCABEZADO y no por número de columna, pero si alguien agrega una en el medio
#: el archivo viejo tiene que seguir subiendo, y para eso el encabezado manda.
COLUMNAS = [
    ("id", 34, "La llave. NO se toca: es con lo que se aparea al subir."),
    ("Departamento", 22, ""),
    ("Bloque", 20, ""),
    ("Depto GL", 10, ""),
    ("Cuenta", 10, ""),
    ("Nombre de la cuenta", 38, ""),
    ("Línea del P&L", 20, ""),
    ("% Variable", 12, "LA ÚNICA COLUMNA QUE SE EDITA. 0 a 100."),
    ("% Fijo", 10, "Se calcula solo: 100 menos el variable."),
    ("Monto del año", 17, "Para no clasificar a ciegas."),
    ("Clase de origen", 16, ""),
]

#: La columna que se edita, en número (1-based). Se deriva del encabezado para
#: que agregar una columna a la izquierda no rompa la protección en silencio.
COL_PCT = [c[0] for c in COLUMNAS].index("% Variable") + 1
COL_FIJO = [c[0] for c in COLUMNAS].index("% Fijo") + 1

FILA_ENCABEZADO = 8          # las siete de arriba son la leyenda


def construir_plantilla(filas: list[dict], hotel: str, escenario: str) -> bytes:
    """`filas` viene del endpoint: ya trae monto, nombre y el % actual.

    No recibe mes a propósito — ver el encabezado. El `escenario` es de
    dónde salió el MONTO que se muestra, no un ámbito de la clasificación.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Clasificación"

    # ── La leyenda ───────────────────────────────────────────────────────────
    #
    # Va ARRIBA y no en una hoja aparte: una instrucción en otra pestaña es una
    # instrucción que no se lee. Son cinco líneas y dicen lo único que hay que
    # saber para no romper el archivo.
    ws["A1"] = f"Clasificación fijo / variable — {hotel}"
    ws["A1"].font = font(bold=True, size=13)
    ws["A2"] = ("Escribí el % VARIABLE de cada cuenta en la columna resaltada. "
                "El % fijo se calcula solo.")
    ws["A3"] = ("Una celda VACÍA deja la regla como está. Para poner cero, "
                "escribí 0.")
    ws["A4"] = ("El resto de la hoja está bloqueado a propósito: el archivo se "
                "sube de vuelta y se aparea por la columna «id».")
    ws["A5"] = ("Guardá el archivo en .xlsx y subilo desde la misma pantalla "
                "de donde lo bajaste.")
    ws["A6"] = (f"La clasificación es UNA sola para todo el año, sin mes. "
                f"El monto que se muestra es el del AÑO COMPLETO de {escenario}, "
                f"para no clasificar a ciegas.")
    for r in (2, 3, 4, 5, 6):
        ws.cell(r, 1).font = font(size=10, color="4A5568")

    # ── Encabezado ───────────────────────────────────────────────────────────
    for i, (titulo, _ancho, nota) in enumerate(COLUMNAS, start=1):
        c = ws.cell(FILA_ENCABEZADO, i, titulo)
        c.font = font(bold=True, color="FFFFFF")
        c.fill = fill("2D3748" if i != COL_PCT else "2B6CB0")
        c.alignment = align(h="center", wrap=True)
        if nota:
            c.comment = None            # el comentario vive en la leyenda
    ws.freeze_panes = ws.cell(FILA_ENCABEZADO + 1, 1)
    ws.auto_filter.ref = (f"A{FILA_ENCABEZADO}:"
                          f"{get_column_letter(len(COLUMNAS))}"
                          f"{FILA_ENCABEZADO + len(filas)}")
    set_col_widths(ws, {i: a for i, (_t, a, _n) in enumerate(COLUMNAS, start=1)})

    # ── Las filas ────────────────────────────────────────────────────────────
    r = FILA_ENCABEZADO
    for f in filas:
        r += 1
        pv = Decimal(str(f.get("pct_variable") or 0))
        ws.cell(r, 1, f["id"]).font = font(size=8, color="A0AEC0")
        ws.cell(r, 2, f.get("departamento") or "")
        ws.cell(r, 3, f.get("be_section") or "")
        ws.cell(r, 4, f.get("dept_code") or "")
        ws.cell(r, 5, f.get("account") or "")
        ws.cell(r, 6, f.get("account_name") or "")
        ws.cell(r, 7, f.get("pl_line") or "")

        celda = ws.cell(r, COL_PCT, float(pv * 100))
        celda.number_format = "0"
        celda.fill = fill("EBF8FF")
        celda.alignment = align(h="center")
        unlock(celda)                   # la ÚNICA editable

        # El fijo como FÓRMULA: si fuera un número, el archivo podría volver
        # diciendo 30 y 30, y habría que elegir a cuál creerle.
        fijo = ws.cell(r, COL_FIJO,
                       f"=100-{get_column_letter(COL_PCT)}{r}")
        fijo.number_format = "0"
        fijo.alignment = align(h="center")
        fijo.font = font(color="718096")

        m = ws.cell(r, 10, float(f.get("amount") or 0))
        m.number_format = '#,##0.00'
        ws.cell(r, 11, f.get("original_class") or "")

        # ⚠️ Las líneas excluidas del cálculo se muestran pero NO se editan: el
        # impuesto de renta no tiene parte variable que asignar. Dejarlas
        # editables sería ofrecer una decisión que el motor ignora.
        if f.get("excluded_from_be"):
            celda.value = None
            celda.fill = fill("EDF2F7")
            celda.protection = _BLOQUEADA        # vuelve a quedar bloqueada
            ws.cell(r, 11).value = "excluida del cálculo"
            ws.cell(r, 11).font = font(italic=True, color="A0AEC0")

    protect_sheet(ws)
    return workbook_to_bytes(wb)


def leer_plantilla(crudo: bytes) -> list[tuple[str, object]]:
    """Devuelve `[(id, valor crudo del % variable)]` tal como vino el archivo.

    **Función PURA y sin criterio de negocio**: no convierte, no valida, no
    decide qué es un cero. Sólo encuentra el encabezado y saca las dos columnas
    que importan. Quién puede cambiar qué lo decide el endpoint, que es el que
    ve la base.

    ⚠️ El encabezado se busca por CONTENIDO, no por número de fila. El día que
    la leyenda crezca una línea, los archivos ya bajados tienen que seguir
    subiendo — si no, cada cambio de formato invalida en silencio el archivo que
    alguien tenía a medio llenar.
    """
    import io

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(crudo), data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    filas = list(ws.iter_rows(values_only=True))

    cab = idx = None
    for i, fila in enumerate(filas):
        vals = [str(v).strip().lower() if v is not None else "" for v in fila]
        if "id" in vals and any("variable" in v for v in vals):
            cab, idx = vals, i
            break
    if cab is None:
        raise ValueError("el archivo no tiene el encabezado de la plantilla")

    c_id = cab.index("id")
    c_pct = next(i for i, v in enumerate(cab) if "variable" in v)

    fuera = []
    for fila in filas[idx + 1:]:
        if c_id >= len(fila):
            continue
        rid = str(fila[c_id] or "").strip()
        if not rid:
            continue
        fuera.append((rid, fila[c_pct] if c_pct < len(fila) else None))
    return fuera
