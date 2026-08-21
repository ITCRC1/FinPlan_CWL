# ESCANEO 02 — ESTRUCTURA DE COLUMNAS

**Archivo:** `C:\FinPlan_CWL\docs\fase2\PL_DETALLADO_FORMATO.xlsx`
**Hoja:** `P&L Full Detail` (única)
**Dimensión declarada:** `A1:HB1046` (1046 filas × 210 columnas)
**Contenido real de la tabla:** `C2:Q1007` — 17 columnas útiles, 1007 filas
**Herramienta:** openpyxl 3.1.5, `data_only=False` (se leyeron fórmulas, no valores)

---

## 1. RESUMEN EJECUTIVO

### Hay UN SOLO bloque de 12 meses. No hay comparativos, ni varianzas, ni varios años.

La hipótesis de "varios bloques de 12 meses" **es falsa**. Las 210 columnas son un espejismo:

- La tabla ocupa **A..Q (17 columnas)**. El área de impresión lo confirma: `$C$2:$Q$1008`.
- La única celda combinada, **`C2:Q2`** (título *"Presupuesto 2026 Consolidado"*, Arial 26 pt centrado), define exactamente el ancho visual del reporte: de C a Q. Nada a la derecha de Q forma parte del reporte.
- De la columna **R (18) a la HA (209): 192 columnas completamente vacías** — sin valor y sin estilo (salvo restos en R..Y, ver §4).
- La columna **HB (210) es la culpable del "ancho 210"**: contiene una lista auxiliar de meses en inglés (`HB29:HB42`) que sirve de origen a una **validación de datos tipo lista sobre `D18:P18`** (el desplegable con el que se cambia el encabezado de mes). Es una celda-almacén, no una columna del reporte.

### Corrección al supuesto de partida
La fila 18 **no** llega hasta Noviembre en N: llega hasta **Diciembre en O**. El reparto real es
`D18:O18 = Enero..Diciembre` (12 meses) y **`Q18 = "Total Año"`**, con **P como separador vacío** en medio.

### Conteo de columnas

| Categoría | Cantidad | Columnas |
|---|---|---|
| Etiqueta de fila (cuentas) | 1 | C |
| Datos mensuales | 12 | D..O |
| Total anual | 1 | Q |
| **Datos reales (subtotal)** | **14** | **C..O + Q** |
| Separadores / decoración | 3 | A (margen), B (banda), P (gutter) |
| **Tabla completa** | **17** | **A..Q** |
| Vacías fuera de la tabla | 192 | R..HA |
| Auxiliar oculta de validación | 1 | HB |
| **Total del archivo** | **210** | A..HB |

### Encabezados apilados (3 niveles + 2 filas de aire)

| Fila | Rol | Contenido |
|---|---|---|
| 2 | **Título** (combinado `C2:Q2`) | `Presupuesto 2026 Consolidado` |
| 3–8 | Bloque de estadísticas (hab. disponibles/ocupadas, huéspedes, % ocupación, ADR) | — |
| 11–14 | Bloque de membresías del Club | — |
| **18** | **Nivel 1 de encabezado: MES** | `Enero … Diciembre` en D..O · `Total Año` en Q |
| **19** | **Nivel 2 de encabezado: ESCENARIO** | `DESCRIPCIÓN DE CUENTA` en C · `Presupuesto 2026` repetido en D..O **y** Q |
| 20–21 | Filas de aire con formato (parte del bloque de encabezado que se repite al imprimir) | vacías |
| 22+ | Cuerpo del reporte (`INGRESOS`, etc.) | — |

`print_title_rows = $17:$21` y `print_title_cols = $C:$C` → al imprimir se repiten las 5 filas de encabezado y la columna de etiquetas. **Ojo: `freeze_panes = None`** — en pantalla no hay paneles congelados pese a ser un reporte de 1007 filas.

### Implicación para la app web
El grid a reconstruir es **una sola rejilla: 1 columna de etiqueta + 12 columnas de mes + 1 columna de total**.
No hay que modelar escenarios lado a lado. El escenario ("Presupuesto 2026") es un **atributo global de la tabla**, no una dimensión de columna — por eso se repite idéntico en las 13 columnas de la fila 19. La columna P es puramente cosmética (separación visual antes del total) y se resuelve con CSS, no con una columna de datos.

