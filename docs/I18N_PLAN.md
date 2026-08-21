# Plan de Internacionalización (i18n) — FinPlan CWL

> **Estado:** PLANIFICADO. No iniciado. Esperando luz verde para Fase 0.
> **Fecha del plan:** 2026-06-29 · **Autor:** auditoría de alcance (workflow 5 agentes) + decisiones del owner.
> **Regla de oro:** el idioma se fija en el **provisionamiento del tenant** (no es toggle por usuario en runtime). Es un parámetro del cliente, estable.

---

## 0-bis. Re-medición 2026-08-11 (nada iniciado; el producto creció 49%)

| | Junio 2026 | **Hoy** |
|---|---|---|
| Archivos `.ts`/`.tsx` | 69 | **92** |
| LOC frontend | ~18,200 | **27,090** |
| Páginas (`page.tsx`) | ~64 | **73** |
| Strings visibles (texto JSX + placeholder/title/label) | ~700-900 distintos | **~1,030 crudos** |
| `HTTPException` literales | ~90 | **56** (25 archivos de API) |
| `next-intl` instalado | no | **no** |
| `hotels.default_locale` | no existe | **no existe** |

**Lectura:** el costo de la Fase 3 (extraer página por página) crece con el
producto, ~1.5× desde que se escribió el plan. La infraestructura (Fase 0) NO
crece: son las mismas 6 tareas. Eso inclina a **poner la fundación ya y extraer
al pasar**, en vez de traducir 73 páginas de golpe.

### Pedido nuevo del owner (2026-08-11): «con un click cambiar idioma»

Son **dos cosas distintas** y conviene tener las dos:

- **Idioma en el provisionamiento** = default de la PROPIEDAD (decisión D3, ya
  cerrada). Sin esto, cada usuario nuevo arranca en el idioma equivocado.
- **Botón de un click** = preferencia del USUARIO, en runtime. Es la «migración
  aditiva futura» de §2.1: columna `locale` nullable en `users` y resolución
  `user.locale ?? hotel.default_locale ?? 'es'`.

El botón **cuesta ~1 día encima de la Fase 0** si se hace al mismo tiempo, y
bastante más si se hace después (hay que volver a tocar la resolución del locale
en cada capa). Recomendación: hacer los dos en la Fase 0.

---

## 0. Decisiones cerradas (owner, 2026-06-29)

| # | Decisión | Valor |
|---|----------|-------|
| D1 | Idiomas soportados | **es + en** (diseñar para que un 3º sea aditivo; NO construir tabla de traducciones genérica todavía) |
| D2 | Términos USALI / cuentas GL | **Canónicos** — NO se traducen. Solo se traduce chrome de UI + subset descriptivo |
| D3 | Alcance del idioma | **Global por tenant**, seteado en provisioning. Per-usuario = migración aditiva futura si la piden |
| D4 | Exports Excel/PDF | **Canónicos en inglés/USALI** (nombres de hoja fijos por CLAUDE.md: `00_DASHBOARD`, `TAX_PANORAMA`) |
| D5 | Mojibake en BD | **Descartado** — BD verificada limpia (0 filas U+FFFD en `report_line_config`/`account_mapping`; guarda `'Área Recreativa'` correcto). El "�" visto era artefacto de consola cp1252. NO hay fase de reparación |

---

## 1. Por qué el sistema está "spanglish" (diagnóstico)

- **Cero infraestructura i18n:** `package.json` sin librería, `next.config.mjs` sin bloque i18n, `app/layout.tsx` con `<html lang="es">` fijo, sin hook `t()`/`useTranslation` en ningún lado.
- **Strings hardcoded inline** en JSX/objetos, escritos por distintas manos → inglés y español conviven en el mismo menú (`TopNav`: "Dashboard"/"Planning" junto a "Escenarios"/"Ingresos").
- **Tres superficies de texto independientes**, cada una eligió su idioma: chrome de frontend (mayormente español), labels de backend (P&L en inglés desde `GROUP_NAMES` + literales, pero `HTTPException` en español), y datos en BD (`report_line_config` mayormente inglés, `position_name` en español).
- **USALI es estándar inglés** → GOP/EBITDA/RevPAR/Room Revenue se dejaron en inglés a propósito. Ese inglés es intencional, NO un bug. Es la razón principal del "spanglish".

