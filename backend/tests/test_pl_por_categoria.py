# -*- coding: utf-8 -*-
"""El segundo formato del P&L dice el MISMO GOP que el primero.

## De dónde sale (2026-11-09)

Owner: *«necesito que el P&L tenga 2 versiones de formato: 1) tal como está en
este momento, y 2) Ingreso − Costo − Planilla − Opex igual a GOP. En este
formato no es formato USALI, solo necesito poder ir viendo los totales por
departamento de cada categoría, GOP menos todo lo demás hasta llegar a net
profit»*.

El formato 1 es USALI: agrupa por DEPARTAMENTO y dentro de cada uno mezcla
planilla, costo y opex en un solo renglón. El formato 2 agrupa por NATURALEZA y
abre los departamentos adentro. Es la misma plata sumada en otro orden.

## Lo que cuida, y por qué importa tanto

**Que los dos formatos den el mismo GOP.** Dos pantallas del mismo sistema
contando la misma plata y dando números distintos es el modo de falla más caro
que hay acá: el total sigue cuadrando consigo mismo en las dos, no hay error, no
hay alerta, y quien compare las dos pantallas no sabe a cuál creerle.

Y la identidad es fácil de romper — ya se rompió midiendo:

* **Si se excluye algún departamento.** `gasto-por-clase` excluye Cafetería
  (0220) y Lavandería (0161), que es correcto para lo que ese endpoint hace.
  Construir el formato 2 sobre esa exclusión daba **$245.126,80** de diferencia
  al año en el Budget Working 2027.
* **Si falta el bloque de reparto.** Suma cero entre departamentos, así que es
  tentador no dibujarlo. Pero es lo que hace netear a esos dos: sin él,
  Cafetería muestra su gasto bruto —$18.688,80 en enero— y nunca se cancela.

Por eso la prueba no mira sólo el total: exige el cero **mes a mes**, y exige
que el bloque de reparto exista y sume cero.
"""
import pytest

from app.api import pl_categoria_api as cat

from ._rutas import FRONT, sin_comentarios


# ── La forma del reporte ────────────────────────────────────────────────────

def test_los_bloques_son_las_cuatro_naturalezas_mas_el_reparto():
    """El orden es el que nombró el owner, y el reparto va al final.

    Leer el reparto antes de ver el gasto bruto que cancela no se entiende."""
    claves = [b[0] for b in cat.BLOQUES]
    assert claves == ["cost", "payroll", "opex", "reparto"]


def test_el_corte_de_la_plantilla_se_busca_por_rotulo():
    """⚠️ Por rótulo y NO por índice.

    La plantilla del formato 1 crece —el owner pide renglones cada tanto— y un
    número fijo se desplaza en silencio, dejando el GOP de un lado y «Rent» del
    otro sin que nada falle."""
    from app.api import pl_detail_api as det

    rotulos = [r for _t, r, _c in det.CONSOLIDADO]
    assert cat.ROTULO_GOP in rotulos, (
        f"{cat.ROTULO_GOP!r} ya no está en la plantilla del P&L: el formato 2 "
        "no sabría dónde cortar")


def test_el_rotulo_del_GOP_es_el_MISMO_de_los_dos_formatos():
    """⚠️ El desencaje que no falla ruidosamente.

    De este renglón cuelga toda la cascada de abajo: «EBITDA BEFORE CAPITAL» lo
    nombra como operando. Si el formato 2 lo llamara distinto —y la primera
    versión lo llamaba «GOP · Ingreso − Costo − Planilla − OPEX», que se lee
    mejor— el exportador no encontraría el operando y dejaría EBITDA, EBT y NET
    PROFIT como números PEGADOS, mientras todo el detalle de arriba baja con
    fórmula. Nada se pone rojo: sólo se pierden las tres celdas más miradas.

    La aritmética del formato 2 se lee en los encabezados de sus cinco
    secciones, que es donde corresponde."""
    from app.api import pl_detail_api as det

    gop_formato_1 = [r for t, r, _c in det.CONSOLIDADO
                     if t == "tot" and r == cat.ROTULO_GOP]
    assert gop_formato_1, "el formato 1 ya no tiene ese rótulo como total"

    fuente = (__import__("pathlib").Path(cat.__file__)).read_text(encoding="utf-8")
    assert '_fila("tot", ROTULO_GOP, gop_resta)' in fuente, (
        "el GOP del formato 2 dejó de usar ROTULO_GOP: la cascada de abajo "
        "pierde sus fórmulas sin que nada falle")