---

## 2. MAPA DE BLOQUES

| Rango | Bloque | Cols | Qué es |
|---|---|---|---|
| **A** | Margen | 1 | Vacía, ancho 4.00. Margen izquierdo del reporte. |
| **B** | Banda izquierda | 1 | Vacía, ancho 5.71, con relleno sólido en 140 filas (bordea el bloque de encabezado y el cuerpo). Decorativa. |
| **C** | Etiqueta | 1 | `DESCRIPCIÓN DE CUENTA`. Ancho 44.00. 861 celdas de texto (nombres de cuenta/sección). Único texto del reporte. |
| **D..O** | **BLOQUE ÚNICO: 12 meses de Presupuesto 2026** | 12 | Enero→Diciembre. ~719 fórmulas por columna que son enlaces externos a `'[1]Budget 2025W'!K..V` (mapeo 1:1, ver §4). Formato moneda USD. |
| **P** | **SEPARADOR** | 1 | Vacía, ancho 3.29, con relleno y formato de moneda heredado en 1045 filas. Gutter visual entre Diciembre y el Total. Está **dentro** del rango combinado del título y **dentro** del rango de validación `D18:P18`. |
| **Q** | **TOTAL AÑO** | 1 | Ancho 28.57. 695 fórmulas `=SUM(D#:O#)` + 44 enlaces a la columna anual del origen + 12 `=SUM(Q#:Q#)` (subtotales de subtotales) + aritmética suelta. Relleno gris `FFEDEDED` en el encabezado. |
| **R..HA** | Fuera de la tabla | 192 | Vacías. Un registro de `<col>` (`R` con `min=18, max=529, width=15.71`) es lo que infla el rango usado. |
| **HB** | Auxiliar de validación | 1 | `HB29:HB42` = lista de meses en inglés, origen del desplegable de `D18:P18`. Única razón de que `max_column = 210`. |

**No existe ninguna columna de VARIACIÓN ni de PORCENTAJE.** Se verificó fórmula por fórmula: ninguna columna calcula `A−B`, `A/B−1` ni `%` sobre otra columna. Los porcentajes del reporte están implementados como **filas**, no como columnas:

| Fila | Etiqueta | Fórmula (col D) |
|---|---|---|
| 7 | `% de Ocupación` | enlace externo; en Q: `=IF(Q3=0,"",Q4/Q3)` — formato `0.00%` |
| 294, 334, 479, 490, 523, 534 | `% de Ingresos del Depto.` | `=IFERROR(D293/D259,"")` etc. |
| 336, 492, 536 | `% Utilidad` | `=IFERROR(D335/D259,"")` etc. |

### Confirmación de las columnas TOTAL

`Q` es la única columna total. Reparto de sus 774 fórmulas:

| Forma | Nº | Significado |
|---|---|---|
| `=SUM(D#:O#)` | 695 | Suma horizontal de los 12 meses ✅ |
| `=+'[1]Budget 2025W'!AP#` | 44 | Trae el total anual directo del libro origen (columna AP) en lugar de sumar |
| `=SUM(Q#:Q#)` | 12 | Total de sección (suma vertical de subtotales del propio Q) |
| `=+O#` | 4 | **No suma**: arrastra Diciembre. Son saldos de cierre (membresías del Club, filas 11–14) |
| `=+Q#-Q#` / `=+Q#+Q#…` | 12 | Aritmética de márgenes (p. ej. `=+Q65-Q78`) |
| `=IF(Q3=0,"",Q4/Q3)` | 1 | % de ocupación anual |

Las columnas mensuales D..O también contienen 12 `=SUM(...)` cada una: son las **filas** de subtotal (p. ej. fila 36 `INGRESOS TOTALES` = `=SUM(D23:D35)`), no columnas de agregación.

---

## 3. TABLA COMPLETA — LAS 210 COLUMNAS

