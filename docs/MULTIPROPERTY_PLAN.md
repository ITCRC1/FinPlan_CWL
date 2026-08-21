# Plan Multi-Propiedad — SUPERSEDIDO (2026-08-17)

> ⚠️ **Este documento describe un modelo que el owner NO eligió.** Asume una
> sola app sirviendo a las cuatro propiedades (selector de hotel, control de
> acceso por usuario, `POST /api/hotels/`). El owner, consultado directamente
> (2026-08-17): **«un FinPlan por propiedad»** — el mismo patrón que ya usa en
> CRC Ops Manual, Daily-Ops y CWL-Tarifario: cada propiedad es un despliegue
> Railway+Vercel aparte, con su propia base. No multi-tenant en una sola base.
>
> **Ese modelo ya está construido.** Ver `app/hotel_actual.py`: la identidad
> del hotel sale del entorno (`HOTEL_ID`), no de una tabla ni de un selector.
> Los ~20 literales `'CWL'` que este plan quería sacar del código **ya se
> sacaron** — verificado 2026-08-17, lo único que queda son comparaciones
> correctas contra `HOTEL_ID` en `seed.py`, no lookups que lo ignoren.
>
> **Abrir Amarena/Oxígen/Ojochal es un ejercicio de despliegue, no de
> código:** Railway + Vercel nuevos, `HOTEL_ID=AMA` (o el que corresponda),
> `alembic upgrade head` contra una base vacía, sembrar. El mismo playbook de
> siempre. No hace falta selector de hotel, no hace falta `POST
> /api/hotels/`, y no hace falta control de acceso por hotel — cada base
> tiene un solo cliente, así que no hay nada que fugar entre propiedades.
>
> **Este documento queda como referencia histórica** de la opción que se
> evaluó y no se tomó. Si en algún momento el owner decide centralizar las
> cuatro propiedades en una sola app, las 8 fases de abajo siguen siendo el
> mapa — pero es una decisión nueva, no la que está vigente hoy.
>
> Ver `docs/PENDIENTES.md` — B6.5 quedó cerrado bajo este mismo criterio.

---

## Lo que sigue es EL PLAN VIEJO, sin actualizar desde 2026-06-29

> **Estado:** PLANIFICADO. No iniciado. **Y no se va a iniciar salvo que el
> owner cambie de opinión sobre el modelo de despliegue** (ver arriba).
> **Fecha:** 2026-06-29 · **Base:** auditoría de arquitectura (workflow 5 agentes) + decisiones del owner.
> **Pregunta que origina este plan:** *"si encuentro un error en los reportes que afecta a todas las propiedades, ¿cómo se copia ese cambio?"*
> **Respuesta corta:** **No se copia — no hay nada que copiar.** Reportes = capa compartida (arreglás 1 lugar, aplica a todas). Las propiedades difieren solo en sus DATOS.

---

## 0. Decisiones cerradas (owner, 2026-06-29)

| # | Decisión | Valor | Implicación |
|---|----------|-------|-------------|
| M1 | Catálogo de cuentas / estructura USALI | **Mismo para todas** (AMA/OXI/OJO adoptan los códigos de depto/cuenta de CWL) | El mapeo compartido vale tal cual → "arreglar una vez" funciona perfecto |
| M2 | `account_mapping` / `report_line_config` | **Totalmente compartido (1 set, sin `hotel_id`)** | Un arreglo de mapeo se propaga solo. NO agregar overrides hasta que una divergencia real lo obligue |
| M3 | Control de acceso por hotel | **Sí, antes de go-live** | Hoy `User` no tiene `hotel_id` → todos ven todo. Bloqueante de lanzamiento |

---

## 1. El modelo de propagación de arreglos (núcleo)

Tres categorías de "cosa que puede tener un error", cada una con su regla:

### (a) Lógica del reporte — código compartido
- **Qué:** `pl_engine.py` (`calculate_full_pl`, cadena GOP→EBITDA→tax, `_eval_calc_logic`), `tax.py`, `cashflow.py`, `cashflow_budget.py`, `payroll_calculator.py`, `revenue_calculator.py`, `cost_calculator.py`, `allocation_calculator.py`. **Funciones puras, cero parámetros `hotel_id`.**
- **Cómo se arregla:** editás la función + tests (pytest patrón `test_pl_chain`/aguinaldo/severance de CLAUDE.md) + redeploy backend a Railway.
- **Propagación:** **AUTO a todas** al recalcular. Como hay UNA sola copia del código, no existe el riesgo "lo arreglé en CWL, me olvidé de Amarena".

