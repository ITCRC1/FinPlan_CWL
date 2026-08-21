# Plan — Master Data de Provisioning (habilitación por propiedad)

> **Estado:** PLANIFICADO. No iniciado. Decisiones de owner pendientes (§7).
> **Fecha:** 2026-06-29 · **Base:** 2 auditorías de diseño (workflows, 9 agentes) + decisiones del owner.
> **Qué resuelve:** en el provisioning de cada propiedad, un **check** para TODO — qué tabs/módulos, reportes y configuraciones ve, y qué departamentos están activos en cada dimensión financiera. Ej.: *Área Recreativa solo en Amarena*.
> **Depende de:** [[MULTIPROPERTY_PLAN]] (hotel_id obligatorio + contexto de hotel activo). Encaja con [[I18N_PLAN]] (idioma = otro parámetro del mismo provisioning).

---

## 1. Concepto: UNA master data, DOS granularidades

| Capa | Controla | Unidad | Tablas |
|------|----------|--------|--------|
| **GRUESA — Registro de Features + Entitlement** | Qué **módulos/tabs, reportes, configs** ve la propiedad (visibilidad/alcanzabilidad) | `(hotel, feature) → on/off`, en árbol | `feature_registry` + `hotel_feature_entitlement` |
| **FINA — Matriz Depto × Dimensión** | Qué **deptos** están activos en Ingreso/Planilla/OPEX/Costos/Propiedad (alcance de datos) | `(hotel, unidad, dimensión) → on/off` | `department_catalog` + `dept_enablement` |

**Principios (ambas):**
- **Filtran VISIBILIDAD/ALCANCE — nunca el cálculo.** El motor y el mapeo (`account_mapping`/`report_line_config`) siguen compartidos (M2). Un reporte oculto **igual computa bien** si se reactiva.
- **Default-ON** sembrado del estado actual → el día que se despliega, CWL no cambia en nada.
- **Provisioning desde plantilla:** la propiedad arranca con el estándar completo y se **desmarca** lo que no aplica. CWL = todo habilitado.
- **Composición jerárquica:** si un feature está OFF (grueso), su matriz de deptos es irrelevante (la página no es alcanzable). Si está ON, la matriz afina qué filas/columnas aparecen dentro.

---

## 2. Capa GRUESA — Registro de Features + Entitlement

### 2.1 Modelo
- **`feature_registry`** (global, sin hotel_id) — catálogo de TODA capacidad. PK `feature_key`; `parent_key` (self-FK), `type` ∈ {module,report,config,feature}, `label_key`, `route`, `display_order`, `is_active`.
  - **~81 filas** sembradas 1:1 del array NAV de `components/TopNav.tsx`: **11 módulos** (dashboard, escenarios, planning, estados-financieros, cashflow-planning, reportes, operation-insight, marketing-insight, master-data, admin) + ~70 hojas.
  - Los headers cosméticos del dropdown (Avance, Ingresos, Planilla, P&L…) **NO son filas**.
  - Stubs "próx." (`master-data.properties`, `admin.audit`) se siembran con `is_active=false`.
- **`hotel_feature_entitlement`** — PK `(hotel_id, feature_key)`, `enabled` bool, `updated_at/by`.
  - **Resolución = default-ON con override de desactivación:** visible sii `registry.is_active=true` AND no existe fila `enabled=false` AND ningún ancestro está deshabilitado.
  - **Cascada padre→hijo en read-time** (no denormalizada): desmarcar "Marketing Insight" oculta sus 4 reportes sin escribir 4 filas.
  - **`is_active`** = "¿feature globalmente lanzado?"; **`entitlement`** = "¿esta propiedad lo quiere?". Un feature a medio construir va con `is_active=false` para que no aparezca en ninguna propiedad.

### 2.2 Dónde se filtra (gating — 3 lugares)
1. **Backend:** `GET /api/hotels/{id}/entitlements` → set efectivo resuelto (la cascada vive en UN solo lugar). Cache por hotel, invalida al escribir.
2. **TopNav** (`components/TopNav.tsx`): filtra el array NAV antes de render (dropea módulos/items deshabilitados y grupos vacíos). Unifica el `disabled:true` actual con el entitlement.
3. **Guard de ruta** (layout/middleware): mapea `pathname → feature_key` y bloquea/redirige si está deshabilitado (evita llegar por URL). El mapa reverso se construye del MISMO fixture derivado del NAV, no por heurística de path.

