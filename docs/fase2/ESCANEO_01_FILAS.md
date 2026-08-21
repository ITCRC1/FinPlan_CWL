# ESCANEO 01 — Estructura de filas

**Archivo:** `C:\FinPlan_CWL\docs\fase2\PL_DETALLADO_FORMATO.xlsx`  
**Hoja:** `P&L Full Detail` (única)  
**Rango con contenido:** filas 1–1007 · columnas A–HB (210)  
**Generado con:** `openpyxl` (`data_only=False`, es decir se leyeron fórmulas, no valores)

> Este documento es la **especificación de filas** para reconstruir el reporte al 100 %.
> No resume: lista las 1007 filas, incluidas las vacías (son separadores visuales del formato).

---

## 1. Resumen ejecutivo

### 1.1 Geometría real de la hoja

| Concepto | Valor |
|---|---|
| Filas con contenido | 1–1007 (`ws.max_row` = 1046, pero 1008–1046 están 100 % vacías) |
| Columna de etiquetas | **C**, siempre. `A` y `B` están vacías en las 1007 filas. |
| Columnas de datos | **D…O** = Enero…Diciembre (12 meses) |
| Columna de total | **Q** = `Total Año` |
| Columna P | **espaciadora**, vacía en toda la hoja (separa Diciembre del Total) |
| Columnas R…HA | vacías |
| Columna HB | basura residual: nombres de mes en inglés en filas 29–42 (ver §4) |
| Celdas combinadas | 1 sola: `C2:Q2` (título) |
| Paneles congelados | ninguno (`freeze_panes = None`) |
| `outlineLevel` | **0 en las 1007 filas** — no hay agrupamientos de Excel |
| Filas ocultas | **265** (ver §4.1) |

### 1.2 Conteos

| Métrica | Cantidad |
|---|---:|
| Filas totales inventariadas | 1007 |
| Filas con etiqueta en C | 862 |
| Filas sin etiqueta (separadoras/vacías) | 145 |
| — `línea de detalle` | 670 |
| — `fila en blanco` | 73 |
| — `encabezado de sub-bloque` | 57 |
| — `subtotal de sub-bloque` | 57 |
| — `separadora (celdas con espacio)` | 47 |
| — `total` | 18 |
| — `ratio / % (sin etiqueta)` | 18 |
| — `encabezado de departamento (banner)` | 15 |
| — `total de departamento` | 14 |
| — `KPI` | 10 |
| — `ratio / % (KPI)` | 9 |
| — `separadora (banda gris)` | 7 |
| — `encabezado de sección` | 5 |
| — `subtotal` | 3 |
| — `encabezado de columnas` | 2 |
| — `título del reporte` | 1 |
| — `encabezado de grupo (banner)` | 1 |

**Bloques y secciones:**

| Elemento | Cantidad |
|---|---:|
| Zonas macro | 8 |
| Banners de departamento / grupo (nivel 0) | 16 |
| Encabezados de sub-bloque (nivel 1) | 57 |
| Subtotales de sub-bloque (nivel 2) | 57 |
| Totales de departamento (banda negra) | 14 |
| Filas de ratio / % | 27 |
| Líneas de detalle | 670 |

### 1.3 ¿Hay patrón repetido? **Sí, y es fuerte.**

El reporte **no** es una lista plana de 1007 filas distintas. Es la aplicación repetida de
una sola plantilla de departamento. Se puede generar con un motor.

**Plantilla de departamento** (se repite 16 veces, filas 154–943):

```
[banner]      NOMBRE DEL DEPARTAMENTO            fill FF404040, letra roja negrita
  [sub]       INGRESOS                           fill FFD9E1F2   (opcional)
    detalle   1..n líneas de ingreso
  [subtotal]  Total Ingresos <Depto>             fill FFBDD7EE, borde doble
  [sub]       COSTO DE VENTAS                    fill FFD9E1F2   (opcional)
    detalle   1..n líneas de costo
  [subtotal]  Total Costo de Ventas              fill FFBDD7EE
  [sub]       NÓMINA                             fill FFD9E1F2
    detalle   LOS MISMOS 16 CONCEPTOS SIEMPRE    <- ver abajo
  [subtotal]  TOTAL NÓMINA                       fill FFBDD7EE
  [ratio]     % de Ingresos del Depto.           fill FFF2F2F2, itálica gris (a veces sin etiqueta)
  [sub]       Gastos Operativos                  fill FFD9E1F2
    detalle   1..n líneas de gasto (catálogo variable por depto)
  [subtotal]  TOTAL GASTOS OPERATIVOS            fill FFBDD7EE
  [ratio]     % de Ingresos del Depto.
  [total]     UTILIDAD NETA <DEPTO>              fill FF262626, letra blanca
  [ratio]     % Utilidad
```

**El sub-bloque NÓMINA es idéntico en los 13 departamentos que lo tienen.** 
Siempre los mismos 16 conceptos, en el mismo orden:

1. Salarios y Sueldos
2. Horas Extra
3. Día Libre
4. Feriado Trabajado
5. Comisiones
6. Seguro Social (CCSS)
7. Aguinaldo
8. Póliza de Riesgos del Trabajo
9. Provisión de Vacaciones
10. Vacaciones Disfrutadas
11. Cafetería
12. Preaviso y Cesantía
13. Bono de Incentivo
14. Vivienda
15. Transporte de Empleados
16. Otros Beneficios a Empleados

Única excepción: **Tours** (fila 430) agrega un 17.º concepto, `Mano de Obra por Contrato`.

Ocurrencias del bloque NÓMINA:

| Encabezado | Detalle | `TOTAL NÓMINA` | N.º conceptos | ¿16 estándar? |
|---:|---|---:|---:|---|
| 168 | 169–184 | 186 | 16 | sí |
| 276 | 277–292 | 293 | 16 | sí |
| 351 | 352–367 | 368 | 16 | sí |
| 413 | 414–430 | 431 | 17 | sí + `Mano de Obra por Contrato` |
| 461 | 462–477 | 478 | 16 | sí |
| 505 | 506–521 | 522 | 16 | sí |
| 547 | 548–563 | 564 | 16 | sí |
| 606 | 607–622 | 623 | 16 | sí |
| 666 | 667–682 | 683 | 16 | sí |
| 723 | 724–739 | 740 | 16 | sí |
| 775 | 776–791 | 792 | 16 | sí |
| 829 | 830–845 | 846 | 16 | sí |
| 910 | 911–926 | 927 | 16 | sí |

**Consecuencia para la app:** el motor sólo necesita, por departamento:
el nombre, la lista de líneas de ingreso, la de costo de ventas y la de gastos operativos.
La nómina (16 filas), los subtotales, los ratios y los separadores se generan solos.
Eso reduce ~790 filas de detalle a ~462 definiciones de catálogo.

---

## 2. Árbol de secciones

Notación: `fila` · etiqueta · *(dónde está su total)*

### Z0 · Título — filas 1–2

- `2` Presupuesto 2026 Consolidado _(título del reporte)_

### Z1 · KPIs y estadísticas — filas 3–17

- `3` Habitaciones Disponibles Totales _(KPI)_
- `4` Habitaciones Ocupadas Totales _(KPI)_
- `5` Habitaciones por Día _(KPI)_ _(OCULTO)_
- `6` Huéspedes Totales _(KPI)_
- `7` % de Ocupación _(KPI)_
- `8` Tarifa Promedio Diaria (solo habitación) _(KPI)_
- `11` Total Membresias _(KPI)_
- `12` Membresías Condicionados _(KPI)_
- `13` Membresias Pagando _(KPI)_
- `14` Membresias En acuerdo de pago _(KPI)_

### Z2 · Encabezado de columnas — filas 18–20

- `18` Enero _(encabezado de columnas)_
- `19` DESCRIPCIÓN DE CUENTA _(encabezado de columnas)_

### Z3 · RESUMEN P&L consolidado — filas 21–152