---

## 2. Arquitectura objetivo

### 2.1 Dónde vive el idioma
- **Migración:** columna `default_locale VARCHAR(5) DEFAULT 'es'` en la tabla **`hotels`** (modelo `app/models/hotel.py`; ya alberga `closed_months`/`pax_per_night`). Es el registro del tenant.
- **Admin lo cambia:** `PATCH /api/hotels/{id}/locale` protegido por `get_current_admin` (ya existe). `GET` para leerlo. `<select>` en `/admin`.
- **Resolución por request:** cookie **`finplan_locale`** legible por el server, **sembrada al login** desde `hotel.default_locale`. Fallback server: `hotel.default_locale ?? 'es'`.
  - ⚠️ Auth es **JWT custom en localStorage** (NO NextAuth) → el locale NO puede venir de una sesión NextAuth. La cookie + fallback del hotel es el camino server-readable limpio para server components.
- **Futuro aditivo (no ahora):** columna `locale` nullable en `users`; orden de resolución `user.locale ?? hotel.default_locale ?? 'es'`.
- **NO** construir tabla de settings genérica (overkill para 1 tenant).

### 2.2 Frontend
- **Librería:** `next-intl` en modo **"without i18n routing"** (sin segmento `[locale]`, sin renombrar páginas, sin reescribir `<Link>`).
- `getRequestConfig` lee la cookie `finplan_locale`; `NextIntlClientProvider` envuelve `TopNav`+`AuthGate` en `app/layout.tsx`; `<html lang={locale}>` dinámico.
- **Catálogos namespaced:** `nav.*`, `common.*`, `validation.*`, `dashboard.*`, `reports.*`, `pl.*`. Archivos `messages/es.json`, `messages/en.json`.
- **La normalización del spanglish se hace DENTRO de la extracción** (al armar `es.json` se vuelve consistente el español), NO como pase separado.

### 2.3 Backend
- **Engine puro-Python (regla CLAUDE.md):** NO pasar locale a `calculate_full_pl`. El engine ya emite un `line_code` estable con cada label → **el código es el contrato**, inglés como fallback, se traduce en el frontend namespace `pl.*` por `line_code`.
  - ⚠️ Mapear AMBOS vocabularios (`_PL_ALIASES`/`_MOTOR_TO_CANON`) a UNA sola clave para evitar drift (un total bajo dos `line_code`).
- **Sí se traduce server-side:** ~90+ mensajes `HTTPException` en español (~10 archivos API) → claves estilo gettext con parametrización (interpolación de f-strings). Más ~6 `SECTION_LABELS` de colaboración.
- **Exports** (`payroll_excel`/`opex_excel`/`costs_excel`/owner) → canónicos inglés/USALI.

### 2.4 Labels de BD (híbrido, inclinado a canónico)
- **EXCLUIR de i18n:** ~7,206 descripciones de cuentas USALI (`accounts.descripcion`) y nombres GL-tied — traducirlos rompe mapeo P&L, paridad con export y confianza de auditores.
- **Subset descriptivo a traducir:** `report_line_config.line_name`/`section` (~61 líneas / ~12 secciones), campos de reporte de `account_mapping`, ~18 `dept_name` + ~53 `position_name`, labels de canales.
- **Mecanismo:** columnas paralelas **`_es`/`_en`** (no tabla de traducciones — volumen chico, evita join en el path caliente del reporte). Clave en **business keys estables** (`report_id`, `line_code`)/`account_code` → para que el `DELETE`+reinsert de los importers (mapping_loader) NO borre las traducciones.
- **Tag canónico-vs-chrome POR FILA** (estas tablas mezclan términos contables con labels descriptivos), no por tabla.
- Reservar una tabla `(entity, locale, field)` SOLO si aparece un 3er idioma real.

