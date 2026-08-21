# -*- coding: utf-8 -*-
"""El impuesto de renta, leído POR EL CAMINO DE LA API.

## Por qué existe este archivo

`test_candado_y_renta.py` prueba el MOTOR (`pl_engine.renta_por_mes`). Eso no
alcanza, y se comprobó caro: el motor puede estar bien y el reporte mostrar otra
cosa, porque entre los dos hay una capa —`_aggregate_selected`, que corre
`_apply_tax_correction`— capaz de reescribir el impuesto de una columna después
de que el motor lo escribió. Una verificación hecha sobre el motor da verde
igual. Estas pruebas leen por donde lee el endpoint.

## Las dos reglas que fijan

1. **El signo mensual no se pierde entre el motor y el reporte.** Un mes en
   pérdida devenga un crédito (impuesto negativo) y la columna mensual de la API
   tiene que mostrarlo, no un cero.
2. **En un escenario con el dato SUBIDO no se corrige nada.** Regla del owner:
   «en los históricos solo debe aceptar lo que se sube… nada más».
"""
from app.api.pl_api import _aggregate_selected, _apply_tax_correction, _ebt_anual
from app.engine.pl_engine import PLLineResult


KPIS = {"rooms_available": 0, "rooms_occupied": 0, "guests": 0, "adr": 0.0}

# El perfil real del BUDGET Working 2027 en producción: cinco meses en pérdida
# (mayo, junio, julio, setiembre, octubre — el lodge cierra en octubre).
EBT_2027 = [484495.07, 508995.32, 501161.52, 280013.41, -24535.62, -9631.28,
            -12763.51, 20132.37, -181001.48, -342246.09, 191602.28, 447495.83]
TASA = 0.30


def _mes(mes: int, ebt: float, impuesto: float) -> dict:
    """Un mes tal como lo entrega el motor a `_aggregate_selected`."""
    return {"month": mes, "kpis": dict(KPIS), "lines": [
        PLLineResult("EBT", "EBT", "EBT", ebt),
        PLLineResult("INCOME_TAXES", "Income Taxes", "EBT", impuesto),
        PLLineResult("NET_PROFIT", "Net Profit", "NET_PROFIT", ebt - impuesto),
    ]}


def _año(ebts=EBT_2027) -> list[dict]:
    """Los doce meses con la renta que produce el criterio vigente."""
    anual = sum(ebts)
    renta = [e * TASA for e in ebts] if anual > 0 else [0.0] * len(ebts)
    return [_mes(i, e, t) for i, (e, t) in enumerate(zip(ebts, renta), 1)]


def _linea(col: dict, code: str) -> float:
    for ln in col["lines"]:
        if ln["line_code"] == code:
            return float(ln["amount_usd"])
    return 0.0


# ─── 1. El signo mensual sobrevive al reporte ─────────────────────────────────
def test_la_columna_mensual_de_la_api_conserva_el_credito():
    """Mayo da pérdida: la API tiene que mostrar -7.360,69, no 0,00.

    Es el número exacto de producción, y es el que se perdía: el reporte mostraba
    cero y el mes en pérdida aparecía sin efecto fiscal."""
    meses = _año()
    col = _aggregate_selected([meses[4]])            # mayo, como lo pide el endpoint
    assert _linea(col, "EBT") < 0
    assert _linea(col, "INCOME_TAXES") == -7360.69
    assert _linea(col, "NET_PROFIT") == -17174.93


def test_cada_mes_paga_el_30_de_su_ebt_en_la_api():
    """Y no el 23% que salía cuando el anual se prorrateaba entre los meses con
    ganancia. Se comprueba en LOS DOCE, con signo."""
    for m in _año():
        col = _aggregate_selected([m])
        ebt, imp = _linea(col, "EBT"), _linea(col, "INCOME_TAXES")
        assert abs(imp - ebt * TASA) < 0.01, f"mes {m['month']} no paga el 30% de SU EBT"


def test_el_anual_de_la_api_es_el_30_del_ebt_del_ano():
    meses = _año()
    col = _aggregate_selected(meses)
    assert abs(_linea(col, "INCOME_TAXES") - sum(EBT_2027) * TASA) < 0.01
    assert abs(_linea(col, "INCOME_TAXES") - 559115.34) < 0.02   # producción


