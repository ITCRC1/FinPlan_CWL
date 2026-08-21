"""Apunta el proceso a la base de PRODUCCIÓN (solo lectura por convención).

Se importa ANTES que cualquier `app.*`, porque `app.db` arma el engine al
importarse. Lee las variables cacheadas de Railway; si no están, respeta el
DATABASE_URL que ya venga del entorno.
"""
from __future__ import annotations

import json
import os

_CACHE = os.environ.get(
    "FINPLAN_PGVARS",
    r"C:/Users/finco/AppData/Local/Temp/claude/pgvars.json")


def usar_produccion(cache: str = _CACHE) -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    with open(cache, encoding="utf-8") as f:
        v = json.load(f)
    url = v["DATABASE_PUBLIC_URL"].replace("postgresql://", "postgresql+asyncpg://")
    os.environ["DATABASE_URL"] = url
    return url
