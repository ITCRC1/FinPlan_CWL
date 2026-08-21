# FinPlan — Módulo Break-Even (cálculo y modelo de datos)

**Versión 2** — corregida tras revisión con el método de 7 lentes. Los cambios respecto de la
v1 están en §9.

**Propiedad piloto:** SCP Corcovado Wilderness Lodge (CWL)
**Semillas:** `be_departments_seed.csv` (22 filas) · `be_classification_seed.csv` (567 filas)
**Modelo de referencia:** `BREAK_EVEN_CWL.xlsx`
**Interfaz:** `FINPLAN_TAB_BREAK-E.md`

---

## 1. Objetivo

Calcular el punto de equilibrio de cada propiedad a partir del P&L de FinPlan, separando cada
cuenta del catálogo en una porción **variable** y una **fija**. La separación es un porcentaje
editable por cuenta, no una etiqueta binaria.

Carga inicial: `Variable → pct_variable = 1.00` · `Fixed Cost → pct_variable = 0.00`.
El usuario edita `pct_variable`; el % fijo **siempre** se deriva como `1 - pct_variable`.
Nunca se almacenan ambos como campos independientes.

---

## 2. Modelo de datos

### 2.1 `be_department` — catálogo, no lista fija en código

Los departamentos crecen: hoy CWL usa 14 y hay 8 más en el catálogo GL que otras propiedades
van a necesitar. Si viven como enum en el código, cada propiedad nueva es un release.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | PK | |
| `slug` | varchar(40) UNIQUE | Llave estable: `rooms`, `fb`, `gift-shop`. **Nunca el nombre como llave** |
| `name` | varchar(60) | Nombre visible |
| `display_order` | int | Orden de los sub-tabs |
| `generates_revenue` | boolean | Si `false`, no se le calcula % MC ni equilibrio propio |
| `dept_codes` | varchar(60) | Códigos GL asociados, separados por coma |
| `status` | enum | `active` \| `pending_classification` |
| `property_id` | FK nullable | `NULL` = aplica a todas las propiedades |

Semilla: 14 activos (CWL) + 8 `pending_classification` — Private Bar, Tienda, Crowther Lab,
Claro Huerta, Cafetería, Club Madresal, Área Recreativa, Misceláneos.

### 2.2 `be_cost_classification` — la tabla que el usuario edita

| Campo | Tipo | Notas |
|---|---|---|
| `id` | PK | |
| `property_id` | FK | Resuelto desde `property_code` UNIQUE |
| `be_department_id` | FK → `be_department` | Nunca el nombre como texto |
| `dept_code` | varchar(6) NOT NULL DEFAULT `''` | **String vacío, jamás NULL** — ver §2.4 |
| `account` | varchar(10) NOT NULL DEFAULT `''` | Vacío en filas `LINEA` |
| `account_name` | varchar(120) | Descriptivo |
| `pl_line` | varchar(40) NOT NULL | `OPEX_ROOMS`, `COS_FB_FOOD`, … |
| `section` | varchar(40) | Sección FinPlan |
| `be_section` | varchar(40) | `PAYROLL`, `COST OF SALES`, `OPERATING EXPENSES`, … |
| `original_class` | enum | `Variable` \| `Fixed Cost` — referencia histórica |
| `pct_variable` | numeric(5,4) NOT NULL | `CHECK (pct_variable BETWEEN 0 AND 1)`. **Único editable** |
| `map_source` | enum | `GL` \| `LINEA` |
| `excluded_from_be` | boolean NOT NULL DEFAULT false | Ver §2.5 |
| `created_at`, `updated_at` | timestamptz | |
| `updated_by` | FK usuario | |

```sql
UNIQUE (property_id, dept_code, account, pl_line)
INDEX  (property_id, pl_line)            -- resolución de respaldo
INDEX  (property_id, be_department_id)   -- pantalla de configuración
```

### 2.3 `be_classification_snapshot` — congelar periodos cerrados

`pct_variable` no tiene dimensión de tiempo. Sin esto, ajustar un porcentaje en noviembre
cambia retroactivamente el punto de equilibrio de enero que ya se reportó.

Campos: `property_id`, `period`, `data_version`, `payload` JSONB (juego completo de
`pct_variable` al cierre), `frozen_at`, `frozen_by`.

El reporte de un periodo cerrado se lee del snapshot, nunca de la tabla viva.

### 2.4 Por qué `dept_code` y `account` van vacíos y no NULL

El seed carga con `ON CONFLICT (property_id, dept_code, account, pl_line) DO NOTHING`. En
Postgres `NULL ≠ NULL`, así que si las filas `LINEA` entraran con NULL, una segunda corrida del
seed las duplicaría en silencio. String vacío mantiene el constraint funcionando.

### 2.5 Exclusión del impuesto de renta