---

## 3. Capa FINA — Matriz Depto × Dimensión

### 3.1 Modelo
- **`department_catalog`** (global, sin hotel_id) — universo USALI único de deptos. PK `dept_code`; `dept_name`, `name_en`, `name_aliases` (absorbe `gl_detail_importer.dept_code_from_name`), `usali_class`, `default_pl_group`, `pl_kind` (OPERATING|OVERHEAD), `is_revenue_dept`, `is_allocation_source` (0220/0161), `parent_dept_code` (reemplaza `CHECKBOOK_DEPT_CONSOLIDATION`), `display_order`, `active`.
  - **Reemplaza las 3 fuentes fragmentadas:** `pl_engine` (constantes dept→grupo), `gl_detail_importer` (name→code), `cwl-depts.ts` (code→name). Resuelve los conflictos Spa (0130/0140) y Retail/Tienda (0165/0151) **una vez acá**.
  - Sembrado **byte-por-byte** de las constantes actuales → cero cambio día 1.
- **`dept_enablement`** (por propiedad) — UNIQUE `(hotel_id, scope_kind, scope_key, dimension)`, `enabled`.
  - `scope_kind` ∈ {DEPT, REV_LINE, BELOWGOP_LINE}; `dimension` ∈ {REVENUE, PAYROLL, OPEX, COST, PROPERTY}.
  - **ENUM dimensión, NO 5 booleans en una fila de depto** — porque las 5 dimensiones no comparten clave (planilla/opex/costo→dept_code; ingreso→grupo/línea; propiedad→línea below-GOP sin depto). Esparsa: ausencia = default de plantilla. Agregar 6ª dimensión (CAPEX) = nuevo enum, sin migración.
  - **Generaliza** el `participates` de cafetería/lavandería de scope-escenario a scope-hotel × 5 dimensiones.

### 3.2 Las 5 dimensiones
| Dimensión | Unidad | Cómo encaja |
|-----------|--------|-------------|
| **Planilla** | `dept_code` | Limpio. Selector = `catalog ∩ matriz PAYROLL-on`. Es la fuente upstream (allocation init lee depts de planilla). |
| **OPEX** | `dept_code` | Limpio. Selector = `catalog ∩ OPEX-on`. Depto OFF no debe caer en `OTHER_OVERHEAD`. |
| **Costos** | `dept_code` | Limpio pero **3 fuentes** hoy (cost_entries DISTINCT + cwl-depts.ts + `/costs/catalog/` de AccountMapping clase 5). La matriz debe gatear también `/costs/catalog/`. |
| **Ingreso** | grupo/depto vía puente línea↔grupo | **Line-based hoy** (`REVENUE_LINES`), dept-based solo en actuals. NO togglear líneas crudas (re-introduce 4ª fuente). Guardar enablement en el **grupo operativo**; el checkbook renderiza `REVENUE_LINES` filtrado por grupo-on. **Agregar CLUB/AREC a `REVENUE_LINES`** (gap conocido) → así se vuelven toggleables. Actuals (260/270) filtrados por la misma matriz. |
| **Propiedad** (below-GOP, "Gastos de propiedad") | `report_line_code` (no dept) + drivers % | NonOp **no tiene dept_code**; clave por línea (RENT, PROPERTY_INSURANCE, DEPRECIATION, CAPITAL_RESERVE, LARGE_CAPEX…). Habilitar = lista de líneas (propiedad alquilada → RENT on; propia → DEPRECIATION on). Mgmt-fee/royalty/capital-reserve/tax son **drivers calculados** (habilitar = % > 0). |

---

## 4. Provisioning UX (flujo de 2 pasos, una sola área)

Pantalla **"Provisioning / Master Data"** por hotel (reemplaza el stub "próx." `master-data.properties`):

