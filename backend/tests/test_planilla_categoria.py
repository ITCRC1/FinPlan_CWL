"""Categoria y SubCategoria de cada posición en la planilla.

Owner, 2026-11-22: «necesito categorizar cada posición o por departamento entre
Operations and Non Operation… cuando yo bajo el Excel necesito tener la posibilidad
de filtrar» y, con el archivo de RRHH, «revisa la columna C y D» → las dos tal cual:
Categoria (Operaciones | Administrativo | Gerencial) y SubCategoria (On Property | Outside).
"""
import io

import openpyxl

from app.export.payroll_excel import (COL_CAT, COL_SUBCAT, HEADER_ROW,
                                      export_payroll_to_excel, import_payroll_from_excel)
from app.models.payroll_position import (ADMINISTRATIVO, GERENCIAL, ON_PROPERTY, OPERACIONES,
                                         OUTSIDE, PayrollPosition, categoria_de,
                                         normalizar_categoria, normalizar_subcategoria,
                                         para_guardar, subcategoria_de)

MESES = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _pos(nombre, cat, sub):
    return {"dept_name": "", "position_code": "X-01", "position_name": nombre,
            "employee_name": "VACANTE", "employee_type": "1-Permanente",
            "salary_amount": 500_000, "salary_currency": "CRC",
            "categoria": cat, "subcategoria": sub, **{f"fte_{m}": 1.0 for m in MESES}}


def _exportar():
    xlsx = export_payroll_to_excel(
        {"0111": [_pos("Front Desk Agent", OPERACIONES, ON_PROPERTY)],
         "0182": [_pos("Contador", ADMINISTRATIVO, OUTSIDE)]},
        "CWL Working", 2027, dept_names={"0111": "Front Desk", "0182": "Finance"},
        tc_por_mes=[500.0] * 12)
    return xlsx, openpyxl.load_workbook(io.BytesIO(xlsx)).active


def test_la_regla_del_departamento():
    assert (categoria_de(PayrollPosition(dept_code="0111")),
            subcategoria_de(PayrollPosition(dept_code="0111"))) == (OPERACIONES, ON_PROPERTY)
    assert (categoria_de(PayrollPosition(dept_code="0182")),
            subcategoria_de(PayrollPosition(dept_code="0182"))) == (ADMINISTRATIVO, OUTSIDE)
    assert categoria_de(PayrollPosition(dept_code="0181")) == GERENCIAL
    # la fijada a mano gana sobre la del depto (los gerentes de Front Desk)
    p = PayrollPosition(dept_code="0111", categoria=GERENCIAL)
    assert (categoria_de(p), subcategoria_de(p)) == (GERENCIAL, ON_PROPERTY)


def test_lo_que_se_escribe_a_mano():
    for txt in ("Operaciones", "operations", "OPS"):
        assert normalizar_categoria(txt) == OPERACIONES, txt
    assert normalizar_categoria("administrativo") == ADMINISTRATIVO
    assert normalizar_categoria("Gerencial") == GERENCIAL
    assert normalizar_categoria("Management") == GERENCIAL
    assert normalizar_subcategoria("On Property") == ON_PROPERTY
    assert normalizar_subcategoria("outside") == OUTSIDE
    assert normalizar_categoria("") is None and normalizar_subcategoria("xyz") is None


def test_solo_se_guarda_la_excepcion():
    """Igual a la del depto → None, para que la posición siga a su depto."""
    assert para_guardar("0111", "Operaciones", "On Property") == (None, None)
    assert para_guardar("0182", "Administrativo", "Outside") == (None, None)
    assert para_guardar("0111", "Gerencial", "On Property") == (GERENCIAL, None)
    assert para_guardar("0183", "Operaciones", "On Property") == (OPERACIONES, ON_PROPERTY)


def test_el_excel_trae_las_dos_columnas_con_filtro_que_funciona():
    _, ws = _exportar()
    assert ws.cell(HEADER_ROW, COL_CAT).value == "Categoria"
    assert ws.cell(HEADER_ROW, COL_SUBCAT).value == "SubCategoria"
    filas = [r for r in range(HEADER_ROW + 1, ws.max_row + 1) if ws.cell(r, 4).value]
    assert [(ws.cell(r, COL_CAT).value, ws.cell(r, COL_SUBCAT).value) for r in filas] == \
        [(OPERACIONES, ON_PROPERTY), (ADMINISTRATIVO, OUTSIDE)]
    assert ws.auto_filter.ref.startswith(f"A{HEADER_ROW}:W")
    # con la hoja protegida, filtrar tiene que estar permitido
    assert ws.protection.sheet and ws.protection.autoFilter is False
    for col in (COL_CAT, COL_SUBCAT):
        assert ws.cell(filas[0], col).protection.locked is False
    listas = {dv.formula1 for dv in ws.data_validations.dataValidation}
    assert '"Operaciones,Administrativo,Gerencial"' in listas
    assert '"On Property,Outside"' in listas


def test_ida_y_vuelta_y_el_cambio_a_mano():
    xlsx, _ = _exportar()
    filas = import_payroll_from_excel(xlsx)
    assert [(f["categoria"], f["subcategoria"]) for f in filas] == \
        [(OPERACIONES, ON_PROPERTY), (ADMINISTRATIVO, OUTSIDE)]
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    hoja = wb.active
    fila = next(r for r in range(HEADER_ROW + 1, hoja.max_row + 1)
                if hoja.cell(r, 4).value == "Front Desk Agent")
    hoja.cell(fila, COL_CAT).value = "Gerencial"
    hoja.cell(fila, COL_SUBCAT).value = "Outside"
    out = io.BytesIO(); wb.save(out)
    filas = import_payroll_from_excel(out.getvalue())
    assert (filas[0]["categoria"], filas[0]["subcategoria"]) == (GERENCIAL, OUTSIDE)