El impuesto viene marcado como `Fixed Cost` en Property Expenses, pero es **función del
resultado**, no un costo fijo. Si entra al cálculo, el equilibrio de CWL sube de $3,996,427 a
$4,109,443.

La exclusión es una **columna booleana**, no una comparación de texto contra
`be_section = 'INCOME TAX'`. Con texto, el día que alguien renombre la sección o que otra
propiedad la llame distinto, la exclusión deja de aplicar y el equilibrio salta $113k sin que
nadie lo note.

Hoy en CWL: una sola fila con `excluded_from_be = true` (`pl_line = INCOME_TAXES`, $75,044).

### 2.6 Resolución al calcular

1. Coincidencia exacta `(property_id, dept_code, account)`.
2. Si no existe, `(property_id, pl_line)` con `map_source = 'LINEA'`.
3. Si no existe ninguna: tratar el monto como **100% fijo** y registrarlo en `be_unclassified`,
   visible en la UI. Nunca fallar en silencio ni asumir variable.

La regla 3 importa: el catálogo GL crece, y una cuenta nueva que se asuma variable infla el
margen de contribución y baja artificialmente el equilibrio.

**La regla 2 ahora es determinista.** En la v1 las 40 filas `LINEA` se colapsaban en 18 líneas
P&L, con hasta 9 filas compitiendo por la misma clave — la resolución era ambigua y no había
forma de repartir el monto, porque FinPlan lo tiene agregado a nivel de línea. En la v2 hay
**exactamente una fila por `pl_line`**. El colapso no perdió información: los 18 grupos son
homogéneos, ninguno mezclaba `Variable` con `Fixed Cost`.

---

## 3. Cálculo

```
VC     = Σ (monto × pct_variable)          donde excluded_from_be = false
FC     = Σ (monto × (1 - pct_variable))    donde excluded_from_be = false
EXCL   = Σ (monto)                         donde excluded_from_be = true
REV    = Σ ingresos (secciones REVENUES)

CM     = REV − VC
CM%    = CM / REV
EBT    = CM − FC                           resultado antes de impuestos
NET    = EBT − EXCL                        resultado neto

BE_REV      = FC / CM%
BE_PCT      = BE_REV / REV
MOS         = REV − BE_REV
MOS%        = MOS / REV
OP_LEVERAGE = CM / EBT
```

### 3.1 Métricas de habitaciones

Suponen **mezcla de ingresos constante** — el supuesto más fuerte del modelo, hay que
declararlo en pantalla:

```
MIX_ROOMS      = REV_ROOMS / REV
BE_ROOM_NIGHTS = (BE_REV × MIX_ROOMS) / ADR
BE_OCCUPANCY   = BE_ROOM_NIGHTS / ROOMS_AVAILABLE
BE_TREVPAR     = BE_REV / ROOMS_AVAILABLE
REV_META       = (FC + utilidad_objetivo) / CM%
```

### 3.2 Equilibrio mensual

`BE_REV / 12` es un **prorrateo lineal** y en CWL engaña: la ocupación va de 52% en febrero a
0.7% en septiembre, así que un umbral plano de $333,036 mensuales no describe ningún mes real.

- **Fase 1:** mostrarlo rotulado literalmente como *"prorrateo lineal — no refleja
  estacionalidad"*. Nunca presentarlo como el equilibrio del mes.
- **Fase 2:** calcularlo mes a mes con los costos fijos y la mezcla de cada mes.

### 3.3 Versión de dato

Toda llamada de cálculo recibe **`data_version` obligatorio**: `ACTUAL` \| `BUDGET` \|
`FORECAST`. No hay valor implícito — sin el parámetro la llamada falla, porque un punto de
equilibrio calculado sobre la versión equivocada se ve idéntico a uno correcto.

El modelo de referencia en Excel usa `BUDGET` (Budget 2025 Dec).

### 3.4 Guardas obligatorias

- `CM% ≤ 0` → devolver `null` con el mensaje *"el margen de contribución es negativo: ningún
  nivel de ingreso cubre los costos fijos"*. No un cero ni un blanco.
- `REV = 0` → todos los ratios en 0, sin división por cero.
- `ROOMS_AVAILABLE = 0` → métricas de habitaciones en `null`, no en cero.

---

## 4. Departamentos

