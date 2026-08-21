# ESCANEO 03 — Mapa de fórmulas y dependencias

**Archivo:** `C:\FinPlan_CWL\docs\fase2\PL_DETALLADO_FORMATO.xlsx`
**Hoja:** `P&L Full Detail` (única) · rango real `A1:HB1046`, contenido en filas 1–1007
**Método:** openpyxl `data_only=False` (fórmulas) + segunda pasada `data_only=True` (valores cacheados)

---

## 1. Resumen ejecutivo

### 1.1 El hallazgo central

**Este archivo no contiene ni un solo número.** Sobre 11.240 celdas con contenido:

| Tipo de celda | Cantidad |
|---|---|
| Fórmulas | **10.122** |
| Texto (etiquetas, encabezados) | 1.118 |
| **Constantes numéricas** | **0** |

No hay ninguna celda de entrada manual numérica. El archivo es **puro formato de presentación**: una cáscara de 910 filas que lee sus valores de otro libro y los reordena para mostrarlos.

De las 10.122 fórmulas, **8.797 (86,9 %) son referencias a un libro externo**. Las 1.325 restantes son agregaciones y aritmética que operan sobre esas mismas referencias. Sin el libro externo el reporte es una hoja de ceros.

### 1.2 Fórmulas por familia

| # | Familia | Cant. | % | Descripción |
|---|---------|------:|----:|---|
| 1 | **Referencia externa simple** | 8.756 | 86,5 % | `=+'[1]Budget 2025W'!K17` — un valor traído tal cual |
| 2 | **Suma horizontal (12 meses)** | 695 | 6,9 % | `=SUM(D23:O23)` en columna Q (Total Año) |
| 3 | **Aritmética interna** | 336 | 3,3 % | `=+D65-D78`, `=D165-D186-D227` (cadena del P&L) |
| 4 | **Suma vertical (subtotal)** | 156 | 1,5 % | `=SUM(D23:D35)` — solo 12 filas distintas × 13 columnas |
| 5 | **IFERROR (ratios %)** | 110 | 1,1 % | `=IFERROR(D293/D259,"")` — % sobre ingreso del depto |
| 6 | **Referencia interna simple** | 54 | 0,5 % | `=+D131`, `=+O11` |
| 7 | **Externa con cálculo** | 12 | 0,1 % | `=+'[1]Budget 2025W'!K179-...!K769-...!K770` |
| 8 | **Externa + SUM** | 1 | 0,0 % | Q137 (ver §5.9) |
| 9 | **IF** | 1 | 0,0 % | `=IF(Q3=0,"",Q4/Q3)` — % ocupación anual |
| 10 | **División simple** | 1 | 0,0 % | `=+Q23/Q4` — ADR anual |

**Funciones usadas en todo el libro: solo 3.** `SUM` (853), `IFERROR` (110), `IF` (1).
No hay `VLOOKUP`, `INDEX/MATCH`, `SUMIF`, `OFFSET`, `INDIRECT`, referencias circulares, tablas, ni nombres definidos en uso. La lógica es trivial; **toda la complejidad vive en el libro externo.**

### 1.3 Hojas externas

El archivo declara **7 libros externos** en su cadena de vínculos, pero **solo el `[1]` se usa realmente**. Los otros 6 son basura heredada de copiar/pegar entre archivos a lo largo de los años (uno apunta a una auditoría de Nicaragua de 2012).

| Ref | Ruta declarada | ¿Se usa? |
|-----|----------------|----------|
| **`[1]`** | `G:\.shortcut-targets-by-id\...\3-102-865727 - CORCOVADO HOLDING SCP S.R.L\AMARENA\BUDGET 2026\BUDGET 2026-AMA.xlsx` | **SÍ — 8.797 refs** |
| `[2]` | `\\8EFA44D0\CP 2025 Property Budget Template_Master working.xlsx` | No |
| `[3]` | `F:\ESTADOS FINANCIEROS\Estados Financieros DICIEMBRE 2023 FINAL.xls` | No |
| `[4]` | `E:\Presupuesto 2020\...\PL Definitivo (00B) 29_01 (VERSION) 11 PC F(VERSION ULTIMA) (1) (FLUJO DE CAJA).xlsx` | No |
| `[5]` | `\\0E29EA9E\CWL RATES 2022-2025 (Ajuste Lapa Rios) 2026 (TA).xlsx` | No |
| `[6]` | `https://desarrolladores506-my.sharepoint.com/.../Presupuesto Proyecto Amarena.xlsx` | No |
| `[7]` | `\\tsclient\C\...\Auditoria 30-jun-12\...\Cierre_de_Caja_Masaya_16_de_Junio_2012(VALE).xlsx` | No |

Dentro de `[1]` se usan **2 hojas**:

| Hoja externa | Refs | Filas externas distintas | Rango |
|---|---:|---:|---|
| `Budget 2025W` | 8.749 | **725** | 3 – 1434 |
| `P&L Detail Club` | 48 | 4 | 12 – 15 |

> **Nota de nomenclatura:** el libro se llama `BUDGET 2026-AMA.xlsx`, la hoja se llama `Budget 2025W`, y el reporte se titula `Presupuesto 2026 Consolidado` con encabezado de columna `Presupuesto 2026`. El nombre de la hoja quedó sin actualizar del año anterior. **Es Amarena (AMA), no CWL.**

### 1.4 Geometría de la hoja

| Columna | Contenido |
|---|---|
| A, B | vacías (sangría visual) |
| **C** | Etiqueta de la línea (861 textos) |
| **D … O** | Los 12 meses: D=Enero … O=Diciembre (fila 18 tiene los nombres) |
| P | vacía (separador) |
| **Q** | **Total Año** |
| R … HA | vacías |
| HB | 11 celdas sueltas con nombres de meses en inglés (`January`, `March`, …) — basura, filas 29–42, sin fórmula ni uso |

