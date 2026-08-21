# Decisiones que solo puede tomar el owner

> **Última revisión: 2026-08-15.** Acá está **solo lo que necesita tu respuesta**.
> Nada de esto lo puede resolver el sistema, y ninguno se destraba escribiendo
> código. El trabajo de código abierto vive en [`PENDIENTES.md`](PENDIENTES.md).
>
> Cada punto dice **cuánto vale**, **qué se mueve** y **qué pasa si no decidís**.
> Si un punto no tiene monto, es porque hoy vale cero y la decisión es barata
> justamente ahora.

---

## 0. Lo decidido el 19 y 20 de agosto de 2026 ✅

Ocho decisiones, todas ya construidas. Se listan para que nadie las vuelva a
preguntar.

| # | Decisión | Dónde vive |
|---|---|---|
| 0.1 | **Los grupos se negocian DESDE la tarifa rack** — la salida es `descuento_max = 1 − piso/rack` | tab `Cost` |
| 0.2 | Los costos salen del **Forecast Working 2026**; las tarifas se copiaron del **Budget 2027** y se editan aparte | `escenario_base` y `escenario_tarifas` |
| 0.3 | **Período cerrado: avisar, no bloquear.** El corte avanza SOLO al importar, así que bloquear haría fallar siempre el segundo import del mismo mes | `docs/GUILLERMO.md` §6 |
| 0.4 | **Extender `mapeo_origen`**, no crear `mapping_rules` aparte | mig 134 |
| 0.5 | **D-1 · el manifiesto**: XML de Operations y Marketing todos los días; actuales del GL y Balance Sheet una vez al mes | `app/seed_guillermo.py:MANIFIESTO` |
| 0.6 | **D-8 · todo auxiliar contra el GL**, en todos los tabs, cada despliegue | `app/guillermo/cuadre.py` |
| 0.7 | **El recálculo NO corre en cada guardado** — botón, «podría hacer 30 actualizaciones» | `Admin → Guillermo` |
| 0.8 | **Tres niveles de capacidad**: bajo · medio · alto. ⚠️ En los tres, una propuesta del modelo va a la cola: lo que crece es *cuándo actúa*, no *qué decide solo* | `app/guillermo/core.py:NIVELES` |

---

## 1. ~~La cuenta `8090`~~ ✅ **CERRADO 2026-08-15 — queda como está**

Owner: «el problema de esto es que vive en una **no cuenta**… solo desaparece si
vuelvo a subir 2024. Cerremos esto así: por ahora dejemos tal cual está. Si yo lo
subo, decido qué cambio hacer».

Y es la lectura correcta: la `8090` «Financial Losses (ajuste recon.)» **no existe
en el catálogo contable** — la fabricó `scripts/ajuste_cuadre_2024.py` para cuadrar
el año. No es una cuenta a la que le falte una regla: es un asiento de ajuste que
sobrevive al año que lo necesitó. Darle regla sería institucionalizarlo.

**No se toca.** Sigue en `DROP`: −$43.698,37 en el `Actual 2024` y +$98,16 en el
`2025`, sin llegar a ningún reporte. Se resuelve sola cuando el owner vuelva a
subir el 2024, y ahí decide.

⚠️ Lo único que queda dicho para el que lea esto después: el motor viejo
(`NONOP_ACCOUNT_LINE` en `pl_engine.py`) sí la manda a `FINANCIAL_LOSSES`. Los dos
caminos dicen cosas distintas sobre la misma cuenta. Como el dato es transitorio,
no se unificó — pero si alguien alguna vez hace que el sistema lea por el motor
viejo, ese ajuste reaparece.

---

## 2. ~~Cuál hoja manda en el `Actual 2024`~~ ✅ **CERRADO 2026-08-15 — queda como está**

Owner: «tal cual está, así lo dejamos». Los +$40.613 de Rooms y los −$3.085 de
Innoceana se quedan como están hoy.

---

## 3. ~~El mix aplica de **2027 en adelante**~~ ✅ **CERRADO 2026-08-15 — los seis presupuestos**

Owner, 2026-08-15: «hagamos que el mix y todos los cambios que se hicieron
apliquen para 2027 en adelante».

**Hecho** (migración 116): `BUDGET Draft1`, `Draft2`, `Draft3`, `Draft4-BIG` y
`Final` de 2027 pasaron de `checkbook` a `drivers`. El sexto —el `Working
2027`, que el Club retenía— entró con la **117**, abajo. El ingreso ya no son montos
digitados: sale de **tarifas × ocupación**, y el mix lo maneja.

### Lo que se movió, y de dónde sale

Los cinco son la misma carga, así que dan el mismo número:

| | antes (digitado) | ahora (drivers) | cambio |
|---|---|---|---|
| Ingresos | 5.997.346 | 5.826.131 | **−171.215** (−2,9%) |
| GOP | 2.842.543 | 2.671.328 | −171.215 |
| EBITDA | 2.662.623 | 2.496.544 | −166.078 |
| Utilidad neta | 1.567.716 | 1.455.588 | **−112.128** |

