# ESCANEO 04 — FORMATO VISUAL

**Archivo:** `C:\FinPlan_CWL\docs\fase2\PL_DETALLADO_FORMATO.xlsx`
**Hoja:** `P&L Full Detail` (única) · rango real `A1:HB1046` · contenido útil `B1:Q1008`
**Fecha del escaneo:** 2026-08-11 · herramienta: openpyxl 3.1.5

---

## 1. RESUMEN EJECUTIVO

El archivo declara **234 `cellXfs`** (combinaciones de estilo a nivel Excel), pero eso es ruido:
el reporte se compone en realidad de **13 estilos visuales distintos** más 3 variantes menores.
Todo lo demás son repeticiones de esos 13 aplicadas a 1,007 filas.

| Dimensión | Cuántos valores distintos hay realmente |
|---|---|
| Rellenos (fills) | **15** hex distintos → **9 con significado semántico** |
| Tipografías (fuente+tamaño+peso+color) | **16** combinaciones → **8 con significado** |
| Formatos numéricos | **11** → **5 familias** (moneda, moneda contable, entero contable, %, fecha) |
| Bordes | **32** combinaciones → **5 reglas** (thin / medium / double / thick / marco) |
| Indentación (`alignment.indent`) | **0** — la jerarquía NO se expresa con sangría |
| Formato condicional | **0 reglas** — no hay |
| Imágenes / gráficos / logos | **0** |
| Celdas combinadas | **1** (`C2:Q2`, el título) |
| Comentarios (notas) | **7** en C567, C568, C570, C581, C584, C585, C586 |

**Hallazgo clave:** la jerarquía se comunica **solo por color de relleno + peso de fuente + bordes**.
No hay sangrías, no hay espacios al inicio de las etiquetas (verificado: 861 etiquetas, todas con
0 espacios iniciales), no hay agrupación/outline. Si se replica en web, el nivel jerárquico se
deduce del **estilo de la fila**, no de un `padding-left`.

**Segundo hallazgo:** los números están **CENTRADOS**, no alineados a la derecha
(columnas D–O y Q: `horizontal='center'` en 923–981 celdas cada una). La columna de etiqueta C
usa alineación por defecto (izquierda). Es una decisión deliberada del autor y hay que respetarla
si el requisito es "en esta misma forma".

---

## 2. PALETA — todos los colores de relleno y qué significan

Los colores de tema se resolvieron contra `theme1.xml` (esquema **Office 2013-2022**):
`lt1=FFFFFF · dk1=000000 · lt2=E7E6E6 · dk2=44546A · accent1=4472C4 · accent2=ED7D31 · accent3=A5A5A5 · accent6=70AD47`.

