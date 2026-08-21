"""
Tests for app/engine/allocation_calculator.py
Run: pytest tests/test_allocation_calculator.py -v
"""
from decimal import Decimal
import pytest
from app.engine.allocation_calculator import (
    calculate_cafeteria_distribution,
    calculate_laundry_distribution,
    verify_allocation_nets_zero,
)


# ─── Helper ───────────────────────────────────────────────────────────────────

def sum_rows(rows: list[dict]) -> Decimal:
    return sum(r["amount_usd"] for r in rows)


# ─── Cafetería tests ──────────────────────────────────────────────────────────

def test_cafeteria_nets_to_zero_simple():
    """All 12 simulated months must net to zero."""
    for month in range(12):
        total_cost = Decimal("5000.00")
        fte_by_dept = {"0110": Decimal("10"), "0120": Decimal("5"), "0150": Decimal("2")}
        rows = calculate_cafeteria_distribution(total_cost, fte_by_dept)
        assert verify_allocation_nets_zero(rows), f"Month {month+1} does not net to zero"


def test_cafeteria_sum_equals_total_cost():
    """Positive rows must sum to total_cost (source credit equals total debits)."""
    total_cost = Decimal("8250.75")
    fte_by_dept = {"0110": Decimal("15"), "0120": Decimal("8"), "0130": Decimal("3")}
    rows = calculate_cafeteria_distribution(total_cost, fte_by_dept)
    positive_total = sum(r["amount_usd"] for r in rows if r["amount_usd"] > 0)
    assert abs(positive_total - total_cost) < Decimal("0.01"), (
        f"Expected {total_cost}, got {positive_total}"
    )


def test_remote_dept_excluded():
    """
    REMOTE_DEPTS (0191, 0192, 0200) must be excluded from cafetería.
    The caller is responsible for filtering — this test verifies the engine
    ignores dept codes that are NOT in the weights dict.
    """
    total_cost = Decimal("4000.00")
    # Simulate caller having already excluded 0191 from fte_by_dept
    fte_by_dept = {"0110": Decimal("10"), "0120": Decimal("5")}
    rows = calculate_cafeteria_distribution(total_cost, fte_by_dept)
    target_depts = {r["target_dept"] for r in rows if r["amount_usd"] > 0}
    assert "0191" not in target_depts
    assert "0192" not in target_depts


def test_cafeteria_proportional():
    """Dept with 2× FTE should get 2× the allocation."""
    total_cost = Decimal("3000.00")
    fte_by_dept = {"A": Decimal("10"), "B": Decimal("5")}  # A = 2× B
    rows = calculate_cafeteria_distribution(total_cost, fte_by_dept)
    a_row = next(r for r in rows if r["target_dept"] == "A")
    b_row = next(r for r in rows if r["target_dept"] == "B")
    ratio = a_row["amount_usd"] / b_row["amount_usd"]
    assert abs(ratio - Decimal("2")) < Decimal("0.01"), f"Expected 2:1 ratio, got {ratio}"


def test_cafeteria_zero_cost_returns_empty():
    """Zero total cost should produce no rows (no-op month like October at CWL)."""
    rows = calculate_cafeteria_distribution(Decimal("0"), {"0110": Decimal("5")})
    assert rows == []


def test_cafeteria_zero_fte_returns_empty():
    """Zero FTE denominator must not raise ZeroDivisionError."""
    rows = calculate_cafeteria_distribution(Decimal("1000"), {"0110": Decimal("0")})
    assert rows == []


# ─── Lavandería tests (modelo 3 vías: linen / uniformes / huéspedes) ───────────

def test_laundry_linen_only_nets_to_zero():
    """With no uniform/guest kilos, the whole cost is linen and nets to zero."""
    for month in range(12):
        total_cost = Decimal("3200.50")
        kilos = {"0110": Decimal("2000"), "0120": Decimal("800"), "0130": Decimal("400")}
        res = calculate_laundry_distribution(total_cost, kilos, {})
        assert verify_allocation_nets_zero(res["rows"]), f"Month {month+1} does not net to zero"
        assert abs(res["linen_cost"] - total_cost) < Decimal("0.01")
        assert res["guest_cost"] == Decimal("0")


def test_laundry_linen_proportional():
    """2:1 kilos ratio must produce 2:1 linen allocation (account 7310)."""
    total_cost = Decimal("6000.00")
    kilos = {"0110": Decimal("200"), "0120": Decimal("100")}
    res = calculate_laundry_distribution(total_cost, kilos, {})
    rooms_row = next(r for r in res["rows"] if r["target_dept"] == "0110")
    fb_row = next(r for r in res["rows"] if r["target_dept"] == "0120")
    assert rooms_row["account"] == "7310"
    assert rooms_row["basis_type"] == "KILOS"
    ratio = rooms_row["amount_usd"] / fb_row["amount_usd"]
    assert abs(ratio - Decimal("2")) < Decimal("0.01"), f"Expected 2:1 ratio, got {ratio}"


