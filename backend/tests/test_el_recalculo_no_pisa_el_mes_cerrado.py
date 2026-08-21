# -*- coding: utf-8 -*-
"""EL RECÁLCULO CORRIENDO DE VERDAD, CON UN MES CERRADO ADENTRO.

`test_los_meses_cerrados_no_se_mueven` vigila la FORMA del código —que el
borrado se filtre, que las cuatro etapas reciban el corte—. Esto ejecuta las dos
etapas que de verdad tocan datos guardados y mide el resultado al centavo.

Hace falta separarlo porque el modo de falla de este sistema es exactamente ese:
*«"da 0,00" no alcanza»*. Una prueba que solo lee el código no distingue entre
«el filtro está» y «el filtro funciona».

Se usa una sesión de mentira en vez de la base: estas dos funciones consultan
por modelo y devuelven objetos, así que despacharlas por entidad reproduce el
contrato completo sin depender de Postgres.
"""
from decimal import Decimal

import pytest

from app.engine import recalculate as recalc
from app.models.opex_entry import OpexEntry
from app.models.exchange_rate import ExchangeRate
from app.models.payroll_position import PayrollPosition
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.cost_entry import CostEntry
from app.models.benefit_allocation_config import BenefitAllocationConfig
from app.models.payroll_params import PayrollParams


class _Resultado:
    def __init__(self, filas):
        self._f = list(filas)

    def scalars(self):
        return self

    def all(self):
        return list(self._f)

    def scalar_one_or_none(self):
        return self._f[0] if self._f else None

    def scalar_one(self):
        return self._f[0] if self._f else 0


class _Sesion:
    """Despacha cada `select(Modelo)` a la lista que le corresponde."""

    def __init__(self, **por_modelo):
        self.datos = por_modelo
        self.agregados = []

    async def execute(self, stmt):
        try:
            ent = stmt.column_descriptions[0]["entity"]
        except Exception:                                   # noqa: BLE001
            ent = None
        nombre = getattr(ent, "__name__", "")
        return _Resultado(self.datos.get(nombre, []))

    async def flush(self):
        pass

    def add(self, obj):
        self.agregados.append(obj)


class _Esc:
    id = "esc"
    year = 2026
    type = "FORECAST"
    version = "Working"
    hotel_id = "CWL"
    actuals_through = 6


def _tc(mes, valor):
    r = ExchangeRate(scenario_id="esc", hotel_id="CWL", month=mes, year=2026,
                     tc_crc_usd=Decimal(str(valor)))
    return r


# ── El tipo de cambio: mover UN mes reescribía los DOCE ──────────────────────

def _linea_en_colones():
    e = OpexEntry(scenario_id="esc", dept_code="0110", account_code="7065",
                  currency="CRC")
    for m in range(1, 13):
        e.set_crc(m, Decimal("465000"))
        e.set_month(m, Decimal("1000.0000"))   # derivado con el TC viejo (465)
    return e


@pytest.mark.asyncio
async def test_cambiar_el_tc_no_reescribe_un_mes_cerrado():
    """El TC vive en una tabla aparte: basta tocarlo para que julio ya cerrado
    cambie de monto. Acá se sube el TC de TODOS los meses a 500 y se comprueba
    que enero–junio (cerrados) siguen valiendo exactamente lo mismo."""
    fila = _linea_en_colones()
    ses = _Sesion(ExchangeRate=[_tc(m, 500) for m in range(1, 13)],
                  OpexEntry=[fila], CostEntry=[])
    avisos: list[str] = []

    await recalc._derivar_monedas(ses, _Esc(), cerrados={1, 2, 3, 4, 5, 6},
                                  avisos=avisos)

    for m in range(1, 7):
        assert fila.get_month(m) == Decimal("1000.0000"), (
            f"el mes cerrado {m} se re-expresó con el TC nuevo")
    for m in range(7, 13):
        assert fila.get_month(m) == Decimal("930.0000"), (
            f"el mes abierto {m} NO se re-expresó: la protección se pasó de largo")


@pytest.mark.asyncio
async def test_congelar_el_mes_cerrado_no_es_silencioso():
    """Proteger en silencio es el mismo defecto con otro signo: el owner cambió
    el TC y tiene que saber que ese mes no lo tomó, con el monto."""
    ses = _Sesion(ExchangeRate=[_tc(m, 500) for m in range(1, 13)],
                  OpexEntry=[_linea_en_colones()], CostEntry=[])
    avisos: list[str] = []
    await recalc._derivar_monedas(ses, _Esc(), cerrados={1}, avisos=avisos)
    assert any("Mes 1 está cerrado" in a for a in avisos)
    assert any("-70.00" in a for a in avisos), avisos


