# CLAUDE.md — FinPlan CWL
## Especificación técnica completa para Claude Code
## Versión 2.0 — Basada en archivos reales de Corcovado Wilderness Lodge

> **Lee este archivo completo antes de escribir cualquier línea de código.**
> Contiene la arquitectura, fuentes de datos reales, reglas de negocio y convenciones del proyecto.

---

## 1. CONTEXTO DEL PROYECTO

### Empresa y propiedad piloto
- **Empresa:** Seed Costa Rica S.A. — `fincontroller@seedcostarica.com`
- **Grupo hotelero:** The Costa Rica Collection
- **Propiedad piloto v1:** Corcovado Wilderness Lodge (`CWL`)
- **Moneda base:** USD
- **Tipo de cambio:** parámetro configurable (default 530 CRC/USD)
- **Año fiscal:** enero–diciembre
- **Estándar contable:** USALI (Uniform System of Accounts for the Lodging Industry)
- **Sistema contable fuente:** Integrity SDG + QuickBooks

### ⚠️ REGLA PERMANENTE — Departamentos de ALLOCATION (aplica a TODO mes/año/escenario)
Algunos departamentos no son operativos: su gasto se **reparte (aloca)** a otros vía la
cuenta **"Distribución"** (4xxx negativa) y NO debe entrar a los totales operativos. La
regla vive en código: `ALLOCATION_EXCLUDE` en `app/importers/gl_detail_importer.py`
(la aplican el importador GL y los reportes de planilla/costos/opex), y está blindada por
`tests/test_gl_allocation.py`. Aplica automáticamente a cada bloque/escenario/mes — NO hay
paso manual; subir cualquier mes futuro la respeta.
- **0220 (Employee Dining / comida): allocation TOTAL** → excluir costo(5)/planilla(6)/opex(7). Netea a 0.
- **0161 (Laundry): SPLIT** → la lavandería interna (planilla 6 + insumos 7) es allocation
  (netea a 0); el **Laundry Services** que vende afuera es OPERATIVO → su ingreso(4) y
  costo de venta(5) SE QUEDAN. Excluir solo 6 y 7.
- La cuenta 4xxx "Distribución" se excluye del revenue (es el crédito de alocación, no ingreso).
- **Verificado:** con esta regla el profit por categorías = Net del P&L al centavo (Budget y Actual, YTD y Full Year).

### ⚠️ REGLA PERMANENTE — El SEED manda sobre `account_mapping` y `report_line_config`
`backend/Procfile` arranca con `alembic upgrade head && python -m app.seed && uvicorn`.
`app/seed_mapping.py` corre **en cada deploy** y re-afirma **campo por campo** todas las
filas de esas dos tablas desde `app/seed_data/mapping_pl.json`, buscándolas por su llave
de negocio (`report_id + line_code`; `report_id + source_department + account_code +
source_origin`).

**Una migración que toque esas dos tablas y NO cambie también el JSON se revierte sola en
el próximo deploy.** Pasó con las migraciones 093/094/095: corrieron, se midió el efecto
contra producción, quedó verificado — y el deploy siguiente las borró. Es el modo de falla
más caro que tiene el sistema porque **el total sigue cuadrando**: no hay error, no hay
alerta, y la plata cambia de línea sola. Solo se ve en el P&L por departamento.

- Al cambiar el mapeo: **editar `app/seed_data/mapping_pl.json`** y, si hace falta que
  quede bien ya, agregar la migración que lo aplica *también* a la base actual.
- El seed **no borra lo que sobra** (a propósito: borrar por ausencia le vaciaría el P&L a
  un hotel con mapeos propios). Renombrar una fila deja **las dos** — la vieja vuelve del
  JSON y la nueva se queda huérfana. Si se renombra, hay que borrar la vieja por migración.
- Blindado por `tests/test_seed_manda_sobre_mapeo.py`.

### Habitaciones CWL (30 unidades en 6 categorías)
| # | Tipo | Unidades | Pax típico |
|---|------|----------|------------|
| 1 | Corcovado Deluxe Villas, King bed | 6 | 1-2 |
| 2 | Carate Deluxe Villa Double Beds | 2 | 2 |
| 3 | Agujas Villa 2 Queen Beds | 4 | 2-4 |
| 4 | Sirena Suites, Queen Bed (connecting) | 8 | 2-4 |
| 5 | Treehouse king bed | 5 | 1-2 |
| 6 | 5 Elements Treehouse king bed | 5 | 1-2 |
| — | Other Rooms Revenue | — | ingresos varios sin tipo |

**Datos reales YTD Mayo 2026 (referencia de validación):**
| Tipo | Noches Disp | Noches Occ | Ocup% | Revenue | ADR | Pax |
|------|------------|-----------|-------|---------|-----|-----|
| Corcovado Deluxe King | 906 | 556 | 61.4% | $265,399 | $477.34 | 948 |
| Carate Double | 302 | 205 | 67.9% | $91,943 | $448.50 | 462 |
| Agujas Queen | 604 | 338 | 56.0% | $144,446 | $427.36 | 676 |
| Sirena Suites | 1,208 | 702 | 58.1% | $237,902 | $338.89 | 1,065 |
| Treehouse | 755 | 553 | 73.2% | $378,943 | $685.25 | 885 |
| 5 Elements Treehouse | 755 | 489 | 64.8% | $452,241 | $924.83 | 847 |
| **TOTAL** | **4,530** | **2,843** | **62.8%** | **$1,570,875** | **$552.54** | **4,883** |

### Qué es este sistema
FinPlan CWL es un sistema de **planificación y análisis financiero hotelero USALI-compliant** que permite:
1. **Construir** el Budget y el Forecast directamente dentro del sistema (entrada de datos)
2. **Subir** los Actuales desde archivos Excel exportados de Integrity/QuickBooks (solo importación)
3. **Comparar** ACTUAL vs BUDGET vs FORECAST por mes, acumulado y departamento
4. **Generar** el P&L USALI completo (Revenue → GOP → EBITDA → Net Profit)
5. **Analizar** KPIs operativos (Occupancy, ADR, RevPAR por tipo de villa)
6. **Exportar** reportes a Excel y PDF

### Modelo de entrada de datos por módulo
| Módulo | ACTUAL | BUDGET | FORECAST |
|--------|--------|--------|----------|
| Ingresos | Upload Excel | Entrada en sistema | Entrada en sistema |
| OPEX | Upload Excel | Entrada en sistema (checkbook por dept) | Entrada en sistema |
| Planilla | Upload Excel | Entrada en sistema (checkbook por dept) | Entrada en sistema |
| KPIs | Upload Excel | Entrada en sistema | Entrada en sistema |

---

## 2. FUENTES DE DATOS REALES

Todos los archivos viven en la carpeta `data/raw/` del proyecto. Nunca modificar los originales.

### 2.1 Catálogo de Cuentas (Integrity)
**Archivo:** `CATALOGO_DE_CUENTAS_THE_COSTA_RICA_COLLECTION.xlsx`
- Hoja: `DATA`
- 31,269 cuentas con jerarquía de 7 segmentos
- Formato de código: `XXXX-XXXX-XXX-XXX-XXX-XX-XX`
- Tipos: `I` (Income), `G` (Gasto/Expense), `T` (Cost of Sales)
- 23,292 cuentas hoja (AceptaMov = Sí), 7,977 agrupadores

### 2.2 Catálogo de Planilla (Integrity)
**Archivo:** `PLANNING_CATALOGO.xlsx`
- Hoja `DATA PAYROLL`: cuentas clase 6000-6030 con jerarquía de 7 niveles
- Hoja `Planning`: diccionario de niveles (departamentos, posiciones, categorías)

**Estructura de cuenta de planilla:**
```
6000 - 0111 - 500 - 011 - 015 - 00 - 00
│      │      │     │     │
│      │      │     │     └── Categoría (010=Expats, 015=Local Perm, 020=Temporal)
│      │      │     └──────── Clase empleado (010=Directors, 011=Managers, 012=Supervisors, 013=Line Staff)
│      │      └────────────── Posición (500=Manager, 501=Agent, 502=Night Auditor...)
│      └───────────────────── Departamento (0111=Front Desk, 0120=F&B, 0150=Tours, etc.)
└──────────────────────────── Concepto nómina (6000=S&W, 6001=OT, 6021=Aguinaldo...)
```

### 2.3 Codificación de Planilla (QuickBooks)
**Archivo:** `Codificacion_Planilla_11_de_febrero.xlsx`
- Hoja `Hoja1`: 4,376 filas — mapeo completo de conceptos de nómina
- Columnas clave: `Codigo_Depto`, `Depto`, `Codigo_Ocupacion`, `Ocupación`, `TIPO`, `Codigo`, `Descripción`, `Tipo_Plaza`, `Nivel1..7`
- Tipos: `1-DEVENGADOS` (ingresos al empleado), `2-DEDUCCIONES`, `3-RESERVAS` (cargas patronales)
- Conceptos principales:
  - 1001 → ORDINARIO → cuenta 6000
  - 1002 → HORAS EXTRAORDINARIAS → cuenta 6001
  - 1007 → DÍA FERIADO/LIBRE LABORADO → cuenta 6002
  - 1010 → DISFRUTE DE VACACIONES → cuenta 6024
  - 1112 → AGUINALDO → cuenta 6021
  - 4001 → PREAVISO Y CESANTIA → cuenta 6026
  - 4002 → TRANSPORTE → cuenta 6029
  - 3001 → ALOJAMIENTO → cuenta 6028
  - 0003 → C.C.S.S. 26.83% → cuenta 6020
  - 1113 → COMISIONES → cuenta 6010

### 2.4 Mapping Actual (QuickBooks → USALI)
**Archivo:** `MAPPING_USALI_QUICKBOOKS_2025.xlsx`
- Hoja `CONSOLIDADOV (2)`: puente entre QuickBooks y USALI
- Columnas: `Link`, `Department`, `GL_Acc`, `Description`, `Cuenta_USALI`, `Tipo`, `Origen`, `Secuencia_dept`, `Departamento`, + meses T-ENE a T-DIC
- Departamentos: Rooms (1), F&B (2), Spa (3), Activities (4), Retail (5), Innoceana (6), Transportation (6)
- Esto es el **Actual** — viene de QuickBooks con cuentas USALI cortas (4000, 4110, 4125, etc.)

### 2.5 Revenue Budget (Auxiliar de Ingresos)
**Archivo:** `Budget2026_Revenue_CORCO.xlsx`
- Hoja `Summary`: resumen por línea de ingreso × 12 meses
- Hojas individuales: `Rooms`, `Food Revenue`, `Beverage Revenue`, `F&B Mis Revenue`, `Spa Revenue`, `Retail Gift Shop`, `Activities`, `Transportation`, `Innoceanna`, `Sustainability Fee`, `Laundry`
- Hoja `Rates 2026` / `Key Indicators`: KPIs por tipo de villa × mes (occupancy, ADR, RevPAR)
- **Fila de budget 2026:** fila B10:M10 en cada hoja individual

**KPIs clave en Summary:**
- Total available Rooms, Total Rooms Occupied, Total Guests
- % Occupancy, ADR, RevPAR
- Ingresos por línea: Rooms, Food, Beverage, F&B Misc, Spa, Retail, Activities, Transport, Innoceana, Sustainability, Laundry

### 2.6 OPEX Checkbooks (18 archivos por departamento)
**Patrón de archivos:** `OPEXC_2026__[DEPT]__BUDGET.xlsx`

| Archivo | Departamento | Código |
|---------|-------------|--------|
| ROOMS | Habitaciones | 0110 |
| F_B | Alimentos y Bebidas | 0120 |
| SPA | Spa | 0130 |
| ADMIN | Administración | 0180 |
| IT | Sistemas | 0190 |
| OWN | Propietarios | 0200 |
| SALES | Ventas y Marketing | 0190 |
| UTILITY | Utilities/Energía | 0200 |
| LAUND | Lavandería | 0161 |
| ACT | Actividades | 0150 |
| C_BOSQ | Crowler/Bosque | 0156 |
| CAF | Cafetería | n/a |
| CROW | Crowther | 0156 |
| INNO | Innoceana | 0155 |
| MAINT | Mantenimiento | 0200 |
| RETAIL | Retail Gift Shop | 0165 |
| TRANSP | Transporte | 0152 |

**Estructura de cada checkbook (fila de datos desde ~fila 12):**
```
Col B: # Cuenta (USALI corto: 7015, 7025, 7065, etc.)
Col C: Descripcion de Cuenta
Col D: Departamento (código 4 dígitos: 0120, 0180, etc.)
Col E: Detalle (sub-código numérico: 800, 801, 802...)
Col F: Detalle Descripción (descripción en español)
Col G-R: 12 meses (fechas como 2026-01-01, 2026-02-01...)
Col S: Total anual
```

**Importante:** Las filas 3-5 de cada checkbook tienen totales de GRAN TOTAL por año (2024, 2025, 2026) que sirven como verificación.

### 2.7 P&L Consolidado (Forecast/Budget Summary)
**Archivo:** `FCST_May_500__2026.xlsx`
- Hoja `Budget 2025W`: P&L consolidado con Actual 2024, Actual 2025, Forecast 2026, Budget 2026
- Este archivo es el **destino** — el sistema debe replicar y mejorar este reporte
- Formato muy complejo (horizontal, cientos de columnas) — no importar directamente

---

## 3. MAPA DE CUENTAS CONTABLES — CLASES 4, 5 y 6

Este es el núcleo del modelo USALI. Claude Code debe conocer exactamente qué cuenta va en qué clase y qué departamentos las usan.

### 3.1 Clase 4 — INGRESOS (Tipo I)

18,318 cuentas totales. Se registran con signo positivo en el P&L.

| Rango | Descripción | Departamento principal |
|-------|-------------|----------------------|
| 4000–4099 | Rooms Revenue | 0110 |
| 4110–4132 | F&B Revenue (Food, NA Bev, Beer, Liquor, Wine, Misc) | 0120–0131 |
| 4201–4216 | Spa Services Revenue | 0130–0133 |
| 4250–4258 | Spa Retail Revenue | 0140 |
| 4301–4321 | Retail Gift Shop Revenue | 0151 |
| 4400–4403 | Activities Revenue (Grounds, Water, Pelagic, Other) | 0150 |
| 4500–4503 | Transportation Revenue (Grounds, Water, Air, Other) | 0152 |
| 4600–4603 | Innoceana Revenue | 0155 |
| 4700–4702 | Laundry Revenue (externo) | 0160–0161 |
| 4800–4890 | Miscellaneous Income (Cancellation fees, Interest, etc.) | varios |
| **4999** | **EXPENSE DISTRIBUTION ACCOUNTS-ALLOCATIONS** | 0220 (Cafetería) |

> **⚠️ Cuenta 4999:** Es el mecanismo de allocation de salida. Cuando Cafetería hace el allocation, registra un crédito en 4999-0220 (ingreso ficticio que cancela el gasto) y un débito en los departamentos receptores. Esta cuenta **siempre debe sumar cero** a nivel de hotel.

### 3.2 Clase 5 — COST OF SALES (Tipo T)

106 cuentas totales. Son el costo directo de lo que se vende — van **inmediatamente después** del ingreso correspondiente en el P&L departamental. **Nunca aparecen en Rooms, Admin, Sales, Maintenance, ni Owners.**

| Rango | Descripción | Departamento | Vinculado a ingreso |
|-------|-------------|--------------|---------------------|
| 5101–5165 | Food & Beverage Costs (Food, Bar, Freight, Bev, Wine, Beer, Misc) | **0120** (F&B) | 4110–4132 |
| 5201–5223 | Retail Store Costs (Clothing, Jewelry, Sundry, etc.) | **0151** (Retail) | 4301–4321 |
| 5300–5301 | Spa Retail Costs | **0140** (Spa Retail) | 4250–4258 |
| 5350–5351 | Activity Costs | **0150** (Activities) | 4400–4403 |
| 5360–5363 | Transportation Costs | **0152** (Transport) | 4500–4503 |
| 5380–5383 | Innoceana Costs | **0155** (Innoceana) | 4600–4603 |
| 5400–5404 | Cost of Telecom/Internet Services | **0230** (IT) | n/a |
| 5420–5421 | **Cost of Food Cafetería Empleados** | **0220** (Cafetería) | n/a |
| 5501 | Laundry Costs | **0160** (Laundry) | 4700–4702 |

> **⚠️ Cuentas 5420–5421 (Cafetería):** El costo de los alimentos de la cafetería de empleados. Van al dept 0220. Al hacer el allocation de cafetería, este costo (junto con la planilla 6xxx-0220 y el OPEX 7xxx-0220) queda en cero vía la cuenta 4999.

> **⚠️ Cuenta 5501 (Laundry):** El costo de la lavandería. Va al dept 0160. Al hacer el allocation de lavandería, queda en cero vía 4999.

**Gross Profit departamental:**
```
Dept Revenue (4xxx) − Cost of Sales (5xxx) = Gross Profit
```

### 3.3 Clase 6 — PLANILLA (Tipo G)

14,062 cuentas totales, 17 conceptos de nómina × departamento × posición × categoría.

| Cuenta | Concepto | Tipo |
|--------|----------|------|
| 6000 | SALARIES AND WAGES | Devengado |
| 6001 | OVERTIME | Devengado |
| 6002 | DAYS OFF LAB | Devengado |
| 6003 | WORKED HOLIDAYS | Devengado |
| 6004 | DISABILITIES | Devengado |
| 6010 | COMMISSIONS | Devengado |
| 6020 | CCSS (Carga Patronal 26.83%) | Carga patronal |
| 6021 | 13TH SALARY (Aguinaldo 1/12) | Provisión |
| 6022 | OCCUPATIONAL HAZARDS (INS 1.50%) | Carga patronal |
| 6023 | PROVISION VACATIONS (2/52) | Provisión |
| 6024 | VACATION TAKEN | Devengado real |
| 6025 | CAFETERIA | Beneficio |
| 6026 | NOTICE AND SEVERANCE (5.5%/12) | Provisión |
| 6027 | INCENTIVE BONUS | Variable |
| 6028 | HOUSING BENEFIT | Beneficio en especie |
| 6029 | TRANSPORTATION | Beneficio |
| 6030 | OTHER BENEFITS | Beneficio |

**Departamentos de planilla en CWL (seg2 de cuentas 6):**

| Dept | Descripción | # Cuentas 6 | Cuentas 5 |
|------|-------------|-------------|-----------|
| 0111 | Front Desk / Rooms | 629 | No |
| 0112 | Reservations | 289 | No |
| 0113 | Housekeeping | 629 | No |
| 0114 | Concierge | 546 | No |
| 0121 | F&B Management | 204 | No |
| 0122 | Kitchen | 1,479 | No |
| 0123 | Restaurant Vitrales | 782 | No |
| 0128 | Private Bar | 12 | 5165 |
| 0131 | Spa Management | 187 | No |
| 0132 | Spa Therapists | 272 | No |
| 0133 | Spa Front Desk | 119 | No |
| 0150 | Tours / Activities | 881 | 5350–5351 |
| 0152 | Transportation | 715 | 5360–5363 |
| 0155 | Innoceana | 544 | 5380–5383 |
| 0156 | Crowther Lab | 544 | No |
| 0161 | Laundry | 190 | 5501 |
| 0181 | General Management | 442 | No |
| 0182 | Finance | 629 | No |
| 0183 | Purchasing | 314 | No |
| 0184 | Human Resources | 714 | No |
| 0186 | Security | 272 | No |
| 0190 | Sales & Marketing | 374 | No |
| 0200 | Maintenance | 1,383 | No |
| 0205 | Utilities (sub de Maintenance) | 273 | No |
| **0220** | **Cafetería Empleados** | 1,504 | 5420–5421 |
| 0230 | IT | 118 | 5400–5404 |

> **Regla crítica de planilla:** Al calcular el P&L, los gastos de planilla se agrupan por `seg2` (departamento). Nunca sumar 6xxx sin filtrar por departamento — la misma cuenta 6000 existe en todos los departamentos.

### 3.4 Resumen: qué departamentos tienen qué clases de cuentas

```
DEPARTAMENTO        INGRESOS(4)  COSTO(5)  PLANILLA(6)  OPEX(7)  RESULTADO
───────────────────────────────────────────────────────────────────────────
Rooms (0110)            ✓          ✗           ✓           ✓       Dept Profit
F&B (0120-0131)         ✓          ✓           ✓           ✓       Dept Profit
Spa (0130-0133)         ✓          ✓           ✓           ✓       Dept Profit
Activities (0150)       ✓          ✓           ✓           ✓       Dept Profit
Retail (0151)           ✓          ✓           ✓           ✓       Dept Profit
Transport (0152)        ✓          ✓           ✓           ✓       Dept Profit
Innoceana (0155)        ✓          ✓           ✓           ✓       Dept Profit
Laundry (0160-0161)     ✓*         ✓           ✓           ✓       CERO (allocation)
Cafetería (0220)        4999*      ✓           ✓           ✓       CERO (allocation)
IT (0230)               ✗          ✓           ✓           ✓       Overhead
Admin (0180-0186)       ✗          ✗           ✓           ✓       Overhead
Sales (0190)            ✗          ✗           ✓           ✓       Overhead
Maintenance (0200-0205) ✗          ✗           ✓           ✓       Overhead
Owners (8xxx)           ✗          ✗           ✗           8xxx    Below GOP

* Laundry 4700 = ingreso externo si aplica; Cafetería 4999 = solo para allocation
```

---

## 4. ARQUITECTURA Y STACK TECNOLÓGICO

```
Backend:     Python 3.11+ · FastAPI · SQLAlchemy (async)
Database:    PostgreSQL 15+
Frontend:    Next.js 14 · React · TypeScript · Tailwind CSS · Recharts
Export:      openpyxl (Excel) · WeasyPrint (PDF)
Auth:        NextAuth.js · JWT
Deploy:      Railway (backend + DB) · Vercel (frontend)
Tests:       pytest (backend) · Vitest (frontend)
```

### Estructura de directorios
```
finplan-cwl/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models/
│   │   │   ├── account.py          # Catálogo USALI
│   │   │   ├── payroll_catalog.py  # Catálogo planilla
│   │   │   ├── hotel.py
│   │   │   ├── scenario.py         # Actual / Budget / Forecast
│   │   │   ├── revenue_entry.py    # Líneas de ingreso
│   │   │   ├── opex_entry.py       # Líneas de gasto OPEX
│   │   │   ├── payroll_entry.py    # Líneas de planilla
│   │   │   └── kpi.py              # Estadísticas operativas
│   │   ├── importers/
│   │   │   ├── base.py
│   │   │   ├── catalog_importer.py     # Catálogo de cuentas
│   │   │   ├── payroll_catalog_importer.py
│   │   │   ├── actual_importer.py      # MAPPING_USALI_QUICKBOOKS
│   │   │   ├── revenue_importer.py     # Budget2026_Revenue_CORCO
│   │   │   ├── opex_importer.py        # OPEX checkbooks (18 archivos)
│   │   │   └── payroll_importer.py     # Codificacion_Planilla
│   │   ├── engine/
│   │   │   ├── pl.py               # P&L USALI (Revenue → GOP → EBITDA)
│   │   │   ├── kpis.py             # Occupancy, ADR, RevPAR
│   │   │   └── variance.py         # Actual vs Budget vs Forecast
│   │   ├── api/
│   │   │   ├── import_api.py
│   │   │   ├── pl_api.py
│   │   │   ├── kpi_api.py
│   │   │   ├── variance_api.py
│   │   │   └── export_api.py
│   │   ├── export/
│   │   │   ├── excel.py
│   │   │   └── pdf.py
│   │   └── db.py
│   ├── tests/
│   ├── alembic/
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── dashboard/              # KPIs ejecutivos
│   │   ├── pl/                     # P&L por escenario
│   │   ├── revenue/                # Análisis de ingresos
│   │   ├── opex/                   # Análisis de gastos
│   │   ├── payroll/                # Análisis de planilla
│   │   └── import/                 # Carga de archivos
│   └── components/
├── data/
│   └── raw/                        # Archivos Excel originales (nunca modificar)
└── CLAUDE.md
```

---

## 5. ESQUEMA DE BASE DE DATOS

### 5.1 Catálogo de cuentas USALI
```python
class Account(Base):
    __tablename__ = 'accounts'
    
    code_full: str          # '4000-0110-001-001-001-01-01' — PRIMARY KEY
    seg1: str               # '4000' — clase USALI (Income/Expense/Cost)
    seg2: str               # '0110' — departamento
    seg3: str               # '001'  — posición/subgrupo
    seg4: str               # '001'
    seg5: str               # '001'
    seg6: str               # '01'
    seg7: str               # '01'
    descripcion: str
    tipo: str               # 'I' | 'G' | 'T'
    estado: str             # 'A' | 'I'
    acepta_mov: bool        # True = cuenta hoja (puede recibir transacciones)
    usa_cc: bool
    aplica_diferencial: bool
    link_id: int            # número secuencial de Integrity
```

### 5.2 Catálogo de planilla
```python
class PayrollAccount(Base):
    __tablename__ = 'payroll_accounts'
    
    code_full: str          # '6000-0111-500-011-015-00-00'
    nivel1: int             # 6000 — concepto nómina (S&W, OT, Aguinaldo...)
    nivel2: int             # 0111 — departamento
    nivel3: int             # 500  — posición
    nivel4: int             # 011  — clase empleado
    nivel5: int             # 015  — categoría (Expat/Local Perm/Temporal)
    nivel6: int             # 00
    nivel7: int             # 00
    descripcion: str
    tipo: str               # 'G'
    acepta_mov: bool
    link_id: int
```

### 5.3 Hotel y escenario
```python
class Hotel(Base):
    __tablename__ = 'hotels'
    
    id: str                 # 'CWL'
    name: str               # 'Corcovado Wilderness Lodge'
    rooms: int              # 30
    tc_usd: Decimal         # 530 (tipo de cambio default)
    active: bool

class Scenario(Base):
    __tablename__ = 'scenarios'
    
    id: UUID
    hotel_id: str           # FK → Hotel
    year: int               # 2026
    type: str               # 'ACTUAL' | 'BUDGET' | 'FORECAST'
    version: str            # 'v1', 'FINAL', 'MAY_REFORECAST'
    status: str             # 'draft' | 'approved' | 'locked'
    source_file: str        # nombre del archivo importado
    imported_at: datetime
    created_by: str
```

### 5.4 Entradas de datos (normalizadas)
```python
# Una fila = una cuenta × un mes × un escenario
class FinancialEntry(Base):
    __tablename__ = 'financial_entries'
    
    id: UUID
    scenario_id: UUID       # FK → Scenario
    hotel_id: str
    account_code: str       # código USALI corto: '7065', '4000', '6000'
    dept_code: str          # '0120', '0180', etc.
    detail_code: str        # '800', '801' — sub-línea del checkbook (nullable)
    detail_desc: str        # descripción en español (nullable)
    entry_type: str         # 'REVENUE' | 'OPEX' | 'PAYROLL' | 'COST'
    month: int              # 1-12
    year: int
    amount_usd: Decimal
    amount_crc: Decimal     # nullable — si viene en CRC
    source: str             # 'REVENUE_FILE' | 'OPEX_CHECKBOOK' | 'PAYROLL' | 'ACTUAL_MAPPING'

# KPIs operativos (estadísticas clase 9)
class KpiEntry(Base):
    __tablename__ = 'kpi_entries'
    
    id: UUID
    scenario_id: UUID
    hotel_id: str
    room_type: str          # 'Corcovado Deluxe King' | 'ALL' | etc.
    month: int
    year: int
    rooms_available: int
    rooms_occupied: Decimal
    guests: Decimal
    occupancy_pct: Decimal  # 0.75 = 75%
    adr_usd: Decimal
    revpar_usd: Decimal
```

---

## 6. MÓDULO DE IMPORTACIÓN — REGLAS CRÍTICAS

### 6.1 Importador de catálogo de cuentas
```python
# importer: catalog_importer.py
# Fuente: CATALOGO_DE_CUENTAS_THE_COSTA_RICA_COLLECTION.xlsx → hoja DATA
# Header real en fila 4 (índice 3): Cuenta, Descripción, Tipo, Estado, AceptaMov, UsaCC, AplicaDif

def import_catalog(filepath: str) -> int:
    df = pd.read_excel(filepath, header=3)
    df.columns = ['Cuenta','Descripcion','Tipo','Estado','AceptaMov','UsaCC','AplicaDif']
    df = df.dropna(subset=['Cuenta'])
    
    for _, row in df.iterrows():
        parts = str(row['Cuenta']).split('-')
        # parts tiene exactamente 7 elementos
        account = Account(
            code_full=row['Cuenta'],
            seg1=parts[0], seg2=parts[1], seg3=parts[2],
            seg4=parts[3], seg5=parts[4], seg6=parts[5], seg7=parts[6],
            descripcion=row['Descripcion'],
            tipo=row['Tipo'],
            estado=row['Estado'],
            acepta_mov=(row['AceptaMov'] == 'Sí'),
            usa_cc=(row['UsaCC'] == 'Sí'),
            aplica_diferencial=(row['AplicaDif'] == 'Sí')
        )
```

### 6.2 Importador de OPEX checkbooks
```python
# importer: opex_importer.py
# Fuente: OPEXC_2026__[DEPT]__BUDGET.xlsx — hoja principal de cada archivo
# Los datos empiezan aproximadamente en fila 12 (después de las filas de summary)
# Hay que buscar la fila donde col[1] == '# Cuenta' para encontrar el header real

OPEX_FILES = {
    'ROOMS': ('OPEXCR_2026___ROOMS__BUDGET.xlsx', 'ROOMS'),
    'F_B':   ('OPEXC_2026__F_B__BUDGET.xlsx', 'F&B'),
    'SPA':   ('OPEXC_2026__SPA__BUDGET.xlsx', 'SPA'),
    'ADMIN': ('OPEXC__2026__ADMIN__BUDGET.xlsx', 'administración'),
    # ... etc
}

def find_header_row(df: pd.DataFrame) -> int:
    """Busca la fila donde aparece '# Cuenta' — ese es el header real."""
    for i, row in df.iterrows():
        if '# Cuenta' in str(row.values):
            return i
    raise ValueError("Header row not found")

def import_opex_checkbook(filepath: str, sheet_name: str, scenario_id: UUID, year: int):
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=None)
    header_row = find_header_row(df)
    
    # La fila siguiente al header tiene las fechas de meses
    # Las columnas de meses son fechas: 2026-01-01, 2026-02-01, etc.
    month_row = df.iloc[header_row + 1]
    
    # Datos empiezan 2 filas después del header
    data = df.iloc[header_row + 2:].copy()
    data = data[data.iloc[:, 1].notna()]  # Col B = # Cuenta
    
    for _, row in data.iterrows():
        account_code = str(row.iloc[1]).strip()   # Col B
        descripcion  = str(row.iloc[2]).strip()   # Col C
        dept_code    = str(row.iloc[3]).strip()   # Col D
        detail_code  = str(row.iloc[4]).strip()   # Col E
        detail_desc  = str(row.iloc[5]).strip()   # Col F
        
        for month_idx, col_idx in enumerate(range(6, 18)):  # Cols G-R = meses 1-12
            amount = row.iloc[col_idx]
            if pd.notna(amount) and float(amount) != 0:
                entry = FinancialEntry(
                    scenario_id=scenario_id,
                    account_code=account_code,
                    dept_code=dept_code,
                    detail_code=detail_code,
                    detail_desc=detail_desc,
                    entry_type='OPEX',
                    month=month_idx + 1,
                    year=year,
                    amount_usd=Decimal(str(amount)),
                    source='OPEX_CHECKBOOK'
                )
```

### 6.3 Importador de ingresos (Revenue Budget)
```python
# importer: revenue_importer.py
# Fuente: Budget2026_Revenue_CORCO.xlsx
# Hoja Summary fila 4 = headers, filas 17-25 = líneas de ingreso × 12 meses

REVENUE_LINES = {
    'Rooms':            ('4000', '0110'),
    'Food Revenue':     ('4110', '0120'),
    'Beverage Revenue': ('4120', '0120'),
    'F&B Mis Revenue':  ('4132', '0120'),
    'Spa Revenue':      ('4201', '0130'),
    'Retail Gift Shop': ('4301', '0165'),
    'Activities':       ('4400', '0150'),
    'Transportation':   ('4500', '0152'),
    'Innoceanna':       ('4600', '0155'),
    'Sustainability Fee':('4880', '0110'),
    'Laundry':          ('4700', '0161'),
}

# KPIs: leer hoja 'Rates 2026' o 'Key Indicators'
# Fila 5 = Units Available por mes
# Fila 6 = Days per month
# Filas 13-18 = unidades por tipo de villa
# Filas 24-29 = room nights available por tipo
# Más abajo = room nights occupied, occupancy%, ADR, RevPAR por tipo
```

### 6.4 Importador de actual (Mapping QuickBooks)
```python
# importer: actual_importer.py
# Fuente: MAPPING_USALI_QUICKBOOKS_2025.xlsx → hoja 'CONSOLIDADOV (2)'
# Header real en fila 6 (índice 5)
# Columnas: NaN, Link, Department, GL_Acc, Description, Cuenta_USALI, Tipo, Origen,
#           Secuencia_dept, Departamento, T-ENERO, T-FEBRERO, ..., T-AGOSTO

# IMPORTANTE: el campo 'Cuenta_USALI' tiene el nombre largo con guiones
# El campo 'GL_Acc' tiene el código USALI corto (ej: 4000, 4110, 6000)
# Usar GL_Acc como account_code + Department como dept_code

# Los meses disponibles: T-ENERO 2025 a T-AUGUST (datos hasta agosto 2025)
```

---

## 7. MOTOR DE CÁLCULO P&L USALI

### 7.1 Estructura del P&L para CWL

```
REVENUE
  Rooms Revenue                    (accounts 4000-4099, dept 0110)
  F&B Revenue                      (accounts 4110-4132, dept 0120)
  Spa Revenue                      (accounts 4201-4215, dept 0130)
  Activities Revenue               (accounts 4400-4403, dept 0150)
  Transportation Revenue           (accounts 4500-4503, dept 0152)
  Innoceana Revenue                (accounts 4600-4603, dept 0155)
  Retail Gift Shop                 (accounts 4301-4321, dept 0165)
  Laundry Revenue                  (accounts 4700-4702, dept 0161)
  Sustainability Fee               (account 4880)
  Miscellaneous Revenue            (account 4800-4890)
TOTAL REVENUE

COST OF SALES (accounts 5xxx)
  Food Cost                        (5101-5103)
  Beverage Cost                    (5150-5165)
  Activity Cost                    (5350-5363)
  Transportation Cost              (5360-5363)
TOTAL COST OF SALES

GROSS OPERATING PROFIT BY DEPT
  For each dept: Revenue - Cost - Payroll - OPEX = Dept Profit

PAYROLL (accounts 6000-6030, grouped by dept seg2)
  Salaries & Wages                 (6000)
  Overtime                         (6001)
  Days Off                         (6002)
  Worked Holidays                  (6003)
  Disabilities                     (6004)
  Commissions                      (6010)
  CCSS (Carga Patronal)            (6020)
  13th Salary (Aguinaldo)          (6021)
  Occupational Hazards             (6022)
  Vacation Provision               (6023)
  Vacation Taken                   (6024)
  Cafeteria                        (6025)
  Notice & Severance               (6026)
  Incentive Bonus                  (6027)
  Housing Benefit                  (6028)
  Transportation                   (6029)
  Other Benefits                   (6030)
TOTAL PAYROLL

OPEX (accounts 7000-7715, grouped by dept)
  [by USALI category per department]
TOTAL OPEX

DEPARTMENTAL PROFIT = REVENUE - COST - PAYROLL - OPEX

OVERHEAD (accounts 7xxx, dept 0180/0181/0182/0183/0184/0186/0190/0200)
  Admin & General                  (dept 0180-0186)
  Sales & Marketing                (dept 0190)
  Maintenance                      (dept 0200)
  Utilities                        (dept 0200)
TOTAL OVERHEAD

GROSS OPERATING PROFIT (GOP) = DEPARTMENTAL PROFIT - OVERHEAD

OWNERS EXPENSES (accounts 8000-8050)
  Rent                             (8000)
  Owners Fees                      (8005)
  Property Insurance               (8015)
  Depreciation                     (8040)
  Interest on Loans                (8035)
  Income Tax                       (8060)
EBITDA = GOP - (8000+8015+8030)
NET PROFIT = EBITDA - (8035+8040+8060)
```

### 7.2 Función principal del engine
```python
# engine/pl_engine.py

def calculate_pl(scenario_id: UUID, month: int = None) -> PLResult:
    """
    Calcula el P&L completo para un escenario.
    Si month=None, calcula el año completo.
    Si month=1-12, calcula ese mes.
    """
    entries = get_entries(scenario_id, month)
    
    # Agrupar por clase de cuenta
    revenue = sum_by_account_class(entries, '4')      # cuentas 4xxx
    cost_of_sales = sum_by_account_class(entries, '5') # cuentas 5xxx
    payroll = sum_by_account_class(entries, '6')       # cuentas 6xxx
    opex = sum_by_account_range(entries, 7000, 7799)   # cuentas 7000-7799
    overhead = sum_by_dept(entries, OVERHEAD_DEPTS)    # depts 0180-0200
    owners_exp = sum_by_account_range(entries, 8000, 8060)
    
    gross_profit = revenue - cost_of_sales
    dept_profit = gross_profit - payroll - opex
    gop = dept_profit - overhead
    ebitda = gop - (owners_exp['rent'] + owners_exp['insurance'] + owners_exp['bank_charges'])
    net_profit = ebitda - (owners_exp['interest'] + owners_exp['depreciation'] + owners_exp['income_tax'])
    
    return PLResult(
        revenue=revenue, cost_of_sales=cost_of_sales,
        gross_profit=gross_profit, payroll=payroll, opex=opex,
        dept_profit=dept_profit, overhead=overhead,
        gop=gop, ebitda=ebitda, net_profit=net_profit
    )
```

### 7.3 Cálculo de varianza
```python
# engine/pl_engine.py

def calculate_variance(
    actual_scenario_id: UUID,
    budget_scenario_id: UUID,
    month: int = None
) -> VarianceResult:
    """
    Varianza = Actual - Budget
    Para ingresos: positivo = favorable
    Para gastos: positivo = desfavorable (gasto mayor al budget)
    """
    actual = calculate_pl(actual_scenario_id, month)
    budget = calculate_pl(budget_scenario_id, month)
    
    return VarianceResult(
        actual=actual,
        budget=budget,
        variance_abs=actual - budget,
        variance_pct=(actual - budget) / budget * 100
    )
```

