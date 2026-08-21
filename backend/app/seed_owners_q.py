"""Siembra el reporte `Owners Q`: `report_lines` + `report_line_mapping` + `capacidad`.

Mismo contrato que `seed_mapping`: IDEMPOTENTE Y NO DESTRUCTIVO. Inserta lo que
falta, actualiza lo que cambió, y lo que sobra se REPORTA pero no se toca —
borrar por ausencia le vaciaría el reporte a alguien en un redeploy.

Las 48 filas y las 68 `Línea P&L` viven en git (`seed_data/owners_q.json`),
no en la base. Es la misma regla que el resto del proyecto: el seed manda.

⚠️ GATE DE COBERTURA. Si una `Línea P&L` tiene reglas activas en el Account
Mapping y NO tiene fila destino, esto FALLA. No cae en un residual silencioso:
el residual es para cuentas sin regla, no para líneas sin ruteo. Una línea
nueva que nadie mapeó es un error de configuración y tiene que doler.
"""
import json
import pathlib
import uuid

from sqlalchemy import select

from app.hotel_actual import HOTEL_ID
from app.models.owners_q import Capacidad, ReportLine, ReportLineMapping

ARCHIVO = pathlib.Path(__file__).parent / "seed_data" / "owners_q.json"
REPORT_KEY = "owners_q"

#: `INCOME_TAXES` no tiene fila a propósito (D8: la última línea del reporte es
#: NET INCOME BEFORE TAXES). No es un hueco, es una exclusión.
SIN_FILA_A_PROPOSITO = {"INCOME_TAXES"}

#: Confirmado constante en 2025–2026. Vive en tabla igual (ver el modelo).
HABITACIONES_CWL = 30


def _campos(obj) -> dict:
    return {c.name: getattr(obj, c.name)
            for c in obj.__table__.columns
            if c.name not in ("id", "created_at", "updated_at")}


async def seed_owners_q(db, entidad: str | None = None,
                        anios=(2024, 2025, 2026, 2027)) -> dict:
    # ⚠️ La entidad es la de ESTA instalación. Con «CWL» clavado, un clon
    # sembraba las líneas del reporte bajo la entidad de Corcovado, y el
    # control de contaminación no lo veía: estas tablas se llavean por
    # `entidad`, no por `hotel_id`.
    entidad = entidad or HOTEL_ID
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    filas = datos["report_lines"]
    ruteo = datos["report_line_mapping"]

    # ── report_lines ─────────────────────────────────────────────────────────
    existentes = {
        (r.report_key, r.report_code): r
        for r in (await db.execute(
            select(ReportLine).where(ReportLine.report_key == REPORT_KEY)
        )).scalars().all()
    }
    nuevas = cambiadas = 0
    for f in filas:
        clave = (f["report_key"], f["report_code"])
        obj = existentes.get(clave)
        if obj is None:
            db.add(ReportLine(id=str(uuid.uuid4()), **f))
            nuevas += 1
        else:
            antes = _campos(obj)
            for k, v in f.items():
                setattr(obj, k, v)
            if _campos(obj) != antes:
                cambiadas += 1
    sobran_filas = sorted(k[1] for k in existentes
                          if k[1] not in {f["report_code"] for f in filas})

    # ── report_line_mapping ──────────────────────────────────────────────────
    ex_map = {
        (r.report_key, r.linea_pl): r
        for r in (await db.execute(
            select(ReportLineMapping).where(ReportLineMapping.report_key == REPORT_KEY)
        )).scalars().all()
    }
    nuevas_m = cambiadas_m = 0
    for m in ruteo:
        clave = (m["report_key"], m["linea_pl"])
        obj = ex_map.get(clave)
        if obj is None:
            db.add(ReportLineMapping(id=str(uuid.uuid4()), **m))
            nuevas_m += 1
        else:
            antes = _campos(obj)
            for k, v in m.items():
                setattr(obj, k, v)
            if _campos(obj) != antes:
                cambiadas_m += 1
    sobran_map = sorted(k[1] for k in ex_map
                        if k[1] not in {m["linea_pl"] for m in ruteo})

    # ── capacidad ────────────────────────────────────────────────────────────
    ex_cap = {
        (c.entidad, c.anio, c.mes)
        for c in (await db.execute(
            select(Capacidad).where(Capacidad.entidad == entidad)
        )).scalars().all()
    }
    nuevas_c = 0
    for anio in anios:
        for mes in range(1, 13):
            if (entidad, anio, mes) in ex_cap:
                continue        # lo que el owner haya editado NO se pisa
            db.add(Capacidad(id=str(uuid.uuid4()), entidad=entidad, anio=anio,
                             mes=mes, habitaciones_disponibles=HABITACIONES_CWL))
            nuevas_c += 1

    await db.flush()
    return {
        "filas": {"total": len(filas), "nuevas": nuevas, "cambiadas": cambiadas,
                  "sobran": sobran_filas},
        "ruteo": {"total": len(ruteo), "nuevas": nuevas_m, "cambiadas": cambiadas_m,
                  "sobran": sobran_map},
        "capacidad": {"nuevas": nuevas_c},
    }


async def verificar_cobertura(db) -> dict:
    """Gate A: toda `Línea P&L` con reglas activas tiene exactamente una fila.

    Se corre después de sembrar. Devuelve el detalle; el que decide si rompe
    el arranque es quien lo llama.
    """
    from app.models.mapping import AccountMapping

    reglas = (await db.execute(
        select(AccountMapping.report_line_code)
        .where(AccountMapping.report_id == "P&L_DETAIL_OWNERS")
    )).scalars().all()
    en_reglas = set(reglas)

    ruteo = {
        r.linea_pl: r.report_code
        for r in (await db.execute(
            select(ReportLineMapping).where(ReportLineMapping.report_key == REPORT_KEY)
        )).scalars().all()
    }
    codigos = {
        r.report_code
        for r in (await db.execute(
            select(ReportLine).where(ReportLine.report_key == REPORT_KEY)
        )).scalars().all()
    }

    huerfanas = sorted(en_reglas - set(ruteo) - SIN_FILA_A_PROPOSITO)
    sin_regla = sorted(set(ruteo) - en_reglas)
    destino_inexistente = sorted({c for c in ruteo.values() if c not in codigos})

    return {
        "ok": not huerfanas and not destino_inexistente,
        "lineas_en_reglas": len(en_reglas),
        "lineas_ruteadas": len(ruteo),
        # Reglas activas sin fila destino: ESTO ROMPE.
        "huerfanas": huerfanas,
        # Ruteadas pero sin ninguna regla todavía: se avisa, no rompe (es el
        # caso normal de una línea recién creada, como OH_CC_COMMISSIONS antes
        # de que su vigencia arranque).
        "ruteadas_sin_regla": sin_regla,
        "destino_inexistente": destino_inexistente,
    }
