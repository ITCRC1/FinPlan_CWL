"""el Club tiene TRES fuentes de ingreso, una por cuenta — no una con un «otros»

El owner pasó las tres líneas del Club Madresal tal como las lleva el catálogo:

    4500  Ingreso Madresal Club    ← la cuota de acceso (sale del driver)
    4501  Actividad fin de año     ← se digita
    4502  Visitantes               ← se digita

La versión anterior tenía UNA línea de Club y un `otros_usd` anónimo colgando
del driver. Funcionaba para el total, pero borraba de dónde venía la plata: el
presupuesto hablaba de «club» donde el mayor tiene tres renglones con nombre y
cuenta, así que compararlos era a ojo.

**Lo que esto NO hace todavía:** el reporte P&L Full Detail desglosa el ingreso
por cuenta solo en los escenarios importados; los de checkbook (los Budget 2027)
no tienen `revenue_account_entries` y ahí el ingreso sigue saliendo a nivel de
línea. Es el hueco conocido de la Fase 2. Esto deja el dato listo —cada línea ya
sabe su cuenta— pero el reporte todavía no lo usa.

**Los nombres no se inventaron acá.** Ya estaban en `account_mapping` para el
departamento 260, con esos tres destinos a `REV_CLUB`. Esta migración solo hace
que el checkbook los tenga; hay una prueba que compara los rótulos contra
`mapping_pl.json` y falla si alguien los separa.

**Cuidado al leer el código de cuenta solo:** 4500/4501/4502 los comparten Club
Madresal, INNOCEANA y Claro Huerta, cada uno con su nombre y su propio destino
en el P&L. Lo que identifica la línea es el par (departamento, cuenta). Por eso
la hoja del owner mostraba «Ingreso Innoceana #3» al lado de la 4502: el número
sin el departamento no alcanza.

Las tres caen en `REV_CLUB`, igual que Food + Beverage + Misc caen en `REV_FB`
(`revenue_seed_from_lines` suma, no pisa), así que el total del P&L no cambia
por partir la línea.

`club_fee_budgets` estaba vacía en producción al momento de migrar, así que
partir `otros_usd` en dos no reparte plata de nadie: si hubiera datos, todo lo
que estaba en «otros» se va a «actividad», que es de donde salió el nombre.

Revision ID: 100
Revises: 099
"""
from alembic import op
import sqlalchemy as sa

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("club_fee_budgets", sa.Column(
        "actividad_usd", sa.Numeric(14, 4), nullable=False, server_default="0"))
    op.add_column("club_fee_budgets", sa.Column(
        "visitantes_usd", sa.Numeric(14, 4), nullable=False, server_default="0"))
    # Lo que estuviera en el «otros» anónimo era, por su propia descripción, la
    # actividad de fin de año. No se inventa un reparto entre las dos nuevas.
    op.execute("UPDATE club_fee_budgets SET actividad_usd = otros_usd")
    op.drop_column("club_fee_budgets", "otros_usd")


def downgrade() -> None:
    op.add_column("club_fee_budgets", sa.Column(
        "otros_usd", sa.Numeric(14, 4), nullable=False, server_default="0"))
    op.execute("UPDATE club_fee_budgets SET otros_usd = actividad_usd + visitantes_usd")
    op.drop_column("club_fee_budgets", "visitantes_usd")
    op.drop_column("club_fee_budgets", "actividad_usd")
