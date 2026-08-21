"""Cash flow — de dónde salió la caja inicial

El botón de anclar dejaba el monto pero no de dónde venía. $702,799.20 puede
ser el cierre del Forecast 2026, el del Budget 2027 o algo escrito a mano, y al
recargar la página no quedaba rastro. Se guardan el escenario fuente, su nombre
y el momento — el nombre aparte del id porque el escenario puede cambiar de
versión o borrarse, y ahí el número quedaría huérfano justo cuando alguien
pregunte de dónde salió.

Todo nullable: los escenarios que ya tienen caja inicial escrita a mano quedan
como están, sin fuente, que es la verdad.

Revision ID: 082
Revises: 081
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "082"
down_revision: Union[str, None] = "081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cashflow_params", sa.Column("anchor_scenario_id", sa.String(36), nullable=True))
    op.add_column("cashflow_params", sa.Column("anchor_label", sa.String(120), nullable=True))
    op.add_column("cashflow_params", sa.Column("anchored_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("cashflow_params", "anchored_at")
    op.drop_column("cashflow_params", "anchor_label")
    op.drop_column("cashflow_params", "anchor_scenario_id")