- `22` INGRESOS _(encabezado de sección)_
- `36` INGRESOS TOTALES _(total)_
- `38` Gastos Operativos _(encabezado de sección)_
- `50` Total Gastos Operativos _(total)_
- `53` Utilidad Operativa _(encabezado de sección)_
- `65` UTILIDAD OPERATIVA _(total)_
- `68` GASTOS GENERALES (OVERHEAD) _(encabezado de sección)_
- `78` TOTAL GASTOS GENERALES _(total)_
- `80` UTILIDAD OPERATIVA BRUTA TOTAL (GOP) _(total)_
- `85` TOTAL ALQUILER Y HONORARIOS DE ADMINISTRACIÓN _(total)_
- `89` SEGURO DE PROPIEDAD _(total)_
- `93` TOTAL OTROS GASTOS _(total)_
- `98` TOTAL GASTOS NO OPERATIVOS _(total)_
- `100` EBITDA ANTES DE CAPITAL _(total)_
- `107` GASTO DE CAPITAL _(total)_
- `109` EBITDA DESPUÉS DE CAPITAL _(total)_
- `114` GASTOS FINANCIEROS _(total)_
- `119` TOTAL DEPRECIACIONES _(total)_
- `122` UTILIDAD ANTES DE IMPUESTOS _(total)_
- `127` UTILIDAD NETA _(total)_
- `132` UTILIDAD NETA _(total)_
- `135` Resumen _(encabezado de sección)_
- `140` UTILIDAD NETA _(total)_

### Z4 · Departamentos operativos (detalle) — filas 153–662

- **`154` DEPARTAMENTO DE HABITACIONES** 
  - `158` **Ingresos por Habitaciones** → detalle 159–164, total en `165` “Total Ingresos por Habitaciones”
  - `168` **NÓMINA** → detalle 169–185, total en `186` “TOTAL NÓMINA”
  - `192` **Gastos Operativos** → detalle 193–226, total en `227` “TOTAL GASTOS OPERATIVOS”
  - `230` **UTILIDAD NETA HABITACIONES** _(total de departamento)_
- **`233` DEPARTAMENTO DE ALIMENTOS Y BEBIDAS** 
  - `234` **INGRESOS** → detalle 235–258, total en `259` “Total Ingresos A&B” _(OCULTO)_
  - `260` **COSTO DE VENTAS** → detalle 261–274, total en `275` “Total Costo de Ventas” _(OCULTO)_
  - `276` **NÓMINA** → detalle 277–292, total en `293` “TOTAL NÓMINA” _(OCULTO)_
  - `295` **Gastos Operativos** → detalle 296–332, total en `333` “TOTAL GASTOS OPERATIVOS”
  - `335` **UTILIDAD NETA A&B** _(total de departamento)_
- **`338` DEPARTAMENTO DE SPA** 
  - `339` **INGRESOS** → detalle 340–345, total en `346` “Total Ingresos de Spa”
  - `347` **COSTO DE VENTAS** → detalle 348–349, total en `350` “Total Costo de Ventas”
  - `351` **NÓMINA** → detalle 352–367, total en `368` “TOTAL NÓMINA”
  - `370` **Gastos Operativos** → detalle 371–397, total en `398` “TOTAL GASTOS OPERATIVOS”
  - `400` **UTILIDAD NETA SPA** _(total de departamento)_
- **`402` DEPARTAMENTO DE TOURS** 
  - `403` **INGRESOS** → detalle 404–407, total en `408` “Total Ingresos por Tours”
  - `409` **COSTO DE VENTAS** → detalle 410–411, total en `412` “Total Costo de Ventas”
  - `413` **NÓMINA** → detalle 414–430, total en `431` “TOTAL NÓMINA”
  - `433` **Gastos Operativos** → detalle 434–441, total en `442` “TOTAL GASTOS OPERATIVOS”
  - `444` **UTILIDAD NETA TOURS** _(total de departamento)_
- **`446` DEPARTAMENTO DE TIENDA DE REGALOS** _(OCULTO)_
  - `447` **INGRESOS** → detalle 448–451, total en `452` “Total Ingresos de Tienda” _(OCULTO)_
  - `453` **COSTO DE VENTAS** → detalle 454–459, total en `460` “Total Costo de Ventas” _(OCULTO)_
  - `461` **NÓMINA** → detalle 462–477, total en `478` “TOTAL NÓMINA” _(OCULTO)_
  - `480` **Gastos Operativos** → detalle 481–488, total en `489` “TOTAL GASTOS OPERATIVOS” _(OCULTO)_
  - `491` **UTILIDAD NETA TIENDA** _(total de departamento)_ _(OCULTO)_
- **`493` DEPARTAMENTO DE BAR PRIVADO** _(OCULTO)_
  - `494` **INGRESOS** → detalle 495–498, total en `499` “Total Ingresos de Bar Privado” _(OCULTO)_
  - `500` **COSTO DE VENTAS** → detalle 501–503, total en `504` “Total Costo de Ventas” _(OCULTO)_
  - `505` **NÓMINA** → detalle 506–521, total en `522` “TOTAL NÓMINA” _(OCULTO)_
  - `524` **Gastos Operativos** → detalle 525–532, total en `533` “TOTAL GASTOS OPERATIVOS” _(OCULTO)_
  - `535` **UTILIDAD NETA BAR PRIVADO** _(total de departamento)_ _(OCULTO)_
- **`537` DEPARTAMENTO CLUB MADRESAL** 
  - `538` **INGRESOS** → detalle 539–541, total en `542` “Total Ingresos Club Madresal”
  - `543` **COSTO DE VENTAS** → detalle 544–545, total en `546` “Total Costo de Ventas”
  - `547` **NÓMINA** → detalle 548–563, total en `564` “TOTAL NÓMINA”
  - `566` **Gastos Operativos** → detalle 567–592, total en `593` “TOTAL GASTOS OPERATIVOS”
  - `595` **UTILIDAD NETA CLUB MADRESAL** _(total de departamento)_
- **`597` DEPARTAMENTO DE LAVANDERÍA** 
  - `598` **INGRESOS** → detalle 599–601, total en `602` “Total Ingresos de Lavandería”
  - `603` **COSTO DE VENTAS** → detalle 604–604, total en `605` “Total Costo de Ventas”
  - `606` **NÓMINA** → detalle 607–622, total en `623` “TOTAL NÓMINA”
  - `625` **Gastos Operativos** → detalle 626–643, total en `644` “TOTAL GASTOS OPERATIVOS”
  - `646` **UTILIDAD NETA LAVANDERÍA** _(total de departamento)_
- **`648` DEPARTAMENTO DE INGRESOS VARIOS** _(OCULTO)_
  - `649` **INGRESOS** → detalle 650–659, total en `660` “Total Ingresos Varios” _(OCULTO)_
  - `661` **UTILIDAD NETA INGRESOS VARIOS** _(total de departamento)_

### Z5 · Departamentos de gastos generales (overhead) — filas 663–899

- **`664` DEPARTAMENTOS DE GASTOS GENERALES (OVERHEAD)** 
- **`665` ADMINISTRACIÓN Y GENERAL** 
  - `666` **NÓMINA** → detalle 667–682, total en `683` “TOTAL NÓMINA”
  - `684` **Gastos Operativos** → detalle 685–719, total en `720` “TOTAL GASTOS OPERATIVOS”
  - `721` **TOTAL ADMINISTRACIÓN Y GENERAL** _(total de departamento)_
- **`722` VENTAS Y MERCADEO** 
  - `723` **NÓMINA** → detalle 724–739, total en `740` “TOTAL NÓMINA” _(OCULTO)_
  - `741` **Gastos Operativos** → detalle 742–771, total en `772` “TOTAL GASTOS OPERATIVOS”
  - `773` **TOTAL VENTAS Y MERCADEO** _(total de departamento)_
- **`774` MANTENIMIENTO** 
  - `775` **NÓMINA** → detalle 776–791, total en `792` “TOTAL NÓMINA”
  - `793` **Gastos Operativos** → detalle 794–825, total en `826` “TOTAL GASTOS OPERATIVOS”
  - `827` **TOTAL MANTENIMIENTO** _(total de departamento)_
- **`828` SISTEMAS DE INFORMACIÓN** _(OCULTO)_
  - `829` **NÓMINA** → detalle 830–845, total en `846` “TOTAL NÓMINA” _(OCULTO)_
  - `847` **Costo de Servicios** → detalle 848–852, total en `853` “Total Costo de Servicios” _(OCULTO)_
  - `854` **Gastos Operativos** → detalle 855–884, total en `885` “TOTAL GASTOS OPERATIVOS” _(OCULTO)_
  - `886` **TOTAL SISTEMAS DE INFORMACIÓN** _(total de departamento)_ _(OCULTO)_
- **`887` SERVICIOS PÚBLICOS** 
  - `888` **Gastos Operativos** → detalle 889–898, total en `899` “TOTAL SERVICIOS PÚBLICOS”

### Z6 · Área Recreativa (departamento operativo, ubicado tras overhead) — filas 900–943