- **Paso 1 — ¿Qué módulos/reportes/configs?** Árbol colapsable de `feature_registry` (11 módulos → hojas), checkboxes con cascada visual. Guarda solo **deltas** (`enabled=false`) → tabla esparsa. Botón **"Copiar de CWL"** para clonar el set como punto de partida.
- **Paso 2 — Para lo activado, ¿qué deptos/dimensiones?** Matriz **filas=depto × 5 columnas** (Ingreso/Planilla/OPEX/Costos/Propiedad), solo mostrada para las familias data-bearing activadas (payroll/opex/costs checkbook, pl-by-dept). Ingreso vivo solo donde `is_revenue_dept`; Propiedad = sección de líneas below-GOP. SUSTAINABILITY = fila Ingreso-only sin dept.

**Defaults:** propiedad nueva arranca del estándar completo (default-ON + sin filas = todo visible); el owner desmarca. **CWL backfill:** capa gruesa NO necesita filas (default-ON = todo como hoy); capa fina se rellena de la data existente (PayrollPosition→PAYROLL, OpexEntry→OPEX, etc.) **unida con la plantilla** para no ocultar deptos reales-pero-vacíos.

---

## 5. Migración (orden seguro — todo antes de la 2ª propiedad)

**Prerequisito:** fundación multi-propiedad ([[MULTIPROPERTY_PLAN]] pasos 1-3): hotel_id obligatorio + contexto de hotel activo.
**Prerequisito recomendado:** reconciliar las **4 fuentes en conflicto de below-GOP 8xxx** (frontend SECTIONS vs `NONOP_ACCOUNT_MAP` vs sentinela 0240 vs `report_line_config`) como ticket aparte — la dimensión Propiedad no es confiable sin una sola fuente de verdad.

1. **Crear+sembrar `department_catalog`** (byte-por-byte de las constantes; resolver Spa/Retail acá). Nadie lo lee aún → sin cambio.
2. **Refactor: las 3 fuentes leen el catálogo** (pl_engine constantes, gl_detail_importer, cwl-depts.ts). Puro refactor; regresión del P&L de CWL contra el output previo.
3. **Crear `dept_enablement` + back-fill CWL** (de la data; unión con plantilla). CWL todo-on → output idéntico. *(CLUB/AREC a `REVENUE_LINES` se DIFIERE al paso 10 — decisión F4.)*
4. **Enhebrar el filtro** en `calculate_pl_from_mapping` (skip depto/línea OFF por el MISMO camino que el `if not m: continue`) + selectores (payroll/opex/costs + `/costs/catalog/`) + retirar `withExtraDepts`/`mergeDepts`. No-op para CWL.
5. **Crear `feature_registry`** (seed del NAV; stubs `is_active=false`) — migración alembic (cadena actual = 059).
6. **Crear `hotel_feature_entitlement`** (sin seed; default-ON = CWL completo). Cutover de riesgo cero.
7. **Resolver backend + `GET /entitlements`** (+ PUT write).
8. **Frontend:** provider de entitlement por hotel activo + filtro en TopNav + guard de ruta. Con tabla vacía es no-op para CWL → despliega "dark-safe".
9. **Provisioning UX** (árbol de checks + matriz, wizard de 2 pasos).
10. **THEN provisionar Amarena/Oxígen/Ojochal** — clonar CWL, desmarcar lo que no aplica (Amarena deja Club/AREC ON; las otras OFF). **Acá entra el cambio diferido (F4): agregar CLUB/AREC a `REVENUE_LINES`+labels** para que Amarena pueda presupuestar su fee de Club/Área Recreativa. **Único paso que introduce divergencia.**

---

## 6. Riesgos