---

## 8. API ENDPOINTS

```
# Importación
POST /api/import/catalog/           subir catálogo de cuentas
POST /api/import/revenue/           subir auxiliar de ingresos
POST /api/import/opex/              subir checkbook de OPEX (un dept a la vez)
POST /api/import/opex/bulk/         subir múltiples checkbooks
POST /api/import/payroll/           subir codificación de planilla
POST /api/import/actual/            subir mapping QuickBooks/USALI

# Escenarios
GET  /api/scenarios/                listar escenarios disponibles
POST /api/scenarios/                crear nuevo escenario
GET  /api/scenarios/{id}/           detalle de escenario

# P&L
GET  /api/pl/{scenario_id}/                    P&L anual
GET  /api/pl/{scenario_id}/monthly/            P&L × 12 meses
GET  /api/pl/{scenario_id}/month/{month}/      P&L mes específico
GET  /api/pl/{scenario_id}/dept/{dept}/        P&L por departamento

# Varianza
GET  /api/variance/actual/{id}/budget/{id}/           Actual vs Budget anual
GET  /api/variance/actual/{id}/budget/{id}/monthly/   Actual vs Budget × meses
GET  /api/variance/actual/{id}/forecast/{id}/         Actual vs Forecast

# KPIs
GET  /api/kpis/{scenario_id}/                  KPIs completos
GET  /api/kpis/{scenario_id}/monthly/          KPIs × 12 meses
GET  /api/kpis/{scenario_id}/by-room-type/     KPIs por tipo de villa

# Export
POST /api/export/{scenario_id}/excel/          genera .xlsx
POST /api/export/comparison/excel/             Actual vs Budget vs Forecast en .xlsx
POST /api/export/{scenario_id}/pdf/            genera PDF
```

---

## 9. ORDEN DE CONSTRUCCIÓN

**Regla general:** cada fase tiene un criterio de "Done" verificable con tests. No avanzar a la siguiente fase sin pasar los tests de la actual.

```
═══════════════════════════════════════════════════════════════
FASE 1 — BASE DE DATOS Y CATÁLOGOS
Sesión 1-2
═══════════════════════════════════════════════════════════════
  alembic init + primera migración
  models/account.py              ← catálogo 7 segmentos (clases 4,5,6,7,9)
  models/payroll_catalog.py      ← catálogo de posiciones
  importers/catalog_importer.py  ← importar 31,269 cuentas
  importers/stats_importer.py    ← importar 9,292 cuentas estadísticas (9xxx)

  ✅ Done: GET /api/accounts/?seg1=6000 devuelve cuentas con 7 segmentos correctos
  ✅ Done: GET /api/accounts/?seg1=9000 devuelve cuentas estadísticas
  ✅ Done: GET /api/payroll-catalog/ devuelve posiciones con dept + position_name

═══════════════════════════════════════════════════════════════
FASE 2 — MASTER DATA: ESCENARIOS, TIPOS DE CAMBIO, HABITACIONES
Sesión 3
═══════════════════════════════════════════════════════════════
  models/scenario.py             ← BUDGET | FORECAST | ACTUAL + locked
  models/exchange_rate.py        ← TC por escenario × mes
  models/room_type_config.py     ← 6 tipos CWL (30 unidades)
  api/scenarios_api.py
  api/exchange_rates_api.py

  ✅ Done: crear escenario BUDGET 2026, cargar TC mes a mes
  ✅ Done: escenario locked rechaza edición con PermissionError
  ✅ Done: 6 tipos de habitación cargados con unidades correctas (6,2,4,8,5,5)

═══════════════════════════════════════════════════════════════
FASE 3 — CHECKBOOK DE INGRESOS (REVENUE)
Sesión 4-5
═══════════════════════════════════════════════════════════════
  models/sales_channel_config.py ← canales (TA 28%, OTA 20%, Direct 0%)
  models/rate_card.py            ← Rack + Net Rate por tipo × mes
  models/occupancy_budget.py     ← FTE 0.00-1.00 por tipo × mes
  models/package_component.py    ← Transfer, Breakfast, Lunch, Dinner, Tours
  models/revenue_result.py       ← resultados calculados (read-only)
  models/historical_kpi.py       ← 2024 y 2025 actuals (read-only)
  engine/revenue_calculator.py   ← Net Rate, Room Rev, F&B, Activities, KPIs
  api/revenue_api.py
  frontend/revenue/rates.tsx     ← inputs Rack, canales, ocupación, paquete
  frontend/revenue/kpis.tsx      ← Key Indicators comparativo 4 columnas

  ✅ Done: cambiar ocupación% → recalcula Room Revenue → recalcula ADR/RevPAR
  ✅ Done: cambiar canal → recalcula Net Rate → recalcula todo revenue
  ✅ Done: Revenue = 0 cuando occupancy=0 y FTE=0 (comportamiento actual de CWL en octubre — no hardcodeado)
  ✅ Done: Enero 2026 Budget Rooms ≈ $415,201 (referencia archivo)

═══════════════════════════════════════════════════════════════
FASE 4 — CHECKBOOK DE PLANILLA
Sesión 6-7
═══════════════════════════════════════════════════════════════
  models/payroll_position.py     ← dept_code + position_name + salary + FTE
  models/payroll_concept_entry.py ← 17 conceptos por posición × mes
  engine/payroll_calculator.py   ← SW×FTE/TC, BASE, 6020=BASE×26.83%, 6021=BASE/12
  api/payroll_api.py
  frontend/payroll/checkbook.tsx ← por dept: posiciones × FTE × conceptos
  frontend/payroll/fte_report.tsx ← todos los depts × 12 meses

  ✅ Done: salario CRC×FTE/TC_mes = SW correcto en USD
  ✅ Done: BASE = 6000+6001+6002+6003+6010+6024+6027 → CCSS y Agu automáticos
  ✅ Done: FTE=0.00 → SW=0 → CCSS=0 → Aguinaldo=0
  ✅ Done: reporte FTE muestra todos los depts × 12 meses (octubre = 0 en CWL 2026 porque FTE=0, no por regla del sistema)
  ✅ Done: conceptos manuales sobreviven el recálculo

═══════════════════════════════════════════════════════════════
FASE 5 — CHECKBOOK DE COSTOS (CLASE 5)
Sesión 8
═══════════════════════════════════════════════════════════════
  models/cost_entry.py           ← cuenta 5xxx × dept × mes
  engine/cost_calculator.py      ← drivers: REVENUE_LINE, OCC_ROOMS, GUESTS,
                                    AVAIL_ROOMS, KILOS, MANUAL
  api/costs_api.py
  frontend/costs/checkbook.tsx   ← checkbook por dept con línea de ingreso visible

  ✅ Done: Food Cost = 28% × Food Revenue del mes (driver REVENUE_LINE)
  ✅ Done: costos con driver REVENUE_LINE = 0 cuando revenue = 0 (ej: octubre en CWL 2026)
  ✅ Done: línea MANUAL no cambia al recalcular
  ✅ Done: Gross Profit y % Margen se calculan al fondo del checkbook

═══════════════════════════════════════════════════════════════
FASE 6 — CHECKBOOK OPEX (CLASE 7)
Sesión 9
═══════════════════════════════════════════════════════════════
  models/opex_entry.py           ← cuenta 7xxx × dept × detalle × mes
  importers/opex_importer.py     ← leer 17 archivos OPEXC_2026__[DEPT]__BUDGET.xlsx
  api/opex_api.py
  frontend/opex/checkbook.tsx    ← cuenta × subcuenta × histórico × budget

  ✅ Done: importar F&B OPEX → totales coinciden con archivo original
  ✅ Done: cada subcuenta (800-810) es editable independientemente
  ✅ Done: total cuenta = suma de subcuentas
  ✅ Done: histórico 2024 y 2025 visible como referencia (read-only)

═══════════════════════════════════════════════════════════════
FASE 7 — ALLOCATIONS (CAFETERÍA Y LAVANDERÍA)
Sesión 10
⚠️  DEBE completarse ANTES del P&L
═══════════════════════════════════════════════════════════════
  models/cafeteria_allocation_config.py  ← participates por dept
  models/laundry_allocation_config.py    ← kilos históricos por dept
  models/allocation_entry.py
  engine/allocation_calculator.py
  api/allocation_api.py
  frontend/allocations/config.tsx

  ✅ Done: Cafetería neto = $0 cada mes
  ✅ Done: Lavandería neto = $0 cada mes
  ✅ Done: dept remoto (Sales) excluido del allocation de cafetería
  ✅ Done: kilos de 9700-9702 alimentan LaundryAllocationConfig

═══════════════════════════════════════════════════════════════
FASE 8 — BOTÓN RECALCULAR + ENGINE P&L COMPLETO
Sesión 11
═══════════════════════════════════════════════════════════════
  engine/recalculate.py          ← orquesta todo en orden correcto
  engine/pl_engine.py            ← P&L completo 13 columnas
  models/pl_line.py              ← líneas del P&L calculadas
  models/pl_manual_input.py      ← Rent, Depreciation, Mgmt Fee%, etc.
  api/pl_api.py
  frontend/pl/full_pl.tsx        ← vista P&L 13 columnas (como el PDF)

  ORDEN de recálculo (crítico):
    1. Net Rates (canales → rack)
    2. Revenue (occupancy × net rate → R&B, Activities, etc.)
    3. Planilla (SW × FTE/TC → BASE → 6020/6021)
    4. CoS (drivers × base)
    5. Allocations (Cafetería y Lavandería)
    6. P&L completo (Revenue→OpExp→OpProfit→Overhead→GOP→EBITDA→Net)
    7. KPIs (Occupancy%, ADR, RevPAR)

  ✅ Done: GOP = Operating Profit − Overhead
  ✅ Done: Net Profit = EBT − Income Tax (0 si EBT negativo)
  ✅ Done: Management Fee = Total Revenue × % editable
  ✅ Done: Cafetería y Lavandería = $0 en el P&L
  ✅ Done: Abril 2026 Actual GOP ≈ $176,037 (referencia PDF)

═══════════════════════════════════════════════════════════════
FASE 9 — IMPORTADORES DE ACTUALS
Sesión 12
═══════════════════════════════════════════════════════════════
  importers/actual_revenue_importer.py    ← Revenue real desde Integrity/QB
  importers/actual_payroll_importer.py    ← Planilla real (7 segmentos → dept+pos)
  importers/actual_opex_importer.py       ← OPEX real desde MAPPING_USALI
  importers/actual_stats_importer.py      ← cuentas 9xxx (noches, kilos, covers)
  api/import_api.py
  frontend/import/upload.tsx

  ✅ Done: importar actual abril 2026 → Revenue total ≈ $597,135
  ✅ Done: kilos de 9700-9702 se guardan en StatisticalSummary
  ✅ Done: meses importados se pueden usar en el Forecast

═══════════════════════════════════════════════════════════════
FASE 10 — ESCENARIO FORECAST
Sesión 13
═══════════════════════════════════════════════════════════════
  models/forecast_version.py     ← versiones con through_month
  engine/forecast_builder.py     ← copia actuals + proyecciones previas
  api/forecast_api.py
  frontend/forecast/versions.tsx ← lista de versiones + crear nueva

  ✅ Done: crear Forecast v1 = copia exacta del Budget
  ✅ Done: crear Forecast v2 con Ene=actual → Ene bloqueado, Feb-Dic editables
  ✅ Done: recalcular Forecast no toca meses locked
  ✅ Done: Budget original intacto después de editar Forecast

═══════════════════════════════════════════════════════════════
FASE 11 — REPORTE DE PROPIETARIOS (YTD SUMMARY)
Sesión 14-15
═══════════════════════════════════════════════════════════════
  engine/owner_report_engine.py  ← genera los 14 tabs automáticos
  api/reports_api.py
  frontend/reports/ytd_summary.tsx  ← 22 tabs navegables
  export/excel_report.py         ← exportar a Excel (formato YTD_APRIL)
  export/pdf_report.py

  TABS automáticos (14): Summary, P&L, Total Revenue, Payroll,
    F&B Cost, Headcounts, Room Stats, On The Books, 12M Budget,
    12M Forecast, Simplified P&L YTD, Simplified P&L Full Year,
    Cash Flow, COLON-DOLLAR CHART

  TABS semi-automáticos (6): Ops KPI, Country, Market Set,
    Capex, AP Aging, AR Aging

  ✅ Done: Summary Abril 2026 → Total Revenue ≈ $597,135, GOP ≈ $176,037
  ✅ Done: YTD = suma de meses enero a mes del reporte
  ✅ Done: exportar Excel reproduce el formato del archivo original

═══════════════════════════════════════════════════════════════
FASE 12 — PULIDO Y MULTI-PROPIEDAD
Sesión 16+
═══════════════════════════════════════════════════════════════
  - Narrativa Additional Data con Claude API
  - Clonar CWL para segunda propiedad
  - Dashboard ejecutivo multi-propiedad
  - Alertas de varianza (cuando Actual supera Budget en X%)
```

---



## 10. TESTS CRÍTICOS

```python
# tests/test_exchange_rates.py

def test_tc_by_month():
    """Cada mes puede tener TC diferente."""
    scenario = get_budget_scenario()
    set_tc(scenario.id, month=1, tc=530.00)
    set_tc(scenario.id, month=7, tc=545.00)
    assert get_tc(scenario.id, month=1) == Decimal('530.00')
    assert get_tc(scenario.id, month=7) == Decimal('545.00')

def test_tc_fallback():
    """Si no hay TC para un mes, usa el más reciente disponible."""
    scenario = get_budget_scenario()
    set_tc(scenario.id, month=1, tc=530.00)
    # Sin TC para marzo
    assert get_tc(scenario.id, month=3) == Decimal('530.00')  # fallback a enero

# tests/test_payroll.py

def test_salary_crc_conversion():
    """Salario mensual CRC × FTE / TC = SW en USD."""
    position = PayrollPosition(
        salary_amount=Decimal('650000'),  # salario mensual completo en CRC
        salary_currency='CRC',
        fte_jan=Decimal('1.00'),          # mes completo
    )
    tc = Decimal('530')
    # SW = 650,000 × 1.00 / 530 = $1,226.42
    result = calculate_sw(position, month=1, tc=tc)
    assert abs(float(result) - 1226.42) < 0.01

def test_salary_crc_half_fte():
    """FTE=0.50 = 15 días / medio tiempo → exactamente la mitad del salario."""
    position = PayrollPosition(
        salary_amount=Decimal('650000'),
        salary_currency='CRC',
        fte_jan=Decimal('0.50'),          # 15 días o medio tiempo
    )
    tc = Decimal('530')
    # SW = 650,000 × 0.50 / 530 = $613.21
    result = calculate_sw(position, month=1, tc=tc)
    assert abs(float(result) - 613.21) < 0.01

def test_salary_crc_zero_fte():
    """FTE=0.00 → SW=0.00 sin importar el salario."""
    position = PayrollPosition(
        salary_amount=Decimal('650000'),
        salary_currency='CRC',
        fte_jan=Decimal('0.00'),          # vacante ese mes
    )
    result = calculate_sw(position, month=1, tc=Decimal('530'))
    assert result == Decimal('0.00')

def test_salary_usd_no_conversion():
    """Salario USD × FTE, sin conversión."""
    position = PayrollPosition(
        salary_amount=Decimal('2500'),    # salario mensual completo en USD
        salary_currency='USD',
        fte_jan=Decimal('1.00'),
    )
    assert calculate_sw(position, month=1, tc=Decimal('530')) == Decimal('2500')

def test_salary_usd_half_fte():
    """Salario USD × 0.50 = mitad."""
    position = PayrollPosition(
        salary_amount=Decimal('2500'),
        salary_currency='USD',
        fte_jan=Decimal('0.50'),
    )
    assert calculate_sw(position, month=1, tc=Decimal('530')) == Decimal('1250')

def test_mixed_currency_dept():
    """Un departamento puede tener posiciones en CRC y USD mezcladas."""
    dept_positions = [
        PayrollPosition(salary_amount=Decimal('650000'), salary_currency='CRC', fte_jan=1.0),
        PayrollPosition(salary_amount=Decimal('2500'), salary_currency='USD', fte_jan=1.0),
    ]
    tc = Decimal('530')
    total_sw = sum(
        calculate_payroll_for_position(p, default_params, 1, tc)['6000_sw']
        for p in dept_positions
    )
    expected = (650000 / 530) + 2500
    assert float(total_sw) == pytest.approx(expected, rel=0.001)

def test_aguinaldo_rate():
    """Aguinaldo = SW × (1/12). NO SW / (1/12)."""
    sw = Decimal('1226.42')  # USD equivalente de 650,000 CRC @ 530
    agu = sw * Decimal('1') / Decimal('12')
    assert float(agu) == pytest.approx(102.20, rel=0.01)
    # Si el valor fuera ~14,717 → el bug de la inversión está de regreso

def test_ccss_rate():
    """CCSS patronal = 26.83% sobre SW."""
    sw = Decimal('1000')
    ccss = sw * Decimal('0.2683')
    assert float(ccss) == pytest.approx(268.30, rel=0.01)

# tests/test_importers.py

def test_catalog_import_count():
    count = db.query(Account).count()
    assert 31000 <= count <= 32000

def test_opex_totals_match():
    """Totales calculados ±1% vs GRAN TOTAL de cada checkbook."""
    for dept, (file, sheet) in OPEX_FILES.items():
        expected = read_gran_total_2026(file, sheet)
        calculated = sum_opex_by_dept(scenario_budget_id, dept)
        assert abs(calculated - expected) / expected < 0.01

def test_pl_chain():
    pl = calculate_pl(scenario_budget_id)
    assert pl.gross_profit == pl.revenue - pl.cost_of_sales
    assert pl.dept_profit == pl.gross_profit - pl.payroll - pl.opex
    assert pl.gop == pl.dept_profit - pl.overhead
    assert pl.net_profit < pl.gop

def test_kpi_october_zero():
    """Octubre tiene 0 habitaciones ocupadas en CWL 2026 porque occupancy=0.0 en los inputs.
    Si se cambia occupancy a >0, el sistema debe producir números correctos.
    Octubre NO está hardcodeado — es un resultado de los inputs del usuario."""
    oct_kpi = db.query(KpiEntry).filter_by(
        scenario_id=scenario_budget_id, month=10, room_type='ALL'
    ).first()
    assert oct_kpi.rooms_occupied == 0
```

---

## 11. MASTER DATA — TIPOS DE CAMBIO

### 11.1 Modelo
```python
class ExchangeRate(Base):
    __tablename__ = 'exchange_rates'

    id: UUID
    scenario_id: UUID       # FK → Scenario
                            # Cada escenario (Budget, Forecast v1, v2...) tiene su PROPIA tabla de TC
                            # Budget 2026: TC fijos al momento de aprobación
                            # Forecast Feb 2026: puede tener TC distintos para meses futuros
                            # Actual: NO usa esta tabla — los valores ya vienen en USD
    hotel_id: str
    month: int              # 1-12
    year: int
    tc_crc_usd: Decimal     # tipo de cambio CRC/USD para ese mes
                            # 530.00 significa 1 USD = ₡530
                            # amount_usd = amount_crc / tc_crc_usd
    notes: str              # opcional — "Tipo de cambio BCCR proyectado"
```

### 11.2 Una tabla de TC por escenario — los 12 meses del año

Cada escenario tiene exactamente **12 filas** en `exchange_rates` — una por mes. El usuario las ingresa al crear el escenario. Son el primer paso antes de calcular cualquier salario en CRC.

**Vista de la tabla en el UI:**

```
TIPOS DE CAMBIO — Budget 2026
  (ingrese el TC proyectado para cada mes)

  Mes        TC CRC/USD    Notas
  ────────   ──────────    ─────────────────────────────
  Enero      [ 530.00 ]    ← editable
  Febrero    [ 532.00 ]    ← editable
  Marzo      [ 533.00 ]    ← editable
  Abril      [ 535.00 ]    ← editable
  Mayo       [ 536.00 ]    ← editable
  Junio      [ 537.00 ]    ← editable
  Julio      [ 538.00 ]    ← editable
  Agosto     [ 539.00 ]    ← editable
  Septiembre [ 540.00 ]    ← editable
  Octubre    [ 541.00 ]    ← editable (hotel cerrado pero TC igual se registra)
  Noviembre  [ 542.00 ]    ← editable
  Diciembre  [ 543.00 ]    ← editable
  ────────────────────────────────────────────────────
  TC promedio año: 537.17  (informativo, calculado)

  [Guardar]  [Copiar al Forecast]
```

### 11.3 Budget vs Forecast — TC independientes

```
BUDGET 2026 (locked al aprobar):
  Ene: 530 | Feb: 532 | Mar: 533 | ... | Dic: 543
  → estos TC nunca cambian
  → todos los salarios CRC del Budget usan estos TC

FORECAST Feb 2026 (se crea al cerrar enero):
  Ene: 530  (copiado del actual — mes ya cerrado, TC real)
  Feb: 534  ← el usuario puede AJUSTAR si el mercado cambió
  Mar: 535  ← ajustable
  ...
  Dic: 545  ← ajustable

  → El TC de meses pasados del Forecast = TC real de ese mes
  → El TC de meses futuros del Forecast = proyección actualizada
  → Si hay diferencia vs Budget → impacta los salarios CRC proyectados
```

**Impacto de cambiar un TC en el Forecast:**
```
Ejemplo: Salario ₡650,000, FTE=1.0
  Budget (TC=530):  $1,226.42/mes
  Forecast (TC=545): $1,192.66/mes  ← cambia $33.76 menos por la devaluación
  
→ El botón "Recalcular" propaga automáticamente el nuevo TC a todos los
  salarios CRC de los meses afectados.
```

### 11.4 Reglas críticas de tipo de cambio

- **Budget y Forecast:** cada uno tiene su propia tabla de 12 TC. Independientes.
- **Actual:** NO tiene TC — los valores ya vienen en USD desde QuickBooks/Integrity.
- **Conversión:** `amount_usd = amount_crc / tc_crc_usd` del mes correspondiente.
- **TC varía mes a mes.** El sistema aplica el TC del mes al calcular.
- **Si falta TC de un mes:** el sistema usa el TC del mes más reciente disponible (fallback hacia atrás). Esto no debe pasar — el usuario debe completar los 12 meses.
- **TC siempre visible en UI** de planilla — el usuario ve qué TC se aplica a cada mes.
- **Recalcular al cambiar TC:** si el usuario edita un TC, presionar Recalcular actualiza todos los salarios CRC de ese mes en cascada.
- **Octubre:** el TC se registra aunque el hotel esté cerrado — para consistencia de la tabla.

### 11.5 Cómo el TC se aplica en el recálculo

```python
def get_tc(scenario_id: UUID, month: int) -> Decimal:
    """
    Obtiene el TC del mes para un escenario.
    Si no existe para ese mes exacto, busca hacia atrás.
    """
    tc = db.query(ExchangeRate).filter_by(
        scenario_id=scenario_id, month=month
    ).first()
    
    if tc:
        return tc.tc_crc_usd
    
    # Fallback: TC del mes anterior más cercano
    for m in range(month - 1, 0, -1):
        tc = db.query(ExchangeRate).filter_by(
            scenario_id=scenario_id, month=m
        ).first()
        if tc:
            return tc.tc_crc_usd
    
    raise ValueError(f"No TC found for scenario {scenario_id}")


def copy_tc_to_forecast(
    source_scenario_id: UUID,
    target_scenario_id: UUID,
    locked_months: list[int],    # meses con actuals — TC real
    actual_tcs: dict[int, Decimal]  # TC reales de meses cerrados
):
    """
    Al crear una nueva versión de Forecast:
    - Meses locked: usar TC real del actual
    - Meses futuros: copiar TC del forecast anterior (o Budget)
    """
    for month in range(1, 13):
        if month in locked_months:
            tc_value = actual_tcs[month]  # TC real del mes cerrado
        else:
            # Copiar del escenario fuente (forecast anterior o budget)
            tc_value = get_tc(source_scenario_id, month)
        
        ExchangeRate(
            scenario_id=target_scenario_id,
            month=month,
            tc_crc_usd=tc_value
        )
```

### 11.6 Endpoint de TC

```
GET  /api/exchange-rates/{scenario_id}/           TC 12 meses del escenario
PUT  /api/exchange-rates/{scenario_id}/{month}/   actualizar TC de un mes → Recalcular
POST /api/exchange-rates/{scenario_id}/bulk/      cargar TC todos los meses de una vez
GET  /api/exchange-rates/{scenario_id}/average/   TC promedio anual (informativo)
POST /api/exchange-rates/{scenario_id}/copy-from/{source_id}/  copiar TC de otro escenario
```

### 11.7 Tests críticos de TC

```python
def test_exchange_rate_table_has_12_months():
    """Todo escenario Budget o Forecast debe tener exactamente 12 TC."""
    scenarios = db.query(Scenario).filter(
        Scenario.scenario_type.in_(['BUDGET', 'FORECAST'])
    ).all()
    for s in scenarios:
        tcs = db.query(ExchangeRate).filter_by(scenario_id=s.id).count()
        assert tcs == 12, f"Scenario {s.version_name} has {tcs} TC rows, expected 12"

def test_tc_change_recalculates_crc_salary():
    """Cambiar TC de febrero → salario CRC de febrero cambia en USD."""
    pos = get_position(scenario_id, 'CRC', salary=650000)
    sw_before = get_sw(pos, month=2)  # con TC=532
    update_tc(scenario_id, month=2, tc=Decimal('545'))
    recalculate_scenario(scenario_id)
    sw_after = get_sw(pos, month=2)   # con TC=545
    assert sw_before > sw_after       # TC más alto → menos USD

def test_budget_and_forecast_have_independent_tc():
    """Budget y Forecast pueden tener TC distintos para el mismo mes."""
    budget_tc_mar = get_tc(budget_id, month=3)
    update_tc(forecast_id, month=3, tc=Decimal('540'))
    forecast_tc_mar = get_tc(forecast_id, month=3)
    assert budget_tc_mar != forecast_tc_mar  # independientes

def test_usd_salary_unaffected_by_tc():
    """Salario en USD no cambia cuando cambia el TC."""
    pos_usd = get_position(scenario_id, 'USD', salary=2500)
    sw_before = get_sw(pos_usd, month=2)
    update_tc(scenario_id, month=2, tc=Decimal('600'))
    recalculate_scenario(scenario_id)
    sw_after = get_sw(pos_usd, month=2)
    assert sw_before == sw_after  # USD no se afecta por TC

def test_forecast_locked_months_use_actual_tc():
    """Los meses cerrados del Forecast usan el TC real del actual."""
    # TC real de enero = 531.50
    actual_tc_jan = get_tc(actual_scenario_id, month=1)
    forecast = create_forecast_version(
        hotel_id='CWL', year=2026, through_month=1,
        actual_scenario_id=actual_scenario_id,
        prev_forecast_id=budget_id
    )
    forecast_tc_jan = get_tc(forecast.id, month=1)
    assert forecast_tc_jan == actual_tc_jan  # usa el TC real
```



---

## 12. CHECKBOOK DE PLANILLA (ENTRADA DE DATOS)

El presupuesto y forecast de planilla se construyen **dentro del sistema**, departamento por departamento, similar al formato de los checkbooks OPEX pero con campos adicionales para moneda y tipo de cambio.

### 12.1 Estructura del checkbook de planilla

**Lo más importante: Departamento + Posición.**

El checkbook se organiza y agrupa siempre por `dept_code` + `position_name`. Todo lo demás es contexto.

Para los **actuales de Integrity**, los datos vienen con 7 niveles jerárquicos en el código de cuenta. Para comparar contra el presupuesto, se mapea simplemente a dept (seg2) + posición (seg3):

```
Código Integrity: 6000 - 0150 - 604 - 013 - 015 - 00 - 00
                         │      │
                         Dept   Posición
                  → dept_code = 0150 (Tours)
                  → position_code = 604 (Capitán de Barco)
```

### 12.2 Modelo de posición de planilla

```python
class PayrollPosition(Base):
    # Campos esenciales para el checkbook
    dept_code: str          # '0150' Tours, '0120' F&B, etc.
    dept_name: str
    position_name: str      # 'CAPITAN DE BARCO', 'ROOM ATTENDANT', etc.

    # Datos de soporte
    position_code: str      # código del PLANNING_CATALOGO
    employee_name: str      # nombre real o 'VACANTE'
    employee_type: str      # '1-Permanente' | '2-Temporal'
    class_code: str         # '013'=Line, '012'=Supervisors, etc.
    category_code: str      # '015'=Local Perm, '010'=Expat, etc.

    # Salario mensual completo (cuando FTE=1.00)
    salary_amount: Decimal  # Ej: 650000 CRC o 2500 USD
    salary_currency: str    # 'CRC' | 'USD'

    # FTE por mes 0.00-1.00 — multiplicador del salario mensual
    # SW_mes = salary_amount x FTE_mes / TC_mes (CRC)
    # SW_mes = salary_amount x FTE_mes          (USD)
    fte_jan: Decimal; fte_feb: Decimal; fte_mar: Decimal; fte_apr: Decimal
    fte_may: Decimal; fte_jun: Decimal; fte_jul: Decimal; fte_aug: Decimal
    fte_sep: Decimal; fte_oct: Decimal; fte_nov: Decimal; fte_dec: Decimal


class ActualPayrollEntry(Base):
    # Planilla real de Integrity -- 7 segmentos completos guardados para auditoria
    account_code_full: str  # '6000-0150-604-013-015-00-00'
    # Mapeado para comparar vs presupuesto
    dept_code: str          # seg2: '0150'
    dept_name: str
    position_code: str      # seg3: '604'
    position_name: str
    concept_code: str       # seg1: '6000', '6020', etc.
    concept_name: str
    amount_usd: Decimal
    amount_crc: Decimal
```


### 12.3 Base de cálculo — Regla de CCSS y Aguinaldo

**REGLA CRÍTICA:** 6020 y 6021 son **siempre automáticos**. El usuario nunca los ingresa manualmente — el sistema los calcula y recalcula cada vez que cambia cualquier concepto de la base.

```
BASE CCSS/AGUINALDO = SUMA DE:
  6000  Salary and Wages
+ 6001  Overtime
+ 6002  Day Off
+ 6003  Working Holiday
+ 6010  Commissions
+ 6024  Vacations Taken
+ 6027  Incentive Bonus
= BASE

6020  CCSS Patronal  = BASE × 26.83%   ← AUTOMÁTICO, no editable
6021  Aguinaldo      = BASE ÷ 12       ← AUTOMÁTICO, no editable
```

**Todos los demás conceptos son MANUALES** — el usuario los ingresa directamente:
```
6004  Disabilities              MANUAL
6022  Occupational Hazards      MANUAL
6023  Vacation Provision        MANUAL
6025  Cafeteria                 MANUAL
6026  Notice & Severance        MANUAL
6028  Housing                   MANUAL
6029  Transportation            MANUAL
6030  Other Benefits            MANUAL
```

### 12.4 Botón de recálculo global

El sistema tiene un **botón "Recalcular Presupuesto"** que recorre todo el escenario y vuelve a calcular en cascada:

```
RECALCULAR PRESUPUESTO (un solo botón)
    │
    ├── 1. Actualizar Net Rates (Rack × canales)
    │
    ├── 2. Recalcular Revenue por mes × tipo de villa
    │       → Room Revenue, F&B, Activities, Transport, etc.
    │
    ├── 3. Recalcular Planilla por dept × mes
    │       → Para cada posición: SW = salary × FTE / TC_mes
    │       → BASE = SW + OT + DayOff + Holiday + Comm + VacTaken + Bonus
    │       → 6020 = BASE × 26.83%
    │       → 6021 = BASE / 12
    │
    ├── 4. Recalcular Allocations (Cafetería y Lavandería)
    │       → Cafetería: distribuir por FTE de depts participantes
    │       → Lavandería: distribuir por kilos históricos
    │
    ├── 5. Recalcular P&L completo
    │       → Revenue − CoS − Payroll − OPEX = Dept Profit
    │       → Dept Profit − Overhead = GOP
    │       → GOP − Owners = EBITDA → Net Profit
    │
    └── 6. Actualizar KPIs
            → Occupancy%, ADR, RevPAR, Rev/Guest
```

**Cuándo se dispara:**
- Manual: el usuario presiona "Recalcular"
- Automático: al cambiar TC de algún mes, al cambiar canal de ventas, al cambiar rack rates
- NO automático al cambiar planilla individual (para no hacer lento el ingreso fila por fila) — el usuario termina de ingresar y luego recalcula

```python
# engine/recalculate.py

def recalculate_scenario(scenario_id: UUID, user_id: str) -> RecalcResult:
    """
    Recálculo completo del escenario en el orden correcto.
    Devuelve un resumen de qué cambió para mostrar al usuario.
    """
    log = RecalcLog(scenario_id=scenario_id, triggered_by=user_id, started_at=now())

    # Paso 1: Net rates (dependen de canales y rack)
    update_net_rates_all_months(scenario_id)

    # Paso 2: Revenue
    for month in range(1, 13):
        calculate_revenue_month(scenario_id, month)

    # Paso 3: Planilla — 6020 y 6021 desde BASE
    for dept in get_all_depts(scenario_id):
        for month in range(1, 13):
            tc = get_tc(scenario_id, month)
            for position in get_positions(scenario_id, dept):
                fte = get_fte(position, month)          # 0.00 a 1.00
                # SW = salario mensual completo × FTE
                # Si CRC: convertir a USD con TC del mes
                if position.salary_currency == 'CRC':
                    sw = position.salary_amount * fte / tc
                else:
                    sw = position.salary_amount * fte
                # Si FTE=0.00 → SW=0 → no genera costo ese mes
                entry = get_or_create_entry(position, month)
                entry.c6000_sw = sw
                # BASE = SW + todos los manuales del grupo base
                base = calc_base(entry)
                entry.c6020_ccss      = base * CCSS_RATE   # siempre automático
                entry.c6021_aguinaldo = base / Decimal('12')  # siempre automático
                save(entry)

    # Paso 4: Allocations
    for month in range(1, 13):
        calculate_cafeteria_allocation(scenario_id, month)
        calculate_laundry_allocation(scenario_id, month)

    # Paso 5: P&L
    for month in range(1, 13):
        calculate_pl(scenario_id, month)

    # Paso 6: KPIs
    update_kpi_snapshots(scenario_id)

    log.finished_at = now()
    log.status = 'success'
    return RecalcResult(log=log, summary=build_summary(scenario_id))
```

### 12.5 Modelo de datos de planilla

```python
class PayrollConceptEntry(Base):
    """
    Conceptos de planilla por posición × mes.
    6020 y 6021 son siempre calculados — nunca editables por el usuario.
    """
    __tablename__ = 'payroll_concept_entries'

    id: UUID
    scenario_id: UUID
    position_id: UUID
    dept_code: str
    month: int
    year: int

    # ── GRUPO BASE (7 conceptos) ──────────────────────────────
    c6000_sw: Decimal               # calculado: salary × FTE / TC
    c6001_overtime: Decimal         # MANUAL
    c6002_day_off: Decimal          # MANUAL
    c6003_working_holiday: Decimal  # MANUAL
    c6010_commissions: Decimal      # MANUAL
    c6024_vacations_taken: Decimal  # MANUAL
    c6027_incentive_bonus: Decimal  # MANUAL

    # ── AUTOMÁTICOS (calculados desde BASE, no editables) ─────
    c6020_ccss: Decimal             # = BASE × 26.83%
    c6021_aguinaldo: Decimal        # = BASE / 12

    # ── MANUALES (ingreso directo del usuario) ────────────────
    c6004_disabilities: Decimal
    c6022_occ_hazard: Decimal
    c6023_vacation_prov: Decimal
    c6025_cafeteria: Decimal
    c6026_severance: Decimal
    c6028_housing: Decimal
    c6029_transport: Decimal
    c6030_other: Decimal
```

### 12.6 Vista del checkbook de planilla en el UI

```
DEPARTAMENTO: TOURS (0150)        TC Ene: ₡530 | TC Feb: ₡532 | ...

Posición        | Empleado   | Moneda |  Salario  | Ene FTE | Feb FTE | Total USD
─────────────────────────────────────────────────────────────────────────────────
Capitán Barco   | Juan Pérez | CRC    | ₡650,000  |   1.0   |   1.0   |  $X,XXX
Guía Tours      | VACANTE    | CRC    | ₡450,000  |   0.0   |   1.0   |  $X,XXX
Director Act.   | Mike Smith | USD    |   $2,500  |   1.0   |   1.0   |  $X,XXX

CONCEPTOS — ENERO
┌─────────────────────────────────────────────────────────┐
│ GRUPO BASE                                    USD        │
│  6000  Salary & Wages            [calculado]  $X,XXX    │
│  6001  Overtime                  [manual   ]  $  XXX    │
│  6002  Day Off                   [manual   ]  $  XXX    │
│  6003  Working Holiday           [manual   ]  $  XXX    │
│  6010  Commissions               [manual   ]  $  XXX    │
│  6024  Vacations Taken           [manual   ]  $  XXX    │
│  6027  Incentive Bonus           [manual   ]  $  XXX    │
│                                               ───────   │
│  BASE CCSS/Aguinaldo             [auto     ]  $X,XXX    │
├─────────────────────────────────────────────────────────┤
│ AUTOMÁTICOS (read-only — recalcular para actualizar)    │
│  6020  CCSS 26.83%               [auto 🔒 ]  $  XXX    │
│  6021  Aguinaldo ÷12             [auto 🔒 ]  $  XXX    │
├─────────────────────────────────────────────────────────┤
│ MANUALES                                                │
│  6004  Disabilities              [manual   ]  $  XXX    │
│  6022  Occ. Hazards              [manual   ]  $  XXX    │
│  6023  Vacation Provision        [manual   ]  $  XXX    │
│  6025  Cafeteria                 [manual   ]  $  XXX    │
│  6026  Notice & Severance        [manual   ]  $  XXX    │
│  6028  Housing                   [manual   ]  $  XXX    │
│  6029  Transportation            [manual   ]  $  XXX    │
│  6030  Other Benefits            [manual   ]  $  XXX    │
│                                               ───────   │
│  TOTAL PLANILLA DEPT ENERO                   $XX,XXX   │
└─────────────────────────────────────────────────────────┘

        [ 🔄 RECALCULAR PRESUPUESTO ]
```

### 12.7 Reporte de FTE por Departamento

El reporte de FTE es una vista transversal de todos los departamentos que muestra el headcount presupuestado mes a mes.

