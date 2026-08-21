# -*- coding: utf-8 -*-
"""Le devuelve al `0162` la regla de la `5301`: el costo de huéspedes de lavandería.

## Qué se rompió

La migración **114** («el `0162` es solo ingreso») le sacó al `0162` sus trece
reglas de gasto. Doce estaban bien sacadas. La decimotercera, la `5301`, no:
**es el destino de un asiento que escribe el motor**.

El reparto de lavandería parte el costo del `0161` en tres y el tercer pedazo —
los kilos de HUÉSPED, o sea el servicio que se le vendió a un tercero— lo manda
al `0162` en la cuenta `5301`, para que el ingreso del servicio y su costo vivan
en el mismo departamento y el `0161` netee a cero
(`calculate_laundry_distribution`, `guest_dept="0162"`).

Sin la regla, esos **$12.257,04** dejaron de resolver por `exact` y pasaron a
resolver por `FALLBACK`, que agarra la regla de la cuenta con departamento de
código MENOR: el `0140`, o sea **el Spa**. En los seis escenarios de checkbook
`COS_LAUNDRY` se fue a cero y `COS_SPA` subió lo mismo, **$6.604,12** — el costo
de la lavandería vendida contándose como costo del Spa.

## Por qué la 114 no lo vio

Porque midió sobre las tablas del **checkbook**, y ahí el `0162` está en cero de
verdad: `opex_entries` y `cost_entries` no tienen una sola fila suya. La
medición decía «las trece dan 0,00 en todos los escenarios» y era correcta
sobre lo que miró.

Lo que no miró fue **`allocation_entries`**, que es una tabla que **no llena
nadie: la escribe el motor**. Es exactamente la trampa que CLAUDE.md ya
documenta para la `4999` —«no tiene filas en el GL porque la escribe el motor,
no el upload»— y que volvió a morder con otra cuenta.

**La regla para la próxima:** antes de sacar una regla de mapeo por «no tiene
dato», mirá también `allocation_entries`. Una cuenta sin filas en el GL no es
una cuenta sin plata si hay un motor que la escribe.

## Y el `0162` sigue fuera del checkbook

Que era la razón por la que el owner mandó sacar las trece. `GET /departments/`
ya no cuenta las **cuentas de reparto** al derivar `lleva_gasto`: son cuentas
donde aterriza un asiento calculado, no donde alguien digita. La lista sale del
propio motor (`allocation_calculator.cuentas_de_reparto`), así que un reparto
nuevo queda cubierto solo. El `0121` Private Bar no se mueve: tiene cuentas de
gasto que no son de reparto.

## Esta migración es cinturón, no tirantes

La fuente de verdad sigue siendo `mapping_pl.json`, y el seed inserta lo que
falta en cada arranque. Pero el seed **falla en silencio** (va envuelto en un
`try/except` y Railway queda verde igual), y esta fila es la diferencia entre
que el costo de lavandería esté en su línea o en la del Spa. Se inserta acá
también, idempotente: si el seed ya la puso, no pasa nada, y si el seed se
cayó, la fila está.

El archivo lleva además una regla nueva para la `7685` del `0162` —uniformes,
que el reparto de lavandería cobra por FTE a cualquier departamento con
planilla, y el `0162` tiene—. Esa NO va acá: hoy el `0162` no participa de ese
reparto, así que vale $0,00 y el seed alcanza. La `5301` es la que mueve plata.

Revision ID: 115
Revises: 114
"""
from alembic import op
import sqlalchemy as sa

revision = "115"
down_revision = "114"
branch_labels = None
depends_on = None

#: Los mismos valores del archivo. La llave única es
#: (report_id, source_department, account_code, source_origin).
FILA = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "COS_LAUNDRY",
    "report_line_name": "Laundry Cost",
    "report_section": "COST OF SALES",
    "display_order": 47,
    "source_origin": "Cost",
    "source_department": "Laundry Revenue",
    "account_code": "5301",
    "account_name_example": "Costo Servicio Lavanderia (huespedes)",
    "financial_nature": "Expense",
    "rollup_operator": "SUM",
    "sign_rule": ("Aggregate to line as positive display value; calculations "
                  "subtract expense lines at subtotal level."),
    "notes": ("La escribe el MOTOR de repartos, no el upload: la lavanderia 0161 le "
              "manda aca el costo de los kilos de huesped para que el ingreso del "
              "servicio y su costo vivan juntos. Sin esta regla cae por descarte en "
              "el Spa. No habilita el checkbook: es cuenta de reparto (ver "
              "cuentas_de_reparto)."),
    "dept_code": "0162",
}


def upgrade() -> None:
    cols = ", ".join(FILA)
    vals = ", ".join(f":{c}" for c in FILA)
    op.execute(sa.text(
        f"INSERT INTO account_mapping (id, {cols}) "
        f"VALUES (gen_random_uuid()::text, {vals}) "
        "ON CONFLICT ON CONSTRAINT uq_account_mapping DO NOTHING"
    ).bindparams(**FILA))


def downgrade() -> None:
    # La fuente de verdad es `mapping_pl.json`: volver el archivo atrás y
    # arrancar deja la base como estaba (ver la 097, la 112, la 113 y la 114).
    pass
