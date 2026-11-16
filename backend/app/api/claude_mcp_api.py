"""El conector de Claude (claude.ai) a FinPlan: OAuth 2.1 + servidor MCP.

Consulta todo; MODIFICA solo versiones marcadas «editable desde Claude» (`claude_escritura`).

Owner, 2026-11-16: «como hago para que mi jefe haga consultas directas a Claude
desde su computadora sin tener que bajar nada» → conector personalizado de
claude.ai (plan Team: lo agrega el Owner en Organization settings → Connectors;
cada persona hace «Connect» con su usuario de FinPlan).

Rutas (en la RAÍZ del backend, no bajo /api, como las espera Claude):

    GET  /.well-known/oauth-protected-resource[/mcp]   RFC 9728
    GET  /.well-known/oauth-authorization-server       RFC 8414
    POST /oauth/register                               DCR, RFC 7591
    GET  /oauth/authorize   · POST /oauth/authorize    pantalla de entrada de FinPlan
    POST /oauth/token                                  código+PKCE → tokens; refresh rotado
    POST /mcp                                          JSON-RPC de MCP (Streamable HTTP)

Requisitos de Claude que esto cumple (claude.com/docs/connectors/building/authentication):
* `401` con `WWW-Authenticate: Bearer resource_metadata=…` para arrancar el login.
* `resource` = la URL del conector EXACTA (`…/mcp`); un solo authorization server.
* DCR con `registration_endpoint`; PKCE S256 obligatorio; `token_endpoint_auth_methods_supported: ["none"]`.
* `/oauth/token` acepta `application/x-www-form-urlencoded`; refresh rotado; `invalid_grant` cuando no vale.
* Retorno a `https://claude.ai/api/mcp/auth_callback` (y claude.com) o loopback de Claude Code.

⚠️ **Quién entra:** un usuario ACTIVO de FinPlan con la casilla «Acceso desde
Claude» (`users.acceso_claude`). Se vuelve a verificar en CADA consulta, no solo
al entrar: desactivar al usuario o apagar la casilla corta el conector de inmediato.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select

from app.auth import SECRET, _b64, _b64d, verify_password
from app.db import get_session
from app.hotel_actual import HOTEL_NAME
from app.models.acceso_claude import ClaudeCliente, ClaudeCodigo, ClaudeConsulta, ClaudeRefresh
from app.models.user import User

router = APIRouter(tags=["claude"])

ACCESS_TTL = 60 * 60            # 1 hora: Claude renueva solo con el refresh token
REFRESH_TTL = 60 * 60 * 24 * 30  # 30 días; se rota en cada uso
CODIGO_TTL = 5 * 60
SCOPE = "finplan.lectura"
AUD = "finplan-mcp"
VERSIONES_MCP = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

#: Las únicas direcciones a las que FinPlan devuelve el código. Un cliente
#: registrado con otra dirección se rechaza: así nadie puede registrar un
#: «cliente» que se lleve el permiso a su propio servidor.
REDIRECTS_PERMITIDOS = ("https://claude.ai/api/mcp/auth_callback",
                        "https://claude.com/api/mcp/auth_callback")


def _redirect_valido(uri: str) -> bool:
    if uri in REDIRECTS_PERMITIDOS:
        return True
    # Claude Code: loopback en cualquier puerto (RFC 8252 §7.3), localhost o 127.0.0.1.
    try:
        u = urlparse(uri)
    except ValueError:
        return False
    return u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1") and u.path == "/callback"


def _base(request: Request) -> str:
    """La URL pública del backend. Railway termina el TLS delante: el request
    llega como http, así que se toma el esquema de `x-forwarded-proto`."""
    fija = (os.environ.get("MCP_BASE_URL") or "").strip().rstrip("/")
    if fija:
        return fija
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    if not host.startswith(("localhost", "127.0.0.1")):
        proto = "https"
    return f"{proto}://{host}"


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _vigente(dt: datetime | None) -> bool:
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt > _ahora()


# ── Token de acceso: JWT HS256 propio, con audiencia distinta al de la app ────
#
# ⚠️ Lleva `aud=finplan-mcp`: un token del conector NO sirve para la API de la
# app, y uno de la app (aud ausente) NO sirve acá. Si compartieran formato sin
# audiencia, el token que se le da a Claude abriría también las rutas que escriben.

def _token_acceso(user: User, client_id: str, base: str) -> str:
    import hmac
    cab = {"alg": "HS256", "typ": "JWT"}
    cuerpo = {"sub": user.id, "email": user.email, "aud": AUD, "iss": base, "cid": client_id,
              "scope": SCOPE, "exp": int(time.time()) + ACCESS_TTL, "iat": int(time.time())}
    seg = _b64(json.dumps(cab, separators=(",", ":")).encode()) + "." + \
        _b64(json.dumps(cuerpo, separators=(",", ":")).encode())
    firma = hmac.new(SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return seg + "." + _b64(firma)


def _leer_token(tok: str) -> dict | None:
    import hmac
    try:
        seg, firma = tok.rsplit(".", 1)
        esperada = hmac.new(SECRET.encode(), seg.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(esperada, _b64d(firma)):
            return None
        cuerpo = json.loads(_b64d(seg.split(".", 1)[1]))
        if cuerpo.get("aud") != AUD or cuerpo.get("exp", 0) < time.time():
            return None
        return cuerpo
    except Exception:  # noqa: BLE001
        return None


# ── Descubrimiento ───────────────────────────────────────────────────────────

def _metadata_recurso(request: Request) -> dict:
    b = _base(request)
    return {"resource": f"{b}/mcp", "authorization_servers": [b],
            "scopes_supported": [SCOPE], "bearer_methods_supported": ["header"],
            "resource_name": f"FinPlan {HOTEL_NAME}"}


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def recurso_protegido(request: Request):
    return JSONResponse(_metadata_recurso(request))


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
@router.get("/.well-known/openid-configuration")
async def servidor_autorizacion(request: Request):
    b = _base(request)
    return JSONResponse({
        "issuer": b,
        "authorization_endpoint": f"{b}/oauth/authorize",
        "token_endpoint": f"{b}/oauth/token",
        "registration_endpoint": f"{b}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [SCOPE],
    })


# ── Registro dinámico de clientes (RFC 7591) ─────────────────────────────────

@router.post("/oauth/register")
async def registrar(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid_client_metadata"}, status_code=400)
    uris = body.get("redirect_uris") or []
    if not uris or not all(isinstance(u, str) and _redirect_valido(u) for u in uris):
        return JSONResponse({"error": "invalid_redirect_uri",
                             "error_description": "FinPlan solo acepta la dirección de retorno de Claude."},
                            status_code=400)
    cid = "fp_" + secrets.token_urlsafe(24)
    async with get_session() as s:
        s.add(ClaudeCliente(client_id=cid, nombre=str(body.get("client_name") or "")[:200], redirect_uris=uris))
        await s.commit()
    return JSONResponse({
        "client_id": cid, "client_id_issued_at": int(time.time()),
        "client_name": body.get("client_name") or "", "redirect_uris": uris,
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none", "scope": SCOPE,
    }, status_code=201)


# ── Pantalla de entrada ──────────────────────────────────────────────────────

_PARAMS = ("response_type", "client_id", "redirect_uri", "code_challenge",
           "code_challenge_method", "state", "scope", "resource")


def _pantalla(p: dict, error: str = "", email: str = "") -> HTMLResponse:
    destino = urlparse(p.get("redirect_uri") or "").hostname or ""
    ocultos = "".join(f'<input type="hidden" name="{k}" value="{html.escape(p.get(k) or "")}">' for k in _PARAMS)
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FinPlan · Conectar con Claude</title>
<style>body{{font-family:Arial,sans-serif;background:#f4f3ef;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center}}
.c{{background:#fff;border:1px solid #ddd;border-radius:10px;padding:28px;max-width:380px;width:92%}}
h1{{font-size:20px;margin:0 0 6px}}p{{font-size:14px;color:#444;line-height:1.45}}label{{font-size:13px;color:#555}}
input[type=email],input[type=password]{{width:100%;box-sizing:border-box;padding:10px;margin:4px 0 12px;border:1px solid #ccc;border-radius:6px;font-size:15px}}
button{{width:100%;padding:11px;background:#2156c5;color:#fff;border:0;border-radius:6px;font-size:15px;font-weight:bold;cursor:pointer}}
.err{{color:#b00020;font-weight:bold}}.mut{{font-size:12px;color:#777}}</style></head><body><div class="c">
<h1>FinPlan · {html.escape(HOTEL_NAME)}</h1>
<p><b>Claude</b> ({html.escape(destino)}) quiere usar FinPlan en tu nombre: P&amp;L, versiones, planilla,
checkbooks y el mayor. <b>Solo puede modificar las versiones de trabajo habilitadas para Claude</b>
(nunca el Working, el Final, los reales ni el Pre-Cierre).</p>{err}
<form method="post" action="/oauth/authorize">{ocultos}
<label>Correo</label><input type="email" name="email" required autofocus value="{html.escape(email)}">
<label>Contraseña de FinPlan</label><input type="password" name="password" required>
<button type="submit">Conectar con Claude</button></form>
<p class="mut">Para quitarle el acceso: en FinPlan, Admin → Usuarios → «Acceso desde Claude».</p>
</div></body></html>""", headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})


