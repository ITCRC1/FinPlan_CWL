# -*- coding: utf-8 -*-
"""Semilla del módulo de Costos para Negociación de Grupos.

Siembra el mapa de temporadas y los parámetros por defecto del spec
(`COSTOS_GRUPOS.md` §2 y §3.1).

⚠️ **NO pisa lo que el owner edite.** Sólo inserta lo que falta. El mapa de
temporadas es explícitamente revisable —el propio spec marca noviembre en MEDIA
como «una decisión comercial, no contable»— así que una corrida del seed no
puede deshacer un cambio hecho en la app.

⚠️ **Los días abiertos son DATO, no fórmula.** Verificado contra producción: el
cierre anual es **octubre** (el spec lo daba por confirmar), pero no está en
todos los escenarios — el Forecast Working 2026 y el Budget Final 2027 lo traen
cerrado; el Budget Working 2027 y los Actuals lo tienen abierto. La diferencia
mueve el overhead por habitación disponible de $216 a $198, un 9% del piso.
"""
from __future__ import annotations

import calendar
import json
import pathlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hotel_actual import HOTEL_ID
from app.models.costos_grupos import CfgParametro, CfgTemporada

ARCHIVO_RACK = (pathlib.Path(__file__).parent / "seed_data" / HOTEL_ID
                / "rack_rates.json")

# El mapa del spec §2. ALTA arranca en diciembre a propósito: el ciclo comercial
# no coincide con el año calendario.
MAPA = {
    12: "ALTA", 1: "ALTA", 2: "ALTA", 3: "ALTA", 4: "ALTA",
    5: "MEDIA", 6: "MEDIA", 7: "MEDIA", 8: "MEDIA", 11: "MEDIA",
    9: "BAJA", 10: "BAJA",
}

# Octubre cerrado. Es el único mes con días abiertos distintos de sus días
# naturales, y va acá y no en una fórmula porque el día que el hotel decida
# cerrar otro mes —o medio mes— esto es una fila, no un `if`.
CERRADOS = {10}

# §3.1. El valor viaja como texto: conviven números y opciones.
PARAMETROS = {
    "management_fee_pct": "0.03",
    "margen_protegido_pct": "0.15",
    # M2 = overhead entre habitaciones DISPONIBLES. Es el default del spec y
    # es el correcto para un piso: se mantiene estable entre temporadas
    # ($207 / $221 / $216) mientras que como % del revenue se dispara
    # (24.5% / 66.2%). Quien tiene que cubrirlo todo es la Golden Rate, que
    # divide entre ocupadas — el módulo usa las dos, cada una donde sirve.
    "metodo_absorcion": "M2",
    # B = el mes cerrado se absorbe en el ciclo anual. Con A, el costo de
    # octubre cae sobre las 900 noches de setiembre y las duplica: la
    # operación terminaría rechazando el único negocio del mes más flojo.
    "tratamiento_mes_cerrado": "B",
    "incluir_capital_en_piso": "NO",
    # NO hasta que se resuelva el hueco 1 del spec: el Sustainability Fee son
    # $238.325 con CERO costo asignado. Si el aporte a conservación es su
    # contrapartida, el fee no es margen libre y acreditarlo contra el piso
    # sobrestima el margen del grupo en hasta $92 por habitación-noche.
    "sustainability_libre": "NO",
    # El escenario del que sale todo. Decisión del owner (2026-08-19):
    # Forecast Working 2026. Verificado que reproduce las semillas del §7 —
    # 3.600 disponibles, 2.587 ocupadas, 4.883 noches-huésped, 71,86% — y que
    # trae octubre cerrado.
    "escenario_base": "FORECAST/2026/Working",
    # De donde salen las TARIFAS. Va aparte del escenario de costos porque el
    # rack vive SOLO en los BUDGET: el Forecast Working 2026 tiene cero tarifas,
    # cero canales y cero paquetes. Verificado en produccion (2026-08-19).
    #
    # Regla del owner: los grupos se negocian desde la tarifa rack. Los costos
    # siguen saliendo del Forecast —son los validados contra las semillas del
    # §7— y el precio de referencia sale de aca.
    "escenario_tarifas": "BUDGET/2027/Working",
}


