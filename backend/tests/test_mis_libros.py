"""Mis libros: el Excel del owner se guarda tal cual, uno por título.

Owner, 2026-11-24: «quiero ir a un lugar solo y bajar mis proyectos, mis
creaciones, pero que no se rompa nada» y «no quiero llenarme de versiones».

Lo que se prueba:
- se devuelve EXACTO lo que se subió (byte por byte: el Power Query viaja ahí);
- subir con el mismo título reemplaza y deja UNA versión anterior, no más;
- «volver a la anterior» las intercambia;
- solo entra un Excel de verdad.
"""
import io
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import pytest_asyncio

pytest.importorskip("aiosqlite")


@pytest_asyncio.fixture
async def api(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.api import libros_colgados_api as mod
    from app.models.libro_colgado import LibroColgado

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        await c.run_sync(lambda s: LibroColgado.__table__.create(s))
    hacer = async_sessionmaker(eng, expire_on_commit=False)

    @asynccontextmanager
    async def sesion():
        async with hacer() as s:
            yield s

    monkeypatch.setattr(mod, "get_session", sesion)
    yield mod
    await eng.dispose()


class _Archivo:
    def __init__(self, nombre, datos):
        self.filename, self._d = nombre, datos

    async def read(self):
        return self._d


ADMIN = SimpleNamespace(email="owner@hotel")


def _xlsx(marca: bytes) -> bytes:
    return b"PK\x03\x04" + marca * 1000


@pytest.mark.asyncio
async def test_se_baja_exacto_lo_que_se_subio(api):
    datos = _xlsx(b"v13")
    r = await api.subir_libro("Budget Package (todo en un libro)", "", _Archivo("v13.xlsx", datos), ADMIN)
    resp = await api.descargar_libro(r["id"])
    assert resp.body == datos
    assert 'filename="v13.xlsx"' in resp.headers["content-disposition"]
    bp = await api.budget_package()
    assert bp["existe"] and bp["id"] == r["id"]


@pytest.mark.asyncio
async def test_reemplazar_deja_una_sola_anterior(api):
    t = "Mi libro"
    a = await api.subir_libro(t, "", _Archivo("a.xlsx", _xlsx(b"a")), ADMIN)
    await api.subir_libro(t, "", _Archivo("b.xlsx", _xlsx(b"b")), ADMIN)
    c = await api.subir_libro(t, "", _Archivo("c.xlsx", _xlsx(b"c")), ADMIN)
    assert c["id"] == a["id"]                      # sigue siendo UN libro
    assert c["nombre_archivo"] == "c.xlsx"
    assert c["anterior"]["nombre_archivo"] == "b.xlsx"   # «a» ya no está
    assert len(await api.listar_libros()) == 1
    assert (await api.descargar_anterior(c["id"])).body == _xlsx(b"b")


@pytest.mark.asyncio
async def test_volver_a_la_anterior(api):
    t = "Mi libro"
    await api.subir_libro(t, "", _Archivo("a.xlsx", _xlsx(b"a")), ADMIN)
    b = await api.subir_libro(t, "", _Archivo("b.xlsx", _xlsx(b"b")), ADMIN)
    r = await api.volver_a_anterior(b["id"], ADMIN)
    assert r["nombre_archivo"] == "a.xlsx" and r["anterior"]["nombre_archivo"] == "b.xlsx"
    assert (await api.descargar_libro(b["id"])).body == _xlsx(b"a")


@pytest.mark.asyncio
async def test_entra_cualquier_archivo_y_sale_como_descarga(api):
    """Owner, 2026-11-26: «que acepte todo tipo de archivos». Word, PDF, lo que sea;
    pero siempre se entrega como descarga y con nosniff (nunca se abre en la app)."""
    w = await api.subir_libro("Resumen Ejecutivo budget 2027", "", _Archivo("Resumen.docx", b"PKword"), ADMIN)
    resp = await api.descargar_libro(w["id"])
    assert resp.body == b"PKword"
    assert "wordprocessingml" in resp.media_type
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["x-content-type-options"] == "nosniff"
    p = await api.subir_libro("Informe", "", _Archivo("informe.pdf", b"%PDF-1.7"), ADMIN)
    assert (await api.descargar_libro(p["id"])).media_type == "application/pdf"
    h = await api.subir_libro("Pagina", "", _Archivo("x.html", b"<script>alert(1)</script>"), ADMIN)
    rh = await api.descargar_libro(h["id"])
    assert rh.headers["content-disposition"].startswith("attachment")


@pytest.mark.asyncio
async def test_no_entra_vacio_ni_sin_nombre(api):
    from app.errores import ErrorApi
    with pytest.raises(ErrorApi):
        await api.subir_libro("x", "", _Archivo("x.pdf", b""), ADMIN)
    with pytest.raises(ErrorApi):
        await api.subir_libro("   ", "", _Archivo("x.xlsx", _xlsx(b"x")), ADMIN)


@pytest.mark.asyncio
async def test_quitar(api):
    r = await api.subir_libro("Borrar", "", _Archivo("x.xlsx", _xlsx(b"x")), ADMIN)
    await api.quitar_libro(r["id"], ADMIN)
    assert await api.listar_libros() == []


def test_subir_y_quitar_son_solo_admin():
    import inspect
    from app.api import libros_colgados_api as mod
    for fn in (mod.subir_libro, mod.volver_a_anterior, mod.quitar_libro):
        assert "get_current_admin" in inspect.getsource(fn)


# ── Los sub-tabs (carpetas) ───────────────────────────────────────────────────
# Owner, 2026-11-24: «podemos crear sub tabs acá… ya si no se mezclan» y «es un
# mismo repositorio solo que organizado por estos sub tabs».

@pytest.mark.asyncio
async def test_el_libro_queda_en_la_carpeta_que_se_eligio(api):
    r = await api.subir_libro("Cierre octubre", "", _Archivo("o.xlsx", _xlsx(b"o")),
                              ADMIN, "CIERRE")
    assert r["carpeta"] == "CIERRE"
    assert (await api.listar_libros())[0]["carpeta"] == "CIERRE"


@pytest.mark.asyncio
async def test_sin_carpeta_cae_en_otros(api):
    """Los que ya estaban subidos no tienen carpeta: no pueden desaparecer."""
    r = await api.subir_libro("Viejo", "", _Archivo("v.xlsx", _xlsx(b"v")), ADMIN)
    assert r["carpeta"] == "OTROS"


@pytest.mark.asyncio
async def test_una_carpeta_desconocida_no_pierde_la_subida(api):
    r = await api.subir_libro("Raro", "", _Archivo("r.xlsx", _xlsx(b"r")), ADMIN, "INVENTADA")
    assert r["carpeta"] == "OTROS"      # se clasifica solo, no rebota


@pytest.mark.asyncio
async def test_mover_de_carpeta_no_toca_el_archivo(api):
    datos = _xlsx(b"m")
    r = await api.subir_libro("Forecast nov", "", _Archivo("f.xlsx", datos), ADMIN, "OTROS")
    m = await api.mover_libro(r["id"], "FORECAST", ADMIN)
    assert m["id"] == r["id"] and m["carpeta"] == "FORECAST"
    assert (await api.descargar_libro(r["id"])).body == datos   # byte por byte
    assert len(await api.listar_libros()) == 1                  # no se clonó


@pytest.mark.asyncio
async def test_mover_a_una_carpeta_que_no_existe_rebota(api):
    from app.errores import ErrorApi
    r = await api.subir_libro("X", "", _Archivo("x.xlsx", _xlsx(b"x")), ADMIN)
    with pytest.raises(ErrorApi):
        await api.mover_libro(r["id"], "NO_EXISTE", ADMIN)


@pytest.mark.asyncio
async def test_el_titulo_sigue_siendo_la_llave_entre_carpetas(api):
    """Un mismo nombre en dos tabs NO son dos libros: el repositorio es uno."""
    a = await api.subir_libro("Cierre octubre", "", _Archivo("a.xlsx", _xlsx(b"a")),
                              ADMIN, "CIERRE")
    b = await api.subir_libro("Cierre octubre", "", _Archivo("b.xlsx", _xlsx(b"b")),
                              ADMIN, "BUDGET")
    assert b["id"] == a["id"]
    assert len(await api.listar_libros()) == 1
    # Y se queda donde estaba: reemplazar un archivo no lo cambia de tab.
    assert b["carpeta"] == "CIERRE"


@pytest.mark.asyncio
async def test_las_cuatro_carpetas_salen_siempre_aunque_esten_vacias(api):
    await api.subir_libro("Uno", "", _Archivo("u.xlsx", _xlsx(b"u")), ADMIN, "CIERRE")
    cs = await api.listar_carpetas()
    assert [c["clave"] for c in cs] == ["CIERRE", "BUDGET", "FORECAST", "OTROS"]
    assert {c["clave"]: c["libros"] for c in cs} == {
        "CIERRE": 1, "BUDGET": 0, "FORECAST": 0, "OTROS": 0}


@pytest.mark.asyncio
async def test_el_budget_package_sigue_siendo_el_del_boton_este_donde_este(api):
    r = await api.subir_libro("Budget Package (todo en un libro)", "",
                              _Archivo("bp.xlsx", _xlsx(b"bp")), ADMIN, "CIERRE")
    bp = await api.budget_package()
    assert bp["existe"] and bp["id"] == r["id"]


def test_mover_es_solo_admin():
    import inspect
    from app.api import libros_colgados_api as mod
    assert "get_current_admin" in inspect.getsource(mod.mover_libro)
