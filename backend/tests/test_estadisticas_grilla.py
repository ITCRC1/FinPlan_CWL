# -*- coding: utf-8 -*-
"""La grilla de estadísticas: qué filas hay que llenar en cada escenario.

**De dónde salió (owner, 2026-08-14).** «Para el presupuesto ya hay que hacer la
combinación.» Tiene razón: para cargar un actual la combinación viene con el
dato, pero para presupuestar hay que poder escribir en cada casilla, así que las
filas tienen que existir antes.

La decisión fue **generarlas, no guardarlas como cuentas**. Con las permutaciones
en el catálogo serían más de dos mil cuentas —y con el producto completo, más de
cincuenta mil—, pero lo que decide no es el volumen: **contratar a alguien en una
posición nueva obligaría a crear nueve cuentas antes de poder cargarle una hora**,
y si nadie las crea esas horas caen en la posición equivocada por regla de
repuesto. Es lo que pasó con el SPA y el departamento 0130.
"""
from types import SimpleNamespace

import pytest

from app.engine import estadisticas_grilla as g
from app.models.stat_account import StatAccount


def _cta(code, dims, grupo="9980", deptos="", nombre="X", unidad="hours"):
    return StatAccount(code=code, grupo=grupo, nombre_es=nombre, unidad=unidad,
                       dims=dims, deptos=deptos, agrega="SUM", activa=True)


class _Sesion:
    """Sesión de mentira: devuelve las listas que se le den, sin base."""
    def __init__(self, posiciones=(), deptos=(), tipos=(), mcodes=(), paises=()):
        self._p, self._d = list(posiciones), list(deptos)
        self._t, self._m = list(tipos), list(mcodes)
        # Los países del Country Mix del escenario: desde el 18-ago-2026 la
        # grilla los consulta para poder generar las cuentas por país.
        self._pa = list(paises)

    async def execute(self, stmt):
        # Se decide por la tabla que consulta el `select`.
        tabla = stmt.column_descriptions[0]["entity"].__tablename__
        datos = {"payroll_positions": self._p, "department_catalog": self._d,
                 "room_type_configs": self._t, "market_codes": self._m,
                 "country_mix_entries": self._pa}[tabla]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: datos))


def _pos(dept, code, nombre="ALGUIEN"):
    return SimpleNamespace(dept_code=dept, position_code=code,
                           position_name=nombre, dept_name=dept)


def _dep(code, nombre=""):
    return SimpleNamespace(dept_code=code, dept_name=nombre or code)


def _tipo(code, nombre=""):
    return SimpleNamespace(code=code, name=nombre or code)


def _mc(code, canal="Direct Client"):
    return SimpleNamespace(code=code, canal=canal, nombre=code, orden=0, activo=True)


ESC = SimpleNamespace(id="s1", hotel_id="CWL")


async def _construir(cuentas, **kw):
    return await g.construir(_Sesion(**kw), ESC, cuentas)


# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_una_posicion_con_varias_personas_da_UNA_fila():
    """⚠️ El bug que apareció al construirla la primera vez.

    Una posición puede tener varias personas: hay tres «AGENTE DE RECEPCIÓN 501»
    en el mismo departamento. Recorriendo las filas de planilla salían 126
    llaves repetidas — la grilla pedía el mismo dato tres veces y la carga
    habría guardado el último, perdiendo los otros dos.
    """
    filas = await _construir(
        [_cta("9980", "DEPT,POSITION")],
        posiciones=[_pos("0111", "501"), _pos("0111", "501"), _pos("0111", "501")],
        deptos=[_dep("0111")])
    assert len(filas) == 1
    assert filas[0].dept_code == "0111" and filas[0].position_code == "501"


@pytest.mark.asyncio
async def test_ninguna_llave_se_repite():
    """La llave de la grilla es la misma que la restricción de unicidad de la
    tabla. Dos filas con la misma llave son dos casillas para el mismo dato."""
    filas = await _construir(
        [_cta("9980", "DEPT,POSITION"), _cta("9981", "DEPT,POSITION"),
         _cta("9700", "DEPT", grupo="9700", deptos="0110"),
         _cta("9040", "ROOMTYPE", grupo="9000")],
        posiciones=[_pos("0111", "501"), _pos("0111", "502"), _pos("0120", "601")],
        deptos=[_dep("0110"), _dep("0111"), _dep("0120")],
        tipos=[_tipo("BL01"), _tipo("BI02")])
    llaves = [f.llave for f in filas]
    assert len(llaves) == len(set(llaves))


