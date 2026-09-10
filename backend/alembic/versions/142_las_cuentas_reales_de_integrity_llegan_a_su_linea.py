# -*- coding: utf-8 -*-
"""Las cuentas que Integrity usa de verdad llegan a su línea del P&L.

## El mismo defecto, cinco veces más

La migración 141 arregló dos cuentas de IT: el mapeo se había sembrado con la
numeración **USALI de plantilla** (`5700`-`5704`, «Costo 1..5») mientras
Integrity postea en la `54xx`. No era un caso aislado. Buscándolo a propósito
en `P&L Agosto 2026 CRC.xlsx`, con el resolvedor real del P&L
(`construir_resolvedor`), aparecieron **diez cuentas más** en cinco líneas —y
los nombres de ejemplo del mapeo lo delataban: «Ingreso Tienda #1», «Ingreso
TRANSPORTION», «Costo 1».

## Cinco no se perdían: estaban en la LÍNEA EQUIVOCADA

Esto es lo que hace este hallazgo caro. El resolvedor, cuando no encuentra la
regla del departamento, cae al **descarte**: cualquier regla que use esa
cuenta, la del departamento menor. Así que la plata llegaba al P&L —el Total
Revenue cuadraba— pero en otro renglón:

    cuenta  depto                agosto (CRC)     caía en           debía ser
    ------------------------------------------------------------------------
    4500    0152 Transportation  6.549.206,01     REV_INNOCEANA     REV_TRANSPORTATION
    4600    0155 Innoceana           4.371,59     REV_CROWTHER_LAB  REV_INNOCEANA
    4120    0121 Private Bar        75.560,87     REV_FB_BEV        REV_PRIVATE_BAR
    4131    0121 Private Bar        43.026,15     REV_FB_BEV        REV_PRIVATE_BAR
    4125    0121 Private Bar        12.220,98     REV_FB_BEV        REV_PRIVATE_BAR

El ingreso de **Transportation se reportaba como Innoceana**: ~US$14.457 en un
mes. Es exactamente el modo de falla que `CLAUDE.md` marca como el más caro del
sistema — «el total sigue cuadrando: no hay error, no hay alerta, y la plata
cambia de línea sola. Solo se ve en el P&L por departamento».

## Cinco sí se perdían

    4305    0165 Gift Shop        118.595,64      DROP → ninguna línea
    4307    0165 Gift Shop        373.160,14      DROP
    4316    0165 Gift Shop        493.318,30      DROP
    4320    0165 Gift Shop         60.848,55      DROP
    5420    0220 Cafetería      5.864.362,37      DROP

El `5420` es el costo de la comida de empleados. Hasta ahora no se notaba
porque `ALLOCATION_EXCLUDE` lo sacaba antes de llegar al mapeo; desde que el
Pre-Cierre lo muestra como overhead, la falta de regla lo dejaba sin renglón.

## ⚠️ Esto MUEVE plata entre renglones del Actual, y está bien

Después de re-subir el mes: Innoceana **baja** ~US$14.457 y Transportation
**sube** lo mismo; A&B Bebida baja ~US$289 y Private Bar sube lo mismo; Gift
Shop y el costo de Cafetería **aparecen**. Ningún total se mueve por las cinco
primeras: son reclasificaciones. Total Revenue sube por el Gift Shop.

Verificado: con estas diez reglas, las **211** parejas (departamento, cuenta)
del archivo de agosto resuelven `exact`. Cero descartes, cero pérdidas.

## Solo las que se verificaron contra un archivo real

Ninguna se mapeó por su número. Cada una salió del archivo de agosto con su
nombre de Integrity, y el nombre dice el concepto («TRANSPORTATION - GROUNDS»,
«COST OF FOOD CAFETERIA - STAFF»). Mapear por número sería adivinar, y una
cuenta adivinada en la línea equivocada es este mismo error otra vez, en
silencio. Las que no aparecen en ningún archivo quedan sin mapear a propósito:
el hallazgo de nivel 1 del Pre-Cierre las delata con su monto cuando lleguen.

Revision ID: 142
Revises: 141
"""
import sqlalchemy as sa
from alembic import op

revision = "142"
down_revision = "141"
branch_labels = None
depends_on = None