| # | Hex | Muestra | Celdas | Dónde aparece | Significado |
|---|-----|---------|--------|---------------|-------------|
| 1 | `#FFFFFF` | blanco | 9,348 (+2,875 como tema0) | filas de detalle en todo el reporte | **Línea de detalle** — cuenta individual, dato base |
| 2 | `#BDD7EE` | azul claro | 798 | 50 filas: 165, 186, 227, 259, 275, 293, 333, 346, 350, 368, 398, 408, 412, 431, 442, 452, 460, 478, 489, 499, 504, 522, 533, 542, 546, 564, 593, 602, 605, 623, 644, 660, 683, 720, 740, 772, 792, 826, 846, 853, 885, 899, 905, 909, 927, 938, 940, 951, 956, 965, 970, 975, 980, 985, 997, 1003, 1007 | **SUBTOTAL de grupo** (`TOTAL NÓMINA`, `Total Ingresos …`, `TOTAL GASTOS OPERATIVOS`) |
| 3 | `#D9E1F2` | azul muy claro | 795 | 57 filas: 158, 168, 192, 234, 260, 276, 295, 339, 347, 351, 370, 403, 409, 413, 433, 447, 453, 461, 480, 494, 500, 505, 524, 538, 543, 547, 566, 598, 603, 606, 625, 649, 666, 684, 723, 741, 775, 793, 829, 847, 854, 888, 901, 906, 910, 929, 946, 948, 953, 958, 967, 972, 977, 982, 987, 999, 1005 | **Encabezado de categoría** dentro de un departamento (`INGRESOS`, `COSTO DE VENTAS`, `NÓMINA`, `Gastos Operativos`) |
| 4 | `#F2F2F2` | gris claro | 378 | 27 filas: 187, 231, 294, 334, 336, 369, 399, 401, 432, 443, 445, 479, 490, 492, 523, 534, 536, 565, 594, 596, 624, 645, 647, 662, 928, 941, 943 | **Fila de ratio / porcentaje** (`% de Ingresos del Depto.`, `% Utilidad`) |
| 5 | `#CCCCFF` | periwinkle (indexed 31) | 261 + 10 | filas 19, 20, 22, 36, 38, 50, 53, 65, 68, 78, 80, 85, 89, 93, 98, 100, 107, 109, 114, 119, 122, 127, 132, 140 (cols C–O y Q) | **Resumen ejecutivo**: encabezado de bloque y TOTAL del P&L consolidado (parte superior del reporte) |
| 6 | `#262626` | casi negro | 209 | filas 230, 335, 400, 444, 491, 535, 595, 646, 661, 664, 721, 773, 827, 886, 942 | **UTILIDAD NETA del departamento** / total de bloque overhead |
| 7 | `#404040` | carbón | 67 | filas 154, 233, 338, 402, 446, 493, 537, 597, 648, 665, 722, 774, 828, 887, 900 | **BANNER DE DEPARTAMENTO** (`DEPARTAMENTO DE HABITACIONES`, …) |
| 8 | `#D0CECE` | gris cálido (`lt2` −10%) | 195 | filas 3–9 y 11–16, cols C–Q | **Bloque KPI / estadísticas** (habitaciones, ocupación, ADR, membresías) |
| 9 | `#EBEBEB` | gris muy claro | 85 | filas 155, 188, 189, 229, 232, 337, 663 | **Fila separadora fina** (alto 3.95 pt) entre secciones |
| 10 | `#EDEDED` | gris claro (`accent3` +80%) | 24 + 2 | fila 18 (D–O) y Q18/Q19 | **Cabecera de meses** |
| 11 | `#DAE3F3` | azul pálido (`accent1` +80%) | 21 | filas 28, 60, 116 (cols B–T) | **Marca de revisión / dato importado** — `Club Madresal` (ingresos y utilidad operativa) y `Depreciación` |
| 12 | `#FFFAE6` | crema | 1 | D1 | Marca residual de "input manual" (una sola celda, sin uso real) |

Colores de **texto** (no de relleno) que también forman parte de la paleta:

| Hex | Uso |
|---|---|
| `#000000` | texto de detalle y de totales del resumen ejecutivo |
| `#1F3864` | azul marino — **todo el texto sobre `#BDD7EE` y `#D9E1F2`** |
| `#FFFFFF` | texto sobre `#262626` y sobre `#404040` (columnas de datos) |
| `#595959` | gris — texto **itálico** de las filas de ratio (`#F2F2F2`) |
| `#FF0000` | rojo — título de la hoja (fila 2) **y la etiqueta C del banner de departamento** |
| `#C65911` | naranja quemado (`accent2` −25%) — nombres de mes en la fila 18 y Q18 |

Color de pestaña de la hoja: `#548235` (verde, `accent6` −25%).

---

## 3. TABLA MAESTRA: estilo → qué representa → qué filas

Los 13 estilos del sistema. `T:` = borde superior, `B:` = borde inferior.

