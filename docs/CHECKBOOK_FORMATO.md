# CHECKBOOK — Formato estándar de gastos por departamento (v2)

**Proyecto:** FinPlan · The Costa Rica Collection
**Origen:** derivado de `CHECKBOOK_MADRESAL__2026.xlsx`
**Objetivo:** un formato parametrizable para capturar gastos de cualquier departamento y devolver los datos a FinPlan sin re-digitar. Solo cambia el departamento, el año y la lista de cuentas; la geometría se adapta sola.

**Scripts:** `build_checkbook.py` (genera) · `read_checkbook.py` (lee de vuelta)

---

## 1. Estructura

| Tab | Nombre |
|---|---|
| 1 | `BUDGET {AÑO} Detail` |
| 2 | `SUMMARY` |

---

## 2. Tab `BUDGET {AÑO} Detail`

### 2.1 Columnas

| Col | Contenido | Editable |
|---|---|---|
| A | vacía (margen) | — |
| B | `# Cuenta` (llave del SUMIF) | no |
| C | `Descripcion de Cuenta` | no |
| D | `Departamento` (código) | no |
| E | `Detalle` — 800 … 810 | no |
| F | `Detalle Descripcion` | **sí** |
| G–R | Ene … Dic del año de versión | **sí** |
| S | `TOTAL` = `=SUM(G:R)` | no (fórmula) |

### 2.2 Encabezado (filas 1–13)

| Fila | Contenido |
|---|---|
| 1–2 | Leyenda |
| 3 | `C3` = nombre del departamento (Arial 14 bold) |
| 4 | `C4 = "ESTADISTICAS"`; `G4:R4` meses `mmm-yy`; `S4 = "TOTAL"` |
| 5 | **Noches Disponibles** — captura / precarga |
| 6 | **Noches Ocupadas** — captura / precarga |
| 7 | **% Ocupación** = `=IFERROR(G6/G5,0)`, formato `0.0%` |
| 9 | `GRAN TOTAL {AÑO}` — fórmula, suma de todas las filas `TOTAL {AÑO}` |
| 10 | `GRAN TOTAL {AÑO-1}` — fórmula, suma de las referencias |
| 11 | `GRAN TOTAL {AÑO-2}` |
| 12 | `GRAN TOTAL {AÑO-3}` |
| 13 | `C13` = año de versión |

> No hay fila REVENUE: los departamentos de este checkbook son de gasto puro.

### 2.3 Bloque por cuenta (desde la fila 15)

Cada cuenta ocupa **18 filas** (con 11 detalles), igual que el archivo original:

```
hdr          encabezado (meses G:R + TOTAL en S)
hdr+1 … +11  11 líneas de detalle (E = 800 … 810)
hdr+12       TOTAL {AÑO}      fórmula = SUM de las 11 líneas
hdr+13       TOTAL {AÑO-1}    referencia — precarga FinPlan
hdr+14       TOTAL {AÑO-2}    referencia — precarga FinPlan
hdr+15       TOTAL {AÑO-3}    referencia — precarga FinPlan
hdr+16, +17  blanco
```

```
paso           = detalles_por_cuenta + 2 + 3 + 2      # = 18 con 11 detalles
fila_header(i) = 15 + i * paso                        # headers 15, 33, 51, 69 …
fila_total(i)  = fila_header(i) + detalles_por_cuenta + 1   # 27, 45, 63 …
```

**Regla crítica:** las filas TOTAL y las de referencia llevan la **columna B vacía**. Eso es lo que evita que el `SUMIF` del SUMMARY doble los montos. No escribir el número de cuenta ahí.

Las etiquetas B:F solo aparecen en el primer encabezado (fila 15), como en el original.

### 2.4 Formatos

