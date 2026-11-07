"""La grilla de un libro de cuadros: qué hay en cada celda y con qué estilo.

**Para qué (owner, 2026-11-06).** *«automatiza este [Budget Package] de una,
así como está… cada tab»*. El libro se refresca desde Excel con «Actualizar
todo»: Power Query no puede traer un archivo con su formato, pero sí una tabla.
Esta función convierte el libro que arma el exportador de siempre en esa tabla —
valor por celda y un número de estilo por celda— y el Excel en vivo la vuelve a
pintar con formato condicional.

⚠️ **Lee el libro YA ARMADO por `build_cuadros_workbook`, no rehace el diseño.**
Las filas donde va la cabecera, la franja de estadísticas, qué es total y qué
es sección, el formato de cada número: todo eso lo decide `cuadro_excel.py`. Si
esta función lo calculara por su cuenta habría dos diseños del mismo libro, y
el Excel que se refresca dejaría de parecerse al que se baja con el botón el
primer día que alguien tocara uno solo.

La sangría de la etiqueta viaja como espacios al frente del texto: el formato
condicional de Excel no sabe poner sangría, y sin ella el checkbook pierde la
jerarquía (departamento › cuenta › sub-línea).
"""
from __future__ import annotations

import io

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

#: Espacios por nivel de sangría. Excel usa ~3 caracteres por nivel.
ESPACIOS_POR_NIVEL = 3


def _color(c) -> str | None:
    """El RGB de un color de openpyxl, o None si no es un color fijo."""
    if c is None or getattr(c, "type", None) != "rgb":
        return None
    rgb = c.rgb if isinstance(c.rgb, str) else None
    if not rgb or rgb in ("00000000",):
        return None
    return rgb[-6:].upper()


def _borde(lado) -> str | None:
    return getattr(lado, "style", None) or None


def _estilo(celda) -> dict:
    """Lo que el formato condicional SÍ puede repetir: relleno, negrita, color
    y subrayado de la letra, formato de número y bordes."""
    f = celda.font
    relleno = None
    if celda.fill is not None and celda.fill.fill_type == "solid":
        relleno = _color(celda.fill.fgColor)
    b = celda.border
    return {
        "relleno": relleno,
        "negrita": bool(f.b),
        "color": _color(f.color) if f is not None else None,
        "subrayado": bool(f.u),
        "formato": celda.number_format if celda.number_format != "General" else None,
        "arriba": _borde(b.top), "abajo": _borde(b.bottom),
        "izq": _borde(b.left), "der": _borde(b.right),
    }


def grilla_de_libro(contenido: bytes) -> dict:
    """Cada hoja del libro como una tabla de valores y una de estilos.

    Devuelve::

        {"hojas": [{"nombre", "filas", "columnas", "anchos", "congelar",
                    "valores": [[...]], "estilos": [[id...]]}],
         "estilos": [{...}, ...]}       # el id es el índice en esta lista

    ⚠️ Con `data_only=True`: las celdas de total llevan fórmula (`=SUM(...)`) y
    el exportador les deja pegado el resultado. Lo que el Excel en vivo muestra
    es ese número, el mismo que se ve al abrir el libro del botón.
    """
    wb_valores = load_workbook(io.BytesIO(contenido), data_only=True)
    wb_formulas = load_workbook(io.BytesIO(contenido))
    tabla: list[dict] = []
    ids: dict[tuple, int] = {}

    def id_de(est: dict) -> int:
        llave = tuple(sorted(est.items()))
        if llave not in ids:
            ids[llave] = len(tabla)
            tabla.append(est)
        return ids[llave]

    hojas = []
    for ws in wb_valores.worksheets:
        wf = wb_formulas[ws.title]
        n_fil, n_col = ws.max_row, ws.max_column
        valores, estilos = [], []
        for r in range(1, n_fil + 1):
            fila_v, fila_e = [], []
            for c in range(1, n_col + 1):
                celda = ws.cell(r, c)
                v = celda.value
                if v is None and isinstance(wf.cell(r, c).value, str) \
                        and str(wf.cell(r, c).value).startswith("="):
                    v = None          # fórmula sin resultado guardado: vacía
                sangria = int(celda.alignment.indent or 0) if celda.alignment else 0
                if isinstance(v, str) and sangria:
                    v = " " * (ESPACIOS_POR_NIVEL * sangria) + v
                fila_v.append(v)
                fila_e.append(id_de(_estilo(celda)))
            valores.append(fila_v)
            estilos.append(fila_e)
        anchos = [round(ws.column_dimensions[get_column_letter(c)].width or 8.43, 2)
                  for c in range(1, n_col + 1)]
        hojas.append({
            "nombre": ws.title, "filas": n_fil, "columnas": n_col,
            "anchos": anchos, "congelar": ws.freeze_panes,
            "valores": valores, "estilos": estilos,
        })
    return {"hojas": hojas, "estilos": tabla}