def test_un_excel_viejo_sin_las_columnas_sigue_subiendo():
    xlsx, _ = _exportar()
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    hoja = wb.active
    hoja.delete_cols(COL_CAT, 2)
    out = io.BytesIO(); wb.save(out)
    filas = import_payroll_from_excel(out.getvalue())
    assert len(filas) == 2
    assert all(f["categoria"] is None and f["subcategoria"] is None for f in filas)
    assert filas[0]["salary_amount"] == 500_000


# ── Bajar filtrado y volver a subir ─────────────────────────────────────────
# Owner, 2026-11-22: «quiero tener la posibilidad antes de bajar el Excel poder
# filtrar por operacional o Admin». Lo peligroso no es bajar: es SUBIR, porque el
# import reemplaza cada depto del archivo. Recepción (0111) tiene Operaciones y dos
# Gerencial: si el archivo filtrado solo trae las Operaciones y el depto se
# reemplazara entero, subirlo borraría a los Gerencial sin avisar.
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.export.payroll_excel import categorias_del_archivo  # noqa: E402


@pytest_asyncio.fixture
async def base():
    pytest.importorskip("aiosqlite")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.department_catalog import DepartmentCatalog
    from app.models.exchange_rate import ExchangeRate
    from app.models.hotel import Hotel
    from app.models.payroll_concept_entry import PayrollConceptEntry
    from app.models.scenario import Scenario

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        for m in (Hotel, Scenario, PayrollPosition, PayrollConceptEntry, ExchangeRate,
                  DepartmentCatalog):
            await c.run_sync(lambda s, m=m: m.__table__.create(s))
    hacer = async_sessionmaker(eng, expire_on_commit=False)
    async with hacer() as db:
        from app.models.hotel import Hotel
        db.add(Hotel(id="CWL", name="Corcovado Wilderness Lodge", short_name="Corcovado", rooms=30))
        db.add(Scenario(id="sc-1", hotel_id="CWL", year=2027, type="BUDGET",
                        version="Working", status="draft"))
        for i, (dept, nombre, cat) in enumerate((
                ("0111", "Front Desk Agent", None),
                ("0111", "Front Office Manager", GERENCIAL),
                ("0182", "Contador", None))):
            db.add(PayrollPosition(id=f"p{i}", scenario_id="sc-1", hotel_id="CWL",
                                   dept_code=dept, position_name=nombre, categoria=cat,
                                   salary_amount=500_000, salary_currency="CRC"))
        await db.commit()
        yield db
    await eng.dispose()


async def _bajar(db, categoria=None):
    from app.api.payroll_api import export_payroll_excel
    return (await export_payroll_excel("sc-1", categoria=categoria, db=db)).body


async def _subir(db, xlsx):
    from starlette.datastructures import UploadFile

    from app.api.payroll_api import import_payroll_excel
    return await import_payroll_excel("sc-1", file=UploadFile(io.BytesIO(xlsx), filename="p.xlsx"),
                                      replace=True, db=db, idioma="es")


async def _puestos(db):
    from sqlalchemy import select
    return sorted((p.dept_code, p.position_name) for p in
                  (await db.execute(select(PayrollPosition))).scalars().all())


@pytest.mark.asyncio
async def test_bajar_solo_operaciones_trae_solo_esas(base):
    ws = openpyxl.load_workbook(io.BytesIO(await _bajar(base, "Operaciones"))).active
    puestos = {ws.cell(r, 4).value for r in range(HEADER_ROW + 1, ws.max_row + 1)} - {None, "TOTAL DEPT"}
    assert "Front Desk Agent" in puestos
    assert "Front Office Manager" not in puestos and "Contador" not in puestos
    assert "Operaciones" in str(ws.cell(2, 1).value)


@pytest.mark.asyncio
async def test_bajar_admin_y_gerencial_juntos(base):
    xlsx = await _bajar(base, "Administrativo,Gerencial")
    assert categorias_del_archivo(xlsx) == {ADMINISTRATIVO, GERENCIAL}


@pytest.mark.asyncio
async def test_las_tres_o_ninguna_es_el_archivo_completo(base):
    for cat in (None, "", "Operaciones,Administrativo,Gerencial"):
        assert categorias_del_archivo(await _bajar(base, cat)) is None


@pytest.mark.asyncio
async def test_una_categoria_que_no_existe_se_rechaza(base):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await _bajar(base, "Mantenimiento")


@pytest.mark.asyncio
async def test_subir_el_filtrado_no_borra_a_los_demas_del_depto(base):
    """El caso que importa: Recepción baja sin su gerente, sube, y el gerente sigue."""
    antes = await _puestos(base)
    await _subir(base, await _bajar(base, "Operaciones"))
    assert await _puestos(base) == antes


@pytest.mark.asyncio
async def test_subir_el_completo_sigue_reemplazando_el_depto(base):
    """Sin filtro, igual que siempre: lo que no viene en el archivo se va."""
    xlsx = await _bajar(base)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    ws = wb.active
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        if ws.cell(r, 4).value == "Front Office Manager":
            ws.cell(r, 4).value = None
    buf = io.BytesIO(); wb.save(buf)
    await _subir(base, buf.getvalue())
    assert ("0111", "Front Office Manager") not in await _puestos(base)
