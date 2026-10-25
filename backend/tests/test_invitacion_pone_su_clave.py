# -*- coding: utf-8 -*-
"""La persona se pone SU contraseña; el servidor nunca la ve.

**El pedido (owner, 2026-10-25):** *«favor valida la forma de asignar claves
que sea igual como app dashboard. yo mando la invitación y ellos generan sus
claves»*.

## Lo que había

Al crear un usuario, la pantalla generaba la contraseña, la mostraba una vez y
el admin la mandaba «por un canal privado». La contraseña quedaba **fuera de la
cabeza de su dueño**: en el portapapeles, en el chat del que la mandó y en el
del que la recibió. El propio texto de la pantalla lo delataba — *«pídale que la
cambie cuando entre»*: un paso que depende de que alguien se acuerde.

## Lo que hay

Un enlace de un solo uso que vence a los 7 días. El admin lo manda por donde
quiera y la persona escribe su clave.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import hash_password, verify_password
from app.models.invitacion import (DIAS_DE_VIGENCIA, InvitacionUsuario,
                                   SIN_CLAVE, hash_de_token, nuevo_token)


# ═══════════════════════════════════════════════════════════════════════════
# Lo que no puede fallar nunca
# ═══════════════════════════════════════════════════════════════════════════
def test_usuario_sin_clave_no_entra():
    """⚠️ La prueba que justifica que `SIN_CLAVE` exista.

    Un usuario recién invitado NO tiene contraseña. Lo que lleve ese campo
    mientras tanto tiene que ser un valor que `verify_password` no pueda
    aceptar **jamás** — si alguna cadena lo hiciera pasar, cada cuenta invitada
    y todavía sin canjear sería una puerta abierta, y no habría nada en
    pantalla que lo dijera.
    """
    for intento in ("", " ", SIN_CLAVE, "!sin-clave-todavia", "password",
                    "admin", "pbkdf2_sha256$1$00$00", "$$$"):
        assert verify_password(intento, SIN_CLAVE) is False, (
            f"{intento!r} abrió una cuenta sin contraseña")


def test_sin_clave_NO_es_un_hash_valido():
    """No es «el hash de una contraseña rara»: es un valor que no es un hash.
    Si fuera un hash de verdad, alguien podría conocer su preimagen."""
    assert "$" not in SIN_CLAVE or SIN_CLAVE.count("$") != 3


def test_se_guarda_el_HASH_del_token_no_el_token():
    """Quien lea la tabla no puede entrar con lo que encuentre — el mismo
    criterio que las contraseñas, y por la misma razón."""
    token, th = nuevo_token()
    assert th != token
    assert len(th) == 64 and all(c in "0123456789abcdef" for c in th)
    assert hash_de_token(token) == th


def test_el_token_es_largo_y_aleatorio():
    """Un token corto se adivina probando. Y dos iguales serían un enlace que
    sirve para dos personas."""
    tokens = {nuevo_token()[0] for _ in range(200)}
    assert len(tokens) == 200, "se repitió un token"
    assert all(len(t) >= 40 for t in tokens)


# ═══════════════════════════════════════════════════════════════════════════
# Cuándo vale una invitación
# ═══════════════════════════════════════════════════════════════════════════
def _inv(**kw) -> InvitacionUsuario:
    base = dict(user_id="u1", token_hash="x" * 64,
                expires_at=InvitacionUsuario.vencimiento(), used_at=None)
    base.update(kw)
    return InvitacionUsuario(**base)


def test_una_invitacion_recien_hecha_vale():
    assert _inv().vigente() is True


def test_una_invitacion_YA_USADA_no_vale():
    """De un solo uso. Si el enlace siguiera abriendo después de canjearse,
    quien lo tenga en el chat podría cambiarle la clave a esa persona."""
    assert _inv(used_at=datetime.now(timezone.utc)).vigente() is False


def test_una_invitacion_VENCIDA_no_vale():
    """Lo que viaja por un chat no puede quedar vivo para siempre."""
    viejo = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert _inv(expires_at=viejo).vigente() is False


def test_vence_a_los_siete_dias():
    v = InvitacionUsuario.vencimiento(datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert v == datetime(2026, 1, 8, tzinfo=timezone.utc)
    assert DIAS_DE_VIGENCIA == 7


def test_una_fecha_SIN_ZONA_no_revienta():
    """⚠️ Postgres devuelve con zona; SQLite a veces sin ella. Comparar una con
    otra tira `TypeError`, y lo haría dentro del canje — justo donde no se
    puede: la persona vería un error 500 al poner su clave."""
    sin_zona = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1)
    assert _inv(expires_at=sin_zona).vigente() is True
    pasado = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    assert _inv(expires_at=pasado).vigente() is False


# ═══════════════════════════════════════════════════════════════════════════
# Las reglas del flujo, leídas del código
# ═══════════════════════════════════════════════════════════════════════════
import inspect  # noqa: E402

from app.api import auth_api  # noqa: E402


@pytest.fixture(scope="module")
def fuente() -> str:
    return inspect.getsource(auth_api)


def test_crear_usuario_YA_NO_recibe_contrasena(fuente):
    """Si el alta siguiera aceptando una clave, el camino viejo quedaría vivo
    al lado del nuevo y alguien lo usaría sin saber que hay otro."""
    cuerpo = fuente[fuente.index("class UserCreate(BaseModel):"):][:300]
    assert "password" not in cuerpo, (
        "el alta no recibe contraseña: la pone su dueño por la invitación")


def test_el_usuario_nuevo_nace_SIN_clave(fuente):
    cuerpo = fuente[fuente.index("async def create_user"):][:1400]
    assert "password_hash=SIN_CLAVE" in cuerpo
    assert "hash_password(body.password)" not in cuerpo


def test_emitir_una_invitacion_NO_revoca_la_clave_vigente(fuente):
    """⚠️ Owner, 2026-10-25, sobre Blake: *«deja que entre con ambos métodos…
    acaba de enviar la clave»*.

    Emitir no puede dejar afuera a alguien que ya estaba entrando. Sólo el
    CANJE reemplaza la contraseña. Si `_emitir_invitacion` tocara
    `password_hash`, mandar una invitación sacaría del sistema a la persona
    hasta que abra el enlace — y nadie lo pidió.
    """
    cuerpo = fuente[fuente.index("async def _emitir_invitacion"):]
    cuerpo = cuerpo[:cuerpo.index("@router")]
    assert "password_hash" not in cuerpo.split('"""')[2], (
        "emitir una invitación no puede tocar la contraseña")