### (b) Mapeo canónico — config compartida (HOY, y se mantiene así por M2)
- **Qué:** `account_mapping` (cuenta→línea, `sign_rule`, `rollup_operator`) y `report_line_config` (orden de líneas, secciones, `calculation_logic`). Claveadas por `report_id='P&L_DETAIL_OWNERS'`, **sin columna `hotel_id`** (`app/models/mapping.py:5,25`). Cargadas sin filtro de hotel (`app/engine/recalculate.py:245-281`).
- **Cómo se arregla:** una fila en BD vía `PUT /mapping/accounts/{id}/` (`mapping_api.py:146`) o el loader bulk. **Sin redeploy.** Stage con `active_status='REVIEW'`, revisar `/mapping/unmapped/`, flip a `'YES'`.
- **Propagación:** **AUTO a todas.** Una propiedad que no usa esa cuenta aporta $0 → inofensivo.

### (c) Datos de la propiedad — por-hotel, nunca tocados por un arreglo de reporte
- **Qué:** `scenarios` (`hotel_id` es FK real, `scenario.py:20`), checkbooks (opex/cost/revenue/nonop), payroll positions+params, rate_card/occupancy/packages, allocation configs, exchange_rate, actual_entry, balance_sheet_lines.
- **Propagación:** **NINGUNA — correcto.** Un arreglo de lógica/mapeo cambia cómo se agrega/muestra el dato, nunca reescribe el dato. Un número mal tipeado en Oxígen se arregla solo en Oxígen.

### Cómo se propaga un arreglo, según el caso real

| Escenario | Qué hacés | ¿Toca otras propiedades? |
|-----------|-----------|--------------------------|
| **Bug de cálculo** (GOP/EBITDA/mgmt-fee%/tax 30%/aguinaldo) | Editar función pura en el engine + tests + redeploy | **SÍ, a propósito** — todas recalculan bien |
| **Regla de mapeo errada** (cuenta a línea equivocada) | Update 1 fila en BD (sin deploy), stage REVIEW→YES | **SÍ, automático** — 1 fila maneja todas |
| **Ajuste de UNA propiedad** (mgmt-fee%, mes cerrado, depto propio) | Cambiar solo el `Hotel` row o el scenario de esa propiedad. **NUNCA** `if hotel_id=='OXI'` en el engine ni literal en el mapeo compartido | **NO — y no debe** |

---

## 2. Inventario: compartido vs por-hotel vs hardcodeado a CWL (estado actual)

### ✅ Compartido (un arreglo aplica a todas)
- Motor de cálculo: `pl_engine.py`, `tax.py`, `cashflow.py`, `cashflow_budget.py`, `payroll_calculator.py`, `revenue_calculator.py`, `cost_calculator.py`, `allocation_calculator.py` — puros, sin `hotel_id`.
- `account_mapping` — clave `(report_id, source_department, account_code, source_origin)`, **sin `hotel_id`**.
- `report_line_config` — clave `(report_id, line_code)`, **sin `hotel_id`**.
- Loaders `load_active_account_mappings`/`load_report_line_config` — filtran solo por `report_id`.
- Catálogo de cuentas USALI (`account.py`) y `PayrollAccount` — singletons globales.

### 🔵 Por-hotel (DATA — nunca tocada por un arreglo de reporte)
- `Scenario` (`hotel_id` FK real) — la clave de partición de todo.
- Checkbooks: `opex_entry`, `cost_entry`, `revenue_entry`, `nonop_entry`, `revenue_account_entry`, `belowgop_account_entry` (`scenario_id` CASCADE + `hotel_id` index).
- `PayrollPosition` + `PayrollParams` (rates por escenario).
- Drivers: `rate_card`, `occupancy_budget`, `sales_channel_config`, `package_config`, `spa_budget`, `scenario_stat`.
- Config/output por escenario: `balance_sheet_lines`, `allocation_entry`, configs de cafetería/lavandería, `pl_lines`, `actual_entry`, `exchange_rate`.
- `Hotel` (rooms, tc_usd_default, closed_months, pax_per_night) + `RoomTypeConfig` (FK real).

