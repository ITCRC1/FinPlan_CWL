# -*- coding: utf-8 -*-
"""Que el análisis escrito NO lleve números adentro.

Owner, 2026-10-17, después de que el informe de setiembre quedara vencido por
tercera vez en dos días: *«seguiré moviendo setiembre..pero hay que hacer lo
necesario para que esto funcione»*.

## El problema no era reescribirlo rápido

El informe tiene dos mitades. Los 53 cuadros salen del corte y están siempre al
día. El análisis es texto a mano —y traía **208 cifras escritas adentro**—, así
que cada subida del mes lo volvía falso. Entre el archivo del 16-oct y el del
17-oct el gasto se movió US$9.799,86 sin que cambiara un centavo de ingreso: el
texto seguía diciendo las cifras viejas.

Reescribirlo a mano cada vez no es una solución, es una tarea que se repite
hasta que alguien se olvida. Y el día que se olvide, el documento va a salir
completo, cuadrado y mintiendo — que es como falla todo lo caro de este sistema.

## Qué cambia

El texto lleva **marcas** en vez de cifras:

    "Setiembre cerró con {{tot ACT revenue}} contra {{tot BUD revenue}}
     presupuestados: {{varpct ACT BUD revenue}}."

y se resuelven contra el corte EN EL MOMENTO de armar el documento. La frase es
verdadera con cualquier archivo que esté cargado.

**El juicio sigue escrito a mano**, que es lo que no se puede calcular: qué
hallazgo va primero, si una favorabilidad es ahorro o diferimiento, a qué
gerente se le pregunta. Eso no se vence porque se mueva una reclasificación.

## Dos reglas que no se negocian

* **No hay `eval`.** El vocabulario es una lista cerrada de funciones. Una
  plantilla es un dato del hotel y se edita como texto; si pudiera ejecutar
  código, editar el análisis sería ejecutar código en el servidor.
* **Una marca que no resuelve se VE** —`⟦?…⟧`— y se cuenta. Nunca sale un cero
  silencioso en lugar de un número: un cero se lee como «no hubo», y en un
  informe de variaciones eso es una conclusión, no un hueco.
"""
from __future__ import annotations

import re

from app.informes.datos import OPERATIVOS, OVERHEAD

#: `{{ funcion arg arg }}`. Las llaves dobles no aparecen en el texto normal.
MARCA = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

#: Los grupos de departamento, por su rótulo del informe. Es el MISMO nombre que
#: usan los cuadros: si el texto dice «Tours / Actividades», el cuadro de arriba
#: también, y el lector puede atar los dos sin pensar.
GRUPOS = {nom: cods for nom, cods in OPERATIVOS + OVERHEAD}

CLASES = {"revenue", "cost", "payroll", "opex", "property"}


def _mil(x: float, dec: int = 2) -> str:
    """`40178.28` → `40.178,28`. La convención que ya usa el texto del informe:
    punto de miles y coma decimal."""
    s = f"{abs(x):,.{dec}f}".replace(",", "\x00").replace(".", ",")
    return ("-" if x < 0 else "") + s.replace("\x00", ".")


def _usd(x: float, dec: int = 2) -> str:
    return ("-$" if x < 0 else "$") + _mil(abs(x), dec)


def _gasto(D, esc: str, cods=None) -> float:
    """Costo + planilla + opex. El gasto operativo, que es como lo mira el
    informe en todos sus cuadros."""
    if cods is None:
        return sum(D.total(esc, c) for c in ("cost", "payroll", "opex"))
    return sum(D.grupo(cods, c, esc) for c in ("cost", "payroll", "opex"))


def _num(D, fn: str, args: list[str]) -> float:
    """El NÚMERO crudo de una marca. Separado del formato a propósito: `var` y
    `varpct` necesitan el número de otras dos marcas."""
    if fn in ("tot", "total"):
        esc, clase = args[0], args[1]
        if clase == "gasto":
            return _gasto(D, esc)
        if clase not in CLASES:
            raise KeyError(f"clase desconocida: {clase}")
        return D.total(esc, clase)
    if fn == "gop":
        return D.gop(args[0])
    if fn == "dept":
        # `dept "Alimentos y Bebidas" ACT gasto`
        nom, esc = args[0], args[1]
        que = args[2] if len(args) > 2 else "gasto"
        if nom not in GRUPOS:
            raise KeyError(f"departamento desconocido: {nom}")
        cods = GRUPOS[nom]
        if que == "gasto":
            return _gasto(D, esc, cods)
        if que == "resultado":
            return D.resultado(cods, esc)
        if que not in CLASES:
            raise KeyError(f"clase desconocida: {que}")
        return D.grupo(cods, que, esc)
    if fn == "cta":
        # `cta 0110 7080 ACT` — una cuenta de un departamento.
        #
        # ⚠️ Solo las clases que la apertura por cuenta TIENE. La planilla se
        # abre por concepto (`conc`), no por cuenta, y pedirsela a
        # `por_cuenta` revienta con KeyError — que es como se descubrio esto:
        # las diez marcas de clase 8 salieron con ⟦?⟧ visible en vez de un cero.
        dep, cuenta, esc = args[0], args[1], args[2]
        for clase in ("opex", "cost", "property", "revenue"):
            f = D.por_cuenta(clase).get((dep, cuenta))
            if f:
                return float(f.get(esc) or 0)
        # Que NO esté no es lo mismo que que valga cero: una cuenta mal escrita
        # daria «$0,00» y se leeria como «no hubo movimiento».
        raise KeyError(f"cuenta sin movimiento ni presupuesto: {dep}/{cuenta}")
    if fn == "conc":
        # `conc 6001 ACT` — un concepto de planilla.
        r = D.payroll_concepto().get(args[0])
        return float((r or {}).get(args[1], 0.0))
    if fn == "kpi":
        return _kpi(D, args[0])
    raise KeyError(f"funcion desconocida: {fn}")


