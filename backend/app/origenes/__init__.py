# -*- coding: utf-8 -*-
"""De dónde salen los actuales — la capa que iguala orígenes distintos.

**El problema (owner, 2026-08-14).** Oxígen y Ojochal llevan la contabilidad en
QuickBooks. Corcovado va a traer la suya de un backoffice por API. Y hoy todo
entra por Excel. Son tres formas distintas de decir lo mismo.

**La forma de resolverlo:** cada origen es un adaptador cuyo único trabajo es
devolver filas con esta forma. De ahí para abajo el camino es uno solo —
traducir con el mapeo, y aterrizar en `actual_entries`— y ya no importa de dónde
vino.

    QuickBooks  ─┐
    Backoffice  ─┼→  FilaDeOrigen  →  traducir  →  aterrizar  →  el motor
    Archivo     ─┘

**Por qué así y no un conector por hotel.** Con esta capa, sumar una propiedad es
cargar su mapeo (dato) y, si su sistema es nuevo, escribir UN adaptador chico.
Sin ella, cada hotel sería un desarrollo entero — que es exactamente lo que el
owner pidió evitar.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class FilaDeOrigen:
    """Un monto de un mes, tal como lo manda el sistema de afuera.

    Es deliberadamente pobre: cuenta, mes y monto. Cuanto menos entienda esta
    capa del sistema de origen, menos se rompe cuando ese sistema cambia.
    """
    cuenta: str            # el código TAL COMO viene de allá
    mes: int               # 1..12
    monto: Decimal
    nombre: str = ""       # descripción de la cuenta en el origen, si la manda
    dept: str = ""         # departamento/clase del origen; vacío si no lo manda
    outlet: str = ""       # punto de venta, cuando el origen lo distingue

    def __post_init__(self):
        if not 1 <= self.mes <= 12:
            raise ValueError(f"mes fuera de rango: {self.mes}")


class OrigenDeActuales:
    """Lo que tiene que saber hacer un adaptador. Nada más que esto."""

    clave: str = ""
    nombre: str = ""

    async def traer(self, year: int, meses: list[int]) -> list[FilaDeOrigen]:
        """Los movimientos de esos meses, en filas.

        `meses` es explícito y no «todo el año» a propósito: traer de más obliga
        a decidir después qué se pisa, y ahí es donde se borra sin querer un mes
        que estaba bien.
        """
        raise NotImplementedError