| # | Nombre | Relleno | Fuente | Bordes | Alto | Formato nº | Qué representa | Filas |
|---|--------|---------|--------|--------|------|-----------|----------------|-------|
| **S1** | `titulo-hoja` | ninguno | Arial **26 bold** `#FF0000` centrado | — | 48.75 pt | General | Título del reporte, combinado `C2:Q2` | 2 |
| **S2** | `kpi-block` | `#D0CECE` | Arial 12 **bold** negro | marco: `medium` arriba (f.3), `medium` abajo (f.9), `medium` izq. en C y der. en O/Q | 20.1 pt | contable entero `_-* #,##0_-;…` (f.7 = `0.00%`, f.8 = contable `#,##0.00`) | Estadísticas de operación: habitaciones disponibles/ocupadas/día, huéspedes, % ocupación, ADR | 3–9 |
| **S2b** | `kpi-membresias` | `#D0CECE` | etiqueta **Segoe UI 14 bold**; datos Arial 12 | — | 20.25 pt | contable entero | Bloque de membresías del Club | 11–16 |
| **S3** | `cabecera-meses` | `#EDEDED` | Arial 12 **bold** `#C65911` centrado | `medium` arriba; f.19 `medium` arriba+abajo | 16.5 pt | (`mmm-yy`, residual — los valores son texto) | Enero…Diciembre + `Total Año` (Q); debajo fila 19 `DESCRIPCIÓN DE CUENTA` / `Presupuesto 2026` en negro, y fila 20 = franja de cierre `#CCCCFF` con `medium` abajo | 18, 19, 20 |
| **S4** | `resumen-seccion` | `#CCCCFF` | Arial 12 **bold** negro | `thin` arriba+abajo | 15.75 pt | moneda-paréntesis | Apertura de bloque del P&L consolidado: `INGRESOS`, `Gastos Operativos`, `Utilidad Operativa`, `GASTOS GENERALES (OVERHEAD)` | 22, 38, 53, 68 |
| **S5** | `resumen-total` | `#CCCCFF` | Arial 12 **bold** negro | `medium` arriba+abajo + `thin` izq/der (caja) | 16.5 pt | **`"$"#,##0.00;[Red]"$"#,##0.00`** (sin paréntesis) | Totales duros del P&L consolidado | 36, 50, 65, 78, 80, 85, 89, 93, 98, 100, 107, 109, 114, 119, 122, 127, 132, 140 |
| **S6** | `detalle` | `#FFFFFF` | Arial 12 regular `#000000` | ninguno | 15.75 pt | moneda-paréntesis, blanco si 0 | Línea de cuenta individual. Es el 63 % de las filas | 638 filas (todo el cuerpo) |
| **S7** | `banner-departamento` | `#404040` | Arial 12 **bold**; etiqueta C en `#FF0000`, datos D–Q en `#FFFFFF` | `medium` arriba+abajo; `medium` izq/der en C y Q | 16.5 pt | moneda-paréntesis | Apertura de cada uno de los 15 departamentos | 154, 233, 338, 402, 446, 493, 537, 597, 648, 665, 722, 774, 828, 887, 900 |
| **S8** | `categoria` | `#D9E1F2` | Arial 12 **bold** `#1F3864` | `thin` abajo; la **primera categoría** de cada departamento además lleva `medium` arriba | 15.75 pt | moneda-paréntesis | `INGRESOS` · `COSTO DE VENTAS` · `NÓMINA` · `Gastos Operativos` · `ALQUILER` · `DEPRECIACIÓN` … | 57 filas (ver §2 fila 3) |
| **S9** | `subtotal` | `#BDD7EE` | Arial 12 **bold** `#1F3864` | **`double` arriba** (+ `double` abajo cuando cierra el grupo) | 17.25 pt | **contable** `"$"#,##0.00_);[Red]\("$"#,##0.00\)` | Subtotales: `Total Ingresos …`, `TOTAL NÓMINA`, `TOTAL GASTOS OPERATIVOS` | 50 filas (ver §2 fila 2) |
| **S10** | `ratio` | `#F2F2F2` | Arial 12 ***itálica*** `#595959` | `double` arriba + `medium` abajo (variante fuerte: `thick` arriba + `medium` abajo) | 16.5 pt | ⚠️ moneda (defecto heredado — debería ser `0.00%`) | `% de Ingresos del Depto.`, `% Utilidad` | 187, 231, 294, 334, 336, 369, 399, 401, 432, 443, 445, 479, 490, 492, 523, 534, 536, 565, 594, 596, 624, 645, 647, 662, 928, 941, 943 |
| **S11** | `utilidad-neta-depto` | `#262626` | Arial 12 **bold** `#FFFFFF` | `thick` arriba (variante overhead: `double` arriba + `thick` abajo) | 17.25 pt | moneda-paréntesis | `UTILIDAD NETA <DEPTO>`; también `TOTAL ADMINISTRACIÓN Y GENERAL`, `TOTAL VENTAS Y MERCADEO`, `TOTAL MANTENIMIENTO`, `TOTAL SISTEMAS DE INFORMACIÓN` | 230, 335, 400, 444, 491, 535, 595, 646, 661, 664, 721, 773, 827, 886, 942 |
| **S12** | `separador` | `#EBEBEB` | — | — | **3.95 pt** (3.75 en f.337) | Franja fina de aire entre secciones. Detalle sutil pero muy visible | 155, 188, 189, 229, 232, 337, 663 |
| **S13** | `resaltado-revision` | `#DAE3F3` | Arial 12 regular | ninguno | 15.75 pt | moneda-paréntesis | Marca de "ojo con este dato": `Club Madresal` (f.28 y 60) y `Depreciación` (f.116) | 28, 60, 116 |

---

## 4. FORMATOS NUMÉRICOS Y CONVENCIÓN DE NEGATIVOS