**Reglas de FTE:**
- FTE es un valor decimal entre `0.00` y `1.00`
- `1.00` = tiempo completo ese mes
- `0.50` = medio tiempo ese mes
- `0.25` = cuarto de tiempo
- `0.00` = posición vacante ese mes — existe en el presupuesto pero no genera costo
- **Nunca supera 1.00 por posición** — si se necesita más capacidad, se agrega una posición nueva
- Cambiar de `0.00` a cualquier valor o viceversa no elimina la posición — solo cambia si genera costo
- Al recalcular, si FTE = 0.00 → SW = 0 → BASE = 0 → CCSS = 0, Aguinaldo = 0 automáticamente

**Formato del reporte:**

```
REPORTE FTE — BUDGET 2026 — CWL
Comparativo: Budget | Actual (cuando disponible)

DEPARTAMENTO              | Ene  | Feb  | Mar  | Abr  | May  | Jun  | Jul  | Ago  | Sep  | Oct  | Nov  | Dic  | TOTAL
──────────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
ROOMS
  Front Desk (0111)       | 3.0  | 3.0  | 3.0  | 2.0  | 2.0  | 1.5  | 2.0  | 2.0  | 1.0  | 0.0  | 2.0  | 3.0  | 24.5
  Reservations (0112)     | 1.0  | 1.0  | 1.0  | 1.0  | 1.0  | 1.0  | 1.0  | 1.0  | 0.5  | 0.0  | 1.0  | 1.0  | 10.5
  Housekeeping (0113)     | 8.0  | 8.0  | 8.0  | 5.0  | 4.0  | 3.0  | 5.0  | 4.0  | 2.0  | 0.0  | 5.0  | 8.0  | 60.0
  Concierge (0114)        | 2.0  | 2.0  | 2.0  | 1.5  | 1.0  | 1.0  | 1.5  | 1.5  | 0.5  | 0.0  | 1.5  | 2.0  | 16.5
  SUBTOTAL ROOMS          | 14.0 | 14.0 | 14.0 | 9.5  | 8.0  | 6.5  | 9.5  | 8.5  | 4.0  | 0.0  | 9.5  | 14.0 | 111.5
──────────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
F&B
  F&B Management (0121)   | 1.0  | ...
  Kitchen (0122)          | 6.0  | ...
  Restaurant (0123)       | 4.0  | ...
  SUBTOTAL F&B            | 11.0 | ...
──────────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
SPA                       | ...
ACTIVITIES                | ...
TRANSPORT                 | ...
INNOCEANA                 | ...
RETAIL                    | ...
LAUNDRY                   | ...
──────────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
OVERHEAD
  General Management(0181)| ...
  Finance (0182)          | ...
  Purchasing (0183)       | ...
  HR (0184)               | ...
  Security (0186)         | ...
  Sales & Mktg (0190)     | ...
  Maintenance (0200)      | ...
  IT (0230)               | ...
  SUBTOTAL OVERHEAD       | ...
──────────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
SUPPORT (allocation depts)
  Cafetería (0220)        | 3.0  | 3.0  | 3.0  | 2.0  | 2.0  | 1.5  | 2.0  | 2.0  | 1.0  | 0.0  | 2.0  | 3.0  | 24.5
──────────────────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
TOTAL HOTEL               | XX.X | XX.X | XX.X | XX.X | XX.X | XX.X | XX.X | XX.X | XX.X | 0.0  | XX.X | XX.X | XXX.X
══════════════════════════════════════════════════════════════════════════════════════════════════
Octubre = 0.0 en CWL 2026 (el usuario ingresó FTE=0.00 para todos los depts en octubre)
```

**El reporte también muestra:**
- FTE promedio anual por departamento (Total / 12)
- Comparativo Budget vs Actual cuando hay datos reales cargados
- Highlight en rojo si Actual > Budget en algún departamento/mes
- Highlight en amarillo si FTE = 0 en meses distintos a octubre (posible vacante no planificada)

**Modelo de datos para el reporte (calculado, no almacenado):**

```python
def get_fte_report(scenario_id: UUID) -> FTEReport:
    """
    Agrega el FTE de todas las posiciones activas por dept × mes.
    FTE 0.00 en una posición significa que existe pero no genera costo ese mes.
    Se incluyen en el reporte para visibilidad del headcount planificado.
    """
    positions = get_all_positions(scenario_id)
    report = {}

    for pos in positions:
        dept = pos.dept_code
        if dept not in report:
            report[dept] = {m: Decimal('0') for m in range(1, 13)}
        for month in range(1, 13):
            fte = get_fte(pos, month)  # puede ser 0.00
            report[dept][month] += fte

    return FTEReport(
        scenario_id=scenario_id,
        by_dept=report,
        totals={m: sum(report[d][m] for d in report) for m in range(1, 13)},
        annual_avg={d: sum(report[d].values()) / 12 for d in report}
    )
```

### 12.8 Endpoints de planilla

```
# Posiciones
GET  /api/payroll/{scenario_id}/depts/
GET  /api/payroll/{scenario_id}/dept/{dept_code}/
POST /api/payroll/{scenario_id}/dept/{dept_code}/position/
PUT  /api/payroll/{scenario_id}/position/{id}/
DEL  /api/payroll/{scenario_id}/position/{id}/

# Conceptos manuales del grupo base (6001, 6002, 6003, 6010, 6024, 6027)
PUT  /api/payroll/{scenario_id}/position/{id}/month/{month}/base-concepts/

# Conceptos manuales de beneficios (6004, 6022–6030)
PUT  /api/payroll/{scenario_id}/position/{id}/month/{month}/benefit-concepts/

# Resumen calculado
GET  /api/payroll/{scenario_id}/dept/{dept_code}/summary/
GET  /api/payroll/{scenario_id}/summary/
GET  /api/payroll/{scenario_id}/params/
PUT  /api/payroll/{scenario_id}/params/

# Reporte FTE
GET  /api/payroll/{scenario_id}/fte-report/                    todos los depts × 12 meses
GET  /api/payroll/{scenario_id}/fte-report/dept/{dept_code}/   un departamento
GET  /api/payroll/{scenario_id}/fte-report/comparison/         Budget vs Actual

# Recálculo global
POST /api/scenarios/{scenario_id}/recalculate/
GET  /api/scenarios/{scenario_id}/recalc-status/
```

### 12.9 Tests críticos de planilla

```python
def test_6020_always_automatic():
    """6020 CCSS nunca lo ingresa el usuario — siempre se calcula."""
    entry = make_entry(sw=1000, overtime=150, bonus=100)  # base=1250
    recalculate_scenario(scenario_id)
    updated = get_entry(entry.id)
    assert updated.c6020_ccss == pytest.approx(1250 * 0.2683, rel=0.001)

def test_6021_always_automatic():
    """6021 Aguinaldo = BASE / 12, siempre calculado."""
    entry = make_entry(sw=1000, overtime=150, bonus=100)  # base=1250
    recalculate_scenario(scenario_id)
    updated = get_entry(entry.id)
    assert updated.c6021_aguinaldo == pytest.approx(1250 / 12, rel=0.001)

def test_ccss_base_includes_all_7_concepts():
    """CCSS se calcula sobre los 7 conceptos, no solo SW."""
    entry = make_entry(
        sw=1000, overtime=150, day_off=50,
        working_holiday=30, commissions=200,
        vacations_taken=80, incentive_bonus=100
    )
    base = get_base_ccss_agu(entry)
    assert base == Decimal('1610')
    assert entry.c6020_ccss == pytest.approx(1610 * 0.2683, rel=0.001)
    # 431.97 — NO 268.30 (que sería solo sobre SW)

def test_manual_concepts_survive_recalc():
    """Los conceptos manuales no cambian cuando se recalcula."""
    set_manual_concepts(position_id, month=1,
        c6004=50, c6025=30, c6028=200)
    update_salary(position_id, new_salary=800000)
    recalculate_scenario(scenario_id)
    entry = get_entry(position_id, month=1)
    assert entry.c6004_disabilities == Decimal('50')   # intacto
    assert entry.c6025_cafeteria    == Decimal('30')   # intacto
    assert entry.c6028_housing      == Decimal('200')  # intacto
    # Solo 6000, 6020, 6021 cambiaron

def test_recalc_cascades_to_pl():
    """Recalcular planilla actualiza el P&L automáticamente."""
    pl_before = get_pl(scenario_id, month=1)
    update_salary(position_id, new_salary=900000)
    recalculate_scenario(scenario_id)
    pl_after = get_pl(scenario_id, month=1)
    assert pl_after.payroll != pl_before.payroll
    assert pl_after.gop != pl_before.gop

def test_fte_zero_generates_no_cost():
    """FTE = 0.00 → SW = 0 → CCSS = 0 → Aguinaldo = 0.
    Aplica a cualquier mes — octubre en CWL 2026 tiene FTE=0 por decisión del usuario, no del sistema."""
    set_fte(position_id, month=10, fte=Decimal('0.00'))  # en CWL 2026, octubre = 0 por input del usuario
    recalculate_scenario(scenario_id)
    entry = get_entry(position_id, month=10)
    assert entry.c6000_sw        == Decimal('0')
    assert entry.c6020_ccss      == Decimal('0')
    assert entry.c6021_aguinaldo == Decimal('0')

def test_fte_zero_position_appears_in_report():
    """Una posición con FTE=0 sigue apareciendo en el reporte FTE."""
    set_fte(position_id, month=10, fte=Decimal('0.00'))
    report = get_fte_report(scenario_id)
    # La posición aparece en el reporte con 0.0, no desaparece
    assert position_id in [p.id for p in report.positions]
    assert report.by_dept[dept_code][10] == Decimal('0.0')

def test_fte_report_october_zero_in_cwl_2026():
    """En CWL Budget 2026, octubre tiene FTE=0 porque el usuario lo configuró así.
    Si se cambia el FTE de octubre, el reporte debe reflejar el nuevo valor.
    Octubre NO está bloqueado — es un input como cualquier otro mes."""
    report = get_fte_report(scenario_id)
    # En el Budget 2026 de CWL, octubre = 0 por diseño del presupuesto
    assert report.totals[10] == Decimal('0')
    # Pero si cambiamos FTE de octubre, debe funcionar
    set_fte(position_id, month=10, fte=Decimal('1.00'))
    report2 = get_fte_report(scenario_id)
    assert report2.by_dept[dept_code][10] == Decimal('1.00')  # se actualiza correctamente

def test_fte_report_all_depts_present():
    """El reporte incluye todos los departamentos, incluyendo Cafetería."""
    report = get_fte_report(scenario_id)
    expected_depts = ['0111','0112','0113','0114','0121','0122','0123',
                      '0131','0132','0150','0152','0155','0161',
                      '0181','0182','0183','0184','0186','0190',
                      '0200','0220','0230']
    for dept in expected_depts:
        assert dept in report.by_dept, f"Dept {dept} falta en reporte FTE"

def test_fte_range_validation():
    """FTE debe estar entre 0.00 y 1.00 — nunca mayor a 1."""
    with pytest.raises(ValidationError):
        set_fte(position_id, month=1, fte=Decimal('1.50'))  # inválido
    with pytest.raises(ValidationError):
        set_fte(position_id, month=1, fte=Decimal('-0.10'))  # inválido
    # Estos sí deben funcionar
    set_fte(position_id, month=1, fte=Decimal('1.00'))   # OK
    set_fte(position_id, month=2, fte=Decimal('0.50'))   # OK
    set_fte(position_id, month=3, fte=Decimal('0.25'))   # OK
    set_fte(position_id, month=4, fte=Decimal('0.00'))   # OK — vacante
```

**Luego:**
```
6020  CCSS Patronal = BASE_CCSS_AGU × 26.83%
6021  Aguinaldo     = BASE_CCSS_AGU / 12
```

**Todos los demás conceptos son MANUALES** — el usuario los ingresa directamente, no se calculan:
```
6004  Disabilities                (manual — según incapacidades reales)
6022  Occupational Hazards (INS)  (manual — según tasa de riesgo de la empresa)
6023  Provision Vacations         (manual — provisión contable)
6025  Cafeteria                   (manual — monto por empleado)
6026  Notice and Severance        (manual — provisión mensual 5.5%/12 del SW base)
6028  Housing Benefit             (manual — monto por posición)
6029  Transportation              (manual — monto por posición)
6030  Other Benefits              (manual — otros)
```

---

## 13. CHECKBOOK DE COSTOS (CLASE 5 — COST OF SALES)

### 13.1 Concepto general

El checkbook de costos funciona igual que el de OPEX — una tabla por departamento con todas las cuentas 5xxx que le corresponden. La diferencia clave es que **cada línea de costo puede calcularse automáticamente usando un driver**, o ingresarse manualmente.

**El usuario decide línea por línea:**
- `MANUAL` → ingresa el monto directamente en cada mes
- `% DRIVER` → ingresa un porcentaje y elige la base — el sistema calcula el monto

**La base del driver puede ser:**
| Base | Descripción | Ejemplo de uso |
|------|-------------|----------------|
| `REVENUE_LINE` | % del ingreso de una línea específica | Food Cost = 28% de Food Revenue |
| `OCC_ROOMS` | Costo por noche ocupada × noches ocupadas | Costo tours = $X por noche occ |
| `GUESTS` | Costo por huésped × total huéspedes | Amenities = $X por huésped |
| `AVAIL_ROOMS` | Costo por noche disponible × noches disponibles | Costo fijo de lavandería |
| `KILOS` | Costo por kilo lavado × kilos del mes | Lavandería real |
| `MANUAL` | Monto fijo ingresado por el usuario | Cualquier costo sin driver claro |

**La línea de ingreso siempre es visible** en el checkbook de costos para que el usuario pueda calcular el porcentaje correcto.

### 13.2 Modelo de datos

```python
class CostEntry(Base):
    """
    Una línea del checkbook de costos por departamento.
    Cada cuenta 5xxx del catálogo que aplica al dept tiene su fila.
    """
    __tablename__ = 'cost_entries'

    id: UUID
    scenario_id: UUID
    hotel_id: str
    dept_code: str              # '0120' F&B, '0151' Retail, '0150' Activities, etc.
    account_code: str           # '5101', '5102', '5150', '5201', '5350', etc.
    account_name: str           # 'FOOD COST', 'BEVERAGE COST', etc.

    # Modo de cálculo — el usuario elige por línea
    calc_mode: str              # 'MANUAL' | 'DRIVER'

    # Si DRIVER: configuración del driver
    driver_type: str            # 'REVENUE_LINE' | 'OCC_ROOMS' | 'GUESTS' |
                                # 'AVAIL_ROOMS' | 'KILOS' | null si MANUAL
    driver_pct_or_rate: Decimal # el % o tarifa que ingresa el usuario
                                # Si REVENUE_LINE: porcentaje (ej: 0.28 = 28%)
                                # Si OCC_ROOMS/GUESTS/AVAIL_ROOMS/KILOS: monto por unidad
    revenue_line_ref: str       # si driver_type='REVENUE_LINE': qué línea de ingreso
                                # 'FOOD' | 'BEVERAGE' | 'ACTIVITIES' | 'TRANSPORT' |
                                # 'INNOCEANA' | 'RETAIL' | 'ROOMS' | 'SPA'

    # Montos calculados o manuales por mes (siempre en USD)
    jan: Decimal; feb: Decimal; mar: Decimal; apr: Decimal
    may: Decimal; jun: Decimal; jul: Decimal; aug: Decimal
    sep: Decimal; oct: Decimal; nov: Decimal; dec: Decimal

    # Flag: si es DRIVER, estos montos se recalculan al presionar Recalcular
    # Si es MANUAL, se preservan intactos
```

### 13.3 Engine de cálculo de costos

```python
# engine/cost_calculator.py

def calculate_cost_entry(
    entry: CostEntry,
    scenario_id: UUID,
    month: int
) -> Decimal:
    """
    Calcula el monto de una línea de costo para un mes dado.
    Si MANUAL → devuelve el valor ya ingresado sin tocarlo.
    Si DRIVER → calcula desde la base elegida × driver_pct_or_rate.
    """
    if entry.calc_mode == 'MANUAL':
        return get_month_value(entry, month)  # respeta lo ingresado

    # Obtener el valor base según el driver_type
    if entry.driver_type == 'REVENUE_LINE':
        # Base = ingreso de la línea referenciada ese mes
        base = get_revenue_line(scenario_id, entry.revenue_line_ref, month)
        # Monto = ingreso × porcentaje
        # Ej: Food Revenue $113,357 × 28% = $31,740 Food Cost
        return base * entry.driver_pct_or_rate

    elif entry.driver_type == 'OCC_ROOMS':
        # Base = noches ocupadas del mes
        occ_rooms = get_rooms_occupied(scenario_id, month)
        # Monto = noches ocupadas × tarifa por noche
        # Ej: 697.5 noches × $12 = $8,370
        return occ_rooms * entry.driver_pct_or_rate

    elif entry.driver_type == 'GUESTS':
        # Base = total huéspedes del mes
        guests = get_total_guests(scenario_id, month)
        # Monto = huéspedes × tarifa por huésped
        return guests * entry.driver_pct_or_rate

    elif entry.driver_type == 'AVAIL_ROOMS':
        # Base = noches disponibles del mes (independiente de ocupación)
        avail_rooms = get_rooms_available(scenario_id, month)
        return avail_rooms * entry.driver_pct_or_rate

    elif entry.driver_type == 'KILOS':
        # Base = kilos lavados del mes (de LaundryAllocationConfig)
        kilos = get_total_kilos(scenario_id, month)
        return kilos * entry.driver_pct_or_rate

    return Decimal('0')


def recalculate_costs(scenario_id: UUID, month: int):
    """
    Recalcula todas las líneas de costo con DRIVER para un mes.
    Las líneas MANUAL no se tocan.
    Llamado desde recalculate_scenario() en el paso de costos.
    """
    entries = get_cost_entries(scenario_id)
    for entry in entries:
        if entry.calc_mode == 'DRIVER':
            amount = calculate_cost_entry(entry, scenario_id, month)
            set_month_value(entry, month, amount)
            save(entry)
```

### 13.4 Vista del checkbook de costos en el UI

```
CHECKBOOK DE COSTOS — F&B (Dept 0120) — Budget 2026

                                                    BASE DRIVER
Cuenta  | Descripción        | Modo    | Driver / % | Ref Ingreso   | Ene       | Feb       | ... | Total
────────┼────────────────────┼─────────┼────────────┼───────────────┼───────────┼───────────┼─────┼──────
        | ── REFERENCIA ──   |         |            |               |           |           |     |
        | Food Revenue       | [ref]   |            |               | $113,357  | $103,752  | ... | $709,115
        | Beverage Revenue   | [ref]   |            |               | $38,541   | $35,276   | ... | $241,099
────────┼────────────────────┼─────────┼────────────┼───────────────┼───────────┼───────────┼─────┼──────
        | ── COSTOS ──       |         |            |               |           |           |     |
5101    | Food Cost          | DRIVER  | 28.0%      | Food Rev      | $31,740   | $29,051   | ... | $198,552
5102    | Bar to Food Cost   | DRIVER  |  2.0%      | Bev Rev       | $771      | $706      | ... | $4,822
5103    | Freight on Food    | MANUAL  |            |               | $500      | $500      | ... | $6,000
5150    | Beverage Cost      | DRIVER  | 22.0%      | Bev Rev       | $8,479    | $7,761    | ... | $53,042
5151    | Liquor Cost        | DRIVER  | 25.0%      | Bev Rev       | $2,500    | $2,290    | ... | $15,675  ← % editable
5152    | Wine Cost          | DRIVER  | 30.0%      | Bev Rev       | $1,200    | $1,100    | ... |
5153    | Beer Cost          | DRIVER  | 18.0%      | Bev Rev       | $800      | $733      | ... |
5154    | Other Costs        | MANUAL  |            |               | $200      | $200      | ... |
5161    | F&B Misc Cost      | DRIVER  |  3.0%      | Food Rev      | $3,401    | $3,113    | ... |
────────┼────────────────────┼─────────┼────────────┼───────────────┼───────────┼───────────┼─────┼──────
        | TOTAL COST OF SALES|         |            |               | $49,591   | $45,454   | ... | $XXX,XXX
        | GROSS PROFIT       |         |            |               | $102,307  | $93,574   | ... | $XXX,XXX
        | % GROSS MARGIN     |         |            |               |   67.4%   |   66.7%   | ... |    XX.X%
```

**Notas del UI:**
- Las filas de **REFERENCIA** (ingresos) son read-only — aparecen para contexto visual
- Cuando el modo es `DRIVER`, el campo `%` o `tarifa` es editable por el usuario
- Cuando el modo es `MANUAL`, el usuario ingresa el monto directamente en cada celda de mes
- El usuario puede cambiar el modo de cualquier línea en cualquier momento
- `GROSS PROFIT` y `% GROSS MARGIN` se calculan automáticamente al fondo del checkbook

### 13.5 Checkbooks de costos por departamento

Cada departamento que tiene cuentas 5xxx tiene su propio checkbook:

| Dept | Checkbook | Cuentas 5 disponibles | Driver natural |
|------|-----------|----------------------|----------------|
| 0120 | F&B Costs | 5101–5165 | % de Food/Bev Revenue |
| 0140 | Spa Retail Costs | 5300–5301 | % de Spa Retail Revenue |
| 0150 | Activity Costs | 5350–5351 | Por noche ocupada o por huésped |
| 0151 | Retail Store Costs | 5201–5223 | % de Retail Revenue |
| 0152 | Transport Costs | 5360–5363 | Por noche ocupada |
| 0155 | Innoceana Costs | 5380–5383 | Por noche ocupada |
| 0160 | Laundry Costs | 5501 | Por kilo lavado |
| 0220 | Cafetería Costs | 5420–5421 | Por huésped (staff meals) o manual |
| 0230 | IT/Telecom Costs | 5400–5404 | Manual (facturas fijas) |

### 13.6 Endpoints del checkbook de costos

```
# Checkbook por departamento
GET  /api/costs/{scenario_id}/depts/                    depts que tienen cuentas 5
GET  /api/costs/{scenario_id}/dept/{dept_code}/         checkbook completo del dept
PUT  /api/costs/{scenario_id}/dept/{dept_code}/entry/{account_code}/
                                                        actualizar modo + driver + montos

# Cambiar modo de una línea
PUT  /api/costs/{scenario_id}/entry/{id}/mode/          MANUAL ↔ DRIVER
PUT  /api/costs/{scenario_id}/entry/{id}/driver/        cambiar tipo y % de driver

# Resumen
GET  /api/costs/{scenario_id}/summary/                  todos los depts
GET  /api/costs/{scenario_id}/dept/{dept_code}/gross-profit/  GP y margen del dept
```

### 13.7 Tests críticos de costos

```python
def test_food_cost_pct_of_revenue():
    """Food Cost = % × Food Revenue del mes."""
    set_driver(entry_5101, driver_type='REVENUE_LINE',
               pct=Decimal('0.28'), ref='FOOD')
    recalculate_scenario(scenario_id)
    food_rev_jan = get_revenue('FOOD', month=1)   # $113,357
    food_cost_jan = get_cost('5101', dept='0120', month=1)
    assert abs(float(food_cost_jan) - float(food_rev_jan * Decimal('0.28'))) < 0.01

def test_manual_cost_not_changed_on_recalc():
    """Una línea MANUAL no cambia al recalcular."""
    set_manual(entry_5103, month=1, amount=Decimal('500'))
    set_manual(entry_5103, month=2, amount=Decimal('450'))
    recalculate_scenario(scenario_id)
    assert get_cost('5103', dept='0120', month=1) == Decimal('500')
    assert get_cost('5103', dept='0120', month=2) == Decimal('450')

def test_cost_per_occ_room():
    """Costo por noche ocupada × noches ocupadas del mes."""
    set_driver(entry_5350, driver_type='OCC_ROOMS',
               rate=Decimal('12.00'))  # $12 por noche ocupada
    recalculate_scenario(scenario_id)
    occ_jan = get_rooms_occupied(scenario_id, month=1)  # 697.5
    cost_jan = get_cost('5350', dept='0150', month=1)
    assert abs(float(cost_jan) - float(occ_jan * Decimal('12'))) < 0.01

def test_october_cost_zero_when_no_revenue():
    """Cuando revenue=0, costs con driver REVENUE_LINE = 0 (cualquier mes, no solo octubre)."""
    recalculate_scenario(scenario_id)
    food_cost_oct = get_cost('5101', dept='0120', month=10)
    assert food_cost_oct == Decimal('0')  # Food Revenue Oct = 0

def test_gross_profit_calculation():
    """Gross Profit = Revenue - Cost of Sales."""
    food_rev = get_revenue('FOOD', month=1)
    bev_rev  = get_revenue('BEVERAGE', month=1)
    fb_costs = sum_dept_costs(scenario_id, dept='0120', month=1)
    gp = calculate_dept_gross_profit(scenario_id, dept='0120', month=1)
    assert abs(float(gp) - float(food_rev + bev_rev - fb_costs)) < 0.01

def test_driver_mode_change_triggers_recalc():
    """Cambiar de MANUAL a DRIVER recalcula el monto en el siguiente recalculate."""
    set_manual(entry_5101, month=1, amount=Decimal('30000'))
    switch_to_driver(entry_5101, driver_type='REVENUE_LINE',
                     pct=Decimal('0.28'), ref='FOOD')
    recalculate_scenario(scenario_id)
    food_rev = get_revenue('FOOD', month=1)
    new_cost = get_cost('5101', dept='0120', month=1)
    assert abs(float(new_cost) - float(food_rev * Decimal('0.28'))) < 0.01
    # Ya no es $30,000 — ahora es 28% del Food Revenue
```

---

## 14. ALLOCATIONS — CAFETERÍA Y LAVANDERÍA


### 14.1 Concepto general
Cafetería (empleados) y Lavandería son **departamentos de soporte** cuyos costos deben quedar en **$0 neto** al final de cada mes. Sus gastos se redistribuyen (allocate) a los departamentos operativos y overhead. El P&L de CWL siempre debe mostrar:

```
Cafetería de Empleados:   Gasto bruto - Allocation saliente = $0
Lavandería:               Gasto bruto - Allocation saliente = $0
```

Los departamentos receptores reciben una línea adicional de gasto (allocation entrante) que aumenta su costo operativo.

### 14.2 Cafetería de Empleados — Allocation por FTE

**Regla:** El gasto total de cafetería del mes se distribuye proporcionalmente al FTE de cada departamento. Solo participan los departamentos cuyos empleados **físicamente comen en la propiedad**.

```python
class CafeteriaAllocationConfig(Base):
    """
    Configuración de qué departamentos participan en el allocation de cafetería.
    Editable por escenario — puede cambiar entre Budget y Forecast.
    """
    __tablename__ = 'cafeteria_allocation_config'

    id: UUID
    scenario_id: UUID
    dept_code: str          # '0111', '0120', '0150', etc.
    dept_name: str
    participates: bool      # True = come en propiedad, recibe allocation
                            # False = remoto o fuera de propiedad, NO recibe allocation
    notes: str              # ej: "Equipo de ventas — trabaja en San José"

# Ejemplos de departamentos que NO participan (remotos o fuera de propiedad):
# - Sales & Marketing (trabajan en oficinas en San José)
# - Algunas posiciones de Finance/Admin que son remotas
# - Propietarios (Owners expenses — no tienen empleados en propiedad)
```

**Cálculo del allocation de cafetería:**
```python
def calculate_cafeteria_allocation(
    scenario_id: UUID,
    month: int
) -> dict[str, Decimal]:
    """
    Distribuye el gasto total de cafetería entre departamentos participantes
    en proporción a su FTE del mes.

    PASOS:
    1. Obtener gasto total cafetería del mes (sum de FinancialEntry donde
       dept=Cafetería y entry_type='OPEX' + 'PAYROLL')
    2. Obtener FTE total del mes solo de departamentos con participates=True
    3. Para cada dept participante: allocation = gasto_total × (fte_dept / fte_total)
    4. Crear entradas de allocation con account_code='ALLOC_CAF' y signo negativo
       en el dept de Cafetería, y positivo en cada dept receptor

    RESULTADO: Cafetería queda en $0, cada dept receptor absorbe su parte.
    """
    config = get_cafeteria_config(scenario_id)
    participating_depts = [c.dept_code for c in config if c.participates]

    total_cafeteria_cost = sum_dept_total(scenario_id, 'CAF', month)

    # FTE solo de departamentos participantes
    fte_by_dept = {
        dept: sum_fte_by_dept(scenario_id, dept, month)
        for dept in participating_depts
    }
    total_fte = sum(fte_by_dept.values())

    if total_fte == 0:
        return {}  # Sin FTE no hay allocation — evitar división por cero

    return {
        dept: total_cafeteria_cost * (fte / total_fte)
        for dept, fte in fte_by_dept.items()
    }
```

**Regla del FTE remoto:**
- Un empleado remoto tiene `participates=False` en su departamento.
- Su FTE **sí** se cuenta para el presupuesto de planilla del departamento.
- Su FTE **NO** se cuenta para el denominador del allocation de cafetería.
- Esta configuración es por escenario — puede cambiar si un empleado se vuelve presencial.

### 14.3 Lavandería — Allocation por Kilos Históricos

**Regla:** El gasto total de lavandería del mes se distribuye según la proporción histórica de kilos lavados por departamento. Los kilos históricos son un parámetro fijo por escenario (no cambian mes a mes dentro del mismo escenario).

```python
class LaundryAllocationConfig(Base):
    """
    Configuración de kilos históricos por departamento para el allocation de lavandería.
    Se ingresa una vez por escenario basado en datos históricos reales.
    """
    __tablename__ = 'laundry_allocation_config'

    id: UUID
    scenario_id: UUID
    dept_code: str
    dept_name: str
    kilos_historicos: Decimal   # kilos promedio mensual lavados para este dept
                                # basado en datos históricos de CWL
    participates: bool          # True = usa lavandería, False = no aplica
    notes: str                  # ej: "Rooms: lencería de camas y toallas"

# Ejemplos de uso típico en CWL:
# Rooms:      mayor volumen (ropa de cama, toallas de habitaciones)
# F&B:        mantelería, uniformes de cocina
# Spa:        toallas de spa, batas
# Housekeeping: uniformes del personal
# Admin/Sales: muy poco o nulo
```

**Cálculo del allocation de lavandería:**
```python
def calculate_laundry_allocation(
    scenario_id: UUID,
    month: int
) -> dict[str, Decimal]:
    """
    Distribuye el gasto total de lavandería según proporción de kilos históricos.

    PASOS:
    1. Obtener gasto total lavandería del mes
    2. Obtener kilos históricos de departamentos participantes
    3. Para cada dept: allocation = gasto_total × (kilos_dept / kilos_total)
    4. Crear entradas de allocation — Lavandería queda en $0

    NOTA: Los kilos no varían mes a mes dentro del mismo escenario.
    Si hay variaciones estacionales significativas, se puede crear una versión
    con kilos por mes (extensión futura).
    """
    config = get_laundry_config(scenario_id)
    participating = [c for c in config if c.participates]

    total_laundry_cost = sum_dept_total(scenario_id, 'LAUND', month)
    total_kilos = sum(c.kilos_historicos for c in participating)

    if total_kilos == 0:
        return {}

    return {
        c.dept_code: total_laundry_cost * (c.kilos_historicos / total_kilos)
        for c in participating
    }
```

### 14.4 Modelo de entrada de allocation en el P&L

```python
class AllocationEntry(Base):
    """
    Registra cada allocation calculado. Separado de FinancialEntry
    para poder auditarlo y revertirlo independientemente.
    """
    __tablename__ = 'allocation_entries'

    id: UUID
    scenario_id: UUID
    allocation_type: str    # 'CAFETERIA' | 'LAUNDRY'
    month: int
    year: int
    source_dept: str        # dept que origina el gasto ('CAF', 'LAUND')
    target_dept: str        # dept que recibe el allocation
    amount_usd: Decimal     # siempre positivo — es un cargo al dept receptor
    basis_value: Decimal    # FTE o kilos usados como base para el cálculo
    basis_type: str         # 'FTE' | 'KILOS'
    calculated_at: datetime
```

### 14.5 Cómo se muestra en el P&L

```
DEPARTAMENTO: ROOMS
  Gasto OPEX propio:              $12,500
  Gasto Planilla propio:          $45,000
  + Allocation Cafetería:         +$1,850   ← línea separada e identificada
  + Allocation Lavandería:        +$3,200   ← línea separada e identificada
  ─────────────────────────────────────────
  TOTAL GASTO ROOMS:              $62,550

DEPARTAMENTO: CAFETERÍA EMPLEADOS
  Gasto OPEX:                     $8,500
  Gasto Planilla:                 $3,200
  − Allocation saliente:          −$11,700
  ─────────────────────────────────────────
  NETO CAFETERÍA:                 $0        ← siempre debe ser $0

DEPARTAMENTO: LAVANDERÍA
  Gasto OPEX:                     $4,100
  Gasto Planilla:                 $2,800
  − Allocation saliente:          −$6,900
  ─────────────────────────────────────────
  NETO LAVANDERÍA:                $0        ← siempre debe ser $0
```

### 14.6 Endpoints de allocation
```
# Configuración
GET  /api/allocations/cafeteria/{scenario_id}/config/      ver config FTE remoto
PUT  /api/allocations/cafeteria/{scenario_id}/config/      actualizar participación depts
GET  /api/allocations/laundry/{scenario_id}/config/        ver kilos históricos
PUT  /api/allocations/laundry/{scenario_id}/config/        actualizar kilos

# Cálculo y resultados
POST /api/allocations/{scenario_id}/calculate/             recalcular todos los meses
GET  /api/allocations/{scenario_id}/month/{month}/         resultado de un mes
GET  /api/allocations/{scenario_id}/summary/               resumen anual por dept
```

### 14.7 Tests críticos de allocation
```python
def test_cafeteria_nets_to_zero():
    """El departamento de cafetería debe quedar en $0 cada mes."""
    for month in range(1, 13):
        net = calculate_dept_net(scenario_id, 'CAF', month)
        assert abs(float(net)) < 0.01, f"Cafetería no es $0 en mes {month}: {net}"

def test_laundry_nets_to_zero():
    """El departamento de lavandería debe quedar en $0 cada mes."""
    for month in range(1, 13):
        net = calculate_dept_net(scenario_id, 'LAUND', month)
        assert abs(float(net)) < 0.01, f"Lavandería no es $0 en mes {month}: {net}"

def test_cafeteria_allocation_sum_equals_total():
    """La suma de todos los allocations salientes = gasto total del dept."""
    for month in range(1, 13):
        total_cost = sum_dept_total(scenario_id, 'CAF', month)
        total_allocated = sum(calculate_cafeteria_allocation(scenario_id, month).values())
        assert abs(float(total_cost - total_allocated)) < 0.01

def test_remote_dept_excluded_from_cafeteria():
    """Un departamento marcado como remoto no recibe allocation de cafetería."""
    # Marcar Sales como remoto
    set_cafeteria_participation(scenario_id, 'SALES', participates=False)
    allocations = calculate_cafeteria_allocation(scenario_id, month=1)
    assert 'SALES' not in allocations

def test_remote_fte_still_counts_for_payroll():
    """Un dept remoto sí tiene FTE para planilla — solo se excluye de cafetería."""
    sales_fte = sum_fte_by_dept(scenario_id, 'SALES', month=1)
    assert sales_fte > 0  # tiene empleados
    allocations = calculate_cafeteria_allocation(scenario_id, month=1)
    assert 'SALES' not in allocations  # pero no recibe cafetería

def test_laundry_allocation_proportional():
    """Si Rooms tiene el doble de kilos que F&B, recibe el doble del allocation."""
    set_laundry_kilos(scenario_id, 'ROOMS', kilos=2000)
    set_laundry_kilos(scenario_id, 'F_B', kilos=1000)
    allocations = calculate_laundry_allocation(scenario_id, month=1)
    assert abs(float(allocations['ROOMS'] / allocations['F_B']) - 2.0) < 0.01
```

---

## 15. MÓDULO DE INGRESOS — OPERATIVA COMPLETA

### 15.1 Visión general: qué contienen Rates y Key Indicators

El tab **`Rates 2026`** y el tab **`Key Indicators`** son el cerebro del presupuesto de ingresos. Contienen:

1. **Inventario de habitaciones** por tipo de villa × mes (unidades y noches disponibles)
2. **Tarifas Rack y Netas** por tipo de villa × mes (inputs manuales)
3. **Mix de canales de venta** con su % de comisión (Travel Agency 28%, OTAs 20%, Direct 0%)
4. **Net Rate after commissions** = Rack × (1 - comisión ponderada por canal)
5. **Ocupación** por tipo de villa × mes (inputs manuales)
6. **Revenue por tipo de villa** = Noches Ocupadas × Net Rate
7. **Guests** = Noches Ocupadas × Ratio Guests/Room (1.8 en CWL)
8. **Componentes del paquete** (Transfer, Breakfast, Lunch, Dinner, Tours) con su valor Rack y Neto
9. **Revenue de paquete** por componente × mes
10. **ADR ponderado** y **RevPAR** calculados

El tab **`Key Indicators`** también tiene los **históricos 2024 y 2025** lado a lado con el Budget 2026, permitiendo análisis comparativo.

### 15.2 Cómo funciona el modelo de canales

CWL vende a través de 3 canales con distintos % de comisión:

```
Canal           % Ventas (Budget 2026)   % Comisión
─────────────────────────────────────────────────────
Travel Agency        60%                    28%
OTAs                  5%                    20%
Direct               35%                     0%
─────────────────────────────────────────────────────
SUMPRODUCT net commission = 0.6×0.28 + 0.05×0.20 + 0.35×0 = 0.178 (17.8% promedio)
Net Rate = Rack Rate × (1 - 0.178) = Rack × 0.822
```

**Estos porcentajes son inputs manuales editables** por escenario. El sistema recalcula el Net Rate automáticamente cuando cambian.

### 15.3 Componentes del paquete CWL

CWL vende paquetes todo-incluido. El paquete tiene componentes con valor propio que se contabilizan en diferentes líneas de ingreso:

**Por estadía de 3 días (Rack):**
| Componente | Rack/pax | Se registra en |
|---|---|---|
| Transfer In & Out | $105 | Transportation |
| Breakfast Included | $54 (3 días × $18) | Food Revenue |
| Lunch Included | $108 (3 días × $36) | Food Revenue |
| Dinner Included | $162 (3 días × $54) | Food Revenue |
| Snorkeling Tour | $144 | Activities |
| PN Walk San Pedrillo | $159 | Activities |
| **Total paquete/pax** | **$732** | — |