def test_laundry_three_way_split():
    """Cost splits by kilos: linen / uniform / guest. Linen+uniform go to the
    consuming depts, the guest COGS goes to 0162 (Laundry Revenue); 0161 is
    credited in full and nets to $0."""
    total_cost = Decimal("10000.00")
    linen = {"0110": Decimal("3000"), "0120": Decimal("1000")}  # 4000 kg linen
    uniform_fte = {"0110": Decimal("10"), "0200": Decimal("5")}  # by FTE
    res = calculate_laundry_distribution(
        total_cost, linen, uniform_fte,
        kilos_uniformes=Decimal("1000"), kilos_huespedes=Decimal("5000"),
    )
    # total kilos = 4000 + 1000 + 5000 = 10000 → 40% linen, 10% uniform, 50% guest
    assert abs(res["linen_cost"] - Decimal("4000")) < Decimal("0.01")
    assert abs(res["uniform_cost"] - Decimal("1000")) < Decimal("0.01")
    assert abs(res["guest_cost"] - Decimal("5000")) < Decimal("0.01")
    # distributed rows (linen + uniform + credit) net to $0
    assert verify_allocation_nets_zero(res["rows"])
    # uniform rows use account 7685 + FTE basis
    uni = [r for r in res["rows"] if r["account"] == "7685"]
    assert uni and all(r["basis_type"] == "FTE" for r in uni)
    # guest portion (COGS) moves to 0162 (Laundry Revenue), account 5301
    guest = next(r for r in res["rows"] if r["target_dept"] == "0162")
    assert abs(guest["amount_usd"] - Decimal("5000")) < Decimal("0.01")
    assert guest["account"] == "5301"
    # credit equals -total (linen + uniform + guest) → 0161 nets to $0
    credit = next(r for r in res["rows"] if r["target_dept"] == "0161")
    assert abs(credit["amount_usd"] + Decimal("10000")) < Decimal("0.01")
    assert credit["account"] == "4999"


def test_laundry_guest_only_goes_to_revenue_dept():
    """If all kilos are guests, the whole cost is the sold-service COGS → it
    moves to 0162 (Laundry Revenue) and 0161 is credited in full (nets to $0)."""
    total_cost = Decimal("4000")
    res = calculate_laundry_distribution(
        total_cost, {}, {}, kilos_uniformes=Decimal("0"), kilos_huespedes=Decimal("1000"),
    )
    assert abs(res["guest_cost"] - total_cost) < Decimal("0.01")
    guest = next(r for r in res["rows"] if r["target_dept"] == "0162")
    assert abs(guest["amount_usd"] - Decimal("4000")) < Decimal("0.01")
    credit = next(r for r in res["rows"] if r["target_dept"] == "0161")
    assert abs(credit["amount_usd"] + Decimal("4000")) < Decimal("0.01")
    assert verify_allocation_nets_zero(res["rows"])


def test_laundry_credito_es_la_unica_contrapartida():
    """El credito a la 4999 cubre TODO el costo del 0161 —linen, uniformes y
    huespedes—, y es el unico renglon negativo.

    Quien arme el asiento a partir de estas filas no debe agregar un segundo
    credito por la parte de huespedes: esa plata ya viene dentro del credito.
    Hacerlo la acredita dos veces y el asiento descuadra por ese monto.
    """
    res = calculate_laundry_distribution(
        Decimal("10000.00"),
        {"0110": Decimal("3000"), "0120": Decimal("1000")},
        {"0110": Decimal("10"), "0200": Decimal("5")},
        kilos_uniformes=Decimal("1000"), kilos_huespedes=Decimal("5000"),
    )
    cargos = [r for r in res["rows"] if r["amount_usd"] > 0]
    creditos = [r for r in res["rows"] if r["amount_usd"] < 0]

    assert len(creditos) == 1, "debe haber un solo credito"
    debe = sum(r["amount_usd"] for r in cargos)
    haber = -creditos[0]["amount_usd"]
    assert abs(debe - haber) < Decimal("0.01"), "debe y haber tienen que dar igual"

    # y el credito incluye a los huespedes, no solo linen + uniformes
    assert haber > res["linen_cost"] + res["uniform_cost"]
    assert abs(haber - (res["linen_cost"] + res["uniform_cost"] + res["guest_cost"])) < Decimal("0.01")


def test_laundry_huespedes_nunca_se_carga_al_0161():
    """El COGS de huespedes se carga al 0162. Cargarlo al 0161 lo deja sin
    regla exacta de mapeo (5301 solo existe para 0130 y 0162) y el motor
    tendria que resolverlo por descarte."""
    res = calculate_laundry_distribution(
        Decimal("8000"), {"0110": Decimal("1000")}, {},
        kilos_uniformes=Decimal("0"), kilos_huespedes=Decimal("1000"),
    )
    cargos_5301 = [r for r in res["rows"] if r["account"] == "5301" and r["amount_usd"] > 0]
    assert cargos_5301, "tiene que existir el cargo de huespedes"
    assert all(r["target_dept"] == "0162" for r in cargos_5301)


def test_laundry_zero_kilos_returns_empty():
    """Zero kilos must not raise ZeroDivisionError."""
    res = calculate_laundry_distribution(Decimal("1000"), {}, {})
    assert res["rows"] == []


# ─── verify_allocation_nets_zero ─────────────────────────────────────────────

def test_verify_nets_zero_true():
    rows = [
        {"amount_usd": Decimal("100")},
        {"amount_usd": Decimal("-100")},
    ]
    assert verify_allocation_nets_zero(rows) is True


def test_verify_nets_zero_false():
    rows = [
        {"amount_usd": Decimal("100")},
        {"amount_usd": Decimal("-99")},
    ]
    assert verify_allocation_nets_zero(rows) is False
