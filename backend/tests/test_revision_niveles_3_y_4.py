# -*- coding: utf-8 -*-
"""
NIVEL 3 · contra las otras fuentes  ·  NIVEL 4 · contra lo que se esperaba.

Los niveles 1 y 2 miran el archivo por dentro. Éstos lo cruzan con lo que el
sistema sabe por otro camino, y con lo que se había planeado.

La prueba de verdad del nivel 4 corre contra el P&L REAL de julio 2026 de los
tres escenarios de producción (`pl_julio2026_escenarios.json`): así se comprueba
que las líneas de un escenario se traducen bien a las claves de la hoja, que es
lo que también llena las columnas Forecast y Budget.
"""
import json
import pathlib
from decimal import Decimal as D

import pytest

from app.export import revision_mes_xlsx as rev
from app.revision import nivel3_fuentes as n3
from app.revision import nivel4_expectativa as n4

BASE = pathlib.Path(__file__).resolve().parents[1]
ESCENARIOS = BASE / "tests" / "fixtures" / "pl_julio2026_escenarios.json"


@pytest.fixture(scope="module")
def bloques() -> dict:
    return json.loads(ESCENARIOS.read_text(encoding="utf-8"))["bloques"]


@pytest.fixture(scope="module")
def valores(bloques) -> dict:
    return {k: rev._totales(rev.valores_desde_lineas_pl(v["lineas"]))
            for k, v in bloques.items()}


def fila(cuenta="6000-0110", base=6000, destino="0110", mes=1000):
    return {"fila": 20, "cuenta": cuenta, "cuenta_base": base, "depto": destino,
            "destino_finplan": destino, "grupo": "ROOMS", "categoria": "Nómina",
            "descripcion": "x", "mes_usd": D(str(mes)),
            "acumulado_usd": D(str(mes))}


# ═════════════════════════════════════════════════════════════════════════════
# LA TRADUCCIÓN DE UN ESCENARIO A LAS CLAVES DE LA HOJA
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("rol,clave,esperado", [
    # Contra la columna del tab del owner, julio 2026.
    ("FORECAST", "rev.Rooms", "133920.00"),
    ("FORECAST", "rev.Tours", "26855.61"),
    ("FORECAST", "opex.Transportation", "13569.46"),   # daba CERO con `TRANSPORT`
    ("FORECAST", "bg.DEPRECIATION", "26583.33"),       # se contaba DOS veces
    ("BUDGET", "rev.Rooms", "188045.45"),
    ("BUDGET", "rev.F&B", "72322.96"),                 # REV_FB + REV_FB_BEV
    ("BUDGET", "opex.F&B", "45274.32"),                # OPEX_FB + los dos COS_FB_*
    ("BUDGET", "oh.Administrations", "56811.53"),      # OH_ADMIN + CC_COMMISSIONS
    ("BUDGET", "oh.Cafeteria", "0"),                   # OH_CAFETERIA + COH_CAFETERIA
])
def test_las_lineas_del_escenario_dan_lo_que_dice_el_tab(valores, rol, clave, esperado):
    assert abs(valores[rol][clave] - D(esperado)) < D("0.06")


def test_no_se_mezclan_los_dos_vocabularios(bloques):
    """Un escenario emite `REV_TRANSPORT` (motor viejo) y `REV_TRANSPORTATION`
    (canónico). Sumar los dos contaría la plata dos veces."""
    lineas = bloques["FORECAST"]["lineas"]
    assert "REV_TRANSPORT" in lineas and "REV_TRANSPORTATION" in lineas
    v = rev.valores_desde_lineas_pl(lineas)
    assert abs(v["rev.Transportation"] - D("11118.28")) < D("0.02")


def test_el_forecast_de_produccion_todavia_no_trae_OPERATING_PROFIT(bloques):
    """El bug del commit 9875685, sin aplicar en producción al 2026-09-01.

    Sus `PROFIT_*` sí están y suman 94.062,52 — que es justo lo que el arreglo
    deriva. Esta prueba documenta el estado; cuando IT aplique el parche va a
    fallar, y ahí se saca.
    """
    lineas = bloques["FORECAST"]["lineas"]
    assert "OPERATING_PROFIT" not in lineas
    suma = sum((D(str(v)) for k, v in lineas.items()
                if k.startswith("PROFIT_")), D(0))
    assert abs(suma - D("94062.52")) < D("0.02")


# ═════════════════════════════════════════════════════════════════════════════
# NIVEL 4 · VARIANZAS
# ═════════════════════════════════════════════════════════════════════════════

def test_hacen_falta_LOS_DOS_umbrales():
    """Mucha plata pero poco porcentaje no entra; mucho porcentaje pero poca
    plata tampoco."""
    grande_pero_chico = n4.comparar({"rev.Rooms": D("206000")},
                                    {"rev.Rooms": D("200000")}, "Budget")
    assert grande_pero_chico == [], "6.000 sobre 200.000 es 3%: no es un desvío"
    chico_pero_grande = n4.comparar({"rev.SPA": D("140")}, {"rev.SPA": D("40")},
                                    "Budget")
    assert chico_pero_grande == [], "100 dólares no importan aunque sean 250%"
    los_dos = n4.comparar({"rev.SPA": D("26000")}, {"rev.SPA": D("20000")},
                          "Budget")
    assert len(los_dos) == 1


def test_el_porcentaje_lleva_el_signo_de_la_diferencia():
    """Con el valor absoluto, una caída se mostraba «+21%» y se leía como que
    había subido."""
    h = n4.comparar({"rev.Rooms": D("105358")}, {"rev.Rooms": D("133920")},
                    "Forecast")
    assert h[0].referencias[0]["pct"] < 0


