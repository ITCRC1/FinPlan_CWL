"""
Payroll calculator — pure Python, no DB dependencies.

Handles the three automatic computations:
  c6000_sw       = salary × FTE / TC  (CRC currency)
                 = salary × FTE        (USD currency)
  BASE           = c6000 + c6001 + c6002 + c6003 + c6010 + c6024 + c6027
  c6020_ccss     = BASE × 26.83%
  c6021_aguinaldo = BASE / 12

All other concepts are manual — the engine never overwrites them.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.models.payroll_position import PayrollPosition, get_fte
from app.models.payroll_concept_entry import PayrollConceptEntry

CCSS_RATE = Decimal("0.2683")
AGUINALDO_DIVISOR = Decimal("12")
ZERO = Decimal("0")
CENT = Decimal("0.01")


def calc_sw(position: PayrollPosition, month: int, tc: Decimal) -> Decimal:
    """
    Compute Salaries & Wages for a position in a given month.
    Returns 0 when FTE = 0.
    """
    fte = get_fte(position, month)
    if fte == ZERO:
        return ZERO
    if position.salary_currency == "CRC":
        if tc == ZERO:
            raise ValueError(f"TC for month {month} is zero — cannot convert CRC salary")
        return (position.salary_amount * fte / tc).quantize(CENT, ROUND_HALF_UP)
    return (position.salary_amount * fte).quantize(CENT, ROUND_HALF_UP)


def _q(x: Decimal) -> Decimal:
    """Redondeo a centavo, igual que el resto del motor."""
    return Decimal(x).quantize(CENT, ROUND_HALF_UP)


def _v(x: Optional[Decimal]) -> Decimal:
    """Coalesce None → 0. A freshly-built concept entry has None columns until
    flushed (Python-side defaults only apply at INSERT)."""
    return x if x is not None else ZERO


def calc_base(entry: PayrollConceptEntry) -> Decimal:
    """
    BASE for CCSS and Aguinaldo.
    BASE = SW + OT + DayOff + WorkingHoliday + Commissions + VacationsTaken + IncentiveBonus
    """
    return (
        _v(entry.c6000_sw)
        + _v(entry.c6001_overtime)
        + _v(entry.c6002_day_off)
        + _v(entry.c6003_working_holiday)
        + _v(entry.c6010_commissions)
        + _v(entry.c6024_vacations_taken)
        + _v(entry.c6027_incentive_bonus)
    )


def recalculate_entry(
    entry: PayrollConceptEntry,
    position: PayrollPosition,
    month: int,
    tc: Decimal,
    ccss_rate: Decimal = CCSS_RATE,
    aguinaldo_divisor: Decimal = AGUINALDO_DIVISOR,
    params=None,
) -> PayrollConceptEntry:
    """
    Recalcula los conceptos AUTOMÁTICOS de una fila (posición × mes).

    Sin `params` solo se mueven 6000/6020/6021, como siempre. Con `params`
    (PayrollParams del escenario) también se calculan los 9 conceptos que en CR
    salen de una tasa o un monto: 6001, 6003, 6027, 6023, 6026, 6025, 6029,
    6028 y 6030. Todos los drivers nacen en cero, así que un escenario que no los
    haya llenado da exactamente los mismos números que antes.

    REGLA CLAVE: un driver en CERO significa «este concepto no es automático», y
    entonces se RESPETA lo que la fila ya tenga — lo que el usuario digitó o subió
    por Excel. Así conviven los dos mundos: con tasa manda la fórmula, sin tasa
    manda el dato manual. Sin esta regla, recalcular borraría la carga manual.

    Nunca se tocan aquí:
      6002 Día libre · 6004 Incapacidades · 6010 Comisiones · 6024 Vac. tomadas
      6022 INS y 6025 Cafetería — vienen del REPARTO, no de una tasa.

    Devuelve la misma fila, modificada.
    """
    entry.c6000_sw = calc_sw(position, month, tc)

    # Conceptos por driver. El ORDEN importa: overtime, feriados y bono entran a la
    # BASE, así que se calculan antes que la CCSS y el aguinaldo. Todos los drivers
    # nacen en cero, así que sin parámetros esto no cambia nada.
    if params is not None:
        sw = _v(entry.c6000_sw)
        fte = get_fte(position, month)
        dias_cal = params.mes("calendar_days", month)
        feriados = params.mes("holidays", month)
        # REGLA: un driver en CERO significa «este concepto no es automático»,
        # así que se respeta lo que haya — lo que el usuario digitó o subió por
        # Excel. Sin esto, recalcular le borraría la carga manual de horas extra,
        # bono, cesantía, transporte, vivienda y otros beneficios.
        if params.overtime_pct:
            entry.c6001_overtime = _q(sw * params.overtime_pct)
        if params.bonus_pct:
            entry.c6027_incentive_bonus = _q(sw * params.bonus_pct)
        if dias_cal and feriados:
            entry.c6003_working_holiday = _q(sw / Decimal(dias_cal) * Decimal(feriados))
        libres = params.mes("days_off", month)
        if dias_cal and libres:
            entry.c6002_day_off = _q(sw / Decimal(dias_cal) * Decimal(libres))

    base = calc_base(entry)
    entry.c6020_ccss = (base * ccss_rate).quantize(CENT, ROUND_HALF_UP)
    entry.c6021_aguinaldo = (base / aguinaldo_divisor).quantize(CENT, ROUND_HALF_UP)

    if params is not None:
        # Provisiones sobre la BASE (no entran a la BASE ellas mismas).
        if params.vacaciones_rate:
            entry.c6023_vacation_prov = _q(base * params.vacaciones_rate)
        if params.severance_annual_rate:
            # Sobre la BASE del MES, igual que vacaciones. En CR la cesantia se
            # provisiona sobre cada salario mensual; dividir entre 12 la dejaba
            # 12 veces mas chica de lo que corresponde.
            entry.c6026_severance = _q(base * params.severance_annual_rate)
        # Beneficios por persona: se pagan en colones y NO cotizan.
        # 6025 Cafetería NO se toca aquí: viene del reparto (Allocations toma el
        # costo del depto 0220 y lo distribuye por FTE). Calcularla también como
        # per diem la contaría dos veces.
        tc_ = tc if tc and tc > 0 else Decimal("1")
        if params.transport_monthly_crc:
            entry.c6029_transport = _q(fte * params.transport_monthly_crc / tc_)
        if params.housing_monthly_crc:
            entry.c6028_housing = _q(fte * params.housing_monthly_crc / tc_)
        if params.other_monthly_crc:
            entry.c6030_other = _q(fte * params.other_monthly_crc / tc_)
    return entry


def repartir_beneficio(
    filas: list[tuple[PayrollConceptEntry, PayrollPosition]],
    columna: str,
    monto_anual_crc: Decimal,
    tc_por_mes: dict[int, Decimal],
    base: str = "FTE",
    en_usd: bool = False,
) -> Decimal:
    """Reparte un monto anual entre todas las filas de planilla, por posición.

    Sirve para cualquier cuenta de beneficio: el INS (6022), la cafetería (6025),
    transporte, vivienda, otros. Cada posición-mes recibe la parte que le toca:

        concepto = monto_anual × (peso de esa fila ÷ suma de todos los pesos)

    El peso es el FTE (por plaza) o 1 por cabeza si `base='HEADCOUNT'`. Un mes con
    menos gente recibe menos, y octubre con el lodge cerrado (FTE 0) no recibe nada.

    El reparto es EXACTO en la moneda del monto: el sobrante del redondeo va a la
    fila más grande. Si el monto viene en colones (`en_usd=False`), cada fila se
    convierte con el TC DE SU MES — no con uno solo del año, que daría cifras
    equivocadas en cuanto el tipo de cambio se mueva mes a mes. Si ya viene en
    dólares (`en_usd=True`, p.ej. el costo de un departamento), no se convierte:
    dar la vuelta por colones y volver introduciría un error de redondeo gratis.

    Devuelve el total repartido en USD. Con monto 0 pone la columna en cero.
    """
    if not columna:
        return ZERO
    for e, _ in filas:
        setattr(e, columna, ZERO)
    if not filas or monto_anual_crc <= ZERO:
        return ZERO

    def _peso(p: PayrollPosition, mes: int) -> Decimal:
        fte = get_fte(p, mes)
        if base == "HEADCOUNT":
            return Decimal("1") if fte > ZERO else ZERO
        return fte

    pesos = [(e, _peso(p, e.month)) for e, p in filas]
    total_fte = sum(f for _, f in pesos)
    if total_fte <= ZERO:
        return ZERO

    # Se reparte en la moneda del monto, que es donde tiene que cuadrar exacto; la
    # conversión (si hace falta) viene después, con el TC del mes de CADA fila.
    partes: list[tuple[PayrollConceptEntry, Decimal]] = []
    for e, fte in pesos:
        if fte <= ZERO:
            continue
        partes.append((e, _q(monto_anual_crc * fte / total_fte)))
    if not partes:
        return ZERO

    resto = monto_anual_crc - sum(v for _, v in partes)
    if resto != ZERO:
        i = max(range(len(partes)), key=lambda k: partes[k][1])
        partes[i] = (partes[i][0], _q(partes[i][1] + resto))

    repartido_usd = ZERO
    for e, monto in partes:
        if en_usd:
            valor = monto
        else:
            tc = tc_por_mes.get(e.month) or Decimal("1")
            valor = _q(monto / (tc if tc > ZERO else Decimal("1")))
        setattr(e, columna, valor)
        repartido_usd += valor
    return repartido_usd


def repartir_ins(filas, monto_anual_crc, tc_por_mes) -> Decimal:
    """Atajo histórico: el INS es un reparto por FTE a la cuenta 6022."""
    return repartir_beneficio(filas, "c6022_occ_hazard", monto_anual_crc,
                              tc_por_mes, base="FTE")


def total_entry(entry: PayrollConceptEntry) -> Decimal:
    """Sum all 17 concepts for one position × month."""
    return (
        _v(entry.c6000_sw)
        + _v(entry.c6001_overtime)
        + _v(entry.c6002_day_off)
        + _v(entry.c6003_working_holiday)
        + _v(entry.c6010_commissions)
        + _v(entry.c6024_vacations_taken)
        + _v(entry.c6027_incentive_bonus)
        + _v(entry.c6020_ccss)
        + _v(entry.c6021_aguinaldo)
        + _v(entry.c6004_disabilities)
        + _v(entry.c6022_occ_hazard)
        + _v(entry.c6023_vacation_prov)
        + _v(entry.c6025_cafeteria)
        + _v(entry.c6026_severance)
        + _v(entry.c6028_housing)
        + _v(entry.c6029_transport)
        + _v(entry.c6030_other)
    )


@dataclass
class DeptPayrollSummary:
    """Aggregated payroll totals for a department × month."""
    dept_code: str
    month: int
    year: int
    c6000: Decimal = ZERO
    c6001: Decimal = ZERO
    c6002: Decimal = ZERO
    c6003: Decimal = ZERO
    c6010: Decimal = ZERO
    c6024: Decimal = ZERO
    c6027: Decimal = ZERO
    base: Decimal = ZERO
    c6020: Decimal = ZERO
    c6021: Decimal = ZERO
    c6004: Decimal = ZERO
    c6022: Decimal = ZERO
    c6023: Decimal = ZERO
    c6025: Decimal = ZERO
    c6026: Decimal = ZERO
    c6028: Decimal = ZERO
    c6029: Decimal = ZERO
    c6030: Decimal = ZERO
    total: Decimal = ZERO


def summarize_dept(
    entries: list[PayrollConceptEntry],
    dept_code: str,
    month: int,
    year: int,
) -> DeptPayrollSummary:
    """
    Aggregate PayrollConceptEntry rows for a single dept × month.
    entries should already be filtered to the correct dept + month.
    """
    s = DeptPayrollSummary(dept_code=dept_code, month=month, year=year)
    for e in entries:
        s.c6000 += e.c6000_sw
        s.c6001 += e.c6001_overtime
        s.c6002 += e.c6002_day_off
        s.c6003 += e.c6003_working_holiday
        s.c6010 += e.c6010_commissions
        s.c6024 += e.c6024_vacations_taken
        s.c6027 += e.c6027_incentive_bonus
        s.c6020 += e.c6020_ccss
        s.c6021 += e.c6021_aguinaldo
        s.c6004 += e.c6004_disabilities
        s.c6022 += e.c6022_occ_hazard
        s.c6023 += e.c6023_vacation_prov
        s.c6025 += e.c6025_cafeteria
        s.c6026 += e.c6026_severance
        s.c6028 += e.c6028_housing
        s.c6029 += e.c6029_transport
        s.c6030 += e.c6030_other

    s.base = s.c6000 + s.c6001 + s.c6002 + s.c6003 + s.c6010 + s.c6024 + s.c6027
    s.total = (
        s.c6000 + s.c6001 + s.c6002 + s.c6003 + s.c6010 + s.c6024 + s.c6027
        + s.c6020 + s.c6021
        + s.c6004 + s.c6022 + s.c6023 + s.c6025 + s.c6026 + s.c6028 + s.c6029 + s.c6030
    )
    return s


@dataclass
class FTEReport:
    scenario_id: str
    by_dept: dict[str, dict[int, Decimal]] = field(default_factory=dict)
    totals: dict[int, Decimal] = field(default_factory=dict)
    annual_avg: dict[str, Decimal] = field(default_factory=dict)


def build_fte_report(
    positions: list[PayrollPosition],
) -> FTEReport:
    """
    Aggregate FTE by dept × month.
    Positions with FTE=0 in a month still appear (visible as 0, not absent).
    """
    report = FTEReport(scenario_id=positions[0].scenario_id if positions else "")
    for pos in positions:
        dept = pos.dept_code
        if dept not in report.by_dept:
            report.by_dept[dept] = {m: ZERO for m in range(1, 13)}
        for month in range(1, 13):
            report.by_dept[dept][month] += get_fte(pos, month)

    report.totals = {
        m: sum(report.by_dept[d][m] for d in report.by_dept)
        for m in range(1, 13)
    }
    report.annual_avg = {
        d: sum(report.by_dept[d].values()) / Decimal("12")
        for d in report.by_dept
    }
    return report
