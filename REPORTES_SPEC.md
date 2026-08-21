# FinPlan CWL — Especificación de Estructura + Reportes

> Consolidado de la sesión de diseño 2026-06-26. Define (1) la arquitectura de navegación
> de "clase mundial" (7 tabs) y (2) la biblioteca de reportes con formatos reales de CWL.
> Los PDFs/Excel de referencia viven en el Drive ejecutivo de Corcovado Holding
> (`Executive Month End Commentes/2026/MAYO 2026/`).

---

## PARTE 1 — Arquitectura de navegación (7 tabs)

El problema actual: la app es un menú de **módulos** sueltos (Ingresos, Planilla, Costos, P&L…)
con el escenario como dropdown repetido adentro → no tiene secuencia, el usuario no sabe por
dónde empezar. La solución: invertirlo a **escenario-primero**, estilo Hyperion/Oracle EPM.

| # | Tab | Rol | Subsecciones |
|---|-----|-----|--------------|
| 1 | **Escenarios** | La biblioteca: donde nacen los escenarios | Crear nuevo (en blanco) · Copiar draft · Forecast rolling · Lista (Budget/FCT/Actual) |
| 2 | **Planning** | El taller: elegís UNA versión y la construís hasta terminar | [selector de versión] · Setup del año · Constructor (Ingresos·Planilla·Costos·OPEX·Gastos dueños) · Tablero (aprobaciones) · Q&A |
| 3 | **Dashboard** | Análisis vs versiones (estilo hospitality/Hyperion) | KPIs (Occ·ADR·RevPAR·GOP) · Tendencias mensuales · P&L comparativo · Tiles configurables · barra POV |
| 4 | **Master Data** | Lo estable del hotel (casi no cambia) | Hoteles · Catálogo de cuentas · Departamentos · Mapeo P&L · Parámetros base |
| 5 | **Estados financieros** | Los números finales | P&L USALI · Cash Flow · Tax / Panorama fiscal |
| 6 | **Reportes** | Biblioteca de formatos para dueños (ver Parte 2) | (ver abajo) |
| 7 | **Admin** | Se toca una vez | Usuarios y roles · Auditoría / feed de actividad |

### Decisiones de diseño clave
- **El tab "Planning" NO crea escenarios** — solo se elige una versión existente y se trabaja.
  Crear/copiar/forecast-rolling viven en **Escenarios** (la biblioteca).
- **Tablero y Q&A van DENTRO de Planning** — son parte del mismo proceso de armar el budget.
- **Dashboard = análisis** (gráficos + tablas vs versiones), NO la pantalla de inicio.
- **Master Data tiene dos niveles:** (a) apartado global del hotel (catálogo, mapeo, params base
  — casi fijo); (b) "Setup del año" dentro de cada escenario en Planning (units, meses cerrados,
  pax, TC, salarios — cambia por presupuesto). El apartado define defaults; el escenario los ajusta.
- **Actuales = solo lectura.** No tienen Constructor; son historia para comparar. Budget/Forecast
  se construyen.
- **Forecast (blend):** ya existe `Scenario.actuals_through`. Forecast 2026 con corte abril →
  ene-abr toman el Actual real, may-dic se construyen. Budget = 12 meses completos.
- **POV (Point of View)** = el corazón del Dashboard: selectores escenario/versión/año/depto que
  cambian todos los gráficos/tablas a la vez. Permite comparar cualquier versión en cualquier tile.

### Modelo Hyperion/EPM de referencia (mapeo)
| Oracle EPM | FinPlan |
|---|---|
| Home (cards) | Inicio / Escenarios |
| Dashboards 2.0 (POV-driven) | Dashboard ⬅️ falta |
| Forms 2.0 | Constructor (checkbooks) ✅ |
| Approvals (scenario+version+entity) | Tablero ✅ |
| Reports (XLSX/HTML) | Reportes ✅ parcial |
| Smart View (Excel add-in) | export Excel (futuro) |

