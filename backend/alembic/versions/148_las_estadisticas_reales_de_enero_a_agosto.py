# -*- coding: utf-8 -*-
"""Las estadisticas de habitaciones de CWL, enero a agosto 2026.

Owner, 2026-09-16, con su hoja maestra al lado: *«necesito que siembres estas
tarifas ahi, tal cual. sin recalculo .. solo puesto ahi»*.

## Que estaba mal

El ACTUAL 2026 traia 3.492 noches ocupadas contra las 3.341 de la hoja del
owner —151 de mas— y **junio y julio sin tarifa**. La plata siempre estuvo
bien: el P&L cuadraba al centavo contra su Excel en las doce lineas, de Total
Revenue a Net Profit. Lo que no cuadraba eran las noches, y con ellas la
ocupacion, el ADR y el RevPAR.

Con la tarifa en blanco pasaba algo peor que faltar: `adr = 0` en un mes CON
noches vendidas entraba al promedio ponderado como si se hubiera vendido a
cero. Esas 395 noches de junio y julio —11,3% del acumulado— bajaban el ADR del
periodo de $587.89 a $521.39. Ningun error; un promedio que no es de nadie.

## De donde salen estos numeros

De la hoja maestra del owner, verbatim. Cuadran solos:

    disponibles 7.290 · ocupadas 3.341 · huespedes 6.490
    ADR ponderado por noches = $599.41

Los tres totales y el ADR son exactamente los de su YTD August. No hay nada
calculado aca — estan copiados.

## La unica columna que NO se copia: % ocupacion

En su hoja el porcentaje es una formula, y seis de los ocho meses lo prueban al
decimal. Los dos que no —julio (27,42% contra 233/930 = 25,05%) y agosto
(27,02% contra 254/930 = 27,31%)— son EXACTAMENTE las dos celdas que el owner
marco en amarillo: cambio las noches y el porcentaje quedo del valor anterior.

Guardar 27,42% junto a 233 noches sobre 930 seria grabar una contradiccion que
despues nadie puede explicar. Se guarda noches/disponibles, que ademas
reproduce el 45,83% de su propio acumulado (3.341 / 7.290).

## Alcance

Solo CWL, solo 2026, solo el ACTUAL — y NO el espejo del Pre-Cierre, que es
`type="ACTUAL"` pero trae un mes suelto (ver `scenario.actual_de_verdad`). En
las otras propiedades del grupo no encuentra nada y no hace nada.

Setiembre a diciembre NO se tocan: en la hoja son Forecast, y hay varias
versiones de forecast — sembrar en la equivocada seria un numero mudo.
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "148"
down_revision = "147"
branch_labels = None
depends_on = None

#: mes: (disponibles, ocupadas, huespedes, ADR). Hoja maestra del owner.
DATOS = {
    1: (930, 637, 1181, "654.65"),
    2: (840, 668, 1256, "618.48"),
    3: (930, 691, 1359, "612.42"),
    4: (900, 473,  903, "671.34"),
    5: (930, 223,  421, "534.39"),
    6: (900, 162,  278, "478.63"),
    7: (930, 233,  518, "449.10"),
    8: (930, 254,  574, "513.44"),
}


def _escenarios(bind):
    return [r[0] for r in bind.execute(sa.text("""
        SELECT id FROM scenarios
         WHERE hotel_id = 'CWL' AND year = 2026 AND type = 'ACTUAL'
           AND (es_precierre IS NULL OR es_precierre = false)
    """))]


def upgrade() -> None:
    bind = op.get_bind()
    for sid in _escenarios(bind):
        # Reescribible: borrar y poner de nuevo deja el mismo resultado si esto
        # se corre dos veces.
        bind.execute(sa.text(
            "DELETE FROM scenario_stats WHERE scenario_id = :s AND month <= 8"),
            {"s": sid})
        for mes, (disp, ocup, pax, adr) in DATOS.items():
            bind.execute(sa.text("""
                INSERT INTO scenario_stats
                    (id, scenario_id, month, rooms_available, rooms_occupied,
                     guests, occupancy_pct, adr)
                VALUES (:id, :s, :m, :disp, :ocup, :pax, :pct, :adr)
            """), {"id": str(uuid.uuid4()), "s": sid, "m": mes,
                   "disp": disp, "ocup": ocup, "pax": pax,
                   "pct": round(ocup / disp, 6), "adr": adr})


def downgrade() -> None:
    # No se restaura lo que habia: eran las cifras que el owner vino a
    # corregir. Se vacian los meses sembrados y se recargan por la pantalla.
    bind = op.get_bind()
    for sid in _escenarios(bind):
        bind.execute(sa.text(
            "DELETE FROM scenario_stats WHERE scenario_id = :s AND month <= 8"),
            {"s": sid})