---

## 3. Glosario CANÓNICO (NO traducir nunca)

Enforced en review. ~30 términos protegidos:

- **Acrónimos/totales USALI:** GOP, EBITDA, EBT, RevPAR, ADR, NOI, FTE, P&L, F&B, COGS, USALI
- **Roles de columna (estándar contable):** Actual, Budget, Forecast, Reforecast, Var, YTD, LY
- **Líneas/secciones USALI del P&L** emitidas por `pl_engine` (Total Revenues, Total Gross Operating Profit (GOP), Rooms, F&B) — canónicas; traducir por `line_code` en frontend solo si se quiere label localizado
- **Catálogo de cuentas (~7,206) y nombres GL-tied**
- **Nombres propios / marca:** Innoceana(/Innoceanna), Crowther Lab(/Crowler Lab), Club Madresal, Claro del Bosque, room types (Sirena Suites, 5 Elements Treehouse), nombre del hotel, nombres de empleados
- **Exports** y nombres de hoja mandados (`00_DASHBOARD`, `TAX_PANORAMA`)
- **Contenido libre del usuario** (ops_kpi, anotaciones/Q&A, códigos de escenario) = contenido, no localización

---

## 4. Inventario de alcance (medido por la auditoría)

### Frontend (`C:\FinPlan_CWL\frontend`, 69 .tsx / ~18,200 LOC)
| Dónde | Qué | Aprox |
|-------|-----|-------|
| `components/TopNav.tsx` (NAV líneas 21-146) | nav groups + menú + headers + login/logout | ~95 strings |
| `app/**/page.tsx` | títulos H1/H2 + sub-headers | ~64 títulos + 150-200 sub |
| `app/**/page.tsx` | `<th>`/`<button>`/`<option>`/`<label>` | varios cientos (neto ~700-900 distintos) |
| `app/admin/*`, `app/scenarios`, `app/login`, checkbooks | validación/toast/confirm/alert | ~60-100 mensajes |
| `lib/cwl-depts.ts` (CWL_DEPTS) | 21 nombres de depto (fallback) | 21 |
| `lib/fmt.ts` + ~41 copias inline | formato money/fecha (NO locale-aware) | 1 módulo + 41 dup + `MONTHS` en ~48 archivos |
| `app/dashboard`, `app/pl/full`, `app/reports/*` | labels PROVISTOS por backend (NO frontend strings) | 82 sitios en 20 archivos |

**Magnitud frontend:** ~700-900 strings distintos. Sin centralización → la extracción toca casi los 69 archivos.

### Backend (`C:\FinPlan_CWL\backend`, ~250-300 strings)
| Dónde | Qué | Aprox |
|-------|-----|-------|
| `app/engine/pl_engine.py` GROUP_NAMES (líneas 80-90) | nombres de grupo/depto P&L | 19 |
| `app/engine/pl_engine.py` `add(...)` line_name | nombres de totales/subtotales | ~25 |
| `app/engine/pl_engine.py` secciones (~421-459) | headers de sección | ~16 |
| `app/importers/payroll_catalog_importer.py` CONCEPTO_NOMBRES | 17 conceptos de nómina CR | 17 |
| `app/models/section_assignment.py` SECTION_LABELS | labels colaboración | 6 |
| `app/models/revenue_entry.py` REVENUE_LINE_LABELS | líneas revenue checkbook | 11 |
| `app/api/revenue_api.py` _CHANNEL_LABELS / _PKG_LABELS | canales / componentes paquete | 3 + 4 |
| `app/api/scenarios_api.py` CATS (400-408) | labels de varianza | 7 |
| ~10 archivos API | mensajes `HTTPException` español | ~90+ ← mayor bucket traducible |

