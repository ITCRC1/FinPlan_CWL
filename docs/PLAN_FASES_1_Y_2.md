# Plan de trabajo — Fase 1 y Fase 2

> **Escrito para arrancar en frío.** Asume que quien lo lee no estuvo en la
> conversación donde se decidió. Todo lo necesario —rutas, estado actual,
> decisiones y por qué— está acá adentro.
>
> **Última actualización:** 2026-08-12 · **Proyecto:** `C:\FinPlan_CWL`
> **Rama:** `master` · **Cabeza de alembic:** `097` · **Pruebas:** 584 ✅
> **LAS DOS FASES COMPLETAS** (1.A · 1.B · Fase 2), desplegadas y verificadas.

---

## Decisiones del owner (2026-08-11) — cerradas

| # | Decisión |
|---|---|
| **D1** | El idioma se elige en **provisionamiento** (default de la propiedad) **y además** hay un botón de un click (preferencia del usuario). Van los dos. |
| **D2** | Las palabras hoteleras quedan en **inglés**. Se traduce el chrome. |
| **D3** | La corrección de la cuenta **8020 / LARGE_CAPEX** entra en la **Fase 1**. |
| **D4** | **Área Recreativa va en OVERHEAD** (como el Excel), no en operativo. |
| **D5** | El P&L Full Detail es un reporte **NUEVO que convive** con los existentes: «no hay reporte con máximo detalle». No reemplaza a `/reports/pl-full` ni a `/reports/pl-by-dept`. |
| **D6** | El reporte nuevo vive en el menú **Reportes**. |
| **D7** | El reporte abre **Rooms en sus tres sets** (Standard / Villas / Residencias), cada uno con ocupación, ADR y RevPAR. |

---

## Cómo se despliega (aplica a todo)

```bash
# 1. backend: migrar producción ANTES de que el código nuevo la necesite
cd backend && python -c "
import json,os,subprocess,sys
v=json.load(open(r'C:/Users/finco/AppData/Local/Temp/claude/pgvars.json'))
env=dict(os.environ); env['DATABASE_URL']=v['DATABASE_PUBLIC_URL']
print(subprocess.run([sys.executable,'-m','alembic','upgrade','head'],
                     env=env,capture_output=True,text=True).stderr[-400:])"

# 2. pruebas y typecheck ANTES de push
cd backend && py -3 -m pytest -q
cd frontend && npx tsc --noEmit

# 3. backend: push a master → Railway despliega solo
git push origin master

# 4. frontend: MANUAL, siempre
cd frontend && npx vercel deploy --prod --yes
```

**Verificar que el backend nuevo está arriba** (no confiar en el reloj):

```bash
curl -s https://finplan-cwl-production.up.railway.app/openapi.json \
  | python -c "import json,sys; print([p for p in json.load(sys.stdin)['paths'] if 'RUTA_NUEVA' in p])"
```

**Leer la base de PRODUCCIÓN en solo-lectura** (desde `backend/`, con `py -3`):

```python
import asyncio, json, os, sys
sys.path.insert(0, ".")
v = json.load(open(r'C:/Users/finco/AppData/Local/Temp/claude/pgvars.json'))
os.environ["DATABASE_URL"] = v["DATABASE_PUBLIC_URL"].replace("postgresql://", "postgresql+asyncpg://")
from sqlalchemy import select
from app.db import SessionLocal
```

> ⚠️ Salida con acentos: usar `PYTHONIOENCODING=utf-8`, la consola es cp1252.

---

# FASE 1

## 1.A — Correcciones bloqueantes del below-GOP (D3)

**Por qué va primero:** la Fase 2 construye un reporte de **máximo detalle** para
revisar línea por línea. Montarlo encima de un below-GOP inconsistente es
garantizar que nazca mintiendo.

> ✅ **1.A CERRADO — 2026-08-12.** Migraciones `093` · `094` · `095`,
> 514 pruebas, desplegado y verificado contra producción.
> **Delta total del P&L: $41.04 cambian de bloque en cinco escenarios; el GOP,
> el EBT y el Neto NO se movieron en ninguno.** Detalle abajo y en la bitácora.

### A1 — La cuenta 8020 tenía TRES verdades ✅

| Fuente | Decía |
|---|---|
| `account_mapping` | Capital Reserve |
| El dato cargado | Large Capital Expenditure |
| `NONOP_ACCOUNT_MAP` del motor (`pl_engine.py`) | `mgmt_fee` |

**Qué es de verdad:** la `8020` lleva **las dos** líneas. Medido contra
producción — Actual 2026: la cuenta suma `177,804.33` y el P&L del owner la
parte en `CAPITAL_RESERVE 31,326.89` + `LARGE_CAPEX 146,477.44`, que da
exactamente eso. Actual 2025: `221,403.14 = −1,082.55 + 222,485.69`. La apertura
existe en el detalle del libro; el importador agrega por `(depto, cuenta)` y se
queda con el último nombre, y por eso la misma cuenta se llama «CAPITAL RESERVE»
en una tabla y «LARGE CAPITAL EXPENDITURE» en la otra.

- [x] Investigado contra los montos cargados
- [x] **Una sola verdad**: la 8020 es capital; la apertura entra a nivel LÍNEA
      (snapshot importado o `nonop_entries`), nunca por código de cuenta. Con
      solo la cuenta a mano, todo cae en `CAPITAL_RESERVE` — las dos viven
      dentro de `CAPITAL_EXPENSE`, así que subtotal, EBITDA After Capital, EBT y
      Neto salen idénticos
- [x] `LARGE_CAPEX` **queda sin regla de cuenta a propósito** y documentado
      (igual `ASSET_LOSS`, que comparte la 8040 con Depreciación)