Notas de lectura:
- **Ancho**: `ws.column_dimensions[letra].width`. Las columnas R..HA heredan 15.71 de un único registro `<col min="18" max="529">`.
- **Formato num. predominante**: el más frecuente entre las filas 22–1007 de esa columna.
- **Celdas con contenido**: valores o fórmulas no vacíos en toda la columna (filas 1–1046).
- Ninguna columna está oculta y **todas tienen `outlineLevel = 0`** (no hay agrupaciones/outline de columnas en esta hoja).

| # | Letra | Encab. r18 | Encab. r19 | Ancho | Oculta | Outline | Formato num. predominante (filas de datos) | Celdas con contenido | Rol |
|---|-------|-----------|-----------|-------|--------|---------|--------------------------------------------|----------------------|-----|
| 1 | A |  |  | 4.00 | no | 0 | `—` | 0 | Margen izquierdo (vacía) |
| 2 | B |  |  | 5.71 | no | 0 | `—` | 0 | Banda/indent izquierdo (vacía, con relleno) |
| 3 | C |  | DESCRIPCIÓN DE CUENTA | 44.00 | no | 0 | `General` | 861 | Etiqueta: DESCRIPCIÓN DE CUENTA |
| 4 | D | Enero | Presupuesto 2026 | 14.86 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 777 | Mes 1 (Enero) — origen '[1]Budget 2025W'!K |
| 5 | E | Febrero | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 777 | Mes 2 (Febrero) — origen '[1]Budget 2025W'!L |
| 6 | F | Marzo | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 777 | Mes 3 (Marzo) — origen '[1]Budget 2025W'!M |
| 7 | G | Abril | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 777 | Mes 4 (Abril) — origen '[1]Budget 2025W'!N |
| 8 | H | Mayo | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 783 | Mes 5 (Mayo) — origen '[1]Budget 2025W'!O |
| 9 | I | Junio | Presupuesto 2026 | 21.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 783 | Mes 6 (Junio) — origen '[1]Budget 2025W'!P |
| 10 | J | Julio | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 783 | Mes 7 (Julio) — origen '[1]Budget 2025W'!Q |
| 11 | K | Agosto | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 783 | Mes 8 (Agosto) — origen '[1]Budget 2025W'!R |
| 12 | L | Septiembre | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 783 | Mes 9 (Septiembre) — origen '[1]Budget 2025W'!S |
| 13 | M | Octubre | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 783 | Mes 10 (Octubre) — origen '[1]Budget 2025W'!T |
| 14 | N | Noviembre | Presupuesto 2026 | 22.71 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 784 | Mes 11 (Noviembre) — origen '[1]Budget 2025W'!U |
| 15 | O | Diciembre | Presupuesto 2026 | 21.43 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 784 | Mes 12 (Diciembre) — origen '[1]Budget 2025W'!V |
| 16 | P |  |  | 3.29 | no | 0 | `—` | 0 | SEPARADOR visual (gutter angosto, vacío) |
| 17 | Q | Total Año | Presupuesto 2026 | 28.57 | no | 0 | `"$"#,##0.00;[Red]\("$"#,##0.00\);""` | 774 | TOTAL AÑO (suma de los 12 meses) |
| 18 | R |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 19 | S |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 20 | T |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 21 | U |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 22 | V |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 23 | W |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 24 | X |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 25 | Y |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 26 | Z |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 27 | AA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 28 | AB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 29 | AC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 30 | AD |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 31 | AE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 32 | AF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 33 | AG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 34 | AH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 35 | AI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 36 | AJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 37 | AK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 38 | AL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 39 | AM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 40 | AN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 41 | AO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 42 | AP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 43 | AQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 44 | AR |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 45 | AS |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 46 | AT |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 47 | AU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 48 | AV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 49 | AW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 50 | AX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 51 | AY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 52 | AZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 53 | BA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 54 | BB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 55 | BC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 56 | BD |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 57 | BE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 58 | BF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 59 | BG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 60 | BH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 61 | BI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 62 | BJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 63 | BK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 64 | BL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 65 | BM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 66 | BN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 67 | BO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 68 | BP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 69 | BQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 70 | BR |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 71 | BS |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 72 | BT |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 73 | BU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 74 | BV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 75 | BW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 76 | BX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 77 | BY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 78 | BZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 79 | CA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 80 | CB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 81 | CC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 82 | CD |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 83 | CE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 84 | CF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 85 | CG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 86 | CH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 87 | CI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 88 | CJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 89 | CK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 90 | CL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 91 | CM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 92 | CN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 93 | CO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 94 | CP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 95 | CQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 96 | CR |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 97 | CS |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 98 | CT |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 99 | CU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 100 | CV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 101 | CW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 102 | CX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 103 | CY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 104 | CZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 105 | DA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 106 | DB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 107 | DC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 108 | DD |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 109 | DE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 110 | DF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 111 | DG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 112 | DH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 113 | DI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 114 | DJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 115 | DK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 116 | DL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 117 | DM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 118 | DN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 119 | DO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 120 | DP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 121 | DQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 122 | DR |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 123 | DS |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 124 | DT |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 125 | DU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 126 | DV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 127 | DW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 128 | DX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 129 | DY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 130 | DZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 131 | EA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 132 | EB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 133 | EC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 134 | ED |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 135 | EE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 136 | EF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 137 | EG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 138 | EH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 139 | EI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 140 | EJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 141 | EK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 142 | EL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 143 | EM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 144 | EN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 145 | EO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 146 | EP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 147 | EQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 148 | ER |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 149 | ES |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 150 | ET |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 151 | EU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 152 | EV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 153 | EW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 154 | EX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 155 | EY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 156 | EZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 157 | FA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 158 | FB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 159 | FC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 160 | FD |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 161 | FE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 162 | FF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 163 | FG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 164 | FH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 165 | FI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 166 | FJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 167 | FK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 168 | FL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 169 | FM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 170 | FN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 171 | FO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 172 | FP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 173 | FQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 174 | FR |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 175 | FS |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 176 | FT |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 177 | FU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 178 | FV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 179 | FW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 180 | FX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 181 | FY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 182 | FZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 183 | GA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 184 | GB |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 185 | GC |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 186 | GD |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 187 | GE |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 188 | GF |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 189 | GG |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 190 | GH |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 191 | GI |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 192 | GJ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 193 | GK |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 194 | GL |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 195 | GM |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 196 | GN |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 197 | GO |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 198 | GP |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 199 | GQ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 200 | GR |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 201 | GS |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 202 | GT |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 203 | GU |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 204 | GV |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 205 | GW |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 206 | GX |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 207 | GY |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 208 | GZ |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 209 | HA |  |  | 15.71 | no | 0 | `—` | 0 | Fuera de la tabla (vacía) |
| 210 | HB |  |  | 15.71 | no | 0 | `General` | 11 | Lista auxiliar de validación (meses en inglés) |

