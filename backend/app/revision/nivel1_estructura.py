# -*- coding: utf-8 -*-
"""Nivel 1 · estructura — «cualquier cosa puede subir».

La pregunta de este nivel es una sola: **¿esta plata va a algún lado?** Una
cuenta sin mapeo, un departamento sin puente o una línea obligatoria vacía no
hacen ruido: el archivo entra, el P&L se arma, cuadra consigo mismo, y lo que
falta se descubre meses después comparando contra otra cosa.

Puro: recibe las filas ya traducidas y el contexto ya cargado, no toca la base.
"""
from __future__ import annotations

from decimal import Decimal

from app.revision.hallazgo import hallazgo

ZERO = Decimal("0")
NIVEL = 1


def _suma(filas) -> Decimal:
    return sum((f["mes_usd"] for f in filas), ZERO)


def cuentas_sin_mapeo(filas: list[dict], linea_de) -> list:
    """Cuentas que no llegan a ninguna línea del P&L.

    Éste es el caso «no autorizada por USALI»: la cuenta existe en el mayor, su
    plata entra al total del departamento, y sin embargo no aparece en ninguna
    línea del reporte. `linea_de(depto, cuenta)` devuelve la línea, o vacío.
    """
    huerfanas: dict[tuple, dict] = {}
    for f in filas:
        if not f["mes_usd"]:
            continue
        cuenta = str(f["cuenta_base"] or "")
        if linea_de(f["destino_finplan"], cuenta):
            continue
        k = (cuenta, f["destino_finplan"])
        acc = huerfanas.setdefault(k, {"monto": ZERO, "refs": []})
        acc["monto"] += f["mes_usd"]
        acc["refs"].append({"fila": f["fila"], "cuenta": f["cuenta"],
                            "nombre": f["descripcion"],
                            # El depto y el monto van en CADA referencia para que
                            # la pantalla las muestre como tabla y no como texto:
                            # «no subió» sin el monto al lado no se puede priorizar.
                            "depto": f["destino_finplan"],
                            "monto": float(f["mes_usd"]),
                            "motivo": "sin_renglon"})
    if not huerfanas:
        return []
    total = sum((v["monto"] for v in huerfanas.values()), ZERO)
    cuales = ", ".join(f"{c} ({d})" for (c, d) in sorted(huerfanas)[:8])
    return [hallazgo(
        "cuenta_sin_mapeo",
        "Cuentas que no llegan a ninguna línea del P&L",
        "critico" if total else "aviso",
        f"{len(huerfanas)} combinaciones de cuenta y departamento no resuelven a "
        f"ninguna línea del reporte: {cuales}"
        + ("…" if len(huerfanas) > 8 else ""),
        porque="Su plata entra al total del departamento pero no aparece en "
               "ninguna línea del P&L. El reporte cuadra consigo mismo y la "
               "diferencia sólo se ve comparando contra otra cosa.",
        que_hacer="Agregar la regla en Mapeo de cuentas, o confirmar que esa "
                  "cuenta no debe reportarse.",
        monto=total, nivel=NIVEL,
        referencias=[r for v in huerfanas.values() for r in v["refs"]])]


def cuentas_en_linea_prestada(filas: list[dict], como_de) -> list:
    """Cuentas que llegan a una línea que NO es la suya.

    El resolvedor tiene un último recurso: si no hay regla para (departamento,
    cuenta), toma **cualquier regla que use esa cuenta** — la del departamento
    de número más bajo. La plata entra al P&L, el total cuadra, y el renglón es
    el de otro departamento.

    ⚠️ **Esto es peor que perderse.** Una cuenta sin renglón deja un hueco que
    tarde o temprano alguien nota; una cuenta en el renglón ajeno no deja
    ninguno: los totales cuadran, no hay error, no hay alerta, y la plata cambió
    de línea sola. Es el modo de falla que `CLAUDE.md` marca como el más caro
    del sistema.

    Agosto 2026: la `5501` (costo de lavandería, departamento 0162) caía en
    `COS_INNOCEANA` por este camino — US$150,09 reportados como costo de
    Innoceana. Sólo apareció buscándola a mano.

    `como_de(depto, cuenta)` devuelve cómo resolvió: `exact`, `parent`,
    `FALLBACK` o vacío. Sólo el `FALLBACK` es préstamo: `parent` es una regla
    declarada a propósito en el departamento madre.
    """
    prestadas: dict[tuple, dict] = {}
    for f in filas:
        if not f["mes_usd"]:
            continue
        cuenta = str(f["cuenta_base"] or "")
        linea, como = como_de(f["destino_finplan"], cuenta)
        if como != "FALLBACK" or not linea:
            continue
        k = (cuenta, f["destino_finplan"])
        acc = prestadas.setdefault(k, {"monto": ZERO, "linea": linea, "refs": []})
        acc["monto"] += f["mes_usd"]
        acc["refs"].append({"fila": f["fila"], "cuenta": f["cuenta"],
                            "nombre": f["descripcion"],
                            "depto": f["destino_finplan"],
                            "monto": float(f["mes_usd"]),
                            "linea": linea,
                            "motivo": "renglon_prestado"})
    if not prestadas:
        return []
    total = sum((v["monto"] for v in prestadas.values()), ZERO)
    cuales = ", ".join(f"{c} ({d}) → {v['linea']}"
                       for (c, d), v in sorted(prestadas.items())[:8])
    return [hallazgo(
        "cuenta_en_linea_prestada",
        "Cuentas que llegan a la línea de otro departamento",
        "critico" if total else "aviso",
        f"{len(prestadas)} combinaciones de cuenta y departamento no tienen "
        f"regla propia y entraron por descarte: {cuales}"
        + ("…" if len(prestadas) > 8 else ""),
        porque="La plata SÍ entra al P&L, así que todos los totales cuadran — "
               "pero en el renglón de otro departamento. No hay error ni alerta "
               "que lo delate: sólo se ve comparando el P&L por departamento "
               "contra el mayor.",
        que_hacer="Agregar en Mapeo de cuentas la regla de ESE departamento "
                  "para esa cuenta, o confirmar que el renglón actual es el que "
                  "corresponde.",
        monto=total, nivel=NIVEL,
        referencias=[r for v in prestadas.values() for r in v["refs"]])]


