"""
Load the CWL working workbook into scenarios + ActualEntry rows.

Ties the parser (actual_pl_importer) to the database: for each version block it
finds-or-creates a Scenario and (re)loads its account-level detail. The P&L
engine then computes each scenario's P&L from that detail
(see recalculate.compute_pl_month).
"""
from __future__ import annotations

from sqlalchemy import select, delete

from app.models.scenario import Scenario
from app.models.actual_entry import ActualEntry
from app.importers.actual_pl_importer import (
    import_actual_pl, VERSION_BLOCKS, MONTH_KEYS, DEFAULT_SHEET,
)
from app.hotel_actual import HOTEL_ID

# Version block -> (scenario_type, year, version label)
BLOCK_TO_SCENARIO: dict[str, tuple[str, int, str]] = {
    "ACTUAL_2024":       ("ACTUAL",   2024, "actual"),
    "ACTUAL_2025":       ("ACTUAL",   2025, "actual"),
    "ACTUAL_2026":       ("ACTUAL",   2026, "actual"),
    "FORECAST_2026":     ("FORECAST", 2026, "FY"),
    "FORECAST_APR_2026": ("FORECAST", 2026, "reforecast-apr"),
    "BUDGET_2026":       ("BUDGET",   2026, "from-xlsx"),
}

# every parser block must have a scenario mapping
assert set(BLOCK_TO_SCENARIO) == set(VERSION_BLOCKS)


def _is_all_zero(row: dict) -> bool:
    return all((row.get(m) or 0) == 0 for m in MONTH_KEYS)


async def _find_or_create_scenario(
    session, hotel_id: str, year: int, stype: str, version: str, source_file: str
) -> Scenario:
    s = (await session.execute(
        select(Scenario).where(
            Scenario.hotel_id == hotel_id,
            Scenario.year == year,
            Scenario.type == stype,
            Scenario.version == version,
        )
    )).scalar_one_or_none()
    if s is not None:
        return s
    s = Scenario(
        hotel_id=hotel_id, year=year, type=stype, version=version,
        status="draft", source_file=source_file,
    )
    session.add(s)
    await session.flush()
    return s


async def load_actuals_workbook(
    session, path: str, hotel_id: str = HOTEL_ID,
    sheet: str = DEFAULT_SHEET, blocks: list[str] | None = None,
) -> dict:
    """
    Parse the workbook and load each version block into its scenario's
    ActualEntry rows (replacing any existing detail for that scenario).
    Returns a per-block summary {block: {scenario_id, type, year, version, rows}}.
    """
    import os
    source_file = os.path.basename(path)
    parsed = import_actual_pl(path, sheet)

    summary: dict[str, dict] = {}
    for block, rows in parsed.items():
        if blocks and block not in blocks:
            continue
        stype, year, version = BLOCK_TO_SCENARIO[block]
        scenario = await _find_or_create_scenario(
            session, hotel_id, year, stype, version, source_file
        )
        await session.execute(
            delete(ActualEntry).where(ActualEntry.scenario_id == scenario.id)
        )
        await session.flush()

        n = 0
        for r in rows:
            if _is_all_zero(r):
                continue
            ae = ActualEntry(
                scenario_id=scenario.id, hotel_id=hotel_id,
                dept_code=r["dept_code"], account_code=r["account_code"],
                account_name=r["account_name"],
            )
            for m in MONTH_KEYS:
                setattr(ae, m, r.get(m) or 0)
            session.add(ae)
            n += 1

        summary[block] = {
            "scenario_id": scenario.id, "type": stype, "year": year,
            "version": version, "rows": n,
        }

    await session.commit()
    return summary