**Por noche (Rack):**
| Componente | Rack/pax/noche |
|---|---|
| Transfer In & Out | $35 |
| Breakfast | $18 |
| Lunch | $36 |
| Dinner | $54 |
| Snorkeling | $48 |
| PN Walk | $53 |
| **Total/noche** | **$244** |

**Net por noche (después de comisiones):** $203.984 ≈ $244 × (1 - 0.164)

### 15.4 Modelo de datos completo

```python
class RoomTypeConfig(Base):
    """
    Configuración fija de tipos de habitación — master data de CWL.
    Datos exactos del archivo YTD_Rev_by_Room2026.xlsx.
    30 unidades en 6 categorías.
    """
    __tablename__ = 'room_type_configs'

    id: int
    hotel_id: str               # 'CWL'
    name: str
    units: int
    active: bool

# MASTER DATA CWL — NO MODIFICAR SIN AUTORIZACIÓN:
# id  name                                      units
#  1  Corcovado Deluxe Villas, King bed            6
#  2  Carate Deluxe Villa Double Beds              2
#  3  Agujas Villa 2 Queen Beds                    4
#  4  Sirena Suites, Queen Bed (connecting)        8
#  5  Treehouse king bed                           5
#  6  5 Elements Treehouse king bed                5
#     TOTAL                                       30
#
# Noches disponibles por mes = units × días del mes
# Ej: Enero (31 días):
#   Corcovado Deluxe (6):  6 × 31 = 186 noches
#   Carate Double (2):     2 × 31 =  62 noches
#   Agujas Queen (4):      4 × 31 = 124 noches
#   Sirena Suites (8):     8 × 31 = 248 noches
#   Treehouse (5):         5 × 31 = 155 noches
#   5 Elements (5):        5 × 31 = 155 noches
#   TOTAL (30):           30 × 31 = 930 noches disponibles enero
#
# Octubre en CWL 2026: rooms_available = units × 31 (normal), pero occupancy% = 0.00 (input del usuario)
    # Si el usuario cambia occupancy% de octubre, el sistema calcula revenue correctamente
#
# LÍNEA ESPECIAL "Other Rooms Revenue":
# Aparece en el reporte de Room Stats como una línea separada.
# Son ingresos de habitaciones que no clasifican en ningún tipo específico
# (ej: upgrades, ajustes, cortesías cobradas). Se registran aparte.
# En el sistema se almacena como room_type_id = 0 (otros).
# Ene 2026: $10,246.62 | Feb: $3,020.85 | Mar: $799.80
# No tiene noches ni ADR asociados — es solo un monto de Revenue.


class HistoricalKpi(Base):
    """
    KPIs históricos reales (Actual) por tipo de villa × mes × año.
    Se importan desde el archivo Excel o se suben manualmente.
    Incluye 2024 y 2025. Son READ-ONLY una vez importados.
    """
    __tablename__ = 'historical_kpis'

    id: UUID
    hotel_id: str
    year: int                   # 2024, 2025
    month: int                  # 1-12
    room_type_id: int           # 1-6 o 0 para total
    rooms_available: int
    rooms_occupied: Decimal
    guests: Decimal
    occupancy_pct: Decimal
    adr_usd: Decimal            # Average Daily Rate real
    revpar_usd: Decimal
    revenue_usd: Decimal        # ingreso real de rooms
    source: str                 # 'ACTUAL_IMPORT' | 'MANUAL'


class SalesChannelConfig(Base):
    """
    Configuración de canales de venta por escenario.
    Inputs manuales que afectan el Net Rate.
    """
    __tablename__ = 'sales_channel_configs'

    id: UUID
    scenario_id: UUID
    channel_name: str           # 'Travel Agency' | 'OTAs' | 'Direct'
    sales_pct: Decimal          # % de ventas por este canal (deben sumar 1.0)
    commission_pct: Decimal     # % de comisión que cobra este canal
    # Net commission efectiva = SUM(sales_pct × commission_pct) para todos los canales


class RateCard(Base):
    """
    Tarifas Rack por tipo de villa × mes. Input manual.
    Net Rate se calcula automáticamente desde Rack × (1 - net_commission).
    """
    __tablename__ = 'rate_cards'

    id: UUID
    scenario_id: UUID
    month: int
    room_type_id: int
    rack_rate_usd: Decimal          # Input manual — tarifa publicada
    net_commission_pct: Decimal     # Calculado desde SalesChannelConfig
    net_rate_usd: Decimal           # Calculado: rack × (1 - net_commission_pct)


class OccupancyBudget(Base):
    """
    Ocupación presupuestada por tipo de villa × mes. Input manual.
    """
    __tablename__ = 'occupancy_budgets'

    id: UUID
    scenario_id: UUID
    month: int
    room_type_id: int
    days_in_month: int              # 28, 30, 31 según el mes
    units: int                      # unidades de ese tipo
    rooms_available: int            # Calculado: units × days_in_month
    occupancy_pct: Decimal          # INPUT MANUAL
    rooms_occupied: Decimal         # Calculado: rooms_available × occupancy_pct
    guests: Decimal                 # Calculado: rooms_occupied × guests_per_room_ratio


class PackageComponentConfig(Base):
    """
    Valor de cada componente del paquete por escenario.
    Los valores Rack son inputs manuales.
    Los valores Net se calculan con la comisión del canal.
    """
    __tablename__ = 'package_component_configs'

    id: UUID
    scenario_id: UUID
    component_name: str         # 'Transfer', 'Breakfast', 'Lunch', 'Dinner', 'Snorkeling', 'PN Walk'
    revenue_line: str           # 'TRANSPORT' | 'FOOD' | 'ACTIVITIES'
    usali_account: str          # '4500' | '4110' | '4400'
    rack_rate_per_pax_night: Decimal    # valor rack por pax por noche
    net_rate_per_pax_night: Decimal     # calculado: rack × (1 - commission)
    included_in_package: bool


class RevenueResult(Base):
    """
    Resultados calculados por el engine. NUNCA editar directamente.
    Se regeneran automáticamente cuando cambia cualquier input.
    """
    __tablename__ = 'revenue_results'

    id: UUID
    scenario_id: UUID
    month: int
    year: int
    revenue_line: str           # 'ROOMS', 'FOOD', 'TRANSPORT', 'ACTIVITIES', 'SPA', etc.
    dept_code: str
    account_code: str
    amount_usd: Decimal
    # KPIs solo para ROOMS
    rooms_available: int
    rooms_occupied: Decimal
    total_guests: Decimal
    occupancy_pct: Decimal
    adr_usd: Decimal
    revpar_usd: Decimal
```

### 15.5 Engine de cálculo de ingresos

```python
# engine/revenue_calculator.py

def calculate_net_commission(scenario_id: UUID) -> Decimal:
    """
    Comisión neta ponderada = SUMPRODUCT(% ventas × % comisión por canal)
    Ej: 0.60×0.28 + 0.05×0.20 + 0.35×0.00 = 0.178
    """
    channels = get_channel_configs(scenario_id)
    return sum(c.sales_pct * c.commission_pct for c in channels)


def calculate_net_rates(scenario_id: UUID, month: int):
    """
    Para cada tipo de villa del mes:
    net_rate = rack_rate × (1 - net_commission)
    Actualiza RateCard.net_rate_usd automáticamente.
    """
    net_comm = calculate_net_commission(scenario_id)
    rates = get_rate_cards(scenario_id, month)
    for rate in rates:
        rate.net_commission_pct = net_comm
        rate.net_rate_usd = rate.rack_rate_usd * (1 - net_comm)
    save_rates(rates)


def calculate_revenue_month(scenario_id: UUID, month: int) -> dict:
    """
    PASO 1: Net rates (desde Rack + canales)
    PASO 2: Rooms Occupied y Guests por tipo de villa
    PASO 3: Room Revenue = SUM(rooms_occ_tipo × net_rate_tipo)
    PASO 4: ADR ponderado = Room Revenue / Total Rooms Occupied
    PASO 5: RevPAR = ADR × Occupancy%
    PASO 6: Package components revenue (Food, Transport, Activities)
    """
    occupancy = get_occupancy(scenario_id, month)   # por tipo de villa
    rates = get_rate_cards(scenario_id, month)       # net_rate por tipo
    packages = get_package_configs(scenario_id)
    ratio = get_guests_per_room_ratio(scenario_id)  # 1.8

    # Rooms
    total_available = sum(o.rooms_available for o in occupancy)
    total_occupied  = sum(o.rooms_occupied  for o in occupancy)
    total_guests    = sum(o.guests          for o in occupancy)  # occ × ratio
    occ_pct = total_occupied / total_available if total_available > 0 else 0

    room_revenue = sum(
        o.rooms_occupied * get_rate(rates, o.room_type_id).net_rate_usd
        for o in occupancy
    )
    adr    = room_revenue / total_occupied if total_occupied > 0 else 0
    revpar = adr * occ_pct

    # Package components → distribuir por revenue_line
    component_revenue = {}
    for pkg in packages:
        if pkg.included_in_package:
            rev = total_guests * pkg.net_rate_per_pax_night
            line = pkg.revenue_line
            component_revenue[line] = component_revenue.get(line, 0) + rev

    return {
        'ROOMS':        room_revenue,
        'FOOD':         component_revenue.get('FOOD', 0),
        'TRANSPORT':    component_revenue.get('TRANSPORT', 0),
        'ACTIVITIES':   component_revenue.get('ACTIVITIES', 0),
        # KPIs
        'rooms_available': total_available,
        'rooms_occupied':  total_occupied,
        'total_guests':    total_guests,
        'occupancy_pct':   occ_pct,
        'adr':             adr,
        'revpar':          revpar,
    }


def recalculate_all(scenario_id: UUID):
    """
    Disparado automáticamente cuando cambia:
    - Canal de ventas (% o comisión)
    - Rack rate de cualquier tipo de villa
    - Ocupación de cualquier tipo de villa o mes
    - Ratio guests/room
    - Componente de paquete
    """
    update_net_rates_all_months(scenario_id)
    for month in range(1, 13):
        result = calculate_revenue_month(scenario_id, month)
        save_revenue_result(scenario_id, month, result)
        propagate_to_financial_entries(scenario_id, month, result)
```

### 15.6 Históricos: estructura de datos multi-año

El sistema mantiene KPIs históricos desde **2024** para permitir comparación:

```python
# Vista Key Indicators en el sistema:
# Columnas: Indicador | 2024 Actual | 2025 Actual | 2026 Budget | 2026 Forecast
# Filas: Rooms Available, Rooms Occupied, Guests, Occupancy%, ADR, RevPAR,
#        Revenue by Room Type (6 tipos), Revenue by Month

class KpiSnapshot(Base):
    """
    Snapshot anual de KPIs para comparación histórica.
    Una fila por hotel × año × mes × room_type × data_type.
    """
    __tablename__ = 'kpi_snapshots'

    id: UUID
    hotel_id: str
    year: int
    month: int
    room_type_id: int           # 0 = total, 1-6 = por tipo
    data_type: str              # 'ACTUAL' | 'BUDGET' | 'FORECAST'
    scenario_id: UUID           # nullable para ACTUAL histórico

    # Métricas
    rooms_available: int
    rooms_occupied: Decimal
    guests: Decimal
    occupancy_pct: Decimal
    adr_usd: Decimal
    revpar_usd: Decimal
    room_revenue_usd: Decimal

    # Revenue por línea (para Key Indicators completo)
    food_revenue: Decimal
    bev_revenue: Decimal
    activities_revenue: Decimal
    transport_revenue: Decimal
    spa_revenue: Decimal
    retail_revenue: Decimal
    innoceana_revenue: Decimal
    total_revenue: Decimal
```

### 15.7 UI del módulo de ingresos

**Pantalla 1 — Key Indicators (vista comparativa):**
```
                    2024 Actual  2025 Actual  2026 Budget  2026 Forecast
─────────────────────────────────────────────────────────────────────────
ENERO
  Rooms Available      930          930          930           930
  Rooms Occupied       429          454          697.5         680
  % Occupancy         46.1%        48.8%         75%          73.1%
  ADR                $359.84      $473.51       $595.27       $581.00
  RevPAR             $166.07      $231.18       $446.45       $424.85
  Total Guests         711          809          1,255         1,224

REVENUE POR TIPO DE VILLA (Enero)
  Corcovado Deluxe King  $XXX   $XXX   $101,461  $XXX
  Carate Double          $XXX   $XXX    $31,255  $XXX
  ...
```

**Pantalla 2 — Rates (inputs editables):**
```
CANALES DE VENTA                    % Ventas  % Comisión
  Travel Agency                      60%        28%      ← editable
  OTAs                                5%        20%      ← editable
  Direct                             35%         0%      ← editable
  ─────────────────────────────────────────────────────
  Comisión neta ponderada:           17.8%      (calculado)

RACK RATES POR TIPO DE VILLA × MES  (editables)
  Tipo de Villa            Ene    Feb    Mar  ...  Dic
  Corcovado Deluxe King   $725   $725   $725  ... $830  ← editables
  Carate Double           $670   $670   $670  ... $775
  ...

NET RATES CALCULADOS (read-only)
  Corcovado Deluxe King  $606.1 $606.1 $606.1 ... $693.88
  ...

OCUPACIÓN POR TIPO × MES            (editables)
  Tipo de Villa            Ene    Feb    Mar  ...  Dic
  Corcovado Deluxe King   75%    76%    65%  ...  65%   ← editables
  ...

COMPONENTES DEL PAQUETE             (editables)
  Componente              Rack/pax/noche  Net/pax/noche
  Transfer In & Out            $35           $29.26     ← rack editable
  Breakfast                    $18           $15.05
  Lunch                        $36           $30.10
  Dinner                       $54           $45.14
  Snorkeling                   $48           $40.13
  PN Walk                      $53           $44.31
```

### 15.8 Endpoints del módulo de ingresos

```
# Históricos
GET  /api/revenue/{hotel_id}/historical/               KPIs 2024-2025
POST /api/revenue/{hotel_id}/historical/import/        importar desde Excel

# Configuración (inputs manuales)
GET  /api/revenue/{scenario_id}/channels/              canales de venta
PUT  /api/revenue/{scenario_id}/channels/              actualizar → recálculo
GET  /api/revenue/{scenario_id}/rates/                 rack rates por tipo × mes
PUT  /api/revenue/{scenario_id}/rates/{month}/         actualizar → recálculo
GET  /api/revenue/{scenario_id}/occupancy/             ocupación por tipo × mes
PUT  /api/revenue/{scenario_id}/occupancy/{month}/     actualizar → recálculo
GET  /api/revenue/{scenario_id}/packages/              componentes del paquete
PUT  /api/revenue/{scenario_id}/packages/              actualizar → recálculo

# Resultados calculados (read-only)
GET  /api/revenue/{scenario_id}/results/               revenue 12 meses
GET  /api/revenue/{scenario_id}/kpis/                  KPIs calculados
GET  /api/revenue/{scenario_id}/kpis/comparison/       Budget vs Actual vs Forecast vs Histórico

# Recálculo manual (normalmente automático)
POST /api/revenue/{scenario_id}/recalculate/
```

### 15.9 Tests críticos de ingresos

```python
def test_net_rate_from_rack_and_channels():
    """Net rate = Rack × (1 - comisión ponderada)."""
    # Canal mix: 60% TA @ 28%, 5% OTA @ 20%, 35% Direct @ 0%
    net_comm = 0.60*0.28 + 0.05*0.20 + 0.35*0.00  # = 0.178
    rack = Decimal('725')
    expected_net = rack * Decimal(str(1 - net_comm))
    assert abs(float(get_net_rate(scenario_id, room_type=1, month=1) - expected_net)) < 0.01

def test_package_components_sum_to_total():
    """La suma de componentes del paquete × guests = total F&B + Transport + Activities."""
    result = calculate_revenue_month(scenario_id, month=1)
    guests = result['total_guests']
    net_per_pax = Decimal('203.984')  # del archivo
    expected_pkg_revenue = guests * net_per_pax
    actual_pkg = result['FOOD'] + result['TRANSPORT'] + result['ACTIVITIES']
    assert abs(float(actual_pkg - expected_pkg_revenue)) / float(expected_pkg_revenue) < 0.01

def test_october_zero_cwl_2026():
    """Octubre CWL Budget 2026: occupancy=0 → revenue=0.
    rooms_available sigue siendo 930 (30 villas × 31 días).
    Octubre NO tiene rooms_available=0 — tiene occupancy=0%."""
    result = calculate_revenue_month(scenario_id, month=10)
    assert result['rooms_available'] == 930   # el hotel existe
    assert result['occupancy_pct'] == 0        # pero no hay ocupación presupuestada
    assert result['ROOMS'] == 0               # sin ocupación → sin revenue
    assert result['FOOD'] == 0                # sin guests → sin F&B
    # Si cambiamos occupancy a 20%, debe calcular revenue correctamente
    update_occupancy(scenario_id, month=10, pct=Decimal('0.20'))
    result2 = calculate_revenue_month(scenario_id, month=10)
    assert result2['ROOMS'] > 0               # ahora sí hay revenue

def test_channel_change_recalculates_net_rate():
    """Cambiar % de canal dispara recálculo del net rate."""
    original_net = get_net_rate(scenario_id, room_type=1, month=1)
    update_channel(scenario_id, 'Direct', sales_pct=0.50)  # subir Direct de 35% a 50%
    new_net = get_net_rate(scenario_id, room_type=1, month=1)
    assert new_net > original_net  # más ventas directas = menor comisión = mayor net rate

def test_historical_2024_2025_preserved():
    """Los históricos 2024 y 2025 no cambian al modificar el Budget 2026."""
    hist_2024 = get_historical_kpi(hotel_id='CWL', year=2024, month=1)
    update_occupancy(scenario_id, month=1, occupancy_pct=Decimal('0.90'))
    hist_2024_after = get_historical_kpi(hotel_id='CWL', year=2024, month=1)
    assert hist_2024.rooms_occupied == hist_2024_after.rooms_occupied  # sin cambio

def test_jan2026_budget_reference_values():
    """Verificar contra datos del archivo original."""
    result = calculate_revenue_month(scenario_id, month=1)
    assert abs(float(result['ROOMS']) - 415201.91) < 100
    assert abs(float(result['total_guests']) - 1255.5) < 1
    assert abs(float(result['occupancy_pct']) - 0.75) < 0.001
    assert abs(float(result['adr']) - 595.27) < 1
```

### 15.10 Cómo funciona el presupuesto de ingresos (detalle)

El ingreso **no se ingresa directamente** en el sistema. Se construye desde **drivers (supuestos manuales)** que el sistema usa para calcular y explotar automáticamente todos los auxiliares y el total de ingresos.

La cadena de cálculo es:

```
INPUTS MANUALES (lo que el usuario ingresa)
    ↓
DRIVERS / SUPUESTOS
  · Tarifas (Rack Rate y Net Rate por tipo de villa × temporada)
  · Ocupación % por mes (por tipo de villa o total)
  · Ratio Guests per Room (huéspedes por habitación ocupada)
  · Revenue per Occupied Room (para Activities, F&B, Spa, etc.)
  · Revenue per Guest (alternativa para algunos departamentos)
    ↓
ENGINE CALCULA AUTOMÁTICAMENTE
  · Rooms Occupied = Rooms Available × Occupancy%
  · Total Guests = Rooms Occupied × Ratio Guests/Room
  · Room Revenue = Rooms Occupied × Net Rate (ponderado por tipo)
  · F&B Revenue = Total Guests × Revenue per Guest (Food)
  · Activities Revenue = Rooms Occupied × Revenue per Occupied Room
  · Spa Revenue = fijo mensual o por guest
  · Transport, Innoceana, Retail, Laundry = sus propios drivers
    ↓
AUXILIARES SE LLENAN AUTOMÁTICAMENTE
  · Hoja Rooms → detalle por tipo de villa × mes
  · Hoja Food Revenue → detalle por mes
  · Hoja Activities → detalle por mes
  · etc.
    ↓
SUMMARY SE RECALCULA
  · Total por línea de ingreso × mes
  · KPIs: Occupancy%, ADR, RevPAR, Revenue per Guest
```

### 15.11 Modelo de datos de ingresos (detalle)

```python
class RevenueAssumptions(Base):
    """
    Supuestos/drivers manuales por escenario. El usuario edita esto.
    El engine recalcula todo lo demás.
    """
    __tablename__ = 'revenue_assumptions'

    id: UUID
    scenario_id: UUID
    hotel_id: str           # 'CWL'
    month: int              # 1-12

    # === ROOMS ===
    # Ocupación se define por tipo de villa O total — no ambos
    occupancy_input_mode: str   # 'BY_ROOM_TYPE' | 'TOTAL'
    guests_per_room_ratio: Decimal  # ej: 1.8 — cuántos huéspedes por habitación ocupada

    # Tarifa neta promedio (después de descuentos/comisiones)
    # Se define por tipo de villa en RevenueRateCard
    # El ADR resultante es ponderado automáticamente

    # === F&B ===
    food_rev_per_guest: Decimal     # USD por huésped por día
    beverage_rev_per_guest: Decimal
    fb_misc_rev_per_guest: Decimal

    # === ACTIVITIES ===
    activities_rev_per_occ_room: Decimal  # USD por habitación ocupada
    # O alternativamente por guest:
    activities_rev_per_guest: Decimal

    # === SPA ===
    spa_rev_monthly_fixed: Decimal  # monto fijo mensual
    # O por guest:
    spa_rev_per_guest: Decimal
    spa_input_mode: str             # 'FIXED' | 'PER_GUEST'

    # === OTROS ===
    retail_rev_per_occ_room: Decimal
    transport_rev_per_occ_room: Decimal
    innoceana_rev_per_occ_room: Decimal
    sustainability_fee_per_guest: Decimal  # fee fija por huésped
    laundry_external_rev: Decimal           # ingreso fijo si hay servicio externo


class RevenueRateCard(Base):  # usar RateCard — ver sección 15.4
    """
    Tarifas por tipo de villa × mes × temporada.
    El usuario las ingresa. El engine las usa para calcular ADR y Room Revenue.
    """
    __tablename__ = 'revenue_rate_cards'

    id: UUID
    scenario_id: UUID
    month: int
    room_type_id: int       # 1-6 (los 6 tipos de CWL)
    room_type_name: str
    rack_rate_usd: Decimal  # tarifa publicada (Rack)
    net_rate_usd: Decimal   # tarifa neta (después de comisiones/descuentos)
                            # Revenue = Rooms Occupied × net_rate
    # Net rate = rack × (1 - comisión%)
    # En CWL la relación histórica neta/rack es ≈ 70% según datos del archivo


class RevenueOccupancy(Base):  # usar OccupancyBudget — ver sección 15.4
    """
    Ocupación por tipo de villa × mes.
    Input manual si occupancy_input_mode = 'BY_ROOM_TYPE'.
    Calculado desde total si mode = 'TOTAL'.
    """
    __tablename__ = 'revenue_occupancy'

    id: UUID
    scenario_id: UUID
    month: int
    room_type_id: int
    rooms_available: int    # calculado: unidades × días del mes
    occupancy_pct: Decimal  # INPUT MANUAL — el usuario define esto
    rooms_occupied: Decimal # CALCULADO: rooms_available × occupancy_pct


class RevenueResult(Base):  # duplicado — ver definición canónica arriba en sección 15.4
    """
    Resultados calculados por el engine. Se regeneran cada vez que
    cambia un assumption. NUNCA editar directamente — son outputs.
    """
    __tablename__ = 'revenue_results'

    id: UUID
    scenario_id: UUID
    month: int
    revenue_line: str       # 'ROOMS', 'FOOD', 'BEVERAGE', 'SPA', 'ACTIVITIES', etc.
    dept_code: str
    account_code: str       # código USALI
    amount_usd: Decimal
    # KPIs derivados
    rooms_available: int
    rooms_occupied: Decimal
    total_guests: Decimal
    occupancy_pct: Decimal
    adr_usd: Decimal        # Average Daily Rate (ponderado por tipo de villa)
    revpar_usd: Decimal     # Revenue Per Available Room = ADR × Occupancy%
    rev_per_guest: Decimal
    rev_per_occ_room: Decimal
    is_calculated: bool     # True = calculado por engine, False = ingresado manual
```

### 15.12 Engine de cálculo de ingresos (detalle)

```python
# engine/revenue_calculator.py

def calculate_revenue(scenario_id: UUID, month: int) -> RevenueResult:
    """
    PASO 1: Leer assumptions del mes
    PASO 2: Calcular KPIs base (rooms, guests)
    PASO 3: Calcular ingresos por línea
    PASO 4: Guardar RevenueResult (reemplazando cálculos anteriores del mes)
    PASO 5: Propagar a FinancialEntry para el P&L
    """
    assumptions = get_assumptions(scenario_id, month)
    rates = get_rate_cards(scenario_id, month)        # por tipo de villa
    occupancy = get_occupancy(scenario_id, month)     # por tipo de villa

    # --- PASO 2: KPIs base ---
    rooms_available = sum(o.rooms_available for o in occupancy)
    rooms_occupied = sum(o.rooms_occupied for o in occupancy)
    occupancy_pct = rooms_occupied / rooms_available if rooms_available > 0 else 0
    total_guests = rooms_occupied * assumptions.guests_per_room_ratio

    # ADR ponderado: suma(rooms_occ_tipo × net_rate_tipo) / total_rooms_occ
    weighted_revenue = sum(
        o.rooms_occupied * get_net_rate(rates, o.room_type_id)
        for o in occupancy
    )
    adr = weighted_revenue / rooms_occupied if rooms_occupied > 0 else 0
    revpar = adr * occupancy_pct

    # --- PASO 3: Ingresos por línea ---
    room_revenue = weighted_revenue  # ya calculado arriba

    food_revenue = total_guests * assumptions.food_rev_per_guest
    bev_revenue  = total_guests * assumptions.beverage_rev_per_guest
    fb_misc      = total_guests * assumptions.fb_misc_rev_per_guest

    activities_revenue = (
        rooms_occupied * assumptions.activities_rev_per_occ_room
        if assumptions.activities_rev_per_occ_room
        else total_guests * assumptions.activities_rev_per_guest
    )

    spa_revenue = (
        assumptions.spa_rev_monthly_fixed
        if assumptions.spa_input_mode == 'FIXED'
        else total_guests * assumptions.spa_rev_per_guest
    )

    retail_revenue    = rooms_occupied * assumptions.retail_rev_per_occ_room
    transport_revenue = rooms_occupied * assumptions.transport_rev_per_occ_room
    innoceana_revenue = rooms_occupied * assumptions.innoceana_rev_per_occ_room
    sustainability    = total_guests * assumptions.sustainability_fee_per_guest
    laundry_revenue   = assumptions.laundry_external_rev

    return {
        'ROOMS':        room_revenue,
        'FOOD':         food_revenue,
        'BEVERAGE':     bev_revenue,
        'FB_MISC':      fb_misc,
        'SPA':          spa_revenue,
        'ACTIVITIES':   activities_revenue,
        'RETAIL':       retail_revenue,
        'TRANSPORT':    transport_revenue,
        'INNOCEANA':    innoceana_revenue,
        'SUSTAINABILITY': sustainability,
        'LAUNDRY':      laundry_revenue,
        # KPIs
        'rooms_available': rooms_available,
        'rooms_occupied':  rooms_occupied,
        'occupancy_pct':   occupancy_pct,
        'total_guests':    total_guests,
        'adr':             adr,
        'revpar':          revpar,
    }


def recalculate_all_months(scenario_id: UUID):
    """
    Recalcula los 12 meses cuando cambia cualquier assumption.
    Se llama automáticamente cada vez que el usuario guarda un cambio.
    """
    for month in range(1, 13):
        result = calculate_revenue(scenario_id, month)
        save_revenue_result(scenario_id, month, result)
        propagate_to_financial_entries(scenario_id, month, result)
```

### 15.13 Tarifas por temporada — CWL

CWL tiene tarifas variables por temporada. Las temporadas son:
- **Holiday Season:** Dic 15 – Ene 5 (tarifas más altas del año)
- **High Season:** Ene 6 – Abr 30
- **Low/Shoulder Season:** May – Sep
- **Octubre en CWL 2026:** occupancy% = 0.00 en los inputs → ingreso = $0. rooms_available = 30 × 31 = 930 (el hotel existe, simplemente no presupuesta ocupación ese mes)
- **Recovery Season:** Nov – Dic 14

Los rate cards se ingresan por **tipo de villa × mes** — el sistema no asume temporadas fijas, el usuario define la tarifa de cada mes libremente.

**Datos históricos de referencia (del archivo):**
```
Net Rate ≈ Rack Rate × 0.70 (relación histórica aproximada para CWL)

Rack Rates 2026 (Budget):
  Corcovado Deluxe King:  $725 (Ene-Mar), $615 (May-Ago), $560 (Sep), $575 (Nov), $830 (Dic)
  5 Elements Treehouse: $1,130 (Ene-Mar), $980 (May-Ago), $910 (Sep), $965 (Nov), $1,282 (Dic)

Revenue per Occupied Room 2026 (Budget):
  Activities:   $151.98 constante todos los meses
  Food Revenue: $162.52 constante todos los meses
  Guests/Room:  1.8 ratio
```

### 15.14 UI del módulo de ingresos (detalle)

El usuario ve **dos niveles** de edición:

**Nivel 1 — Assumptions (inputs manuales):**
```
MES: ENERO 2026

ROOMS
  Tipo de Villa              | Unidades | Días | Noches Disp. | Ocup% (editable) | Noches Ocup. | Net Rate (editable)
  Corcovado Deluxe King      |    6     |  31  |    186       |    75%           |    139.5     |   $606.10
  Carate Deluxe Double       |    2     |  31  |     62       |    75%           |     46.5     |   $560.12
  ...
  TOTAL                      |   30     |  31  |    930       |    75%           |    697.5     |   ADR: $595.27

F&B
  Food Revenue/Guest:    $90.29 (editable)
  Beverage Rev/Guest:    $30.72 (editable)

ACTIVITIES
  Rev/Occupied Room:    $151.98 (editable)
```

**Nivel 2 — Resultados calculados (read-only, se actualizan automáticamente):**
```
INGRESOS CALCULADOS — ENERO 2026
  Rooms:         $415,202
  Food:          $113,357
  Beverage:       $38,541
  Activities:    $106,009
  ...
  TOTAL:         $XXX,XXX

KPIs:
  Occupancy:      75.0%
  ADR:           $595.27
  RevPAR:        $446.45
  Rev/Guest:     $XXX.XX
```

### 15.15 Endpoints del módulo de ingresos (detalle)
```
# Assumptions (inputs editables)
GET  /api/revenue/{scenario_id}/assumptions/              todos los meses
GET  /api/revenue/{scenario_id}/assumptions/{month}/      un mes
PUT  /api/revenue/{scenario_id}/assumptions/{month}/      actualizar → dispara recálculo

# Rate Cards
GET  /api/revenue/{scenario_id}/rates/                    tarifas todos los meses
PUT  /api/revenue/{scenario_id}/rates/{month}/            actualizar tarifas → dispara recálculo

# Ocupación
GET  /api/revenue/{scenario_id}/occupancy/                ocupación todos los meses
PUT  /api/revenue/{scenario_id}/occupancy/{month}/        actualizar → dispara recálculo

# Resultados (read-only — calculados por engine)
GET  /api/revenue/{scenario_id}/results/                  resultados 12 meses
GET  /api/revenue/{scenario_id}/results/{month}/          resultados un mes
GET  /api/revenue/{scenario_id}/summary/                  resumen anual por línea + KPIs

# Recálculo manual (normalmente automático)
POST /api/revenue/{scenario_id}/recalculate/              forzar recálculo completo
```

### 15.16 Tests críticos de ingresos (detalle)
```python
def test_october_revenue_zero():
    """Octubre CWL 2026: occupancy=0 en inputs → revenue=$0.
    IMPORTANTE: si se cambia occupancy a >0, el sistema debe calcular revenue correctamente."""
    result = calculate_revenue(scenario_id, month=10)
    assert result['ROOMS'] == 0
    assert result['FOOD'] == 0
    assert result['rooms_available'] == 0

def test_rooms_occupied_within_available():
    """No puede haber más habitaciones ocupadas que disponibles."""
    for month in range(1, 13):
        result = calculate_revenue(scenario_id, month)
        assert result['rooms_occupied'] <= result['rooms_available']

def test_revpar_formula():
    """RevPAR = ADR × Occupancy%"""
    result = calculate_revenue(scenario_id, month=1)
    expected_revpar = result['adr'] * result['occupancy_pct']
    assert abs(float(result['revpar'] - expected_revpar)) < 0.01

def test_revenue_recalculates_on_assumption_change():
    """Cambiar occupancy% debe recalcular room revenue automáticamente."""
    original = get_revenue_result(scenario_id, month=3)
    update_occupancy(scenario_id, month=3, occupancy_pct=Decimal('0.80'))
    updated = get_revenue_result(scenario_id, month=3)
    assert updated['ROOMS'] != original['ROOMS']
    assert updated['rooms_occupied'] > original['rooms_occupied']

def test_jan_budget_rooms_reference():
    """Verificar contra datos del archivo original — Enero 2026 Budget."""
    result = calculate_revenue(scenario_id, month=1)
    # Del archivo Budget2026_Revenue_CORCO.xlsx → Summary → Revenue 2026 Budget Enero
    assert abs(float(result['ROOMS']) - 415201.91) < 100   # ±$100 tolerancia
    assert abs(float(result['FOOD'])  - 113356.58) < 100

def test_room_types_total_30_units():
    """CWL siempre tiene 30 unidades en total."""
    configs = get_room_type_configs('CWL')
    assert sum(c.units for c in configs) == 30

def test_room_type_units_exact():
    """Unidades exactas por tipo de habitación."""
    configs = {c.id: c for c in get_room_type_configs('CWL')}
    assert configs[1].units == 6   # Corcovado Deluxe King
    assert configs[2].units == 2   # Carate Double
    assert configs[3].units == 4   # Agujas Queen
    assert configs[4].units == 8   # Sirena Suites
    assert configs[5].units == 5   # Treehouse
    assert configs[6].units == 5   # 5 Elements Treehouse

def test_rooms_available_calculation():
    """Noches disponibles = unidades × días del mes."""
    # Enero 2026 = 31 días
    occ = get_occupancy(scenario_id, month=1)
    for o in occ:
        config = get_room_type_config(o.room_type_id)
        assert o.rooms_available == config.units * 31
    # Total enero: 30 × 31 = 930
    assert sum(o.rooms_available for o in occ) == 930

def test_ytd_may_room_stats_reference():
    """Verificar KPIs YTD Mayo 2026 contra el archivo YTD_Rev_by_Room2026.xlsx."""
    stats = get_ytd_room_stats('CWL', through_month=5, year=2026)
    total = stats['TOTAL']
    assert total['rooms_available']  == 4530
    assert total['rooms_occupied']   == 2843
    assert abs(float(total['occupancy_pct']) - 0.6276) < 0.001
    assert abs(float(total['revenue'])       - 1570875.28) < 100
    assert abs(float(total['adr'])           - 552.54) < 1
    assert total['total_pax']        == 4883

def test_other_rooms_revenue_jan():
    """Other Rooms Revenue enero 2026 = $10,246.62."""
    other = get_other_rooms_revenue('CWL', year=2026, month=1)
    assert abs(float(other) - 10246.62) < 10
```

1. **Multi-escenario:** Una misma propiedad puede tener múltiples escenarios del mismo año y tipo (versiones). El sistema compara siempre escenarios explícitamente seleccionados.

2. **Tipo de cambio — regla fundamental:** El TC es por mes y por escenario. Un salario en CRC se convierte a USD usando el TC del mes en que se paga. Si el TC de enero es 530 y el de julio es 545, el mismo salario CRC tiene diferente valor USD en cada mes.

3. **Moneda por posición, no por departamento:** Dentro del mismo departamento puede haber empleados en CRC (locales) y en USD (expatriados, contratos especiales). El campo `salary_currency` vive en cada posición, no en el departamento.

4. **Cuenta 7380 Miscellaneous:** Aparece en múltiples checkbooks. Al calcular el P&L, siempre filtrar por `dept_code` además de `account_code`.

5. **Octubre 2026 en CWL:** El Revenue Budget tiene Octubre = 0 porque el usuario ingresó occupancy=0% y FTE=0 para ese mes. No es una regla del sistema — si se presupuesta ocupación en octubre, el sistema calcula normalmente. Es la estacionalidad histórica de CWL, no un hardcode.

6. **Planilla Actual vs Budget/Forecast:**
   - **Actual:** se sube desde `Codificacion_Planilla` (QuickBooks) — valores reales ya en CRC/USD
   - **Budget/Forecast:** se construye en el sistema posición por posición con TC por mes

7. **Los checkbooks OPEX tienen datos 2024, 2025 y 2026:** Las filas de GRAN TOTAL superiores son comparativos históricos. Los datos de budget 2026 son los que tienen fechas `2026-01-01` como headers.

8. **Cuentas clase 5 (Cost of Sales):** Solo existen en F&B, Retail y operativos. Nunca en Admin, Maintenance, ni Overhead.

9. **Aguinaldo CR:** Provisión mensual = `SW × (1/12)`. Cuenta 6021. El pago real es en diciembre — para cash flow se refleja en diciembre, no en las provisiones mensuales.

10. **Cesantía (Notice & Severance):** Provisión mensual = `SW × 0.055 / 12`. Cuenta 6026. Es provisión contable, no pago mensual real.

11. **CCSS Patronal total ≈ 26.83%** sobre salario bruto. Cuenta 6020.

12. **Cafetería y Lavandería siempre neto $0:** Si el P&L muestra un balance distinto de cero en estos departamentos, hay un error en el módulo de allocation. Son los únicos dos departamentos con esta restricción.

13. **FTE remoto ≠ FTE presencial para cafetería:** Un empleado puede tener FTE=1.0 en planilla pero `participates=False` en cafetería (porque trabaja remotamente). Estos son conceptos independientes — no mezclarlos.

14. **Kilos de lavandería son datos históricos fijos:** No se calculan — se ingresan manualmente al configurar el escenario. Son constantes dentro del mismo escenario (no varían mes a mes en v1).

15. **Cuenta 4999 — Allocation de salida:** Es la cuenta que cancela el gasto de Cafetería y Lavandería. Siempre debe sumar cero a nivel de hotel. Si el P&L muestra un saldo en 4999, hay un error en el módulo de allocation.

16. **Cuentas 5 nunca van en Rooms, Admin, Sales, Maintenance ni Owners** — solo en departamentos que venden un producto directo (F&B, Retail, Spa, Activities, Transport, Innoceana, Laundry, Cafetería).

