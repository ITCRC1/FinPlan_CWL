# -*- coding: utf-8 -*-
"""Bajar la plantilla y subirla sin tocar nada no puede cambiar NI UN CENTAVO.

Ese es el invariante. Las seis fallas del 2026-10-06 —dos horas del owner— son
todas la misma: la plantilla pliega el departamento y la carga escribía literal.

    4201 vive en 0130, la plantilla lo baja en 0140, la carga crea 0140 y deja
    0130 en cero.

En un mes abierto eso pasa EN SILENCIO —el P&L consolida los dos, el total no se
mueve— y en uno cerrado lo frena el candado. Por eso aparecía de a uno, mes a
mes, y parecía un problema distinto cada vez.

**Y pueden ser varias filas.** Habitaciones tiene cuatro hijos (0111, 0112, 0113,
0114) y los cuatro llevan la 6000. La plantilla los suma en una línea de 0110.
La versión anterior, al ver más de un candidato, no adivinaba: creaba la fila en
el padre y dejaba las cuatro en cero. No adivinar estaba bien; dejarlas en cero
era borrar la misma plata por no elegir.

El reparto por lo que cada fila ya tenía es lo que hace el viaje redondo nulo: si
el archivo devuelve la misma suma, cada fila recibe exactamente lo suyo.
"""
from decimal import Decimal

import pytest

from app.api.scenarios_api import destinos_de_la_fila, repartir_entre_destinos


class _Fila:
    def __init__(self, dept, code, outlet=""):
        self.dept_code = dept
        self.account_code = code
        self.outlet = outlet

    def __repr__(self):
        return f"{self.account_code}@{self.dept_code}"


def _indice(*filas):
    return {(f.dept_code, f.account_code, f.outlet): f for f in filas}


# ── A quién alimenta una línea del archivo ────────────────────────────────────

def test_el_spa_del_0130_lo_reconoce_la_linea_del_0140():
    """El caso del owner, con sus números."""
    hijo = _Fila("0130", "4201")
    dest = destinos_de_la_fila(_indice(hijo), "0140", "4201")
    assert dest == [hijo]


def test_los_cuatro_hijos_de_habitaciones():
    """Una línea de 0110/6000 alimenta a Recepción, Reservas, Ama de llaves y
    Conserjería — no a una sola ni a ninguna."""
    hijos = [_Fila(d, "6000") for d in ("0111", "0112", "0113", "0114")]
    dest = destinos_de_la_fila(_indice(*hijos), "0110", "6000")
    assert {d.dept_code for d in dest} == {"0111", "0112", "0113", "0114"}


def test_el_padre_va_primero():
    """Orden estable: el resto del redondeo tiene que caer siempre en la misma
    fila, o cada carga movería un centavo de sitio."""
    padre = _Fila("0110", "6000")
    hijos = [_Fila("0113", "6000"), _Fila("0111", "6000")]
    dest = destinos_de_la_fila(_indice(padre, *hijos), "0110", "6000")
    assert dest[0] is padre
    assert [d.dept_code for d in dest[1:]] == ["0111", "0113"]


def test_el_criterio_es_UN_escalon_igual_que_la_bajada():
    """`0132` (Spa terapeutas) lo baja la plantilla como `0130`, no como `0140`.

    La versión anterior comparaba con la cadena entera y acertaba con el Spa de
    casualidad: para el 0132 decía 0140, no se reconocía con la línea de 0130, y
    la fila se iba a cero igual.
    """
    f = _Fila("0132", "6000")
    assert destinos_de_la_fila(_indice(f), "0130", "6000") == [f]
    assert destinos_de_la_fila(_indice(f), "0140", "6000") == []


def test_otro_departamento_no_se_toca():
    """Dos departamentos sin parentesco no se mezclan nunca."""
    ajena = _Fila("0120", "7065")
    assert destinos_de_la_fila(_indice(ajena), "0110", "7065") == []


def test_el_outlet_separa():
    """La misma cuenta en dos puntos de venta son dos filas distintas."""
    o1, o2 = _Fila("0120", "4110", "Outlet 1"), _Fila("0120", "4110", "Outlet 2")
    assert destinos_de_la_fila(_indice(o1, o2), "0120", "4110", "Outlet 1") == [o1]


# ── Cuánto le toca a cada uno ────────────────────────────────────────────────

def test_una_sola_fila_se_lleva_todo():
    d = [_Fila("0130", "4201")]
    assert repartir_entre_destinos(d, [Decimal("500")], Decimal("6268.26")) \
        == [Decimal("6268.26")]


def test_el_viaje_redondo_no_mueve_nada():
    """**El invariante.** Si el archivo devuelve la misma suma, cada fila recibe
    exactamente lo que tenía. Es lo que hace que bajar y subir sin tocar nada no
    dispare el candado."""
    d = [_Fila("0111", "6000"), _Fila("0113", "6000")]
    tenian = [Decimal("3000.00"), Decimal("7000.00")]
    partes = repartir_entre_destinos(d, tenian, sum(tenian))
    assert partes == tenian


def test_la_edicion_se_reparte_por_el_peso():
    d = [_Fila("0111", "6000"), _Fila("0113", "6000")]
    partes = repartir_entre_destinos(d, [Decimal("3000"), Decimal("7000")],
                                     Decimal("20000"))
    assert partes == [Decimal("6000.0000"), Decimal("14000.0000")]


def test_la_suma_da_exacta_aunque_no_reparta_redondo():
    """Un tercio no cabe en cuatro decimales: el sobrante cae en la primera.

    Si cada parte se redondeara por su lado, el total del archivo y el de la
    base se separarían por fila y por mes, y el descuadre aparecería meses
    después comparando contra el auxiliar.
    """
    d = [_Fila("0111", "6000"), _Fila("0112", "6000"), _Fila("0113", "6000")]
    monto = Decimal("100")
    partes = repartir_entre_destinos(d, [Decimal("1")] * 3, monto)
    assert sum(partes) == monto


def test_sin_peso_todo_a_la_primera():
    """Todas en cero, o cuenta nueva: no hay historia que respetar."""
    d = [_Fila("0110", "6000"), _Fila("0111", "6000")]
    partes = repartir_entre_destinos(d, [Decimal("0"), Decimal("0")], Decimal("900"))
    assert partes == [Decimal("900"), Decimal("0")]


def test_sin_destinos_no_truena():
    assert repartir_entre_destinos([], [], Decimal("100")) == []


@pytest.mark.parametrize("monto", ["0", "-1500.75", "6268.2590"])
def test_el_total_siempre_se_conserva(monto):
    """Incluido el crédito negativo de un reparto."""
    d = [_Fila("0111", "6000"), _Fila("0112", "6000"), _Fila("0113", "6000")]
    partes = repartir_entre_destinos(d, [Decimal("7"), Decimal("11"), Decimal("13")],
                                     Decimal(monto))
    assert sum(partes) == Decimal(monto)
