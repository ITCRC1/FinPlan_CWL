# FinPlan CWL — Roadmap del producto

> Visión: convertir el set de pantallas de planificación en una **app de clase mundial**
> para construir presupuestos hoteleros: un proceso lógico, colaborativo, con grado de
> avance visible, validación, y narrativa automática para los dueños.

---

## Concepto central

El presupuesto **no lo llena una sola persona**. Es un **paquete por año** (un *escenario*:
Budget 2027, Forecast 2027, etc.) que un **equipo** llena en paralelo, cada quien su sección,
con un coordinador de finanzas que revisa y aprueba.

```
Budget 2027  ← el "paquete" del año (escenario aislado)
 ├── Master data del año   (inventario, meses cerrados, factor pax, TC, params planilla)
 ├── Ingresos              (drivers → 11 líneas de revenue + Spa)
 ├── Costos de venta       (Clase 5)
 ├── Planilla              (headcount + 17 conceptos)
 ├── OPEX                  (Clase 7)
 ├── Gastos del propietario(8xxx: mgmt fee, reserva, depreciación, financieros)
 └── Revisión & P&L        (GOP → EBITDA → Net) + aprobación
```

---

## Los 6 pilares

### 1. Paquete por año
- Cada Budget/Forecast es un contenedor aislado; no se pisan entre años.
- **Master data por escenario**: units (29 vs 40 según el año), meses cerrados, factor pax,
  TC y **parámetros de planilla** (CCSS, aguinaldo, salario mínimo — cambian cada año en CR).
  Hoy varias de estas viven a nivel hotel (global) → migrar a escenario.
- Granularidad **por mes** donde haga falta (units que cambian a mitad de año, TC por mes).
- **Crear nuevo Budget**: vacío (con defaults) o **copiando** de un año/versión previo.
- **Versiones por año** (ya hay campos `type` + `version` + `actuals_through`):
  - **Budget**: varios drafts del mismo año (Draft1 / Draft2 / Draft3 → FINAL) para iterar sin pisar.
  - **Forecast rolling**: hasta **12 versiones por año** (una por mes: actuals hasta el mes + proyección
    del resto; `actuals_through` marca el corte).
  - Copiar de versión a versión usa el mismo mecanismo de copia.

### 2. Flujo lógico + grado de avance
- **Todas las etapas abiertas** desde el inicio — se avanza un poco en cada una, en cualquier orden.
- **% de avance por etapa** y global; barra de progreso.
- **P&L preliminar en vivo**: se recalcula mientras el equipo llena; se ve siempre, no solo al final.
- **Validación en lenguaje humano**: "Mix de canales = 100% ✓", "Faltan 2 líneas: FNB misc, Laundry",
  "12 posiciones sin salario". Dependencias = avisos suaves, no candados.
- **Checklist a nivel de departamento** dentro de cada sección (Rooms ✓, F&B ✓, Spa ⬜…). El % de
  la sección sale de cuántos deptos están listos. Un check no impide ajustes en revisión.

### 3. Colaborativo + asignación
- **Asignar secciones/departamentos** a personas; trabajan en paralelo sin pisarse.
- **Presencia en vivo** ("editando ahora") + última edición por usuario.
- **Flujo de estados** por sección: En progreso → En revisión → Aprobada.
- **Bloqueo por el administrador**: cuando una sección/depto queda lista, el admin la **congela**
  (Ingresos primero, es lo más sensible). Ajustar en revisión requiere desbloqueo. Queda registro.
- **Puerta de aprobación**: no se aprueba el Budget con etapas incompletas o validaciones/Q&A abiertas.

### 4. Q&A en contexto
- Hilos de preguntas **anclados a la sección/línea/celda** (no un chat suelto).
- **@menciones** → notificación. Estado **Abierta / Resuelta**. Contador visible por celda/sección.
- **Canal general del Budget** para dudas que no son de una línea puntual.

### 5. Contexto + comparativos (decisión, no solo captura)
- **Contexto macro** al inicio del año: Mundo (PIB, inflación, turismo), País (PIB CR, inflación, TC),
  Industria hotelera (ocupación, ADR/RevPAR LatAm). Editables / o vía fuente externa.
