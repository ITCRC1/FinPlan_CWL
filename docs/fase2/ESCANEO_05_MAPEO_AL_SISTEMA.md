# ESCANEO 05 — Mapeo del P&L Detallado al sistema FinPlan CWL

**Archivo analizado:** `docs/fase2/PL_DETALLADO_FORMATO.xlsx`, hoja `P&L Full Detail`
(filas 1–1007, columnas D–O = Enero…Diciembre, columna Q = Total Año; las fórmulas
apuntan al libro externo `[1]Budget 2025W` / `[1]P&L Detail Club`, o sea que el Excel
es **formato**, los números tienen que salir de nuestro motor).

**Sistema:** `backend/app/engine/pl_engine.py` + `report_line_config` (89 líneas,
report_id `P&L_DETAIL_OWNERS`) + `account_mapping` (961 reglas, 235 cuentas,
44 líneas de reporte) + `department_catalog` (39 departamentos).
Base de PRODUCCIÓN leída en solo-lectura el 2026-08-11.

---

## 1. Resumen ejecutivo

El Excel tiene **781 líneas etiquetadas** (sin contar encabezados de sección ni
títulos). El cruce contra el sistema da:

| | Líneas | % |
|---|---|---|
| **YA EXISTE** — el dato está y se puede leer hoy sin cálculo nuevo | **703** | **90.0 %** |
| **EXISTE CON OTRO NOMBRE / GRANULARIDAD** — el número está adentro de otro | 12 | 1.5 % |
| **NO EXISTE** — no hay dato en ninguna tabla | 66 | 8.5 % |

**Pero ese 90 % tiene tres asteriscos grandes, y hay que leerlos antes de prometer nada:**

1. **El reporte P&L de hoy NO emite esas líneas.** `report_line_config` llega al
   nivel de **departamento** (13 líneas de ingreso, 13 de opex, 13 de utilidad,
   9 de overhead). De las 781 líneas del Excel, el P&L actual emite como línea
   propia solo **76 (≈10 %)**: los 6 KPIs y el bloque resumen de las filas 22–145.
   Las otras 627 viven en tablas de detalle (`opex_entries`, `cost_entries`,
   `payroll_concept_entries`, `revenue_account_entries`, `belowgop_account_entries`,
   `actual_entries`) y en endpoints por departamento que ya existen —
   pero **nadie las arma en el orden y con las etiquetas del Excel**.

2. **El 90 % aplica a escenarios IMPORTADOS** (Actual 2024/2025/2026, Budget 2026
   Final, Forecast 2026), que traen el detalle GL cuenta por cuenta. Para el
   **Budget 2027 armado dentro del sistema (`source_mode = checkbook`)** el
   número real es **≈63 %**, porque:
   - `revenue_account_entries` = **0** (el ingreso sale de rate cards a nivel de
     línea: REV_ROOMS, REV_FB… sin apertura por cuenta 4xxx),
   - `belowgop_account_entries` = **0** y `nonop_entries` = 0–2,
   - `cost_entries` = **3 líneas** (contra 35 que pide el Excel),
   - Club Madresal (260) y Área Recreativa (270) no tienen opex cargado.

3. Los escenarios **2028–2035 están vacíos** (0 filas en todas las tablas de
   detalle): alimentarían el reporte con ceros.

**Lectura corta:** el catálogo de cuentas del sistema es casi idéntico al del
Excel — las 235 cuentas de `account_mapping` cubren 293 de las 306 líneas de
gastos operativos, las 35 de costo de venta menos 3, y los 16 conceptos de
planilla ×12 departamentos. Lo que falta no es dato: es **el ensamblador del
reporte**, más cinco huecos concretos (Club Madresal estadísticas, departamento
Bar Privado, apertura de A&B por outlet, ingresos por cuenta en checkbook,
below-GOP por cuenta en checkbook).

---

## 2. Inventario del Excel

| Bloque | Filas | Líneas |
|---|---|---|
| KPIs de habitaciones | 3–8 | 6 |
| Estadísticas Club Madresal | 11–14 | 4 |
| Resumen P&L (ingresos → utilidad neta + cuadres) | 22–145 | 70 |
| Detalle — Ingresos por cuenta | varias | 60 |
| Detalle — Costo de ventas (incl. Costo de Servicios de TI) | varias | 35 |
| Detalle — Planilla (16 conceptos × 12 deptos + Mano de Obra por Contrato) | varias | 209 |
| Detalle — Gastos operativos por cuenta | varias | 306 |
| Subtotales / totales / % de los bloques de detalle | varias | 80 |
| Gastos de Propiedad (below-GOP) | 946–1007 | 11 |
| **TOTAL** | | **781** |

Departamentos con bloque de detalle propio (15): Habitaciones, Alimentos y Bebidas,
Spa, Tours, Tienda de Regalos, **Bar Privado**, Club Madresal, Lavandería,
Ingresos Varios, Administración y General, Ventas y Mercadeo, Mantenimiento,
Sistemas de Información, Servicios Públicos, Área Recreativa.

---

## 3. Cruce completo

### 3.1 KPIs (filas 3–8)

