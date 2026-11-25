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
async def test_solo_entra_un_excel(api):
    from app.errores import ErrorApi
    with pytest.raises(ErrorApi):
        await api.subir_libro("x", "", _Archivo("x.xlsx", b"no soy zip"), ADMIN)
    with pytest.raises(ErrorApi):
        await api.subir_libro("x", "", _Archivo("x.pdf", _xlsx(b"x")), ADMIN)
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
