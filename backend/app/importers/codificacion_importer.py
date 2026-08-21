"""
Importer for 'Codificacion Planilla' Excel file → PayrollPosition templates.

The Codificacion Planilla file maps positions to payroll concepts in the HR system.
This importer extracts unique (dept_code, position_code) pairs and creates
PayrollPosition template rows with salary=0 / employee='VACANTE'.
Salary amounts and employee names must be filled in via the checkbook UI.

Sheet: Hoja1
Header row: row index 1 (second row)
Only '1-DEVENGADOS' rows are processed (earnings, not deductions/reserves).
Nivel2 is zero-padded to 4 digits → dept_code.
"""
import uuid
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.models.payroll_position import PayrollPosition


def _pad4(val) -> str:
    """Convert numeric nivel2 to zero-padded 4-char dept_code string."""
    try:
        return str(int(val)).zfill(4)
    except (ValueError, TypeError):
        return str(val).strip().zfill(4)


def import_codificacion(
    xlsx_path: str | Path,
    scenario_id: str,
    hotel_id: str,
    default_oct_fte: Decimal = Decimal("0.0"),
) -> list[PayrollPosition]:
    """
    Parse the Codificacion Planilla file and return PayrollPosition templates.

    One template per unique (nivel2=dept_code, nivel3=position_code) combination.
    Deduplication is by (dept_code, position_code) — only the first occurrence is kept.

    Args:
        xlsx_path: Path to 'Codificacion Planilla ...' Excel.
        scenario_id: Target scenario UUID.
        hotel_id: Hotel ID (e.g. 'CWL').
        default_oct_fte: FTE for October. Defaults 0.0 (CWL 2026 hotel closed in Oct).
    """
    df = pd.read_excel(str(xlsx_path), header=1, dtype=str)
    df.columns = [
        "seq", "dept_num", "dept_name", "pos_num", "pos_name",
        "tipo", "concept_num", "concept_desc", "emp_type",
        "nivel1", "nivel2", "nivel3", "nivel4", "nivel5", "nivel6", "nivel7",
    ]

    dev = df[df["tipo"] == "1-DEVENGADOS"].copy()

    seen: set[tuple[str, str]] = set()
    positions: list[PayrollPosition] = []

    for _, row in dev.iterrows():
        dept_code = _pad4(row["nivel2"])
        pos_code = str(row["nivel3"]).strip().zfill(3)
        key = (dept_code, pos_code)
        if key in seen:
            continue
        seen.add(key)

        dept_name = str(row["dept_name"]).strip()
        pos_name = str(row["pos_name"]).strip()
        emp_type = str(row["emp_type"]).strip()
        class_code = str(row["nivel4"]).strip().zfill(3)
        cat_code = str(row["nivel5"]).strip().zfill(3)

        positions.append(PayrollPosition(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=hotel_id,
            dept_code=dept_code,
            dept_name=dept_name,
            position_code=pos_code,
            position_name=pos_name,
            employee_name="VACANTE",
            employee_type=emp_type,
            class_code=class_code,
            category_code=cat_code,
            salary_amount=Decimal("0"),
            salary_currency="CRC",
            fte_jan=Decimal("1.0"),
            fte_feb=Decimal("1.0"),
            fte_mar=Decimal("1.0"),
            fte_apr=Decimal("1.0"),
            fte_may=Decimal("1.0"),
            fte_jun=Decimal("1.0"),
            fte_jul=Decimal("1.0"),
            fte_aug=Decimal("1.0"),
            fte_sep=Decimal("1.0"),
            fte_oct=default_oct_fte,
            fte_nov=Decimal("1.0"),
            fte_dec=Decimal("1.0"),
        ))

    return positions