---

## 16. REPORTE PARA PROPIETARIOS — YTD SUMMARY

Este es el reporte mensual que se envía a los dueños. Actualmente es el archivo `YTD_APRIL__SUMMARY_2026.xlsx`. El sistema debe generarlo automáticamente desde los datos cargados.

### 16.1 Clasificación de los 22 tabs

**GRUPO A — Generados 100% automático desde datos del sistema:**
| Tab | Qué es | Fuente de datos |
|-----|--------|-----------------|
| `Summary` | KPIs del mes: Occupancy, ADR, RevPAR, Revenue por línea. Mes actual + YTD. Actual vs Budget + varianza | Revenue Results + P&L |
| `Profit&Loss` | P&L completo: Revenue, Payroll, CoS, OpEx, GOP. Mes + YTD. Actual vs Budget + % | P&L engine |
| `Total Revenue` | Detalle de ingresos por departamento. Mes + YTD. Actual vs Budget | Revenue Results |
| `Payroll Expenses` | Planilla por departamento. Mes + YTD. Actual vs Budget | Payroll engine |
| `F&B Cost` | Revenue F&B + Costo F&B + % de costo. Mes + YTD. Actual vs Budget vs Año anterior | Cost engine |
| `Headcounts` | FTE por departamento. Mes actual vs Budget. Incluye mes siguiente | FTE report |
| `Room Stats` | Ocupación, Revenue y ADR por tipo de villa × mes. YTD + mes actual + cada mes del año. Incluye línea "Other Rooms Revenue". Columnas: Units, Noches Disponibles, Noches Ocupadas, Occupancy%, Revenue, ADR, Total Pax | Revenue Results |
| `On the Books` | OTB vs Budget mes a mes para el año completo | Scenario data |
| `12 months Budget 06` | P&L de 12 meses con 2024 actuals + 2025 actuals + 2026 Budget | Históricos + Budget |
| `12 Month Forecast` | P&L de 12 meses mezclando actuals (meses pasados) + forecast (meses futuros) | Actual + Forecast |
| `Simplified P&L YTD` | P&L simplificado YTD con % de Revenue, PAR, POR | P&L engine |
| `Simplified P&LFull Year` | P&L simplificado año completo (Forecast) | P&L engine + Forecast |
| `Cash Flow` | Forecast vs Budget de cash flow mes a mes | Cash flow data |
| `COLON-DOLLAR CHART` | Histórico del tipo de cambio CRC/USD desde 2017 | ExchangeRate master data |

**GRUPO B — Semi-automáticos (datos del sistema + input manual):**
| Tab | Qué es | Manual |
|-----|--------|--------|
| `Ops KPI` | KPIs operativos con Actual, Target, Varianza, Owner, Driver, Action | Target y Actions son manuales |
| `Country` | Reservas por país de origen. YTD mes a mes | Viene de PMS/Integrity — importar |
| `Market set` | Mix de canales (Travel Agent, Direct, Website, OTA). YTD mes a mes | Viene de PMS — importar |
| `Capex` | Tracker de proyectos de capital: Budget, Actual, Committed, Remaining | Se ingresa manual |
| `AP Aging` | Cuentas por pagar por antigüedad (Current, 1-30, 31-60, 61-90, 91+) | Importar desde Integrity |
| `AR Aging` | Cuentas por cobrar por cliente e invoice | Importar desde Integrity |

**GRUPO C — Complementarios (se incluyen pero son más simples):**
| Tab | Qué es |
|-----|--------|
| `Balance Sheet` | Balance general mensual — importar desde Integrity |
| `Additional Data` | Narrativa textual de la gestión del mes — se redacta manualmente (candidato a AI) |

### 16.2 Estructura del reporte — lógica de columnas

La mayoría de los tabs siguen el mismo patrón de columnas:

```
Departamento / Línea | Actual Mes | Budget Mes | Var $ | Var % | YTD Actual | YTD Budget | YTD Var $ | YTD Var %
```

Algunos tabs agregan columna de **año anterior** para comparación de 3 períodos:
```
... | Actual Año Anterior | Var vs Año Anterior $
```

### 16.3 Modelo de datos del reporte

```python
class OwnerReport(Base):
    """
    Metadata del reporte generado. Los datos vienen de los escenarios.
    """
    __tablename__ = 'owner_reports'

    id: UUID
    hotel_id: str
    report_month: int       # mes del reporte (ej: 4 = Abril)
    report_year: int        # año del reporte
    title: str              # 'YTD April 2026 Summary'
    actual_scenario_id: UUID    # escenario ACTUAL cargado
    budget_scenario_id: UUID    # escenario BUDGET
    forecast_scenario_id: UUID  # escenario FORECAST
    prior_year_scenario_id: UUID # actuals año anterior (nullable)
    generated_at: datetime
    generated_by: str
    status: str             # 'draft' | 'sent'


def generate_owner_report(
    hotel_id: str,
    report_month: int,
    report_year: int,
    actual_id: UUID,
    budget_id: UUID,
    forecast_id: UUID
) -> OwnerReport:
    """
    Genera todos los tabs del reporte desde los datos del sistema.
    El orden de generación importa — Summary depende de P&L que depende de Revenue.
    """
    # Los tabs del Grupo A se generan en este orden:
    steps = [
        'revenue_results',    # base para todos
        'pl_summary',         # depende de revenue
        'payroll_summary',    # independiente
        'cost_summary',       # depende de revenue
        'fte_report',         # independiente
        'room_stats',         # depende de revenue
        'simplified_pl',      # depende de pl_summary
        'on_the_books',       # depende de scenarios
        'twelve_month_view',  # depende de históricos + budget
        'twelve_month_fcst',  # depende de actuals + forecast
        'cash_flow',          # depende de scenarios
        'tc_chart',           # depende de exchange_rates
    ]
```

### 16.4 Endpoints del reporte

```
# Generar reporte
POST /api/reports/{hotel_id}/owner/generate/
     body: { month, year, actual_id, budget_id, forecast_id }

# Vistas individuales (para el frontend del sistema)
GET  /api/reports/{hotel_id}/summary/{year}/{month}/
GET  /api/reports/{hotel_id}/pl/{year}/{month}/
GET  /api/reports/{hotel_id}/revenue/{year}/{month}/
GET  /api/reports/{hotel_id}/payroll/{year}/{month}/
GET  /api/reports/{hotel_id}/costs/{year}/{month}/
GET  /api/reports/{hotel_id}/headcount/{year}/{month}/
GET  /api/reports/{hotel_id}/room-stats/{year}/{month}/
GET  /api/reports/{hotel_id}/on-the-books/{year}/{month}/
GET  /api/reports/{hotel_id}/12-month/{year}/{month}/
GET  /api/reports/{hotel_id}/forecast/{year}/
GET  /api/reports/{hotel_id}/cash-flow/{year}/

# Export a Excel (replica el formato del archivo YTD_APRIL)
POST /api/reports/{hotel_id}/owner/export/excel/
     body: { report_id }

# Narrativa (Additional Data) — candidato a AI
POST /api/reports/{hotel_id}/owner/narrative/generate/
     body: { report_id, language: 'en' | 'es' }
```

### 16.5 Tab `Additional Data` — narrativa automática con AI

Este tab contiene texto narrativo en inglés que explica la gestión del mes. Actualmente se redacta manualmente. Es un candidato natural para generación con Claude API:

```python
def generate_narrative(report_id: UUID) -> str:
    """
    Genera la narrativa del reporte usando Claude API.
    Inputs: datos del P&L, varianzas vs budget, KPIs del mes.
    Output: texto en inglés listo para copiar al reporte.
    """
    report_data = get_report_summary(report_id)

    prompt = f"""
    Generate a concise monthly performance narrative for hotel owners.
    Use this data: {report_data}
    Format: bullet points by area (Payroll, Revenue, Costs, GOP).
    Tone: professional, factual, brief explanations of variances.
    Language: English
    """
    # Llama a Claude API (claude-sonnet-4-6)
    # Ver system prompt en anthropic_api_in_artifacts
```

### 16.6 Tests del reporte

```python
def test_summary_tab_totals_match_pl():
    """Los totales del Summary deben coincidir con el P&L."""
    summary = get_summary(report_id)
    pl = get_pl(actual_scenario_id, month=report_month)
    assert abs(float(summary.total_revenue - pl.revenue)) < 1

def test_ytd_is_sum_of_months():
    """YTD = suma de todos los meses desde enero hasta report_month."""
    for line in ['rooms', 'fb', 'payroll', 'gop']:
        ytd = get_ytd(actual_scenario_id, line, through_month=4)
        monthly_sum = sum(
            get_pl(actual_scenario_id, month=m).__getattribute__(line)
            for m in range(1, 5)
        )
        assert abs(float(ytd - monthly_sum)) < 1

def test_variance_formula():
    """Var $ = Actual - Budget. Var % = Var $ / Budget."""
    summary = get_summary(report_id)
    expected_var = summary.actual_revenue - summary.budget_revenue
    expected_pct = expected_var / summary.budget_revenue
    assert abs(float(summary.var_revenue - expected_var)) < 1
    assert abs(float(summary.var_pct_revenue - expected_pct)) < 0.001

def test_april_2026_reference_values():
    """Verificar contra datos del archivo original."""
    summary = get_summary(report_id)  # Abril 2026
    assert abs(float(summary.actual_total_revenue) - 597135.41) < 100
    assert abs(float(summary.budget_total_revenue) - 378005.83) < 100
    assert abs(float(summary.actual_occupancy) - 0.5589) < 0.001
    assert abs(float(summary.actual_adr) - 631.30) < 1
```

---



```bash
# .env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/finplan_cwl
SECRET_KEY=<jwt-secret>
NEXTAUTH_SECRET=<nextauth-secret>
NEXTAUTH_URL=http://localhost:3000
API_URL=http://localhost:8000
DATA_RAW_PATH=./data/raw/
```

---

## 17. ESTRUCTURA DEL P&L — FULL P&L CWL

Este es el reporte P&L mensual que se envía a los propietarios. El sistema debe generarlo automáticamente. La referencia exacta es el archivo `Full_P_L_CWL_YTD_APRIL_2026____Full_Year_Forecast.pdf`.

### 17.1 Columnas del reporte (13 columnas)

```
Grupo 1 — MES ACTUAL:
  Col 1:  Actual mes (ej: April 2026)
  Col 2:  Budget mes
  Col 3:  Variance vs Budget ($)
  Col 4:  Actual mismo mes año anterior (April 2025)

Grupo 2 — YTD (acumulado enero → mes actual):
  Col 5:  YTD Actual (ej: YTD April 2026)
  Col 6:  YTD Budget
  Col 7:  YTD Variance vs Budget ($)
  Col 8:  YTD Actual año anterior (YTD April 2025)

Grupo 3 — FULL YEAR:
  Col 9:  Full Year Forecast 2026
  Col 10: Full Year Budget 2026
  Col 11: Full Year Variance vs Budget ($)
  Col 12: Full Year Actual 2025
  Col 13: Full Year Actual 2024
```

**Varianza siempre = Actual − Budget** (positivo = favorable para ingresos, negativo = desfavorable para gastos)

### 17.2 KPIs de encabezado

Aparecen arriba del P&L, mismas 13 columnas:
```
Total available Rooms
Total Rooms Occupied
Total Guests
% Occupancy
Average Daily Room Only   (ADR)
Total RevPAR
```

### 17.3 Estructura completa del P&L

```
══════════════════════════════════════════════════════════════
REVENUES
  Rooms
  F&B
  SPA
  Tours
  Retail-Gift Shop
  Transportation
  Laundry
  Innoceana
  Sustainability Fee / Others
──────────────────────────────────────────────────────────────
TOTAL REVENUES

══════════════════════════════════════════════════════════════
OPERATING EXPENSES  (por dept = Payroll + CoS + OpEx juntos)
  Rooms
  F&B
  SPA
  Tours
  Retail-Gift Shop
  Transportation
  Laundry
  Innoceana
──────────────────────────────────────────────────────────────
TOTAL OPERATING EXPENSES

══════════════════════════════════════════════════════════════
OPERATING PROFIT  (Revenue dept − Operating Expenses dept)
  Rooms
  F&B
  SPA
  Tours
  Retail-Gift Shop
  Transportation
  Laundry
  Innoceana
  Crowther Lab
  Sustainability Fee / Others
──────────────────────────────────────────────────────────────
TOTAL OPERATING PROFIT

══════════════════════════════════════════════════════════════
OVERHEAD EXPENSES
  Administrations
  Sales & Marketing
  Maintenance
  Information System
  Utilities
──────────────────────────────────────────────────────────────
TOTAL OVERHEAD EXPENSES

══════════════════════════════════════════════════════════════
TOTAL GROSS OPERATING PROFIT (GOP)
  = Operating Profit − Overhead Expenses

══════════════════════════════════════════════════════════════
NON-OPERATING EXPENSES
  Rent
  Management Fees (3%)
  Management Fees (5%) Royalties
  ─────────────────────────────
  Total Rent and Management Fees

  Properties Insurance
  Other Expenses
  ─────────────────────────────
  Total Other Expenses

──────────────────────────────────────────────────────────────
TOTAL NON-OP EXPENSES

══════════════════════════════════════════════════════════════
EBITDA BEFORE CAPITAL
  = GOP − Total Non-Op Expenses

  Capital Reserve
  Large Capital Expenditure
  ─────────────────────────────
  Capital Expense

══════════════════════════════════════════════════════════════
EBITDA AFTER CAPITAL
  = EBITDA Before Capital − Capital Expense

  Bank Interest Charges
  Leasings / Rents
  Financial Losses
  ─────────────────────────────
  Financial Expenses

  Depreciation
  Asset Loss
  ─────────────────────────────
  Total Depreciations

══════════════════════════════════════════════════════════════
EARNINGS BEFORE INCOME TAXES (EBT)
  = EBITDA After Capital − Financial Expenses − Depreciations

INCOME TAXES (30%)

══════════════════════════════════════════════════════════════
NET PROFIT
  = EBT − Income Taxes

══════════════════════════════════════════════════════════════
RESUMEN AL PIE (crosscheck):
  Total Payroll and Benefits
  Total Operating Expenses
  Total Cost of Sales
  Total Property Expenses (Owners)
  Total Profit
```

### 17.4 Regla crítica — Operating Expenses en este P&L

En este reporte las **Operating Expenses por departamento son la suma de Payroll + CoS + OpEx** de ese departamento, NO se muestran separadas. Es una vista consolidada por departamento.

```
Operating Expenses Rooms = Payroll Rooms + CoS Rooms + OpEx Rooms
Operating Expenses F&B   = Payroll F&B   + CoS F&B   + OpEx F&B
...etc
```

El detalle desagregado (Payroll separado de CoS separado de OpEx) vive en los otros tabs del reporte (Payroll Expenses, F&B Cost, etc.).

### 17.5 Líneas que requieren input manual (no vienen del presupuesto)

```
Rent                        → monto fijo mensual — input manual por escenario
Management Fees (3%)        → % editable × Total Revenue del mes (default 3%)
Management Fees (5%)        → % editable × Total Revenue del mes (cuando aplique, default 0%)
Properties Insurance        → monto fijo — input manual
Capital Reserve             → monto mensual — input manual
Large Capital Expenditure   → según proyectos Capex — input manual
Bank Interest Charges       → input manual
Depreciation                → monto mensual fijo — input manual
Income Taxes (30%)          → calculado: 30% del EBT (si EBT > 0)
```

**Management Fees — vista en el UI:**
```
MANAGEMENT FEES
  Base de cálculo:   Total Revenue del mes     $597,135.41   ← read-only, viene del P&L
  Management Fee %:  [ 3.00% ]                              ← editable por el usuario
  Monto calculado:   $17,905.62                             ← automático: Revenue × %
  
  Royalties %:       [ 0.00% ]                              ← editable (cuando aplique)
  Monto calculado:   $0.00                                  ← automático: Revenue × %
  ──────────────────────────────────────────────────────
  Total Mgmt Fees:   $17,905.62
```

**Modelo de datos:**
```python
class PLManualInput(Base):
    __tablename__ = 'pl_manual_inputs'

    id: UUID
    scenario_id: UUID
    month: int

    rent: Decimal                       # monto fijo
    mgmt_fee_pct: Decimal               # % Management Fee (ej: 0.03)
    royalties_pct: Decimal              # % Royalties (ej: 0.05 o 0.00)
    # mgmt_fee_amount = Total Revenue × mgmt_fee_pct   ← CALCULADO, no se guarda
    # royalties_amount = Total Revenue × royalties_pct ← CALCULADO, no se guarda

    properties_insurance: Decimal       # monto fijo
    capital_reserve: Decimal            # monto fijo mensual
    large_capex: Decimal                # según proyectos
    bank_interest: Decimal              # monto fijo
    depreciation: Decimal               # monto fijo mensual
    income_tax_rate: Decimal            # tasa (default 0.30)
```

**Engine:**
```python
# En calculate_full_pl():
total_revenue = get_line(pl, 'TOTAL_REVENUES')

mgmt_fee    = total_revenue * manual.mgmt_fee_pct     # Revenue × % → monto
royalties   = total_revenue * manual.royalties_pct    # Revenue × % → monto
total_mgmt  = mgmt_fee + royalties

total_non_op = manual.rent + total_mgmt + manual.properties_insurance
```

### 17.6 Modelo de datos del P&L

```python
class PLLine(Base):
    """
    Una línea del P&L por escenario × mes.
    Se genera automáticamente al recalcular.
    """
    __tablename__ = 'pl_lines'

    id: UUID
    scenario_id: UUID
    month: int
    year: int
    line_code: str          # 'REV_ROOMS', 'REV_FB', 'OPEXP_ROOMS', 'GOP', 'NET_PROFIT', etc.
    line_name: str          # 'Rooms', 'F&B', 'GOP', 'Net Profit', etc.
    section: str            # 'REVENUE' | 'OPEXP' | 'OP_PROFIT' | 'OVERHEAD' |
                            # 'GOP' | 'NON_OP' | 'EBITDA_CAP' | 'EBITDA_AFTER' |
                            # 'EBT' | 'NET_PROFIT'
    dept_code: str          # null para totales y subtotales
    amount_usd: Decimal
    is_calculated: bool     # True = calculado por engine, False = input manual


class PLManualInput(Base):  # DEFINICIÓN CANÓNICA — usar esta
    """
    Inputs manuales que van al P&L pero no vienen del presupuesto operativo.
    Se ingresan por escenario × mes.
    """
    __tablename__ = 'pl_manual_inputs'

    id: UUID
    scenario_id: UUID
    month: int

    rent: Decimal                   # Rent mensual
    mgmt_fee_pct_3: Decimal         # % para Management Fee (default 3%)
    mgmt_fee_pct_5: Decimal         # % para Royalties (default 0%, cuando aplique)
    properties_insurance: Decimal   # seguro mensual
    capital_reserve: Decimal        # reserva de capital mensual
    large_capex: Decimal            # gastos de capital grandes
    bank_interest: Decimal          # intereses bancarios
    depreciation: Decimal           # depreciación mensual
    income_tax_rate: Decimal        # tasa impuesto (default 30%)
```

### 17.7 Engine del P&L completo

```python
# engine/pl_engine.py

def calculate_full_pl(scenario_id: UUID, month: int) -> list[PLLine]:
    """
    Construye el P&L completo en el orden correcto.
    Requiere que ya estén calculados:
      - Revenue (sección 15)
      - Payroll (sección 12)
      - Cost of Sales (sección 13)
      - OPEX (checkbooks de gastos operativos)
      - Allocations (sección 14)
    """
    rev   = get_revenue_results(scenario_id, month)
    pay   = get_payroll_totals(scenario_id, month)    # por dept
    cos   = get_cost_totals(scenario_id, month)       # por dept
    opex  = get_opex_totals(scenario_id, month)       # por dept
    manual = get_manual_inputs(scenario_id, month)

    # 1. REVENUES
    total_revenue = sum(rev.values())

    # 2. OPERATING EXPENSES por dept (Payroll + CoS + OpEx)
    op_exp = {
        dept: pay.get(dept,0) + cos.get(dept,0) + opex.get(dept,0)
        for dept in ALL_REVENUE_DEPTS
    }
    total_op_exp = sum(op_exp.values())

    # 3. OPERATING PROFIT por dept
    op_profit = {
        dept: rev.get(dept,0) - op_exp.get(dept,0)
        for dept in ALL_REVENUE_DEPTS
    }
    total_op_profit = sum(op_profit.values())

    # 4. OVERHEAD (solo Payroll + OpEx, sin revenue ni CoS)
    overhead = {
        dept: pay.get(dept,0) + opex.get(dept,0)
        for dept in OVERHEAD_DEPTS  # Admin, Sales, Maint, IT, Utilities
    }
    total_overhead = sum(overhead.values())

    # 5. GOP
    gop = total_op_profit - total_overhead

    # 6. NON-OP EXPENSES
    mgmt_fee = total_revenue * (manual.mgmt_fee_pct_3 + manual.mgmt_fee_pct_5)
    total_non_op = manual.rent + mgmt_fee + manual.properties_insurance

    # 7. EBITDA BEFORE CAPITAL
    ebitda_before = gop - total_non_op

    # 8. CAPITAL
    capital_exp = manual.capital_reserve + manual.large_capex
    ebitda_after = ebitda_before - capital_exp

    # 9. FINANCIAL
    financial_exp = manual.bank_interest  # financial losses se agregan si hay
    ebt = ebitda_after - financial_exp - manual.depreciation

    # 10. TAXES & NET PROFIT
    income_tax = max(ebt * manual.income_tax_rate, Decimal('0'))
    net_profit = ebt - income_tax

    return build_pl_lines(locals())  # convierte todo a PLLine objects


REVENUE_DEPTS = [
    'ROOMS', 'FB', 'SPA', 'TOURS', 'RETAIL',
    'TRANSPORT', 'LAUNDRY', 'INNOCEANA', 'SUSTAINABILITY'
]

OVERHEAD_DEPTS = [
    'ADMIN', 'SALES', 'MAINTENANCE', 'IT', 'UTILITIES'
]
```

### 17.8 Vista del P&L en el sistema

El frontend muestra el P&L con las mismas 13 columnas del PDF:

```
                          Mes Actual          YTD                  Full Year
                     Actual  Budget  Var $  Actual  Budget  Var $  Forecast  Budget   Var $  2025   2024
─────────────────────────────────────────────────────────────────────────────────────────────────────────
KPIs
  Rooms Available      900     900    -     3,600   3,600    -     10,020   10,020    -
  Rooms Occupied       503     332   171    2,587   2,276   311     4,613    4,363   250
  Occupancy%         55.9%  36.9% +19pp   71.9%   63.2%  +8.7pp   46.0%   43.5%  +2.5pp
  ADR               $631.3  $635.3  -$4   $607.2  $596.6  $10.6   $595.7  $596.9   -$1.2
  RevPAR            $663.5  $420.0 $243   $846.8  $714.3  $133   $518.1  $486.3   $31.9

REVENUES
  Rooms            319,273 210,917 108,357 1,586,674 1,357,736 228,938 2,763,459 2,604,397  159,062
  F&B              119,211  72,301  46,910   541,210   495,568  45,642   945,775   950,214  -4,439
  SPA                6,088   5,625     463    33,230    22,500  10,730    69,402    62,625   6,777
  Tours             87,645  50,459  37,186   464,224   345,857 118,368   755,903   663,154  92,749
  ...
  TOTAL REVENUES   597,135 378,006 219,130 3,048,622 2,571,379 477,242 5,191,809 4,872,775  319,034

OPERATING EXPENSES
  Rooms             69,790  53,240  16,550   275,407   216,159  59,248   649,392   581,089   68,303
  F&B               85,106  56,695  28,411   346,879   280,159  66,720   722,432   626,096   96,336
  ...

OPERATING PROFIT
  Rooms            249,484 157,677  91,807 1,311,267 1,141,577 169,690 2,114,066 2,023,308   90,758
  ...
  TOTAL OP PROFIT  364,577 211,934 152,643 2,085,125 1,809,985 275,140 3,092,199 3,011,969   80,231

OVERHEAD
  Admin             66,503  61,573   4,931   252,997   241,307  11,690   693,885   682,083   11,803
  ...
  TOTAL OVERHEAD   188,539 182,324   6,215   747,128   716,898  30,230 2,166,287 2,120,882   45,405

GOP              $176,038  $29,610 $146,428 $1,337,997 $1,093,087 $244,910 $925,912 $891,086 $34,826
...
NET PROFIT        $52,031 -$22,340  $74,371  $673,406  $468,944 $204,461    -$992  $13,229 -$14,221
```

### 17.9 Tests del P&L

```python
def test_gop_formula():
    """GOP = Operating Profit - Overhead Expenses."""
    pl = calculate_full_pl(scenario_id, month=4)
    gop = get_line(pl, 'GOP')
    op_profit = get_line(pl, 'TOTAL_OP_PROFIT')
    overhead = get_line(pl, 'TOTAL_OVERHEAD')
    assert abs(float(gop - (op_profit - overhead))) < 1

def test_net_profit_formula():
    """Net Profit = EBT - Income Taxes."""
    pl = calculate_full_pl(scenario_id, month=4)
    ebt = get_line(pl, 'EBT')
    tax = get_line(pl, 'INCOME_TAXES')
    net = get_line(pl, 'NET_PROFIT')
    assert abs(float(net - (ebt - tax))) < 1

def test_mgmt_fee_uses_total_revenue():
    """Management Fee = Total Revenue × % configurado por el usuario."""
    set_manual(scenario_id, month=4, mgmt_fee_pct=Decimal('0.03'))
    pl = calculate_full_pl(scenario_id, month=4)
    total_rev  = get_line(pl, 'TOTAL_REVENUES')   # $597,135.41
    mgmt_fee   = get_line(pl, 'MGMT_FEE')
    assert abs(float(mgmt_fee - total_rev * Decimal('0.03'))) < 1
    # $597,135.41 × 3% = $17,914.06

def test_mgmt_fee_changes_when_revenue_changes():
    """Si cambia el Revenue, el Management Fee se recalcula automáticamente."""
    pl_before = calculate_full_pl(scenario_id, month=4)
    fee_before = get_line(pl_before, 'MGMT_FEE')
    # Cambiar ocupación → sube Revenue → sube Management Fee
    update_occupancy(scenario_id, month=4, pct=Decimal('0.70'))
    recalculate_scenario(scenario_id)
    pl_after = calculate_full_pl(scenario_id, month=4)
    fee_after = get_line(pl_after, 'MGMT_FEE')
    assert fee_after > fee_before  # más revenue = más management fee

def test_income_tax_zero_when_negative_ebt():
    """Income Tax = 0 cuando EBT es negativo — no hay impuesto sobre pérdidas."""
    pl = calculate_full_pl(scenario_id_loss_month, month=10)
    ebt = get_line(pl, 'EBT')
    tax = get_line(pl, 'INCOME_TAXES')
    assert ebt < 0
    assert tax == Decimal('0')

def test_april_2026_reference_values():
    """Verificar contra datos del PDF original."""
    pl = calculate_full_pl(actual_scenario_id, month=4)
    assert abs(float(get_line(pl,'TOTAL_REVENUES'))  - 597135.41) < 100
    assert abs(float(get_line(pl,'GOP'))             - 176037.54) < 100
    assert abs(float(get_line(pl,'EBITDA_BEFORE'))   - 145359.79) < 100
    assert abs(float(get_line(pl,'NET_PROFIT'))      -  52030.76) < 100

def test_operating_exp_is_sum_of_three():
    """Operating Expenses dept = Payroll + CoS + OpEx de ese dept."""
    pl = calculate_full_pl(scenario_id, month=4)
    rooms_opexp = get_dept_line(pl, dept='ROOMS', section='OPEXP')
    rooms_pay   = get_payroll_total(scenario_id, dept='ROOMS', month=4)
    rooms_cos   = get_cost_total(scenario_id, dept='ROOMS', month=4)
    rooms_opex  = get_opex_total(scenario_id, dept='ROOMS', month=4)
    assert abs(float(rooms_opexp - (rooms_pay + rooms_cos + rooms_opex))) < 1

def test_ytd_is_cumulative():
    """YTD April = suma de enero a abril."""
    ytd_rev = get_ytd(actual_scenario_id, 'TOTAL_REVENUES', through_month=4)
    monthly = sum(
        get_line(calculate_full_pl(actual_scenario_id, m), 'TOTAL_REVENUES')
        for m in range(1, 5)
    )
    assert abs(float(ytd_rev - monthly)) < 1
```

---



```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.seed_data     # importa catálogos desde DATA_RAW_PATH
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Importar datos CWL (después de arrancar el backend)
curl -X POST http://localhost:8000/api/import/catalog/
curl -X POST http://localhost:8000/api/import/revenue/ -F "file=@data/raw/Budget2026_Revenue_CORCO.xlsx&scenario_type=BUDGET&year=2026"
# ... etc para cada checkbook
```

---

## 18. CUENTAS ESTADÍSTICAS — CLASE 9

Las cuentas 9xxx son cuentas **no financieras** — registran volúmenes y cantidades, no montos en dinero. Son la fuente de los drivers operativos (noches, covers, pax, kilos, horas) que el sistema usa para calcular KPIs y distribuir costos.

**Origen:** Archivo `Catálogo_al_19_de_Set__V1__enviado__con_stats.xlsx`
**Total cuentas 9xxx:** 9,292
**Estructura:** Mismo formato de 7 segmentos que el resto del catálogo

### 18.1 Grupos de cuentas estadísticas

| Rango | Tipo | Descripción | Dept | Uso en el sistema |
|-------|------|-------------|------|-------------------|
| **9000** | STATS NTs | Noches ocupadas por tipo de habitación × segmento de mercado | 0110 | Room Stats, RevPAR, drivers de costo |
| **9110–9132** | STATS Cust | Covers de F&B por restaurante × servicio (Breakfast, Lunch, Dinner) | 0123–0129 | Revenue per Cover, benchmarks F&B |
| **9201–9216** | STATS Treat | Tratamientos de Spa por tipo (Massage, Body, Facial, Beauty…) | 0140 | Spa revenue per treatment |
| **9400–9403** | STATS Tours | Número de tours y PAX de Activities | 0150 | Activity utilization |
| **9500–9503** | STATS Transport | Número de clientes de transporte | 0152 | Transport utilization |
| **9600–9603** | STATS Innoceana | Número de lecciones y PAX | 0155 | Innoceana utilization |
| **9700–9702** | STATS Kilos | Kilos lavados por departamento (Rooms, F&B, Spa) | 0160 | **Base para allocation de Lavandería** |
| **9980–9985** | STATS Horas | Horas regulares, extras, libres, feriados, vacaciones por posición | todos | Control de planilla vs Budget |

### 18.2 Detalle 9000 — Noches por segmento de mercado

```
Segmentos (Nivel3):
  001 = Retail Transient       (tarifa rack)
  002 = Discount Transient
  003 = Negotiated Transient
  004 = Qualified Transient
  005 = Wholesale Transient    → Travel Agencies
  006 = Corporate Transient
  007 = Association Transient
  008 = Government Transient
  009 = Tour/Wholesale         → OTAs y mayoristas
  010 = No Show
  012 = Accommodation Pets
  014 = Day Use
  017 = House Use              → uso interno, no genera revenue
```

**Uso:** Al importar actuals de Integrity, estas cuentas dan las noches reales por tipo de villa y segmento. Son la fuente de occupancy%, ADR y RevPAR reales.

### 18.3 Detalle 9700–9702 — Kilos Lavandería

```
9700 = Kilos Washed Rooms   (dept 0160)
9701 = Kilos Washed F&B     (dept 0160)
9702 = Kilos Washed SPA     (dept 0160)
```

**Uso crítico:** Son los datos reales que alimentan `LaundryAllocationConfig.kilos_historicos`. Al importar actuals, se actualizan los kilos por departamento para que el allocation del siguiente presupuesto use datos reales.

### 18.4 Detalle 9980–9985 — Horas de planilla

```
9980 = Horas Regulares         → por posición × dept
9981 = Horas Extras
9982 = Horas Libres
9983 = Horas Feriados Lab.
9984 = Horas Provisión Vac.
9985 = Horas Vacaciones Tomadas
```

**Uso:** FTE real = horas regulares del mes / horas disponibles del mes. Permite el comparativo Budget FTE vs Actual FTE en el reporte de headcount.

### 18.5 Modelo de datos

```python
class StatisticalEntry(Base):
    """
    Valores de cuentas 9xxx importados desde Integrity.
    Son cantidades/volúmenes — NO montos en dinero.
    """
    __tablename__ = 'statistical_entries'

    id: UUID
    hotel_id: str
    year: int
    month: int
    account_code_full: str  # '9000-0110-001-001-001-01-01'
    stat_group: str         # '9000' | '9700' | '9980' | etc.
    dept_code: str          # seg2
    concept_code: str       # seg3 (segmento, tipo de servicio, posición)
    description: str
    value: Decimal          # cantidad — NO dinero
    unit: str               # 'nights' | 'covers' | 'kilos' | 'hours' | 'pax'

class StatisticalSummary(Base):
    """Resumen mensual de stats clave — calculado al importar."""
    __tablename__ = 'statistical_summaries'

    id: UUID
    hotel_id: str
    year: int
    month: int

    # Rooms (9000) — noches por tipo de villa
    rooms_occupied_total: Decimal
    rooms_occupied_by_type: dict    # {room_type_id: noches}
    rooms_by_segment: dict          # {'001': noches, '005': noches, ...}

    # F&B (9110-9132) — covers por servicio
    fb_covers_breakfast: Decimal
    fb_covers_lunch: Decimal
    fb_covers_dinner: Decimal
    fb_covers_total: Decimal

    # Kilos lavandería (9700-9702)
    kilos_rooms: Decimal
    kilos_fb: Decimal
    kilos_spa: Decimal
    kilos_total: Decimal            # → alimenta LaundryAllocationConfig

    # Horas planilla (9980-9985)
    hours_regular: Decimal
    hours_overtime: Decimal
    hours_vacation: Decimal
```

### 18.6 Cómo conectan con el resto del sistema

```
9000 Noches por segmento
  → Occupancy%, ADR, RevPAR reales (KPIs del reporte de propietarios)
  → Driver OCC_ROOMS en checkbook de costos (actuals)

9700-9702 Kilos lavados
  → LaundryAllocationConfig.kilos_historicos
  → Motor de allocation de lavandería (base de distribución)

9110-9132 Covers F&B
  → Revenue per Cover (KPI de eficiencia F&B)
  → Benchmarks del restaurante para el presupuesto siguiente

9980-9985 Horas
  → FTE real = horas_regulares / horas_disponibles_mes
  → Reporte FTE: columna Actual vs Budget
```

---

## 19. CLASE 7 — OPEX CHECKBOOKS (GASTOS OPERATIVOS)

### 19.1 Concepto general

La clase 7 son los **gastos operativos** de cada departamento — todo lo que no es planilla (6xxx) ni costo de ventas (5xxx). Hay más de 100 tipos de cuentas 7xxx en el catálogo pero cada departamento solo usa un subconjunto específico definido en su checkbook.

**Total cuentas 7xxx en catálogo:** 3,607 (incluyendo todos los departamentos)
**Tipo contable:** Gasto operativo — siempre suman positivo al gasto en el P&L

### 19.2 Estructura del checkbook OPEX

Basado en los archivos `OPEXC_2026__[DEPT]__BUDGET.xlsx`. Cada checkbook tiene:

```
Columnas:
  # Cuenta     → código 7xxx (ej: 7065)
  Descripción  → nombre de la cuenta (ej: CLEANING SUPPLIES)
  Departamento → código dept (ej: 0120)
  Detalle      → subcuenta numérica (800, 801, 802...) — línea específica del gasto
  Detalle Desc → descripción del ítem específico (ej: "Vajilla para hotel")
  2024 Ene–Dic → histórico real 2024 (read-only, referencia)
  2025 Ene–Dic → histórico real 2025 (read-only, referencia)
  2026 Ene–Dic → INPUT MANUAL — el usuario ingresa el presupuesto

Filas subtotal por cuenta:
  Por cada cuenta 7xxx hay múltiples líneas de detalle (subcuentas 800–810)
  El usuario puede ingresar en cualquier línea de detalle
  El sistema suma todas las líneas de detalle de la misma cuenta
```

**Lógica de detalle (subcuentas):**
- Cada cuenta 7xxx puede tener hasta 11 líneas de detalle (800 a 810)
- El usuario describe en texto qué es cada línea (ej: "Alquiler de mesas para eventos")
- Permite desglosar el gasto dentro de una misma cuenta contable
- En el P&L solo se ve el total de la cuenta — el detalle es solo para el checkbook

### 19.3 Cuentas 7xxx por departamento

Cada departamento tiene su propio conjunto de cuentas relevantes:

| Dept | Nombre | Cuentas 7xxx clave |
|------|--------|-------------------|
| 0110 Rooms | ROOMS | 7065 Cleaning, 7100 Comp Services, 7105 Contract, 7250 Guest Supplies, 7350 Linen, 7680 Uniforms |
| 0120 F&B | F&B | 7025 Banquet, 7060 China, 7065 Cleaning, 7140 Dishwashing, 7195 Flatware, 7235 Glassware, 7300 Kitchen SW, 7350 Linen |
| 0130 SPA | SPA | 7005 Ambience, 7010 Athletic, 7065 Cleaning, 7260 Health Beauty, 7310 Laundry, 7350 Linen |
| 0150 Tours | ACTIVITIES | 7065 Cleaning, 7100 Comp, 7105 Contract, 7185 Equipment Rental |
| 0152 Transport | TRANSPORT | 7065 Cleaning, 7080 Commissions, 7105 Contract, 7700 Vehicle Repair |
| 0181 Admin | ADMIN | 7015 Audit, 7020 Bank Charges, 7050 Centralized Acctg, 7115 Credit, 7120 Credit Cards, 7325 Legal, 7465 Payroll Proc |
| 0190 Sales | SALES | 7000 Agency Fees, 7075 Collateral, 7135 Direct Mail, 7190 Fam Trips, 7500 Promotion, 7660 Trade Shows, 7715 Website |
| 0200 Maint | MAINTENANCE | 7030 Building, 7155 Electrical, 7165 Elevators, 7170 Engineering, 7240 Grounds, 7480 Plumbing, 7700 Vehicle |
| 0230 IT | IT | 7560–7640 System Expenses (todos los IT), 7380 Misc, 7400 Operating Supplies |
| Utilities | UTILITIES | 7160 Electricity, 7230 Gas, 7710 Water/Sewer, 7055 Chilled Water, 7395 Oil |