- [x] De paso aparecieron **dos cuentas más mal ruteadas** en el mismo mapa:
      `8030` (cargos bancarios) decía `capital_reserve` y `8045` (diferencial
      cambiario) decía `large_capex`. Y la `8025` (multas y no deducibles, hasta
      $109k en 2025) no estaba mapeada: caía al cajón de intereses, **debajo**
      del EBITDA en vez de arriba. Ahora tiene línea propia, `OTHER_EXPENSES`
- [x] Delta medido: **cero**. El camino que usaba ese mapa es el último
      recurso del motor y en producción nunca corre (existen `account_mapping` y
      `report_line_config`). La prueba `tests/test_belowgop_8020.py` cruza el
      motor contra el Excel de mapeo para que no se vuelvan a separar

### A2 — Área Recreativa a OVERHEAD (D4) ✅

- [x] `pl_kind = OVERHEAD` en `department_catalog`, `OPEX_AREC` → **`OH_AREC`**
      en `report_line_config` y en las reglas de `account_mapping` del depto 270,
      y `AREC` movido a `OVERHEAD_DEPT_GROUPS` en el motor
- [x] **El GOP NO se movió.** `REV_AREC = $0` en los 12 escenarios y
      `OPEX_AREC = $41.04` solo en las cinco versiones 2027. Con el ingreso
      adentro el GOP es idéntico por construcción: lo que sale de Utilidad
      Operativa entra a Overhead y se resta igual
- [x] **Su ingreso SE QUEDA en `INGRESOS TOTALES`.** El Excel lo bota, pero el
      escaneo marcó ese punto para confirmar, no para copiar: «si el área genera
      ingreso real, hoy se está perdiendo del estado de resultados»
      (`ESCANEO_03` §5.12). Hoy vale $0, así que la decisión no mueve un centavo
      y se revierte con una línea si el owner prefiere lo contrario
- [x] `/admin/control`: `DROP = 0`, `perdido = $0.00`, `pares_ambiguos = 0`,
      `mapeos_a_línea_inexistente = 0` en los 12 escenarios

### A3 — Honorarios de administración ✅

**Decisión: se dejan las DOS líneas abiertas.** El 3% de management fee y el 5%
de royalties son conceptos distintos aunque el GL los junte en la 8005;
`TOTAL_RENT_MGMT_FEES` las vuelve a sumar, así que el consolidado sale igual en
las dos lecturas y no se pierde detalle.

Buscando eso aparecieron **dos defectos reales**:

- [x] **La fórmula pisaba el dato digitado.** `seeds["MGMT_FEE_3"] = …` corría
      DESPUÉS de los seeds del checkbook y asignaba con `=`: cualquier honorario
      escrito en el mini-checkbook de below-GOP quedaba pisado, y **sin
      porcentaje cargado lo pisaba con CERO**. Ahora el porcentaje es un driver
      opcional: manda solo si está configurado
- [x] **La 8005 tenía dos reglas activas para el mismo `(0250, 8005)`**, una
      hacia cada línea. El resolvedor hace `setdefault`, así que ganaba la fila
      que estuviera físicamente primero — y ese orden cambia cada vez que se
      recarga el mapeo. Queda **una sola regla** (`MGMT_FEE_3`); la de royalties
      se **desactiva**, no se borra, para que se lea como decisión

### Hallazgos que quedan anotados (no se tocaron)

1. **5 filas caen por FALLBACK de cuenta** en los escenarios importados:
   ingreso de lavandería cargado en el depto `0161` en vez del `0162`, y
   misceláneos / sustainability en el `0240` en vez del `280`. **Aterrizan en la
   línea correcta** (`REV_LAUNDRY`, `REV_MISC_OTHER`, `REV_SUSTAINABILITY`) y no
   se pierde plata, pero el ruteo depende del orden físico de las filas. Se
   arregla agregando reglas exactas para esos pares.
2. **`OPEX_MISCELLANEOUS`** es la tercera línea `MAPPED` sin ninguna regla de
   cuenta (además de `LARGE_CAPEX` y `ASSET_LOSS`, que sí están explicadas).

## 1.B — Idioma español / inglés (D1, D2)

### Lo que NO se traduce

- Acrónimos y totales USALI: `GOP`, `EBITDA`, `EBT`, `RevPAR`, `ADR`, `NOI`,
  `FTE`, `P&L`, `F&B`, `COGS`, `USALI`
- Roles de columna: `Actual`, `Budget`, `Forecast`, `Var`, `YTD`, `LY`
- Las ~7,206 descripciones del catálogo de cuentas y todo nombre atado al GL
- Nombres propios: Innoceana, Crowther Lab, Club Madresal, Claro del Bosque,
  los room types, nombres de empleados
- **Los exports Excel/PDF**: canónicos en inglés, nombres de hoja fijos
  (`00_DASHBOARD`, `TAX_PANORAMA`, `10_PL_FULL_DETAIL`)

Glosario completo en `docs/I18N_PLAN.md` §3.

> **1.B CERRADO — 2026-08-12.** Migracion `096`, 534 pruebas, build limpio,
> verificado en el navegador: el boton cambia el menu, el login y el
> `<html lang>` en los dos sentidos.

### Estado al arrancar (2026-08-11): nada empezado

`next-intl` no instalado · `hotels.default_locale` no existe ·
`users.locale` no existe · `app/layout.tsx` con `<html lang="es">` fijo ·
sin hook `t()`.

Tamaño: **92 archivos**, **27,090 LOC**, **73 páginas**, **~1,030 strings**,
**56 `HTTPException`**.

### B1 — Fundación ✅

- [x] `next-intl` **4.13.6** (soporta Next 14; peer `^12 || ^13 || ^14 || ^15 || ^16`)
- [x] Migración **`096`**: `hotels.default_locale VARCHAR(5) NOT NULL DEFAULT 'es'`
      + `users.locale VARCHAR(5) NULL`. **Nullable a propósito**: `NULL` = «usá
      el del hotel», distinto de «elegí español» — sin esa distinción, mover el
      default de la propiedad no le llegaría a quien ya tuviera algo guardado
