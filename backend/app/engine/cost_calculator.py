"""
Cost of Sales calculator — Phase 5.

Pure Python, no DB calls. Receives hydrated model objects.

6 driver types:
  REVENUE_LINE  → entry.driver_pct_or_rate × revenue_line amount
  OCC_ROOMS     → entry.driver_pct_or_rate × rooms_occupied
  GUESTS        → entry.driver_pct_or_rate × total_guests
  AVAIL_ROOMS   → entry.driver_pct_or_rate × rooms_available
  KILOS         → entry.driver_pct_or_rate × total_kilos (laundry)
  MANUAL        → value preserved; engine never overwrites it
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.models.cost_entry import CostEntry
from app.engine.revenue_calculator import RevenueResult

ZERO = Decimal("0")
CENT = Decimal("0.01")


@dataclass
class CostSummary:
    """Aggregated CoS by dept for one month."""
    dept_code: str
    month: int
    entries: list[tuple[str, str, Decimal]]  # (account_code, account_name, amount)

    @property
    def total(self) -> Decimal:
        return sum(a for _, _, a in self.entries)


def _get_revenue_line(rev: RevenueResult, line_ref: str) -> Decimal:
    """Map revenue_line_ref string to actual revenue amount."""
    mapping = {
        "ROOMS":          rev.rooms,
        "FOOD":           rev.food,
        "BEVERAGE":       rev.beverage,
        "ACTIVITIES":     rev.activities,
        "TRANSPORT":      rev.transport,
        "SUSTAINABILITY": rev.sustainability,
        "INNOCEANA":      rev.innoceana,
        "RETAIL":         rev.retail,
        "SPA":            rev.spa,
    }
    return mapping.get(line_ref.upper(), ZERO)


def calculate_cost_amount(
    entry: CostEntry,
    month: int,
    rev: Optional[RevenueResult],
    rooms_occupied: Optional[Decimal] = None,
    guests: Optional[Decimal] = None,
    rooms_available: Optional[int] = None,
    kilos: Optional[Decimal] = None,
    fte: Optional[Decimal] = None,
) -> Decimal:
    """
    Calculate the USD amount for a single CostEntry in a given month.
    MANUAL entries return their stored value unchanged.
    Returns 0 when the required driver input is unavailable.
    """
    if entry.calc_mode == "MANUAL":
        return entry.get_month(month)

    rate = entry.get_rate(month)  # monthly rate if set, else base rate
    driver = (entry.driver_type or "").upper()

    if driver == "REVENUE_LINE":
        if rev is None:
            return ZERO
        base = _get_revenue_line(rev, entry.revenue_line_ref)
        return (base * rate).quantize(CENT, ROUND_HALF_UP)

    if driver == "OCC_ROOMS":
        base = rooms_occupied or ZERO
        return (base * rate).quantize(CENT, ROUND_HALF_UP)

    if driver == "GUESTS":
        base = guests or ZERO
        return (base * rate).quantize(CENT, ROUND_HALF_UP)

    if driver == "AVAIL_ROOMS":
        base = Decimal(rooms_available or 0)
        return (base * rate).quantize(CENT, ROUND_HALF_UP)

    if driver == "KILOS":
        base = kilos or ZERO
        return (base * rate).quantize(CENT, ROUND_HALF_UP)

    # FTE: monto POR PERSONA × la gente que hubo ese mes. Es el caso de la
    # cafetería — se come según cuánta gente haya, así que octubre con el lodge
    # cerrado (FTE 0) no cuesta nada, sin que nadie tenga que acordarse.
    if driver == "FTE":
        base = fte or ZERO
        return (base * rate).quantize(CENT, ROUND_HALF_UP)

    return ZERO


def recalculate_cost_entries(
    entries: list[CostEntry],
    month: int,
    rev: Optional[RevenueResult],
    rooms_occupied: Optional[Decimal] = None,
    guests: Optional[Decimal] = None,
    rooms_available: Optional[int] = None,
    kilos: Optional[Decimal] = None,
    fte: Optional[Decimal] = None,
) -> None:
    """
    Mutate cost entries in-place for a given month.
    MANUAL entries are not touched.
    Called from recalculate_scenario() as step 4.
    """
    for entry in entries:
        if entry.calc_mode == "DRIVER":
            amount = calculate_cost_amount(
                entry, month, rev,
                rooms_occupied=rooms_occupied,
                guests=guests,
                rooms_available=rooms_available,
                kilos=kilos,
                fte=fte,
            )
            entry.set_month(month, amount)


def build_cost_summary(
    entries: list[CostEntry],
    month: int,
) -> Decimal:
    """Return total CoS across all entries for a dept/month."""
    return sum(e.get_month(month) for e in entries)
