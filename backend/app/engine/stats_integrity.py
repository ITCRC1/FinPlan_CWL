# -*- coding: utf-8 -*-
"""Estadísticas de Integrity (clase 9) al mes, sobre el catálogo homologado.

**De dónde sale el dato: la contabilidad manda** (owner, 2026-11-10). No hay
plantilla ni otra subida: las estadísticas se leen del Balance de Comprobación
que ya se sube en la Auditoría del mayor y queda en `mayor_movimientos`. Cuando
Integrity empiece a registrar la clase 9 (2027), aparecen acá solas.

**El día se suma acá, y en ningún otro lado.** En Integrity el nivel 6 de la
cuenta es el DÍA: lo pone la interfaz de Opera, igual que en el ingreso —
`4320-0151-999-999-001-12-00` es la venta del día 12—. El owner no quiere
manejar días (*«solo full month»*), así que la llave del mes es el código SIN
el nivel 6 y el valor del mes es la suma de todos sus días. Las horas (998x) ya
traen 00 en ese nivel: la misma regla les da su único valor.

**El valor es débito − crédito.** Una estadística no es plata: Integrity la
registra como un movimiento de la cuenta y la cantidad es su saldo del mes. Un
reverso (crédito) la descuenta, que es lo que tiene que pasar.

⚠️ **Esto no alimenta ningún total.** No lo lee el P&L, ni un escenario, ni el
catálogo estadístico de FinPlan (`stat_accounts`): es la vista de lo que
contabilidad registró, para revisarlo y medir productividad. Que el dato viva en
una sola tabla —el mayor— es lo que evita tener dos verdades sobre el mismo
número.

Puro: no importa nada de la base. Lo usan la API y las pruebas.
"""
from __future__ import annotations

import json
import pathlib
import re
from decimal import Decimal
from functools import lru_cache
from typing import Iterable

CARPETA = pathlib.Path(__file__).resolve().parents[1] / "seed_data"

#: Siete segmentos: 9000-0110-001-001-001-12-01.
_CODIGO = re.compile(r"^\d{4}-\d{3,4}-\d{3}-\d{3}-\d{3}-\d{2}-\d{2}$")


def clave_mensual(cuenta: str) -> str | None:
    """El código sin el nivel 6 (el día). `None` si no es una cuenta de 7 niveles."""
    c = (cuenta or "").strip()
    if not _CODIGO.match(c):
        return None
    p = c.split("-")
    return "-".join(p[:5] + p[6:])


def dia(cuenta: str) -> str:
    """El nivel 6 tal cual (el día, o 00 en las horas)."""
    p = (cuenta or "").strip().split("-")
    return p[5] if len(p) == 7 else ""


@lru_cache(maxsize=8)
def leer_catalogo(hotel_id: str) -> dict:
    """El catálogo homologado de ESTE hotel. Vacío si el hotel no lo tiene.

    Valida lo que, si fallara, haría que un valor caiga en la cuenta equivocada:
    claves repetidas y claves que no tienen la forma de 6 niveles.
    """
    archivo = CARPETA / f"stats_integrity_{hotel_id}.json"
    if not archivo.exists():
        return {"hotel": hotel_id, "version": "", "grupos": {}, "cuentas": []}
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    vistos: set[str] = set()
    for c in datos["cuentas"]:
        k = c["clave"]
        if k in vistos:
            raise ValueError(f"{k}: clave repetida en el catálogo de Integrity")
        if len(k.split("-")) != 6 or not k.startswith("9"):
            raise ValueError(f"{k}: la clave es el código de Integrity sin el día (6 niveles, clase 9)")
        if clave_mensual(c["codigo"].replace("DD", "01")) != k:
            raise ValueError(f"{c['codigo']}: su clave no es {k}")
        vistos.add(k)
    return datos


def agregar(movimientos: Iterable[tuple]) -> dict:
    """Suma los movimientos de clase 9 por (mes, clave).

    `movimientos`: tuplas `(mes, cuenta, debito, credito)`. Devuelve
    `{(mes, clave): {"valor": Decimal, "dias": set, "movimientos": int}}`.
    Lo que no es una cuenta de 7 niveles se ignora: no es una estadística.
    """
    out: dict[tuple[int, str], dict] = {}
    for mes, cuenta, debito, credito in movimientos:
        k = clave_mensual(cuenta)
        if k is None or not k.startswith("9"):
            continue
        a = out.setdefault((int(mes), k), {"valor": Decimal("0"), "dias": set(), "movimientos": 0})
        a["valor"] += Decimal(str(debito or 0)) - Decimal(str(credito or 0))
        a["dias"].add(dia(cuenta))
        a["movimientos"] += 1
    return out