def test_el_CANJE_si_reemplaza_la_clave(fuente):
    """El contrapeso: sin esto el arreglo de arriba se «logra» no escribiendo
    nunca la contraseña nueva."""
    cuerpo = fuente[fuente.index("async def canjear_invitacion"):]
    assert "u.password_hash = hash_password(body.password)" in cuerpo


def test_reenviar_mata_las_invitaciones_ANTERIORES(fuente):
    """Si no, el enlace viejo —que sigue vivo en algún chat— también abre, y
    entonces «reenviar» no revoca nada."""
    cuerpo = fuente[fuente.index("async def _emitir_invitacion"):]
    cuerpo = cuerpo[:cuerpo.index("@router")]
    assert "InvitacionUsuario.used_at.is_(None)" in cuerpo
    assert "p.used_at = ahora" in cuerpo


def test_el_token_se_marca_usado_en_la_MISMA_transaccion(fuente):
    """Marcarlo después de un commit aparte deja una ventana en la que la
    clave ya cambió y el enlace todavía abre."""
    cuerpo = fuente[fuente.index("async def canjear_invitacion"):]
    i_clave = cuerpo.index("u.password_hash = hash_password")
    i_usado = cuerpo.index("inv.used_at =")
    i_commit = cuerpo.index("await db.commit()")
    assert i_clave < i_commit and i_usado < i_commit, (
        "la clave y el canje van en el mismo commit")


def test_el_error_NO_distingue_por_que_fallo(fuente):
    """⚠️ «No existe», «ya se usó» y «venció» dan el mismo 404. Distinguirlos
    le contaría a quien prueba tokens al azar cuál acertó a medias."""
    cuerpo = fuente[fuente.index("async def _invitacion_de"):]
    cuerpo = cuerpo[:cuerpo.index("@router.get")]
    assert cuerpo.count("invitacion.no_valida") == 1
    assert "vencida" not in cuerpo and "usada" not in cuerpo.replace("ya se usó", "")


