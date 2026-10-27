# -*- coding: utf-8 -*-
"""El acumulado YTD de Rooms Statistics: la serie que se rehacía a mano.

**El pedido (owner, 2026-10-26).** La pantalla daba el YTD del mes elegido —un
solo número— así que para ver cómo venía cayendo la ocupación y la tarifa, el
owner rehacía la serie mes a mes en Excel arrastrando la fórmula. En esa hoja
el ADR acumulado quedó corrido una columna: agosto mostraba 598,73 (que es el
de setiembre) y setiembre 591,42, que no es de ningún mes. El dato de FinPlan
estaba bien —*«los numeros de finplan en room stats son los corrctos y no los
que subo»*—; lo que fallaba era el viaje a Excel.

**Las dos trampas que esto cierra.**

1. **El ADR acumulado NO es el promedio de los ADR mensuales.** Es el ingreso
   acumulado entre las noches acumuladas. En CWL 2026 la diferencia no es
   cosmética: setiembre tuvo 35 noches a 534,09 contra 3.341 noches previas a
   599,41. Ponderando bien, el YTD baja a **598,73**; promediando los nueve
   meses daría ~**574**, y nadie sabría cuál de los dos creer.

2. **El último punto de la serie TIENE que dar el KPI de arriba.** Y el KPI
   suma distinto a propósito: noches y pax solo de las categorías con
   unidades, ingreso de TODAS —ahí vive «Other Rooms Revenue», el ingreso sin
   tipo asociado (no-show, penalidades)—. Esa plata ya desapareció callada una
   vez del KPI y del Excel. Si el acumulado sumara el ingreso solo de las
   categorías con unidades, su última columna no daría el ADR del encabezado y
   la pantalla diría dos cosas del mismo mes.
"""
import re

import pytest

from tests._rutas import FRONT, sin_comentarios

PAGINA = FRONT / "app" / "operation-insight" / "room-stats" / "page.tsx"
ES = FRONT / "messages" / "es.json"
EN = FRONT / "messages" / "en.json"


@pytest.fixture(scope="module")
def pag() -> str:
    assert PAGINA.exists(), f"no está {PAGINA}"
    return PAGINA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def codigo(pag: str) -> str:
    """El código, sin los comentarios que lo explican.

    Casi todo lo que esta prueba busca está también escrito en la prosa de
    arriba del `useMemo`. Sin esto, cada aserción acertaría en su propia
    explicación y la prueba pasaría sin haber mirado el código.
    """
    return sin_comentarios(pag)


@pytest.fixture(scope="module")
def memo(codigo: str) -> str:
    """Solo el cuerpo del `useMemo` que arma la serie."""
    i = codigo.find("const acumulado = useMemo(")
    assert i > 0, "no está el useMemo `acumulado` en la pantalla"
    j = codigo.find("}, [rs, month]);", i)
    assert j > i, "el useMemo `acumulado` no cierra con [rs, month]"
    return codigo[i:j]


# ═══════════════════════════════════════════════════════════════════════════
# 1 · La serie existe y la recalcula el mes elegido
# ═══════════════════════════════════════════════════════════════════════════
def test_la_serie_existe(codigo):
    assert "const acumulado = useMemo(" in codigo


def test_la_serie_se_rehace_al_cambiar_el_corte(memo):
    """Si `month` no fuera dependencia, mover el selector dejaría la tabla
    quieta mostrando la serie del corte anterior — y sin avisar."""
    assert "for (let m = 1; m <= month; m++)" in memo, (
        "la serie tiene que recorrer de enero al mes elegido")


def test_la_serie_sale_de_la_misma_lectura_que_la_pantalla(memo):
    """De `rs.months`, no de una llamada propia al servidor.

    `getRevenueByRoomType` ya trae el detalle de cada mes. Pedirlo aparte
    crearía una segunda fuente del mismo número.
    """
    assert "rs.months.find" in memo
    assert "fetch(" not in memo and "await " not in memo


# ═══════════════════════════════════════════════════════════════════════════
# 2 · Trampa 1: el ADR acumulado se pondera, no se promedia
# ═══════════════════════════════════════════════════════════════════════════
def test_el_adr_acumulado_es_ingreso_entre_noches(memo):
    assert "adr: no ? rev / no : 0" in memo, (
        "el ADR acumulado tiene que ser el ingreso acumulado entre las noches "
        "acumuladas")


def test_la_ocupacion_acumulada_es_noches_entre_disponibles(memo):
    assert "occ: na ? no / na : 0" in memo


def test_el_adr_acumulado_NO_promedia_los_meses(memo):
    """Promediar los nueve ADR mensuales daría ~574 donde FinPlan dice 598,73.

    No hay una sola forma de escribir el promedio, así que se descartan las
    dos que se escribirían sin pensar: dividir entre la cantidad de meses, o
    acumular los ADR de cada mes.
    """
    assert not re.search(r"/\s*(serie\.length|month\b|meses\.length)", memo), (
        "la serie no se divide entre la cantidad de meses")
    assert "adr +=" not in memo and "sumaAdr" not in memo, (
        "no se acumulan los ADR mensuales: se acumulan ingreso y noches")


