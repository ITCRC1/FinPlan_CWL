# Portación FinPlan CWL → Agencia de Tours (Planning + Cash Flow)

> **Documento de handoff.** Se escribió en el proyecto **origen** (FinPlan CWL,
> `C:\FinPlan_CWL`) para llevarse a un proyecto **destino** ya avanzado: una
> **agencia de viajes de tours con flotilla propia y guías especializados**, con
> rutas por toda Costa Rica y **cobro mixto (crédito + contado)**.
>
> **Objetivo:** portar, con toda su profundidad, dos módulos maduros de CWL —
> **Planning** y **Cash Flow Planning** (en todas sus versiones)— y las **mejores
> prácticas de subir/bajar Excel con hojas protegidas para corregir datos**.
> Adaptar el dominio (hotel → tours+flota), **NO** rehacer la arquitectura.

---

## 0. CÓMO USAR ESTE DOCUMENTO (leer primero)

**Para el humano (owner):**
1. Copiá este archivo a la raíz o `docs/` del proyecto **destino** (tours).
2. Asegurate de que el código de referencia de CWL esté accesible en la misma
   máquina: `C:\FinPlan_CWL` (o cloná/agregá el repo `brodriguez7301-dot/finplan-cwl`).
3. Abrí Claude Code en el proyecto destino y pegale: *"Seguí
   `PORTING_TOURS_PLANNING_CASHFLOW.md`. Usá `C:\FinPlan_CWL` como referencia de
   solo lectura. Empezá por la Fase 0 (inventario del destino) y pará para que yo
   confirme el mapeo de dominio antes de escribir código."*

**Para Claude (destino) — reglas de trabajo:**
- **CWL es referencia de solo lectura.** No modificar `C:\FinPlan_CWL`. Leer sus
  archivos para copiar patrones; escribir SOLO en el proyecto destino.
- **El proyecto destino ya está avanzado** → primero **inventariar** qué existe
  (Fase 0) y decidir *adaptar in-place* vs *portar módulo nuevo* por cada tab.
  No duplicar lo que ya haya; no romper lo que funciona.
- **El motor (`engine/`) es Python puro sin dependencias de UI/DB** — mantenerlo
  así (facilita tests y portación). La lógica financiera vive ahí, no en la API.
- **Adaptación = renombrar dominio + cambiar catálogo de cuentas/deptos/revenue
  lines + KPIs.** La MECÁNICA (motor de timing WC, roll de saldos, proyección,
  protección de Excel, source_mode, escenarios, aliases) se copia igual.
- **Cambios materiales (que muevan EBITDA/caja/impuesto): comparar antes/después
  por escenario y confirmar con el owner ANTES de desplegar.**
- **Verificación obligatoria:** tests del motor + `tsc` del front + correr el
  motor contra datos reales antes de dar por bueno.
- **Seguir instrucciones al pie:** no agregar lógica "inteligente" no pedida; el
  owner carga los datos correctos.

**Orden macro:** Fase 0 (inventario destino) → Fase 1 (mapeo de dominio, CONFIRMAR
con owner) → Fase 2 (Planning) → Fase 3 (Cash Flow) → Fase 4 (Excel protegido) →
Fase 5 (verificación + despliegue). Detalle en §7.

---

## 0.1 ESTADO REAL DEL DESTINO — Fase 0 YA EJECUTADA (Luz de Mono, 2026-06-30)

> Se inventarió el proyecto destino (`C:\proyectos\luzdemono`). Esto **reemplaza**
> el trabajo genérico de la Fase 0 — leelo antes de tocar nada.

**Stack: idéntico y compatible** (FastAPI async, SQLAlchemy 2.0 async, PostgreSQL/
asyncpg, Alembic, Next.js 14 App Router + TS, openpyxl, Playwright, Railway/Vercel).
El motor puede seguir siendo Python puro. **Payroll CR (17 conceptos) es IDÉNTICO**
a CWL — no portar.

**⚠️ Diferencias de ARQUITECTURA (impedancia — NO es copy-paste, hay que mapear):**
1. **Escenarios:** Luz de Mono usa el modelo **`Budget`** (`year`, `version`,
   `version_type` ∈ {budget, forecast, actuals}, `is_final`, `actuals_through`), NO
   el **`Scenario`** de CWL. Todo cuelga de `budget_id` (dentro de un `hotel_id`).
   → Al portar, mapear conceptualmente `Scenario` ⇄ `Budget`. `actuals_through` ya
   existe; `source_mode` (imported/checkbook) y `is_current_forecast` NO existen.
2. **Routing / navegación:** anidado **`/hotels/[hotelId]/budgets/[budgetId]/...`**
   con **`Sidebar.tsx`** (grupos: Resumen/Cargar datos/Reportes/Análisis/
   Herramientas/Sistema), NO el top-nav plano de CWL. → Los tabs nuevos se agregan
   al Sidebar DENTRO del budget, respetando el patrón de rutas anidadas.
3. **Motor P&L:** `backend/app/engine/pl.py` con un **`PLResult` dataclass de campos
   fijos** (revenue_rooms, payroll_*, gop, ebitda, net_profit…), **SIN** el patrón
   CWL de `source_mode` / mapeo por `report_line_config` / aliases. → **NO
   refactorizar el P&L para portar el Cash Flow.** El CF solo necesita, por mes:
   Revenue, Operating Expenses, Overhead, Non Allocated y EBITDA-antes-de-capital,
   que `pl.py` YA produce (`total_revenue`, `total_opex_depts`, `total_overhead`,
   `total_nonop`, `ebitda`). El adaptador del Cash Flow mapea esos campos a las
   filas `PL_ROWS` (§5.2) en vez de leer `TOTAL_REVENUES`/`TOTAL_OPEXP` por código.