@pytest.mark.asyncio
async def test_la_posicion_sin_codigo_no_entra():
    """Sin código no hay forma de identificarla en un archivo: la fila no se
    podría cargar de vuelta."""
    filas = await _construir(
        [_cta("9980", "DEPT,POSITION")],
        posiciones=[_pos("0111", ""), _pos("0111", "501")],
        deptos=[_dep("0111")])
    assert [f.position_code for f in filas] == ["501"]


@pytest.mark.asyncio
async def test_una_cuenta_con_dimension_sin_definir_no_genera_filas():
    """⚠️ El PAÍS no tiene lista canónica: `country_mix_entries` la lleva
    abierta, sin catálogo. Generar filas con códigos inventados es peor que no
    generarlas: alguien las llenaría y el dato quedaría atado a una lista que
    después va a cambiar."""
    filas = await _construir(
        [_cta("9080", "COUNTRY", grupo="9000"),
         _cta("9040", "ROOMTYPE", grupo="9000")],
        tipos=[_tipo("BL01")], deptos=[_dep("0110")])
    assert {f.account_code for f in filas} == {"9040"}


@pytest.mark.asyncio
async def test_el_segmento_de_mercado_es_el_market_code():
    """El owner mandó su tabla de Market Codes (2026-08-14): SEGMENT son sus
    códigos de Opera, no una lista inventada."""
    filas = await _construir(
        [_cta("9000", "SEGMENT", grupo="9000", unidad="nights")],
        mcodes=[_mc("BAR"), _mc("TAFIT", "Travel Agent"), _mc("WEB", "Website")])
    assert {f.dim_code for f in filas} == {"BAR", "TAFIT", "WEB"}
    assert {f.dim_type for f in filas} == {"SEGMENT"}


@pytest.mark.asyncio
async def test_segmento_por_tipo_de_habitacion_se_cruzan():
    filas = await _construir(
        [_cta("9000", "SEGMENT,ROOMTYPE", grupo="9000", unidad="nights")],
        mcodes=[_mc("BAR"), _mc("WEB", "Website")],
        tipos=[_tipo("BL01"), _tipo("BI02")])
    assert len(filas) == 4
    assert len({f.llave for f in filas}) == 4


@pytest.mark.asyncio
async def test_los_canales_salen_de_los_market_codes():
    """⚠️ NO de una lista aparte. Había TRES listas de canales en el sistema que
    no se hablaban; derivarlos del market code es lo que impide que vuelvan a
    desincronizarse.

    Y un código SIN canal no aporta canal: no se adivina."""
    filas = await _construir(
        [_cta("9070", "CHANNEL", grupo="9000", unidad="rooms")],
        mcodes=[_mc("BAR", "Direct Client"), _mc("DIR", "Direct Client"),
                _mc("TAFIT", "Travel Agent"), _mc("CORP", "")])
    assert {f.dim_code for f in filas} == {"Direct Client", "Travel Agent"}


@pytest.mark.asyncio
async def test_la_cuenta_solo_pide_sus_departamentos():
    """⚠️ Sin esto, una cuenta con dimensión DEPT genera fila para los 38
    departamentos: covers de Mantenimiento, kilos de Ventas. Cientos de filas
    que nunca van a tener dato — y una fila siempre vacía entrena a no mirar."""
    filas = await _construir(
        [_cta("9110", "DEPT", grupo="9110", deptos="0120,0123", unidad="covers")],
        deptos=[_dep("0110"), _dep("0120"), _dep("0123"), _dep("0200")])
    assert sorted(f.dept_code for f in filas) == ["0120", "0123"]


@pytest.mark.asyncio
async def test_la_cuenta_sin_dimensiones_da_una_sola_fila():
    filas = await _construir([_cta("9010", "", grupo="9000", unidad="rooms")],
                             deptos=[_dep("0110"), _dep("0120")])
    assert len(filas) == 1
    assert filas[0].dept_code == "" and filas[0].position_code == ""


@pytest.mark.asyncio
async def test_la_planilla_solo_pide_departamentos_con_gente():
    """Un departamento sin una sola posición no va a tener horas."""
    filas = await _construir(
        [_cta("9900", "DEPT,POSITION", grupo="9900", unidad="count")],
        posiciones=[_pos("0111", "501")],
        deptos=[_dep("0111"), _dep("0200"), _dep("0230")])
    assert {f.dept_code for f in filas} == {"0111"}
