# COSTOS_GRUPOS.md
## Módulo de Costos para Negociación de Grupos — SCP Corcovado Wilderness Lodge

**Destino:** tab `COSTOS` de FinPlan CWL
**Consumidores:** Dirección Comercial (vista de pisos), Finanzas (vista completa), CWL-TARIFARIO (cotizador de grupos)
**Base documental:** Política de descuentos por capas aprobada para Junta Directiva (YTD abril 2026)
**Versión:** 1.0 — agosto 2026

---

## 0. Propósito y alcance

Este módulo calcula **cuánto cuesta atender un grupo**, expresado en dólares por unidad de servicio, para que la operación pueda negociar sin destruir margen y sin rechazar negocio rentable.

**Qué hace:**
- Convierte el P&L mensual en costos unitarios por driver operativo.
- Separa costo variable, costo fijo departamental, overhead absorbido y fee.
- Produce cuatro pisos de precio por servicio y por temporada, en dólares.
- Ensambla el costo de un paquete de grupo y lo compara contra el precio propuesto.

**Qué NO hace:**
- No fija tarifas rack ni sustituye Revenue Management.
- No reemplaza la política de descuentos aprobada; la instrumenta.
- No aplica a huéspedes FIT individuales, que siguen la política por capas vigente.

---

## 1. Principio rector: dólares por driver, no porcentajes de revenue

El modelo actual asigna overhead como porcentaje del revenue del departamento. Para análisis de P&L es correcto y concilia. **Para fijar pisos de precio es circular:** si se concede un descuento, baja el revenue y baja el overhead asignado en la misma proporción, de modo que el piso se mueve junto con el precio y nunca se alcanza.

Consecuencia práctica: el "descuento máximo 56.8%" de Habitaciones en la política es un techo contable, no un piso operativo.

**Regla del módulo:** todo costo que entra en un piso se expresa en dólares por unidad física (habitación-noche, noche-huésped, pax, traslado, tratamiento). El método porcentual se conserva únicamente en el sub-tab de conciliación.

**Evidencia que respalda la regla** — el overhead por habitación *disponible* es estable entre temporadas, mientras que como porcentaje del revenue se dispara:

| Métrica | Alta (ene–abr) | Baja derivada | Año |
|---|---|---|---|
| Overhead como % del revenue | 24.5% | 66.2% | 41.7% |
| Overhead por hab. disponible-noche | $207.54 | $221.05 | $216.20 |

La estructura no cambia. Lo que cambia es sobre cuántas ventas se reparte.

---

## 2. Calendario de temporadas

Definición oficial. **Es configurable:** los meses son el dato, la temporada es un mapa.

| Temporada | Meses | Días | Hab-noche disponibles |
|---|---|---|---|
| ALTA | dic, ene, feb, mar, abr | 151 | 4,530 |
| MEDIA | may, jun, jul, ago, nov | 153 | 4,590 |
| BAJA | set, oct | 61 (30 abiertos) | 900 |
| **Total** | | **365 (334 abiertos)** | **10,020** |

**Cierre anual:** 31 días × 30 habitaciones = 930 hab-noche. Por aritmética de días corresponde a **octubre** (único mes de 31 días en la temporada baja). Confirmar contra el calendario operativo antes de la primera corrida.

### 2.1 Regla del mes cerrado

El overhead del mes cerrado no desaparece. Hay dos tratamientos y dan resultados opuestos:

| Tratamiento | Fórmula | Alta | Media | Baja |
|---|---|---|---|---|
| **A** · Absorción estacional | OH_temporada ÷ hab-noche disponibles de la temporada | ~$198 | ~$198 | ~$402 |
| **B** · Absorción del ciclo anual *(default)* | OH_anual ÷ hab-noche disponibles del año | $216.20 | $216.20 | $216.20 |

Con el tratamiento A, el costo de octubre cae sobre las 900 noches de setiembre y las duplica. Ningún grupo compra eso y la operación rechaza el único negocio disponible en el mes más flojo.

**Default = B.** El mes cerrado es costo de operar el ciclo, no costo de setiembre. **A se calcula y se muestra siempre al lado, como diagnóstico** de cuánto cuesta tener el hotel cerrado.

Parámetro: `cfg.tratamiento_mes_cerrado ∈ {A, B}`, default `B`.

### 2.2 Advertencias sobre el mapa

