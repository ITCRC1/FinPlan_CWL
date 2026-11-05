# -*- coding: utf-8 -*-
"""El Deposit Ledger: la plata de huespedes que el hotel tiene en custodia.

Owner, 2026-11-04: *«puedes crearme un sub tab llamado Deposit Analysis. Que
revisa el reporte tal como esta en el xml y despues sub tab que analice por mes
arrival... yo quiero seguir el tracking. que lleve la version para comparar una
subida a otra y que vea cuales salieron y cuales entraron.»*

## Que guarda

El Deposit Ledger de Opera lista, a un corte, cada reserva futura con deposito
cobrado. El primer archivo (4-nov-2026) trae 165 reservas y $923,058.91 contra
llegadas que van de noviembre 2026 a octubre 2028. Es plata recibida que
todavia no es ingreso: un pasivo hasta que el huesped se hospede.

## Por que dos tablas y no una

`deposit_loads` es el corte —el archivo— y `deposit_entries` sus reservas.

⚠️ **Cada corte guarda su copia completa, no se reemplaza por reserva.** Es lo
contrario de `pacing_reservations`, donde la fila mas reciente manda y la vieja
se pisa. Aca el dato viejo es el que tiene valor: sin el no hay contra que
comparar, y comparar es lo que se pidio. Un ledger son ~165 filas; cincuenta
cortes son 8.250 — no hay nada que ahorrar.

⚠️ **`(hotel_id, as_of)` es unico.** Un ledger del 4 de noviembre es *el*
ledger del 4 de noviembre; subirlo otra vez reemplaza. Si se permitieran dos,
la comparacion tendria que preguntar cual, y eso no es lo que se quiere elegir.

⚠️ **El monto se guarda NEGATIVO, como viene.** En Opera el deposito es un
credito a favor del huesped (`TOTAL_PAID_AMT = -5019.76`). La pestaña que
enseña «el reporte tal como esta en el XML» tiene que mostrar ese signo. El
motor (`app/engine/deposits.py`) es el unico que lo da vuelta para analizar.

Revision ID: 160
Revises: 159
"""
import sqlalchemy as sa
from alembic import op

revision = "160"
down_revision = "159"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deposit_loads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("as_of", sa.String(10), nullable=False, index=True),
        sa.Column("file_name", sa.String(255)),
        sa.Column("cuenta", sa.Integer, server_default="0"),
        sa.Column("total_amt", sa.Numeric(16, 2), server_default="0"),
        sa.Column("min_arrival", sa.String(10)),
        sa.Column("max_arrival", sa.String(10)),
        sa.Column("nota", sa.String(500)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("uploaded_by", sa.String(255)),
        sa.UniqueConstraint("hotel_id", "as_of", name="uq_deposit_load_hotel_asof"),
    )
    op.create_table(
        "deposit_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("load_id", sa.String(36), nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("resv_name_id", sa.String(40), nullable=False, index=True),
        sa.Column("confirmation_no", sa.String(40)),
        sa.Column("name", sa.String(120)),
        sa.Column("sname", sa.String(120)),
        sa.Column("room", sa.String(20)),
        sa.Column("arrival", sa.String(10), index=True),
        sa.Column("departure", sa.String(10)),
        sa.Column("last_date", sa.String(10)),
        sa.Column("resv_status", sa.String(10), index=True),
        sa.Column("guarantee_code", sa.String(10)),
        sa.Column("external_reference", sa.String(80)),
        sa.Column("total_paid_amt", sa.Numeric(14, 2), server_default="0"),
        sa.Column("nights", sa.Integer, server_default="0"),
        sa.UniqueConstraint("load_id", "resv_name_id", name="uq_deposit_load_resv"),
    )


def downgrade() -> None:
    op.drop_table("deposit_entries")
    op.drop_table("deposit_loads")
