# -*- coding: utf-8 -*-
"""
HACIA DÓNDE MUEVE EL EQUILIBRIO AJUSTAR UN PORCENTAJE.

El pendiente 1 del módulo (`docs/PENDIENTES.md` A0.-10) dice que la semilla
100/0 «no es un diagnóstico» y que al marcar la planilla como fija —que es lo
que es en CWL, personal de planta— **el equilibrio va a subir de forma
material**. Medido contra producción, eso es cierto en dos escenarios y
**falso en el tercero**: en el `ACTUAL 2025` el mismo ajuste lo hace **bajar**
$925.541.

No es una contradicción, es una identidad que conviene tener escrita, porque
del lado equivocado un ajuste correcto se lee como una mejora:

    BE = F·R / (R − V)

Mover `d` de variable a fijo sube `F` y sube el margen a la vez. Sale:

    BE' > BE  ⟺  (F+d)(R−V) > F(R−V+d)  ⟺  R − V > F  ⟺  **EBT > 0**

O sea: **el signo del efecto es el signo del resultado**. Con utilidad,
reclasificar a fijo SUBE el equilibrio; con pérdida, lo BAJA — y ahí un ajuste
que endurece los supuestos aparece en pantalla como una buena noticia.

Verificado con los tres escenarios vivos (ver `scripts/mover_los_porcentajes`):

| escenario | EBT | mover TODA la planilla a fija |
|---|---|---|
| `BUDGET Final 2026` | +18.898 | sube 8.087 |
| `BUDGET Working 2027` | +2.882.508 | sube 431.495 |
| `ACTUAL 2025` | −1.125.864 | **baja 925.541** |
"""
from decimal import Decimal

import pytest

from app.engine import break_even as be

D = Decimal


def _escenario(revenue, variable, fijo):
    """Un caso mínimo: una regla variable y una fija, con montos conocidos."""
    reglas = [
        be.Regla("rooms", "0110", "6000", "OPEX_ROOMS", D("1")),   # variable
        be.Regla("rooms", "0110", "7000", "OPEX_ROOMS", D("0")),   # fija
    ]
    montos = [
        be.Monto("0110", "6000", "OPEX_ROOMS", D(variable)),
        be.Monto("0110", "7000", "OPEX_ROOMS", D(fijo)),
    ]
    return be.calcular(data_version="BUDGET", revenue=D(revenue),
                       montos=montos, reglas=reglas)


def _reclasificado(revenue, variable, fijo, d):
    """El mismo escenario con `d` movido de variable a fijo."""
    return _escenario(revenue, str(D(variable) - D(d)), str(D(fijo) + D(d)))


# ─── La identidad, en los tres signos posibles del resultado ─────────────────

@pytest.mark.parametrize("etq,revenue,variable,fijo", [
    # EBT > 0: R−V = 3.074.131 > F = 3.055.233, apenas
    ("BUDGET Final 2026", "4872775", "1798644", "3055233"),
    # EBT > 0 con holgura
    ("BUDGET Working 2027", "6374026", "1133376", "2358142"),
])
def test_con_utilidad_pasar_costo_a_fijo_SUBE_el_equilibrio(
        etq, revenue, variable, fijo):
    antes = _escenario(revenue, variable, fijo)
    despues = _reclasificado(revenue, variable, fijo, "100000")
    assert antes.ebt > 0, etq
    assert despues.be_revenue > antes.be_revenue, etq


def test_con_perdida_pasar_costo_a_fijo_BAJA_el_equilibrio():
    """`ACTUAL 2025`, que es el caso que rompe la frase del documento.

    Endurecer los supuestos —marcar fija la planilla que es de planta— hace que
    el equilibrio **baje** $137k en esta muestra. Quien lea solo el número va a
    creer que el hotel quedó más cerca del equilibrio, y lo que pasó es que el
    escenario pierde plata.
    """
    antes = _escenario("3093799", "1550506", "2669220")
    despues = _reclasificado("3093799", "1550506", "2669220", "100000")
    assert antes.ebt < 0
    assert despues.be_revenue < antes.be_revenue


def test_en_el_equilibrio_exacto_reclasificar_no_mueve_nada():
    """`EBT = 0` es el punto de giro: ahí el ajuste es neutro, y es lo que
    prueba que el umbral es el resultado y no una casualidad de los montos."""
    # R − V = F  ⟹  1.000.000 − 400.000 = 600.000
    antes = _escenario("1000000", "400000", "600000")
    despues = _reclasificado("1000000", "400000", "600000", "50000")
    assert antes.ebt == 0
    assert despues.be_revenue == antes.be_revenue == antes.revenue


def test_el_costo_total_no_se_mueve_al_reclasificar():
    """La contracautela: reclasificar reparte, **no crea ni destruye costo**.
    Si esta se cae, el efecto medido arriba no es de la reclasificación."""
    antes = _escenario("4872775", "1798644", "3055233")
    despues = _reclasificado("4872775", "1798644", "3055233", "100000")
    assert (antes.variable_cost + antes.fixed_cost
            == despues.variable_cost + despues.fixed_cost)
    assert antes.ebt == despues.ebt