4. **Multi-industria ya presente:** hay `IndustryTemplate` (hotel/transport/
   construction/restaurant/retail) y **departamentos de transporte YA definidos**
   en `HotelDeptConfig`: `0110 Transporte`, `0120 Tours y Excursiones`, `0140
   Servicios Complementarios`, `0150 Corporativo`, `0170 Otros Ingresos`, `0180
   Admin`, `0190 Ventas/Mercadeo`, `0200 Taller/Flota Indirecta`, `0230 Tecnología`,
   `0240 Propiedad/Terminal`. → **El mapeo de dominio §2 ya está ~50% hecho**;
   ajustar §2 a estos deptos reales en vez de inventar.

**Qué YA TIENE Luz de Mono (NO portar):** P&L USALI (`engine/pl.py`), payroll CR 17
conceptos (`engine/planilla.py`, idéntico), tax + retenciones (`engine/tax.py`),
**cash flow indirecto básico** (`engine/cashflow.py`: DSO/DPO, `CashFlowParams`,
página `/cashflow`), export Excel 7 hojas (`export/excel.py` + `export/styles.py`),
import Excel (`import_excel.py`), paste desde Excel, multi-hotel, `PlanningBoard`
(capacidades/FODA/macro/loans/capex), status flow draft→approved→locked.

**Qué FALTA (portar de CWL) — POR PRIORIDAD:**

- 🥇 **Cash Flow avanzado — el mayor valor y el port más limpio.** Luz de Mono NO
  tiene NADA de esto: **Modelo de timing WC (§5.3)**, **Criterios (§5.1)**, **Cash
  Flow Budget (§5.2)**, **Balance Sheet proyectado (§5.4)**, **Versiones para
  dueños (§5.7)**. El CF indirecto actual se queda como la vista "simple/tradicional"
  (§5.5). Modelos a crear: `cashflow_wc_params`, `cashflow_budget_input/driver`,
  `cashflow_version`, `balance_sheet_line`. **Empezar por acá.**
- 🥈 **Excel PROTEGIDO (§6).** Luz de Mono exporta/importa pero **sin hojas
  protegidas** (`styles.py` tiene colores/formatos pero no `protect_sheet`/`unlock`/
  dropdowns/validación de cuadre/`dry_run`). Portar el patrón de `excel_base.py`
  sobre su `export/styles.py` + agregar `dry_run` a los importadores.
- 🥉 **Planning / Revenue por inventario.** Luz de Mono presupuesta revenue
  **manual en checkbooks**; CWL lo arma por inventario×tarifa×canal×pax
  (`revenue_calculator.py` + models occupancy/rates/channels/pax/packages, que NO
  existen en el destino). Es el port **más grande y el que más adaptación de dominio
  necesita** (rooms→asientos/cupos por salida, ADR→precio por pax, occupancy→
  ocupación por tour). **Evaluar con el owner si el negocio de tours realmente lo
  necesita o si el checkbook alcanza**; si se hace, por etapas.

**Secuencia recomendada para el destino:** (1) Cash Flow avanzado — Criterios →
Cash Flow Budget → Modelo WC → Balance proyectado → Versiones; (2) Excel protegido;
(3) Planning/Revenue por inventario (si el owner lo pide). **El P&L NO se
refactoriza** — solo se mapea su salida mensual al Cash Flow (punto 3 de arriba).

---

## 1. STACK Y ARQUITECTURA A REPLICAR

Idéntico stack que el destino probablemente ya usa (confirmar en Fase 0):

```
Backend:   Python 3.11+ · FastAPI · SQLAlchemy async · PostgreSQL · Alembic
Frontend:  Next.js 14 (App Router) · React · TypeScript · (estilos inline, tema oscuro TradingView)
Deploy:    Railway (backend + DB) · Vercel (frontend)
Tests:     pytest (backend)
Auth:      JWT Bearer en todos los endpoints
```

**Capas (de datos a UI) — el patrón que hace todo esto mantenible:**

```
Modelos ORM (models/*.py)
   └─ tablas por concepto: Scenario, RevenueEntry, PayrollConceptEntry, OpexEntry,
      CostEntry, AllocationEntry, NonOpEntry, CashFlowBudgetInput/Driver,
      CashFlowWCParams, CashFlowParams, CashFlowVersion, BalanceSheetLine, ...
Motor puro (engine/*.py)  ← SIN DB, SIN UI. Recibe dicts/listas, devuelve dicts/listas.
   └─ pl_engine.py         P&L (waterfall Revenue→GOP→EBITDA→EBT→Net)
   └─ cashflow_budget.py   Cash Flow Budget + modelo de timing WC + Balance Sheet proyectado
   └─ cashflow.py          Flujo de caja indirecto (DSO/DPO clásico)
   └─ tax.py               Panorama fiscal (retención tarjeta + renta)
   └─ payroll_calculator / revenue_calculator / cost_calculator / allocation_calculator
Orquestador (engine/recalculate.py)  ← el ÚNICO que toca DB + llama al motor.
   └─ compute_pl_month(scenario, month) decide la RUTA de datos (ver §1.1)
   └─ recalculateScenario() recomputa todo un escenario y persiste snapshots
API (api/*.py)  ← FastAPI: valida payloads, arma dicts para el motor, serializa.
   └─ pl_api.py concentra P&L, cashflow-budget, wc-model, drivers, versions
Frontend (app/**/page.tsx + lib/api.ts)  ← páginas por tab; api.ts tipa cada endpoint.
```

### 1.1 Conceptos transversales que hay que entender antes de tocar nada

- **Escenario (`Scenario`)** = una versión de plan: `type` ∈ {BUDGET, FORECAST,
  ACTUAL}, `year`, `version` ('v1', 'FY', 'actual'…), `source_mode`,
  `actuals_through`, `is_current_forecast`. Todo cuelga de un `scenario_id`.
- **`source_mode` (imported vs checkbook)** — CLAVE:
  - `imported`: el P&L se lee de un **snapshot** subido por Excel (`actual_pl_lines`
    / `actual_entries`). Se muestra tal cual se cargó.
  - `checkbook`: el P&L se **construye desde los auxiliares** de la app (revenue,
    payroll, opex, costs…). Para budgets que se arman dentro del sistema.
  - *Trampa vivida:* un snapshot importado dejado en `checkbook` da **$0** en todo.
