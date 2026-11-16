"""Acceso desde Claude: la casilla del usuario y las tablas del OAuth del conector.

Owner, 2026-11-16: «quiero que mi jefe haga consultas directas a Claude desde su
computadora sin bajar nada» → conector de claude.ai a FinPlan en vivo, de solo
lectura, con la cuenta de FinPlan de cada persona. «1- sí dale [casilla], 2- ok,
construye».

Solo agrega: una columna que nace en FALSE (nadie gana acceso por la migración)
y cuatro tablas nuevas. No toca datos existentes.

Revision ID: 164
Revises: 163
"""
import sqlalchemy as sa
from alembic import op

revision = "164"
down_revision = "163"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("acceso_claude", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))
    # Qué versiones puede MODIFICAR Claude. Nace en false para todas; la única que
    # se marca es la que el owner creó para eso: «he creado la versión Budget
    # Draft1-PAN para que si él le pide a Claude que cree el budget lo haga».
    op.add_column("scenarios", sa.Column("claude_puede_editar", sa.Boolean(), nullable=False,
                                         server_default=sa.false()))
    op.execute("UPDATE scenarios SET claude_puede_editar = true "
               "WHERE type = 'BUDGET' AND year = 2027 AND version = 'Draft1-PAN'")
    op.create_table(
        "claude_oauth_clientes",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("nombre", sa.String(200), nullable=False, server_default=""),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "claude_oauth_codigos",
        sa.Column("codigo_hash", sa.String(64), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(200), nullable=False, server_default=""),
        sa.Column("vence", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "claude_oauth_refresh",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("scope", sa.String(200), nullable=False, server_default=""),
        sa.Column("vence", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "claude_consultas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("email", sa.String(160), nullable=False, server_default=""),
        sa.Column("herramienta", sa.String(60), nullable=False),
        sa.Column("argumentos", sa.JSON(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )


def downgrade():
    op.drop_table("claude_consultas")
    op.drop_table("claude_oauth_refresh")
    op.drop_table("claude_oauth_codigos")
    op.drop_table("claude_oauth_clientes")
    op.drop_column("scenarios", "claude_puede_editar")
    op.drop_column("users", "acceso_claude")
