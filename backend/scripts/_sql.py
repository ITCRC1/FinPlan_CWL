# -*- coding: utf-8 -*-
"""Corredor de SQL de SOLO LECTURA contra producción (verificación 2da opinión).

    python -m scripts._sql "select ..."
    python -m scripts._sql --file consulta.sql

Rechaza cualquier cosa que no empiece con SELECT/WITH.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def run(sqls: list[str]) -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import text
    from app.db import SessionLocal

    async with SessionLocal() as db:
        for sql in sqls:
            s = sql.strip().rstrip(";")
            if not s:
                continue
            head = s.lstrip().split(None, 1)[0].upper()
            if head not in ("SELECT", "WITH"):
                raise SystemExit(f"SOLO LECTURA: rechazado -> {head}")
            res = await db.execute(text(s))
            cols = list(res.keys())
            rows = res.fetchall()
            print("| " + " | ".join(cols))
            for r in rows:
                print("| " + " | ".join("" if v is None else str(v) for v in r))
            print(f"({len(rows)} filas)\n")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        txt = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
        parts = [p for p in txt.split(";\n") if p.strip()]
    else:
        parts = [sys.argv[1]]
    asyncio.run(run(parts))
