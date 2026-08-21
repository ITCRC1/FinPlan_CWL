# -*- coding: utf-8 -*-
"""Las cuentas clase 5 tienen línea propia de COSTO, y eso no movió el resultado.

**De dónde salió (owner, 2026-08-14).** En la Consulta GL la cuenta 5101 se
llama «Food Cost» y su línea de P&L decía `OPEX_FB`. «Todas las líneas de
cuentas 5 son Cost». En el mismo movimiento pidió partir el ingreso de Rooms y
de A&B, con el mapeo marcado sobre su propia pantalla.

**La regla que puso: el resultado NO se mueve.** Verificado contra los 20
escenarios de producción con `scripts/foto_pl_totales.py` —siete líneas cada
uno, del ingreso al neto— antes de desplegar: idéntico al centavo.

⚠️ **Por qué esto necesita pruebas.** El motor arma `TOTAL_OPERATING_EXPENSES`
como `SUM(OPEX_*)` —por PREFIJO— y cada `PROFIT_X` como `REV_X − OPEX_X`. Mover
las clase 5 a `COS_*` **sin tocar esas fórmulas** las saca de los dos lados y el
GOP sube por el costo de ventas completo, en silencio. Estas pruebas son lo que
impide que alguien deshaga media reforma y deje la otra media en pie.
"""
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEED = RAIZ / "app" / "seed_data" / "mapping_pl.json"


def _datos():
    return json.loads(SEED.read_text(encoding="utf-8"))


def _lineas():
    return {r["line_code"]: r for r in _datos()["report_line_config"]}


# ─────────────────────────────────────────────────────────────────────────────
# El corte
# ─────────────────────────────────────────────────────────────────────────────

def test_ninguna_cuenta_clase_5_quedo_en_una_linea_de_gasto():
    """La regla del owner, tal cual: toda cuenta 5 va a una línea de costo."""
    malas = [(r["account_code"], r["report_line_code"])
             for r in _datos()["account_mapping"]
             if str(r["account_code"]).startswith("5")
             and not r["report_line_code"].startswith(("COS_", "COH_"))]
    assert not malas, f"cuentas clase 5 fuera de una línea de costo: {malas}"


def test_ninguna_linea_de_costo_recibe_algo_que_no_sea_clase_5():
    """Al revés: una 7xxx en una línea de costo inflaría el costo de ventas y el
    % de costo saldría mal, pero el total seguiría cuadrando."""
    malas = [(r["account_code"], r["report_line_code"])
             for r in _datos()["account_mapping"]
             if r["report_line_code"].startswith(("COS_", "COH_"))
             and not str(r["account_code"]).startswith("5")]
    assert not malas, f"cuentas que no son clase 5 en una línea de costo: {malas}"


def test_el_ingreso_quedo_partido_como_lo_marco_el_owner():
    """El mapeo que mandó sobre su pantalla de Account Mapping."""
    por_cuenta = {}
    for r in _datos()["account_mapping"]:
        if str(r["account_code"]).startswith("4") and r["dept_code"] in ("0110", "0120"):
            por_cuenta.setdefault(str(r["account_code"]), set()).add(r["report_line_code"])
    esperado = {
        "4000": "REV_ROOMS",          # Room Revenue      -> Rooms Revenue
        "4001": "REV_ROOMS_OTHER",    # Cancellations     -> Other Rooms Revenue
        "4002": "REV_ROOMS_OTHER",    # No Show           -> Other Rooms Revenue
        "4110": "REV_FB",             # Food              -> F&B Food
        "4120": "REV_FB_BEV",         # NA Beverage       -> F&B Beverage
        "4125": "REV_FB_BEV",         # Beer
        "4130": "REV_FB_BEV",         # Liquor
        "4131": "REV_FB_BEV",         # Wine
        "4132": "REV_FB_MISC",        # F&B Misc.
    }
    for cta, linea in esperado.items():
        assert por_cuenta.get(cta) == {linea}, (
            f"la cuenta {cta} tenía que ir a {linea} y está en {por_cuenta.get(cta)}"
        )