| Elemento | Valor |
|---|---|
| Fuente | Arial 10 · Arial 14 bold para el departamento |
| Montos | `_("$"* #,##0.00_);_("$"* \(#,##0.00\);_("$"* "-"??_);_(@_)` |
| Meses | `mmm-yy` (fecha real, día 1) |
| Noches | `#,##0` · Ocupación `0.0%` |
| Rellenos | encabezado `FCE4D6` · meses `FAE2D5` · gran total `BDD7EE` · TOTAL cuenta `F2F2F2` · referencias `FAFAFA` · estadísticas `E2EFDA` |
| Captura | fuente azul `0000FF` · referencias azul cursiva |
| Anchos | B 9 · C 27.57 · D 14 · E 7.43 · F 64.29 · G:R 13 · S 16.71 |
| Vista | panel congelado `G8` · gridlines ocultas |

### 2.5 Protección

`proteger: true` bloquea la hoja (password por defecto `FINPLAN`, configurable). Quedan desbloqueadas solo:

- `F` y `G:R` de cada línea de detalle
- `G5:R6` (noches disponibles / ocupadas)
- `G:R` de las filas de referencia

Todo lo demás —columna S, filas TOTAL, gran totales, encabezados— queda bloqueado. Esto es lo que permite repartir el archivo a varias personas sin que una fórmula se destruya al pegar.

---

## 3. Tab `SUMMARY`

Una fila por cuenta, sin detalles.

| Zona | Contenido |
|---|---|
| `G3:S3` | `BUDGET {AÑO}` (Arial 18 bold, merge) |
| Fila 5 | meses + TOTAL |
| `D6` | nombre del departamento |
| Fila 9 | encabezados: `# Cuenta`, `Descripcion de Cuenta`, meses, `TOTAL {AÑO-1..-3}`, `Var %` |
| Filas 10 … | `G:R` = SUMIF · `S` = SUM · `U,V,W` = referencias · `X` = variación |
| Última + 2 | fila TOTAL |

```excel
G10 =SUMIF('BUDGET 2027 Detail'!$B:$B,$D10,'BUDGET 2027 Detail'!G:G)
U10 ='BUDGET 2027 Detail'!S28        ← TOTAL 2026 del bloque de esa cuenta
X10 =IFERROR(S10/U10-1,0)            ← variación vs año anterior
```

---

## 4. Configuración

```json
{
  "departamento": "Gastos Operativos Club Madresal",
  "codigo_departamento": 600,
  "anio_version": 2027,
  "detalles_por_cuenta": 11,
  "detalle_inicial": 800,
  "incluir_leyenda": true,
  "proteger": true,
  "password_proteccion": "FINPLAN",
  "estadisticas": {
    "noches_disponibles": [310, 280, 310, 300, 310, 300, 310, 310, 300, 310, 300, 310],
    "noches_ocupadas":    [155, 186, 217, 124,  93, 124, 155, 186, 124,  93, 155, 217]
  },
  "referencias": {
    "2026": { "7030": [100,100,100,100,100,100,100,100,100,100,100,100] },
    "2025": { "7030": [90,90,90,90,90,90,90,90,90,90,90,90] },
    "2024": { "7030": [80,80,80,80,80,80,80,80,80,80,80,80] }
  },
  "cuentas": [
    { "cuenta": 7030, "descripcion": "Building" }
  ]
}
```

| Campo | Oblig. | Default | Nota |
|---|---|---|---|
| `departamento`, `codigo_departamento`, `anio_version`, `cuentas` | sí | — | — |
| `detalles_por_cuenta` | no | 11 | recalcula el paso del bloque |
| `detalle_inicial` | no | 800 | 800→810 son 11 líneas |
| `estadisticas` | no | vacío | series de 12; si falta, quedan en blanco para captura |
| `referencias` | no | vacío | `{año: {cuenta: [12 montos]}}` desde FinPlan; cuenta sin dato queda en blanco |
| `proteger` / `password_proteccion` | no | true / FINPLAN | — |