### 19.4 Modelo de datos OPEX

```python
class OpexEntry(Base):
    """
    Línea del checkbook OPEX. Una fila por cuenta × detalle × mes.
    El usuario ingresa los montos directamente — no hay drivers automáticos.
    Todo OPEX es MANUAL (a diferencia del CoS que puede tener drivers).
    """
    __tablename__ = 'opex_entries'

    id: UUID
    scenario_id: UUID
    hotel_id: str
    dept_code: str          # '0120', '0181', '0200', etc.
    account_code: str       # '7065', '7105', '7350', etc.
    account_name: str       # 'CLEANING SUPPLIES', 'CONTRACT SERVICES', etc.
    detail_code: str        # '800'–'810' — subcuenta descriptiva
    detail_description: str # texto libre: "Vajilla para hotel"

    # Montos presupuestados por mes (USD) — INPUT MANUAL
    jan: Decimal; feb: Decimal; mar: Decimal; apr: Decimal
    may: Decimal; jun: Decimal; jul: Decimal; aug: Decimal
    sep: Decimal; oct: Decimal; nov: Decimal; dec: Decimal

    # Históricos (read-only — importados)
    jan_2024: Decimal; feb_2024: Decimal  # ... etc
    jan_2025: Decimal; feb_2025: Decimal  # ... etc


class OpexAccountTotal(Base):
    """
    Total por cuenta 7xxx × dept × mes — calculado sumando todos los detalles.
    Esta es la cifra que va al P&L.
    """
    __tablename__ = 'opex_account_totals'

    id: UUID
    scenario_id: UUID
    dept_code: str
    account_code: str       # '7065'
    account_name: str
    month: int
    amount_usd: Decimal     # suma de todos los detail_codes de esta cuenta
```

### 19.5 Vista del checkbook OPEX en el UI

```
CHECKBOOK OPEX — F&B (Dept 0120) — Budget 2026

Cuenta  | Descripción          | Det | Descripción Detalle              | 2024   | 2025   | Ene    | Feb    | ... | Total
────────┼──────────────────────┼─────┼──────────────────────────────────┼────────┼────────┼────────┼────────┼─────┼──────
7025    | Banquet Expenses     | 800 | Alquiler mesas y equipos eventos | $1,054 |   $235 | [   0] | [   0] | ... |    $0
        |                      | 801 | Alquiler carpa fiestas           |      0 |      0 | [   0] | [   0] | ... |    $0
        |                      | 802 |                                  |      0 |      0 | [   0] | [   0] | ... |    $0
        |   SUBTOTAL 7025      |     |                                  | $1,054 |   $235 |     $0 |     $0 | ... |    $0
────────┼──────────────────────┼─────┼──────────────────────────────────┼────────┼────────┼────────┼────────┼─────┼──────
7060    | China                | 800 | Vajilla para hotel               |   $446 |   $478 | [   0] | [ 500] | ... |  $500
        |                      | 801 |                                  |      0 |      0 | [   0] | [   0] | ... |    $0
        |   SUBTOTAL 7060      |     |                                  |   $446 |   $478 |     $0 |   $500 | ... |  $500
────────┼──────────────────────┼─────┼──────────────────────────────────┼────────┼────────┼────────┼────────┼─────┼──────
7065    | Cleaning Supplies    | 800 | Detergentes y químicos limpieza  | $1,053 | $1,398 | [ 450] | [ 450] | ... | $5,400
        |                      | 801 | Utensilios de limpieza           |   $250 |   $300 | [ 100] | [ 100] | ... | $1,200
        |   SUBTOTAL 7065      |     |                                  | $1,303 | $1,698 |   $550 |   $550 | ... | $6,600
────────┼──────────────────────┼─────┼──────────────────────────────────┼────────┼────────┼────────┼────────┼─────┼──────
...
────────┴──────────────────────┴─────┴──────────────────────────────────┴────────┴────────┴────────┴────────┴─────┴──────
TOTAL OPEX F&B                                                          $10,911 | $5,360 | $X,XXX | $X,XXX | ... | $XX,XXX
```

**Reglas del UI:**
- Los campos `[  ]` son editables — el usuario ingresa el monto en USD directamente
- Las columnas 2024 y 2025 son read-only — referencia histórica
- Octubre: en CWL 2026 el presupuesto es $0 porque FTE=0 y occupancy=0 — pero el campo es editable. Si el usuario ingresa valores, el sistema los usa normalmente.
- El total de la cuenta se calcula sumando todos los detalles de esa cuenta
- El total del dept se calcula sumando todos los totales de cuenta del dept

### 19.6 Importador de checkbooks OPEX

```python
# importers/opex_importer.py

OPEX_FILES = {
    '0110': 'OPEXCR_2026___ROOMS__BUDGET.xlsx',
    '0120': 'OPEXC_2026__F_B__BUDGET.xlsx',
    '0130': 'OPEXC_2026__SPA__BUDGET.xlsx',
    '0150': 'OPEXC_2026__ACT__BUDGET.xlsx',
    '0152': 'OPEXC_2026__TRANSP__BUDGET.xlsx',
    '0155': 'OPEXC_2026__INNO__BUDGET.xlsx',
    '0160': 'OPEXC_2025__LAUND__BUDGET.xlsx',
    '0181': 'OPEXC__2026__ADMIN__BUDGET.xlsx',
    '0190': 'OPEXC__2026__SALES__BUDGET.xlsx',
    '0200': 'OPEXC_2026__MAINT__BUDGET_FINAL.xlsx',
    '0220': 'OPEXC_2026__CAF__BUD.xlsx',
    '0230': 'OPEXC__2026__IT__BUDGET.xlsx',
    'OWN':  'OPEXC__2026__OWN__BUDGET.xlsx',
    'UTL':  'OPEXC__2026__UTILITY__BUDGET.xlsx',
    'CROW': 'OPEXC_2026__CROW__BUDGET.xlsx',
    'BOSQ': 'OPEXC_2026__C_BOSQ__BUDGET.xlsx',
    'RTAIL':'OPEXC_2026__RETAIL__BUDGET.xlsx',
}

def import_opex_checkbook(
    path: str,
    dept_code: str,
    scenario_id: UUID
) -> list[OpexEntry]:
    """
    Importa un checkbook OPEX desde Excel.

    ESTRUCTURA DEL ARCHIVO:
    - Header en fila 11 (0-indexed): # Cuenta | Descripcion | Dept | Detalle | Desc | 2025-01 | ...
    - Filas de datos: cuentas 7xxx con sus líneas de detalle
    - Filas de subtotal: cuando col[1] empieza con NaN y col[4] es NaN → es subtotal, ignorar
    - Columnas de año: detectar dinámicamente por fecha en el header

    REGLA: Solo importar filas donde col[0] (# Cuenta) es un número 7xxx válido
    """
    df = pd.read_excel(path, header=None)
    header_row = find_header_row(df, marker='# Cuenta')
    df.columns = df.iloc[header_row]
    df = df.iloc[header_row+1:]

    entries = []
    for _, row in df.iterrows():
        account = str(row.get('# Cuenta', '')).strip()
        if not (account.startswith('7') and len(account) == 4):
            continue  # ignorar subtotales y filas vacías
        entries.append(OpexEntry(
            scenario_id=scenario_id,
            dept_code=dept_code,
            account_code=account,
            account_name=str(row.get('Descripcion de Cuenta', '')).strip(),
            detail_code=str(row.get('Detalle', '800')).strip(),
            detail_description=str(row.get('Detalle Descripción', '')).strip(),
            jan=safe_decimal(row, '2026-01'),
            feb=safe_decimal(row, '2026-02'),
            # ... etc
        ))
    return entries
```

### 19.7 Endpoints OPEX

```
GET  /api/opex/{scenario_id}/depts/                     depts con checkbook OPEX
GET  /api/opex/{scenario_id}/dept/{dept_code}/          checkbook completo
GET  /api/opex/{scenario_id}/dept/{dept_code}/accounts/ cuentas 7xxx del dept
PUT  /api/opex/{scenario_id}/entry/{id}/                actualizar monto(s) de una línea
GET  /api/opex/{scenario_id}/dept/{dept_code}/total/    total OPEX del dept × mes
GET  /api/opex/{scenario_id}/summary/                   todos los depts × 12 meses
POST /api/opex/{scenario_id}/import/                    importar desde Excel
```

### 19.8 Cuentas 7xxx globales — presentes en casi todos los departamentos

Estas cuentas aparecen en la mayoría de checkbooks — Claude Code debe reconocerlas:

```
7065  CLEANING SUPPLIES          → limpieza general, casi todo dept operativo
7070  CLUSTER SERVICES           → servicios compartidos corporativos
7100  COMPLIMENTARY SERVICES     → servicios de cortesía
7105  CONTRACT SERVICES          → servicios externos contratados
7110  CORPORATE OFFICE REIMB.    → gastos corporativos a reembolsar
7125  DECORATIONS                → decoración y ambientación
7150  DUES AND SUBSCRIPTIONS     → cuotas y suscripciones
7175  ENTERTAINMENT IN-HOUSE     → entretenimiento dentro del hotel
7185  EQUIPMENT RENTAL           → alquiler de equipos
7380  MISCELLANEOUS              → varios (usar con criterio)
7400  OPERATING SUPPLIES         → suministros operativos generales
7665  TRAINING                   → capacitación del personal
7670  TRAVEL MEALS               → viajes y alimentación de trabajo
7675  TRAVEL OTHER               → otros gastos de viaje
7680  UNIFORM COSTS              → costos de uniformes
7685  UNIFORM LAUNDRY            → lavado de uniformes
```

## 20. LÓGICA DE ESCENARIOS — BUDGET Y FORECAST

### 20.1 Los tres tipos de escenario

```python
class ScenarioType(str, Enum):
    BUDGET   = 'BUDGET'    # Meta original del año — se congela al aprobar
    FORECAST = 'FORECAST'  # Budget dinámico — se actualiza durante el año
    ACTUAL   = 'ACTUAL'    # Datos reales importados — nunca se editan
```

### 20.2 Budget — congelado para siempre

El Budget se construye antes de que empiece el año. Una vez aprobado:
- Se marca como `locked = True` — ningún campo es editable
- Nunca se modifica — es la referencia permanente para varianzas todo el año
- El sistema bloquea cualquier intento de edición de un Budget locked

### 20.3 Forecast — budget dinámico con versiones mensuales

El Forecast nace como **copia exacta del Budget**. A partir de ahí el usuario ajusta lo que cambia en el mercado (salarios, headcounts, tarifas, ocupación).

**Ciclo de vida:**
```
Al aprobar Budget    → Forecast v1: todos los meses proyectados (= copia Budget)
Al cerrar enero      → Forecast v2: Ene=actual, Feb-Dic=proyección ajustable
Al cerrar febrero    → Forecast v3: Ene-Feb=actuals, Mar-Dic=proyección ajustable
...hasta diciembre.
```

Resultado: hasta **12 versiones de Forecast** por año, una por mes cerrado.

### 20.4 Cómo se construye el Forecast internamente

El Forecast es un **escenario independiente** con sus propias tablas. Al crear una nueva versión:

```python
def create_forecast_version(
    hotel_id: str,
    year: int,
    through_month: int,          # actuals hasta este mes (ej: 4 = cierre abril)
    actual_scenario_id: UUID,    # actuals cargados en el sistema
    prev_forecast_id: UUID,      # forecast anterior (o Budget si es la primera vez)
) -> Scenario:
    for month in range(1, 13):
        if month <= through_month:
            # Mes cerrado → copiar de actuals, bloquear edición
            copy_month(source=actual_scenario_id, target=new_forecast, month=month, locked=True)
        else:
            # Mes futuro → copiar de forecast anterior, dejar editable
            copy_month(source=prev_forecast_id, target=new_forecast, month=month, locked=False)
```

### 20.5 Qué puede editar el usuario en el Forecast

El Forecast tiene el **mismo formato de entrada que el Budget** — mismos checkbooks, mismas pantallas. La diferencia: los meses con actuals están bloqueados.

```
FORECAST MAR 2026 — Checkbook Planilla

                  ENE (locked actual)  FEB (locked actual)  MAR (editable)  ABR (editable)
Capitán Barco         $1,226               $1,226             [ 1,350 ]       [ 1,350 ]
```

El usuario puede cambiar en meses futuros: salarios, FTE, tarifas, ocupación, canales, OPEX, inputs del P&L.
No puede cambiar: meses locked (actuals) ni el Budget original.

### 20.6 Modelo de datos de escenario

```python
class Scenario(Base):  # DEFINICIÓN CANÓNICA completa — ver sección 5.3 y 20.6
    __tablename__ = 'scenarios'

    id: UUID
    hotel_id: str
    year: int
    scenario_type: str          # 'BUDGET' | 'FORECAST' | 'ACTUAL'
    version_name: str           # 'Budget 2026' | 'Forecast Feb 2026'
    locked: bool                # True = no editable (Budget siempre True al aprobar)
    locked_at: datetime
    parent_scenario_id: UUID    # Forecast apunta al Budget del que fue copiado
    forecast_through_month: int # para FORECAST: último mes con actuals (0 si es v1)
    is_current_forecast: bool   # True = versión activa más reciente
    created_at: datetime
    created_by: str
    notes: str
```

### 20.7 Versiones de Forecast — tabla de control

| Versión | Nombre | Actuals | Proyectados | Se crea al |
|---------|--------|---------|-------------|------------|
| v1 | Forecast Ene 2026 | — | Ene–Dic | Aprobar Budget |
| v2 | Forecast Feb 2026 | Ene | Feb–Dic | Cerrar enero |
| v3 | Forecast Mar 2026 | Ene–Feb | Mar–Dic | Cerrar febrero |
| v4 | Forecast Abr 2026 | Ene–Mar | Abr–Dic | Cerrar marzo |
| v12 | Forecast Dic 2026 | Ene–Nov | Dic | Cerrar noviembre |

### 20.8 Recálculo en el Forecast

Mismo botón "Recalcular" que el Budget. Solo recalcula los meses futuros (no locked). Los meses de actuals se preservan intactos siempre.

### 20.9 Endpoints de Forecast

```
GET  /api/forecast/{hotel_id}/{year}/versions/      lista de versiones
GET  /api/forecast/{hotel_id}/{year}/current/       versión activa
POST /api/forecast/{hotel_id}/{year}/create/        crear nueva versión
     body: { through_month, actual_scenario_id }
POST /api/scenarios/{forecast_id}/recalculate/      recalcular meses futuros
GET  /api/forecast/{hotel_id}/{year}/compare/       Budget vs Forecast vs Actual
```

---

## 21. GLOSARIO DE CÓDIGOS — REFERENCIA RÁPIDA

Esta sección es la tabla de referencia para Claude Code. Ante cualquier duda sobre un código, consultar aquí primero.

### 21.1 Clases de cuenta (seg1 — primer segmento)

| Clase | Tipo contable | Descripción | Cuentas |
|-------|--------------|-------------|---------|
| **4xxx** | Ingreso (I) | Revenues — ingresos por departamento | 13,333 |
| **5xxx** | Costo (T) | Cost of Sales — costo directo de lo vendido | 106 |
| **6xxx** | Planilla (G) | Salaries & Benefits — nómina completa | 14,062 |
| **7xxx** | OPEX | Operating Expenses — gastos operativos | 3,607 |
| **8xxx** | Owners | Owner Expenses — gastos del propietario | 161 |
| **9xxx** | Estadística | Stats — volúmenes y cantidades (no dinero) | 9,292 |

### 21.2 Departamentos (seg2 — segundo segmento)

**Departamentos operativos con ingreso (tienen cuentas 4xxx):**

| Código | Nombre en sistema | Área USALI |
|--------|------------------|------------|
| **0110** | ROOMS | Rooms |
| **0120** | F&B (consolidado) | Food & Beverage |
| **0123** | Restaurant Vitrales | Food & Beverage |
| **0124** | Restaurant Sueño del Bosque | Food & Beverage |
| **0125** | F&B Pool | Food & Beverage |
| **0126** | F&B Beach | Food & Beverage |
| **0127** | Room Service | Food & Beverage |
| **0128** | Private Bar | Food & Beverage |
| **0129** | Events F&B | Food & Beverage |
| **0140** | SPA | Spa |
| **0150** | Activities / Tours | Activities |
| **0151** | Retail / Gift Shop | Retail |
| **0152** | Transportation | Transportation |
| **0155** | Innoceana | Other operated |
| **0160** | Laundry (externo) | Other operated |
| **0170** | Miscellaneous Income | Other |

**Departamentos de planilla dentro de Rooms:**

| Código | Nombre |
|--------|--------|
| **0111** | Front Desk |
| **0112** | Reservations |
| **0113** | Housekeeping |
| **0114** | Concierge / Guest Services |

**Departamentos de planilla dentro de F&B:**

| Código | Nombre |
|--------|--------|
| **0121** | F&B Management (ADM F&B) |
| **0122** | Kitchen |
| **0131** | Spa Management |
| **0132** | Spa Therapists |
| **0133** | Spa Front Desk |

**Departamentos Overhead (sin ingreso, solo gastos):**

| Código | Nombre | Área USALI |
|--------|--------|------------|
| **0180** | Admin general | Admin & General |
| **0181** | General Management | Admin & General |
| **0182** | Finance / Accounting | Admin & General |
| **0183** | Purchasing | Admin & General |
| **0184** | Human Resources | Admin & General |
| **0186** | Security | Admin & General |
| **0190** | Sales & Marketing | Sales & Marketing |
| **0191** | S&M Complimentary | Sales & Marketing |
| **0200** | Maintenance | Property Operation |
| **0205** | Utilities (sub-Maint) | Property Operation |
| **0210** | Chilled Water | Property Operation |
| **0230** | IT / Information Systems | IT |
| **0240** | Rent | Non-operating |

**Departamentos de soporte — siempre neto $0 (allocation):**

| Código | Nombre | Mecanismo |
|--------|--------|-----------|
| **0220** | Cafetería Empleados | Allocation por FTE |
| **0161** | Lavandería (allocation) | Allocation por kilos |
| **0156** | Crowther Lab | Sin allocation definido |

### 21.3 Conceptos de planilla (seg1 = 6xxx)

| Cuenta | Nombre | Tipo | Cálculo |
|--------|--------|------|---------|
| **6000** | Salaries and Wages | Devengado | `salary × FTE / TC` (CRC) o `× FTE` (USD) |
| **6001** | Overtime | Devengado | **MANUAL** |
| **6002** | Days Off Lab | Devengado | **MANUAL** |
| **6003** | Worked Holidays | Devengado | **MANUAL** |
| **6004** | Disabilities | Devengado | **MANUAL** |
| **6010** | Commissions | Devengado | **MANUAL** |
| **6020** | CCSS (Carga Patronal) | Patronal | **AUTO:** BASE × 26.83% |
| **6021** | 13th Salary (Aguinaldo) | Provisión | **AUTO:** BASE ÷ 12 |
| **6022** | Occupational Hazards (INS) | Patronal | **MANUAL** |
| **6023** | Provision Vacations | Provisión | **MANUAL** |
| **6024** | Vacation Taken | Devengado | **MANUAL** |
| **6025** | Cafeteria | Beneficio | **MANUAL** |
| **6026** | Notice and Severance | Provisión | **MANUAL** |
| **6027** | Incentive Bonus | Variable | **MANUAL** |
| **6028** | Housing Benefit | Beneficio | **MANUAL** |
| **6029** | Transportation | Beneficio | **MANUAL** |
| **6030** | Other Benefits | Beneficio | **MANUAL** |

**BASE para 6020 y 6021 = 6000 + 6001 + 6002 + 6003 + 6010 + 6024 + 6027**

### 21.4 Líneas de ingreso (seg1 = 4xxx)

| Cuenta | Descripción | Departamento |
|--------|-------------|--------------|
| **4000** | Rooms Revenue | 0110 |
| **4110** | F&B Food Revenue | 0120–0129 |
| **4120** | F&B NA Beverage Revenue | 0120–0129 |
| **4125** | F&B Beer Revenue | 0120–0129 |
| **4130** | F&B Liquors Revenue | 0120–0129 |
| **4131** | F&B Wine Revenue | 0120–0129 |
| **4132** | F&B Misc Revenue | 0120–0129 |
| **4201–4216** | Spa Services Revenue | 0140 |
| **4250–4258** | Spa Retail Revenue | 0140 |
| **4301–4321** | Retail Gift Shop Revenue | 0151 |
| **4400–4403** | Activities Revenue | 0150 |
| **4500–4503** | Transportation Revenue | 0152 |
| **4600–4603** | Innoceana Revenue | 0155 |
| **4700–4702** | Laundry Revenue | 0160–0161 |
| **4800–4890** | Miscellaneous Income | varios |
| **4880** | Sustainability Fee | 0170 |
| **4999** | Expense Distribution (Allocation) | 0220 — siempre = $0 neto |

### 21.5 Cost of Sales (seg1 = 5xxx)

| Cuenta | Descripción | Departamento |
|--------|-------------|--------------|
| **5101** | Food Cost | 0120 |
| **5102** | Bar to Food Cost | 0120 |
| **5103** | Freight on Food | 0120 |
| **5150** | Beverage Cost | 0120 |
| **5151** | Liquor Cost | 0120 |
| **5152** | Wine Cost | 0120 |
| **5153** | Beer Cost | 0120 |
| **5154** | Other Costs | 0120 |
| **5161–5165** | F&B Misc Cost | 0120 |
| **5201–5223** | Retail Store Costs | 0151 |
| **5300–5301** | Spa Retail Costs | 0140 |
| **5350–5351** | Activity Costs | 0150 |
| **5360–5363** | Transportation Costs | 0152 |
| **5380–5383** | Innoceana Costs | 0155 |
| **5400–5404** | IT/Telecom Costs | 0230 |
| **5420–5421** | Cost of Food Cafetería | 0220 |
| **5501** | Laundry Costs | 0160 |

### 21.6 Owners Expenses (seg1 = 8xxx)

| Cuenta | Descripción | En el P&L |
|--------|-------------|-----------|
| **8000** | Rent | Non-Op Expenses |
| **8005** | Owners Fees / Management Fees | Non-Op Expenses |
| **8010** | Municipal Patents/Licenses | Non-Op Expenses |
| **8015** | Property Insurance | Non-Op Expenses |
| **8020** | Expense Reserves / Capital Reserve | Capital Expense |
| **8030** | Bank and Commission Charges | Financial Expenses |
| **8035** | Interest on Loans | Financial Expenses |
| **8040** | Depreciation | Depreciations |
| **8045** | Exchange Gain/Losses | Financial Expenses |
| **8060** | Income Tax Expenditure | Income Taxes |

### 21.7 Cuentas estadísticas clave (seg1 = 9xxx)

| Cuenta | Descripción | Unidad | Uso |
|--------|-------------|--------|-----|
| **9000** | Noches ocupadas por segmento | Noches | Occupancy%, ADR, RevPAR |
| **9110–9132** | Covers F&B por servicio | Covers | Revenue per Cover |
| **9201–9216** | Tratamientos Spa | Tratamientos | Spa utilization |
| **9400–9403** | Tours y PAX | Unidades | Activity utilization |
| **9700** | Kilos lavados Rooms | Kilos | Allocation Lavandería |
| **9701** | Kilos lavados F&B | Kilos | Allocation Lavandería |
| **9702** | Kilos lavados Spa | Kilos | Allocation Lavandería |
| **9980–9985** | Horas de planilla | Horas | FTE real vs Budget |

### 21.8 Tipos de villa CWL (room_type_id)

| ID | Nombre | Unidades |
|----|--------|----------|
| **1** | Corcovado Deluxe Villas, King bed | 6 |
| **2** | Carate Deluxe Villa Double Beds | 2 |
| **3** | Agujas Villa 2 Queen Beds | 4 |
| **4** | Sirena Suites, Queen Bed (connecting) | 8 |
| **5** | Treehouse king bed | 5 |
| **6** | 5 Elements Treehouse king bed | 5 |
| **0** | Other Rooms Revenue | — (sin noches) |
| — | **TOTAL** | **30** |

### 21.9 Canales de venta CWL (Budget 2026)

| Canal | % Ventas | % Comisión |
|-------|----------|------------|
| Travel Agency | 60% | 28% |
| OTAs | 5% | 20% |
| Direct | 35% | 0% |
| **Comisión neta ponderada** | — | **17.8%** |

### 21.10 Reglas de negocio críticas — resumen rápido

```
1. FTE: 0.00 a 1.00 por posición por mes. Nunca > 1.00.
2. SW = salary_amount × FTE / TC_mes  (CRC)
   SW = salary_amount × FTE           (USD)
3. BASE_CCSS = 6000+6001+6002+6003+6010+6024+6027
4. 6020 = BASE × 26.83%   → AUTOMÁTICO, no editable
5. 6021 = BASE / 12       → AUTOMÁTICO, no editable
6. Octubre en CWL 2026 = occupancy=0%, FTE=0 → revenue=$0, costos=$0
   NO es una regla del sistema — es el input del usuario para ese mes
   Si se cambia a occupancy>0 o FTE>0 → el sistema calcula normalmente
7. Cafetería (0220) neto = $0 → allocation por FTE de depts presenciales
8. Lavandería (0160) neto = $0 → allocation por kilos históricos (9700-9702)
9. 4999 = cuenta de allocation saliente → siempre $0 a nivel hotel
10. Management Fee = Total Revenue × % editable (default 3%)
11. Budget = locked para siempre al aprobar
12. Forecast = meses pasados (actuals locked) + meses futuros (editables)
13. Cuentas 5xxx: NUNCA en Rooms, Admin, Sales, Maintenance, Owners
14. 7380 Miscellaneous: existe en casi todos los depts → filtrar por dept_code
```

---



## 22. INTEGRIDAD DEL MODELO — TRAZABILIDAD AL CATÁLOGO

Toda tabla del sistema debe poder trazarse hacia atrás hasta una cuenta del catálogo. El catálogo es la columna vertebral — sin este link el P&L no puede construirse correctamente.

### 22.1 Principio de trazabilidad

El catálogo de cuentas (tabla `accounts`) es la única fuente de verdad para todos los códigos contables. Toda tabla que registra montos debe referenciar una cuenta del catálogo:

```
accounts (el catálogo)
    ├── financial_entries       → account_code (4-8xxx)
    ├── opex_entries            → account_code (7xxx)
    ├── cost_entries            → account_code (5xxx)
    ├── allocation_entries      → source=4999, target=7xxx
    ├── actual_payroll_entries  → account_code_full (6xxx, 7 segmentos)
    ├── payroll_concept_entries → concept_account_code (6000-6030)
    ├── revenue_results         → account_code (4xxx)
    ├── pl_lines                → account_code (4-8xxx)
    └── statistical_entries     → account_code_full (9xxx)
```

### 22.2 Mapa completo tablas → catálogo

```
TABLA                       CUENTA EN CATÁLOGO              CLASE
──────────────────────────────────────────────────────────────────
financial_entries           account_code → accounts         4-9xxx
opex_entries                account_code → accounts         7xxx
opex_account_totals         account_code → accounts         7xxx
cost_entries                account_code → accounts         5xxx
allocation_entries          source=4999, target=7xxx        4/7xxx
actual_payroll_entries      account_code_full (7 segs)      6xxx
payroll_concept_entries     concept_account_code=6000-6030  6xxx
revenue_results             account_code → accounts         4xxx
pl_lines                    account_code → accounts         4-8xxx
statistical_entries         account_code_full → accounts    9xxx
payroll_positions           dept_code+position_code → 6xxx  6xxx (indir.)
package_component_configs   usali_account → accounts        4xxx (directo)
laundry_alloc_config        cost_account_code=5501          5xxx (directo)
pl_manual_inputs            lineas 8xxx via pl_engine       8xxx (indir.)
```

### 22.3 Campos requeridos en modelos para completar trazabilidad

```python
class PayrollConceptEntry(Base):
    concept_account_code: str   # '6000' a '6030' → FK a accounts.seg1
    # PayrollConceptEntry → accounts (6xxx) OK

class AllocationEntry(Base):
    source_account_code: str    # '4999' siempre
    target_account_code: str    # cuenta 7xxx del dept receptor
    # AllocationEntry → accounts (4999 + 7xxx) OK

class PLLine(Base):
    account_code: str           # '4000','5101','6000','7065','8000', etc.
    account_class: str          # '4'|'5'|'6'|'7'|'8' (primer digito de seg1)
    # PLLine → accounts (cualquier clase) OK

class PayrollPosition(Base):
    payroll_catalog_code: str   # position_code del PLANNING_CATALOGO
    # PayrollPosition → payroll_accounts → 6xxx OK

class LaundryAllocationConfig(Base):
    cost_account_code: str      # '5501' — LAUNDRY COSTS
    # LaundryAllocationConfig → accounts (5501) OK
```

### 22.4 Flujo completo: inputs → catálogo → P&L

```
INPUTS DEL USUARIO
    |
    +-- Tarifas+Ocupacion → revenue_calculator → RevenueResult (4xxx)
    +-- Salarios+FTE      → payroll_calculator → PayrollConceptEntry (6xxx)
    +-- OPEX por cuenta   → OpexEntry (7xxx)
    +-- CoS con drivers   → cost_calculator    → CostEntry (5xxx)
    +-- Allocations       → allocation_calc    → AllocationEntry (4999+7xxx)
    +-- Manual inputs     → PLManualInput      → PLLine (8xxx)
    |
    v
FinancialEntry (todas las clases — una fila por cuenta × dept × mes)
    |
    v
pl_engine.py (agrupa por seg1=account_class y seg2=dept_code)
    |
    v
PLLine (account_code ligado al catalogo)
    |
    v
P&L REPORT + OWNER REPORT
```

### 22.5 Regla account_class → seccion del P&L

```
seg1 starts with:
  4xxx → REVENUES
  5xxx → OPERATING EXPENSES (costo de ventas, dentro del dept)
  6xxx → OPERATING EXPENSES (planilla, dept operativo u overhead)
  7xxx → OPERATING EXPENSES (OPEX, dept operativo u overhead)
  8xxx → NON-OPERATING (owners: rent, deprec, taxes, mgmt fees)
  9xxx → NO VA AL P&L (solo estadisticas y KPIs)

NUNCA:
  5xxx en depts overhead (0181-0230) — no tienen CoS
  9xxx en ninguna seccion del P&L
  4999 con saldo distinto de $0 a nivel hotel
```

### 22.6 Tests de integridad referencial

```python
def test_every_financial_entry_references_catalog():
    entries = db.query(FinancialEntry).filter_by(scenario_id=scenario_id).all()
    catalog_codes = {a.seg1 for a in db.query(Account).all()}
    for e in entries:
        assert e.account_code[:4] in catalog_codes

def test_no_cos_in_overhead_depts():
    OVERHEAD = ['0181','0182','0183','0184','0186','0190','0200','0205','0230']
    bad = db.query(CostEntry).filter(CostEntry.dept_code.in_(OVERHEAD)).count()
    assert bad == 0, f"CostEntry (5xxx) found in overhead depts"

def test_9xxx_never_in_pl():
    stat_lines = db.query(PLLine).filter(PLLine.account_code.like('9%')).count()
    assert stat_lines == 0

def test_4999_nets_to_zero_all_months():
    for month in range(1, 13):
        total = db.query(func.sum(FinancialEntry.amount_usd)).filter(
            FinancialEntry.account_code == '4999',
            FinancialEntry.month == month
        ).scalar() or 0
        assert abs(float(total)) < 0.01, f"4999 not zero month {month}"

def test_pl_sums_match_financial_entries():
    for cls in ['4','5','6','7']:
        fe_sum = db.query(func.sum(FinancialEntry.amount_usd)).filter(
            FinancialEntry.account_code.like(f'{cls}%')
        ).scalar() or 0
        pl_sum = db.query(func.sum(PLLine.amount_usd)).filter(
            PLLine.account_class == cls
        ).scalar() or 0
        assert abs(float(fe_sum - pl_sum)) < 1, f"Class {cls} mismatch"
```

---


## 23. CALENDARIO DE PLANNING

El sistema tiene dos capas de calendario con propósitos distintos pero complementarios.

**Capa 1 — Calendario Laboral CR:** feriados nacionales y días libres por ley. Afecta planilla (conceptos 6002 y 6003).

**Capa 2 — Calendario de Demanda Global:** eventos mundiales que generan picos de demanda en el mercado de CWL (USA 50%, UK 20%, Europa 10%, CR 6%). Apoyo para planificar tarifas y ocupación.

### 23.1 Modelo de datos

```python
class PlanningCalendar(Base):
    __tablename__ = 'planning_calendar'

    id: UUID
    hotel_id: str
    year: int
    event_type: str         # 'CR_HOLIDAY' | 'DEMAND_EVENT' | 'HOTEL_CLOSURE' | 'OTHER'
    event_name: str         # 'Thanksgiving US', 'Semana Santa', 'Viernes Santo'
    market: str             # 'US' | 'UK' | 'EU' | 'CR' | 'ALL' | 'HOTEL'
    date_from: date
    date_to: date           # igual a date_from si es un solo dia
    demand_impact: str      # 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
    payroll_impact: str     # 'HOLIDAY' | 'DAY_OFF' | 'NONE'
    notes: str
    is_recurring: bool      # True = se replica cada año automaticamente
    created_by: str


class PayrollCalendarLink(Base):
    """Liga un feriado CR a la planilla de un mes — facilita calculo de 6002/6003."""
    __tablename__ = 'payroll_calendar_links'

    id: UUID
    scenario_id: UUID
    calendar_event_id: UUID
    dept_code: str          # departamento afectado ('ALL' si aplica a todos)
    month: int
    days_count: Decimal     # cuantos dias del evento caen en este mes
    concept_code: str       # '6002' dia libre | '6003' feriado trabajado
    amount_per_day: Decimal # salary_amount / 30
```

### 23.2 Capa 1 — Feriados nacionales CR

Pre-cargados automaticamente al crear un año. Los movibles (Semana Santa) los ingresa el usuario.

```
FERIADOS FIJOS (is_recurring=True)          payroll_impact
  Ene  1  Año Nuevo                          HOLIDAY
  Abr  11 Día de Juan Santamaría             HOLIDAY
  May  1  Día del Trabajo                    HOLIDAY
  Jul  25 Anexión de Guanacaste              HOLIDAY
  Ago  2  Virgen de los Ángeles              HOLIDAY
  Ago  15 Día de la Madre                    HOLIDAY
  Sep  15 Día de la Independencia            HOLIDAY
  Oct  12 Día de las Culturas                HOLIDAY
  Dic  25 Navidad                            HOLIDAY

FERIADOS MOVIBLES (is_recurring=False — usuario actualiza cada año)
  Jueves Santo     (Mar/Abr — variable)
  Viernes Santo    (Mar/Abr — variable)
  Sábado de Gloria (Mar/Abr — variable)
```

Impacto en planilla:
- Si trabaja en feriado → 6003 Worked Holidays = salary_diario × 2.0 (doble pago CR)
- Si descansa → 6002 Days Off = salary_diario × 1.0 (pago normal sin trabajar)
- salary_diario = salary_amount / 30

### 23.3 Capa 2 — Calendario de demanda global

No afectan planilla. Son referencia visual al presupuestar occupancy%.

```
MERCADO USA (50% huéspedes CWL)
  HIGH    Martin Luther King Day       Ene — 3er lunes
  HIGH    Presidents Day Weekend       Feb — 3er lunes (3 dias)
  HIGH    Spring Break                 Mar 1 – Abr 15 (variable por estado)
  HIGH    Easter / Semana Santa        Mar/Abr variable
  MEDIUM  Memorial Day Weekend         May — ultimo lunes (3 dias)
  MEDIUM  Independence Day             Jul 4
  MEDIUM  Labor Day Weekend            Sep — 1er lunes (3 dias)
  HIGH    Thanksgiving Week            Nov — 4to jueves (toda la semana)
  HIGH    Christmas – New Year         Dic 20 – Ene 5

MERCADO UK / EUROPA (30% combinado)
  MEDIUM  UK February Half Term        Feb — semana media
  HIGH    Easter EU School Break       Mar/Abr — 2 semanas
  MEDIUM  Whitsun / Pentecost          May/Jun (varia por pais)
  HIGH    European Summer Holidays     Jul 1 – Ago 31
  MEDIUM  UK October Half Term         Oct — ultima semana
  HIGH    Christmas EU                 Dic 20 – Ene 5

MERCADO CR + REGIONAL
  HIGH    Semana Santa CR              Mar/Abr variable
  MEDIUM  Vacaciones medio año CR      Jul 1-31
```

### 23.4 Como conecta con el resto del sistema

```
PlanningCalendar
    |
    +-- Feriados CR (CR_HOLIDAY)
    |       → PayrollCalendarLink → muestra cuantos dias 6002/6003 hay por mes
    |       → El usuario usa esto como referencia para ingresar valores manuales
    |          de 6002 (Days Off) y 6003 (Worked Holidays) en el checkbook de planilla
    |       → NO calcula automaticamente — es apoyo al usuario
    |
    +-- Eventos de demanda (DEMAND_EVENT)
            → Visible en el modulo de ingresos al presupuestar occupancy%
            → "Febrero tiene Presidents Day (US HIGH) → considerar 75% vs 65%"
            → El sistema NO ajusta automaticamente — es informacion de apoyo
            → El usuario decide que occupancy% ingresa
```

### 23.5 Vista del calendario en el UI

```
CALENDARIO DE PLANNING 2026
[Filtros: Todos | Feriados CR | Demanda US | Demanda EU | Cierre Hotel]

ENERO 2026
  Ene 1  Año Nuevo ──────────────────── Feriado CR   payroll: 6002/6003
  Ene 19 Martin Luther King Day ──────── Demanda US  ★★★ HIGH

FEBRERO 2026
  Feb 9  UK Half Term ───────────────── Demanda UK   ★★ MEDIUM
  Feb 16 Presidents Day Weekend ──────── Demanda US  ★★★ HIGH

MARZO 2026
  Mar 1  Spring Break USA starts ──────── Demanda US ★★★ HIGH
  Mar 29 Easter / Semana Santa ──────── Demanda ALL  ★★★ HIGH
  Mar 30 Jueves Santo ────────────────── Feriado CR   payroll: 6002/6003
  Mar 31 Viernes Santo ───────────────── Feriado CR   payroll: 6002/6003
  ...

[+ Agregar evento]   [Exportar a PDF]   [Ver impacto planilla]
```

### 23.6 Pre-carga automatica al crear un año

