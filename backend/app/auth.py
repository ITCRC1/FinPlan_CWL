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

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.models.user import User

SECRET = os.environ.get("SECRET_KEY", "dev-secret-change-me")
# Vida del token: 10 minutos. Es corto A PROPÓSITO y NO significa que a quien
# esté trabajando lo saquen cada 10 minutos: el frontend renueva el token
# mientras haya actividad (`components/AuthGate.tsx`), así que lo que se corta a
# los 10 minutos es la INACTIVIDAD.
#
# ⚠️ Si se cambia este número hay que cambiar `TTL_MS` en `AuthGate.tsx`. Si el
# front creyera que la vida es más larga de lo que es, renovaría tarde y sacaría
# a gente que está escribiendo. Lo blinda `tests/test_sesion_por_inactividad.py`.
TOKEN_TTL = 60 * 10   # 10 minutos (ver nota de arriba)
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


# ─── Llave del Budget Package en vivo ─────────────────────────────────────────
#
# Owner, 2026-11-06: *«automatiza este [Budget Package] de una, así como está…
# cada tab»* — y, preguntado si eso incluía la plantilla con sueldos, *«sí,
# las 22»*. El libro se refresca desde Excel: quien lo pide es la ruta
# `/api/paquete` del frontend, que no tiene usuario con sesión.
#
# ⚠️ **Es OTRA llave que la del consolidado, a propósito.** Aquélla abre el P&L
# por línea y nada más; ésta abre la plantilla por posición con su sueldo. Que
# sean distintas permite revocar una sin tocar la otra.
#
# Tres candados, igual que la del consolidado:
#   * abre SÓLO las rutas que arma el paquete (`RUTAS_DEL_PAQUETE`), y sólo en
#     el método con que se leen — ninguna escribe en la base;
#   * nace apagada: sin `PAQUETE_API_KEY` no existe ninguna llave válida;
#   * se compara en tiempo constante.
RUTAS_DEL_PAQUETE = frozenset({
    ("GET", "/api/scenarios/"),
    ("GET", "/api/reports/pl-detail/{ambito}/"),
    ("GET", "/api/gasto-por-clase/"),
    ("GET", "/api/gasto-por-clase/detalle-de-celda/"),
    ("GET", "/api/payroll/posiciones/"),
    ("GET", "/api/allocations/{scenario_id}/summary/"),
    ("GET", "/api/pl/{scenario_id}/estadisticas/"),
    # Arma la grilla del libro con el exportador de siempre. No toca la base.
    ("POST", "/api/export/cuadros/grilla/"),
})

#: Quien entra con la llave del paquete. No existe en la tabla de usuarios ni
#: se guarda: es sólo para que los endpoints que piden un `User` lo reciban.
LECTOR_DEL_PAQUETE_ID = "llave-budget-package"


def llave_del_paquete_valida(recibida: str) -> bool:
    esperada = (os.environ.get("PAQUETE_API_KEY") or "").strip()
    if not esperada or not recibida:
        return False
    return hmac.compare_digest(recibida.strip(), esperada)


def _ruta_del_paquete(request: Request | None) -> bool:
    if request is None:
        return False
    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", "") or request.url.path
    # ⚠️ La ruta del router viene SIN el prefijo `/api` con que la monta
    # `main.py`; la URL cruda, con él. Se comparan las dos igual.
    if not plantilla.startswith("/api/"):
        plantilla = "/api" + plantilla
    return (request.method, plantilla) in RUTAS_DEL_PAQUETE


# ─── FastAPI dependencies ─────────────────────────────────────────────────────
async def get_current_user(
    request: Request = None,
    authorization: str = Header(default=""),
    token: str | None = None,   # alterna para descargas <a href> (no mandan header)
    x_paquete_key: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    # ⚠️ `isinstance`: quien llama a esta función a mano —`lector_del_consolidado`—
    # no pasa la cabecera, y lo que recibe es el `Header(...)` por defecto, que
    # es un objeto y daría verdadero.
    if isinstance(x_paquete_key, str) and x_paquete_key:
        # Una llave que no es, o una ruta que el paquete no usa, no cae a la
        # sesión: contesta 401. Si cayera, quien probara llaves vería la
        # diferencia entre «llave mala» y «ruta cerrada».
        if llave_del_paquete_valida(x_paquete_key) and _ruta_del_paquete(request):
            return User(id=LECTOR_DEL_PAQUETE_ID, email=LECTOR_DEL_PAQUETE_ID,
                        name="Budget Package en vivo", role="viewer",
                        password_hash="", active=True)
        raise ErrorApi(401, "auth.no_autenticado")
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
