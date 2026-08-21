"""
Revenue calculator — pure Python, no DB dependencies.

Input: hydrated model objects (RateCard, OccupancyBudget, SalesChannelConfig, etc.)
Output: RevenueResult dataclass with all revenue lines for a given month.

Formulas verified against Budget2026_Revenue_CORCO.xlsx January 2026:
  Room Revenue  = Σ(rooms_occupied[type] × net_rate[type])          → $415,201.91
  Food Revenue  = total_rooms × pax_per_room × food_rate × net_factor → $113,356.58
  Beverage Rev  = food_revenue × bev_food_ratio (0.34)               → $38,541.24
  Activities    = total_rooms × pax_per_room × act_rate × net_factor  → $106,009.40
  Transport     = total_rooms × pax_per_room × trans_rate × net_factor → $36,735.93
  Sustainability= total_rooms × pax_per_room × sust_rate (no factor)  → $35,154.00
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.models.sales_channel_config import SalesChannelConfig, compute_net_factor
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.package_config import PackageConfig, COMPONENT_FOOD, COMPONENT_BEV, \
    COMPONENT_ACTIVITIES, COMPONENT_TRANSPORT, COMPONENT_SUSTAINABILITY
from app.models.revenue_other import OTHER_REVENUE_LINES, RevenueOther

CALENDAR_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# Línea de `RevenueOther` → campo de `RevenueResult`. Uno a uno en minúscula:
# la línea del checkbook y el campo del resultado son el mismo nombre, y eso
# es lo que permite que la lista se derive en vez de escribirse.
_OTHER_LINE_TO_FIELD = {ln: ln.lower() for ln in OTHER_REVENUE_LINES}


@dataclass
class RevenueResult:
    month: int
    year: int
    # Core revenue lines (USD)
    rooms: Decimal = Decimal("0")
    food: Decimal = Decimal("0")
    beverage: Decimal = Decimal("0")
    activities: Decimal = Decimal("0")
    transport: Decimal = Decimal("0")
    sustainability: Decimal = Decimal("0")
    # Other lines (from flat budgets)
    spa: Decimal = Decimal("0")
    retail: Decimal = Decimal("0")
    fnb_misc: Decimal = Decimal("0")
    innoceana: Decimal = Decimal("0")
    laundry: Decimal = Decimal("0")
    # Club Madresal, sus TRES fuentes de ingreso — una por cuenta contable, que
    # es como las lleva el catálogo (depto 260):
    #   4500 la cuota de acceso  · sale del driver socios × precio
    #   4501 actividad fin de año · se digita
    #   4502 visitantes           · se digita
    # Las tres caen en REV_CLUB, igual que Food + Beverage + Misc caen en REV_FB.
    # El desarrollo inmobiliario que hay detrás NO es parte de este P&L.
    club: Decimal = Decimal("0")
    club_actividad: Decimal = Decimal("0")
    club_visitantes: Decimal = Decimal("0")
    # KPIs
    rooms_available: int = 0
    rooms_occupied: Decimal = Decimal("0")
    guests: Decimal = Decimal("0")
    net_factor: Decimal = Decimal("0")

    @property
    def total_package(self) -> Decimal:
        return self.rooms + self.food + self.beverage + self.activities + self.transport

    @property
    def total_revenue(self) -> Decimal:
        return (self.rooms + self.food + self.beverage + self.activities
                + self.transport + self.sustainability + self.spa
                + self.retail + self.fnb_misc + self.innoceana + self.laundry
                # El Club quedaba fuera: en un escenario de checkbook su ingreso
                # sí llega al P&L (por REV_CLUB) pero no aparecía en este total,
                # así que las dos cifras se contradecían. Hoy no se nota porque
                # está en cero en todos los escenarios; se corrige antes de que
                # haya plata que lo delate.
                + self.club + self.club_actividad + self.club_visitantes)

    @property
    def occupancy_pct(self) -> Decimal:
        if not self.rooms_available:
            return Decimal("0")
        return (self.rooms_occupied / self.rooms_available).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

    @property
    def adr(self) -> Decimal:
        if not self.rooms_occupied:
            return Decimal("0")
        return (self.rooms / self.rooms_occupied).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def revpar(self) -> Decimal:
        if not self.rooms_available:
            return Decimal("0")
        return (self.rooms / self.rooms_available).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


def _effective_net_factor(rate_cards: list[RateCard]) -> Decimal | None:
    """
    Derive the effective net_factor from imported rate cards (net_rate / rack_rate).
    The Excel may use a different commission structure than the stored channel mix,
    so we compute it directly from the actual rates. Returns None if no rack rates exist.
    """
    ratios = [
        rc.net_rate / rc.rack_rate
        for rc in rate_cards
        if rc.rack_rate and rc.rack_rate != Decimal("0")
    ]
    if not ratios:
        return None
    avg = sum(ratios) / len(ratios)
    return avg.quantize(Decimal("0.000001"))


def calculate_revenue(
    month: int,
    year: int,
    rate_cards: list[RateCard],           # filtered for this scenario+month
    occ_budgets: list[OccupancyBudget],   # filtered for this scenario+month
    channels: list[SalesChannelConfig],   # todos los del escenario — se filtran por mes acá
    pkg_configs: list[PackageConfig],     # all package configs for this scenario
    other_revenues: list[RevenueOther],   # filtered for this scenario+month
    room_type_units: dict[str, int],      # room_type_id → total_units
) -> RevenueResult:
    """
    Calculate all revenue lines for a single month.

    rate_cards and occ_budgets must be pre-filtered to the correct scenario and month.
    pkg_configs is scenario-level. ⚠️ `channels` NO: se guardan por mes y la
    mezcla puede variar, así que se filtran adentro con `month`.
    other_revenues must be pre-filtered to the correct scenario and month.
    room_type_units maps room_type_id → number of physical rooms (for available rooms calc).
    """
    result = RevenueResult(month=month, year=year)

    # Use effective net_factor from actual rate cards when available;
    # the Excel commission structure may differ from the stored channel mix formula.
    effective_nf = _effective_net_factor(rate_cards)
    # ⚠️ El MES importa: los canales se guardan por mes y la mezcla puede
    # variar. Sin pasarlo, un escenario con mezcla estacional usaría el
    # promedio del año en todos los meses.
    nf = effective_nf if effective_nf else compute_net_factor(channels, month)
    result.net_factor = nf

    # Index by room_type_id
    rates_by_type: dict[str, RateCard] = {rc.room_type_id: rc for rc in rate_cards}
    occ_by_type: dict[str, OccupancyBudget] = {ob.room_type_id: ob for ob in occ_budgets}
    pkg_by_component: dict[str, PackageConfig] = {pc.component: pc for pc in pkg_configs}

    # Room Revenue = Σ(rooms_occupied × net_rate)
    total_rooms_occ = Decimal("0")
    total_guests = Decimal("0")
    rooms_revenue = Decimal("0")

    for rt_id, occ in occ_by_type.items():
        if rt_id not in rates_by_type:
            continue
        rc = rates_by_type[rt_id]
        rooms_occ = occ.rooms_occupied
        total_rooms_occ += rooms_occ
        total_guests += rooms_occ * rc.pax_per_room
        rooms_revenue += rooms_occ * rc.net_rate

    result.rooms = rooms_revenue.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    result.rooms_occupied = total_rooms_occ
    result.guests = total_guests

    # Available rooms = Σ(units × calendar_days_in_month)
    cal_days = Decimal(str(CALENDAR_DAYS[month - 1]))
    result.rooms_available = int(
        sum(units * CALENDAR_DAYS[month - 1] for units in room_type_units.values())
    )

    # Package revenues (need total_rooms_occ and pax_per_room)
    avg_pax = (total_guests / total_rooms_occ) if total_rooms_occ else Decimal("1.8")

    food_cfg = pkg_by_component.get(COMPONENT_FOOD)
    if food_cfg:
        food_rev = total_rooms_occ * avg_pax * food_cfg.rate_per_pax_night * nf
        result.food = food_rev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        bev_cfg = pkg_by_component.get(COMPONENT_BEV)
        if bev_cfg and bev_cfg.bev_food_ratio:
            bev_rev = result.food * bev_cfg.bev_food_ratio
            result.beverage = bev_rev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    act_cfg = pkg_by_component.get(COMPONENT_ACTIVITIES)
    if act_cfg:
        act_rev = total_rooms_occ * avg_pax * act_cfg.rate_per_pax_night * nf
        result.activities = act_rev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    trans_cfg = pkg_by_component.get(COMPONENT_TRANSPORT)
    if trans_cfg:
        trans_rev = total_rooms_occ * avg_pax * trans_cfg.rate_per_pax_night * nf
        result.transport = trans_rev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Sustainability: non-commissionable flat fee per guest per night
    sust_cfg = pkg_by_component.get(COMPONENT_SUSTAINABILITY)
    if sust_cfg:
        sust_rev = total_rooms_occ * avg_pax * sust_cfg.rate_per_pax_night
        result.sustainability = sust_rev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Líneas de monto mensual: todo lo que el motor no deriva.
    #
    # Antes esto era una cadena de `if` con cinco líneas escritas a mano, y por
    # eso el **Club** no existía en este camino: su driver guardaba socios ×
    # precio y acá no había ningún `elif` que lo leyera, así que el escenario
    # mostraba el ingreso y el P&L seguía en cero. Ahora el mapeo se deriva de
    # las líneas canónicas (`OTHER_REVENUE_LINES`), de manera que un
    # departamento nuevo llega al P&L sin que nadie se acuerde de tocar el motor.
    for oth in other_revenues:
        campo = _OTHER_LINE_TO_FIELD.get(oth.line.upper())
        if campo is not None:
            setattr(result, campo, oth.amount_usd)

    return result


def room_type_breakdown(
    month: int,
    rate_cards: list[RateCard],          # filtered for this scenario+month
    occ_budgets: list[OccupancyBudget],  # filtered for this scenario+month
    room_type_units: dict[str, int],     # room_type_id → total_units
) -> list[dict]:
    """Per-room-type revenue detail for one month (report "Ingresos por tipo").

    Each row: units · nights_available · nights_occupied · occupancy_pct ·
    revenue (rooms_occupied × net_rate) · adr (revenue ÷ occupied) · pax.
    Same per-type math the room-revenue loop uses, but kept per type instead of
    summed. Pure (no DB); rows ordered as room_type_units iterates.
    """
    cal_days = CALENDAR_DAYS[month - 1]
    rates_by_type = {rc.room_type_id: rc for rc in rate_cards}
    occ_by_type = {ob.room_type_id: ob for ob in occ_budgets}
    rows = []
    for rt_id, units in room_type_units.items():
        rc = rates_by_type.get(rt_id)
        ob = occ_by_type.get(rt_id)
        nights_avail = int(units) * cal_days
        rooms_occ = float(ob.rooms_occupied) if ob else 0.0
        net_rate = float(rc.net_rate) if rc else 0.0
        pax_per_room = float(rc.pax_per_room) if rc else 0.0
        revenue = rooms_occ * net_rate
        rows.append({
            "room_type_id": rt_id,
            "units": int(units),
            "nights_available": nights_avail,
            "nights_occupied": rooms_occ,
            "occupancy_pct": (rooms_occ / nights_avail) if nights_avail else 0.0,
            "revenue": round(revenue, 2),
            "adr": (revenue / rooms_occ) if rooms_occ else 0.0,
            "pax": rooms_occ * pax_per_room,
        })
    return rows


def calculate_annual_revenue(
    year: int,
    rate_cards_by_month: dict[int, list[RateCard]],
    occ_by_month: dict[int, list[OccupancyBudget]],
    channels: list[SalesChannelConfig],
    pkg_configs: list[PackageConfig],
    other_by_month: dict[int, list[RevenueOther]],
    room_type_units: dict[str, int],
) -> list[RevenueResult]:
    """Compute revenue for all 12 months."""
    return [
        calculate_revenue(
            month=m,
            year=year,
            rate_cards=rate_cards_by_month.get(m, []),
            occ_budgets=occ_by_month.get(m, []),
            # canales del mes (mix/comisión pueden variar por mes); fallback a todos
            channels=[c for c in channels if getattr(c, "month", m) == m] or channels,
            pkg_configs=pkg_configs,
            other_revenues=other_by_month.get(m, []),
            room_type_units=room_type_units,
        )
        for m in range(1, 13)
    ]
