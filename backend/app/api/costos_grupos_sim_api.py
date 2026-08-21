# -*- coding: utf-8 -*-
"""Simulador de grupos y salida a Ventas (spec §4.6, §4.9 y sub-tabs 12 y 13).

Dos endpoints y una diferencia deliberada entre ellos:

* `/simular/` es para **adentro**. Trae el costo desarmado, los cuatro pisos,
  el desplazamiento y el semáforo con su autorización.
* `/salida-ventas/` es para **la mesa**. Trae el precio mínimo por pax y
  **ningún costo** — ni total, ni por componente, ni el overhead. El spec lo
  pide en letras: «Sin costos visibles». Un vendedor con el costo a la vista
  negocia contra el costo, no contra el piso.

⚠️ Que el segundo endpoint sea otro endpoint y no un parámetro del primero es
a propósito: un `?ocultar_costos=true` que alguien olvide poner filtra el
costo, y no falla nada.
"""
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import get_current_user
from app.db import get_db
from app.engine import costos_grupos as cg
from app.hotel_actual import HOTEL_ID
from app.models.costos_grupos import CfgEscalon

router = APIRouter(prefix="/costos-grupos", tags=["costos-grupos"])


class Cotizacion(BaseModel):
    habitaciones: int
    noches: int
    pax: int
    mes: int
    # Precio propuesto por pax por noche. Si no viene, no hay semáforo — que es
    # honesto: sin precio no hay nada que semaforizar.
    precio_pax_noche: str | None = None
    amenidades_usd: str = "0"


def _d(v: str, campo: str) -> Decimal:
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, f"número inválido en {campo}: {v}")


CENTAVO = Decimal("0.01")


def _piso(v: Decimal) -> str:
    """Un MÍNIMO se redondea hacia ARRIBA.

    ⚠️ Redondear al centavo más cercano deja el precio publicado por debajo del
    piso cuando la fracción es menor a medio centavo. Es plata despreciable y
    es la clase de detalle que hace que un control diga «cumple» cuando no.
    """
    return str(v.quantize(CENTAVO, rounding=ROUND_CEILING))


def _dinero(v: Decimal) -> str:
    """Un importe informativo se redondea normal."""
    return str(v.quantize(CENTAVO, rounding=ROUND_HALF_UP))


async def _armar(db, c: Cotizacion):
    """Lo común a los dos endpoints. Devuelve (grupo, comisión, mes)."""
    if not 1 <= c.mes <= 12:
        raise HTTPException(400, f"mes fuera de rango: {c.mes}")
    if c.habitaciones <= 0 or c.noches <= 0 or c.pax <= 0:
        raise HTTPException(400, "habitaciones, noches y pax tienen que ser mayores que cero")
    # ⚠️ Un grupo con más habitaciones que el hotel no es un error de tipeo que
    # convenga tolerar: el costo saldría igual y nadie lo notaría.
    if c.pax < c.habitaciones:
        raise HTTPException(400, "hay más habitaciones que pax")

    sc = await cg.escenario_base(db, HOTEL_ID)
    if sc is None:
        raise HTTPException(409, "el escenario base no existe")

    par = await cg.cargar_parametros(db, HOTEL_ID)
    comp = await cg.cargar_composicion(db, HOTEL_ID)
    meses = await cg.hechos_mensuales(db, sc, HOTEL_ID)

    el_mes = meses[c.mes - 1]
    if el_mes.dias_abiertos == 0:
        raise HTTPException(409, f"el mes {c.mes} está cerrado: no se puede cotizar")

    dela_temporada = [m for m in meses if m.temporada == el_mes.temporada]
    factor = cg.factor_neto_del_rack(await cg.tarifas_rack(db, HOTEL_ID, c.mes))
    comision = (Decimal("1") - factor) if factor is not None else Decimal("0")

    reglas = (await db.execute(
        select(CfgEscalon).where(CfgEscalon.hotel_id == HOTEL_ID)
    )).scalars().all()

    grupo = cg.ensamblar_grupo(
        dela_temporada, comp, par, comision,
        Decimal(c.habitaciones), Decimal(c.noches), Decimal(c.pax),
        reglas_escalon=list(reglas),
        amenidades_usd=_d(c.amenidades_usd, "amenidades"),
        ciclo=meses, meses_del_grupo=[el_mes],
    )
    return grupo, comision, el_mes, sc


