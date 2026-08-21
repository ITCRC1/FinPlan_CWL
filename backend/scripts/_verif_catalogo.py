# -*- coding: utf-8 -*-
"""SOLO LECTURA. Verificación independiente del catálogo de departamentos.

Compara `department_catalog` de PRODUCCIÓN contra lo que produce
`app.seed_department_catalog.build_rows()`, y busca:
  - filas que el seed construye y en la base están DISTINTAS
  - nombres duplicados
  - padres que apuntan a un departamento que no existe
  - ciclos en la cadena de padres
  - departamentos activos que no aparecen en ninguna pantalla
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

CAMPOS = ["dept_name", "name_en", "name_aliases", "usali_class", "default_pl_group",
          "pl_kind", "is_revenue_dept", "is_allocation_source", "parent_dept_code",
          "display_order", "active"]


async def main() -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.department_catalog import DepartmentCatalog
    from app.seed_department_catalog import build_rows

    esperado = {r["dept_code"]: r for r in build_rows()}
    async with SessionLocal() as db:
        filas = (await db.execute(select(DepartmentCatalog))).scalars().all()
    real = {f.dept_code: f for f in filas}

    print(f"catalogo prod = {len(real)} filas | seed construye = {len(esperado)}")
    extra = sorted(set(real) - set(esperado))
    falta = sorted(set(esperado) - set(real))
    print(f"\n[1] En prod y NO construidos por el seed (esperado: 0115/0116): {extra}")
    print(f"[2] Construidos por el seed y AUSENTES en prod (debe ser vacio): {falta}")

    print("\n[3] Filas que el seed construye y en la base estan DISTINTAS:")
    difs = 0
    for code in sorted(esperado):
        if code not in real:
            continue
        e, r = esperado[code], real[code]
        for c in CAMPOS:
            ev, rv = e.get(c), getattr(r, c)
            if c == "display_order":
                continue  # el orden lo pisan las migraciones 0115/0116
            if (ev or None) != (rv or None):
                print(f"   {code:<6} {c:<20} seed={ev!r:<34} base={rv!r}")
                difs += 1
    print(f"   -> {difs} diferencias de campo")

    print("\n[4] display_order (informativo, seed vs base):")
    for code in sorted(esperado):
        if code in real and esperado[code]["display_order"] != real[code].display_order:
            print(f"   {code:<6} seed={esperado[code]['display_order']:<4} base={real[code].display_order}")

    print("\n[5] Nombres duplicados en el catalogo:")
    por_nombre: dict[str, list[str]] = {}
    for f in filas:
        por_nombre.setdefault((f.dept_name or "").strip().lower(), []).append(f.dept_code)
    dup = {n: c for n, c in por_nombre.items() if len(c) > 1}
    print("   " + (str(dup) if dup else "ninguno"))

    print("\n[6] Alias duplicados (dos deptos con el mismo keyword):")
    por_alias: dict[str, list[str]] = {}
    for f in filas:
        for a in (f.name_aliases or []):
            por_alias.setdefault(str(a).strip().lower(), []).append(f.dept_code)
    dupa = {n: c for n, c in por_alias.items() if len(c) > 1}
    print("   " + (str(dupa) if dupa else "ninguno"))

    print("\n[7] parent_dept_code que apunta a un depto inexistente:")
    huerf = [(f.dept_code, f.parent_dept_code) for f in filas
             if (f.parent_dept_code or "").strip() and f.parent_dept_code not in real]
    print("   " + (str(huerf) if huerf else "ninguno"))

    print("\n[8] Ciclos / cadenas de padres:")
    ciclos = []
    cadenas = []
    for f in filas:
        visto, cur, camino = set(), f.dept_code, []
        while True:
            p = (real[cur].parent_dept_code or "").strip() if cur in real else ""
            if not p:
                break
            camino.append(p)
            if p in visto or p == f.dept_code:
                ciclos.append((f.dept_code, camino))
                break
            visto.add(p)
            cur = p
        if len(camino) > 1:
            cadenas.append((f.dept_code, camino))
    print("   ciclos: " + (str(ciclos) if ciclos else "ninguno"))
    print("   cadenas de mas de 1 salto: " + (str(cadenas) if cadenas else "ninguna"))

    print("\n[9] Padres que a su vez son hijos (nieto -> abuelo):")
    nietos = [(f.dept_code, f.parent_dept_code,
               real[f.parent_dept_code].parent_dept_code)
              for f in filas
              if (f.parent_dept_code or "") in real
              and (real[f.parent_dept_code].parent_dept_code or "").strip()]
    print("   " + (str(nietos) if nietos else "ninguno"))

    print("\n[10] Deptos inactivos:")
    print("   " + str([f.dept_code for f in filas if not f.active]) or "ninguno")


if __name__ == "__main__":
    asyncio.run(main())