#: Los mismos valores que `seed_data/mapping_pl.json`, que es la fuente de
#: verdad (regla permanente de CLAUDE.md). La llave única es
#: (report_id, source_department, account_code, source_origin).
NOTA = ("Cuenta real de Integrity. El mapeo se sembro con numeros "
        "de plantilla USALI que Integrity no usa (2026-09-10).")

FILAS: list[dict] = []

REV_RETAIL = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "REV_RETAIL",
    "report_line_name": "Gift Shop",
    "report_section": "REVENUES",
    "display_order": 24,
    "source_origin": "Revenue",
    "source_department": "Departamento Gift Shop",
    "financial_nature": "Revenue",
    "rollup_operator": "SUM",
    "sign_rule": "Aggregate to line as positive display value; calculations subtract expense lines at subtotal level.",
    "dept_code": "0165",
}

FILAS += [
    {**REV_RETAIL, "account_code": "4305",
     "account_name_example": "VISORS/HATS/CAPS RETAIL GIFT SHOP",
     "notes": NOTA},
    {**REV_RETAIL, "account_code": "4307",
     "account_name_example": "CLOTHING OTHER RETAIL GIFT SHOP 1",
     "notes": NOTA},
    {**REV_RETAIL, "account_code": "4316",
     "account_name_example": "RETAIL GIFT SHOP OTHERS",
     "notes": NOTA},
    {**REV_RETAIL, "account_code": "4320",
     "account_name_example": "OTHER SUNDRY RETAIL GIFT SHOP",
     "notes": NOTA},
]

COH_CAFETERIA = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "COH_CAFETERIA",
    "report_line_name": "Cafetería Cost",
    "report_section": "OVERHEAD COST OF SALES",
    "display_order": 80,
    "source_origin": "Cost",
    "source_department": "Departamento de Cafeteria",
    "financial_nature": "Expense",
    "rollup_operator": "SUM",
    "sign_rule": "Aggregate to line as positive display value; calculations subtract expense lines at subtotal level.",
    "dept_code": "0220",
}

FILAS += [
    {**COH_CAFETERIA, "account_code": "5420",
     "account_name_example": "COST OF FOOD CAFETERIA - STAFF",
     "notes": NOTA},
]

REV_PRIVATE_BAR = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "REV_PRIVATE_BAR",
    "report_line_name": "Private Bar",
    "report_section": "REVENUES",
    "display_order": 21,
    "source_origin": "Revenue",
    "source_department": "Departamento Private Bar",
    "financial_nature": "Revenue",
    "rollup_operator": "SUM",
    "sign_rule": "Aggregate to line as positive display value; calculations subtract expense lines at subtotal level.",
    "dept_code": "0121",
}

FILAS += [
    {**REV_PRIVATE_BAR, "account_code": "4120",
     "account_name_example": "F&B NA BEVERAGE - PRIVATE BAR",
     "notes": NOTA},
    {**REV_PRIVATE_BAR, "account_code": "4125",
     "account_name_example": "F&B BEER - PRIVATE BAR",
     "notes": NOTA},
    {**REV_PRIVATE_BAR, "account_code": "4131",
     "account_name_example": "F&B WINE - PRIVATE BAR",
     "notes": NOTA},
]

REV_TRANSPORTATION = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "REV_TRANSPORTATION",
    "report_line_name": "Transportation",
    "report_section": "REVENUES",
    "display_order": 25,
    "source_origin": "Revenue",
    "source_department": "Departamento de Transportation",
    "financial_nature": "Revenue",
    "rollup_operator": "SUM",
    "sign_rule": "Aggregate to line as positive display value; calculations subtract expense lines at subtotal level.",
    "dept_code": "0152",
}

FILAS += [
    {**REV_TRANSPORTATION, "account_code": "4500",
     "account_name_example": "TRANSPORTATION - GROUNDS",
     "notes": NOTA},
]

REV_INNOCEANA = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_line_code": "REV_INNOCEANA",
    "report_line_name": "Innoceana",
    "report_section": "REVENUES",
    "display_order": 27,
    "source_origin": "Revenue",
    "source_department": "Departamento de INNOCEANA",
    "financial_nature": "Revenue",
    "rollup_operator": "SUM",
    "sign_rule": "Aggregate to line as positive display value; calculations subtract expense lines at subtotal level.",
    "dept_code": "0155",
}

FILAS += [
    {**REV_INNOCEANA, "account_code": "4600",
     "account_name_example": "INNOCEANA 1",
     "notes": NOTA},
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