---

## PARTE 2 — Biblioteca de reportes

Agrupados por tema. Estado: ✅ existe · ⚠️ parcial · ⬜ por construir.
Cada reporte: **ver en pantalla · exportar Excel · exportar PDF**.

### Planilla
- ⚠️ Reporte de FTEs (existe `/payroll/fte`)
- ⬜ Salarios por mes y departamento
- ⬜ Cargas sociales (17 conceptos CR)
- ⬜ Headcount por departamento

### Gastos y costos
- ⬜ Gastos operativos (OPEX)
- ⬜ Costos de venta (Clase 5)
- ⬜ Overhead
- ⬜ Gastos del propietario (8xxx)

### P&L (resultados)
- ✅ P&L YTD (existe reporte YTD) — ver formato detallado abajo
- ⬜ P&L Full Year
- ⬜ P&L Forecast 12 meses
- ⬜ P&L por departamento

### Financieros (vienen de CONTABILIDAD/Integrity, no del presupuesto)
- ⬜ Flujo de caja (real) — FinPlan puede hacer proyectado; el real se importa
- ⬜ Panorama fiscal (Tax)
- ⬜ Balance Sheet — externo
- ⬜ AP Aging / AR Aging — externo

### Comparativos
- ⬜ Variaciones (Budget vs Actual)
- ⬜ Comparar versiones
- ⬜ KPIs / Estadísticas
- ⬜ Ingresos por tipo de habitación — ver formato abajo

### Dueños / Ejecutivo
- ✅ Reporte para propietarios (versión simple ya construida)
- ⬜ Full P&L ejecutivo (el grande, ver abajo)
- ⬜ Summary ejecutivo (one-pager)
- ⬜ Narrativa de variaciones

---

## PARTE 3 — Formatos detallados (de los archivos reales)

### 3.1 — P&L YTD (`YTD May 2026.pdf`)
P&L USALI, una página. Columnas = **3 bloques × 4 métricas**:
- **Actual 2026 (YTD)** · **Budget 2026 (YTD)** · **Variance vs Budget**
- Cada bloque: `$ · % of Revenue · PAR · POR`
- **PAR** = Per Available Room (÷ habitaciones disponibles)
- **POR** = Per Occupied Room (÷ habitaciones ocupadas)

Encabezado stats (Actual|Budget|Var): Total Rooms Available · Rooms Occupied · Total Guests ·
% Occupancy · Average Daily Room Only (ADR).

Secciones: REVENUES por depto → TOTAL REVENUES · Operating Expenses por depto + overhead
(Admin, Sales&Mktg, Maintenance, IS, Utilities, Cafeteria) · below-GOP (Rent, Mgmt Fees 3%/5%,
Insurance, Bank Interest, Other Expenses) → Total Operating Expenses · **EBITDA** · Depreciation ·
Financial Losses · Income Taxes 30% · Capital · **Net Income**.

### 3.2 — Full P&L ejecutivo a dueños (`Full P&L CWL YTD MAY 2026 & Full Year Forecast.pdf`)
El reporte estrella. ~13 columnas por línea = **3 horizontes × varias versiones**:
- **Mes (May):** Actual 26 · Budget 26 · Variance · Reforecast 26
- **YTD May:** Actual 26 · Budget 26 · Variance · Reforecast 26
- **Full Year:** Forecast 26 · Budget 26 · Variance · Reforecast 26 · **Actual 25** (LY)

Stats: Rooms Available · Occupied · Guests · % Occupancy · ADR · **Total RevPAR**.

Secciones: REVENUES → TOTAL REVENUES · Operating Expenses · CAPITAL RESERVE / LARGE CAPEX →
CAPITAL EXPENSE · **EBITDA AFTER CAPITAL** · Bank Interest / Leasings / Financial Losses →
FINANCIAL EXPENSES · Depreciation / Asset Loss → TOTAL DEPRECIATIONS · **EBT** · Income Taxes 30%
→ **NET PROFIT** · resumen (Total Incomes, Total OpEx, Owners Expenses, Net Profit) · **Comments**
(Total Payroll & Benefits + Total OpEx desglosados + texto).