- [x] Resolución en **UN solo lugar**: `backend/app/i18n.py`, función
      `resolve_locale(user_locale, hotel_locale)`
- [x] `GET`/`PATCH /api/provisioning/{hotel_id}/locale/` (el PATCH con
      `get_current_admin`). **Distinto de lo planeado**: el plan decía
      `/api/hotels/{id}/locale`, pero no existe un router de hoteles y el
      `<select>` vive en Provisionamiento, así que el endpoint quedó ahí
- [x] `PATCH /api/auth/me/locale` (cualquier usuario; acepta `null` para volver
      al default de la propiedad)
- [x] `frontend/i18n/request.ts` con `getRequestConfig` leyendo `finplan_locale`
- [x] `NextIntlClientProvider` sobre `TopNav` + `AuthGate` en `app/layout.tsx`,
      con `<html lang={locale}>` dinámico
- [x] `/auth/login` y `/auth/bootstrap` devuelven el locale **ya resuelto**, y
      `persistSession` lo copia a la cookie
- [x] `<select>` «Idioma de la propiedad» en **Master Data → Provisionamiento**
- [x] Botón **ES/EN** en el header (`components/LanguageSwitch.tsx`)
- [x] `messages/es.json` + `messages/en.json` con `nav.*`, `common.*`, `auth.*`,
      `validation.*` y los namespaces `dashboard.*` / `reports.*` / `pl.*`
      sembrados vacíos para la extracción que viene
- [x] Piezas compartidas servidor/cliente en `frontend/lib/locale.ts`, **sin
      imports**: lo usan `i18n/request.ts`, `lib/api.ts` y los componentes, y
      cualquier import de `lib/api` desde ahí armaría un ciclo

**Verificado en el navegador** (no supuesto): con la cookie en `en` el login
dice «Sign in to continue», el menú dice Scenarios / Financial Statements /
Reports y `<html lang="en">`; apretando **ES** vuelve a «Iniciar sesión»,
Escenarios / Estados financieros / Reportes y `<html lang="es">`. Los dropdowns
traducen también sus encabezados de sección.

> Usar `next-intl` en modo **«without i18n routing»**: sin segmento `[locale]`,
> sin renombrar páginas, sin tocar los `<Link>`.

### B2 — Chrome compartido ✅

- [x] El array `NAV` de `components/TopNav.tsx` → `nav.groups` / `nav.items` /
      `nav.headers`. **Los rótulos salieron del código**: lo que queda es la
      estructura, que es lo único que no cambia con el idioma
- [x] `AuthGate`, `app/login`, «Salir» / «Iniciar sesión» / «admin» → `common.*`
      y `auth.*`
- [x] `validation.*` sembrado (required, minChars, invalidNumber,
      unsavedChanges); las validaciones de cada pantalla se extraen al pasar
- [x] **Spanglish normalizado al extraer**: los términos hoteleros y los
      acrónimos USALI (P&L, GOP, Rack Rates, Cash Flow, Room Stats, Net Rate)
      quedan en inglés en los DOS idiomas, por D2. Se tradujo el chrome
- [x] La fecha del header ya cambia de locale (`es-CR` / `en-US`). El resto de
      los formatos de plata y mes sigue fijo — es el tramo pospuesto de abajo

### Pospuesto a propósito (NO es Fase 1)

| Tramo | Esfuerzo |
|---|---|
| Formato de plata y meses por locale (~41 formateadores duplicados) | 2-3 días |
| Las 73 páginas | 2-4 semanas |
| Los 56 mensajes del backend | 3-5 días |
| Labels descriptivos de BD | 1-2 semanas |

**Por qué:** la fundación NO crece con el producto; la extracción sí (creció 49%
en dos meses). Se pone la base ya y se extrae al pasar.

### Riesgos de i18n

**R1 — El más real.** `next-intl` asume el locale en la URL; acá vive en la BD.
Y el auth es **JWT en `localStorage`**, que el servidor NO puede leer. Por eso
la cookie `finplan_locale`, escrita al login. Si se desincroniza, las páginas
SSR salen en el idioma equivocado y cuesta verlo.
→ **Cómo quedó:** la cookie se escribe en los DOS únicos momentos en que el
idioma puede cambiar (al entrar, con el valor resuelto que devuelve
`/auth/login`; y al apretar ES/EN). El botón además recarga, porque los mensajes
se resuelven en el servidor: sin recargar, media pantalla quedaría en el idioma
viejo. Si el backend no responde, el idioma igual cambia en esa sesión — lo que
se pierde es la persistencia, no el cambio.

**R2 — Los importers borran y reinsertan.** `mapping_loader` hace `DELETE` +
reinsert por `REPORT_ID`. Las traducciones de BD deben clavar en **llaves de
negocio** (`report_id`, `line_code`, `account_code`), nunca en el id de fila.

**R3 — Español colado en sets «ingleses»** (`Cafetería`, `Área Recreativa`,
`Administrations`[sic]). Cada string se clasifica a mano; no hay diccionario.

**R4 — Encoding al GENERAR archivos.** La BD está limpia. Usar **Bash o
`-Encoding utf8`**, nunca el default de PowerShell.

**R5 — Vocabularios duales en `pl_engine`** (`_PL_ALIASES` / `_MOTOR_TO_CANON`)
pueden emitir el mismo total bajo dos `line_code`. El namespace `pl.*` DEBE
mapear ambos a una sola clave.

### Regla que no se rompe

**El motor sigue siendo Python puro.** NO se le pasa locale a nada de
`backend/app/engine/`. El motor emite `line_code` estable: **el código es el
contrato**, el inglés es el fallback, la traducción ocurre en el frontend.

