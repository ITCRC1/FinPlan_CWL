"""el seed manda sobre el mapeo — se rehacen 093/094/095 donde correspondía

## Lo que pasó

Las migraciones `093`, `094` y `095` escribieron en `account_mapping` y
`report_line_config`. Corrieron bien, se midió el efecto, quedó verificado…
**y el siguiente deploy las revirtió.**

`backend/Procfile` arranca con
`alembic upgrade head && python -m app.seed && uvicorn …`, y `app/seed_mapping.py`
re-afirma **campo por campo** todas las filas desde
`backend/app/seed_data/mapping_pl.json`, buscándolas por su llave de negocio:

* `report_line_config` → `(report_id, line_code)`
* `account_mapping` → `(report_id, source_department, account_code, source_origin)`

O sea: **ese JSON es la fuente de verdad de esas dos tablas, no las
migraciones.** Cualquier cambio que viva solo en una migración dura hasta el
próximo deploy. Y no avisa: el seed imprime «N actualizados» y sigue.

Peor todavía, la `094` dejó la base en un estado que ninguna de las dos partes
quería. Renombró la fila `OPEX_AREC` → `OH_AREC` en `report_line_config`; el
seed **no borra lo que sobra** (a propósito: borrar por ausencia le vaciaría el
P&L a un hotel que tenga mapeos propios), así que `OH_AREC` se quedó, pero
`OPEX_AREC` volvió a insertarse desde el JSON. Quedaron **las dos**, y como
`TOTAL_OPERATING_EXPENSES = SUM(OPEX_*)`, el costo de Área Recreativa volvió al
bloque operativo mientras `OH_AREC` colgaba vacía del overhead.

## Lo que hace esta migración

1. Borra la fila huérfana `OPEX_AREC` de `report_line_config` — es lo único que
   el seed no puede arreglar solo.
2. Re-aplica 093/094/095 sobre la base, para que quede bien **ahora** y no
   recién en el próximo arranque.

Y el arreglo de fondo va afuera: las tres decisiones ya están escritas en
`mapping_pl.json`, así que de acá en adelante el seed las **sostiene** en vez de
pisarlas — y además viajan a una instalación nueva, que es algo que una
migración de datos no hacía.

> **Regla para el futuro:** una migración que toque `account_mapping` o
> `report_line_config` **tiene que cambiar también `app/seed_data/mapping_pl.json`**,
> o se revierte sola en el próximo deploy. `tests/test_seed_manda_sobre_mapeo.py`
> vigila las decisiones que ya se tomaron.

Revision ID: 097
Revises: 096
"""
from alembic import op
import sqlalchemy as sa

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"
NOMBRE = "Área Recreativa"
LOGICA_OH_AREC = "Nómina + Opex del depto 270. Centro de costo, no departamento operativo."
LOGICA_LARGE_CAPEX = ("Sin regla de cuenta a propósito: comparte la 8020 con CAPITAL_RESERVE "
                      "y el GL no las separa. Se alimenta a nivel línea (actual_pl_lines o "
                      "nonop_entries).")
LOGICA_ASSET_LOSS = ("Sin regla de cuenta: comparte la 8040 con DEPRECIATION y el GL de CWL no "
                     "trae cuentas de pérdida de activos. Se alimenta a nivel línea si aparece.")
NOTA_8020 = ("La 8020 lleva LAS DOS lineas: Capital Reserve y Large Capital Expenditure. "
             "El GL no las separa, asi que la apertura entra a nivel linea (snapshot "
             "importado o nonop_entries). Con solo la cuenta, todo cae aca: ambas viven "
             "dentro de CAPITAL_EXPENSE y el subtotal, el EBITDA After Capital, el EBT y "
             "el Neto no cambian.")
NOTA_ROYALTIES = ("Desactivada a proposito: la cuenta 8005 carga MGMT_FEE_3 y "
                  "MGMT_FEE_5_ROYALTIES, y el resolvedor solo admite una regla por "
                  "(departamento, cuenta). La linea por defecto es MGMT_FEE_3; los "
                  "royalties se alimentan a nivel linea (porcentaje o nonop_entries).")


def _sql(q: str, **kw) -> None:
    op.execute(sa.text(q).bindparams(**kw))


