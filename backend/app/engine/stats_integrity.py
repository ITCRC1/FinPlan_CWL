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