### 🟠 Hardcodeado a CWL (lo que hay que SOLTAR)
- **`pl_engine` dept→grupo** (`:42-116`): embebe deptos solo-CWL (INNOCEANA 0155, CROWTHER 0156, CLUB 260, AREC 270). Hotel con códigos distintos → todo cae en `FALLBACK_OVERHEAD_GROUP` sin error.
- Mapa de rangos revenue 4xxx (`:226-243`), `ACTUAL_EXCLUDED_DEPTS={'0220'}`, `ALLOCATION_ACCOUNTS={'4900','4999'}`, `NONOP_ACCOUNT_MAP` (marcado PROVISIONAL), `CHECKBOOK_DEPT_CONSOLIDATION` — constantes del chart de CWL.
- `cashflow_budget` `WC_MODEL_DEFAULTS`: `_DEFAULT_FLEX` (estacionalidad Feb/May/Ago/Nov), IVA 13%, tarjeta 70%, retenciones 2.5%, aguinaldo mes=12, growth_y2=7%; y `_BS_LINE_MAP`/`_BS_GRAND` (strings de balance en ES/EN del upload de CWL).
- `allocation_calculator`: cafetería hardcodea dept '0220' + cuenta 6025; defaults (laundry `DEFAULT_KILOS`, cafetería `REMOTE_DEPTS={'0191','0192','0200'}`) asumen deptos CWL.
- `revenue_calculator` `CALENDAR_DAYS` ignora `Hotel.closed_months` (octubre de CWL debe expresarse como DATA, no código).
- **Provisioning:** `seed.py` hardcodea `Hotel(id='CWL', rooms=30, tc=530)` + 6 room types; **no hay `POST /api/hotels/`**; `scenarios_api.py:92-116` hace `db.get(Hotel,'CWL')` literal; ~15 defaults 'CWL' en backend; **76 literales 'CWL' en 60 archivos** frontend; `TopNav.tsx:347` pill estático sin handler; CORS fijo a `finplan-cwl.vercel.app` (`main.py:28`).

---

## 3. Pasos de fundación (orden seguro)

> Principio: **nunca duplicar la capa de reportes.** Solo (1) blindar lo compartido, (2) soltar lo CWL-hardcodeado a config DB-driven, (3) sembrar DATA por propiedad.

| # | Paso | Por qué | Esfuerzo |
|---|------|---------|----------|
| 1 | **Blindar "mapeo compartido"** — NO agregar `hotel_id` a `account_mapping`/`report_line_config`. Nota en CLAUDE.md + comentario en `mapping.py` | ES la respuesta a la preocupación del owner; evita que un dev futuro lo parta por-hotel y destruya el "arreglar una vez" | Trivial (decisión+doc) |
| 2 | **`hotel_id` obligatorio end-to-end** — quitar ~15 defaults 'CWL' (`scenarios_api.py:69/93/110/116`, `mapping_api.py:176`, `big_picture_api.py:72/94`, `pl_api.py:909/979`, `actuals_api.py:122`) + defaults de columna (`big_picture_version.py:18`, `cashflow_version.py:19`); validar que el hotel existe. De-hardcodear `get_hotel`/`get_room-types` que hacen `db.get(Hotel,'CWL')` | Todo cuelga de un `hotel_id` real; un default 'CWL' silencioso estamparía el hotel equivocado en filas de Amarena | Medio (mecánico) |
| 3 | **Provisioning parametrizado** — `provision_hotel(id,name,rooms,room_types,closed_months,tc)` + `POST /api/hotels/`. Reusar `POST /hotels/{id}/room-types/`. Sembrar CWL llamándolo; AMA/OXI/OJO igual. Cargar el mapeo compartido UNA vez, nunca por hotel | Hoy no hay create-hotel; solo `seed.py` hardcodea CWL | Medio |
| 4 | **dept→grupo de constantes a tabla DB** (`dept_group_config`: filas default compartidas + override opcional por `hotel_id`). Pasar el mapa al engine como argumento (mantiene puro/testeable). Cubre `OPERATING/OVERHEAD_DEPT_GROUPS`, `GROUP_NAMES`, `ACTUAL_EXCLUDED_DEPTS`, `CHECKBOOK_DEPT_CONSOLIDATION` | Hoy es código compartido pero embebe deptos CWL; sin esto cada hotel con depto nuevo fuerza editar código compartido (riesgo de desviar CWL). Como M1=mismo catálogo, los defaults compartidos alcanzan; el override queda para divergencias reales | Medio-alto |
| 5 | **Sembrar DATA por propiedad** — escenarios, room types, occupancy, costos, payroll, nonop, exchange rates, allocation configs (con kilos/participación PROPIOS, no los de CWL). REUSAR mapeo+motor compartidos | Acá se construyen Amarena/Oxígen/Ojochal, montadas 100% en la lógica+config compartida | Data entry recurrente |
| 6 | **Frontend hotel activo** — `HotelProvider`+`useHotel`, cablear el pill (`TopNav.tsx:347`), reemplazar ~76 literales 'CWL' + defaults en `lib/api.ts` (1424/1845/1854/1864). Calls de mapeo siguen hotel-agnósticas | `api.ts` ya pasa `hotelId` como parámetro en casi todo → es mayormente reemplazo de literales + selector | Medio |
| 7 | **Control de acceso por hotel (M3)** — membresía `User`↔hotel, scoping de colaboración/secciones por hotel | Hoy todo usuario ve todo; abrir Amarena expondría sus finanzas a usuarios de CWL. Bloqueante de go-live | Medio |
| 8 | **Tests del motor multi-forma** — fixtures de ≥2 formas de hotel (CWL-con-Innoceana/Crowther y un hotel vanilla rooms+F&B) | Garantiza que un arreglo futuro no quede afinado a CWL sin querer — el único riesgo real con una sola copia de código | Bajo-medio |