---

## 4. RAREZAS ENCONTRADAS

1. **El libro dice "Presupuesto 2026" pero la hoja origen se llama `Budget 2025W`.** Los 8 749 enlaces externos de D..Q apuntan a `'[1]Budget 2025W'!…` y 48 más a `'[1]P&L Detail Club'!…`. El destino `[1]` es:
   `G:\.shortcut-targets-by-id\…\AMARENA\BUDGET 2026\BUDGET 2026-AMA.xlsx`
   → **el origen es de AMARENA, no de CWL**, y el nombre de hoja quedó del año anterior. Cualquier validación de cifras contra "CWL" debe tener esto en cuenta.

2. **Mapeo de columnas origen→destino corrido:** `D..O` (Ene..Dic) leen `K..V` del origen, y `Q` lee `AP`. En el bloque de estadísticas (filas 3–8) el origen se corre a `O..V`, por eso **las filas 3 a 8 no tienen datos en D..G (Enero–Abril)**: las estadísticas empiezan en Mayo. Son las únicas 6 filas con ese hueco.

3. **La lista de validación está rota.** `D18:P18` tiene validación de lista contra `$HB$29:$HB$42`, y esa lista contiene: `January, March, April, (3 celdas vacías), May, June, July, August, September, October, November, December`. **Falta February**, sobran 3 blancos, y está **en inglés** mientras los encabezados reales están en español. Además la validación abarca la columna **P**, que es el separador vacío.