def departamentos_sin_puente(sin_mapeo: list[dict]) -> list:
    """Departamentos de Integrity que el puente no traduce.

    Sus filas **no se cargan**. Lo produce el propio lector; acá se convierte en
    hallazgo con su monto.
    """
    if not sin_mapeo:
        return []
    total = sum((Decimal(str(x["mes_usd"])) for x in sin_mapeo), ZERO)
    return [hallazgo(
        "depto_sin_puente",
        "Departamentos que el puente no traduce",
        "critico",
        "no se cargaron: " + ", ".join(
            f"{x['depto']} (${float(x['mes_usd']):,.2f})" for x in sin_mapeo[:8]),
        porque="Los códigos de Integrity y los de FinPlan no son el mismo "
               "espacio: sin una entrada en el puente no se sabe a qué "
               "departamento va, y adivinarlo mandaría la plata al lugar "
               "equivocado con el total cuadrando igual.",
        que_hacer="Agregar el código a `mapd_integrity.json` con su destino en "
                  "FinPlan.",
        monto=total, nivel=NIVEL,
        referencias=[{"depto": x["depto"], "cuentas": x.get("cuentas", [])[:6]}
                     for x in sin_mapeo])]


def cuentas_nuevas(filas: list[dict], vistas_antes: set) -> list:
    """Cuentas que no aparecen en ningún mes anterior del mismo año.

    Puede ser legítima —una operación nueva— o un error de codificación. Lo que
    no puede es pasar sin que nadie la vea: `vistas_antes` es el conjunto de
    `(cuenta_base, depto)` de los meses ya cerrados.
    """
    if not vistas_antes:
        return []          # sin historia no hay novedad que reportar
    nuevas: dict[tuple, dict] = {}
    for f in filas:
        if not f["mes_usd"]:
            continue
        k = (f["cuenta_base"], f["depto"])
        if k in vistas_antes:
            continue
        acc = nuevas.setdefault(k, {"monto": ZERO, "nombre": f["descripcion"],
                                    "refs": []})
        acc["monto"] += f["mes_usd"]
        acc["refs"].append({"fila": f["fila"], "cuenta": f["cuenta"]})
    if not nuevas:
        return []
    total = sum((v["monto"] for v in nuevas.values()), ZERO)
    cuales = ", ".join(f"{c}-{d} {v['nombre'][:28]}"
                       for (c, d), v in list(nuevas.items())[:6])
    return [hallazgo(
        "cuenta_nueva",
        "Cuentas que no estaban en los meses anteriores",
        "aviso",
        f"{len(nuevas)} aparecen por primera vez este año: {cuales}"
        + ("…" if len(nuevas) > 6 else ""),
        porque="Una cuenta nueva puede ser una operación nueva o un error de "
               "codificación. Las dos se ven igual en el total.",
        que_hacer="Confirmar que corresponde. Si es un error de posteo, "
                  "corregirlo en Integrity y volver a subir.",
        monto=total, nivel=NIVEL,
        referencias=[r for v in nuevas.values() for r in v["refs"]])]


def lineas_obligatorias_vacias(valores: dict, obligatorias: list[str],
                               etiqueta_de=None) -> list:
    """Líneas que un mes tiene que traer con dato, y vinieron en cero.

    La lista es del owner (`seed_data/lineas_obligatorias.json`). El motivo está
    en ese archivo: *«si `OH_UTILITIES` está en cero, el GOP no es mejor — es un
    GOP al que le falta la luz»*.
    """
    faltan = [c for c in obligatorias
              if not Decimal(str(valores.get(c, 0) or 0))]
    if not faltan:
        return []
    nombres = [(etiqueta_de(c) if etiqueta_de else c) for c in faltan]
    return [hallazgo(
        "linea_obligatoria_vacia",
        "Líneas que el mes debería traer y vinieron en cero",
        "aviso",
        f"{len(faltan)} en cero: " + ", ".join(nombres[:10])
        + ("…" if len(faltan) > 10 else ""),
        porque="Comparar contra el histórico deja de significar algo. Un GOP al "
               "que le falta la luz no es un GOP mejor.",
        que_hacer="Verificar si el gasto todavía no se posteó, o si la línea ya "
                  "no aplica — en ese caso sacarla de la lista de obligatorias.",
        nivel=NIVEL,
        referencias=[{"linea": c} for c in faltan])]


def revisar(filas: list[dict], *, linea_de=None, sin_mapeo=None,
            vistas_antes=None, valores=None, obligatorias=None,
            etiqueta_de=None, como_de=None) -> list:
    """Los cuatro chequeos del nivel. Lo que no reciba su contexto, no corre —
    en silencio y a propósito: un chequeo sin datos no puede decir nada, y
    hacerlo fallar sería confundir «no se pudo mirar» con «está mal»."""
    out = []
    if linea_de is not None:
        out += cuentas_sin_mapeo(filas, linea_de)
    if como_de is not None:
        out += cuentas_en_linea_prestada(filas, como_de)
    out += departamentos_sin_puente(sin_mapeo or [])
    out += cuentas_nuevas(filas, vistas_antes or set())
    if valores is not None and obligatorias:
        out += lineas_obligatorias_vacias(valores, obligatorias, etiqueta_de)
    return out