**Mapeo de columnas al libro externo (100 % consistente, sin una sola excepción):**

```
Este archivo    ->  'Budget 2025W'      'P&L Detail Club'
D (Enero)       ->  K                   D
E (Febrero)     ->  L                   E
...                 ...                 ...
O (Diciembre)   ->  V                   O
Q (Total Año)   ->  AP                  (no aplica)
```

Es decir: `Budget 2025W` tiene los meses en K:V y el total anual en AP. `P&L Detail Club` usa el mismo layout D:O que este archivo.

### 1.5 Cómo se llena la columna Q (Total Año)

| Patrón | Filas | Nota |
|---|---:|---|
| `=SUM(Dn:On)` — suma los 12 meses | 695 | El caso normal. Verificado: el rango de fila siempre coincide con la propia fila (0 errores) |
| Sin fórmula (etiqueta o separador) | 102 | |
| Aritmética (cadena del P&L) | 53 | Replica la fórmula del mes |
| `=+'[1]Budget 2025W'!APn` — total anual externo | 45 | Solo en el P&L consolidado, filas 23–138 |
| `=SUM(Qa:Qb)` — subtotal vertical | 12 | Las 12 filas de subtotal |
| `=+On` (toma diciembre) | 2 | Filas 11–14, saldos de membresías |
| `IF` | 1 | Fila 7 |

**Verificación de cuadre Q vs. suma de meses (valores cacheados):** de 910 filas, solo **5** difieren, y las 5 por diseño correcto: filas 7 (% ocupación), 8 (ADR), 11, 12, 13 (conteos de membresías, que son saldos puntuales, no flujos). **Las 45 filas que traen el total anual externo `AP` cuadran al centavo con la suma de K:V.** El libro externo es internamente consistente.

---

## 2. Mapa de dependencias externas

### 2.1 `[1]P&L Detail Club` — 4 filas

| Fila reporte | Etiqueta | Celda externa | Qué representa |
|---|---|---|---|
| 11 | Total Membresias | `D12:O12` | Conteo de membresías del Club Madresal, por mes |
| 12 | Membresías Condicionados | `D13:O13` | Membresías condicionadas |
| 13 | Membresias Pagando | `D14:O14` | Membresías al día |
| 14 | Membresias En acuerdo de pago | `D15:O15` | Membresías en arreglo de pago |

Son **conteos (stock), no montos**. Su columna Q toma diciembre (`=+O11`), no la suma. Al reconstruir en la app: son cuatro series de enteros mensuales, y el "total" es el saldo de cierre.

### 2.2 `[1]Budget 2025W` — 725 filas, por sección del reporte

| Sección del reporte | Filas de este archivo | Filas externas pedidas | Qué representa |
|---|---|---|---|
| Estadísticas de operación | 3–8 | 3–8 | Hab. disponibles, ocupadas, hab/día, huéspedes, % ocup., ADR |
| INGRESOS consolidado | 23–31 | 17–24, 26 | 9 líneas de ingreso por departamento |
| Gastos operativos por depto (consolidado) | 40–48 | 32–40 | Costo total por depto de ingreso |
| Utilidad operativa por depto | 55–63 | 48–56 | Utilidad departamental ya calculada afuera |
| Overhead (gastos generales) | 71–75 | 66–70 | Admin, Ventas, Mantenimiento, Sistemas, Serv. Públicos |
| Alquiler y honorarios | 82–83 | 80–81 | Alquiler + honorarios de administración 5 % |
| Seguro de propiedad | 87 | 86 | |
| Otros gastos | 91 | 90 | |
| Pérdida financiera | 112 | 99 | |
| Depreciación | 116 | 103 | |
| Capital | 104–105 | 107–108 | Reserva de capital + mejoras mayores |
| Impuesto sobre la renta | 124 | 114 | 30 % |
| Bloque "Resumen" (chequeo alterno) | 136–138 | 150, 179, 204, 769, 770 | Nómina total, opex total, costo total |
| **DEPTO HABITACIONES** | 154–232 | 216–218, 222, 226–241, 245, 249–278, 283 | Ingreso · Nómina (16 conceptos) · Opex (30 líneas) |
| **DEPTO A&B** | 233–337 | 289–312, 315, 318–331, 334, 339–354, 359, 362–398, 401 | Ingreso · COGS · Nómina · Opex — el bloque más grande (95 filas ext.) |
| **DEPTO SPA** | 338–401 | 407–410, 414, 419, 423, 426–441, 445, 448–474, 477 | |
| **DEPTO TOURS** | 402–445 | 484–487, 492, 495–511, 514, 517–518, 521, 524–531 | |
| **DEPTO TIENDA DE REGALOS** | 446–492 | 541–544, 547, 550–565, 568, 571–576, 580, 585–592, 596 | |
| **DEPTO BAR PRIVADO** | 493–536 | 601–604, 609, 612–627, 630, 633–635, 637, 640–647, 651 | |
| **DEPTO CLUB MADRESAL** | 537–596 | 658–660, 664, 667–682, 686, 689–690, 692, 696–720, 724 | |
| **DEPTO LAVANDERÍA** | 597–647 | 786–788, 793, 799, 801, **1159–1174, 1179, 1183–1200, 1204** | Ingreso y COGS en el 700; nómina y opex saltan al 1100 (ver §5.6) |
| **DEPTO INGRESOS VARIOS** | 648–663 | 867–876, 878 | Solo ingresos, sin costos |
| **OH ADMINISTRACIÓN Y GENERAL** | 665–721 | 882–897, 900, 905–939, 943 | |
| **OH VENTAS Y MERCADEO** | 722–773 | 950–965, 969, 972–1001, 1004 | |
| **OH MANTENIMIENTO** | 774–827 | 1010–1025, 1028, 1031–1062, 1064 | |
| **OH SISTEMAS DE INFORMACIÓN** | 828–886 | 1070–1085, 1089, 1092–1096, 1100, 1104–1133, 1136 | Único OH con "Costo de Servicios" |
| **OH SERVICIOS PÚBLICOS** | 887–899 | 1141–1150, 1153 | Solo opex, sin nómina |
| **DEPTO ÁREA RECREATIVA** | 900–943 | 731, 737, 740–755, 759, 762, 765, 769–776 | |
| **GASTOS DE PROPIEDAD** | 946–1007 | 1356–1434 | Alquiler, honorarios, seguro, intereses, cargos bancarios, cambiaria, capital, depreciación, multas, renta |

