# -*- coding: utf-8 -*-
"""El USALI dentro de la aplicación.

La especificación de por qué cada cosa está donde está vive en
`app/models/usali.py` y `app/importers/usali_pdf.py`. Estas pruebas vigilan lo
que puede romperse en silencio.
"""
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.importers.usali_pdf import (SCHEDULES, Entrada, _norm, cruzar,
                                     fusionar, leer_diccionario)
from app.models.usali import UsaliDefinicion, UsaliDocumento, UsaliItem

#: El libro del owner. Las pruebas que lo necesitan se saltan si no está: el
#: texto tiene derechos y NO se versiona, así que en CI no va a existir.
LIBRO = pathlib.Path.home() / "Desktop" / "usali-659-11-digital.pdf"
hay_libro = pytest.mark.skipif(not LIBRO.exists(),
                               reason="el PDF del USALI no está en esta máquina")


# ── el parser, con texto armado a mano ──────────────────────────────────────

def _pag(texto: str):
    return [(1, texto)]


def test_lee_las_dos_formas_de_ordenar_la_misma_linea():
    """⚠️ El orden de columnas se decide por LÍNEA, no por el encabezado de la
    página. El libro cambia de sección a mitad de página —en la 266 termina la
    guía de ingresos y empieza la de gastos— y el encabezado aparece recién en
    la siguiente. Con el orden arrastrado, 1.800 entradas quedaron con el
    departamento y el artículo intercambiados sin que nada lo dijera."""
    por_cuenta = leer_diccionario(_pag(
        "Rooms ......... Linen ......... Robes"))
    por_item = leer_diccionario(_pag(
        "Robes ......... Rooms ......... Linen"))
    for e in (por_cuenta[0], por_item[0]):
        assert e.item == "Robes"
        assert e.schedule == "Rooms"
        assert e.cuenta == "Linen"


def test_una_linea_sin_departamento_conocido_NO_se_adivina():
    """Una entrada inventada es peor que una entrada que falta: la inventada se
    usa para marcarle algo a un gerente."""
    assert leer_diccionario(_pag("Algo ..... Otra cosa ..... Tercera")) == []


def test_la_continuacion_sangrada_sigue_a_la_linea_anterior():
    e = leer_diccionario(_pag(
        "F&B ..... Misc. Cost ..... Banquet/conference/catering\n"
        " recoverable supplies"))
    assert len(e) == 1
    assert e[0].item == "Banquet/conference/catering recoverable supplies"


def test_la_linea_sin_sangria_es_el_PRINCIPIO_de_la_siguiente():
    """El otro caso de renglón partido, y es al revés que el anterior: cuando el
    artículo no cupo, su principio queda en una línea sin puntos y sin sangría.
    Tratar los dos casos igual pegaba el principio de uno al final del otro."""
    e = leer_diccionario(_pag(
        "Beverage assessment (this is not other tax\n"
        "and assessment) ..... F&B ..... Cost of Beverage Sales"))
    assert len(e) == 1
    assert e[0].item.startswith("Beverage assessment")
    assert e[0].item.endswith("and assessment)")
    assert e[0].cuenta == "Cost of Beverage Sales"


def test_el_vocabulario_de_departamentos_es_cerrado():
    """Si alguien le agrega algo que no es un schedule del USALI, el parser va a
    empezar a leer artículos como departamentos."""
    assert "rooms" in SCHEDULES and "f b" in SCHEDULES
    assert len(SCHEDULES) < 40, "esto es un vocabulario chico, no un cajón"
    for s in SCHEDULES:
        assert s == _norm(s), f"«{s}» tiene que estar normalizado"


def test_la_fusion_prefiere_el_nombre_de_cuenta_COMPLETO():
    """El libro abrevia en la columna angosta —«Storage Fee Rev» contra «Storage
    Fee Revenue»—. Si ganara el abreviado, el catálogo quedaría con nombres que
    no aparean con nada."""
    e = [Entrada("Bag storage fees", "Golf/Pro Shop", "Storage Fee Rev", 1,
                 "por_item"),
         Entrada("Bag storage fees", "Golf/Pro Shop", "Storage Fee Revenue", 2,
                 "por_cuenta")]
    c = fusionar(e)
    assert len(c) == 1
    assert c[0].cuenta == "Storage Fee Revenue"
    assert c[0].confianza == "confirmado"


