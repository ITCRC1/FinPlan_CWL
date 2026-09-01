# -*- coding: utf-8 -*-
"""Nivel 3 · contra las otras fuentes que el sistema ya tiene.

Es el nivel que `guillermo/cuadre_opera` llama *«lo que distingue "los archivos
están" de "los datos sirven"»*. Los niveles 1 y 2 miran el archivo por dentro;
éste lo cruza con lo que el sistema sabe por otro camino.

Un mayor puede estar impecable y aun así no coincidir con la planilla, con el
checkbook o con Opera. Cuando eso pasa, uno de los dos está mal — y hasta ahora
nadie lo miraba en el momento del cierre.

Puro: recibe los auxiliares ya sumados, no toca la base.
"""
from __future__ import annotations

from decimal import Decimal

from app.revision.hallazgo import hallazgo

ZERO = Decimal("0")
NIVEL = 3

#: Un dólar. Igual que el resto del sistema.
TOLERANCIA = Decimal("1")

#: Clases de cuenta por bloque, para cruzar contra su auxiliar.
CLASE_PLANILLA = "6"
CLASE_OPEX = "7"


def _por_depto(filas, clase: str) -> dict:
    acc: dict[str, Decimal] = {}
    for f in filas:
        if str(f["cuenta_base"] or "").startswith(clase):
            d = f["destino_finplan"]
            acc[d] = acc.get(d, ZERO) + Decimal(str(f["mes_usd"]))
    return acc


def _cruce(mayor: dict, auxiliar: dict, clave: str, titulo: str,
           que_es: str, donde: str) -> list:
    """El patrón común: el mayor contra un auxiliar, departamento por
    departamento. Sólo se juzgan los departamentos que el auxiliar CONOCE — si
    no tiene una fila, no está diciendo que sea cero, está diciendo nada."""
    if not auxiliar:
        return []
    difs = []
    for depto, esperado in auxiliar.items():
        real = Decimal(str(mayor.get(depto, 0)))
        d = real - Decimal(str(esperado))
        if abs(d) > TOLERANCIA:
            difs.append({"depto": depto, "mayor": float(real),
                         "auxiliar": float(esperado), "diferencia": float(d)})
    if not difs:
        return []
    difs.sort(key=lambda x: -abs(x["diferencia"]))
    return [hallazgo(
        clave, titulo, "aviso",
        ", ".join(f"{x['depto']} {x['diferencia']:+,.2f}" for x in difs[:6])
        + ("…" if len(difs) > 6 else ""),
        porque=f"{que_es} El mayor y el auxiliar salen de caminos distintos: si "
               f"no coinciden, uno de los dos está mal, y el P&L cuadra consigo "
               f"mismo igual.",
        que_hacer=f"Comparar {donde} contra el mayor del mes en los "
                  f"departamentos de la lista.",
        monto=sum((Decimal(str(x["diferencia"])) for x in difs), ZERO),
        nivel=NIVEL, referencias=difs)]


def planilla_vs_mayor(filas: list[dict], planilla_por_depto: dict) -> list:
    """Las cuentas 6xxx del mayor contra el auxiliar de planilla."""
    return _cruce(_por_depto(filas, CLASE_PLANILLA), planilla_por_depto,
                  "planilla_no_cuadra",
                  "La planilla no coincide con el mayor",
                  "La planilla es el auxiliar de las cuentas 6xxx.",
                  "el auxiliar de planilla")


def opex_vs_mayor(filas: list[dict], opex_por_depto: dict) -> list:
    """Las cuentas 7xxx del mayor contra el checkbook de gastos."""
    return _cruce(_por_depto(filas, CLASE_OPEX), opex_por_depto,
                  "opex_no_cuadra",
                  "El checkbook de gastos no coincide con el mayor",
                  "El checkbook es el auxiliar de las cuentas 7xxx.",
                  "el checkbook de OPEX")