- **`900` DEPARTAMENTO ÁREA RECREATIVA** 
  - `901` **INGRESOS** → detalle 902–904, total en `905` “Total Ingresos Área Recreativa”
  - `906` **COSTO DE VENTAS** → detalle 907–908, total en `909` “Total Costo de Ventas”
  - `910` **NÓMINA** → detalle 911–926, total en `927` “TOTAL NÓMINA”
  - `929` **Gastos Operativos** → detalle 930–937, total en `938` “TOTAL GASTOS OPERATIVOS”
  - `942` **UTILIDAD NETA ÁREA RECREATIVA** _(total de departamento)_

### Z7 · Gastos de propiedad / bajo GOP — filas 944–1007

- `946` **GASTOS DE PROPIEDAD** _(encabezado sin total propio)_
- `948` **ALQUILER** → detalle 949–950, total en `951` “TOTAL ALQUILER”
- `953` **HONORARIOS DE ADMINISTRACIÓN** → detalle 954–955, total en `956` “TOTAL HONORARIOS DE ADMINISTRACIÓN (5%) Y REGALÍAS”
- `958` **SEGURO DE PROPIEDAD** → detalle 959–964, total en `965` “TOTAL SEGURO DE PROPIEDAD”
- `967` **INTERESES SOBRE PRÉSTAMOS** → detalle 968–969, total en `970` “TOTAL INTERESES SOBRE PRÉSTAMOS”
- `972` **CARGOS BANCARIOS Y COMISIONES** → detalle 973–974, total en `975` “TOTAL CARGOS BANCARIOS Y COMISIONES”
- `977` **GANANCIA / PÉRDIDA CAMBIARIA** → detalle 978–979, total en `980` “TOTAL GANANCIA / PÉRDIDA CAMBIARIA”
- `982` **RESERVA / GASTO DE CAPITAL** → detalle 983–984, total en `985` “TOTAL GASTO DE CAPITAL”
- `987` **DEPRECIACIÓN** → detalle 988–996, total en `997` “TOTAL DEPRECIACIÓN”
- `999` **MULTAS Y OTROS GASTOS NO DEDUCIBLES** → detalle 1000–1002, total en `1003` “TOTAL MULTAS Y OTROS NO DEDUCIBLES”
- `1005` **IMPUESTO SOBRE LA RENTA** → detalle 1006–1006, total en `1007` “TOTAL IMPUESTO SOBRE LA RENTA”

---

## 3. Inventario completo — las 1007 filas

**Columnas de la tabla**

- **Fila** — número de fila en Excel.
- **Etiqueta** — texto en la columna C (vacío = fila sin etiqueta).
- **Niv** — nivel jerárquico inferido: `0` banner · `1` encabezado/total de sección ·
  `2` subtotal de sub-bloque · `3` línea de detalle · `4` fila de ratio · `—` separadora.
- **Tipo** — rol de la fila.
- **Datos** — `ENLACE` = fórmula `=+'[1]Budget 2025W'!…` a libro externo · `SUM` = suma interna ·
  `CALC` = fórmula aritmética propia · `(sólo etiqueta)` · `(espacios)` = celdas con `" "` literal ·
  `(vacía)`.
- **Cols** — columnas de datos con fórmula (`D:O,Q` = los 12 meses + Total Año).
- **Ocu** — `SÍ` si `row_dimensions[r].hidden`.
- **Alto** — altura de fila cuando difiere del default (default = `None`/15).
- **OL** — `outlineLevel` (siempre 0 en este archivo).