| slug | Nombre | Códigos GL | Ingreso | Líneas | Cuentas GL | Costo FY |
|---|---|---|---|---|---|---|
| `rooms` | Rooms | 0110, 0115, 0116 | Sí | 46 | 138 | $474,249 |
| `fb` | F&B | 0120 | Sí | 55 | 53 | $544,907 |
| `spa` | Spa | 0140 | Sí | 43 | 43 | $48,114 |
| `tours` | Tours | 0150 | Sí | 28 | 26 | $293,080 |
| `gift-shop` | Gift Shop | 0165 | Sí | 9 | 8 | $13,399 |
| `transportation` | Transportation | 0152 | Sí | 26 | 24 | $157,425 |
| `innoceana` | Innoceana | 0155 | Sí | 26 | 25 | $125,478 |
| `laundry` | Laundry | 0161, 0162 | Sí | 1 | 0 | $2,261 |
| `ag` | A&G | 0180, 0181, 0184 | No | 51 | 80 | $616,073 |
| `sales-marketing` | Sales & Marketing | 0190 | No | 44 | 44 | $433,387 |
| `maintenance` | Maintenance | 0200 | No | 48 | 48 | $476,415 |
| `information-system` | Information System | 0230 | No | 52 | 51 | $41,508 |
| `utility` | Utility | 0210 | No | 11 | 7 | $259,233 |
| `property-expenses` | Property Expenses | 0250 | No | 27 | 2 | $712,513 |
| | **Total** | | | **467** | **549** | **$4,198,042** |

Con las 18 filas `LINEA`, la tabla queda en **567 filas**.

Ingresos sin departamento de costo: `REV_CROWTHER_LAB` (0156) y `REV_MISC_OTHER` (280),
$220,059 combinados. Entran al MC al 100% y hay que marcarlos en la UI, porque en la práctica
sí tienen costo y hoy el margen queda sobreestimado.

---

## 5. Calidad del mapeo

De las 467 líneas: **427 (91%)** empatan con cuenta GL exacta (`map_source = GL`, 549 filas
expandidas a departamentos hermanos); **40 (9%)** se resuelven a nivel de línea P&L, colapsadas
a **18 filas** (`map_source = LINEA`).

Las filas `LINEA` son costos de venta de A&B, tickets de parque de Tours, seguros, cargos
financieros, depreciaciones, honorarios de administración y gastos no deducibles. 25 de las 40
están en Property Expenses.

### 5.1 Desambiguación por rango de cuenta

Nueve cuentas GL quedaban asignadas a dos líneas distintas porque el nombre se repite entre
secciones: `Commissions` existe como 6010 (planilla) y 7080 (gasto operativo) en cinco
departamentos, y `Other Cost of Services` como 5704 y 7410 en Information System.

| `be_section` | Rango de cuenta |
|---|---|
| PAYROLL | 6xxx |
| OPERATING EXPENSES | 7xxx, 4xxx |
| COST OF SALES | 5xxx, 8xxx |

Resultado: **cero colisiones**. El constraint `UNIQUE` de §2.2 se cumple sin excepciones.

### 5.2 Departamento y sección derivados por posición

`be_department` y `be_section` **no** se toman de la hoja `Clasificacion B`. Se derivan del
encabezado más cercano hacia arriba en el P&L. Esto corrigió dos errores del origen:

- **9 líneas de Gift Shop ($13,399) estaban etiquetadas como Tours** — en el P&L pertenecen al
  bloque Retail-Gift Shop (filas 649–707), que no tiene encabezado propio en esa posición. Con
  la corrección, Tours cierra en $293,080 y Gift Shop en $13,399, ambos exactos contra el P&L.
- **26 líneas quedaban sin sección** — 22 de Information System (el encabezado dice `PAYROLLl`,
  con la ele de más) y 4 de Property Expenses.

### 5.3 Validación contra el P&L (CWL, Budget 2025 Dec)

| Concepto | Modelo | P&L | Δ |
|---|---|---|---|
| Ingresos totales | 4,373,146 | 4,373,146 | 0 |
| Costo total clasificado | 4,198,042 | 3,485,529 + 712,513 | 0 |
| Resultado antes de impuestos | 250,148 | 250,148 | 0 |
| Resultado neto | 175,103 | 175,103 | 0 |
| Tours (costo departamental) | 293,080 | 293,080 | 0 |
| Gift Shop (costo departamental) | 13,399 | 13,399 | 0 |

---

## 6. Resultado con la semilla 100/0

| Métrica | Valor |
|---|---|
| Costos variables | $1,469,297 (35% del costo total) |
| Costos fijos (sin impuesto) | $2,653,701 |
| Margen de contribución | $2,903,849 — **66.4%** |
| Ingreso de equilibrio anual | **$3,996,427** (91.4% del presupuesto) |
| Margen de seguridad | $376,718 (8.6%) |
| Ocupación de equilibrio | **35.9%** vs 39.3% presupuestada |
| Apalancamiento operativo | 11.6x |

Es el resultado de la semilla, no un diagnóstico. Con toda la planilla en 100% variable el
margen queda alto y el equilibrio bajo. En CWL la planilla es mayoritariamente de planta, así
que al ajustar los porcentajes el equilibrio va a subir de forma material — y con 11.6x de
apalancamiento, 3 puntos de ocupación borran el resultado del año. Medir eso es el punto del
módulo.