### BD (~12 tablas con labels; modelos en `app/models/`)
| Tabla (modelo) | Campo | Decisión |
|----------------|-------|----------|
| `report_line_config` (`mapping.py ReportLineConfig`) | line_name, section | TRADUCIR (~81 filas, 61 líneas, 12 secciones) |
| `account_mapping` (`mapping.py AccountMapping`) | report_line_name, report_section | TRADUCIR subset (719 filas, 31 distintos) |
| `accounts` (`account.py`) | descripcion | **EXCLUIR** (~7,206 USALI canónicas) |
| `payroll_positions` (`payroll_position.py`) | dept_name, position titles | TRADUCIR (18 dept + 53 puestos) |
| `room_type_configs` (`room_type_config.py`) | room types, canales | room types EXCLUIR (marca); canales TRADUCIR |
| `cashflow_versions` (`cashflow_version.py`) | row labels (JSON) | revisar caso a caso |
| `ops_kpi_entries` (`ops_kpi.py`) | kpi/owner/action | EXCLUIR (contenido libre del usuario) |

---

## 5. Plan por fases (con checklist y Definition of Done)

### Fase 0 — Infra + idioma en provisionamiento + botón de un click · **3-4 días**
- [ ] `npm i next-intl`
- [ ] Migración alembic: `default_locale VARCHAR(5) DEFAULT 'es'` en `hotels` (siguiente nº tras 092)
- [ ] Migración: `locale VARCHAR(5) NULL` en `users` (el botón de un click)
- [ ] Resolución en UN solo lugar: `user.locale ?? hotel.default_locale ?? 'es'`
- [ ] `getRequestConfig` lee cookie `finplan_locale`; `NextIntlClientProvider` en `app/layout.tsx`; `<html lang={locale}>` dinámico
- [ ] `GET`/`PATCH /api/hotels/{id}/locale` con `get_current_admin`
- [ ] `<select>` de idioma en **Master Data → Provisionamiento** (junto a la matriz de deptos)
- [ ] Botón ES/EN en el header (escribe `users.locale` + la cookie)
- [ ] Flujo de login escribe la cookie `finplan_locale` desde el setting resuelto
- [ ] Scaffolding `messages/es.json` + `messages/en.json` (vacíos con namespaces)
- **DoD:** el idioma se elige en provisionamiento, el botón lo cambia para un usuario, `<html lang>` refleja el resuelto y persiste entre sesiones; sin romper ninguna página existente (texto sigue hardcoded, aún no traducido).

### Fase 1 — Chrome compartido (quick win visible) · **3-5 días**
- [ ] Extraer `TopNav` NAV (~95, mayor tráfico) → `nav.*`
- [ ] `AuthGate`, `login`, botones comunes (`common.*`), validación/toast (`validation.*`)
- [ ] Normalizar spanglish AL extraer (es.json consistente)
- **DoD:** con el toggle, nav + login + mensajes cambian es↔en en toda la app.

### Fase 2 — Centralizar formato · **2-3 días**
- [ ] Colapsar ~41 formateadores money + ~48 arrays `MONTHS` en `lib/fmt.ts` parametrizado por locale
- [ ] Actualizar formateadores de recharts (ejes/tooltips) y xlsx
- **DoD:** ninguna tabla se rompe bajo otro locale; un solo módulo de formato.

### Fase 3 — Chrome página por página (por tráfico) · **2-4 semanas**
- [ ] Extraer títulos, sub-headers, headers de tabla, filtros, botones en ~40 carpetas (`dashboard`, `reports/*`, `revenue/*`, `payroll`/`costs`/`opex`/`nonop`, `marketing-insight/*`, `operation-insight/*`)
- [ ] Aplicar el glosario canónico (§3) en review
- [ ] Traducir `pl.*` por `line_code` para labels del P&L
- **DoD:** todas las páginas con chrome traducido; USALI canónico intacto.