def test_ver_invitacion_NO_filtra_de_mas(fuente):
    """Esto lo abre cualquiera que tenga el enlace. Devuelve el correo —la
    persona tiene que ver a qué cuenta le pone clave— y nada más."""
    cuerpo = fuente[fuente.index("async def ver_invitacion"):]
    cuerpo = cuerpo[:cuerpo.index("class ClaveNueva")]
    devuelve = cuerpo[cuerpo.index("return {"):]
    assert '"role"' not in devuelve and "u.role" not in devuelve
    assert "created_by" not in devuelve


def test_una_cuenta_DESACTIVADA_no_se_puede_canjear(fuente):
    """Desactivar a alguien tiene que cerrarle también la invitación que le
    quedó dando vueltas."""
    for f in ("ver_invitacion", "canjear_invitacion"):
        cuerpo = fuente[fuente.index(f"async def {f}"):][:1200]
        assert "not u.active" in cuerpo, f"{f} no mira si la cuenta está activa"


def test_la_clave_nueva_tiene_largo_minimo(fuente):
    cuerpo = fuente[fuente.index("async def canjear_invitacion"):][:600]
    assert "LARGO_MINIMO" in cuerpo
    assert auth_api.LARGO_MINIMO >= 8


def test_el_enlace_sale_de_APP_URL_y_no_se_adivina(fuente):
    """Adivinar un dominio sería mandarle a la gente un enlace que no abre."""
    cuerpo = fuente[fuente.index("def _url_invitacion"):][:900]
    assert "APP_URL" in cuerpo
    assert "/invitacion/" in cuerpo


# ═══════════════════════════════════════════════════════════════════════════
# El flujo COMPLETO, contra una base de verdad
#
# Lo de arriba lee el código; esto lo ejecuta. Es la diferencia entre «la
# función dice que no toca la contraseña» y «la contraseña sigue sirviendo
# después de mandar la invitación».
# ═══════════════════════════════════════════════════════════════════════════
import asyncio  # noqa: E402

import pytest_asyncio  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.db import Base  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture()
def cliente(monkeypatch):
    """Un backend de verdad sobre SQLite en memoria, con un admin logueado."""
    motor = create_async_engine("sqlite+aiosqlite:///:memory:")
    Sesion = async_sessionmaker(motor, expire_on_commit=False)

    async def _crear():
        async with motor.begin() as con:
            # Las tablas que toca este flujo: montar el esquema entero trae
            # medio sistema y tarda. `hotels` entra porque el login resuelve
            # con ella el idioma de la sesión — sin esa tabla el canje devuelve
            # 500 justo en el paso final, que es como lo descubrí.
            await con.run_sync(Base.metadata.create_all, tables=[
                Base.metadata.tables["users"],
                Base.metadata.tables["user_invitations"],
                Base.metadata.tables["hotels"]])
        async with Sesion() as db:
            admin = User(id="admin-1", email="admin@cwl.com", name="Admin",
                         password_hash=hash_password("admin12345"),
                         role="admin", active=True)
            # Blake ya entraba con su clave. Owner, 2026-10-25: *«deja que
            # entre con ambos métodos»*.
            blake = User(id="blake-1", email="blake@seedcostarica.com",
                         name="Blake D",
                         password_hash=hash_password("zGmUZptsP6p5pi"),
                         role="collaborator", active=True)
            from app.models.hotel import Hotel
            db.add(Hotel(id="CWL", name="Corcovado Wilderness Lodge",
                         short_name="CWL", rooms=30, active=True))
            db.add_all([admin, blake])
            await db.commit()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_crear())

    app = FastAPI()
    app.include_router(auth_api.router, prefix="/api")

    async def _db():
        async with Sesion() as s:
            yield s

    async def _admin():
        async with Sesion() as s:
            return await s.get(User, "admin-1")

    app.dependency_overrides[auth_api.get_db] = _db
    app.dependency_overrides[auth_api.get_current_admin] = _admin
    monkeypatch.setenv("APP_URL", "https://finplan-cwl.up.railway.app")
    c = TestClient(app)
    c.Sesion = Sesion       # type: ignore[attr-defined]
    return c