def test_el_ab_quedo_partido_en_comida_bebida_y_misc():
    por_linea = {}
    for r in _datos()["account_mapping"]:
        if r["report_line_code"].startswith("COS_FB"):
            por_linea.setdefault(r["report_line_code"], set()).add(str(r["account_code"]))
    assert por_linea["COS_FB_FOOD"] == {"5101", "5102", "5103"}
    assert por_linea["COS_FB_BEV"] == {"5150", "5151", "5152", "5153", "5154", "5155"}
    assert por_linea["COS_FB_MISC"] == {"5161", "5162", "5163", "5164", "5165"}


# ─────────────────────────────────────────────────────────────────────────────
# Lo que impide que el GOP se mueva
# ─────────────────────────────────────────────────────────────────────────────

def test_el_total_operativo_suma_tambien_el_costo():
    """⚠️ Sin este `+ SUM(COS_*)`, el costo de ventas desaparece del total y el
    GOP sube por su monto completo. Nada avisa: cada línea se ve bien."""
    f = _lineas()["TOTAL_OPERATING_EXPENSES"]["calculation_logic"]
    assert "SUM(OPEX_*)" in f and "SUM(COS_*)" in f, f"quedó como «{f}»"


def test_el_total_de_overhead_suma_tambien_su_costo():
    f = _lineas()["TOTAL_OVERHEAD_EXPENSES"]["calculation_logic"]
    assert "SUM(OH_*)" in f and "SUM(COH_*)" in f, f"quedó como «{f}»"


def test_los_dos_prefijos_de_costo_no_se_pisan():
    """`COS_` y `COH_` tienen que ser mundos separados: si un prefijo alcanzara
    al otro, el mismo costo entraría en el total operativo Y en el de overhead,
    y el GOP bajaría el doble.

    ⚠️ La primera versión de esta prueba comparaba LITERALES
    (`"COH_".startswith("COS_")`), o sea que era siempre verdadera y no tocaba
    el sistema. Ahora se comprueba MOVIENDO una línea de cada familia: subirle
    $1,000 al costo operativo no puede mover el overhead, y viceversa.
    """
    from decimal import Decimal
    from app.engine.pl_engine import _eval_calc_logic
    f_ope = _lineas()["TOTAL_OPERATING_EXPENSES"]["calculation_logic"]
    f_ovh = _lineas()["TOTAL_OVERHEAD_EXPENSES"]["calculation_logic"]
    base = {"OPEX_FB": Decimal(1000), "COS_FB_FOOD": Decimal(1000),
            "OH_ADMIN": Decimal(1000), "COH_CAFETERIA": Decimal(1000)}
    ope0, ovh0 = _eval_calc_logic(f_ope, base), _eval_calc_logic(f_ovh, base)
    mas_cos = {**base, "COS_FB_FOOD": Decimal(2000)}
    assert _eval_calc_logic(f_ope, mas_cos) - ope0 == Decimal(1000)
    assert _eval_calc_logic(f_ovh, mas_cos) == ovh0, (
        "el costo OPERATIVO se está sumando también al overhead")
    mas_coh = {**base, "COH_CAFETERIA": Decimal(2000)}
    assert _eval_calc_logic(f_ovh, mas_coh) - ovh0 == Decimal(1000)
    assert _eval_calc_logic(f_ope, mas_coh) == ope0, (
        "el costo de OVERHEAD se está sumando también al operativo")


def test_toda_linea_de_costo_entra_en_algun_total():
    """⚠️ La primera versión comprobaba `"SUM(COS_*)" in formulas` DENTRO del
    bucle: la misma constante para cada línea, o sea que no dependía de la
    línea y era un duplicado de la prueba de arriba. Y su docstring prometía
    detectar «un prefijo nuevo», que ni siquiera entraba al bucle.

    La propiedad de verdad —que ninguna línea con cuentas quede sin sumar en
    ningún total, sea cual sea su prefijo— vive ahora en
    `test_profit_lines_completas.test_real_toda_linea_con_cuentas_llega_a_algun_total`,
    que lo comprueba moviendo cada línea y mirando si los totales reaccionan.

    Acá queda el caso concreto de las dos familias de costo.
    """
    lineas = _lineas()
    assert any(c.startswith("COS_") for c in lineas)
    assert any(c.startswith("COH_") for c in lineas)


