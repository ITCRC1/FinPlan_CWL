# -*- coding: utf-8 -*-
"""
EL TRADUCTOR TIENE QUE DAR LO MISMO QUE EL EXCEL DEL OWNER.

`app/importers/integrity_final.py` reemplaza las fórmulas que hoy se escriben a
mano cada mes en la hoja `Final` del libro de cierre. La prueba de que son
equivalentes no es leerlas: es correr el archivo de un mes ya cerrado y validado
—julio 2026— y comprobar que salen los mismos números.

El fixture `integrity_final_JUL2026.xlsx` trae SÓLO las columnas A–U, que es lo
que Integrity entrega. Que la prueba pase con eso demuestra que el traductor no
depende de ninguna de las columnas que el owner agrega a mano.
"""
import io
import json
import pathlib
from collections import defaultdict
from decimal import Decimal as D

import pytest

from app.importers import integrity_final as m

BASE = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = BASE / "tests" / "fixtures" / "integrity_final_JUL2026.xlsx"
SEMILLA = BASE / "app" / "seed_data" / "CWL" / "mapd_integrity.json"

#: El tipo de cambio de julio 2026, tal como está en `Final!AD11` del libro.
TC_JULIO = D("454.75")

#: Las divisiones que NO son departamentos operativos. Es la agrupación USALI que
#: usa el propio libro para partir «gasto operativo» de «overhead».
OVERHEAD = {"Administrative & General", "Sales & Marketing",
            "Property Operation & Maintenance", "Utilities", "Cafeteria",
            "Information & Telecommunications Systems", "Laundry (Overhead)",
            "Property Expenses"}


@pytest.fixture(scope="module")
def mapd() -> dict:
    d = json.loads(SEMILLA.read_text(encoding="utf-8"))
    return {x["codigo"]: x for x in d["departamentos"]}


@pytest.fixture(scope="module")
def julio(mapd) -> dict:
    return m.leer(FIXTURE.read_bytes(), TC_JULIO, mapd)


@pytest.fixture(scope="module")
def por_categoria(julio) -> dict:
    acc = defaultdict(D)
    for f in julio["filas"]:
        acc[f["categoria"]] += f["mes_usd"]
    return acc


# ═════════════════════════════════════════════════════════════════════════════
# LA PRUEBA DE ORO — julio 2026, un mes ya cerrado y revisado por el owner
# ═════════════════════════════════════════════════════════════════════════════

def test_ingresos_totales(por_categoria):
    assert abs(por_categoria["Ingresos"] - D("248437.33")) < D("0.02")


def test_gasto_operativo(julio):
    """Los departamentos operativos, sin overhead y sin la clase 8."""
    t = sum((f["mes_usd"] for f in julio["filas"]
             if f["categoria"] not in ("Ingresos", "No Operativo")
             and f["division_usali"] not in OVERHEAD), D(0))
    assert abs(t - D("147248.79")) < D("0.02")


def test_overhead(julio):
    t = sum((f["mes_usd"] for f in julio["filas"]
             if f["categoria"] not in ("Ingresos", "No Operativo")
             and f["division_usali"] in OVERHEAD), D(0))
    assert abs(t - D("178789.87")) < D("0.02")


def test_utilidad_neta(por_categoria):
    """La línea de abajo. Si ésta cuadra, la cascada entera cuadra."""
    gastos = sum((por_categoria[c] for c in
                  ("Costo de Ventas", "Nómina", "Otros Gastos", "No Operativo",
                   "Allocation")), D(0))
    assert abs((por_categoria["Ingresos"] - gastos) - D("-94182.95")) < D("0.02")


def test_la_clase_8_completa_es_la_suma_de_sus_cinco_baldes(por_categoria):
    """La verificación parte la clase 8 en no operativo · capital · financieros ·
    depreciación · impuesto. Juntos tienen que dar el total de la clase."""
    baldes = D("18664.70") + D("9937.63") + D("0") + D("28343.41") + D("-40364.12")
    assert abs(por_categoria["No Operativo"] - baldes) < D("0.02")


def test_ningun_departamento_quedo_sin_mapeo(julio):
    """Si aparece uno, su plata no llega a ningún departamento."""
    assert julio["sin_mapeo"] == [], (
        "departamentos sin mapear: "
        + str([(x["depto"], float(x["mes_usd"])) for x in julio["sin_mapeo"]]))


# ═════════════════════════════════════════════════════════════════════════════
# LAS REGLAS, UNA POR UNA
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cuenta,esperado", [
    ("4000-0110", -1),      # ingreso: baja como crédito, se da vuelta
    ("4999-0110", 1),       # allocation: ya viene con el signo bueno
    ("5000-0120", 1),
    ("7000-0180", 1),
    ("8000-0240", 1),
])
def test_signo_por_clase(cuenta, esperado):
    assert m.signo_de(cuenta) == esperado


