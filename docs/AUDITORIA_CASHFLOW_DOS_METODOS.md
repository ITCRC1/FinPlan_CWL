# Auditoría — Cash Flow Directo vs Indirecto

**Objetivo:** que los dos métodos usen la misma metodología y que se pueda
determinar dónde está cada diferencia.

**Estado: CONCILIADO.** La brecha máxima es de **6 centavos** (redondeo a dos
decimales), sobre los ocho escenarios vivos de CWL — incluidos los que tienen
meses reales, los que tienen el modelo de timing apagado y las versiones
enllavadas.

| | Antes | Después |
|---|---|---|
| Brecha máxima en el año (Budget 2027) | **$285,652** (enero) | **$0.06** |
| Brecha de caja final | $215 (por compensación de errores) | $0.06 |
| Criterios que llegaban a los dos métodos | 5 de 24 | **24 de 24** |

---

## 1. El cambio de fondo

El problema no era un parámetro mal puesto: **eran dos modelos distintos del
mismo hotel.** El método directo tenía su propio modelo de cobro, su propia base
de cuentas por pagar, su propio IVA y una nómina reconstruida desde cero. Trece
divergencias salían de ahí.

Ahora el **directo es una presentación del mismo calendario de caja que arma el
indirecto**. Para cada mes se cumple, por construcción:

```
Cobros − Pagos  ≡  NOI − CapEx + Δ(Working Capital)
```

El directo lo muestra al derecho —de la venta al cobro, del gasto al pago— y el
indirecto como ajustes sobre el resultado. Son la misma plata contada dos veces
de dos maneras, que es lo que siempre debieron ser.

Además, el directo consume los **movimientos finales** del indirecto, no una
recalculación propia. Eso importa porque esos movimientos no siempre vienen del
modelo: en meses cerrados salen del Balance Sheet real, pueden estar pisados a
mano celda por celda, o venir de un driver. Por eso ahora concilian también los
escenarios con datos reales, que antes no podían coincidir ni en teoría.

---

## 2. Registro de hallazgos

Tipo: **P** permanente (cambia el total del año) · **T** de timing · **B** de borde.

### Corregidos

| # | Hallazgo | Tipo | Qué pasaba |
|---|----------|------|-----------|
| **1** | **Aguinaldo contado dos veces** | P | El directo restaba del OPEX solo el salario imponible, así que la CCSS, el aguinaldo y otros ocho conceptos quedaban dentro del bucket de proveedores — y encima volvía a pagar el aguinaldo entero en diciembre. **≈$148,115/año duplicados.** |
| **2** | **CCSS patronal tratada como deducción al empleado** | T+P | `neta = bruto − ccss` le restaba al salario la carga *patronal*, y la reponía rezagada un mes. La CCSS de diciembre no se pagaba nunca. |
| **3** | **Rezago de entrada del gasto** | B | El directo cobraba mirando al año anterior pero pagaba como si el año empezara en cero: enero no pagaba la cola de la factura de diciembre. **La causa aritmética de los $285,652.** |
| **4** | **Nómina de departamentos sin línea equivalente** | P | El emparejamiento nómina↔OPEX era por *nombre visible*. Los departamentos cuyo nombre de grupo no coincide con el de su línea (0205 «Claro Huerta», 280) se sumaban sin restarse de nada. |
| **5** | **Clamp `max(0, opex − nómina)`** | P | Cuando la nómina superaba el OPEX de la línea, el clamp no perdía: **inflaba** el gasto, y en silencio. |
| **6** | **Doble conteo de OPEX y revenue en escenarios importados** | P | El motor emite cada línea bajo su código canónico y bajo su alias, con el mismo nombre visible. El directo fundía por nombre y sumaba las dos. **100% de sobrecosto** en escenarios de snapshot. |
| **7** | **Management fee reconstruido** | P | El directo descartaba las líneas `MGMT_FEE`/`ROYALTIES` del P&L y las recalculaba como % de ventas, con un default del 5% contra el 3% real. **Hasta +$119,947/año.** |
| **8** | **IVA de «otros gastos» pagado y nunca acreditado** | P | `iva_otr` se pagaba en caja y faltaba en la suma del crédito. **≈$13,260/año** que salían y no volvían. |
| **9** | **`max(0, …)` destruía el crédito de IVA** | P | En un mes con saldo a favor el directo pagaba 0 y **perdía el crédito**: no lo arrastraba. La ley CR reconoce el arrastre. |
| **10** | **Base de A/P e IVA incompatibles** | P | Indirecto: OPEX+OVERHEAD+NON_OP sin IVA, con la planilla adentro. Directo: solo OPEX, con IVA, sin el bloque non-op. |
| **11** | **Seguros y alquiler con reglas distintas** | T | Semestral con IVA en uno, mensual por A/P en el otro, para el mismo gasto. |
| **12** | **`ap_same_pct` 60% vs 70%** | T | Defaults distintos para el mismo criterio. |
| **13** | **Retenciones de tarjeta 2.5% vs 0%** | P | Ídem. El directo no retenía nada si el criterio no estaba guardado explícitamente. |
| **14** | **`card_comision` reactivable** | P | Seguía viva en `DIRECT_DEFAULTS` (1.95%) y podía volver a aplicarse, duplicando la comisión que ya está en el P&L (cuenta 7120). |
| **15** | **El interruptor «Modelo de timing ACTIVO» solo apagaba el indirecto** | P | El directo leía los parámetros sin mirar el flag. Con el modelo apagado, una pantalla cobraba con la matriz y la otra no. Budget 2028 estaba exactamente así. |
| **16** | **Guardar la pantalla del directo congelaba los criterios** | P | La pantalla recibía la matriz ya resuelta y la mandaba de vuelta al guardar. Desde ese momento la condición de herencia no se cumplía nunca más: cambiar un criterio movía un método y no el otro, sin aviso. |
| **17** | **Guardar los Criterios borraba trabajo** | P | El PUT reemplazaba el blob entero: se perdían los `_overrides` (la copia de los reales de meses cerrados) y las matrices de años vecinos. Las doce filas de años vecinos de la pantalla eran decorativas — el motor las leía y siempre encontraba vacío. |
| **18** | **Cada método elegía un escenario vecino distinto** | P | El indirecto prefería el FORECAST del año anterior; el directo, el mismo tipo y versión. Para un Budget 2027 uno miraba el Forecast 2026 y el otro el Budget 2026. Ninguna de las dos consultas tenía orden determinista. |
| **19** | **Retención de anticipos y servicio F&B solo en un método** | T+B | El 5% de retención y el 10% de servicio de ley existían en el indirecto y no en el directo. |
| **20** | **`Financiamiento Requerido` inyectaba caja** | P | Un plug automático forzaba el saldo a no bajar de cero. Con un solo mes en rojo, los saldos dejaban de ser comparables. Ahora el requerimiento se informa pero no se suma. |