| Excel (col C) | Estado | Dónde está en el sistema |
|---|---|---|
| Habitaciones Disponibles Totales | **YA EXISTE** | `scenario_stats.rooms_available` → `KPI_AVAILABLE_ROOMS`; sale en `/pl/{id}/monthly/` como `kpis.rooms_available` |
| Habitaciones Ocupadas Totales | **YA EXISTE** | `scenario_stats.rooms_occupied` → `KPI_OCCUPIED_ROOMS` |
| Habitaciones por Día | **OTRA GRANULARIDAD** | `KPI_ROOMS_PER_DAY` está declarada en `report_line_config` pero **el API no la emite**. Derivable: `rooms_available / días del mes`. Trabajo: 1 línea. |
| Huéspedes Totales | **YA EXISTE** | `scenario_stats.guests` → `KPI_TOTAL_GUESTS` |
| % de Ocupación | **YA EXISTE** | `scenario_stats.occupancy_pct` → `KPI_OCCUPANCY` |
| Tarifa Promedio Diaria (solo habitación) | **YA EXISTE** | `scenario_stats.adr` → `KPI_ADR_ROOM_ONLY` |

`scenario_stats` tiene los 12 meses cargados para **todos** los escenarios con
datos (2024–2027). El sistema además calcula RevPAR (`KPI_TOTAL_REVPAR`) y
PAR/POR por línea (`pl_engine.par_por`), que el Excel no pide.

### 3.2 Estadísticas Club Madresal (filas 11–14) — **NO EXISTE, las cuatro**

| Excel | Estado | Qué haría falta |
|---|---|---|
| Total Membresías | **NO EXISTE** | No hay ninguna tabla de membresías en la base (busqué `membres*` / `membership` en todo el repo: solo aparece en comentarios). |
| Membresías Condicionados | **NO EXISTE** | idem |
| Membresías Pagando | **NO EXISTE** | idem |
| Membresías En acuerdo de pago | **NO EXISTE** | idem |

El sistema sí tiene el **dinero** del Club (`REV_CLUB`, `OPEX_CLUB`,
`PROFIT_CLUB`, dept 260, cuentas 4500 Ingreso Madresal Club / 4501 Actividad fin
de año / 4502 Visitantes, costos 5500/5501). Lo que no tiene es el **conteo de
socios**. Hace falta una tabla nueva tipo `club_membership_stats
(scenario_id, month, total, condicionados, pagando, acuerdo_pago)` + su pantalla
de captura, análoga a `scenario_stats`.

### 3.3 Resumen P&L (filas 22–145)

Este bloque es el que el sistema **ya emite tal cual**. 63 de 70 líneas son
`line_code` existentes.

