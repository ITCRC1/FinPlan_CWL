# -*- coding: utf-8 -*-
"""El mayor guardado: uno por mes, y el que sube le cae encima.

Owner, 2026-10-06: *«me gustaría que quede guardado pero cada vez que se corra
se le caiga encima […] es solo para poder revisar detalladamente a nivel de
detalle»* · *«dale, máximo detalle y descripción del asiento»*.

Hasta ese día el Balance de Comprobación entraba, se revisaba y se iba. Guardarlo
cambia dos cosas que hay que vigilar, y son las de acá:

1. **El mes sale del archivo**, y si no se entiende NO se guarda. Adivinar
   dejaría los asientos de setiembre bajo otro mes, y después no hay forma de
   darse cuenta: el mes bueno se queda sin su libro y el malo muestra asientos
   que no son suyos.
2. **Subir el mismo mes reemplaza**, no acumula. Sin eso, tres vueltas del mismo
   mes —que es lo normal cuando corrigen un posteo— dejarían el triple de
   asientos y cualquier suma daría el triple.
"""
import inspect
import pathlib

import pytest
import pytest_asyncio

from app.api import auditoria_gl_api
from app.importers.balance_comprobacion import Archivo, _anio_mes


# ── El mes sale del archivo, o no se guarda ──────────────────────────────────

@pytest.mark.parametrize("periodo,esperado", [
    # El archivo del owner dice «Setiembre»; el castellano general,
    # «Septiembre». Las DOS tienen que valer o se pierde el libro de un mes
    # entero por una letra.
    ("Setiembre - 2026", (2026, 9)),
    ("Septiembre - 2026", (2026, 9)),
    ("September - 2026", (2026, 9)),
    ("Agosto - 2025", (2025, 8)),
    ("Diciembre - 2026", (2026, 12)),
    ("  enero - 2027  ", (2027, 1)),
])
def test_entiende_el_periodo(periodo, esperado):
    assert _anio_mes(periodo) == esperado


@pytest.mark.parametrize("periodo", ["", "basura", "Marzo", "2026", "- 2026"])
def test_lo_que_no_entiende_NO_lo_adivina(periodo):
    """Sin año o sin mes devuelve None. No hay «mes por defecto»."""
    assert _anio_mes(periodo) is None


@pytest.mark.asyncio
async def test_sin_periodo_no_escribe_nada():
    """El caso peligroso: un archivo cuyo encabezado no se entiende.

    Se comprueba que NO se toca la base — ni un DELETE— y que la respuesta lo
    dice. Un `db` que explota si alguien lo usa es la forma de probarlo.
    """
    class _DbQueNoSeDebeTocar:
        async def execute(self, *a, **k):   # pragma: no cover - debe no llamarse
            raise AssertionError("tocó la base sin saber de qué mes es el archivo")
        def add(self, *a, **k):             # pragma: no cover
            raise AssertionError("insertó sin saber de qué mes es el archivo")
        async def commit(self):             # pragma: no cover
            raise AssertionError("hizo commit sin saber de qué mes es el archivo")

    leido = Archivo(periodo="un encabezado raro")
    r = await auditoria_gl_api._guardar(
        _DbQueNoSeDebeTocar(), leido, b"", "x.xlsx", "yo@test.com")
    assert r["guardado"] is False
    assert r["motivo"] == "periodo_no_entendido"


# ── Le cae encima, no se acumula ─────────────────────────────────────────────

def test_borra_el_mes_ANTES_de_insertarlo():
    """El reemplazo es un DELETE del mes y después el INSERT, en ese orden.

    Mira el código porque lo que importa es el ORDEN, y el orden no se ve
    llamando a la función sin una base. Sin el DELETE, tres vueltas del mismo
    mes dejan el triple de asientos y cualquier suma da el triple.
    """
    fuente = inspect.getsource(auditoria_gl_api._guardar)
    i_del = fuente.index("sa_delete(MayorMovimiento)")
    i_add = fuente.index("db.add(MayorMovimiento(")
    assert i_del < i_add
    # Y el DELETE va acotado a ESE mes de ESE hotel: sin las tres condiciones,
    # guardar octubre se llevaría setiembre por delante.
    recorte = fuente[i_del:i_add]
    for cond in ("hotel_id == HOTEL_ID", "anio == anio", "mes == mes"):
        assert cond in recorte, f"el DELETE no filtra por {cond}"


def test_un_solo_commit():
    """O queda el mes nuevo entero, o queda el viejo entero.

    Un commit entre el DELETE y el INSERT dejaría el mes vacío si el insert
    falla — un libro contable a medias es la peor forma de fallar.
    """
    fuente = inspect.getsource(auditoria_gl_api._guardar)
    assert fuente.count("await db.commit()") == 1
    assert fuente.index("db.add(MayorMovimiento(") < fuente.index("await db.commit()")


# ── Lo que se guarda ─────────────────────────────────────────────────────────

def test_se_guarda_la_descripcion_del_ASIENTO_y_la_de_la_LINEA():
    """Owner: «máximo detalle y descripción del asiento». Son dos campos
    distintos: la línea dice qué se compró, el asiento de dónde viene."""
    from app.models.mayor_movimiento import MayorMovimiento

    cols = set(MayorMovimiento.__table__.columns.keys())
    assert {"descripcion", "desc_asiento"} <= cols


