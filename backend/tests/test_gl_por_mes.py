# -*- coding: utf-8 -*-
"""Las cuentas del mayor por mes, y que Σ sea la utilidad cambiada de signo.

Owner, 2026-11-05: *«que lo pongas en el tab Reports al final para poder
conciliar los resultados… y que exista un proceso de validación interno para
que pegue con los reportes»*.

## Lo que estas pruebas defienden

La propiedad que hace útil al reporte: **Σ de todas las filas = −utilidad**.
Si eso vale, cada peso del mayor llegó a un renglón del P&L. Si no vale, el
reporte dice cuál se quedó afuera.

## El error que casi se comete, y que estas pruebas impiden repetir

La primera versión decidía el signo por el **primer dígito de la cuenta**:
4xxx = ingreso = crédito. Daba una diferencia de **180.817,68** contra ACTUAL
2026, que era **exactamente el doble** de 90.408,84 — y un factor dos aparece
cuando una partida se resta de un lado y se suma del otro. Eran estas:

    0161  4900  Distribución   −18.852,40  → OH_LAUNDRY    [OVERHEAD EXPENSES]
    0220  4901  Distribución   −71.556,43  → OH_CAFETERIA  [OVERHEAD EXPENSES]

Clase 4, pero **no son ingreso**: son el crédito con que el reparto deja a
lavandería y cafetería en cero. Manda la **sección del P&L**, no el dígito.
"""
from decimal import Decimal

import pytest

from app.engine import gl_por_mes as gl

ZERO = Decimal("0")


def _fila(cuenta, dept="0110", nombre="", **meses):
    base = {"dept_code": dept, "account_code": cuenta, "account_name": nombre}
    base.update({m: ZERO for m in gl.MESES})
    base.update(meses)
    return base


def _resolver(mapa):
    """`(dept, cuenta) -> (regla, cómo)` a partir de {cuenta: line_code}."""
    def r(dept, cuenta):
        lc = mapa.get(cuenta)
        if lc is None:
            return None, "DROP"
        return {"report_line_code": lc, "report_line_name": lc}, "exact"
    return r


SECCIONES = {
    "REV_ROOMS": "REVENUES",
    "REV_FB": "REVENUES",
    "COS_FB": "COST OF SALES",
    "DEPT_PAYROLL": "OPERATING EXPENSES",
    "OH_ADMIN": "OVERHEAD EXPENSES",
    "OH_LAUNDRY": "OVERHEAD EXPENSES",
    "DEPRECIATION": "DEPRECIATION",
}


# ── El signo ────────────────────────────────────────────────────────────────