1. **El gating NO debe tocar el cálculo NUNCA.** Entitlement se lee SOLO en TopNav + guard + provisioning; jamás en `engine/`. Un reporte oculto debe seguir computando bien. Enforcer en code review.
2. **`FALLBACK_OVERHEAD_GROUP` traga deptos desconocidos hoy** — si el filtro dropea un depto pero el lookup de grupo igual lo resuelve, podría filtrarse a `OTHER_OVERHEAD`. El skip debe ir por el mismo camino que el unmapped; tests deben afirmar que un depto OFF da $0, no fallback.
3. **Conflicto Spa/Retail (0130/0165 vs 0140/0151)** — canonicalizar en el catálogo puede re-mapear actuals históricos de CWL (0140/0151). Reconciliar (migración o alias) o el P&L de períodos previos se mueve entre SPA/RETAIL y OTHER_OVERHEAD.
4. **Ingreso line-based budget vs dept-based actuals** — un toggle (dept, REVENUE) debe filtrar AMBOS caminos o budget y actuals discrepan. FOOD/BEVERAGE/FNB_MISC colapsan a FB/0120 → un toggle de grupo FB controla las 3 líneas (el owner debe entender la granularidad).
5. **Below-GOP 4 fuentes 8xxx** — reconciliarlas es prerequisito; 8030/8035/8040/8045 mal mapeado misrutea interés/depreciación/reserva.
6. **Mapeo de rutas (guard):** rutas como `/revenue/master` y `/revenue/checkbook` están bajo `/revenue` pero pertenecen al módulo `planning` → mapa reverso del fixture NAV, no por prefijo. Rutas huérfanas no-en-NAV (`/revenue/kpis`, `/revenue/packages`…) → política "permitir si autenticado" + loguear.
7. **Scope hotel vs escenario:** la matriz es por-hotel pero las fact tables son por-escenario; la regla de precedencia (matriz gatea, escenario refina) debe ser consistente.
8. **Back-fill:** unir data con plantilla para no ocultar deptos reales-pero-vacíos (estacionales).

---

## 7. Decisiones del owner — ✅ CERRADAS (2026-06-29)

**Capa gruesa (registro):**
- R1 Resolución: **default-ON** (CWL sin seed, cutover sin riesgo). *(default recomendado)*
- R2 Scope: **per-hotel SOLO ahora.** Rol de usuario = capa ortogonal futura (visible sii hotel-on Y rol-permite), sin enredarlo ahora. ✅
- R3 Granularidad: **página/reporte + configs** (configs ya son hojas; NO widgets). *(default)*
- R4 Stubs "próx.": **sembrar `is_active=false`** (unifica el path de filtrado). *(default)*

**Capa fina (matriz):**
- F1 Depto OFF: **grey/read-only en provisioning, oculto en checkbooks.** *(default)*
- F2 Scope: **per-propiedad baseline + override per-escenario** (el `participates` de cafetería/lavandería sigue como override fino). ✅
- F3 Back-fill CWL: **data ∪ plantilla.** *(default)*
- F4 CLUB/AREC a `REVENUE_LINES`: **DIFERIDO a la provisión de Amarena** ✅ (decisión del owner — distinta de la recomendación). CWL no presupuesta ingreso de Club/AREC (solo actuals) → no pierde nada. El cambio de schema (`REVENUE_LINES` + labels) entra en el **paso 10** (provisionar Amarena), NO en el paso 3. Hasta entonces, Club/AREC en la matriz solo se gestionan en Planilla/OPEX/Costos; su ingreso queda solo-actuals.
- F5 Reconciliación below-GOP 8xxx: **ticket prerequisito aparte** (antes del paso 1). ✅

---

## 8. Resumen ejecutivo
- Una master data de provisioning, dos granularidades: **features (visibilidad)** + **deptos×dimensión (alcance de datos)**. Ambas **filtran, no bifurcan** → el motor/mapeo siguen compartidos (M2 intacto).
- **Cutover de riesgo cero:** todo se siembra del estado actual; default-ON + back-fill → CWL idéntico el día 1. La divergencia entra solo al provisionar la 2ª propiedad.
- **Bonus:** unifica las 3 fuentes de verdad de deptos en `department_catalog` y cierra el gap de revenue de Club/AREC.
- **Esfuerzo:** capa gruesa es chica (2 tablas + filtro nav/ruta, mayormente mecánico). Capa fina es media-alta (catálogo + matriz + enhebrar el motor + reconciliar below-GOP). Va después de la fundación multi-propiedad.