def test_un_articulo_puede_tener_DOS_destinos_legitimos():
    """«Apparel sales» va a F&B o a Spa según dónde se venda. Quedarse con uno
    solo perdería la mitad del catálogo sin avisar."""
    e = [Entrada("Apparel sales", "F&B", "Misc. Other Rev", 1, "por_item"),
         Entrada("Apparel sales", "Health Club/Spa", "Retail Rev", 1, "por_item")]
    c = fusionar(e)
    assert len(c) == 2
    assert {x.schedule for x in c} == {"F&B", "Health Club/Spa"}


def test_la_confianza_distingue_confirmado_de_unico():
    """⚠️ No se mezclan sin decir cuál es cuál: el día que esto marque algo, el
    hallazgo tiene que poder decir de dónde salió."""
    c = fusionar([Entrada("Cots", "Rooms", "Operating Supplies", 1, "por_item")])
    assert c[0].confianza == "unico"


def test_el_cruce_mide_lo_que_coincide():
    e = [Entrada("Cots", "Rooms", "Operating Supplies", 1, "por_item"),
         Entrada("Cots", "Rooms", "Operating Supplies", 2, "por_cuenta"),
         Entrada("Robes", "Rooms", "Linen", 3, "por_item")]
    r = cruzar(e)
    assert r["coinciden"] == 1
    assert r["solo_por_item"] == 1
    assert 0 < r["confianza"] <= 1


# ── el libro de verdad ──────────────────────────────────────────────────────

@hay_libro
def test_el_libro_del_owner_se_lee_entero():
    """La verificación que importa: el departamento tiene que coincidir en los
    dos ordenamientos. Medido sobre el libro entero el 2026-10-08: 1.651
    artículos en ambos, 100% de acuerdo en departamento."""
    from app.importers.usali_pdf import leer_pdf

    L = leer_pdf(LIBRO.read_bytes())
    assert L.paginas > 300
    assert len(L.catalogo) > 1500, "el diccionario salió corto"
    assert len(L.definiciones) > 300, "faltan las definiciones de cuenta"

    ia, ib = {}, {}
    for e in L.entradas:
        (ia if e.orden == "por_item" else ib).setdefault(
            _norm(e.item), []).append(e)
    comunes = set(ia) & set(ib)
    assert len(comunes) > 1200
    discrepan = [k for k in comunes
                 if {_norm(x.schedule) for x in ia[k]}
                 != {_norm(x.schedule) for x in ib[k]}]
    assert not discrepan, (
        f"{len(discrepan)} artículos con departamento distinto entre los dos "
        f"ordenamientos: la lectura salió mal. Ejemplos: {discrepan[:5]}")

    # Y ningún «departamento» que no sea del vocabulario.
    assert {_norm(c.schedule) for c in L.catalogo} <= SCHEDULES


# ── la tabla ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def base():
    from app.db import Base
    import app.models  # noqa: F401

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    hacer = async_sessionmaker(eng, expire_on_commit=False)
    async with hacer() as db:
        yield db
    await eng.dispose()


@pytest.mark.asyncio
async def test_la_llave_impide_el_mismo_articulo_dos_veces(base):
    """Subir dos veces no puede dejar el catálogo duplicado: una búsqueda que
    devuelve el mismo artículo dos veces se lee como dos reglas distintas."""
    import sqlalchemy.exc

    for _ in range(2):
        base.add(UsaliItem(hotel_id="X", item="Cots", item_norm="cots",
                           schedule="Rooms", cuenta="Operating Supplies"))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await base.commit()


@pytest.mark.asyncio
async def test_las_tres_tablas_existen_y_arrancan_vacias(base):
    """⚠️ El USALI NO se siembra: el texto es de AHLA/HFTP y cada instalación
    sube el suyo. Un clon tiene que arrancar sin nada."""
    for modelo in (UsaliDocumento, UsaliItem, UsaliDefinicion):
        n = (await base.execute(select(func.count()).select_from(modelo))).scalar()
        assert n == 0


def test_el_usali_no_se_siembra():
    import inspect

    from app import seed
    assert "usali" not in inspect.getsource(seed).lower()


def test_el_endpoint_de_subida_pide_ADMIN():
    """Reemplaza el catálogo entero de la propiedad: no es una lectura."""
    import inspect

    from app.api import usali_api
    assert "get_current_admin" in inspect.getsource(usali_api.subir)