@pytest.mark.asyncio
async def test_sin_meses_cerrados_se_re_expresan_los_doce():
    """La protección no puede cambiar lo que pasa hoy en un escenario sin corte
    — que son 18 de los 20 en producción."""
    fila = _linea_en_colones()
    ses = _Sesion(ExchangeRate=[_tc(m, 500) for m in range(1, 13)],
                  OpexEntry=[fila], CostEntry=[])
    await recalc._derivar_monedas(ses, _Esc(), cerrados=set(), avisos=[])
    for m in range(1, 13):
        assert fila.get_month(m) == Decimal("930.0000")


# ── La planilla: proteger julio no puede mover agosto ────────────────────────

def _posicion():
    return PayrollPosition(
        id="p1", scenario_id="esc", dept_code="0110", position_code="0110-01",
        position_name="Recepción", salary_amount=Decimal("465000"),
        salary_currency="CRC", **{f"fte_{m}": Decimal("1") for m in
                           ["jan", "feb", "mar", "apr", "may", "jun",
                            "jul", "aug", "sep", "oct", "nov", "dec"]})


def _fila(mes, sw):
    return PayrollConceptEntry(scenario_id="esc", position_id="p1", dept_code="0110",
                               month=mes, year=2026, c6000_sw=Decimal(str(sw)))


class _SesionPlanilla(_Sesion):
    """Igual, pero devuelve la fila de planilla que corresponde al mes pedido."""

    def __init__(self, filas_por_mes, **resto):
        super().__init__(**resto)
        self.filas = filas_por_mes

    async def execute(self, stmt):
        ent = stmt.column_descriptions[0]["entity"]
        if getattr(ent, "__name__", "") == "PayrollConceptEntry":
            mes = None
            for c in stmt.whereclause.clauses:
                if getattr(c.left, "key", "") == "month":
                    mes = c.right.value
            return _Resultado([self.filas[mes]] if mes in self.filas else [])
        return await super().execute(stmt)


@pytest.mark.asyncio
async def test_la_planilla_de_un_mes_cerrado_queda_intacta():
    """El salario cambió (465.000 → 600.000). Los meses abiertos lo toman; los
    cerrados se quedan con el número que el owner ya revisó."""
    filas = {m: _fila(m, 1000 if m <= 6 else 0) for m in range(1, 13)}
    pos = _posicion()
    pos.salary_amount = Decimal("600000")
    ses = _SesionPlanilla(
        filas,
        ExchangeRate=[_tc(m, 500) for m in range(1, 13)],
        PayrollPosition=[pos], PayrollParams=[], BenefitAllocationConfig=[])
    avisos: list[str] = []

    await recalc._recalc_payroll(ses, _Esc(), avisos, cerrados={1, 2, 3, 4, 5, 6})

    for m in range(1, 7):
        assert filas[m].c6000_sw == Decimal("1000"), (
            f"el mes cerrado {m} se recalculó: {filas[m].c6000_sw}")
    for m in range(7, 13):
        assert filas[m].c6000_sw == Decimal("1200.0000"), (
            f"el mes abierto {m} no se recalculó: {filas[m].c6000_sw}")
    assert any("meses cerrados" in a for a in avisos)


@pytest.mark.asyncio
async def test_el_reparto_anual_da_lo_mismo_con_y_sin_meses_cerrados():
    """Ver el docstring de arriba: proteger julio no puede mover agosto."""
    async def _correr(cerrados):
        filas = {m: _fila(m, 0) for m in range(1, 13)}
        cfg = BenefitAllocationConfig(
            scenario_id="esc", account="6025", label="Cafetería", level="POSITION",
            basis="FTE", active=True,
            amount_crc=Decimal("1200000"), source_type="MONTO")
        ses = _SesionPlanilla(
            filas,
            ExchangeRate=[_tc(m, 500) for m in range(1, 13)],
            PayrollPosition=[_posicion()], PayrollParams=[],
            BenefitAllocationConfig=[cfg])
        await recalc._recalc_payroll(ses, _Esc(), [], cerrados=cerrados)
        return {m: filas[m].c6025_cafeteria for m in range(1, 13)}

    libre = await _correr(set())
    protegido = await _correr({1, 2, 3, 4, 5, 6})

    # Que el reparto haya corrido de verdad. Sin esto la prueba pasa comparando
    # doce ceros contra doce ceros — el modo de falla que ya costó dos veces.
    assert libre[7] > 0, "el reparto no corrió: la prueba no está midiendo nada"

    for m in range(7, 13):
        assert protegido[m] == libre[m], (
            f"proteger enero–junio movió el mes ABIERTO {m}: "
            f"{libre[m]} → {protegido[m]}. El monto anual se está repartiendo "
            f"entre menos filas.")
