# -*- coding: utf-8 -*-
"""EL AVISO: que lineas obligatorias dejo este escenario en cero.

Es el par de `app/importers/verificacion.py`. Aquella cuida los **actuales** en
la puerta: el archivo trae sus totales de control arriba y se validan al subir.
Esta cuida los **presupuestos**, que no traen totales de control porque nadie los
declaro todavia — y por eso su forma de fallar es al reves: no un numero que no
cuadra, sino **una linea que no esta**.

## Por que existe (owner, 2026-08-16)

El owner esta por clonar propiedades. Medido ese dia contra produccion, el
presupuesto 2027 tiene **lineas con regla de mapeo y sin un centavo de dato**:
`OH_UTILITIES` (275.927 en 2025), los tres `COS_*`, `RENT`, `PROPERTY_INSURANCE`
y `DEPRECIATION`. No es el mapeo — `OH_UTILITIES` tiene 37 reglas activas. Es que
falta cargar la plata.

Y **cada propiedad clonada hereda los agujeros**. Un GOP 2027 mejor que el 2025
no es una buena noticia si es un GOP sin luz, sin renta y sin seguro.

## AVISA, NO BLOQUEA

Un presupuesto en construccion tiene lineas vacias con todo derecho: se arma por
partes durante semanas. Bloquear convertiria la herramienta en un estorbo y en
una semana el owner la apagaria. El aviso dice **que falta y cuanto vale en el
historico**, para saber en que orden cargarlo.

## Se mide sobre el P&L CALCULADO, nunca sobre el checkbook

Leccion cara de agosto: `allocation_entries` y la `4999` **las escribe el motor**,
no el usuario. Un checkbook vacio no prueba que la linea este vacia, y una linea
vacia no prueba que el checkbook lo este. Lo unico que responde la pregunta del
owner —«¿esta linea del reporte esta en cero?»— es el reporte.

Tampoco se lee `pl_lines`. Medido el 2026-08-16 contra produccion: el ACTUAL 2025
tiene **cero** filas persistidas y el ACTUAL 2026 difiere en 72 lineas del
calculo vivo. Avisar desde ahi habria inventado agujeros que no existen.

## Respeta el corte del rolling forecast

Un forecast toma sus meses cerrados del Actual enlazado. Mirar los doce meses
mediria meses que el reporte no usa: `FORECAST Working 2026` (corte en 6) se
revisa **solo de julio a diciembre**, que son los que este escenario aporta.
Se reusa `verificacion.meses_comparables` para que las dos puertas corten igual.

⚠️ Modulo PURO: no toca la base ni escribe nada. Un aviso que ademas corrige es
un aviso en el que no se puede confiar cuando dice que esta todo bien.
"""
from __future__ import annotations

import json
import pathlib
from functools import lru_cache

from app.importers.verificacion import meses_comparables

#: Por debajo de esto la linea esta en cero. No es tolerancia contable: es el
#: piso por debajo del cual un residuo de redondeo no cuenta como «hay dato».
CERO = 0.005

ARCHIVO = pathlib.Path(__file__).resolve().parents[1] / "seed_data" / "lineas_obligatorias.json"


@lru_cache(maxsize=1)
def lista() -> dict:
    """La lista tal cual esta en el repo. `{}` si el archivo no esta.

    Que falte no puede tumbar nada: sin lista simplemente no hay aviso. Es un
    control, y un control roto tiene que desaparecer, no romper el reporte.
    """
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return {"lineas": [], "criterio": {}, "generado": "", "_nota": []}
    datos.setdefault("lineas", [])
    return datos


