# -*- coding: utf-8 -*-
"""QuickBooks Online — prevista.

**Para qué serviría.** Traer el mayor (GL) del mes cerrado en vez de subirlo por
Excel. Hoy el owner baja el detalle, lo revisa y lo sube; el importador ya existe
y funciona. Esto le quitaría el paso manual, no cambiaría el cálculo.

**Cómo se autentica.** OAuth 2.0 con *refresh token*: se da el permiso UNA vez
desde el navegador, con la cuenta de QuickBooks, y queda un refresh token de
larga vida. Con él se pide un access token de una hora cada vez que hace falta.

⚠️ **Ese permiso lo da el dueño de la cuenta.** Es una frontera de seguridad:
nadie más puede completarlo, y no hay forma de saltárselo desde acá.

**Lo que falta después de las credenciales, y no es poco:** decidir qué cuenta de
QuickBooks corresponde a qué línea del P&L USALI. El sistema ya tiene esa capa
(`account_mapping`), así que es trabajo de mapeo con el catálogo real a la vista;
no se puede adivinar de antemano.
"""
from app.i18n import DEFAULT_LOCALE
from app.integraciones import Integracion, Variable
from app.textos import t

# El endpoint de tokens de Intuit es igual para todos y no cambia por cliente.
TOKENS = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


class QuickBooks(Integracion):
    def __init__(self):
        super().__init__(
            clave="quickbooks",
            nombre="QuickBooks Online",
            para_que="Traer el detalle del mayor (GL) sin subir el Excel a mano.",
            documentacion="docs/INTEGRACIONES.md#quickbooks-online",
            variables=[
                Variable("QBO_CLIENT_ID",
                         "Identifica la app ante Intuit.",
                         "developer.intuit.com, tu app, Keys and credentials.",
                         secreta=False),
                Variable("QBO_CLIENT_SECRET",
                         "La contrasena de esa app.",
                         "Mismo lugar que el CLIENT_ID. No se comparte por chat ni correo."),
                Variable("QBO_REFRESH_TOKEN",
                         "Permiso de larga vida sobre la empresa. Se renueva al usarse.",
                         "Sale del OAuth que autoriza el dueno de la cuenta, una sola vez."),
                Variable("QBO_REALM_ID",
                         "Cual empresa de QuickBooks. Cada propiedad tiene la suya.",
                         "Aparece en la URL al entrar a la empresa, o al terminar el OAuth.",
                         secreta=False),
                Variable("QBO_ENTORNO",
                         "sandbox para probar, produccion para el dato real.",
                         "Lo elegis vos. Sin la variable se asume sandbox, que no toca dato real.",
                         obligatoria=False, secreta=False),
            ],
        )

    def _base_api(self) -> str:
        entorno = (self.variables[-1].valor() or "sandbox").lower()
        if entorno.startswith("prod"):
            return "https://quickbooks.api.intuit.com"
        return "https://sandbox-quickbooks.api.intuit.com"

    async def probar(self, idioma: str = DEFAULT_LOCALE) -> dict:
        """Pide un access token y lee los datos de la empresa.

        Se eligio `companyinfo` a proposito: es la lectura mas inofensiva que
        existe —el nombre de la empresa— y alcanza para saber si la credencial
        sirve. Probar con algo que traiga plata seria innecesario.
        """
        faltan = self.faltantes()
        if faltan:
            return {"conecta": False,
                    "motivo": t(idioma, "integracion.sin_configurar"),
                    "faltan": faltan}

        import base64
        import httpx

        cid = self.variables[0].valor()
        secreto = self.variables[1].valor()
        refresh = self.variables[2].valor()
        realm = self.variables[3].valor()
        basico = base64.b64encode(f"{cid}:{secreto}".encode()).decode()

        try:
            async with httpx.AsyncClient(timeout=25) as cli:
                r = await cli.post(
                    TOKENS,
                    headers={"Authorization": f"Basic {basico}",
                             "Content-Type": "application/x-www-form-urlencoded",
                             "Accept": "application/json"},
                    data={"grant_type": "refresh_token", "refresh_token": refresh},
                )
                if r.status_code != 200:
                    return {"conecta": False,
                            "motivo": t(idioma, "integracion.qbo_refresh_rechazado"),
                            "detalle": t(idioma, "integracion.qbo_http_al_pedir_token",
                                         http=r.status_code),
                            "que_hacer": t(idioma, "integracion.qbo_rehacer_oauth")}
                token = r.json().get("access_token")
                if not token:
                    return {"conecta": False,
                            "motivo": t(idioma, "integracion.qbo_sin_access_token")}

                r2 = await cli.get(
                    f"{self._base_api()}/v3/company/{realm}/companyinfo/{realm}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
            if r2.status_code != 200:
                return {"conecta": False,
                        "motivo": t(idioma, "integracion.qbo_empresa_no_responde"),
                        "detalle": f"HTTP {r2.status_code}",
                        "que_hacer": t(idioma, "integracion.qbo_revisar_realm")}
            datos = r2.json().get("CompanyInfo", {})
            return {"conecta": True,
                    "empresa": datos.get("CompanyName", ""),
                    "entorno": "sandbox" if "sandbox" in self._base_api() else "produccion"}
        except Exception as e:  # noqa: BLE001 — todo fallo se informa, no se traga
            return {"conecta": False,
                    "motivo": t(idioma, "integracion.qbo_sin_contacto"),
                    "detalle": type(e).__name__}
