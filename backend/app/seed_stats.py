# -*- coding: utf-8 -*-
"""Siembra el catálogo de cuentas estadísticas desde `seed_data/stats_catalog.json`.

**Idempotente y no destructivo**, misma regla que `seed_mapping`: inserta lo que
falta, actualiza lo que cambió, y NO borra lo que sobra. El seed corre en cada
arranque; borrar por ausencia le dejaría a alguien las estadísticas huérfanas en
un redeploy. Lo que sobra se reporta para mirarlo, no se toca.

**El JSON manda.** Está escrito en `alembic/versions/097_el_seed_manda_sobre_el_mapeo.py`
para el mapeo del P&L y aplica igual acá: una migración que toque `stat_accounts`
sin cambiar el JSON **se revierte sola en el siguiente deploy**, y el total sigue
cuadrando, así que no avisa.
"""
import json
import pathlib

from sqlalchemy import select

from app.models.stat_account import DIMENSIONES, StatAccount

ARCHIVO = pathlib.Path(__file__).parent / "seed_data" / "stats_catalog.json"


def leer_catalogo() -> list[dict]:
    """Las cuentas del JSON, ya validadas. Pura: la usan las pruebas sin base."""
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    cuentas = datos["cuentas"]

    vistos = set()
    for c in cuentas:
        code = str(c["code"])
        if not (len(code) == 4 and code.isdigit() and code[0] == "9"):
            raise ValueError(f"{code}: una cuenta estadística es 9 + 3 dígitos")
        if code in vistos:
            raise ValueError(f"{code}: código repetido en el catálogo")
        vistos.add(code)

        malas = set(c.get("dims", [])) - set(DIMENSIONES)
        if malas:
            raise ValueError(f"{code}: dimensión desconocida {sorted(malas)}")

        if c.get("agrega", "SUM") not in ("SUM", "FIN"):
            raise ValueError(f"{code}: `agrega` solo puede ser SUM o FIN")

        # ⚠️ ACÁ NO ENTRA DINERO (owner, 2026-08-14). Solo cantidades.
        #
        # La primera versión traía tres cuentas de venta de habitaciones —por
        # canal, país y segmento— que tenían que cuadrar contra `REV_ROOMS`. El
        # owner las descartó, y es la decisión correcta: cuadrarlas con una
        # prueba MITIGA el riesgo de tener dos verdades sobre el mismo dinero;
        # no tenerlas lo ELIMINA.
        #
        # La plata la reporta el P&L. Si algún día se quiere la venta abierta
        # por canal, el lugar es el P&L, no el catálogo estadístico.
        if c.get("dinero") or c.get("unidad") == "usd":
            raise ValueError(
                f"{code}: las cuentas estadísticas son de CANTIDADES, no de "
                "dinero. La plata la reporta el P&L; una apertura de la misma "
                "plata acá sería una segunda verdad sobre el mismo número."
            )
    return cuentas


def _campos(c: dict) -> dict:
    return {
        "grupo": str(c["grupo"]),
        "nombre_es": c["nombre_es"],
        "nombre_en": c.get("nombre_en", ""),
        "unidad": c["unidad"],
        "dims": ",".join(c.get("dims", [])),
        "agrega": c.get("agrega", "SUM"),
        "dinero": bool(c.get("dinero", False)),
        "amarra_con": c.get("amarra_con", ""),
        "deptos": ",".join(c.get("deptos", [])),
        "legado": c.get("legado", ""),
        "activa": bool(c.get("activa", True)),
    }


async def seed_stats(db) -> dict:
    cuentas = leer_catalogo()
    actuales = {a.code: a for a in (await db.execute(select(StatAccount))).scalars()}

    nuevas = cambiadas = 0
    for c in cuentas:
        code = str(c["code"])
        campos = _campos(c)
        obj = actuales.get(code)
        if obj is None:
            db.add(StatAccount(code=code, **campos))
            nuevas += 1
            continue
        if any(getattr(obj, k) != v for k, v in campos.items()):
            for k, v in campos.items():
                setattr(obj, k, v)
            cambiadas += 1

    sobran = sorted(set(actuales) - {str(c["code"]) for c in cuentas})
    await db.flush()
    return {"nuevas": nuevas, "cambiadas": cambiadas, "sobran": sobran,
            "total": len(cuentas)}