def revisar(por_mes: dict[int, dict[str, float]], tipo: str,
            actuals_through: int | None) -> dict:
    """Que lineas obligatorias dejo este escenario en cero.

    por_mes : {mes: {line_code: monto_usd}} — el P&L calculado, los 12 meses.
    tipo    : 'ACTUAL' | 'BUDGET' | 'FORECAST'
    actuals_through : el corte del rolling forecast (0 si no aplica).

    Devuelve el informe completo: lo que falta, lo que esta, y —cuando el
    escenario esta entero vacio— lo dice en vez de escupir 33 avisos que en
    realidad son uno solo.
    """
    cfg = lista()
    meses, omitidos = meses_comparables(tipo, actuals_through)
    mm = set(meses)

    total: dict[str, float] = {}
    hay_algo = False
    for m, lineas_mes in (por_mes or {}).items():
        if int(m) not in mm:
            continue
        for code, monto in (lineas_mes or {}).items():
            v = float(monto or 0.0)
            total[code] = total.get(code, 0.0) + v
            if abs(v) > CERO:
                hay_algo = True

    faltan, presentes = [], []
    for L in cfg["lineas"]:
        monto = total.get(L["line_code"], 0.0)
        fila = {
            "line_code": L["line_code"],
            "nombre": L.get("nombre", L["line_code"]),
            "seccion": L.get("seccion", ""),
            "donde_se_carga": L.get("donde_se_carga", ""),
            "pantalla": L.get("pantalla", ""),
            "departamentos": L.get("departamentos", []),
            "reglas_de_mapeo": L.get("reglas_de_mapeo", 0),
            "historico": L.get("historico", {}),
            "referencia_usd": L.get("referencia_usd", 0.0),
            "referencia_anio": L.get("referencia_anio"),
            "escenario_usd": round(monto, 2),
        }
        (faltan if abs(monto) <= CERO else presentes).append(fila)

    # El orden es el del owner: lo que mas plata vale, primero. Es literalmente
    # la pregunta que hizo — «que tengo que cargar y en que orden».
    faltan.sort(key=lambda f: -abs(f["referencia_usd"]))
    magnitud = round(sum(abs(f["referencia_usd"]) for f in faltan), 2)

    return {
        "hay_lista": bool(cfg["lineas"]),
        "generado": cfg.get("generado", ""),
        "obligatorias": len(cfg["lineas"]),
        "vacio": not hay_algo,
        "faltan": faltan,
        "presentes": presentes,
        "cuantas_faltan": len(faltan),
        "magnitud_historica_usd": magnitud,
        "meses_revisados": meses,
        "meses_no_revisados": omitidos,
        "motivo_meses_no_revisados": (
            "Son meses cerrados: el forecast los toma del Actual enlazado, no de este "
            "escenario. Revisarlos mediria meses que el reporte no usa."
            if omitidos else ""),
    }


def resumen_texto(rep: dict, etiqueta: str = "") -> str:
    """El aviso en una cadena, para consola y para el cuerpo de un mensaje."""
    if not rep.get("hay_lista"):
        return "No hay lista de lineas obligatorias en el repo: no se reviso nada."
    partes = []
    if etiqueta:
        partes.append(etiqueta)
    if rep["vacio"]:
        partes.append(
            "Escenario VACIO: no tiene un solo monto en los meses que aporta. "
            f"Faltan las {rep['obligatorias']} lineas porque falta todo — no es un "
            "agujero, es un escenario sin empezar.")
        return "\n".join(partes)
    if not rep["faltan"]:
        partes.append(f"Las {rep['obligatorias']} lineas obligatorias tienen dato.")
        return "\n".join(partes)
    partes.append(f"{rep['cuantas_faltan']} de {rep['obligatorias']} lineas obligatorias "
                  f"estan en CERO (valen {rep['magnitud_historica_usd']:,.0f} USD en el historico):")
    for f in rep["faltan"]:
        partes.append(f"    · {f['line_code']:<24} {f['referencia_usd']:>12,.0f} USD "
                      f"({f['referencia_anio']})  cargar en: {f['donde_se_carga']}")
    if rep.get("meses_no_revisados"):
        partes.append("No se revisaron los meses "
                      + ", ".join(f"{m:02d}" for m in rep["meses_no_revisados"])
                      + ": " + rep.get("motivo_meses_no_revisados", ""))
    return "\n".join(partes)