def armar_vista(catalogo: dict, agregado: dict, meses_cargados: Iterable[int]) -> dict:
    """La respuesta de la pantalla: cada cuenta del catálogo con sus 12 meses, los
    totales por grupo, y lo que Integrity registró y el catálogo no conoce.

    ⚠️ Lo que no está en el catálogo NO se descarta: se devuelve aparte. Una
    estadística registrada con un código que la homologación no previó es justo
    lo que hay que ver — tirarla en silencio es como se pierden datos acá.
    """
    por_clave: dict[str, dict[int, Decimal]] = {}
    for (mes, k), a in agregado.items():
        por_clave.setdefault(k, {})[mes] = a["valor"]
    conocidas = {c["clave"] for c in catalogo["cuentas"]}

    cuentas = []
    grupos: dict[str, dict] = {}
    for c in catalogo["cuentas"]:
        vals = por_clave.get(c["clave"], {})
        meses = [float(vals[m]) if m in vals else None for m in range(1, 13)]
        con_dato = any(v is not None for v in meses)
        cuentas.append({**c, "meses": meses, "con_dato": con_dato,
                        "total": float(sum(vals.values(), Decimal("0")))})
        g = grupos.setdefault(c["grupo"], {"grupo": c["grupo"], "concepto": c["concepto"],
                                           "unidad": c["unidad"], "cuentas": 0, "con_dato": 0,
                                           "meses": [0.0] * 12})
        g["cuentas"] += 1
        g["con_dato"] += 1 if con_dato else 0
        for i, v in enumerate(meses):
            if v is not None:
                g["meses"][i] += v

    fuera = []
    for k in sorted(set(por_clave) - conocidas):
        vals = por_clave[k]
        fuera.append({"clave": k, "grupo": k.split("-")[0], "depto": k.split("-")[1],
                      "meses": [float(vals[m]) if m in vals else None for m in range(1, 13)],
                      "total": float(sum(vals.values(), Decimal("0")))})

    return {
        "version_catalogo": catalogo.get("version", ""),
        "meses_cargados": sorted(set(int(m) for m in meses_cargados)),
        "grupos": sorted(grupos.values(), key=lambda g: g["grupo"]),
        "cuentas": cuentas,
        "fuera_de_catalogo": fuera,
        "cuentas_con_dato": sum(1 for c in cuentas if c["con_dato"]),
    }


# ═══ El plan (Budget / Forecast) en la misma estructura ═══════════════════════
#
# Owner, 2026-11-10: «quiero mapear budget 2027 y forecast 2026 working separado
# por rooms y villas» · «por ahora en budget me interesa tipo de habitación al
# menos» · «available rooms per room type» · «occupied room per room type» · «las
# estadísticas de spa, laundry».
#
# El plan no se arma acá: sale de lo que el sistema ya calcula (noches por tipo
# del motor, Spa del ingreso, kilos de la config del reparto). Esto solo lo pone
# al lado de lo que registra Integrity, con la misma llave: depto (0110 Rooms /
# 0115 Villas / 0116 Residencias) × tipo de habitación (nivel 7).

#: El rótulo de cada depto de habitaciones.
DEPTOS_HAB = {"0110": "Rooms", "0115": "Villas", "0116": "Residencias"}

#: Grupos de Integrity que son tratamientos (los 9210–9216 son fitness).
GRUPOS_TRATAMIENTOS = {f"92{n:02d}" for n in range(1, 10)}

#: Kilos: área → cuenta de Integrity. 9702 trae Spa, Huéspedes y Otros con el
#: MISMO código (ver la lista de correcciones): hasta que contabilidad los
#: separe, el real de esas tres áreas llega junto en 9702.
KILOS_AREA = [("rooms", "9700", "Rooms (ropa de cama y toallas)"),
              ("fb", "9701", "A&B"),
              ("spa", "9702", "Spa"),
              ("uniformes", "9702", "Uniformes"),
              ("huespedes", "9702", "Huéspedes")]


def real_por_tipo(agregado: dict, n7_a_codigo: dict[str, str]) -> dict:
    """Noches ocupadas de Integrity (9000) por (depto, código de tipo) y mes,
    sumando todos los segmentos. `n7_a_codigo`: '01' → 'BL01'."""
    out: dict[tuple[str, str], list[float | None]] = {}
    for (mes, k), a in agregado.items():
        p = k.split("-")
        if p[0] != "9000":
            continue
        codigo = n7_a_codigo.get(p[5], "") if p[5] != "00" else ""
        # None = el mes no tiene movimiento: no es lo mismo que «cero noches».
        fila = out.setdefault((p[1], codigo), [None] * 12)
        fila[mes - 1] = (fila[mes - 1] or 0.0) + float(a["valor"])
    return out


def real_por_grupos(agregado: dict, grupos: set[str]) -> list[float | None]:
    """La suma de los grupos de Integrity pedidos, por mes (None si no hay dato)."""
    meses: list[float | None] = [None] * 12
    for (mes, k), a in agregado.items():
        if k.split("-")[0] in grupos:
            meses[mes - 1] = (meses[mes - 1] or 0.0) + float(a["valor"])
    return meses


def real_horas_por_depto(agregado: dict, grupo: str = "9980") -> dict[str, list[float | None]]:
    """Horas de Integrity de un grupo (9980 = regulares) por depto y mes, sumando
    todas las posiciones del depto. La llave es la de planilla: 9980-DEPTO-POS-…"""
    out: dict[str, list[float | None]] = {}
    for (mes, k), a in agregado.items():
        p = k.split("-")
        if p[0] != grupo:
            continue
        fila = out.setdefault(p[1], [None] * 12)
        fila[mes - 1] = (fila[mes - 1] or 0.0) + float(a["valor"])
    return out


