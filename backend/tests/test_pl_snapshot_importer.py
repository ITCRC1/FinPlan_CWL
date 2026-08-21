"""
Tests for the multi-scenario P&L upload parser — pl_snapshot_importer.

Run: pytest tests/test_pl_snapshot_importer.py -v

Builds a tiny synthetic workbook mirroring the real "upload" layout (version row
15, stats rows, section-aware P&L) and checks block detection + mapping.
"""
import io
from decimal import Decimal
import openpyxl

from app.importers.pl_snapshot_importer import parse_pl_snapshot


def _build(tmp_blocks):
    """tmp_blocks: list of (label,). Two blocks, 12 months each from col 5."""
    wb = openpyxl.Workbook()
    ws = wb.active
    def put(r, c, v): ws.cell(row=r, column=c, value=v)
    # Fila 15 = rótulo del bloque · Fila 14 = mes de cada columna.
    # El parser detecta los bloques por (rótulo + mes): así tolera bloques de ancho
    # variable y columnas "Full Year" intercaladas, como en el archivo real.
    MESES = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
    for b, label in enumerate(tmp_blocks):
        for m in range(12):
            put(15, 5 + b * 12 + m, label)
            put(14, 5 + b * 12 + m, MESES[m])
    # stats rows (only Jan filled, col of each block)
    for b in range(len(tmp_blocks)):
        c0 = 5 + b * 12
        put(3, 4, "Total available Rooms"); put(3, c0, 930)
        put(4, 4, "Total Rooms Occupied");  put(4, c0, 429)
        put(6, 4, "Total Guests");          put(6, c0, 711)
        put(7, 4, "% Occupancy");           put(7, c0, 0.46)
        put(8, 4, "Average Daily Room Only"); put(8, c0, 359.8)
    # P&L section-aware
    put(16, 4, "REVENUE")
    put(17, 4, "Rooms"); put(18, 4, "F&B")
    put(28, 4, "TOTAL INCOMES")
    put(30, 4, "Operating Expenses")
    put(32, 4, "Rooms")
    put(79, 4, "TOTAL GROSS OPERATING PROFIT")
    put(123, 4, "EARNINGS BEFORE INCOME TAXES")
    put(128, 4, "EARNINGS AFTER INCOME TAXES")
    for b in range(len(tmp_blocks)):
        c0 = 5 + b * 12
        put(17, c0, 100000); put(18, c0, 50000); put(28, c0, 150000)
        put(32, c0, 40000); put(79, c0, 70000)
        put(123, c0, 60000); put(128, c0, 42000)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_detects_blocks_and_versions():
    data = _build(["Actual 2024", "Budget 2026"])
    blocks = parse_pl_snapshot(data)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "ACTUAL" and blocks[0]["year"] == 2024
    assert blocks[1]["type"] == "BUDGET" and blocks[1]["year"] == 2026


def test_section_aware_codes():
    blocks = parse_pl_snapshot(_build(["Actual 2024"]))
    jan = blocks[0]["lines"][1]
    assert jan["REV_ROOMS"] == Decimal("100000")
    assert jan["REV_FB"] == Decimal("50000")
    assert jan["TOTAL_REVENUES"] == Decimal("150000")
    assert jan["OPEXP_ROOMS"] == Decimal("40000")   # same "Rooms" label, OPEXP section
    assert jan["GOP"] == Decimal("70000")
    assert jan["EBT"] == Decimal("60000")
    assert jan["NET_PROFIT"] == Decimal("42000")


def test_stats_parsed():
    blocks = parse_pl_snapshot(_build(["Actual 2024"]))
    s = blocks[0]["stats"][1]
    assert s["rooms_available"] == Decimal("930")
    assert s["rooms_occupied"] == Decimal("429")
    assert s["adr"] == Decimal("359.8")


def test_forecast_label():
    blocks = parse_pl_snapshot(_build(["Forecast Apr 2026"]))
    assert blocks[0]["type"] == "FORECAST" and blocks[0]["year"] == 2026
