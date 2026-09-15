# -*- coding: utf-8 -*-
"""La `5201` del Gift Shop llega a su línea.

Owner, 2026-09-15, subiendo el cierre de agosto: *«me da este 0165 como
error… lo que no sé es que en lo que estoy subiendo esta combinación no
está»*.

El hallazgo tenía razón y el owner también. La cuenta **sí** está en su
archivo, como `5201-0151 CLOTHING COST STORE` por −58.346,44 CRC (−US$128,61 a
TC 453,68). Lo que no estaba era el `0165`: ése es el destino en FinPlan, y el
puente traduce `0151 → 0165`. El aviso le mostraba el departamento de llegada
en vez del que él tiene delante — arreglado aparte, en `nivel1_estructura`.

## La regla que faltaba

La `5201` no tenía regla en **ningún** departamento y resolvía a `DROP`: su
plata no aparecía en ninguna línea del P&L. Sus hermanas `5203`–`5208` sí las
tienen, en las dos puntas:

    5203..5208  0165  ->  COS_RETAIL   (Gift Shop Cost)
    5203..5208  0151  ->  COS_TIENDA   (Tienda Cost)

Se agrega la `5201` a las dos, con el nombre real de Integrity. Es el mismo par
que ya tienen sus hermanas: el GL trae un solo «Tienda / Gift Shop» y según el
segmento cae en uno u otro.

## Por qué aparece recién ahora

Hasta agosto el Gift Shop no tenía costo de ventas posteado — quedó anotado el
2026-09-10 como «Gift Shop tiene ingreso y CERO costo». Este cierre es el
primero que lo trae, y la cuenta sin regla se delató sola en el hallazgo de
nivel 1. Es exactamente para lo que ese hallazgo existe.

## Verificado

Con esta regla, el archivo `Final August 2026 INTEGRITY1.xlsx` resuelve sin un
solo descarte y sin un solo fallback.

⚠️ El monto es NEGATIVO: un costo de ventas con saldo acreedor. Eso lo levanta
el hallazgo de nivel 2 («montos con el signo contrario al de su clase») y es
una pregunta para Integrity —una devolución de mercadería, probablemente—, no
algo que el mapeo pueda ni deba corregir.

Revision ID: 145
Revises: 144
"""
import sqlalchemy as sa
from alembic import op

revision = "145"
down_revision = "144"
branch_labels = None
depends_on = None

#: Los mismos valores que `seed_data/mapping_pl.json`, que es la fuente de
#: verdad (regla permanente de CLAUDE.md).
SIGNO = ("Aggregate to line as positive display value; calculations subtract "
         "expense lines at subtotal level.")
NOTA = ("Gemela de las 5203-5208, con el nombre real de Integrity. Detectada el "
        "2026-09-15 en el hallazgo de nivel 1 del Pre-Cierre: la 5201 no tenia "
        "regla en NINGUN departamento y resolvia a DROP - US$128,61 de agosto "
        "2026 que no llegaban a ningun renglon.")

BASE = {
    "active_status": "YES",
    "report_id": "P&L_DETAIL_OWNERS",
    "report_section": "COST OF SALES",
    "display_order": 47,
    "source_origin": "Cost",
    "account_code": "5201",
    "account_name_example": "CLOTHING COST STORE",
    "financial_nature": "Expense",
    "rollup_operator": "SUM",
    "sign_rule": SIGNO,
}

FILAS: list[dict] = [
    {**BASE, "report_line_code": "COS_RETAIL", "report_line_name": "Gift Shop Cost",
     "source_department": "Departamento Gift Shop", "dept_code": "0165",
     "notes": NOTA},
    {**BASE, "report_line_code": "COS_TIENDA", "report_line_name": "Tienda Cost",
     "source_department": "Departamento Tienda 0151", "dept_code": "0151",
     "notes": NOTA + " Par del 0151, igual que las 5203-5208."},
    # ⚠️ Y el Private Bar, que está modelado como TIENDA con las MISMAS cuentas
    # de costo que el Gift Shop — decisión del owner, blindada por
    # `test_private_bar_aparte`. Agregar la 5201 a uno y no al otro rompe esa
    # prueba, y con razón: el modelo dejaría de ser el mismo.
    {**BASE, "report_line_code": "COS_PRIVATE_BAR",
     "report_line_name": "Private Bar Cost",
     "source_department": "Departamento Private Bar", "dept_code": "0121",
     "notes": ("El Private Bar esta modelado como TIENDA, con las mismas "
               "cuentas de costo que el Gift Shop (decision del owner, blindada "
               "por test_private_bar_aparte).")},
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