- **Noviembre en MEDIA es una decisión comercial, no contable.** Pega contra el cierre y contra el arranque de alta. Debe calcularse como mes independiente y mostrarse su costo unitario propio; si su ocupación real se parece más a octubre que a junio, inflará artificialmente el costo unitario de toda la temporada media.
- **Diciembre no existe en los archivos fuente actuales.** La "alta" disponible es enero–abril. Sin diciembre actual, ALTA es un ciclo incompleto de cuatro meses.
- **La "temporada baja" de los archivos previos no es la baja.** Es un residuo (Forecast anual − YTD abril) que mezcla mayo–diciembre: media, baja y diciembre alto en un solo cubo. **No usar para nada en este módulo.** Se recalcula desde el mensual.

---

## 3. Modelo de datos

### 3.1 Configuración

```
cfg_temporadas          mes(1-12) → temporada {ALTA, MEDIA, BAJA}, dias, dias_abiertos
cfg_parametros          management_fee_pct (default 0.03)
                        margen_protegido_pct (default 0.15)
                        metodo_absorcion {M1,M2,M3,M4} (default M2)
                        tratamiento_mes_cerrado {A,B} (default B)
                        incluir_capital_en_piso (default NO)
                        sustainability_libre {SI,NO} (default NO — ver §8)
cfg_canales             canal, comision_pct, aplica_a_grupos
cfg_clasificacion       departamento, linea_gasto, pct_variable, pct_fijo, pct_escalonado
cfg_escalones           departamento, driver, umbral, costo_adicional, descripcion
cfg_drivers_overhead    componente_overhead, driver (para método M4)
```

### 3.2 Hechos (origen: FinPlan)

```
fact_pl_mensual         anio, mes, departamento, revenue, cost_of_sales, payroll, opex
fact_overhead_mensual   anio, mes, componente, monto
fact_no_operativo       anio, mes, concepto, monto   (renta, seguro, otros, reserva, capital)
fact_volumenes          anio, mes,
                          hab_disponibles, hab_ocupadas, noches_huesped,
                          pax_tours, salidas_tours,
                          traslados, pax_traslados,
                          tratamientos_spa, transacciones_tienda,
                          cubiertos_desayuno, cubiertos_almuerzo, cubiertos_cena
```

**Grano obligatorio: mensual.** Nada se carga a nivel de temporada. Las temporadas se agregan desde meses vía `cfg_temporadas`. Esto permite además cotizar grupos que cruzan temporadas, ponderando por noche.

**Departamentos:** Habitaciones, F&B, Spa, Tienda, Tours y Actividades, Transporte, Laundry, Sustainability Fee.

**Componentes de overhead:** Administración, Ventas y Mercadeo, Mantenimiento, Sistemas de Información, Servicios Públicos.

### 3.3 Marcado de calidad del dato

Cada fila de `fact_*` lleva `origen ∈ {ACTUAL, FORECAST, PRORRATEO, ESTIMADO}`. Todo output que dependa de una fila no-ACTUAL se muestra marcado. Regla dura: **un piso construido sobre PRORRATEO no puede presentarse a Ventas como piso firme.**

---

## 4. Motor de cálculo

### 4.1 Costos unitarios

Para cada mes `m`, luego agregados por temporada como suma de costos ÷ suma de volúmenes (**nunca promedio de promedios**).

```
CU_hab_propio        = (payroll_rooms + opex_rooms + cos_rooms) / hab_ocupadas
CU_fb_variable       = cos_fb / noches_huesped          [o / cubiertos si existe el dato]
CU_fb_propio         = (cos_fb + payroll_fb + opex_fb) / noches_huesped
CU_tours_variable    = cos_tours / pax_tours            [fallback: / noches_huesped]
CU_tours_propio      = (cos + payroll + opex)_tours / pax_tours
CU_transp_variable   = cos_transp / traslados           [fallback: / noches_huesped]
CU_transp_propio     = (cos + payroll + opex)_transp / traslados
CU_spa_propio        = (payroll + opex)_spa / tratamientos_spa
CU_tienda_variable   = cos_tienda / transacciones_tienda
```

Cada uno se reporta partido en tres columnas: **variable / fijo departamental / escalonado**, según `cfg_clasificacion`.

### 4.2 Absorción de overhead — cuatro métodos

