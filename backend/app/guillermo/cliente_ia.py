# -*- coding: utf-8 -*-
"""La llamada real al modelo — pendiente 18 (`docs/GUILLERMO.md` §8 y §9).

La frontera ya estaba construida y probada en `ia.py`: el payload mínimo, la
lista de campos permitidos, la redacción de PII, el system prompt y el
envoltorio de dato no confiable. Lo que faltaba era el cliente.

⚠️ **NO ESTÁ VERIFICADO CONTRA LA API DE VERDAD.** El owner decidió el
2026-08-20 que la llave se pone **al clonar** —«cada propiedad decide cómo
manejar a Guillermo»—, así que este módulo se escribió sin poder llamar una vez.
Las pruebas cubren lo que se puede probar sin red: que el payload sucio NO
salga, que una propuesta no se aplique sola y que un fallo no tumbe la ronda.
**La primera llamada real hay que mirarla.**

⚠️ **El guardia corre ANTES de cada llamada, y bloquea.** `payload_limpio` ya
existía; sin alguien que lo consulte era una regla que nadie verifica, o sea
ninguna protección. Acá se consulta, y si no pasa **no se llama al modelo**: se
devuelve el motivo.

⚠️ **Los números nunca los produce el modelo** (§9.1). Por eso la herramienta
que se le fuerza devuelve un CÓDIGO DE CUENTA y una explicación — ni un monto.

⚠️ **Una propuesta no se aplica sola, en ningún nivel** (§4). Este módulo no
importa una sola tabla del modelo financiero: no tiene con qué escribir.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.guillermo import ia

# El techo de una clasificación: es una cuenta y una línea de explicación.
MAX_TOKENS = 512

# ⚠️ Forzada. Sin `tool_choice` el modelo puede contestar en prosa y habría que
# parsear texto libre — que es exactamente donde se cuela un número inventado.
HERRAMIENTA = {
    "name": "proponer_cuenta",
    "description": (
        "Devolvé la cuenta contable que corresponde al concepto, elegida "
        "SÓLO de la lista de candidatas. Si ninguna corresponde, devolvé "
        "cuenta vacía y explicá por qué."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cuenta": {
                "type": "string",
                "description": "Código de una cuenta de la lista, o vacío",
            },
            "confianza": {
                "type": "number",
                "description": "0 a 1. Cuán seguro estás de la elección",
            },
            "explicacion": {
                "type": "string",
                "description": "Una línea. Por qué esa cuenta y no otra",
            },
        },
        "required": ["cuenta", "confianza", "explicacion"],
        "additionalProperties": False,
    },
    # Garantiza que el input valide exactamente contra el esquema.
    "strict": True,
}


@dataclass(frozen=True)
class Propuesta:
    """Lo que vuelve del modelo. **Va a la cola y ahí se detiene.**"""
    cuenta: str
    confianza: float
    explicacion: str
    modelo: str
    # Lo que se mandó, tal cual, para la auditoría del apéndice 4.
    payload: dict


def _cliente():
    """El cliente del SDK oficial. Se construye por llamada a propósito: la
    llave puede aparecer en el entorno después de que el proceso arrancó."""
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "").strip())


async def proponer_cuenta(concepto: str, normalizado: str,
                          candidatas: list[dict]) -> tuple[Propuesta | None, str]:
    """Le pide al modelo una cuenta para un concepto que no matcheó ninguna regla.

    Devuelve `(propuesta, motivo)`. **Nunca levanta**: un fallo del modelo no
    puede tumbar la ronda — el concepto se queda sin propuesta y la excepción
    igual va a la cola, que es donde tenía que ir de todos modos.
    """
    con = ia.estado()
    if not con.conectado:
        return None, con.motivo

    payload = ia.payload_de_propuesta(concepto, normalizado, candidatas)

    # ⚠️ El guardia. Si el payload no tiene exactamente la forma permitida, no
    # se llama: una regla que nadie verifica no protege de nada.
    limpio, motivos = ia.payload_limpio(payload)
    if not limpio:
        return None, f"el payload no salió: {'; '.join(motivos)}"

    if not payload["cuentas_candidatas"]:
        # Sin candidatas el modelo no puede elegir de una lista, y elegir fuera
        # de la lista es justo lo que el system prompt prohíbe.
        return None, "no hay cuentas candidatas para elegir"

    datos = ia.envoltorio(
        f"concepto: {payload['concepto']}\n"
        f"normalizado: {payload['concepto_normalizado']}\n"
        "cuentas candidatas:\n" + "\n".join(
            f"- {c['codigo']}: {c['nombre']}"
            for c in payload["cuentas_candidatas"]))

    try:
        r = await _cliente().messages.create(
            model=ia.MODELO_CHICO,
            max_tokens=MAX_TOKENS,
            system=ia.SYSTEM_PROMPT,
            tools=[HERRAMIENTA],
            tool_choice={"type": "tool", "name": HERRAMIENTA["name"]},
            messages=[{"role": "user", "content": datos}],
        )
    except Exception as e:                          # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"[:300]

    # ⚠️ Se busca el bloque `tool_use`; no se asume que sea el primero ni que
    # exista. Un `stop_reason` de rechazo o de tope de tokens deja la respuesta
    # sin herramienta, y ahí `content[0].input` reventaría.
    bloque = next((b for b in r.content if getattr(b, "type", "") == "tool_use"),
                  None)
    if bloque is None:
        return None, f"el modelo no usó la herramienta (stop_reason={r.stop_reason})"

    datos_out = bloque.input or {}
    cuenta = str(datos_out.get("cuenta", "")).strip()

    # ⚠️ **La cuenta tiene que estar en la lista que se mandó.** El system
    # prompt lo pide, pero pedirlo no es garantizarlo: un código inventado que
    # se guardara en la cola parecería una propuesta legítima, y alguien la
    # aprobaría. Se verifica en código, que es donde se puede.
    validas = {c["codigo"] for c in payload["cuentas_candidatas"]}
    if cuenta and cuenta not in validas:
        return None, (f"el modelo propuso «{cuenta}», que no estaba entre las "
                      f"candidatas: se descarta")

    try:
        confianza = max(0.0, min(1.0, float(datos_out.get("confianza", 0))))
    except (TypeError, ValueError):
        confianza = 0.0

    return Propuesta(
        cuenta=cuenta,
        confianza=confianza,
        explicacion=str(datos_out.get("explicacion", ""))[:400],
        modelo=ia.MODELO_CHICO,
        payload=payload,
    ), "ok"