**Validaciones que fallan temprano:** config incompleto · cuentas duplicadas (romperían el SUMIF) · cuentas sin descripción · series que no traigan exactamente 12 valores · archivo de salida ya existente (usar `--force`).

---

## 5. Ejecución

```bash
# Generar
python build_checkbook.py config_depto.json CHECKBOOK_MADRESAL_2027.xlsx

# Leer de vuelta el archivo lleno
python read_checkbook.py CHECKBOOK_MADRESAL_2027.xlsx --out-dir ./salida
```

El lector produce tres archivos:

| Archivo | Granularidad | Uso |
|---|---|---|
| `*_detalle.csv` | cuenta × detalle × mes | cuando FinPlan tenga la dimensión `detalle` |
| `*_por_cuenta.csv` | cuenta × mes | **carga directa a FinPlan hoy** |
| `*.json` | todo + estadísticas + referencias | integración programática |

Y valida el cuadre: `GRAN TOTAL calculado` (sumando líneas) vs `GRAN TOTAL en la hoja` (fila 9). Si dice `NO`, alguien tocó una fórmula.

---

## 6. Integración con FinPlan

**Precarga (FinPlan → Excel).** Para el año V, consultar por cada cuenta del departamento los montos mensuales de V−1, V−2 y V−3, y armar el bloque `referencias` del config. Cuenta que no exista en un año se deja en blanco.

**Retorno (Excel → FinPlan).** Cargar `*_por_cuenta.csv` en el presupuesto. El detalle 800–810 **no existe hoy en FinPlan**: los códigos se imprimen igual para dar espacio de captura, y el `*_detalle.csv` queda listo para el día en que se agregue esa dimensión. Recomendación para cuando llegue ese momento: una tabla `budget_detail (cuenta, departamento, detalle, anio, mes, monto, descripcion)` con llave única `(cuenta, departamento, detalle, anio, mes)` — así el mismo CSV entra sin transformación.

**Catálogo de cuentas.** Poblar `cuentas` desde el Account Mapping filtrando por departamento, en vez de mantenerlo a mano en cada JSON.

---

## 7. Desviaciones deliberadas vs. `CHECKBOOK_MADRESAL__2026.xlsx`

| Elemento | Original 2026 | Formato v2 |
|---|---|---|
| Fila REVENUE (4) | link externo a `[7]Budget 2025W` | eliminada (no hay revenue) |
| Encabezado | departamento en `C5` | estadísticas en 4–7, departamento en `C3` |
| Años de referencia | ninguno | 3 por cuenta (`hdr+13..+15`) + gran totales 10–12 |
| Filas en blanco por bloque | 5 | 2 (las otras 3 ahora son referencias) |
| Paso del bloque | 18 filas | **18 filas — sin cambio** |
| Headers / TOTAL | 15, 33, 51 / 27, 45, 63 | **idénticos** |
| Panel congelado | `I6` | `G8` |
| Anchos G, H, I | 17.4 / 16.6 / 11.7 | 13 uniforme |
| Gridlines | visibles | ocultas |
| Fila TOTAL de cuenta | sin relleno | gris `F2F2F2` |
| Celdas de captura | negro | azul |
| Protección de hoja | ninguna | activa |
| SUMMARY | solo año de versión | + 3 años de referencia + Var % |

---

## 8. Verificación (validado)

- 1,184 fórmulas, 0 errores de recálculo con 25 cuentas.
- `Detail!S9` = `SUMMARY` fila TOTAL col S (año de versión).
- `Detail!S10` = `SUMMARY` fila TOTAL col U (año−1).
- Cada `TOTAL {AÑO}` = suma de sus 11 líneas.
- Ida y vuelta: generar → capturar → leer devuelve el mismo gran total.

---

## 9. Integración en el módulo Planning de FinPlan

El checkbook cuelga **al final de Planning**, como último bloque del módulo, y se baja a Excel desde ahí.