async def _validar_pedido(p: dict) -> str:
    """Devuelve '' si el pedido es válido, o el motivo."""
    if p.get("response_type") != "code":
        return "response_type debe ser «code»"
    if p.get("code_challenge_method") != "S256" or not p.get("code_challenge"):
        return "Falta PKCE S256"
    async with get_session() as s:
        cli = await s.get(ClaudeCliente, p.get("client_id") or "")
    if cli is None:
        return "Cliente desconocido: volvé a conectar desde Claude"
    if p.get("redirect_uri") not in (cli.redirect_uris or []):
        return "La dirección de retorno no es la registrada"
    return ""


@router.get("/oauth/authorize")
async def autorizar_get(request: Request):
    p = {k: request.query_params.get(k) for k in _PARAMS}
    motivo = await _validar_pedido(p)
    if motivo:
        return HTMLResponse(f"<p>{html.escape(motivo)}</p>", status_code=400)
    return _pantalla(p)


#: Intentos fallidos por correo: 5 en 15 minutos y se frena. En memoria a
#: propósito — un reinicio lo limpia, pero alcanza contra adivinar claves a mano.
_FALLOS: dict[str, list[float]] = {}


@router.post("/oauth/authorize")
async def autorizar_post(request: Request):
    form = await request.form()
    p = {k: (form.get(k) or None) for k in _PARAMS}
    motivo = await _validar_pedido(p)
    if motivo:
        return HTMLResponse(f"<p>{html.escape(motivo)}</p>", status_code=400)
    email = str(form.get("email") or "").strip().lower()
    clave = str(form.get("password") or "")
    ahora = time.time()
    recientes = [t for t in _FALLOS.get(email, []) if ahora - t < 900]
    if len(recientes) >= 5:
        return _pantalla(p, "Demasiados intentos. Esperá 15 minutos.", email)
    async with get_session() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        ok = bool(user and user.active and verify_password(clave, user.password_hash))
        if not ok:
            _FALLOS[email] = recientes + [ahora]
            return _pantalla(p, "Correo o contraseña incorrectos.", email)
        if not getattr(user, "acceso_claude", False):
            return _pantalla(p, "Tu usuario no tiene «Acceso desde Claude». Pedíselo a un administrador de FinPlan.", email)
        _FALLOS.pop(email, None)
        codigo = secrets.token_urlsafe(32)
        s.add(ClaudeCodigo(codigo_hash=_h(codigo), client_id=p["client_id"], user_id=user.id,
                           redirect_uri=p["redirect_uri"], code_challenge=p["code_challenge"],
                           scope=SCOPE, vence=_ahora() + timedelta(seconds=CODIGO_TTL)))
        await s.commit()
    q = {"code": codigo}
    if p.get("state"):
        q["state"] = p["state"]
    sep = "&" if "?" in p["redirect_uri"] else "?"
    return RedirectResponse(p["redirect_uri"] + sep + urlencode(q), status_code=302)