- **Key indicators comparativos**: el Budget que se construye **vs Año pasado (real)** y **vs Forecast**,
  en vivo → "qué tipo de budget estoy armando" (agresivo vs conservador).
- **Comparar versiones** lado a lado (Budget Draft1 vs Draft2 vs Draft3; Forecast-marzo vs Forecast-junio)
  para análisis en "Budget time".

### 6. Narrativa para los dueños (storytelling automático)
- **Comentarios por línea/celda** en Ingresos, Planilla, OPEX, Costos y Dueños explicando el *por qué*.
  Ej. "Abril 2026 tuvo el grupo NH → ingreso alto; 2027 sin ese grupo → abril baja".
- Los comentarios se **agregan en un reporte de variaciones** → la explicación a los dueños se va
  formando sola, línea por línea, en vez de reconstruirla al final.
- **Auditoría**: quién cambió qué y cuándo; quién bloqueó/aprobó.

---

## Roadmap por fases

| Fase | Qué | Desbloquea | Prerrequisito |
|------|-----|------------|---------------|
| **0 · Cimientos** | Login real + usuarios + roles (admin / colaborador) | Todo lo colaborativo | — |
| **1 · Paquete por año** | Crear Budget por año (vacío/copiar) · master data por escenario · arreglar el copiador (incluir Revenue Checkbook + Spa) | **Budget 2027 ya** | — (no necesita auth) |
| **2 · Motor de avance** | % por etapa y por depto · reglas de validación · estado por sección · P&L preliminar en vivo · contexto macro + comparativos LY/FC | El "command center" | Fase 1 |
| **3 · Colaboración** | Asignar secciones · estados revisión→aprobado · presencia · bloqueo admin · Q&A en contexto · comentarios | Equipo en paralelo | Fase 0 |
| **4 · Narrativa & pulido** | Comentarios→reporte de variaciones · feed de actividad · notificaciones · historial/auditoría · export Excel/PDF · dashboard dueños | El acabado "clase mundial" | Fases 1–3 |

### Recomendación de arranque
**Fase 1 ahora** (valor inmediato, sin auth) + **Fase 0 en paralelo** (cimiento de lo colaborativo).

---

## Arquitectura de navegación final (7 tabs) — definida 2026-06-26

La app pasa de "menú de módulos" a **escenario-primero** (estilo Hyperion/EPM). Detalle completo
+ formatos de reportes reales en **`REPORTES_SPEC.md`**.

1. **Escenarios** — biblioteca: crear/copiar draft/forecast rolling + lista (Budget/FCT/Actual)
2. **Planning** — taller: elegir versión + Setup del año + Constructor + Tablero + Q&A
3. **Dashboard** — análisis vs versiones (KPIs, tendencias, P&L comparativo, POV) ⬅️ falta
4. **Master Data** — hoteles, catálogo, departamentos, mapeo P&L, params base
5. **Estados financieros** — P&L · Cash Flow · Tax
6. **Reportes** — biblioteca de formatos (ver REPORTES_SPEC.md)
7. **Admin** — usuarios/roles · auditoría

Reglas: Planning NO crea escenarios (eso es Escenarios); Tablero+Q&A van dentro de Planning;
Dashboard = análisis (no inicio); Actuales = solo lectura; POV = corazón del Dashboard.

---

## Estado actual (base ya construida)
- Backend FastAPI + PostgreSQL (Railway), frontend Next.js 14 (Vercel). Desplegado.
- Escenarios: Actual 2024/25/26, Budget 2026, Forecast, Reforecast.
- Módulos funcionando: Ingresos (drivers tab-por-tab + 11 líneas checkbook + Spa capture-rate),
  Costos, Planilla, OPEX, Gastos Dueños, Mgmt fees, P&L USALI (motor + recálculo), Reportes YTD.
- ⚠️ Sin auth real (API pública). ⚠️ Master data (units, meses cerrados, pax, params planilla)
  todavía a nivel hotel/hardcoded → mover a escenario (Fase 1).

---

_Última actualización: 2026-06-26_
