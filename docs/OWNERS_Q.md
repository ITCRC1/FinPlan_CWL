# Owners Q — reporte mensual a SCP (POR/PAR)

**Dónde vive:** `Reports` → `Owners Q` (`/reports/owners-q`).
**Qué se entrega:** `SCP_<entidad>_<MMMYY>_Statement_of_Income.xlsx`. El nombre
interno "Owners Q" **no viaja** al archivo: SCP lo recibe titulado
*Statement of Income*, como siempre.

Construido el 2026-08-17 contra la especificación `OWNERS_Q.md v2.2` del owner.

---

## Qué hace

Reproduce el *SCP Monthly P&L Report* alimentado 100% del Account Mapping y del
GL. Cero digitación manual, cero líneas huérfanas.

**No calcula nada nuevo.** Toma las `Línea P&L` que el P&L ya produce
(`compute_pl_month`) y las acomoda en las 48 filas que SCP espera. Si el P&L y
este reporte se separan algún día, no va a ser por acá.

| Pieza | Dónde |
|---|---|
| Motor puro (sin base) | `backend/app/engine/owners_q.py` |
| API | `backend/app/api/owners_q_api.py` |
| Excel | `backend/app/export/owners_q_excel.py` |
| Catálogo de filas y ruteo | `backend/app/seed_data/owners_q.json` |
| Seed + gate de cobertura | `backend/app/seed_owners_q.py` |
| Tablas | migración `123_owners_q.py` |
| Pantalla | `frontend/app/reports/owners-q/page.tsx` |
| Fixture de regresión | `backend/tests/fixtures/fixture_SCPCWL_JUN2026.csv` |

---

## Estado de validación (2026-08-17)

Contra el fixture dorado de junio 2026, con datos vivos de producción:

| Columna | Resultado |
|---|---|
| E · PTD Budget | **43/43 al centavo** |
| K · PTD Prior Year | **43/43 al centavo** |
| V · YTD Budget | **43/43 al centavo** |
| AB · YTD Prior Year | **43/43 al centavo** |
| A · PTD Actual | pendiente — **junio 2026 no está cargado** |
| R · YTD Actual | pendiente — le falta junio |

El `ACTUAL 2026` llega hasta **mayo**. Las dos columnas de Actual se validan
solas el día que se suba junio; el resto del reporte ya está probado.

**Gate D** (el archivo contra el original de SCP): 1.268 celdas con valor y 268
vacías, **0 diferencias**.

Las cuatro columnas se revalidaron **contra el despliegue**, no solo en local.

---

## Decisiones — D0 a D9, con su evidencia

| ID | Decisión | Cómo se resolvió |
|---|---|---|
| **D0** | Convención `favorable` por default | Del owner. Junio 2026 se congela en `raw` porque **ya se envió así**; `favorable` rige de julio en adelante |
| **D1** | ADR = `REV_ROOMS` ÷ noches, **sin** `REV_ROOMS_OTHER` | Del owner. Consecuencia deliberada: **RevPar ≠ ADR × Occ%** |
| **D2** | Private Bar → F&B (filas 17 y 24) | Default. Las cuatro columnas validables cuadran sin moverlo |
| **D3** | Área Recreativa y Claro Huerta → ingreso 18, gasto 29 | Default. Ídem |
| **D4** | Cafetería de personal → A&G (29) | Default. Ídem |
| **D5** | Lavandería interna → A&G (29) | Default. Ídem |
| **D6** | `LEASINGS_RENTS` → fila 43 RENT | Default. Ídem |
| **D7** | `FINANCIAL_LOSSES` → **fila 52 INTEREST**, no la 46 | **Ganó la ALTERNATIVA.** Ver abajo |
| **D8** | Income taxes fuera del reporte | Del owner. La última línea es NET INCOME BEFORE TAXES |
| **D9** | Cuenta `7120` separada en `OH_CC_COMMISSIONS` | Aplicado en el **seed**, con vigencia |

### D7 — la única que cambió de default

El spec mandaba `FINANCIAL_LOSSES` (diferencial cambiario) a la fila 46. Medido
contra la columna Prior Year del fixture, la **alternativa** es la única que
explica dos filas a la vez:

```
FL(jun-25) = −232,13  →  f46  4.709,41 − (−232,13)  =  4.941,54   ✔ fixture
                         f52  −(128,49 + (−232,13)) =    103,64   ✔ fixture
FL(ytd)    = +579,30  →  f46 15.899,77 − 579,30     = 15.320,47   ✔ fixture
                         f52  −(1.069,96 + 579,30)  = −1.649,26   ✔ fixture
```

Cuatro números al centavo, en dos períodos. El diferencial cambiario **puede ser
ganancia** —junio 2025 lo fue— y por eso la fila 52 es `signed` y la 56 la suma.

### El signo de la fila 52

El P&L guarda todo gasto en **positivo**; la fila 52 lo reporta en su **signo
natural**. La conversión es una negación, y se verificó contra el fixture: en
las dos columnas de Budget la diferencia era la negación exacta (−226,01 vs
+226,01 en el mes, −1.356,07 vs +1.356,07 en el acumulado).