### 2.3 Qué datos necesita el reporte para existir

Traducido a modelo de datos, el reporte necesita exactamente esto:

1. **Una serie mensual de 12 valores + un total anual** por cada una de **725 líneas contables**.
2. **6 estadísticas de operación** mensuales (habitaciones disponibles/ocupadas, hab/día, huéspedes, ocupación, ADR).
3. **4 conteos de membresías** del Club Madresal.
4. La estructura de **14 departamentos** (9 de ingreso + Área Recreativa + 5 de overhead) más el bloque de Gastos de Propiedad.
5. Por cada departamento operativo, el mismo patrón de **16–17 conceptos de nómina** (Salarios, Horas Extra, Día Libre, Feriado Trabajado, Comisiones, CCSS, Aguinaldo, Póliza Riesgos, Provisión Vacaciones, Vacaciones Disfrutadas, Cafetería, Preaviso y Cesantía, Bono Incentivo, Vivienda, Transporte, Otros Beneficios, y en Tours también Mano de Obra por Contrato).

**Nada de esto se calcula acá.** El motor de la app tiene que producir esas 725 series; este archivo solo dice cómo se ordenan y presentan.

### 2.4 Filas externas usadas por dos filas del reporte

Solo 2 casos, y ambos son deliberados (ver §5.9):

| Fila externa | Filas del reporte | Contexto |
|---|---|---|
| `Budget 2025W!769` | 137 (resta), 930 ("Varios" de Área Recreativa) | |
| `Budget 2025W!770` | 137 (resta), 931 ("Suministros Operativos" de Área Recreativa) | |

---

## 3. Subtotales y totales — jerarquía real

### 3.1 Las 12 únicas sumas verticales del archivo

Estas son las **únicas** filas que agregan otras filas del propio reporte con `SUM`. Todo lo demás que se llama "TOTAL" viene traído del libro externo.

| Fila | Etiqueta | Fórmula meses (D:O) | Fórmula Q | Filas con dato dentro del rango | Estado |
|---|---|---|---|---|---|
| **36** | INGRESOS TOTALES | `=SUM(D23:D35)` | `=SUM(Q23:Q35)` | 23,24,25,26,27,28,29,30,31 | OK |
| **50** | Total Gastos Operativos | D:G `=SUM(D37:D49)` · **H:O `=SUM(H40:H47)`** | `=SUM(Q40:Q47)` | 40–48 | ⚠ **§5.1** |
| **65** | UTILIDAD OPERATIVA | D:G `=SUM(D52:D64)` · **H:O `=SUM(H55:H63)`** | `=SUM(Q55:Q63)` | 55–63 | ⚠ **§5.2** |
| **78** | TOTAL GASTOS GENERALES | D:G `=SUM(D65:D77)` · **H:O `=SUM(H71:H77)`** | `=SUM(Q71:Q77)` | **65**, 71,72,73,74,75,76 | 🔴 **§5.3** |
| **85** | TOTAL ALQUILER Y HONORARIOS DE ADMINISTRACIÓN | `=SUM(D82:D84)` | `=SUM(Q82:Q84)` | 82, 83 | OK |
| **89** | SEGURO DE PROPIEDAD | `=SUM(D87:D88)` | `=SUM(Q87:Q88)` | 87 | OK |
| **93** | TOTAL OTROS GASTOS | `=SUM(D91:D92)` | `=SUM(Q91:Q92)` | 91 | OK |
| **107** | GASTO DE CAPITAL | `=SUM(D104:D105)` | `=SUM(Q104:Q105)` | 104, 105 | OK |
| **114** | GASTOS FINANCIEROS | `=SUM(D111:D112)` | `=SUM(Q111:Q112)` | 112 | OK |
| **119** | TOTAL DEPRECIACIONES | `=SUM(D116:D118)` | `=SUM(Q116:Q118)` | 116 | OK |
| **442** | TOTAL GASTOS OPERATIVOS (Tours) | `=SUM(D434:D441)` | `=SUM(Q434:Q441)` | 434–441 | ⚠ **§5.4** |
| **938** | TOTAL GASTOS OPERATIVOS (Área Rec.) | `=SUM(D930:D937)` | `=SUM(Q930:Q937)` | 930–937 | ⚠ **§5.4** |

Los rangos de 85, 89, 93, 107, 114 y 119 incluyen una o dos filas vacías al final — es margen deliberado para insertar líneas nuevas sin romper el subtotal. No es un error.

### 3.2 Cadena aritmética del P&L consolidado (filas 80–145)

Esta es la jerarquía real del estado de resultados. Cada fórmula está en las 13 columnas (D:O y Q) con la misma forma.