| Excel | Estado | `line_code` |
|---|---|---|
| **INGRESOS** | | |
| Habitaciones | YA EXISTE | `REV_ROOMS` |
| Alimentos y Bebidas | YA EXISTE | `REV_FB` |
| Spa | YA EXISTE | `REV_SPA` |
| Tours | YA EXISTE | `REV_TOURS` |
| Tienda de Regalos | YA EXISTE | `REV_RETAIL` |
| Club Madresal | YA EXISTE | `REV_CLUB` |
| Lavandería | YA EXISTE | `REV_LAUNDRY` |
| **Bar Privado** | **OTRA GRANULARIDAD** | no hay grupo propio; el dept 0121 "Bar" existe en `department_catalog` pero su `default_pl_group` es **FB** → hoy queda dentro de `REV_FB` |
| Ingresos Varios | YA EXISTE | `REV_MISC_OTHER` |
| INGRESOS TOTALES | YA EXISTE | `TOTAL_REVENUES` |
| **GASTOS OPERATIVOS** (9 líneas, mismo orden) | YA EXISTE (8) / Bar Privado OTRA GRANULARIDAD | `OPEX_ROOMS`, `OPEX_FB`, `OPEX_SPA`, `OPEX_TOURS`, `OPEX_RETAIL`, `OPEX_CLUB`, `OPEX_LAUNDRY`, —, `OPEX_MISCELLANEOUS` |
| Total Gastos Operativos | YA EXISTE | `TOTAL_OPERATING_EXPENSES` |
| **UTILIDAD OPERATIVA** (9 líneas) | YA EXISTE (8) / Bar Privado OTRA GRANULARIDAD | `PROFIT_ROOMS`, `PROFIT_FB`, `PROFIT_SPA`, `PROFIT_TOURS`, `PROFIT_RETAIL`, `PROFIT_CLUB`, `PROFIT_LAUNDRY`, —, `PROFIT_MISC_OTHER` |
| UTILIDAD OPERATIVA (total) | YA EXISTE | `OPERATING_PROFIT` |
| **GASTOS GENERALES** | | |
| Administración | YA EXISTE | `OH_ADMIN` |
| Ventas y Mercadeo | YA EXISTE | `OH_SALES_MARKETING` |
| Mantenimiento | YA EXISTE | `OH_MAINTENANCE` |
| Sistemas de Información | YA EXISTE | `OH_INFORMATION_SYSTEM` |
| Servicios Públicos | YA EXISTE | `OH_UTILITIES` |
| **Área Recreativa** | **OTRA GRANULARIDAD** | existe como `OPEX_AREC` / `PROFIT_AREC`, pero el sistema la trata como **departamento operativo con ingreso**; el Excel la mete en overhead (fila 76 = `D940`, que es planilla + opex de AREC). Ver §5, riesgo 1. |
| TOTAL GASTOS GENERALES | YA EXISTE | `TOTAL_OVERHEAD_EXPENSES` |
| UTILIDAD OPERATIVA BRUTA TOTAL (GOP) | YA EXISTE | `TOTAL_GOP` |
| Alquiler | YA EXISTE | `RENT` (cuenta 8000) |
| Honorarios de Administración (5%) | YA EXISTE (con reserva) | `MGMT_FEE_5_ROYALTIES` **y** `MGMT_FEE_3` — las dos apuntan a la cuenta 8005. Ver riesgo 2. |
| TOTAL ALQUILER Y HONORARIOS | YA EXISTE | `TOTAL_RENT_MGMT_FEES` |
| Seguro de Propiedad / SEGURO DE PROPIEDAD | YA EXISTE | `PROPERTY_INSURANCE` / `TOTAL_PROPERTY_INSURANCE` (8015) |
| Otros Gastos / TOTAL OTROS GASTOS | YA EXISTE | `OTHER_EXPENSES` / `TOTAL_OTHER_EXPENSES` (8025) |
| TOTAL GASTOS NO OPERATIVOS | YA EXISTE | `TOTAL_NON_OP_EXPENSES` |
| EBITDA ANTES DE CAPITAL | YA EXISTE | `EBITDA_BEFORE_CAPITAL` |
| Reserva de Capital | YA EXISTE | `CAPITAL_RESERVE` (8020) |
| Mejoras Mayores | YA EXISTE (con reserva) | `LARGE_CAPEX` — la línea existe pero **no tiene ninguna cuenta mapeada**. Ver riesgo 3. |
| GASTO DE CAPITAL | YA EXISTE | `CAPITAL_EXPENSE` |
| EBITDA DESPUÉS DE CAPITAL | YA EXISTE | `EBITDA_AFTER_CAPITAL` |
| Pérdida Financiera | YA EXISTE | `FINANCIAL_LOSSES` (8045) |
| GASTOS FINANCIEROS | YA EXISTE | `FINANCIAL_EXPENSES` |
| Depreciación / TOTAL DEPRECIACIONES | YA EXISTE | `DEPRECIATION` (8040) / `TOTAL_DEPRECIATIONS` |
| UTILIDAD ANTES DE IMPUESTOS | YA EXISTE | `EBT` |
| Impuesto sobre la Renta (30%) | YA EXISTE | `INCOME_TAXES` |
| UTILIDAD NETA | YA EXISTE | `NET_PROFIT` |
| **Cuadres (129–132, 144–145)** | | |
| Ingresos totales | YA EXISTE | `= TOTAL_REVENUES` |
| Total gastos operativos (`D50+D78`) | YA EXISTE | `TOTAL_OPERATING_EXPENSES + TOTAL_OVERHEAD_EXPENSES` |
| Gastos de la Propiedad | YA EXISTE | derivable de `TOTAL_NON_OP + FINANCIAL + DEPRECIACIÓN + IMPUESTO + CAPITAL` |
| UTILIDAD NETA (cuadre) | YA EXISTE | `NET_PROFIT` |
| Gastos de propiedad / Gastos después de EBITDA | YA EXISTE | derivables |
| **Resumen (136–141)** | | |
| Total Nómina y Beneficios | **OTRA GRANULARIDAD** | no es línea del P&L; hoy sale de `GET /payroll/{id}/summary/` y `/payroll/{id}/dept-report/` (suma de los 17 conceptos). Hay que exponerla como línea. |
| Total Gastos Operativos (solo clase 7) | **OTRA GRANULARIDAD** | `GET /opex/{id}/summary/`; el P&L la mezcla con planilla y costo dentro de `OPEX_*` |
| Costo Total (clase 5) | **OTRA GRANULARIDAD** | `GET /costs/{id}/report/`; idem |
| Total Gastos de Propiedad | YA EXISTE | derivable |
| UTILIDAD NETA / Variación 0 | YA EXISTE | `NET_PROFIT` + cuadre |

### 3.4 Planilla — 16 conceptos × 12 departamentos (209 líneas)

El Excel repite el mismo bloque de 16 conceptos en cada departamento. **Los 16
existen uno a uno** como columnas de `payroll_concept_entries` y como cuentas
6xxx en `account_mapping`, y `GET /payroll/{scenario}/dept/{dept}/summary/` ya
los devuelve **por mes (1–12)**.

| Excel | Estado | Columna / cuenta |
|---|---|---|
| Salarios y Sueldos | YA EXISTE | `c6000_sw` / 6000 Salary and Wages |
| Horas Extra | YA EXISTE | `c6001_overtime` / 6001 Overtime |
| Día Libre | YA EXISTE | `c6002_day_off` / 6002 Day Off |
| Feriado Trabajado | YA EXISTE | `c6003_working_holiday` / 6003 Working Holiday |
| Comisiones | YA EXISTE | `c6010_commissions` / 6010 Commissions |
| Seguro Social (CCSS) | YA EXISTE | `c6020_ccss` / 6020 Social Security |
| Aguinaldo | YA EXISTE | `c6021_aguinaldo` / 6021 Christmas bonus |
| Póliza de Riesgos del Trabajo | YA EXISTE | `c6022_occ_hazard` / 6022 Work Risk Policy |
| Provisión de Vacaciones | YA EXISTE | `c6023_vacation_prov` / 6023 Vacations Accrual |
| Vacaciones Disfrutadas | YA EXISTE | `c6024_vacations_taken` / 6024 Vacations Taken |
| Cafetería | YA EXISTE | `c6025_cafeteria` / 6025 Cafeteria |
| Preaviso y Cesantía | YA EXISTE | `c6026_severance` / 6026 Notice and Severance Pay |
| Bono de Incentivo | YA EXISTE | `c6027_incentive_bonus` / 6027 Incentive Bonus |
| Vivienda | YA EXISTE | `c6028_housing` / 6028 Housing |
| Transporte de Empleados | YA EXISTE | `c6029_transport` / 6029 Employee Transportation |
| Otros Beneficios a Empleados | YA EXISTE | `c6030_other` / 6030 Employee Benefit Others |
| **Mano de Obra por Contrato** (solo Tours) | **OTRA GRANULARIDAD** | la cuenta **6031** existe en `account_mapping` y en `actual_entries`, pero **no hay columna** en `payroll_concept_entries`. En actuales entra por GL al total de nómina; en checkbook no tiene dónde vivir. |

