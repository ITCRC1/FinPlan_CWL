"""Auth API — login, bootstrap del primer admin, gestión de usuarios.

Fase 0 paso A: existe el sistema de usuarios pero los endpoints de datos NO
exigen token todavía (eso es el paso C). Acá ya se puede crear el admin y loguear.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.i18n import LOCALES, normalize_locale, resolve_locale
from app.temas import TEMAS, TEMA_POR_DEFECTO
from app.models.hotel import Hotel
from app.models.invitacion import (DIAS_DE_VIGENCIA, InvitacionUsuario,
                                    SIN_CLAVE, hash_de_token, nuevo_token)
from app.models.user import User, ROLES
from app.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, get_current_admin,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "active": u.active, "locale": u.locale, "tema": u.tema}


async def _hotel_locale(db: AsyncSession) -> str | None:
    """El default de la propiedad. Hoy hay una sola (CWL); el día que haya
    varias, esto pasa a leer la del usuario."""
    h = (await db.execute(
        select(Hotel).where(Hotel.active.is_(True)).order_by(Hotel.id)
    )).scalars().first()
    return getattr(h, "default_locale", None) if h else None


async def _session_payload(db: AsyncSession, user: User, token: str) -> dict:
    """Lo que necesita el frontend para arrancar: sesión + idioma YA RESUELTO.

    El idioma viaja resuelto porque el token vive en `localStorage` y el render
    del servidor no puede leerlo: el frontend guarda este valor en la cookie
    `finplan_locale`, que sí se lee del lado del servidor.
    """
    return {"token": token, "user": _user_dict(user),
            "locale": resolve_locale(user.locale, await _hotel_locale(db)),
            # El tema viaja por la misma razón que el idioma: el render del
            # servidor lo necesita ANTES de que exista JavaScript, y sin esto
            # cada carga parpadearía del default al elegido.
            "tema": user.tema or TEMA_POR_DEFECTO}


class LoginBody(BaseModel):
    email: str
    password: str


class BootstrapBody(BaseModel):
    email: str
    password: str
    name: str = ""


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Público: ¿ya hay usuarios? (para decidir login vs crear-primer-admin)."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return {"has_users": bool(count and count > 0)}


@router.post("/bootstrap")
async def bootstrap_admin(body: BootstrapBody, db: AsyncSession = Depends(get_db)):
    """Crea el PRIMER admin. Solo funciona si todavía no hay usuarios."""
    count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if count and count > 0:
        raise ErrorApi(409, "auth.bootstrap_deshabilitado")
    if len(body.password) < 8:
        raise ErrorApi(422, "clave.muy_corta")
    user = User(email=str(body.email).lower(), name=body.name or str(body.email),
                password_hash=hash_password(body.password), role="admin", active=True)
    db.add(user)
    await db.commit()
    token = create_access_token(user.id, user.role, user.email)
    return await _session_payload(db, user, token)


@router.post("/login")
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(
        select(User).where(User.email == str(body.email).lower())
    )).scalar_one_or_none()
    if not user or not user.active or not verify_password(body.password, user.password_hash):
        raise ErrorApi(401, "auth.credenciales_invalidas")
    token = create_access_token(user.id, user.role, user.email)
    return await _session_payload(db, user, token)


@router.post("/refresh")
async def refresh(user: User = Depends(get_current_user)):
    """Cambia un token válido por uno nuevo. Es lo que hace que la sesión se
    corte por INACTIVIDAD y no por reloj.

    `TOKEN_TTL` son 10 minutos. Sin este endpoint, ese número sacaría a la gente
    a mitad de cargar un checkbook de 12 meses —y sin refresh no hay nada que
    salve lo no guardado—. Con él, el frontend renueva mientras haya actividad
    (`components/AuthGate.tsx`) y el token solo caduca si nadie tocó nada.

    Pide un token que TODAVÍA sirva: renovar es prolongar una sesión viva, no
    resucitar una vencida. Quien llega tarde vuelve a entrar por `/login`.
    """
    return {"token": create_access_token(user.id, user.role, user.email)}


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {**_user_dict(user),
            "resolved_locale": resolve_locale(user.locale, await _hotel_locale(db))}


class LocaleBody(BaseModel):
    locale: str | None = None   # None = «usá el del hotel»


@router.patch("/me/locale")
async def set_my_locale(
    body: LocaleBody,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """Preferencia personal de idioma. `null` la borra y vuelve a mandar el
    default de la propiedad — por eso el campo es nullable y no un 'es'."""
    if body.locale is not None and normalize_locale(body.locale) is None:
        raise ErrorApi(422, "locale.invalido", locales=LOCALES)
    user.locale = normalize_locale(body.locale)
    await db.commit()
    return {**_user_dict(user),
            "resolved_locale": resolve_locale(user.locale, await _hotel_locale(db))}


class TemaBody(BaseModel):
    tema: str | None = None   # None = «usá el que viene por defecto»


@router.patch("/me/tema")
async def set_my_tema(
    body: TemaBody,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """La paleta que eligió esta persona. `null` la borra y vuelve al default.

    Se valida contra la lista: un tema que no existe no rompe la pantalla —el
    CSS cae al `:root`— pero deja al usuario con un valor guardado que no hace
    nada y que nadie puede explicar después."""
    if body.tema is not None and body.tema not in TEMAS:
        raise ErrorApi(422, "tema.invalido", temas=", ".join(TEMAS))
    user.tema = body.tema
    await db.commit()
    return {**_user_dict(user), "tema": user.tema or TEMA_POR_DEFECTO}


class UserCreate(BaseModel):
    email: str
    name: str = ""
    role: str = "collaborator"


#: Mínimo de una contraseña. El mismo que ya exigía el alta.
LARGO_MINIMO = 8


def _url_invitacion(token: str) -> str:
    """El enlace que el admin copia y manda.

    Sale de `APP_URL` del entorno; si no está, se devuelve la ruta sola y la
    pantalla la completa con su propio origen. Adivinar un dominio acá sería
    mandarle a la gente un enlace que no abre.
    """
    import os

    base = (os.getenv("APP_URL") or "").strip().rstrip("/")
    ruta = f"/invitacion/{token}"
    return f"{base}{ruta}" if base else ruta


async def _emitir_invitacion(db: AsyncSession, user: User, quien: str | None,
                             es_alta: bool) -> dict:
    """Crea la invitación y devuelve el enlace EN CLARO — la única vez que
    existe fuera del navegador de quien la pide.

    ⚠️ **No toca `password_hash`.** Owner, 2026-10-25, sobre Blake: *«deja que
    entre con ambos métodos… acaba de enviar la clave»*. Emitir una invitación
    no puede dejar afuera a alguien que ya estaba entrando: la clave vigente
    sigue sirviendo hasta que la persona canjee el enlace y ponga otra.

    ⚠️ **Las invitaciones anteriores de ese usuario se marcan usadas.** Si no,
    el enlace viejo —que sigue vivo en algún chat— también abre, y entonces
    «reenviar» no revoca nada.
    """
    ahora = datetime.now(timezone.utc)
    previas = (await db.execute(select(InvitacionUsuario).where(
        InvitacionUsuario.user_id == user.id,
        InvitacionUsuario.used_at.is_(None)))).scalars().all()
    for p in previas:
        p.used_at = ahora

    token, th = nuevo_token()
    inv = InvitacionUsuario(
        user_id=user.id, token_hash=th,
        expires_at=InvitacionUsuario.vencimiento(ahora),
        created_by=quien, es_alta=es_alta)
    db.add(inv)
    await db.flush()
    return {"url": _url_invitacion(token), "token": token,
            "vence": inv.expires_at.isoformat(), "dias": DIAS_DE_VIGENCIA,
            "reemplazo": len(previas)}


@router.get("/users")
async def list_users(_admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
    return [_user_dict(u) for u in rows]


@router.post("/users")
async def create_user(
    body: UserCreate, _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    if body.role not in ROLES:
        raise ErrorApi(422, "usuario.rol_invalido", roles=ROLES)
    exists = (await db.execute(
        select(User).where(User.email == str(body.email).lower())
    )).scalar_one_or_none()
    if exists:
        raise ErrorApi(409, "usuario.email_duplicado")
    # ⚠️ Nace SIN clave utilizable. `SIN_CLAVE` no es el hash de una contraseña
    # rara: es un valor que `verify_password` no puede aceptar. Hasta que la
    # persona canjee su invitación, no hay forma de entrar con esta cuenta.
    user = User(email=str(body.email).lower(), name=body.name or str(body.email),
                password_hash=SIN_CLAVE, role=body.role, active=True)
    db.add(user)
    await db.flush()
    inv = await _emitir_invitacion(db, user, getattr(_admin, "id", None), True)
    await db.commit()
    return {**_user_dict(user), "invitacion": inv}


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, body: UserUpdate,
    _admin: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    u = await db.get(User, user_id)
    if not u:
        raise ErrorApi(404, "usuario.no_encontrado")
    if body.name is not None:
        u.name = body.name
    if body.role is not None:
        if body.role not in ROLES:
            raise ErrorApi(422, "usuario.rol_invalido", roles=ROLES)
        u.role = body.role
    if body.active is not None:
        u.active = body.active
    if body.password:
        if len(body.password) < 8:
            raise ErrorApi(422, "clave.muy_corta")
        u.password_hash = hash_password(body.password)
    await db.commit()
    return _user_dict(u)


# ═══════════════════════════════════════════════════════════════════════════
# Invitaciones: la persona se pone SU clave
#
# Owner, 2026-10-25: *«yo mando la invitación y ellos generan sus claves»*.
#
# Los dos endpoints de abajo son PÚBLICOS a propósito —quien los usa todavía no
# tiene sesión— y por eso el token es lo único que vale: 32 bytes aleatorios,
# de un solo uso, que vencen a los 7 días.
# ═══════════════════════════════════════════════════════════════════════════
@router.post("/users/{user_id}/invitacion")
async def reenviar_invitacion(
    user_id: str, _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Emite una invitación nueva para un usuario que ya existe.

    Reemplaza al viejo «Reset password», que generaba una contraseña y se la
    mostraba al admin para que la mandara. Acá lo que se manda es un enlace: la
    clave la escribe su dueño y el servidor nunca la ve.

    ⚠️ **No revoca la clave actual.** La persona sigue entrando con la que
    tiene hasta que canjee el enlace. Owner, sobre Blake: *«deja que entre con
    ambos métodos»*.
    """
    u = await db.get(User, user_id)
    if not u:
        raise ErrorApi(404, "usuario.no_encontrado")
    if not u.active:
        raise ErrorApi(409, "usuario.inactivo")
    inv = await _emitir_invitacion(db, u, _admin.id, u.password_hash == SIN_CLAVE)
    await db.commit()
    return {**_user_dict(u), "invitacion": inv}