def test_se_guarda_todo_el_movimiento():
    """Los campos que hacen falta para revisar: asiento, fecha, plata y origen.

    Si alguno se cayera del modelo, la pantalla mostraría una columna vacía y
    habría que volver a subir el mes para recuperarlo.
    """
    from app.models.mayor_movimiento import MayorMovimiento

    cols = set(MayorMovimiento.__table__.columns.keys())
    faltan = {"cuenta", "seg1", "seg2", "seg3", "asiento", "linea", "fecha",
              "origen", "referencia", "num_doc", "debito", "credito", "tc",
              "moneda", "archivo", "checksum", "subido_en"} - cols
    assert not faltan, faltan


def test_no_entra_a_ningun_total():
    """Esto es el LIBRO, no una fuente de plata.

    La tabla no tiene `scenario_id` a propósito: la plata del mes entra por
    `integrity_final` → borrador → espejo → ACTUAL, y una segunda fuente es
    exactamente el defecto que este repo ya pagó varias veces.
    """
    from app.models.mayor_movimiento import MayorMovimiento

    assert "scenario_id" not in MayorMovimiento.__table__.columns.keys()


def test_la_migracion_existe_y_cuelga_de_la_anterior():
    base = pathlib.Path(__file__).resolve().parents[1]
    f = next(base.glob("alembic/versions/151_*.py"))
    texto = f.read_text(encoding="utf-8")
    assert 'revision = "151"' in texto
    assert 'down_revision = "150"' in texto
    assert "mayor_movimientos" in texto


# ── El ensayo de verdad: una base en memoria ─────────────────────────────────
#
# Lo de arriba mira el codigo; esto lo EJECUTA. Un DELETE bien escrito que no se
# ejecuta por un `autoflush` de por medio pasaria todas las pruebas anteriores —
# y es exactamente la clase de defecto que mordio este mismo dia, en otra tabla.

pytest.importorskip("aiosqlite")


@pytest_asyncio.fixture
async def base():
    """Una base en memoria con la tabla sola, sin PostgreSQL."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.mayor_movimiento import MayorMovimiento

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        await c.run_sync(lambda s: MayorMovimiento.__table__.create(s))
    hacer = async_sessionmaker(eng, expire_on_commit=False)
    async with hacer() as db:
        yield db
    await eng.dispose()


def _archivo(periodo: str, n: int) -> Archivo:
    from app.importers.balance_comprobacion import Linea

    return Archivo(periodo=periodo, lineas=[
        Linea(cuenta="7310-0110-001-000-000-00-00", seg1="7310", seg2="0110",
              seg3="001", asiento=str(1000 + i), linea="1", fecha="30/09/26",
              descripcion=f"linea {i}", desc_asiento="Allocation LN Septiembre",
              origen="CON", referencia="", num_doc="", tc=453.0, moneda="DOL",
              debito=100.0, credito=0.0)
        for i in range(n)])


async def _cuantos(db, **donde) -> int:
    from sqlalchemy import func, select

    from app.models.mayor_movimiento import MayorMovimiento

    q = select(func.count()).select_from(MayorMovimiento)
    for k, v in donde.items():
        q = q.where(getattr(MayorMovimiento, k) == v)
    return (await db.execute(q)).scalar()


@pytest.mark.asyncio
async def test_subir_el_mismo_mes_REEMPLAZA(base):
    """Lo que pidio el owner: «cada vez que se corra se le caiga encima».

    Sin esto, tres vueltas del mismo mes —lo normal cuando corrigen un posteo—
    dejarian el triple de asientos y cualquier suma daria el triple.
    """
    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2026", 5), b"a", "v1.xlsx", "yo")
    assert await _cuantos(base) == 5

    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2026", 3), b"b", "v2.xlsx", "yo")
    assert await _cuantos(base) == 3, "acumulo en vez de reemplazar"


@pytest.mark.asyncio
async def test_otro_mes_NO_toca_el_anterior(base):
    """Subir octubre no puede llevarse setiembre por delante."""
    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2026", 5), b"a", "sep.xlsx", "yo")
    await auditoria_gl_api._guardar(
        base, _archivo("Octubre - 2026", 7), b"b", "oct.xlsx", "yo")
    assert await _cuantos(base, mes=9) == 5
    assert await _cuantos(base, mes=10) == 7
    assert await _cuantos(base) == 12


@pytest.mark.asyncio
async def test_el_mismo_mes_de_OTRO_año_tampoco(base):
    """Setiembre 2025 y setiembre 2026 son dos meses distintos."""
    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2025", 4), b"a", "2025.xlsx", "yo")
    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2026", 6), b"b", "2026.xlsx", "yo")
    assert await _cuantos(base, anio=2025) == 4
    assert await _cuantos(base, anio=2026) == 6


@pytest.mark.asyncio
async def test_queda_de_que_archivo_salio(base):
    """«¿De que archivo salio este asiento?» se contesta mirando el asiento."""
    from sqlalchemy import select

    from app.models.mayor_movimiento import MayorMovimiento

    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2026", 2), b"contenido", "elbueno.xlsx", "yo@x.com")
    f = (await base.execute(select(MayorMovimiento).limit(1))).scalar_one()
    assert f.archivo == "elbueno.xlsx"
    assert f.subido_por == "yo@x.com"
    assert len(f.checksum) == 64            # sha256 del archivo
    assert f.subido_en is not None
    # Y la descripcion del asiento, que es lo que el owner pidio por su nombre.
    assert f.desc_asiento == "Allocation LN Septiembre"
