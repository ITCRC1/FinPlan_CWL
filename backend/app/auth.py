"""Auth — stdlib puro (sin dependencias): pbkdf2 para passwords, JWT HS256 con hmac.

No enforcement global todavía (Fase 0 paso A): estas utilidades + dependencias
existen y se usan en /auth, pero los endpoints de datos aún NO exigen token.
"""
import os
import hmac
import json
import time
import base64
import hashlib
from typing import Optional

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.models.user import User

SECRET = os.environ.get("SECRET_KEY", "dev-secret-change-me")
TOKEN_TTL = 60 * 60 * 24 * 7   # 7 días
PBKDF2_ITERS = 200_000


# ─── Password hashing (pbkdf2_sha256) ─────────────────────────────────────────
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ITERS)
    return f"pbkdf2_sha256${PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _algo, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ─── JWT HS256 ────────────────────────────────────────────────────────────────
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_access_token(sub: str, role: str, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = {"sub": sub, "role": role, "email": email, "exp": int(time.time()) + TOKEN_TTL}
    seg = _b64(json.dumps(header, separators=(",", ":")).encode()) + "." + \
        _b64(json.dumps(body, separators=(",", ":")).encode())
    sig = hmac.new(SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return seg + "." + _b64(sig)


def decode_token(token: str) -> Optional[dict]:
    try:
        seg, sig = token.rsplit(".", 1)
        expected = hmac.new(SECRET.encode(), seg.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(sig)):
            return None
        body = json.loads(_b64d(seg.split(".", 1)[1]))
        if body.get("exp", 0) < time.time():
            return None
        return body
    except Exception:
        return None


# ─── FastAPI dependencies ─────────────────────────────────────────────────────
async def get_current_user(
    authorization: str = Header(default=""),
    token: str | None = None,   # alterna para descargas <a href> (no mandan header)
    db: AsyncSession = Depends(get_db),
) -> User:
    raw = ""
    if authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif token:
        raw = token
    if not raw:
        raise ErrorApi(401, "auth.no_autenticado")
    payload = decode_token(raw)
    if not payload:
        raise ErrorApi(401, "auth.token_invalido")
    user = (await db.execute(
        select(User).where(User.id == payload.get("sub"))
    )).scalar_one_or_none()
    if not user or not user.active:
        raise ErrorApi(401, "auth.usuario_no_valido")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Sólo `admin`. **No se tocó al agregar roles nuevos, y es a propósito.**

    ⚠️ Un rol nuevo NO puede heredar los 12 endpoints de administración —crear
    usuarios, editar orígenes, integraciones— sólo porque se lo agregó a la
    lista. Quien necesite un permiso distinto pide una dependencia distinta.
    """
    if user.role != "admin":
        raise ErrorApi(403, "auth.requiere_admin")
    return user


async def get_guillermo_approver(user: User = Depends(get_current_user)) -> User:
    """Quien puede aprobar o rechazar una excepción de Guillermo (§9.5).

    ⚠️ **`admin` también entra.** Si el único rol habilitado fuera
    `guillermo_approver`, el administrador del sistema quedaría afuera de la
    cola — y con él la única persona que puede crear el rol. Un permiso que
    puede dejar a todos afuera no es un permiso, es una trampa.
    """
    if user.role not in ("admin", "guillermo_approver"):
        raise ErrorApi(403, "auth.requiere_admin")
    return user


# ─── Llave de solo lectura para el consolidado ────────────────────────────────
#
# El token de sesión dura 7 días: sirve para la app, no para un consolidador que
# jala todos los lunes — se vence y el tablero queda en blanco sin avisar.
#
# Esta llave es larga, propia de CADA propiedad y abre UN endpoint: el P&L por
# línea. No escribe, no lista usuarios, no ve detalle.
#
# **Nace apagada.** Sin la variable de entorno no existe ninguna llave válida, y
# el endpoint queda solo para la sesión normal. Se revoca cambiando la variable.
def _llave_configurada() -> str:
    return (os.environ.get("CONSOLIDADO_API_KEY") or "").strip()


def llave_de_consolidado_valida(recibida: str) -> bool:
    """Comparación en tiempo constante — con `==` se puede adivinar la llave
    midiendo cuánto tarda en responder."""
    esperada = _llave_configurada()
    if not esperada or not recibida:
        return False
    return hmac.compare_digest(recibida.strip(), esperada)


async def lector_del_consolidado(
    authorization: str = Header(default=""),
    x_api_key: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Deja pasar a la llave de solo lectura O a un usuario con sesión.

    Devuelve quién entró, para que el endpoint lo pueda registrar.
    """
    if x_api_key and llave_de_consolidado_valida(x_api_key):
        return "llave-consolidado"
    usuario = await get_current_user(authorization=authorization, db=db)
    return usuario.email