@router.post("/simular/")
async def simular(c: Cotizacion, db=Depends(get_db),
                  _=Depends(get_current_user)):
    """El grupo desarmado: costo, pisos, desplazamiento y semáforo."""
    g, comision, el_mes, sc = await _armar(db, c)

    zona = autoriza = None
    ingreso = margen = None
    if c.precio_pax_noche:
        precio = _d(c.precio_pax_noche, "precio")
        ing = precio * Decimal(c.pax) * Decimal(c.noches)
        zona = cg.semaforo(ing, g.ingreso_minimo)
        autoriza = cg.ZONAS[zona]
        ingreso = _dinero(ing)
        # Margen contra el costo integral, después de fee y comisión.
        neto = ing * (Decimal("1") - Decimal(
            (await cg.cargar_parametros(db, HOTEL_ID)).get(
                "management_fee_pct", "0.03")) - comision)
        margen = _dinero(neto - g.costo_total)

    return {
        "escenario": f"{sc.type}/{sc.year}/{sc.version}",
        "mes": el_mes.mes, "temporada": el_mes.temporada,
        "comision": str(comision),
        "grupo": {
            "habitaciones": str(g.habitaciones), "noches": str(g.noches),
            "pax": str(g.pax), "hab_noches": str(g.hab_noches),
            "noches_huesped": str(g.noches_huesped),
        },
        "costo": {
            "habitaciones": _dinero(g.costo_habitaciones),
            "fb": _dinero(g.costo_fb), "tours": _dinero(g.costo_tours),
            "transporte": _dinero(g.costo_transporte), "spa": _dinero(g.costo_spa),
            "amenidades": _dinero(g.costo_amenidades),
            "escalones": _dinero(g.costo_escalones),
            "overhead": _dinero(g.overhead), "total": _dinero(g.costo_total),
        },
        "desplazamiento": {
            "aplica": g.desplazamiento.aplica,
            "motivo": g.desplazamiento.motivo,
            "noches": str(g.desplazamiento.noches_desplazadas),
            "adr_esperado": str(g.desplazamiento.adr_esperado),
            "contribucion": str(g.desplazamiento.contribucion_desplazada),
            "ocupacion_pct": str(g.desplazamiento.ocupacion_pct),
            "habitaciones_libres": str(g.desplazamiento.habitaciones_libres),
        },
        "escalones": [
            {"descripcion": e.descripcion, "driver": e.driver,
             "umbral": str(e.umbral), "costo": str(e.costo)}
            for e in g.escalones
        ],
        "minimos": {
            "por_pax_noche": {k: _piso(v) for k, v in g.minimo_pax_noche.items()},
            "por_pax_estadia": {k: _piso(v) for k, v in g.minimo_pax_estadia.items()},
            "ingreso": {k: _piso(v) for k, v in g.ingreso_minimo.items()},
        },
        "propuesta": {"ingreso": ingreso, "margen": margen,
                      "zona": zona, "autoriza": autoriza},
        # ⚠️ Lo que la pantalla TIENE que mostrar. Un costo prorrateado que se
        # presenta como medido convierte un supuesto en un compromiso.
        "marginal_estimado": g.marginal_estimado,
        "prorrateados": g.prorrateados,
    }


@router.post("/salida-ventas/")
async def salida_ventas(c: Cotizacion, db=Depends(get_db),
                        _=Depends(get_current_user)):
    """El precio mínimo por pax. **Sin un solo costo** (spec sub-tab 13).

    ⚠️ Devuelve los Pisos 3 y 4 nada más. El Piso 1 y el Piso 2 son
    autorizaciones de excepción —hacen falta el GG y Finanzas— y ponerlos en la
    pantalla de Ventas los convierte en el precio de lista de cualquier
    negociación difícil.
    """
    g, _comision, el_mes, _sc = await _armar(db, c)

    zona = autoriza = None
    if c.precio_pax_noche:
        precio = _d(c.precio_pax_noche, "precio")
        ing = precio * Decimal(c.pax) * Decimal(c.noches)
        zona = cg.semaforo(ing, g.ingreso_minimo)
        autoriza = cg.ZONAS[zona]

    return {
        "mes": el_mes.mes, "temporada": el_mes.temporada,
        "grupo": {"habitaciones": str(g.habitaciones), "noches": str(g.noches),
                  "pax": str(g.pax)},
        "precio_minimo": {
            "recomendado_pax_noche": _piso(g.minimo_pax_noche["con_margen"]),
            "recomendado_pax_estadia": _piso(g.minimo_pax_estadia["con_margen"]),
            "recomendado_total": _piso(g.ingreso_minimo["con_margen"]),
            "limite_pax_noche": _piso(g.minimo_pax_noche["integral"]),
            "limite_pax_estadia": _piso(g.minimo_pax_estadia["integral"]),
            "limite_total": _piso(g.ingreso_minimo["integral"]),
        },
        "zona": zona, "autoriza": autoriza,
        # Por debajo del límite hace falta autorización, y decirlo es parte de
        # la salida: si no, el vendedor cree que el límite es el piso final.
        "bajo_el_limite_requiere": cg.ZONAS["roja"],
    }