Es la misma regla del provisionamiento de departamentos: la presentación filtra
y traduce, el cálculo nunca se entera. Hay una prueba que falla si `engine/` lee
la habilitación de departamentos; **ya existe la equivalente para el locale**:
`tests/test_i18n_locale.py::test_el_motor_no_se_entera_del_idioma` recorre
`backend/app/engine/` y falla si alguno importa `app.i18n`, llama a
`resolve_locale` o menciona la cookie.

---

# FASE 2 — P&L Full Detail

> ✅ **FASE 2 CERRADA — 2026-08-12.** `GET /api/reports/pl-full-detail/{id}/` +
> `/reports/pl-full-detail` en el menú Reportes. 555 pruebas, desplegado y
> verificado contra producción con token de admin.
> **10 de los 12 escenarios amarran AL CENTAVO** contra el P&L del motor. Los 2
> que no son descuadres del DATO subido, no del reporte (detalle abajo).

## 2.0 Qué es

**No es un reporte nuevo desde cero ni una carga de datos.** El owner:

> «ya existe en la memoria este mismo reporte… sería agarrar los departamentos
> que ya hay en el master data y convertir a este formato.»

El sistema **ya calcula** estos números. Falta la **presentación**: tomar los
departamentos del master data y volcarlos en la forma exacta del Excel.

**Para qué sirve:** máximo detalle para revisión. Es la vista con la que se
audita el presupuesto línea por línea. **Es un reporte DISTINTO** (D5): convive
con `/reports/pl-full` y `/reports/pl-by-dept`, no los reemplaza, porque hoy no
hay ninguno con este nivel de detalle.

**Dónde vive:** menú **Reportes** (D6).

**El archivo:** `docs/fase2/PL_DETALLADO_FORMATO.xlsx`, hoja `P&L Full Detail`.

## 2.1 Anatomía del Excel (escaneo de 5 agentes)

**1,007 filas × 17 columnas útiles.** C = etiqueta · **D..O = los 12 meses** ·
P = separador vacío · **Q = Total Año**. Las otras 192 columnas están vacías;
`HB29:HB42` es una lista de validación rota (en inglés, **le falta February**).

**CERO números propios.** 10,122 fórmulas, 1,118 textos, 0 constantes. Todo
apunta a `BUDGET 2026-AMA.xlsx` (**Amarena**), hoja `Budget 2025W`. Sin ese
libro es una hoja de ceros. Solo usa 3 funciones: `SUM` (853), `IFERROR` (110),
un `IF`.

**Es generable, no dibujado.** 16 banners de departamento aplican la MISMA
plantilla:

> INGRESOS → COSTO DE VENTAS → NÓMINA → Gastos Operativos → UTILIDAD NETA

y el sub-bloque **NÓMINA es idéntico 13 veces** (16 conceptos, mismo orden;
Tours suma un 17.º). Las ~670 filas de detalle salen de **~462 definiciones de
catálogo**.

**La jerarquía NO está en la sangría** (`indent = 0` en las 1,007 filas): está
en el **color de relleno**. Son **13 estilos**.

Detalle completo en `docs/fase2/ESCANEO_0{1..5}_*.md`.

## 2.2 Cuánto se puede alimentar hoy

De las **781 líneas etiquetadas**:

| Escenario | % | Por qué |
|---|---|---|
| Importados (Actual/Budget/Forecast 2024-2026) | **90%** | Traen el detalle por cuenta |
| **Budget 2027 del checkbook** | **63%** | Sin ingresos por cuenta, 3 de 35 líneas de costo, below-GOP vacío |
| Lo que el P&L emite hoy como línea propia | **10%** | `report_line_config` llega a DEPARTAMENTO (89 líneas), no a cuenta |

**Ese 10% vs 90% ES el trabajo.** El dato existe a nivel cuenta
(`account_mapping`: 961 reglas, 235 cuentas — prácticamente el catálogo del
Excel). Falta el **ensamblador** que arme el reporte desde ahí en vez de desde
`report_line_config`.

Calzan cuenta por cuenta: 16 conceptos de planilla × 12 deptos (192 líneas),
293 de 306 gastos operativos, 32 de 35 costos de venta, 10 de Ingresos Varios,
14 de costo de A&B.

## 2.3 Decisiones de arquitectura (salen del escaneo)

1. **El detalle por departamento es la fuente única; el consolidado se DERIVA.**
   En el Excel son dos lecturas independientes del mismo libro, sin una celda
   que las compare: cuadran por consistencia del origen, no por diseño. Hay 35
   filas de total huérfanas.
2. **La etiqueta NO identifica:** hay **83 duplicadas**. Cada fila va amarrada
   al **código de cuenta + departamento**, nunca al texto.
3. **Las 265 filas ocultas son departamentos enteros colapsados** (Tienda de
   Regalos, Bar Privado, Sistemas de Información, Ingresos Varios, media A&B) y
   **siguen sumando en los totales**. En web: **colapsables, nunca excluidas del
   cálculo**.

## 2.4 Rooms abierto en sus tres sets (D7)

El Excel trae un bloque de KPIs arriba (filas 3-8). En el reporte nuevo **se
repite por set**: Rooms Standard · Villas (0115) · Residencias (0116), cada uno
con habitaciones disponibles · ocupadas · **% ocupación** · huéspedes · **ADR** ·
**RevPAR** · ingreso · costo. Más el consolidado.

**Casi todo existe.** `GET /api/reports/rooms-sets/{scenario_id}`
(`backend/app/api/rooms_sets_api.py`) ya devuelve por set el `revenue`, el
`costo` abierto en payroll/opex/distribución, el `fte`, las
`noches_disponibles` y las `noches_ocupadas`, mes a mes:

```
ocupación = noches_ocupadas / noches_disponibles
ADR       = revenue / noches_ocupadas
RevPAR    = revenue / noches_disponibles
```