```
M1  Revenue share     OH_asignado = revenue_dept × (OH_total / revenue_total)
                      → SOLO conciliación con P&L. Prohibido para pisos (§1).
M2  Hab. disponible   OH_unitario = OH_total / hab_disponibles          [DEFAULT]
M3  Hab. ocupada      OH_unitario = OH_total / hab_ocupadas
M4  Híbrido           cada componente por su driver (cfg_drivers_overhead):
                        Administración      → revenue o transacciones
                        Ventas y Mercadeo   → revenue por canal
                        Mantenimiento       → área física / work orders
                        Sistemas            → usuarios / terminales
                        Servicios Públicos  → medición directa; si no, ocupación
```

El overhead unitario se aplica a la **habitación-noche** como unidad de absorción del grupo, porque la habitación es lo que reserva la capacidad del hotel. Los componentes de F&B, tours, spa y transporte entran a los pisos con su costo propio; **no se les carga overhead por separado**, para no duplicar la absorción dentro de un mismo paquete.

### 4.3 Pisos de precio

Fee y comisión son porcentajes **sobre el precio**, no costos fijos. El piso se calcula con gross-up:

```
Piso = Costo_$ / (1 − fee_pct − comision_pct − margen_pct)
```

| Piso | Costo_$ incluido | margen_pct | Uso |
|---|---|---|---|
| **1 — Marginal** | sólo costo variable de todos los componentes | 0 | Capacidad ociosa, sin desplazamiento |
| **2 — Departamental** | costo propio completo, sin overhead | 0 | FAM, recuperación, grupo estratégico |
| **3 — Costo Total Integral** | costo propio + overhead unitario | 0 | Piso normal de contratos recurrentes |
| **4 — CTI + margen** | costo propio + overhead unitario | `cfg.margen_protegido_pct` | Tarifa comercial estándar |

**Crédito de Sustainability Fee:** si `cfg.sustainability_libre = SI`, se resta del piso el fee por habitación-noche cobrado al grupo. Ver §8 antes de activarlo.

```
Piso_neto = Piso − SF_por_hab_noche
```

**Ejemplo Habitaciones, temporada alta, comisión 25%** (costo propio $106.46 + overhead $216.20 = $322.66):

| Escenario | Piso bruto | Neto de SF ($92.12) |
|---|---|---|
| Piso 3 (CTI, sin margen) | $448.14 | $356.02 |
| Piso 4 (CTI + 15%) | $566.07 | $473.95 |
| Piso 2 (departamental) | $147.86 | $55.74 |

Contra tarifas rack de $464.97 a $964.53, esto muestra dónde está realmente el espacio de negociación de un grupo en alta.

### 4.4 Escalones

Costos que aparecen al cruzar umbrales; se suman al costo del grupo **antes** del gross-up.

```
si pax > umbral_guia          → + costo_guia_adicional
si pax > capacidad_vehiculo   → + costo_vehiculo_adicional
si pax > umbral_cocina        → + costo_turno_extra
si hab_grupo > umbral_bloque  → + costo_apertura_bloque
```

Definidos en `cfg_escalones`. Sin estos, el modelo subestima grupos grandes.

### 4.5 Desplazamiento

Sólo aplica cuando la ocupación proyectada de las fechas supera un umbral configurable.

```
Contribucion_desplazada = noches_desplazadas
                          × [ ADR_esperado × (1 − fee − comision_FIT) − CU_hab_variable ]
Piso_ajustado = Piso + (Contribucion_desplazada / hab_noche_grupo)
```

Esto es lo que hace que el piso dependa de la **fecha**, no sólo del departamento. En baja tiende a cero; en alta puede ser el componente dominante.

### 4.6 Ensamblador del paquete

```
Costo_grupo = hab_noches × CU_hab
            + noches_huesped × CU_fb (por plan: full board / MAP / sólo desayuno)
            + Σ (pax_tour × CU_tour) por tour incluido
            + Σ (traslados × CU_traslado)
            + tratamientos × CU_spa
            + amenidades y cortesías
            + Σ escalones aplicables

Precio_minimo_pax = [ (Costo_grupo + Contribucion_desplazada)
                      / (1 − fee − comision − margen) ] / pax
```

Salida: costo total, precio mínimo por pax, precio mínimo por pax por noche, y margen resultante contra el precio propuesto.

### 4.7 Golden Rate

La **Golden Rate** es la tarifa por habitación-noche que el hotel necesita para cubrirlo todo: costo propio de Habitaciones, overhead completo, gastos no operativos y, opcionalmente, reserva y capital — **descontando lo que los demás departamentos aportan**. Es el único número que Ventas debe memorizar.

