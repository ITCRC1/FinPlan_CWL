# -*- coding: utf-8 -*-
"""El costo de telecomunicaciones de IT llega a su línea del P&L.

## El síntoma

El P&L Statement de agosto 2026 avisaba solo:

    El GOP acumulado de este cuadro (-$71.282,07) no coincide con el del motor
    (-$70.213,81): -$1.068,26 de diferencia.

Son dos caminos al mismo número —ingreso menos las clases 5/6/7 contra la suma
de las líneas por departamento— y tienen que dar lo mismo.

## Qué eran esos $1.068,26

Dos cuentas, al centavo:

    5400-0230   IT / COST OF CELL PHONE            234,94
    5401-0230   IT - COST OF INTERNET SERVICES     833,32
    ----------------------------------------------------
                                                 1.068,26

Clase 5, así que el camino **por naturaleza** las sumaba. Pero no resolvían a
ninguna línea del reporte —caían por `DROP`— así que el camino **departamental**
no las veía. El gasto existía, estaba bien clasificado por naturaleza, y no
llegaba al P&L.

## Por qué no estaban mapeadas

El mapeo de IT se construyó con la numeración **USALI**: `5700`–`5704`, con
`account_name_example` «Costo 1» … «Costo 5», o sea plantillas. El catálogo real
de Integrity usa la **54xx** para los mismos conceptos:

    mapeo tiene                        Integrity entrega
    5700 Cost of Cells Phones     ->   5400 IT / COST OF CELL PHONE
    5702 Cost of Internet Serv.   ->   5401 IT - COST OF INTERNET SERVICES

Las `7xxx` de IT sí coinciden en los dos catálogos —las veinticinco resuelven—
y por eso solo se cayeron estas dos. Nadie las echó de menos: son mil dólares
en un departamento de overhead, y el total seguía cuadrando **consigo mismo**.

## ⚠️ Esto EMPEORA el GOP reportado, y está bien

Al entrar las dos cuentas, el motor pasa a ver ese gasto: el GOP de agosto va de
-$70.213,81 a **-$71.282,07**. No es que el resultado cambie — es que mil
sesenta y ocho dólares de gasto real de IT ya estaban ahí y no se estaban
mostrando.

## Solo las dos que se verificaron

La `5402`, `5403` y `5404` quedan SIN mapear a proposito, aunque
`CLAUDE.md` §3.2 dé el rango `5400-5404` completo. No aparecen en ningún archivo
todavía y no hay con qué comprobar a qué concepto corresponden: mapearlas por su
número seria adivinar, y una cuenta adivinada que cae en la línea equivocada es
el mismo error de arriba al revés — solo que en silencio. El día que aparezcan,
el hallazgo de nivel 1 del Pre-Cierre las delata con su monto.

Revision ID: 141
Revises: 140
"""
import sqlalchemy as sa
from alembic import op

revision = "141"
down_revision = "140"
branch_labels = None
depends_on = None

#: Los mismos valores que `seed_data/mapping_pl.json`, que es la fuente de
#: verdad. La llave única es (report_id, source_department, account_code,
#: source_origin).
COMUN = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "COH_INFORMATION_SYSTEM",
    "report_line_name": "Information Systems Cost",
    "report_section": "OVERHEAD COST OF SALES",
    "display_order": 80,
    "source_origin": "Cost",
    "source_department": "Departamento de TI",
    "financial_nature": "Expense",
    "rollup_operator": "SUM",
    "sign_rule": ("Aggregate to line as positive display value; calculations "
                  "subtract expense lines at subtotal level."),
    "notes": ("Cuenta REAL de Integrity para el costo de telecomunicaciones de "
              "IT. El mapeo se construyo con la numeracion USALI (5700-5704, "
              "'Costo 1..5') y el catalogo de Integrity usa la 54xx para los "
              "mismos conceptos, asi que estas dos no resolvian a ninguna linea: "
              "se caian por DROP. El camino por naturaleza (ingreso menos clases "
              "5/6/7) SI las contaba y el departamental no, y esos $1.068,26 "
              "eran la brecha de GOP de agosto 2026. Ver migracion 141."),
    "dept_code": "0230",
}

FILAS = [
    {**COMUN, "account_code": "5400",
     "account_name_example": "IT / COST OF CELL PHONE"},
    {**COMUN, "account_code": "5401",
     "account_name_example": "IT - COST OF INTERNET SERVICES"},
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