def test_el_club_es_el_260():
    from app.api import club_stats_api

    assert cat.CLUB_DEPT == club_stats_api.DEPT_CLUB


@pytest.mark.parametrize("ambito,dentro,fuera", [
    ("consolidado", ["0110", "260"], []),
    ("hotel", ["0110"], ["260"]),
    ("club", ["260"], ["0110"]),
])
def test_el_filtro_de_ambito(ambito, dentro, fuera):
    d = {"0110": 10, "260": 5}
    salida = cat._filtra_ambito(d, ambito)
    for k in dentro:
        assert k in salida, f"{k} debería estar en el ámbito {ambito}"
    for k in fuera:
        assert k not in salida, f"{k} NO debería estar en el ámbito {ambito}"


# ── La identidad, sobre datos armados a mano ────────────────────────────────

def test_la_resta_da_el_gop():
    """Ingreso − Costo − Planilla − OPEX − Reparto = GOP, con números a mano.

    Los del Budget Working 2027 de enero, redondeados: es la cuenta que se midió
    contra producción y dio $0.0000 de diferencia."""
    ingreso = 862230.09
    costo, planilla, opex, reparto = 98121.00, 211885.16, 168236.64, 0.00
    assert round(ingreso - costo - planilla - opex - reparto, 2) == 383987.29


def test_el_reparto_suma_cero_entre_departamentos():
    """Cafetería y Lavandería reparten lo suyo: lo que sale de ellas entra a las
    demás. Si el bloque no diera cero, el GOP de este formato se iría por esa
    diferencia."""
    reparto = {"0220": -181139.42, "0161": -45280.21,
               "0110": 24424.46, "0122": 26829.16, "0183": 55754.78,
               "0150": -21030.50, "0152": 18763.90, "0113": 13607.04,
               "0111": 13414.58, "0112": 9581.85, "0114": 11498.22,
               "0120": 9769.78, "0123": 21080.04, "0132": 8191.57,
               "0162": 2442.47, "0181": 1916.36, "0182": 396.07,
               "0186": 9581.85, "0200": 16497.32, "0205": 1916.36,
               "0230": 1784.34}
    assert abs(sum(reparto.values())) < 0.02, (
        "el reparto no netea: el formato 2 diría un GOP distinto al del P&L")


def test_excluir_cafeteria_y_lavanderia_ROMPE_la_identidad():
    """La prueba de que la condición 1 no es decorativa.

    Con la exclusión de `gasto-por-clase`, enero daba $1.601,34 de diferencia —
    que es exactamente el neto de esos dos departamentos en el overhead del
    formato 1 (−9.238,46 + 10.500,00 de Cafetería, +339,80 de Lavandería)."""
    excluidos = {"planilla": 2525.31 + 6058.80, "costo": 10500.00,
                 "opex": 2310.00 + 2130.00, "reparto": -4495.51 - 17427.26}
    assert round(sum(excluidos.values()), 2) == 1601.34


# ── Los auxiliares ──────────────────────────────────────────────────────────

def test_suma_series_alinea_los_meses():
    a = [1.0] * 12
    b = [0.5] * 12
    assert cat._suma_series([a, b]) == [1.5] * 12


def test_suma_series_sin_nada_da_doce_ceros():
    """Un departamento sin movimiento no puede devolver una serie corta: el
    cuadro la pone en una columna de mes y correría todo lo de la derecha."""
    assert cat._suma_series([]) == [0.0] * 12


def test_el_rotulo_del_depto_lleva_el_nombre():
    """Una lista de números sueltos —0120, 0150, 0220— no le dice nada a nadie."""
    nombres = {"0120": "Alimentos y Bebidas"}
    assert cat._rotulo_depto("0120", nombres) == "0120 · Alimentos y Bebidas"
    assert cat._rotulo_depto("9999", nombres) == "9999"


def test_la_ruta_esta_registrada():
    """Leer el módulo no es montarlo: un router que nadie incluye contesta 404
    y la pantalla ve «no se pudo cargar» sin decir por qué."""
    from app.main import app

    rutas = {r for r in app.openapi()["paths"]}
    assert "/api/reports/pl-por-categoria/{ambito}/" in rutas