def test_lo_que_el_comparativo_tiene_en_cero_es_su_propio_hallazgo():
    """Dividir por cero no dice nada, y «apareció algo que nadie presupuestó» es
    justo lo que hay que mirar."""
    h = n4.comparar({"rev.Innoceana": D("10975")}, {"rev.Innoceana": D("0")},
                    "Forecast")
    assert len(h) == 1 and h[0].clave == "sin_comparativo_forecast"
    assert h[0].monto == D("10975")


def test_los_totales_no_se_comparan():
    """Reportarlos duplicaría cada desvío: una vez en la línea y otra en su
    total."""
    h = n4.comparar({"TOTAL INCOMES": D("100000"), "EBITDA": D("-90000")},
                    {"TOTAL INCOMES": D("200000"), "EBITDA": D("10000")},
                    "Budget")
    assert h == []


def test_sin_comparativo_no_hay_varianzas():
    assert n4.revisar({"rev.Rooms": D("1")}) == []


def test_las_varianzas_de_julio_contra_el_forecast(valores):
    """Contra los escenarios de producción: la caída de Rooms tiene que estar
    arriba de todo."""
    h = n4.comparar(valores["ACTUAL"], valores["FORECAST"], "Forecast")
    grandes = [x for x in h if x.clave == "varianza_forecast"][0]
    primera = grandes.referencias[0]
    assert primera["linea"] == "Ingreso · Rooms"
    assert abs(D(str(primera["diferencia"])) - D("-28561.63")) < D("1")


# ═════════════════════════════════════════════════════════════════════════════
# NIVEL 3 · CONTRA LAS OTRAS FUENTES
# ═════════════════════════════════════════════════════════════════════════════

def test_la_planilla_que_no_cuadra_con_el_mayor():
    h = n3.planilla_vs_mayor([fila(mes=1000)], {"0110": D("900")})
    assert h[0].clave == "planilla_no_cuadra" and h[0].monto == D("100")


def test_si_la_planilla_cuadra_no_hay_hallazgo():
    assert n3.planilla_vs_mayor([fila(mes=1000)], {"0110": D("1000")}) == []


def test_un_departamento_que_el_auxiliar_no_conoce_no_se_juzga():
    """No tener una fila en el auxiliar no es decir que sea cero: es no decir
    nada. Sólo se juzgan los departamentos que el auxiliar SÍ conoce."""
    # El mayor tiene 0110 con 1.000 y el auxiliar sólo habla de 0180 → el 0110
    # no se juzga; el 0180, que el auxiliar dice 1.000 y el mayor no tiene, sí.
    h = n3.planilla_vs_mayor([fila(mes=1000)], {"0180": D("1000")})
    assert [x["depto"] for x in h[0].referencias] == ["0180"]

    # Sin auxiliar no hay nada contra qué cruzar.
    assert n3.planilla_vs_mayor([fila(mes=1000)], {}) == []

    # El auxiliar dice que 0110 es cero y el mayor tiene 1.000: eso SÍ se juzga.
    h2 = n3.planilla_vs_mayor([fila(mes=1000)], {"0110": D("0")})
    assert h2 and h2[0].monto == D("1000")


def test_el_checkbook_de_gastos_contra_el_mayor():
    f = fila(cuenta="7400-0180", base=7400, destino="0180", mes=500)
    h = n3.opex_vs_mayor([f], {"0180": D("450")})
    assert h[0].clave == "opex_no_cuadra" and h[0].monto == D("50")


@pytest.mark.parametrize("stats,espera", [
    ({"rooms_disponibles": 930, "rooms_ocupadas": 233, "huespedes": 518}, False),
    ({"rooms_disponibles": 930, "rooms_ocupadas": 1200, "huespedes": 1500}, True),
    ({"rooms_disponibles": 930, "rooms_ocupadas": 233, "huespedes": 100}, True),
    ({}, False),
])
def test_estadisticas_imposibles(stats, espera):
    """Son imposibles aritméticas, no diferencias de criterio."""
    assert bool(n3.estadisticas_coherentes(stats)) is espera


def test_un_adr_fuera_de_rango_se_reporta():
    """Julio real: 105.358,37 / 233 = 452 por noche, que es razonable."""
    ok = n3.estadisticas_coherentes(
        {"rooms_disponibles": 930, "rooms_ocupadas": 233, "huespedes": 518},
        ingreso_habitaciones=D("105358.37"))
    assert ok == []
    mal = n3.estadisticas_coherentes(
        {"rooms_disponibles": 930, "rooms_ocupadas": 233, "huespedes": 518},
        ingreso_habitaciones=D("10535837"))
    assert mal and "ADR" in mal[0].detalle


def test_las_noches_contra_opera():
    h = n3.rooms_vs_opera({"rooms_ocupadas": 233}, 267)
    assert h[0].clave == "rooms_no_cuadra_con_opera" and h[0].monto == D("-34")
    assert n3.rooms_vs_opera({"rooms_ocupadas": 233}, 233) == []
    assert n3.rooms_vs_opera({"rooms_ocupadas": 233}, None) == []


def test_todo_hallazgo_de_estos_niveles_explica_por_que():
    todos = (n3.planilla_vs_mayor([fila(mes=1000)], {"0110": D("1")})
             + n3.estadisticas_coherentes({"rooms_disponibles": 1,
                                           "rooms_ocupadas": 9, "huespedes": 9})
             + n3.rooms_vs_opera({"rooms_ocupadas": 1}, 99)
             + n4.comparar({"rev.SPA": D("26000")}, {"rev.SPA": D("20000")}, "Budget"))
    assert todos
    for h in todos:
        assert h.porque and h.que_hacer, h.clave
        assert h.nivel in (3, 4)
        assert h.gravedad in ("critico", "aviso", "info")