```
Requerido_rooms = costo_propio_rooms + overhead_total + no_operativos
                  [+ reserva y capital si cfg.incluir_capital_en_piso = SI]
                  − Σ (revenue − costo propio) de todos los demás departamentos

Golden_Rate = (Requerido_rooms / hab_ocupadas) / (1 − fee − comision − margen)
```

La resta de la contribución ajena es lo que distingue la Golden Rate de un piso departamental: F&B, tours, transporte y el Sustainability Fee ya absorben parte de la estructura, y cobrarla dos veces en la tarifa de habitación produce un número inflado que nadie puede vender.

**Regla dura: la Golden Rate se calcula sobre el año completo, nunca sobre una temporada.**

Por qué, con los datos disponibles (comisión 25%, sin margen, sin capital):

| Base de cálculo | Golden Rate | ADR real |
|---|---|---|
| Sólo temporada alta (ene–abr) | $155.13 | $613.33 |
| Año completo | $585.26 | $599.06 |

Aislada, la temporada alta parece necesitar $155 por habitación-noche, porque en esos meses el volumen es alto y los demás departamentos aportan $773,857. Pero esa base ignora el mes cerrado, la temporada baja y la estructura que corre los doce meses. **Vender alta contra una Golden Rate estacional destruye el año.**

El número honesto es el anual: $585.26 contra un ADR real de $599.06. El hotel cubre su estructura completa por apenas $14 por habitación-noche, y eso **sin** reserva ni capital mayor. Incluyéndolos, la Golden Rate sube a $652.62 y el ADR actual **no alcanza**.

**Distribución estacional.** La Golden Rate anual se reparte entre temporadas con un índice configurable (`cfg_indice_estacional`, default = mezcla de ADR rack por temporada), de modo que alta cargue más y baja menos. La suma ponderada por habitaciones ocupadas proyectadas debe reproducir la Golden Rate anual. Esa reconciliación es obligatoria: si la suma da menos, el año no cierra.

**Presentación:** siempre en tres versiones —sin capital / con capital, y a la comisión del canal seleccionado— para que quede explícito qué se está cubriendo y qué no.

### 4.8 Comisión máxima por capas

Responde a: **¿cuánta comisión aguanta esta tarifa antes de que deje de cubrir su costo?** Es distinto del descuento máximo, aunque la aritmética se parezca: la comisión no reduce la tarifa publicada, reduce lo que el hotel recibe.

```
c_max = 1 − fee − t − (C / R_bruto)

  C        = costo propio + overhead asignado, en dólares
  R_bruto  = tarifa bruta antes de comisión
  t        = margen protegido de la capa (0 en la Capa 1)
```

**El gross-up es obligatorio y es donde está la trampa.** El revenue del P&L de CWL ya viene **neto de comisión de agencias**. Si se calcula `c_max` contra ese revenue, se descuenta la comisión dos veces y el techo sale artificialmente bajo. Hay que reconstruir la tarifa bruta:

```
R_bruto = revenue_neto / (1 − c_actual)
C / R_bruto = k × (1 − c_actual)      donde k = costo % sobre revenue neto
```

`c_actual` es un parámetro **por departamento y canal**, no global (`cfg_canales.comision_pct`). Habitaciones y paquetes vendidos por agencia llevan comisión embebida — factor neto 0.8220 con la mezcla real de canales. Tienda, spa y consumos en sitio se venden directo: su factor es 1.0 y aplicarles el gross-up sería inventar un techo que no existe.

**Verificación de coherencia:** cuando el factor es 1.0, `c_max` de la Capa 1 debe dar exactamente igual al Margen Integral. Si no coincide, hay un error de base. Sólo donde hay comisión embebida los dos números se separan — y esa separación es precisamente el valor del cálculo.

**Capas mínimas a mostrar en el resumen** (dos obligatorias, la tercera opcional):

| Capa | Cubre | `t` | Uso |
|---|---|---|---|
| **Capa 1 — Cobertura** | Costo Total Integral, margen cero | 0 | Techo absoluto. Un punto más y la venta destruye valor. |
| **Capa 2 — Sostenible** | CTI + margen protegido | `cfg.margen_protegido_pct` | Comisión negociable en contrato normal. |
| *(Capa 0 — Táctica)* | sólo costo departamental + fee | 0 | Excepción con capacidad ociosa y sin desplazamiento. |