# ── El cableado del FRONT ───────────────────────────────────────────────────
#
# Misma convención que `test_tarifa_neta_en_el_front.py`: lo que hay que
# impedir no es una cuenta mal hecha, es que el cuadro pierda su fórmula o que
# la hoja deje de bajar. Eso no se ve ejecutando nada — se ve leyendo el código.

PANTALLA = "app/planning/report/page.tsx"
LIBRERIA = "lib/planningReport.ts"
CASCADA = "lib/tresCortes.ts"


def _src(rel: str) -> str:
    return sin_comentarios((FRONT / rel).read_text(encoding="utf-8"))


def test_el_cuadro_usa_la_cascada_POR_CATEGORIA():
    """⚠️ La que más barato se rompe.

    `resultadosDelPL` tiene por defecto la cascada del formato USALI. Llamarla
    sin la tabla del formato 2 compila, dibuja bien en pantalla y sólo se nota
    en el Excel: el GOP y las tres líneas de abajo bajan como números pegados
    mientras todo el detalle lleva fórmula."""
    src = _src(LIBRERIA)
    assert "cuadroPlanningPorCategoria" in src
    bloque = src.split("export function cuadroPlanningPorCategoria")[1]
    bloque = bloque.split("export function")[0]
    assert "resultadosDelPL(emitidas, RESULTADOS_POR_CATEGORIA)" in bloque, (
        "el cuadro por categoría usa la cascada de siempre: el GOP y lo de "
        "abajo pierden la fórmula en el Excel")


def test_la_cascada_por_categoria_resta_las_CUATRO_naturalezas():
    """Y el reparto entre ellas: sin él, el GOP se va $245.126,80 al año."""
    src = _src(CASCADA)
    bloque = src.split("RESULTADOS_POR_CATEGORIA")[1].split("};")[0]
    for rotulo in ("TOTAL INGRESO", "TOTAL COSTO DE VENTAS", "TOTAL PLANILLA",
                   "TOTAL GASTOS OPERATIVOS", "TOTAL REPARTO"):
        assert rotulo in bloque, f"falta {rotulo!r} en la cascada del formato 2"


def test_los_totales_del_formato_2_suman_su_detalle():
    """Sin esto, los cinco totales bajan pegados en vez de con `=SUM(...)`."""
    src = _src(CASCADA)
    bloque = src.split("SUMA_DEL_DETALLE")[1].split("]);")[0]
    for rotulo in ("TOTAL INGRESO", "TOTAL COSTO DE VENTAS", "TOTAL PLANILLA",
                   "TOTAL GASTOS OPERATIVOS", "TOTAL REPARTO"):
        assert rotulo in bloque, f"{rotulo!r} no suma su detalle"


def test_la_pantalla_tiene_el_sub_tab():
    """Owner, 2026-11-09: *«lo pones como un sub tab»*."""
    src = _src(PANTALLA)
    assert "FORMATOS" in src and "setFormato" in src
    assert "cuadroPlanningPorCategoria" in src


def test_el_paquete_de_excel_baja_LAS_DOS_hojas():
    """*«pero también lo pones en el excel como versión 2»*.

    Las dos por ámbito: el formato 1 y el 2. Si alguien saca la segunda
    llamada, el paquete sigue bajando —con una hoja menos— y nada falla."""
    src = _src(PANTALLA)
    bloque = src.split("const hojasDe")[1].split('} else if (v === "aperturas")')[0]
    assert "getPLDetail" in bloque, "el paquete dejó de bajar el P&L de siempre"
    assert "getPLPorCategoria" in bloque, (
        "el paquete dejó de bajar la hoja v2 del P&L")
    assert "cuadroPlanningPorCategoria" in bloque


def test_los_dos_formatos_se_piden_juntos():
    """Cambiar de sub-tab no puede esperar un viaje al servidor: los dos se
    piden en la misma pasada, con la de estadísticas."""
    src = _src(PANTALLA)
    bloque = src.split('if (vista === "pl") {')[1].split("setStats")[0]
    assert "Promise.all" in bloque
    assert "getPLPorCategoria" in bloque


def test_si_el_formato_2_falla_el_P_y_L_igual_se_dibuja():
    """Una hoja nueva que rompe el paquete entero es peor que no tenerla."""
    src = _src(PANTALLA)
    assert "getPLPorCategoria(ambito, principal, otros).catch(() => null)" in src