```python
CR_FIXED_HOLIDAYS = [
    (1,  1,  "Año Nuevo"),
    (4,  11, "Día de Juan Santamaría"),
    (5,  1,  "Día del Trabajo"),
    (7,  25, "Anexión de Guanacaste"),
    (8,  2,  "Virgen de los Ángeles"),
    (8,  15, "Día de la Madre"),
    (9,  15, "Día de la Independencia"),
    (10, 12, "Día de las Culturas"),
    (12, 25, "Navidad"),
]

def seed_calendar_year(hotel_id: str, year: int):
    """
    Pre-carga al crear un año:
    1. Feriados fijos CR automaticamente
    2. Eventos de demanda recurrentes (con fechas aproximadas)
    3. Semana Santa y feriados movibles quedan en blanco — usuario los ingresa
    """
    for month, day, name in CR_FIXED_HOLIDAYS:
        create_event(hotel_id, year, 'CR_HOLIDAY', name, 'CR',
                     date_from=date(year, month, day),
                     payroll_impact='HOLIDAY', is_recurring=True)
    # Eventos de demanda — sin fechas exactas, el usuario las ajusta
    create_demand_events_template(hotel_id, year)
```

### 23.7 Endpoints del calendario

```
GET  /api/calendar/{hotel_id}/{year}/              todos los eventos
GET  /api/calendar/{hotel_id}/{year}/{month}/      eventos de un mes
POST /api/calendar/{hotel_id}/event/               agregar evento manual
PUT  /api/calendar/{hotel_id}/event/{id}/          editar (ej: fecha exacta Semana Santa)
DEL  /api/calendar/{hotel_id}/event/{id}/          eliminar
POST /api/calendar/{hotel_id}/year/seed/           pre-cargar feriados CR del año
POST /api/calendar/{hotel_id}/year/replicate/      copiar eventos recurrentes al año siguiente

GET  /api/calendar/{scenario_id}/payroll-impact/   feriados CR × dept × mes
     → cuantos dias 6002/6003 hay por mes como referencia para planilla
```

---


## 24. HISTORIAL DE GRUPOS

Módulo para registrar y analizar el historial de grupos que han visitado CWL. Cubre 2025–2030 (extensible). Permite identificar patrones de repetición, estacionalidad y proyectar business de grupos para el presupuesto.

### 24.1 Modelo de datos

```python
class GroupBooking(Base):
    """
    Registro de cada grupo que visita CWL.
    Una fila por grupo × año. Si el mismo grupo viene en años distintos,
    tiene una fila por cada visita.
    """
    __tablename__ = 'group_bookings'

    id: UUID
    hotel_id: str               # 'CWL'
    year: int                   # 2025, 2026, 2027, 2028, 2029, 2030

    # Identidad del grupo
    group_name: str             # 'Smithsonian Institution', 'National Geographic'
    group_type: str             # 'CORPORATE' | 'INCENTIVE' | 'ASSOCIATION' |
                                # 'FAMILY_REUNION' | 'WEDDING' | 'EDUCATIONAL' |
                                # 'MEDIA' | 'OTHER'
    contact_name: str           # nombre del organizador/agente
    contact_company: str        # agencia o empresa que lo organiza
    market: str                 # 'US' | 'UK' | 'EU' | 'CR' | 'OTHER'

    # Fechas
    arrival_month: int          # mes de llegada (1-12)
    arrival_date: date          # fecha exacta de llegada
    departure_date: date        # fecha de salida

    # Volumen
    pax: int                    # número de personas
    rooms_used: int             # habitaciones utilizadas
    nights: int                 # número de noches
                                # Calculado: (departure_date - arrival_date).days

    # Financiero
    total_paid_usd: Decimal     # total pagado en USD
    rate_per_person_usd: Decimal # calculado: total_paid / pax
    rate_per_room_usd: Decimal  # calculado: total_paid / rooms_used / nights
    currency_paid: str          # 'USD' | 'CRC' | 'EUR'
    total_paid_original: Decimal # monto en moneda original si no es USD

    # Contexto
    notes: str                  # observaciones, actividades especiales, etc.
    repeat_group: bool          # True = este grupo ha venido antes
    first_year: int             # año de la primera visita (para medir fidelidad)
    referred_by: str            # cómo llegó el grupo (agencia, directo, referido)
    status: str                 # 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | 'TENTATIVE'
```

### 24.2 Vista principal — tabla por año y mes

```
HISTORIAL DE GRUPOS CWL — 2025 a 2030
[Filtrar: Todos | Por año | Por mes | Por tipo | Por mercado]   [+ Agregar grupo]

AÑO 2026
  Mes   Grupo                    Tipo         Mercado   Pax   Noc   Noches   Total USD   $/Pax
  ────  ───────────────────────  ───────────  ───────  ────  ────  ──────   ─────────   ─────
  Ene   Smithsonian Journeys     Educational  US        24    8      6       $28,800     $1,200
  Feb   Butterfield & Robinson   Incentive    US/CA     16    6      5       $22,400     $1,400
  Mar   National Geographic      Media        US        8     4      4       $14,400     $1,800  ★ repeat
  Mar   Yale Alumni Travel       Association  US        30    10     5       $36,000     $1,200
  Abr   (ninguno)
  May   Exodus Travels           Corporate    UK        12    5      4       $12,000     $1,000
  ...
  Nov   Lindblad Expeditions     Educational  US        20    8      5       $28,000     $1,400  ★ repeat
  Dic   (ninguno)
  ────────────────────────────────────────────────────────────────────────────────────────
  TOTAL 2026                                           110   41             $141,600

AÑO 2025
  Mes   Grupo                    Tipo         Mercado   Pax   Noc   Noches   Total USD
  ────  ───────────────────────  ───────────  ───────  ────  ────  ──────   ─────────
  Ene   Smithsonian Journeys     Educational  US        20    7      5       $22,000     ★ volvió 2026
  Mar   National Geographic      Media        US        6     3      4       $9,600      ★ volvió 2026
  ...
  ────────────────────────────────────────────────────────────────────────────────────────
  TOTAL 2025                                           ...

[★ = grupo que ha repetido visita]
```

### 24.3 Vista de análisis — patrones por mes

```
ESTACIONALIDAD DE GRUPOS — CWL (2025-2030)

Mes        Grupos/año   Pax prom   Revenue prom   Meses más activos
────────   ──────────   ────────   ────────────   ─────────────────
Enero      ████         2.1        $25,400        ★★★ Alto
Febrero    ████         1.8        $21,200        ★★★ Alto
Marzo      █████        3.2        $38,600        ★★★★ Pico
Abril      ███          1.5        $17,800        ★★★ Alto
Mayo       ██           0.8        $9,200         ★★ Medio
Junio      █            0.4        $4,800         ★ Bajo
Julio      █            0.6        $7,200         ★ Bajo
Agosto     █            0.5        $5,600         ★ Bajo
Septiembre ██           0.7        $8,400         ★ Bajo-Medio
Octubre    —            —          —              Cerrado (2026)
Noviembre  ████         2.0        $24,000        ★★★ Alto (inicio temporada)
Diciembre  ██           1.2        $14,400        ★★ Medio
```

### 24.4 Vista de grupos repetidores

```
GRUPOS QUE HAN REPETIDO VISITA

Grupo                    Visitas   Años              Tendencia
───────────────────────  ───────   ────────────────  ──────────
Smithsonian Journeys     3         2024, 2025, 2026  ↑ creciendo
National Geographic      2         2025, 2026        → estable
Lindblad Expeditions     2         2025, 2026        → estable
Yale Alumni Travel       1         2026              nuevo
```

### 24.5 Conexión con el presupuesto

Los datos históricos de grupos alimentan el revenue planning:

```
GroupBooking (historial)
    │
    ├── → Revenue Budget (referencia)
    │       Al presupuestar Rooms Revenue y Groups, el usuario puede ver:
    │       "En enero los últimos 2 años tuvimos 2 grupos promedio
    │        con $25,400 de revenue — ¿cuánto presupuestamos para 2027?"
    │
    └── → Calendario de Planning (sección 23)
            Los grupos confirmados para el año en curso
            pueden marcarse en el calendario como HOTEL_CLOSURE parcial
            (habitaciones bloqueadas para el grupo)
```

### 24.6 Endpoints del módulo de grupos

```
# CRUD
GET  /api/groups/{hotel_id}/                          todos los grupos
GET  /api/groups/{hotel_id}/?year=2026                grupos de un año
GET  /api/groups/{hotel_id}/?year=2026&month=3        grupos de un mes
GET  /api/groups/{hotel_id}/{group_id}/               detalle de un grupo
POST /api/groups/{hotel_id}/                          registrar grupo
PUT  /api/groups/{hotel_id}/{group_id}/               editar
DEL  /api/groups/{hotel_id}/{group_id}/               eliminar

# Análisis
GET  /api/groups/{hotel_id}/summary/                  resumen por año 2025-2030
GET  /api/groups/{hotel_id}/by-month/                 estacionalidad (pax, revenue por mes)
GET  /api/groups/{hotel_id}/repeating/                grupos que han repetido
GET  /api/groups/{hotel_id}/by-type/                  breakdown por tipo de grupo
GET  /api/groups/{hotel_id}/by-market/                breakdown por mercado
GET  /api/groups/{hotel_id}/kpis/{year}/              KPIs del año: total grupos, pax, revenue
```

### 24.7 KPIs del módulo de grupos

```python
class GroupKpis(TypedDict):
    """KPIs calculados por año."""
    year: int
    total_groups: int           # cantidad de grupos
    total_pax: int              # total personas
    total_nights: int           # total noches
    total_revenue_usd: Decimal  # revenue total
    avg_revenue_per_group: Decimal
    avg_pax_per_group: Decimal
    avg_rate_per_pax: Decimal   # ADR por persona
    repeat_groups: int          # grupos que volvieron
    repeat_pct: Decimal         # % de grupos repetidores
    most_active_month: int      # mes con más grupos
    top_market: str             # mercado con más revenue
```

---


## 25. ESTÁNDARES DE DATOS — DECIMALES Y COPY-PASTE

### 25.1 Precisión decimal — 2 decimales en todo el sistema

**Regla global: todo valor numérico se guarda y muestra con exactamente 2 decimales.**

```python
# PostgreSQL — definición de columnas
amount_usd:       Numeric(15, 2)   # $999,999,999,999.99
amount_crc:       Numeric(15, 2)
salary_amount:    Numeric(12, 2)
tc_crc_usd:       Numeric(8,  2)   # 530.00
rack_rate_usd:    Numeric(10, 2)
occupancy_pct:    Numeric(5,  2)   # 0.75 = 75%
fte:              Numeric(4,  2)   # 0.00 a 1.00
kilos:            Numeric(10, 2)
rooms_occupied:   Numeric(8,  2)   # puede ser fracción en promedios
pax:              Integer          # entero
nights:           Integer          # entero
rooms_available:  Integer          # entero

# Python — siempre Decimal, NUNCA float
from decimal import Decimal, ROUND_HALF_UP

def round2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

# CORRECTO:  Decimal('650000') / Decimal('530') → round2() → Decimal('1226.42')
# INCORRECTO: 650000 / 530 → 1226.4150943396226 (float, impreciso para dinero)
```

**Presentación en el UI:**
```
Montos USD:       $1,226.42
Montos CRC:       ₡650,000.00
Porcentajes:      75.00%
Tipo de cambio:   530.00
FTE:              1.00 / 0.50
ADR / RevPAR:     $595.27
Volumen (enteros): 2,587 noches | 943 pax | 30 habitaciones
```

### 25.2 Copy-paste desde Excel — regla global del UI

**Todo campo numérico acepta copy-paste desde Excel sin fricción.** Es el caso de uso más frecuente.

```python
# utils/input_parser.py

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import re

def parse_numeric_input(raw: str) -> Decimal:
    """
    Acepta cualquier formato que pueda pegar Excel:
    "$1,226.42"   → Decimal('1226.42')
    "1.226,42"    → Decimal('1226.42')  # formato europeo
    "(1,226.42)"  → Decimal('-1226.42') # negativo contable
    "75%"         → Decimal('0.75')     # porcentaje
    "₡650,000"    → Decimal('650000.00')
    " 530 "       → Decimal('530.00')   # con espacios
    """
    if raw is None:
        return Decimal('0.00')
    s = str(raw).strip()

    # Strip simbolos de moneda
    s = s.replace('$','').replace('₡','').replace('€','').replace('£','')

    # Negativo en parentesis
    is_negative = s.startswith('(') and s.endswith(')')
    if is_negative:
        s = s[1:-1]

    # Porcentaje
    is_pct = s.strip().endswith('%')
    if is_pct:
        s = s.strip()[:-1]

    s = s.strip()

    # Formato europeo vs americano
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.','').replace(',','.')  # europeo: 1.226,42
        else:
            s = s.replace(',','')                    # americano: 1,226.42
    elif ',' in s:
        parts = s.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = s.replace(',','.')  # decimal: 1226,42
        else:
            s = s.replace(',','')   # miles: 1,226,000

    s = re.sub(r'\s+', '', s)
    if not s:
        return Decimal('0.00')

    try:
        value = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"No se puede parsear: {repr(raw)}")

    if is_pct:
        value = value / Decimal('100')
    if is_negative:
        value = -value

    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
```

### 25.3 Copy-paste de rangos (múltiples celdas)

Cuando el usuario copia un rango de Excel, el sistema recibe TSV (Tab + Newline):

```python
def parse_excel_paste(raw_text: str) -> list[list[Decimal]]:
    """Parsea un rango de Excel pegado (filas=newline, columnas=tab)."""
    rows = []
    for line in raw_text.strip().split('\n'):
        cells = line.split('\t')
        rows.append([parse_numeric_input(c) for c in cells])
    return rows
```

**Caso más común — pegar 12 TC del año desde Excel:**
```javascript
// Frontend Next.js — campo de TC con paste inteligente
onPaste={(e) => {
    const text = e.clipboardData.getData('text')
    const values = text.trim().split(/[\n\t]/).map(v => parseFloat(v.replace(/[,$₡]/g,'')))
    if (values.length === 12) {
        setAllMonthsTC(values)  // asigna los 12 meses de una vez
        e.preventDefault()
    }
}}
```

### 25.4 Campos con copy-paste crítico

| Módulo | Campos clave para paste |
|--------|------------------------|
| Tipos de Cambio | 12 TC del año — pegar columna completa |
| Checkbook Planilla | Salarios de múltiples posiciones |
| Checkbook OPEX | Montos por mes (12 columnas) |
| Tarifas Rack | 12 meses × 6 tipos de villa |
| Ocupación % | 12 meses × 6 tipos de villa |
| Historial Grupos | Datos desde Excel de seguimiento |
| Históricos KPIs | Actuals 2024-2025 desde reportes Excel |

---

## 26. DISEÑO DE INTERFAZ — DESIGN SYSTEM

La interfaz debe verse y sentirse como una herramienta financiera profesional de clase mundial. La referencia es TradingView — dark theme, datos densos pero legibles, colores con significado, tipografía monoespacio para números.

### 26.1 Paleta de colores

```css
/* === DESIGN TOKENS — FinPlan CWL === */
:root {
  /* Backgrounds */
  --bg-base:        #131722;   /* fondo principal — casi negro azulado */
  --bg-surface:     #1E2130;   /* cards, paneles, checkbooks */
  --bg-elevated:    #2A2E3F;   /* hover states, filas seleccionadas */
  --bg-input:       #1A1D2E;   /* campos de entrada */
  --bg-header:      #0F1118;   /* topbar y sidebar */

  /* Borders */
  --border-subtle:  #2A2E3F;   /* separadores suaves */
  --border-medium:  #363B52;   /* bordes de cards */
  --border-focus:   #2962FF;   /* foco en inputs */

  /* Text */
  --text-primary:   #D1D4DC;   /* texto principal */
  --text-secondary: #787B86;   /* labels, texto secundario */
  --text-disabled:  #4C505E;   /* deshabilitado */
  --text-inverse:   #131722;   /* texto sobre colores claros */

  /* Brand / Accent */
  --brand:          #2962FF;   /* azul TradingView — acciones primarias */
  --brand-hover:    #1E53E5;

  /* Semánticos financieros */
  --positive:       #26A69A;   /* verde — favorable, por encima de budget */
  --negative:       #EF5350;   /* rojo — desfavorable, por debajo */
  --warning:        #F59E0B;   /* amarillo — atención, varianza moderada */
  --neutral:        #787B86;   /* gris — sin varianza */

  /* Demanda en calendario */
  --demand-high:    #26A69A;   /* HIGH — verde */
  --demand-medium:  #F59E0B;   /* MEDIUM — amarillo */
  --demand-low:     #787B86;   /* LOW — gris */
  --holiday-cr:     #EF5350;   /* feriado CR — rojo */

  /* Tipografía */
  --font-ui:        'Inter', -apple-system, sans-serif;
  --font-mono:      'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  --font-display:   'Inter', sans-serif;
}
```

### 26.2 Tipografía

```css
/* Números financieros — SIEMPRE monospace */
.amount, .rate, .fte, .pct, .kpi-value {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;  /* alineación de dígitos */
  letter-spacing: -0.01em;
}

/* Escala tipográfica */
--text-xs:    11px;   /* labels de tabla, footnotes */
--text-sm:    12px;   /* cuerpo de tabla */
--text-base:  13px;   /* cuerpo general */
--text-md:    14px;   /* labels de sección */
--text-lg:    16px;   /* títulos de panel */
--text-xl:    20px;   /* títulos de página */
--text-2xl:   24px;   /* KPIs principales */
--text-3xl:   32px;   /* números hero (GOP, Net Profit) */

/* Números grandes en KPIs */
.kpi-hero {
  font-family: var(--font-mono);
  font-size: var(--text-3xl);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}
```

### 26.3 Componentes clave

**KPI Cards (como las de TradingView):**
```
┌──────────────────────────────────┐
│  Total Revenue          Apr 2026 │
│  $597,135.41                     │  ← monospace, grande
│  ↑ $219,129  +57.9% vs Budget    │  ← verde si favorable
│  YTD: $3,048,621.50              │  ← texto secundario
└──────────────────────────────────┘

┌──────────────────────────────────┐
│  GOP                    Apr 2026 │
│  $176,037.54                     │
│  ↑ $146,428  +494.5% vs Budget   │
│  YTD: $1,337,996.68              │
└──────────────────────────────────┘
```

**Tablas (checkbooks):**
```
Fila par:        bg-surface   #1E2130
Fila impar:      bg-base      #131722
Fila hover:      bg-elevated  #2A2E3F
Fila seleccion:  bg-elevated  + border-left: 2px solid var(--brand)
Header tabla:    bg-header    #0F1118, text-secondary
Totales:         bg-elevated  + font-weight: 600
```

**Varianzas con color semántico:**
```css
.variance-positive { color: var(--positive); }   /* #26A69A verde */
.variance-negative { color: var(--negative); }   /* #EF5350 rojo */
.variance-neutral  { color: var(--neutral);  }   /* #787B86 gris */

/* Aplicar automáticamente según el tipo de línea:
   Revenue: positivo = actual > budget (más ingresos = bueno)
   Gastos:  positivo = actual < budget (menos gastos = bueno)
   La lógica del color se invierte según el tipo */
```

### 26.4 Layout general — navegación tipo Opera Cloud

Inspirado en Opera Cloud (el PMS que ya usa el equipo): navegación horizontal con dropdowns, sin sidebar. Más limpio, más familiar para el equipo.

```
┌─────────────────────────────────────────────────────────────────────────┐
│ TOPBAR                                                                  │
│ [≡] [Logo CWL]  Ingresos ▾  Planilla ▾  Costos ▾  P&L ▾  Reportes ▾  │
│                                         Viernes, 19 Jun 2026  BISMARK ▾│
├─────────────────────────────────────────────────────────────────────────┤
│ BREADCRUMB: Dashboard / Planilla / Tours                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  CONTENT AREA — ocupa todo el ancho                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Dropdowns del menú principal:**

```
Ingresos ▾                Planilla ▾           Costos ▾
  Rates & Tarifas           Por Departamento     Cost of Sales
  Key Indicators            Reporte FTE          OPEX por Dept
  Canales de Venta          Tipo de Cambio       ──────────────
  Paquetes                  ─────────────        Checkbook F&B
  Históricos 2024-25        Parámetros           Checkbook Tours
                                                 Checkbook Rooms

P&L ▾                     Reportes ▾           Config ▾
  P&L Full Year              YTD Summary          Propiedades
  Simplified P&L             Owner Report         Usuarios
  Varianzas                  Exportar Excel       Calendario
  Budget vs Forecast         Exportar PDF         Grupos
  ──────────────             ─────────────        Master Data
  Recalcular ⟳              Narrativa AI
```

**Topbar derecha — igual que Opera Cloud:**
```
[Viernes, 19 Jun 2026]  [CWL — Corcovado WL ▾]  [BISMARK RODRIGUEZ ▾]
                              └── cambiar propiedad    └── Mi perfil
                                                           Cambiar password
                                                           Cerrar sesión
```

**Tabs por página** (como Opera Cloud FINANCE / FINANCE 2/4 etc.):
```
P&L Full Year
[Mes Actual] [YTD] [Full Year] [Comparativo]
```

### 26.5 Componentes de navegación

```css
/* Topbar */
.topbar {
  background: #0F1118;
  height: 44px;
  display: flex;
  align-items: center;
  border-bottom: 1px solid #2A2E3F;
  padding: 0 16px;
  gap: 0;
}

/* Nav items */
.nav-item {
  color: #787B86;
  font-size: 13px;
  padding: 0 14px;
  height: 44px;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}
.nav-item:hover {
  color: #D1D4DC;
  background: #1E2130;
}
.nav-item.active {
  color: #D1D4DC;
  border-bottom-color: #2962FF;
}