- **Rolling forecast (`actuals_through`)** — un FORECAST "vivo" mezcla meses
  cerrados (del ACTUAL vinculado) + proyección; su corte = último mes real. Un
  snapshot **congelado** ya trae el blend horneado → corte = 0 (mostrar tal cual).
- **Aliases / canonicalización de líneas** (`add_pl_aliases`,
  `canonicalize_pl_lines` en pl_engine): el motor emite un vocabulario de códigos
  y el snapshot/reporte usa otro; una capa aditiva garantiza que cada línea exista
  en ambos vocabularios con el mismo valor. **Copiar este patrón** — evita que
  cada consumidor tenga que saber de dónde vino el dato.
- **Recalcular** = recomputar payroll → costos → opex → allocations → P&L →
  snapshots, en orden, para un escenario. Todo lo "calculado" se deriva; el owner
  solo edita inputs.

---

## 2. MAPEO DE DOMINIO — Hotel (CWL) → Agencia de Tours + Flota

> **Fase 1 = CONFIRMAR esta tabla con el owner antes de escribir código.** Es lo
> único que cambia de fondo; el resto es mecánica. Ajustá al catálogo contable
> real del destino (probablemente ya tenga uno).

> ### ⚠️ CUIDADO — LOS DEPARTAMENTOS SON OPCIONES DEL PROVISIONAMIENTO (no hotel)
> Es transporte: **NUNCA sembrar "Rooms" / "F&B" / "Spa" / "Club".** Los
> departamentos deben venir del **template de industria** (`IndustryTemplate`,
> id `transport`) y ser **seleccionables por empresa en el provisioning**, no una
> lista hotelera fija. Luz de Mono YA tiene esto:
> - `backend/app/models/industry.py` → `IndustryTemplate` (por industria:
>   `default_departments`, `pl_structure`, `kpi_definitions`, `account_guide`).
> - `backend/app/models/hotel_config.py` → `HotelDeptConfig` + `ALL_DEPARTMENTS`
>   (ya en **transporte**) + `HOTEL_DEFAULTS = {"LDM": [...]}` (activos por empresa).
>
> **Dos riesgos a blindar:**
> 1. El **`CWL_account_mapping.xlsx`** que se exportó de CWL es **HOTELERO**
>    (Rooms/F&B/Spa/Club). Es **referencia ESTRUCTURAL únicamente** — muestra CÓMO
>    funciona `cuenta + depto → línea de P&L` (operador SUM/SUBTRACT, secciones).
>    **Se RE-EXPRESA sobre los departamentos de transporte; NO se importa tal cual.**
> 2. Hay **dos fuentes de departamentos** (el `ALL_DEPARTMENTS` hardcodeado y el
>    `IndustryTemplate.default_departments`). Para que el provisioning mande de
>    verdad, la selección de departamentos de una empresa debe derivarse del
>    **template de industria elegido al provisionar**, no de una lista global. Si
>    no está unificado, unificarlo (design cleanup) antes de portar el mapeo.
>
> **Regla:** al construir el `account_mapping` de transporte, las líneas de revenue
> son **Transporte / Tours / Servicios Complementarios / Corporativo / Otros**, y
> los códigos de línea del P&L usan vocabulario de transporte (REV_TRANSPORT,
> REV_TOURS…), no REV_ROOMS/REV_FB.

### 2.1 Revenue lines (líneas de ingreso)

| CWL (hotel) | Tours + Flota (propuesto — confirmar) |
|---|---|
| Rooms | **Tours / Excursiones** (por producto/ruta) — el core |
| F&B | **Alimentación en tour** (si aplica; o pass-through) |
| Spa | — (quitar) |
| Tours | **Traslados / Transfers / Shuttle** |
| Laundry | — (quitar) |
| Retail | **Merchandising / tienda** |
| Club / Área rec. | **Charter privado / alquiler de flota** |
| Misc / Other | **Comisiones de reventa (hoteles/actividades de terceros)**, **Paquetes multi-día**, **Servicios de guía** |

### 2.2 Departamentos / centros de costo (LOS REALES de Luz de Mono — del código)

Estos son los departamentos de **transporte** que Luz de Mono YA define en
`HotelDeptConfig.ALL_DEPARTMENTS` (código interno conservado, reetiquetado a
transporte). **Usar estos, seleccionables por empresa en el provisioning — NO los
hoteleros.** El código interno se conserva porque el motor mapea por código.

| Code | Departamento | Grupo |
|---|---|---|
| 0110 | **Transporte** | Revenue |
| 0120 | **Tours y Excursiones** | Revenue |
| 0140 | **Servicios Complementarios** | Revenue |
| 0150 | **Corporativo** | Revenue |
| 0170 | **Otros Ingresos** | Revenue |
| 0180 | **Administración y General** | Overhead |
| 0190 | **Ventas y Mercadeo** | Overhead |
| 0200 | **Taller / Flota Indirecta** | Overhead |
| 0230 | **Tecnología y Sistemas** | Overhead |
| 0240 | **Propiedad / Terminal (POM)** | Overhead |

`HOTEL_DEFAULTS["LDM"]` = los 10 activos por default para la empresa LDM. Al
provisionar otra empresa/industria, la lista de departamentos debe salir del
`IndustryTemplate` correspondiente, no de un hardcode. **Guías y choferes** son
planilla dentro de estos deptos (Tours / Transporte); **flota, combustible,
mantenimiento, llantas, seguros de vehículos** son OPEX/COGS de 0110/0120/0200.

### 2.3 Estructura de costos específica de transporte (nueva vs hotel)

Agregar como cuentas/centros dedicados (no existen en CWL hotelero):
- **Combustible** (variable por km/ruta) — driver clave del cash flow (A/P a proveedores de diésel).
- **Mantenimiento** preventivo/correctivo + **llantas**.
- **Seguros de vehículos**, **marchamo**, **RITEVE** (revisión técnica), **permisos/concesiones**.
- **Peajes** y viáticos de choferes/guías.
- **Depreciación de flota** (CapEx grande — buses/vans; abajo de EBITDA).
- **Guías**: payroll + viáticos + comisiones por tour.

