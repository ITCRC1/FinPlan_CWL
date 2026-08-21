"""
El mapeo de cuentas y la estructura del reporte se leen una vez por petición.

El P&L se computa mes a mes, así que sin caché estas dos tablas —globales e
inmutables durante una petición— se releían 25 veces por pantalla. Eran 50 de
las 280 consultas del Cash Flow Budget, y ese costo fue lo que vació el pool de
conexiones y tumbó las pantallas con «Failed to fetch».

Run: pytest tests/test_cache_configuracion.py -v
"""
import pytest

from app.engine.recalculate import (
    _cache_de_configuracion,
    load_active_account_mappings,
    load_report_line_config,
)


class _Fila:
    """Fila mínima con los atributos que leen los cargadores."""
    account_code = "7080"
    dept_code = "0110"
    report_line_code = "OPEX_ROOMS"
    active_status = "YES"
    rollup_operator = "SUM"
    line_code = "OPEX_ROOMS"
    line_name = "Rooms"
    section = "OPEX"
    line_type = "MAPPED"
    display_order = 10
    calculation_logic = None
    active = True


class _Resultado:
    def scalars(self):
        return self

    def all(self):
        return [_Fila()]


class _SesionFalsa:
    """Sesión de mentira que cuenta cuántas veces la consultan."""

    def __init__(self):
        self.info = {}
        self.consultas = 0

    async def execute(self, *_a, **_k):
        self.consultas += 1
        return _Resultado()


@pytest.mark.asyncio
async def test_el_mapeo_se_lee_una_sola_vez_por_sesion():
    s = _SesionFalsa()
    for _ in range(25):
        await load_active_account_mappings(s)
    assert s.consultas == 1, "el mapeo se releyó: el caché no está actuando"


@pytest.mark.asyncio
async def test_la_estructura_del_reporte_se_lee_una_sola_vez():
    s = _SesionFalsa()
    for _ in range(25):
        await load_report_line_config(s)
    assert s.consultas == 1


@pytest.mark.asyncio
async def test_devuelve_lo_mismo_cacheado_que_recien_leido():
    s = _SesionFalsa()
    primera = await load_active_account_mappings(s)
    segunda = await load_active_account_mappings(s)
    assert primera == segunda


@pytest.mark.asyncio
async def test_quien_modifica_la_lista_no_envenena_a_los_demas():
    """Se devuelve una copia: ordenar o agregar en un consumidor no puede
    corromper lo que ve el siguiente."""
    s = _SesionFalsa()
    primera = await load_active_account_mappings(s)
    primera.append({"account_code": "BASURA"})
    segunda = await load_active_account_mappings(s)
    assert len(segunda) == 1
    assert segunda[0]["account_code"] == "7080"


@pytest.mark.asyncio
async def test_dos_reportes_distintos_no_comparten_entrada():
    s = _SesionFalsa()
    await load_active_account_mappings(s, report_id="P&L_DETAIL_OWNERS")
    await load_active_account_mappings(s, report_id="OTRO_REPORTE")
    assert s.consultas == 2, "el caché debe separar por report_id"


@pytest.mark.asyncio
async def test_el_cache_no_cruza_entre_sesiones():
    """Cada petición tiene su sesión: lo cacheado en una no puede aparecer en
    otra, si no un cambio de mapeo nunca se vería."""
    a, b = _SesionFalsa(), _SesionFalsa()
    await load_active_account_mappings(a)
    await load_active_account_mappings(b)
    assert a.consultas == 1 and b.consultas == 1
    assert _cache_de_configuracion(a) is not _cache_de_configuracion(b)
