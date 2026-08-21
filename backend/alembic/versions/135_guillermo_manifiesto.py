# -*- coding: utf-8 -*-
"""El manifiesto de Guillermo aprende a verificarse (D-1 del owner).

El owner definió qué se espera (2026-08-20):

* XML de **Operations** y **Marketing** — todos los días.
* **Actuales** (GL) — una vez al mes.
* **Balance Sheet** — una vez al mes.

`guillermo_expected_reports` nació orientada a ARCHIVOS (un glob y un formato),
porque así lo describía el spec. Pero lo que el owner necesita saber no es «¿me
llegó un archivo?» sino **«¿tengo el dato del período que ya debería estar?»** —
y eso se puede contestar sobre las tablas de destino, incluso hacia atrás, sin
esperar a que empiece a haber historial de subidas.

Esta migración agrega la columna que dice **cómo se verifica** cada reporte.

⚠️ **Son dos verificaciones distintas y hay que saber cuál se está mirando:**

* `cobertura` — mira hasta qué período hay dato en la tabla de destino. Funciona
  **retroactivamente**: contesta desde hoy sobre lo que pasó antes.
* `ultima_subida` — mira `import_files`, que empezó a registrar el 2026-08-20.
  Para los XML diarios es la única forma correcta (un XML de reservas es a
  futuro: «hasta qué mes hay dato» no dice si se subió hoy), pero **no puede
  hablar de antes de esa fecha**. Decirlo es parte de la respuesta.

Aditiva y reversible.
"""
import sqlalchemy as sa
from alembic import op

revision = "135"
down_revision = "134"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `cobertura` | `ultima_subida` | vacío = no se verifica todavía
    op.add_column("guillermo_expected_reports",
                  sa.Column("verifica", sa.String(20), nullable=False,
                            server_default=""))
    # La tabla de destino (para `cobertura`) o el trozo de ruta del endpoint
    # (para `ultima_subida`).
    op.add_column("guillermo_expected_reports",
                  sa.Column("objetivo", sa.String(80), nullable=False,
                            server_default=""))
    # Cuántos días de atraso se toleran antes de reclamar. Un mensual que se
    # cierra el día 10 no es un atraso el día 2.
    op.add_column("guillermo_expected_reports",
                  sa.Column("gracia_dias", sa.Integer, nullable=False,
                            server_default="0"))


def downgrade() -> None:
    op.drop_column("guillermo_expected_reports", "gracia_dias")
    op.drop_column("guillermo_expected_reports", "objetivo")
    op.drop_column("guillermo_expected_reports", "verifica")