### Documentados, sin corregir (decisión del owner)

| # | Hallazgo | Por qué se deja |
|---|----------|-----------------|
| **21** | **La fila de enero de la matriz suma 110%** | Es un dato de los Criterios, no del código. Afecta a los dos métodos por igual (~$86,991/año de caja que no existe), así que no impide conciliar. El motor lo reporta en rojo y no lo normaliza en silencio. |
| **22** | **CCSS al 26.83% contra el 26.67% del Excel** | Afecta a los dos por igual. Es un parámetro de planilla, decisión del owner. |
| **23** | **El IVA se declara sobre el devengo, no sobre el cobro** | En CR el anticipo facturado devenga IVA al recibirse. Hoy los dos métodos lo declaran en el mes de la estadía. Cambiarlo movería los números del Cash Flow Budget que el owner ya presentó; queda como mejora de exactitud a decidir. |
| **24** | **El CapEx no genera crédito de IVA** | Un capex real se paga con IVA y da crédito. Hoy ninguno de los dos lo modela. Mismo criterio que arriba: unificado, pendiente de decisión. |
| **25** | **Intereses, leasings e impuesto de renta quedan fuera de los dos** | El flujo corta en EBITDA antes de capital. Es una subestimación compartida, no una divergencia. |

---

## 3. Qué se construyó

| Pieza | Para qué |
|---|---|
| `backend/app/engine/cashflow_criterios.py` | **Fuente única de criterios.** Un default por concepto, con los conflictos resueltos. `resolver()` decide la precedencia; `divergencias()` reporta cualquier criterio compartido que quede distinto. |
| `backend/app/api/_cashflow_criterios.py` | Carga los criterios desde la base, la ventana de años vecinos y la regla ÚNICA de escenario vecino. Lo consumen las dos APIs. |
| `cashflow_budget.wc_schedule_ventana()` | El calendario completo de caja sobre la ventana de tres años, recortado al año. Es lo que ahora comparten los dos métodos. |
| `backend/scripts/reconcile_cashflow.py` | **El puente auditable.** Corre los dos endpoints reales contra la base y emite el flujo mes a mes, los saldos, el puente por bloque, el detalle por concepto y la tabla de criterios lado a lado. |
| `backend/tests/test_cashflow_conciliacion.py` | 11 pruebas que fallan si alguien vuelve a darle al directo un modelo propio, si un criterio compartido se bifurca, o si guardar una pantalla desconecta la otra. |

### Guardas del puente

`reconcile_cashflow.py` avisa antes de comparar. Si alguna salta, la comparación
no es concluyente:

- **G1** el directo no recibió matriz de timing (cobra por el camino viejo)
- **G2** la caja proyectada queda negativa (ya no se inyecta caja, pero conviene verlo)
- **G3** una fila de la matriz no suma 100%
- **G4** caja inicial distinta entre los dos
- **G6** el modelo de timing está desactivado
- **G7** no hay escenario del año anterior (sin arrastre de cruce de año)

Uso:

```bash
python -m scripts.reconcile_cashflow <scenario_id>
```

---

## 4. Resultado por escenario

| Escenario | Año | Brecha máxima |
|---|---|---|
| Budget Working | 2027 | $0.06 |
| Budget Final (enllavado) | 2027 | $0.03 |
| Forecast Working (con meses reales) | 2026 | $0.02 |
| Actual (con balance real) | 2026 | $0.01 |
| Budget Final (enllavado) | 2026 | $0.03 |
| Budget Working (modelo apagado) | 2028 | $0.00 |
| Actual (enllavado) | 2025 | $0.02 |
| Actual (enllavado) | 2024 | $0.03 |

El residuo es redondeo a dos decimales por fila, no diferencia de método.

---

## 5. Para los demás hoteles

La conciliación ya no depende de que alguien acierte los parámetros: los
criterios son uno solo, la elección de escenario vecino es determinista y la
identidad está cubierta por pruebas. Un hotel nuevo arranca conciliado salvo que
se le carguen criterios inconsistentes — y en ese caso el puente lo dice.
