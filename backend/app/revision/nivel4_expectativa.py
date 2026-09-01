# -*- coding: utf-8 -*-
"""Nivel 4 · contra lo que se esperaba — las varianzas.

Actual contra **Forecast** y contra **Budget**, línea por línea, en monto y en
porcentaje. Es la mitad «varianzas» del informe que pidió el owner; la otra
mitad —las discrepancias— vive en los niveles 1 a 3.

## Dos umbrales, y los dos tienen que superarse

Sólo con monto, un departamento chico nunca aparece aunque se haya duplicado.
Sólo con porcentaje, una línea de $40 que pasa a $80 sale al tope de la lista
por encima de una de $200.000 que se movió un 3%. Se piden **los dos**: importa
y además es mucho.

Los valores por defecto son un punto de partida, no una verdad — se ajustan
desde la pantalla.

## Lo que aparece de la nada

Una línea con monto en el Actual y **cero** en el comparativo es su propio
hallazgo, sin umbral de porcentaje: dividir por cero no dice nada, y «apareció
algo que nadie presupuestó» es exactamente lo que hay que mirar.

Puro: recibe los tres diccionarios de valores ya calculados.
"""
from __future__ import annotations

from decimal import Decimal

from app.revision.hallazgo import hallazgo

ZERO = Decimal("0")
NIVEL = 4

#: Punto de partida: US$ 5.000 **y** 10%. Ajustables desde la pantalla.
UMBRAL_MONTO = Decimal("5000")
UMBRAL_PCT = Decimal("10")

#: Las claves que NO se comparan: son totales de otras que ya se comparan, y
#: reportarlas duplicaría cada desvío —una vez en la línea y otra en su total—.
TOTALES = {
    "TOTAL INCOMES", "Total Operationg expenses", "OPERATING PROFIT",
    "TOTAL OVERHEAD EXPENSES", "TOTAL GROSS OPERATING PROFIT",
    "TOTAL RENTA AND MANAGEMENT FEES", "TOTAL RENTA AND MANAGEMENT FEE",
    "PROPERTY INSURANCE", "TOTAL OTHER EXPENSES", "CAPITAL EXPENSE",
    "TOTAL Owners Expenses", "EBITDA", "FINANCIAL EXPENSES",
    "TOTAL DEPRECIATIONS", "EARNINGS BEFORE INCOME TAXES",
    "EARNINGS AFTER INCOME TAXES", "cero",
}


def _etiqueta(clave: str) -> str:
    """`rev.Rooms` → `Ingreso · Rooms`. Lo que se lee en la lista."""
    prefijos = {"rev": "Ingreso", "opex": "Gasto", "profit": "Utilidad",
                "oh": "Overhead", "bg": "Bajo GOP"}
    if "." in clave:
        p, resto = clave.split(".", 1)
        return f"{prefijos.get(p, p)} · {resto}"
    return clave