def test_el_ytd_parcial_no_se_reescribe():
    """Una ventana YTD suma lo que sumó el motor; la corrección no debe meterse
    solo porque la ventana da positivo."""
    meses = _año()
    col = _aggregate_selected(meses[:7], ebt_anual=_ebt_anual(meses))
    crudo = sum(_linea(_aggregate_selected([m]), "INCOME_TAXES") for m in meses[:7])
    assert abs(_linea(col, "INCOME_TAXES") - crudo) < 0.02


# ─── 2. El borde: el año que no paga ──────────────────────────────────────────
def test_en_un_ano_en_perdida_ninguna_ventana_muestra_impuesto():
    """El ejercicio cierra en pérdida → impuesto cero. Entonces NINGUNA columna
    suya puede mostrar renta, ni un mes con ganancia ni un YTD parcial positivo.

    Antes sí: la corrección veía una ventana con EBT>0 y sin impuesto, y le
    pintaba el 30% — un cargo de un año que no paga."""
    ebts = list(EBT_2027)
    ebts[0] = -2500000.0                     # el año entero se hunde
    meses = _año(ebts)
    anual = _ebt_anual(meses)
    assert anual < 0
    for etiqueta, sel in (("mes 2", [meses[1]]), ("YTD 2-4", meses[1:4]),
                          ("AÑO", meses)):
        col = _aggregate_selected(sel, ebt_anual=anual)
        assert _linea(col, "INCOME_TAXES") == 0.0, f"{etiqueta} cobra renta de un año en pérdida"


# ─── 3. Lo subido manda ───────────────────────────────────────────────────────
def test_un_escenario_importado_no_se_corrige():
    """Regla del owner: «en los históricos solo debe aceptar lo que se sube, nada
    más». El caso real es el FORECAST April 2026: el snapshot trae $39.197,30 de
    impuesto sobre un EBT de -$992,48. Se ve raro, pero es lo que se subió, y
    corregirlo en silencio es inventar un número que nadie contabilizó. El
    arreglo va en el archivo de origen, no acá."""
    mes = _mes(1, -992.48, 39197.30)
    col = _aggregate_selected([mes], lo_subido_manda=True)
    assert _linea(col, "INCOME_TAXES") == 39197.30
    assert abs(_linea(col, "NET_PROFIT") - (-992.48 - 39197.30)) < 0.01


def test_sin_la_bandera_ese_mismo_dato_si_se_corrige():
    """El contraste, para que la prueba de arriba pruebe algo: el mismo dato, en
    un escenario CALCULADO, sí se repara (no se paga renta sobre una pérdida)."""
    mes = _mes(1, -992.48, 39197.30)
    col = _aggregate_selected([mes], lo_subido_manda=False)
    assert _linea(col, "INCOME_TAXES") == 0.0


def test_lo_subido_manda_mira_source_mode_y_tambien_los_datos():
    """Un escenario en modo `imported` pero VACÍO lo calcula el motor desde los
    checkbooks (es el caso de los presupuestos 2028-2035). Tratarlo como
    histórico le congelaría un impuesto que nadie subió.

    El veredicto se mudó al motor (`recalculate.lo_subido_manda`) porque la
    MISMA pregunta decide si el recálculo puede pisar los auxiliares.
    `pl_api._lo_subido_manda` quedó como alias, así que se inspecciona el
    original."""
    import inspect
    from app.engine import recalculate as recalc
    from app.api import pl_api
    assert pl_api._lo_subido_manda is not None
    src = inspect.getsource(recalc.lo_subido_manda)
    assert "checkbook" in src, "no mira source_mode"
    assert ("actual_pl_lines_for_month" in src and "actual_rows_for_month" in src), (
        "no comprueba que el escenario TENGA datos subidos: un escenario "
        "'imported' vacío lo calcula el motor y no puede tratarse como histórico")


def test_el_endpoint_le_pregunta_a_lo_subido_manda():
    """Si alguien saca el veredicto de los endpoints, la corrección vuelve a
    correr sobre los históricos y nada avisa."""
    import inspect
    from app.api import pl_api
    for fn in (pl_api.get_pl_monthly, pl_api.get_pl_ytd, pl_api.get_pl_compare):
        src = inspect.getsource(fn)
        assert "_lo_subido_manda" in src, (
            f"{fn.__name__} arma columnas sin preguntar si manda lo subido")