**Falta DATO, no código:** `SH07 Villas Deluxe` tiene unidades pero **0% de
ocupación todo el año**; `SH08 Residencia` tiene 1 unidad. Hasta que se les
cargue ocupación y tarifa, ADR y RevPAR salen en cero.

⚠️ Sus unidades **sí suman noches disponibles al consolidado**: con ocupación en
cero, diluyen la ocupación general y el RevPAR del hotel.

## 2.5 Bugs del Excel original — NO replicar

Los cinco vienen de lo mismo: **el archivo se armó para un ejercicio que arranca
en mayo** y las fórmulas de Ene–Abr nunca se revisaron. Están latentes porque
Ene–Abr y Área Recreativa valen 0 hoy.

1. **Fila 78** — Ene–Abr suma `D65:D77`, que **incluye la fila 65 (UTILIDAD
   OPERATIVA)** dentro del overhead. Como GOP = 65 − 78, **corrompe el GOP** de
   esos 4 meses. El único que daña un resultado.
2. **Fila 50** — Ene–Abr suma 9 líneas, May–Dic suma 8 (se cae «Ingresos
   Varios», fila 48).
3. **Fila 942** — resta dos veces la nómina de Área Recreativa. Causa: filas
   938 y 940 con la MISMA etiqueta y contenidos distintos.
4. **Fila 137** — descuenta dos líneas de Área Recreativa del opex total.
   Deliberado, pero es regla de negocio escondida en una fórmula.
5. **Fila 76** — meses de adentro, anual de afuera.

**Defectos de formato:** los ratios `% de Ingresos del Depto.` y `% Utilidad`
**tienen formato de moneda** (se ven `$0.35` en vez de `35.00%`) → **se corrige**.
Los negativos van entre paréntesis y en rojo, **el cero no se imprime**, y los
números están **centrados** (decisión del autor; en web se alinean a la derecha,
que es lo legible para columnas de cifras).

## 2.6 Los huecos

| # | Hueco | Tamaño |
|---|---|---|
| 1 | **El ensamblador del reporte** | **GRANDE** — el trabajo real |
| 2 | Estadísticas de socios del Club Madresal (4 líneas): existe la plata, no el conteo de socios | CHICO |
| 3 | Departamento **Bar Privado** completo (31 líneas) — no existe | MEDIANO |
| 4 | Apertura de A&B por outlet (18 líneas: el Excel abre 4 sub-cuentas por familia, el sistema tiene 1) | MEDIANO |
| 5 | Ingresos por cuenta en el checkbook | GRANDE — probablemente la respuesta correcta es NO abrirlos: hoy salen de rate cards a nivel línea, que es más sano |

## 2.7 Los cinco archivos que toca un reporte nuevo

Patrón del último construido («Planilla x Posición», 2026-08-11):

| | Archivo |
|---|---|
| Endpoint | `backend/app/api/<nombre>_api.py` — nuevo `APIRouter` |
| Registrar | `backend/app/main.py` — import + `include_router(..., prefix="/api", dependencies=_guard)` |
| Cliente | `frontend/lib/api.ts` — interfaces + `getXxx()` |
| Pantalla | `frontend/app/reports/<ruta>/page.tsx` |
| Menú | `frontend/components/TopNav.tsx` — grupo «Reportes» |

**Convenciones ya resueltas, copiarlas:**

- Envolver la tabla en `className="fin-sticky"` **con contenedor que scrollee
  por su cuenta**. Hay una regla global que pega el `<thead>` al viewport
  (`top: 44px`) y sin eso **la primera fila queda escondida** — pasó dos veces.
- Los totales se arman **sumando los renglones YA REDONDEADOS**, no redondeando
  el total aparte, o la fila se descuadra por un centavo.
- Contenido ancho: `overflow-x: auto` en su contenedor. La página nunca
  scrollea de lado.
- Números con `fontVariantNumeric: "tabular-nums"`.

## 2.8 Criterio de terminado ✅

- [x] **Amarra al dólar** en 10 de los 12 escenarios, medido escenario por
      escenario contra el motor. Los 2 que no:
      **Actual 2024** (ingresos −3,085.07 · gastos +40,613.30 = 1.47%) y
      **Actual 2025** (gastos −455.68). Son descuadres **del dato**, no del
      reporte: el resumen sale del snapshot que subió el owner y el detalle sale
      del GL del mismo archivo. Los dos ya estaban documentados —el 1.5% de
      Actual 2024 por el reparto, y el overhead de Actual 2025 que no cuadra en
      julio (−686) y diciembre (+588), que la Vista previa del importador ya
      señalaba. El reporte los muestra con el mensaje que explica cuál de los
      dos lados mirar
- [x] En los escenarios de **checkbook** el gasto amarra al centavo. El ingreso
      sale vacío **a propósito**: viene de rate cards a nivel de línea y
      prorratearlo por cuenta sería inventar números (es la opción «(c) es lo
      honesto» del escaneo §6). El reporte lo dice en vez de dibujar un cero
- [x] `/admin/control`: `DROP = 0`, `perdido = $0.00`, `pares_ambiguos = 0`
- [x] **555 pruebas** (497 al arrancar → 21 nuevas solo de este reporte)
- [x] Los 5 bugs del Excel NO están replicados, y hay una prueba por cada uno
- [x] Rooms abre en sus 3 sets con ocupación, ADR y RevPAR, más el consolidado

### Dos cosas que aparecieron construyéndolo

1. **La cuenta `4900` de Lavandería empieza con 4 pero NO es ingreso**: es el
   crédito del reparto, el gasto que se fue. Eran los **$18,852.40** que le
   faltaban al ingreso de Actual 2026 y le sobraban al gasto, y **$47,613.19**
   en Budget 2026. Se clasifica preguntándole al mapeo —si no resuelve a una
   línea `REV_*`, no es ingreso— y no con una lista escrita a mano, así la
   próxima cuenta de reparto se clasifica sola.