Los 11 `number_format` del archivo, agrupados en 5 familias:

| Familia | Código exacto | Celdas | Dónde | Negativos |
|---|---|---|---|---|
| **Moneda con paréntesis** (el estándar del reporte) | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 9,454 | todas las líneas de detalle, categorías, banners, ratios | **`($1,234.56)` en ROJO**; el cero se muestra **vacío** (tercera sección `""`) |
| **Moneda contable** (subtotales) | `"$"#,##0.00_);[Red]\("$"#,##0.00\)` | 521 | filas S9 (`#BDD7EE`) | `($1,234.56)` en rojo; positivos con espacio reservado para el paréntesis (alineación óptica) |
| **Moneda contable con locale** | `[$$-409]#,##0.00_);[Red]\([$$-409]#,##0.00\)` | 121 | cola bajo GOP: filas 944–1008 (alquiler, honorarios, seguro, intereses, depreciación, renta) | igual, pero con marcador de locale en-US |
| **Moneda SIN paréntesis** ⚠️ | `"$"#,##0.00;[Red]"$"#,##0.00` | 161 | **solo** los totales duros del resumen ejecutivo (S5): 36, 50, 65, 78, 80, 85, 89, 93, 98, 100, 107, 109, 114, 119, 122, 127, 132, 140 | `$-1,234.56` en ROJO, **sin paréntesis**. Es la excepción deliberada del archivo |
| **Contable estilo Excel** | `_-* #,##0_-;\-* #,##0_-;_-* "-"??_-;_-@_-` | 91 | bloque KPI (3–6, 11–14) | `-1,234` con guion; el cero se muestra como `-` |
| | `_-* #,##0.00_-;…` | 5 | fila 8 (ADR) y C11–C14 | ídem con 2 decimales |
| | `_([$$-409]* #,##0.00_);_([$$-409]* \(#,##0.00\);_([$$-409]* "-"??_);_(@_)` | 9 | fila 8 (H8:O8, Q8) | contable con `$` a la izquierda del campo |
| **Entero con paréntesis** | `#,##0;\(#,##0\);\-` | 22 | D/E de filas 949, 954, 959, 968, 973, 978, 983, 984, 988, 1000, 1006 | `(1,234)`; cero = `-` |
| **Porcentaje** | `0.00%` | 35 | fila **7** (`% de Ocupación`) completa; C187, C231, B137 y la columna huérfana HB29:HB44 | sin tratamiento especial de negativo |
| **Fecha** | `mmm-yy` | 13 | fila 18 (D18:O18, Q18) — **residual**: los valores reales son texto (`"Enero"`…) | n/a |
| **General** | `General` | 822 | etiquetas de texto (columna C) y encabezados | n/a |

### Convención de negativos — resumen

1. **Regla general del reporte: negativos entre paréntesis y en rojo.** `($1,234.56)`
2. **Excepción única:** los 18 totales duros del resumen ejecutivo (S5) usan rojo **sin** paréntesis.
3. **Los ceros se ocultan**: la tercera sección `""` del formato principal hace que un 0 se vea
   como celda vacía. Esto es visualmente muy importante — el reporte se ve "limpio" porque
   cientos de celdas en 0 no imprimen nada.
4. En el bloque KPI el cero se muestra como guion `-` (formato contable clásico).

### ⚠️ Defecto heredado detectable

Las filas de ratio S10 (`% de Ingresos del Depto.`, `% Utilidad`) contienen fórmulas
`=IFERROR(D293/D259,"")` (un cociente, 0–1) pero tienen aplicado el **formato de moneda**, no
`0.00%`. En Excel se ven como `$0.35` en vez de `35.00%`. Al reconstruir hay que decidir: replicar
el defecto (fidelidad literal) o corregirlo a `0.00%` (lo correcto). **Recomendación: corregir y
avisar al owner** — es el único punto donde "no perder nada" y "estar bien" chocan.

---

## 5. BORDES — la convención contable

No hay líneas verticales de rejilla en el cuerpo (`showGridLines = False`). Los bordes se usan
**exclusivamente como semántica contable**:

| Estilo de borde | Celdas | Significado |
|---|---|---|
| **`double` arriba** | 684 + 104 | **SUBTOTAL** — la raya que se dibuja *sobre* un total en contabilidad. Filas S9 (`#BDD7EE`) |
| **`double` arriba + `double` abajo** | 684 | Subtotal que **cierra** el grupo (no sigue nada debajo) |
| **`thin` abajo** | 403 | Bajo un **encabezado de categoría** (S8) — "abre" el grupo |
| **`medium` arriba + `thin` abajo** | 221 | Primera categoría de un departamento — separa del banner |
| **`double` arriba + `medium` abajo** | 221 | Cierre de sección con fila de ratio debajo |
| **`thick` arriba** | 130 + 38 | **GRAN TOTAL** — utilidad neta del departamento (S11) |
| **`double` arriba + `thick` abajo** | 52 | Total de bloque overhead (721, 773, 827, 886) |
| **`medium` en los 4 lados** | 185 + varios | **Caja** alrededor de un total del resumen ejecutivo (S5) y de las celdas C/Q del banner de departamento |
| **`medium` arriba (f.3) / abajo (f.9) + `medium` izq. en C + `medium` der. en O y Q** | 32+23+17+8 | **Marco** del bloque KPI (filas 3–9) y de la cabecera de meses (f.18–20) |

**Regla derivada, en una frase:**
`thin` = abre grupo · `double` = subtotal · `thick` = total mayor · `medium` = marco de bloque.

---

## 6. INDENTACIÓN, ALINEACIÓN Y JERARQUÍA

- **`alignment.indent` = 0 en todas las celdas.** No se usó sangría de Excel.
- **Sin espacios iniciales**: se verificaron las 861 etiquetas de la columna C → todas con 0
  espacios al inicio. La jerarquía **no** viene del texto.
- **La jerarquía se lee del color de fondo.** Orden de peso visual, de mayor a menor:
  `#404040` banner > `#262626` utilidad neta > `#CCCCFF` total ejecutivo > `#BDD7EE` subtotal >
  `#D9E1F2` categoría > `#F2F2F2` ratio > `#FFFFFF` detalle.
- **Alineación por columna:**

| Columna | Alineación | Nota |
|---|---|---|
| B (2) | `left` (82 celdas) | columna auxiliar, ancho 5.71, prácticamente vacía |
| **C (3)** | por defecto (**izquierda**); 26 celdas con `left` explícito (rows 567–591) | columna de etiquetas |
| **D–O (4–15)** | **`center`** | ⚠️ los números están CENTRADOS, no a la derecha |
| P (16) | — | columna espaciadora, ancho 3.29 |
| **Q (17)** | **`center`** | Total Año |

- Sin `wrapText` en ninguna celda. Sin alineación vertical explícita (default `bottom`).

---

## 7. ANCHOS DE COLUMNA Y ALTOS DE FILA

Ancho por defecto: `11.43` · alto por defecto: `15.0 pt`.

| Columna | Ancho Excel | ≈ px | Rol |
|---|---|---|---|
| A | 4.00 | 33 | margen izquierdo |
| B | 5.71 | 45 | auxiliar |
| **C** | **44.00** | **313** | **etiquetas** |
| D | 14.86 | 109 | Enero (más angosta que el resto — anomalía del original) |
| E, F, G | 22.71 | 164 | Feb–Abr |
| H | 22.71 | 164 | May |
| I | 21.71 | 157 | Jun |
| J–N | 22.71 | 164 | Jul–Nov |
| O | 21.43 | 155 | Diciembre |
| P | 3.29 | 28 | **espaciador** antes del total |
| **Q** | **28.57** | **205** | **Total Año** |
| R–… | 15.71 | 115 | fuera del área imprimible |

Altos de fila usados (todos explícitos, ninguno automático en el cuerpo):

| Alto (pt) | ≈ px | Nº filas | Tipo de fila |
|---|---|---|---|
| 48.75 | 65 | 1 | Título (fila 2) |
| 20.25 | 27 | 6 | Bloque membresías (11–16) |
| 20.10 | 27 | 7 | Bloque KPI (3–9) |
| 17.25 | 23 | 70 | **Subtotales (S9) y utilidades netas (S11)** |
| 16.50 | 22 | 147 | Categorías, banners, totales ejecutivos, ratios |
| 15.75 | 21 | 229 | **Detalle (fila base)** |
| **3.95 / 3.75** | **5** | 7 | **Separadores finos** (155, 188, 189, 229, 232, 337, 663) |

**266 filas están ocultas** (`hidden=True`). Rangos: 5, 33–34, 52, 70, 95–96, 102–103, 111, 117,
121, 126, 141–147, 149–152, **234–294**, **446–536**, **648–660**, **723–740**, **828–886**.
Los bloques grandes son secciones de departamento colapsadas (A&B detalle, Tienda/Bar,
Ingresos Varios, Administración, Sistemas). Al reconstruir hay que decidir si se muestran o
se ofrecen colapsadas.