> Este es el verdadero "Reporte para propietarios"; el simple que ya construimos es una versión
> reducida. El motor YA calcula todas las líneas por mes y por escenario → el reporte es
> **ensamblaje** (agregar Mes/YTD/Full Year + cruzar versiones), no cálculo nuevo.

### 3.3 — Paquete ejecutivo Excel (`YTD MAYO SUMMARY 2026.xlsx`, 22 hojas)
"El entregable maestro". Mucho sale del P&L. Clasificación:

**✅ FinPlan genera (del motor / datos existentes):**
Simplified P&L YTD · Simplified P&L Full Year · Profit&Loss · Summary (one-pager) · Total Revenue ·
Payroll Expenses · F&B Cost · Capex · Headcounts · Room Stats · 12 months Budget / Reforecast /
Forecast · Colon-Dollar.

**⚠️ Mixtas (template / mercado / manual):** Ops KPI (tracker de acciones) · Market set ·
On the Books (pickup) · Country.

**⬜ De CONTABILIDAD (Integrity), NO presupuesto:** Balance Sheet · Cash Flow (real) ·
AP Aging · AR Aging.

→ ~80% del paquete es generable por FinPlan. El resto (BS, Aging) se importaría del contable.

#### Hoja "Summary" (one-pager ejecutivo)
Métricas (filas) × Actual May · Budget May · Var$ · Var% · YTD Actual · YTD Budget · Var$ · Var% · Notes:
Total Rooms Available/Occupied · Total Guests · Occupancy% · ADR · RevPAR · Total Revenue ·
Rooms Revenue · F&B Revenue · Other Revenue · GOP · EBITDA · Net Profit · **Cash (End of Month)**.

#### Hoja "Headcounts" (headcount por depto)
Department × Actual May · Budget May · Notes. Deptos: Front Office, Reservations, Housekeeping,
Guest Services, Kitchen, Restaurant, Spa Therapists, Claro Huerta, Laundry, Cafeteria, Management,
Finance, Purchasing, HR, Security, Sales&Mktg, IT, PO&M, Activities-Tour, Transportation →
TOTAL HEADCOUNT.

### 3.4 — Ingresos por tipo de habitación (`YTD Rev by Room2026.xlsx`, hoja "Room Stats")
Por categoría de habitación: **Units · Total Noches · Noches Ocupadas · Occupancy% · Total Revenue ·
ADR · Total Pax · % del total**. Bloque YTD arriba + un bloque por mes (Ene, Feb, Mar…).
6 categorías CWL: Corcovado Deluxe Villas King · Carate Deluxe Villa Double · Agujas Villa 2 Queen ·
Sirena Suites Queen (connecting) · Treehouse king · 5 Elements Treehouse king.
Revela qué categoría produce más (Treehouse/5 Elements por ADR alto pese a menos units).
**Buildable:** los drivers de Ingresos ya tienen estos datos por tipo; falta el reporte (la memoria
ya marcaba "ADR/RevPAR por tipo" como pendiente).

---

## PARTE 4 — Implicaciones para el motor
- El motor de P&L ya calcula por **mes × escenario**. Reportes YTD = sumar ene→mes; Full Year =
  12 meses (o blend forecast); Mes = un mes. Cruzar versiones = ya lo hace el Command Center.
- **Falta agregar PAR/POR** por línea (÷ rooms available / ÷ rooms occupied) — métricas USALI core.
- **Revenue por tipo de habitación**: exponer el desglose por room type (ya en los drivers).
- **Balance Sheet / Aging / Cash real**: fuera del alcance de planificación → importar de Integrity.

_Última actualización: 2026-06-26._
