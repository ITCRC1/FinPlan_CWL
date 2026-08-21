"""idioma: default por propiedad + preferencia por usuario

Dos perillas, las dos que pidió el owner (decisión D1): el idioma se elige al
**provisionar** la propiedad, y además cada usuario puede cambiarlo con un
botón.

* `hotels.default_locale VARCHAR(5) NOT NULL DEFAULT 'es'` — con qué idioma abre
  la propiedad.
* `users.locale VARCHAR(5) NULL` — preferencia personal. **Nullable a
  propósito:** `NULL` = «usá el del hotel», que no es lo mismo que «elegí
  español». Sin esa distinción, mover el default de la propiedad no le llegaría
  nunca a quien ya tuviera un valor guardado.

La resolución (`usuario → hotel → 'es'`) vive en UN solo lugar,
`backend/app/i18n.py`.

Revision ID: 096
Revises: 095
"""
from alembic import op
import sqlalchemy as sa

revision = "096"
down_revision = "095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hotels", sa.Column(
        "default_locale", sa.String(length=5), nullable=False, server_default="es"))
    op.add_column("users", sa.Column(
        "locale", sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "locale")
    op.drop_column("hotels", "default_locale")
