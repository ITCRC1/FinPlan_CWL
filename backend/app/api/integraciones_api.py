# -*- coding: utf-8 -*-
"""Estado de las conexiones con sistemas de afuera.

Dos endpoints y nada mas:

  GET  /api/integraciones/                  que hay, que falta cargar
  POST /api/integraciones/{clave}/probar/   hace UNA llamada real y cuenta

Son de ADMIN: la lista dice que credenciales existen y cuales faltan, y eso ya
es informacion util para alguien de afuera. Los VALORES no salen nunca, ni
truncados — los primeros caracteres de un client_secret ya son media pista.
"""
from fastapi import APIRouter, Depends

from app.errores import ErrorApi
from app.textos import Idioma, t
from app.auth import get_current_admin
from app.integraciones import registro

router = APIRouter()


@router.get("/integraciones/")
async def listar(_=Depends(get_current_admin), idioma: str = Idioma):
    """Que se puede conectar y que falta para conectarlo.

    `configurada` NO quiere decir «funciona»: quiere decir que las variables
    estan cargadas. Para saber si funciona hay que probar, y probar cuesta una
    llamada — por eso es otro endpoint y no pasa solo.
    """
    return {
        "integraciones": [i.estado() for i in registro().values()],
        "nota": t(idioma, "integracion.configurada_no_es_conectada"),
    }


@router.post("/integraciones/{clave}/probar/")
async def probar(clave: str, _=Depends(get_current_admin),
                 idioma: str = Idioma):
    """Hace una llamada de verdad al sistema de afuera y devuelve que paso.

    `conecta: true` solo aparece si algo del otro lado contesto bien. Sin
    credenciales es false con la lista de lo que falta — nunca un verde vacio.
    """
    inte = registro().get(clave)
    if inte is None:
        raise ErrorApi(404, "integracion.no_existe", integracion=clave,
                       disponibles=", ".join(registro()))
    resultado = await inte.probar(idioma)
    return {"clave": clave, "nombre": inte.nombre, **resultado}