**Orden recomendado:** 1 (decisión) → 2 → 3 → 4 → 5 (ya se puede empezar a cargar Amarena) → 6 → 7 (antes de go-live) → 8 (en paralelo).

---

## 4. Riesgos

1. **El "arreglar una vez" se sostiene SOLO mientras el mapeo siga compartido.** Si alguien agrega `hotel_id` a las tablas de mapeo (o una propiedad necesita un mapeo distinto), un arreglo habría que re-aplicarlo N veces y las filas por-hotel chocarían con las unique keys actuales. → decisión guardada (M2).
2. **Supuestos CWL en código compartido** (`pl_engine` dept→grupo, rangos 4xxx, `ACTUAL_EXCLUDED_DEPTS`, `NONOP_ACCOUNT_MAP`) mis-clasifican silenciosamente un hotel con códigos distintos (cae en `FALLBACK_OVERHEAD_GROUP` sin error). Mitiga el paso 4 + M1 (mismo catálogo).
3. **`cashflow_budget` estacionalidad `_DEFAULT_FLEX`** y los strings ES/EN de `_BS_LINE_MAP` son forma-CWL; otra propiedad con otra estacionalidad/upload mis-mapearía. Los params de timing son overridables por escenario, pero la estacionalidad default y el match de labels de BS no salen de data del hotel.
4. **~15 defaults 'CWL' backend + 76 literales frontend** pueden rutear silenciosamente a CWL si un caller omite `hotel_id` — benigno hoy, peligroso apenas exista Amarena (ej. estampar 'CWL' en filas de Amarena). Lo resuelve el paso 2.
5. **Sin control de acceso `User`↔hotel** (paso 7 / M3): abrir Amarena expone su data a todo usuario de CWL hasta agregar scoping.
6. **`revenue_calculator` ignora `Hotel.closed_months`**: una propiedad con meses cerrados distintos a octubre de CWL debe forzar el cierre vía DATA (occupancy 0 / `ScenarioStat`), o `rooms_available` queda mal por construcción.
7. **Defaults de allocation** (laundry `DEFAULT_KILOS`, cafetería `REMOTE_DEPTS`, dept '0220'/cuenta 6025) asumen deptos CWL — un hotel nuevo heredaría defaults equivocados salvo que se provisione con los suyos.

---

## 5. Resumen ejecutivo

- **No se copian arreglos de reporte** — la lógica es código compartido (1 lugar + deploy) y el mapeo es config compartida (1 fila, sin deploy). Las propiedades difieren solo en DATA. Eso es exactamente lo que el owner quería: arreglar una vez, corregir en todas.
- **Lo que se protege:** mantener el mapeo compartido (M2) — es una decisión a blindar, no un hueco.
- **El trabajo real** no es duplicar reportes; es soltar lo hardcodeado a CWL (dept-grupos a DB, quitar literales 'CWL', provisioning parametrizado) y agregar control de acceso por hotel antes de abrir.
- Con M1 (mismo catálogo USALI) + M2 (mapeo compartido), Amarena/Oxígen/Ojochal se montan sobre el mismo motor+mapeo; solo cargan su propia DATA.