**Resultado con los datos de temporada alta** (margen protegido 15%):

| Departamento | Capa 1 · cubre CTI | Capa 2 · CTI + 15% |
|---|---|---|
| Habitaciones | 62.6% | 47.6% |
| F&B | 8.4% | −6.6% |
| Spa | 16.5% | 1.5% |
| Tienda | −2.1% | −17.1% |
| Tours y Actividades | 23.5% | 8.5% |
| Transporte | 23.0% | 8.0% |

Lectura: Habitaciones aguanta comisiones de tres niveles (20/25/30%) con holgura incluso en la capa sostenible. **F&B, Spa, Tienda, Tours y Transporte no aguantan una comisión de 25% en la Capa 2** — varios ni siquiera en la Capa 1. Un contrato que aplique la misma comisión sobre el paquete completo está financiando la comisión de esos componentes con el margen de la habitación. Eso es defendible si es una decisión consciente; es destructivo si nadie lo midió.

**Regla de acumulación.** Comisión y descuento se multiplican, no se suman:

```
erosion_combinada = 1 − (1 − descuento) × (1 − comision)
```

El resumen muestra las dos palancas por separado, y el simulador la combinada. Un 20% de descuento con 25% de comisión erosiona 40%, no 45%.

**Valores negativos** significan que la tarifa actual no alcanza esa capa ni con comisión cero. No se muestran como cero: se muestran en negativo, porque el faltante es la magnitud del problema.

### 4.9 Semáforo

| Zona | Condición | Autorización |
|---|---|---|
| Verde | ≥ Piso 4 | Gerente departamental / Comercial |
| Amarilla | ≥ Piso 3 y < Piso 4 | Finance Controller + Gerente General |
| Roja | ≥ Piso 1 y < Piso 3 | GG + Finanzas, con capacidad ociosa documentada y sin desplazamiento |
| Prohibida | < Piso 1 | No autorizado |

Coincide con la matriz aprobada por la Junta; sólo cambia la unidad de medida de porcentaje a dólares.

---

## 5. Sub-tabs del tab COSTOS

El orden es deliberado: **el resumen va de primero**. Quien abre el tab —operación, Ventas, Gerencia— ve el número que necesita sin recorrer el motor. El detalle de cómo se llegó ahí vive detrás.

**Resumen (landing)**
1. **SUMMARY COST** — vista de una pantalla, sin scroll. Es la vista de entrada del tab.

   **Selectores (independientes, combinables):**
   - **Período:** Mes (cualquiera de los 12) · YTD · Full Year
   - **Temporada:** ALTA · MEDIA · BAJA · Todas
   - **Base:** Actual · Budget · Forecast
   - **Canal:** define la comisión aplicada a pisos y Golden Rate
   - **Método de absorción** y **tratamiento del mes cerrado**

   Período y temporada se combinan por intersección: "YTD × ALTA" devuelve los meses de alta transcurridos; "Mes de julio × Todas" devuelve julio solo. Si la combinación queda vacía (p. ej. "Mes de julio × ALTA"), la vista lo indica en lugar de mostrar ceros.

   **Bloque A — Vista porcentual** (formato del resumen actual aprobado, ahora dinámico y con las dos capas de comisión):

   | Departamento | Costo del Departamento | Overhead | Fee | Margen Integral | Descuento Máximo | Comisión máx. Capa 1 (cubre CTI) | Comisión máx. Capa 2 (CTI + margen protegido) |
   |---|---|---|---|---|---|---|---|

   Las dos últimas columnas salen de §4.8 y llevan el gross-up por departamento aplicado. El encabezado debe indicar el margen protegido vigente y el factor neto usado en cada fila, porque sin eso las cifras no son auditables.

   Se conserva el formato porque es el lenguaje que la Junta ya aprobó y concilia con el P&L. **Lleva advertencia visible:** estos porcentajes sirven para leer el P&L y para fijar techos de comisión, no para fijar pisos de precio (§1). En vista mensual el overhead como % del revenue oscila fuertemente entre meses; es efecto del denominador, no de la estructura.

   **Bloque B — Vista en dólares por driver** (la que se usa para negociar):
   costo por habitación-noche, por noche-huésped de F&B, por pax de tour, por traslado, por tratamiento de spa. Cada uno partido en variable / fijo departamental / overhead. Más los cuatro pisos de la habitación-noche a la comisión seleccionada.

   **Bloque C — Golden Rate** (§4.7): siempre anual, con y sin capital, a la comisión seleccionada, y el índice estacional aplicado. Se muestra junto al ADR real del período seleccionado, con la brecha en dólares.

   **Pie — calidad del dato:** cuántas cifras se apoyan en ACTUAL y cuántas en FORECAST, PRORRATEO o ESTIMADO; fecha de última corrida y período fuente. Si alguna cifra crítica no es ACTUAL, se indica en el encabezado.

   Es una vista **derivada**: no acepta entradas ni recalcula por su cuenta. Todo viene de los sub-tabs 6 a 9. Se construye al final, pero se presenta de primero.