### Fase 4 — Mensajes backend + labels colab · **3-5 días**
- [ ] Clavar ~90+ `HTTPException` español (parametrizado para f-strings)
- [ ] ~6 `SECTION_LABELS` de colaboración
- [ ] Engine sigue puro-Python; solo expone `line_code`
- **DoD:** errores y labels de colaboración localizados; engine sin tocar.

### ~~Fase 5 — Encoding~~ · **SE SALTA** (BD verificada limpia, ver D5)
- Guardrail permanente: escribir catálogos/migraciones con **Bash o `-Encoding utf8`**, nunca PowerShell default (cp1252/UTF-16) que SÍ introduciría mojibake.

### Fase 6 — Labels de BD · **1-2 semanas**
- [ ] Auditar `report_line_config`/`account_mapping` fila por fila → tag canónico vs descriptivo
- [ ] Columnas `_es`/`_en` en el subset descriptivo, clave en business keys estables
- [ ] Traducir ~53 puestos + dept/canal
- [ ] EXCLUIR las ~7,206 descripciones de cuentas
- [ ] Verificar que `DELETE`+reinsert de importers NO borra traducciones
- **DoD:** reportes muestran labels descriptivos en el idioma del tenant; cuentas GL canónicas; re-import no pierde traducciones.

---

## 6. Riesgos y guardrails

1. **Leakage de español en sets "ingleses"** (`Administrations`[sic], `Cafetería`, `Área Recreativa`, `F&B Misceláneo`, filas de balance en español en `cashflow_budget`) → no se puede inferir idioma por dict; cada string necesita clasificación individual canónico-vs-chrome. Lento y propenso a error.
2. **Tooling encoding:** escribir catálogos vía PowerShell default INTRODUCE mojibake → siempre Bash o `-Encoding utf8`. (La BD ya está limpia; el riesgo es al GENERAR archivos.)
3. **Labels denormalizados/duplicados:** `account_name` copiado en opex/cost/nonop/revenue/belowgop; `report_line_name`/`section` en `report_line_config` Y `account_mapping` → sin clave canónica única, el mismo string se traduce inconsistente en decenas de filas.
4. **Re-imports sobrescriben:** `mapping_loader` hace `DELETE`+reinsert por REPORT_ID → traducciones DEBEN clavar en business keys, no en row id.
5. **Source-of-truth del locale:** next-intl asume locale en URL, acá es setting de BD; server components necesitan locale en request pero auth vive en localStorage → la cookie debe escribirse al login y mantenerse sync con el setting del hotel, o las páginas SSR caen al idioma equivocado.
6. **Paridad de export:** si UI se traduce pero exports no → owners ven labels inconsistentes. Política decidida: exports canónicos inglés (D4).
7. **Scope creep:** hacer normalización-spanglish + extracción simultánea en ~40 carpetas puede inflar el esfuerzo → gatear fase por fase.
8. **Vocabularios duales en `pl_engine`** (`_PL_ALIASES`/`_MOTOR_TO_CANON`) pueden emitir un total bajo dos `line_code` → el esquema por clave DEBE mapear ambos a una sola key.

---

## 7. Resumen ejecutivo

- **Factible**, encaja limpio (next-intl sin routing, locale en `hotels`, cookie server-readable). Sin reescritura de rutas.
- **Quick win** (Fases 0-1) en **~1 semana** → toggle admin funcionando + chrome visible traducido.
- **Producto totalmente traducido** = **multi-semana** (Fase 3 es el grueso: ~40 carpetas).
- **Lo más caro se colapsó** gracias a idioma-en-provisioning: los labels de BD se SIEMBRAN en el idioma del tenant (sin sistema de traducción runtime para datos) + BD ya limpia (sin fase de encoding).
- **No empezar a construir** hasta luz verde del owner para Fase 0.