### 2.4 KPIs (reemplazan occupancy/ADR/RevPAR del hotel)

- Pax por tour · ocupación por unidad/asiento · # tours por ruta.
- Revenue por tour / por pax / por unidad.
- **Costo por km**, km recorridos, **utilización de flota** (% días en ruta).
- Margen por ruta/producto.

### 2.5 Drivers de Working Capital para **cobro mixto** (esto define el cash flow)

El modelo de timing de CWL (§5.3) ya soporta la mezcla que necesitás:
- **Contado / tarjeta / prepago (turistas, OTAs, walk-in):** los tours se pagan por
  adelantado → mapean a **anticipos/depósitos** (NRR/Flex/Stay) y a **tarjeta 70%**
  con retención. "Mes de estadía" (hotel) → **fecha del tour**.
- **Crédito (empresas, agencias mayoristas, DMCs):** facturación a 30/60 días →
  **A/R con DSO** (partida `WC_AR`, modo `days`).
- La mezcla `mix_nrr / mix_flex / mix_credit / mix_stay` se calibra por mes con la
  proporción real contado vs crédito del negocio de tours.

---

## 3. MÓDULO PLANNING — tab por tab

Menú "Planning" de CWL (de `frontend/components/TopNav.tsx`). Cada tab = una página
`frontend/app/<ruta>/page.tsx` + endpoints en `backend/app/api/*` + su modelo.
Para cada uno: **qué hace**, **archivos**, **adaptación a tours**.

> Portá los que aporten. El owner del destino pidió *todo Planning*; priorizá los
> que alimentan el Cash Flow (revenue, payroll, opex, costos, allocations).

### Avance
- **Command Center** (`/command`): tablero de avance del presupuesto (qué está
  cargado/validado por escenario). *Adaptación:* mismas validaciones, sobre los
  tabs de tours.

### Presupuesto
- **Budget Big Picture** (`/planning/big-picture`): vista macro del año.

### Setup del año
- **Master Data del año** (`/revenue/master`): parámetros del año (TC, días
  laborales, feriados CR, etc.). *Base de todo.*

### Ingresos (el bloque de revenue — adaptar fuerte a tours)
- **Inventario (Units)** (`/revenue/inventory`): capacidad vendible. Hotel=habitaciones;
  **tours = asientos por unidad / cupos por salida de tour**.
- **Disponibilidad** (`/revenue/availability`): unidades disponibles por mes/día.
- **Noches por Categoría** (`/revenue/room-nights`): → **pax o salidas por producto/ruta**.
- **Rack Rates** (`/revenue/rack-rates`): tarifas base → **precio de tour por producto**.
- **Ocupación** (`/revenue/occupancy`): → **% de ocupación por salida/unidad**.
- **Pax (Huéspedes)** (`/revenue/pax`): pax → se queda (pax por tour).
- **Canales de Venta** (`/revenue/channels`): OTA/directo/agencia → **directo/OTA/mayorista/DMC** (define el mix contado/crédito ⇒ WC).
- **Package Components / Packages** (`/revenue/package-components`, `/revenue/packages`):
  paquetes → **paquetes multi-día de tours** (componentes: transporte+guía+entradas+alimentación).
- **Net Rate** (`/revenue/net-rate`): tarifa neta tras comisión de canal.
- **Spa (capture rate)** (`/revenue/spa`): → quitar o reusar como **add-ons/actividades extra**.
- **Total Revenue** (`/revenue/total-revenue`): consolidado.
- **Checkbook (USD)** (`/revenue/checkbook`): captura de ingreso por línea/mes.
  *Patrón "checkbook"* = grilla editable con **paste desde Excel**, base de casi todos los tabs.

### Planilla (payroll — reusar tal cual, es ley CR)
- **Por Departamento** (`/payroll/checkbook`): headcount + salarios por depto.
- **Reporte FTE** (`/payroll/fte`): FTE por mes.
- **Parámetros** (`/payroll/params`): CCSS, aguinaldo, cesantía, cafetería, etc.
  *17 conceptos de nómina CR — copiar íntegro el `payroll_calculator`.* Los guías y
  choferes son planilla normal CR (aguinaldo 1/12, cesantía, CCSS ~26.83%).

### Costos y gastos
- **Cost of Sales** (`/costs/checkbook`): COGS (Clase 5). *Tours:* combustible por
  ruta, entradas/tickets de terceros, comisiones a mayoristas.
- **OPEX por Dept** (`/opex/checkbook`): gastos operativos 7xxx por depto.
- **Gastos Propietario** (`/nonop/checkbook`): below-GOP (renta, mgmt fees,
  seguros, otros). *Ver §5 — la línea "Non Allocated Expenses" del cash flow sale de acá.*
- **Management Fees** (`/nonop/management-fees`): fees a la administradora.
- **Allocations** (`/allocations/config`): reparto de deptos de servicio
  (cafetería/lavandería) a los demás, neteando a $0. *Tours:* p.ej. repartir
  **taller/mantenimiento** o **combustible de flota** a las rutas que lo consumen.
- **Salary Allocation** (`/allocations/salary`): reasigna salarios de deptos de
  apoyo a las áreas que apoyan, por FTE, con porción % configurable, moviendo el
  **costo cargado** (SW + CCSS + aguinaldo + cafetería). *Tours:* reasignar guías/
  choferes compartidos entre rutas/productos.

### Colaboración
- **Tablero (equipo)** (`/board`) y **Comentarios & Q&A** (`/notes`): colaboración por depto.

**Patrón común de TODA página de Planning** (copiar):
- Grilla `Section · Description · Ene..Dic · Total`, filas **✎ editables con paste
  desde Excel** (`parseClip` por `\t`/`\n`), recálculo en vivo en cliente,
  **selector de escenario/versión**, botón Guardar (PUT que borra-luego-inserta por
  clave), y **exportar/importar Excel protegido** (§6).

---

## 4. ESTADOS FINANCIEROS (contexto para el Cash Flow)

