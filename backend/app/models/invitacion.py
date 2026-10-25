"""La invitación con la que una persona se pone SU propia contraseña.

**El pedido (owner, 2026-10-25):** *«favor valida la forma de asignar claves
que sea igual como app dashboard. yo mando la invitación y ellos generan sus
claves»*.

## Lo que había

Al crear un usuario, la pantalla generaba una contraseña, la mostraba una vez y
el admin la mandaba «por un canal privado». Funciona, pero **la contraseña
existe fuera de la cabeza de su dueño**: queda en el portapapeles, en el
WhatsApp del que la mandó y en el del que la recibió, y nadie la borra. El
texto de la pantalla lo decía sin querer — *«pídale que la cambie cuando
entre»*: un paso que depende de que la persona se acuerde.

## Lo que hay

El sistema crea un enlace de **un solo uso** que vence, el admin lo manda por
donde quiera, y la persona escribe su clave. El servidor nunca la ve, y lo que
viaja por el chat caduca solo.

⚠️ **Se guarda el HASH del token, no el token.** Quien lea esta tabla no puede
entrar con lo que encuentre: lo mismo que se hace con las contraseñas, y por la
misma razón. El token en claro existe una sola vez, en la respuesta del
endpoint que lo crea.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: Cuánto dura una invitación. Una semana alcanza para que alguien la abra
#: después de un fin de semana largo, y es poco para que quede viva en un chat
#: durante meses.
DIAS_DE_VIGENCIA = 7

#: Lo que lleva `password_hash` mientras la persona no haya puesto su clave.
#:
#: ⚠️ **Tiene que ser un valor que `verify_password` NO pueda aceptar jamás.**
#: Esa función parte el hash guardado por `$` y espera cuatro pedazos; con esto
#: revienta y devuelve `False`. No es un hash de una contraseña rara: es un
#: valor que no es un hash. Dejar el campo vacío sería peor — un `""` también
#: falla hoy, pero no lo dice, y el día que alguien cambie el verificador nadie
#: se acuerda de este caso. Blindado por `test_usuario_sin_clave_no_entra`.
SIN_CLAVE = "!sin-clave-todavia"


def nuevo_token() -> tuple[str, str]:
    """Devuelve `(token_en_claro, hash)`. El claro se muestra UNA vez."""
    token = secrets.token_urlsafe(32)
    return token, hash_de_token(token)


def hash_de_token(token: str) -> str:
    """SHA-256 del token. No lleva sal a propósito: el token ya es aleatorio de
    32 bytes, así que no hay diccionario que lo alcance, y sin sal se puede
    buscar la fila por el hash en una sola consulta."""
    return hashlib.sha256(token.encode()).hexdigest()


class InvitacionUsuario(Base):
    """Una invitación emitida para un usuario. Puede haber varias por usuario
    —si se reenvía—; vale la última que siga viva y sin usar."""

    __tablename__ = "user_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: SHA-256 del token. Nunca el token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Cuándo se canjeó. `None` = sigue sin usar.
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    #: Quién la emitió, para poder auditar quién le dio acceso a quién.
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    #: `True` cuando es el alta de un usuario nuevo; `False` cuando es un
    #: reemplazo de clave de alguien que ya entraba. Cambia lo que dice la
    #: pantalla donde la persona la abre, nada más.
    es_alta: Mapped[bool] = mapped_column(Boolean, default=True)

    def vigente(self, ahora: datetime | None = None) -> bool:
        """¿Se puede canjear? Sin usar y sin vencer."""
        if self.used_at is not None:
            return False
        ahora = ahora or datetime.now(timezone.utc)
        vence = self.expires_at
        # Postgres devuelve con zona; SQLite (las pruebas) a veces sin ella.
        # Comparar una fecha con zona contra una sin zona revienta, y lo haría
        # dentro del login — justo donde no se puede.
        if vence.tzinfo is None:
            vence = vence.replace(tzinfo=timezone.utc)
        return vence > ahora

    @staticmethod
    def vencimiento(ahora: datetime | None = None) -> datetime:
        return (ahora or datetime.now(timezone.utc)) + timedelta(days=DIAS_DE_VIGENCIA)

    def __repr__(self) -> str:
        return (f"<Invitacion {self.user_id} "
                f"{'usada' if self.used_at else 'vigente'}>")
