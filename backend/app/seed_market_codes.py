# -*- coding: utf-8 -*-
"""Siembra los market codes desde `seed_data/market_codes.json`.

Idempotente y **no destructivo**, misma regla que el resto de los seeds: inserta
lo que falta, y **NO pisa lo que el owner haya editado en la app**. El nombre y
el canal son suyos: si los cambia en pantalla, un redeploy no puede revertirlos.

Lo unico que el seed re-afirma es la EXISTENCIA del codigo y su orden.
"""
import json
import pathlib

from sqlalchemy import select

from app.models.market_code import CANALES, MarketCode

ARCHIVO = pathlib.Path(__file__).parent / "seed_data" / "market_codes.json"


def leer() -> list[dict]:
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))["codigos"]
    vistos = set()
    for c in datos:
        code = str(c["code"]).strip()
        if not code:
            raise ValueError("hay un market code sin codigo")
        if code in vistos:
            raise ValueError(f"{code}: market code repetido")
        vistos.add(code)
        canal = c.get("canal", "")
        if canal and canal not in CANALES:
            raise ValueError(f"{code}: el canal '{canal}' no esta en CANALES")
    return datos


async def seed_market_codes(db) -> dict:
    codigos = leer()
    actuales = {m.code: m for m in (await db.execute(select(MarketCode))).scalars()}
    nuevos = 0
    for c in codigos:
        code = str(c["code"]).strip()
        m = actuales.get(code)
        if m is None:
            db.add(MarketCode(code=code, nombre=c.get("nombre", ""),
                              canal=c.get("canal", ""), orden=c.get("orden", 0),
                              activo=True))
            nuevos += 1
        else:
            # Solo el orden. El nombre y el canal son del owner.
            m.orden = c.get("orden", m.orden)
    await db.flush()
    return {"total": len(codigos), "nuevos": nuevos}