**Todo el cambio es el mix. Nada es tarifa ni ocupación**, y eso está medido, no
supuesto:

| | antes | ahora |
|---|---|---|
| noches ocupadas | 4.981,8 | 4.981,8 — *idéntico* |
| pax | 8.967 | 8.967 — *idéntico* |
| venta a tarifa **rack** | $4.331.219 | $4.331.219 — *idéntico* |
| **Net Factor** | **0,8220** | **0,7970** |

El checkbook había quedado congelado con el factor de antes del mixer. Los
drivers usan el de hoy. La venta bruta no se movió ni un dólar: lo que cambió es
cuánto se queda la casa después de comisión.

⚠️ **La vieja estimación de −$181.000 no era el número.** Quedó cerca, pero
estaba calculada como si el factor ya manejara el ingreso —no lo hacía—. El
número real es **−$171.215 por escenario**.

### El Club Madresal en el `BUDGET Working 2027` — *decidido y aplicado*

> «No sé qué está pasando… **solo quiero que trabaje estándar como todos los
> departamentos**.» — 15-ago

**Hecho** (migración 117): el `BUDGET Working 2027` pasó a `drivers` y ya no hay
excepción. Era el único de los seis que quedaba afuera.

#### Qué le faltaba al motor

Nada del Club en particular: **le faltaba una lista**. En modo `drivers` el motor
deriva Habitaciones, Food, Beverage, Tours, Transporte y Sustainability de
tarifas × ocupación, y las demás líneas las lee de una tabla de montos
mensuales… pero con una lista escrita a mano de cinco (Spa, Retail, F&B
misceláneo, Innoceana, Lavandería). El Club no estaba en esa lista, así que su
driver depositaba el ingreso en el **checkbook** —la fuente del *otro* modo— y en
modo `drivers` ese ingreso no existía. Sin error, sin nada en los logs.

Hoy la lista **se deriva** de las líneas de ingreso del sistema, así que un
departamento nuevo llega al P&L sin que nadie se acuerde de agregarlo; y todo
driver deja su resultado en **las dos fuentes**, por un único camino compartido.
Un departamento ya no tiene que saber en qué modo está su escenario.

#### El Spa tenía lo mismo

Y se tapó con el mismo mecanismo, no con un parche aparte. Su ingreso también
aterrizaba solo en el checkbook: en un escenario en modo `drivers` se guardaba y
el P&L no lo veía. Hoy pasa por el mismo camino. **Sus números no se movieron**
—solo cambia dónde aterriza el próximo guardado—.

#### Lo que se movió

Un solo escenario. Los otros diecinueve quedaron idénticos línea por línea.

| `BUDGET Working 2027` | antes | ahora | cambio |
|---|---|---|---|
| Ingresos | 6.449.238 | **6.374.026** | **−75.212** |
| GOP | 2.799.112 | 2.723.900 | −75.212 |
| EBITDA (antes de capital) | 2.503.634 | 2.430.679 | −72.956 |
| Utilidad neta | 1.180.322 | 1.133.549 | −46.773 |
| **REV_CLUB** | **125.180** | **125.180** | **0 — intacto** |
| **PROFIT_CLUB** | **−228.471** | **−228.471** | **0 — intacto** |

Los −75.212 son dos cosas, y solo dos:

* **−118.218 el mix**, todo sobre Room Revenue (Net Factor 0,8220 → 0,7970);
* **+43.006 la ocupación**: 4.981,8 → 5.215,6 noches, porque el escenario tiene
  **ocho** tipos de habitación cargados contra los **seis** con que se congeló su
  checkbook. Eso sube food, beverage, tours, transporte y sustainability.

El Club aporta cero al cambio, que era exactamente el punto.

### Los 2028–2035

Ya estaban en `drivers` y siguen así. Están vacíos, o sea que **nacen con el
modelo nuevo**. Un escenario creado de cero también nace en `drivers` (es el
default del sistema); uno creado **copiando** hereda el modo del original, que es
a propósito — una copia tiene que dar los mismos números que su origen.

## 3.b. ~~El impuesto en el veredicto Resumen vs Detalle~~ ✅ **CERRADO 2026-08-16 — no se toca**

Owner: «**no muevas nada en lo que se subió, dejá igual los taxes… no recalcules
nada**».

`PENDIENTES.md` A0.-2 dejaba abierto «decidir si el validador compara o excluye
el impuesto». Se probó excluirlo —la regla ya existía escrita en
`importers/verificacion.py`— y **se midió antes de proponerlo**: excluirlo hacía
que el `FORECAST April 2026` pasara a reportar desde el Detalle, y eso arrastraba
**cuál de los dos impuestos se reporta**:

