"""El reparto de Rooms a sus sets: familia, base y porcentajes.

Lo que se protege acá es lo que se rompe callado:
  - que un hijo de FUNCIÓN (Housekeeping) no se confunda con un SET (Villas),
  - que la base incluya los repartos que ya cayeron en Rooms (corre al final),
  - que un set NO entre en su propia base (se repartiría sobre sí mismo),
  - que un % vacío no mueva nada.
"""
import asyncio
from decimal import Decimal

import pytest

from app.engine.recalculate import rooms_family, _rooms_base_por_cuenta
from app.models.rooms_allocation_config import RoomsAllocationConfig

ZERO = Decimal("0")


# ── dobles mínimos ────────────────────────────────────────────────────────────
class _Dept:
    def __init__(self, code, parent="", room_set=False, name=""):
        self.dept_code = code
        self.parent_dept_code = parent
        self.room_set = room_set
        self.dept_name = name or code


class _Scalars:
    def __init__(self, filas):
        self._filas = filas

    def scalars(self):
        return self

    def all(self):
        return list(self._filas)

    def __iter__(self):
        return iter(self._filas)


class _Session:
    """Devuelve siempre el mismo catálogo: rooms_family solo consulta eso."""
    def __init__(self, filas):
        self._filas = filas

    async def execute(self, _q):
        return _Scalars(self._filas)


CATALOGO = [
    _Dept("0110", "", True, "Rooms"),
    _Dept("0111", "0110", False, "Front Desk"),
    _Dept("0113", "0110", False, "Housekeeping"),
    _Dept("0115", "0110", True, "Villas"),
    _Dept("0116", "0110", True, "Residencias"),
    _Dept("0120", "", False, "A&B"),
    _Dept("0122", "0120", False, "Cocina"),
]


def _familia():
    return asyncio.get_event_loop().run_until_complete(
        rooms_family(_Session(CATALOGO), "0110"))


# ── familia vs sets ───────────────────────────────────────────────────────────
def test_los_hijos_de_funcion_son_familia_no_destinos():
    familia, sets = asyncio.run(rooms_family(_Session(CATALOGO), "0110"))
    assert familia == {"0110", "0111", "0113"}
    assert sets == {"0115", "0116"}


def test_un_set_nunca_entra_en_su_propia_base():
    """Si Villas cayera en la familia, la base incluiría lo que ya se le movió
    y el próximo recálculo lo repartiría otra vez sobre sí mismo."""
    familia, sets = asyncio.run(rooms_family(_Session(CATALOGO), "0110"))
    assert not (familia & sets)


def test_otros_departamentos_quedan_afuera():
    familia, _sets = asyncio.run(rooms_family(_Session(CATALOGO), "0110"))
    assert "0120" not in familia and "0122" not in familia


def test_catalogo_con_ciclo_no_cuelga():
    ciclo = [_Dept("0110", "0115", True), _Dept("0115", "0110", True)]
    familia, sets = asyncio.run(rooms_family(_Session(ciclo), "0110"))
    assert "0110" in familia


# ── base por cuenta ───────────────────────────────────────────────────────────
class _Opex:
    def __init__(self, dept, cuenta, monto):
        self.dept_code, self.account_code, self._m = dept, cuenta, Decimal(str(monto))

    def get_month(self, _m):
        return self._m


class _Reparto:
    def __init__(self, dept, cuenta, monto, mes=1):
        self.target_dept, self.account = dept, cuenta
        self.amount_usd, self.month = Decimal(str(monto)), mes


FAMILIA = {"0110", "0111", "0113"}


def test_la_base_suma_el_gl_de_toda_la_familia():
    base = _rooms_base_por_cuenta(
        [_Opex("0110", "7065", 100), _Opex("0113", "7065", 40),
         _Opex("0120", "7065", 999)],
        [], [], [], FAMILIA, 1)
    assert base == {"7065": Decimal("140")}


def test_la_base_incluye_lo_que_ya_repartieron_a_rooms():
    """Corre al final: la cafetería y la lavandería ya cayeron en Rooms, así que
    las villas se llevan su proporción de eso también."""
    base = _rooms_base_por_cuenta(
        [_Opex("0110", "7065", 100)], [], [],
        [_Reparto("0113", "6025", 30), _Reparto("0110", "7310", 20)],
        FAMILIA, 1)
    assert base == {"7065": Decimal("100"), "6025": Decimal("30"),
                    "7310": Decimal("20")}


def test_un_credito_a_rooms_baja_la_base():
    """Una posición de Rooms que apoya a otra área ya entregó su costo: la base
    tiene que bajar, no repartirse de nuevo."""
    base = _rooms_base_por_cuenta(
        [_Opex("0110", "6000", 100)], [], [],
        [_Reparto("0110", "6000", -40)], FAMILIA, 1)
    assert base == {"6000": Decimal("60")}