**Base (input)**
2. **Parámetros** — temporadas, fee, comisiones por canal, margen protegido, método de absorción, tratamiento del mes cerrado, crédito de sustainability.
3. **Master Data** — P&L mensual por departamento. Sólo lectura, trazable a FinPlan.
4. **Drivers y volúmenes** — todos los denominadores, con marcado de origen y de huecos.
5. **Clasificación fijo/variable/escalonado** — % por línea de gasto. Comparte criterio con el módulo Break-E.

**Motor**
6. **Costos unitarios** — matriz departamento × temporada, partida en variable / fijo / overhead+fee.
7. **Absorción** — los cuatro métodos lado a lado; drivers del método híbrido; tratamiento A vs B del mes cerrado.
8. **Pisos por servicio** — Pisos 1 a 4 en dólares por unidad, por temporada.
9. **Escalones** — tabla de umbrales y costos incrementales.

**Aplicación**
10. **Costo del paquete** — ensamblador del grupo.
11. **Desplazamiento** — ocupación proyectada por fecha y contribución desplazada.
12. **Simulador** — tamaño, noches, fechas, canal, precio propuesto → margen y semáforo.
13. **Salida a Ventas** — precio mínimo por pax por paquete y temporada. **Sin costos visibles.**
14. **Validación** — reconciliaciones y bitácora de datos faltantes.

---

## 6. Validación obligatoria

Ninguna corrida se publica sin pasar estos controles:

1. **Reconciliación de costos:** Σ (costo unitario × volumen) por departamento y mes = costo del P&L. Tolerancia $1.
2. **Reconciliación de overhead:** Σ overhead asignado por cualquier método = overhead total. Tolerancia $1.
3. **Cuadre de capacidad:** Σ hab_disponibles de los 12 meses = 10,020 (o el disponible real del año).
4. **Control del Management Fee:** el archivo fuente reporta $97,727.16 = **3.21%** del revenue; la política usa **3.00%** = $91,458.64. **Diferencia $6,268.52 sin explicar.** Finanzas debe confirmar si corresponde a base distinta, ajustes de períodos anteriores o timing contable antes de usar los pisos en contratos.
5. **Coherencia estacional:** ningún costo unitario variable debe variar más de ±15% entre temporadas sin explicación documentada. El costo de venta de F&B por noche-huésped se mantuvo en $34.74–$35.77 entre cubos; una desviación mayor indica error de volumen, no de costo.
6. **Prueba de no-circularidad:** aplicar un descuento de 20% al precio y verificar que el piso **no** se mueve. Si se mueve, hay un porcentaje sobre revenue infiltrado en el cálculo.
7. **Coherencia de la comisión máxima:** en todo departamento con factor neto 1.0, la Comisión máx. Capa 1 debe ser idéntica al Margen Integral. Cualquier diferencia indica gross-up mal aplicado o doble descuento de comisión.
8. **Reconciliación de la Golden Rate:** Σ (Golden Rate estacional × hab. ocupadas proyectadas de esa temporada) = Golden Rate anual × hab. ocupadas anuales. Si la suma da menos, el año no cierra y el índice estacional está mal calibrado.

---

## 7. Valores semilla para la primera corrida

Derivados de YTD abril 2026 (enero–abril). Sirven para validar que el motor reproduce los números conocidos; **se reemplazan por el cálculo mensual apenas FinPlan entregue los doce meses.**

