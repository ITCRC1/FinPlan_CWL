"""Formular los conceptos de planilla que en CR son regla, no digitacion.

De los 17 conceptos solo se calculaban 3 (SW, CCSS, aguinaldo). Los otros 14 eran
campos manuales por posicion x mes: con 110 posiciones son 18,480 celdas a mano, y
la pantalla ni siquiera las expone. Resultado: en la practica quedaban en cero y el
costo de planilla salia corto.

Estos 9 se derivan de una tasa o un monto, igual que la CCSS:

    6001 Overtime        = SW x overtime_pct
    6003 Work Holiday    = SW / dias_calendario[mes] x feriados[mes]
    6027 Incentive Bonus = SW x bonus_pct
    6023 Vac. Prov.      = BASE x vacaciones_rate        (CR: 2/52 = 3.846%)
    6026 Severance       = BASE x severance_anual / 12   (CR: cesantia ~5.33%)
    6025 Cafeteria       = FTE x dias_trabajados[mes] x costo_diario_CRC / TC
    6029 Transport       = FTE x monto_mensual_CRC / TC
    6028 Housing         = FTE x monto_mensual_CRC / TC
    6030 Other           = FTE x monto_mensual_CRC / TC

Quedan manuales a proposito, porque son por persona y no por regla:
    6002 Day Off · 6004 Disabilities · 6010 Commissions · 6024 Vac. Taken

Y 6022 Occ. Hazard se deja en cero a proposito: el INS de riesgos del trabajo YA
esta dentro del 26.83% de la CCSS. Cargarlo aparte seria contarlo dos veces.

TODOS los drivers nacen en CERO: mientras no se llenen, ningun numero cambia.

Revision ID: 073
Revises: 072
"""
from alembic import op
import sqlalchemy as sa

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None

# Dias del mes 2027. Se guardan (y no se calculan) porque el usuario puede querer
# usar 30 dias parejos, que es como se liquida en algunas planillas.
CALENDARIO_2027 = "[31,28,31,30,31,30,31,31,30,31,30,31]"
CEROS = "[0,0,0,0,0,0,0,0,0,0,0,0]"

TASAS = [
    ("overtime_pct", "Numeric(7,5)"),
    ("bonus_pct", "Numeric(7,5)"),
    ("vacaciones_rate", "Numeric(7,5)"),
    ("severance_annual_rate", "Numeric(7,5)"),
]
MONTOS = [
    ("cafeteria_daily_crc", "Numeric(14,2)"),
    ("transport_monthly_crc", "Numeric(14,2)"),
    ("housing_monthly_crc", "Numeric(14,2)"),
    ("other_monthly_crc", "Numeric(14,2)"),
]
CALENDARIOS = [
    ("working_days", CEROS),
    ("holidays", CEROS),
    ("calendar_days", CALENDARIO_2027),
]


def upgrade() -> None:
    for col, _ in TASAS:
        op.add_column("payroll_params",
                      sa.Column(col, sa.Numeric(7, 5), nullable=False, server_default="0"))
    for col, _ in MONTOS:
        op.add_column("payroll_params",
                      sa.Column(col, sa.Numeric(14, 2), nullable=False, server_default="0"))
    for col, default in CALENDARIOS:
        op.add_column("payroll_params",
                      sa.Column(col, sa.String(120), nullable=False, server_default=default))


def downgrade() -> None:
    for col, _ in TASAS + MONTOS:
        op.drop_column("payroll_params", col)
    for col, _ in CALENDARIOS:
        op.drop_column("payroll_params", col)