def estadisticas_coherentes(stats: dict, ingreso_habitaciones=None,
                            adr_min=Decimal("50"),
                            adr_max=Decimal("2000")) -> list:
    """Las tres estadísticas tienen que poder ser ciertas a la vez.

    No necesita otra fuente: son imposibles aritméticas. Ocupadas por encima de
    disponibles, huéspedes por debajo de ocupadas, o un ADR fuera de rango son
    errores de tipeo que después arrastran todos los KPI del mes.
    """
    disp = Decimal(str(stats.get("rooms_disponibles") or 0))
    ocup = Decimal(str(stats.get("rooms_ocupadas") or 0))
    hues = Decimal(str(stats.get("huespedes") or 0))
    if not (disp or ocup or hues):
        return []          # todavía no se cargaron; eso lo dice otro aviso
    problemas = []
    if disp and ocup > disp:
        problemas.append(f"ocupadas ({ocup:,.0f}) supera disponibles ({disp:,.0f})")
    if ocup and hues and hues < ocup:
        problemas.append(f"huéspedes ({hues:,.0f}) es menos que ocupadas ({ocup:,.0f})")
    if ocup and ingreso_habitaciones is not None:
        adr = Decimal(str(ingreso_habitaciones)) / ocup
        if not (Decimal(str(adr_min)) <= adr <= Decimal(str(adr_max))):
            problemas.append(f"el ADR da US$ {adr:,.0f} por noche")
    if not problemas:
        return []
    return [hallazgo(
        "estadisticas_incoherentes",
        "Las estadísticas del mes no cierran entre sí",
        "aviso", " · ".join(problemas),
        porque="Son imposibles aritméticas, no diferencias de criterio. Un dígito "
               "de más acá arrastra todos los KPI del mes — ocupación, ADR, "
               "RevPAR— y ninguno de ellos avisa.",
        que_hacer="Revisar las tres cifras contra el reporte de Opera.",
        nivel=NIVEL,
        referencias=[{"disponibles": float(disp), "ocupadas": float(ocup),
                      "huespedes": float(hues)}])]


def rooms_vs_opera(stats: dict, noches_opera) -> list:
    """Las noches declaradas contra las que dice Opera.

    ⚠️ Sólo tiene sentido con las noches que vinieron del XML (`origen='xml'`) y
    en meses CERRADOS — la disciplina que `cuadre_opera` ya fijó. Contra un mes
    abierto, el On the Books es parcial por definición y daría diferencia
    siempre, que es la forma más rápida de que la lista se ignore.
    """
    if noches_opera is None:
        return []
    ocup = Decimal(str(stats.get("rooms_ocupadas") or 0))
    d = ocup - Decimal(str(noches_opera))
    if abs(d) <= TOLERANCIA:
        return []
    return [hallazgo(
        "rooms_no_cuadra_con_opera",
        "Las noches del mes no coinciden con Opera",
        "aviso",
        f"el cierre declara {ocup:,.0f} y Opera dice {float(noches_opera):,.0f} "
        f"({float(d):+,.0f})",
        porque="Los dos números salen del mismo hotel por caminos distintos. Si "
               "no coinciden, el ADR y el RevPAR del mes están calculados sobre "
               "una base que no es la real.",
        que_hacer="Comparar contra el Channel Mix del mes, que es el mismo XML "
                  "de Opera.",
        monto=d, nivel=NIVEL)]


def revisar(filas: list[dict], *, planilla=None, opex=None, stats=None,
            ingreso_habitaciones=None, noches_opera=None) -> list:
    """Los cuatro cruces. El que no reciba su fuente, no corre."""
    out = []
    out += planilla_vs_mayor(filas, planilla or {})
    out += opex_vs_mayor(filas, opex or {})
    out += estadisticas_coherentes(stats or {}, ingreso_habitaciones)
    out += rooms_vs_opera(stats or {}, noches_opera)
    return out