```
 36  INGRESOS TOTALES                    = SUM(23:35)              [9 líneas de ingreso]
 50  Total Gastos Operativos             = SUM(40:47|49)           [costo por depto]
 65  UTILIDAD OPERATIVA                  = SUM(55:63)              [utilidad por depto]
 78  TOTAL GASTOS GENERALES              = SUM(71:77)              [overhead]
 80  UTILIDAD OPERATIVA BRUTA (GOP)      = 65 - 78
 85  TOTAL ALQUILER Y HONORARIOS         = SUM(82:84)
 89  SEGURO DE PROPIEDAD                 = SUM(87:88)
 93  TOTAL OTROS GASTOS                  = SUM(91:92)
 98  TOTAL GASTOS NO OPERATIVOS          = 85 + 89 + 93
100  EBITDA ANTES DE CAPITAL             = 80 - 98
107  GASTO DE CAPITAL                    = SUM(104:105)
109  EBITDA DESPUÉS DE CAPITAL           = 100 - 107
114  GASTOS FINANCIEROS                  = SUM(111:112)
119  TOTAL DEPRECIACIONES                = SUM(116:118)
122  UTILIDAD ANTES DE IMPUESTOS         = 109 - 114 - 119
124  Impuesto sobre la Renta (30%)       = externo!114
127  UTILIDAD NETA                       = 122 - 124
```

**Bloque de re-expresión (filas 129–132)** — el mismo resultado por otro camino:
```
129  Ingresos totales                    = 36
130  Total gastos operativos             = 50 + 78
131  Gastos de la Propiedad              = 98 + 114 + 119 + 124 + 107
132  UTILIDAD NETA                       = 129 - 130 - 131
```

**Bloque "Resumen" (filas 136–141)** — un tercer camino, esta vez contra totales externos:
```
136  Total Nómina y Beneficios           = externo!150
137  Total Gastos Operativos             = externo!179 - externo!769 - externo!770
138  Costo Total                         = externo!204
139  Total Gastos de Propiedad           = 131
140  UTILIDAD NETA                       = 129 - 136 - 137 - 138 - 139
141  Variación 0                         = 132 - 140      <- celda de chequeo, debe dar 0
```
**Verificado: fila 141 = 0,00 en los 12 meses y en el total.** Los tres caminos cuadran.

**Filas 144–145** — dos agregados sueltos, sin uso en ninguna otra fórmula:
```
144  Gastos de propiedad                 = 85 + 89 + 93          (= fila 98)
145  Gastos después de EBITDA            = 107 + 114 + 119 + 124
```
Su columna Q usa `=SUM(D:O)` en lugar de replicar la aritmética, a diferencia de todas las demás filas de la cadena. Inofensivo (dan lo mismo) pero rompe el patrón.

### 3.3 Utilidad neta por departamento (bloques de detalle)

Todas siguen `Ingreso − COGS − Nómina − Opex`, con las fuentes traídas de afuera:

| Fila | Departamento | Fórmula |
|---|---|---|
| 230 | HABITACIONES | `=D165-D186-D227` (sin COGS — Rooms no tiene) |
| 335 | A&B | `=D259-D275-D293-D333` |
| 400 | SPA | `=D346-D350-D368-D398` |
| 444 | TOURS | `=D408-D412-D431-D442` |
| 491 | TIENDA | `=D452-D460-D478-D489` |
| 535 | BAR PRIVADO | `=D499-D504-D522-D533` |
| 595 | CLUB MADRESAL | `=D542-D546-D564-D593` |
| 646 | LAVANDERÍA | `=D602-D605-D623-D644` |
| 661 | INGRESOS VARIOS | `=D660` (sin costos) |
| **942** | **ÁREA RECREATIVA** | `=D905-D909-D927-D940` 🔴 **§5.5** |

### 3.4 Totales de overhead (bloques de detalle)

| Fila | Departamento | Fórmula |
|---|---|---|
| 721 | TOTAL ADMINISTRACIÓN Y GENERAL | `=D683+D720` (nómina + opex) |
| 773 | TOTAL VENTAS Y MERCADEO | `=D740+D772` |
| 827 | TOTAL MANTENIMIENTO | `=D792+D826` |
| 886 | TOTAL SISTEMAS DE INFORMACIÓN | `=D846+D853+D885` (nómina + costo servicios + opex) |
| 899 | TOTAL SERVICIOS PÚBLICOS | externo!1153 (no tiene nómina) |
| 940 | TOTAL GASTOS OPERATIVOS (Área Rec.) | `=+D938+D927` (opex + nómina) |

---

## 4. Filas sin fórmula (etiquetas / entrada manual)

**No existe ninguna celda de entrada manual numérica en todo el archivo.** Las 102 filas sin fórmula en D:O son todas:

**a) Títulos de sección (col. C con texto, D:O vacías):**
`2` Presupuesto 2026 Consolidado · `22` INGRESOS · `38` Gastos Operativos · `135` Resumen · `154` DEPARTAMENTO DE HABITACIONES · `233` A&B · `234/260/276/295` (INGRESOS/COSTO DE VENTAS/NÓMINA/Gastos Operativos) · `338` SPA · `402` TOURS · `446` TIENDA · `493` BAR PRIVADO · `537` CLUB MADRESAL · `597` LAVANDERÍA · `648` INGRESOS VARIOS · `664` OVERHEAD · `665` ADMINISTRACIÓN Y GENERAL · `722` VENTAS Y MERCADEO · `774` MANTENIMIENTO · `828` SISTEMAS · `887` SERVICIOS PÚBLICOS · `900` ÁREA RECREATIVA · `946` GASTOS DE PROPIEDAD · `948` ALQUILER · `953` HONORARIOS · `958` SEGURO DE PROPIEDAD · `967` INTERESES · `972` CARGOS BANCARIOS · `977` GANANCIA/PÉRDIDA CAMBIARIA · `982` RESERVA/GASTO DE CAPITAL · `987` DEPRECIACIÓN · `999` MULTAS · `1005` IMPUESTO SOBRE LA RENTA
(y los sub-encabezados equivalentes dentro de cada bloque departamental)

