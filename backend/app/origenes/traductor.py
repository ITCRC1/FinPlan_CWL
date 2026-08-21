# -*- coding: utf-8 -*-
"""Traduce las filas de un origen al catálogo de acá, usando el mapeo.

**La regla que manda todo este archivo:** lo que no tiene equivalencia NO entra,
y se reporta con nombre y monto. Nunca se descarta en silencio.

Un import que se traga tres cuentas sin avisar deja un P&L que cuadra consigo
mismo y no cuadra con la realidad — el peor resultado posible, porque nada lo
delata. Es la misma lección de los 21 departamentos que perdían gasto: el total
seguía dando bien.
"""
from collections import defaultdict
from decimal import Decimal

from app.origenes import FilaDeOrigen

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


def _llave(cuenta: str, dept: str) -> tuple[str, str]:
    return ((cuenta or "").strip(), (dept or "").strip())


def indexar_mapeo(reglas) -> dict:
    """Arma el índice de búsqueda.

    Dos niveles a propósito: una regla CON departamento gana sobre una sin él.
    Así se puede tener «la 5010 va a Food Cost» y, aparte, «la 5010 del
    departamento BAR va a Beverage Cost», sin duplicar el catálogo entero.
    """
    exactas: dict[tuple[str, str], object] = {}
    generales: dict[str, object] = {}
    for r in reglas:
        if not getattr(r, "activo", True):
            continue
        cuenta = (r.cuenta_origen or "").strip()
        dept = (r.dept_origen or "").strip()
        if dept:
            exactas[_llave(cuenta, dept)] = r
        else:
            generales[cuenta] = r
    return {"exactas": exactas, "generales": generales}


def buscar(indice: dict, fila: FilaDeOrigen):
    """La regla que le toca a esta fila, o None."""
    exacta = indice["exactas"].get(_llave(fila.cuenta, fila.dept))
    if exacta is not None:
        return exacta
    return indice["generales"].get((fila.cuenta or "").strip())


def traducir(filas: list[FilaDeOrigen], reglas) -> dict:
    """Filas del origen → filas listas para `actual_entries`.

    Devuelve `{"filas": [...], "sin_mapeo": [...], "meses": [...]}`.

    `sin_mapeo` viene agregado por cuenta y con el monto total, que es lo que
    hace falta para decidir: una cuenta suelta de doce dólares no es lo mismo que
    una de sesenta mil, y viendo fila por fila no se distingue.
    """
    indice = indexar_mapeo(reglas)
    acumulado: dict[tuple[str, str, str], dict] = {}
    faltantes: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"monto": Decimal("0"), "nombre": "", "meses": set()})
    meses_vistos: set[int] = set()

    for f in filas:
        meses_vistos.add(f.mes)
        regla = buscar(indice, f)
        if regla is None:
            k = (f.cuenta, f.dept)
            faltantes[k]["monto"] += Decimal(str(f.monto))
            faltantes[k]["nombre"] = faltantes[k]["nombre"] or f.nombre
            faltantes[k]["meses"].add(f.mes)
            continue

        # El outlet va en la llave, no solo de adorno: el GL de A&B trae la MISMA
        # cuenta una vez por punto de venta. Sin él, las filas comparten llave y
        # la plata de todos menos uno se pierde.
        outlet = (regla.outlet or f.outlet or "").strip()
        k = (regla.dept_code or "", regla.account_code, outlet)
        destino = acumulado.setdefault(k, {
            "dept_code": regla.dept_code or "",
            "account_code": regla.account_code,
            "account_name": regla.nombre_origen or f.nombre or "",
            "outlet": outlet,
            **{m: Decimal("0") for m in MESES},
        })
        # Se SUMA: dos cuentas del origen pueden caer en la misma de acá, y ahí
        # asignar en vez de acumular perdería una.
        destino[MESES[f.mes - 1]] += Decimal(str(f.monto))

    sin_mapeo = [{
        "cuenta_origen": c, "dept_origen": d,
        "nombre": v["nombre"], "monto": float(v["monto"]),
        "meses": sorted(v["meses"]),
    } for (c, d), v in sorted(faltantes.items(), key=lambda kv: -abs(kv[1]["monto"]))]

    return {
        "filas": list(acumulado.values()),
        "sin_mapeo": sin_mapeo,
        "meses": sorted(meses_vistos),
    }
