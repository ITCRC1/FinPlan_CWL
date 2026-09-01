# -*- coding: utf-8 -*-
"""La forma de un hallazgo.

Es la misma que ya usa **Admin → Chequeo** (`api/chequeo_api._r`): clave,
título, estado, detalle, por qué y qué hacer. Se reusa a propósito — el owner ya
sabe leer esa pantalla, y una segunda forma para decir lo mismo obliga a
aprender dos.

Se le agrega **el monto**. Sin él no hay forma de saber si un hallazgo es ruido o
si falta media operación.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

#: `critico` = hay plata que no llega a ningún lado · `aviso` = mirar antes de
#: cerrar · `info` = quedó registrado, probablemente esté bien.
#:
#: ⚠️ Ninguna de las tres rechaza la carga. Bloquear es potestad de los cuatro
#: controles de `importers/verificacion.py`, y de nadie más.
GRAVEDADES = ("critico", "aviso", "info")

ZERO = Decimal("0")


@dataclass
class Hallazgo:
    #: Estable y en snake_case. Es por lo que la cola de excepciones reconoce que
    #: un hallazgo YA está abierto y no lo duplica en la siguiente vuelta.
    clave: str
    titulo: str
    gravedad: str
    detalle: str
    #: Por qué importa. No es adorno: un hallazgo sin explicación no se puede
    #: discutir, y el que lo lee termina aprobándolo por cansancio.
    porque: str
    que_hacer: str
    monto: Decimal = ZERO
    nivel: int = 0
    #: Dónde mirar: fila del Excel de origen, cuenta, departamento.
    referencias: list[dict] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"clave": self.clave, "titulo": self.titulo,
                "gravedad": self.gravedad, "detalle": self.detalle,
                "porque": self.porque, "que_hacer": self.que_hacer,
                "monto": float(self.monto), "nivel": self.nivel,
                "referencias": self.referencias[:50]}


def hallazgo(clave: str, titulo: str, gravedad: str, detalle: str,
             porque: str = "", que_hacer: str = "", monto=ZERO,
             nivel: int = 0, referencias=None) -> Hallazgo:
    if gravedad not in GRAVEDADES:
        raise ValueError(f"gravedad desconocida: {gravedad!r}")
    return Hallazgo(clave=clave, titulo=titulo, gravedad=gravedad,
                    detalle=detalle, porque=porque, que_hacer=que_hacer,
                    monto=Decimal(str(monto or 0)), nivel=nivel,
                    referencias=list(referencias or []))