---

## 7. Seguridad

- **Autorización en el servidor, no en la UI.** Deshabilitar inputs no protege nada: un PATCH
  directo pasa igual. Cada endpoint verifica rol de edición financiera.
- **Scoping por propiedad.** Todo endpoint valida que el usuario tiene acceso a `{id}`. Sin
  esto, cambiar el ID en la URL permite editar los porcentajes de otra propiedad.
- **El endpoint bulk acepta solo campos enumerados** (`department_slug`, `be_section`,
  `row_ids[]`). Nunca un filtro libre del cliente convertido en query.
- **Rate limit** en el PATCH de autosave.

---

## 8. Carga inicial

FinPlan es FastAPI + SQLAlchemy, no Django — no existe `manage.py`:

```
python -m finplan.cli load-break-even-seed --property CWL \
    --departments be_departments_seed.csv \
    --classification be_classification_seed.csv \
    --encoding utf-8
```

**Verificar antes de insertar**, como paso separado: que la propiedad existe por
`property_code`, que el periodo tiene datos cargados, y cuántas reglas ya hay. Reportar el
conteo y pedir confirmación antes de escribir.

`ON CONFLICT (property_id, dept_code, account, pl_line) DO NOTHING` para que una recarga nunca
pise porcentajes ya ajustados.

**Windows:** forzar `encoding='utf-8'` explícito. Los nombres traen `Á`, `—` y `&`; con el
cp1252 por defecto entran corruptos y el match por nombre falla en silencio.

### 8.1 Contenido del CSV de clasificación

`property_code · be_department_slug · be_department · be_section · dept_code · account ·
account_name · pl_line · section · original_class · pct_variable · map_source ·
excluded_from_be · source_rows`

**No lleva columna de monto.** En la v1 la traía y sumaba $5,987,085 contra $4,198,042 reales,
porque al expandir cada línea a sus cuentas GL hermanas el monto se repetía en cada fila. El
monto es dato de periodo y vive en el P&L de FinPlan; la clasificación es atemporal.

`source_rows` guarda la fila o filas del Excel original, para auditar de dónde salió cada regla.

---

## 9. Cambios respecto de la v1

| # | Cambio | Por qué |
|---|---|---|
| 1 | Gift Shop separado de Tours (9 líneas, $13,399) | Estaban mal etiquetadas en el origen; ninguno de los dos cerraba contra el P&L |
| 2 | Departamento y sección derivados por posición en el P&L | Resolvió 26 líneas sin sección y el error de Gift Shop |
| 3 | Desambiguación por rango de cuenta | 9 cuentas GL estaban asignadas a dos líneas a la vez |
| 4 | Filas `LINEA` colapsadas de 40 a 18 | La resolución por `pl_line` era ambigua con hasta 9 filas por clave |
| 5 | `excluded_from_be` como columna booleana | La exclusión dependía de comparar texto contra `'INCOME TAX'` |
| 6 | `be_department` como tabla catálogo | 8 departamentos pendientes exigían cambio de código |
| 7 | Columna de monto eliminada del CSV | Sumaba 43% de más por duplicación |
| 8 | Slugs en vez de nombres como llave | 8 nombres traían doble espacio (`'A&G  Department'`) |
| 9 | `data_version` obligatorio | No estaba definido de qué versión salía el P&L |
| 10 | Snapshot de periodo cerrado | Los porcentajes cambiaban reportes ya emitidos |
| 11 | `created_at`, CHECK, y `''` en vez de NULL en el constraint | Recargas duplicaban las filas `LINEA` |
| 12 | Comando de carga FastAPI, no Django | `manage.py` no existe en este stack |
| 13 | Autorización y scoping en el servidor | Los permisos estaban solo en la UI |
| 14 | Equilibrio mensual rotulado como prorrateo lineal | Con estacionalidad de 52% a 0.7%, el promedio no describe ningún mes |

---

## 10. Decisiones pendientes de tu confirmación

Implementadas con un valor provisional para no bloquear el arranque, y marcadas también en la
hoja `RESUMEN` del Excel:

1. **Versión de dato por defecto** — provisional: `BUDGET`. ¿Se compara contra `ACTUAL`?
2. **Equilibrio mensual** — provisional: lineal rotulado; estacional en Fase 2.
3. **Escenarios: ¿compartidos o personales?** — provisional: compartidos por propiedad, con
   autor. Es Fase 3 de todos modos.
4. **¿Se congela la clasificación al cerrar el mes?** — provisional: sí.
5. **Filas `LINEA`** — aplicado: colapsar a 18. Reversible si preferís crear las 40 cuentas en
   el master data.