def test_el_ingreso_se_muestra_negativo():
    [fila] = gl.armar_grilla(
        [_fila("4000", jan=Decimal("1000"))],
        resolver=_resolver({"4000": "REV_ROOMS"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("-1000")
    assert fila["categoria"] == "REVENUE"


def test_el_gasto_se_muestra_positivo():
    [fila] = gl.armar_grilla(
        [_fila("7065", jan=Decimal("400"))],
        resolver=_resolver({"7065": "OH_ADMIN"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("400")
    assert fila["categoria"] == "OPERATING_EXPENSES"


def test_una_4xxx_que_el_PL_manda_a_overhead_NO_se_invierte():
    """⚠️ El defecto exacto que costó 180.817,68 de diferencia.

    `4900 Distribución` es clase 4 y es el crédito del reparto de lavandería.
    El P&L la manda a OVERHEAD EXPENSES. Si se la invierte por empezar con 4,
    la plata se mueve de lado y la diferencia sale al DOBLE del monto.
    """
    [fila] = gl.armar_grilla(
        [_fila("4900", dept="0161", jan=Decimal("-18852.40"))],
        resolver=_resolver({"4900": "OH_LAUNDRY"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("-18852.40"), "no se invierte"
    # ⚠️ La categoría cambió el 2026-11-10 (owner: «4999 allocations»): el
    # reparto dejó de esconderse dentro del gasto operativo y tiene la suya.
    # El SIGNO -- que es lo que esta prueba cuida -- no se tocó.
    assert fila["categoria"] == "ALLOCATIONS"
    # Y ya no se marca como rareza: tener su propia categoría es mejor que una
    # alarma que venía con la excusa al lado («estas dos están bien»).
    assert fila["clase_discrepa"] is False


def test_una_4xxx_que_NO_es_reparto_y_cae_en_gasto_SI_se_marca():
    """La bandera queda para lo que de verdad no se espera: una tercera cuenta
    clase 4 cayendo en gasto, que no sea una `49xx` de reparto."""
    [fila] = gl.armar_grilla(
        [_fila("4300", dept="0165", jan=Decimal("-500"))],
        resolver=_resolver({"4300": "OH_ADMIN"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["clase_discrepa"] is True
    assert fila["categoria"] == "ALLOCATIONS", (
        "se agrupa con los repartos -- es clase 4 que el P&L no trata como "
        "ingreso -- pero la bandera avisa que no es una 49xx conocida")


def test_sin_mapeo_el_signo_cae_al_primer_digito():
    """Es lo único que queda — y la fila sale marcada DROP."""
    [fila] = gl.armar_grilla(
        [_fila("4000", jan=Decimal("500"))],
        resolver=_resolver({}), seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("-500")
    assert fila["mapeo"] == "DROP"


# ── La igualdad ─────────────────────────────────────────────────────────────

def test_la_suma_es_la_utilidad_cambiada_de_signo():
    grilla = gl.armar_grilla([
        _fila("4000", jan=Decimal("1000")),                    # ingreso
        _fila("5101", dept="0120", jan=Decimal("300")),        # costo
        _fila("6000", jan=Decimal("200")),                     # planilla
    ], resolver=_resolver({"4000": "REV_ROOMS", "5101": "COS_FB",
                           "6000": "DEPT_PAYROLL"}),
       seccion_de_linea=SECCIONES.get)
    # utilidad = 1000 − 300 − 200 = 500  →  Σ debe dar −500
    assert gl.total_del_reporte(grilla) == Decimal("-500")
    res = gl.conciliar(grilla, utilidad_pl=Decimal("500"))
    assert res["cuadra"] is True
    assert res["diferencia"] == ZERO


def test_una_cuenta_sin_mapeo_es_la_diferencia():
    """El caso real del Pre-Cierre 2026: una sola cuenta, 529,21."""
    grilla = gl.armar_grilla([
        _fila("4000", jan=Decimal("1000")),
        _fila("8050", dept="0250", nombre="OTHER OWNERS' EXPENSES",
              jan=Decimal("529.21")),
    ], resolver=_resolver({"4000": "REV_ROOMS"}),
       seccion_de_linea=SECCIONES.get)
    # El P&L no ve la 8050, así que su utilidad es 1000.
    res = gl.conciliar(grilla, utilidad_pl=Decimal("1000"))
    assert res["cuadra"] is False
    assert res["diferencia"] == Decimal("529.21")
    assert len(res["sin_mapeo"]) == 1
    assert res["sin_mapeo_total"] == Decimal("529.21")
    assert res["sin_mapeo"][0]["account_code"] == "8050"


def test_las_estadisticas_no_suman():
    """Las 9xxx son noches y kilos. Sumarlas rompería la igualdad sin avisar."""
    grilla = gl.armar_grilla([
        _fila("4000", jan=Decimal("1000")),
        _fila("9000", jan=Decimal("930")),      # noches disponibles
    ], resolver=_resolver({"4000": "REV_ROOMS"}),
       seccion_de_linea=SECCIONES.get)
    assert gl.total_del_reporte(grilla) == Decimal("-1000")
    resumen = {f["categoria"]: f for f in gl.resumen_por_categoria(grilla)}
    assert resumen["STATISTICS"]["suma"] is False
    assert resumen["NET"]["total"] == Decimal("-1000")


def test_las_estadisticas_sin_mapeo_no_se_denuncian():
    """Una 9xxx no tiene por qué llegar al P&L: no es plata."""
    grilla = gl.armar_grilla([_fila("9000", jan=Decimal("930"))],
                             resolver=_resolver({}))
    res = gl.conciliar(grilla, utilidad_pl=ZERO)
    assert res["sin_mapeo"] == []


# ── La comparación renglón por renglón ──────────────────────────────────────

def test_el_ingreso_se_compara_en_la_misma_vara():
    """La grilla lo tiene negativo y el P&L positivo.

    ⚠️ Mirar el SIGNO del número para decidir da el doble del monto cada vez
    que un gasto resulta negativo — es lo que pasó con `INCOME_TAXES`. Se mira
    la SECCIÓN.
    """
    grilla = gl.armar_grilla([_fila("4000", jan=Decimal("1000"))],
                             resolver=_resolver({"4000": "REV_ROOMS"}),
                             seccion_de_linea=SECCIONES.get)
    res = gl.conciliar(grilla, utilidad_pl=Decimal("1000"),
                       por_linea_pl={"REV_ROOMS": Decimal("1000")},
                       comparables={"REV_ROOMS"}, secciones=SECCIONES)
    [linea] = res["por_linea"]
    assert linea["gl"] == Decimal("1000"), "puesto en la vara del P&L"
    assert linea["diferencia"] == ZERO


def test_un_gasto_negativo_no_se_duplica():
    """El caso de `INCOME_TAXES`: −17.530,33 en los dos lados, diferencia 0."""
    grilla = gl.armar_grilla(
        [_fila("8060", dept="0250", jan=Decimal("-17530.33"))],
        resolver=_resolver({"8060": "DEPRECIATION"}),
        seccion_de_linea=SECCIONES.get)
    res = gl.conciliar(grilla, utilidad_pl=Decimal("17530.33"),
                       por_linea_pl={"DEPRECIATION": Decimal("-17530.33")},
                       comparables={"DEPRECIATION"}, secciones=SECCIONES)
    [linea] = res["por_linea"]
    assert linea["diferencia"] == ZERO


def test_solo_se_comparan_los_renglones_comparables():
    """⚠️ El motor emite `GOP`, `EBITDA_BEFORE` y `EBITDA_AFTER`, que **no
    están en la configuración**. Comparados salen con el mayor en cero y una
    diferencia igual a todo el renglón: ruido que tapa lo que sí importa.
    """
    grilla = gl.armar_grilla([_fila("4000", jan=Decimal("1000"))],
                             resolver=_resolver({"4000": "REV_ROOMS"}),
                             seccion_de_linea=SECCIONES.get)
    res = gl.conciliar(grilla, utilidad_pl=Decimal("1000"),
                       por_linea_pl={"REV_ROOMS": Decimal("1000"),
                                     "GOP": Decimal("-581947.24")},
                       comparables={"REV_ROOMS"}, secciones=SECCIONES)
    assert [l["pl_line_code"] for l in res["por_linea"]] == ["REV_ROOMS"]


def test_el_resumen_abre_planilla_de_opex():
    """El P&L mete las dos en OPERATING EXPENSES; el reporte las separa."""
    grilla = gl.armar_grilla([
        _fila("6000", jan=Decimal("200")),
        _fila("7065", jan=Decimal("400")),
    ], resolver=_resolver({"6000": "DEPT_PAYROLL", "7065": "OH_ADMIN"}),
       seccion_de_linea=SECCIONES.get)
    cats = {r["account_code"]: r["categoria"] for r in grilla}
    assert cats["6000"] == "PAYROLL"
    assert cats["7065"] == "OPERATING_EXPENSES"


@pytest.mark.parametrize("cuenta,esperado", [
    ("4000", "REVENUE"), ("5101", "COST_OF_SALES"), ("6000", "PAYROLL"),
    ("7065", "OPERATING_EXPENSES"), ("8040", "BELOW_GOP"), ("9000", "STATISTICS"),
])
def test_sin_seccion_la_categoria_sale_del_primer_digito(cuenta, esperado):
    assert gl.categoria_de(cuenta) == esperado


# --- El catálogo del mapeo dentro de la grilla -----------------------------
#
# Owner, 2026-11-10, señalando Admin · Account Mapping: *«¿por qué no jalas
# este master data a esta vista? ya tiene todo»*. La grilla sólo mostraba las
# cuentas CON movimiento, así que una cuenta que existe y quedó sin
# presupuestar era indistinguible de una que no existe.

def test_las_cuentas_en_cero_NO_mueven_ningun_total():
    """⚠️ La prueba que hace seguro traer el catálogo.

    Las cuentas del mapeo entran en CERO. Si alguna moviera un total, el
    reporte diría una cifra distinta según esté prendido o apagado el
    interruptor — y el que concilia no tendría forma de saber cuál es la
    buena.
    """
    con_plata = [_fila("7065", jan=Decimal("400")),
                 _fila("4000", dept="0110", jan=Decimal("1000"))]
    resolver = _resolver({"7065": "OH_ADMIN", "4000": "REV_ROOMS"})

    solas = gl.armar_grilla(con_plata, resolver=resolver,
                            seccion_de_linea=SECCIONES.get)
    # Las mismas, más nueve cuentas del catálogo que el escenario no usó.
    del_catalogo = [_fila(c, dept="0120") for c in
                    ("4110", "4120", "5101", "5150", "6001", "7025",
                     "7060", "7150", "8040")]
    con_catalogo = gl.armar_grilla(con_plata + del_catalogo, resolver=resolver,
                                   seccion_de_linea=SECCIONES.get)

    assert len(con_catalogo) == len(solas) + 9, "las cuentas vacías sí se ven"
    assert gl.total_del_reporte(con_catalogo) == gl.total_del_reporte(solas), (
        "una cuenta en cero movió el total del reporte")

    neto = lambda g: next(f["total"] for f in gl.resumen_por_categoria(g)
                          if f["categoria"] == "NET")
    assert neto(con_catalogo) == neto(solas), "el NET cambió al traer el catálogo"


def test_la_cuenta_vacia_se_clasifica_igual_que_si_tuviera_plata():
    """Una cuenta del catálogo tiene que caer en SU categoría, no en OTHER:
    verla en cero sólo sirve si está en el renglón donde le tocaría estar."""
    [vacia] = gl.armar_grilla(
        [_fila("4110", dept="0120")],
        resolver=_resolver({"4110": "REV_FB"}),
        seccion_de_linea=SECCIONES.get)
    assert vacia["categoria"] == "REVENUE"
    assert vacia["total"] == Decimal("0")


# --- La liga contable del checkbook ----------------------------------------
#
# Owner, 2026-11-10: *«asigna cuenta y asigna departamento, realiza la liga
# contable al checkbook»*. El checkbook guarda el ingreso por LÍNEA, sin
# cuenta ni departamento; `ancla_contable` le da su asiento.

MAPEO_REV = [
    {"report_line_code": "REV_ROOMS", "account_code": "4000",
     "dept_code": "0116", "account_name_example": "Room Revenue"},
    {"report_line_code": "REV_ROOMS", "account_code": "4000",
     "dept_code": "0110", "account_name_example": "Room Revenue"},
    {"report_line_code": "REV_ROOMS", "account_code": "4000",
     "dept_code": "0115", "account_name_example": "Room Revenue"},
    {"report_line_code": "REV_ROOMS_OTHER", "account_code": "4002",
     "dept_code": "0110", "account_name_example": "No Show"},
    {"report_line_code": "REV_ROOMS_OTHER", "account_code": "4001",
     "dept_code": "0110", "account_name_example": "Cancellations"},
]


def test_el_ancla_es_determinista():
    """Dos corridas tienen que dar la MISMA cuenta.

    Si el ancla dependiera del orden en que la base devuelve las filas, el
    ingreso de un mes aparecería un día en 0110 y otro en 0115 sin que nadie
    tocara nada -- y el total seguiría cuadrando, que es lo que lo hace
    peligroso.
    """
    a = gl.ancla_contable(MAPEO_REV)
    b = gl.ancla_contable(list(reversed(MAPEO_REV)))
    assert a == b
    assert a["REV_ROOMS"] == ("0110", "4000", "Room Revenue")
    assert a["REV_ROOMS_OTHER"] == ("0110", "4001", "Cancellations")


def test_el_ancla_sale_del_mapeo_que_usa_el_PL():
    """No de una lista aparte. Una línea sin regla no tiene ancla y la fila
    no se inventa: mejor que falte a que aparezca en una cuenta cualquiera."""
    assert "REV_INEXISTENTE" not in gl.ancla_contable(MAPEO_REV)
    sin_cuenta = [{"report_line_code": "REV_X", "account_code": "",
                   "dept_code": "0110"}]
    assert gl.ancla_contable(sin_cuenta) == {}


def test_la_cuenta_anclada_vuelve_a_SU_linea():
    """⚠️ El invariante que hace que esto no mueva plata.

    La cuenta de asiento de una línea tiene que resolver de vuelta a esa misma
    línea. Si no, el ingreso aparecería en la grilla bajo un renglón distinto
    del que lo tiene en el P&L, y la conciliación renglón por renglón acusaría
    una diferencia en dos líneas -- una de más y otra de menos -- sobre un P&L
    que está bien.
    """
    ancla = gl.ancla_contable(MAPEO_REV)
    resolver = _resolver({m["account_code"]: m["report_line_code"]
                          for m in MAPEO_REV})
    for linea, (dept, cuenta, _n) in ancla.items():
        regla, _como = resolver(dept, cuenta)
        assert regla is not None, f"{linea}: su cuenta de asiento no tiene mapeo"


def test_el_nombre_de_la_cuenta_sale_limpio():
    """⚠️ El ancla pedia `account_name_example` a un cargador que NO lo trae.

    `recalc.load_active_account_mappings` devuelve un dict reducido -- cuenta,
    depto, linea, estado, operador -- sin el nombre. Pedirselo igual devolvia
    siempre vacio, y las 8xxx salian como `0250 Gastos de la Propiedad · 8020`
    a secas teniendo «CAPITAL RESERVE» escrito en el mapeo. Hay que ir al
    modelo.

    Y el campo guarda EJEMPLOS separados por `|`: Integrity numera las
    variantes de un mismo nombre. Volcar la lista entera en la celda la vuelve
    ilegible.
    """
    assert gl.nombre_de_cuenta("RENT1 | RENT") == "RENT"
    assert gl.nombre_de_cuenta(
        "DEPRECIATION1 | DEPRECIATION2 | DEPRECIATION4 | DEPRECIATION") == "DEPRECIATION"
    # Cuando TODAS llevan numero, se le quitan los digitos del final a la
    # primera: el numero lo puso el mayor, no es parte del nombre.
    assert gl.nombre_de_cuenta(
        "PROPERTY INSURANCE1 | PROPERTY INSURANCE2 | PROPERTY INSURANCE5"
    ) == "PROPERTY INSURANCE"
    assert gl.nombre_de_cuenta("OWNERS FEES") == "OWNERS FEES"
    assert gl.nombre_de_cuenta("") == ""
    assert gl.nombre_de_cuenta(None) == ""


def test_el_ancla_trae_el_nombre_del_mapeo():
    """Si no lo trae, la cuenta sale sin descripcion en el Excel que se manda."""
    ancla = gl.ancla_contable([
        {"report_line_code": "DEPRECIATION", "account_code": "8040",
         "dept_code": "0250",
         "account_name_example": "DEPRECIATION1 | DEPRECIATION"},
    ])
    assert ancla["DEPRECIATION"] == ("0250", "8040", "DEPRECIATION")


def test_una_prueba_que_use_el_cargador_REDUCIDO_falla():
    """Lo que paso: el dict de `load_active_account_mappings` no tiene el
    nombre, asi que el ancla salia sin descripcion y nada avisaba."""
    reducido = [{"report_line_code": "RENT", "account_code": "8000",
                 "dept_code": "0250", "active_status": "YES",
                 "rollup_operator": "SUM"}]          # <- sin account_name_example
    assert gl.ancla_contable(reducido)["RENT"] == ("0250", "8000", "")


# ─── Rooms abierto por set: Villas (0115) en su departamento ─────────────────

def test_el_ingreso_de_rooms_se_abre_por_el_depto_del_set():
    """Owner, 2026-11-10: «no me está bajando a los GL el departamento 0115 en
    ingresos». La parte de cada set va a SU depto con la misma cuenta, y el
    ancla (0110) se queda con el resto: la línea suma igual."""
    import inspect
    from app.api import gl_api
    src = inspect.getsource(gl_api._filas_del_mayor)
    assert "_apertura_de_rooms(db, esc)" in src
    assert 'linea.line_code == "REV_ROOMS"' in src
    assert "monto -= v" in src                    # el ancla se queda con el RESTO
    ap = inspect.getsource(gl_api._apertura_de_rooms)
    assert "get_revenue_by_room_type" in ap       # la apertura de los drivers, no un reparto nuevo
    assert 'rt.dept_code or "0110"' in ap


def test_la_planilla_baja_con_el_nombre_de_su_cuenta():
    """La planilla no guarda el nombre de la cuenta: las 6xxx con monto bajaban
    con «Account name» vacío (Villas 0115, 2026-11-10). La grilla lo completa
    del mapeo antes de armar las filas."""
    import inspect
    from app.api import gl_api
    src = inspect.getsource(gl_api._grilla)
    assert "por_par.get((f[\"dept_code\"], f[\"account_code\"]))" in src
    assert "por_cuenta.get(f[\"account_code\"]" in src
    # Se completa ANTES de armar las filas, para que el nombre viaje en la grilla.
    assert src.index("por_cuenta.get(") < src.index("grilla = [_fila(")


def test_villas_baja_en_su_depto_aunque_el_catalogo_la_cuelgue_de_rooms():
    """En producción el catálogo de departamentos cuelga 0115 de 0110, y el armado
    de los checkbooks subía su planilla y su OPEX al padre: el Excel recibía el
    ingreso en 0115 y el gasto en 0110 (owner, 2026-11-10). La grilla del mayor
    pide esos deptos aparte; el P&L no (Villas sigue sumando en Rooms)."""
    import inspect
    from app.api import gl_api
    from app.engine import pl_engine, recalculate as recalc
    assert gl_api.DEPTOS_PROPIOS_EN_EL_MAYOR == frozenset({"0115", "0116"})
    assert "respetar=DEPTOS_PROPIOS_EN_EL_MAYOR" in inspect.getsource(gl_api._filas_del_mayor)
    firma = inspect.signature(recalc.checkbook_account_rows_for_month)
    assert firma.parameters["respetar"].default == frozenset()     # el P&L no cambia
    # Con el catálogo de producción cargado, el padre de Villas es Rooms.
    pl_engine.set_dept_catalog([
        {"dept_code": "0110", "default_pl_group": "ROOMS", "parent_dept_code": ""},
        {"dept_code": "0115", "default_pl_group": "ROOMS", "parent_dept_code": "0110"}])
    try:
        assert pl_engine.consolidate_dept("0115") == "0110"
    finally:
        pl_engine.reset_dept_catalog()


# ─── El detalle por cuenta manda línea por línea, y solo si cuadra (AMA) ─────

def _meses(*v):
    return {m: Decimal(str(x)) for m, x in zip(gl.MESES, list(v) + [0] * (12 - len(v)))}


def test_el_detalle_que_cuadra_con_su_linea_manda():
    det = {"MGMT_FEE_3": [_meses(100, 50), _meses(0, 50)]}
    pl = {"MGMT_FEE_3": [Decimal("100"), Decimal("100")] + [ZERO] * 10}
    assert gl.lineas_con_detalle_fiel(det, pl) == {"MGMT_FEE_3"}


def test_el_detalle_que_no_cuadra_no_reemplaza_al_pl():
    """Budget 2026 Final de Amarena: el detalle de below-GOP decía 18,915 de
    honorarios y el P&L 68,337. La grilla usa el P&L."""
    det = {"MGMT_FEE_3": [_meses(18915)]}
    pl = {"MGMT_FEE_3": [Decimal("68337")] + [ZERO] * 11}
    assert gl.lineas_con_detalle_fiel(det, pl) == set()


def test_un_centavo_de_redondeo_sigue_siendo_el_mismo_numero():
    det = {"RENT": [_meses("1000.004")]}
    pl = {"RENT": [Decimal("1000")] + [ZERO] * 11}
    assert gl.lineas_con_detalle_fiel(det, pl) == {"RENT"}


def test_el_detalle_de_una_linea_no_apaga_el_ancla_de_las_demas():
    """Antes una sola fila de detalle apagaba el ancla de TODAS las líneas y la
    grilla perdía el ingreso entero ($452,657 en el Budget 2026 Final de AMA)."""
    import inspect
    from app.api import gl_api
    src = inspect.getsource(gl_api._filas_del_mayor)
    assert "if not detalle_real" not in src
    assert "gl.lineas_con_detalle_fiel(det_por_linea, pl_por_linea)" in src
    assert "linea.line_code in fieles" in src
    det = {"PROPERTY_INSURANCE": [_meses(10)]}
    pl = {"PROPERTY_INSURANCE": [Decimal("10")] + [ZERO] * 11,
          "REV_ROOMS": [Decimal("5000")] + [ZERO] * 11}
    assert gl.lineas_con_detalle_fiel(det, pl) == {"PROPERTY_INSURANCE"}   # REV_ROOMS se ancla


def test_los_centavos_de_cada_mes_no_se_acumulan_en_el_anio():
    """Seguro de Amarena 2026: 1,670.20 en el detalle contra 1,670.13 en el P&L,
    menos de un centavo por mes. La grilla usa el P&L y cuadra en $0.00."""
    det = {"PROPERTY_INSURANCE": [_meses(*([Decimal("139.1834")] * 12))]}
    pl = {"PROPERTY_INSURANCE": [Decimal("139.1775")] * 12}
    assert gl.lineas_con_detalle_fiel(det, pl) == set()
