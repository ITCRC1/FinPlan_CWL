# -*- coding: utf-8 -*-
"""
LA PRUEBA DE ACEPTACIÓN DEL BREAK-EVEN — los nueve números y los catorce totales.

`00_INSTRUCCIONES_PROYECTO.md` la define así: *«Si algún número no cuadra, el
problema está en el código, no en las semillas: ya están validadas contra el P&L
al centavo.»* Esta prueba es esa frase, ejecutable.

## De dónde salen los montos, y por qué NO de la base

Las semillas **no traen monto** — a propósito (spec §8.1): el monto es dato de
periodo y vive en el P&L; la clasificación es atemporal. Así que la aceptación
necesita una tercera pieza: los importes del modelo de referencia.

`tests/fixtures/break_even_montos_cwl.csv` son las **467 líneas del P&L** del
`BREAK_EVEN_CWL.xlsx` (Budget 2025 Dec). Está en el repo para que esta prueba
corra sin base de datos y sin el Excel — que es lo que la hace útil dentro de
cinco meses.

⚠️ **Ningún escenario de FinPlan de hoy tiene estos $4.373.146 de ingreso**
(medido el 2026-08-16 contra los 20 escenarios: el más cercano es
`BUDGET Final 2026` con $4.872.775). El Excel está armado sobre un «Budget 2025
Dec» que el sistema no tiene cargado. Por eso la aceptación se corre contra el
fixture y no contra un escenario vivo: **verifica el MOTOR**, que es lo que el
spec pide. Que el motor lea el P&L real es la capa de integración, y se prueba
aparte.

## La trampa que esta prueba existe para cazar

La semilla tiene **567 filas** y el P&L **467 líneas**: una línea de planilla se
abre en varias cuentas GL hermanas. Sumar fila por fila da **$5.872.331**, un
**+39,9%** sobre los $4.198.042 reales. El motor no puede iterar las REGLAS
sumando montos: itera los MONTOS del P&L y busca su regla. `test_no_cuenta_dos_veces`
lo fija.
"""
import csv
import pathlib
from decimal import Decimal

import pytest

from app.engine import break_even as be

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SEMILLA = RAIZ / "app" / "seed_data" / "CWL" / "break_even" / "be_classification_seed.csv"
MONTOS = RAIZ / "tests" / "fixtures" / "break_even_montos_cwl.csv"

# Los parámetros del modelo de referencia (hoja PARAMETROS / INGRESOS).
REV = Decimal("4373145.56")
REV_ROOMS = Decimal("2123202.61")
ADR = Decimal("493.5156")
ROOMS_AVAILABLE = Decimal("10950")

#: Tolerancia: un dólar. Los números publicados están redondeados a entero.
TOL = Decimal("1")


def _leer(ruta):
    #: utf-8 EXPLÍCITO. En Windows el default es cp1252 y los nombres traen
    #: `Á`, `—`, `·` y `&`: entran corruptos y el match falla en silencio.
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def resultado():
    reglas = [
        be.Regla(
            dept_slug=r["be_department_slug"], dept_code=r["dept_code"],
            account=r["account"], pl_line=r["pl_line"],
            pct_variable=Decimal(r["pct_variable"]),
            map_source=r["map_source"],
            excluded_from_be=r["excluded_from_be"].strip().lower() == "true",
            be_section=r["be_section"], account_name=r["account_name"],
        )
        for r in _leer(SEMILLA)
    ]
    montos = [
        be.Monto(dept_code=m["dept_code"], account=m["account"],
                 pl_line=m["pl_line"], amount=Decimal(m["amount"]))
        for m in _leer(MONTOS)
    ]
    return be.calcular(
        data_version="BUDGET", revenue=REV, revenue_rooms=REV_ROOMS,
        montos=montos, reglas=reglas, adr=ADR, rooms_available=ROOMS_AVAILABLE,
    )


# ─── Los nueve números ────────────────────────────────────────────────────────

