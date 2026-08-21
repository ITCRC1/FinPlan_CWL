# FRONTEND_PLAN — Fase 3 (Revenue) y base del frontend

> Plan preparado en Opus (2026-06-20) para ejecutar en **Sonnet**.
> Objetivo: montar el scaffold de Next.js 14 + tema + navegación, y luego las
> 2 pantallas de Fase 3. Todo lo demás del frontend reusa esta misma base.
> El backend (Fases 1–4 + historical_kpi) ya está completo y commiteado.

---

## 0. Contexto rápido

- **Dir frontend:** `C:\FinPlan_CWL\frontend` (HOY VACÍO — hay que crear todo).
- **Backend local:** `cd backend && uvicorn app.main:app --reload` → `http://localhost:8000`.
- **Stack obligatorio (CLAUDE.md §2):** Next.js 14 (App Router) · TypeScript · Tailwind CSS · Recharts.
- **Estética (CLAUDE.md §26):** dark theme estilo TradingView; navegación horizontal con dropdowns estilo Opera Cloud (SIN sidebar); números en monospace con `tabular-nums`.
- Antes de codear, leer del CLAUDE.md las secciones **25–26** (líneas ~5378–5870) y **15** (Rates/Key Indicators).

---

## 1. Scaffold (hacer primero)

```bash
cd C:\FinPlan_CWL\frontend
npx create-next-app@14 . --ts --tailwind --app --eslint --no-src-dir --import-alias "@/*"
npm install recharts
```

Crear `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

Verificar `npm run dev` → arranca en `http://localhost:3000`.

---

## 2. Design tokens (copiar tal cual del CLAUDE.md §26.1)

Poner las CSS variables en `app/globals.css` dentro de `:root` (valores exactos):

```css
:root {
  --bg-base:#131722; --bg-surface:#1E2130; --bg-elevated:#2A2E3F;
  --bg-input:#1A1D2E; --bg-header:#0F1118;
  --border-subtle:#2A2E3F; --border-medium:#363B52; --border-focus:#2962FF;
  --text-primary:#D1D4DC; --text-secondary:#787B86; --text-disabled:#4C505E; --text-inverse:#131722;
  --brand:#2962FF; --brand-hover:#1E53E5;
  --positive:#26A69A; --negative:#EF5350; --warning:#F59E0B; --neutral:#787B86;
  --font-ui:'Inter',-apple-system,sans-serif;
  --font-mono:'JetBrains Mono','Fira Code','Consolas',monospace;
}
```
- Fuentes: cargar Inter + JetBrains Mono vía `next/font/google`.
- Clase utilitaria `.mono` → `font-family:var(--font-mono); font-variant-numeric:tabular-nums; letter-spacing:-0.01em;` para TODO número.
- Mapear los tokens a `tailwind.config.ts` (`theme.extend.colors`) para usar `bg-base`, `text-secondary`, etc.

---

## 3. Layout y navegación (componente compartido — base de TODO el frontend)

Crear `app/layout.tsx` + componente `components/TopNav.tsx`:

- **Topbar** (alto 44px, `--bg-header`, borde inferior `--border-subtle`): logo CWL + items con dropdown. Derecha: fecha, selector de propiedad `[CWL ▾]`, menú usuario.
- **Sin sidebar.** Breadcrumb opcional bajo el topbar.
- Dropdowns del menú principal (CLAUDE.md §26.4) — para Fase 3 solo se necesita activo el menú **Ingresos**:
  ```
  Ingresos ▾
    Rates & Tarifas      → /revenue/rates
    Key Indicators       → /revenue/kpis
    Canales de Venta     → (Fase posterior)
    Paquetes             → (Fase posterior)
    Históricos 2024-25   → /revenue/kpis (mismo, columna histórica)
  ```
- Dejar los otros menús (Planilla, Costos, P&L, Reportes, Config) como placeholders deshabilitados o con items "próximamente".

Crear `lib/api.ts`: wrapper `fetch` con base `NEXT_PUBLIC_API_URL`, manejo de errores, y header `Authorization: Bearer` listo para cuando exista auth (Fase 12). Por ahora sin token.

---

## 4. Pantalla A — `app/revenue/rates/page.tsx` (inputs)

Reproduce la lógica del tab "Rates 2026" / "Key Indicators" del Excel. Inputs editables:
- **Rack rate** por tipo de villa (6) × mes (12).
- **Canales de venta**: mix % y comisión % (Travel Agency, OTAs, Direct).
- **Ocupación** (rooms occupied) por tipo × mes.
- **Paquete**: rate por componente (FOOD, BEVERAGE, ACTIVITIES, TRANSPORT, SUSTAINABILITY).

