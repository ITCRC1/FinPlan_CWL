# -*- coding: utf-8 -*-
"""La `5603` de lavandería se va al `0162` y pasa a COST OF SALES.

## Qué pidió el owner (2026-08-16)

> «Así debe quedar el departamento `0162`, debes mover el `0161` a `0162`» ·
> «cambiá para que no haya duda dónde va el costo» · «**en `0162` es COS**».

Hasta hoy la lavandería tenía **dos cuentas de costo en dos secciones
distintas**: la `5301` (servicio vendido) en `COS_LAUNDRY` / COST OF SALES bajo
el `0162`, y la `5603` «Costos 1» en `COH_LAUNDRY` / OVERHEAD COST OF SALES bajo
el `0161`. Esa era la duda. Ahora las dos viven en el `0162` y en `COS_LAUNDRY`.

## Las DOS filas, y por qué no alcanza con mover una

El GL trae **un solo departamento «Lavandería»** y el importador lo manda
siempre al `0161` (`gl_detail_importer.py`, `("lavander", "0161")`). Si esta
migración solo cambiara el `dept_code` de la regla, el costo que entra por
archivo quedaría **sin regla** — y el `0161` no tiene padre del cual heredar, o
sea `FALLBACK`. Es exactamente lo que le pasó a la `5301` con la migración 114 y
costó $6.604,12 contados como costo del Spa.

Por eso quedan **dos reglas apuntando a la misma línea**, que es la pareja que
ya tienen la `4700`, la `4701` y la `4702`:

    (0161, 5603, "Departamento de Lavanderia")  ->  COS_LAUNDRY
    (0162, 5603, "Laundry Revenue")             ->  COS_LAUNDRY

Venga etiquetado como venga, el costo aterriza en el mismo lugar.

## Y el DATO se mueve, no solo la regla

`actual_entries` y `cost_entries` tienen la `5603` bajo el `0161`:

    BUDGET Final 2026        3.262,98
    FORECAST April 2026      1.725,26
    FORECAST Working 2026    1.513,50

Se mueven al `0162`. Es el patrón de `consolidar_0240_en_0250.py`: **se mueve el
dato, no se inactiva el código.** Dos de los tres escenarios están `locked` — la
migración los toca a propósito, porque el enllavado congela la edición del
usuario, no una corrección de mapeo (ver
`project_finplan_cwl_enllavar_no_congela`).

## Lo que se mueve en el reporte

$6.501,74 de `OVERHEAD COST OF SALES` a `COST OF SALES` en tres escenarios. El
GOP **no cambia** —los dos lados caen adentro del mismo subtotal— pero cambian
dos líneas, así que esto se verifica con `scripts/foto_lineas.py`, nunca con
`foto_pl_totales`.

Efecto buscado, medido antes en `scripts/residuo_lavanderia.py` y
`scripts/quien_manda.py`: era la única diferencia que hacía que el **Resumen**
le ganara al **Detalle** en `BUDGET Final 2026`, `FORECAST April 2026` y
`FORECAST Working 2026`. Con la `5603` del lado del gasto operativo, los tres
totales de control cierran y vuelve a mandar el mayor, que es la regla del owner.

⚠️ `COH_LAUNDRY` queda **sin ninguna cuenta**. Era su única regla. La línea sigue
declarada y suma cero; retirarla del reporte es otra decisión y no se toca acá.
"""
from alembic import op
import sqlalchemy as sa

revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None

CUENTA = "5603"
DESTINO = {"linea": "COS_LAUNDRY", "seccion": "COST OF SALES", "orden": 47}

#: La gemela nueva. Mismos valores que `mapping_pl.json`, que es la fuente de
#: verdad: si la migración y el archivo dijeran cosas distintas, el próximo
#: deploy revierte esto solo (ver `project_finplan_seed_manda_sobre_mapeo`).
FILA_0162 = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": DESTINO["linea"],
    "report_line_name": "Laundry Cost",
    "report_section": DESTINO["seccion"],
    "display_order": DESTINO["orden"],
    "source_origin": "Cost",
    "source_department": "Laundry Revenue",
    "account_code": CUENTA,
    "account_name_example": "Costos 1",
    "financial_nature": "Expense",
    "rollup_operator": "SUM",
    "sign_rule": ("Aggregate to line as positive display value; calculations "
                  "subtract expense lines at subtotal level."),
    "notes": ("El costo de lavanderia vive con su ingreso, en el 0162. Owner "
              "2026-08-16: «asi debe quedar el departamento 0162, debes mover el "
              "0161 a 0162» y «en 0162 es COS». Antes estaba en el 0161 como "
              "COH_LAUNDRY (overhead) — ver PENDIENTES A0.-7."),
    "dept_code": "0162",
}


def upgrade() -> None:
    # 1. La regla que ya existía deja de ser overhead: mismo departamento (es la
    #    que atrapa lo que entra etiquetado «Lavanderia»), nueva línea.
    op.execute(sa.text(
        "UPDATE account_mapping SET report_line_code = :linea, "
        "report_section = :seccion, display_order = :orden, notes = :notas "
        "WHERE account_code = :cuenta AND dept_code = '0161'"
    ).bindparams(
        linea=DESTINO["linea"], seccion=DESTINO["seccion"], orden=DESTINO["orden"],
        cuenta=CUENTA,
        notas=("GEMELA de la regla del 0162. El GL trae UN solo departamento "
               "«Lavanderia» y el importador lo manda siempre al 0161, asi que sin "
               "esta fila el costo que entra por archivo se queda sin regla — y el "
               "0161 no tiene padre del cual heredar. Es la misma pareja que tienen "
               "la 4700/4701/4702. Las dos apuntan a COS_LAUNDRY: no hay duda de "
               "donde va el costo."),
    ))

    # 2. La gemela del 0162, que es donde vive el dato de ahora en adelante.
    cols = ", ".join(FILA_0162)
    vals = ", ".join(f":{c}" for c in FILA_0162)
    op.execute(sa.text(
        f"INSERT INTO account_mapping (id, {cols}) "
        f"VALUES (gen_random_uuid()::text, {vals}) "
        "ON CONFLICT ON CONSTRAINT uq_account_mapping DO NOTHING"
    ).bindparams(**FILA_0162))

    # 3. El DATO. Sin esto la regla nueva no tiene a quién aplicarle: el costo
    #    seguiría contándose bajo el 0161, que es un departamento de reparto y
    #    debe cerrar en cero.
    for tabla in ("actual_entries", "cost_entries"):
        op.execute(sa.text(
            f"UPDATE {tabla} SET dept_code = '0162' "
            "WHERE account_code = :cuenta AND dept_code = '0161'"
        ).bindparams(cuenta=CUENTA))


def downgrade() -> None:
    # El mapeo vuelve solo: la fuente de verdad es `mapping_pl.json` y el seed lo
    # re-afirma en cada arranque (misma doctrina que la 097, 112, 113, 114, 115).
    # El DATO no vuelve solo, así que esto sí lo devuelve.
    for tabla in ("actual_entries", "cost_entries"):
        op.execute(sa.text(
            f"UPDATE {tabla} SET dept_code = '0161' "
            "WHERE account_code = :cuenta AND dept_code = '0162'"
        ).bindparams(cuenta=CUENTA))