| Fila | Etiqueta | Niv | Tipo | Datos | Cols | Ocu | Alto | OL | Notas |
|---:|---|:---:|---|---|---|:---:|---:|:--:|---|
| 1 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 2 | Presupuesto 2026 Consolidado | 0 | título del reporte | (sólo etiqueta) |  |  | 48.75 | 0 | letra roja |
| 3 | Habitaciones Disponibles Totales | 1 | KPI | SUM | H:O,Q |  | 20.1 | 0 | banda KPI · **sólo 9 fórmulas** |
| 4 | Habitaciones Ocupadas Totales | 1 | KPI | SUM | H:O,Q |  | 20.1 | 0 | banda KPI · **sólo 9 fórmulas** |
| 5 | Habitaciones por Día | 1 | KPI | SUM | H:O,Q | SÍ | 20.1 | 0 | banda KPI · **sólo 9 fórmulas** |
| 6 | Huéspedes Totales | 1 | KPI | SUM | H:O,Q |  | 20.1 | 0 | banda KPI · **sólo 9 fórmulas** |
| 7 | % de Ocupación | 1 | KPI | CALC | H:O,Q |  | 20.1 | 0 | banda KPI · **sólo 9 fórmulas** · formato % |
| 8 | Tarifa Promedio Diaria (solo habitación) | 1 | KPI | CALC | H:O,Q |  | 20.1 | 0 | banda KPI · **sólo 9 fórmulas** |
| 9 |  | — | fila en blanco | (vacía) |  |  | 20.1 | 0 | banda KPI |
| 10 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 11 | Total Membresias | 1 | KPI | ENLACE | D:O,Q |  | 20.25 | 0 | banda KPI · fuente Segoe UI 14 |
| 12 | Membresías Condicionados | 1 | KPI | ENLACE | D:O,Q |  | 20.25 | 0 | banda KPI · fuente Segoe UI 14 |
| 13 | Membresias Pagando | 1 | KPI | ENLACE | D:O,Q |  | 20.25 | 0 | banda KPI · fuente Segoe UI 14 |
| 14 | Membresias En acuerdo de pago | 1 | KPI | ENLACE | D:O,Q |  | 20.25 | 0 | banda KPI · fuente Segoe UI 14 |
| 15 |  | — | fila en blanco | (vacía) |  |  | 20.25 | 0 | banda KPI · fuente Segoe UI 14 |
| 16 |  | — | fila en blanco | (vacía) |  |  | 20.25 | 0 | banda KPI · fuente Segoe UI 14 |
| 17 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 18 | Enero | 0 | encabezado de columnas | CONSTANTE |  |  | 16.5 | 0 |  |
| 19 | DESCRIPCIÓN DE CUENTA | 0 | encabezado de columnas | CONSTANTE |  |  | 16.5 | 0 | banda resumen |
| 20 |  | — | fila en blanco | (vacía) |  |  | 16.5 | 0 | banda resumen |
| 21 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 22 | INGRESOS | 1 | encabezado de sección | (sólo etiqueta) |  |  | 15.75 | 0 | banda resumen |
| 23 | Habitaciones | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 24 | Alimentos y Bebidas | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 25 | Spa | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 26 | Tours | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 27 | Tienda de Regalos | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 28 | Club Madresal | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 29 | Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 30 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 31 | Ingresos Varios | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 32 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 33 |  | — | fila en blanco | (vacía) |  | SÍ | 15.75 | 0 |  |
| 34 |  | — | fila en blanco | (vacía) |  | SÍ | 15.75 | 0 |  |
| 35 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 36 | INGRESOS TOTALES | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 37 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 38 | Gastos Operativos | 1 | encabezado de sección | (espacios) |  |  | 15.75 | 0 | banda resumen |
| 39 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 40 | Habitaciones | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 41 | Alimentos y Bebidas | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 42 | Spa | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 43 | Tours | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 44 | Tienda de Regalos | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 45 | Club Madresal | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 46 | Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 47 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.6 | 0 |  |
| 48 | Ingresos Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 49 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 50 | Total Gastos Operativos | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen · **rangos SUM inconsistentes** |
| 51 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 52 |  | — | separadora (celdas con espacio) | (espacios) |  | SÍ |  | 0 |  |
| 53 | Utilidad Operativa | 1 | encabezado de sección | (espacios) |  |  | 15.75 | 0 | banda resumen |
| 54 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 55 | Habitaciones | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 56 | Alimentos y Bebidas | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 57 | Spa | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 58 | Tours | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 59 | Tienda de Regalos | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 60 | Club Madresal | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 | **resaltado manual** |
| 61 | Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  | 15 | 0 |  |
| 62 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 63 | Ingresos Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 64 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 65 | UTILIDAD OPERATIVA | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen · **rangos SUM inconsistentes** |
| 66 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 67 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 68 | GASTOS GENERALES (OVERHEAD) | 1 | encabezado de sección | (espacios) |  |  | 15.75 | 0 | banda resumen |
| 69 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 70 |  | — | separadora (celdas con espacio) | (espacios) |  | SÍ | 15.75 | 0 |  |
| 71 | Administración | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 72 | Ventas y Mercadeo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 73 | Mantenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 74 | Sistemas de Información | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 75 | Servicios Públicos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 76 | Área Recreativa | 3 | línea de detalle | CALC | D:O,Q |  |  | 0 |  |
| 77 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 16.5 | 0 |  |
| 78 | TOTAL GASTOS GENERALES | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen · **rangos SUM inconsistentes** |
| 79 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 12 | 0 |  |
| 80 | UTILIDAD OPERATIVA BRUTA TOTAL (GOP) | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 81 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 82 | Alquiler | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 83 | Honorarios de Administración (5%) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 84 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 85 | TOTAL ALQUILER Y HONORARIOS DE ADMINISTRACIÓN | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 86 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 87 | Seguro de Propiedad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 88 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 89 | SEGURO DE PROPIEDAD | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 90 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 91 | Otros Gastos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 92 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 93 | TOTAL OTROS GASTOS | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 94 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 95 |  | — | fila en blanco | (vacía) |  | SÍ | 15.75 | 0 |  |
| 96 |  | — | separadora (celdas con espacio) | (espacios) |  | SÍ | 15.75 | 0 |  |
| 97 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 16.5 | 0 |  |
| 98 | TOTAL GASTOS NO OPERATIVOS | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 99 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 16.5 | 0 |  |
| 100 | EBITDA ANTES DE CAPITAL | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 101 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 102 |  | — | fila en blanco | (vacía) |  | SÍ | 15.75 | 0 |  |
| 103 |  | — | fila en blanco | (vacía) |  | SÍ | 15.75 | 0 |  |
| 104 | Reserva de Capital | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 105 | Mejoras Mayores | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 106 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 107 | GASTO DE CAPITAL | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 108 |  | — | fila en blanco | (vacía) |  |  | 16.5 | 0 |  |
| 109 | EBITDA DESPUÉS DE CAPITAL | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 110 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 111 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 112 | Pérdida Financiera | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 113 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 114 | GASTOS FINANCIEROS | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 115 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 116 | Depreciación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | **resaltado manual** |
| 117 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 118 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 119 | TOTAL DEPRECIACIONES | 1 | total | SUM | D:O,Q |  | 16.5 | 0 | banda resumen |
| 120 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 121 |  | — | separadora (celdas con espacio) | (espacios) |  | SÍ | 15.75 | 0 |  |
| 122 | UTILIDAD ANTES DE IMPUESTOS | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 123 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 124 | Impuesto sobre la Renta (30%) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 125 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 126 |  | — | separadora (celdas con espacio) | (espacios) |  | SÍ | 15.75 | 0 |  |
| 127 | UTILIDAD NETA | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 128 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 129 | Ingresos totales | 2 | subtotal | CALC | D:O,Q |  | 15.75 | 0 |  |
| 130 | Total gastos operativos | 2 | subtotal | CALC | D:O,Q |  | 20.45 | 0 |  |
| 131 | Gastos de la Propiedad | 2 | subtotal | CALC | D:O,Q |  | 16.5 | 0 |  |
| 132 | UTILIDAD NETA | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 133 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 134 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 135 | Resumen | 1 | encabezado de sección | (sólo etiqueta) |  |  | 16.5 | 0 |  |
| 136 | Total Nómina y Beneficios | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 137 | Total Gastos Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 138 | Costo Total | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 139 | Total Gastos de Propiedad | 3 | línea de detalle | CALC | D:O,Q |  | 15.75 | 0 |  |
| 140 | UTILIDAD NETA | 1 | total | CALC | D:O,Q |  | 16.5 | 0 | banda resumen |
| 141 | Variación 0 | 3 | línea de detalle | CALC | D:O,Q | SÍ |  | 0 |  |
| 142 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 143 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 144 | Gastos de propiedad | 3 | línea de detalle | CALC | D:O,Q | SÍ |  | 0 |  |
| 145 | Gastos después de EBITDA | 3 | línea de detalle | CALC | D:O,Q | SÍ |  | 0 |  |
| 146 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 147 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 148 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 149 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 150 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 151 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 152 |  | — | fila en blanco | (vacía) |  | SÍ |  | 0 |  |
| 153 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 154 | DEPARTAMENTO DE HABITACIONES | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 16.5 | 0 | banner depto · letra roja |
| 155 |  | — | separadora (banda gris) | (vacía) |  |  | 3.95 | 0 | banda gris separadora |
| 156 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 157 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 158 | Ingresos por Habitaciones | 1 | encabezado de sub-bloque | (espacios) |  |  | 15.75 | 0 | banda encabezado |
| 159 | Cancelaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 160 | No Show | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 161 | Habitaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 162 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 163 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 164 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 165 | Total Ingresos por Habitaciones | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 166 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 167 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 168 | NÓMINA | 1 | encabezado de sub-bloque | (espacios) |  |  | 15.75 | 0 | banda encabezado |
| 169 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 170 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 171 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 172 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 173 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 174 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 175 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 176 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 177 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 178 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 179 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 180 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 181 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 182 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 183 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 184 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 185 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 186 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 187 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 188 |  | — | separadora (banda gris) | (vacía) |  |  | 3.95 | 0 | banda gris separadora |
| 189 |  | — | separadora (banda gris) | (vacía) |  |  | 3.95 | 0 | banda gris separadora |
| 190 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 191 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 192 | Gastos Operativos | 1 | encabezado de sub-bloque | (espacios) |  |  | 15.75 | 0 | banda encabezado |
| 193 | Suministros de Limpieza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 194 | Servicios de Clúster | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 195 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 196 | Comisiones y Honorarios—Grupos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 197 | Alimentos y Bebidas de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 198 | Entretenimiento en Habitación de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 199 | Servicios y Regalos de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 200 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 201 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 202 | Decoraciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 203 | Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 204 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 205 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 206 | Reubicación de Huéspedes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 207 | Suministros para Huéspedes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 208 | Transporte de Huéspedes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 209 | Lavandería y Limpieza en Seco | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 210 | Licencias y Permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 211 | Linen | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 212 | Gastos Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 213 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 214 | Envios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 215 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 216 | Reservaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 217 | Honorarios de Regalía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 218 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 219 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 220 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 221 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 222 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 223 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 224 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 225 |  | — | separadora (celdas con espacio) | (espacios) |  |  |  | 0 |  |
| 226 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 227 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 228 |  | — | separadora (celdas con espacio) | (espacios) |  |  | 15.75 | 0 |  |
| 229 |  | — | separadora (banda gris) | (vacía) |  |  | 3.95 | 0 | banda gris separadora |
| 230 | UTILIDAD NETA HABITACIONES | 1 | total de departamento | CALC | D:O,Q |  | 17.25 | 0 | banda negra |
| 231 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 232 |  | — | separadora (banda gris) | (vacía) |  |  | 3.95 | 0 | banda gris separadora |
| 233 | DEPARTAMENTO DE ALIMENTOS Y BEBIDAS | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 17.25 | 0 | banner depto · letra roja |
| 234 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 15.75 | 0 | banda encabezado |
| 235 | Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 236 | Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 237 | Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 238 | Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 239 | Bebida sin Alcohol | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 240 | Bebida sin Alcohol | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 241 | Bebida sin Alcohol | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 242 | Bebida sin Alcohol | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 243 | Cerveza | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 244 | Cerveza | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 245 | Cerveza | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 246 | Cerveza | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 247 | Licor | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 248 | Licor | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 249 | Licor | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 250 | Licor | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 251 | Vino | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 252 | Vino | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 253 | Vino | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 254 | Vino | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 255 | A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 256 | A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 257 | A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 258 | A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 259 | Total Ingresos A&B | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 260 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 15.75 | 0 | banda encabezado |
| 261 | Costo de Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 262 | Traslado de Bar a Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 263 | Flete sobre Alimentos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 264 | Costo de Bebidas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 265 | Costo de Licor | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 266 | Costo de Vino | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 267 | Costo de Cerveza | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 268 | Costo de Otras Bebidas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 269 | Traslado de Alimentos a Bar | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 270 | Costo A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 271 | Costo A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 272 | Costo A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 273 | Costo A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 274 | Costo A&B Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 275 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 276 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 15.75 | 0 | banda encabezado |
| 277 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 278 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 279 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 280 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 281 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 282 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 283 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 284 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 285 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 286 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 287 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 288 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 289 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 290 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 291 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 292 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 293 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 16.5 | 0 | banda subtotal |
| 294 | % de Ingresos del Depto. | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 295 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 296 | Gastos de Banquetes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 297 | Vajilla (Loza) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 298 | Suministros de Limpieza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 299 | Servicios de Clúster | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 300 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 301 | Servicios y Regalos de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 302 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 303 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 304 | Decoraciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 305 | Suministros de Lavavajillas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 306 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 307 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 308 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 309 | Cubería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 310 | Cristalería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 311 | Hielo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 312 | Combustible de Cocina | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 313 | Utensilios Menores de Cocina | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 314 | Lavandería y Limpieza en Seco | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 315 | Licencias y Permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 316 | Lencería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 317 | Honorarios de Administración | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 318 | Menús y Cartas de Bebidas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 319 | Desayunos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | letra roja |
| 320 | Música y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 321 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 322 | Papel y Plásticos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 323 | Franqueo y Mensajería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 324 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 325 | Reservaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 326 | Honorarios de Regalía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 327 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 328 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 329 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 330 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 331 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 332 | Utensilios | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 333 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 334 | % de Ingresos del Depto. | 4 | ratio / % (KPI) | CALC | D:O |  | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 335 | UTILIDAD NETA A&B | 1 | total de departamento | CALC | D:O,Q |  | 16.5 | 0 | banda negra |
| 336 | % Utilidad | 4 | ratio / % (KPI) | CALC | D:O |  | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 337 |  | — | separadora (banda gris) | (vacía) |  |  | 3.75 | 0 | banda gris separadora |
| 338 | DEPARTAMENTO DE SPA | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 16.5 | 0 | banner depto · letra roja |
| 339 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 340 | Masajes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 341 | Ingresos de Tratamientos Corporales | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 342 | Ingresos de Belleza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 343 | Tienda de Spa (Retail) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 344 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 345 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 346 | Total Ingresos de Spa | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 347 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 348 | Costo de Spa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 349 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 350 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 351 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 352 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 353 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 354 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 355 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 356 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 357 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 358 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 359 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 360 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 361 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 362 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 363 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 364 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 365 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 366 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 367 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 368 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 369 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 370 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 371 | Ambientación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 372 | Suministros Deportivos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 373 | Suministros de Limpieza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 374 | Servicios de Clúster | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 375 | Servicios y Regalos de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 376 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 377 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 378 | Decoraciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 379 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 380 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 381 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 382 | Productos de Salud y Belleza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 383 | Lavandería y Limpieza en Seco | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 384 | Licencias y Permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 385 | Lencería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 386 | Honorarios de Administración | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 387 | Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 388 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 389 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 390 | Reservaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 391 | Honorarios de Regalía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 392 | Piscina | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 393 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 394 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 395 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 396 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 397 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 398 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 399 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 400 | UTILIDAD NETA SPA | 1 | total de departamento | CALC | D:O,Q |  | 16.5 | 0 | banda negra |
| 401 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 402 | DEPARTAMENTO DE TOURS | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 16.5 | 0 | banner depto · letra roja |
| 403 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 404 | Ingresos por Tours | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 405 | Tours | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 406 | Tours | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 407 | Tours | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 408 | Total Ingresos por Tours | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 409 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 410 | Costo de Tours | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 411 | Costo Tours | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 412 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 413 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 414 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 415 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 416 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 417 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 418 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 419 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 420 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 421 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 422 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 423 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 424 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 425 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 426 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 427 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 428 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 429 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 430 | Mano de Obra por Contrato | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 431 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 432 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 433 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 434 | Gastos Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 435 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 436 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 437 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 438 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 439 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 440 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 441 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 442 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | SUM | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 443 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 444 | UTILIDAD NETA TOURS | 1 | total de departamento | CALC | D:O,Q |  | 16.5 | 0 | banda negra |
| 445 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 446 | DEPARTAMENTO DE TIENDA DE REGALOS | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banner depto · letra roja |
| 447 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 448 | Ingreso Tienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 449 | Ingreso Tienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 450 | Ingreso Tienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 451 | Ingreso Tienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 452 | Total Ingresos de Tienda | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 453 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 454 | Costo de Ropa de Mujer | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 455 | Costo de Ropa de Niños | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 456 | Costo de Accesorios de Vestir | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 457 | Costo de Viseras/Sombreros/Gorras | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 458 | Costo de Calzado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 459 | Costo de Otra Ropa | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 460 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 461 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 462 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 463 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 464 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 465 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 466 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 467 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 468 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 469 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 470 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 471 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 472 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 473 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 474 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 475 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 476 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 477 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 478 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 479 | % de Ingresos del Depto. | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 480 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 481 | Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 482 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 483 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 484 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 485 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 486 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 487 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 488 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 489 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 490 | % de Ingresos del Depto. | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 491 | UTILIDAD NETA TIENDA | 1 | total de departamento | CALC | D:O,Q | SÍ | 16.5 | 0 | banda negra |
| 492 | % Utilidad | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 493 | DEPARTAMENTO DE BAR PRIVADO | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banner depto · letra roja |
| 494 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 495 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 496 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 497 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 498 | Bar Privado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 499 | Total Ingresos de Bar Privado | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 500 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 501 | Costo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 502 | Costo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 503 | Costo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 504 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 505 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 506 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 507 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 508 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 509 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 510 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 511 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 512 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 513 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 514 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 515 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 516 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 517 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 518 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 519 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 520 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 521 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 522 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 523 | % de Ingresos del Depto. | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 524 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 525 | Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 526 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 527 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 528 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 529 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 530 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 531 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 532 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 533 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 534 | % de Ingresos del Depto. | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 535 | UTILIDAD NETA BAR PRIVADO | 1 | total de departamento | CALC | D:O,Q | SÍ | 16.5 | 0 | banda negra |
| 536 | % Utilidad | 4 | ratio / % (KPI) | CALC | D:O | SÍ | 16.5 | 0 | banda ratio · **sólo 12 fórmulas** |
| 537 | DEPARTAMENTO CLUB MADRESAL | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 16.5 | 0 | banner depto · letra roja |
| 538 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 539 | Ingreso Madresal Club-Cuotas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 540 | Ingreso Club Madresal | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 541 | Ingreso Club Madresal | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 542 | Total Ingresos Club Madresal | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 543 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 544 | Costos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 545 | Costos | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 546 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 547 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 548 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 549 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 550 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 551 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 552 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 553 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 554 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 555 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 556 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 557 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 558 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 559 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 560 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 561 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 562 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 563 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 564 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 565 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 566 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 567 | Edificio | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 568 | Cargos de contabilidad centralizada | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 569 | Suministros de limpieza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 570 | Servicios contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 571 | Equipo eléctrico y mecánico | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 572 | Electricidad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 573 | Suministros de ingeniería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 574 | Entretenimiento—interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 575 | Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 576 | Mantenimiento de terrenos y jardinería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 577 | Lavandería y limpieza en seco | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 578 | Licencias y permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 579 | Vida/seguridad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 580 | Varios/caja chica | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 581 | Suministros operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 582 | Otros combustibles | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 583 | Impresión y papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 584 | Promoción | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 585 | Piscina | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 586 | Gastos de sistemas: sistemas de información | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 587 | Gastos de sistemas: telecomunicaciones y sistemas de información-internet | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 588 | Costos de uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 589 | Agua | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 590 | Fees | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 591 | Seguro de propiedad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 | alineada a la izq. |
| 592 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 593 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 594 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 595 | UTILIDAD NETA CLUB MADRESAL | 1 | total de departamento | CALC | D:O,Q |  | 16.5 | 0 | banda negra |
| 596 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 597 | DEPARTAMENTO DE LAVANDERÍA | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 16.5 | 0 | banner depto · letra roja |
| 598 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 599 | Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 600 | Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 601 | Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 602 | Total Ingresos de Lavandería | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 603 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 604 | Costos de Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 605 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 606 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 607 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 608 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 609 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 610 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 611 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 612 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 613 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 614 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 615 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 616 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 617 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 618 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 619 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 620 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 621 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 622 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 623 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 624 |  | 4 | ratio / % (sin etiqueta) | CALC | N:O |  | 16.5 | 0 | banda ratio · **sólo 2 fórmulas** |
| 625 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 626 | Suministros de Limpieza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 627 | Servicios y Regalos de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 628 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 629 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 630 | Decoraciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 631 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 632 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 633 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 634 | Lavandería y Limpieza en Seco | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 635 | Suministros de Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 636 | Licencias y Permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 637 | Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 638 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 639 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 640 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 641 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 642 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 643 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 644 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 645 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 646 | UTILIDAD NETA LAVANDERÍA | 1 | total de departamento | CALC | D:O,Q |  | 16.5 | 0 | banda negra |
| 647 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 648 | DEPARTAMENTO DE INGRESOS VARIOS | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banner depto · letra roja |
| 649 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 16.5 | 0 | banda encabezado |
| 650 | Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 651 | Cargos por Deserción (Attrition) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 652 | Cargo por Cancelación | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 653 | Descuento por Pronto Pago Obtenido | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 654 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 655 | Pérdidas Cambiarias | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 656 | Ingresos por Intereses | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 657 | Ruptura de Paquetes (Package Breakage) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 658 | Cuota de Sostenibilidad | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 659 | Servicios Médicos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 15.75 | 0 |  |
| 660 | Total Ingresos Varios | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 661 | UTILIDAD NETA INGRESOS VARIOS | 1 | total de departamento | CALC | D:O,Q |  | 17.25 | 0 | banda negra |
| 662 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 663 |  | — | separadora (banda gris) | (vacía) |  |  | 3.95 | 0 | banda gris separadora |
| 664 | DEPARTAMENTOS DE GASTOS GENERALES (OVERHEAD) | 0 | encabezado de grupo (banner) | (sólo etiqueta) |  |  | 17.25 | 0 | banda negra |
| 665 | ADMINISTRACIÓN Y GENERAL | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 16.5 | 0 | banner depto · letra roja |
| 666 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 667 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 668 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 669 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 670 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 671 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 672 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 673 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 674 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 675 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 676 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 677 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 678 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 679 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 680 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 681 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 682 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 683 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 684 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 685 | Honorarios de Auditoría | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 686 | Cargos Bancarios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 687 | Sobrantes y Faltantes de Caja | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 688 | Cargos de Contabilidad Centralizada | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 689 | Servicios de Clúster | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 690 | Servicios y Regalos de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 691 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 692 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 693 | Crédito y Cobranza | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 694 | Comisiones de Tarjeta de Crédito | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 695 | Decoraciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 696 | Donaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 697 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 698 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 699 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 700 | Ganancias (Pérdidas) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 701 | Recursos Humanos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 702 | Servicios Legales | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 703 | Licencias y Permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 704 | Pérdidas y Daños | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 705 | Varios/Sostenibilidad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 706 | Cambio de Divisa de No Huéspedes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 707 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 708 | Procesamiento de Planilla | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 709 | Franqueo y Mensajería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 710 | Honorarios Profesionales | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 711 | Provisión para Cuentas Incobrables | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 712 | Seguridad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 713 | Costos de Liquidación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 714 | Transporte de Personal | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 715 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 716 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 717 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 718 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 719 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 720 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 721 | TOTAL ADMINISTRACIÓN Y GENERAL | 1 | total de departamento | CALC | D:O,Q |  | 17.25 | 0 | banda negra |
| 722 | VENTAS Y MERCADEO | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 17.25 | 0 | banner depto · letra roja |
| 723 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 15.75 | 0 | banda encabezado |
| 724 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 725 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 726 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 727 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 728 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 729 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 730 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 731 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 732 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 733 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 734 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 735 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 736 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 737 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 738 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 739 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ |  | 0 |  |
| 740 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 741 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 742 | Honorarios de Agencia | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 743 | Servicios de Clúster (cuota de mercadeo) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 744 | Material Promocional (Colateral) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 745 | Servicios y Regalos de Cortesía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 746 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 747 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 748 | Decoraciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 749 | Correo Directo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 750 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 751 | Entretenimiento—Interno (CPL) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 752 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 753 | Viajes de Familiarización | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 754 | Franquicia y Afiliación—Regalías | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 755 | Mercadeo de Franquicia y Afiliación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 756 | Diseño Gráfico Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 757 | Programas de Lealtad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 758 | Medios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 759 | Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 760 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 761 | Representación de Ventas Externa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 762 | Servicios Externos de Investigación de Mercado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 763 | Rotulación Externa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 764 | Fotografía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 765 | Franqueo y Mensajería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 766 | Promoción | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 767 | Ferias Comerciales | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 768 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 769 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 770 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 771 | Sitio Web | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 772 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 773 | TOTAL VENTAS Y MERCADEO | 1 | total de departamento | CALC | D:O,Q |  | 17.25 | 0 | banda negra |
| 774 | MANTENIMIENTO | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 17.25 | 0 | banner depto · letra roja |
| 775 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 776 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 777 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 778 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 779 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 780 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 781 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 782 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 783 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 784 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 785 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 786 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 787 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 788 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 789 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 790 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 791 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 792 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 793 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 794 | Edificio | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 795 | Servicios de Clúster | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 796 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 797 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 798 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 799 | Equipo Eléctrico y Mecánico | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 800 | Ascensores y Escaleras Eléctricas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 801 | Suministros de Ingeniería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 802 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 803 | Equipo (hardware) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 804 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 805 | Revestimiento de Pisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 806 | Mobiliario y Equipo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 807 | Mantenimiento de Terrenos y Jardinería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 808 | Calefacción, Ventilación y A/C | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 809 | Equipo de Cocina | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 810 | Equipo de Lavandería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 811 | Licencias y Permisos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 812 | Vida/Seguridad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 813 | Bombillos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 814 | Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 815 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 816 | Pintura y Revestimiento de Paredes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 817 | Plomería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 818 | Piscina | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 819 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 820 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 821 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 822 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 823 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 824 | Reparación de Vehículos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 825 | Recolección de Desechos | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 826 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 827 | TOTAL MANTENIMIENTO | 1 | total de departamento | CALC | D:O,Q |  | 17.25 | 0 | banda negra |
| 828 | SISTEMAS DE INFORMACIÓN | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  | SÍ | 17.25 | 0 | banner depto · letra roja |
| 829 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 17.25 | 0 | banda encabezado |
| 830 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 831 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 832 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 833 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 834 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 835 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 836 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 837 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 838 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 839 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 840 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 841 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 842 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 843 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 844 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 845 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 846 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 847 | Costo de Servicios | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 17.25 | 0 | banda encabezado |
| 848 | Costo de Telefonía Celular | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 849 | Costo de Llamadas Locales | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 850 | Costo de Servicios de Internet | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 851 | Costo de Larga Distancia | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 852 | Otros Costos de Servicios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 853 | Total Costo de Servicios | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 854 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  | SÍ | 17.25 | 0 | banda encabezado |
| 855 | Reembolsos a Oficina Corporativa | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 856 | Cuotas y Suscripciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 857 | Entretenimiento—Interno | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 858 | Alquiler de Equipo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 859 | Varios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 860 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 861 | Otros Costos de Servicios | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 862 | Otro Equipo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 863 | Gastos de Sistema: Administración y General | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 864 | Gastos de Sistema: SI Centralizados | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 865 | Gastos de Sistema: Gestión de Energía | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 866 | Gastos de Sistema: A&B | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 867 | Gastos de Sistema: Golf | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 868 | Gastos de Sistema: Hardware | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 869 | Gastos de Sistema: Club de Salud/Spa | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 870 | Gastos de Sistema: RR. HH. | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 871 | Gastos de Sistema: Seguridad de la Información | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 872 | Gastos de Sistema: Sistemas de Información | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 873 | Gastos de Sistema: Otros | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 874 | Gastos de Sistema: Estacionamiento | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 875 | Gastos de Sistema: Operaciones de Propiedad | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 876 | Gastos de Sistema: Habitaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 877 | Gastos de Sistema: Ventas y Mercadeo | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 878 | Gastos de Sistema: Telecomunicaciones | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 879 | Almacenamiento y Optimización de Sistemas | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 880 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 881 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 882 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 883 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 884 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q | SÍ | 16.5 | 0 |  |
| 885 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q | SÍ | 17.25 | 0 | banda subtotal |
| 886 | TOTAL SISTEMAS DE INFORMACIÓN | 1 | total de departamento | CALC | D:O,Q | SÍ | 17.25 | 0 | banda negra |
| 887 | SERVICIOS PÚBLICOS | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 17.25 | 0 | banner depto |
| 888 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 889 | Agua (Chilled Water) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 890 | Servicios Contratados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 891 | Electricidad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 892 | Gas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 893 | Combustible (Generador) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 894 | Combustible | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 895 | Combustible (Lancha y Equipo) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 896 | Otros Combustibles | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 897 | Vapor | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 898 | Agua | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 899 | TOTAL SERVICIOS PÚBLICOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 900 | DEPARTAMENTO ÁREA RECREATIVA | 0 | encabezado de departamento (banner) | (sólo etiqueta) |  |  | 17.25 | 0 | banner depto · letra roja |
| 901 | INGRESOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 902 | Ingreso | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 903 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 904 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 905 | Total Ingresos Área Recreativa | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 906 | COSTO DE VENTAS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 907 | Costos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 908 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 909 | Total Costo de Ventas | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 910 | NÓMINA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 16.5 | 0 | banda encabezado |
| 911 | Salarios y Sueldos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 912 | Horas Extra | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 913 | Día Libre | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 914 | Feriado Trabajado | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 915 | Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 916 | Seguro Social (CCSS) | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 917 | Aguinaldo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 918 | Póliza de Riesgos del Trabajo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 919 | Provisión de Vacaciones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 920 | Vacaciones Disfrutadas | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 921 | Cafetería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 922 | Preaviso y Cesantía | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 923 | Bono de Incentivo | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 924 | Vivienda | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 925 | Transporte de Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 926 | Otros Beneficios a Empleados | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 927 | TOTAL NÓMINA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 928 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 929 | Gastos Operativos | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 930 | Varios | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 931 | Suministros Operativos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 932 | Impresión y Papelería | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 933 | Capacitación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 934 | Viajes—Comidas y Entretenimiento | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 935 | Viajes—Otros | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 936 | Costos de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  | 12 | 0 |  |
| 937 | Lavado de Uniformes | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 938 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | SUM | D:O,Q |  | 16.5 | 0 | banda subtotal |
| 939 |  | — | fila en blanco | (vacía) |  |  | 16.5 | 0 |  |
| 940 | TOTAL GASTOS OPERATIVOS | 2 | subtotal de sub-bloque | CALC | D:O,Q |  | 16.5 | 0 | banda subtotal |
| 941 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 942 | UTILIDAD NETA ÁREA RECREATIVA | 1 | total de departamento | CALC | D:O,Q |  | 16.5 | 0 | banda negra |
| 943 |  | 4 | ratio / % (sin etiqueta) | (vacía) |  |  | 16.5 | 0 | banda ratio |
| 944 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 945 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 946 | GASTOS DE PROPIEDAD | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 947 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 948 | ALQUILER | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 949 | Alquiler | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 950 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 951 | TOTAL ALQUILER | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 952 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 953 | HONORARIOS DE ADMINISTRACIÓN | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 954 | Honorarios de Administración | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 955 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 956 | TOTAL HONORARIOS DE ADMINISTRACIÓN (5%) Y REGALÍAS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 957 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 958 | SEGURO DE PROPIEDAD | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 959 | Seguro de Propiedad | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 960 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 961 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 962 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 963 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 964 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 965 | TOTAL SEGURO DE PROPIEDAD | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 966 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 967 | INTERESES SOBRE PRÉSTAMOS | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 968 | Intereses sobre Préstamos | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 969 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 970 | TOTAL INTERESES SOBRE PRÉSTAMOS | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 971 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 972 | CARGOS BANCARIOS Y COMISIONES | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 973 | Cargos Bancarios y Comisiones | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 974 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 975 | TOTAL CARGOS BANCARIOS Y COMISIONES | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 976 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 977 | GANANCIA / PÉRDIDA CAMBIARIA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 978 | Ganancia / Pérdida Cambiaria | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 979 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 980 | TOTAL GANANCIA / PÉRDIDA CAMBIARIA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 981 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 982 | RESERVA / GASTO DE CAPITAL | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 983 | Reserva de Capital | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 984 | Gasto de Capital Mayor | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 985 | TOTAL GASTO DE CAPITAL | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 986 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 987 | DEPRECIACIÓN | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 988 | Depreciación | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 989 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 990 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 991 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 992 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 993 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 994 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 995 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 996 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 997 | TOTAL DEPRECIACIÓN | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 998 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 999 | MULTAS Y OTROS GASTOS NO DEDUCIBLES | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 1000 | Multas y Otros Gastos No Deducibles | 3 | línea de detalle | ENLACE | D:O,Q |  |  | 0 |  |
| 1001 |  | — | fila en blanco | (vacía) |  |  |  | 0 |  |
| 1002 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 1003 | TOTAL MULTAS Y OTROS NO DEDUCIBLES | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |
| 1004 |  | — | fila en blanco | (vacía) |  |  | 15.75 | 0 |  |
| 1005 | IMPUESTO SOBRE LA RENTA | 1 | encabezado de sub-bloque | (sólo etiqueta) |  |  | 15.75 | 0 | banda encabezado |
| 1006 | Impuesto sobre la Renta | 3 | línea de detalle | ENLACE | D:O,Q |  | 15.75 | 0 |  |
| 1007 | TOTAL IMPUESTO SOBRE LA RENTA | 2 | subtotal de sub-bloque | ENLACE | D:O,Q |  | 17.25 | 0 | banda subtotal |

