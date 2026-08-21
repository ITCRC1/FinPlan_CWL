# -*- coding: utf-8 -*-
"""El tema visual, guardado por usuario.

**El pedido (owner, 2026-08-19).** «Me gusta el Lino… ¿es posible que este set
de colores estén en el admin y puedan ser escogibles?»

El fondo casi negro cansa en sesiones largas, y la causa no era el modo oscuro
sino tres cosas sumadas: el fondo al 9% de luminosidad, la barra superior aún
más oscura, y un azul de marca muy saturado que hace vibrar los bordes. Hay
cuatro paletas completas en `frontend/app/globals.css`; esta columna guarda cuál
eligió cada quien.

**Por qué en `users` y no en `hotels`.** El idioma es del TENANT —una propiedad
opera en español o en inglés y eso no es preferencia de nadie— pero el fondo que
cansa la vista es de la PERSONA. Dos analistas en la misma propiedad pueden
querer distinto y ninguno de los dos está equivocado.

**Nullable a propósito**, igual que `users.locale`: `NULL` significa «usá el que
viene por defecto», que NO es lo mismo que «elegí Lino». Sin esa distinción, el
día que cambie el default no le llegaría a quien ya tenga un valor guardado.
"""
import sqlalchemy as sa
from alembic import op

revision = "129"
down_revision = "128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tema", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tema")