Comportamiento (acceptance, del CLAUDE.md §FASE 3):
- Cambiar ocupación% → recalcula Room Revenue → recalcula ADR/RevPAR (llamar al backend y refrescar).
- Cambiar canal → recalcula Net Rate → recalcula todo el revenue.
- Tabla densa: filas alternas (`--bg-surface`/`--bg-base`), hover `--bg-elevated`, header `--bg-header`. Inputs con `--bg-input`.
- Mostrar fila de Net Rate calculado (read-only) al lado del Rack (input).

### Endpoints backend a usar (ya existen)
```
POST /scenarios/{scenario_id}/revenue/import/                      → importa desde Excel
GET  /scenarios/{scenario_id}/revenue/monthly/                     → resultados calculados 12 meses
GET  /scenarios/{scenario_id}/revenue/{month}/                     → un mes
PUT  /scenarios/{scenario_id}/revenue/rate-cards/{room_type_id}/{month}/   → editar rack rate
PUT  /scenarios/{scenario_id}/revenue/occupancy/{room_type_id}/{month}/    → editar ocupación
```

> ⚠️ **Gap de backend a resolver primero (tarea chica, puede hacerla Sonnet):**
> No hay GET para leer los **inputs crudos** (rack rates, canales, ocupación, paquetes)
> que necesitan los formularios. Hoy solo existe `GET monthly` (resultados calculados).
> Agregar en `backend/app/api/revenue_api.py`:
> `GET /scenarios/{id}/revenue/rate-cards/`, `.../occupancy/`, `.../channels/`, `.../packages/`
> devolviendo los valores almacenados. Patrón: copiar `_load_revenue_data()` ya existente
> y serializar. Añadir un test por endpoint.

---

## 5. Pantalla B — `app/revenue/kpis/page.tsx` (Key Indicators comparativo 4 columnas)

Vista comparativa (CLAUDE.md §15 / línea ~2731):
```
Indicador            2024 Actual   2025 Actual   2026 Budget   2026 Forecast
% Occupancy            46.13%        48.82%        75.00%          —
ADR                   $359.84       $473.51       $595.27         —
RevPAR                  ...           ...           ...            —
Rooms Occupied          429           454          697.5           —
Room Revenue        $154,371      $214,972      $415,202         —
Total Guests            711           809         1,255.5         —
```
- **2024/2025 Actual** ← `GET /hotels/CWL/historical/` (ya existe; devuelve 24 filas hotel-total).
- **2026 Budget** ← `GET /scenarios/{budget_scenario_id}/revenue/monthly/`.
- **2026 Forecast** ← columna vacía/`—` hasta que exista Forecast (Fase 10).
- Selector de mes (Ene–Dic) arriba; tabla cambia al mes elegido.
- Varianzas con color semántico: verde `--positive` si 2026 > año previo (más ingreso = bueno), rojo `--negative` si menos.
- 2 gráficas Recharts: línea de ocupación mensual (2024 vs 2025 vs 2026) y barras de Room Revenue por mes.
- Números en monospace.

---

## 6. Cómo obtener el `scenario_id` del Budget 2026

El frontend necesita el id del escenario Budget de CWL. Endpoints de escenarios en
`backend/app/api/scenarios_api.py` (revisar paths exactos). Flujo sugerido:
1. `GET` lista de escenarios del hotel CWL → tomar el Budget 2026.
2. Guardar `scenario_id` en un contexto/estado global (React context) para reusar en todas las pantallas.

---

## 7. Orden de trabajo

1. Scaffold + tokens + layout/nav (sección 1–3). Confirmar dev server y tema visible.
2. Resolver el gap de GET de inputs en el backend (sección 4 ⚠️).
3. Pantalla B (kpis) primero — es solo lectura, valida que la conexión API + tabla + Recharts funcionan con datos reales (historical + monthly).
4. Pantalla A (rates) — formularios con PUT y recálculo.
5. Verificar en navegador (preview): cambiar ocupación → ver Room Revenue/ADR recalcular.

## 8. Acceptance final de Fase 3 (frontend)
- [ ] `npm run dev` corre, tema oscuro TradingView visible, nav Opera Cloud funcional.
- [ ] KPIs muestra 2024/2025 reales lado a lado con Budget 2026 (ene-2026 Room Rev ≈ $415,201).
- [ ] Editar ocupación en Rates recalcula Room Revenue/ADR/RevPAR contra el backend.
- [ ] Sin errores en consola; números en monospace; varianzas con color correcto.

## 9. Recordatorio de estrategia
Esto es UI mecánica → ejecutar en **Sonnet** para conservar tokens de Opus.
Reservar Opus para el núcleo financiero (Fases 7 allocations, 8 motor P&L) y debugging difícil.