def comparar(actual: dict, contra: dict, nombre: str, *,
             umbral_monto=UMBRAL_MONTO, umbral_pct=UMBRAL_PCT) -> list:
    """Las líneas que se desviaron de `contra` más allá de los dos umbrales."""
    umbral_monto = Decimal(str(umbral_monto))
    umbral_pct = Decimal(str(umbral_pct))
    grandes, aparecieron = [], []
    for clave in sorted(set(actual) | set(contra)):
        if clave in TOTALES or clave.startswith("stat."):
            continue
        a, b = Decimal(str(actual.get(clave, 0))), Decimal(str(contra.get(clave, 0)))
        d = a - b
        if abs(d) < umbral_monto:
            continue
        if b == ZERO:
            aparecieron.append({"linea": _etiqueta(clave), "actual": float(a),
                                "comparativo": 0.0, "diferencia": float(d)})
            continue
        # ⚠️ CON SIGNO. Con `abs(d)` una caída de 28.562 se mostraba «+21%»,
        # que se lee como que subió. El denominador sí va en absoluto: si no,
        # un comparativo negativo invierte el sentido del porcentaje.
        pct = d / abs(b) * 100
        if abs(pct) >= umbral_pct:
            grandes.append({"linea": _etiqueta(clave), "actual": float(a),
                            "comparativo": float(b), "diferencia": float(d),
                            "pct": float(round(pct, 1))})
    out = []
    if grandes:
        grandes.sort(key=lambda x: -abs(x["diferencia"]))
        out.append(hallazgo(
            f"varianza_{nombre.lower()}",
            f"Desvíos grandes contra el {nombre}",
            "aviso",
            ", ".join(f"{x['linea']} {x['diferencia']:+,.0f} ({x['pct']:+.0f}%)"
                      for x in grandes[:6])
            + ("…" if len(grandes) > 6 else ""),
            porque=f"Superan los dos umbrales a la vez: más de "
                   f"US$ {float(umbral_monto):,.0f} y más de {float(umbral_pct):.0f}%. "
                   f"Uno solo dejaría pasar un departamento chico que se duplicó, "
                   f"o llenaría la lista de líneas de $40.",
            que_hacer=f"Confirmar que el desvío contra el {nombre} es real y no "
                      f"un error de posteo ni un comparativo desactualizado.",
            monto=sum((Decimal(str(x["diferencia"])) for x in grandes), ZERO),
            nivel=NIVEL, referencias=grandes))
    if aparecieron:
        aparecieron.sort(key=lambda x: -abs(x["diferencia"]))
        out.append(hallazgo(
            f"sin_comparativo_{nombre.lower()}",
            f"Líneas con monto que el {nombre} tiene en cero",
            "aviso",
            ", ".join(f"{x['linea']} {x['actual']:+,.0f}" for x in aparecieron[:6])
            + ("…" if len(aparecieron) > 6 else ""),
            porque=f"Apareció algo que el {nombre} no contemplaba. Puede ser una "
                   f"operación nueva o una cuenta mal clasificada; el porcentaje "
                   f"no ayuda a distinguirlas porque el comparativo es cero.",
            que_hacer=f"Verificar si corresponde, y si el {nombre} quedó "
                      f"desactualizado.",
            monto=sum((Decimal(str(x["diferencia"])) for x in aparecieron), ZERO),
            nivel=NIVEL, referencias=aparecieron))
    return out


def salto_contra_el_mes_anterior(actual: dict, anterior: dict, *,
                                 umbral_monto=UMBRAL_MONTO,
                                 umbral_pct=UMBRAL_PCT) -> list:
    """Un mes que se movió mucho respecto del anterior.

    No es una varianza contra un plan: es contra la propia operación. Un salto
    grande sin explicación suele ser un asiento que entró al mes equivocado.
    """
    if not anterior:
        return []
    h = comparar(actual, anterior, "mes anterior",
                 umbral_monto=umbral_monto, umbral_pct=umbral_pct)
    for x in h:
        x.clave = x.clave.replace("varianza_mes anterior", "salto_mes_anterior")
        x.clave = x.clave.replace("sin_comparativo_mes anterior",
                                  "sin_dato_mes_anterior")
    return h


def revisar(actual: dict, *, forecast=None, budget=None, mes_anterior=None,
            umbral_monto=UMBRAL_MONTO, umbral_pct=UMBRAL_PCT) -> list:
    """Las tres comparaciones. La que no reciba su comparativo, no corre."""
    out = []
    if forecast:
        out += comparar(actual, forecast, "Forecast",
                        umbral_monto=umbral_monto, umbral_pct=umbral_pct)
    if budget:
        out += comparar(actual, budget, "Budget",
                        umbral_monto=umbral_monto, umbral_pct=umbral_pct)
    out += salto_contra_el_mes_anterior(actual, mes_anterior or {},
                                        umbral_monto=umbral_monto,
                                        umbral_pct=umbral_pct)
    return out