# ── Token ────────────────────────────────────────────────────────────────────

def _err(code: str, desc: str = "", status: int = 400) -> JSONResponse:
    return JSONResponse({"error": code, **({"error_description": desc} if desc else {})},
                        status_code=status, headers={"Cache-Control": "no-store"})


async def _emitir(s, user: User, client_id: str, base: str) -> JSONResponse:
    refresh = secrets.token_urlsafe(40)
    s.add(ClaudeRefresh(token_hash=_h(refresh), client_id=client_id, user_id=user.id, scope=SCOPE,
                        vence=_ahora() + timedelta(seconds=REFRESH_TTL)))
    await s.commit()
    return JSONResponse({"access_token": _token_acceso(user, client_id, base), "token_type": "Bearer",
                         "expires_in": ACCESS_TTL, "refresh_token": refresh, "scope": SCOPE},
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


def _usuario_habilitado(user: User | None) -> bool:
    return bool(user and user.active and getattr(user, "acceso_claude", False))


@router.post("/oauth/token")
async def token(request: Request):
    form = await request.form()
    grant = form.get("grant_type")
    client_id = str(form.get("client_id") or "")
    base = _base(request)
    async with get_session() as s:
        if grant == "authorization_code":
            cod = await s.get(ClaudeCodigo, _h(str(form.get("code") or "")))
            if cod is None or cod.usado or not _vigente(cod.vence):
                return _err("invalid_grant", "El código no vale o ya se usó")
            if client_id and cod.client_id != client_id:
                return _err("invalid_grant", "El código es de otro cliente")
            if str(form.get("redirect_uri") or cod.redirect_uri) != cod.redirect_uri:
                return _err("invalid_grant", "redirect_uri distinta")
            verificador = str(form.get("code_verifier") or "")
            reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
            if not verificador or not secrets.compare_digest(reto, cod.code_challenge):
                return _err("invalid_grant", "PKCE no coincide")
            cod.usado = True
            user = await s.get(User, cod.user_id)
            if not _usuario_habilitado(user):
                await s.commit()
                return _err("invalid_grant", "Usuario sin acceso")
            return await _emitir(s, user, cod.client_id, base)
        if grant == "refresh_token":
            rt = await s.get(ClaudeRefresh, _h(str(form.get("refresh_token") or "")))
            if rt is None or rt.revocado or not _vigente(rt.vence):
                return _err("invalid_grant", "El refresh token no vale")
            if client_id and rt.client_id != client_id:
                return _err("invalid_grant", "El refresh token es de otro cliente")
            rt.revocado = True        # rotación: el viejo ya no sirve
            user = await s.get(User, rt.user_id)
            if not _usuario_habilitado(user):
                await s.commit()
                return _err("invalid_grant", "Usuario sin acceso")
            return await _emitir(s, user, rt.client_id, base)
    return _err("unsupported_grant_type")


# ── MCP (Streamable HTTP, respuestas JSON) ───────────────────────────────────

def _no_autorizado(request: Request, error: str = "") -> Response:
    b = _base(request)
    extra = f', error="{error}"' if error else ""
    return JSONResponse({"error": "unauthorized"}, status_code=401, headers={
        "WWW-Authenticate": f'Bearer resource_metadata="{b}/.well-known/oauth-protected-resource"{extra}'})


INSTRUCCIONES = (
    f"FinPlan es el sistema de planificación financiera de {HOTEL_NAME} (formato USALI, USD). "
    "Versiones: ACTUAL (real), Pre-Cierre (el mes que se está cerrando: tipo ACTUAL versión «Pre-Cierre»), "
    "FORECAST (el vigente lleva forecast_vigente=true y trae reales hasta «actuales_hasta_mes») y BUDGET. "
    "Empezá por `versiones` si no sabés el nombre exacto. Para comparar, usá `comparar`. "
    "Siempre que des una cifra de un mes, dala también contra el mismo mes del año anterior (Actual). "
    "Cafetería (0220) y Lavandería interna (0161) son centros que reparten su costo a los departamentos "
    "(crédito 4999): en el Actual, Budget y Forecast su neto es 0; solo el Pre-Cierre los muestra. "
    "Consultar es libre. MODIFICAR solo se puede en versiones con claude_puede_editar=true (hoy BUDGET 2027 "
    "«Draft1-PAN», para armar un modelo de negocio nuevo): nombrá siempre la versión exacta, decile al usuario "
    "qué vas a cambiar antes de hacerlo, y al terminar llamá a `recalcular` y mostrá el resultado contra el "
    "Budget Working. Nunca intentes cambiar el Working, el Final, un Actual ni el Pre-Cierre."
)


async def _usuario_del_token(request: Request) -> tuple[User | None, str]:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None, ""
    cuerpo = _leer_token(auth[7:].strip())
    if not cuerpo:
        return None, "invalid_token"
    async with get_session() as s:
        user = await s.get(User, cuerpo.get("sub"))
    if not _usuario_habilitado(user):
        return None, "invalid_token"
    return user, ""


def _rpc_ok(id_, result) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _rpc_err(id_, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": msg}}


async def _registrar(user: User, herramienta: str, args: dict, ok: bool, error: str, ms: int):
    try:
        async with get_session() as s:
            s.add(ClaudeConsulta(user_id=user.id, email=user.email, herramienta=herramienta[:60],
                                 argumentos=args or {}, ok=ok, error=error[:2000], ms=ms))
            await s.commit()
    except Exception:  # noqa: BLE001 — el registro nunca tumba la respuesta
        pass


async def _atender(msg: dict, user: User) -> dict | None:
    from app import claude_herramientas as H
    metodo = msg.get("method")
    id_ = msg.get("id")
    if id_ is None:                       # notificación (p. ej. notifications/initialized)
        return None
    if metodo == "initialize":
        pedida = (msg.get("params") or {}).get("protocolVersion")
        return _rpc_ok(id_, {
            "protocolVersion": pedida if pedida in VERSIONES_MCP else VERSIONES_MCP[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "finplan-cwl", "title": f"FinPlan {HOTEL_NAME}", "version": "1.0.0"},
            "instructions": INSTRUCCIONES,
        })
    if metodo == "ping":
        return _rpc_ok(id_, {})
    if metodo == "tools/list":
        return _rpc_ok(id_, {"tools": H.lista_mcp()})
    if metodo == "tools/call":
        params = msg.get("params") or {}
        nombre, args = params.get("name") or "", params.get("arguments") or {}
        t0 = time.time()
        try:
            datos = await H.ejecutar(nombre, args, user)
        except KeyError:
            return _rpc_err(id_, -32602, f"Herramienta desconocida: {nombre}")
        except Exception as e:  # noqa: BLE001 — el error vuelve a Claude como resultado, no como caída
            await _registrar(user, nombre, args, False, f"{type(e).__name__}: {e}", int((time.time() - t0) * 1000))
            return _rpc_ok(id_, {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True})
        await _registrar(user, nombre, args, True, "", int((time.time() - t0) * 1000))
        texto = json.dumps(datos, ensure_ascii=False, default=str)
        return _rpc_ok(id_, {"content": [{"type": "text", "text": texto}], "isError": False})
    if metodo in ("resources/list", "prompts/list"):
        return _rpc_ok(id_, {"resources": []} if metodo == "resources/list" else {"prompts": []})
    return _rpc_err(id_, -32601, f"Método no soportado: {metodo}")


@router.post("/mcp")
async def mcp(request: Request):
    user, error = await _usuario_del_token(request)
    if user is None:
        return _no_autorizado(request, error)
    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(_rpc_err(None, -32700, "JSON inválido"), status_code=400)
    if isinstance(cuerpo, list):
        respuestas = [r for r in [await _atender(m, user) for m in cuerpo] if r is not None]
        return JSONResponse(respuestas) if respuestas else Response(status_code=202)
    r = await _atender(cuerpo, user)
    if r is None:
        return Response(status_code=202)
    return JSONResponse(r)


@router.get("/mcp")
async def mcp_get(request: Request):
    """Sin canal SSE de servidor a cliente: este conector solo responde."""
    user, error = await _usuario_del_token(request)
    if user is None:
        return _no_autorizado(request, error)
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp")
async def mcp_delete():
    return Response(status_code=405, headers={"Allow": "POST"})