**b) Filas separadoras** que contienen un carácter de espacio `" "` en D:O y en Q — no son fórmulas, son texto. Filas 35, 37, 39, 51–54, 66–70, 77, 79, 84, 86, 88, 90, 92, 94, 96, 97, 99, 101, 106, 113, 115, 118, 120, 121, 123, 125, 126, 128, y las filas en blanco dentro de cada bloque (156, 157, 162–164, 166, 167, 185, 190, 191, 223–226, 228, …).

> **Importante para el port:** ese `" "` no es inocuo. `SUM` lo ignora, pero cualquier parser que trate la celda como "tiene contenido" va a confundir separadores con datos. Y es la razón por la que los rangos de subtotal pueden abarcar filas de encabezado sin dar error (§5.2).

**c) Fila 18** — nombres de meses (`Enero`…`Diciembre`, `Total Año`). **Fila 19** — subtítulo repetido `Presupuesto 2026` en las 13 columnas.

**d) Columna HB, filas 29–42** — 11 celdas con nombres de meses en inglés (`January`, `March`, `April`, `May`…`December`; **falta `February`**). Fuera de cualquier rango de fórmula, sin uso. Residuo de un pegado accidental. Descartable.

---

## 5. Inconsistencias y fórmulas raras

> Esta es la sección crítica. Ordenada de mayor a menor riesgo para la reconstrucción.

### 🔴 5.1 — Fila 50 «Total Gastos Operativos»: enero–abril suman un renglón que mayo–diciembre no

| Columnas | Fórmula | Filas sumadas |
|---|---|---|
| D, E, F, G (Ene–Abr) | `=SUM(D37:D49)` | 40, 41, 42, 43, 44, 45, 46, 47, **48** |
| H … O (May–Dic) | `=SUM(H40:H47)` | 40, 41, 42, 43, 44, 45, 46, 47 |
| Q (Total Año) | `=SUM(Q40:Q47)` | 40 … 47 |

**La fila 48 es «Ingresos Varios» (gasto operativo del depto de Ingresos Varios, externo!40).** Está incluida en el total de enero a abril y **excluida de mayo a diciembre y del total anual**.

**Por qué no ha estallado:** hoy los meses de enero a abril traen 0 en todo el reporte (ver §5.7), y la fila 48 vale 0 en los 12 meses. El error está latente. En cuanto se carguen datos reales en enero–abril **o** aparezca gasto en Ingresos Varios, el total mensual y el total anual dejan de cuadrar.

**Decisión para la app:** el rango correcto es **40:48** (las 9 líneas de gasto departamental, simétricas con las 9 líneas de ingreso de 23:31 y las 9 de utilidad de 55:63). Tanto el rango de mayo–diciembre como el de la columna Q están **mal**: omiten un departamento. Implementar `SUM(40:48)` y anotar la diferencia contra el Excel original.

### 🔴 5.2 — Fila 65 «UTILIDAD OPERATIVA»: mismo desfase, sin consecuencia

| Columnas | Fórmula | Filas con dato dentro |
|---|---|---|
| D–G | `=SUM(D52:D64)` | 55 … 63 |
| H–O | `=SUM(H55:H63)` | 55 … 63 |
| Q | `=SUM(Q55:Q63)` | 55 … 63 |

Enero–abril abarcan además las filas 52, 53, 54 y 64. Las tres primeras contienen el texto `" "` y la 64 está vacía, así que **`SUM` las ignora y el resultado es idéntico.** Es cosmética, pero delata la misma edición descuidada que produjo §5.1 y §5.3: alguien reescribió las fórmulas de mayo a diciembre y no tocó enero–abril (o al revés).

**Decisión:** usar `SUM(55:63)`.

### 🔴 5.3 — Fila 78 «TOTAL GASTOS GENERALES»: enero–abril **incluyen la fila 65 (UTILIDAD OPERATIVA)**

| Columnas | Fórmula | Filas con dato dentro |
|---|---|---|
| D, E, F, G (Ene–Abr) | `=SUM(D65:D77)` | **65**, 71, 72, 73, 74, 75, 76 |
| H … O (May–Dic) | `=SUM(H71:H77)` | 71, 72, 73, 74, 75, 76 |
| Q | `=SUM(Q71:Q77)` | 71 … 76 |

**El overhead de enero a abril incorpora la utilidad operativa del mes.** Y como la fila 80 hace `GOP = 65 − 78`, el GOP de esos cuatro meses queda `65 − (65 + overhead)` = `−overhead`: la utilidad operativa se anula y el GOP sale negativo por el monto total del overhead.

**Es el único error del archivo que corrompe el resultado, no solo un subtotal.** Está latente por la misma razón que §5.1: enero–abril valen 0 hoy. Confirmado con los valores cacheados: `D65 = D78 = D80 = 0`.

**Decisión:** el rango correcto es **71:77**. Enero–abril están mal, sin ambigüedad.

### 🔴 5.4 — Filas 442 y 938: los dos únicos «TOTAL GASTOS OPERATIVOS» que se calculan en vez de traerse

En los 12 bloques departamentales, la fila `TOTAL GASTOS OPERATIVOS` siempre viene del libro externo (`externo!283` para Habitaciones, `externo!401` para A&B, `externo!477` para Spa, etc.). **Dos excepciones:**

| Fila | Depto | Fórmula | Resto de los bloques |
|---|---|---|---|
| **442** | TOURS | `=SUM(D434:D441)` | traen `externo!` |
| **938** | ÁREA RECREATIVA | `=SUM(D930:D937)` | traen `externo!` |