def test_las_cuentas_en_cero_no_ensucian_la_base():
    base = _rooms_base_por_cuenta(
        [_Opex("0110", "7065", 0)], [], [], [], FAMILIA, 1)
    assert base == {}


def test_el_reparto_de_otro_mes_no_entra():
    """Se le pasan solo las filas del mes; una fila de febrero en la base de
    enero inflaría el mes equivocado."""
    base = _rooms_base_por_cuenta(
        [], [], [], [_Reparto("0110", "6025", 50, mes=2)], FAMILIA, 1)
    assert base == {"6025": Decimal("50")}   # el filtro lo hace quien llama


# ── porcentajes ───────────────────────────────────────────────────────────────
def test_pct_for_devuelve_la_fraccion_del_mes():
    c = RoomsAllocationConfig(dept_code="0115", active=True,
                              pct_monthly=[0.3] * 6 + [0.1] * 6)
    assert c.pct_for(1) == Decimal("0.3")
    assert c.pct_for(12) == Decimal("0.1")


def test_una_config_inactiva_no_reparte():
    c = RoomsAllocationConfig(dept_code="0115", active=False, pct_monthly=[0.5] * 12)
    assert c.pct_for(1) == ZERO


def test_una_lista_corta_o_vacia_da_cero():
    assert RoomsAllocationConfig(dept_code="0115", active=True,
                                 pct_monthly=[]).pct_for(1) == ZERO
    assert RoomsAllocationConfig(dept_code="0115", active=True,
                                 pct_monthly=[0.2]).pct_for(5) == ZERO


def test_un_pct_basura_no_revienta_el_recalculo():
    c = RoomsAllocationConfig(dept_code="0115", active=True,
                              pct_monthly=["", None, "x"] + [0] * 9)
    assert c.pct_for(1) == ZERO and c.pct_for(3) == ZERO


# ── el asiento completo, de punta a punta ─────────────────────────────────────
def test_el_asiento_netea_cero_y_conserva_las_cuentas():
    from app.engine.allocation_calculator import (
        calculate_rooms_by_pct, verify_allocation_nets_zero,
    )
    base = {"6000": Decimal("60000"), "6020": Decimal("16098"),
            "7065": Decimal("24000")}
    filas, fte, avisos = calculate_rooms_by_pct(
        base, {"0115": Decimal("0.30"), "0116": Decimal("0.10")},
        source_dept="0110", fte=Decimal("20"))

    assert not avisos
    assert verify_allocation_nets_zero(filas)

    debitos = [f for f in filas if f["basis_type"] != "CREDIT"]
    # cada set conserva las TRES cuentas: la villa muestra la misma estructura
    # de gasto que cualquier departamento, no una bolsa
    assert {f["account"] for f in debitos if f["target_dept"] == "0115"} == {
        "6000", "6020", "7065"}
    villas = sum(f["amount_usd"] for f in debitos if f["target_dept"] == "0115")
    assert villas == pytest.approx(Decimal("30029.4"), rel=1e-6)

    credito = [f for f in filas if f["basis_type"] == "CREDIT"]
    assert len(credito) == 1 and credito[0]["target_dept"] == "0110"
    assert credito[0]["account"] == "4999"

    # el FTE viaja proporcional, para poder leer costo por FTE en el set
    assert fte["0115"] == Decimal("6.00")
    assert fte["0116"] == Decimal("2.00")


def test_el_credito_sale_en_4999_sobre_el_depto_fuente():
    """El par (0110, 4999) TIENE que tener regla de mapeo — migración 089.

    Sin ella el resolvedor cae al FALLBACK y usa la regla de la 4999 del 0220:
    el crédito se va restando de la línea de CAFETERÍA en vez de la de Rooms.
    No da error y el GOP no se mueve, así que solo se ve mirando el P&L por
    departamento — Rooms inflado y Cafetería en negativo por el mismo monto.
    Es la misma trampa de la migración 079.
    """
    from app.engine.allocation_calculator import (
        calculate_rooms_by_pct, ALLOCATION_ACCOUNT,
    )
    filas, _f, _a = calculate_rooms_by_pct(
        {"6000": Decimal("1000")}, {"0115": Decimal("0.2")}, source_dept="0110")
    credito = [f for f in filas if f["basis_type"] == "CREDIT"]
    assert len(credito) == 1
    assert credito[0]["account"] == ALLOCATION_ACCOUNT == "4999"
    assert credito[0]["target_dept"] == "0110"


def test_pasarse_del_100_no_arma_asiento():
    from app.engine.allocation_calculator import calculate_rooms_by_pct
    filas, _fte, avisos = calculate_rooms_by_pct(
        {"6000": Decimal("1000")},
        {"0115": Decimal("0.7"), "0116": Decimal("0.5")}, source_dept="0110")
    assert filas == [] and avisos
    assert "100%" in avisos[0]