@pytest.mark.parametrize("campo,esperado", [
    ("revenue",             Decimal("4373146")),
    ("variable_cost",       Decimal("1469297")),
    ("fixed_cost",          Decimal("2653701")),
    ("contribution_margin", Decimal("2903849")),
    ("ebt",                 Decimal("250148")),
    ("net",                 Decimal("175103")),
    ("be_revenue",          Decimal("3996427")),
])
def test_los_numeros_de_aceptacion(resultado, campo, esperado):
    real = getattr(resultado, campo)
    assert abs(real - esperado) <= TOL, (
        f"{campo}: esperado {esperado:,} · obtenido {real:,.2f} · "
        f"diferencia {real - esperado:,.2f}")


def test_margen_de_contribucion_es_66_4_pct(resultado):
    assert abs(resultado.cm_pct - Decimal("0.664")) < Decimal("0.001")


def test_ocupacion_de_equilibrio_es_35_9_pct(resultado):
    assert abs(resultado.be_occupancy - Decimal("0.359")) < Decimal("0.001")


def test_apalancamiento_operativo_es_11_6(resultado):
    assert abs(resultado.operating_leverage - Decimal("11.6")) < Decimal("0.1")


# ─── Los catorce departamentos, contra el P&L ─────────────────────────────────

DEPARTAMENTOS = {
    "rooms": 474249, "fb": 544907, "spa": 48114, "tours": 293080,
    "gift-shop": 13399, "transportation": 157425, "innoceana": 125478,
    "laundry": 2261, "ag": 616073, "sales-marketing": 433387,
    "maintenance": 476415, "information-system": 41508, "utility": 259233,
    "property-expenses": 712513,
}


@pytest.mark.parametrize("slug,esperado", sorted(DEPARTAMENTOS.items()))
def test_el_costo_por_departamento_cierra_contra_el_pl(resultado, slug, esperado):
    d = resultado.por_departamento.get(slug)
    assert d is not None, f"el departamento {slug} no recibió ni un monto"
    assert abs(d.total_cost - Decimal(esperado)) <= TOL, (
        f"{slug}: esperado {esperado:,} · obtenido {d.total_cost:,.2f}")


def test_el_costo_total_cierra_en_4_198_042(resultado):
    total = sum((d.total_cost for d in resultado.por_departamento.values()),
                Decimal("0"))
    assert abs(total - Decimal("4198042")) <= TOL


# ─── Las reglas que no se negocian ────────────────────────────────────────────

def test_no_cuenta_dos_veces(resultado):
    """567 reglas contra 467 montos.

    Si el motor iterara las REGLAS en vez de los MONTOS, el costo daría
    ~$5.872.331 (+39,9%). Esta prueba es la que caza esa regresión, y lo hace
    por el total, que es donde se nota.
    """
    total = (resultado.variable_cost + resultado.fixed_cost
             + resultado.excluded_cost)
    assert abs(total - Decimal("4198042")) <= TOL, (
        f"el costo total dio {total:,.2f}. Si se parece a 5.872.331, el motor "
        f"está iterando las reglas y contando las cuentas hermanas de más.")


def test_el_impuesto_queda_fuera_del_costo_fijo(resultado):
    """$75.044 de impuesto: resta al neto, NO al costo fijo del equilibrio.

    Si entrara, el equilibrio de CWL sube de $3.996.427 a $4.109.443 — $113k que
    nadie notaría, porque el número sigue pareciendo razonable.
    """
    assert abs(resultado.excluded_cost - Decimal("75044")) <= TOL
    assert abs(resultado.ebt - resultado.net - resultado.excluded_cost) <= TOL


def test_todo_monto_encontro_regla(resultado):
    """Con las semillas completas no debe quedar nada sin clasificar. Si aparece
    algo, se está contando como 100% fijo y el equilibrio sube sin explicación."""
    assert resultado.sin_clasificar == [], [
        (s.dept_code, s.account, s.pl_line) for s in resultado.sin_clasificar]


def test_la_semilla_es_binaria(resultado):
    """Contexto que el spec recalca: la semilla es 100/0, no un diagnóstico.

    Con toda la planilla en 100% variable el margen queda alto y el equilibrio
    bajo. El módulo existe para que el owner mueva esos porcentajes.
    """
    pcts = {Decimal(r["pct_variable"]) for r in _leer(SEMILLA)}
    assert pcts == {Decimal("1.0"), Decimal("0.0")}