El sistema tiene además `c6004_disabilities` (incapacidades, cuenta 6004) que el
Excel no muestra — se sumaría al total sin línea propia.

**Cobertura por departamento:** 12 de los 13 bloques de planilla del Excel tienen
departamento en el sistema. El que falta es **Bar Privado** (16 líneas).

| Excel | Dept del sistema |
|---|---|
| Habitaciones | 0110 (+0111 Front Desk, 0112 Reservation, 0113 Housekeeping, 0114 Concierge) |
| Alimentos y Bebidas | 0120 (+0122 Kitchen, 0123 Restaurant) |
| Spa | 0130 / 0132 / 0140 |
| Tours | 0150 |
| Tienda de Regalos | 0151 / 0165 |
| **Bar Privado** | **— (0121 "Bar" existe pero cae en el grupo FB)** |
| Club Madresal | 260 |
| Lavandería | 0161 (interna, allocation) / 0162 (servicio vendido) |
| Administración y General | 0180 (+0181/0182/0183/0184/0186) |
| Ventas y Mercadeo | 0190 / 0191 |
| Mantenimiento | 0200 |
| Sistemas de Información | 0230 |
| Área Recreativa | 270 |

### 3.5 Ingresos por cuenta (60 líneas)

| Bloque Excel | Líneas | Estado | Cuentas del sistema |
|---|---|---|---|
| Habitaciones: Cancelaciones / No Show / Habitaciones | 3 | **1 YA EXISTE, 2 OTRA GRANULARIDAD** | solo **4000** (`account_name_example` = "Cancellations", pero es la cuenta que carga todo el room revenue). No hay cuenta separada para No Show ni para el ingreso de habitación. |
| A&B: Alimentos ×4, Bebida sin Alcohol ×4, Cerveza ×4, Licor ×4, Vino ×4, A&B Varios ×4 | 24 | **6 YA EXISTE, 18 NO EXISTE** | 4110 Food1, 4120 NA Beverage, 4125 Beer1, 4130 Liquor, 4131 Wine, 4132 F&B Misc — **una cuenta por familia, el Excel abre cuatro** (un outlet por columna). |
| Spa: Masajes / Tratamientos Corporales / Belleza / Tienda de Spa | 4 | **YA EXISTE (4/4)** | 4201 Massage, 4202 Body, 4203 Beauty, 4250 Spa Retail (+4212 Class Revenue, que el Excel no pide) |
| Tours: Ingresos por Tours + Tours ×3 | 4 | **YA EXISTE (4/4)** | 4400–4403 |
| Tienda: Ingreso Tienda ×4 | 4 | **YA EXISTE (4/4)** | 4301–4304 |
| **Bar Privado ×4** | 4 | **NO EXISTE** | no hay departamento ni cuentas 4xxx |
| Club Madresal: Cuotas + 2 | 3 | **YA EXISTE (3/3)** | 4500 Ingreso Madresal Club, 4501 Actividad fin de año, 4502 Visitantes |
| Lavandería ×3 | 3 | **YA EXISTE (3/3)** | 4700–4702 |
| Ingresos Varios ×10 | 10 | **YA EXISTE (10/10)** | 4800 Miscelaneos, 4810 Attrition Fees, 4820 Cancellation Fee, 4830 Cash Discount Earned, 4840 Commissions, 4850 Exchange Losses, 4860 Interest Income, 4870 Package Breakage, 4880 Sustainability Fee, 4890 Medical Services — **coincidencia exacta, línea por línea** |
| Área Recreativa: Ingreso | 1 | **YA EXISTE** | 4600–4602 |

> ⚠️ Todo lo anterior vale para escenarios **importados**. Para el Budget 2027
> (checkbook) `revenue_account_entries` está **vacío**: el ingreso se calcula desde
> rate cards a nivel de línea (`REV_ROOMS`, `REV_FB`…) vía `revenue_seed_from_lines()`.
> Las 60 líneas de detalle de ingreso **no se pueden alimentar** en ese escenario
> sin inventar un prorrateo.

### 3.6 Costo de ventas (35 líneas)

| Bloque Excel | Líneas | Estado | Cuentas |
|---|---|---|---|
| A&B: Costo de Alimentos, Traslado Bar→Alimentos, Flete sobre Alimentos, Costo de Bebidas, Licor, Vino, Cerveza, Otras Bebidas, Traslado Alimentos→Bar, Costo A&B Varios ×5 | 14 | **YA EXISTE (14/14)** | 5101, 5102, 5103, 5150, 5151, 5152, 5153, 5154, 5155, 5161–5165 — **coincidencia exacta** |
| Spa: Costo de Spa | 1 | YA EXISTE | 5300 / 5301 (Spa Retail Cost) |
| Tours: Costo de Tours ×2 | 2 | YA EXISTE | 5350 / 5351 (+5352) |
| Tienda: Ropa Mujer, Ropa Niños, Accesorios, Viseras/Sombreros/Gorras, Calzado, Otra Ropa | 6 | **YA EXISTE (6/6)** | 5203, 5204, 5205, 5206, 5207, 5208 — **coincidencia exacta** |
| **Bar Privado: Costo ×3** | 3 | **NO EXISTE** | sin departamento |
| Club Madresal: Costos ×2 | 2 | YA EXISTE | 5500 / 5501 (dept 260) |
| Lavandería: Costos de Lavandería | 1 | YA EXISTE | 5603 (0161) / 5301 (0162, servicio a huéspedes) |
| Área Recreativa: Costos | 1 | YA EXISTE | 5600 / 5601 (dept 270) |
| Sistemas: Celular, Llamadas Locales, Internet, Larga Distancia, Otros | 5 | **YA EXISTE (5/5)** | 5700, 5701, 5702, 5703, 5704 — **coincidencia exacta** |

