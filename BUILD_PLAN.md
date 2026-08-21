# FinPlan CWL — Plan de construcción

> Orden derivado de `REPORTES_SPEC.md` (estructura 7 tabs + biblioteca de reportes).
> Principio: primero primitivas del motor (invisibles, desbloquean todo), luego lo visible
> de mayor impacto, reorganización de nav al final. Cada fase se despliega sola sin romper
> lo vivo. Estado: ⬜ pendiente · 🔨 en curso · ✅ hecho.

## Fase A — Primitivas del motor (backend, bajo riesgo) · base de todo
- ✅ **A1** — PAR (Per Available Room) / POR (Per Occupied Room) por línea del P&L. `pl_engine.par_por()` (pura, testeada) + aplicada en `/pl/.../month/` y `/pl/.../monthly/` (cada línea trae `par`/`por`; respuesta monthly trae `annual_kpis`). 4 tests nuevos (match exacto vs reporte real). Desbloquea P&L YTD, Full P&L, Summary.
- ✅ **A2** — Agregación YTD / Full Year. `_monthly_results` (computa los 12 meses una vez) + `_aggregate(monthly, through)` (suma ene→mes con PAR/POR sobre KPIs acumulados + corrección de impuesto) + `_apply_tax_correction`. Endpoint nuevo `/pl/{id}/ytd/{month}/`. `get_pl_monthly` refactorizado para reusar (mismo output). 4 tests nuevos. Desbloquea todos los reportes.
- ✅ **A3** — Revenue por tipo de habitación. `revenue_calculator.room_type_breakdown()` (puro: units/nights/occ/revenue/adr/pax por tipo y mes) + endpoint `/scenarios/{id}/revenue/by-room-type/` (meses + anual con % del total). 3 tests (match real Treehouse). Desbloquea Room Stats + Dashboard.
- ✅ **A4** — Endpoint multi-versión `/pl/compare/?scenarios=id1,id2&month=N`: por cada escenario devuelve los 3 horizontes (month/ytd/full) con kpis+lines. Refactor: `_aggregate_selected(sel)` (núcleo reusable) + `_aggregate` delega + `_scenario_label`. Generaliza el Command Center en una llamada. 1 test nuevo. Desbloquea Dashboard + Full P&L. **Fase A COMPLETA.**

## Fase B — Dashboard (máximo impacto visual) · usa A — **COMPLETA**
Pantalla `/dashboard` (`frontend/app/dashboard/page.tsx`), link en TopNav→Admin. Usa
`getPLCompare` (A4) + `getPLMonthly`. Verificado en prod con datos reales.
- ✅ **B1** — Barra POV: escenario primario + 3 comparaciones + horizonte Full Year/YTD (selector de mes).
- ✅ **B2** — Tiles KPI (Occ/ADR/RevPAR/Revenue/GOP/EBITDA/Net) vs versiones con variación en color.
- ✅ **B3** — Tendencias mensuales (Recharts LineChart): Revenue y GOP, una línea por versión.
- ✅ **B4** — Tabla P&L comparativa (todas las líneas × versiones con Δ%).