En el libro externo, Tours y Área Recreativa **no tienen fila de total de opex** en el rango correspondiente (Tours usa 524–531 sin fila de total; Área Recreativa usa 769–776 igual). Quien armó el formato tuvo que sumarlas a mano.

**Consecuencia para la app:** son el único punto donde el reporte **calcula** un total departamental de opex en vez de leerlo. Si la app calcula todos los totales por su cuenta (lo recomendable), estos dos dejan de ser especiales — pero hay que verificar que el motor produzca el mismo número que el externo para los otros 10 departamentos, porque **hoy nadie valida esa igualdad.**

### 🔴 5.5 — Fila 942 «UTILIDAD NETA ÁREA RECREATIVA»: la nómina se resta dos veces

```
938  TOTAL GASTOS OPERATIVOS   = SUM(D930:D937)      [solo opex]
940  TOTAL GASTOS OPERATIVOS   = +D938 + D927        [opex + NÓMINA]     <- mismo nombre, otro contenido
942  UTILIDAD NETA ÁREA REC.   = D905 - D909 - D927 - D940
                                             ^^^^   ^^^^
                                             nómina  ya contiene la nómina
```

`D927` (TOTAL NÓMINA) se resta explícitamente **y** viene dentro de `D940`. **La nómina de Área Recreativa se descuenta dos veces.**

Compárese con los otros nueve departamentos, que hacen `Ingreso − COGS − Nómina − Opex` con un opex que **no** incluye nómina.

Agravante de legibilidad: **las filas 938 y 940 tienen la misma etiqueta** `TOTAL GASTOS OPERATIVOS` con significados distintos. Es la trampa que provocó el error.

**Latente** (Área Recreativa vale 0 hoy). **Decisión:** la fórmula correcta es `=D905-D909-D927-D938`, o equivalentemente `=D905-D909-D940`.

### 🟠 5.6 — Lavandería: nómina y opex viven en otra zona del libro externo

| Sub-bloque | Filas del reporte | Filas externas |
|---|---|---|
| Ingresos | 599–602 | 786–788, **793** |
| Costo de ventas | 604–605 | 799, **801** |
| **Nómina** | 607–623 | **1159–1174, 1179** |
| **Gastos operativos** | 626–644 | **1183–1200, 1204** |

Los otros once departamentos tienen sus cuatro sub-bloques contiguos en el libro externo. Lavandería salta ~360 filas hacia adelante para nómina y opex.

**No es un error de fórmula** — es la estructura del libro externo: la planilla de Lavandería está en otra sección. Pero es una **trampa de mantenimiento**: si el reporte se regenera apuntando "el bloque siguiente", Lavandería se rompe. Documentarlo como caso especial en el mapeo del importador.

Detalle adicional: los saltos grandes de filas externas no usadas son `114→150`, `150→179`, `179→204`, `801→867` (65 filas) y `1204→1356` (**151 filas**). Ese último hueco es donde vive material del libro externo que este reporte ignora por completo.

### 🟠 5.7 — Enero a abril están vacíos en las estadísticas (filas 3–8)

| Fila | Etiqueta | D–G (Ene–Abr) | H–O (May–Dic) |
|---|---|---|---|
| 3 | Habitaciones Disponibles Totales | **sin fórmula** | `=+'[1]Budget 2025W'!O3` … `!V3` |
| 4 | Habitaciones Ocupadas Totales | **sin fórmula** | ✔ |
| 5 | Habitaciones por Día | **sin fórmula** | ✔ |
| 6 | Huéspedes Totales | **sin fórmula** | ✔ |
| 7 | % de Ocupación | **sin fórmula** | ✔ |
| 8 | Tarifa Promedio Diaria | **sin fórmula** | ✔ |

Las seis filas de estadísticas **no tienen fórmula en enero, febrero, marzo ni abril**, pero su columna Q sí hace `=SUM(D3:O3)`. El reporte es efectivamente de **8 meses (mayo–diciembre)** en su capa estadística, mientras el P&L abajo sí tiene las 12 columnas cableadas (aunque devuelvan 0).

Esto correlaciona con §5.1–§5.3: **el archivo se armó para un ejercicio que arranca en mayo**, y las fórmulas de enero–abril quedaron como estaban en la versión anterior, sin revisar. Es la causa raíz común de los tres bugs de rango.

### 🟠 5.8 — Los ratios (%) existen en 4 departamentos de 12, y uno está a medias

Solo hay **10 filas de ratio** en todo el archivo (110 fórmulas `IFERROR`):

| Fila | Depto | Ratio | Meses con fórmula | Q |
|---|---|---|---|---|
| 294 | A&B | `TOTAL NÓMINA / Total Ingresos A&B` | 12 | — |
| 334 | A&B | `TOTAL GASTOS OPERATIVOS / Ingresos` | 12 | — |
| 336 | A&B | `UTILIDAD NETA / Ingresos` | 12 | — |
| 479 | TIENDA | `Nómina / Ingresos` | 12 | — |
| 490 | TIENDA | `Opex / Ingresos` | 12 | — |
| 492 | TIENDA | `Utilidad / Ingresos` | 12 | — |
| 523 | BAR PRIVADO | `Nómina / Ingresos` | 12 | — |
| 534 | BAR PRIVADO | `Opex / Ingresos` | 12 | — |
| 536 | BAR PRIVADO | `Utilidad / Ingresos` | 12 | — |
| **624** | **LAVANDERÍA** | `Nómina / Ingresos` | **solo 2 (N y O = nov y dic)** | — |

