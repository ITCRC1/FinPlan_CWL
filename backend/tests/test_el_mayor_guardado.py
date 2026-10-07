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
    """Una base en memoria con las dos tablas del mayor, sin PostgreSQL.

    Las DOS, porque guardar un mes archiva la version anterior: con una sola el
    guardado revienta, y ese es justamente el camino que se prueba.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.mayor_movimiento import MayorMovimiento, MayorMovimientoPrevio

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        await c.run_sync(lambda s: MayorMovimiento.__table__.create(s))
        await c.run_sync(lambda s: MayorMovimientoPrevio.__table__.create(s))
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


# ── Un export que repite la misma linea en varias hojas ──────────────────────

def test_la_linea_repetida_en_otra_hoja_no_se_cuenta_dos_veces():
    """`Full Detail P&L September 2026.xlsx` (owner, 2026-10-06) trae TRES hojas
    —`Detalle`, `Detalle (2)`, `Detalle (3)`— y las dos ultimas estan contenidas
    enteras en la primera: no aportan ni una linea nueva.

    Concatenandolas salian 8.852 lineas donde hay 4.565, y el debito del mes daba
    1.092 millones de colones en vez de 815 — **277 millones contados dos y tres
    veces**. No fallaba nada: la auditoria corria y daba hallazgos reales, solo
    que sobre un libro inflado.

    Se prueba con un libro armado a mano —dos hojas, la segunda repitiendo una
    linea de la primera— para que la prueba no dependa de un archivo que vive en
    la carpeta de descargas del owner.
    """
    import io

    from openpyxl import Workbook

    from app.importers.balance_comprobacion import leer

    wb = Workbook()
    h1 = wb.active
    h1.title = "Detalle"
    h1.append(["Balance de Comprobación"])
    h1.append(["Setiembre - 2026"])
    h1.append(["Moneda: DOL"])
    fila_a = ["7310-0110-001-000-000-00-00", "1083", "8", "30/09/26",
              "Distribución gasto Lavandería", "Allocation LN Septiembre",
              "FIJ", "", "", "", "", 453.0, "DOL", 1207.84, 0.0]
    fila_b = ["7310-0110-001-000-000-00-00", "1085", "8", "30/09/26",
              "Ajuste", "Allocation LN Septiembre Ajuste",
              "FIJ", "", "", "", "", 453.0, "DOL", 96.65, 0.0]
    h1.append(fila_a)
    h1.append(fila_b)
    h2 = wb.create_sheet("Detalle (2)")
    h2.append(fila_a)                      # la MISMA linea, otra vez

    buf = io.BytesIO()
    wb.save(buf)
    a = leer(buf.getvalue())

    assert len(a.lineas) == 2, [l.asiento for l in a.lineas]
    assert a.repetidas == 1
    assert sum(l.debito for l in a.lineas) == pytest.approx(1304.49)


def test_dos_lineas_distintas_del_MISMO_asiento_se_quedan_las_dos():
    """La llave lleva el numero de linea: un asiento con dos renglones de la
    misma cuenta son dos movimientos, no una repeticion.

    Sin esto, el arreglo de arriba borraria plata de verdad — que seria peor que
    el defecto que viene a arreglar.
    """
    import io

    from openpyxl import Workbook

    from app.importers.balance_comprobacion import leer

    wb = Workbook()
    h = wb.active
    h.title = "Detalle"
    h.append(["Balance de Comprobación"])
    h.append(["Setiembre - 2026"])
    for linea, monto in (("1", 100.0), ("2", 250.0)):
        h.append(["7400-0120-800-000-000-00-00", "900", linea, "15/09/26",
                  "Compra", "Factura 55", "CON", "", "", "", "", 453.0, "DOL",
                  monto, 0.0])
    buf = io.BytesIO()
    wb.save(buf)
    a = leer(buf.getvalue())

    assert len(a.lineas) == 2
    assert a.repetidas == 0
    assert sum(l.debito for l in a.lineas) == pytest.approx(350.0)


# ── El mismo balance, en colones o en dolares ────────────────────────────────

def _linea(moneda_archivo: str, monto: float, tc: float = 450.0):
    from app.importers.balance_comprobacion import Linea

    return Linea(
        cuenta="7400-0120-800-000-000-00-00", seg1="7400", seg2="0120",
        seg3="800", asiento="900", linea="1", fecha="15/09/26",
        descripcion="Compra", desc_asiento="Factura 55", origen="CON",
        referencia="", num_doc="", tc=tc, moneda="COL",
        debito=monto, credito=0.0, moneda_archivo=moneda_archivo)


def test_el_mismo_gasto_da_lo_mismo_venga_en_la_moneda_que_venga():
    """Owner, 2026-10-06: «¿cómo hay que subir el archivo, en colones o en USD?»

    La respuesta tiene que ser «como lo tengas», y para eso el lector mira el
    encabezado (`Moneda: DOL` / `Moneda: COL`).

    ⚠️ Antes devolvía la columna cruda y la llamaba colones. Con un export en
    dólares el monto salía rotulado CRC siendo dólares, y `monto_usd` volvía a
    dividir por el tipo de cambio: un gasto de 1.207,84 aparecía como US$2,63.
    La auditoría seguía dando los hallazgos correctos —las reglas comparan unos
    contra otros, no contra una escala— y sólo los MONTOS mentían.
    """
    en_colones = _linea("COL", 450_000.0)
    en_dolares = _linea("DOL", 1_000.0)
    assert en_colones.monto_crc == pytest.approx(en_dolares.monto_crc)
    assert en_colones.monto_usd == pytest.approx(en_dolares.monto_usd)
    assert en_dolares.monto_usd == pytest.approx(1_000.0)
    assert en_dolares.monto_crc == pytest.approx(450_000.0)


def test_sin_encabezado_se_asume_colones():
    """Lo que se asumía antes de mirar el encabezado: no se le cambia el
    significado a nadie que construya una `Linea` a mano."""
    from app.importers.balance_comprobacion import Linea

    l = Linea(cuenta="x", seg1="7400", seg2="0120", seg3="800", asiento="1",
              linea="1", fecha="", descripcion="", desc_asiento="", origen="",
              referencia="", num_doc="", tc=450.0, moneda="COL",
              debito=450_000.0, credito=0.0)
    assert l.monto_crc == pytest.approx(450_000.0)
    assert l.monto_usd == pytest.approx(1_000.0)


def test_el_encabezado_viaja_a_cada_linea():
    """El lector tiene que pasárselo: sin eso, el arreglo no hace nada."""
    import io

    from openpyxl import Workbook

    from app.importers.balance_comprobacion import leer

    wb = Workbook()
    h = wb.active
    h.title = "Detalle"
    h.append(["Balance de Comprobación"])
    h.append(["Setiembre - 2026"])
    h.append(["Moneda: DOL"])
    h.append(["7400-0120-800-000-000-00-00", "900", "1", "15/09/26", "Compra",
              "Factura 55", "CON", "", "", "", "", 450.0, "COL", 1000.0, 0.0])
    buf = io.BytesIO()
    wb.save(buf)
    a = leer(buf.getvalue())

    assert a.moneda == "DOL"
    assert a.lineas[0].moneda_archivo == "DOL"
    assert a.lineas[0].monto_usd == pytest.approx(1000.0)
    assert a.lineas[0].monto_crc == pytest.approx(450_000.0)


# ── Dos versiones: la vigente y la anterior ──────────────────────────────────
#
# Owner, 2026-10-07: «hicimos cambios en esta version… como se que cambio con
# respecto a la primera. Tendrias que guardar 2 versiones para poder comparar el
# nuevo versus el anterior y ver si los cambios quedaron».


def test_la_anterior_vive_en_OTRA_tabla():
    """⚠️ La razon de que sean dos tablas y no una columna «vigente».

    Si `mayor_movimientos` pudiera tener dos versiones del mismo mes, cualquier
    consulta que olvide filtrar la vigente contaria todo dos veces — el modo de
    falla mas caro de este sistema, porque el total cuadra consigo mismo y no hay
    error. Con la anterior aparte, ese olvido es imposible.
    """
    from app.models.mayor_movimiento import MayorMovimiento, MayorMovimientoPrevio

    assert MayorMovimiento.__tablename__ != MayorMovimientoPrevio.__tablename__
    # Y la vigente NO tiene por donde distinguir versiones: no hay nada que
    # filtrar porque no hay dos.
    cols = set(MayorMovimiento.__table__.columns.keys())
    assert not (cols & {"vigente", "version", "es_actual"})


def test_las_dos_tablas_tienen_las_MISMAS_columnas():
    """Salvo `reemplazado_en`, que es lo unico propio de la anterior.

    Si alguien le agrega una columna a una y no a la otra, la copia perderia ese
    dato en silencio.
    """
    from app.models.mayor_movimiento import MayorMovimiento, MayorMovimientoPrevio

    a = set(MayorMovimiento.__table__.columns.keys())
    b = set(MayorMovimientoPrevio.__table__.columns.keys())
    assert a - b == set(), f"le falta a la anterior: {sorted(a - b)}"
    assert b - a == {"reemplazado_en"}, f"sobra en la anterior: {sorted(b - a - {'reemplazado_en'})}"


def test_las_columnas_a_copiar_se_DERIVAN_del_modelo():
    """No una lista a mano: el dia que la vigente crezca, la copia crece con ella."""
    import inspect

    from app.models import mayor_movimiento as m

    fuente = inspect.getsource(m)
    assert "MayorMovimiento.__table__.columns.keys()" in fuente
    assert "id" not in m.COLUMNAS_A_COPIAR
    assert len(m.COLUMNAS_A_COPIAR) == len(MayorMovimientoCols := set(
        m.MayorMovimiento.__table__.columns.keys())) - 1
    assert "desc_asiento" in m.COLUMNAS_A_COPIAR


def test_se_archiva_ANTES_de_borrar():
    """El orden es lo unico que hace que la anterior exista.

    Al reves, el DELETE se lleva las filas y la copia sale vacia — y el owner se
    queda sin punto de comparacion justo cuando lo necesita.
    """
    import inspect

    fuente = inspect.getsource(auditoria_gl_api._guardar)
    i_copia = fuente.index("insert(MayorMovimientoPrevio)")
    i_borra = fuente.index("sa_delete(MayorMovimiento)")
    assert i_copia < i_borra, "se borra la vigente antes de copiarla"


@pytest.mark.asyncio
async def test_la_primera_subida_lo_DICE_en_vez_de_decir_que_no_cambio_nada(base):
    """«Sin subida anterior» y «no cambio nada» son dos cosas distintas."""
    await auditoria_gl_api._guardar(
        base, _archivo("Setiembre - 2026", 3), b"a", "v1.xlsx", "yo")
    c = await auditoria_gl_api.cambios(2026, 9, umbral=0.005, limite=400,
                                       db=base, _=object())
    assert c["hay"] is False
    assert c["motivo"] == "sin_subida_anterior"


@pytest.mark.asyncio
async def test_una_reclasificacion_sale_en_las_DOS_cuentas(base):
    """El caso que el owner quiere verificar: moví plata de cuenta, ¿quedó?

    Tiene que verse en la de origen y en la de destino, con signo opuesto. Verlo
    en los dos lados es la prueba de que la reclasificacion entro; verlo en uno
    solo no distingue un movimiento borrado de uno movido.
    """
    from app.importers.balance_comprobacion import Archivo, Linea

    def uno(cuenta, seg1, monto):
        return Linea(cuenta=cuenta, seg1=seg1, seg2="0120", seg3="800",
                     asiento="567", linea="5", fecha="08/09/26",
                     descripcion="BLUETECH", desc_asiento="CXP Compras",
                     origen="CXP", referencia="", num_doc="", tc=453.0,
                     moneda="COL", debito=monto, credito=0.0)

    v1 = Archivo(periodo="Setiembre - 2026",
                 lineas=[uno("7140-0120-800-000-000-00-00", "7140", 88.55)])
    v2 = Archivo(periodo="Setiembre - 2026",
                 lineas=[uno("7065-0120-800-000-000-00-00", "7065", 88.55)])
    await auditoria_gl_api._guardar(base, v1, b"a", "v1.xlsx", "yo")
    await auditoria_gl_api._guardar(base, v2, b"b", "v2.xlsx", "yo")
    c = await auditoria_gl_api.cambios(2026, 9, umbral=0.005, limite=400,
                                       db=base, _=object())
    assert c["hay"] is True
    por = {x["cuenta"]: x["diferencia"] for x in c["cuentas"]}
    assert por["7140-0120-800-000-000-00-00"] == pytest.approx(-88.55)
    assert por["7065-0120-800-000-000-00-00"] == pytest.approx(88.55)
    ques = {x["que"] for x in c["movimientos"]}
    assert ques == {"aparecio", "desaparecio"}


@pytest.mark.asyncio
async def test_la_tercera_subida_compara_contra_la_SEGUNDA(base):
    """Se guarda UNA anterior: la inmediata. Es a proposito — un historial
    traeria la pregunta de cual era la buena."""
    for v in ("v1", "v2", "v3"):
        await auditoria_gl_api._guardar(
            base, _archivo("Setiembre - 2026", 2), v.encode(), f"{v}.xlsx", "yo")
    c = await auditoria_gl_api.cambios(2026, 9, umbral=0.005, limite=400,
                                       db=base, _=object())
    assert c["anterior"]["archivo"] == "v2.xlsx"
    assert c["vigente"]["archivo"] == "v3.xlsx"


@pytest.mark.asyncio
async def test_subir_el_mismo_archivo_dos_veces_no_reporta_cambios(base):
    """El control de que la comparacion no invente diferencias."""
    a = _archivo("Setiembre - 2026", 4)
    await auditoria_gl_api._guardar(base, a, b"x", "v1.xlsx", "yo")
    await auditoria_gl_api._guardar(base, a, b"x", "v2.xlsx", "yo")
    c = await auditoria_gl_api.cambios(2026, 9, umbral=0.005, limite=400,
                                       db=base, _=object())
    assert c["hay"] is True
    assert c["cuentas_que_cambiaron"] == 0
    assert c["movimientos_que_cambiaron"] == 0
    assert c["diferencia"]["debito"] == pytest.approx(0.0)
