"""El acceso de Claude (claude.ai) a FinPlan: OAuth 2.1 + el registro de consultas.

Owner, 2026-11-16: «como hago para que mi jefe haga consultas directas a claude
desde su computadora» · «el 3 me gusta» (conector a FinPlan en vivo) · «él puede
ver todo» · «1- sí dale [la casilla Acceso desde Claude], 2- ok, construye».

Claude entra con la cuenta de FinPlan DE CADA PERSONA, nunca con una llave
compartida: el usuario pone su correo y su clave en la pantalla de FinPlan, y
FinPlan le entrega a Claude un permiso propio de esa persona. Desactivar al
usuario o quitarle «Acceso desde Claude» corta el conector en la siguiente
consulta.

⚠️ Ningún secreto se guarda en claro: códigos y refresh tokens van como SHA-256.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _id() -> str:
    return str(uuid.uuid4())


class ClaudeCliente(Base):
    """Un cliente OAuth registrado por Dynamic Client Registration (RFC 7591).

    Claude registra uno en cada conexión nueva. Solo se aceptan las direcciones
    de retorno de Claude (ver `claude_mcp_api.REDIRECTS_PERMITIDOS`): un tercero
    que registre un cliente no puede llevarse el código a otro lado.
    """
    __tablename__ = "claude_oauth_clientes"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), default="")
    redirect_uris: Mapped[list] = mapped_column(JSON, default=list)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaudeCodigo(Base):
    """Código de autorización de un solo uso (5 minutos), atado a PKCE S256."""
    __tablename__ = "claude_oauth_codigos"

    codigo_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    redirect_uri: Mapped[str] = mapped_column(Text)
    code_challenge: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(200), default="")
    vence: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado: Mapped[bool] = mapped_column(Boolean, default=False)


class ClaudeRefresh(Base):
    """Refresh token (30 días). Se ROTA en cada uso: el viejo queda revocado."""
    __tablename__ = "claude_oauth_refresh"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    scope: Mapped[str] = mapped_column(String(200), default="")
    vence: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaudeConsulta(Base):
    """Cada herramienta que Claude usó: quién, qué, con qué y cuánto tardó."""
    __tablename__ = "claude_consultas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    email: Mapped[str] = mapped_column(String(160), default="")
    herramienta: Mapped[str] = mapped_column(String(60))
    argumentos: Mapped[dict] = mapped_column(JSON, default=dict)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")
    ms: Mapped[int] = mapped_column(Integer, default=0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
