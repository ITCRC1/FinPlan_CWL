"""Below-GOP: que la tabla de cuentas 8xxx del motor y el `account_mapping`
digan lo MISMO.

Cuando se separan no salta ningún error: la plata aterriza en otra línea y el
total sigue cuadrando, así que solo se nota mirando el P&L línea por línea.
Pasó con tres cuentas a la vez (8020, 8030, 8045) y nadie lo vio.

Ver `alembic/versions/093_una_sola_verdad_8020.py` para la historia completa.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from app.engine.pl_engine import (
    NONOP_ACCOUNT_LINE,
    NONOP_ACCOUNT_MAP,
    NonOpActuals,
    build_actual_inputs,
    calculate_full_pl,
    nonop_bucket_for_account,
    nonop_line_for_account,
)

MAPPING_XLSX = Path(__file__).resolve().parents[2] / "data" / "formato_mapping_reporte_app.xlsx"


# ─── La verdad de cada cuenta ─────────────────────────────────────────────────

def test_8020_es_capital_no_management_fee():
    """El bug que originó todo: la 8020 caía en el management fee."""
    assert nonop_line_for_account("8020") == "CAPITAL_RESERVE"
    assert nonop_bucket_for_account("8020") == "capital_reserve"


def test_8030_y_8045_son_financieros():
    """8030 = cargos bancarios · 8045 = diferencial cambiario. Ninguna es capital."""
    assert nonop_line_for_account("8030") == "LEASINGS_RENTS"
    assert nonop_line_for_account("8045") == "FINANCIAL_LOSSES"
    assert nonop_bucket_for_account("8030") == "bank_interest"
    assert nonop_bucket_for_account("8045") == "bank_interest"
    for acct in ("8030", "8045"):
        assert nonop_bucket_for_account(acct) not in ("capital_reserve", "large_capex")


def test_8025_va_arriba_del_ebitda():
    """Multas y no deducibles son gasto de dueño, no un cargo financiero."""
    assert nonop_line_for_account("8025") == "OTHER_EXPENSES"
    assert nonop_bucket_for_account("8025") == "other_expenses"


def test_cuenta_desconocida_no_pierde_plata():
    assert nonop_line_for_account("8999") is None
    assert nonop_bucket_for_account("8999") == "bank_interest"


def test_todo_bucket_existe_en_nonop_actuals():
    campos = set(NonOpActuals.__dataclass_fields__)
    for acct, bucket in NONOP_ACCOUNT_MAP.items():
        assert bucket in campos, f"{acct} apunta a un cajón inexistente: {bucket}"


# ─── Que el motor y la base no se separen ─────────────────────────────────────

def test_el_motor_dice_lo_mismo_que_el_account_mapping():
    """Contra el archivo que alimenta `account_mapping`. Es la prueba que
    importa: el motor viejo y la base tienen que rutear igual."""
    if not MAPPING_XLSX.exists():
        pytest.skip(f"no está el archivo de mapeo: {MAPPING_XLSX}")
    from app.importers.mapping_loader import parse_mapping_upload

    del_archivo: dict[str, set[str]] = {}
    for r in parse_mapping_upload(str(MAPPING_XLSX)):
        acct = (r.get("account_code") or "").strip()
        if not acct.startswith("8") or r.get("active_status", "YES").upper() != "YES":
            continue
        linea = (r.get("report_line_code") or "").strip()
        if linea:
            del_archivo.setdefault(acct, set()).add(linea)

    assert del_archivo, "el archivo de mapeo no trajo ninguna cuenta 8xxx"
    for acct, lineas in sorted(del_archivo.items()):
        motor = NONOP_ACCOUNT_LINE.get(acct)
        assert motor is not None, f"la {acct} está en el mapeo y no en el motor"
        assert motor in lineas, (
            f"la {acct}: el motor dice {motor}, el mapeo dice {sorted(lineas)}"
        )


def test_large_capex_y_asset_loss_no_tienen_cuenta_a_proposito():
    """No es un mapeo faltante: comparten cuenta (8020 / 8040) con su hermana y
    el GL no las separa. Si alguien les inventa una regla, esto avisa."""
    assert "LARGE_CAPEX" not in NONOP_ACCOUNT_LINE.values()
    assert "ASSET_LOSS" not in NONOP_ACCOUNT_LINE.values()


# ─── Que el EBT no se mueva ───────────────────────────────────────────────────

def _fila(acct: str, monto: str) -> dict:
    return {"account_code": acct, "dept_code": "0240", "amount": Decimal(monto)}


def test_el_ebt_no_depende_de_en_que_sublinea_caiga_la_8xxx():
    """Las 8xxx se restan todas una sola vez. Mover una de sub-línea cambia el
    EBITDA, nunca el EBT ni el Neto."""
    rows = [
        {"account_code": "4110", "dept_code": "0110", "amount": Decimal("1000000")},
        _fila("8000", "10000"),    # rent
        _fila("8005", "30000"),    # mgmt fee
        _fila("8015", "20000"),    # seguro
        _fila("8020", "50000"),    # capital
        _fila("8025", "15000"),    # otros gastos
        _fila("8030", "3000"),     # leasings
        _fila("8035", "2000"),     # intereses
        _fila("8040", "40000"),    # depreciación
        _fila("8045", "1000"),     # diferencial cambiario
    ]
    pl = {l.line_code: l.amount_usd for l in calculate_full_pl(**build_actual_inputs(rows))}
    suma_8xxx = Decimal("171000")
    assert pl["EBT"] == pl["GOP"] - suma_8xxx
    # y cada peso aterrizó donde dice el mapeo
    assert pl["CAPITAL_RESERVE"] == Decimal("50000")
    assert pl["OTHER_EXPENSES"] == Decimal("15000")
    assert pl["MGMT_FEE"] == Decimal("30000")
    assert pl["LARGE_CAPEX"] == Decimal("0")


def test_other_expenses_esta_dentro_del_total_non_op():
    rows = [_fila("8025", "15000")]
    pl = {l.line_code: l.amount_usd for l in calculate_full_pl(**build_actual_inputs(rows))}
    assert pl["OTHER_EXPENSES"] == Decimal("15000")
    assert pl["TOTAL_NON_OP"] == Decimal("15000")
    assert pl["BANK_INTEREST"] == Decimal("0")