def test_los_endpoints_estan_registrados_y_piden_token():
    from fastapi.testclient import TestClient

    from app.main import app
    cliente = TestClient(app, raise_server_exceptions=False)
    rutas = cliente.app.openapi()["paths"]
    for r in ("/api/usali/estado/", "/api/usali/subir/", "/api/usali/buscar/",
              "/api/usali/definicion/"):
        assert r in rutas, f"falta {r}"
    assert cliente.get("/api/usali/buscar/?q=cots").status_code in (401, 403)
    assert cliente.post("/api/usali/subir/").status_code in (401, 403, 422)


# ── el USALI como capa de explicación ───────────────────────────────────────
#
# Owner, 2026-10-08: «ok, A» — el estándar al lado de la cuenta, para leer. NO
# como regla que marca. La diferencia no es de estilo: aparear ASIENTO contra
# estándar no se puede —medido, el 98,3% de las descripciones del mayor no
# comparte una palabra con el libro, porque el mayor dice el proveedor en
# español y el libro el artículo en inglés—. Aparear NOMBRE DE CUENTA sí: el
# catálogo del hotel se armó sobre USALI y el 61,5% de las cuentas de setiembre
# 2026 tiene el nombre idéntico.


def test_el_umbral_rechaza_lo_que_no_se_parece():
    """⚠️ «Cafetería → Collateral Material» (0,57) NO se puede mostrar.

    Una referencia que acierta ahorra tiempo; una que inventa enseña a
    desconfiar de la pantalla, y eso no se recupera.
    """
    from app.api.usali_api import (UMBRAL_EXACTO, UMBRAL_PARECIDO, _parecido)

    assert _parecido("Cafeteria", "Collateral Material") < UMBRAL_PARECIDO
    assert _parecido("Massage Spa", "Management Fees") < UMBRAL_PARECIDO
    assert _parecido("Christmas bonus", "Commissions") < UMBRAL_PARECIDO
    assert UMBRAL_PARECIDO < UMBRAL_EXACTO


def test_el_umbral_acepta_la_misma_cuenta():
    from app.api.usali_api import UMBRAL_EXACTO, _parecido

    for n in ("Operating Supplies", "Water/Sewer", "Uniform Costs",
              "Payroll Processing", "Waste Removal"):
        assert _parecido(n, n) >= UMBRAL_EXACTO


def test_las_abreviaturas_del_libro_no_rompen_el_apareo():
    """El libro abrevia en la columna angosta. Sin resolverlas, dos nombres de
    la MISMA cuenta caen por debajo del umbral y la definición no se muestra."""
    from app.api.usali_api import UMBRAL_PARECIDO, _parecido

    assert _parecido("Misc. Other Rev", "Miscellaneous Other Revenue") >= UMBRAL_PARECIDO
    assert _parecido("Equip. Rental", "Equipment Rental") >= UMBRAL_PARECIDO


def test_sin_parecido_NO_devuelve_el_candidato_malo():
    """El endpoint contesta «ninguno» y deja la cuenta en nulo: la pantalla no
    puede mostrar un nombre que el servidor ya descartó."""
    import inspect

    from app.api import usali_api
    fuente = inspect.getsource(usali_api.para_cuenta)
    assert '"grado": "ninguno"' in fuente
    assert '"cuenta_usali": None' in fuente


def test_el_estandar_no_marca_nada():
    """⚠️ Es referencia, no regla. Si algún día esto empieza a generar
    hallazgos, tiene que ser una decisión tomada, no algo que se filtró."""
    import inspect

    from app.api import usali_api
    fuente = inspect.getsource(usali_api)
    for palabra in ("hallazgo", "Hallazgo", "severidad", "REGLAS"):
        assert palabra not in fuente


# ── los renglones de cada Schedule ──────────────────────────────────────────
#
# La otra mitad del libro. El diccionario da EJEMPLOS de artículos; el Schedule
# da el RENGLÓN del reporte. Es referencia del panel, no alarma, y estas pruebas
# existen para que siga siéndolo.