---

## 4. Rarezas encontradas

### 4.1 Filas ocultas (265)

No hay agrupamientos de Excel (`outlineLevel` = 0 en todas). El ocultamiento es manual,
fila por fila. Los rangos son:

```
5, 33-34, 52, 70, 95-96, 102-103, 111, 117, 121, 126, 141-147, 149-152, 234-294, 446-536, 648-660, 723-740, 828-886
```

Lo importante: **hay departamentos enteros ocultos**, no sólo filas sueltas.

| Rango | Qué está oculto |
|---|---|
| 5 | KPI `Habitaciones por Día` |
| 33–34, 52, 70, 95–96, 102–103, 111, 117, 121, 126 | filas muertas dentro del bloque RESUMEN |
| 141–147, 149–152 | cola de diagnóstico del RESUMEN (`Variación 0`, `Gastos de propiedad`, `Gastos después de EBITDA`). Ojo: **la 148 quedó visible** en medio del bloque oculto. |
| **234–294** | **DEPARTAMENTO DE ALIMENTOS Y BEBIDAS — INGRESOS, COSTO DE VENTAS y NÓMINA completos.** Sólo quedan visibles sus Gastos Operativos y la utilidad neta. |
| **446–536** | **DEPARTAMENTO DE TIENDA DE REGALOS y DEPARTAMENTO DE BAR PRIVADO completos** (banner incluido). |
| **648–660** | **DEPARTAMENTO DE INGRESOS VARIOS** completo salvo su fila de utilidad neta (661, visible). |
| **723–740** | NÓMINA completa de VENTAS Y MERCADEO. |
| **828–886** | **SISTEMAS DE INFORMACIÓN completo** (banner incluido). |