Aunque el foco es Planning + Cash Flow, el Cash Flow **jala** del P&L, así que hay
que tener el P&L funcionando:
- **P&L Full Year** (`/pl/full`), **Simplified** (`/pl/simplified`), **Balance
  Sheet real** (`/pl/balance-sheet`, se SUBE por Excel y valida `Total assets =
  Capital & Liab.`).
- El motor `pl_engine.py` produce el waterfall: Revenue → Operating Expenses →
  Overhead → **GOP** → Non Allocated (below-GOP) → **EBITDA** → CapEx → Financial/
  Depreciación → **EBT** → Tax → **Net Profit**.
- **Regla aprendida (importante):** el "management fee = 3% de ventas" es un driver
  **opt-in**, NO un default. El below-GOP real viene de las cuentas 8xxx. (En CWL
  se mató un "3% fantasma" que inflaba el Non Allocated). Ver
  `docs`/memoria de below-GOP. En tours el below-GOP = renta de instalaciones,
  mgmt fees, seguros, otros — de las cuentas reales, no fórmula.

---

## 5. MÓDULO CASH FLOW PLANNING — el corazón, en profundidad

Menú "Cash Flow Planning" (4 sub-grupos). Todo el motor está en
`backend/app/engine/cashflow_budget.py` (puro) + endpoints en `backend/app/api/pl_api.py`.
Modelos: `cashflow_budget_input.py`, `cashflow_budget_driver.py`,
`cashflow_wc_params.py`, `cashflow_params.py`, `cashflow_version.py`,
`balance_sheet_line.py`. Front: `frontend/app/reports/cashflow-*` + `balance-sheet-projection`.

### 5.1 Criterios del modelo (`/reports/cashflow-criteria`)
Hoja **editable y auditable** con TODOS los parámetros del modelo de WC (§5.3),
agrupados, con **helpers por campo** (explican qué es cada perilla) + la **grilla
de mezcla de pago por mes** (Flex editable, Stay derivado) + toggle **"Modelo
ACTIVO"** + Guardar. Es el panel de control del cash flow.
- Endpoint: `PUT /scenarios/{id}/cashflow-budget/wc-model` (persiste `CashFlowWCParams`:
  `enabled` + `params` JSON).
- *Adaptación:* renombrar perillas al vocabulario de tours (p.ej. "% pago en tour"
  en vez de "StayCash"), pero la mecánica igual.

### 5.2 Cash Flow Budget (`/reports/cashflow-budget`)
La vista principal. Estructura tipo "FULL YEAR CASH FLOW BUDGET":

```
OPERATING PERFORMANCE  (jalado del P&L, NO se edita)
   Revenue                     = TOTAL_REVENUES
   (−) Operating Expenses      = TOTAL_OPEXP
   (−) Overhead Expenses       = TOTAL_OVERHEAD
   (−) Non Allocated Expenses  = TOTAL_NON_OP        ← below-GOP real (8xxx)
   = Subtotal #1  Net Operating Income (NOI = EBITDA antes de capital)
PROJECTS / CAPEX  (input)      → CAPEX_PREV, CAPEX_NEW, CAPEX_SMALL, CAPEX_LARGE
BALANCE SHEET / WORKING CAPITAL (modelo §5.3 o input) → 8 partidas WC (§5.3)
OTHER CASH MOVEMENTS  (input)  → Contribuciones/Distribuciones, Other, FX, House Ledger, Ajuste manual
= Net Change in Cash = NOI + CapEx + WC + Other
Beginning / Ending Cash        → roll mes a mes desde opening_cash
```

Definido en `cashflow_budget.py`: `PL_ROWS`, `CAPEX_ROWS`, `WC_ROWS`, `OTHER_ROWS`,
`compute_cashflow_budget(monthly, inputs, opening_cash, ...)`.
- Endpoints: `GET/PUT /scenarios/{id}/cashflow-budget/` (inputs por `row_key`×mes),
  `PUT .../drivers/` (driver por partida), `PUT .../wc-model`.
- **Anclaje a caja real en meses cerrados:** `compute_cashflow_budget(..., cash_actuals=)`
  agrega la fila **"Ajuste a caja real (meses cerrados)"** (`OTH_RECON`) que fuerza
  la caja final de Ene..corte al banco real (del balance). Meses abiertos
  forecastean desde la última caja real. *Copiar* — evita que el bottom-up se
  despegue de la realidad.
- **WC real en meses cerrados:** `wc_actuals_from_balances(balances, year, through)`
  computa el movimiento REAL de cada partida WC desde el Δ del Balance Sheet y lo
  **superpone** en los meses cerrados (bloquea esas columnas).
- **Drill-down de auditoría:** doble-click en cualquier celda → fuente/cuentas/link.
- Front: grilla con filas input ✎ + **paste de Excel**, recálculo en vivo de
  subtotales/net/caja en cliente, Beginning Cash editable.

### 5.3 Modelo de timing de Working Capital — "si no se entiende esto, todo colapsa"
El diferenciador. Descompone el revenue por **tipo de pago** y hace **rodar los
saldos** de Depósitos / A/R / A/P / Provisiones / IVA con su timing. Todo en
`cashflow_budget.py` (`WC_MODEL_DEFAULTS`, `effective_timing_matrix`, `wc_schedule`,
`compute_wc_model`, `wc_breakdown`).

**Las 8 partidas WC** (`WC_ROWS`): Deposits Received, Deposits Applied, A/P, A/R,
Tax credits/debits, Provisions/reserves, Rent Taxes, Servicio F&B por pagar.

**Modelo de mezcla de pago (el núcleo):** el revenue de cada mes se paga en varios
momentos. Cajas: **NRR** (no reembolsable, cobra por adelantado), **Flex**
(flexible, cobra 1M antes), **Stay** (paga en la fecha del servicio), **Credit**
(queda en A/R, cobra después). Parámetros (`WC_MODEL_DEFAULTS`):