2. **Un forecast con corte de actuales no se lee entero de sí mismo.** Los meses
   cerrados los toma del ACTUAL vinculado, igual que el motor. Sin ese blend, el
   Forecast Working 2026 mostraba la proyección debajo de un resumen que mostraba
   lo real: **+124,824.69** de ingreso y **+340,419.67** de gasto que no eran de
   nadie.

### Lo que quedó afuera (los huecos del §2.6, sin tocar)

| Hueco | Estado |
|---|---|
| Estadísticas de socios del Club Madresal (4 líneas) | ✅ hecho — mig `098`, se carga en Room Stats y se ve en el reporte |
| Departamento **Bar Privado** (31 líneas) | no existe; decidir si es depto propio o sub-depto de A&B |
| Apertura de A&B por outlet (18 líneas) | el GL de CWL tiene 1 cuenta por familia, no 4 |
| Ingresos por cuenta en checkbook (60 líneas) | **no se hace a propósito** — ver arriba |
| Export a Excel del reporte | ✅ hecho — `GET /reports/pl-full-detail/{id}/export/` + botón «⬇ Excel» |

También quedó anotado: la cuenta **`4000` se llama «Cancellations»** en el
catálogo pero es la que carga TODO el room revenue ($1,706,130 en Actual 2026).
El nombre miente; el número está bien. Cambiarlo es alta en `accounts` +
`account_mapping`, no código.

---

## Trampas del sistema (valen para cualquier trabajo acá)

0. **El SEED manda sobre `account_mapping` y `report_line_config`, no las
   migraciones.** `backend/Procfile` arranca con
   `alembic upgrade head && python -m app.seed && uvicorn`, y
   `app/seed_mapping.py` re-afirma **campo por campo** todas las filas de esas
   dos tablas desde `app/seed_data/mapping_pl.json`. Una migración que las toque
   y NO cambie el JSON **se revierte sola en el próximo deploy** — pasó con las
   093/094/095, que corrieron, se midieron y quedaron verificadas antes de que
   el deploy siguiente las borrara. Es el modo de falla más caro del sistema
   porque **el total sigue cuadrando**: no hay error, no hay alerta, y la plata
   cambia de línea sola.
   Además el seed **no borra lo que sobra** (a propósito), así que renombrar una
   fila deja **las dos**: la vieja vuelve del JSON y la nueva queda huérfana.
   Blindado por `tests/test_seed_manda_sobre_mapeo.py`.

1. **`PUT /payroll/{id}/bulk/` BORRA toda la planilla y la recrea.**
   `payroll_concept_entries` cuelga de la posición con `ON DELETE CASCADE`: se
   lleva horas extra, comisiones, bonos, transporte y vivienda **digitados**, y
   el recálculo solo repone 6000, 6020 y 6021. Para agregar existe
   `POST /payroll/{id}/positions/add/`. Aplica a cualquier endpoint que empiece
   con un `delete()`.

2. **Un departamento o cuenta SIN regla de mapeo no da error: cae al FALLBACK y
   aterriza en la línea de otro.** Pasó tres veces (la 6004 sin mapear, Villas
   sin mapeo, el crédito 4999 de Rooms restando de Cafetería). El total sigue
   cuadrando, así que **solo se ve en el P&L por departamento**. Verificar
   siempre `/admin/control`.

3. **Un recálculo que falla revierte la transacción entera y no deja rastro.**
   Síntoma: «apreté y no cambió nada». Mirar los logs de Railway PRIMERO.

4. **El P&L se recomputa siempre con el motor de HOY.** `pl_lines` se escribe y
   nunca se lee. Enllavar NO congela los números; lo único que congela es
   `cashflow_versions` / `big_picture_versions`.

5. **Las filas `(Actual GL)`** (`position_code = 'GL'`, una por depto y por
   escenario de actuales) **no son personas**: traen el costo del GL. Excluirlas
   de todo conteo de headcount y de las auditorías de código duplicado.

6. **Los repartos corren en cadena y el de Rooms va AL FINAL.** Ver
   `_recalc_allocations` en `backend/app/engine/recalculate.py`.

---

## ▶️ RETOMAR ACÁ (2026-08-11, contexto limpiado)

> **Frase de arranque del owner: «Arrancá las fases».**
> Significa: trabajar sin parar hasta terminar las dos, sin pedir permiso entre
> tramos. Orden: **1.A (below-GOP) → 1.B (idioma) → Fase 2 (P&L Full Detail)**.
> Cerrar cada tramo entero —código, pruebas, migración, push, deploy,
> verificación— y **anotarlo en la bitácora** antes de pasar al siguiente.
> Todo cambio que mueva un número del P&L se **mide antes y después** y se
> reporta el delta. Solo se para si algo contradice una de las 7 decisiones
> cerradas o si un cambio destruiría datos de forma irreversible.

**✅ LAS DOS FASES ESTÁN COMPLETAS.** Alembic en `096`, **555 pruebas**, todo
desplegado y verificado contra producción.

| Tramo | Qué quedó |
|---|---|
| **1.A** | below-GOP con una sola verdad (migs `093`/`094`/`095`) |
| **1.B** | idioma es/en (mig `096`) |
| **Fase 2** | `/reports/pl-full-detail` — el P&L cuenta por cuenta |

**Lo que le toca al owner** (nadie más lo puede resolver):

1. **Los dos descuadres del dato.** `Actual 2024` (1.47%, el reparto) y
   `Actual 2025` ($455.68, el overhead de julio y diciembre). El reporte los
   señala; hay que corregir el archivo que se subió, no el reporte.
