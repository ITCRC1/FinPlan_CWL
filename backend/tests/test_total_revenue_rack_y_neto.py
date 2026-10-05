# -*- coding: utf-8 -*-
"""Total Revenue: primero a tarifa RACK, despues NETO, y el % de ocupacion.

Owner, 2026-10-04: *«necesito poder ver total revenue tarifa rack, y despues
TOTAL REVENUE POR TIPO HABITACION NET RATE Y TODO LO QUE SIGUE DE LAS
ESTADISTICAS»* · *«METE % DE OCUPACION QUE NO ESTA»*.

## Por que los dos

El de RACK es lo que se le cobra al huesped; el NETO es lo que queda despues de
la comision del canal, y es el unico que mueve el P&L. Con uno solo, la comision
—266.077 dolares en el Budget Working 2027, el 16,8% del rack— no se ve en
ninguna pantalla: hay que ir a Canales de Venta, leer el mix y hacer la cuenta.

## ⚠️ Un solo renderizador para los dos bloques

Son la misma tabla con otra cifra adentro. Escritos dos veces, el dia que
alguien agregue una fila al pie la agrega en uno y el otro queda distinto — y
dos tablas que se leen una debajo de la otra tienen que verse iguales o la
comparacion engaña.

## Medido contra produccion

Reproducido el Budget Working 2027 desde los datos de produccion —rack rates,
mix de canales y ocupacion— el bloque NETO da exactamente lo que la pantalla
mostraba antes de este cambio: 1.322.441 al año, 2.666 noches, 5.840
disponibles, ADR 496,00 y RevPAR 226,45, y las cuatro categorias al dolar. El
bloque RACK da 1.588.518.
"""
import pathlib

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
PAGINA = FRONT / "app/revenue/total-revenue/page.tsx"
BLOQUE = FRONT / "app/revenue/total-revenue/BloqueRevenue.tsx"


def test_se_calculan_LOS_DOS_ingresos():
    """⚠️ El de rack NO es el neto con un ajuste al final.

    Son dos series desde el principio: `rack × noches` y `rack × factor × noches`.
    Derivar uno del otro al dibujar deja la comision escrita en la pantalla y no
    en el calculo, y el dia que el factor neto cambie de forma —por mes, por
    canal, por categoria— la resta deja de valer sin que nada avise.
    """
    s = PAGINA.read_text(encoding="utf-8")
    assert "rack: number[];" in s and "revenue: number[];" in s
    assert "const rack = MONTHS.map((_m, mi) => nights[mi] * rack12[mi]);" in s
    assert "const revenue = MONTHS.map((_m, mi) => rack[mi] * (nf[mi] || 0));" in s


def test_los_dos_bloques_usan_EL_MISMO_renderizador():
    """Misma tabla, otra cifra. Dos copias se separan en el primer retoque."""
    assert BLOQUE.exists()
    s = PAGINA.read_text(encoding="utf-8")
    assert s.count("<BloqueRevenue") == 2
    assert 'import BloqueRevenue from "./BloqueRevenue";' in s


def test_el_RACK_va_primero():
    """En ese orden se lee la comision sin tener que calcularla: lo que se cobra
    arriba, lo que queda abajo."""
    s = PAGINA.read_text(encoding="utf-8")
    assert s.index('titulo={t("rackTitle")}') < s.index('titulo={t("netTitle")}')
    assert 'commissionLine' in s, "no se dice cuanto se lleva el canal"


def test_esta_el_PORCENTAJE_DE_OCUPACION():
    """Owner, 2026-10-04: *«mete % de ocupacion que no esta»*.

    Es de donde sale todo lo de arriba —las noches ocupadas son el % por las
    disponibles— y no se veia en la pantalla que lo usa.

    ⚠️ Y en el Excel baja como FRACCION con formato de porcentaje, no como «40.5»
    suelto: un 40,5 multiplicado por algo da cien veces lo que deberia.
    """
    b = BLOQUE.read_text(encoding="utf-8")
    assert "const ocupacion = (occ: number, disp: number) =>" in b
    assert "rotulos.ocupacion" in b
    s = PAGINA.read_text(encoding="utf-8")
    assert 'label: t("occupancyLabel"), formato: "pct"' in s
    for idioma in ("es", "en"):
        msgs = (FRONT / f"messages/{idioma}.json").read_text(encoding="utf-8")
        assert '"occupancyLabel"' in msgs, f"falta el rotulo en {idioma}"


def test_sin_base_la_tarifa_y_la_ocupacion_NO_son_cero():
    """⚠️ Un mes cerrado con «$0.00» y «0,0%» se lee como un mes abierto que no
    vendio nada. No aplica no es cero."""
    b = BLOQUE.read_text(encoding="utf-8")
    assert 'base ? fmtUsd(rev / base) : "—"' in b
    assert 'disp ? `${(occ / disp * 100).toFixed(1)}%` : "—"' in b


def test_el_EXCEL_trae_los_dos_bloques():
    """El owner compara rack contra neto mirando una tabla debajo de la otra; un
    Excel con solo el neto le pide rehacer la resta a mano."""
    s = PAGINA.read_text(encoding="utf-8")
    bloque = s[s.index("async function bajarExcel()"):]
    assert bloque.count("...bloque(") == 2
    assert 't("rackTitle")' in bloque and 't("netTitle")' in bloque