```python
mix_nrr=0.10, mix_credit=0.10, mix_flex=[por mes]   # Stay = 1 − NRR − Credit − Flex
lead_nrr=2, lead_flex=1, lag_credit=1               # timing en meses
retention=0.05                                       # % anticipo retenido (cancelaciones)
card_pct=0.70, card_iva_ret=0.025, card_renta_ret=0.025   # tarjeta CR
service_rate=0.10, service_lag=1                     # servicio 10% ley CR (pass-through)
iva_rate=0.13                                        # IVA CR
ap_same_pct=0.60                                     # A/P: 60% mismo mes, 40% siguiente
payroll_outsourced=True                              # planilla tercerizada lleva IVA/A-P
aguinaldo_monthly=..., aguinaldo_pay_month=12        # aguinaldo se paga en diciembre
growth_y2=0.07                                       # proyección año 2
```

**Matriz de timing 12×6 editable** (`effective_timing_matrix`, offsets −4..+1 meses
respecto a la fecha del servicio): generaliza las cajas; por mes se programa qué %
entra en cada offset. Backward-compatible (si no hay matriz explícita, la deriva de
las cajas). *Clave para estacionalidad* (en CWL, Dic: venta 20–31 se cobra en Oct;
en tours: temporada alta/baja y anticipos de mayoristas).

**Reglas de negocio CR incorporadas** (mantener — son ley/práctica local):
- **IVA 13%** simétrico: `WC_TAX = Δ(IVA por pagar)` con `payable = iva_out − iva_in
  − iva_ret`. Registrar el PAGO neto sin la cobranza = fuga de caja (bug vivido).
- **Tarjeta 70%:** Hacienda retiene 2.5% IVA (crédito mes siguiente) + 2.5% Renta
  (crédito anual). Comisión bancaria va en el P&L (CC Commissions), NO duplicar en WC.
- **Servicio 10%** (A&B): pass-through — se cobra con la venta y se paga a empleados
  `service_lag` meses después. *Tours: propinas/servicio de guía si aplica igual.*
- **A/P 60/40:** 60% se paga el mismo mes, 40% el siguiente.
- **Aguinaldo** se acumula mensual y se paga todo en diciembre.

**Calibración con reales:** `compute_wc_calibration(balances, revenue_by_month, year)`
deriva el % real de cada partida desde el Δ del Balance Sheet ÷ ventas → hint "real
X%" en la hoja de Criterios (clic = usar ese %). El owner ajusta los parámetros a
sus actuales.

### 5.4 Balance Sheet Proyectado (`/reports/balance-sheet-projection`)
`project_full_balance_sheet(anchor_lines, deltas, ...)` + `project_balance_sheet(...)`:
- **Ancla** en el último Balance Sheet REAL subido y **rueda CADA línea 24 meses**
  (WC con el modelo §5.3, utilidad → Patrimonio, **Caja = plug que cuadra**).
- Cuadra `Total assets = Capital & Liab.` cada mes.
- Endpoint `GET /scenarios/{id}/balance-sheet-projection/?months=`.
- *Adaptación tours:* activos fijos = **flota** (depreciación real), inventario =
  combustible/repuestos, A/R = crédito a empresas.

### 5.5 Flujo de Caja indirecto (`/reports/cashflow`)
Método indirecto clásico (`cashflow.py`): EBITDA + Δ A/R (DSO) + Δ A/P (DPO) +
impuesto + inversión (CapEx) + financiamiento (deuda/intereses/distribuciones). Es
la versión "simple/tradicional" que convive con el Cash Flow Budget (§5.2).

### 5.6 Panorama Fiscal (`/reports/tax`)
`tax.py`: retención de tarjetas por mes (crédito) + liquidación de renta anual (30%
del EBT). *Tours: igual — el 2.5% de tarjeta y la renta 30% aplican igual en CR.*

### 5.7 Versiones (Dueños) (`/reports/cashflow-versions`) — plano/congelado
Feature para **archivar y comparar** las versiones de cash flow presentadas a los
dueños, **desconectadas del motor** (foto congelada). Modelo `CashFlowVersion`
(`hotel_id`, `name`, `order_idx`, `rows` JSON, `kind` ∈ {frozen, working}).
- Importador `cashflow_version_importer.py` (`parse_cashflow_version`): parsea el
  Excel formato **Section · Description · Ene..Dic · Full Year** (localiza el header
  por la celda "Description"; tolera posición, paréntesis, comas, `$`).
- Endpoints: `GET /cashflow-versions/?hotel_id=`, `GET /{id}/`,
  `POST /cashflow-versions/import/?name=&hotel_id=&order_idx=&dry_run=` (multipart),
  `POST /cashflow-versions/working/?scenario_id=&name=` (copia editable del cash
  flow vivo), `PUT /{id}/`, `DELETE /{id}/`.
- Página: 3 modos — **Ver versión** (12 meses), **Comparar** (V1 | V2 | Current
  vivo, con Δ vs base, períodos Full Year/Mes/YTD; orden = UNIÓN de filas para que
  ninguna partida se caiga), **Por línea** (una línea × meses × versiones).
  "Working" = copia plana editable con recálculo formulado (subtotales/Net/roll de
  caja desde las líneas input).
- *Adaptación:* directo, sin cambios de dominio (es una capa de comparación).

---

## 6. EXCEL: SUBIR / BAJAR PARA CORREGIR — hojas PROTEGIDAS (mejores prácticas)

El patrón de CWL para "bajo un Excel, lo corrijo, lo vuelvo a subir" con hojas
protegidas. Base: `backend/app/export/excel_base.py` (openpyxl).

**Bajar (export) — hoja protegida con solo las celdas de input editables:**
```python
from app.export.excel_base import (
    protect_sheet, unlock, add_dropdown, fill, font, border, align,
    month_header_row, set_col_widths, workbook_to_bytes, SHEET_PASSWORD,
)
# 1) Escribir estructura (headers, fórmulas, totales) → quedan LOCKED por default.
# 2) En cada celda de captura:  unlock(cell)   # la vuelve editable
# 3) Validaciones in-cell:      add_dropdown(ws, "B", 5, 200, ["Directo","OTA","Mayorista"])
# 4) protect_sheet(ws)          # activa protección; contraseña SHEET_PASSWORD
# 5) return workbook_to_bytes(wb)  # como StreamingResponse .xlsx
```
- **Solo las celdas `unlock()` se pueden editar**; el resto (fórmulas, totales,
  encabezados) queda bloqueado → el owner no rompe la estructura al corregir.