> ⚠️ Al reconstruir hay que decidir explícitamente si estas filas se muestran, se ocultan
> por defecto con un toggle, o se descartan. Ocultas **siguen sumando** en los totales.

### 4.2 Rangos `SUM` inconsistentes entre columnas (bug del Excel)

En estas filas la fórmula de enero–abril suma un rango distinto al de mayo–diciembre.
Alguien insertó filas y arrastró la fórmula sólo en parte de la fila.

| Fila | Etiqueta | Rango en D:G | Rango en H:O, Q |
|---:|---|---|---|
| 50 | Total Gastos Operativos | `37:49` | `40:47` |
| 65 | UTILIDAD OPERATIVA | `52:64` | `55:63` |
| 78 | TOTAL GASTOS GENERALES | `65:77` | `71:77` |

> ⚠️ En la fila 78 el rango de D:G (`65:77`) **incluye la fila 65 (UTILIDAD OPERATIVA)**,
> es decir enero–abril están sumando la utilidad dentro de los gastos generales.
> Al portar hay que usar el rango correcto, no replicar el error.

### 4.3 Filas con fórmulas incompletas

| Filas | Qué pasa |
|---|---|
| 3–8 (KPIs) | Sólo tienen fórmula en `H:O` y `Q`. **Enero a abril (`D:G`) están vacíos.** Habitaciones disponibles/ocupadas, huéspedes, ocupación y ADR no tienen datos del primer cuatrimestre. |
| 294, 334, 336, 479, 490, 492, 523, 534, 536 | Filas de `%%` con fórmula en `D:O` pero **sin fórmula en `Q` (Total Año)** — el porcentaje anual no se calcula. |
| 624 | Fila de ratio **sin etiqueta** con fórmula sólo en `N` y `O` (noviembre y diciembre). Resto del año en blanco. |

