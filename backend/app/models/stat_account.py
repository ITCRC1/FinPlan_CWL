# -*- coding: utf-8 -*-
"""Catálogo de cuentas estadísticas (clase 9).

**Por qué existe una tabla y no un diccionario de Python.** Hasta hoy «cuenta
clase 9» eran tres códigos escritos a mano en `gl_detail_importer.STAT_BY_ACCT`.
Cualquier otra cuenta 9xxx que llegara en un archivo se descartaba en silencio
absoluto: no entraba a `unmapped`, no entraba a `sin_cuenta`, no salía en la
vista previa. El espejo exacto del bug de los $40,613 — allá la fila no traía
cuenta y hoy truena; acá la fila traía cuenta y aun así se perdía.

**Por qué no sale de la tabla `accounts`.** `CLAUDE.md` §18 dice que el catálogo
contable trae 9,292 cuentas 9xxx. En producción esa tabla tiene **cero filas**
(verificado 2026-08-14): el archivo del catálogo nunca se importó. Colgar la
estadística de ahí la dejaría sin llave el día uno.

Así que la lista de verdad vive en `seed_data/stats_catalog.json` y se siembra
en cada arranque, igual que el mapeo del P&L. Los códigos respetan los rangos
que ya documenta `CLAUDE.md` §18.1.
"""
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Las dimensiones que una estadística puede llevar. Cada cuenta declara cuáles
# acepta; la carga rechaza el resto. Una cuenta de kilos con un código de canal
# adentro es un error de digitación, no un dato.
# ⚠️ `OUTLET` no está: el punto de venta YA ES un departamento en este sistema
# (0121 Private Bar, 0122 Cocina, 0123 Restaurante), así que abrir los covers por
# departamento ya da el corte por outlet. Una dimensión extra para lo mismo
# obliga a decidir dos veces dónde va cada cover, y el día que discrepen nadie
# sabría cuál manda.
DIMENSIONES = ("DEPT", "POSITION", "ROOMTYPE", "CHANNEL", "COUNTRY", "SEGMENT")


class StatAccount(Base):
    __tablename__ = "stat_accounts"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)   # '9010'
    grupo: Mapped[str] = mapped_column(String(10), index=True)        # '9000', '9700'…
    nombre_es: Mapped[str] = mapped_column(String(200))
    nombre_en: Mapped[str] = mapped_column(String(200), default="")
    unidad: Mapped[str] = mapped_column(String(16))                   # nights, kilos, hours…

    # CSV de `DIMENSIONES`. Vacío = la cuenta es un total del hotel y no se abre
    # por nada.
    dims: Mapped[str] = mapped_column(String(120), default="")

    # SUM = el año es la suma de los doce meses.
    # FIN = el año es el saldo de diciembre. Es el caso de los conteos de padrón
    #       —headcount, socios—: sumar doce meses de 129 socios da 1,548 socios
    #       donde hay 129. Mismo criterio que `ClubMembershipStat`.
    agrega: Mapped[str] = mapped_column(String(4), default="SUM")

    # ⚠️ `dinero=True` NO es una cantidad: es plata que el P&L ya reporta,
    # partida de otra forma. Una venta de habitaciones abierta por canal es la
    # MISMA plata de `REV_ROOMS`. Si se carga suelta, el día que los canales no
    # sumen igual hay dos verdades sobre el mismo dinero y ninguna avisa.
    # Por eso lleva `amarra_con`: la carga exige que cuadre contra esa línea.
    dinero: Mapped[bool] = mapped_column(Boolean, default=False)
    amarra_con: Mapped[str] = mapped_column(String(40), default="")

    # Campo de `scenario_stats` que esta cuenta ya alimentaba antes de que
    # existiera esta tabla. Se sigue escribiendo ahí además de acá, para no mover
    # nada de lo que ya se reporta.
    legado: Mapped[str] = mapped_column(String(40), default="")

    # En qué departamentos vive esta cuenta (CSV). Vacío = todos. Sin esto, una
    # cuenta con dimensión DEPT pide fila para los 38 departamentos y el archivo
    # se llena de combinaciones imposibles: covers de Mantenimiento.
    deptos: Mapped[str] = mapped_column(String(200), default="")

    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    def deptos_propios(self) -> list[str]:
        return [d for d in (self.deptos or "").split(",") if d]

    def dims_permitidas(self) -> set[str]:
        return {d for d in (self.dims or "").split(",") if d}

    def __repr__(self) -> str:
        return f"<StatAccount {self.code} {self.nombre_es[:30]} [{self.unidad}]>"