- Colores/estilo por tipo de celda (input amarillo, total verde, header navy) →
  paleta `C` en `excel_base`. Dropdowns para catálogos (deptos, canales, cuentas).
- Password compartida (`SHEET_PASSWORD`) — cambiar por proyecto.

**Subir (import) — parsear, validar, previsualizar, commitear:**
- Cada importador vive en `backend/app/importers/*.py` y expone un
  `parse_*(file/bytes) -> filas` + un endpoint que acepta **multipart** con
  **`dry_run`**: primero devuelve un preview (qué se va a cargar, totales, errores)
  y solo commitea si `dry_run=false`.
- **Validación de cuadre** (ejemplo `balance_sheet_importer`): rechaza si
  `Total assets ≠ Capital & Liab.`. Replicar validaciones de integridad por hoja.
- **Localización tolerante del header** (ej. `cashflow_version_importer` busca la
  celda "Description") → robusto ante que el owner mueva filas/columnas.
- Merge inteligente: cargar por clave (scenario, row_key, month) con
  borra-luego-inserta, sin pisar lo que el archivo no trae.

**Paste directo desde Excel (sin archivo):** además del import de archivo, todas
las grillas del front aceptan **pegar un bloque copiado de Excel** (`parseClip`
divide por `\t`/`\n`) → carga rápida celda a celda. Es el camino diario; el Excel
protegido es para correcciones masivas/offline.

**Regla de oro:** nunca sobreescribir un archivo fuente del owner. En CWL hay un
`data/Budget 2025W upload.xlsx` que es **intocable**. Definí y respetá los archivos
"solo lectura del owner" en el destino.

---

## 7. PROCESO DE REDISEÑO — fases y verificación

**Fase 0 — Inventario del destino (sin escribir código).**
- Mapear qué módulos/tabs ya existen en el proyecto tours y cuáles de §3/§5 faltan.
- Confirmar stack (FastAPI/SQLAlchemy async/Next 14) y que el motor sea puro.
- Decidir por tab: *adaptar in-place* (ya existe algo) vs *portar de CWL* (no existe).
- Entregable: una lista "tab → acción (adaptar/portar/omitir)".

**Fase 1 — Mapeo de dominio (CONFIRMAR con owner).**
- Llenar la tabla §2 con el catálogo real de cuentas/deptos/revenue lines de tours.
- Definir el mix contado/crédito por línea (⇒ parámetros del modelo WC §5.3).
- Entregable: catálogo de cuentas + deptos + revenue lines aprobado.

**Fase 2 — Planning.**
- Portar/adaptar revenue (inventario→cupos, rack→precio de tour, canales, pax),
  payroll (íntegro, es ley CR), costos/opex (agregar combustible/mantenimiento/
  llantas/seguros de flota), allocations, salary allocation.
- Verificar: cada grilla guarda, pega de Excel y recalcula; el P&L cuadra.

**Fase 3 — Cash Flow (en este orden).**
1. Criterios del modelo (parámetros WC) — con vocabulario de tours.
2. Cash Flow Budget (Operating del P&L + CapEx/WC/Other, roll de caja, anclaje real).
3. Modelo de timing WC (§5.3) — calibrar con reales del negocio de tours.
4. Balance Sheet proyectado (anclar en balance real; flota como activo fijo).
5. Flujo indirecto + Panorama fiscal.
6. Versiones (Dueños) — comparador congelado.

**Fase 4 — Excel protegido (subir/bajar).**
- Export protegido por cada hoja de captura + importadores con `dry_run` + validaciones.

**Fase 5 — Verificación y despliegue.**
- `pytest` del motor (portar y adaptar los tests de CWL: payroll CR, waterfall P&L,
  cash flow, WC model). `tsc` del front sin errores.
- Correr el motor contra un escenario real y revisar: P&L cuadra, cash flow rueda,
  Balance proyectado cuadra `activos = pasivo+patrimonio`.
- **Cambios materiales → antes/después por escenario + OK del owner antes de push.**
- Migraciones Alembic incrementales; nunca romper datos existentes.

**Checklist de "un tab bien portado":**
- [ ] Modelo ORM + migración.  [ ] Motor puro con test.  [ ] Endpoint GET/PUT.
- [ ] `lib/api.ts` tipado.  [ ] Página con grilla editable + paste + selector de
  escenario + Guardar.  [ ] Export/Import Excel protegido (si aplica).
- [ ] Vocabulario de tours (no quedaron "rooms"/"spa"/"ADR").
- [ ] Verificado con datos reales.

---

## 9. MÓDULOS ADICIONALES A PORTAR (seleccionados por el owner)

Además de Planning + Cash Flow, se priorizaron dos bloques de CWL de alto valor.

### 9.A — P&L CONFIGURABLE (mapping-driven) + source_mode + forecast rolling

**Por qué:** habilita que **departamentos y líneas de P&L sean DATOS por industria**
(no código) → es la pieza que hace de verdad configurable el provisioning (§2 ⚠️),
y permite un **forecast "vivo"** que mezcla meses reales + proyección.

**Qué tiene CWL (vs el `pl.py` de campos fijos de Luz de Mono):**
- **`report_line_config`** (tabla): define CADA línea del P&L como fila —
  `line_code`, `line_name`, `section`, `line_type` (MAPPED / CALCULATED / HEADER /
  KPI), `display_order`, `calculation_logic` (fórmula tipo `SUM(x) + y − z`),
  `parent_line_code`. El waterfall completo es data, no `if/else`.
- **`account_mapping`** (tabla): `(account_code, dept_code) → report_line_code` con
  `rollup_operator` (SUM/SUBTRACT), `active_status`, `section`. (Es el
  `CWL_account_mapping.xlsx` que se exportó — 789 filas, HOTELERO, re-expresar).
