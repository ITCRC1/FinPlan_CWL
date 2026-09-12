# -*- coding: utf-8 -*-
"""Dos cuentas que el P&L no sabía dónde poner.

Compañera de código del arreglo del crédito de reparto en `parse_gl_detail`.
Aquel no necesita migración —es parser—; estas dos reglas sí, porque el mapeo
vive en la base.

## Medido contra el cierre real de agosto 2026

El owner subió `P&L Agosto 2026 CRC123.xlsx` (TC 453,06) y el Net Profit del
tab de Pre-Closing no le pegaba. Resolviendo las 247 cuentas del archivo con el
resolvedor real (`construir_resolvedor`) y el puente de departamentos:

    cuenta  depto Integrity      destino  agosto (US$)   caía en
    ---------------------------------------------------------------------
    8010    0240 Property Exp.   0250        2.735,83    DROP -> ninguna
    5501    0160 Lavanderia      0162          150,09    COS_INNOCEANA

### `8010` — se perdía entera

`PROPERTY EXPENSES - TAXES & PERMITS`: impuesto de bienes inmuebles (subcuenta
800) y canon de zona marítima (801). **No tenía regla en NINGÚN departamento**,
así que el resolvedor la descartaba y los US$2.735,83 no aparecían en ningún
renglón del P&L. Las demás 8xxx del `0250` ya estaban; ésta se quedó afuera.

### `5501` — estaba en la línea equivocada

El costo de lavandería se reportaba como **costo de Innoceana**. El `0160` de
Integrity aterriza en el `0162` por el puente (`mapd_integrity`), y para el
`5501` sólo existían reglas en el `260` y el `0155`; el descarte toma la del
`dept_code` menor, que es Innoceana. Es el modo de falla caro de `CLAUDE.md`:
el total cuadra y la plata cambia de renglón sola.

Se agregan las **dos gemelas**, `0161` y `0162`, igual que el par que ya tienen
el `5603` y las `4700/4701/4702`: el GL trae un solo departamento «Lavandería»
y según el segmento cae en uno u otro. Las dos apuntan a `COS_LAUNDRY`, así que
no hay duda de dónde va el costo. Se distinguen por `source_department`, que es
parte de la llave única (`uq_account_mapping`).

## Verificado

Con estas tres reglas, las **247** parejas (departamento, cuenta) del archivo de
agosto resuelven `exact`: cero descartes, cero fallbacks.

## Efecto al re-subir el mes

Aparece `8010` en RENT (+US$2.735,83 de gasto no operativo, que hoy no
se ve) y US$150,09 se mueven de Innoceana Cost a Laundry Cost. El primero
**empeora** la utilidad neta en su monto: la plata siempre estuvo, sólo que sin
renglón.

Revision ID: 144
Revises: 143
"""
import sqlalchemy as sa
from alembic import op

revision = "144"
down_revision = "143"
branch_labels = None
depends_on = None

#: Los mismos valores que `seed_data/mapping_pl.json`, que es la fuente de
#: verdad (regla permanente de CLAUDE.md). Si esta lista y el JSON se separan,
#: el próximo deploy revierte la migración sin decir nada.
SIGNO = ("Aggregate to line as positive display value; calculations subtract "
         "expense lines at subtotal level.")

COS_LAUNDRY = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "COS_LAUNDRY",
    "report_line_name": "Laundry Cost",
    "report_section": "COST OF SALES",
    "display_order": 47,
    "source_origin": "Cost",
    "account_code": "5501",
    "account_name_example": "LAUNDRY COSTS",
    "financial_nature": "Expense",
    "rollup_operator": "SUM",
    "sign_rule": SIGNO,
}

FILAS: list[dict] = [
    {
        "active_status": "YES",
        "report_id": "P&L_DETAIL_OWNERS",
        "report_line_code": "RENT",
        "report_line_name": "RENT",
        "report_section": "OWNER / NON-OP EXPENSES",
        "display_order": 86,
        "source_origin": "Below GOP",
        "source_department": "Departamento de Property Expenses",
        "account_code": "8010",
        "account_name_example": "PROPERTY EXPENSES - TAXES & PERMITS",
        "financial_nature": "Expense",
        "rollup_operator": "SUM",
        "sign_rule": SIGNO,
        "notes": ("Impuesto de bienes inmuebles y canon de zona maritima "
                  "(subcuentas 800 y 801). NO tenia regla en NINGUN "
                  "departamento: resolvia a DROP y la plata desaparecia del "
                  "P&L sin aviso. Agosto 2026: US$2.735,83. Va con las demas "
                  "8xxx del 0250, que es el destino del 0240 de Integrity "
                  "segun el puente. La linea es RENT porque el motor "
                  "(pl_engine.NONOP_ACCOUNT_LINE) ya trataba la 8010 como "
                  "alias historico de RENT; separarlas mandaria la misma "
                  "cuenta a dos renglones segun el camino."),
        "dept_code": "0250",
    },
    {
        **COS_LAUNDRY,
        "source_department": "Laundry Revenue",
        "dept_code": "0162",
        "notes": ("El 0160 de Integrity aterriza en el 0162 por el puente. Sin "
                  "esta regla el 5501 caia por FALLBACK a COS_INNOCEANA -el "
                  "0155 es el dept_code mas bajo con regla para el 5501- y el "
                  "costo de lavanderia aparecia como costo de Innoceana. "
                  "Agosto 2026: US$150,09. GEMELA de la del 0161, igual que la "
                  "pareja del 5603."),
    },
    {
        **COS_LAUNDRY,
        "source_department": "Departamento de Lavanderia",
        "dept_code": "0161",
        "notes": ("GEMELA de la regla del 0162. El GL trae UN solo "
                  "departamento 'Lavanderia' y segun el segmento cae en 0161 o "
                  "en 0162; las dos apuntan a COS_LAUNDRY. Mismo par que "
                  "tienen el 5603 y las 4700/4701/4702."),
    },
]


def upgrade() -> None:
    for fila in FILAS:
        campos = list(fila.keys())
        op.execute(sa.text(
            f"INSERT INTO account_mapping (id, {', '.join(campos)}) "
            f"VALUES (gen_random_uuid()::text, "
            f"{', '.join(':' + c for c in campos)}) "
            "ON CONFLICT ON CONSTRAINT uq_account_mapping DO NOTHING"
        ).bindparams(**fila))


def downgrade() -> None:
    # La fuente de verdad es `mapping_pl.json`: volver el archivo atras y
    # arrancar deja la base como estaba — el seed re-afirma campo por campo en
    # CADA deploy (ver la regla permanente de CLAUDE.md y la migracion 115).
    pass