4. **Segunda validación huérfana:** `D1` (celda vacía, fuera del área de impresión) tiene una lista contra `$D$18:$O$18`. Resto de un selector que ya no se usa.

5. **La fila 18 tiene formato de número `mmm-yy` pero contiene texto** (`"Enero"`, `"Febrero"`…). Los encabezados son cadenas, no fechas: el formato no hace nada. Si en la app se guardan como fechas, el render cambia.

6. **Anchos inconsistentes entre meses:** D = 14.86, E–H = 22.71, I = 21.71, J–N = 22.71, O = 21.43, Q = 28.57. Enero es notablemente más angosto que el resto sin razón funcional. En la app conviene un ancho uniforme para los 12 meses.

7. **Formatos numéricos inconsistentes en la misma fila entre meses.** Conviven 5 formatos en las columnas de datos:
   - `"$"#,##0.00;[Red]\("$"#,##0.00\);""` (dominante, ~768–785 celdas/columna) — con tercera sección vacía: **los ceros se muestran en blanco**.
   - `"$"#,##0.00_);[Red]\("$"#,##0.00\)` (34–43 celdas)
   - `[$$-409]#,##0.00_);[Red]\([$$-409]#,##0.00\)` (11–20 celdas)
   - `"$"#,##0.00;[Red]"$"#,##0.00` (9–18 celdas) — negativos **sin** paréntesis, usado en filas de total como la 36
   - `#,##0;\(#,##0\);\-` (11 celdas) — **solo en D y E**; en F..O esas mismas filas llevan `[$$-409]…`. Son filas de conteo (unidades) formateadas como moneda en 10 de los 12 meses.

8. **Las filas de porcentaje están formateadas como moneda.** `% de Ingresos del Depto.` (294, 334, 479, 490, 523, 534) y `% Utilidad` (336, 492, 536) calculan un ratio con `=IFERROR(D293/D259,"")` pero llevan formato `"$"#,##0.00…`. En Excel se ven como `$0.35` en vez de `35%`. **Es un bug de formato del original** — al reconstruir hay que decidir si se replica o se corrige (recomendado: corregir a porcentaje).

9. **Espacios en blanco como valor.** 28 filas tienen en D..O (y a veces Q) la cadena literal `" "` (un espacio) en lugar de estar vacías: filas 35, 37, 39, 51–54, 66–70, 77, 79, 156–158, 162–164, 166–168, 185, 190–192, 223–226, 228. Son separadores de sección tecleados a mano. **Cualquier parser que haga `float(celda)` va a reventar en esas filas** — hay que tratarlas como vacías.

10. **Restos de formato fuera de la tabla:** las columnas R..Y tienen celdas con estilo (sin valor) en las filas 19, 20, 36, 38, 50, 53 y 55–59. Es desbordamiento de formato al copiar filas; no aporta nada al reporte pero explica por qué Excel "ve" contenido más allá de Q.

11. **Registros de ancho de columna fantasma** que inflan el rango usado: `<col min=18 max=529 width=15.71>`, `<col min=530 max=16115 width=2.29 bestFit>` y `<col min=16116 max=16384 width=11.43>`. Alguien aplicó ancho a la hoja entera en algún momento.

12. **Sin cuadrícula, zoom al 71 %, pestaña con color de tema 9.** `showGridLines = False` — el reporte se lee solo con sus propios bordes y rellenos. Al reconstruir en web, las líneas de la tabla deben venir de los bordes definidos por fila, no de un grid genérico.

13. **7 libros externos referenciados** en total (`[1]`..`[7]`) y ~70 nombres definidos rotos que apuntan a `[2]Assumptions!…`, `#REF!`, discos `E:`/`F:` y una ruta de SharePoint. Solo `[1]` se usa en las fórmulas de esta hoja; el resto es equipaje heredado de plantillas anteriores (incluye un `A_impresión_IM = #REF!`).

14. **No hay formato condicional, ni autofiltro, ni paneles congelados, ni columnas ocultas, ni agrupaciones.** Todo el color del reporte es formato estático fila por fila.
