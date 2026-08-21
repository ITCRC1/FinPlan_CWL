# El mixer de canales — propuesta para revisar

Fecha: 2026-08-14. Para decidir en vivo con el owner.

> «El primero es planteamiento general, y después hay que hacer un mixer para
> derivar las otras.» — «Hay que ver cuál sería la base de arranque: si con lo
> que tiene ahorita el app o si hay que ampliarla para que el mixer funcione
> mejor.»

---

## 1. Qué hay hoy, medido

Tres listas de canales, cada una contestando otra pregunta:

| Lista | Pregunta | Tamaño | Dónde vive |
|---|---|---|---|
| Market codes de Opera | ¿cómo entró? | 13 códigos → 5 canales | `market_codes` (nuevo) |
| Sub-canales comerciales | ¿quién cobra? | 7 | `canales_comerciales` (nuevo) |
| Canales de comisión | ¿cuánto pago? | 3 (TA/OTA/DIRECT) | `sales_channel_configs` |

Y esto es lo que dice la base de producción sobre la tercera:

```
escenario                    canales  meses   ¿varía por mes?
BUDGET Final 2026                  3      1   no, los 12 iguales
BUDGET Draft1..Final 2027          3     12   no, los 12 iguales
BUDGET Working 2027                3     12   no, los 12 iguales
FORECAST (todos)                   —      —   NO TIENE NADA GUARDADO
```

Tres cosas que importan para la decisión:

1. **Nadie usa la variación por mes.** Los 12 meses son idénticos en los 7
   escenarios. La capacidad existe y está sin usar: son 252 filas que dicen lo
   mismo.
2. **Budget Final 2026 tiene UN solo mes guardado.** Los otros once no están.
3. **Ningún Forecast tiene configuración guardada** — la pantalla dice
   «Suggested default values — Save to pin them», o sea que corre con valores
   por defecto que nadie fijó.

---

## 2. Lo que el mixer ya calcula

Con el mix de Corcovado y las comisiones del cuadro del owner:

| Sub-canal | Mix | Comisión | Rueda a |
|---|---:|---:|---|
| B2B — agency / DMC / TO | 55% | 30% | TA |
| Direct — website / booking engine | 15% | 10% | DIRECT |
| Direct — phone / email / social | 10% | 7% | DIRECT |
| Costa Rica Collection direct | 7% | 10% | DIRECT |
| Direct groups | 6% | 10% | DIRECT |
| Executive personal direct | 3% | 10% | DIRECT |
| OTA | 4% | 0% | OTA |

Derivado:

| | Hoy en FinPlan | Con el mixer |
|---|---|---|
| TA | 60% al 28% | **55% al 30%** |
| OTA | 5% al 20% | **4% al 0%** |
| DIRECT | 35% al **0%** | **41% al 9,27%** |
| **Net Factor** | **0,8220** | **0,7970** |

La comisión de DIRECT es el promedio **ponderado por mix**, no el simple: con el
simple, la ejecutiva —que trae el 3%— pesaría igual que el website —que trae el
15%— y la comisión saldría más alta de lo que se paga.

**Impacto en plata**, sobre el ingreso de habitaciones de cada escenario:

| Escenario | Rooms | Impacto |
|---|---:|---:|
| Budget Final 2026 | 2.604.397 | **−79.209** |
| Budget Draft1 2027 | 3.560.261 | **−108.280** |
| Actual 2026 (a la fecha) | 1.706.130 | −51.890 |

⚠️ La causa es una sola: **FinPlan cree que la venta directa no cuesta nada.**
Tiene `DIRECT` en comisión 0% y el cuadro del owner dice 7%–10%. Como el Net
Factor multiplica el ingreso de habitaciones de todo el presupuesto, esos 79 mil
nunca se vieron: cada tabla se veía razonable por su lado.

---

## 3. La base de arranque: qué falta

Para que el mixer funcione hay que resolver **dónde vive el mix de los
sub-canales**. Hoy `canales_comerciales` guarda la comisión pero **no el mix**, y
el mix vive en otra app (Compensación), por propiedad.

### Lo que hay que agregar

| Qué | Por qué |
|---|---|
| **Mix por sub-canal, por escenario** | El mix de un Budget 2027 no es el de un Actual 2026. Hoy la comisión es global y eso ya es una limitación. |
| **Comisión por sub-canal, por escenario** | El owner renegocia. Una comisión global obliga a que el 2027 y el 2026 tengan la misma, que es falso. |

### La decisión de fondo: ¿por mes o por año?

**Recomiendo por AÑO, con excepción por mes.** Una fila por sub-canal por
escenario con el valor anual, y la posibilidad de pisar meses concretos.