- **Motor** `pl_engine.py`: `calculate_pl_from_mapping(acct_rows, mappings,
  report_lines, seeds)` acumula por línea y evalúa las CALCULATED con
  `_eval_calc_logic`. `calculate_budget_pl_from_mapping(...)` para budgets desde
  checkbook. **`add_pl_aliases` / `canonicalize_pl_lines`**: capa aditiva que
  garantiza que cada línea exista en ambos vocabularios (motor / report_line_config)
  con el mismo valor — copiar, evita que cada consumidor sepa el origen del dato.
- **`source_mode` (imported / checkbook)** en el escenario: leer snapshot subido vs
  construir desde auxiliares. **`actuals_through`** + **`is_current_forecast`**:
  el forecast vivo computa Ene..corte del ACTUAL vinculado y proyecta el resto
  (`recalculate._compute_pl_month_core`). Un snapshot congelado va con corte 0.

**Adaptación a Luz de Mono (impedancia — hacer por etapas, NO romper `pl.py`):**
1. Crear tablas `report_line_config` + `account_mapping` (migración Alembic) y
   **sembrarlas desde el `IndustryTemplate` de transporte** (líneas REV_TRANSPORT/
   REV_TOURS/…, deptos 0110/0120/0200/…), NO hotel. El seed sale del template →
   el provisioning manda.
2. Agregar un **motor `pl_engine` mapping-driven** (portar `calculate_pl_from_mapping`
   + `_eval_calc_logic` + aliases) como camino ALTERNO; mantener `pl.py` como
   fallback hasta paridad. Reconciliar contra el P&L viejo antes de cambiar el default.
3. Extender el modelo `Budget` con `source_mode` e `is_current_forecast` (ya tiene
   `actuals_through`). Portar el blend rolling de `_compute_pl_month_core`.
4. **Verificación:** correr ambos motores sobre el mismo budget y comparar línea a
   línea (deben coincidir) antes de exponer el nuevo. Cambios materiales → OK owner.

### 9.B — OPERATION INSIGHT + COMMAND CENTER + KPIs de transporte

**Headcounts** (`/operation-insight/headcounts`): tabla por depto **HC · FTE ·
Costo anual** con Δ y Var% entre Actual/Budget, + **vista mensual** (HC/FTE/Costo ×
12 meses). Frontend puro sobre el reporte de planilla por depto
(`GET /payroll/{id}/dept-report/` y `/dept-report-monthly/`). *Luz de Mono ya tiene
payroll por depto → port casi directo.*

**Ops KPI** (`/operation-insight/ops-kpi`): tablero **manual** por escenario —
`kpi · target · actual · responsable · acción` (modelo `OpsKpiEntry`, GET/PUT,
grilla editable con paste + agregar/borrar filas). Cero dependencia de dominio →
port directo. *Tours:* metas operativas (puntualidad de salidas, NPS, incidentes de
flota, ocupación media por salida…).

**Command Center** (`/command`): tablero de **avance/validaciones del presupuesto**
— qué está cargado y cuadra por escenario (revenue, planilla, opex, allocations,
below-GOP). Luz de Mono tiene `PlanningBoard` (más simple) → extender con las
validaciones de completitud/cuadre de CWL.

**KPIs de transporte** (motor nuevo, reemplaza occupancy/ADR/RevPAR): definir en el
`IndustryTemplate` (id `transport`, `kpi_definitions`) — cuentas 9xxxx de estadística
+ fórmulas. Propuesta:
- **Km recorridos** (9xxxx) · **Utilización de flota** = días-en-ruta / días-flota.
- **Pax por tour** · **Ocupación media por salida** = pax / capacidad.
- **Costo por km** = costos de flota / km · **Revenue por pax** · **Margen por ruta**.
Reusa el patrón `engine/kpis.py` (Luz de Mono ya lo tiene hotelero) → cambiar las
definiciones por las de transporte del template. *El motor lee KPIs del template
cuando `industry_type != 'hotel'` — ya está previsto en `industry.py`.*

---

## 8. GLOSARIO — reglas de negocio CR (comunes a hotel y tours)

- **Aguinaldo** = SW × (1/12) mensual; se PAGA en diciembre.
- **Cesantía/preaviso** = SW × (tasa_anual/12) provisión mensual.
- **Vacaciones** = SW × (2/52).
- **CCSS patronal** ≈ 26.83% (SEM+IVM+BP+INS+IMAS+INA+ASFA+FONATEL).
- **IVA 13%** débito/crédito, liquidación mensual (paga la diferencia).
- **Retención tarjeta**: 2.5% IVA (crédito mes siguiente) + 2.5% Renta (crédito anual).
- **Renta** 30% del EBT positivo, liquidación anual (~marzo del año siguiente).
- **Servicio A&B/guía** 10% de ley: pass-through, no es ingreso, se paga al personal.

---

## Referencia rápida — archivos clave en CWL (`C:\FinPlan_CWL`)

```
Motor cash flow:   backend/app/engine/cashflow_budget.py   ← el corazón (§5.3)
                   backend/app/engine/cashflow.py          ← indirecto (§5.5)
                   backend/app/engine/tax.py               ← fiscal (§5.6)
Motor P&L:         backend/app/engine/pl_engine.py         ← waterfall + aliases
Orquestador:       backend/app/engine/recalculate.py       ← rutas de datos, recalc
API cash flow:     backend/app/api/pl_api.py               ← cashflow-budget, wc-model, versions
Excel base:        backend/app/export/excel_base.py        ← protect_sheet/unlock/dropdown (§6)
Importadores:      backend/app/importers/*.py              ← dry_run + validación
Modelos CF:        backend/app/models/cashflow_*.py, balance_sheet_line.py
Front cash flow:   frontend/app/reports/cashflow-budget|criteria|versions|cashflow/
                   frontend/app/reports/balance-sheet-projection/
Navegación/tabs:   frontend/components/TopNav.tsx          ← inventario de todos los tabs
API tipada:        frontend/lib/api.ts
```
```
Migraciones:       backend/alembic/versions/   (CWL va por la 066; portar el patrón, no los números)
```
```
Reglas below-GOP:  ver la memoria/doc de "Non Allocated Expenses" — mgmt fee es opt-in, no 3% default.
```