def test_los_acumuladores_viven_fuera_del_ciclo(memo):
    """Si se reiniciaran en cada vuelta, la «serie» serían doce meses sueltos.

    Y el defecto es silencioso en enero —donde acumulado y mensual coinciden—,
    que es justo donde uno mira para ver si quedó bien.
    """
    i = memo.find("let na = 0")
    j = memo.find("for (let m = 1")
    assert 0 < i < j, "`na/no/pax/rev` arrancan antes del ciclo de meses"


# ═══════════════════════════════════════════════════════════════════════════
# 3 · Trampa 2: la última columna tiene que dar el KPI del encabezado
# ═══════════════════════════════════════════════════════════════════════════
def test_el_ingreso_acumula_TODAS_las_categorias(memo):
    """«Other Rooms Revenue» tiene units=0 y su plata es ingreso real.

    El `rev +=` va ANTES del filtro por categoría con unidades; las noches y
    el pax, después. Mismo reparto que `tot` en la pantalla.
    """
    i = memo.find("rev += r.revenue")
    j = memo.find("if (!conUnidades.has(r.room_type_id)) continue;")
    assert i > 0 and j > 0, "faltan el acumulado de ingreso o el filtro"
    assert i < j, (
        "el ingreso se suma antes de filtrar por unidades; si no, "
        "«Other Rooms Revenue» desaparece y el ADR de la última columna no "
        "da el del KPI")


def test_las_noches_solo_de_categorias_con_unidades(memo):
    k = memo.find("na += r.nights_available")
    j = memo.find("if (!conUnidades.has(r.room_type_id)) continue;")
    assert k > j > 0, "las noches se suman después del filtro por unidades"


def test_el_conjunto_de_categorias_con_unidades_sale_del_catalogo(memo):
    assert "rs.room_types.filter(rt => rt.units > 0)" in memo


# ═══════════════════════════════════════════════════════════════════════════
# 4 · Lo que se ve: la tabla y la hoja del Excel
# ═══════════════════════════════════════════════════════════════════════════
def test_la_tabla_esta_en_pantalla(codigo):
    assert "ACUM_FILAS" in codigo
    assert "acumulado.length > 1" in codigo, (
        "con un solo mes la serie no dice nada: se oculta")


def test_la_tabla_muestra_ocupacion_y_adr(codigo):
    i = codigo.find("const ACUM_FILAS")
    j = codigo.find("];", i)
    filas = codigo[i:j]
    assert '"Occupancy"' in filas and '"ADR"' in filas


def test_el_excel_lleva_la_hoja_del_acumulado(codigo):
    assert 'hoja: "YTD"' in codigo, (
        "la bajada mes a mes tiene que incluir la hoja del acumulado")


def test_la_hoja_del_excel_usa_la_serie_de_la_pantalla(codigo):
    """No la rehace desde `rs.months`: la toma de `acumulado`.

    Dos cálculos del mismo número es exactamente cómo se llega a que el
    archivo diga una cosa y la pantalla otra.
    """
    i = codigo.find('hoja: "YTD"')
    assert i > 0
    bloque = codigo[max(0, i - 1600):i + 600]
    assert "acumulado.map(" in bloque


def test_la_ocupacion_va_a_excel_como_fraccion(codigo):
    """El formato `pct` del exportador multiplica por cien al escribir."""
    i = codigo.find("const ACUM:")
    j = codigo.find("];", i)
    assert i > 0 and j > i
    bloque = codigo[i:j]
    assert 'fmt: "pct",  v: a => a.occ' in bloque.replace("  ", "  ")


# ═══════════════════════════════════════════════════════════════════════════
# 5 · Los rótulos, en los dos idiomas
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("archivo", [ES, EN])
def test_los_rotulos_existen_en_los_dos_idiomas(archivo):
    """Una llave que no existe no la ve el typecheck: revienta la pantalla en
    tiempo de ejecución. Ya pasó con `totalRevenue`."""
    import json
    d = json.loads(archivo.read_text(encoding="utf-8"))["roomStats"]
    for k in ("acumTitulo", "acumNota"):
        assert k in d, f"falta `{k}` en {archivo.name}"
        assert d[k].strip(), f"`{k}` vacía en {archivo.name}"


@pytest.mark.parametrize("archivo", [ES, EN])
def test_la_nota_avisa_que_no_es_promedio(archivo):
    """La nota al pie es lo único que acompaña al número cuando alguien copia
    la tabla a otro lado. Si no dice que no es un promedio, el lector la
    promedia."""
    import json
    nota = json.loads(archivo.read_text(encoding="utf-8"))["roomStats"]["acumNota"]
    assert "NO " in nota or "NOT " in nota
