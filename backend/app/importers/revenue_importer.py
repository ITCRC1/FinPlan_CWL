"""
Revenue importer for Budget2026_Revenue_CORCO.xlsx.

Reads:
  - Key Indicators: rack rates, channel mix/commissions, package components, occupancy
  - Rates 2026:     net rates per room type per month
  - Summary:        Spa, Retail, F&B Misc, Innoceana, Laundry flat monthly amounts

Cell layout (0-indexed pandas positions with header=None):
  Key Indicators:
    Rack rates       rows 37-42  col0=sort_order  col1=name  cols2-13=Jan-Dec
    Channel mix      rows 49-51  col0=channel     cols1-11=Jan-Nov  (Dec same as Nov)
    Commissions      rows 60-62  col0=channel     cols1-12=Jan-Dec
    Package/night    rows 81-86  col0=component   cols1-12=Jan-Dec  (constant)
    Occupancy        rows 96-101 col0=name        cols1-12=Jan-Dec  (Oct=0 for 2026)
  Rates 2026:
    Net rates        rows 51-56  col0=name        cols1-12=Jan-Dec  (Oct=NaN → 0)
  Summary:
    Spa              row 21  cols1-12
    Retail           row 22  cols1-12
    F&B Misc         row 20  cols1-12
    Innoceana        row 25  cols1-12
    Laundry          row 27  cols1-12
"""
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from app.models.sales_channel_config import SalesChannelConfig
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.package_config import PackageConfig, COMPONENT_BEV
from app.models.revenue_other import RevenueOther
from app.seed_data import semilla

# Row indices (0-based) in each sheet
KI_RACK_ROWS = {1: 37, 2: 38, 3: 39, 4: 40, 5: 41, 6: 42}  # sort_order → row
KI_CHANNEL_MIX_ROWS = {"TA": 49, "OTA": 50, "DIRECT": 51}
KI_COMMISSION_ROWS  = {"TA": 60, "OTA": 61, "DIRECT": 62}
KI_PKG_ROWS = {
    "TRANSPORT": 81, "FOOD_B": 82, "FOOD_L": 83, "FOOD_D": 84,
    "ACTIVITIES_S": 85, "ACTIVITIES_W": 86,
}
KI_OCC_ROWS = {1: 96, 2: 97, 3: 98, 4: 99, 5: 100, 6: 101}  # sort_order → row
RATES_NET_ROWS = {1: 51, 2: 52, 3: 53, 4: 54, 5: 55, 6: 56}

# Los `sort_order` para los que ESTE Excel tiene fila. No es una opinión sobre
# cuántos tipos de habitación puede tener un hotel: es el largo del archivo, que
# trae seis filas y ya. Un hotel con más tipos importa los que el Excel cubre y
# los demás quedan intactos — antes el endpoint se negaba entero.
SORT_ORDERS_DEL_EXCEL = frozenset(KI_RACK_ROWS)


def repartir_tipos_para_el_excel(sort_orders) -> tuple[list[int], list[int], list[int]]:
    """Decide qué tipos cubre el Excel. Devuelve (cubiertos, sin_tocar, faltan).

    * `cubiertos` — se importan.
    * `sin_tocar` — el hotel los tiene pero el archivo no trae su fila. No es un
      error: se informan para que nadie crea que se importaron.
    * `faltan`    — el archivo trae la fila y el hotel no tiene el tipo. Eso sí
      impide importar: no habría contra qué guardar esas tarifas.
    """
    presentes = set(sort_orders)
    cubiertos = sorted(presentes & SORT_ORDERS_DEL_EXCEL)
    sin_tocar = sorted(presentes - SORT_ORDERS_DEL_EXCEL)
    faltan = sorted(SORT_ORDERS_DEL_EXCEL - presentes)
    return cubiertos, sin_tocar, faltan

SUMMARY_OTHER = {
    "FNB_MISC": 20,
    "SPA": 21,
    "RETAIL": 22,
    "INNOCEANA": 25,
    "LAUNDRY": 27,
}

PAX_PER_ROOM_DEFAULT = Decimal("1.8000")


