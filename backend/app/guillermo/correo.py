# -*- coding: utf-8 -*-
"""Los avisos por correo — pendiente 20 (`docs/GUILLERMO.md` §12.2 y apéndice 5).

Sin esto, el dead-man switch **sólo grita adentro de una pantalla**: si nadie
abre FinPlan, un Guillermo trabado se ve igual que uno al día. El correo es lo
que hace que el silencio signifique «todo bien» para una persona que no está
mirando.

⚠️ **Las credenciales viven en el ENTORNO, nunca en el repo ni en la base**
(§9.4, igual que la llave del modelo). Los destinatarios sí van en la base,
porque son una decisión del owner de cada propiedad (D-5) y se editan en la
pantalla.

⚠️ **Sin configurar no manda nada, y lo DICE.** Un correo que no sale porque
falta una variable es indistinguible de un correo que no salía porque no había
nada que avisar. `estado()` contesta cuál de los dos es, y la pantalla lo
muestra al lado de la conexión con Claude.

⚠️ **No manda lo mismo dos veces.** Un aviso que llega todos los días se
aprende a saltear, y con él se saltea el que sí era distinto — el mismo
razonamiento que la ronda usa para no duplicar notas en la cola.

⚠️ **Nada de esto se aplica solo.** El correo informa; no importa, no
recalcula y no aprueba. Es la cara del §10, no la autoridad.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

# La clave donde el owner de cada propiedad declara a quién avisarle (D-5).
CLAVE_DESTINATARIOS = "notify_emails"

# ── Lo que vive en el entorno ────────────────────────────────────────────────
VARIABLES = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")


@dataclass(frozen=True)
class Conexion:
    configurado: bool
    servidor: str
    remitente: str
    destinatarios: tuple[str, ...]
    motivo: str


def destinatarios_de(valor: str | None) -> tuple[str, ...]:
    """`a@x.com, b@y.com` → tupla. Sin duplicados y sin vacíos.

    ⚠️ No valida la forma del correo a propósito: rechazar acá una dirección
    rara dejaría al owner sin poder avisarle a un alias interno, y el error de
    verdad lo devuelve el servidor SMTP con su motivo.
    """
    vistos: list[str] = []
    for parte in (valor or "").replace(";", ",").split(","):
        d = parte.strip()
        if d and d not in vistos:
            vistos.append(d)
    return tuple(vistos)


def estado(destinatarios_crudos: str | None = None) -> Conexion:
    """¿Puede mandar? ⚠️ **Nunca devuelve la contraseña ni un pedazo.**"""
    host = os.getenv("SMTP_HOST", "").strip()
    remitente = os.getenv("SMTP_FROM", "").strip() or os.getenv("SMTP_USER", "").strip()
    quienes = destinatarios_de(destinatarios_crudos)

    faltan = [v for v in VARIABLES if v not in ("SMTP_FROM",) and not os.getenv(v, "").strip()]
    if faltan:
        return Conexion(False, host, remitente, quienes,
                        f"faltan variables en el entorno del backend: "
                        f"{', '.join(faltan)}")
    if not quienes:
        return Conexion(False, host, remitente, quienes,
                        f"no hay a quién avisarle: cargá «{CLAVE_DESTINATARIOS}» "
                        f"en Admin → Guillermo (es la decisión D-5, y es de "
                        f"cada propiedad)")
    return Conexion(True, host, remitente, quienes,
                    f"listo para avisarle a {len(quienes)}")


# ── Qué dice cada aviso ──────────────────────────────────────────────────────
#
# ⚠️ **Los errores son específicos y técnicos, nunca en voz de gato** (§10). Un
# aviso que dice «¡ups, algo pasó!» obliga a entrar a la app para saber qué —
# o sea, no avisó nada.

def aviso_de_latido(hotel: str, motivo: str, max_horas: int) -> tuple[str, str]:
    """El correo rojo del dead-man switch."""
    return (
        f"[{hotel}] Guillermo no está corriendo",
        f"{motivo}.\n\n"
        f"El máximo configurado es de {max_horas} horas sin latido. Mientras "
        f"esto siga así, NADIE está verificando que los reportes lleguen ni "
        f"que los auxiliares cuadren contra el GL: el silencio de Guillermo "
        f"dejó de significar «todo bien».\n\n"
        f"Dónde mirar: el servicio de cron en Railway "
        f"(finplan-cwl-guillermo) y sus logs.\n")


def aviso_de_hallazgos(hotel: str, nuevas: int, cerradas: int,
                       abiertas: int, detalle: str) -> tuple[str, str]:
    """El correo de la ronda. **Sólo se manda si hay algo nuevo.**"""
    return (
        f"[{hotel}] {nuevas} hallazgo{'s' if nuevas != 1 else ''} nuevo"
        f"{'s' if nuevas != 1 else ''} de Guillermo",
        f"{detalle}\n\n"
        f"Nuevos: {nuevas} · Se resolvieron solos: {cerradas} · "
        f"Abiertos en total: {abiertas}\n\n"
        f"La lista completa está en Admin → Guillermo. Nada de esto se aplicó "
        f"solo: son notas para que alguien decida.\n")


def resumen_semanal(hotel: str, abiertas: int, corridas: int,
                    lineas: list[str]) -> tuple[str, str]:
    """El resumen de la semana (§12.2).

    ⚠️ Va **aunque no haya nada**: éste es el único aviso cuya ausencia
    significaría algo, y por eso es el que confirma que el canal funciona.
    """
    cuerpo = (f"Guillermo corrió {corridas} vez{'ces' if corridas != 1 else ''} "
              f"esta semana.\n\n")
    cuerpo += ("\n".join(f"· {l}" for l in lineas) if lineas
               else "No quedó ningún hallazgo abierto.\n")
    cuerpo += f"\n\nAbiertos al cierre de la semana: {abiertas}.\n"
    return (f"[{hotel}] Resumen semanal de Guillermo", cuerpo)


# ── El envío ─────────────────────────────────────────────────────────────────

def enviar(asunto: str, cuerpo: str,
           destinatarios_crudos: str | None) -> tuple[bool, str]:
    """Manda, o explica por qué no. **Nunca levanta**: un fallo de correo no
    puede tumbar la ronda ni el latido — el aviso es lo accesorio, y el latido
    lo importante."""
    con = estado(destinatarios_crudos)
    if not con.configurado:
        return False, con.motivo

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = con.remitente
    msg["To"] = ", ".join(con.destinatarios)
    msg.set_content(cuerpo)

    puerto = int(os.getenv("SMTP_PORT", "587") or 587)
    try:
        if puerto == 465:
            with smtplib.SMTP_SSL(con.servidor, puerto, timeout=20,
                                  context=ssl.create_default_context()) as s:
                s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
                s.send_message(msg)
        else:
            with smtplib.SMTP(con.servidor, puerto, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", ""))
                s.send_message(msg)
    except Exception as e:                          # noqa: BLE001
        # ⚠️ El motivo se devuelve, no se traga: «no llegó el correo» tiene que
        # poder contestarse sin adivinar.
        return False, f"{type(e).__name__}: {e}"[:300]
    return True, f"enviado a {len(con.destinatarios)}"