**Archivo:** `checkbook_router.py` (FastAPI)

| Endpoint | Qué hace |
|---|---|
| `GET /api/planning/checkbook/{depto_id}/{anio}/preview` | Muestra antes de descargar: cuántas cuentas, cuántas referencias trae cada año, si hay estadísticas cargadas |
| `GET /api/planning/checkbook/{depto_id}/{anio}/export` | Arma el config desde FinPlan, genera el `.xlsx` y lo devuelve como descarga |
| `POST /api/planning/checkbook/{depto_id}/{anio}/import` | Sube el archivo lleno; sin `confirmar=true` solo devuelve el resumen para revisar |

**De dónde salen los datos** (clase `Repo`, tres consultas aisladas para ajustar al esquema real):

| Config | Fuente en FinPlan |
|---|---|
| `cuentas` | `account_mapping` filtrado por departamento y activo |
| `referencias` | `gl_actual` (o la vista de P&L) para los 3 años anteriores, misma cuenta |
| `estadisticas` | `estadisticas_ocupacion` del año de versión |

**UI sugerida al final de Planning**

```
┌─ Checkbook de gastos ──────────────────────────────────┐
│  Departamento: [ Gastos Operativos Club Madresal  ▾ ]  │
│  Año:          [ 2027 ▾ ]                              │
│                                                        │
│  25 cuentas · referencias 2026 (25) 2025 (24) 2024 (22)│
│  Estadísticas de ocupación: cargadas                   │
│                                                        │
│  [ Descargar Excel ]      [ Subir archivo lleno ]      │
└────────────────────────────────────────────────────────┘
```

**Reglas de importación**

- Si el año del archivo no coincide con el de la ruta → 422.
- Si el archivo no cuadra (gran total de la hoja ≠ suma de líneas) → 422; significa que alguien tocó una fórmula.
- La carga reemplaza solo las líneas con `origen = 'CHECKBOOK'` de ese departamento y año; no toca lo que se cargó por otras vías.
- El detalle 800–810 se guarda cuando FinPlan tenga la dimensión: tabla `budget_detalle(departamento_id, anio, mes, cuenta, detalle, monto, descripcion)` con única `(departamento_id, anio, mes, cuenta, detalle)`.

---

## 10. Diseño visual

| Elemento | Tratamiento |
|---|---|
| Banda de título | fila 1 (Detail) y fila 2 (SUMMARY), navy `1F3864`, texto blanco Arial 12 bold, ancho completo |
| Encabezados de mes | banda navy continua de B a S, texto blanco bold, alto 18 |
| Etiquetas de columna | blancas sobre navy, solo en el primer bloque |
| Estadísticas | verde `E2EFDA` |
| TOTAL de cuenta | gris `F2F2F2` con **borde superior grueso** navy |
| GRAN TOTAL | azul `BDD7EE` con borde superior grueso |
| Referencias | gris muy claro `FAFAFA`, texto azul cursiva |
| SUMMARY | filas alternas `F7F9FC`, panel congelado en `G10` |
| Bordes | hairline `D9D9D9` en toda el área de datos |
| Gridlines | ocultas en ambos tabs |

**Totales presentes en el libro:**

- **Por fila:** columna S de cada línea de detalle (`=SUM(G:R)`).
- **Por cuenta:** fila `TOTAL {AÑO}` de cada bloque.
- **Por columna/mes:** fila 9 del Detail (`GRAN TOTAL {AÑO}`, mes a mes) y fila `TOTAL DEPARTAMENTO` del SUMMARY.
- **Por año de referencia:** filas 10–12 del Detail y columnas U/V/W del SUMMARY.
- **Cantidad de cuentas:** `SUMMARY!E4` = `=COUNT(...)`, junto al gran total en `H4`.
- **Cuadre automático:** `SUMMARY` fila de chequeo = `TOTAL DEPARTAMENTO − Detail!S9`, debe dar `0.00`.