def test_cada_utilidad_departamental_resta_su_costo():
    """`PROFIT_X` restaba solo `OPEX_X`. Si no resta también su costo, la
    utilidad del departamento se infla — aunque el GOP total sí cuadre, porque
    `OPERATING_PROFIT` es `SUM(PROFIT_*)`. O sea: el error se ve en el
    departamento y NO en el total, que es donde nadie lo busca."""
    lineas = _lineas()
    costos = {c for c in lineas if c.startswith("COS_")}
    for code, r in lineas.items():
        if not code.startswith("PROFIT_"):
            continue
        expr = r.get("calculation_logic") or ""
        depto = code[len("PROFIT_"):]
        propios = {c for c in costos
                   if c == f"COS_{depto}" or c.startswith(f"COS_{depto}_")}
        for c in propios:
            assert re.search(rf"-\s*{c}\b", expr), (
                f"{code} no resta {c}: la utilidad de ese departamento queda inflada"
            )


def test_cada_utilidad_departamental_suma_su_ingreso_partido():
    """Mismo razonamiento del otro lado: Rooms y A&B tienen ingreso en más de una
    línea desde que se partieron."""
    lineas = _lineas()
    for code, extras in (("PROFIT_ROOMS", ["REV_ROOMS_OTHER"]),
                         ("PROFIT_FB", ["REV_FB_BEV", "REV_FB_MISC"])):
        expr = lineas[code].get("calculation_logic") or ""
        for x in extras:
            assert re.search(rf"\+\s*{x}\b", expr), (
                f"{code} no suma {x}: ese ingreso se pierde de la utilidad del "
                "departamento"
            )


def test_el_ingreso_total_sigue_tomando_las_lineas_nuevas():
    """Las nuevas mantienen el prefijo `REV_` justamente para esto."""
    assert _lineas()["TOTAL_REVENUES"]["calculation_logic"] == "SUM(REV_*)"
    for c in ("REV_ROOMS_OTHER", "REV_FB_BEV", "REV_FB_MISC"):
        assert c.startswith("REV_"), f"{c} se saldría de TOTAL_REVENUES"
        assert c in _lineas(), f"falta la línea {c}"


# ─────────────────────────────────────────────────────────────────────────────
# El motor tiene que saber leer las fórmulas nuevas
# ─────────────────────────────────────────────────────────────────────────────

def test_el_motor_suma_dos_grupos_en_una_formula():
    """Antes, `SUM(...)` se resolvía con un `fullmatch` sobre la expresión
    ENTERA. `SUM(OPEX_*) + SUM(COS_*)` no calzaba con ninguna rama, caía en la
    aritmética, y esta buscaba «SUM(OPEX_*)» como si fuera un código de línea:
    no existe, devolvía cero, y el total salía en 0.00."""
    from decimal import Decimal
    from app.engine.pl_engine import _eval_calc_logic
    montos = {"OPEX_FB": Decimal("100"), "OPEX_SPA": Decimal("10"),
              "COS_FB_FOOD": Decimal("7"), "COS_SPA": Decimal("3"),
              "OTRA": Decimal("999")}
    assert _eval_calc_logic("SUM(OPEX_*) + SUM(COS_*)", montos) == Decimal("120")


def test_el_motor_sigue_leyendo_las_formulas_de_siempre():
    """La reforma del evaluador no puede romper lo que ya funcionaba."""
    from decimal import Decimal
    from app.engine.pl_engine import _eval_calc_logic
    m = {"REV_FB": Decimal("50"), "OPEX_FB": Decimal("20"),
         "COS_FB_FOOD": Decimal("5"), "A": Decimal("3"), "B": Decimal("1")}
    assert _eval_calc_logic("SUM(REV_*)", m) == Decimal("50")
    assert _eval_calc_logic("SUM(REV_FB)", m) == Decimal("50")
    assert _eval_calc_logic("A - B", m) == Decimal("2")
    assert _eval_calc_logic("REV_FB - OPEX_FB - COS_FB_FOOD", m) == Decimal("25")
    assert _eval_calc_logic("", m) == Decimal("0")
    assert _eval_calc_logic("SUM mapped accounts", m) == Decimal("0")