> ⚠️ En el Budget 2027 solo hay **3 líneas** en `cost_entries` (5101, 5150, 5161).
> Es un hueco de **dato**, no de código: el owner tiene que cargarlas.

### 3.7 Gastos operativos por cuenta (306 líneas / 155 etiquetas únicas)

**293 de 306 líneas (95.8 %) tienen cuenta 7xxx en `account_mapping`.** El
catálogo del sistema tiene 126 cuentas de clase 7 con los nombres USALI en
inglés, y `GET /opex/{scenario}/dept/{dept}/summary/` ya devuelve
**cuenta × mes** para cada departamento.

Traducción de las etiquetas del Excel a la cuenta del sistema (agrupada; las
variantes de mayúsculas/minúsculas se colapsan):

| Etiqueta Excel | Cuenta | Etiqueta Excel | Cuenta |
|---|---|---|---|
| Agua | 7710 Water/Sewer | Agua (Chilled Water) | 7055 Chilled Water |
| Alimentos y Bebidas de Cortesía | 7090 | Almacenamiento y Optimización de Sistemas | 7640 |
| Alquiler de Equipo | 7185 | Ambientación | 7005 Ambience |
| Ascensores y Escaleras Eléctricas | 7165 | Bombillos | 7345 Light Bulbs |
| Calefacción, Ventilación y A/C | 7265 HVAC | Cambio de Divisa de No Huéspedes | 7390 |
| Capacitación | 7665 Training | Cargos Bancarios | 7020 Bank Charges |
| Cargos de Contabilidad Centralizada | 7050 | Combustible de Cocina | 7295 Kitchen Fuel |
| Combustible (Generador) | 7395 Oil & Gas | Otros Combustibles | 7420 Other Fuels |
| Comisiones | 7080 | Comisiones de Tarjeta de Crédito | 7120 |
| Comisiones y Honorarios—Grupos | 7085 | Correo Directo | 7135 Direct Mail |
| Costos de Liquidación | 7540 | Costos de Uniformes | 7680 |
| Cristalería | 7235 Glassware | Crédito y Cobranza | 7115 |
| Cubería | 7195 Flatware | Cuotas y Suscripciones / Suscripciones | 7150 |
| Decoraciones | 7125 | Diseño Gráfico Interno | 7280 In-House Graphics |
| Donaciones | 7145 | Edificio | 7030 Building |
| Electricidad | 7160 | Entretenimiento en Habitación de Cortesía | 7095 |
| Entretenimiento—Interno (y CPL) | 7175 | Envios / Franqueo y Mensajería | 7485 |
| Equipo / Equipo (hardware) | 7180 | Equipo Eléctrico y Mecánico | 7155 |
| Equipo de Cocina | 7290 | Equipo de Lavandería | 7315 |
| Ferias Comerciales | 7660 Trade Shows | Fotografía | 7475 |
| Franquicia y Afiliación—Regalías | 7205 | Mercadeo de Franquicia y Afiliación | 7210 |
| Ganancias (Pérdidas) | 7225 | Gas | 7230 |
| Gastos Varios / Varios / Varios-caja chica / Varios-Sostenibilidad | 7380 Miscellaneous | Gastos de Banquetes | 7025 |
| Gastos de Sistema: A&G / SI Centralizados / Gestión de Energía / A&B / Golf / Hardware / Club de Salud-Spa / RR.HH. / Seguridad de la Información / Sistemas de Información / Otros / Estacionamiento / Operaciones de Propiedad / Habitaciones / Ventas y Mercadeo / Telecomunicaciones (16 líneas) | 7560, 7565, 7570, 7575, 7580, 7585, 7590, 7595, 7600, 7605, 7610, 7615, 7620, 7625, 7630, 7635 | Hielo | 7275 Ice |
| Honorarios Profesionales | 7495 | Honorarios de Administración | 7365 Management Fees |
| Honorarios de Agencia | 7000 Agency Fees | Honorarios de Auditoría | 7015 |
| Honorarios de Regalía | 7530 Royalty Fees | Impresión y Papelería | 7490 |
| Lavado de Uniformes | 7685 | Lavandería y Limpieza en Seco | 7310 |
| Lencería / Linen | 7350 Linen | Licencias y Permisos | 7335 |
| Mantenimiento de Terrenos y Jardinería | 7240 | Material Promocional (Colateral) | 7075 |
| Medios | 7370 Media | Menús y Cartas de Bebidas | 7375 |
| Mobiliario y Equipo | 7215 | Música y Entretenimiento | 7385 |
| Otro Equipo | 7415 | Otros Costos de Servicios | 7410 |
| Papel y Plásticos | 7460 | Pintura y Revestimiento de Paredes | 7455 |
| Piscina | 7555 Swimming Pool | Plomería | 7480 |
| Procesamiento de Planilla | 7465 | Productos de Salud y Belleza | 7260 |
| Programas de Lealtad | 7360 | Promoción | 7500 |
| Provisión para Cuentas Incobrables | 7510 | Pérdidas y Daños | 7355 |
| Recolección de Desechos | 7705 | Recursos Humanos | 7270 |
| Reembolsos a Oficina Corporativa | 7110 | Reparación de Vehículos | 7700 |
| Representación de Ventas Externa | 7435 | Reservaciones | 7525 |
| Reubicación de Huéspedes | 7245 | Revestimiento de Pisos | 7200 |
| Rotulación Externa | 7445 | Seguridad | 7535 |
| Servicios Contratados | 7105 | Servicios Externos de Investigación de Mercado | 7440 |
| Servicios Legales | 7325 | Servicios de Clúster (y cuota de mercadeo) | 7070 |
| Servicios y Regalos de Cortesía | 7100 | Sitio Web | 7715 |
| Sobrantes y Faltantes de Caja | 7045 | Suministros Deportivos | 7010 |
| Suministros Operativos | 7400 | Suministros de Ingeniería | 7170 |
| Suministros de Lavandería | 7320 | Suministros de Lavavajillas | 7140 |
| Suministros de Limpieza | 7065 | Suministros para Huéspedes | 7250 |
| Transporte de Huéspedes | 7255 | Transporte de Personal | 7545 |
| Utensilios | 7695 | Utensilios Menores de Cocina | 7300 |
| Vajilla (Loza) | 7060 China | Vapor | 7550 Steam |
| Viajes de Familiarización | 7190 | Viajes—Comidas y Entretenimiento | 7670 |
| Viajes—Otros | 7675 | Vida/Seguridad | 7340 Life/Safety |