### 4.4 Etiquetas duplicadas

Hay 83 textos que aparecen más de una vez. La etiqueta **no sirve como identificador**:
hay que usar `(departamento, sub-bloque, fila)`.

Las más repetidas:

| Etiqueta | Veces |
|---|---:|
| Comisiones | 16 |
| Gastos Operativos | 15 |
| TOTAL GASTOS OPERATIVOS | 14 |
| NÓMINA | 13 |
| Salarios y Sueldos | 13 |
| Horas Extra | 13 |
| Día Libre | 13 |
| Feriado Trabajado | 13 |
| Seguro Social (CCSS) | 13 |
| Aguinaldo | 13 |
| Póliza de Riesgos del Trabajo | 13 |
| Provisión de Vacaciones | 13 |
| Vacaciones Disfrutadas | 13 |
| Cafetería | 13 |
| Preaviso y Cesantía | 13 |
| Bono de Incentivo | 13 |
| Vivienda | 13 |
| Transporte de Empleados | 13 |
| Otros Beneficios a Empleados | 13 |
| TOTAL NÓMINA | 13 |
| Suministros Operativos | 12 |
| Capacitación | 12 |
| Viajes—Comidas y Entretenimiento | 12 |
| Viajes—Otros | 12 |
| Costos de Uniformes | 11 |
| INGRESOS | 10 |
| Lavado de Uniformes | 10 |
| Varios | 9 |
| Servicios Contratados | 8 |
| Reembolsos a Oficina Corporativa | 8 |