async def seed_costos_grupos(db: AsyncSession) -> dict:
    """Idempotente: cuenta lo que crea y no toca lo que ya está."""
    nuevas_temp = 0
    existentes = {
        t.mes for t in (await db.execute(
            select(CfgTemporada).where(CfgTemporada.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    for mes, temporada in MAPA.items():
        if mes in existentes:
            continue
        # Año no bisiesto: febrero 28. El día 29 de un bisiesto suma una
        # habitación-noche disponible y lo recoge el escenario, que es quien
        # manda sobre la capacidad real.
        dias = calendar.monthrange(2026, mes)[1]
        db.add(CfgTemporada(
            hotel_id=HOTEL_ID, mes=mes, temporada=temporada,
            dias=dias, dias_abiertos=0 if mes in CERRADOS else dias,
        ))
        nuevas_temp += 1

    nuevos_par = 0
    ya = {
        p.clave for p in (await db.execute(
            select(CfgParametro).where(CfgParametro.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    for clave, valor in PARAMETROS.items():
        if clave in ya:
            continue
        db.add(CfgParametro(hotel_id=HOTEL_ID, clave=clave, valor=valor))
        nuevos_par += 1

    return {
        "temporadas": len(MAPA), "temporadas_nuevas": nuevas_temp,
        "parametros": len(PARAMETROS), "parametros_nuevos": nuevos_par,
    }


# La composición verificada contra las semillas del §7. Es la SEMILLA: desde
# acá se edita en la app, y una corrida del seed no la pisa.
#
# ⚠️ SUSTAINABILITY va SEPARADO de «Other / Misc» — decisión del owner
# (2026-08-19). La semilla del spec ($92,12 por habitación ocupada) sólo
# cerraba con los dos juntos, porque en el libro de origen eran un mismo cubo.
# Separados, Sustainability queda en $54,38 y MISC_OTHER pasa a ser un
# departamento propio con $97.656 de contribución en cuatro meses.
COMPOSICION = {
    # (concepto, rol): líneas del P&L
    ("ROOMS", "propio"): ["OPEX_ROOMS"],
    ("ROOMS", "ingreso"): ["REV_ROOMS"],
    # F&B: el propio incluye las TRES cuentas de costo de venta, MISC incluida.
    # Verificado: (170.056,48 + 129.073,94 + 44.271,53 + 3.476,84) / 4.883 = $71,04.
    ("FB", "propio"): ["OPEX_FB", "COS_FB_FOOD", "COS_FB_BEV", "COS_FB_MISC"],
    ("FB", "venta"): ["COS_FB_FOOD", "COS_FB_BEV", "COS_FB_MISC"],
    ("FB", "ingreso"): ["REV_FB", "REV_FB_BEV", "REV_FB_MISC"],
    ("TOURS", "propio"): ["OPEX_TOURS", "COS_TOURS"],
    ("TOURS", "venta"): ["COS_TOURS"],
    ("TOURS", "ingreso"): ["REV_TOURS"],
    # ⚠️ Transporte incluye su costo de VENTA en el propio. Sin eso da $16,78
    # contra los $30,80 de la semilla — el piso saldría a la mitad.
    ("TRANSPORTATION", "propio"): ["OPEX_TRANSPORTATION", "COS_TRANSPORTATION"],
    ("TRANSPORTATION", "venta"): ["COS_TRANSPORTATION"],
    ("TRANSPORTATION", "ingreso"): ["REV_TRANSPORTATION"],
    ("SPA", "propio"): ["OPEX_SPA"],
    ("SPA", "ingreso"): ["REV_SPA"],
    ("RETAIL", "propio"): ["COS_RETAIL", "OPEX_RETAIL"],
    ("RETAIL", "venta"): ["COS_RETAIL"],
    ("RETAIL", "ingreso"): ["REV_RETAIL"],
    ("SUSTAINABILITY", "ingreso"): ["REV_SUSTAINABILITY"],
    ("MISC_OTHER", "ingreso"): ["REV_MISC_OTHER"],
    ("LAUNDRY", "propio"): ["COS_LAUNDRY"],
    ("LAUNDRY", "ingreso"): ["REV_LAUNDRY"],
    # ⚠️ Estos tres estan en CERO en el escenario base, y van igual. Decision
    # del owner: entran TODOS los departamentos. Si el modulo cambia de
    # escenario —el Budget 2027, donde Club Madresal PIERDE 28.470— tienen
    # que aparecer solos; sin la fila, desapareceria un departamento entero de
    # la Golden Rate sin que nada fallara.
    ("CLUB", "propio"): ["OPEX_CLUB"],
    ("CLUB", "ingreso"): ["REV_CLUB"],
    ("INNOCEANA", "propio"): ["OPEX_INNOCEANA"],
    ("INNOCEANA", "ingreso"): ["REV_INNOCEANA"],
    ("AREC", "ingreso"): ["REV_AREC"],
}


async def seed_composicion(db: AsyncSession) -> dict:
    """Idempotente. No pisa lo que el owner edite en la app."""
    from app.models.costos_grupos import CfgComposicion

    ya = {
        (c.concepto, c.rol, c.line_code) for c in (await db.execute(
            select(CfgComposicion).where(CfgComposicion.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    nuevas = 0
    for (concepto, rol), codigos in COMPOSICION.items():
        for code in codigos:
            if (concepto, rol, code) in ya:
                continue
            db.add(CfgComposicion(hotel_id=HOTEL_ID, concepto=concepto,
                                  rol=rol, line_code=code))
            nuevas += 1
    total = sum(len(v) for v in COMPOSICION.values())
    return {"filas": total, "nuevas": nuevas}


# El tarifario RACK de referencia. Los 96 valores son una COPIA del Budget
# Working 2027 —el único escenario con tarifario— porque el owner los dio por
# válidos como punto de partida (2026-08-19). Desde acá se editan en la
# pantalla del módulo, y una corrida del seed NO los pisa.
def _rack_rates() -> list[dict]:
    """La lista de verdad vive en git, no en la base (misma regla que el mapeo)."""
    if not ARCHIVO_RACK.exists():
        # Una propiedad sin archivo abre la pantalla vacía, que es la verdad.
        return []
    return json.loads(ARCHIVO_RACK.read_text(encoding="utf-8")).get("tarifas", [])


async def seed_tarifas_rack(db: AsyncSession) -> dict:
    """Idempotente. NO pisa lo que el owner edite en la pantalla."""
    from decimal import Decimal

    from app.models.costos_grupos import CfgTarifaRack

    filas = _rack_rates()
    ya = {
        (t.room_type_code, t.mes) for t in (await db.execute(
            select(CfgTarifaRack).where(CfgTarifaRack.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    nuevas = 0
    for f in filas:
        clave = (f["room_type_code"], int(f["mes"]))
        if clave in ya:
            continue
        db.add(CfgTarifaRack(
            hotel_id=HOTEL_ID, room_type_code=f["room_type_code"],
            mes=int(f["mes"]), rack=Decimal(f["rack"]),
            neto=Decimal(f["neto"]), pax=Decimal(f["pax"]),
        ))
        nuevas += 1
    return {"filas": len(filas), "nuevas": nuevas}