**Las 13 líneas de opex que NO se pueden alimentar:**

| Excel | Depto | Estado | Por qué |
|---|---|---|---|
| Desayunos (fila 319) | A&B | **NO EXISTE** | no hay cuenta 7xxx equivalente; se está usando algo local del libro externo |
| Fees (fila 590) | Club Madresal | **NO EXISTE** (ambiguo) | etiqueta genérica; candidatas 7365 Management Fees o 7530 Royalty Fees — hay que preguntarle al owner |
| Seguro de propiedad (fila 591) | Club Madresal | **NO EXISTE** en clase 7 | el sistema lo tiene solo como below-GOP (8015). Un seguro dentro del depto necesitaría cuenta propia |
| Combustible (fila 894) | Servicios Públicos | **NO EXISTE** | el sistema tiene 7395 (Generador) y 7420 (Otros); el Excel abre 4 líneas de combustible |
| Combustible (Lancha y Equipo) (fila 895) | Servicios Públicos | **NO EXISTE** | idem — `OH_UTILITIES` tiene 8 cuentas mapeadas contra 10 líneas del Excel |
| 8 líneas de opex de Bar Privado | Bar Privado | **NO EXISTE** | sin departamento |

### 3.8 Gastos de Propiedad / below-GOP (11 líneas)

| Excel | Estado | Cuenta → línea |
|---|---|---|
| Alquiler | YA EXISTE | 8000 → `RENT` |
| Honorarios de Administración | YA EXISTE (con reserva) | 8005 → `MGMT_FEE_3` **y** `MGMT_FEE_5_ROYALTIES` |
| Seguro de Propiedad | YA EXISTE | 8015 → `PROPERTY_INSURANCE` |
| Intereses sobre Préstamos | YA EXISTE | 8035 → `BANK_INTEREST` |
| Cargos Bancarios y Comisiones | YA EXISTE (mal nombrada) | 8030 "BANK AND COMMISSIONS CHARGES" → línea **`LEASINGS_RENTS`** (nombre del reporte: "LEASINGS/RENTS") |
| Ganancia / Pérdida Cambiaria | YA EXISTE | 8045 → `FINANCIAL_LOSSES` |
| Reserva de Capital | YA EXISTE (con reserva) | 8020 → `CAPITAL_RESERVE` |
| **Gasto de Capital Mayor** | **OTRA GRANULARIDAD** | la línea `LARGE_CAPEX` existe en `report_line_config` pero **no tiene ninguna regla en `account_mapping`**; en `belowgop_account_entries` la 8020 está cargada con el nombre "LARGE CAPITAL EXPENDITURE" |
| Depreciación | YA EXISTE | 8040 → `DEPRECIATION` |
| Multas y Otros No Deducibles | YA EXISTE | 8025 → `OTHER_EXPENSES` |
| Impuesto sobre la Renta | YA EXISTE | 8060 → `INCOME_TAXES` |

> ⚠️ En el Budget 2027 `belowgop_account_entries` = 0 y `nonop_entries` tiene 0–2
> filas. Todo este bloque sale hoy de fórmulas (`ManualInputs`) o de cero.

### 3.9 Subtotales de los bloques de detalle (80 líneas)

Todos derivables de sus componentes (`Total Ingresos X`, `Total Costo de Ventas`,
`TOTAL NÓMINA`, `TOTAL GASTOS OPERATIVOS`, `UTILIDAD NETA X`, `% de Ingresos del
Depto.`, `% Utilidad`). **72 se pueden calcular hoy; 8 son del bloque Bar Privado
y por lo tanto no.**

---

## 4. Los HUECOS — qué hay que construir