Problemas:
1. **Faltan por completo** en Habitaciones, Spa, Tours, Club Madresal, Ingresos Varios, Área Recreativa y en los 5 departamentos de overhead.
2. **La fila 624 (Lavandería)** tiene la fórmula únicamente en noviembre y diciembre; los otros 10 meses están vacíos. Además **le faltan las dos filas hermanas** (% opex y % utilidad) que sí tienen A&B, Tienda y Bar Privado. Es un ratio a medio pegar.
3. **Ninguna** tiene fórmula en la columna Q: **no hay porcentajes anuales**.
4. La fila 624 **no tiene etiqueta** en la columna C (las otras nueve dicen `% de Ingresos del Depto.` / `% Utilidad`).

**Decisión para la app:** calcular los tres ratios para **todos** los departamentos y también para el total anual. El Excel es incompleto por accidente, no por diseño — la evidencia es que las tres filas aparecen juntas y con la misma redacción en los tres departamentos donde sí existen.

### 🟡 5.9 — Fila 137: la única fórmula que resta líneas de otro departamento

**Meses (12 fórmulas):**
```
=+'[1]Budget 2025W'!K179 - '[1]Budget 2025W'!K769 - '[1]Budget 2025W'!K770
```
**Total anual (Q137) — la única fórmula del archivo que mezcla referencia externa con `SUM` externo:**
```
=+'[1]Budget 2025W'!AP179 - SUM('[1]Budget 2025W'!K769:'[1]Budget 2025W'!V769)
                          - SUM('[1]Budget 2025W'!K770:'[1]Budget 2025W'!V770)
```

Las filas externas 769 y 770 son **«Varios» y «Suministros Operativos» de Área Recreativa** (filas 930 y 931 de este reporte). La fila 137 («Total Gastos Operativos» del bloque Resumen) toma el total de opex del libro externo y **le descuenta esas dos líneas**.

Es un **ajuste deliberado**, no un error: sin él la fila 141 («Variación 0») no daría cero — y da cero en los 12 meses. Pero es una regla de negocio **invisible y sin documentar** dentro de una fórmula, y es la razón de los únicos dos casos de fila externa referenciada dos veces (§2.4).

**Decisión:** documentar explícitamente en la app que el total de gastos operativos del resumen **excluye dos líneas de Área Recreativa**. Sin esta regla el cuadre se rompe y nadie va a saber por qué.

### 🟡 5.10 — Fila 76 «Área Recreativa»: los meses vienen de adentro, el total anual de afuera

| Columna | Fórmula |
|---|---|
| D … O | `=+D940` … `=+O940` (referencia **interna** al bloque de Área Recreativa) |
| **Q** | `=+'[1]Budget 2025W'!AP71` (referencia **externa**) |

Es la **única fila del archivo** cuyos meses y cuyo total anual salen de fuentes distintas. Las otras cinco filas de overhead (71–75) usan `externo!` en las 13 columnas.

Hoy ambos dan 0, así que no se detecta. Si `AP71` del libro externo difiere de la suma de `D940:O940`, **el total anual del overhead y del GOP no cuadran con la suma de los meses, sin ninguna alerta.**

**Decisión:** unificar. En la app, `Área Recreativa (overhead) = Nómina + Opex del bloque de Área Recreativa`, y el anual = suma de los meses.

### 🟡 5.11 — La estructura visual miente sobre la jerarquía

Tres puntos donde la indentación / el nombre no corresponde al cálculo:

1. **Filas 938 vs. 940** — misma etiqueta `TOTAL GASTOS OPERATIVOS`, contenidos distintos (§5.5).
2. **Fila 940** se llama «TOTAL GASTOS OPERATIVOS» pero **incluye la nómina**. En los cinco bloques de overhead el equivalente se llama `TOTAL ADMINISTRACIÓN Y GENERAL`, `TOTAL MANTENIMIENTO`, etc. — nombre honesto. Área Recreativa reutilizó el rótulo equivocado.
3. **Filas 127, 132 y 140** se llaman todas `UTILIDAD NETA` y son tres caminos al mismo número. La 141 (`Variación 0`) es la celda de control que lo verifica. Un lector desprevenido puede tomar cualquiera de las tres como "la" utilidad neta.

### 🟡 5.12 — Área Recreativa no entra en INGRESOS TOTALES

`INGRESOS TOTALES` (fila 36) suma las filas 23–31: nueve departamentos. **Área Recreativa no está.** Su ingreso (fila 905, `externo!737`) y su costo de ventas (fila 909, `externo!765`) **no llegan a ninguna parte del P&L consolidado.**

Área Recreativa entra al consolidado **solo como overhead** (fila 76 = fila 940 = nómina + opex). Su utilidad neta (fila 942) no alimenta ninguna fórmula.

Puede ser deliberado (tratar el área recreativa como centro de costo, no de ingreso), pero **hay que confirmarlo con el dueño**: si el área genera ingreso real, hoy se está perdiendo del estado de resultados.

### 🟡 5.13 — Las filas 3–8 y las membresías son las únicas con semántica no aditiva

Cuatro fórmulas se salen del patrón `SUM(D:O)` en la columna Q, y todas por razones válidas:

| Fila | Q | Motivo |
|---|---|---|
| 7 | `=IF(Q3=0,"",Q4/Q3)` | % ocupación anual = hab. ocupadas / hab. disponibles (no la suma de 12 porcentajes). **Única `IF` del archivo.** |
| 8 | `=+Q23/Q4` | ADR anual = ingreso de habitaciones / habitaciones ocupadas. **Única división simple del archivo.** |
| 11–14 | `=+O11` … `=+O14` | Conteo de membresías: saldo de cierre = diciembre |

