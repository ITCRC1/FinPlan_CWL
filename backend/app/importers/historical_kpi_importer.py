"""
Historical KPI importer for Budget2026_Revenue_CORCO.xlsx → sheet 'Rooms'.

The 'Rooms' sheet carries hotel-total monthly actuals in stacked blocks:

  "Key Indicators 2024"   (header)
    Total available Rooms      cols Jan..Dec
    Total Rooms Occupied       cols Jan..Dec
    Total Guests               cols Jan..Dec
    % Occupancy                cols Jan..Dec
    Average Daily Room Occ.     cols Jan..Dec  (= ADR)
  "Key Indicators 2025"   (same layout)
  "Key Indicators 2026..." (Budget — skipped here)
  ...
  "Revenue 2024"             cols Jan..Dec
  "Revenue 2025"             cols Jan..Dec

Labels are in column B (0-indexed col 1); months span cols 2..13 (Jan..Dec).
RevPAR is derived as revenue / rooms_available (not stored in the sheet).
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.models.historical_kpi import HistoricalKpi
from app.hotel_actual import HOTEL_ID

MONTH_COLS = list(range(2, 14))  # 0-indexed cols for Jan..Dec


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, str) and not v.strip():
        return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def import_historical_kpi(
    xlsx_path: str | Path,
    hotel_id: str = HOTEL_ID,
    years: tuple[int, ...] = (2024, 2025),
) -> list[HistoricalKpi]:
    """Parse the 'Rooms' sheet and return HistoricalKpi ORM objects (hotel total, room_type_id=0)."""
    df = pd.ExcelFile(str(xlsx_path)).parse("Rooms", header=None, dtype=object)
    nrows = len(df)

    def cell(r: int, c: int):
        if r is None or r < 0 or r >= nrows:
            return None
        v = df.iat[r, c]
        return None if pd.isna(v) else v

    def label(r: int) -> str:
        v = cell(r, 1)
        return str(v).strip() if v is not None else ""

    records: list[HistoricalKpi] = []
    for year in years:
        ki_row = None
        rev_row = None
        for r in range(nrows):
            lab = label(r).lower()
            if lab.startswith(f"key indicators {year}"):
                ki_row = r
            elif lab.startswith(f"revenue {year}"):
                rev_row = r
        if ki_row is None:
            continue

        # Map indicator rows within the block (stop at the next year's header).
        rows: dict[str, int] = {}
        for r in range(ki_row + 1, ki_row + 9):
            lab = label(r).lower()
            if lab.startswith("key indicators"):
                break
            if "available" in lab:
                rows["avail"] = r
            elif "occupied" in lab:
                rows["occ"] = r
            elif "guest" in lab:
                rows["guests"] = r
            elif "occupancy" in lab:
                rows["occupancy"] = r
            elif "average daily" in lab:
                rows["adr"] = r

        for mi, col in enumerate(MONTH_COLS):
            avail = _dec(cell(rows.get("avail", -1), col))
            occ = _dec(cell(rows.get("occ", -1), col))
            guests = _dec(cell(rows.get("guests", -1), col))
            occupancy = _dec(cell(rows.get("occupancy", -1), col))
            adr = _dec(cell(rows.get("adr", -1), col))
            revenue = _dec(cell(rev_row, col)) if rev_row is not None else Decimal("0")
            revpar = (revenue / avail) if avail else Decimal("0")

            rec = HistoricalKpi(
                id=str(uuid.uuid4()),
                hotel_id=hotel_id,
                year=year,
                month=mi + 1,
                room_type_id=0,
                rooms_available=int(avail),
                rooms_occupied=occ,
                guests=guests,
                occupancy_pct=occupancy,
                adr_usd=adr,
                revpar_usd=revpar,
                revenue_usd=revenue,
                source="ACTUAL_IMPORT",
            )
            records.append(rec)

    return records