def _invitar_nuevo(c, email="nuevo@cwl.com"):
    r = c.post("/api/auth/users", json={"email": email, "name": "Nuevo",
                                        "role": "collaborator"})
    assert r.status_code == 200, r.text
    return r.json()


def test_el_alta_devuelve_un_ENLACE_y_no_una_contrasena(cliente):
    """Lo que el admin copia y manda. Owner: *«yo mando la invitación»*."""
    d = _invitar_nuevo(cliente)
    assert "password" not in str(d).lower() or "invitacion" in d
    inv = d["invitacion"]
    assert inv["url"].startswith("https://finplan-cwl.up.railway.app/invitacion/")
    assert inv["dias"] == 7


def test_la_cuenta_nueva_NO_entra_hasta_que_canjea(cliente):
    """⚠️ La ventana que no puede existir: invitada y ya adentro."""
    _invitar_nuevo(cliente)
    for intento in ("", "password", "12345678", SIN_CLAVE):
        r = cliente.post("/api/auth/login",
                         json={"email": "nuevo@cwl.com", "password": intento})
        assert r.status_code != 200, f"entró con {intento!r}"


def test_canjear_pone_la_clave_y_deja_entrar(cliente):
    inv = _invitar_nuevo(cliente)["invitacion"]
    tok = inv["url"].rsplit("/", 1)[-1]

    v = cliente.get(f"/api/auth/invitacion/{tok}")
    assert v.status_code == 200, v.text
    assert v.json()["email"] == "nuevo@cwl.com"

    r = cliente.post(f"/api/auth/invitacion/{tok}",
                     json={"password": "miClaveNueva1"})
    assert r.status_code == 200, r.text

    e = cliente.post("/api/auth/login",
                     json={"email": "nuevo@cwl.com", "password": "miClaveNueva1"})
    assert e.status_code == 200, e.text


def test_el_enlace_sirve_UNA_sola_vez(cliente):
    """Si siguiera abriendo, quien lo tenga en el chat podría cambiarle la
    clave a esa persona después."""
    tok = _invitar_nuevo(cliente)["invitacion"]["url"].rsplit("/", 1)[-1]
    assert cliente.post(f"/api/auth/invitacion/{tok}",
                        json={"password": "primera12345"}).status_code == 200
    r = cliente.post(f"/api/auth/invitacion/{tok}",
                     json={"password": "segunda12345"})
    assert r.status_code == 404
    # y la clave quedó en la PRIMERA
    assert cliente.post("/api/auth/login", json={
        "email": "nuevo@cwl.com", "password": "primera12345"}).status_code == 200


def test_invitar_a_BLAKE_no_le_quita_la_clave_que_ya_usa(cliente):
    """⚠️ Owner, 2026-10-25: *«al usuario Blake, deja que entre con ambos
    métodos… es el owner y acaba de enviar la clave»*.

    Emitir la invitación no puede dejarlo afuera. Las dos puertas abiertas
    hasta que él decida canjear.
    """
    r = cliente.post("/api/auth/users/blake-1/invitacion")
    assert r.status_code == 200, r.text
    assert r.json()["invitacion"]["url"]

    # la clave que ya tenía SIGUE sirviendo
    e = cliente.post("/api/auth/login", json={
        "email": "blake@seedcostarica.com", "password": "zGmUZptsP6p5pi"})
    assert e.status_code == 200, "la invitación le cerró la puerta que ya usaba"

    # y el enlace también
    tok = r.json()["invitacion"]["url"].rsplit("/", 1)[-1]
    assert cliente.get(f"/api/auth/invitacion/{tok}").status_code == 200


def test_reenviar_mata_el_enlace_anterior(cliente):
    """El viejo sigue vivo en algún chat."""
    t1 = cliente.post("/api/auth/users/blake-1/invitacion"
                      ).json()["invitacion"]["url"].rsplit("/", 1)[-1]
    t2 = cliente.post("/api/auth/users/blake-1/invitacion"
                      ).json()["invitacion"]["url"].rsplit("/", 1)[-1]
    assert t1 != t2
    assert cliente.get(f"/api/auth/invitacion/{t1}").status_code == 404
    assert cliente.get(f"/api/auth/invitacion/{t2}").status_code == 200