Casos que además son ambiguos **dentro del mismo departamento**:

| Filas | Etiqueta | Departamento |
|---|---|---|
| 235–238 | `Alimentos` ×4 | A&B — cuatro cuentas distintas, mismo nombre |
| 239–242 | `Bebida sin Alcohol` ×4 | A&B |
| 243–246 | `Cerveza` ×4 | A&B |
| 247–250 | `Licor` ×4 | A&B |
| 251–254 | `Vino` ×4 | A&B |
| 255–258 | `A&B Varios` ×4 | A&B |
| 270–274 | `Costo A&B Varios` ×5 | A&B |
| 405–407 | `Tours` ×3 | Tours |
| 448–451 | `Ingreso Tienda` ×4 | Tienda de Regalos |
| 495–498 | `Bar Privado` ×4 | Bar Privado |
| 501–503 | `Costo` ×3 | Bar Privado |
| 599–601 | `Lavandería` ×3 | Lavandería |
| 852 y 861 | `Otros Costos de Servicios` ×2 | Sistemas de Información (uno en Costo de Servicios, otro en Gastos Operativos) |

> Para la app: cada una de estas filas viene de una **cuenta contable distinta** del libro
> origen. Hay que traer el código de cuenta, no el nombre.

### 4.5 Saltos y anomalías de estructura

| Fila(s) | Anomalía |
|---|---|
| 938 y 940 | **`TOTAL GASTOS OPERATIVOS` dos veces seguidas** en Área Recreativa, separadas por la fila vacía 939. La 938 es `=SUM(...)`; la 940 es `CALC`. Duplicado real, hay que decidir cuál vale. |
| 900–943 | **Área Recreativa es un departamento operativo pero está colocado DESPUÉS del bloque de overhead** (663–899). Rompe el orden lógico del reporte. |
| 887–899 | `SERVICIOS PÚBLICOS` usa banner de departamento (`FF404040`) pero **no tiene NÓMINA ni utilidad neta** — sólo Gastos Operativos y un total. Es un departamento de overhead con formato de operativo. |
| 648–661 | `DEPARTAMENTO DE INGRESOS VARIOS` no tiene nómina ni gastos operativos: sólo ingresos y utilidad neta. |
| 661 | `UTILIDAD NETA INGRESOS VARIOS` está **visible** mientras todo su departamento (648–660) está oculto. |
| 129–132 | Bloque `Ingresos totales / Total gastos operativos / Gastos de la Propiedad / UTILIDAD NETA` que **repite** conceptos ya calculados arriba (36, 50, 127). Es una verificación cruzada. |
| 135–140 | Sub-bloque `Resumen` sin banda de encabezado: `Total Nómina y Beneficios`, `Total Gastos Operativos`, `Costo Total`, `Total Gastos de Propiedad`, `UTILIDAD NETA`. |
| 141, 144, 145 | Filas de control ocultas: `Variación 0`, `Gastos de propiedad`, `Gastos después de EBITDA`. `Variación 0` es un cuadre que debería dar cero. |
| 127, 132, 140 | **`UTILIDAD NETA` aparece 3 veces** en el bloque RESUMEN, calculada por caminos distintos. |
| 846–853 | Sistemas de Información tiene un sub-bloque `Costo de Servicios` que no existe en ningún otro departamento. |
| 944–1007 | El bloque de gastos de propiedad usa encabezado + total pero **sin banner de departamento**; `GASTOS DE PROPIEDAD` (946) tiene formato de sub-encabezado, no de banner. |
| 989–996 | Ocho filas vacías consecutivas entre `Depreciación` (988) y `TOTAL DEPRECIACIÓN` (997). |
| 960–964 | Cinco filas vacías entre `Seguro de Propiedad` (959) y su total (965). |
| 1007 | El archivo **termina en un total** (`TOTAL IMPUESTO SOBRE LA RENTA`) sin fila de utilidad neta final. No hay “UTILIDAD NETA DEL PERIODO” al cierre del detalle. |

### 4.6 Formato inconsistente

| Fila(s) | Detalle |
|---|---|
| 11–16 | Membresías del Club usan **Segoe UI 14** mientras toda la hoja usa **Arial 12**. |
| 60 (`Club Madresal`) y 116 (`Depreciación`) | **Resaltadas a mano** con relleno `theme4/0.80` dentro del bloque RESUMEN. Marcas de trabajo pendiente. |
| 319 (`Desayunos`) | Única línea de detalle con **letra roja** en todo el archivo. |
| 567–591 | Gastos Operativos de Club Madresal: etiquetas **alineadas a la izquierda y en minúscula** (`Edificio`, `Suministros de limpieza`…) mientras el resto de la hoja va centrado y capitalizado. Bloque pegado de otra fuente. |
| 587 | Etiqueta truncada/larga: `Gastos de sistemas: telecomunicaciones y sistemas de …`. |
| 211 (`Linen`), 590 (`Fees`) | Etiquetas **en inglés** dentro de un reporte en español. |
| 316, 385 (`Lencería`) vs 211 (`Linen`) | Mismo concepto, dos nombres distintos. |
| 1 | Fila 1 vacía pero con formato (letra naranja negrita, relleno `FFFFAE6` en D1). |

### 4.7 Basura residual

| Ubicación | Contenido |
|---|---|
| Columna **HB** (210), filas 29–42 | Nombres de mes en inglés sueltos: `January`, `March`, `April`, `May`, `June`, `July`, `August`, `September`, `October`, `November`, `December`. **Falta `February`.** No los referencia ninguna fórmula. Descartables. |
| Filas 1008–1046 | Completamente vacías, pero `ws.max_row` las reporta. |
| Encabezado/pie de página | openpyxl no lo puede parsear (`Cannot parse header or footer`). Está corrupto o usa una extensión no estándar. |

### 4.8 Dependencia externa

**723 de las 782 filas con datos son fórmulas de enlace** a un libro externo indexado como `[1]`:

```
=+'[1]Budget 2025W'!K17          <- la mayoría del detalle
=+'[1]P&L Detail Club'!D12       <- membresías (filas 11-14)
```

Sólo **16 filas** tienen `=SUM()` interno y **43** tienen aritmética propia (`CALC`).

> Es decir: **este archivo es una plantilla de presentación, no un modelo de cálculo.**
> Los números viven en `Budget 2025W`. La hoja sólo define el **layout**.
> Para la app, esto es una buena noticia: hay que replicar el layout y conectar
> cada fila a la cuenta correspondiente del motor, no reimplementar fórmulas.

---

## 5. Notas para quien construya el motor

1. **La columna C es la única fuente de etiquetas.** No hay indentación (`alignment.indent` = 0
   en las 1007 filas). El nivel jerárquico **está codificado únicamente en el color de relleno**
   y en negrita/itálica. Ese mapeo está en §1.3 y en la columna «Notas» de §3.
2. **Las filas en blanco son parte del diseño.** Hay 54 separadoras. Muchas contienen un
   espacio literal `" "` en D:Q (no están realmente vacías) — eso es lo que evita que Excel
   colapse el borde de la banda. Al reconstruir, son márgenes verticales, no datos.
3. **Ocultar ≠ borrar.** Las 265 filas ocultas siguen alimentando los totales.
4. **El identificador de una línea no es su etiqueta** (§4.4). Hace falta el código de cuenta.
5. **No replicar los rangos `SUM` rotos** de las filas 50, 65 y 78 (§4.2).
6. **Área Recreativa está fuera de orden** (§4.5) — decidir si se reubica antes del overhead.