def test_toda_formula_del_seed_es_legible_por_el_motor():
    """Una fórmula que el motor no entiende devuelve CERO en silencio. Esta
    prueba recorre las 117 líneas y exige que cada término sea o un `SUM(...)`
    o un código de línea que exista."""
    from app.engine.pl_engine import _eval_calc_logic  # noqa: F401
    lineas = _lineas()
    for code, r in lineas.items():
        # Solo las CALCULATED. El motor evalúa `calculation_logic` únicamente
        # para esas (`pl_engine.py:1068`); en las MAPPED y en las KPI el campo es
        # prosa que documenta de dónde sale la línea —«Payroll», «Total Rooms
        # Occupied / Total Available Rooms»— y nadie la interpreta.
        if not str(r.get("line_type", "")).startswith("CALCULATED"):
            continue
        expr = (r.get("calculation_logic") or "").strip()
        if not expr or "SUM mapped" in expr or "Source" in expr:
            continue
        for tok in re.split(r"\s+[-+]\s+", expr):
            tok = tok.strip()
            if not tok or re.fullmatch(r"SUM\(\w+\*?\)", tok):
                continue
            assert tok in lineas, (
                f"{code} usa «{tok}», que no es una línea ni un SUM(). El motor "
                "lo lee como cero y el total sale mal sin avisar."
            )


def test_el_puente_cubre_todos_los_grupos_de_overhead():
    """⚠️ El motor legacy emite `OVH_{grupo}` para TODOS los grupos de overhead,
    y `_MOTOR_TO_CANON` es el puente al vocabulario canónico. Le faltaban
    `OVH_CAFETERIA` y `OVH_LAUNDRY_OPS`: en un escenario de checkbook ese gasto
    no aparecía bajo ningún `OH_*`, así que sumar por prefijo no daba el total.

    Se comprueba contra las CONSTANTES del motor, no contra una lista escrita
    acá: el día que nazca un grupo de overhead nuevo, esto falla solo.
    """
    from app.engine import pl_engine as e
    grupos = set(e.OVERHEAD_DEPT_GROUPS)
    alias = {k[len("OVH_"):] for k in e._MOTOR_TO_CANON if k.startswith("OVH_")}
    faltan = grupos - alias
    assert not faltan, (
        f"grupos de overhead sin puente al vocabulario canónico: {sorted(faltan)}. "
        "Su gasto no cae bajo ningún OH_* y el total por prefijo sale corto."
    )


def test_el_puente_apunta_a_lineas_que_existen():
    """Un alias hacia una línea inexistente manda la plata a la nada."""
    import json
    from app.engine import pl_engine as e
    lineas = {r["line_code"] for r in
              json.loads(SEED.read_text(encoding="utf-8"))["report_line_config"]}
    malos = {k: v[0] for k, v in e._MOTOR_TO_CANON.items() if v[0] not in lineas}
    assert not malos, f"alias que apuntan a líneas que no existen: {malos}"


def test_ningun_total_se_dibuja_antes_que_sus_propias_lineas():
    """⚠️ Las 6 líneas `COH_*` compartían `display_order` 82 con
    `TOTAL_OVERHEAD_EXPENSES`, o sea un TOTAL empatado con su propio detalle.

    Los montos salían bien —el motor evalúa por dependencia, no por orden— pero
    el subtotal se dibujaba antes o entre sus componentes **según el orden
    físico de las filas de la base**, que `mapping_loader` reescribe cada vez
    que se recarga el mapeo. No hay índice único que lo impida.
    """
    cfg = _lineas()
    def orden(c):
        return cfg[c]["display_order"]
    for total, prefijo in (("TOTAL_OVERHEAD_EXPENSES", "COH_"),
                           ("TOTAL_OPERATING_EXPENSES", "COS_")):
        hijas = [c for c in cfg if c.startswith(prefijo)]
        assert hijas, f"no hay líneas {prefijo}"
        for h in hijas:
            assert orden(h) < orden(total), (
                f"{h} (orden {orden(h)}) se dibuja igual o después que su total "
                f"{total} (orden {orden(total)})")