def _dec(val: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Convert value to Decimal, returning default on failure."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return Decimal(str(val)).quantize(Decimal("0.0001"))
    except InvalidOperation:
        return default


def _read_12_months(row: pd.Series, col_start: int, col_end: int = None) -> list[Decimal]:
    """
    Read up to 12 values from a Series by column position.
    Returns a list of 12 Decimal values (missing months → 0).
    """
    results = []
    end = col_end if col_end else col_start + 12
    for c in range(col_start, end):
        val = row.iloc[c] if c < len(row) else None
        results.append(_dec(val))
    return results[:12]


def import_revenue(
    xlsx_path: str | Path,
    scenario_id: str,
    hotel_id: str,
    year: int,
    room_type_ids: list[str],  # ordenados por sort_order, empezando en 1
) -> dict:
    """
    Parse Budget2026_Revenue_CORCO.xlsx and return dicts of ORM objects ready for db.add().

    Returns:
        {
            'channels':        list[SalesChannelConfig],
            'rate_cards':      list[RateCard],
            'occupancies':     list[OccupancyBudget],
            'package_configs': list[PackageConfig],
            'other_revenues':  list[RevenueOther],
        }
    """
    xlsx = pd.ExcelFile(str(xlsx_path))

    ki = xlsx.parse("Key Indicators", header=None, dtype=object)
    r26 = xlsx.parse("Rates 2026", header=None, dtype=object)
    summary = xlsx.parse("Summary", header=None, dtype=object)

    # ── 1. Sales channel config ────────────────────────────────────────────
    #
    # Los valores por defecto son de ESTA propiedad, no de Corcovado a secas:
    # solo disparan cuando una celda del Key Indicators viene vacía, y antes
    # eran una constante Python (`CWL_DEFAULT_CHANNELS`) que cualquier hotel
    # habría heredado sin darse cuenta. Ahora salen de
    # `seed_data/<HOTEL_ID>/canales.json` — sin ese archivo, el hotel no tiene
    # defecto que ofrecer y el fallo es explícito, no un número prestado.
    defaults_canales = semilla("canales", hotel_id)
    if not defaults_canales:
        raise ValueError(
            f"El hotel «{hotel_id}» no tiene seed_data/{hotel_id}/canales.json: "
            "no hay mix/comisión por defecto para completar celdas vacías del "
            "Key Indicators.")
    por_canal = {d["channel"]: d for d in defaults_canales}

    channels: list[SalesChannelConfig] = []
    for ch_key in ("TA", "OTA", "DIRECT"):
        def_data = por_canal[ch_key]
        mix_row = ki.iloc[KI_CHANNEL_MIX_ROWS[ch_key]]
        comm_row = ki.iloc[KI_COMMISSION_ROWS[ch_key]]

        # KI sheet: col 0=blank, col 1=channel_name, col 2=January value
        mix_val = _dec(mix_row.iloc[2], def_data["mix_pct"])
        comm_val = _dec(comm_row.iloc[2], def_data["commission_pct"])

        channels.append(SalesChannelConfig(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=hotel_id,
            channel=ch_key,
            mix_pct=mix_val,
            commission_pct=comm_val,
        ))

    # ── 2. Net factor ──────────────────────────────────────────────────────
    # Prefer the effective factor derived from actual Excel rates (net/rack)
    # over the theoretical channel-mix formula. This handles the 0.822 vs 0.836
    # discrepancy and ensures closed months (October) use the same factor.
    channel_formula_nf = sum(c.mix_pct * (Decimal("1") - c.commission_pct) for c in channels)
    # Pre-scan open months to compute the effective net_factor
    _ratios: list[Decimal] = []
    for so in sorted(KI_RACK_ROWS):
        ki_r = ki.iloc[KI_RACK_ROWS[so]]
        r26_r = r26.iloc[RATES_NET_ROWS[so]]
        for col in range(2, 14):
            rack_v = _dec(ki_r.iloc[col])
            net_v = _dec(r26_r.iloc[col])
            if rack_v > Decimal("0") and net_v > Decimal("0"):
                _ratios.append(net_v / rack_v)
    if _ratios:
        net_factor = (sum(_ratios) / len(_ratios)).quantize(Decimal("0.000001"))
    else:
        net_factor = channel_formula_nf

    # ── 3. Occupancy budgets (read first to identify open months) ─────────
    occupancies: list[OccupancyBudget] = []
    open_months: set[int] = set()  # months where at least one room type has occupancy > 0
    for sort_order, rt_id in enumerate(room_type_ids, start=1):
        if sort_order not in SORT_ORDERS_DEL_EXCEL:
            continue  # el hotel tiene más tipos que filas trae el archivo
        occ_row = ki.iloc[KI_OCC_ROWS[sort_order]]
        # KI: col 0=blank, col 1=name, cols 2-13=Jan-Dec
        occ_vals = _read_12_months(occ_row, col_start=2, col_end=14)
        for month_idx, occ in enumerate(occ_vals, start=1):
            if occ == Decimal("0"):
                continue
            open_months.add(month_idx)
            occupancies.append(OccupancyBudget(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                hotel_id=hotel_id,
                room_type_id=rt_id,
                month=month_idx,
                rooms_occupied=occ,
            ))

    # ── 4. Rate cards (rack + net rates, all 12 months) ───────────────────
    # Rate cards are always created for every month, even if the hotel is
    # currently closed (e.g. October 2026). Revenue = $0 when occupancy = 0,
    # but the tariff structure must exist for future scenarios (2027+).
    rate_cards: list[RateCard] = []
    for sort_order, rt_id in enumerate(room_type_ids, start=1):
        if sort_order not in SORT_ORDERS_DEL_EXCEL:
            continue
        ki_row = ki.iloc[KI_RACK_ROWS[sort_order]]
        r26_row = r26.iloc[RATES_NET_ROWS[sort_order]]

        # Rack rates: KI col 0=sort_order, col 1=name, cols 2-13=Jan-Dec
        rack_rates = _read_12_months(ki_row, col_start=2, col_end=14)
        # Net rates: Rates 2026 col 0=blank, col 1=name, cols 2-13=Jan-Dec
        net_rates = _read_12_months(r26_row, col_start=2, col_end=14)

        for month_idx, (rack, net) in enumerate(zip(rack_rates, net_rates), start=1):
            if rack == Decimal("0") and net == Decimal("0"):
                continue  # truly undefined — no rate for this type/month
            if net == Decimal("0") and rack > Decimal("0"):
                # Net rate missing in source (closed month) — derive from rack × net_factor
                net = (rack * net_factor).quantize(Decimal("0.0001"))

            rate_cards.append(RateCard(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                hotel_id=hotel_id,
                room_type_id=rt_id,
                month=month_idx,
                rack_rate=rack,
                net_rate=net,
                pax_per_room=PAX_PER_ROOM_DEFAULT,
            ))

    # ── 5. Package configs ─────────────────────────────────────────────────
    pkg_rows = ki.iloc[[KI_PKG_ROWS[k] for k in KI_PKG_ROWS.keys()]]

    # KI: col 0=blank, col 1=name, col 2=January value (constant for all months in 2026)
    transfer_rate = _dec(ki.iloc[KI_PKG_ROWS["TRANSPORT"]].iloc[2], Decimal("35"))
    breakfast = _dec(ki.iloc[KI_PKG_ROWS["FOOD_B"]].iloc[2], Decimal("18"))
    lunch = _dec(ki.iloc[KI_PKG_ROWS["FOOD_L"]].iloc[2], Decimal("36"))
    dinner = _dec(ki.iloc[KI_PKG_ROWS["FOOD_D"]].iloc[2], Decimal("54"))
    snorkeling = _dec(ki.iloc[KI_PKG_ROWS["ACTIVITIES_S"]].iloc[2], Decimal("48"))
    pn_walk = _dec(ki.iloc[KI_PKG_ROWS["ACTIVITIES_W"]].iloc[2], Decimal("53"))

    food_rate = breakfast + lunch + dinner
    act_rate = snorkeling + pn_walk
    sust_rate = Decimal("28.0000")  # non-commissionable sustainability fee
    bev_ratio = Decimal("0.3400")   # from Beverage Revenue sheet row 49

    # `is_commissionable` y `bev_food_ratio` no vienen del Excel — solo el rate
    # por pax/noche. Antes salían de `CWL_DEFAULT_PACKAGE`, una constante Python
    # que cualquier hotel usaba sin darse cuenta. Ahora salen de
    # `seed_data/<HOTEL_ID>/paquete.json` (la misma semilla que ya alimenta la
    # pantalla de Paquetes por propiedad): sin ese archivo, no hay cómo saber si
    # el componente cobra comisión, y el fallo es explícito.
    default_package = semilla("paquete", hotel_id)
    if not default_package:
        raise ValueError(
            f"El hotel «{hotel_id}» no tiene seed_data/{hotel_id}/paquete.json: "
            "no hay is_commissionable/bev_food_ratio por defecto para los "
            "componentes del paquete.")

    pkg_cfgs = {
        **default_package,
        "FOOD": {**default_package["FOOD"], "rate_per_pax_night": food_rate},
        "ACTIVITIES": {**default_package["ACTIVITIES"], "rate_per_pax_night": act_rate},
        "TRANSPORT": {**default_package["TRANSPORT"], "rate_per_pax_night": transfer_rate},
    }

    package_configs: list[PackageConfig] = []
    for component, cfg in pkg_cfgs.items():
        if component == COMPONENT_BEV:
            rate = Decimal("0")  # beverage derived from food × bev_ratio
        else:
            rate = cfg["rate_per_pax_night"]
        package_configs.append(PackageConfig(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=hotel_id,
            component=component,
            rate_per_pax_night=rate,
            is_commissionable=cfg["is_commissionable"],
            bev_food_ratio=bev_ratio if component == COMPONENT_BEV else None,
        ))
    # Add BEVERAGE entry (not in default_package loop above)
    package_configs.append(PackageConfig(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        hotel_id=hotel_id,
        component=COMPONENT_BEV,
        rate_per_pax_night=Decimal("0"),
        is_commissionable=True,
        bev_food_ratio=bev_ratio,
    ))

    # ── 6. Other revenue lines ─────────────────────────────────────────────
    other_revenues: list[RevenueOther] = []
    for line, row_idx in SUMMARY_OTHER.items():
        row = summary.iloc[row_idx]
        # Summary cols 1-12 = Jan-Dec
        amounts = _read_12_months(row, col_start=1, col_end=13)
        for month_idx, amount in enumerate(amounts, start=1):
            if amount != Decimal("0"):
                other_revenues.append(RevenueOther(
                    id=str(uuid.uuid4()),
                    scenario_id=scenario_id,
                    hotel_id=hotel_id,
                    line=line,
                    month=month_idx,
                    amount_usd=amount,
                ))

    return {
        "channels": channels,
        "rate_cards": rate_cards,
        "occupancies": occupancies,
        "package_configs": package_configs,
        "other_revenues": other_revenues,
    }