async def _invitacion_de(db: AsyncSession, token: str) -> InvitacionUsuario:
    """La invitación vigente de ese token, o un 404 que no dice por qué.

    ⚠️ **El mismo error para «no existe», «ya se usó» y «venció».** Distinguirlos
    le contaría a quien prueba tokens al azar cuál acertó a medias. El admin sí
    ve el estado real desde la pantalla de usuarios, que es donde hace falta.
    """
    inv = (await db.execute(select(InvitacionUsuario).where(
        InvitacionUsuario.token_hash == hash_de_token(token)
    ))).scalar_one_or_none()
    if inv is None or not inv.vigente():
        raise ErrorApi(404, "invitacion.no_valida")
    return inv


@router.get("/invitacion/{token}")
async def ver_invitacion(token: str, db: AsyncSession = Depends(get_db)):
    """¿Sirve este enlace? Para que la pantalla sepa qué mostrar antes de que
    la persona escriba nada.

    Devuelve el correo —la persona tiene que ver a qué cuenta le está poniendo
    clave— y nada más. Ni el rol, ni el nombre de quien invitó, ni si hay otros
    usuarios: esto lo abre cualquiera que tenga el enlace.
    """
    inv = await _invitacion_de(db, token)
    u = await db.get(User, inv.user_id)
    if u is None or not u.active:
        raise ErrorApi(404, "invitacion.no_valida")
    return {"email": u.email, "name": u.name, "es_alta": inv.es_alta,
            "largo_minimo": LARGO_MINIMO}


class ClaveNueva(BaseModel):
    password: str


@router.post("/invitacion/{token}")
async def canjear_invitacion(
    token: str, body: ClaveNueva, db: AsyncSession = Depends(get_db),
):
    """La persona pone su clave. Acá SÍ se reemplaza `password_hash`.

    El token se marca usado en la misma transacción que escribe la clave: si
    se marcara después y algo fallara en medio, el enlace seguiría abriendo.
    """
    if len(body.password) < LARGO_MINIMO:
        raise ErrorApi(422, "clave.muy_corta")
    inv = await _invitacion_de(db, token)
    u = await db.get(User, inv.user_id)
    if u is None or not u.active:
        raise ErrorApi(404, "invitacion.no_valida")
    u.password_hash = hash_password(body.password)
    inv.used_at = datetime.now(timezone.utc)
    await db.commit()
    # Entra directo: ya demostró que tiene el enlace y acaba de elegir la
    # clave. Pedirle que la escriba otra vez en el login es un paso que no
    # prueba nada.
    token_jwt = create_access_token(u.id, u.role, u.email)
    return await _session_payload(db, u, token_jwt)
