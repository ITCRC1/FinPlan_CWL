# -*- coding: utf-8 -*-
"""LOS DOS NIVELES DE TOTAL SE TIENEN QUE DISTINGUIR SIN LEER EL TEXTO.

Owner, 2026-09-10: *«bordes y sombras a cada subtotal, un poco tenue, pero el
total de departamento mas visible, grueso, coloreado»*.

En un cuadro de cientos de filas —Opex x Detalle y Payroll x Posicion lo son—
los subtotales son la unica forma de leerlo sin contar renglones. El de cuenta
SEPARA; el de departamento se busca de lejos. Si los dos gritaran igual,
ninguno de los dos serviria.

El estilo vive en UN lugar y los dos tabs lo usan: dos cuadros que muestran lo
mismo con distinto peso visual se leen como si dijeran cosas distintas.
"""
import io
import os
import re

PANTALLA = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                        "app", "month-end", "pl", "Pantalla.tsx")


def _src() -> str:
    return io.open(PANTALLA, encoding="utf-8").read()


def test_el_estilo_esta_declarado_una_sola_vez():
    src = _src()
    assert src.count("const SUBTOTAL_CUENTA: React.CSSProperties") == 1
    assert src.count("const TOTAL_DEPTO: React.CSSProperties") == 1


def test_el_subtotal_de_cuenta_es_tenue_y_el_de_depto_no():
    """Lo que los distingue: grosor del borde, sombra y color."""
    src = _src()
    sub = src[src.index("const SUBTOTAL_CUENTA"):src.index("const TOTAL_DEPTO")]
    dep = src[src.index("const TOTAL_DEPTO"):]
    dep = dep[:dep.index("};") + 2]

    # El de cuenta: borde fino y sombra hacia adentro — separa sin gritar.
    assert '"1px solid var(--border-medium)"' in sub
    assert "inset" in sub
    assert "var(--brand)" not in sub, "el subtotal de cuenta no lleva color de marca"

    # El de departamento: borde grueso, sombra propia y color.
    assert '"2px solid var(--brand)"' in dep
    assert "boxShadow" in dep and "inset" not in dep
    assert "color: \"var(--brand)\"" in dep


def test_los_dos_tabs_usan_el_mismo_estilo():
    """Opex x Detalle y Payroll x Posicion son el mismo cuadro con otro dato."""
    src = _src()
    assert src.count("<tr style={TOTAL_DEPTO}>") == 2
    assert src.count("<tr style={SUBTOTAL_CUENTA}>") == 2


def test_ningun_total_quedo_con_el_estilo_viejo():
    """El fondo pelado sin borde ni sombra era lo que habia antes: si vuelve a
    aparecer en estos dos cuadros, es un total que dejo de distinguirse."""
    src = _src()
    i = src.index('vista === "gastoDetalle"')
    j = src.index('vista === "planillaCuentas"')
    bloques = src[min(i, j):max(i, j)]
    sueltos = re.findall(r'<tr style=\{\{ background: "var\(--bg-elevated\)" \}\}>',
                         bloques)
    assert sueltos == [], f"quedo un total con el estilo viejo: {len(sueltos)}"
