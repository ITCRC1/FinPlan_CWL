"""Importa un Cash Flow presentado (Excel) a una versión plana congelada.

Formato esperado (= Cash Flow Budget del sistema):
    Section · Description · Ene-26 .. Dic-26 · Full Year
con un encabezado que contiene la celda "Description" y debajo las filas de datos.
Tolerante a la posición: localiza la fila de encabezado y la columna Description,
toma las 12 columnas siguientes como meses y la 13ª (si existe) como Full Year.
"""
from __future__ import annotations
from typing import Optional

# Etiquetas que son subtotales/totales (para marcarlas y no confundirlas con inputs)
_TOTAL_HINTS = (
    "total expenses", "subtotal", "net operating income", "net change",
    "beginning cash", "ending cash", "total ",
)


def _num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(",", "").replace(" ", " ").strip()
    if not s or s in ("-", "—"):
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("%", "").strip()
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return 0.0


def _is_total(label: str) -> bool:
    low = label.strip().lower()
    return any(h in low for h in _TOTAL_HINTS)


def parse_cashflow_version(path_or_file) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(path_or_file, data_only=True, read_only=True)
    ws = wb.active
    grid = [list(r) for r in ws.iter_rows(values_only=True)]
    if not grid:
        return []
    ncols = max(len(r) for r in grid)

    def cell(r, c):  # 0-based, seguro
        row = grid[r] if 0 <= r < len(grid) else []
        return row[c] if 0 <= c < len(row) else None

    # 1) localizar la fila de encabezado y la columna "Description"
    hdr_row, desc_col = -1, -1
    for r in range(min(20, len(grid))):
        for c in range(ncols):
            v = cell(r, c)
            if v is not None and str(v).strip().lower() == "description":
                hdr_row, desc_col = r, c
                break
        if hdr_row >= 0:
            break
    if hdr_row < 0:
        # fallback: primera fila con ≥6 celdas numéricas seguidas
        for r in range(min(20, len(grid))):
            nums = sum(1 for c in range(ncols) if isinstance(cell(r, c), (int, float)))
            if nums >= 6:
                hdr_row = r - 1 if r > 0 else r
                desc_col = 1
                break
    if hdr_row < 0:
        return []

    section_col = desc_col - 1 if desc_col > 0 else None
    month_cols = list(range(desc_col + 1, desc_col + 13))
    fy_col = desc_col + 13
    fy_hdr = cell(hdr_row, fy_col)
    has_fy = fy_hdr is not None and any(t in str(fy_hdr).lower() for t in ("full", "year", "total", "fy", "año", "ano"))

    out = []
    last_section = ""
    for r in range(hdr_row + 1, len(grid)):
        label = cell(r, desc_col)
        label = str(label).strip() if label is not None else ""
        sect = cell(r, section_col) if section_col is not None else None
        sect = str(sect).strip() if sect is not None else ""
        if sect:
            last_section = sect
        if not label:
            # fila vacía → corta si tampoco hay valores
            if all(_num(cell(r, c)) == 0 for c in month_cols):
                continue
        values = [_num(cell(r, c)) for c in month_cols]
        fy = _num(cell(r, fy_col)) if has_fy else round(sum(values), 2)
        out.append({
            "section": last_section,
            "label": label,
            "values": values,
            "full_year": fy,
            "is_total": _is_total(label),
        })
    return out