def armar_horas(horas_plan: dict[str, list[float]], nombres: dict[str, str],
                agregado_real: dict) -> dict:
    """Horas regulares del plan (240 × FTE, ver `engine/jornada.py`) al lado de
    la 9980 de Integrity, por depto de planilla. Un depto que está en uno solo
    de los dos lados igual aparece: es justo lo que hay que mirar."""
    real = real_horas_por_depto(agregado_real)
    filas = []
    for d in sorted(set(horas_plan) | set(real)):
        plan = horas_plan.get(d) or [None] * 12
        filas.append({"depto": d, "nombre": nombres.get(d, ""), "plan": plan,
                      "real": real.get(d) or [None] * 12})
    def suma(campo):
        return [sum(f[campo][i] for f in filas if f[campo][i] is not None)
                if any(f[campo][i] is not None for f in filas) else None for i in range(12)]
    return {"deptos": filas, "total": {"plan": suma("plan"), "real": suma("real")}}


def armar_plan(tipos: list[dict], por_tipo: dict, total_sin_tipo: dict,
               spa: list[float | None], kilos: dict[str, list[float]],
               agregado_real: dict) -> dict:
    """Arma la comparación Plan vs. Integrity.

    `tipos`: [{"codigo","nombre","depto","n7","unidades"}] en el orden del inventario.
    `por_tipo`: {(codigo, mes): {"disponibles","ocupadas","pax"}} del plan.
    `total_sin_tipo`: {mes: {"disponibles","ocupadas"}} para los meses en que el
        escenario no tiene la apertura por tipo (Forecast: los meses propios).
    `spa`: tratamientos del plan por mes. `kilos`: {área: 12 meses}.
    """
    n7_a_codigo = {t["n7"]: t["codigo"] for t in tipos}
    real = real_por_tipo(agregado_real, n7_a_codigo)

    habitaciones = []
    for dep, rotulo in DEPTOS_HAB.items():
        filas = []
        for t in (x for x in tipos if x["depto"] == dep):
            disp = [por_tipo.get((t["codigo"], m), {}).get("disponibles") for m in range(1, 13)]
            ocup = [por_tipo.get((t["codigo"], m), {}).get("ocupadas") for m in range(1, 13)]
            pax = [por_tipo.get((t["codigo"], m), {}).get("pax") for m in range(1, 13)]
            r = real.get((dep, t["codigo"]))
            filas.append({
                "codigo": t["codigo"], "nombre": t["nombre"], "n7": t["n7"], "unidades": t["unidades"],
                "cuenta": f"9000-{dep}-SEG-N4-001-DD-{t['n7']}",
                "disponibles": disp, "ocupadas": ocup, "pax": pax,
                "ocupacion": [(o / d) if (d and o is not None) else None for o, d in zip(ocup, disp)],
                "real_ocupadas": r if r is not None else [None] * 12,
            })
        # Un depto sin un solo dato —ni del plan ni de Integrity— no se muestra:
        # pasa en 2024 y 2025, que no tienen apertura por tipo. Un depto con
        # ceros (Residencias con 0 unidades) SÍ se muestra: el cero es un dato.
        if not any(v is not None for f in filas
                   for c in ("disponibles", "ocupadas", "real_ocupadas") for v in f[c]):
            continue

        def suma(campo):
            return [sum(f[campo][i] for f in filas if f[campo][i] is not None)
                    if any(f[campo][i] is not None for f in filas) else None for i in range(12)]
        sd, so = suma("disponibles"), suma("ocupadas")
        habitaciones.append({
            "depto": dep, "rotulo": rotulo, "tipos": filas,
            "total": {"disponibles": sd, "ocupadas": so, "pax": suma("pax"),
                      "ocupacion": [(o / d) if (d and o is not None) else None for o, d in zip(so, sd)],
                      "real_ocupadas": suma("real_ocupadas") if any(
                          v is not None for f in filas for v in f["real_ocupadas"]) else [None] * 12},
        })

    sin_tipo = None
    if total_sin_tipo:
        sin_tipo = {
            "disponibles": [total_sin_tipo.get(m, {}).get("disponibles") for m in range(1, 13)],
            "ocupadas": [total_sin_tipo.get(m, {}).get("ocupadas") for m in range(1, 13)],
        }

    lav = []
    for area, cuenta, rotulo in KILOS_AREA:
        if area in kilos:
            lav.append({"area": area, "rotulo": rotulo, "cuenta": cuenta, "plan": kilos[area]})
    real_kilos = {c: real_por_grupos(agregado_real, {c}) for c in ("9700", "9701", "9702")}

    return {
        "habitaciones": habitaciones,
        "sin_tipo": sin_tipo,
        "spa": {"plan": spa, "real": real_por_grupos(agregado_real, GRUPOS_TRATAMIENTOS),
                "cuentas": "9201–9209"},
        "lavanderia": {"plan": lav, "real": real_kilos},
    }
