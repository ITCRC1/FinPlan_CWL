# -*- coding: utf-8 -*-
"""Nivel 3 · los reportes de Opera tienen que decir lo mismo entre sí.

Pendiente 22, destrabado por el owner el 2026-08-20: *«todos serán XML de
Opera»*. El §5 del spec de Guillermo llama a esto *«lo que distingue "los
archivos están" de "los datos sirven"»*.

**El criterio.** Country Mix, Channel Mix y On the Books salen del MISMO XML de
Opera, así que las noches de un mes tienen que dar lo mismo en los tres. Si el
país dice 3.403 noches y el canal dice 3.180, uno de los dos está mal — y hasta
hoy nadie lo miraba.

⚠️ **Sólo se comparan las filas que vinieron del XML** (`origen='xml'`). Un mix
planificado a mano no es un reporte de Opera: contra el On the Books sería
**plan contra realidad**, que es otra conversación. Marcarlo como descuadre
llenaría la cola de diferencias que no son errores, y una cola así se aprende a
ignorar.

⚠️ **Contra el OTB, sólo los meses CERRADOS.** El On the Books son reservas:
para un mes futuro es parcial por definición, así que va a dar menos que el
forecast **siempre**. Compararlos daría un descuadre garantizado todos los
meses y no significaría nada.

⚠️ **Falta un lado ≠ descuadre.** Si el Channel Mix de junio no se subió, el
veredicto es «no se puede verificar», no «no cuadra». Es la misma regla de tres
estados que ya usa `cuadre.py`: pintar de verde lo que nadie comparó es el peor
resultado posible.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel_mix import ChannelMixDetail, ChannelMixEntry
from app.models.country_mix import CountryMixEntry
from app.models.otb_daily_occ import OtbDailyOcc
from app.models.scenario import Scenario

ZERO = Decimal("0")

#: Media noche. Las noches se guardan con dos decimales porque una estadía
#: puede repartirse, pero una diferencia menor a media noche es redondeo del
#: XML, no un desacuerdo entre reportes.
TOLERANCIA = Decimal("0.5")

#: Los tres estados. Los mismos que `cuadre.py`, a propósito: dos pantallas que
#: dicen «no cuadra» con criterios distintos son dos pantallas que se
#: contradicen.
CUADRA = "cuadra"
NO_CUADRA = "no_cuadra"
SIN_VERIFICAR = "sin_verificar"


@dataclass
class Par:
    """Dos reportes de Opera comparados en un mes."""
    mes: int
    izquierda: str
    derecha: str
    valor_izq: Decimal | None
    valor_der: Decimal | None
    estado: str
    motivo: str

    @property
    def diferencia(self) -> Decimal:
        if self.valor_izq is None or self.valor_der is None:
            return ZERO
        return self.valor_izq - self.valor_der


def _comparar(mes: int, izq_nombre: str, izq: Decimal | None,
              der_nombre: str, der: Decimal | None,
              motivo_falta: str = "") -> Par:
    """El veredicto de un par. **Tres estados, nunca dos.**"""
    if izq is None or der is None:
        falta = izq_nombre if izq is None else der_nombre
        return Par(mes, izq_nombre, der_nombre, izq, der, SIN_VERIFICAR,
                   motivo_falta or f"no hay dato de {falta} en este mes")
    dif = izq - der
    if abs(dif) <= TOLERANCIA:
        return Par(mes, izq_nombre, der_nombre, izq, der, CUADRA, "")
    return Par(mes, izq_nombre, der_nombre, izq, der, NO_CUADRA,
               f"{izq_nombre} dice {izq:,.2f} y {der_nombre} dice {der:,.2f}: "
               f"difieren en {abs(dif):,.2f} noches")


async def _por_mes(db: AsyncSession, modelo, scenario_id: str,
                   solo_xml: bool) -> dict[int, Decimal]:
    """Noches por mes de un mix. `None` para un mes sin filas — no cero."""
    q = (select(modelo.month, func.sum(modelo.value))
         .where(modelo.scenario_id == scenario_id, modelo.metric == "rooms"))
    if solo_xml:
        q = q.where(modelo.origen == "xml")
    filas = (await db.execute(q.group_by(modelo.month))).all()
    return {int(m): Decimal(str(v or 0)) for m, v in filas}


async def _detalle_por_mes(db: AsyncSession, scenario_id: str) -> dict[int, Decimal]:
    filas = (await db.execute(
        select(ChannelMixDetail.month, func.sum(ChannelMixDetail.value))
        .where(ChannelMixDetail.scenario_id == scenario_id,
               ChannelMixDetail.metric == "rooms")
        .group_by(ChannelMixDetail.month)
    )).all()
    return {int(m): Decimal(str(v or 0)) for m, v in filas}


async def _otb_por_mes(db: AsyncSession, hotel_id: str,
                       anio: int) -> dict[int, Decimal]:
    """⚠️ El OTB se llavea por **hotel y año**, no por escenario: se sube una
    vez y se ve desde cualquier escenario (mig 126). Por eso hay que pedirle el
    año del escenario y no el `scenario_id`."""
    filas = (await db.execute(
        select(OtbDailyOcc.month, func.sum(OtbDailyOcc.rooms_sold))
        .where(OtbDailyOcc.hotel_id == hotel_id, OtbDailyOcc.year == anio)
        .group_by(OtbDailyOcc.month)
    )).all()
    return {int(m): Decimal(str(v or 0)) for m, v in filas}


async def cuadre_de_opera(db: AsyncSession, sc: Scenario,
                          hotel_id: str) -> list[Par]:
    """Los pares comparables del escenario, mes por mes."""
    pais = await _por_mes(db, CountryMixEntry, sc.id, solo_xml=True)
    canal = await _por_mes(db, ChannelMixEntry, sc.id, solo_xml=True)
    canal_detalle = await _detalle_por_mes(db, sc.id)
    otb = await _otb_por_mes(db, hotel_id, sc.year)
    corte = int(sc.actuals_through or 0)

    fuera: list[Par] = []
    for mes in range(1, 13):
        p, c, d, o = (pais.get(mes), canal.get(mes),
                      canal_detalle.get(mes), otb.get(mes))

        # 1. País contra canal: el mismo XML, agrupado de dos maneras.
        fuera.append(_comparar(mes, "Country Mix", p, "Channel Mix", c))

        # 2. El resumen del canal contra su propio detalle por market code.
        #    ⚠️ El modelo dice que el resumen se deriva del detalle y «no puede
        #    discrepar». Se verifica igual: una invariante que nadie comprueba
        #    deja de serlo el día que alguien escribe el resumen por otro lado.
        fuera.append(_comparar(mes, "Channel Mix (resumen)", c,
                               "Channel Mix (detalle)", d))

        # 3. Contra el On the Books, SÓLO si el mes está cerrado.
        if mes <= corte:
            fuera.append(_comparar(mes, "Country Mix", p, "On the Books", o))
        else:
            fuera.append(Par(
                mes, "Country Mix", "On the Books", p, o, SIN_VERIFICAR,
                f"el mes {mes} no está cerrado (corte del escenario: {corte}): "
                f"el On the Books son reservas y todavía es parcial"))
    return fuera


@dataclass
class ResumenOpera:
    escenario: str
    pares: list[Par]

    @property
    def descuadres(self) -> list[Par]:
        return [p for p in self.pares if p.estado == NO_CUADRA]

    @property
    def verificados(self) -> int:
        return sum(1 for p in self.pares if p.estado != SIN_VERIFICAR)

    @property
    def estado(self) -> str:
        if self.descuadres:
            return NO_CUADRA
        # ⚠️ Cero comparaciones **no es «cuadra»**. Sin dato, el veredicto es
        # que no se pudo verificar — pintarlo verde diría que los reportes
        # coinciden cuando nadie comparó nada.
        return CUADRA if self.verificados else SIN_VERIFICAR


async def resumen_opera(db: AsyncSession, sc: Scenario,
                        hotel_id: str) -> ResumenOpera:
    return ResumenOpera(
        escenario=f"{sc.type}/{sc.year}/{sc.version}",
        pares=await cuadre_de_opera(db, sc, hotel_id))