**Ojo con la fila 8:** los doce meses traen el ADR de `externo!8` (calculado afuera), pero el anual se calcula **acá** como `Q23/Q4`. Si el libro externo calcula el ADR con otro criterio (p. ej. neto de cortesías, o incluyendo la fila 159 «Cancelaciones» / 160 «No Show»), el ADR anual y los mensuales quedan sobre bases distintas. Verificado con valores cacheados: Q8 = 382,59 y la suma de meses = 2.650,00 — la diferencia es esperada, pero **no hay forma de comprobar que el criterio coincida sin abrir el libro externo.**

### 🟢 5.14 — Los bloques de detalle no alimentan el consolidado

Arquitectura del archivo, y probablemente lo más importante para el diseño de la app:

**El P&L consolidado (filas 22–145) y los 12 bloques departamentales (filas 154–1007) son dos lecturas independientes del mismo libro externo.** No se hablan entre sí. La única excepción es la fila 76 (§5.10).

Verificado con valores cacheados — todas las parejas cuadran al centavo:

| Concepto | Consolidado | Bloque de detalle | Total Año | Dif. |
|---|---|---|---|---|
| Ingreso Habitaciones | fila 23 | fila 165 | 374.790,00 | 0,00 |
| Ingreso Spa | fila 25 | fila 346 | 11.448,00 | 0,00 |
| Ingreso Tours | fila 26 | fila 408 | 10.800,00 | 0,00 |
| Ingreso Club Madresal | fila 28 | fila 542 | 157.440,00 | 0,00 |
| Utilidad Habitaciones | fila 55 | fila 230 | 118.785,96 | 0,00 |
| Utilidad A&B | fila 56 | fila 335 | −27.869,62 | 0,00 |
| Utilidad Spa | fila 57 | fila 400 | 1.334,55 | 0,00 |
| Utilidad Tours | fila 58 | fila 444 | 734,58 | 0,00 |
| Utilidad Club Madresal | fila 60 | fila 595 | −42.811,19 | 0,00 |
| OH Administración | fila 71 | fila 721 | 85.621,59 | 0,00 |
| OH Ventas y Mercadeo | fila 72 | fila 773 | 76.993,20 | 0,00 |
| OH Mantenimiento | fila 73 | fila 827 | 107.431,55 | 0,00 |
| OH Sistemas | fila 74 | fila 886 | 1.400,00 | 0,00 |
| OH Servicios Públicos | fila 75 | fila 899 | 77.435,02 | 0,00 |

**Cuadran porque el libro externo es consistente, no porque el reporte lo garantice.** No hay una sola celda de control que compare el consolidado contra el detalle. Si el libro externo se desincroniza, el reporte muestra dos verdades distintas sin avisar.

**35 filas de total/utilidad son huérfanas** (no alimentan ninguna otra fórmula): las 10 utilidades netas departamentales, los 5 totales de overhead, las 10 filas de ratio, los 11 totales del bloque Gastos de Propiedad (951, 956, 965, 970, 975, 980, 985, 997, 1003, 1007), y las filas 127 y 141. Existen solo para mostrarse en pantalla.

**Decisión para la app:** implementar **una sola** fuente de verdad — el detalle — y **derivar** el consolidado agregando los departamentos. Replicar la doble lectura del Excel es reproducir su fragilidad.

---

## 6. Resumen de decisiones para la reconstrucción

| # | Punto | Qué hace el Excel | Qué debe hacer la app |
|---|---|---|---|
| 1 | Fila 50 (Total Gastos Operativos) | Ene–Abr suma 40:48, May–Dic y anual suman 40:47 | `SUM(40:48)` — las 9 líneas |
| 2 | Fila 65 (Utilidad Operativa) | rangos distintos, mismo resultado | `SUM(55:63)` |
| 3 | Fila 78 (Total Gastos Generales) | Ene–Abr incluyen la fila 65 (utilidad operativa) | `SUM(71:77)` |
| 4 | Fila 942 (Utilidad Área Recreativa) | resta la nómina dos veces | `905 − 909 − 927 − 938` |
| 5 | Fila 76 (Área Rec. en overhead) | meses internos, anual externo | una sola fuente; anual = suma de meses |
| 6 | Fila 137 (Resumen) | descuenta ext.769 y ext.770 sin documentar | regla explícita y visible |
| 7 | Ratios % | solo 4 deptos, Lavandería a medias, sin anual | los 3 ratios en todos los deptos + anual |
| 8 | Estadísticas filas 3–8 | Ene–Abr sin fórmula | 12 meses siempre |
| 9 | Área Recreativa | fuera de INGRESOS TOTALES | **confirmar con el dueño** |
| 10 | Totales de opex departamental | 10 traídos de afuera, 2 calculados (442, 938) | calcular los 12; validar contra el origen |
| 11 | Consolidado vs. detalle | dos lecturas independientes sin control | detalle = fuente única, consolidado derivado |
| 12 | Lavandería | nómina/opex en ext. 1159–1204, no contiguo | mapeo explícito en el importador |
| 13 | ADR (fila 8) | meses de afuera, anual = Q23/Q4 | fijar un criterio único y documentarlo |
| 14 | Libros externos [2]–[7] | 6 vínculos muertos | descartar |
| 15 | Columna HB | 11 celdas basura | descartar |

---

## 7. Nota de alcance

Todos los errores de §5.1, §5.3 y §5.5 están **latentes**: no se manifiestan hoy porque enero–abril y Área Recreativa valen 0. Un usuario que audite el Excel contra la app va a ver cifras idénticas y concluir que el port es fiel. **Se manifestarán en cuanto se carguen datos reales en esos meses o en ese departamento.** Conviene dejar constancia escrita de las diferencias antes de que aparezcan, para que no se lean como bugs de la app.

El scan cubre el 100 % de las 10.122 fórmulas de la única hoja del archivo. No se abrió el libro externo `BUDGET 2026-AMA.xlsx`; toda afirmación sobre su contenido se infiere de las referencias y de los valores cacheados en este archivo.
