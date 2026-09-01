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
import io
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
async def test_el_mes_se_sube_muchas_veces_hasta_el_cierre_acordado(cliente):
    """Subir de nuevo es el FLUJO, no la excepción.

    Owner (2026-08-31): *«es posible que el Integrity lo suba múltiples veces,
    porque es revisión: un error en posteo se corrige y se sube otra vez, y así
    sucesivamente hasta lograr el final acordado»*.

    Así que cada vuelta reemplaza el borrador anterior **sin preguntar**. Pedir
    confirmación en cada una convertiría el camino principal en una molestia, y
    a la quinta nadie lee el aviso.

    ⚠️ Esto es lo que exige que la unicidad sea un índice PARCIAL sobre los
    borradores. Con una unique de cuatro columnas —(hotel, año, mes, estado)—
    la TERCERA subida reventaba: ya habría dos filas «descartado» del mes.
    """
    import openpyxl
    async with cliente() as c:
        # Tres vueltas con contenido distinto, como un error de posteo corregido.
        ids = []
        for vuelta in range(3):
            wb = openpyxl.load_workbook(FIXTURE)
            wb["Final"]["R17"] = 52273.25 + vuelta      # una cifra que cambia
            buf = io.BytesIO()
            wb.save(buf)
            r = await c.post("/api/precierre/?tc=454.75&mes=7&anio=2026",
                             files={"file": (f"Conc JUL v{vuelta}.xlsx",
                                             buf.getvalue())})
            assert r.status_code == 200, f"vuelta {vuelta}: {r.text}"
            j = r.json()
            assert j["vuelta"] == vuelta + 1
            if vuelta:
                assert j["reemplaza_a"]["id"] == ids[-1], "no dijo a cuál reemplazó"
            ids.append(j["id"])

        # Un solo borrador vivo; las vueltas anteriores quedan de historia.
        listado = (await c.get("/api/precierre/")).json()["precierres"]
        del_mes = [p for p in listado if p["mes"] == 7 and p["anio"] == 2026]
        assert len([p for p in del_mes if p["estado"] == "borrador"]) == 1
        assert len([p for p in del_mes if p["estado"] == "descartado"]) == 2


@pytest.mark.asyncio
async def test_el_mismo_archivo_dos_veces_si_avisa(cliente):
    """Distinto de lo de arriba: el CONTENIDO idéntico no es una vuelta nueva,
    es la misma. Lo dice `registro_de_subida`, el mecanismo común a las
    veinticuatro puertas — y se puede insistir con `permitir_reimport`."""
    async with cliente() as c:
        assert (await _subir(c)).status_code == 200
        mismo = await _subir(c)
        assert mismo.status_code == 409
        assert "import" in json.dumps(mismo.json(), ensure_ascii=False).lower()
        assert (await _subir(c, permitir_reimport="true")).status_code == 200


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


# ═════════════════════════════════════════════════════════════════════════════
# LAS DESCARGAS — «todos los datos de este módulo, en Excel editable»
# ═════════════════════════════════════════════════════════════════════════════