---

## El período: mes, trimestre o Full Year

El selector es de **período**, no de mes: `M01`..`M12`, `Q1`..`Q4`, `FY`. El
bloque de la izquierda es el período y el acumulado va siempre de enero a su
cierre — para un mes son las dos cosas de siempre; para Q2 el bloque es abr-jun
y el acumulado ene-jun; para el año los dos son los doce meses. Cada posición
puede además correr sobre su propio período.

Verificado en producción: Q2 = 2.730 habitaciones (91 días × 30), FY = 10.950
(365 × 30), y M06 sigue cuadrando 43/43 contra el fixture.

**Solo un mes simple es el estándar de SCP.** Con un trimestre o el año:

- el rótulo pasa de `Month Ending` a `Period Ending` — con un trimestre adentro
  el otro sería mentira;
- el nombre del archivo lleva el período (`SCP_CWL_FY26_…`), porque dos archivos
  del mismo año llamados igual y diciendo cosas distintas son una trampa;
- **no se puede congelar.** Un snapshot es «lo que se le MANDÓ a SCP», y a SCP
  se le manda un mes con los tres bloques por defecto. El botón se apaga y el
  endpoint devuelve 400: el candado está en los dos lados, porque el de la
  pantalla no es un candado.

`DELETE /reports/owners-q/snapshots/{id}/` saca uno creado por error. La
inmutabilidad es correcta —es la prueba de qué se envió— pero no puede
significar que un error quede para siempre: uno equivocado miente sobre lo
enviado y el badge «recalculado» compararía contra algo que nunca salió.

---

## Las tres posiciones son elegibles

`budget` y `py` son COLUMNAS de SCP (E-J y K-P), no una obligación sobre qué
escenario vive ahí. Cada posición toma el escenario y el mes que se le indique:
comparar contra el Forecast Working, contra el Final, o junio contra mayo.

```
GET /reports/owners-q/?anio=2026&mes=6
      &escenario_budget=<id>&mes_py=5 …
GET /reports/owners-q/escenarios/     ← lo que se puede poner en cada posición
```

**El default no se mueve.** Sin elegir nada sale exactamente lo que SCP espera,
y hay prueba que lo fija: con la selección estándar el archivo queda idéntico al
del owner, fila 5 en blanco incluida.

**Y si se sale del estándar, el archivo lo dice.** La fila 5 —vacía en el
original— pasa a decir `⚠ Comparación NO estándar` con qué quedó en cada
columna. Quien reciba el Excel no puede deducirlo mirando los números.

El `Month Ending` de cada bloque sigue a SU escenario: un Forecast 2026 puesto
en la columna de año anterior imprime 2026. El año lo manda el escenario, no la
aritmética `anio − 1`. Lo mismo la capacidad: comparar junio contra mayo da 900
disponibles en un bloque y 930 en el otro.

---

## El formato: nueve diferencias contra el archivo del owner

El 2026-08-18 el owner mandó su `.xlsx` real. Los números ya cuadraban; el
formato no se parecía. Corregidas todas, contra su propio archivo:

| # | Faltaba / estaba mal |
|---|---|
| 1 | El bloque `SCP CWL` / `Statement of Income` / `As of Date:` / `Location:` |
| 2 | Filas 6-7: `Month Ending` / `Year To Date` / `Prior Year To Date` con la fecha de cada bloque (2025 en los de año anterior) |
| 3 | Rótulos de la fila 8 abreviados («Budget Diff» vs «PTD Budget Diff») |
| 4 | Los montos sin signo de dólar |
| 5 | Noches con decimales y ocupación sin formato de porcentaje |
| 6 | Resaltes: son `DDEBF7` en 6 subtotales y `BDD7EE` en 5 líneas de utilidad |
| 7 | Bordes: fino arriba de cada corte, doble bajo ADJUSTED EBITDA y NET INCOME |
| 8 | Fuente Helvetica 12, toda la grilla en negrita |
| 9 | Anchos por columna, altos de fila, congelado en B9, sangría de **dos** espacios por nivel |

La hoja se llama `SCPCWL`, como la suya.

**El estilo es dato, no código** (`report_lines.estilo`, migración 124). No se
deriva de nada: la fila 49 lleva línea arriba sin ser subtotal, la 52 la lleva
doble, y `TOTAL DEPARTMENTAL PROFIT` se pinta como subtotal mientras `GROSS
OPERATING PROFIT` —el mismo tipo— se pinta como total.

El archivo del owner vive en `tests/fixtures/SCP_CWL_JUN2026_original.xlsx` y
`test_owners_q_formato.py` lo compara celda por celda. Verificado contra
producción: **0 diferencias de formato**.

---

## Dos bugs que solo aparecieron al desplegar

**El `mapping_version` no llegaba al P&L.** Se aceptaba y se devolvía en la
respuesta, pero solo el panel de excepciones miraba la vigencia: el P&L de abajo
computaba con el mapeo de hoy. Pidiendo junio con el mapeo de junio, el reporte
igual separaba las comisiones de tarjeta. Era exactamente la historia reescrita
que la vigencia existía para evitar. `compute_pl_month(..., periodo=)` ahora lo
enhebra hasta las cuatro cargas del núcleo, y el período entra en las dos llaves
de caché.