| Concepto | Valor | Verificación |
|---|---|---|
| Costo propio Habitaciones / hab. ocupada | $106.46 | coincide con "Cost per Occupied Room" del archivo fuente |
| F&B costo de venta / noche-huésped | $35.77 | estable entre temporadas |
| F&B costo propio / noche-huésped | $71.04 | |
| Tours costo de venta / noche-huésped | $21.91 | |
| Transporte costo propio / hab. ocupada | $30.80 | coincide con "Total Cost Per Occupied Room" |
| Overhead / hab. disponible-noche (anual) | $216.20 | tratamiento B |
| Sustainability Fee / hab. ocupada-noche | $92.12 | $48.81 por noche-huésped |

Volúmenes base: 3,600 hab disponibles, 2,587 ocupadas, 4,883 noches-huésped, 71.86% ocupación, ADR $607.22.

---

## 8. Decisiones pendientes y huecos de datos

Bloquean la publicación de pisos firmes. Cada uno debe resolverse o quedar marcado como supuesto visible.

| # | Tema | Estado | Impacto si no se resuelve |
|---|---|---|---|
| 1 | **Sustainability Fee** — $238,325 con cero costo asignado. Existe un bloque "Innoceana and Tours Combined" en `COSTOS_2026_YTD_Abril_2026.xlsx` enteramente en `#REF!`. Si el aporte a conservación es la contrapartida del fee, **el fee no es margen libre** y no puede acreditarse contra el piso. | **Sin resolver.** Default `sustainability_libre = NO`. | Sobrestima el margen del grupo en hasta $92 por habitación-noche. |
| 2 | Tratamiento del Sustainability Fee en la asignación de overhead: hoy absorbe $58,406 sin costo. Opciones: (a) mantener como está, (b) excluir de la base — sube la tasa de 24.51% a 26.59% y resta 2.1 pp de margen a todos, (c) pegarlo a Habitaciones — Rooms sube a 57.4% y nadie más se mueve. **Recomendación: (c).** | Pendiente de decisión. | Sólo afecta la vista de conciliación; los pisos por driver son inmunes. |
| 3 | **Diciembre 2025 actual** ausente. | Pendiente. | ALTA es un ciclo de cuatro meses, no cinco. |
| 4 | **Overhead mensual real** por componente. Si viene prorrateado en doceavos, el peso estacional es supuesto. | Pendiente. | ALTA y MEDIA dan absorción idéntica artificialmente ($198 vs $198). |
| 5 | **Volúmenes de Spa** (tratamientos) y **Tienda** (transacciones). | Ausentes. | Sin costo unitario real; sólo prorrateo sobre noches-huésped. |
| 6 | **Tours por salida y por pax**, propios vs tercerizados. | Ausente. | El promedio departamental mezcla economías distintas; imposible fijar mínimo por salida. |
| 7 | **Traslados por vehículo y ruta.** | Ausente. | No se puede modelar el escalón del vehículo adicional. |
| 8 | **Mes de cierre** — la aritmética indica octubre. | Por confirmar. | Cambia el tratamiento A y la lectura de la baja. |
| 9 | `#REF!` generalizados en el archivo de costos (bloques Innoceana, tours combinados, uniform laundry). | Sin resolver. | Cadenas de costo rotas en el origen. |

---

## 9. Orden de implementación

| Fase | Entregable |
|---|---|
| 1 | Carga mensual (`fact_pl_mensual`, `fact_overhead_mensual`, `fact_volumenes`) + `cfg_temporadas`. Correr validaciones 1–3. |
| 2 | Costos unitarios y absorción (sub-tabs 6–7). Comparar contra valores semilla §7. |
| 3 | Pisos y escalones (8–9). Correr validación 6 (no-circularidad). |
| 4 | **Golden Rate** (§4.7) e índice estacional, y **comisión máxima por capas** (§4.8). Correr validaciones 7 y 8. |
| 5 | **SUMMARY COST** (sub-tab 1) con los tres selectores y los bloques A, B y C. Pasa a ser la vista de entrada del tab. |
| 6 | Ensamblador, desplazamiento y simulador (10–12). |
| 7 | Salida a Ventas (13) — sólo después de cerrar los huecos 1, 3 y 4 de §8. |
| 8 | Revisión trimestral: recalibrar con actuals y revisar el mapa de temporadas. |

---

*Los costos unitarios, volúmenes y valores semilla provienen de los archivos fuente de CWL. Los pisos, márgenes protegidos, zonas de aprobación, escalones y reglas de desplazamiento son propuesta de gestión y requieren aprobación antes de aplicarse a contratos.*