def _kpi(D, cual: str) -> float:
    filas = (D.d.get("stats") or {}).get("ACT") or []
    disp = sum(float(r.get("nights_available") or 0) for r in filas)
    occ = sum(float(r.get("nights_occupied") or 0) for r in filas)
    rev = sum(float(r.get("revenue") or 0) for r in filas)
    pax = sum(float(r.get("pax") or 0) for r in filas)
    return {"disp": disp, "occ": occ, "pax": pax, "revrooms": rev,
            "ocupacion": (occ / disp if disp else 0.0),
            "adr": (rev / occ if occ else 0.0),
            "revpar": (rev / disp if disp else 0.0)}[cual]


def valor(expr: str, D) -> str:
    """Resuelve UNA marca. Devuelve texto ya formateado."""
    args = _partir(expr)
    if not args:
        raise KeyError("marca vacia")
    fn, args = args[0], args[1:]

    if fn == "var":
        # `var ACT BUD revenue` → la diferencia, con signo.
        a = _num(D, "tot", [args[0], args[2]]) if len(args) == 3 else None
        b = _num(D, "tot", [args[1], args[2]]) if len(args) == 3 else None
        if a is None:
            raise KeyError("var necesita: esc esc clase")
        return _usd(a - b)
    if fn == "varpct":
        a = _num(D, "tot", [args[0], args[2]])
        b = _num(D, "tot", [args[1], args[2]])
        if abs(b) < 0.005:
            return "—"
        return f"{_mil((a - b) / abs(b) * 100, 1)}%"
    if fn == "deptvar":
        # `deptvar "Rooms" ACT BUD resultado`
        que = args[3] if len(args) > 3 else "gasto"
        a = _num(D, "dept", [args[0], args[1], que])
        b = _num(D, "dept", [args[0], args[2], que])
        return _usd(a - b)
    if fn == "pct":
        # `pct ACT payroll revenue` → la clase como % de otra.
        a = _num(D, "tot", [args[0], args[1]])
        b = _num(D, "tot", [args[0], args[2]])
        if abs(b) < 0.005:
            return "—"
        return f"{_mil(a / b * 100, 1)}%"

    v = _num(D, fn, args)
    if fn == "kpi" and args[0] == "ocupacion":
        return f"{_mil(v * 100, 2)}%"
    if fn == "kpi" and args[0] in ("disp", "occ", "pax"):
        return _mil(v, 0)
    return _usd(v)


def _partir(expr: str) -> list[str]:
    """Parte una marca en palabras, respetando "lo que va entre comillas"."""
    return [a or b for a, b in re.findall(r'"([^"]*)"|(\S+)', expr)]


def resolver(valor_o_estructura, D, faltan: list[str] | None = None):
    """Recorre la narrativa entera y resuelve cada marca.

    ⚠️ Se aplica UNA vez, sobre el diccionario completo, antes de que ninguna
    sección lo toque. Así vale para todo —párrafos, viñetas, celdas de cuadro,
    preguntas— sin tocar las doce funciones que arman el documento, y sin que
    mañana alguien agregue una sección que se olvide de resolver.
    """
    x = valor_o_estructura
    if isinstance(x, str):
        def uno(m):
            try:
                return valor(m.group(1), D)
            except Exception as e:                        # noqa: BLE001
                if faltan is not None:
                    faltan.append(f"{m.group(1)} → {type(e).__name__}: {e}")
                # Visible, nunca un cero silencioso.
                return f"⟦? {m.group(1)}⟧"
        return MARCA.sub(uno, x)
    if isinstance(x, dict):
        return {k: resolver(v, D, faltan) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [resolver(v, D, faltan) for v in x]
    return x