| | antes | con el cambio |
|---|---|---|
| `INCOME_TAXES` | 39.197,30 (el subido) | 21.316,20 (el del motor) |
| `NET_PROFIT` | −40.189,78 | −22.308,68 |

O sea **$17.881,10 de utilidad neta** en un escenario `locked`, más 55 líneas que
se re-expresan al cambiar de base. **Revertido y verificado**: el `April 2026`
sigue mandando por Resumen con su provisión, y `quien_manda` da lo mismo que
está desplegado.

**La regla, ampliada:** «en los históricos solo vale lo subido» **incluye el
impuesto**. El motor puede calcularlo para un presupuesto, pero no reemplaza el
que vino en un archivo. Cualquier propuesta futura que mueva un número de un
escenario subido —aunque sea «para que quede consistente»— **ya está contestada
acá**.

⚠️ Consecuencia aceptada: el `April 2026` cuenta con un criterio distinto que los
otros cinco históricos. Es a propósito.

---

## 4. ¿El diferencial cambiario va como renglón propio del P&L?

Hoy comparte cajón con los intereses. Separarlo es presentación, no números.

---

## 5. Los repartos que no netean exacto — *ya dijiste que quedan como están*

Tres celdas, solo en el `Actual 2025`: Cafetería `0220` julio +685,93 y diciembre
−230,26; Lavandería `0161` diciembre −357,51. Y el `Actual 2024` no tiene reparto
de Cafetería ni de Lavandería. Como no vas a volver a subir Corcovado, queda así
salvo que digas lo contrario. Los demás escenarios cierran en cero.

---

## 6. Cuatro cambios que dependen de contabilidad, no tuyos

Las cuentas **ya están habilitadas en el sistema y en cero**. El día que
contabilidad empiece a usarlas, entran solas — no hay trabajo de código
esperando.

| qué |
|---|
| Partir la `4000` en Room Revenue / Cancellations / No Show |
| Llenar los Outlets 2, 3 y 4 de A&B |
| Separar Licor y Vino de `Beer1`, en ingreso **y** en costo |
| Resolver el doble uso de la `5102` (traslado vs Food Cost 2) |

---

## Lo que YA decidiste y no hace falta volver a mirar

| decisión | fecha | dónde quedó |
|---|---|---|
| El On the Books compara **un** escenario; el resto sale del XML, sin semanas | 18-ago | Cerrado. La barra pasó de 4 desplegables (Budget · OTB en · from · to) a **Escenario + dos fechas**. «OTB en» era una trampa: podía apuntar a otro escenario y comparaba el presupuesto de uno contra las reservas de otro sin avisar |
| El `$6.315.043` del OTB **no era de ningún escenario** — y tenías razón | 18-ago | Cerrado. Era la suma de los 3 años del mismo XML (2026 $4.513.865 + 2027 $1.772.782 + 2028 $28.396 = $6.315.043,09, al centavo). El archivo trae 1.826 días = 5 años. El import ahora reporta **año por año**. ⚠️ Mi primer diagnóstico —que el importador contaba cada día dos veces— **estaba equivocado** |
| `0240` y `0250` son el mismo departamento — inactivar el que no tiene reglas | 14-ago | Cerrado: se movió el dato, el `0240` ya no existe |
| «`0250` no hay planilla, solo gastos de la propiedad» | 14-ago | Cerrado: el `0250` es el espejo del `280` |
| Las cuentas de servicios son **Utilities**; todo lo demás va a **Claro del Bosque** | 14-ago | Cerrado moviendo el **dato** (7 cuentas, `0205 → 0210`), no las reglas. La `7105` se quedó: es compartida por 11 departamentos, no es de Utilities |
| `0180` es la madre; `0181` y `0184` solo planilla | 14-ago | **Cerrado en los dos.** El `0181` se queda en Administración y perdió su set de gastos entero |
| Ningún hijo lleva gastos operativos; el gasto es del padre | 14-ago | Cerrado, con prueba que lo cuida. El desplegable de Opex ya no los ofrece |
| El `0121` Private Bar es **principal**, no hijo | 14-ago | Ya lo era; se queda en el checkbook de gastos |
| `0162` es el ingreso de lavandería y `0161` el gasto | 14-ago | Cerrado. Al sacarle las reglas de gasto se fue de más la `5301`, que es donde el **motor** deposita el costo de huéspedes: sin ella $6.604,12 se contaban como costo del Spa. Se devolvió (mig. 115) y el `0162` sigue fuera del checkbook — las cuentas de reparto ya no lo habilitan |
| El Private Bar es un centro de utilidad **aparte**, no un outlet de A&B | 12-ago | Cerrado, con prueba que lo cuida |
| La Tienda y el Gift Shop son **dos locales distintos** | 11-ago | Cerrado, línea propia cada uno |
| Área Recreativa es **centro de costo**, no departamento operativo | 11-ago | Cerrado |
| El orden de la plantilla es **tu archivo**, no una regla del sistema | 14-ago | Cerrado |