| # | Hueco | Tamaño | Detalle |
|---|---|---|---|
| 1 | **El reporte en sí**: ensamblador que arma las 781 líneas en el orden del Excel, con etiquetas en español, 12 meses + Total Año | **GRANDE** | Es el trabajo principal. Necesita: (a) una tabla de layout (tipo `report_line_config` pero a nivel cuenta×depto), (b) un endpoint que junte `opex/dept/summary`, `costs/dept/summary`, `payroll/dept/summary`, `revenue_account_entries` y `belowgop_account_entries` por mes, (c) la página frontend, (d) el export a Excel. El motor de cálculo **no hay que tocarlo**. |
| 2 | **Estadísticas Club Madresal** (4 líneas) | CHICO | Tabla nueva `club_membership_stats(scenario_id, month, total, condicionados, pagando, acuerdo_pago)` + endpoint + captura. Análoga a `scenario_stats`, que ya existe y funciona. |
| 3 | **Departamento Bar Privado** (31 líneas: 4 ingreso + 3 costo + 16 planilla + 8 opex) | MEDIANO | Decidir si es depto propio o sub-depto de A&B. Requiere: fila en `department_catalog` con `default_pl_group` propio, `line_code`s `REV_BAR/OPEX_BAR/PROFIT_BAR` en `report_line_config`, cuentas 4xxx/5xxx y reglas en `account_mapping`. **Cambia `PROFIT_FB`** si hoy había plata de bar ahí adentro. |
| 4 | **Apertura de A&B por outlet** (18 líneas) | MEDIANO | El Excel abre 4 sub-cuentas por familia (Alimentos ×4, Cerveza ×4…). Hay que crear las cuentas (4111-4113, 4121-4123, 4126-4128, etc.) y cargarlas. Si el GL de CWL no las tiene, **no se puede** y hay que aceptar 6 líneas en vez de 24. |
| 5 | **Detalle de ingresos por cuenta en escenarios checkbook** (60 líneas) | **GRANDE** | El Budget 2027 no tiene `revenue_account_entries`. Opciones: (a) un mini-checkbook de ingresos por cuenta que conviva con las rate cards, (b) una regla de apertura declarada por el owner (% por cuenta), (c) mostrar el detalle solo en escenarios importados. **(c) es lo honesto**; (b) inventa números. |
| 6 | **Below-GOP por cuenta en checkbook** (11 líneas) | MEDIANO | `nonop_entries` ya es un mini-checkbook por `report_line_code` + cuenta; hoy solo tiene 2 filas. Falta cargarlo y ampliarlo a las 11 cuentas del Excel. |
| 7 | **Endpoints de detalle mensuales** | CHICO | `/scenarios/{id}/revenue-detail/report/` y `/belowgop-detail/report/` hoy devuelven **solo el total anual**. Hay que devolver los 12 meses (el modelo ya los tiene: `jan…dec`). |
| 8 | **6 cuentas faltantes** | CHICO | Desayunos (A&B), Fees + Seguro de propiedad (Club), Combustible + Combustible Lancha (Servicios Públicos), y separar No Show / Habitaciones de la 4000. Alta en `accounts` + `account_mapping`. |
| 9 | **Mano de Obra por Contrato (6031) como concepto de planilla** | CHICO | Columna `c6031_contract_labor` en `payroll_concept_entries` + su lugar en `summarize_dept()`. Ojo: CLAUDE.md del proyecto hermano dice que el contract labor va a la 7105 — hay que confirmar el criterio con el owner. |
| 10 | **Ubicación de Área Recreativa** | CHICO (decisión) | El Excel la pone en overhead, el sistema en operativo. Es una línea de configuración (`department_catalog.pl_kind` del dept 270), pero **cambia `OPERATING_PROFIT` y `TOTAL_OVERHEAD`** (no el GOP). |
| 11 | **KPI "Habitaciones por Día"** | CHICO | `rooms_available / días del mes`, emitir `KPI_ROOMS_PER_DAY` en `_kpis()`. |
| 12 | **Datos que faltan cargar (no es código)** | MEDIANO | Budget 2027: 3 líneas de costo contra 35; Club (260) y AREC (270) sin opex; below-GOP vacío. Escenarios 2028–2035 completamente vacíos. |

---

## 5. Riesgos — dónde el Excel y el sistema pueden dar números distintos para lo que parece la misma línea

1. **Área Recreativa (dept 270) — arriba o abajo de la Utilidad Operativa.**
   El Excel la lista como gasto general (fila 76 = `D940`, planilla + opex de
   AREC) y **no le da línea de ingreso en el resumen**, aunque su bloque de
   detalle (filas 900–942) sí tiene ingreso, costo, planilla y opex, y calcula
   "UTILIDAD NETA ÁREA RECREATIVA". El sistema la trata como departamento
   **operativo** (`OPERATING_DEPT_GROUPS["AREC"] = ["270"]`). El GOP sale igual;
   **UTILIDAD OPERATIVA y TOTAL GASTOS GENERALES no.** Hay que elegir uno y
   dejarlo escrito.

2. **Honorarios de Administración — una línea en el Excel, dos en el sistema.**
   El Excel tiene "Honorarios de Administración (5%)". `report_line_config` tiene
   `MGMT_FEE_3` (3 %) y `MGMT_FEE_5_ROYALTIES` (5 %), y **las dos mapean a la
   misma cuenta 8005**. Peor: en escenarios budget/forecast el fee se calcula por
   **fórmula** (`total_revenue × mgmt_fee_pct`), no del GL — y `mgmt_fee_pct_3`
   tiene default **0** a propósito (había un 3 % fantasma que inflaba el
   below-GOP; ver el comentario en `pl_engine.ManualInputs`). Si el Excel espera
   un 5 % y el escenario tiene el pct en 0, la línea sale en cero.

