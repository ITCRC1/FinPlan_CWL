# -*- coding: utf-8 -*-
"""Los conceptos de planilla digitados no se pierden sin aviso ni rastro.

Owner, 2026-11-27: las horas extra (6001) del Budget 2027 Working no estaban, junto
con comisiones, vacaciones tomadas, vivienda, transporte y otros beneficios — la
huella de un reemplazo de planilla desde Excel, que borraba las posiciones y con
ellas (ON DELETE CASCADE) todos sus conceptos. «Asegúrate que no se borre en el
futuro.»

Lo que cuida:
* Reemplazar la planilla (Excel, bulk, codificación) devuelve lo digitado a la
  posición nueva con la misma llave (departamento + código).
* Lo que no encuentra posición queda en `payroll_conceptos_borrados`, con su monto.
* Poner una tasa en 0 NO borra si no viene confirmado: contesta 409 con la lista.
  Confirmado, borra y deja el registro.
* Borrar una posición deja el registro de lo digitado que se llevó.
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.api import payroll_api as api
from app.engine import conservar_conceptos as CC

pytest.importorskip("aiosqlite")


# ── Lo puro ─────────────────────────────────────────────────────────────────

def test_las_horas_extra_son_un_concepto_que_se_conserva():
    assert "c6001_overtime" in CC.MANUALES and "c6010_commissions" in CC.MANUALES
    assert not ({"c6000_sw", "c6020_ccss", "c6021_aguinaldo", "c6031_contract_labour"} & set(CC.MANUALES))


def test_la_llave_es_departamento_y_codigo():
    p = SimpleNamespace(dept_code="0111", position_code="0111-06", position_name="Agente", employee_name="X")
    assert CC.llave(p) == ("0111", "0111-06")
    q = SimpleNamespace(dept_code="0111", position_code="", position_name="Agente", employee_name="Ana")
    assert CC.llave(q) == ("0111", "", "AGENTE", "ANA")


def test_cruzar_separa_lo_que_vuelve_de_lo_que_se_pierde():
    foto = {("0111", "A"): {1: {"c6001_overtime": Decimal("10")}}, ("0111", "B"): {1: {"c6010_commissions": Decimal("5")}}}
    vuelve, pierde = CC.cruzar(foto, [("0111", "A")])
    assert list(vuelve) == [("0111", "A")] and list(pierde) == [("0111", "B")]
    r = CC.resumen_perdido(pierde)
    assert r == [{"dept_code": "0111", "position_code": "B", "cuenta": "6010", "concepto": "Comisiones",
                  "col": "c6010_commissions", "meses": 1, "monto": Decimal("5"), "detalle": ""}]


def test_los_reemplazos_de_planilla_usan_la_foto():
    for fn in (api.import_payroll_excel, api.bulk_replace_payroll, api.import_codificacion_endpoint):
        src = inspect.getsource(fn)
        assert "CC.foto" in src and "CC.restaurar" in src and "CC.registrar" in src, fn.__name__
    assert "CC.registrar" in inspect.getsource(api.delete_position)


# ── Con base de datos ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.hotel import Hotel
    from app.models.scenario import Scenario
    from app.models.scenario_master import ScenarioMaster
    from app.models.payroll_position import PayrollPosition
    from app.models.payroll_concept_entry import PayrollConceptEntry
    from app.models.payroll_params import PayrollParams
    from app.models.payroll_concepto_borrado import PayrollConceptoBorrado

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        for m in (Hotel, Scenario, ScenarioMaster, PayrollPosition, PayrollConceptEntry, PayrollParams, PayrollConceptoBorrado):
            await c.run_sync(lambda s, m=m: m.__table__.create(s))
    hacer = async_sessionmaker(eng, expire_on_commit=False)
    async with hacer() as s:
        from app.models.hotel import Hotel as H
        from app.models.scenario import Scenario as Sc
        s.add(H(id="CWL", name="Corcovado Wilderness Lodge", short_name="Corcovado", rooms=30))
        s.add(Sc(id="sc-1", hotel_id="CWL", year=2027, type="BUDGET", version="Working", status="draft"))
        await s.commit()
        yield s
    await eng.dispose()


async def _posicion(db, codigo, ot=Decimal("100")):
    from app.models.payroll_position import PayrollPosition
    p = PayrollPosition(scenario_id="sc-1", hotel_id="CWL", dept_code="0111", dept_name="FRONT DESK",
                        position_code=codigo, position_name="Agente", employee_name="VACANTE")
    db.add(p); await db.flush()
    for mes in (1, 2):
        e = await api._get_or_create_entry(db, "sc-1", p, mes, 2027)
        e.c6001_overtime = ot
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_reemplazar_devuelve_las_horas_extra_y_registra_lo_que_no_vuelve(db):
    from sqlalchemy import delete, select
    from app.models.payroll_position import PayrollPosition
    from app.models.payroll_concepto_borrado import PayrollConceptoBorrado

    a = await _posicion(db, "0111-01"); b = await _posicion(db, "0111-02", Decimal("40"))
    foto = await CC.foto(db, "sc-1", [a, b])
    await db.execute(delete(PayrollPosition).where(PayrollPosition.scenario_id == "sc-1")); await db.flush()
    nueva = PayrollPosition(scenario_id="sc-1", hotel_id="CWL", dept_code="0111", position_code="0111-01", position_name="Agente")
    db.add(nueva); await db.flush()
    n, pierde = await CC.restaurar(db, "sc-1", 2027, [nueva], foto)
    await CC.registrar(db, "sc-1", "CWL", "owner@x", "excel_sin_posicion", CC.resumen_perdido(pierde))
    await db.commit()
    assert n == 2
    e1 = await api._get_or_create_entry(db, "sc-1", nueva, 1, 2027)
    assert e1.c6001_overtime == Decimal("100")
    reg = (await db.execute(select(PayrollConceptoBorrado))).scalars().all()
    assert [(r.cuenta, r.position_code, r.monto, r.quien, r.origen) for r in reg] == [("6001", "0111-02", Decimal("80.00"), "owner@x", "excel_sin_posicion")]


@pytest.mark.asyncio
async def test_tasa_en_cero_sin_confirmar_no_borra_y_avisa(db):
    from app.errores import ErrorApi
    from app.models.payroll_params import PayrollParams
    db.add(PayrollParams(scenario_id="sc-1", overtime_pct=Decimal("0.05"))); await db.commit()
    from sqlalchemy import select
    from app.models.payroll_concept_entry import PayrollConceptEntry
    p = await _posicion(db, "0111-01")
    pid = p.id
    cuerpo = api.PayrollParamsBody(ccss_rate=Decimal("0.2683"), aguinaldo_divisor=Decimal("12"), overtime_pct=Decimal("0"))
    with pytest.raises(ErrorApi) as e:
        await api.put_payroll_params("sc-1", cuerpo, db, idioma="es", user=SimpleNamespace(email="owner@x"))
    assert e.value.status_code == 409 and e.value.clave == "planilla.confirmar_borrado"
    assert e.value.extra["borrar"][0]["cuenta"] == "6001" and e.value.extra["borrar"][0]["monto"] == 200.0
    await db.rollback()   # el endpoint no guardó: la petición termina sin commit
    ots = (await db.execute(select(PayrollConceptEntry.c6001_overtime).where(PayrollConceptEntry.position_id == pid))).scalars().all()
    assert ots == [Decimal("100"), Decimal("100")]


@pytest.mark.asyncio
async def test_tasa_en_cero_confirmada_borra_y_registra(db):
    from sqlalchemy import select
    from app.models.payroll_params import PayrollParams
    from app.models.payroll_concepto_borrado import PayrollConceptoBorrado
    db.add(PayrollParams(scenario_id="sc-1", overtime_pct=Decimal("0.05"))); await db.commit()
    p = await _posicion(db, "0111-01")
    cuerpo = api.PayrollParamsBody(ccss_rate=Decimal("0.2683"), aguinaldo_divisor=Decimal("12"), overtime_pct=Decimal("0"),
                                   confirmar_borrado=True)
    r = await api.put_payroll_params("sc-1", cuerpo, db, idioma="es", user=SimpleNamespace(email="owner@x"))
    assert "c6001_overtime" in r["borrados"]
    e1 = await api._get_or_create_entry(db, "sc-1", p, 1, 2027)
    assert not e1.c6001_overtime
    reg = (await db.execute(select(PayrollConceptoBorrado))).scalars().all()
    assert [(x.cuenta, x.origen, x.monto, x.quien) for x in reg] == [("6001", "parametro_en_cero", Decimal("200.00"), "owner@x")]
