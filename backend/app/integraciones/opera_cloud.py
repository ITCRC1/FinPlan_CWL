# -*- coding: utf-8 -*-
"""Oracle Opera Cloud (OHIP) — prevista.

**Para que serviria.** Traer las estadisticas de habitaciones —noches vendidas,
pax, revenue por categoria— y el On The Books, sin exportar el XML a mano. Hoy
eso entra por archivo y el importador ya existe.

**Como se autentica.** OHIP —Oracle Hospitality Integration Platform— usa OAuth
con una `x-app-key` propia de la integracion. **El host NO es el mismo para
todos:** depende del entorno que Oracle le asigna a cada cadena, asi que va en
variable y no escrito aca. Poner un host inventado seria peor que no tener nada.

⚠️ **Esto arranca con Oracle, no con codigo.** Hay que dar de alta la integracion
en OHIP y que habiliten los servicios a consumir para el `hotelId` de la
propiedad. Ese tramite lo hace el dueno de la cuenta.

**Y algo que conviene saber antes de empezar:** las categorias de habitacion de
Opera hay que emparejarlas con las de aca. Este sistema ya resolvio esa mitad
—cada categoria tiene un codigo fijo, BL01 a SH08, que no cambia entre
propiedades— asi que el emparejamiento es una tabla de equivalencias y se hace
una sola vez.
"""
from app.i18n import DEFAULT_LOCALE
from app.integraciones import Integracion, Variable
from app.textos import t


class OperaCloud(Integracion):
    def __init__(self):
        super().__init__(
            clave="opera_cloud",
            nombre="Oracle Opera Cloud (OHIP)",
            para_que="Traer noches, pax y revenue por categoria, y el On The Books.",
            documentacion="docs/INTEGRACIONES.md#oracle-opera-cloud-ohip",
            variables=[
                Variable("OPERA_BASE_URL",
                         "El host de OHIP de ESTA cadena. No es igual para todos.",
                         "Lo da Oracle al habilitar la integracion.",
                         secreta=False),
                Variable("OPERA_APP_KEY",
                         "Identifica la integracion ante OHIP (cabecera x-app-key).",
                         "Portal de OHIP, en tu aplicacion."),
                Variable("OPERA_CLIENT_ID",
                         "Cliente OAuth.",
                         "Portal de OHIP, junto con la app key.", secreta=False),
                Variable("OPERA_CLIENT_SECRET",
                         "La contrasena de ese cliente.",
                         "Portal de OHIP. No se comparte por chat ni correo."),
                Variable("OPERA_USUARIO",
                         "Usuario de Opera con permiso de LECTURA sobre la propiedad.",
                         "Lo crea el administrador de Opera. Que sea solo lectura, no admin.",
                         secreta=False),
                Variable("OPERA_PASSWORD",
                         "Contrasena de ese usuario.",
                         "La define el administrador de Opera."),
                Variable("OPERA_HOTEL_ID",
                         "Codigo de la propiedad dentro de Opera. Uno por hotel.",
                         "Es el codigo con el que Opera identifica la propiedad.",
                         secreta=False),
            ],
        )

    async def probar(self, idioma: str = DEFAULT_LOCALE) -> dict:
        """Pide un token a OHIP. Nada mas: si el token sale, la puerta abre.

        No se consulta ninguna reserva ni dato de huesped — para saber si la
        credencial sirve alcanza con el token, y pedir menos siempre es mejor.
        """
        faltan = self.faltantes()
        if faltan:
            return {"conecta": False,
                    "motivo": t(idioma, "integracion.sin_configurar"),
                    "faltan": faltan}

        import httpx

        base = self.variables[0].valor().rstrip("/")
        app_key = self.variables[1].valor()
        cid = self.variables[2].valor()
        secreto = self.variables[3].valor()
        usuario = self.variables[4].valor()
        password = self.variables[5].valor()

        try:
            async with httpx.AsyncClient(timeout=25) as cli:
                r = await cli.post(
                    f"{base}/oauth/v1/tokens",
                    headers={"x-app-key": app_key,
                             "Content-Type": "application/x-www-form-urlencoded"},
                    data={"grant_type": "password", "username": usuario, "password": password},
                    auth=(cid, secreto),
                )
            if r.status_code != 200:
                return {"conecta": False,
                        "motivo": t(idioma, "integracion.ohip_sin_token"),
                        "detalle": f"HTTP {r.status_code}",
                        "que_hacer": t(idioma, "integracion.ohip_revisar_base_url")}
            if not r.json().get("access_token"):
                return {"conecta": False,
                        "motivo": t(idioma, "integracion.ohip_sin_access_token")}
            return {"conecta": True, "hotel_id_opera": self.variables[6].valor()}
        except Exception as e:  # noqa: BLE001
            return {"conecta": False,
                    "motivo": t(idioma, "integracion.ohip_sin_contacto"),
                    "detalle": type(e).__name__,
                    "que_hacer": t(idioma, "integracion.ohip_revisar_host")}