---

## 8. FORMATO CONDICIONAL, IMÁGENES Y OTROS OBJETOS

- **Formato condicional: NINGUNO.** `ws.conditional_formatting` está vacío. Todo el color es estático.
- **Imágenes / logos: 0.** **Gráficos: 0.**
- **Celdas combinadas: 1** → `C2:Q2` (el título centrado).
- **Panes congelados: ninguno** (`freeze_panes = None`), pero la **impresión sí repite cabecera**:
  `print_title_rows = $17:$21`, `print_title_cols = $C:$C`. Ese es el comportamiento a replicar
  en web con `position: sticky` (encabezado de meses + columna de etiquetas).
- **Comentarios (notas amarillas de Excel): 7**, todas de *Bismark Rodriguez*, todas en la columna C
  del bloque de gastos de propiedad:

| Celda | Nota |
|---|---|
| C567 | Mantenimiento Instalaciones + Mantenimiento General |
| C568 | Subcontrato Facturación – Contabilidad – cobros (SANDI) |
| C570 | servicios de seguridad |
| C581 | Dispensador de agua JUTURNA + suministros de oficinas |
| C584 | Actividad fin de año, eventos especiales y Publicidad y promoción |
| C585 | Servicio de mantenimiento piscina, Equipo de piscina y químicos Piscinas |
| C586 | EQUIPO Y LICENCIAS |

- **7 enlaces externos** (`externalLink1..7`) — las fórmulas apuntan a `'[1]Budget 2025W'!…`,
  `'[1]P&L Detail Club'!…`, etc. Es decir: **esta hoja es una vista, los datos viven en otro libro.**
- **Configuración de página:** horizontal, papel 5 (Legal), `fitToWidth=2`, `fitToHeight=2`,
  escala 38 %, márgenes 0.5" en los 4 lados, área de impresión `$C$2:$Q$1008`.
- **Vista:** rejilla oculta, zoom 71 %.

---

## 9. TRADUCCIÓN A CSS/HTML — receta de reconstrucción

### 9.1 Tokens

```css
:root{
  /* Rellenos */
  --pl-detalle:        #FFFFFF;  /* línea de cuenta            */
  --pl-categoria:      #D9E1F2;  /* encabezado de categoría    */
  --pl-subtotal:       #BDD7EE;  /* subtotal de grupo          */
  --pl-ratio:          #F2F2F2;  /* fila de %                  */
  --pl-resumen:        #CCCCFF;  /* totales del P&L ejecutivo  */
  --pl-neta:           #262626;  /* utilidad neta de depto.    */
  --pl-banner:         #404040;  /* banner de departamento     */
  --pl-kpi:            #D0CECE;  /* bloque de estadísticas     */
  --pl-separador:      #EBEBEB;  /* franja de 5px              */
  --pl-meses:          #EDEDED;  /* cabecera de meses          */
  --pl-revision:       #DAE3F3;  /* dato marcado para revisar  */

  /* Texto */
  --pl-tx-base:        #000000;
  --pl-tx-azul:        #1F3864;  /* sobre subtotal y categoría */
  --pl-tx-inverso:     #FFFFFF;  /* sobre neta y banner        */
  --pl-tx-ratio:       #595959;
  --pl-tx-rojo:        #FF0000;  /* título y etiqueta banner   */
  --pl-tx-mes:         #C65911;

  /* Métrica */
  --pl-font:           Arial, Helvetica, sans-serif;
  --pl-size:           16px;     /* Arial 12 pt                */
  --pl-h-detalle:      21px;     /* 15.75 pt                   */
  --pl-h-seccion:      22px;     /* 16.50 pt                   */
  --pl-h-total:        23px;     /* 17.25 pt                   */
  --pl-h-separador:     5px;     /*  3.95 pt                   */
  --pl-w-label:       313px;     /* col C = 44                 */
  --pl-w-mes:         164px;     /* cols E..N = 22.71          */
  --pl-w-ene:         109px;     /* col D  = 14.86             */
  --pl-w-gap:          28px;     /* col P  =  3.29             */
  --pl-w-total:       205px;     /* col Q  = 28.57             */
}
```

### 9.2 Clases de fila (1:1 con la tabla del §3)