2. **Villas y Residencias.** En el `Budget Working 2027` ya tienen ocupación
   (22.88% y 18.30%), pero en los demás escenarios siguen en cero — y sus
   unidades igual suman noches disponibles, así que diluyen la ocupación
   general y el RevPAR del hotel. El reporte lo avisa por set.
3. **Los 7 comentarios** de las celdas `C567:C586` del Excel, por si dicen algo
   sobre cómo debe calcularse alguna línea.
4. **La cuenta `4000`** se llama «Cancellations» y es la que carga todo el room
   revenue. Conviene renombrarla.

**Si se quiere seguir**, los incrementos naturales están en §2.6 y en el cuadro
«Lo que quedó afuera» de §2.8: estadísticas de socios del Club Madresal,
departamento Bar Privado, apertura de A&B por outlet y el export a Excel del
reporte nuevo. Y del lado del idioma, la extracción de las 73 páginas, que se
pospuso a propósito (la fundación no crece con el producto; la extracción sí).

## Bitácora

| Fecha | Qué se hizo | Commit |
|---|---|---|
| 2026-08-12 | **El detalle por departamento cierra con utilidad, y Rooms se abre en cuatro.** En los escenarios de checkbook el ingreso se presupuesta a nivel de LÍNEA y el reporte solo sabía leer cuentas: cada bloque mostraba puro gasto y Rooms daba «utilidad −$645,551», su costo con el signo cambiado. Ahora cada línea entra como fila con su nombre, en el departamento del GRUPO con que el motor la empareja (no el del mapeo: el Spa factura por la 0130 y gasta por la 0140). **Los seis escenarios de checkbook pasan a cuadrar ingreso Y gasto al centavo** — antes el ingreso ni se comparaba. Rooms se abre en consolidado + Standard + Villas + Residencias, con estadísticas, ingreso, nómina, opex y utilidad; los tres sangrados y marcados «no suma aparte». **El consolidado no consolidaba**: con reparto activo el costo de las villas vive en 0115/0116 y salían como bloques sueltos sin ingreso. **Hallazgo del dato:** en el Budget 2027 Working los drivers facturan **$326,712** de Villas/Residencias que la línea del checkbook no tiene — el P&L usa la línea, así que ese ingreso no está; se sincroniza re-empujando drivers → checkbook. La apertura NO aplica a importados (fuentes distintas; en Budget 2026 Final daba $79,268 de diferencia) | `cb1449d` |
| 2026-08-12 | **El provisionamiento ahora esconde de verdad.** El owner desmarcó Área Recreativa y Crowther Lab y no desaparecieron: nada se había guardado (desmarcar no guarda solo, y el 270 tiene 14 posiciones así que sale el aviso que pide confirmar) **y aunque se hubiera guardado tampoco pasaba nada** — la matriz estaba a medias: la capa que registra la decisión funcionaba, la que la aplica nunca se cableó. La respetaba una sola pantalla (el tab del Club). Regla en `app/api/_apagados.py`; `/departments/` —el embudo de todos los selectores— devuelve ahora también qué escondió la propiedad, **en la misma respuesta** para que ninguna pantalla pinte la lista antes de saber qué esconder. Los tres checkbooks de carga (OPEX, Costos, Planilla) piden SU dimensión. Verificado en el navegador con el caso real: el `0180` desapareció de Planilla y sigue en OPEX. **Sigue sin restar del P&L** — hay prueba que falla si el motor mira esta matriz. Reportes: pendiente, por decisión del owner | `393a718` |
| 2026-08-12 | **El Club tiene TRES ingresos, no uno.** El owner pasó las tres líneas como las lleva el catálogo: `4500` la cuota (driver), `4501` actividad fin de año, `4502` visitantes. La versión anterior tenía UNA línea y un «otros» anónimo: el total cuadraba pero el reporte cuenta por cuenta mostraba un bulto donde el mayor tiene tres renglones. **Los nombres no se inventaron**: ya estaban en `account_mapping` (depto 260) y una prueba los compara contra `mapping_pl.json` para que no se separen. Las tres caen en `REV_CLUB` como Food+Beverage+Misc caen en `REV_FB`, así que partir la línea no mueve el total. Mig `100`. **Ojo con leer el código de cuenta solo:** 4500/4501/4502 los comparten Club, INNOCEANA y Claro Huerta — por eso la hoja del owner mostraba «Ingreso Innoceana #3» al lado de la 4502; lo que identifica la línea es el par (depto, cuenta). De paso, el Club **no estaba en `total_revenue`** de `RevenueResult`: el P&L lo sumaba y la pantalla de ingresos no. Corregido con delta $0 medido (hoy está en cero) | — |
| 2026-08-12 | **El Club Madresal, movido y convertido en driver.** El owner lo sacó de Room Stats —ese tab va para los dueños de CWL y las membresías son de Amarena— y pidió tab propio «como el Spa, externo», con la cuota como driver del ingreso. Tab en Planning → Ingresos: `socios(base) × cuota + otros`, se guarda y se **empuja a la línea CLUB del checkbook**, que es de donde el P&L lee. Al hacerlo apareció que **el checkbook no tenía línea de Club**: por eso `REV_CLUB` daba cero en el Budget 2027 — no faltaba carga, no había por dónde. Se abrió la cadena entera. Mig `099`. Medido de punta a punta: $55,400 en el driver = $55,400 en `REV_CLUB` | `e5be77e` |
| 2026-08-12 | **Aviso cuando el escenario no lee el checkbook.** Probando lo anterior el P&L dio CERO sin un solo error: la línea CLUB se escribe siempre, pero un escenario en modo `drivers` arma los ingresos con tarifas y ocupación y ni la mira. Los 2027 están en `checkbook` (ahí funciona); los 2028+ no. No se bloquea el guardado, pero la pantalla lo dice | `aad39a0` |
| 2026-08-12 | **El Spa tenía el mismo hueco — cerrado.** Su mensaje de guardado hasta decía «→ línea SPA del checkbook», que suena a trabajo terminado. La regla se mudó a `app/api/_llega_al_pl.py` (mismo patrón que el candado) y una prueba falla si un driver se escribe su propia copia. **Revisada la clase entera:** los otros dos que escriben líneas de ingreso no tienen el problema —la pantalla del checkbook ya avisaba y tiene el interruptor de fuente; el push drivers→checkbook devuelve el diff—, y un centinela recorre los módulos y falla, con nombre, si aparece un tercer escritor que nadie haya decidido. Los avisos ahora dicen **dónde** se arregla. 619 pruebas | `e8c04e9` |
| 2026-08-11 | Escaneo del Excel con 5 agentes → `docs/fase2/ESCANEO_0{1..5}` | `99fc800` |
| 2026-08-11 | Plan cerrado con las 7 decisiones del owner | `66f0fec` |
| 2026-08-12 | **Socios del Club Madresal** (hueco 2). El Club vende ACCESO a las instalaciones; el desarrollo inmobiliario de atrás no es parte de este P&L y la cuota ya vive en `REV_CLUB` — el conteo explica de dónde sale, y por eso es estadístico y no toca ninguna línea (hay prueba que falla si el motor lo lee). Mig `098`. **El total del año es DICIEMBRE, no la suma** (867 ≠ 129), y distingue «diciembre en cero» de «diciembre sin cargar» — el primer intento mostraba 35 condicionados que ya no existían. **Se apaga desde Provisionamiento** (depto 260), no con un `if` por hotel: el owner avisó que desaparece cuando el Club se opere por fuera | `e7299bd` |
| 2026-08-12 | **Export a Excel del P&L Full Detail** — `GET /reports/pl-full-detail/{id}/export/` + botón en la pantalla. Una hoja por bloque, CUADRE primero. Se respeta el formato del owner (paréntesis rojos, cero sin imprimir) y se corrige lo que estaba mal (ratios como % y no como moneda, números a la derecha, jerarquía también en la sangría). El exportador NO recalcula: usa el mismo payload de la pantalla | `465e211` |
| 2026-08-12 | **🔴 El seed revertía las migraciones del mapeo.** `python -m app.seed` corre en cada deploy y re-afirma `account_mapping` + `report_line_config` desde `mapping_pl.json`: se llevó puestas las 093/094/095, y la 094 dejó `OPEX_AREC` y `OH_AREC` conviviendo. Arreglado donde manda (el JSON) + mig `097` para la base actual + regla permanente en CLAUDE.md + `test_seed_manda_sobre_mapeo.py`. De paso, el FALLBACK del resolvedor dejó de depender del orden físico de las filas. **Verificado: sobrevivió a dos deploys** | `ba2f5db` |
| 2026-08-12 | **Fase 2 cerrada** — `P&L Full Detail`: endpoint `pl_full_detail_api.py`, pantalla `/reports/pl-full-detail` y entrada en el menú Reportes. Ensamblador que lee el detalle a nivel CUENTA y lo sube en la forma del Excel; el resumen sale del motor y el reporte compara los dos y publica la diferencia. Los 5 bugs del Excel no se replican (una prueba por cada uno). Se cazaron la cuenta 4900 de Lavandería (crédito de reparto disfrazado de ingreso, $18,852 + $47,613) y el blend faltante del forecast (+$124,824 / +$340,419 fantasma). **10 de 12 escenarios amarran al centavo.** 555 pruebas ✅ | — |
| 2026-08-12 | **1.B cerrado** — fundación de idioma. Mig `096` (`hotels.default_locale` + `users.locale` nullable), `app/i18n.py` como único lugar donde se resuelve, `next-intl` en modo sin routing con la cookie `finplan_locale`, `<select>` en Provisionamiento y botón ES/EN en el header. Chrome traducido: los ~95 rótulos del `NAV`, `AuthGate` y el login. 534 pruebas ✅, build limpio, **verificado en el navegador en los dos sentidos** | — |
| 2026-08-12 | **1.A cerrado** — below-GOP con una sola verdad. Mig `093` (la 8020 y el mapa 8xxx alineados con `account_mapping`; `8030`/`8045` también estaban mal y la `8025` no estaba), `094` (Área Recreativa → overhead, su ingreso se queda), `095` (honorarios: dos líneas, una regla; la fórmula deja de pisar el dato digitado). 514 pruebas ✅. **Delta: $41.04 cambian de bloque en las cinco versiones 2027; GOP, EBT y Neto sin mover en los 12 escenarios.** `/admin/control` con DROP 0, perdido $0.00 y 0 pares ambiguos | — |

---

## Documentos hermanos

| Doc | Qué contiene |
|---|---|
| `docs/fase2/ESCANEO_01_FILAS.md` | Las 1,007 filas, tabla íntegra |
| `docs/fase2/ESCANEO_02_COLUMNAS.md` | Las 210 columnas y 14 rarezas |
| `docs/fase2/ESCANEO_03_FORMULAS.md` | Dependencias, subtotales, 15 decisiones |
| `docs/fase2/ESCANEO_04_FORMATO.md` | Los 13 estilos + tokens CSS listos |
| `docs/fase2/ESCANEO_05_MAPEO_AL_SISTEMA.md` | El cruce línea por línea |
| `docs/I18N_PLAN.md` | Plan largo de idioma: inventario, glosario, todas las fases |
| `docs/PROVISIONING_MASTER_DATA_PLAN.md` | Provisionamiento. La capa FINA ya está hecha; la GRUESA no |
| `docs/MULTIPROPERTY_PLAN.md` | Abrir Amarena / Oxígen / Ojochal |
| `CLAUDE.md` | Reglas del proyecto. **El motor es Python puro** |