def test_el_signo_del_mes_lo_decide_el_acumulado():
    """Integrity da el mes en valor absoluto: sin mirar el acumulado, un ingreso
    y un gasto del mismo monto son indistinguibles."""
    assert m.monto_mes("4000-0110", 100, -500) == D("100")    # ingreso, se invierte
    assert m.monto_mes("4000-0110", 100, 500) == D("-100")
    assert m.monto_mes("7000-0180", 100, 500) == D("100")     # gasto, tal cual


@pytest.mark.parametrize("cuenta,esperado", [
    ("4000-0110", 4000),        # depto: SÍ se mapea
    ("4000", None),             # clase sola: no
    ("4000-0110-001", None),    # subdetalle: ya está sumado en el padre
    ("", None),
    ("no-es-cuenta", None),
])
def test_solo_las_cuentas_de_dos_segmentos_entran(cuenta, esperado):
    """La trampa que contaría la plata tres veces."""
    assert m.cuenta_base(cuenta) == esperado


def test_el_subdetalle_no_se_suma_dos_veces(julio):
    """Ninguna fila mapeada puede tener dos guiones."""
    assert not [f for f in julio["filas"] if f["cuenta"].count("-") != 1]


@pytest.mark.parametrize("cuenta,esperado", [
    ("4999-0110", "Allocation"), ("4000-0110", "Ingresos"),
    ("5000-0120", "Costo de Ventas"), ("6000-0110", "Nómina"),
    ("7000-0180", "Otros Gastos"), ("8000-0240", "No Operativo"),
    ("4000-0110-001", ""),
])
def test_categoria_usali(cuenta, esperado):
    assert m.categoria_usali(cuenta) == esperado


def test_depto_se_saca_de_la_cuenta():
    assert m.depto_de("4000-0110") == "0110"
    assert m.depto_de("4000-0110-001") == ""


# ── El tipo de cambio ────────────────────────────────────────────────────────

def test_el_tipo_de_cambio_es_obligatorio(mapd):
    """No se deduce del archivo. Inventarlo pondría todo el P&L a un TC que
    nadie decidió, y cuadraría igual."""
    with pytest.raises(ValueError):
        m.leer(FIXTURE.read_bytes(), None, mapd)


@pytest.mark.parametrize("tc", [0, -1, D("0")])
def test_un_tipo_de_cambio_invalido_no_pasa(tc):
    with pytest.raises(ValueError):
        m.a_dolares(D("1000"), tc)


def test_la_conversion_es_la_del_libro():
    """Fila 16 de julio: 47.911.719,75 colones / 454,75 = US$105.358,37."""
    crc = m.monto_mes("4000-0110", 47911719.75, -47911719.75)
    assert abs(m.a_dolares(crc, TC_JULIO) - D("105358.37")) < D("0.01")


# ── Números «sumables y legibles» ────────────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    ("1,234.50", D("1234.50")),
    ("(1,234.50)", D("-1234.50")),      # negativo entre paréntesis
    ("$ 1,234.50", D("1234.50")),
    ("", D("0")), (None, D("0")), ("-", D("0")),
    (1234.5, D("1234.5")),
])
def test_texto_a_numero(crudo, esperado):
    assert m._dec(crudo) == esperado


# ── El formato falla ruidoso ─────────────────────────────────────────────────

def test_una_hoja_sin_los_encabezados_no_se_adivina():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Final"
    wb.active["A1"] = "otra cosa"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(m.FormatoInesperado) as e:
        m.leer(buf.getvalue(), TC_JULIO, {})
    assert "Mes Actual" in str(e.value)


def test_un_archivo_sin_la_hoja_Final_dice_que_hojas_trae():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.active.title = "Otra"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(m.FormatoInesperado) as e:
        m.leer(buf.getvalue(), TC_JULIO, {})
    assert "Otra" in str(e.value)


def test_los_encabezados_se_ubican_por_texto_no_por_posicion(julio):
    """Si Integrity agrega un renglón de título, buscar por número de fila leería
    la columna de al lado y el total seguiría cuadrando."""
    cols = julio["columnas"]
    assert cols["fila_encabezado"] == 10      # fila 11 en julio 2026
    assert cols["cuenta"] == 3                # D
    assert cols["mes"] == 17                  # R
    assert cols["acumulado"] == 20            # U


def test_un_depto_sin_mapeo_se_reporta_con_su_monto(mapd):
    """No se adivina y no se descarta en silencio: se dice cuánta plata es."""
    recortado = {k: v for k, v in mapd.items() if k != "0110"}
    r = m.leer(FIXTURE.read_bytes(), TC_JULIO, recortado)
    faltan = {x["depto"] for x in r["sin_mapeo"]}
    assert "0110" in faltan
    assert any(x["mes_usd"] != 0 for x in r["sin_mapeo"] if x["depto"] == "0110")