```css
.pl-tabla{ border-collapse:collapse; font:var(--pl-size)/1.15 var(--pl-font);
           table-layout:fixed; background:#fff; }
.pl-tabla td{ padding:0 6px; white-space:nowrap; }

/* La etiqueta va a la izquierda; TODOS los números van CENTRADOS (fiel al original) */
.pl-tabla td.lbl { text-align:left;   width:var(--pl-w-label); }
.pl-tabla td.num { text-align:center; }
.pl-tabla td.gap { width:var(--pl-w-gap); background:#fff; border:0 !important; }

.r-detalle   { background:var(--pl-detalle);   color:var(--pl-tx-base);   height:var(--pl-h-detalle); }
.r-categoria { background:var(--pl-categoria); color:var(--pl-tx-azul);   font-weight:700;
               height:var(--pl-h-detalle); border-bottom:1px solid #7F7F7F; }
.r-categoria.primera { border-top:2px solid #000; }               /* medium */
.r-subtotal  { background:var(--pl-subtotal);  color:var(--pl-tx-azul);   font-weight:700;
               height:var(--pl-h-total);   border-top:3px double #000; }
.r-subtotal.cierra { border-bottom:3px double #000; }
.r-ratio     { background:var(--pl-ratio);     color:var(--pl-tx-ratio);  font-style:italic;
               height:var(--pl-h-seccion); border-top:3px double #000; border-bottom:2px solid #000; }
.r-ratio.fuerte    { border-top:3px solid #000; }                  /* thick */
.r-neta      { background:var(--pl-neta);      color:var(--pl-tx-inverso);font-weight:700;
               height:var(--pl-h-total);   border-top:3px solid #000; }
.r-neta.overhead   { border-top:3px double #000; border-bottom:3px solid #000; }
.r-banner    { background:var(--pl-banner);    color:var(--pl-tx-inverso);font-weight:700;
               height:var(--pl-h-seccion); border-top:2px solid #000; border-bottom:2px solid #000; }
.r-banner .lbl     { color:var(--pl-tx-rojo); }                    /* etiqueta en rojo */
.r-resumen   { background:var(--pl-resumen);   color:var(--pl-tx-base);   font-weight:700;
               height:var(--pl-h-detalle); border-top:1px solid #000; border-bottom:1px solid #000; }
.r-resumen.total   { height:var(--pl-h-seccion); border:2px solid #000; }
.r-kpi       { background:var(--pl-kpi);       font-weight:700; height:27px; }
.r-separador { background:var(--pl-separador); height:var(--pl-h-separador); }
.r-revision  { background:var(--pl-revision); }
.r-meses     { background:var(--pl-meses);     color:var(--pl-tx-mes);    font-weight:700;
               height:var(--pl-h-seccion); border-top:2px solid #000; }
```

### 9.3 Equivalencias Excel → CSS

| Excel | CSS |
|---|---|
| `thin` | `1px solid #000` |
| `medium` | `2px solid #000` |
| `thick` | `3px solid #000` |
| `double` | `3px double #000` |
| Arial 12 pt | `16px Arial` |
| alto 15.75 pt | `21px` (`pt × 4/3`) |
| ancho 44 | `313px` (`ancho × 7 + 5`) |
| `showGridLines=False` | no poner bordes por defecto en `td` |
| `print_title_rows=$17:$21` | `thead` + `position:sticky; top:0` |
| `print_title_cols=$C:$C` | `td.lbl { position:sticky; left:0; z-index:1 }` |
| celdas combinadas `C2:Q2` | `<td colspan="15">` en la fila de título |
| filas `hidden=True` | `<tr class="oculta">` + toggle de "mostrar detalle" |

### 9.4 Formateador de números (JS) — replica exacta

```js
// Moneda estándar del reporte: ($1,234.56) en rojo, cero = vacío
function fmtMoneda(v, {parentesis = true} = {}) {
  if (v === null || v === undefined || v === '' || Number(v) === 0) return '';
  const n = Number(v);
  const abs = Math.abs(n).toLocaleString('en-US',
                {minimumFractionDigits: 2, maximumFractionDigits: 2});
  if (n < 0) return parentesis ? `($${abs})` : `$-${abs}`;   // ambas van en rojo
  return `$${abs}`;
}
// Totales duros del resumen ejecutivo (S5): fmtMoneda(v, {parentesis:false})
// Bloque KPI (entero contable): 0 se muestra como '-', negativo con guion
function fmtEntero(v){
  if (v === null || v === undefined || v === '' || Number(v) === 0) return '-';
  return Number(v).toLocaleString('en-US', {maximumFractionDigits: 0});
}
// % de ocupación (y las filas de ratio, si se corrige el defecto)
const fmtPct = v => (v == null || v === '') ? '' : (Number(v) * 100).toFixed(2) + '%';
```