## Fase C — Reportes núcleo (entregables a dueños) · usa A · cada uno ver+Excel+PDF
- ✅ **C1** — P&L YTD detalle (formato 3.1). Pantalla nueva `/reports/pl-ytd` (link TopNav→Reportes): Actual vs Budget, cada uno $ · % de ingreso · PAR · POR + Variance $/%; stats header; export Excel (xlsx) + PDF (print). Usa `/pl/compare` (col ytd con par/por). **Verificado vs PDF real al centavo** (Rooms PAR 376.63/POR 600.12). La `/reports/ytd` existente queda como "YTD Summary".
- ✅ **C2** — Full P&L ejecutivo (formato 3.2). Pantalla `/reports/pl-full` (TopNav→Reportes→"Full P&L ejecutivo"): 13 columnas = Mes/YTD/Full Year × roles (Actual·Budget·Variance·Reforecast | Forecast·Budget·Variance·Reforecast·Actual LY). Selectores de rol + mes; export Excel+PDF. Usa `/pl/compare`. **Verificado vs PDF al centavo** (Reforecast May 219,905 / YTD 3,268,526 / Full 5,191,809; Forecast Full 5,216,806; LY 3,093,799). Fix importador: pone `actuals_through=0` (el snapshot ya trae el blend, no pisarlo con el ACTUAL). (Comments section: pendiente menor.)
- ✅ **C3** — Summary ejecutivo one-pager (formato 3.3). Pantalla `/reports/summary` (TopNav→Reportes→"Summary ejecutivo"): 13 indicadores (Rooms avail/occ/guests, Occ%, ADR, RevPAR, Total/Rooms/F&B/Other Revenue, GOP, EBITDA, Net) × Mes (Actual/Budget/Var$/Var%) + YTD (idem). Export Excel+PDF. Usa `/pl/compare`. Verificado vs hoja Summary real (Occ YTD 62.8/55.4 +13.4%, Rev YTD 3.29M/2.81M +17.2%, Net +45%). "Cash (End of Month)" → pendiente (viene de contabilidad, Fase D).
- ✅ **C4** — Planilla por departamento. Endpoint `/payroll/{id}/dept-report/` (headcount # posiciones, FTE promedio, salario base S&W anual, costo total con cargas — todo USD, de positions+concept entries). Pantalla `/reports/payroll-dept` (TopNav→Reportes→"Planilla x Depto") + export Excel+PDF. La planilla detallada vive en budgets/forecasts (default = último Budget; Actuales snapshot dan 0 + nota).
- ✅ **C5** — Ingresos por tipo de habitación (formato 3.4). Pantalla `/reports/revenue-by-room` (TopNav→Reportes→"Ingresos x Habitación"): por categoría units/noches/occ/revenue/ADR/pax/%total + TOTAL; vista Full Year / YTD / Mes; export Excel+PDF. Usa A3 `/scenarios/{id}/revenue/by-room-type/`. **OJO: sale de los DRIVERS** (rate cards+ocupación) → solo budgets/forecasts; los Actuales (snapshot P&L) dan 0 (default = último BUDGET + nota). Verificado Budget 2026: 30 units, 39.8% occ, $2.60M, ADR $596.89.
- ✅ **C6** — OPEX · Costos · Overhead. Endpoints `/opex/{id}/report/` y `/costs/{id}/report/` (dept→cuentas→anual). Pantalla `/reports/expenses` (TopNav→Reportes→"OPEX / Costos"): toggle OPEX/Costos, departamentos colapsables con detalle por cuenta + TOTAL, export Excel+PDF. Overhead = deptos de soporte dentro de OPEX (nota). Default = último Budget. **FASE C COMPLETA.**

## Fase D — Estados financieros nuevos
- ✅ **D1** — Cash Flow proyectado (método indirecto). Modelo `CashFlowParams` (mig **036**: opening_cash/dso/dpo/distributions). `engine/cashflow.py` puro (EBITDA ± ΔA/R ± ΔA/P − tax − capex − distribuciones → caja). Endpoints `GET/PUT /scenarios/{id}/cashflow/`. Pantalla `/reports/cashflow` (TopNav→P&L→"Flujo de Caja"): params editables + tabla 12 meses + Año, export Excel+PDF. 3 tests. Impuesto y distribuciones se pagan en diciembre.
- ✅ **D2** — Panorama fiscal. Modelo `TaxParams` (mig **037**: wh_rate 2.5%, income_tax_rate 30%, card_pct por línea). `engine/tax.py` puro (retención tarjetas por mes + liquidación anual renta: bruto 30%×EBT, crédito = retención acumulada, neto, saldo a favor, tasa efectiva). Endpoints `GET/PUT /scenarios/{id}/tax/`. Pantalla `/reports/tax` (TopNav→P&L→"Panorama Fiscal"): params editables + retención mensual + liquidación anual, export Excel+PDF. 4 tests. **FASE D COMPLETA.**

## Fase E — Planning lifecycle (versiones) — **COMPLETA**
- ✅ **E1** — Versiones (Draft 1/2/Final): ya existía — `/scenarios` crea Budget/Forecast con label de versión (Draft1/v1/FINAL), copiando de otro escenario o en blanco.
- ✅ **E2** — Forecast rolling: columna "Corte rolling" en `/scenarios` — selector de `actuals_through` por FORECAST (Actuales hasta mes X → el motor blendea actual+proyección). Usa el PATCH existente.
- ✅ **E3** — Comparar versiones lado a lado: ya cubierto por el Dashboard (barra POV con 3 comparaciones) + `/pl/compare`.

## Fase F — Reorganización de navegación a los 7 tabs — **COMPLETA**
- ✅ TopNav reescrito a los 7 lugares: **Dashboard · Escenarios · Planning · Estados financieros · Reportes · Master Data · Admin**. Planning agrupa todo el proceso con sub-headers de sección (Setup del año · Ingresos · Planilla · Costos y gastos · Colaboración[Tablero+Q&A]); Dashboard incluye Command Center; Estados financieros = P&L/Cash Flow/Tax; Reportes = biblioteca por tema; Master Data = catálogo/mapeo. Dropdown con headers de sección + scroll. **ROADMAP COMPLETO.**

---

**Arranque acordado:** Fase A → B (primitivas + Dashboard).
_Última actualización: 2026-06-26._