def test_un_token_inventado_no_abre(cliente):
    assert cliente.get("/api/auth/invitacion/loquesea").status_code == 404
    assert cliente.post("/api/auth/invitacion/loquesea",
                        json={"password": "123456789"}).status_code == 404


def test_una_clave_corta_se_rechaza(cliente):
    tok = _invitar_nuevo(cliente)["invitacion"]["url"].rsplit("/", 1)[-1]
    r = cliente.post(f"/api/auth/invitacion/{tok}", json={"password": "corta"})
    assert r.status_code == 422
    # y el enlace NO se quemó: la persona puede volver a intentar
    assert cliente.get(f"/api/auth/invitacion/{tok}").status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# La pantalla
# ═══════════════════════════════════════════════════════════════════════════
from tests._rutas import FRONT, sin_comentarios  # noqa: E402

USERS = FRONT / "app" / "admin" / "users" / "page.tsx"
INVITA = FRONT / "app" / "invitacion" / "[token]" / "page.tsx"


def test_la_pantalla_de_usuarios_YA_NO_genera_contrasenas():
    """⚠️ Mientras el generador siga ahí, el camino viejo queda vivo al lado
    del nuevo y alguien lo usa sin saber que hay otro."""
    t = sin_comentarios(USERS.read_text(encoding="utf-8"))
    assert "generarClave" not in t
    assert "getRandomValues" not in t, (
        "ninguna contraseña se genera en el navegador del admin")


def test_la_pantalla_entrega_un_ENLACE():
    t = USERS.read_text(encoding="utf-8")
    assert "invitarDeNuevo" in t and "entrega.inv" in t
    assert "enlaceCompleto" in t


def test_el_enlace_relativo_se_completa_con_el_origen():
    """⚠️ El backend devuelve la ruta sola si no tiene `APP_URL`. Inventar un
    dominio sería mandarle a la gente un enlace que no abre."""
    t = USERS.read_text(encoding="utf-8")
    cuerpo = t[t.index("function enlaceCompleto"):][:400]
    assert "window.location.origin" in cuerpo


def test_la_pagina_de_invitacion_existe_y_pide_la_clave_dos_veces():
    """Escribirla mal una vez y enterarse en el login es perder el enlace: es
    de un solo uso."""
    t = INVITA.read_text(encoding="utf-8")
    assert "canjearInvitacion" in t
    assert "repetida" in t and "noCoinciden" in t


def test_la_pagina_avisa_si_el_enlace_murio_MIENTRAS_llenaba():
    """Se pudo reenviar otro, o vencer, entre que abrió y envió. Dejarlo
    reintentando contra un 404 es dejarlo trabado sin explicación."""
    t = sin_comentarios(INVITA.read_text(encoding="utf-8"))
    cuerpo = t[t.index("const enviar"):][:1400]
    assert '/404/.test(m)' in cuerpo
    assert 'setEstado("invalida")' in cuerpo


def test_la_pagina_muestra_A_QUE_CUENTA_le_pone_clave():
    """Alguien con dos correos no sabe cuál está configurando."""
    assert "inv.email" in INVITA.read_text(encoding="utf-8")


@pytest.mark.parametrize("archivo", ["es.json", "en.json"])
def test_los_textos_estan_en_los_dos_idiomas(archivo):
    import json
    d = json.loads((FRONT / "messages" / archivo).read_text(encoding="utf-8"))
    for k in ("invite", "inviteConfirm", "inviteFor", "inviteNote"):
        assert d["users"].get(k, "").strip(), f"{archivo}: falta users.{k}"
    for k in ("introAlta", "clave", "repetir", "guardar", "invalidaTitulo",
              "noCoinciden", "privacidad"):
        assert d["invitacion"].get(k, "").strip(), f"{archivo}: falta invitacion.{k}"


@pytest.mark.parametrize("archivo", ["es.json", "en.json"])
def test_los_textos_del_camino_VIEJO_se_retiraron(archivo):
    """Un texto que dice «entréguele esta contraseña» describiendo un flujo que
    ya no existe es peor que no tener texto."""
    import json
    d = json.loads((FRONT / "messages" / archivo).read_text(encoding="utf-8"))
    for k in ("resetPass", "resetConfirm", "passwordFor", "handoffNote"):
        assert k not in d["users"], f"{archivo}: quedó users.{k} del flujo viejo"