/* Dropdown */
.dropdown {
  position: absolute;
  top: 44px;
  background: #1E2130;
  border: 1px solid #2A2E3F;
  border-radius: 4px;
  min-width: 200px;
  padding: 4px 0;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.dropdown-item {
  padding: 8px 16px;
  font-size: 13px;
  color: #787B86;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}
.dropdown-item:hover {
  background: #2A2E3F;
  color: #D1D4DC;
}
.dropdown-divider {
  height: 1px;
  background: #2A2E3F;
  margin: 4px 0;
}

/* Page tabs (como Opera Finance 1/4, 2/4, etc.) */
.page-tabs {
  display: flex;
  border-bottom: 1px solid #2A2E3F;
  background: #131722;
  padding: 0 16px;
  gap: 4px;
}
.page-tab {
  padding: 8px 16px;
  font-size: 12px;
  color: #787B86;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  display: flex;
  align-items: center;
  gap: 6px;
}
.page-tab.active {
  color: #D1D4DC;
  border-bottom-color: #2962FF;
}
.page-tab .tab-actions {
  color: #4C505E;
  font-size: 10px;
}
```

### 26.6 Breadcrumb y acciones de página

```
Dashboard / Planilla / Tours (0150)                [Recalcular ⟳] [Export ↓]
```

Siempre visible debajo del topbar. El botón Recalcular está en la esquina superior derecha de la página, no flotante.



### 26.5 Checkbook — diseño de tabla financiera

```
CHECKBOOK OPEX — F&B (0120)                    [Recalcular ⟳]  [Export ↓]

                         2024      2025    |  Ene    Feb    Mar  ...  Total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7025  Banquet Expenses                    |
  800  Alquiler mesas      $1,054    $235 |  [   0] [   0] [   0]    $0.00
  801  Alquiler carpa          $0      $0 |  [   0] [   0] [   0]    $0.00
  ── SUBTOTAL 7025         $1,054    $235 |   $0.00  $0.00  $0.00    $0.00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
7060  China                              |
  800  Vajilla hotel          $446    $478|  [   0] [ 500] [   0]  $500.00
  ── SUBTOTAL 7060            $446    $478|   $0.00 $500.00 $0.00  $500.00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                                         |
TOTAL OPEX F&B              $10,911  $5,360  $X,XXX $X,XXX        $XX,XXX

Reglas visuales:
  - Columnas 2024/2025: texto-secondary, sin editar, fondo más oscuro
  - Columnas de mes: campos editables, monospace, alineados a la derecha
  - SUBTOTALES: font-weight 500, background ligeramente diferente
  - TOTAL: font-weight 700, border-top 1px solid --border-medium
  - Campos editados (≠0): ligero highlight en --bg-elevated
  - Celda activa: border --brand, fondo --bg-input
```

### 26.6 P&L — diseño del reporte principal

```
Jerarquía visual por nivel:

REVENUES                           ← sección: CAPS, text-secondary, spacing arriba
  Rooms          $319,273  $210,917  ↑$108,357  +51.4%   ← fila normal
  F&B            $119,211   $72,301  ↑ $46,910  +64.9%
  ...
  TOTAL REVENUES $597,135  $378,006  ↑$219,130  +57.9%   ← BOLD, border-top

OPERATING EXPENSES                 ← sección
  Rooms           $69,790   $53,240  ↑ $16,550  +31.1%
  ...

GOP             $176,038   $29,610  ↑$146,428  +494.5%   ← HERO: grande, color
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NET PROFIT       $52,031  -$22,340  ↑ $74,371  +332.9%   ← color positivo/negativo

Columnas del P&L completo (13 cols) — scroll horizontal en pantallas angostas
Columnas fijas (frozen): Account Description
Columnas de datos: scrollable horizontalmente
```

### 26.7 Dashboard principal — KPIs hero

```
┌─────────┬─────────┬─────────┬─────────┐
│OCCUPANCY│   ADR   │  RevPAR │ REVENUE │
│ 55.89%  │ $631.30 │ $663.48 │$597,135 │
│▲ +19.0pp│ ▼ -$4.0 │▲ +$243.5│▲ +57.9% │
│vs Budget│vs Budget│vs Budget│vs Budget│
└─────────┴─────────┴─────────┴─────────┘

┌───────────────────────────────────────┐
│ Revenue por Departamento — Abr 2026   │
│ ████████████████████ Rooms  $319,273  │
│ ████████             F&B    $119,211  │
│ █████████            Tours   $87,645  │
│ ██████               Transp  $30,297  │
│ ██████               Sust.   $30,904  │
└───────────────────────────────────────┘

┌─────────────────┬─────────────────────┐
│ P&L YTD Abr     │ Forecast 12 meses   │
│ [Recharts line] │ [Recharts bar chart]│
└─────────────────┴─────────────────────┘
```

### 26.8 Colores semánticos en varianzas — regla crítica

```javascript
// La lógica del color de varianza depende del tipo de línea
function getVarianceColor(lineType, varianceAmount) {
  if (lineType === 'REVENUE' || lineType === 'GOP' || lineType === 'NET_PROFIT') {
    // Para ingresos y utilidades: más = verde, menos = rojo
    return varianceAmount > 0 ? 'var(--positive)' : 'var(--negative)'
  } else {
    // Para gastos: menos = verde (ahorro), más = rojo (sobrecosto)
    return varianceAmount < 0 ? 'var(--positive)' : 'var(--negative)'
  }
}
// Ejemplos:
// Revenue +$108,357 → verde ✓  (más ingresos es bueno)
// Payroll  +$34,170 → rojo  ✓  (más gasto en planilla es malo)
// Maint.  -$14,406 → verde ✓  (menos gasto en mantenimiento es bueno)
```

### 26.9 Micro-interacciones clave

```
1. GUARDAR: No hay botón Save en los checkbooks — auto-save con debounce 800ms
   Indicador: pequeño punto gris → girando → checkmark verde al guardar

2. RECALCULAR: botón prominente, siempre visible en sticky bar
   Estado: idle → loading (spinner) → done (flash verde) → idle

3. COPY-PASTE: al pegar múltiples valores, flash sutil en las celdas llenadas
   Si hay error de parsing: highlight rojo en la celda + tooltip con el valor original

4. VARIANZA: los números de varianza aparecen con una flecha (↑↓) antes del valor
   ↑ $108,357 en verde para revenue favorable
   ↓ $34,170  en rojo  para gasto sobre budget

5. HOVER en tabla: fila completa se ilumina en --bg-elevated
   Click: selecciona la fila, muestra panel de detalle lateral (si aplica)

6. NÚMERO NEGATIVO: siempre en rojo, sin paréntesis en el UI
   (Los paréntesis son para Excel — en pantalla se usa el signo menos y el color)
```

### 26.10 Stack de UI recomendado

```
Framework:      Next.js 14 (App Router)
Componentes:    shadcn/ui (base) + custom financiero encima
Charts:         Recharts (ya especificado en el stack)
Tablas:         TanStack Table (react-table) — virtual scrolling para checkbooks grandes
Íconos:         Lucide React
Formularios:    React Hook Form + Zod validation
Animaciones:    Framer Motion (suave, no excesivo)
Fuentes:        Inter (UI) + JetBrains Mono (números)
                → Cargar desde Google Fonts o self-hosted

CSS approach:   Tailwind CSS + CSS variables para tokens
                Los colores del design system se pasan como CSS custom properties
                NO hardcodear hex codes en los componentes — siempre usar variables
```


### 26.11 Dashboard principal — especificación completa

El dashboard es la primera pantalla. Dark theme, datos densos, gráficas profesionales — todo visible sin scroll en 1440px.

**Layout:**
```
TOPBAR: Logo | Propiedad ▾ | Escenario ▾ | Mes ▾ | [YTD] [Recalcular]
FILA 1: 5 KPI cards — Ocupación | ADR | RevPAR | Revenue | GOP
FILA 2: Revenue mensual bar chart (2/3) | Ocupación donut+barras (1/3)
FILA 3: Revenue por dept | Gastos stacked | P&L mini (3 columnas)
FILA 4: Forecast full year — líneas Revenue+GOP Actual vs Forecast
```

**Colores de varianza — regla crítica:**
```javascript
const varianceColor = (lineType, pct) => {
  const favorable = (lineType === 'REVENUE' || lineType === 'PROFIT')
    ? pct > 0    // más ingresos = bueno → verde
    : pct < 0    // menos gasto = bueno → verde
  return favorable ? '#26A69A' : '#EF5350'
}
```

**Chart 1 — Revenue mensual (bar agrupado):**
- Barras Actual (#2962FF) lado a lado con Budget (#363B52)
- Meses futuros en Actual = null (sin barra)
- Tooltips monospace con $XXX,XXX

**Chart 2 — Ocupación (donut + horizontal bars):**
- Donut: noches por tipo de villa
- Barras: % ocupación por tipo, verde si >70% azul si >50% gris si <50%

**Chart 3 — Gastos YTD (stacked bar):**
- Planilla #EF5350 | OPEX #F59E0B | CoS #363B52

**Chart 4 — Forecast full year (líneas):**
- Revenue Actual: #2962FF sólida
- Revenue Forecast: #363B52 punteada
- GOP Actual: #26A69A sólida
- GOP Forecast: #1D6B62 punteada
- Línea vertical en el mes de corte Actual/Forecast

**Librerías:** Recharts para componentes React (ya en el stack).
Canvas background transparente — el panel #1E2130 es el fondo.

---


---

 — el usuario ingresa supuestos (occupancy%, tarifas, revenue/guest) y el sistema explota y recalcula todo automáticamente. Nunca hardcodear ingresos.
## 27. AUTENTICACIÓN Y SEGURIDAD MULTI-USUARIO

### 27.1 Modelo de usuarios

```python
class User(Base):
    __tablename__ = 'users'

    id: UUID
    email: str              # único — es el identificador de login
    full_name: str
    password_hash: str      # bcrypt hash — NUNCA guardar password en texto plano
    is_active: bool         # False = cuenta deshabilitada
    is_verified: bool       # True = confirmó su email
    created_at: datetime
    last_login_at: datetime
    created_by: UUID        # quién creó esta cuenta (admin)

    # Seguridad contra brute force
    failed_attempts: int    # contador de intentos fallidos consecutivos
    locked_until: datetime  # si no es null, la cuenta está bloqueada hasta esta hora
    last_failed_at: datetime


class UserRole(Base):
    """Rol de un usuario dentro de una propiedad específica."""
    __tablename__ = 'user_roles'

    id: UUID
    user_id: UUID
    hotel_id: str           # 'CWL' — a qué propiedad tiene acceso
    role: str               # 'ADMIN' | 'FINANCE' | 'VIEWER'
    created_at: datetime
    created_by: UUID
    # Un usuario puede tener roles distintos en distintas propiedades
    # Ej: FINANCE en CWL, VIEWER en Místico


class AuditLog(Base):
    """Registro de todas las acciones importantes del sistema."""
    __tablename__ = 'audit_logs'

    id: UUID
    user_id: UUID
    hotel_id: str
    action: str             # 'LOGIN' | 'LOGOUT' | 'LOGIN_FAILED' | 'ACCOUNT_LOCKED'
                            # 'SCENARIO_EDIT' | 'RECALCULATE' | 'EXPORT' | etc.
    details: str            # descripción de qué se hizo
    ip_address: str
    user_agent: str
    created_at: datetime
    success: bool
```

### 27.2 Roles y permisos

```
ROL ADMIN:
  ✅ Todo — crear usuarios, asignar roles, ver todo, editar todo
  ✅ Crear y aprobar Budget
  ✅ Lockear/unlockear escenarios
  ✅ Importar actuals
  ✅ Exportar reportes

ROL FINANCE:
  ✅ Ver todo
  ✅ Editar checkbooks (planilla, OPEX, CoS, ingresos)
  ✅ Crear versiones de Forecast
  ✅ Recalcular
  ✅ Exportar reportes
  ❌ Crear/editar usuarios
  ❌ Lockear escenarios (solo aprobar)

ROL VIEWER:
  ✅ Ver dashboard, P&L, reportes
  ✅ Ver todos los checkbooks (solo lectura)
  ✅ Exportar reportes
  ❌ Editar nada
  ❌ Recalcular
  ❌ Importar actuals

Sin límite de usuarios — se pueden crear tantos como se necesiten.
```

### 27.3 Regla de seguridad — bloqueo por intentos fallidos

```python
MAX_FAILED_ATTEMPTS = 3       # intentos antes del bloqueo
LOCKOUT_DURATION_MINUTES = 30 # minutos bloqueado

def authenticate(email: str, password: str, ip: str) -> AuthResult:
    user = get_user_by_email(email)

    # Usuario no existe — respuesta genérica (no revelar si el email existe)
    if not user:
        log_failed_attempt(email=email, ip=ip, reason='user_not_found')
        raise AuthError("Credenciales incorrectas")

    # Verificar si la cuenta está bloqueada
    if user.locked_until and user.locked_until > now():
        minutes_left = (user.locked_until - now()).seconds // 60
        raise AuthError(
            f"Cuenta bloqueada por seguridad. "
            f"Intente de nuevo en {minutes_left} minutos."
        )

    # Verificar password
    if not bcrypt.verify(password, user.password_hash):
        user.failed_attempts += 1
        user.last_failed_at = now()

        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            # Bloquear la cuenta
            user.locked_until = now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            save(user)
            log_audit(user.id, 'ACCOUNT_LOCKED', ip=ip,
                details=f"Cuenta bloqueada tras {MAX_FAILED_ATTEMPTS} intentos fallidos")
            raise AuthError(
                f"Cuenta bloqueada por {LOCKOUT_DURATION_MINUTES} minutos "
                f"por seguridad. Si no eres tú, contacta al administrador."
            )

        attempts_left = MAX_FAILED_ATTEMPTS - user.failed_attempts
        save(user)
        log_audit(user.id, 'LOGIN_FAILED', ip=ip)
        raise AuthError(
            f"Credenciales incorrectas. "
            f"Te quedan {attempts_left} intento{'s' if attempts_left > 1 else ''} "
            f"antes del bloqueo."
        )

    # Login exitoso — resetear contador
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now()
    save(user)

    token = create_jwt(user_id=user.id, email=user.email)
    log_audit(user.id, 'LOGIN', ip=ip, success=True)
    return AuthResult(token=token, user=user)
```

### 27.4 Flujo completo de autenticación

```
LOGIN
  1. Usuario ingresa email + password
  2. Sistema verifica:
     a. ¿Existe el email?
     b. ¿Está la cuenta bloqueada?
     c. ¿Es correcto el password?
  3. Si todo OK → JWT token (expira en 8 horas)
  4. Si falla → +1 intento fallido
  5. Si 3 fallos → bloqueo 30 minutos

MENSAJES AL USUARIO:
  1er fallo:  "Credenciales incorrectas. Te quedan 2 intentos antes del bloqueo."
  2do fallo:  "Credenciales incorrectas. Te queda 1 intento antes del bloqueo."
  3er fallo:  "Cuenta bloqueada por 30 minutos por seguridad.
               Si no eres tú, contacta al administrador."
  Bloqueado:  "Cuenta bloqueada. Intenta de nuevo en X minutos."

DESBLOQUEO:
  Opción 1: Esperar 30 minutos (automático)
  Opción 2: Admin desbloquea manualmente desde panel de usuarios
  Opción 3: Usuario solicita reset de password por email
```

### 27.5 Reset de password

```python
def request_password_reset(email: str):
    """
    Genera un token de reset y lo envía por email.
    Si el email no existe, NO lo revela — responde igual.
    Token expira en 1 hora.
    """
    user = get_user_by_email(email)
    if user:
        token = generate_secure_token()  # 32 bytes random
        save_reset_token(user.id, token, expires=now() + timedelta(hours=1))
        send_email(
            to=email,
            subject="Restablecer contraseña — FinPlan CWL",
            body=f"Link válido por 1 hora: {APP_URL}/reset-password?token={token}"
        )
    # Respuesta siempre igual, exista o no el email:
    return {"message": "Si el email existe, recibirás un enlace en minutos."}

def reset_password(token: str, new_password: str):
    """Valida token y actualiza password. Resetea intentos fallidos."""
    record = get_reset_token(token)
    if not record or record.expires < now() or record.used:
        raise AuthError("Token inválido o expirado")

    validate_password_strength(new_password)  # mínimo 8 chars, 1 mayúscula, 1 número
    user = get_user(record.user_id)
    user.password_hash = bcrypt.hash(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    record.used = True
    save(user, record)
    log_audit(user.id, 'PASSWORD_RESET')
```

### 27.6 Modelo de datos

```python
class PasswordResetToken(Base):
    __tablename__ = 'password_reset_tokens'

    id: UUID
    user_id: UUID
    token: str          # hash del token (no guardar el token en texto plano)
    expires_at: datetime
    used: bool
    created_at: datetime
    ip_requested_from: str


class UserSession(Base):
    """Sesiones activas — permite invalidar todas las sesiones de un usuario."""
    __tablename__ = 'user_sessions'

    id: UUID
    user_id: UUID
    jwt_jti: str        # JWT ID único — para blacklist si se hace logout
    created_at: datetime
    expires_at: datetime
    ip_address: str
    user_agent: str
    is_active: bool
```

### 27.7 Vista de login — UI

```
┌─────────────────────────────────────────┐
│                                         │
│         FinPlan CWL                     │
│                                         │
│  Email                                  │
│  ┌─────────────────────────────────┐    │
│  │ usuario@crcollection.com        │    │
│  └─────────────────────────────────┘    │
│                                         │
│  Contraseña                             │
│  ┌─────────────────────────────────┐    │
│  │ ••••••••••••         [👁]        │    │
│  └─────────────────────────────────┘    │
│                                         │
│  [        Ingresar        ]             │
│                                         │
│  ¿Olvidaste tu contraseña?              │
│                                         │
│  ─────────────────────────────────      │
│  ⚠️  Intentos fallidos: 1/3             │  ← aparece tras 1er fallo
│  Te quedan 2 intentos.                  │
└─────────────────────────────────────────┘

Estado bloqueado:
│  🔒 Cuenta bloqueada por seguridad      │
│  Intenta de nuevo en 28 minutos         │
│  ¿No fuiste tú? Contacta al admin       │
```

### 27.8 Panel de administración de usuarios

```
USUARIOS — FinPlan CWL                    [+ Nuevo usuario]

Email                    Nombre           Rol     Propiedad  Estado     Último login
──────────────────────   ───────────────  ──────  ─────────  ─────────  ────────────
ronald@crcollection.com  Ronald Fallas    ADMIN   CWL        ✅ Activo  Hoy 09:42
biskmark@crc.com         Biskmark Rod.    FINANCE CWL        ✅ Activo  Ayer 16:20
luz@crcollection.com     Luz Leiva        FINANCE CWL        ✅ Activo  Hoy 08:15
usuario@test.com         Test User        VIEWER  CWL        🔒 Bloq.   Hoy 10:01  [Desbloquear]

[🔒 Bloq.] = bloqueado por 3 intentos fallidos
[Desbloquear] = admin puede desbloquear manualmente
```

### 27.9 Endpoints de autenticación

```
POST /api/auth/login/                 email + password → JWT token
POST /api/auth/logout/                invalidar sesión
POST /api/auth/refresh/               renovar token antes de expirar
POST /api/auth/forgot-password/       solicitar reset por email
POST /api/auth/reset-password/        token + nuevo password

GET  /api/users/                      listar usuarios (ADMIN only)
POST /api/users/                      crear usuario (ADMIN only)
PUT  /api/users/{id}/                 editar usuario (ADMIN only)
PUT  /api/users/{id}/unlock/          desbloquear cuenta (ADMIN only)
PUT  /api/users/{id}/deactivate/      desactivar cuenta (ADMIN only)
GET  /api/users/{id}/audit-log/       historial de acciones del usuario
```

### 27.10 Tests de seguridad

```python
def test_lockout_after_3_failures():
    """3 intentos fallidos → cuenta bloqueada."""
    for i in range(3):
        with pytest.raises(AuthError):
            authenticate('user@test.com', 'wrong_password', ip='1.2.3.4')
    user = get_user_by_email('user@test.com')
    assert user.locked_until > now()
    assert user.failed_attempts == 3

def test_correct_attempts_left_message():
    """El mensaje muestra cuántos intentos quedan."""
    authenticate_fail('user@test.com')  # 1er fallo
    err = get_last_error()
    assert '2 intentos' in err.message

    authenticate_fail('user@test.com')  # 2do fallo
    err = get_last_error()
    assert '1 intento' in err.message

def test_lockout_clears_after_30_minutes():
    """Después de 30 min el bloqueo se libera automáticamente."""
    lock_user('user@test.com')
    travel_time(minutes=31)
    result = authenticate('user@test.com', 'correct_password', ip='1.2.3.4')
    assert result.token is not None

def test_successful_login_resets_counter():
    """Login exitoso después de 2 fallos resetea el contador."""
    authenticate_fail('user@test.com')
    authenticate_fail('user@test.com')
    authenticate('user@test.com', 'correct_password', ip='1.2.3.4')
    user = get_user_by_email('user@test.com')
    assert user.failed_attempts == 0

def test_email_not_revealed_on_wrong_email():
    """Si el email no existe, el mensaje es igual que si el password es incorrecto."""
    err1 = get_error(lambda: authenticate('noexiste@test.com', 'pass', ip='1.2.3.4'))
    err2 = get_error(lambda: authenticate('real@test.com', 'wrongpass', ip='1.2.3.4'))
    assert err1.message == err2.message  # no revelar si el email existe

def test_viewer_cannot_edit():
    """Un usuario VIEWER no puede editar checkbooks."""
    set_current_user(viewer_user)
    with pytest.raises(PermissionError):
        update_opex_entry(entry_id, month=1, amount=Decimal('500'))

def test_admin_can_unlock():
    """Un ADMIN puede desbloquear una cuenta bloqueada."""
    lock_user('blocked@test.com')
    admin_unlock('blocked@test.com', admin_user)
    user = get_user_by_email('blocked@test.com')
    assert user.locked_until is None
    assert user.failed_attempts == 0
```

---

## 28. SEGURIDAD DE BASE DE DATOS, BACKUPS Y RECUPERACIÓN

### 28.1 Las tres capas de protección

```
CAPA 1 — Protección contra ataques externos
CAPA 2 — Backups diarios automáticos
CAPA 3 — Recuperación de errores del usuario
```

### 28.2 Capa 1 — Protección contra ataques externos

```python
# NUNCA concatenar strings en queries — siempre ORM o bind params
# ❌ f"SELECT * FROM users WHERE email = '{email}'"
# ✅ db.query(User).filter(User.email == email).first()

# .env — NUNCA commitear a git
# DATABASE_URL, SECRET_KEY, SMTP_PASSWORD

# Usuario PostgreSQL con permisos mínimos (no superusuario)
# GRANT SELECT, INSERT, UPDATE, DELETE — NO CREATE, NO DROP

# Rate limiting: 10 intentos login/min por IP, 60 req/min general
# Headers: X-Frame-Options, X-XSS-Protection, HSTS, CSP
```

### 28.3 Capa 2 — Backups diarios automáticos

Estrategia de retención:
```
Diario   (2:00 AM CR)  → retener 30 días
Semanal  (Dom 3:00 AM) → retener 12 semanas
Mensual  (Día 1, 4 AM) → retener 12 meses
```

Script de backup automático (cron `0 2 * * *`):
```bash
#!/bin/bash
# scripts/backup_daily.sh
source /app/.env
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="finplan_cwl_${DATE}.sql.gz"

PGPASSWORD=$DB_PASSWORD pg_dump \
  -h $DB_HOST -U $DB_USER -d $DB_NAME \
  --no-owner --no-privileges --clean --if-exists \
  | gzip > "/backups/daily/$FILENAME"

# Verificar que el archivo existe y no está vacío
[ -s "/backups/daily/$FILENAME" ] || { echo "BACKUP FAILED"; exit 1; }

# Limpiar backups con más de 30 días
find /backups/daily -name "*.sql.gz" -mtime +30 -delete

# Sincronizar a nube (Google Drive, S3, etc.)
sync_to_cloud "/backups/daily/$FILENAME"
echo "Backup OK: $FILENAME"
```

Restaurar desde backup:
```bash
#!/bin/bash
# scripts/restore_backup.sh <archivo>
source /app/.env
gunzip -c $1 | PGPASSWORD=$DB_PASSWORD psql \
  -h $DB_HOST -U $DB_USER -d $DB_NAME
echo "Restauración completada desde: $1"
```

### 28.4 Capa 3 — Recuperación de errores del usuario

**Soft delete — nunca borrar permanentemente:**
```python
class SoftDeleteMixin:
    deleted_at: datetime    # null = activo
    deleted_by: UUID

# Al borrar: marcar como deleted, no DELETE real
# El admin puede restaurar desde el panel en los últimos 30 días
```

**Historial de cambios en checkbooks:**
```python
class ChangeHistory(Base):
    __tablename__ = 'change_history'
    id: UUID
    table_name: str         # 'opex_entries', 'payroll_concept_entries'
    record_id: UUID
    field_name: str
    old_value: str          # valor anterior
    new_value: str          # valor nuevo
    changed_by: UUID
    changed_at: datetime
    scenario_id: UUID
    month: int
    action: str             # 'UPDATE' | 'DELETE' | 'INSERT'
    # Retener 90 días — el usuario puede restaurar cualquier cambio
```

**Snapshots de escenario — punto de restauración manual:**
```python
class ScenarioSnapshot(Base):
    __tablename__ = 'scenario_snapshots'
    id: UUID
    scenario_id: UUID
    name: str               # 'Antes de ajuste planilla marzo'
    data_json: str          # estado completo del escenario
    created_by: UUID
    created_at: datetime

# El usuario crea un snapshot antes de cambios grandes
# Si algo sale mal, restaura el snapshot en un clic
```

### 28.5 Panel de recuperación en el UI

```
HISTORIAL DE CAMBIOS — OPEX F&B

Fecha       Usuario      Campo          Antes   Después   Acción
──────────  ───────────  ─────────────  ──────  ────────  ──────────────
Hoy 10:42   Biskmark R.  7065 Feb       $450    $550      UPDATE  [↩ Restaurar]
Hoy 09:15   Luz Leiva    7060 Mar       $500    $0        UPDATE  [↩ Restaurar]

──────────────────────────────────────────────────────────────────────────
SNAPSHOTS — Budget 2026                             [+ Crear snapshot]

Nombre                           Creado           Tamaño
───────────────────────────────  ───────────────  ──────
Antes de ajuste planilla marzo   Mar 15 14:30     245 KB  [↩ Restaurar]
Versión inicial Budget aprobado  Ene 10 09:00     198 KB  [↩ Restaurar]
```

### 28.6 Endpoints de administración

```
# Backups (solo ADMIN)
GET  /api/admin/backups/                     lista de backups
POST /api/admin/backups/create/              backup manual ahora
GET  /api/admin/backups/{file}/download/     descargar backup

# Historial de cambios
GET  /api/admin/changes/?days=7              cambios recientes
POST /api/admin/changes/{id}/restore/        restaurar un cambio

# Snapshots
GET  /api/scenarios/{id}/snapshots/          lista
POST /api/scenarios/{id}/snapshots/          crear
POST /api/scenarios/{id}/snapshots/{sid}/restore/  restaurar

# Registros borrados
GET  /api/admin/deleted-records/             borrados últimos 30 días
POST /api/admin/deleted-records/{id}/restore/ restaurar
```

## 29. INFRAESTRUCTURA — SERVIDOR EN LA NUBE

### 29.1 Arquitectura en servidor externo

El sistema vive en un servidor cloud pagado. Esto ya da protección importante — los proveedores tienen equipos de seguridad dedicados, data centers físicamente seguros y redundancia imposible de tener en un servidor propio.

```
INTERNET
    |
    v
FIREWALL DEL PROVEEDOR (bloquea puertos)
    |
    v
SERVIDOR CLOUD (Ubuntu 22.04)
    |-- Nginx (SSL + reverse proxy — punto de entrada único)
    |-- Next.js frontend (puerto 3000, solo local)
    |-- FastAPI backend (puerto 8000, solo local)
    `-- PostgreSQL (puerto 5432, solo localhost — NUNCA expuesto a internet)
```

### 29.2 Proveedores recomendados

```
DigitalOcean (recomendado para empezar)
  Droplet básico:     $24/mes  (2 vCPU, 4GB RAM, 80GB SSD)
  Backups servidor:   $4.80/mes (snapshot semanal automático)
  Managed PostgreSQL: $15/mes  (backups automáticos incluidos)
  Total:              ~$44/mes

Hetzner (más económico)
  Server CX21:        ~$8/mes  (2 vCPU, 4GB RAM)
  Con backups:        +20%
  Total:              ~$10/mes
```

### 29.3 Qué protección da el proveedor (gratis con el servidor)

```
Protección física del data center      → nadie entra físicamente
Protección DDoS básica                 → absorbe ataques de volumen
Snapshots del servidor completo        → restaurar todo en 15-30 min
Red privada entre servicios            → PostgreSQL no expuesto
Panel de alertas (CPU, disco, memoria) → monitoreo básico incluido
```

### 29.4 Lo que hay que configurar en el servidor

```bash
# 1. Firewall (UFW)
sudo ufw default deny incoming
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 80/tcp    # HTTP (redirige a HTTPS)
sudo ufw allow 22/tcp    # SSH solo desde tu IP
# Puerto 5432 (PostgreSQL) CERRADO — acceso solo local
sudo ufw enable

# 2. SSH — solo con llave, nunca con password
# En /etc/ssh/sshd_config:
# PasswordAuthentication no
# PubkeyAuthentication yes

# 3. SSL gratuito con Let's Encrypt (renovación automática)
certbot --nginx -d finplan.crcollection.com

# 4. PostgreSQL escucha solo en localhost
# En postgresql.conf: listen_addresses = 'localhost'

# 5. Actualizaciones de seguridad automáticas
sudo apt install unattended-upgrades
```

### 29.5 Los 4 niveles de backup

Con servidor cloud, hay 4 niveles independientes de recuperación:

```
Nivel 1 — Snapshot del servidor (proveedor)
  Frecuencia: semanal automático
  Recupera:   servidor completo (código + DB + config)
  Tiempo:     15-30 minutos
  Costo:      +20% del servidor (~$5/mes)

Nivel 2 — pg_dump diario (sección 28)
  Frecuencia: diario 2:00 AM
  Recupera:   solo la base de datos
  Tiempo:     5-10 minutos
  Costo:      almacenamiento nube (~$1-2/mes)

Nivel 3 — Snapshot de escenario (sección 28)
  Frecuencia: manual antes de cambios grandes
  Recupera:   un escenario completo
  Tiempo:     segundos
  Costo:      nada (en la misma DB)

Nivel 4 — Historial de cambios (sección 28)
  Frecuencia: automático en cada edición
  Recupera:   un campo específico cambiado por error
  Tiempo:     inmediato desde el UI
  Costo:      nada
```

### 29.6 Variables de entorno en producción

```bash
# /app/.env — NUNCA sale del servidor, nunca va a git
chmod 600 /app/.env   # solo el usuario de la app puede leerlo

DATABASE_URL=postgresql://finplan_app:PASSWORD@localhost/finplan_cwl
SECRET_KEY=CLAVE_ALEATORIA_256_BITS
APP_URL=https://finplan.crcollection.com
ENVIRONMENT=production
SMTP_USER=no-reply@crcollection.com
SMTP_PASSWORD=PASSWORD_EMAIL
BACKUP_BUCKET=finplan-cwl-backups
```

### 29.7 Monitoreo

```
UptimeRobot (gratuito):
  → Ping cada 5 min, alerta por email/WhatsApp si el sistema cae

Alertas a configurar:
  → Servidor caído         → alerta inmediata
  → Disco > 80% lleno      → limpiar backups viejos
  → Backup falló           → alerta el mismo día
  → Certificado SSL expira → 30 días antes (Let's Encrypt renueva automático)
```

### 29.8 Checklist de despliegue inicial

```
Servidor:
  ☐ Ubuntu 22.04 LTS
  ☐ SSH solo con llave (sin password)
  ☐ Firewall UFW: solo 80, 443, 22 desde tu IP
  ☐ Backups automáticos del proveedor activados
  ☐ Actualizaciones de seguridad automáticas

Base de datos:
  ☐ PostgreSQL escuchando solo en localhost
  ☐ Usuario con permisos mínimos (no superusuario)
  ☐ Backups diarios con cron
  ☐ Backup inicial creado y restauración verificada

Aplicación:
  ☐ .env con permisos 600
  ☐ HTTPS con Let's Encrypt
  ☐ Nginx con headers de seguridad
  ☐ Rate limiting activado

Post-lanzamiento:
  ☐ Usuario ADMIN creado
  ☐ UptimeRobot configurado
  ☐ Verificar que PostgreSQL NO es accesible desde internet
  ☐ Test de backup y restauración
```

---

## 30. MODELO MULTI-PROPIEDAD

### 30.1 Las propiedades del grupo

El sistema arranca con CWL como piloto. Una vez funcionando, se clona para cada propiedad. Todas comparten la misma estructura, el mismo catálogo USALI y el mismo motor de cálculo.

```
hotel_id   Nombre                          Estado
─────────  ──────────────────────────────  ──────────────
CWL        Corcovado Wilderness Lodge      PILOTO
OJO        Ojochal Garden Villas           Clonar de CWL
OXY        Oxygen Jungle Villas            Clonar de CWL
AMR        Amarena Canvas Hotel            Clonar de CWL
GUA        Hotel Guanacaste               Clonar de CWL
PAV        Hotel Pavones                   Clonar de CWL
COR        Hotel Corcovado                 Clonar de CWL
SJO        Hotel Down Town San José        Clonar de CWL
```

### 30.2 Master Data de Hotel — completo y editable

Todos los campos son editables por un ADMIN en cualquier momento. El `hotel_id` (código corto) es el único campo que no cambia — es la clave interna del sistema.

```python
class Hotel(Base):
    __tablename__ = 'hotels'

    # ── IDENTIFICACIÓN INTERNA ─────────────────────────────────
    id: str             # 'CWL' — INMUTABLE, clave del sistema
    active: bool        # False = desactivado (no aparece en el sistema)
    is_pilot: bool      # True solo para CWL
    cloned_from: str    # 'CWL' para todas las demás
    created_at: datetime
    updated_at: datetime
    updated_by: UUID

    # ── DATOS GENERALES (editables) ────────────────────────────
    display_name: str       # nombre para mostrar en el UI — EDITABLE
                            # ej: 'Corcovado Wilderness Lodge'
    short_name: str         # nombre corto para topbar — EDITABLE
                            # ej: 'Corcovado WL'
    hotel_type: str         # tipo de hotel — EDITABLE
                            # 'LODGE' | 'BOUTIQUE' | 'RESORT' |
                            # 'HOSTEL' | 'APART_HOTEL' | 'GLAMPING' | 'OTHER'

    # ── DATOS LEGALES (editables) ──────────────────────────────
    legal_name: str         # nombre jurídico completo — EDITABLE
                            # ej: 'Corcovado Holding SCP S.R.L.'
    fiscal_id: str          # cédula jurídica — EDITABLE
                            # ej: '3-102-XXXXXX'
    legal_entity_type: str  # tipo de entidad — EDITABLE
                            # 'SRL' | 'SA' | 'SCP' | 'FUNDACION' | 'OTHER'

    # ── REPRESENTANTES LEGALES (editables) ─────────────────────
    # Lista de representantes (puede haber más de uno)
    # Se maneja en tabla separada HotelRepresentative

    # ── UBICACIÓN (editable) ───────────────────────────────────
    address: str            # dirección física — EDITABLE
    province: str           # provincia CR — EDITABLE
                            # 'San José' | 'Alajuela' | 'Cartago' | 'Heredia' |
                            # 'Guanacaste' | 'Puntarenas' | 'Limón'
    canton: str             # cantón — EDITABLE
    district: str           # distrito — EDITABLE
    country: str            # 'Costa Rica' (default)
    latitude: Decimal       # coordenadas GPS — EDITABLE
    longitude: Decimal
    google_maps_url: str    # enlace a Google Maps — EDITABLE

    # ── OPERACIÓN (editables) ──────────────────────────────────
    total_rooms: int        # total de habitaciones — EDITABLE
    total_employees: int    # cantidad de empleados — EDITABLE
    currency: str           # 'USD' (todas operan en USD)
    guests_per_room_ratio: Decimal  # CWL=1.8, puede variar — EDITABLE
    fiscal_year_start: int  # mes inicio año fiscal (default: 1=enero)
    timezone: str           # 'America/Costa_Rica'

    # ── CONTACTO (editables) ───────────────────────────────────
    website: str
    phone: str
    email_general: str
    gm_name: str            # nombre del General Manager — EDITABLE
    gm_email: str
    finance_contact_name: str
    finance_contact_email: str


class HotelRepresentative(Base):
    """
    Representantes legales del hotel.
    Un hotel puede tener varios representantes con distintos roles.
    Editables en cualquier momento.
    """
    __tablename__ = 'hotel_representatives'

    id: UUID
    hotel_id: str           # FK → hotels
    full_name: str          # nombre completo — EDITABLE
    id_number: str          # cédula o pasaporte — EDITABLE
    nationality: str        # nacionalidad — EDITABLE
    role: str               # rol legal — EDITABLE
                            # 'PRESIDENTE' | 'SECRETARIO' | 'TESORERO' |
                            # 'APODERADO' | 'GERENTE' | 'SOCIO' | 'OTHER'
    is_active: bool         # True = representante actual
    notes: str              # observaciones
    created_at: datetime
    updated_at: datetime
```

### 30.3 Vista de Master Data en el UI

```
MASTER DATA — Corcovado Wilderness Lodge       [Editar] [Guardar]
══════════════════════════════════════════════════════════════════

DATOS GENERALES
  Nombre para mostrar:    [Corcovado Wilderness Lodge      ]  ← editable
  Nombre corto:           [Corcovado WL                    ]  ← editable
  Tipo de hotel:          [Lodge              v]              ← dropdown

DATOS LEGALES
  Nombre jurídico:        [Corcovado Holding SCP S.R.L.    ]  ← editable
  Cédula jurídica:        [3-102-XXXXXX                    ]  ← editable
  Tipo de entidad:        [S.C.P.             v]              ← dropdown

REPRESENTANTES LEGALES                         [+ Agregar representante]
  ┌─────────────────────────────────────────────────────────────┐
  │ Nombre          Cédula      Rol           Estado    Acción  │
  │ ─────────────── ─────────── ───────────── ──────── ───────  │
  │ Juan Pérez      1-1234-5678 Presidente    Activo   [Editar] │
  │ María García    1-9876-5432 Secretaria    Activo   [Editar] │
  │ Luis Rodríguez  2-3456-7890 Apoderado     Activo   [Editar] │
  └─────────────────────────────────────────────────────────────┘

UBICACIÓN
  Dirección:              [Bahía Drake, Osa                ]  ← editable
  Provincia:              [Puntarenas         v]              ← dropdown
  Cantón:                 [Osa                             ]  ← editable
  Distrito:               [Drake                           ]  ← editable
  País:                   [Costa Rica                      ]
  Google Maps:            [https://maps.google.com/...     ]  ← editable

OPERACIÓN
  Total habitaciones:     [30                              ]  ← editable
  Total empleados:        [45                              ]  ← editable
  Ratio huéspedes/hab:    [1.80                            ]  ← editable
  General Manager:        [Carlos Mora                     ]  ← editable
  Email GM:               [gm@corcovado.com                ]  ← editable

IDENTIFICADOR DEL SISTEMA
  Hotel ID:               CWL  (no editable — clave interna)
  Creado:                 Ene 10, 2026
  Última actualización:   Hoy 10:42 por Ronald Fallas
```

### 30.4 Separación de datos — hotel_id en todo

Todas las tablas tienen `hotel_id`. Los datos nunca se mezclan entre propiedades.

```
COMPARTIDO entre todas las propiedades:
  - Catálogo de cuentas (accounts) — mismo USALI para el grupo
  - Usuarios (users) — un usuario accede a varias propiedades

ESPECÍFICO por propiedad (filtrado por hotel_id):
  - Master data (Hotel + HotelRepresentative)
  - Escenarios (Budget, Forecast, Actual)
  - Tipos de habitación y tarifas
  - Planilla (posiciones y salarios)
  - Checkbooks (OPEX, CoS, ingresos)
  - Allocations (Cafetería y Lavandería)
  - Calendario de planning
  - Historial de grupos
  - Tipos de cambio
```

### 30.5 Acceso por propiedad — permisos

```python
class UserRole(Base):
    __tablename__ = 'user_roles'
    id: UUID
    user_id: UUID
    hotel_id: str       # a qué propiedad aplica
    role: str           # 'ADMIN' | 'FINANCE' | 'VIEWER'
    is_active: bool

# Ejemplos reales:
# Ronald (CFO):      ADMIN en todas
# Biskmark (Ctrl):   FINANCE en CWL, FINANCE en OJO
# Gerente CWL:       FINANCE en CWL solamente
# Gerente OXY:       FINANCE en OXY solamente
# Dueños:            VIEWER en todas
# Auditor externo:   VIEWER en CWL solamente
```

### 30.6 UI — selector de propiedad en topbar

```
Si 1 propiedad:   [Corcovado WL]          (sin dropdown)
Si varias:        [Corcovado WL v]

  Dropdown:
    Mis propiedades
    ─────────────────────────────────────
    [x] Corcovado Wilderness Lodge  (CWL)  <- activa
        Ojochal Garden Villas       (OJO)
        Oxygen Jungle Villas        (OXY)
        Amarena Canvas Hotel        (AMR)
    ─────────────────────────────────────
    Ver todas ->                           <- solo ADMIN

Al cambiar: URL cambia /dashboard/CWL -> /dashboard/OJO
Todos los datos se recargan para la propiedad seleccionada.
```

### 30.7 Proceso de clonar CWL para una propiedad nueva

```python
def clone_hotel(source_id, new_id, new_name, total_rooms, room_types):
    """
    QUE SE COPIA desde CWL:
    - Estructura de departamentos
    - Configuracion de allocations
    - Plantilla de checkbooks (montos en 0)
    - Feriados CR del año

    QUE NO SE COPIA:
    - Master data legal (se ingresa manualmente)
    - Tipos de habitacion (especificos del hotel)
    - Planilla, tarifas, montos (se ingresan nuevos)
    """
    hotel = Hotel(id=new_id, display_name=new_name,
                  total_rooms=total_rooms, cloned_from=source_id)
    for rt in room_types:
        RoomTypeConfig(hotel_id=new_id, **rt)
    clone_allocation_configs(source_id, new_id)
    clone_checkbook_templates(source_id, new_id)   # montos en 0
    clone_cr_holidays(source_id, new_id)
    Scenario(hotel_id=new_id, scenario_type='BUDGET',
             version_name=f'Budget {year} - {new_name}', locked=False)
```

Después de clonar, configurar en orden:
```
1. Master data legal (nombre jurídico, cédula, representantes)
2. Tipos de habitación específicos del hotel
3. Tipos de cambio del año
4. Planilla (posiciones y salarios)
5. Checkbooks OPEX (montos específicos)
6. Checkbooks CoS (porcentajes de costo)
7. Revenue (tarifas, canales, ocupación)
8. Allocations (cafetería y lavandería)
9. Recalcular y verificar P&L
```

### 30.8 Dashboard consolidado multi-propiedad

Para CFO y dueños con acceso a varias propiedades:

```
THE COSTA RICA COLLECTION — Abril 2026

               CWL      OJO      OXY      AMR     GRUPO
Revenue        $597K    $234K    $312K    $189K   $1.33M
Ocupacion      55.9%    62.3%    48.1%    71.2%   59.4%
ADR           $631.30  $445.20  $512.80  $385.40 $493.70
GOP           $176K     $67K    $102K     $54K    $399K
Net Profit     $52K     $18K     $31K     $12K    $113K

[Ver detalle]   ->       ->       ->       ->
```

### 30.9 Endpoints de Master Data

```
# Hotel
GET  /api/hotels/                      lista (solo los del usuario)
GET  /api/hotels/{hotel_id}/           master data completo
PUT  /api/hotels/{hotel_id}/           actualizar master data (ADMIN)
POST /api/hotels/                      crear nuevo hotel (ADMIN)
POST /api/hotels/{hotel_id}/clone/     clonar desde otro (ADMIN)

# Representantes legales
GET  /api/hotels/{hotel_id}/representatives/
POST /api/hotels/{hotel_id}/representatives/
PUT  /api/hotels/{hotel_id}/representatives/{id}/
DEL  /api/hotels/{hotel_id}/representatives/{id}/

# Historial de cambios del master data
GET  /api/hotels/{hotel_id}/history/   ver cambios anteriores
```

### 30.10 Aislamiento de datos — regla crítica

```python
# NUNCA:
db.query(Scenario).all()   # devuelve datos de TODOS los hoteles

# SIEMPRE filtrar por hotel_id:
db.query(Scenario).filter_by(hotel_id=hotel_id).all()

# Middleware en cada request:
def validate_hotel_access(user_id, hotel_id, min_role='VIEWER'):
    role = get_user_role(user_id, hotel_id)
    if not role:
        raise PermissionError(f"Sin acceso a {hotel_id}")
```

### 30.11 Tests

```python
def test_hotel_name_editable():
    """El nombre del hotel es editable sin afectar el hotel_id."""
    update_hotel('CWL', display_name='Corcovado Wilderness Lodge & Spa')
    hotel = get_hotel('CWL')
    assert hotel.id == 'CWL'                                    # inmutable
    assert hotel.display_name == 'Corcovado Wilderness Lodge & Spa'

def test_representative_crud():
    """Se pueden agregar, editar y desactivar representantes."""
    rep = add_representative('CWL', name='Juan Pérez',
                             id_number='1-1234-5678', role='PRESIDENTE')
    assert rep.is_active == True
    update_representative(rep.id, role='APODERADO')
    deactivate_representative(rep.id)
    assert get_representative(rep.id).is_active == False

def test_user_sees_only_assigned_hotels():
    user = create_user({'CWL': 'FINANCE', 'OJO': 'VIEWER'})
    hotels = get_user_hotels(user.id)
    ids = {h.id for h in hotels}
    assert 'CWL' in ids and 'OJO' in ids
    assert 'OXY' not in ids

def test_unauthorized_hotel_returns_403():
    user = create_user({'CWL': 'FINANCE'})
    response = client.get('/api/scenarios/OXY/', headers=auth(user))
    assert response.status_code == 403

def test_data_isolation():
    cwl_ids = {s.id for s in get_scenarios('CWL')}
    ojo_ids = {s.id for s in get_scenarios('OJO')}
    assert cwl_ids.isdisjoint(ojo_ids)

def test_master_data_has_audit_trail():
    """Cada cambio al master data queda registrado."""
    update_hotel('CWL', display_name='Nuevo Nombre')
    history = get_hotel_history('CWL')
    assert len(history) > 0
    assert history[0].field_name == 'display_name'
    assert history[0].old_value == 'Corcovado Wilderness Lodge'
```

---



### 30.2 Modelo de Hotel expandido

```python
class Hotel(Base):
    __tablename__ = 'hotels'

    id: str             # 'CWL', 'OJO', 'OXY', 'AMR', etc.
    name: str           # nombre completo
    short_name: str     # nombre corto para UI
    legal_entity: str   # SRL, SA, SCP, etc.
    location: str       # zona geográfica
    total_rooms: int
    active: bool
    is_pilot: bool      # True solo para CWL
    cloned_from: str    # 'CWL' para todas las demás
    guests_per_room_ratio: Decimal  # CWL=1.8, puede variar por hotel
    gm_name: str
    gm_email: str
    created_at: datetime
```

### 30.3 Separación de datos — hotel_id en todo

Todas las tablas tienen `hotel_id`. Los datos nunca se mezclan entre propiedades.

```
COMPARTIDO entre todas las propiedades:
  - Catálogo de cuentas (accounts) — mismo USALI para el grupo
  - Usuarios (users) — un usuario puede acceder a varias propiedades

ESPECÍFICO por propiedad (filtrado por hotel_id):
  - Escenarios (Budget, Forecast, Actual)
  - Tipos de habitación y tarifas
  - Planilla (posiciones y salarios)
  - Checkbooks (OPEX, CoS, ingresos)
  - Allocations (Cafetería y Lavandería)
  - Calendario de planning
  - Historial de grupos
  - Tipos de cambio
```

### 30.4 Acceso por propiedad — permisos

Un usuario puede tener distintos roles en distintas propiedades:

```python
class UserRole(Base):
    __tablename__ = 'user_roles'
    id: UUID
    user_id: UUID
    hotel_id: str       # a qué propiedad aplica
    role: str           # 'ADMIN' | 'FINANCE' | 'VIEWER'
    is_active: bool

# Ejemplos reales:
# Ronald (CFO):      ADMIN en todas
# Biskmark (Ctrl):   FINANCE en CWL, FINANCE en OJO
# Gerente CWL:       FINANCE en CWL solamente
# Gerente OXY:       FINANCE en OXY solamente
# Dueños:            VIEWER en todas
# Auditor externo:   VIEWER en CWL solamente
```

### 30.5 UI — selector de propiedad en topbar

```
Si 1 propiedad:   [Corcovado WL]          (sin dropdown)
Si varias:        [Corcovado WL v]

  Dropdown:
    Mis propiedades
    ---------------------------
    [x] Corcovado Wilderness Lodge  (CWL)  <- activa
        Ojochal Garden Villas       (OJO)
        Oxygen Jungle Villas        (OXY)
        Amarena Canvas Hotel        (AMR)
    ---------------------------
    Ver todas ->                           <- solo ADMIN

Al cambiar de propiedad -> URL cambia /dashboard/CWL -> /dashboard/OJO
Todos los datos se recargan para la nueva propiedad seleccionada.
```

### 30.6 Proceso de clonar CWL para una propiedad nueva

```python
def clone_hotel(source_id, new_id, new_name, total_rooms, room_types):
    """
    QUE SE COPIA desde CWL:
    - Estructura de departamentos (mismos codes)
    - Configuracion de allocations (Cafeteria y Lavanderia)
    - Plantilla de checkbooks OPEX (estructura de cuentas, montos en 0)
    - Plantilla de checkbooks CoS (estructura, montos en 0)
    - Feriados CR del año en curso

    QUE NO SE COPIA (especifico por propiedad):
    - Tipos de habitacion -> se configuran nuevos
    - Tarifas y ocupacion -> se ingresan nuevas
    - Planilla -> distintos empleados
    - Montos en checkbooks -> en 0, usuario los llena
    - Escenarios -> se crean nuevos
    - Historial de grupos -> vacio
    """
    hotel = Hotel(id=new_id, name=new_name,
                  total_rooms=total_rooms, cloned_from=source_id)
    for rt in room_types:
        RoomTypeConfig(hotel_id=new_id, **rt)
    clone_allocation_configs(source_id, new_id)
    clone_checkbook_templates(source_id, new_id)   # montos en 0
    clone_cr_holidays(source_id, new_id)
    Scenario(hotel_id=new_id, scenario_type='BUDGET',
             version_name=f'Budget {year} - {new_name}', locked=False)
```

Después de clonar, el usuario configura en este orden:
```
1. Tipos de habitacion de ese hotel (distinto a CWL)
2. Tipos de cambio del año
3. Planilla (posiciones y salarios del hotel)
4. Checkbooks OPEX (montos especificos)
5. Checkbooks CoS (porcentajes de costo)
6. Revenue (tarifas, canales, ocupacion)
7. Allocations (cafeteria y lavanderia)
8. Recalcular y verificar P&L
```

### 30.7 Dashboard consolidado multi-propiedad

Para CFO y dueños con acceso a varias propiedades:

```
THE COSTA RICA COLLECTION — Abril 2026

               CWL      OJO      OXY      AMR     GRUPO
Revenue        $597K    $234K    $312K    $189K   $1.33M
Ocupacion      55.9%    62.3%    48.1%    71.2%   59.4%
ADR           $631.30  $445.20  $512.80  $385.40 $493.70
GOP           $176K     $67K    $102K     $54K    $399K
Net Profit     $52K     $18K     $31K     $12K    $113K

[Ver detalle]   ->       ->       ->       ->
```

### 30.8 Aislamiento de datos — regla critica

```python
# NUNCA en ningun endpoint:
# db.query(Scenario).all()  <- devuelve datos de TODOS los hoteles

# SIEMPRE filtrar por hotel_id:
# db.query(Scenario).filter_by(hotel_id=hotel_id).all()

# Middleware que valida acceso en cada request:
def validate_hotel_access(user_id, hotel_id, min_role='VIEWER'):
    role = get_user_role(user_id, hotel_id)
    if not role:
        raise PermissionError(f"Sin acceso a {hotel_id}")
```

### 30.9 Tests de aislamiento

```python
def test_user_sees_only_assigned_hotels():
    user = create_user({'CWL': 'FINANCE', 'OJO': 'VIEWER'})
    hotels = get_user_hotels(user.id)
    ids = {h.id for h in hotels}
    assert 'CWL' in ids and 'OJO' in ids
    assert 'OXY' not in ids   # sin acceso

def test_unauthorized_hotel_returns_403():
    user = create_user({'CWL': 'FINANCE'})
    response = client.get('/api/scenarios/OXY/', headers=auth(user))
    assert response.status_code == 403

def test_data_isolation():
    cwl_ids = {s.id for s in get_scenarios('CWL')}
    ojo_ids = {s.id for s in get_scenarios('OJO')}
    assert cwl_ids.isdisjoint(ojo_ids)   # ningun escenario en comun

def test_clone_creates_zero_amounts():
    clone_hotel('CWL', 'OJO', 'Ojochal Garden Villas', 10, [])
    for entry in get_opex_entries('OJO'):
        assert entry.jan == Decimal('0.00')   # montos en 0

def test_admin_accesses_all_hotels():
    admin = create_admin_user()
    hotels = get_user_hotels(admin.id)
    ids = {h.id for h in hotels}
    assert ids == {'CWL','OJO','OXY','AMR','GUA','PAV','COR','SJO'}
```

---


---


 cuando cambia cualquier assumption de ingresos → recalcular revenue → propagar a FinancialEntry → recalcular P&L. Esto debe ser transparente para el usuario.
- **Los importadores de actuals son la parte más delicada** — los headers de los Excel están en filas variables, detectarlos dinámicamente con `find_header_row()`.
- **Nunca modificar los archivos en `data/raw/`** — son los originales del cliente, solo lectura.
- **El engine (P&L, revenue, payroll, allocation) es puro Python sin UI** — mantenerlo así para facilitar tests unitarios.
- **La propiedad CWL tiene Octubre = 0 en el Budget 2026** — porque el usuario ingresó occupancy=0% y FTE=0 para ese mes. Octubre NO está hardcodeado en el sistema. Si el usuario decide abrir en octubre, solo cambia los inputs (occupancy%, FTE) y presiona Recalcular — el sistema produce los números correctamente sin ningún cambio en el código.
- **Cafetería y Lavandería siempre deben ser $0 neto** — si no son $0, hay un bug en allocation.
- **Salarios en CRC se convierten con el TC del mes** — TC puede variar mes a mes dentro del mismo escenario.
- **Los archivos de referencia viven en:** `data/raw/` según se especifica en la sección 2.
- **Los números del archivo Budget2026_Revenue_CORCO.xlsx son la referencia de validación** — los tests deben verificar contra esos valores.