Y la clase de color para negativos:

```css
td.neg { color:#FF0000; }   /* aplicar cuando el valor sea < 0, en CUALQUIER estilo de fila */
```

### 9.5 Anatomía de un bloque de departamento (patrón que se repite 15 veces)

```
r-banner        DEPARTAMENTO DE HABITACIONES        (#404040, etiqueta roja)
r-separador                                          (#EBEBEB, 5px)
r-categoria     Ingresos por Habitaciones            (#D9E1F2, borde medium arriba)
r-detalle       Cancelaciones / No Show / Habitaciones
r-subtotal      Total Ingresos por Habitaciones      (#BDD7EE, double arriba)
r-separador
r-categoria     NÓMINA                               (#D9E1F2)
r-detalle       Salarios y Sueldos … Otros Beneficios (17 conceptos CR)
r-subtotal      TOTAL NÓMINA                         (#BDD7EE)
r-ratio         % de Ingresos del Depto.             (#F2F2F2, itálica)
r-separador
r-categoria     Gastos Operativos                    (#D9E1F2)
r-detalle       Suministros de Limpieza … Lavado de Uniformes
r-subtotal      TOTAL GASTOS OPERATIVOS              (#BDD7EE)
r-separador
r-neta          UTILIDAD NETA HABITACIONES           (#262626, blanco, thick arriba)
r-ratio         % Utilidad                           (#F2F2F2, thick arriba)
```

Los departamentos con costo de ventas (A&B, Spa, Tours, Tienda, Bar, Club, Área Recreativa)
insertan un bloque `r-categoria COSTO DE VENTAS → r-detalle × n → r-subtotal Total Costo de Ventas`
entre INGRESOS y NÓMINA.

### 9.6 Estructura global de la hoja

| Filas | Bloque |
|---|---|
| 1 | espaciador (D1 crema, residual) |
| **2** | Título `Presupuesto 2026 Consolidado` — Arial 26 bold rojo, combinado C:Q |
| **3–9** | Bloque KPI (`#D0CECE`, marco medium) |
| 10, 17 | espaciadores |
| **11–16** | Bloque membresías Club (`#D0CECE`, Segoe UI 14 bold) |
| **18–20** | Cabecera de meses + `DESCRIPCIÓN DE CUENTA` + franja de cierre `#CCCCFF` |
| **21–145** | **P&L ejecutivo consolidado** (paleta `#CCCCFF` + blanco) — de INGRESOS a UTILIDAD NETA |
| 146–153 | espaciadores/ocultas |
| **154–943** | **Detalle por departamento** — 15 bloques con el patrón de §9.5 |
| **944–1008** | **Cola bajo GOP**: alquiler, honorarios de administración, seguro, intereses, cargos bancarios, cambiaria, capital, depreciación, multas, impuesto sobre la renta |

---

## 10. CHECKLIST PARA "NO PERDER NADA"

- [ ] 12 colores de relleno + 6 de texto exactos (§2)
- [ ] Arial 12 pt en todo, salvo el título (26) y las membresías (Segoe UI 14)
- [ ] **Números centrados**, etiquetas a la izquierda
- [ ] **El cero no se imprime** (formato con tercera sección `""`)
- [ ] Negativos entre paréntesis y en rojo — **excepto** los 18 totales del resumen ejecutivo
- [ ] `double` arriba en los 50 subtotales, `thick` arriba en las 15 utilidades netas
- [ ] Las 7 franjas separadoras de 5 px
- [ ] Columna P: espaciador de 28 px antes de "Total Año"
- [ ] Columna D (Enero) más angosta que las demás (109 px vs 164 px)
- [ ] Cabecera de meses en naranja `#C65911` sobre `#EDEDED`
- [ ] Etiqueta del banner de departamento en **rojo** sobre carbón (los datos en blanco)
- [ ] Cabecera y columna de etiquetas fijas al hacer scroll (equivale a `print_title_rows/cols`)
- [ ] 266 filas ocultas: decidir mostrar / colapsar
- [ ] 7 comentarios de Bismark → tooltips en la columna de etiqueta
- [ ] Filas de ratio: decidir si se replica el formato de moneda (defecto) o se corrige a `0.00%`
