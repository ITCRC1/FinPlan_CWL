# -*- coding: utf-8 -*-
"""
EL CARRIL DE ESPERA, DE PUNTA A PUNTA.

Sube el estado de resultados crudo de Integrity por el endpoint y comprueba que
del otro lado sale el mes de julio 2026 tal como el owner ya lo cerró. Es la
misma prueba de oro de `test_integrity_final`, pero atravesando la API y la
base: si el traductor está bien pero el guardado redondea, acá se ve.

Necesita PostgreSQL. Sin base se salta sola, igual que el resto de las pruebas
que la piden.
"""
import json
import pathlib
from decimal import Decimal as D

import pytest
import pytest_asyncio

BASE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = BASE / "tests" / "fixtures" / "integrity_final_JUL2026.xlsx"
ESPERADO = BASE / "tests" / "fixtures" / "revision_JUL2026_esperado.json"

pytest.importorskip("httpx")


def _hay_base() -> bool:
    """⚠️ Y al terminar **se desecha el pool**.

    `asyncio.run()` abre un bucle propio y lo cierra. Las conexiones que quedan
    en el pool del motor pertenecen a ese bucle muerto, y la primera prueba que
    las tome revienta con «Event loop is closed» — un fallo que no tiene nada
    que ver con lo que se está probando y que cuesta media hora entender.
    """
    import asyncio
    try:
        from sqlalchemy import text
        from app.db import SessionLocal, engine

        async def probar():
            try:
                async with SessionLocal() as db:
                    await db.execute(text("select 1 from precierre limit 1"))
            finally:
                await engine.dispose()
        asyncio.run(probar())
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _hay_base(),
    reason="Necesita PostgreSQL con la migración 138 (definir DATABASE_URL)")


@pytest.fixture()
def cliente():
    """La app, sin el guard de sesión: lo que se prueba acá es el flujo, no el
    login."""
    from httpx import ASGITransport, AsyncClient
    from app.auth import get_current_user
    from app.main import app

    class Usuario:
        email = "prueba@local"

    app.dependency_overrides[get_current_user] = lambda: Usuario()
    yield lambda: AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture(autouse=True)
async def _limpio():
    """Cada prueba arranca sin pre-cierres. No se tocan otras tablas.

    Es `async` a propósito: con `asyncio.run()` adentro correría en OTRO bucle
    que el de la prueba, y las conexiones cruzadas fallan con «Event loop is
    closed»."""
    from sqlalchemy import delete
    from app.db import SessionLocal, engine
    from app.models.import_registro import ImportBatch
    from app.models.precierre import Precierre

    async def borrar():
        async with SessionLocal() as db:
            await db.execute(delete(Precierre))
            # Y el rastro del registro de subidas. Si no, la segunda prueba sube
            # el MISMO fixture y `registro_de_subida` la frena con «ya se
            # importó» — que es exactamente lo que tiene que hacer en producción,
            # pero acá sería una prueba contaminando a la siguiente.
            await db.execute(delete(ImportBatch).where(
                ImportBatch.endpoint.like("%precierre%")))
            await db.commit()
    # También al EMPEZAR: el módulo anterior de la suite dejó conexiones de su
    # propio bucle en el pool, y la primera prueba de acá se las encuentra.
    await engine.dispose()
    await borrar()
    yield
    await borrar()
    # ⚠️ Y se desecha el pool al terminar CADA prueba. `pytest-asyncio` abre un
    # bucle nuevo por prueba, pero el motor es del módulo: sin esto, la segunda
    # prueba toma una conexión que pertenece al bucle ya cerrado de la primera y
    # falla con «Event loop is closed». Sola pasa; en conjunto, no.
    await engine.dispose()


async def _subir(c, **extra):
    q = {"tc": "454.75", "mes": "7", "anio": "2026", **extra}
    url = "/api/precierre/?" + "&".join(f"{k}={v}" for k, v in q.items())
    return await c.post(url, files={"file": ("Conc JUL 2026.xlsx",
                                             FIXTURE.read_bytes())})


@pytest.mark.asyncio
async def test_sube_y_traduce(cliente):
    async with cliente() as c:
        r = await _subir(c)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["filas"] == 325
        assert j["sin_mapeo"] == []


