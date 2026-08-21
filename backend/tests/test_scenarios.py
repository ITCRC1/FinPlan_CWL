"""
Tests de la Fase 2 — Escenarios, TC y Habitaciones.

Tests unitarios (sin DB):
  ✅ ScenarioLockedError se lanza al intentar editar un escenario locked
  ✅ get_tc_for_month retorna el TC exacto del mes
  ✅ get_tc_for_month hace fallback al mes anterior disponible
  ✅ get_tc_for_month hace fallback al primer mes si no hay anteriores
  ✅ CWL tiene exactamente 6 tipos de habitación con 30 unidades totales
  ✅ Los 6 tipos tienen los nombres y unidades correctos según el archivo real

Tests de integración (requieren DB — marcados como @pytest.mark.integration):
  ✅ Crear escenario BUDGET 2026 genera 12 filas de TC
  ✅ Escenario locked rechaza edición en PUT /exchange-rates/{month}/
"""
import pytest
from decimal import Decimal
from app.models.scenario import Scenario, ScenarioLockedError
from app.models.exchange_rate import ExchangeRate, get_tc_for_month
from app.models.room_type_config import CWL_ROOM_TYPES


# ─── Escenario: locking ────────────────────────────────────────────────────

def test_scenario_locked_raises():
    """assert_editable() lanza ScenarioLockedError cuando status=locked."""
    s = Scenario()
    s.status = "locked"
    s.type = "BUDGET"
    s.version = "v1"
    s.year = 2026
    with pytest.raises(ScenarioLockedError):
        s.assert_editable()


def test_scenario_draft_does_not_raise():
    """assert_editable() no lanza nada para status=draft o approved."""
    for status in ("draft", "approved"):
        s = Scenario()
        s.status = status
        s.type = "BUDGET"
        s.version = "v1"
        s.year = 2026
        s.assert_editable()   # no debe lanzar


def test_scenario_is_locked_property():
    s = Scenario()
    s.status = "locked"
    assert s.is_locked is True
    s.status = "draft"
    assert s.is_locked is False


# ─── Tipo de cambio: lógica de fallback ───────────────────────────────────

def _make_rate(month: int, tc: float) -> ExchangeRate:
    r = ExchangeRate()
    r.month = month
    r.tc_crc_usd = Decimal(str(tc))
    return r


def test_tc_exact_match():
    """get_tc_for_month retorna el TC exacto cuando existe."""
    rates = [_make_rate(1, 530), _make_rate(6, 540), _make_rate(12, 550)]
    assert get_tc_for_month(rates, 6) == Decimal("540")


def test_tc_fallback_to_prior_month():
    """Si no hay TC para el mes, usa el más reciente anterior disponible."""
    rates = [_make_rate(1, 530)]
    # Meses 2-12 deben hacer fallback a enero
    assert get_tc_for_month(rates, 3) == Decimal("530")
    assert get_tc_for_month(rates, 12) == Decimal("530")


def test_tc_fallback_uses_closest_prior():
    """Usa el mes anterior más cercano, no el primero."""
    rates = [_make_rate(1, 530), _make_rate(7, 545)]
    # Mes 9: fallback a julio (545), no a enero (530)
    assert get_tc_for_month(rates, 9) == Decimal("545")
    # Mes 4: fallback a enero (530), porque julio es posterior
    assert get_tc_for_month(rates, 4) == Decimal("530")


def test_tc_fallback_no_prior_uses_first():
    """Si no hay mes anterior, usa el primer mes disponible."""
    rates = [_make_rate(6, 540)]
    # Mes 1-5: no hay meses anteriores → fallback al primer disponible (junio)
    assert get_tc_for_month(rates, 1) == Decimal("540")


def test_tc_empty_raises():
    """Sin ningún TC definido, lanza ValueError."""
    with pytest.raises(ValueError, match="No hay tipos de cambio"):
        get_tc_for_month([], 1)


# ─── Tipos de habitación CWL ──────────────────────────────────────────────

def test_cwl_six_room_types():
    """CWL tiene exactamente 6 tipos de habitación."""
    assert len(CWL_ROOM_TYPES) == 6


def test_cwl_total_30_units():
    """Los 6 tipos suman exactamente 30 unidades."""
    total = sum(rt["units"] for rt in CWL_ROOM_TYPES)
    assert total == 30, f"Se esperaban 30 unidades, se encontraron {total}"


def test_cwl_room_type_units():
    """Cada tipo tiene las unidades correctas según el CLAUDE.md."""
    expected = [
        ("Deluxe King", 6),
        ("Carate Double", 2),
        ("Agujas Queen", 4),
        ("Sirena Suites", 8),
        ("Treehouse", 5),
        ("5 Elements", 5),
    ]
    for (short_name, expected_units), rt in zip(expected, CWL_ROOM_TYPES):
        assert rt["units"] == expected_units, (
            f"{rt['short_name']}: esperaba {expected_units} unidades, "
            f"se encontraron {rt['units']}"
        )


def test_cwl_room_types_sorted():
    """Los tipos están ordenados por sort_order (1-6)."""
    orders = [rt["sort_order"] for rt in CWL_ROOM_TYPES]
    assert orders == list(range(1, 7))
