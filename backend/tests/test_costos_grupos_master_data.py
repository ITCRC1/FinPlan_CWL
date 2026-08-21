# -*- coding: utf-8 -*-
"""MASTER DATA — sub-tab 3 de `COSTOS_GRUPOS.md` §5, pedido del owner.

*«Dame ese tab, será MI RESUMEN»* · *«toda la información está en FinPlan»* ·
*«sólo 2, lado a lado, para ver Budget y Actual y Forecast»*.

Lo que se vigila acá es lo que puede salir mal **en silencio**: que la baja se
derive bien, que la planilla no se deduzca del número de cuenta, que un
escenario vacío no tumbe media pantalla, y que la divergencia de temporadas
contra el Excel del owner se DIGA.
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import costos_grupos_master_api as md
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── La puerta ────────────────────────────────────────────────────────────────

def test_la_ruta_existe_y_pide_token(cliente):
    rutas = cliente.app.openapi()["paths"]
    assert "/api/costos-grupos/master-data/" in rutas
    assert set(rutas["/api/costos-grupos/master-data/"]) == {"get"}
    assert cliente.get("/api/costos-grupos/master-data/?a=x").status_code in (401, 403)


def test_es_una_vista_DERIVADA_no_acepta_entradas(cliente):
    """§5: «Es una vista derivada: no acepta entradas ni recalcula por su
    cuenta». Si mañana aparece un POST acá, algo se está guardando."""
    assert set(cliente.app.openapi()["paths"]["/api/costos-grupos/master-data/"]) == {"get"}
    fuente = inspect.getsource(md)
    for escribe in ("db.add", "commit(", "delete("):
        assert escribe not in fuente, escribe


# ── Las columnas de temporada ────────────────────────────────────────────────

def test_son_DOS_escenarios_no_tres(cliente):
    """El owner pidió dos lado a lado."""
    # ⚠️ `token` y `authorization` los agrega la dependencia de sesión; los de
    # la pantalla son los que van en la query.
    params = {p["name"] for p in
              cliente.app.openapi()["paths"]["/api/costos-grupos/master-data/"]["get"]["parameters"]
              if p.get("in") == "query" and p["name"] not in ("token", "authorization")}
    assert params == {"a", "b"}


def test_las_columnas_SALEN_DE_cfg_temporadas_y_no_de_una_lista():
    """Owner, 2026-08-20: «sólo mapeá tus datos, y demos esos como válidos». Las
    columnas son las temporadas que existan — una lista escrita a mano dejaría
    afuera la que alguien agregue, **y el año seguiría cuadrando**: el gasto
    estaría en el total y en ninguna columna."""
    fuente = inspect.getsource(md.master_data)
    assert "cargar_temporadas" in fuente
    assert "columnas_clave = tuple(vistas)" in fuente


def test_el_ANIO_es_la_SUMA_de_los_meses_y_no_una_pasada_aparte():
    """⚠️ Antes el año se calculaba con una pasada propia del GL y la baja se
    derivaba restando. Sumando los doce, el total pasa a ser un CONTROL: si no
    cierra contra el P&L, se ve."""
    fuente = inspect.getsource(md._bloques_de_costo)
    assert "acumular(base, por_col[ANIO])" in fuente
    assert "construir(db, sc, 0)" not in fuente


def test_un_mes_SIN_TEMPORADA_entra_al_ano_igual():
    """⚠️ Descartarlo lo haría desaparecer del total sin que nada avise, y el
    año dejaría de cuadrar contra el P&L. Entra al año, no a ninguna columna,
    y la respuesta lo lista."""
    assert "fuera[ANIO] += v" in inspect.getsource(md._por_temporada)
    assert "meses_sin_temporada" in inspect.getsource(md.master_data)


COLS = ("ALTA", "BAJA", md.ANIO)


def test_un_escenario_VACIO_no_tumba_la_pantalla():
    """⚠️ Denominador cero devuelve CERO, no una excepción: media pantalla son
    ratios, y un escenario nuevo tiene todo en cero."""
    cero = {k: Decimal("0") for k in COLS}
    r = md._div({k: Decimal("100") for k in COLS}, cero, COLS)
    assert all(v == Decimal("0") for v in r.values())


def test_los_totales_suman_las_filas_columna_por_columna():
    filas = [md._fila("a", {"ALTA": Decimal("10"), "BAJA": Decimal("5"),
                            md.ANIO: Decimal("15")}, COLS),
             md._fila("b", {"ALTA": Decimal("1"), "BAJA": Decimal("2"),
                            md.ANIO: Decimal("3")}, COLS)]
    t = md._total(filas, COLS)
    assert t["valores"]["ALTA"] == "11"
    assert t["valores"]["BAJA"] == "7"
    assert t["valores"][md.ANIO] == "18"
    assert t["es_total"] is True


def test_por_temporada_reparte_cada_mes_a_SU_columna():
    meses = [SimpleNamespace(mes=1, v=Decimal("10")),
             SimpleNamespace(mes=9, v=Decimal("4")),
             SimpleNamespace(mes=7, v=Decimal("1"))]      # julio sin temporada
    r = md._por_temporada(meses, {1: "ALTA", 9: "BAJA"}, COLS, lambda m: m.v)
    assert r["ALTA"] == Decimal("10")
    assert r["BAJA"] == Decimal("4")
    assert r[md.ANIO] == Decimal("15"), "el mes sin temporada se perdió del año"


# ── El corte planilla / opex / costo de venta ────────────────────────────────

def test_la_PLANILLA_no_se_deduce_del_NUMERO_DE_CUENTA():
    """⚠️ **El atajo que habría estado mal.** El P&L junta planilla y opex en la
    línea departamental, y lo obvio sería cortar por el dígito de la cuenta
    (6 = planilla, 7 = opex). Medido sobre las 612 reglas de Break-Even: hay
    cuentas `6xxxx` clasificadas `OPERATING EXPENSES` y otras `PAYROLL`. Por
    dígito, la planilla saldría inflada.
    """
    import csv
    import pathlib

    seed = (pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data"
            / "CWL" / "break_even" / "be_classification_seed.csv")
    filas = list(csv.DictReader(seed.open(encoding="utf-8")))
    seis = {r["be_section"] for r in filas
            if r["account"].startswith("6") and r["be_section"]}
    assert seis == {"PAYROLL", "OPERATING EXPENSES"}, (
        "si esto queda en una sola sección, el atajo por dígito sería válido "
        "y este cuidado sobra — pero hoy no lo es")

    # Y el código va por la tabla, no por el dígito.
    fuente = inspect.getsource(md._secciones_por_cuenta)
    assert "BeCostClassification" in fuente
    assert "be_section" in fuente


def test_comparte_criterio_con_BREAK_EVEN_y_no_crea_otra_clasificacion():
    """El spec §5 lo pide explícito. Dos clasificaciones distintas del mismo
    gasto es cómo dos pantallas terminan contando cosas distintas del mismo
    hotel."""
    fuente = inspect.getsource(md)
    assert "from app.models.break_even import BeCostClassification" in fuente
    # ⚠️ Y NO se usa `cfg_clasificacion_costos`, que hoy no la lee nadie.
    assert "CfgClasificacionCosto" not in fuente


def test_solo_entran_las_tres_secciones_que_el_excel_separa():
    fuente = inspect.getsource(md._bloques_de_costo)
    assert "sec not in (SECCION_COS, SECCION_PLANILLA, SECCION_OPEX)" in fuente
    assert md.SECCION_PLANILLA == "PAYROLL"


def test_los_que_REPARTEN_quedan_fuera():
    """Cafetería y Lavandería reparten todo su costo y netean cero: contarlos
    acá sería contar dos veces el mismo gasto."""
    assert "f.reparte" in inspect.getsource(md._bloques_de_costo)


# ── La divergencia con el Excel del owner ────────────────────────────────────

def test_la_respuesta_dice_QUE_MESES_entran_en_cada_columna():
    """Es lo único que hace falta para leer la pantalla, y evita tener que
    abrir `cfg_temporadas` para saberlo."""
    assert "meses_por_columna" in inspect.getsource(md.master_data)


def test_NO_se_toca_cfg_temporadas_para_que_cuadre():
    """⚠️ Mover noviembre haría cuadrar la hoja **y movería los Pisos y la
    Golden Rate**, que están en uso para negociar. La tabla se lee, nunca se
    escribe desde acá."""
    fuente = inspect.getsource(md)
    assert "cargar_temporadas" in fuente
    assert "CfgTemporada(" not in fuente


def test_no_se_agrupa_MEDIA_dentro_de_BAJA_para_imitar_el_excel():
    """Owner: «sólo mapeá tus datos». Forzar el corte en dos del Excel sería
    inventar una agrupación que FinPlan no tiene."""
    assert "meses_alta" not in inspect.getsource(md)


# ── Los ocho bloques ─────────────────────────────────────────────────────────

def test_estan_los_OCHO_bloques_del_excel():
    fuente = inspect.getsource(md._columna)
    for clave in ("operacion", "ingresos", "costo_venta", "planilla", "opex",
                  "overhead", "no_operativo", "ratios"):
        assert f'"clave": "{clave}"' in fuente, clave


def test_los_departamentos_van_en_el_ORDEN_DEL_EXCEL():
    """No alfabético ni el del catálogo: es el lenguaje con el que el owner lee
    su hoja. ⚠️ Pero es sólo el ORDEN: lo que no está en su hoja sale detrás,
    nunca afuera — ver `test_el_ORDEN_del_owner_manda_pero_no_ESCONDE`."""
    nombres = [md.NOMBRE_DEPTO[c] for c in md.ORDEN_DEL_OWNER]
    assert nombres == ["Rooms", "F&B", "Spa", "Tours y Actividades",
                       "Transporte", "Retail - Gift Shop", "Laundry",
                       "Sustainability Fee"]


def test_el_bloque_7_sale_LINEA_POR_LINEA_del_PL():
    """⚠️ Antes era un solo total, porque el motor DESCARTABA las líneas de
    abajo del GOP. Ahora las guarda y acá se leen una por una — que es como
    está en la hoja del owner."""
    from app.engine.costos_grupos import MesDeCostos

    assert "otras_lineas" in MesDeCostos.__dataclass_fields__
    assert "m.otras_lineas.get(c, ZERO)" in inspect.getsource(md._columna)
    assert [c for c, _n in md.NO_OPERATIVO] == [
        "MGMT_FEE_3", "RENT", "PROPERTY_INSURANCE", "OTHER_EXPENSES",
        "CAPITAL_RESERVE", "LARGE_CAPEX"]


def test_el_TOTAL_del_bloque_7_no_se_arma_sumando_lo_que_conozco():
    """⚠️ **El defecto que esto evita.** El total sale de
    `TOTAL_NON_OP_EXPENSES` del P&L. Si sumara sólo las seis líneas nombradas,
    cualquier concepto abajo del GOP que no esté en la lista **desaparecería sin
    dejar rastro** — y el bloque se vería completo. La diferencia se muestra
    como una fila propia."""
    fuente = inspect.getsource(md._columna)
    assert "sumar(lambda m: m.no_operativo)" in fuente
    assert "Otros conceptos abajo del GOP" in fuente


# ── «¿Qué está fuera?» — owner, 2026-08-20 ──────────────────────────────────

def test_la_lista_de_departamentos_NO_SE_ESCRIBE_A_MANO():
    """⚠️ **Este proyecto ya pagó por una lista a mano.** El Club Madresal
    desaparecía del P&L porque el motor tenía una lista de cinco departamentos
    escrita a mano y el Club no estaba: no fallaba, no había error en los logs,
    su ingreso simplemente no existía. Se arregló DERIVANDO la lista, y acá se
    hace igual.

    Medido el 2026-08-20 con la lista a mano: el cuadro mostraba **8 de las 15
    líneas `REV_`**, así que su TOTAL no era el ingreso del hotel.
    """
    assert not hasattr(md, "DEPARTAMENTOS"), "volvió la lista escrita a mano"
    fuente = inspect.getsource(md._departamentos)
    assert "m.revenue_por_dept" in fuente, "la lista no sale del dato"


def test_sale_TODO_lo_que_tenga_linea_de_ingreso():
    meses = [SimpleNamespace(revenue_por_dept={
        "REV_ROOMS": 1, "REV_TIENDA": 2, "REV_CLUB": 3, "REV_LO_QUE_VENGA": 4})]
    codigos = [c for c, _s, _n in md._departamentos(meses, {})]
    assert set(codigos) == {"REV_ROOMS", "REV_TIENDA", "REV_CLUB",
                            "REV_LO_QUE_VENGA"}


def test_la_TIENDA_no_es_el_RETAIL():
    """⚠️ Son dos locales distintos (decisión del owner, 11-ago). Con la lista a
    mano estaba el Gift Shop y faltaba la Tienda."""
    assert md.NOMBRE_DEPTO["REV_TIENDA"] == "Tienda"
    assert md.NOMBRE_DEPTO["REV_RETAIL"] != md.NOMBRE_DEPTO["REV_TIENDA"]
    assert "REV_TIENDA" not in md.ORDEN_DEL_OWNER, (
        "no estaba en su hoja; sale igual, detrás")


def test_el_ORDEN_del_owner_manda_pero_no_ESCONDE():
    """El orden es una preferencia; la lista es un hecho. Lo que no está en su
    hoja sale detrás, nunca afuera."""
    meses = [SimpleNamespace(revenue_por_dept={
        "REV_TIENDA": 1, "REV_ROOMS": 2, "REV_FB": 3})]
    codigos = [c for c, _s, _n in md._departamentos(meses, {})]
    assert codigos == ["REV_ROOMS", "REV_FB", "REV_TIENDA"]


def test_una_linea_SIN_NOMBRE_sale_con_su_codigo_y_no_se_oculta():
    meses = [SimpleNamespace(revenue_por_dept={"REV_NUEVO_DEPTO": 1})]
    assert md._departamentos(meses, {})[0][2] == "REV_NUEVO_DEPTO"


def test_el_puente_linea_DEPARTAMENTO_sale_del_mapeo():
    """⚠️ El `slug` conecta el ingreso con el costo del GL. Si saliera de un
    diccionario escrito acá, un departamento nuevo mostraría ingreso y costo en
    cero — y un cero se lee como «no cuesta nada»."""
    assert "depto_de_linea" in inspect.getsource(md._bloques_de_costo)
    assert "base.depto_de_linea" in inspect.getsource(md._bloques_de_costo)


def test_el_TOTAL_se_CONTROLA_contra_el_PL():
    """⚠️ **El control que faltaba.** Si el cuadro se deja una línea afuera, su
    total parece el ingreso del hotel y no lo es. Ahora se compara contra
    `TOTAL_REVENUES` y la diferencia se muestra como fila."""
    from app.engine.costos_grupos import MesDeCostos

    assert "total_revenue_pl" in MesDeCostos.__dataclass_fields__
    fuente = inspect.getsource(md._columna)
    assert "m.total_revenue_pl" in fuente
    assert "que este cuadro NO muestra" in fuente


def test_los_RATIOS_dividen_por_el_ingreso_del_PL():
    """⚠️ Si dividieran por la suma del cuadro y el cuadro se dejó una línea
    afuera, todos los porcentajes saldrían inflados sin que nada avise."""
    fuente = inspect.getsource(md._columna)
    assert "rev_total = total_pl" in fuente
