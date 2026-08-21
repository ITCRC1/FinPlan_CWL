"""Auth API — login, bootstrap del primer admin, gestión de usuarios.

Fase 0 paso A: existe el sistema de usuarios pero los endpoints de datos NO
exigen token todavía (eso es el paso C). Acá ya se puede crear el admin y loguear.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.i18n import LOCALES, normalize_locale, resolve_locale
from app.temas import TEMAS, TEMA_POR_DEFECTO
from app.models.hotel import Hotel
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
    password: str
    name: str = ""
    role: str = "collaborator"


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
    if len(body.password) < 8:
        raise ErrorApi(422, "clave.muy_corta")
    exists = (await db.execute(
        select(User).where(User.email == str(body.email).lower())
    )).scalar_one_or_none()
    if exists:
        raise ErrorApi(409, "usuario.email_duplicado")
    user = User(email=str(body.email).lower(), name=body.name or str(body.email),
                password_hash=hash_password(body.password), role=body.role, active=True)
    db.add(user)
    await db.commit()
    return _user_dict(user)


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
