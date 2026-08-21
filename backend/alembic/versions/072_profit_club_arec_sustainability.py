"""Club, Area Recreativa y Sustainability no llegaban al resultado.

OPERATING_PROFIT = SUM(PROFIT_*), pero faltaban dos lineas de profit y una
tercera apuntaba a la cuenta equivocada:

  - No existia PROFIT_CLUB ni PROFIT_AREC. REV_CLUB/OPEX_CLUB y REV_AREC/OPEX_AREC
    alimentaban los totales de ingreso y gasto pero nunca entraban al GOP ni a
    nada debajo. Medido en Budget Working 2027: $263,340 de planilla del Club
    inflaban la utilidad porque el gasto no se restaba.

  - PROFIT_SUSTAINABILITY estaba definida como "REV_MISC_OTHER - OPEX_MISCELLANEOUS",
    exactamente la misma formula que PROFIT_MISC_OTHER. Dos efectos: el ingreso real
    del Sustainability Fee (REV_SUSTAINABILITY, $251,082) no entraba al resultado, y
    en cuanto alguien cargue REV_MISC_OTHER se contaria dos veces.

Los dos errores casi se cancelaban ($263,340 - $251,082 = $12,258), que es por lo
que el descuadre paso desapercibido: el GOP reportado no era ingresos - gastos.

El vocabulario canonico del motor (pl_engine.CANON_ALIASES) ya contemplaba
PROFIT_CLUB y PROFIT_AREC; solo faltaban en report_line_config.

Revision ID: 072
Revises: 071
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"
SECTION = "OPERATING PROFIT"
PARENT = "SEC_OPERATING_PROFIT"

# display_order 61 y 62 estan libres entre PROFIT_MISC_OTHER (60) y
# OPERATING_PROFIT (64): las lineas se evaluan en orden, asi que estas quedan
# calculadas antes de que SUM(PROFIT_*) las recoja.
NUEVAS = [
    (61, "PROFIT_CLUB", "Club Madresal", "REV_CLUB - OPEX_CLUB"),
    (62, "PROFIT_AREC", "Area Recreativa", "REV_AREC - OPEX_AREC"),
]
SUSTAINABILITY_NUEVA = "REV_SUSTAINABILITY"
SUSTAINABILITY_VIEJA = "REV_MISC_OTHER - OPEX_MISCELLANEOUS"


def upgrade() -> None:
    con = op.get_bind()
    for orden, code, nombre, formula in NUEVAS:
        existe = con.execute(
            sa.text("SELECT 1 FROM report_line_config WHERE line_code=:c"),
            {"c": code},
        ).first()
        if existe:
            con.execute(
                sa.text("""UPDATE report_line_config
                           SET calculation_logic=:f, line_type='CALCULATED', active=true
                           WHERE line_code=:c"""),
                {"c": code, "f": formula},
            )
            continue
        con.execute(
            sa.text("""INSERT INTO report_line_config
                       (id, report_id, display_order, line_code, section, line_name,
                        line_type, parent_line_code, calculation_logic, format_hint, active)
                       VALUES (:id, :rid, :ord, :c, :sec, :n, 'CALCULATED', :p, :f,
                               'currency/number', true)"""),
            {"id": str(uuid.uuid4()), "rid": REPORT_ID, "ord": orden, "c": code,
             "sec": SECTION, "n": nombre, "p": PARENT, "f": formula},
        )

    # El Sustainability Fee vive en REV_SUSTAINABILITY, no en REV_MISC_OTHER.
    # PROFIT_MISC_OTHER se queda con la formula de misceláneos, que sí es la suya.
    con.execute(
        sa.text("""UPDATE report_line_config SET calculation_logic=:nueva
                   WHERE line_code='PROFIT_SUSTAINABILITY'"""),
        {"nueva": SUSTAINABILITY_NUEVA},
    )


def downgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("""DELETE FROM report_line_config
                           WHERE line_code IN ('PROFIT_CLUB','PROFIT_AREC')"""))
    con.execute(
        sa.text("""UPDATE report_line_config SET calculation_logic=:vieja
                   WHERE line_code='PROFIT_SUSTAINABILITY'"""),
        {"vieja": SUSTAINABILITY_VIEJA},
    )
