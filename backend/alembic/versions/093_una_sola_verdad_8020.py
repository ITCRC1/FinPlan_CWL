"""la cuenta 8020 tenía tres verdades — queda una sola

**El problema.** La cuenta `8020` decía tres cosas distintas según a quién se le
preguntara:

| Fuente | Decía |
|---|---|
| `account_mapping` | Capital Reserve |
| El dato cargado (`belowgop_account_entries`) | Large Capital Expenditure |
| `NONOP_ACCOUNT_MAP` del motor viejo | `mgmt_fee` |

Y la línea `LARGE_CAPEX` del reporte no tenía **ninguna** cuenta mapeada.

**Qué es de verdad.** Medido contra producción: `8020` lleva LAS DOS líneas. En
Actual 2026 la cuenta suma `177,804.33` y el P&L del owner la parte en
`CAPITAL_RESERVE 31,326.89` + `LARGE_CAPEX 146,477.44` — que da exactamente lo
mismo. En Actual 2025: `221,403.14` = `-1,082.55` + `222,485.69`. La apertura
existe en el detalle del libro mayor, pero el importador agrega por
`(depto, cuenta)` y se queda con el último nombre que ve: por eso la misma
cuenta aparece como «CAPITAL RESERVE» en `actual_entries` y como «LARGE CAPITAL
EXPENDITURE» en `belowgop_account_entries`.

**La única verdad, entonces:** `8020` = cuenta de capital, y la apertura entre
Capital Reserve y Large Capex entra a nivel **línea del reporte** —el snapshot
importado (`actual_pl_lines`) o el mini-checkbook (`nonop_entries`)—, nunca por
código de cuenta. `LARGE_CAPEX` no tiene regla de cuenta propia porque no puede
tenerla; no es un mapeo faltante. Con solo la cuenta a mano todo cae en
`CAPITAL_RESERVE`, y como las dos viven dentro de `CAPITAL_EXPENSE` el subtotal,
el EBITDA After Capital, el EBT y el Neto salen idénticos.

`ASSET_LOSS` está en la misma situación con la `8040` (Depreciación + Asset
Loss), y ahí sí el GL de CWL no tiene la segunda: se documenta igual.

Esta migración solo escribe la explicación donde se va a leer. El
comportamiento lo fija el código (`pl_engine.NONOP_ACCOUNT_LINE`), que quedó
alineado con `account_mapping` en el mismo commit: hasta ahora decía
8020→mgmt_fee, 8030→capital_reserve y 8045→large_capex, cuando en el GL 8030 son
cargos bancarios y 8045 es diferencial cambiario.

⚠️ `mapping_loader` borra y reinserta todo el reporte desde
`data/formato_mapping_reporte_app.xlsx`. Si alguien lo vuelve a correr, estas
notas se pierden (el comportamiento no). La prueba `tests/test_belowgop_8020.py`
es la que no se pierde.

Revision ID: 093
Revises: 092
"""
from alembic import op
import sqlalchemy as sa

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"

NOTA_8020 = (
    "La 8020 lleva LAS DOS lineas: Capital Reserve y Large Capital Expenditure. "
    "El GL no las separa, asi que la apertura entra a nivel linea (snapshot "
    "importado o nonop_entries). Con solo la cuenta, todo cae aca: ambas viven "
    "dentro de CAPITAL_EXPENSE y el subtotal, el EBITDA After Capital, el EBT y "
    "el Neto no cambian."
)
LOGIC_LARGE_CAPEX = (
    "Sin regla de cuenta a proposito: comparte la 8020 con CAPITAL_RESERVE y el "
    "GL no las separa. Se alimenta a nivel linea (actual_pl_lines o nonop_entries)."
)
LOGIC_ASSET_LOSS = (
    "Sin regla de cuenta: comparte la 8040 con DEPRECIATION y el GL de CWL no "
    "trae cuentas de perdida de activos. Se alimenta a nivel linea si aparece."
)

# valores anteriores, para el downgrade
LOGIC_LARGE_CAPEX_ANTES = "SUM mapped large capital expenditure"
LOGIC_ASSET_LOSS_ANTES = "Include if GL has asset loss accounts"


def _set_logic(line_code: str, logic: str) -> None:
    op.execute(sa.text(
        "UPDATE report_line_config SET calculation_logic = :l "
        "WHERE report_id = :r AND line_code = :c"
    ).bindparams(l=logic, r=REPORT_ID, c=line_code))


def upgrade() -> None:
    _set_logic("LARGE_CAPEX", LOGIC_LARGE_CAPEX)
    _set_logic("ASSET_LOSS", LOGIC_ASSET_LOSS)
    op.execute(sa.text(
        "UPDATE account_mapping SET notes = :n "
        "WHERE report_id = :r AND account_code = '8020'"
    ).bindparams(n=NOTA_8020, r=REPORT_ID))


def downgrade() -> None:
    _set_logic("LARGE_CAPEX", LOGIC_LARGE_CAPEX_ANTES)
    _set_logic("ASSET_LOSS", LOGIC_ASSET_LOSS_ANTES)
    op.execute(sa.text(
        "UPDATE account_mapping SET notes = NULL "
        "WHERE report_id = :r AND account_code = '8020'"
    ).bindparams(r=REPORT_ID))