* A favor: nadie usa hoy la variación mensual —está medido, los 12 meses son
  iguales en los 7 escenarios—. Con 7 sub-canales, pasar a mensual son **84
  celdas por escenario** en vez de 7, para un dato que en la práctica no cambia.
* La pantalla actual dice «algunos canales pueden cambiar su rate en ciertos
  meses», así que la excepción tiene que existir — pero como excepción explícita,
  no como obligación de llenar 84 casillas.
* Es el mismo patrón que ya usan el rolling forecast (`actuals_through`) y la
  matriz de cobro del cash flow: el caso normal es simple y la excepción se
  declara.

### Qué pasa con la tabla de los 3

Pasa a ser **derivada y de solo lectura**. Hoy es donde se digita; con el mixer
es el resultado. Eso elimina de raíz el problema de las tres listas: **una se
planifica, las otras se calculan**.

⚠️ Con una salvedad: los escenarios enllavados. Su `sales_channel_configs`
guardado es parte de una foto histórica y **no se toca**. El mixer aplica a los
que están en borrador; para un enllavado se muestra el derivado al lado del
guardado, para poder comparar sin reescribir el pasado.

---

## 4. Lo que sigue siendo de dos ejes, y no lo arregla el mixer

De los 7 sub-canales, **4 describen por dónde entró** la reserva (B2B, website,
teléfono, OTA) y Opera lo sabe. Los otros **3 describen quién la trajo** —Costa
Rica Collection direct, Direct groups, Executive personal direct— y **el PMS no
registra eso**: una reserva con market code `DIR` puede haber entrado por
teléfono, haberla traído la ejecutiva o venir de CRC, y el código es el mismo.

Para el **mixer no es problema**: los tres son venta propia y ruedan a `DIRECT`
igual. Se vuelve problema el día que se quiera **comparar el plan contra lo que
de verdad pasó por sub-canal**, porque Opera no puede decir cuál de los tres fue.
Eso hay que digitarlo, o sacarlo de un campo de agente del PMS.

---

## 4b. ⚠️ Lo que apareció al medir: las tarifas le ganan al mix

El motor de revenue prefiere el factor efectivo de las tarifas
(`net_rate / rack_rate`) **sobre** el mix de canales. Medido en producción:

```
escenario                    gobierna  manda      nf tarifas   nf mix
BUDGET Final 2026                  no  TARIFAS        0.8360   0.8220
BUDGET Draft1..Final 2027          no  TARIFAS        0.8220   0.8220
BUDGET Working 2027                si  TARIFAS        0.8220   0.8220
BUDGET Working 2028..2035          si  -                   -        -
```

**En todos los escenarios que tienen datos manda la tarifa.** O sea que aplicar
el mixer escribiría las tres filas y **no movería un solo número**: un no-op
silencioso, la misma clase de error que este sistema ya sufrió varias veces.

Por eso «Aplicar» tiene una casilla aparte, **Regenerar también la tarifa neta**
(`rack × factor`), apagada por defecto — pisar la tarifa neta que vino del Excel
se decide, no se hereda. Y hay una prueba que fija esa precedencia, para que
nadie la invierta sin darse cuenta.

Dos cosas más que salieron de la misma medición:

* **Budget Final 2026 ya tiene las dos fuentes peleadas**: sus tarifas dicen
  0,8360 y sus canales 0,8220. Gana la tarifa.
* **Cinco de las versiones 2027 están enllavadas** (Draft1, Draft2, Draft3,
  Draft4-BIG y Final). El mixer las salta y dice por qué. De 2027 solo
  *Working* queda dentro. Si tienen que entrar, hay que desenllavarlas primero —
  y eso lo decide el owner.

---

## 5. Preguntas para el owner

1. **¿El mix de tu cuadro es el que manda?** No solo cambia la comisión: hoy
   FinPlan tiene 60/5/35 y tu cuadro da 55/4/41.
2. **¿La OTA de verdad no te cobra?** Tu cuadro dice 0% y FinPlan usa 20%.
   Sospecho que son dos cosas distintas —tarifa neta contra comisión— pero una de
   las dos está mal para el cálculo.
3. **¿Por año o por mes?** (recomendación: por año con excepción)
4. **Los Forecast no tienen nada guardado.** ¿Se les fija el mix, o se quedan con
   los valores por defecto?
5. **Budget Final 2026 tiene un solo mes cargado.** ¿Se completa?
6. **¿Se desenllavan las cinco versiones 2027?** Dijiste «todas las versiones
   desde enero 2027», pero Draft1, Draft2, Draft3, Draft4-BIG y Final están
   enllavadas y el mixer no las toca.
7. **¿Se regeneran las tarifas netas?** Es lo único que hace que el cambio
   llegue al número. Sin eso, aplicar no mueve nada.
