# -*- coding: utf-8 -*-
"""Abrir las cuentas de un departamento en el checkbook, en cero.

**El problema.** Para empezar a presupuestar un departamento hacen falta sus
líneas, y no había forma de crearlas desde la pantalla: el Club Madresal tenía
planilla e ingreso y cero cuentas de OPEX, y quedaba esperando a que alguien las
insertara por detrás. El sembrador que existía en `opex_api` pedía la lista de
cuentas en el cuerpo o usaba 27 escritas a mano — no servía para «las que le
tocan a este departamento».

**De dónde salen las cuentas.** De `account_mapping`, que es el mismo catálogo
que decide a qué línea del P&L va cada una. Así lo que se abre para digitar y lo
que el motor sabe rutear son la misma lista, y un departamento nuevo no necesita
que nadie mantenga una segunda copia.

**Siempre en cero.** No mueve un centavo del P&L: abre la puerta para digitar.
Y no pisa lo que ya existe — sembrar dos veces no duplica ni borra.

La planilla NO se siembra: una línea de gasto vacía es una cuenta esperando un
monto, pero una fila de planilla vacía sería una persona que no existe. Ahí lo
que se abre es el selector, que ya ofrece todos los departamentos.
"""
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.api._candado import candado
from app.db import get_db
from app.models.cost_entry import CostEntry
from app.models.mapping import AccountMapping
from app.models.opex_entry import OpexEntry

router = APIRouter(tags=["sembrar-cuentas"])

# Clase USALI → dónde vive esa línea en el checkbook.
DESTINO = {"7": (OpexEntry, "OPEX"), "5": (CostEntry, "Costos")}


class SembrarIn(BaseModel):
    dept_code: str
    clases: list[str] = ["7", "5"]      # OPEX y costo de ventas


@router.post("/scenarios/{scenario_id}/sembrar-cuentas/")
async def sembrar_cuentas(
    scenario_id: str, body: SembrarIn, db: AsyncSession = Depends(get_db),
):
    scenario = await candado(db, scenario_id)
    dept = (body.dept_code or "").strip()
    if not dept:
        raise ErrorApi(422, "departamento.requerido")

    delcatalogo: dict[str, list[tuple[str, str]]] = {}
    for m in (await db.execute(select(AccountMapping).where(
            AccountMapping.active_status == "YES",
            AccountMapping.dept_code == dept))).scalars():
        cuenta = (m.account_code or "").strip()
        clase = cuenta[:1]
        if clase in DESTINO:
            nombre = (m.account_name_example or "").split("|")[0].strip()
            delcatalogo.setdefault(clase, []).append((cuenta, nombre or cuenta))

    resumen = []
    for clase in body.clases:
        if clase not in DESTINO:
            raise ErrorApi(422, "clase.no_soportada", clase=clase)
        Model, etiqueta = DESTINO[clase]
        cuentas = sorted(set(delcatalogo.get(clase, [])))
        ya = {c for (c,) in await db.execute(select(Model.account_code).where(
            Model.scenario_id == scenario_id, Model.dept_code == dept).distinct())}
        nuevas = 0
        for cuenta, nombre in cuentas:
            if cuenta in ya:
                continue
            fila = Model(id=str(uuid.uuid4()), scenario_id=scenario_id,
                         hotel_id=scenario.hotel_id, dept_code=dept,
                         account_code=cuenta, account_name=nombre)
            db.add(fila)
            nuevas += 1
        resumen.append({"clase": clase, "nombre": etiqueta,
                        "en_el_catalogo": len(cuentas),
                        "ya_estaban": len(cuentas) - nuevas, "nuevas": nuevas})
    await db.commit()

    total = sum(r["nuevas"] for r in resumen)
    return {
        "dept_code": dept,
        "creadas": total,
        "detalle": resumen,
        "nota": ("Las líneas quedan en cero: no mueven el P&L, solo dejan dónde "
                 "digitar. Si el catálogo no tiene cuentas para este "
                 "departamento, no se crea ninguna — primero hay que mapearlas "
                 "en Master Data."),
    }
