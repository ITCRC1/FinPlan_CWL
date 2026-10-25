# -*- coding: utf-8 -*-
"""La persona se pone SU clave: tabla de invitaciones de un solo uso.

Owner, 2026-10-25: *«yo mando la invitacion y ellos generan sus claves»*.

Antes, al crear un usuario la pantalla generaba una contrasena, la mostraba una
vez y el admin la mandaba «por un canal privado». La contrasena quedaba fuera
de la cabeza de su dueno: en el portapapeles, en el chat del que la mando y en
el del que la recibio.

Ahora el sistema emite un enlace de un solo uso que vence a los 7 dias; el
admin lo manda por donde quiera y la persona escribe su clave. El servidor
nunca la ve.

⚠️ **Los 12 usuarios que ya existen NO se tocan** (decision del owner). Siguen
entrando con su clave; el flujo nuevo aplica a los que se inviten de ahora en
adelante.

⚠️ **Emitir una invitacion NO revoca la clave vigente.** Owner, el mismo dia,
sobre Blake: *«deja que entre con ambos metodos... acaba de enviar la clave»*.
Solo CANJEARLA la reemplaza. Por eso esta tabla no toca `users` para nada.
"""
import sqlalchemy as sa
from alembic import op

revision = "158"
down_revision = "157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # ⚠️ El HASH del token, nunca el token: quien lea esta tabla no puede
        # entrar con lo que encuentre. Mismo criterio que las contrasenas.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("es_alta", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_user_invitations_user_id", "user_invitations", ["user_id"])
    # Unico: el canje busca por el hash, y dos filas con el mismo token seria
    # un token que sirve dos veces.
    op.create_index("ix_user_invitations_token_hash", "user_invitations",
                    ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_invitations_token_hash", table_name="user_invitations")
    op.drop_index("ix_user_invitations_user_id", table_name="user_invitations")
    op.drop_table("user_invitations")
