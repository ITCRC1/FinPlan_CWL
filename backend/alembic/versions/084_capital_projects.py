"""detalle de proyectos de capital por área y mes

Revision ID: 084
Revises: 083
"""
from alembic import op
import sqlalchemy as sa

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


def upgrade() -> None:
    op.create_table(
        "capital_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default="CWL"),
        sa.Column("area", sa.String(120), nullable=False, server_default=""),
        sa.Column("name", sa.String(250), nullable=False, server_default=""),
        sa.Column("notes", sa.String(300), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        *[sa.Column(m, sa.Numeric(14, 4), nullable=False, server_default="0") for m in MESES],
    )
    op.create_index("ix_capital_projects_scenario_id", "capital_projects", ["scenario_id"])
    op.create_index("ix_capital_projects_hotel_id", "capital_projects", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_capital_projects_hotel_id", table_name="capital_projects")
    op.drop_index("ix_capital_projects_scenario_id", table_name="capital_projects")
    op.drop_table("capital_projects")