def upgrade() -> None:
    # 1. la fila huérfana que dejó la 094 al renombrar
    _sql("DELETE FROM report_line_config WHERE report_id = :r AND line_code = 'OPEX_AREC'",
         r=REPORT_ID)

    # 2. Área Recreativa a overhead (094)
    _sql("UPDATE report_line_config SET section='OVERHEAD EXPENSES', display_order=78, "
         "line_name=:n, calculation_logic=:l, parent_line_code='SEC_OVERHEAD_EXPENSES' "
         "WHERE report_id=:r AND line_code='OH_AREC'", n=NOMBRE, l=LOGICA_OH_AREC, r=REPORT_ID)
    _sql("UPDATE report_line_config SET calculation_logic='REV_AREC', line_name=:n "
         "WHERE report_id=:r AND line_code='PROFIT_AREC'", n=NOMBRE, r=REPORT_ID)
    _sql("UPDATE account_mapping SET report_line_code='OH_AREC', "
         "report_section='OVERHEAD EXPENSES', display_order=78, report_line_name=:n "
         "WHERE report_id=:r AND report_line_code='OPEX_AREC'", n=NOMBRE, r=REPORT_ID)
    _sql("UPDATE department_catalog SET pl_kind='OVERHEAD' WHERE dept_code='270'")

    # 3. la única verdad de la 8020 y de LARGE_CAPEX / ASSET_LOSS (093)
    _sql("UPDATE report_line_config SET calculation_logic=:l "
         "WHERE report_id=:r AND line_code='LARGE_CAPEX'", l=LOGICA_LARGE_CAPEX, r=REPORT_ID)
    _sql("UPDATE report_line_config SET calculation_logic=:l "
         "WHERE report_id=:r AND line_code='ASSET_LOSS'", l=LOGICA_ASSET_LOSS, r=REPORT_ID)
    _sql("UPDATE account_mapping SET notes=:n WHERE report_id=:r AND account_code='8020'",
         n=NOTA_8020, r=REPORT_ID)

    # 4. honorarios: una sola regla por (departamento, cuenta) (095)
    _sql("UPDATE account_mapping SET active_status='NO', notes=:n "
         "WHERE report_id=:r AND account_code='8005' "
         "  AND report_line_code='MGMT_FEE_5_ROYALTIES'", n=NOTA_ROYALTIES, r=REPORT_ID)


def downgrade() -> None:
    # Se revierte lo que se puede: la fila borrada vuelve como estaba en el JSON
    # original, y OH_AREC regresa al bloque operativo con su nombre viejo.
    _sql("UPDATE report_line_config SET line_code='OPEX_AREC', section='OPERATING EXPENSES', "
         "display_order=45, calculation_logic='SUM mapped accounts', "
         "parent_line_code='SEC_OPERATING_EXPENSES' "
         "WHERE report_id=:r AND line_code='OH_AREC'", r=REPORT_ID)
    _sql("UPDATE report_line_config SET calculation_logic='REV_AREC - OPEX_AREC' "
         "WHERE report_id=:r AND line_code='PROFIT_AREC'", r=REPORT_ID)
    _sql("UPDATE account_mapping SET report_line_code='OPEX_AREC', "
         "report_section='OPERATING EXPENSES', display_order=45 "
         "WHERE report_id=:r AND report_line_code='OH_AREC'", r=REPORT_ID)
    _sql("UPDATE department_catalog SET pl_kind='OPERATING' WHERE dept_code='270'")
    _sql("UPDATE report_line_config SET calculation_logic='SUM mapped large capital expenditure' "
         "WHERE report_id=:r AND line_code='LARGE_CAPEX'", r=REPORT_ID)
    _sql("UPDATE report_line_config SET calculation_logic='Include if GL has asset loss accounts' "
         "WHERE report_id=:r AND line_code='ASSET_LOSS'", r=REPORT_ID)
    _sql("UPDATE account_mapping SET notes=NULL WHERE report_id=:r AND account_code='8020'",
         r=REPORT_ID)
    _sql("UPDATE account_mapping SET active_status='YES', notes=NULL "
         "WHERE report_id=:r AND account_code='8005' "
         "  AND report_line_code='MGMT_FEE_5_ROYALTIES'", r=REPORT_ID)