**La vista de año reventaba con 500.** `construir_anio` usaba `periodo` sin
tenerlo. Al arreglarlo salieron dos cosas de fondo: cada mes va con el mapeo de
SU mes (2026 cruza el cambio de D9 en julio), y las habitaciones disponibles son
**por bloque**, no una para PTD y otra para YTD — el bloque de año anterior corre
sobre su propio calendario, y con 2025 vs 2024 (bisiesto) la diferencia muerde.

`test_nombres_definidos`, que existe justo para atrapar el `NameError`, tenía un
hueco: `ast.walk` visitaba los hijos de las funciones anidadas, así que cada
parámetro del archivo contaba como nombre de módulo. Corregido, con su propia
prueba de regresión.

---

## Hallazgos

**H1 — error de aritmética en el §9.3 del spec.** El documento dice que la
brecha YTD de D1 es `17.892,89`. Da **`17.872,89`**: `619,33 × 2.854 =
1.767.567,82`, no `1.767.547,82`. Son $20,00 exactos de resta mal hecha en la
prosa. El fixture está bien y es coherente; el PTD (1.772,55) calza al centavo.
El test se ancla al **fixture**, no a la prosa — que es justo lo que el §9.3
manda hacer.

**H2 — `8030 BANK AND COMMISSIONS CHARGES` (depto 250) está en
`LEASINGS_RENTS`.** Cargos bancarios en una línea de alquileres parece error del
mapping. **No se corrigió**: es una decisión de negocio del owner. Candidatos:
fila 46 o fila 52.

**H3 — `7020 Bank Charges` y `7115 Credit and Collection`** siguen en
`OH_ADMIN`. El spec pedía confirmar con el owner si SCP las espera también en la
fila 30. **Pendiente de respuesta.**

---

## Cosas que parecen errores y NO lo son

- **RevPar ≠ ADR × Occ%.** El ADR excluye `REV_ROOMS_OTHER` (D1) y el RevPar no.
  La brecha es exactamente el otro ingreso de habitaciones. Es fiel al archivo
  que SCP recibe. **No se "arregla".**
- **Filas que siempre dan 0 y se imprimen igual** (20 Fair Trade, 31 Every Stay
  Does Good, 41 Non-Op Income, 44 Property Taxes, 50 Asset/Project Mgmt Fees).
  SCP consolida por **posición de fila**: omitirlas le rompe la consolidación.
- **30 habitaciones, no 33.** El KPI interno del P&L usa 33; SCP usa 30. En junio
  son 900 disponibles y no 990. Por eso `capacidad` es tabla y no constante.

---

## Versionado del mapeo — por qué existe

D9 mueve la cuenta 7120 de `OH_ADMIN` a `OH_CC_COMMISSIONS`. Sin vigencia, ese
cambio **reescribe la historia**: un período ya enviado a SCP devolvería números
distintos al reejecutarse, y **seguiría cuadrando**, porque la plata solo se
mueve entre dos filas del mismo subtotal. Un cambio que no se nota es el peor.

`account_mapping.vigente_desde` / `vigente_hasta` (`YYYY-MM`, NULL = sin tope):

```
7120 / 0180 → OH_ADMIN            hasta 2026-06
7120 / 0180 → OH_CC_COMMISSIONS   desde 2026-07
```

`OH_ADMIN` queda con **87 reglas activas desde julio** (era 88) — el número que
pedía el §7.

⚠️ **El cambio se hizo en el SEED (`mapping_pl.json`), no por SQL.** En este
proyecto el seed manda: una migración que toque `account_mapping` sin cambiar el
JSON se revierte sola en el próximo despliegue.

⚠️ La unicidad de (depto, cuenta) es **por par y por momento**. Dos reglas que
nunca rigen el mismo mes no son ambiguas; dos que se pisan sí, y ahí la línea la
decide el orden físico de las filas. Los tests
`test_mapeo_coherente` y `test_seed_manda_sobre_mapeo` lo verifican.

---

## Extensibilidad

El motor no tiene nada de CWL adentro. Para Oxígen, Ojochal o Amarena alcanza
con:

1. su Account Mapping (las `Línea P&L` son el estándar USALI, iguales),
2. filas en `capacidad` para esa entidad.

`report_lines`, `report_line_mapping` y `report_snapshots` llevan `report_key`,
así que el **próximo reporte** del tab `Reports` se agrega sembrando filas, sin
tocar el motor ni migrar tablas.

---

## Pendientes

- [ ] Cargar el **actual de junio 2026** y revalidar las columnas A y R.
- [ ] Confirmar con el owner que la pantalla se ve bien (no la pude mirar: el
      login pide contraseña).
- [ ] Owner: ¿la `8030` va a la 46 o a la 52? (H2)
- [ ] Owner: ¿la `7020` y la `7115` van también a la fila 30? (H3)
- [ ] Registrar el snapshot de junio 2026 en `raw` una vez cargado el actual.