#: Los once controles del bloque VERIF del libro del owner (julio 2026).
VERIF_DEL_OWNER = {
    "VER_INGRESOS": D("248437.33"), "VER_GASTO_OPERATIVO": D("147248.79"),
    "VER_OVERHEAD": D("178789.87"), "VER_GOP": D("-77601.33"),
    "VER_NO_OPERATIVO": D("18664.70"), "VER_EBITDA": D("-96266.03"),
    "VER_CAPITAL": D("9937.63"), "VER_FINANCIEROS": D("0"),
    "VER_DEPRECIACION": D("28343.41"), "VER_IMPUESTO": D("-40364.12"),
    "VER_UTILIDAD_NETA": D("-94182.95"),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("ruta,nombre", [
    ("detalle.xlsx", "el formato estándar de FinPlan"),
    ("filas.xlsx", "el detalle traducido"),
    ("hoja.xlsx", "la hoja de revisión"),
])
async def test_todo_se_puede_bajar(cliente, ruta, nombre):
    import openpyxl
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        r = await c.get(f"/api/precierre/{pid}/{ruta}")
    assert r.status_code == 200, nombre
    assert "attachment" in r.headers["content-disposition"]
    openpyxl.load_workbook(io.BytesIO(r.content))      # que abra de verdad


@pytest.mark.asyncio
async def test_el_listado_tambien(cliente):
    import openpyxl
    async with cliente() as c:
        await _subir(c)
        r = await c.get("/api/precierre/listado.xlsx")
    assert r.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    assert ws.cell(1, 1).value == "Año"
    assert ws.cell(2, 2).value == 7


@pytest.mark.asyncio
async def test_la_plantilla_estandar_lleva_los_once_controles(cliente):
    """El bloque VERIF del formato de FinPlan, contra el del libro del owner.

    Es lo que decide si la carga pasa: si estos once no cuadran contra el
    detalle de abajo, `import-gl-detail` la frena. Que salgan bien acá es lo que
    hace que el archivo se pueda subir sin tocarlo.
    """
    import openpyxl
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        r = await c.get(f"/api/precierre/{pid}/detalle.xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    vistos = {}
    for fila in ws.iter_rows(min_row=1, max_row=14, values_only=True):
        for j, v in enumerate(fila):
            if isinstance(v, str) and v.startswith("VER_"):
                vistos[v] = next((x for x in fila[j + 1:]
                                  if isinstance(x, (int, float))), None)
    malos = {k: (float(esp), vistos.get(k)) for k, esp in VERIF_DEL_OWNER.items()
             if vistos.get(k) is None or abs(D(str(vistos[k])) - esp) > D("0.02")}
    assert not malos, f"controles que no coinciden con el libro del owner: {malos}"


@pytest.mark.asyncio
async def test_las_descargas_son_valores_y_no_formulas(cliente):
    """Editable de verdad. Un Excel con fórmulas se ve igual pero se rompe al
    editar una celda de la que otras dependen, y el que lo edita no se entera."""
    import openpyxl
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        for ruta in ("detalle.xlsx", "filas.xlsx", "hoja.xlsx"):
            r = await c.get(f"/api/precierre/{pid}/{ruta}")
            wb = openpyxl.load_workbook(io.BytesIO(r.content))   # sin data_only
            formulas = [(ws.title, c2.coordinate) for ws in wb.worksheets
                        for fila in ws.iter_rows() for c2 in fila
                        if isinstance(c2.value, str) and c2.value.startswith("=")]
            assert not formulas, f"{ruta} trae fórmulas: {formulas[:5]}"


@pytest.mark.asyncio
async def test_el_detalle_traducido_dice_de_donde_salio_cada_numero(cliente):
    """Lleva la fila del Excel de origen: sin eso, revisar un número obliga a
    buscarlo a ojo en el archivo de Integrity."""
    import openpyxl
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        r = await c.get(f"/api/precierre/{pid}/filas.xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    encabezados = [ws.cell(1, j).value for j in range(1, 11)]
    assert encabezados[0] == "Fila origen"
    assert "Depto Integrity" in encabezados and "Depto FinPlan" in encabezados
    assert ws.max_row == 326      # 325 filas + encabezado


# ═════════════════════════════════════════════════════════════════════════════
# EL INFORME DE LA REVISIÓN
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_los_hallazgos_del_archivo_se_calculan_al_subir(cliente):
    """Los niveles 1 y 2 dependen de lo que el lector descarta —filas sin
    cuenta, subdetalle, departamentos sin puente— y eso no se guarda. Si no se
    calculan al subir, después no se pueden calcular."""
    async with cliente() as c:
        j = (await _subir(c)).json()
    claves = {h["clave"] for h in j["hallazgos"]}
    assert "cuenta_sin_mapeo" in claves
    assert all(h["nivel"] in (1, 2) for h in j["hallazgos"])


@pytest.mark.asyncio
async def test_el_informe_ordena_por_gravedad_y_por_monto(cliente):
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        d = (await c.get(f"/api/precierre/{pid}/hallazgos/")).json()
    orden = {"critico": 0, "aviso": 1, "info": 2}
    llaves = [(orden[h["gravedad"]], -abs(h["monto"])) for h in d["hallazgos"]]
    assert llaves == sorted(llaves)
    assert d["resumen"]["critico"] >= 1


@pytest.mark.asyncio
async def test_el_informe_dice_lo_que_NO_pudo_revisar(cliente):
    """«No se revisó» y «está bien» se ven igual en una lista vacía. Esa
    confusión es la que este módulo viene a eliminar."""
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        d = (await c.get(f"/api/precierre/{pid}/hallazgos/")).json()
    assert d["sin_revisar"], "tiene que decir qué cruces no se hicieron"
    assert any("planilla" in x for x in d["sin_revisar"])


@pytest.mark.asyncio
async def test_los_umbrales_se_ajustan_sin_volver_a_subir(cliente):
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        d = (await c.get(f"/api/precierre/{pid}/hallazgos/"
                         "?umbral_monto=1&umbral_pct=1")).json()
    assert d["umbrales"] == {"monto": 1.0, "pct": 1.0}


@pytest.mark.asyncio
async def test_las_estadisticas_imposibles_llegan_al_informe(cliente):
    """El nivel 3 corre en vivo con lo que le pasa la pantalla."""
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        d = (await c.get(f"/api/precierre/{pid}/hallazgos/"
                         "?rooms_disponibles=930&rooms_ocupadas=1200"
                         "&huespedes=1500")).json()
    assert "estadisticas_incoherentes" in {h["clave"] for h in d["hallazgos"]}


@pytest.mark.asyncio
async def test_ningun_hallazgo_impide_nada(cliente):
    """El informe informa. Bloquear es potestad de los cuatro controles de la
    verificación, y de nadie más."""
    async with cliente() as c:
        pid = (await _subir(c)).json()["id"]
        r = await c.get(f"/api/precierre/{pid}/hallazgos/")
        assert r.status_code == 200
        assert r.json()["resumen"]["critico"] >= 1
        # y con hallazgos críticos la hoja y las descargas siguen funcionando
        assert (await c.get(f"/api/precierre/{pid}/detalle.xlsx")).status_code == 200