def test_los_catorce_schedules_salen_por_CONTENIDO():
    """Encontrarlos por número de página habría durado hasta la próxima edición.

    El cuadro se delata por su título en MAYÚSCULAS —«ROOMS—SCHEDULE 1»—, que es
    distinto de la prosa que lo explica —«Rooms—Schedule 1 reflects…»—. Medido
    sobre el libro del owner el 2026-10-09: 399 renglones en 14 schedules.
    """
    from app.importers.usali_pdf import leer_pdf

    L = leer_pdf(LIBRO.read_bytes())
    por_num = {}
    for g in L.renglones:
        por_num.setdefault(g.numero, []).append(g)
    assert sorted(por_num) == list(range(1, 15)), (
        f"faltan o sobran schedules: {sorted(por_num)}")
    assert len(L.renglones) > 350
    # Utilities es el cuadro chico y exacto: sirve de testigo.
    assert [g.renglon for g in por_num[9]] == [
        "Electricity", "Gas", "Oil", "Water/Sewer", "Steam", "Chilled Water",
        "Other Fuels", "Contract Services"]


def test_el_schedule_3_queda_SIN_lista_aprobada():
    """⚠️ La mitad útil de la respuesta.

    El Schedule 3 —Other Operated Departments— no declara lista cerrada: dice
    «only the revenues and expenses […] that exist at an individual property».
    Ahí viven el Spa, Tours, Transporte y Lavandería de esta propiedad: el 27%
    de las cuentas de setiembre 2026. Tratarlo como lista cerrada producía 13
    hallazgos y los 13 eran falsos.
    """
    from app.importers.usali_pdf import leer_pdf

    L = leer_pdf(LIBRO.read_bytes())
    por_num = {}
    for g in L.renglones:
        por_num.setdefault(g.numero, []).append(g)
    assert not any(g.lista_aprobada for g in por_num[3])
    # Y los que sí la declaran, la declaran: con una de las dos frases del
    # libro —«approved as line items» o «does not provide for the addition»—.
    for num in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
        assert all(g.lista_aprobada for g in por_num[num]), (
            f"el Schedule {num} perdió su declaración de lista cerrada")


def test_los_encabezados_del_bloque_de_planilla_NO_son_renglones():
    """Se repiten en los catorce schedules y no son cuentas.

    «Labor Costs and Related Expenses», «Management», «Non-Management» son
    rótulos de agrupación. Colarlos hacía que doce schedules tuvieran los mismos
    cuatro renglones falsos y que el cuadro no se pudiera leer.
    """
    from app.importers.usali_pdf import leer_pdf

    L = leer_pdf(LIBRO.read_bytes())
    malos = {"management", "non-management", "labor costs and related expenses",
             "other expenses", "payroll-related expenses"}
    hallados = {g.renglon.lower() for g in L.renglones} & malos
    assert not hallados, f"encabezados colados como renglones: {hallados}"


def test_la_casilla_del_diccionario_que_no_es_un_schedule_no_afirma_nada():
    """«Health Club/Spa» y «Mult. Depts» son casillas del DICCIONARIO.

    El Spa es un Other Operated Department —Schedule 3, sin lista—; «Mult.
    Depts» quiere decir «este renglón vive en varios», que no es ninguno. Si
    alguna vez se mapean a un schedule con lista cerrada, vuelven los 13 falsos.
    """
    from app.api.usali_api import SCHEDULE_DEL_DICCIONARIO

    assert SCHEDULE_DEL_DICCIONARIO["Health Club/Spa"] == 3
    assert SCHEDULE_DEL_DICCIONARIO["Minor Oper. Dept"] == 3
    assert "Mult. Depts" not in SCHEDULE_DEL_DICCIONARIO


@pytest.mark.asyncio
async def test_los_renglones_arrancan_vacios_en_un_clon(base):
    """Como las otras tres: el texto es de AHLA/HFTP y no se siembra."""
    from app.models.usali import UsaliRenglon

    n = (await base.execute(
        select(func.count()).select_from(UsaliRenglon))).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_sin_USALI_cargado_el_panel_dice_que_no_hay(base):
    """No puede contestar «este departamento no lleva nada» cuando lo que pasa
    es que nadie subió el libro. Son cosas distintas y se leen distinto."""
    from app.api.usali_api import _renglones_del_schedule

    r = await _renglones_del_schedule(base, "Rooms")
    assert r["renglones"] == []
    assert r["lista_aprobada"] is False
    assert "no hay USALI cargado" in r["motivo"]
