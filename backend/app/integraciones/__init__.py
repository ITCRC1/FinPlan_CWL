# -*- coding: utf-8 -*-
"""Conexiones con sistemas de afuera — el conducto, no el cableado.

**Qué es esto y qué NO es (owner, 2026-08-14: «dejá la prevista para conectarse
a QuickBooks y Opera Cloud vía API»).**

Es la prevista: el lugar donde enchufar, con la forma ya definida —dónde van las
credenciales, cómo se prueba la conexión, qué pasa si falla— para que el día que
existan las credenciales sea configurar y no construir.

**No es una integración andando, y el código no finge que lo sea.** Traer datos
de QuickBooks o de Opera necesita:

  * registrar una app en el portal del proveedor (lo hace el dueño de la cuenta),
  * completar un OAuth que devuelve credenciales de larga vida,
  * y decidir el mapeo — qué cuenta de QuickBooks es qué línea del P&L, qué
    código de habitación de Opera es qué categoría de acá.

Los dos primeros son del owner: son fronteras de seguridad y nadie más las puede
cruzar por él. El tercero es trabajo con el dato en la mano.

**La regla de oro de este módulo:** una conexión sin configurar se ve APAGADA, no
verde. Nada devuelve «ok» sin haber hecho una llamada de verdad que haya
contestado. Un tablero que dice «conectado» cuando no lo está es peor que no
tener tablero — que es justo la clase de error que este proyecto viene matando.
"""
import os
from dataclasses import dataclass, field

from app.i18n import DEFAULT_LOCALE


@dataclass
class Variable:
    """Una credencial o parámetro que hay que cargar en el entorno."""
    nombre: str
    para_que: str
    donde_se_saca: str
    obligatoria: bool = True
    secreta: bool = True

    def valor(self) -> str:
        return (os.environ.get(self.nombre) or "").strip()

    def cargada(self) -> bool:
        return bool(self.valor())


@dataclass
class Integracion:
    """Una conexión posible. Se subclasea para implementar `probar()`."""
    clave: str
    nombre: str
    para_que: str
    variables: list[Variable] = field(default_factory=list)
    documentacion: str = ""

    # ── Estado ────────────────────────────────────────────────────────────
    def faltantes(self) -> list[str]:
        return [v.nombre for v in self.variables if v.obligatoria and not v.cargada()]

    def configurada(self) -> bool:
        return not self.faltantes()

    def estado(self) -> dict:
        """Lo que se muestra sin tocar la red. Nunca dice «conectada»: para eso
        hay que probar, y probar cuesta una llamada."""
        return {
            "clave": self.clave,
            "nombre": self.nombre,
            "para_que": self.para_que,
            "configurada": self.configurada(),
            "faltan": self.faltantes(),
            "variables": [{
                "nombre": v.nombre, "para_que": v.para_que,
                "donde_se_saca": v.donde_se_saca,
                "obligatoria": v.obligatoria, "cargada": v.cargada(),
                # El VALOR nunca sale. Ni truncado: los primeros caracteres de un
                # client_secret ya son media pista.
            } for v in self.variables],
            "documentacion": self.documentacion,
        }

    async def probar(self, idioma: str = DEFAULT_LOCALE) -> dict:
        """Hace UNA llamada real y cuenta qué pasó.

        Contrato: `conecta` solo puede ser True si algo del otro lado contestó
        bien. Sin credenciales es False, con el detalle de qué falta.

        `idioma` llega desde la capa de API —esto no es motor, es un conducto—
        para que el `motivo` se lea en el idioma de quien pidió la prueba. Tiene
        default para que llamarlo a mano desde un script siga funcionando.
        """
        raise NotImplementedError


def _todas() -> list[Integracion]:
    from app.integraciones.quickbooks import QuickBooks
    from app.integraciones.opera_cloud import OperaCloud
    return [QuickBooks(), OperaCloud()]


def registro() -> dict[str, Integracion]:
    return {i.clave: i for i in _todas()}
