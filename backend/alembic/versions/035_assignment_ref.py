"""Section assignment: ref (detalle por departamento) — Fase 3

Revision ID: 035
Revises: 034
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("section_assignments",
                  sa.Column("ref", sa.String(40), server_default=""))
    # la unique pasa de (scenario, section) a (scenario, section, ref)
    op.drop_constraint("uq_section_assignment", "section_assignments", type_="unique")
    op.create_unique_constraint(
        "uq_section_assignment", "section_assignments", ["scenario_id", "section", "ref"])


def downgrade() -> None:
    op.drop_constraint("uq_section_assignment", "section_assignments", type_="unique")
    op.create_unique_constraint(
        "uq_section_assignment", "section_assignments", ["scenario_id", "section"])
    op.drop_column("section_assignments", "ref")
