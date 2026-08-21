# -*- coding: utf-8 -*-
"""Escribe en `actual_entries` lo que trajo un origen. Con vista previa.

**Tres reglas, y las tres salieron de errores que ya pasaron en este proyecto:**

1. **Se reemplaza SOLO el período que se trajo.** Si se piden enero y febrero, no
   se toca marzo. Traer «todo el año» y pisar entero es como se borra sin querer
   un mes que estaba bien.

2. **Dentro de ese período, lo que el origen ya no reporta se pone en cero.** Si
   contabilidad borró un asiento de enero, dejar el monto viejo sería peor que
   no importar: el número quedaría sin respaldo en ningún lado.

3. **No se escribe si hay cuentas sin mapeo**, salvo que se pida explícitamente.
   Un import que se traga tres cuentas deja un P&L que cuadra consigo mismo y no
   cuadra con la realidad. Es la lección de los 21 departamentos: el total seguía
   dando bien.

Y por encima de todo: **vista previa primero**. Es la norma del owner en todo el
sistema — se mira antes de que escriba.
"""
from decimal import Decimal

from sqlalchemy import select

from app.models.actual_entry import ActualEntry
from app.origenes.traductor import MESES


def _resumen_por_mes(filas: list[dict], meses: list[int]) -> dict[str, float]:
    return {MESES[m - 1]: float(sum(Decimal(str(f[MESES[m - 1]])) for f in filas))
            for m in meses}


async def previsualizar(session, scenario, traduccion: dict) -> dict:
    """Qué pasaría si se aplicara. NO escribe nada."""
    filas = traduccion["filas"]
    meses = traduccion["meses"]
    cols = [MESES[m - 1] for m in meses]

    actuales = (await session.execute(
        select(ActualEntry).where(ActualEntry.scenario_id == scenario.id)
    )).scalars().all()
    por_llave = {(e.dept_code or "", e.account_code, e.outlet or ""): e for e in actuales}

    nuevas, cambian = 0, 0
    for f in filas:
        k = (f["dept_code"], f["account_code"], f["outlet"])
        e = por_llave.get(k)
        if e is None:
            nuevas += 1
        elif any(Decimal(str(getattr(e, c))) != Decimal(str(f[c])) for c in cols):
            cambian += 1

    llaves_nuevas = {(f["dept_code"], f["account_code"], f["outlet"]) for f in filas}
    # Filas que HAY y el origen ya no reporta: sus meses del período van a cero.
    # Se cuentan aparte porque es el cambio que más sorprende al mirarlo después.
    se_ponen_en_cero = [
        {"dept_code": k[0], "account_code": k[1], "outlet": k[2],
         "monto_actual": float(sum(Decimal(str(getattr(e, c))) for c in cols))}
        for k, e in por_llave.items()
        if k not in llaves_nuevas
        and any(Decimal(str(getattr(e, c))) != 0 for c in cols)
    ]

    return {
        "escribe": False,
        "meses": meses,
        "filas_nuevas": nuevas,
        "filas_que_cambian": cambian,
        "filas_que_se_ponen_en_cero": se_ponen_en_cero,
        "total_por_mes": _resumen_por_mes(filas, meses),
        "sin_mapeo": traduccion["sin_mapeo"],
        "total_sin_mapeo": float(sum(x["monto"] for x in traduccion["sin_mapeo"])),
        "se_puede_aplicar": not traduccion["sin_mapeo"],
    }


async def aplicar(session, scenario, traduccion: dict,
                  permitir_sin_mapeo: bool = False) -> dict:
    """Escribe. Devuelve lo mismo que la vista previa, más lo que hizo."""
    if traduccion["sin_mapeo"] and not permitir_sin_mapeo:
        raise ValueError(
            f"{len(traduccion['sin_mapeo'])} cuentas del origen no tienen "
            "equivalencia. Cargalas en el mapeo, o pedí aplicar igual sabiendo "
            "que esos montos NO van a entrar."
        )

    filas = traduccion["filas"]
    meses = traduccion["meses"]
    cols = [MESES[m - 1] for m in meses]

    actuales = (await session.execute(
        select(ActualEntry).where(ActualEntry.scenario_id == scenario.id)
    )).scalars().all()
    por_llave = {(e.dept_code or "", e.account_code, e.outlet or ""): e for e in actuales}

    escritas, puestas_en_cero = 0, 0
    llaves_nuevas = set()
    for f in filas:
        k = (f["dept_code"], f["account_code"], f["outlet"])
        llaves_nuevas.add(k)
        e = por_llave.get(k)
        if e is None:
            e = ActualEntry(
                scenario_id=scenario.id, hotel_id=scenario.hotel_id,
                dept_code=f["dept_code"], account_code=f["account_code"],
                account_name=f["account_name"], outlet=f["outlet"],
            )
            session.add(e)
            por_llave[k] = e
        elif f["account_name"]:
            e.account_name = f["account_name"]
        # SOLO las columnas del período. Los otros meses ni se tocan.
        for c in cols:
            setattr(e, c, f[c])
        escritas += 1

    for k, e in por_llave.items():
        if k in llaves_nuevas:
            continue
        if any(Decimal(str(getattr(e, c))) != 0 for c in cols):
            for c in cols:
                setattr(e, c, Decimal("0"))
            puestas_en_cero += 1

    await session.commit()
    return {
        "escribe": True,
        "meses": meses,
        "filas_escritas": escritas,
        "filas_puestas_en_cero": puestas_en_cero,
        "total_por_mes": _resumen_por_mes(filas, meses),
        "sin_mapeo": traduccion["sin_mapeo"],
        "aplicado_con_faltantes": bool(traduccion["sin_mapeo"]),
    }