3. **La cuenta 8020 tiene tres verdades distintas.**
   - `account_mapping`: 8020 = "CAPITAL RESERVE" → línea `CAPITAL_RESERVE`
   - `belowgop_account_entries` (dato real cargado): 8020 = "LARGE CAPITAL EXPENDITURE"
   - `pl_engine.NONOP_ACCOUNT_MAP`: `"8020": "mgmt_fee"`
   Y `LARGE_CAPEX` (Mejoras Mayores) **no tiene ninguna cuenta mapeada**. Según
   por dónde entre el dato, la misma plata cae en Reserva de Capital, en Mejoras
   Mayores o en Honorarios de Administración. **Esto hay que resolverlo antes de
   publicar el reporte.**

4. **8030 "Cargos Bancarios y Comisiones" está mapeada a una línea llamada
   `LEASINGS_RENTS`** ("LEASINGS/RENTS"), marcada `MAPPED_REVIEW` con la nota
   *"Source account currently labelled bank/commissions; verify"*. El Excel la
   quiere como "Cargos Bancarios y Comisiones". Es un renombre, pero si alguien
   la lee como leasing va a cuadrar mal contra el flujo de caja.

5. **Lavandería: el Excel mezcla las dos lavanderías.**
   El sistema separa **0162 Laundry Revenue** (servicio que se vende afuera —
   operativo) de **0161 Laundry Operations** (la interna, que es *allocation* y
   netea a cero, regla permanente de CLAUDE.md §"ALLOCATION_EXCLUDE"). El bloque
   "DEPARTAMENTO DE LAVANDERÍA" del Excel toma su planilla de las filas
   `K1159–K1179` del libro externo (o sea, del bloque de la lavandería interna) y
   su ingreso de `K786–K793`. Si el reporte suma las dos, **duplica** la
   lavandería interna que el motor ya repartió a los departamentos.

6. **Cafetería (0220) no aparece en el Excel.** El sistema la excluye del P&L de
   actuales (`ACTUAL_EXCLUDED_DEPTS = {"0220"}`) porque su costo ya está dentro
   de la planilla de cada depto vía el concepto 6025. Coincide con el Excel —
   pero si alguien agrega el bloque de Cafetería al reporte, se duplica.

7. **La cuenta 7380 "Miscellaneous" aparece en 8 departamentos distintos.**
   El resolvedor de `pl_engine.construir_resolvedor()` busca por
   `(depto, cuenta)` y solo si falla cae a un **FALLBACK por cuenta que depende
   del orden físico de las filas**. Si un depto del Excel no tiene su regla
   propia para la 7380, ese gasto puede terminar en otro departamento. Lo mismo
   con "Varios", "Suministros Operativos" (12 apariciones), "Capacitación" (12),
   "Viajes—Otros" (12).

8. **Signos en los ingresos.** "Cancelaciones", "No Show", "Pérdidas Cambiarias"
   y "Descuento por Pronto Pago" son **restas** dentro del bloque INGRESOS del
   Excel. En `account_mapping` el signo depende de `rollup_operator`
   (`SUM` | `SUBTRACT`). Un signo mal puesto en la 4000 mueve todo el room
   revenue.

9. **Impuesto sobre la Renta.** El Excel lo toma de la cuenta 8060 del GL. El
   motor usa el 8060 **solo si viene distinto de cero**; si no, calcula
   `max(EBT × 30 %, 0)`. En un mes con EBT positivo y sin impuesto registrado, el
   sistema muestra impuesto y el Excel muestra cero (o al revés).

10. **Bar Privado dentro de A&B.** Si hoy hay plata de bar en `REV_FB`/`OPEX_FB`
    y se crea el departamento nuevo, **A&B cambia** — y todos los escenarios
    enllavados de 2027 seguirían recalculándose con el motor de hoy (ver
    `docs` / memoria: "enllavar NO congela los números": `pl_lines` se escribe y
    nunca se lee). O sea, el cambio se propaga hacia atrás.

11. **El Excel dice "Presupuesto 2026 Consolidado"** y sus fórmulas apuntan a
    `Budget 2025W`. Antes de cuadrar contra el sistema hay que confirmar **qué
    escenario** es el que tiene que dar igual: `2026 BUDGET Final` (importado,
    636 `actual_pl_lines`) o el `2026 ACTUAL`.

12. **Escenarios vacíos.** 2028–2035 (`BUDGET Working`, importados) tienen 0 filas
    en absolutamente todas las tablas de detalle. El reporte les saldría en cero
    sin avisar; conviene que el endpoint devuelva un aviso explícito.

---

## 6. Recomendación de secuencia

1. **Resolver los riesgos 1, 2 y 3 primero** (Área Recreativa, honorarios, cuenta
   8020 / `LARGE_CAPEX`). Son decisiones del owner, no código, y determinan si el
   reporte cuadra o no.
2. Confirmar contra qué escenario tiene que cuadrar (riesgo 11) y medir el
   TOTAL REVENUES / GOP / NET PROFIT **antes** de construir nada.
3. Construir el ensamblador (hueco 1) **solo para escenarios importados**, que es
   donde el 90 % es real.
4. Huecos chicos en paralelo: 7, 8, 11.
5. Club Madresal (2) y Bar Privado (3) como incrementos aparte.
6. El detalle de ingresos en checkbook (5) queda para el final, y probablemente
   la respuesta correcta sea "en escenarios checkbook el reporte muestra el
   resumen, no el detalle de ingresos".

---

*Escaneo generado el 2026-08-11 leyendo la base de producción en solo-lectura.
No se escribió nada en la base.*