@pytest.mark.asyncio
async def test_la_prueba_de_oro_atraviesa_la_base(cliente):
    """Los cuatro controles de julio, después de ida y vuelta por PostgreSQL.

    ⚠️ La utilidad neta se compara EXACTA. Con `Numeric(16,2)` en las filas se
    redondeaban las 325 antes de sumarlas y daba -94.182,93: dos centavos que no
    rompían ninguna validación. La deriva que nadie nota es la que se acumula.
    """
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        hoja = {f["etiqueta"]: f["actual"]
                for f in (await c.get(f"/api/precierre/{pid}/")).json()["hoja"]
                if f["actual"] is not None}
    assert abs(D(str(hoja["TOTAL INCOMES"])) - D("248437.33")) < D("0.005")
    assert abs(D(str(hoja["Total Operationg expenses"])) - D("147248.79")) < D("0.005")
    assert abs(D(str(hoja["TOTAL OVERHEAD EXPENSES"])) - D("178789.87")) < D("0.005")
    assert abs(D(str(hoja["EARNINGS AFTER INCOME TAXES"])) - D("-94182.95")) < D("0.005")


@pytest.mark.asyncio
async def test_la_hoja_descargada_reproduce_el_tab(cliente):
    """El Excel que baja de la API, celda por celda contra el tab del owner."""
    import io
    import openpyxl
    from app.export import revision_mes_xlsx as rev
    referencia = json.loads(ESPERADO.read_text(encoding="utf-8"))["filas"]
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        r = await c.get(f"/api/precierre/{pid}/hoja.xlsx")
    assert r.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    malas = [(x["fila"], x["etiqueta"]) for x in referencia
             if abs(D(str(ws.cell(x["fila"], rev.COL_ACTUAL).value or 0))
                    - D(str(x["actual"] or 0))) > D("0.06")
             or (ws.cell(x["fila"], rev.COL_ETIQUETA).value or "") != x["etiqueta"]]
    assert not malas, f"celdas que no coinciden: {malas}"


@pytest.mark.asyncio
async def test_hay_DOS_guardas_y_cada_una_pregunta_lo_suyo(cliente):
    """Subir dos veces choca contra dos frenos distintos, en orden.

    1. **`registro_de_subida`** ve el mismo CONTENIDO y dice «este archivo ya se
       importó». Es el mecanismo común a las veinticuatro puertas de subida.
    2. Recién pasado ése, el pre-cierre ve que el MES ya tiene un borrador en
       revisión y pregunta si se descarta.

    Son dos preguntas distintas —«¿el mismo archivo otra vez?» y «¿tiro lo que
    estabas revisando?»— y cada una se contesta con su propia bandera. Juntarlas
    en una sola haría que confirmar una confirmara la otra sin querer.
    """
    async with cliente() as c:
        assert (await _subir(c)).status_code == 200

        mismo = await _subir(c)
        assert mismo.status_code == 409
        assert "import" in json.dumps(mismo.json(), ensure_ascii=False).lower()

        otra_vez = await _subir(c, permitir_reimport="true")
        assert otra_vez.status_code == 409
        assert otra_vez.json()["detail"]["motivo"] == "ya_hay_borrador"

        ambas = await _subir(c, permitir_reimport="true", reemplazar="true")
        assert ambas.status_code == 200, ambas.text


@pytest.mark.asyncio
async def test_el_tipo_de_cambio_es_obligatorio(cliente):
    """Sin TC no hay carga. No se deduce del archivo ni se toma un default."""
    async with cliente() as c:
        r = await c.post("/api/precierre/?mes=7&anio=2026",
                         files={"file": ("x.xlsx", FIXTURE.read_bytes())})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_un_archivo_que_no_es_de_integrity_lo_dice(cliente):
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Otra"
    buf = io.BytesIO()
    wb.save(buf)
    async with cliente() as c:
        r = await c.post("/api/precierre/?tc=454.75&mes=7&anio=2026",
                         files={"file": ("cualquiera.xlsx", buf.getvalue())})
    assert r.status_code == 422
    assert "Final" in json.dumps(r.json(), ensure_ascii=False)


@pytest.mark.asyncio
async def test_descartar_no_borra(cliente):
    """Queda la traza de que se intentó."""
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        r = await c.delete(f"/api/precierre/{pid}/")
        assert r.status_code == 200 and r.json()["estado"] == "descartado"
        listado = (await c.get("/api/precierre/")).json()["precierres"]
    assert [p for p in listado if p["id"] == pid]
