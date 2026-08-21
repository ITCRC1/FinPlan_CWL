# Pendientes — FinPlan CWL

> **Última revisión: 2026-08-14.** Escrito para arrancar en frío: cada punto dice
> qué pasa, cuánto vale y de quién depende.
>
> **Lo que necesita la decisión del owner está filtrado aparte, en
> [`DECISIONES_DEL_OWNER.md`](DECISIONES_DEL_OWNER.md).** Este archivo es el
> trabajo de código; aquel es lo que no se destraba escribiendo código.
>
> ## 🚦 REGLA DE PRECEDENCIA — leer ANTES de proponer nada
>
> **`DECISIONES_DEL_OWNER.md` le gana a este archivo, siempre.** Cuando el owner
> decide algo, ahí queda con fecha; acá abajo el punto puede seguir diciendo «no
> empezado» durante días porque nadie bajó a tacharlo.
>
> **Antes de recomendar un pendiente, buscarlo en `DECISIONES`.** El 2026-08-16
> se propuso «unir Administración» como próximo trabajo estando cerrado desde el
> 14-ago **en el mismo archivo que se acababa de leer**. Tres puntos de esta
> lista resultaron viejos ese día por la misma razón (A0.0 puntos 2 y 3, B6.2
> residual) y otros dos estaban decididos sin tacharse (la `8090` y cuál hoja
> manda en el `Actual 2024`).
>
> **Y antes de dar por abierto un punto medible, medirlo.** Casi todos los de
> acá tienen un script que los contesta en un minuto:
> `auditoria_mapeo` · `verificar_los_historicos` · `quien_manda` ·
> `quien_falta_recalcular` · `quien_usa_el_mix` · `lineas_que_faltan` ·
> `residuo_lavanderia`. Un punto sin medir no es un pendiente: es una nota vieja.
>
> ## ⚠️ Leer esto antes de tomar trabajo de acá
>
> **El Break-Even quedó cerrado del lado del código el 2026-08-17** — ver
> [A0.-10](#a0-10--break-even--cerrado-del-lado-del-código-2026-08-17). Lo que
> queda ahí es del owner, cuando quiera, y no bloquea nada.
>
> ## 📋 LISTA DEL 20 DE AGOSTO — para bajar una por una
>
> Numerada a pedido del owner. **Medida contra producción el 2026-08-20**, no
> copiada de una nota vieja. Lo decidido está en `DECISIONES_DEL_OWNER.md` §0.
>
> ### 🔴 Del owner — no se destraban escribiendo código
>
> | # | Qué | Cuánto vale | Estado |
> |---|---|---|---|
> | **1** | **Subir el RESUMEN de junio** del ACTUAL 2026 | **$199.667,97** | El detalle del mayor está; falta su otra mitad. Medido: quitando junio, los 7 totales cuadran **al centavo** |
> | 2 | Subir junio y julio de los **actuales del GL** | — | último dato: mayo |
> | 3 | Subir junio y julio del **Balance Sheet** | — | último dato: mayo |
> | 4 | Subir junio a agosto del **Channel Mix** | — | último dato: mayo. El owner no lo había notado |
> | 5 | **`ANTHROPIC_API_KEY`** en el entorno de Railway | — | sin eso la conexión con Claude no existe. No la maneja el agente |
> | 6 | **Clasificación fijo/variable** de gastos | — | ⚠️ **Re-medido 2026-08-20 y el enunciado estaba incompleto.** `cfg_clasificacion_costos` existe y **NO LA LEE NADIE**: el motor saca el variable de Rooms de la composición, Rooms no tiene línea de costo de venta en USALI, da CERO y por eso el Piso 1 cae al costo propio = Piso 2, **marcado como estimado**. Break-Even sí tiene la clasificación con pantalla, pero sus 612 reglas están **todas en 0 o 1** (semilla del mapeo: planilla = variable, 132 de 138 en Rooms al 100%). Cablear el motor a esa semilla cambiaría un «estimado» honesto por un número que parece medido: **es decisión del owner mover los porcentajes primero** |
> | 7 | Confirmar los **$6.268,52** del Management Fee | $6.268,52 | fuente 3,21% vs política 3,00%. El spec pide resolverlo **antes** de usar los pisos en un contrato |
> | ~~8~~ | ✅ **D-2 RESUELTA 2026-08-20**: XML de Opera, y los uploads en Excel | — | destraba el 19 (que ya no hace falta) y el 22 |
> | 9 | **D-4**: ¿OHIP está habilitado en la licencia? | — | bloquea la fuente automática |
> | 10 | **D-5**: quién recibe avisos y quién puede aprobar | — | el rol `guillermo_approver` existe; falta a quién dárselo |
> | 11 | **D-7**: cuántos archivos por día | — | dimensionamiento |
> | 12 | **D-9**: contra qué se mide el acierto del modo sombra | — | en sombra no se escribe: sin comparador, esa métrica no existe |
>
> ### 🟡 Decisiones del owner que no bloquean
>
> | # | Qué | Dato medido |
> |---|---|---|
> | 13 | ¿Chip de Guillermo en la barra? | cuesta **161px** y empujaría los tres escalones (1860/1990/2115). Alternativa del spec §10.3: badge en el menú |
> | 14 | ¿`PATCH /scenarios/{id}/status/` pasa a exigir admin? | hoy **cualquier colaborador enllava y desenllava**. No se cambió para no trabar a nadie sin aviso |
> | 15 | ¿Los presupuestos deben tener detalle del mayor? | **14 escenarios no se pueden verificar** contra el GL sin él |
> | 16 | ¿33 o 30 habitaciones? | el Revenue Checkbook cuenta villas y residencia (**12.045**); el resto de la app usa 30 (**10.950**) |
>
> ### 🟠 Tres pantallas que todavía se escriben SIN exigir admin
>
> Medido el 2026-08-20 al mover la configuración a Admin. El mapeo ya quedó
> cerrado —ahí **mover UNA cuenta de $6.500 re-expresó 102 líneas**— pero estas
> tres siguen abiertas, y cerrarlas **traba trabajo diario**, así que es
> decisión del owner:
>
> | pantalla | endpoints que escriben | qué se mueve si alguien la toca |
> |---|---|---|
> | **Mixer de canales** | 7 | un sub-canal mal ruteado **no falla: factura de más** (9,27% en vez de 30%) |
> | Catálogo de departamentos | 2 | crear o inactivar un departamento cambia qué existe en el grupo |
> | Estadísticas (clase 9) | 2 | son el denominador de ADR, RevPAR y los costos unitarios |
>
> ⚠️ Y sigue abierto el **14**: `PATCH /scenarios/{id}/status/` no exige admin,
> así que **cualquier colaborador desenllava** — y con el candado de escritura
> puesto, quien desenllava puede volver a escribir.
>
> ### 🔵 Código — el agente puede hacerlo sin esperar a nadie
>
> | # | Qué | Por qué importa |
> |---|---|---|
> | ~~17~~ | ✅ **El cron que dispara la ronda — CONSTRUIDO 2026-08-20.** `app/guillermo/cron.py` + `backend/railway.cron.json`, 20 pruebas. ✅ **Servicio `finplan-cwl-guillermo` creado y VERIFICADO en producción** el mismo día — ver `docs/GUILLERMO.md` §2.1 | La hora sigue viviendo en `daily_run_at`, no en el crontab: éste dispara cada 30 min y el módulo decide si toca. ⚠️ Los crons de Railway corren en **UTC** — 06:00 de Corcovado no es 06:00 UTC |
> | 18 | ⚠️ **La llamada al modelo — CONSTRUIDA 2026-08-20, SIN VERIFICAR contra la API.** `app/guillermo/cliente_ia.py` (SDK oficial `anthropic`, herramienta forzada). El owner decidió que la llave se pone **al clonar**, así que se escribió sin poder llamar una vez: **la primera llamada real hay que mirarla** | Se corrigió el id del modelo: era `claude-haiku-4-5-20251001` y el correcto es `claude-haiku-4-5` — un id inventado no falla al escribirlo, falla con 404 el día del clonado. Y el guardia `payload_limpio` **ya existía y nadie lo llamaba**: una regla que nadie verifica no protege de nada |
> | ~~19~~ | ✅ **NO HACE FALTA — resuelto por el owner, 2026-08-20.** «Todos serán XML de Opera» · «los uploads de Opera serán Excel». **Ni CSV ni PDF**, así que no hay parser que escribir: FinPlan ya tiene 18 parsers y son todos XLSX y XML | El hueco #4 del spec («no hay parser CSV ni PDF») deja de ser un hueco: era una suposición sobre el formato, no un requisito |
> | ~~20~~ | ✅ **Los correos — CONSTRUIDO 2026-08-20.** `app/guillermo/correo.py`, `GET /guillermo/correo/` y la sección «Avisos por correo» en Admin → Guillermo | ⚠️ **El vigilante vive en los tics en que la ronda NO corre**: un dead-man switch adentro del proceso que vigila no puede avisar cuando ese proceso muere, y el cron despierta 48 veces por día. ⚠️ **El vigilante NO late** — escribir un latido al avisar silenciaría la alarma recién disparada. Falta que el owner cargue `notify_emails` (D-5) y las variables SMTP: **cada propiedad decide** |
> | 21 | **Costos de Grupos: 6 de 14 sub-tabs** | ✅ **El spec ya está en el repo** (`docs/COSTOS_GRUPOS.md`, recuperado de Downloads el 2026-08-20): los 14 están en su §5. **Construidos: 1 Summary · 2 Descuentos · 3 Master Data · 8 Pisos · 9 Escalones · 12 Simulador.** ✅ Y los tres selectores del §5 (base · período · temporada) en Summary y Descuentos. **Faltan 8**: Parámetros · Drivers y volúmenes · Clasificación fijo/variable · Costos unitarios · Absorción · Costo del paquete · Desplazamiento (necesita On the Books) · Validación |
> | 22 | Nivel 3 · cuadre **entre reportes de Opera** | ✅ **D-2 ya no lo bloquea** (todo es XML de Opera). Lo que falta es DECIDIR **qué pares cuadran entre sí** — la mitad abierta de D-8. Propuesta medible: noches del Country Mix = noches del Channel Mix = noches del OTB para el mismo mes, porque salen del mismo XML |
>
> ⚠️ **Y queda «una tarea más, grande»** que el owner dijo que se ve al
> regreso. No dijo cuál.
>
> ### 🟢 Lo que se sumó el 20 de agosto y no estaba en la lista
>
> | qué | por qué entró |
> |---|---|
> | **El manifiesto es POR PROPIEDAD** (`Admin → Guillermo`) | Al clonar, Amarena heredaba el de CWL y arrancaba **en rojo** reclamando cinco reportes que nadie prometió. Y `ExpectedReport` no tenía escritura: sin pantalla, «cada propiedad decide» no se podía ejercer |
> | **El gato se arrastra** y recuerda dónde quedó | «A veces está detrás de cálculos y datos». ⚠️ El contenedor sigue sin recibir clics: arreglar «me tapa los datos» no podía crear «no puedo tocar los datos» |
> | **`Cost → Descuentos`** — el cuadro fully loaded de la Junta | Sus dos reportes, reproducidos **al centavo** por 16 pruebas, incluida la Tienda en negativo |
> | **`Cost → Master Data`** — «Mi Resumen» | Su `FULL YEAR ANALYSIS 2026`, leyendo de FinPlan |
> | ⚠️ **Un guardián que no guardaba** | La prueba de «con cuál escenario abre cada pantalla» aceptaba el nombre `elegir(` suelto: una función local con ese nombre **pasaba en verde eligiendo por su cuenta**. Corregido para exigir el import del módulo |
>
> ### 📌 Decisiones nuevas del owner (2026-08-20)
>
> | decisión | consecuencia |
> |---|---|
> | «La llave de Anthropic la hacemos al clonar; **cada propiedad decide cómo manejar a Guillermo**» | El 5 y el 10 (D-5) se corren al clonado. Destapó el defecto del manifiesto |
> | «**Todos serán XML de Opera**» · «los uploads serán Excel» | Cierra D-2 y **elimina** el 19 |
> | «**Sólo mapeá tus datos y demos esos como válidos**» | Master Data usa las temporadas de FinPlan, no el corte en dos del Excel |
> | «Tiene que ser flexible para escoger versiones; los meses más dinámicos» | Los tres selectores del §5 |
>
> ---
>
> ## ▶️ LO QUE QUEDA ABIERTO — verificado el 2026-08-17
>
> **Nada roto, nada bloqueando.** Se sacó de esta lista todo lo que ya estaba
> cerrado y seguía figurando: **B6.4** (departamentos editables — la pantalla
> `/master-data/departamentos` existe) y **«crear copiando»** (ya filtra los
> escenarios vacíos). Un punto sin medir no es un pendiente: es una nota vieja.
>
> ### Código
>
> | | qué es | tamaño |
> |---|---|---|
> | ~~**MIXER DE CANALES**~~ | ✅ **CERRADO 2026-08-17.** Editable (crear/borrar canales y sub-canales, `rueda_a` como dato), y las dos guardas del clonado puestas — ver [A0.-11](#a0-11--el-mixer-editable-y-listo-para-clonar-2026-08-17) | — |
> | ~~**A0.-2**~~ | ✅ **CERRADO 2026-08-17.** Big Picture muestra si la BASE cuadra Resumen/Detalle, con el motivo en el tooltip. No bloquea — el owner decide si construye igual encima | — |
> | ~~**SEMILLA_PENDIENTE**~~ | ✅ **CERRADO 2026-08-17.** `revenue_importer.py` ya lee `semilla("canales", hotel_id)` y `semilla("paquete", hotel_id)` — los archivos de CWL ya tenían los mismos valores, no se movió un número. La lista quedó vacía | — |
> | **B2** | A&B por outlet — **verificado 2026-08-17, sigue bloqueado.** El propio B2 dice «no puede producir nada real hasta que contabilidad cambie cómo contabiliza»: solo el Outlet 1 tiene monto, los otros tres y las cuentas de Licor/Vino/Cerveza están en cero en ingreso Y costo. Construirlo hoy sería una estructura vacía, y encima tiene una decisión de diseño abierta (cómo repartir el costo entre outlets) que es del owner | grande |
> | ~~**B6.5**~~ | ✅ **CERRADO 2026-08-17** — decisión del owner: **un FinPlan por propiedad**, no una app consolidada. Es el modelo que ya está construido (`app/hotel_actual.py`, `HOTEL_ID` por entorno); `docs/MULTIPROPERTY_PLAN.md` (la app única con selector y control de acceso) queda marcado como superseded. Verificado: no quedan literales `"CWL"` sueltos fuera de `seed.py`, y ahí son comparaciones correctas contra `HOTEL_ID`. Abrir Amarena/Oxígen/Ojochal es desplegar Railway+Vercel con `HOTEL_ID` nuevo — no hay fundación de código pendiente | — |
> | ~~**B7 residual**~~ | ✅ **CERRADO 2026-08-17.** Los cuatro se verificaron: dos eran correcciones reales (TC de cada mes en `SW Anual USD*`, colores de FTE), una era una nota vieja mal descrita (Capital Reserve no duplica — reemplaza, y ahora avisa), y la de "Driver" se renombró a "Modo". Lo que queda (columnas nuevas para el Driver de costos) es agregar plantilla, no corregir | — |
> | ~~**TopNav**~~ | ✅ **Era una nota vieja (verificado 2026-08-17).** Se arregló el 2026-08-16 —el propio archivo lo documenta en un comentario en `Dropdown()`— y la lista nunca se actualizó. Confirmado con `next lint --dir components` limpio y lectura del código: los cuatro hooks están antes del primer `return` | — |
>
> ### Del owner — cuando quiera, no bloquean
>
> | qué | dónde |
> |---|---|
> | Mover los % del break-even | Break-E → Configuración · ver [A0.-10](#a0-10--break-even--cerrado-del-lado-del-código-2026-08-17) |
> | Si el diferencial cambiario va como renglón propio del P&L | decisión |
> | Clasificar la planilla del Club Madresal, o sacar Amarena de la base | $283.758 en el Working 2027 |
>
> ### De contabilidad — las cuentas ya existen y están en cero
>
> Partir la `4000` en Room Revenue / Cancellations / No Show · llenar los
> Outlets 2, 3 y 4 de A&B · separar Licor y Vino de `Beer1` (ingreso **y**
> costo) · resolver el doble uso de la `5102` · la planilla del **Spa** toda en
> fijo mientras Rooms/F&B/Tours tienen las mismas cuentas en variable ·
> `Renting – Transfers Cost` en fijo siendo costo de venta · la `5603` en 2027.
>
> **El día que se empiecen a usar, entran solas.**
>
> Las secciones de abajo quedan como el detalle de CÓMO se cerró cada cosa —
> sirven para entender una decisión, no para tomar trabajo.

---

## A0.-11 · ✅ El mixer: editable, y listo para clonar (2026-08-17)

Owner: *«el mixer hay que revisarlo… antes de clonar»* · *«tenés que dejarme
crear más mix y borrar también, y que el derivado lo tome… inclusive se pueden
crear más canales y sub-canales, pero deben estar sincronizados para que ruede
donde corresponde»*.

### Lo que se construyó (migración 120, aditiva, sin mover un número)

* **`canales_comerciales.rueda_a`** — el destino como COLUMNA, con FK. Antes se
  deducía de `entrada` con un diccionario de seis entradas y **`DIRECT` de
  default**: un sub-canal nuevo rodaba a DIRECT en silencio, cobrando 9,27% en
  vez del 30% de TA. **No fallaba: facturaba de más.**
* **`canales_comision`** — TA/OTA/DIRECT dejan de ser una constante de tres
  repetida en **cinco** lugares. Agregar un cuarto es un INSERT.
* **CRUD** de sub-canales y canales, con la pantalla: «+ Sub-canal», «+ Canal»,
  la «×» por fila y el desplegable de «rueda a».

**Las guardas del «sincronizados»:** `rueda_a` se valida contra la tabla (422);
no se borra un canal con sub-canales colgando (409); borrar un sub-canal se
lleva sus excepciones y avisa la suma que queda; **lo que rueda a un destino
desconocido sale igual, al final** —antes se descartaba en silencio y la suma
bajaba de 100%—; y el seed **exige** `rueda_a`.

⚠️ **La pantalla tenía el mismo defecto por su lado:** el derivado se armaba
sobre `{TA, OTA, DIRECT}` fijos con `acum[c.destino] ?? acum.DIRECT`. Un
sub-canal que rodara a otro lado **sumaba su mix a DIRECT y cobraba la comisión
de DIRECT**.

### Las dos guardas del clonado, y por qué el ORDEN no era opcional

1. **No se escriben tarifas sin mix.** `nf if nf else Decimal("1")` significaba
   «no pago comisión»: la tarifa neta quedaba igual a la rack, el motor leía
   `net/rack = 1,0`, decidía que «mandan las tarifas» y el mixer ya nunca lo
   corregía. Medido sobre el Working 2027: **+$1.494.916,87 (+23,45%)** de
   ingreso, +$973.190,88 de utilidad, gastos $0,00.
2. **La semilla de canales pasa a `seed_data/<HOTEL_ID>/`.** Estaba en la raíz y
   sembraba sin filtro de hotel en cada arranque: una propiedad nueva heredaba
   el mix de Corcovado. Con el 0,797 sobre otra que venda distinto, el error va
   de **−$346.109 a +$552.314** al año.

⚠️ **Gatear la semilla SIN la guarda habría empeorado el clon:** quedaría sin
mix y facturaría **+25%**. Heredar un mix ajeno es equivocado y **conservador**;
caer a «sin comisión» es equivocado e **inflador**.

**Verificado en producción:** backfill exacto (B2B→TA, OTA→OTA, resto→DIRECT),
mix sumando 1,000000 en 7 canales, y el ingreso de Working 2027, Final 2027 y
Final 2026 **idéntico al decimal** antes y después.

**Lo que el mixer NO tenía:** el clonado de propiedad **todavía no existe** — no
hay endpoint que cree un Hotel. Las guardas están puestas antes de que exista el
camino que las necesita, que es más barato que ponerlas después.

---

## A0.-10 · ✅ BREAK-EVEN — cerrado del lado del código (2026-08-17)

**El módulo funciona y no queda trabajo de código.** Owner, 2026-08-17:
*«yo eso lo cambio cuando yo quiera, no te preocupes por los %; solo quiero
tener claro que la herramienta funciona»*.

### Con qué se sostiene que funciona

* **Reproduce los números del owner**, no los propios: las **72 pruebas de
  aceptación** son su Excel — los 9 números del resumen y los 14 departamentos
  al dólar, las 20 celdas de SENSIBILIDAD al centavo, y el equilibrio en noches
  verificado celda por celda contra su hoja. Siguen pasando **después** de la
  cirugía del 17-ago, que tocó el motor.
* **Ve todo lo que hay:** los cuatro escenarios de planificación cuadran contra
  el P&L a **menos de 21 centavos** en costo y a **cero** en ingreso
  (`scripts/cuadre_costo_break_even`).
* **Avisa cuando no sabe:** la validación compara contra el P&L y no contra sí
  misma; `sin control` ya **no** se pinta de verde; un mes sin equilibrio sale
  como tal y no en cero; las noches negativas se muestran; y los dos ACTUAL con
  0,011% y 0,099% de diferencia de mapeo lo declaran en pantalla.

**La distinción que queda:** el número de hoy es aritmética correcta sobre una
clasificación semilla. La cuenta está bien; el supuesto de qué es fijo y qué
variable es del owner. Mover los porcentajes **no es corregir la herramienta**,
es ponerle su criterio — y lo hace cuando quiere, en Break-E → Configuración.
Cuánto mueve, medido: `scripts/cuanto_puede_estar_malo` y
`scripts/mover_los_porcentajes` (este último no escribe una fila).

⚠️ **Y al medirlo hay que mirar el signo del EBT primero.** Con
`BE = F·R/(R−V)`, pasar costo de variable a fijo cumple `BE' > BE ⟺ EBT > 0`:
**el signo del efecto de reclasificar es el signo del resultado.** Con utilidad
sube el equilibrio; con pérdida lo BAJA, y ahí el ajuste correcto aparece en
pantalla como una buena noticia. En el `ACTUAL 2025` marcar toda la planilla
fija lo baja **$925.541**. Fijado en `tests/test_break_even_direccion.py`.

Lo que sigue abajo es **el detalle de cómo se cerró cada cosa** — sirve para
entender una decisión, no para tomar trabajo.

### El dinero que toma el criterio por defecto (medido, y es del owner)

Medido con `python -m scripts._be_sin_clasificar`. Lo que cae al default
100% fijo **por no tener regla**, por escenario:

| escenario | montos | plata | % del ingreso |
|---|---|---|---|
| `BUDGET Final 2026` | 0 | 0,00 | 0,00% |
| **`BUDGET Working 2027`** | 1.284 | **357.183,11** | **5,60%** |
| **`BUDGET Final 2027`** | 1.284 | **282.853,38** | **4,85%** |
| `ACTUAL 2025` | 4 | 18.421,86 | 0,60% |
| `ACTUAL 2024` | 1 | −43.875,95 | −2,13% |

⚠️ **El «22 cuentas con criterio por defecto → en cero» de la tabla de abajo se
midió sobre el `BUDGET Final 2026`**, donde efectivamente da cero. En los 2027
no: ahí sí hay gasto presupuestado en departamentos que **no tienen ni una
regla**.

Y no es disperso — **el 90% es la planilla del Club Madresal (`260`)**, cuentas
`6000`/`6020`/`6021`/`6023`/`6003`/`6022`. Detrás vienen Claro Huerta (`0205`),
el Spa `0130:6023` y Sales & Marketing `0190:7685`.

**La causa es estructural, no un olvido:** los **8 departamentos en
`pending_classification` tienen CERO reglas** —`club-madresal`,
`area-recreativa`, `claro-huerta`, `cafeteria`, `crowther-lab`, `miscelaneos`,
`private-bar`, `tienda`— porque la semilla se armó con los 14 activos de CWL. Y
el Club es de **Amarena**, viviendo en CWL como ambiente común por decisión del
owner (sus 17 posiciones se replicaron al Budget 2027 v1 el 29-jun).

**El módulo no está mintiendo:** las cuenta como 100% fijas, las registra y las
muestra en «Por defecto: 100% fijo» — que es exactamente para lo que existe esa
pantalla. Lo que falta es la decisión: **clasificar la planilla del Club, o
sacar a Amarena de la base del break-even de CWL.** Las dos son del owner.

### Dos incoherencias de la semilla que son CONTABLES, no de código

Salieron al leer el Excel de referencia, y **siguen abiertas — verificado
contra producción el 2026-08-17**:

* **las 26 reglas de planilla del Spa están en 0% (fijo)** mientras las de Rooms
  (48), F&B (16), Tours (17), Transportation (16) e Innoceana (17) —las mismas
  cuentas GL— están en 100% (variable). Al alinearlas, el equilibrio se mueve
  −469 en el `BUDGET Final 2026`, −28.540 en el `Working 2027` y **+41.396** en
  el `ACTUAL 2025` (ver el §1: el signo lo pone el resultado, no el ajuste);
* **`Renting – Transfers Cost`** (`0152:5350/5351/5352`, línea
  `COS_TRANSPORTATION`) está en 0% siendo **COST OF SALES**. Vale 0 en los 2027
  —no tiene monto ahí— y **$70.325** en el `ACTUAL 2025`.

Las dos son de **contabilidad**: el sistema no puede decidirlas.

### ✅ Resuelto el 2026-08-17: el GL es la base

Owner, viendo el banner de Property Expenses: *«¿qué significa esto? ¿por qué no
lo resolvés? El GL es la base, ¿por qué tiene que leer de otro lado?»*. Tenía
razón.

Las reglas `LINEA` venían del Excel de referencia, donde esas líneas del P&L **no
traían cuenta GL**. En FinPlan **sí la traen**: medido en el `0250`, el GL trae
las ocho cuentas y **cero filas sin cuenta**. Era un límite del archivo de
origen, no del sistema.

Se generaron las **23 reglas exactas** que faltaban (los 23 pares que resolvían
por línea en los cuatro años, $10,5 M en valor absoluto), copiando la
clasificación de su regla `LINEA`. **No se movió un centavo** — costo, variable,
fijo y neto idénticos — y los montos que resuelven por línea pasaron de **23 a 0**.

Las 18 reglas `LINEA` quedan de respaldo: la exacta les gana siempre, y si entra
una cuenta nueva bajo esa línea hay con qué clasificarla en vez de caer al
default 100% fijo.

### La `5603` no existe en 2027

Ver [A0.-7](#a0-7). Ahora hay dónde cargarla.

### ✅ Lo que se cerró el 2026-08-17, y no hay que rehacer

| | |
|---|---|
| El ingreso se contaba como costo | lista **blanca** de secciones; el neto cierra contra el P&L a 4 centavos |
| El ADR estaba en cero | sale de las noches reales |
| **Las noches salían de la tabla equivocada** | mandan `scenario_stats` (12 escenarios); `occupancy_budgets` y `actual_room_stats` de respaldo |
| Cafetería y Lavandería en la base de costo | fuera: reparten todo y netean 0,00 — se detectan por su cuenta de distribución |
| 22 cuentas con criterio por defecto | en **cero**: el Spa se resolvió copiando `0140`→`0130`, y las dos de Sales & Marketing al 100% variable por decisión del owner |
| «Sin clasificar» | se llama **«Por defecto: 100% fijo»** — owner: *«si al menos tiene fijo 100% ya tiene un criterio»* |

### ✅ Resuelto el 2026-08-17 (tarde): los cuatro defectos de la pantalla

El owner abrió el Resumen en el `FORECAST April 2026` y mandó la captura:
*«¿qué es todo este desmadre?»*. Eran **cuatro** cosas distintas encimadas, y
la peor no era la roja.

**1. El 422 rojo — un default inventado.** `_contexto.tsx` derivaba la versión de
dato del escenario con `?? "BUDGET"`. Pero `scenarioId` sale de `localStorage` y
está listo en el primer render, mientras la lista de escenarios llega por red un
instante después: en esa ventana el `find` no encuentra nada y salía el par
**«escenario FORECAST + versión BUDGET»**, que es justo lo que el backend está
para rechazar. Ahora la versión **no tiene default**: hay un `ctx.listo` y
ninguna de las seis pantallas consulta hasta que el tipo se sabe.

**2. ⚠️ El error rojo ENCIMA de números correctos — y el reverso es peor.** Las
seis pantallas hacían `setD(await …)` sin secuencia. Con dos consultas en vuelo,
la inválida (422) y la válida salieron casi juntas: **contestó primero la
válida y pintó los números, y la inválida llegó después y pegó el error
encima**. Por eso se veían las dos cosas a la vez.

Al revés no se ve, y es el pecado capital del módulo: si la que contesta última
es la de un escenario que ya no está seleccionado, la pantalla muestra **los
números del escenario equivocado sin ningún error**. Se cerró con `useVigencia()`
en `_contexto.tsx`, aplicado en las seis.

**3. «Apalancamiento operativo −3.213,1x».** Era `CM / EBT` con un EBT de −$993
sobre $5,19 M de ingreso — o sea, el escenario está prácticamente en el
equilibrio. Aritméticamente correcto, informativamente nulo: el cociente tiende
a infinito según el resultado se acerca a cero y **el signo lo decide un
redondeo**. La guarda solo miraba el cero exacto; ahora cubre el entorno
(`UMBRAL_EBT_DESPRECIABLE`, 1% del ingreso) y devuelve `None` **con motivo
escrito en pantalla**, porque un guion sin explicación se lee como «falta el
dato». Lo que sí informa ahí ya estaba a dos renglones: el margen de seguridad,
−$1.616 · 0,0%. La prueba de aceptación (EBT = 5,7% del ingreso → 11,6x) no se
mueve, y hay una contracautela que lo fija.

**4. «376 regla(s) sin movimiento» en el banner amarillo.** 376 de 612. Leído
así parece que faltara clasificar medio módulo, y no falta nada: una regla sin
movimiento es una cuenta que **ese escenario no usa**, lo normal cuando la
semilla cubre 22 departamentos y un escenario mueve doce. Un aviso que salta
siempre deja de ser un aviso y le quita fuerza al que sí importa (las 3 cuentas
con criterio por defecto). Salió del banner; el conteo con detalle sigue en
`/break-e/sin-clasificar`, que es la pantalla que existe para eso.

**5. Y el pie de la pantalla afirmaba lo que el §1 desmiente.** Decía siempre
«el equilibrio va a subir de forma material». Ahora la frase la decide el signo
del EBT de la pantalla — que en ese mismo FORECAST es **negativo**, o sea que el
ajuste lo bajaría.

**Verificado contra el escenario de la captura:** ingresos 5.191.809, variables
2.002.775, fijos 3.190.026, EBT −993, margen −1.616, 3 sin regla y 376 sin
movimiento — los siete números reproducen exacto, y el apalancamiento pasó de
−3.213,1x a `None` con motivo. Backend **1.496 pruebas**, `tsc` limpio.

### ✅ 2026-08-17 — el ingreso por departamento, y el desfase que lo destapó

**El tab «Por Departamento» mostraba los 14 departamentos con ingreso $0.** El
motor deja `DeptoBE.revenue` para «quien llama» y no lo llamaba nadie, así que el
margen era el costo variable en negativo y el `% MC` daba «—» en todas las filas.

Se construyó `app/api/_be_base.py`: **una sola proyección** del GL con la línea
del P&L, la sección, el departamento y si es costo o ingreso. Cada consumidor
filtra la misma base. Calculada, no guardada — decisión del owner, y además una
base guardada y vieja daría un equilibrio que se ve idéntico a uno correcto.

#### ⚠️ Tres cosas que salieron al validar, y ninguna se veía

1. **El ingreso no puede salir de `_sources`.** Esa función es de **COSTO**: en
   modo `checkbook` lee OPEX, Costos, Planilla y Repartos, y nada más — el tab
   de Control lo dice en su propio texto («payroll, OPEX, costs»). En el
   `BUDGET Working 2027` daba **$0 contra $6.374.026**.
2. **El motor emite DOS vocabularios y `canonicalize_pl_lines` es ADITIVO**:
   `REV_TRANSPORT` y `REV_TRANSPORTATION` son el mismo peso. Sumar «todo lo que
   empiece con `REV_`» los contaba dos veces — en el `ACTUAL 2024` daba
   $2.120.135 contra $2.055.687, y la diferencia eran **exactamente** los
   $64.448,17 de Transportation.
3. **⚠️ Derivar el departamento de los grupos de `pl_engine` perdía plata en
   silencio.** Los deptos `280` (Misceláneos) y `0205` (Claro Huerta) caen en
   `OTHER_OVERHEAD` en esa cadena, así que `REV_MISC_OTHER` y
   `REV_SUSTAINABILITY` salían **sin departamento**: $308.405 en el
   `BUDGET Final 2026`. El P&L seguía cuadrando — el total del hotel no se movía,
   solo faltaba margen en departamentos que nadie miraba.

   Owner: *«debe tomar todas las cuentas»*. **Y las cuentas ya estaban**: el
   `account_mapping` trae las 19 líneas de ingreso con su departamento y sus
   cuentas GL (`REV_ROOMS`→`0110/4000`, `REV_SUSTAINABILITY`→`280/4880`). Ahora
   el ingreso se resuelve por **la misma autoridad que el costo**, la que el
   owner edita en Admin · Account Mapping. **Ingreso sin departamento: 0,00 en
   los cinco escenarios.**

**Cuadre (`scripts/cuadre_base_break_even`), 5 escenarios: TODO CUADRA al
centavo, y la base de COSTO no se movió ni una fila.**

### ✅ 2026-08-17 — el ingreso ya no se desincroniza del sub-mayor

Owner: *«no puede quedar así… si todo estaba trabajando bien… esto no puede
volver a pasar»* · *«los canales entran al principio y los resultados que van al
GL son el final del proceso»*.

Hasta el **15-ago** los presupuestos leían el ingreso del checkbook
(`revenue_source = 'checkbook'`): el checkbook **era** la fuente y el botón
«pasar al checkbook» era el único camino. Con el mixer de canales (migs 116-117)
los seis presupuestos 2027 pasaron a **`drivers`**, y desde entonces el P&L
calcula el ingreso mientras **nadie vuelve a escribir el sub-mayor**. Quedó una
foto de la última vez que alguien apretó el botón: **$6.449.238 contra $6.374.026
en el `Working 2027`, y $118.218 solo en Rooms**. Nada fallaba.

**El arreglo va en el RECÁLCULO** (`sincronizar_ingreso_al_checkbook`), no en
otro botón: un botón es exactamente lo que falló, porque depende de que alguien
se acuerde. ⚠️ **En modo `checkbook` no escribe nada** — ahí las filas son montos
tipeados y son la fuente del P&L; sobrescribirlas borra un presupuesto **y el P&L
sigue cuadrando** contra el número equivocado. Meses cerrados tampoco se tocan.
Hay centinela que falla si el recálculo deja de sincronizar.

⚠️ **El `Working 2027` sigue con los $6.449.238 viejos hasta que se recalcule.**

### 🔴 2026-08-17 — LA AUDITORÍA: el equilibrio del 2027 estaba 32% bajo

Barrido adversarial (14 agentes, 5 lentes, verificación por refutación: 7
confirmados, 1 caído). **El módulo declaraba un neto de $2.882.507,99 cuando el
P&L del mismo escenario decía $1.304.602,47** — $1.577.905,52 de costo que la
base no tenía, con la validación de la pantalla en **verde**.

| | antes | ahora |
|---|---|---|
| neto del módulo | 2.882.508 | **1.304.603** (P&L: 1.304.602) |
| **equilibrio** | 2.868.128 | **3.793.243** |
| ocupación de equilibrio | 20,5% | **27,0%** |
| Rooms · margen | 97,6% | **80,9%** (P&L: 80,9%) |

**1 · El fee (3%), la reserva (4%) y el impuesto no entraban** — $446.181,84 +
$559.115,34. No existen como fila de GL: el motor los calcula como porcentaje.
⚠️ Fallaba **solo en los seis presupuestos 2027**, que son los que planifican;
los históricos los traen en el mayor. Por eso Comparar los mostraba consistentes
entre sí. Dos trampas medidas y cubiertas: inyectar **por línea** deja al
impuesto sin regla → 100% fijo → equilibrio $680k arriba; inyectar **sin
comprobar el total** mete plata que no falta ($30k espurios en el FORECAST).
**Si las líneas ausentes no explican la brecha, no se toca nada y se avisa.**

**2 · Rooms se caía entero de la base** — $553.855,87. El filtro marcaba
«reparte» por la sola presencia de una cuenta `4900/4901/4999` y borraba TODAS
las filas del departamento; el reparto de Villas y Residencias asienta un
crédito dentro del propio `0110`. Ahora se **comprueba que netee ≈0**
(`UMBRAL_NETEA_CERO`): Cafetería 0,00 y Lavandería 0,01 lo cumplen, Rooms netea
$553.855,85. Los otros cuatro escenarios quedan idénticos al centavo.

**3 · ⚠️ La «Validación del costo» era una TAUTOLOGÍA.** `total = variable +
fijo` y acto seguido `validacion = variable + fijo − total`. Cero siempre,
incluso con entradas absurdas — y **había una prueba que lo afirmaba**. Port
fiel de la hoja del owner, donde el Total venía tecleado aparte. Ahora compara
contra `TOTAL_REVENUES − NET_PROFIT − INCOME_TAXES`, y **`cuadra: null` =
«sin control»**, que la pantalla ya no pinta de verde.

**4 · El corte por departamento salía de la REGLA, no del monto** — $357.183,11
mal atribuidos. Y una fila **sin** regla entraba al total y desaparecía del
corte: el crédito del reparto dejaba a Rooms en $738.209 contra $646.032,60,
**con el total cerrando igual**. Ahora el departamento sale de `Monto.dept_slug`.

Los cuatro empujaban para el mismo lado: menos costo, más margen, equilibrio más
bajo. **Todos se leían como buena noticia.**

#### ⚠️ Y por qué no lo agarró el cuadre que ya existía

`cuadre_base_break_even` validaba **solo el ingreso** y daba «TODO CUADRA».
El costo se dio por bueno con un «cierra a 4 centavos» **medido sobre el BUDGET
Final 2026** y nunca repetido sobre 2027. Validar la mitad que funciona y
afirmar la otra desde una medición vieja es el mismo error que el módulo
persigue. El cuadre que faltaba es `scripts/cuadre_costo_break_even.py`.

**Queda abierto y el módulo lo dice en vez de taparlo:** `ACTUAL 2025` (−$455,66)
y `ACTUAL 2024` (−$3.085,13) no cuadran — son diferencias de mapeo en escenarios
importados, y las líneas ausentes no las explican.

### ⚠️ Lo que hay que saber antes de tocar el módulo

1. **La fórmula del owner (en noches) es la buena.** `fijo / (ingreso por noche −
   costo variable por noche)`. Es la misma identidad que `FC / CM%` —hay prueba—
   pero **sin el supuesto de mezcla constante**. Verificada celda por celda
   contra su hoja.
2. **Las noches de equilibrio NEGATIVAS no son un error de signo**: significan
   que cada noche vendida pierde plata. En el junio real de CWL pasa.
3. **567 reglas contra 467 líneas del P&L.** Iterar las reglas en vez de los
   montos da **+39,9%**.
4. **`dept_code` y `account` van VACÍOS, jamás NULL**, o el seed duplica las 18
   filas `LINEA` en cada recarga.

---

## A0.-9 · ✅ EN VIVO — Break-Even Fases 1 **y 2**

### Fase 2 (2026-08-17) — sensibilidad y equilibrio mensual

**Las 20 celdas del Excel, al centavo.** `test_break_even_fase2` reproduce la
hoja `SENSIBILIDAD` con las constantes exactas del libro. Más dos invariantes
que delatan un factor mal puesto —cosa que en 153 celdas plausibles no se ve a
ojo—: la celda depende **solo del producto** `k = ocupación × factor` (por eso
`0,30×1,20`, `0,40×0,90` y `0,45×0,80` valen los tres $7.024,11), y cada punto
de ocupación vale **$73.909,03**.

#### ⚠️ Corrección al titular del spec

El spec dice **«tres puntos de ocupación borran el resultado del año»**. Medido:

| pierde | ocupación | resultado |
|---|---|---|
| −0 pp | 39,29% | 250.146 |
| −3 pp | 36,29% | **28.420** ← todavía positivo |
| **−3,385 pp** | **35,90%** | **0** ← acá cruza |
| −4 pp | 35,29% | −45.489 |

Tres puntos se llevan el **89%**, no el 100%. El que borra el año es **3,385 pp**
— la holgura exacta que el propio modelo reporta. No cambia la conclusión, pero
la frase redondeada dice algo más fuerte de lo que el modelo sostiene. Fijado con
prueba y corregido donde se había propagado.

#### El semáforo va con umbrales ABSOLUTOS

±$500.000 con el cero en amarillo, igual que el Excel. La primera versión
normalizaba por el máximo y mínimo de cada corrida, y con rangos configurables
eso significa que **el mismo resultado pinta de otro color según lo que el
usuario elija** — el semáforo dejaría de significar nada entre pantallas.

#### El equilibrio mensual, y de dónde sale la estacionalidad

`BE/12` daba el mismo umbral los doce meses. Ahora se calcula mes a mes con los
costos fijos y la mezcla de **cada** mes, reusando el mismo motor que el anual.

⚠️ **El Excel de referencia no tiene ni un dato mensual** — verificado por nombre
de mes, por estructura (ningún bloque de 12 columnas) y por encabezados (todo
rotulado FY). Lo único que hay ahí sobre estacionalidad es una frase suelta. La
curva sale del **P&L mensual de FinPlan**, que era la única fuente posible.

Un mes puede **no tener equilibrio** y sale como tal con su motivo, no con un
cero. Y la suma de los doce **no** es el equilibrio anual: el endpoint manda esa
nota porque es la trampa de lectura de la pantalla.

Pantallas nuevas: `/break-e/sensibilidad` y `/break-e/mensual`. 34 pruebas.
**Falta de la Fase 2 solo la multipropiedad**, que no se puede construir hasta
que exista una segunda propiedad.

---

## A0.-9.1 · Break-Even Fase 1 (2026-08-16)

Módulo de punto de equilibrio. Specs del owner en
[`docs/break-even/`](break-even/). **Fase 1 completa y desplegada**; Sensibilidad,
Escenarios y multipropiedad quedan para las fases 2 y 3, con los ganchos puestos.

### La prueba de aceptación pasa

Los nueve números y los catorce departamentos, al dólar — `test_break_even_acepta`.
Ingresos 4.373.146 · MC 2.903.849 (66,4%) · equilibrio **3.996.427** · ocupación
de equilibrio **35,9%** · apalancamiento **11,6x** · costo total 4.198.042.

### ⚠️ El hallazgo que definió la arquitectura

**Ningún escenario de FinPlan tiene esos $4.373.146.** Medido contra los 20: el
más cercano es `BUDGET Final 2026` con $4.872.775. El Excel de referencia está
armado sobre un «Budget 2025 Dec» que el sistema no tiene cargado.

Por eso el motor es **puro** y la aceptación corre contra un fixture con las 467
líneas del P&L de referencia (`tests/fixtures/break_even_montos_cwl.csv`), no
contra un escenario vivo. Verifica el MOTOR, que es lo que el spec pide; leer el
P&L real es la capa de integración y se prueba aparte.

### ⚠️ La trampa que más plata mueve: 567 contra 467

La semilla tiene **567 reglas** para **467 líneas** del P&L — una línea de
planilla se abre en varias cuentas GL hermanas. **Sumar fila por fila da
$5.872.331, un +39,9%** sobre los $4.198.042 reales. El motor itera los MONTOS y
busca su regla, nunca al revés. Lo fija `test_no_cuenta_dos_veces`.

### Adaptaciones a FinPlan, y por qué

| el spec dice | acá | por qué |
|---|---|---|
| rutas `/properties/[propertyId]/break-e/…` | `/break-e/…` | en FinPlan **la propiedad es el despliegue**; sería la única ruta del sistema con `propertyId` |
| `data_version` obligatorio | `data_version` **y** `scenario_id`, y el backend exige que coincidan | la versión sola no alcanza para elegir entre seis presupuestos 2027; el escenario solo haría decorativo al parámetro |
| «aprobación entre etapas» | Fase 1 entera de una | instrucción del owner en el chat, que le gana al documento |

### Verificado en producción

Migración **119** · **22 departamentos** (14 activos + 8 pendientes) · **567
reglas** · 18 `LINEA` · 1 excluida · **0 NULLs** en `dept_code`/`account`. La
carga se corrió **dos veces**: la segunda insertó 0 y las 18 filas `LINEA`
siguieron siendo 18 — si hubieran entrado con NULL se habrían duplicado a 36,
que es exactamente lo que la regla del string vacío evita.

### Lo que queda, y es del owner

1. **Ajustar los porcentajes.** La semilla 100/0 **no es un diagnóstico**: con
   toda la planilla en 100% variable el margen queda alto y el equilibrio bajo.
   En CWL la planilla es mayoritariamente de planta, así que al ajustarla el
   equilibrio **va a subir de forma material**. Medir eso es el punto del módulo.
2. **Elegir el escenario contra el cual mirarlo**, ahora que el «Budget 2025 Dec»
   del Excel no existe en el sistema.
3. Dos incoherencias que salieron al leer el Excel de referencia y que son
   contables, no de código: toda la planilla del **Spa** está marcada `Fixed Cost`
   mientras la de Rooms, F&B y Tours —las mismas cuentas GL— está `Variable`; y
   `Renting` de Transportation ($64.528) está `Fixed Cost` siendo costo de venta.

---

## A0.-8 · ✅ LIMPIADO (2026-08-16) — el dato de prueba de $51.886 en los cinco 2027

Los cinco presupuestos 2027 que no son el `Working` —`Draft1`, `Draft2`,
`Draft3`, `Draft4-BIG` y `Final`— repartían **$51.886,44 cada uno**
(**$259.432,19** en total) en concepto de salarios, visible como
`OH_CAFETERIA`. **El número era inventado**, y hay dos mediciones que lo prueban:

1. **El salario es basura tecleada.** La regla `CAMARERO (A)` (`0113` → `0220`)
   traía un `salary_override` de `[1000, 10000, 1, 0, 14, 1, 1, 1, 1, 11, 1, 1]`.
   Diez mil en febrero, uno en marzo, cero en abril. Y `COCINERO A - SUPERVISOR`
   traía `[1500, 0…]` **sin ningún destino**.
2. **La posición no existe.** Las seis reglas apuntan a los códigos de la
   planilla 2026 (`508`, `525`, `598`, `604`, `608`, `612`) y los **129 puestos**
   de los seis escenarios 2027 **no tienen ni uno**. Sin override, esas reglas
   calculan contra el vacío. **Todo lo que salía, salía del override.**

Se copió al abrir cada versión y sobrevivía a los recálculos — el del 16-ago a la
1 AM lo volvió a escribir, así que no se moría solo.

### Lo que se hizo

`scripts/borrar_dato_de_prueba_de_salarios.py` (simula por defecto, escribe con
`--aplicar`): puso los 10 overrides en cero y se recalcularon los cinco.

⚠️ **La baranda:** solo toca la regla si la posición **no existe** en la planilla
de ese escenario. Si existiera, el override podría ser un salario cargado a mano
y eso no es basura. Hoy no se dispara en ninguna.

### El resultado, medido con `foto_lineas`

**45 líneas movidas, 9 por escenario, y ninguna fuera de los cinco.** Y la plata
**no desapareció: volvió a su lugar.**

| línea | antes | después |
|---|---|---|
| `OH_CAFETERIA` | 51.886,44 | **0,00** |
| `OPEX_ROOMS` | 498.335,57 | **550.222,01** |
| `TOTAL_OVERHEAD` | 1.443.019,50 | 1.391.133,06 |
| `TOTAL_OPERATING_EXPENSES` | 1.711.783,30 | 1.763.669,74 |
| `PROFIT_ROOMS` | 2.953.643,31 | 2.901.756,87 |

**GOP, EBITDA y utilidad neta NO se movieron** — no aparecen en el diff. La
reasignación de salarios *mueve* costo, no lo agrega: sacarla devuelve a Rooms
el gasto que el fantasma le estaba mandando a Cafetería. O sea que Rooms venía
mostrando **$51.886 menos de gasto del que tiene**, y su utilidad
departamental **$51.886 más de la real**.

### Lo que NO se hizo, y es del owner

**No se rearmaron las reglas contra el head count 2027.** Eso es lo que se hizo
en el `Working` (da **$103.662,39**) y es una decisión sobre qué deben decir esos
cinco presupuestos, no una corrección de dato sucio. Hoy los cinco quedan con
**$0 de reasignación**, que es lo que corresponde a un escenario cuyas reglas no
encuentran su posición.

---

## A0.-7 · ✅ RESUELTO (2026-08-16) — la `5603` se va al `0162` y es COST OF SALES

**Owner, 2026-08-16:** «así debe quedar el departamento `0162`, debes mover el
`0161` a `0162`» · «cambiá para que no haya duda dónde va el costo» ·
«**en `0162` es COS**» · «`0162` entra en el checkbook con la cuenta mencionada».

### La duda que se saca

La lavandería tenía **dos cuentas de costo en dos secciones distintas**:

| | antes | ahora |
|---|---|---|
| `5301` servicio vendido | `COS_LAUNDRY` · COST OF SALES · `0162` | igual |
| `5603` «Costos 1» | `COH_LAUNDRY` · **OVERHEAD** COST OF SALES · `0161` | **`COS_LAUNDRY` · COST OF SALES · `0162`** |

Las dos líneas se llamaban **«Laundry Cost»**. Ahora el costo de lavandería vive
en una sola línea, en el mismo departamento que su ingreso. `COH_LAUNDRY` queda
sin ninguna cuenta — era su única regla.

### ⚠️ Van DOS reglas, no una

El GL trae **un solo departamento «Lavandería»** y el importador lo manda siempre
al `0161` (`gl_detail_importer.py`, `("lavander", "0161")`). Cambiarle el
`dept_code` a la regla y nada más dejaría **sin regla** al costo que entra por
archivo — y el `0161` no tiene padre del cual heredar, o sea `FALLBACK`. Es el
agujero exacto de la migración 114, que costó **$6.604,12** contados como costo
del Spa.

    (0161, 5603, "Departamento de Lavanderia")  ->  COS_LAUNDRY
    (0162, 5603, "Laundry Revenue")             ->  COS_LAUNDRY

Es la misma pareja que ya tienen la `4700`, la `4701` y la `4702`.

### Y se mueve el DATO, no solo la regla

`actual_entries` y `cost_entries`, `0161 → 0162`: Final 2026 $3.262,98 · April
2026 $1.725,26 · Working 2026 $1.513,50. Patrón de
`consolidar_0240_en_0250.py`: **se mueve el dato, no se inactiva el código.**

### El `0162` entra al checkbook de gastos

Revierte lo decidido el 14-ago («el `0162` es solo ingreso»), y a propósito: si
el departamento lleva COS y no se puede digitar, **no hay dónde presupuestar el
costo de lavandería del 2027** — el agujero medido en [A0.-5](#a0-5).

**La derivación no se tocó.** Sigue siendo «tiene reglas de clase 5/7 propias que
no son cuentas de reparto»; la `5603` no la escribe ningún motor, así que el
`0162` entra solo. Lo que se actualizó son las dos pruebas que fijaban el estado
viejo — y la nueva verifica que entre **por la `5603` y solo por ella**, para que
la `5301` no se cuele por la puerta que se abrió.

### Lo que se mueve, y cómo se verifica

**$6.501,74** de `OVERHEAD COST OF SALES` a `COST OF SALES` en tres escenarios,
dos de ellos `locked`. **El GOP no cambia** —los dos lados caen en el mismo
subtotal—, así que esto **no** se verifica con `foto_pl_totales`: la foto de
antes está en `scripts/_antes_5603.json` y se compara **después del deploy**.

**Efecto buscado:** era la única diferencia que hacía que el **Resumen** le
ganara al **Detalle** en los tres escenarios de 2026 ([A0.-5](#a0-5)). Con la
`5603` del lado del gasto operativo, los siete controles cierran y vuelve a
mandar el mayor — que es la regla del owner.

### ✅ VERIFICADO EN PRODUCCIÓN (2026-08-16, `git_sha 07a543e6d6a9`, alembic 118)

El seed y la migración entraron de verdad, no «en verde»: **1.098 reglas**
(eran 1.097), la `5603` con sus dos, `COH_LAUNDRY` en **0 cuentas**, y **ni una
fila de la `5603` quedó en el `0161`**.

| | antes | después |
|---|---|---|
| residuo del `0161` | **$5.933,72** en 4 escenarios | **$357,52** en 1 |
| `BUDGET Final 2026` | manda el RESUMEN | **manda el DETALLE** · los 11 controles en 0,00 |
| `FORECAST Working 2026` | manda el RESUMEN | **manda el DETALLE** · los 11 controles en 0,00 |
| `FORECAST April 2026` | RESUMEN, 3 controles fallando | RESUMEN, **1** — y es el impuesto |

Lo que queda del residuo es el diciembre del `ACTUAL 2025` (−357,51), que el
owner ya decidió dejar. Y lo único que retiene al `April 2026` es
`NET_PROFIT +17.881,10`, que es **la provisión de impuesto** — el punto que
[A0.-2](#a0-2) deja abierto: si el validador compara o excluye esa línea.

### ⚠️ El efecto fue MUCHO más grande que los $6.501,74

La estimación previa —«mueve presentación, $6.5k entre secciones»— **se quedó
corta**. El movimiento de la `5603` es chico; lo grande es su consecuencia:
**dos escenarios cambiaron de base de reporte**, y el Resumen y el Detalle usan
**vocabularios de línea distintos**. `foto_lineas` midió **102 líneas movidas**,
~51 por escenario:

* la familia del Resumen se va a cero — `OPEXP_*`, `OVH_*`, `OPPROFIT_*`,
  `MGMT_FEE`, `PROPERTIES_INSURANCE`…
* la del Detalle se llena — `OPEX_*`, `OH_*`, `COS_*`, `OPERATING_PROFIT`,
  `EBITDA_AFTER`…

**Ni un dólar se perdió**, y está medido: `verificar_los_historicos` da **CUADRA**
en los dos, con los **once** controles en 0,00 — incluido «No operativo (renta,
fees, seguros)», que es donde asustaba ver `TOTAL_MGMT_FEES → 0`. Ese cero es
cambio de vocabulario, no plata que se fue.

**La lección:** al cambiar de base de reporte, la unidad de medida no es la
cuenta que se movió — es el reporte entero. `foto_pl_totales` habría dicho
«IDÉNTICO» en las dos.

Migración **118**. Sigue abierto de contabilidad: **la `5603` no existe en 2027**;
ahora hay dónde cargarla.

---

## A0.-6 · ✅ ALINEADO (2026-08-16) — la plantilla de salarios decía 2 camareras y no había 2

La plantilla de reasignaciones de salario
(`backend/app/seed_data/CWL/reasignaciones_salario.json`, lo que propone el botón
**«Armar plantilla»** de Allocations → Salary) traía `ROOM ATTENDANT` con
`fte: 2.00`. La regla guardada en `BUDGET Working 2027` mueve **1,00**.

**No era una decisión pendiente del owner: era un arrastre estructural.** El 2,00
venía de la planilla 2026, donde UNA posición (`508 CAMARERO (A)`) cargaba varios
FTE y «2» quería decir «dos camareras» — y así sigue guardado en los Draft2-4 y
el Final 2027, que son de esa época. En el head count 2027 **cada camarera es su
propia posición**: `0113-03` a `0113-15`, **1,0000 FTE cada una**. Sobre esa
estructura, un 2,00 reasigna el **doble del salario** de la posición elegida.

Quedó en **1,00**. Los otros ocho renglones ya coincidían con lo guardado, uno a
uno (`ADVENTURE GUIDE` 0,50+0,50 · `BOAT CAPTAIN` 0,50+0,50 · `DRIVER` 1,00 ·
`PROPERTY SUPPORT` 0,34+0,33+0,33), y el `cafeteria_pct` no hacía falta en el
archivo: el `blank()` de la pantalla ya arranca en 0,20, que es lo que tienen las
nueve reglas guardadas.

**No mueve un número.** La plantilla es una sugerencia: `semillas_api` no la lee
ningún cálculo del P&L, y lo guardado vive en `salary_allocation_config`.

Lo fija `test_ningun_puesto_reasigna_mas_de_un_fte` en
`tests/test_las_semillas_se_sirven_por_ruta.py`: la suma de `fte` por
(departamento, puesto) no puede pasarse de uno. Con el 2,00 viejo, falla.

---

## A0.-5 · ✅ MEDIDO (2026-08-16) — el residuo de la lavandería, y no era rounding

Se midió el `0161` completo, escenario por escenario y mes por mes, con
`backend/scripts/residuo_lavanderia.py` (solo lectura, contra producción). El
`0161` es un departamento de reparto: todo su costo tiene que salir y el
departamento cerrar en cero. Esto mide **lo que no salió**.

### El resultado

| escenario | residuo | qué es |
|---|---|---|
| `BUDGET Final 2026` | **+3.262,98** | la cuenta `5603 «Costos 1»`, entera |
| `FORECAST April 2026` | **+1.725,26** | la `5603`, entera |
| `FORECAST Working 2026` | **+1.303,00** | la `5603`, entera |
| `ACTUAL 2025` | **−357,51** | diciembre: la `4900` acreditó de más |
| `ACTUAL 2024` | 0,00 | no tiene reparto de lavandería (ya sabido) |
| `ACTUAL 2026` | 0,00 | cierra |
| **los seis presupuestos 2027** | **0,00** | el motor cierra exacto, los doce meses |
| `BUDGET Working 2028-2035` | 0,00 | sin costo todavía |

**Suma de todo: $5.933,72.** Y en tres de los cuatro casos el residuo **es una
sola cuenta, dólar por dólar** — no un arrastre de redondeo, que es lo que la
palabra «residuo» venía sugiriendo.

### Lo que cambia respecto de lo que decía A0.0 punto 4

Ahí figuraba una sola celda («Lavandería `0161` diciembre −357,51»). Eso es el
`ACTUAL 2025` y sigue siendo cierto. Lo que faltaba es que **los tres escenarios
de planificación 2026 dejan plata adentro del `0161` todos los meses**, y por un
motivo distinto.

* **La `5603` no es un error: se decidió que quedara ahí.** El 2026-06-29 se
  reclasificó de `OPEX_LAUNDRY` a `OH_LAUNDRY` — es el costo del lavado interno,
  o sea overhead, y se queda en el `0161` a propósito. Lo que esta medición
  agrega es que **es exactamente TODO el residuo** de esos tres escenarios: los
  ±3.262,98 / ±1.725,26 / ±1.303,00 que la puerta del upload ya avisaba por el
  lado del Resumen son **el mismo dinero**, visto desde el otro lado.
* **El `ACTUAL 2025` sí es un descuadre de verdad**, y es el único: la `4900` de
  diciembre acredita $357,51 más que el gasto del mes. El owner ya decidió que
  **no va a volver a subir Corcovado**, así que queda anotado.

### ⚠️ Lo que sí queda para el owner: la `5603` no existe en 2027

En los seis presupuestos 2027 el `0161` no tiene ni una fila de `5603`. Todo su
gasto operativo son **$19.565,22 en la `7400 Operating Supplies`** (más planilla).
En 2026 el mismo departamento traía `7065 Cleaning Supplies`, `7320 Laundry
Supplies` **y** la `5603`.

Resultado: la línea `OH_LAUNDRY` del P&L trae plata en 2026 y **cero en 2027**.
Es una pregunta de contabilidad, no del sistema — si el «Costos 1» se plegó
adentro de la `7400` del presupuesto o si al 2027 le falta esa línea. Se cruza
con los **6 agujeros del 2027** de [A0.-2](#a0-2) y con las 29 cuentas de
alineación de [A0.-4](#a0-4).

### 🔑 Y es la misma cuenta que hace que el Resumen le gane al Detalle

Corriendo `scripts.quien_manda` el 2026-08-16, los tres escenarios que reportan
**desde el Resumen** en vez del Detalle lo hacen por **una sola diferencia**, y
es exactamente ésta:

| escenario | manda | por qué |
|---|---|---|
| `BUDGET Final 2026` | RESUMEN | `TOTAL_OPERATING_EXPENSES` −3.262,98 · `TOTAL_OVERHEAD` +3.262,98 |
| `FORECAST April 2026` | RESUMEN | ±1.725,26 (+ el impuesto, que es otra cosa) |
| `FORECAST Working 2026` | RESUMEN | ±1.303,00 |
| `ACTUAL 2025` · `ACTUAL 2026` | **DETALLE** | reproducen los 7 controles |

**Los tres números son la `5603` de la lavandería, dólar por dólar.** El Detalle
la manda a `COH_LAUNDRY` (overhead) y el Resumen la deja en gasto operativo. No
es ruido: es **una decisión de mapeo sobre una cuenta**, y mientras no se
resuelva esos tres escenarios reportan contra el control en vez de contra el
mayor, que es al revés de la regla del owner («manda el detalle»).

Resolver la `5603` cierra las tres cosas de una: el residuo del `0161`, el
traslado opex↔overhead, y que el Detalle vuelva a mandar en los seis históricos.
**Mueve presentación, no el GOP** —los dos lados caen en el mismo subtotal— pero
mueve dos líneas del reporte, así que se verifica con `scripts/foto_lineas.py`,
nunca con `foto_pl_totales`.

### Dos cosas que se aprendieron midiendo

1. **Medir `allocation_entries` sola no sirve.** Suma cero por construcción —el
   crédito se calcula de lo que se repartió—, así que un balde que nunca se
   repartió es **invisible** ahí. Las 21 combinaciones dan `0,0000` exacto y no
   prueban nada. Hay que comparar contra el **costo** del departamento. Es la
   misma trampa de [[feedback_medir_donde_el_motor_escribe]], del otro lado.
2. **Hay que respetar `actuals_through`.** Medidos los doce meses, el
   `FORECAST Working 2026` daba 1.513,50; salteando los seis meses cerrados —que
   el reporte lee del `ACTUAL` enlazado— da **1.303,00**, que es el número que ya
   estaba documentado. Los 210,50 de diferencia eran junio contado dos veces.

**Y el motor no tiene el problema.** Los dos modos en que podría dejar plata
adentro del `0161` —cero kilos cargados (no reparte nada) o kilos de uniformes
sin ningún FTE que los reciba, el mismo modo de falla que la cafetería de
octubre— **no se dan hoy en ningún escenario**. El script los detecta y los
nombra si aparecen.

---

## A0.-4 · ✅ CONSTRUIDO (2026-08-16) — el setup de la cuenta, en una sola pantalla

**Owner, 2026-08-16 — el otro requisito que destraba clonar propiedades:**

> «Lo que sí quiero que se cumpla es que **el setup de la cuenta esté claro**:
> qué es ingreso, qué es costo, qué es gasto y qué es **gastos de la propiedad**;
> **qué departamento**; y **dónde debe aparecer en el P&L**, para que se alinee
> con los demás años.»

### La verdad ya existía — lo que faltaba era poder verla

El mapeo está sano y es **el mismo para los 20 escenarios**: 1.097 reglas,
0 huérfanas, 0 por descarte, 0 pares ambiguos (auditoría 2026-08-15). El
problema no era la respuesta, era que estaba repartida en once chequeos de un
script que corre en consola, una columna de una plantilla de Excel y un tab que
primero pide elegir un escenario. Nadie puede revisar eso de una sentada, y sin
revisarlo no se le copia el mapeo a Amarena, Oxigen y Ojochal.

### Qué se construyó

**Master Data → El setup de la cuenta** (`/master-data/setup-cuenta`), más
`GET /api/setup-cuenta/` y su Excel de tres hojas. Una fila por
departamento × cuenta con las cinco respuestas:

| | |
|---|---|
| **1. Qué es** | Ingreso · Costo · Planilla · Gasto · **Gasto de la propiedad** — la clase USALI del código |
| **2. Qué departamento** | y si es **madre**, **hijo funcional** o **set de producto** |
| **3. En qué línea del P&L** | la línea exacta y su sección, no el grupo |
| **4. Cómo llegó ahí** | regla propia · heredada del padre · sin departamento · siembra directa · **por descarte** · **sin regla** |
| **5. ¿Se alinea entre años?** | la matriz línea × año de esa cuenta, con el monto |

Se filtra por clase, por departamento y por texto; y hay un interruptor que deja
solo lo que no está limpio. El Excel baja completo o solo lo que hay que revisar.

### ⚠️ Las dos cosas que NO podía ser, y cómo se cerraron

1. **Una segunda lista.** No hay ni un rótulo escrito a mano: las reglas salen
   de `account_mapping`, los departamentos del `department_catalog`, las líneas
   del `report_line_config`. El día que el seed cambie, la pantalla cambia sola.
2. **Un resolvedor propio.** Llama a `pl_engine.construir_resolvedor`, el mismo
   del motor. Lo cuida `test_setup_de_la_cuenta.py`, que además prohíbe que
   reaparezcan `lookup_exact` / `lookup_by_acct` / `_cadena_de_padres` adentro.

### Dos cosas que se aprendieron midiendo, y que ninguna se ve leyendo el código

- **Los gastos del propietario NO pasan por el mapeo.** `nonop_entries` siembra
  su `report_line_code` directo y viene SIN departamento, así que el resolvedor
  los devuelve como FALLBACK. La primera versión acusaba de «por descarte» a la
  `8025` ($102.000) y la `8040` ($312.000) del Budget Working 2027, que están
  bien. Ahora se rutean por su línea sembrada y lo único que se les verifica es
  que esa línea exista en el reporte.
- **La alineación hay que medirla solo entre departamentos VIVOS en los dos
  años.** El Club (260) y Claro del Bosque (0205) empiezan en 2027 e Innoceana
  (0155) termina en 2026: sin ese filtro, TODA cuenta de planilla y de gasto
  «cambiaba de línea» y la lista era ilegible.

### Resultado sobre el catálogo real (2026-08-16)

`1.122` combinaciones departamento × cuenta, `237` cuentas distintas.
**`0` por descarte y `0` sin regla** — el mapeo confirma que está limpio.
`764` combinaciones todavía sin movimiento (mapeo provisionado por adelantado,
que es lo correcto: una cuenta sin regla es una cuenta donde no se puede
digitar). Quedan **`29` cuentas para que el owner mire** en la pestaña de
alineación: no son errores de mapeo —un par (departamento, cuenta) nunca cambia
de línea— sino cuentas que se dejaron de usar en un departamento que sigue vivo.
Las cinco más grandes: `6025` Cafeteria ($262 mil), `6010` Commissions
($193 mil), `7175` Entertainment—In-House ($117 mil), `7400` Operating Supplies
($112 mil) y `6000` Salary and Wages ($97 mil). Las 29 salen ordenadas por plata
en la pestaña «¿Se alinea entre años?» y en la segunda hoja del Excel.

**Años que se compararon** (uno por año, con la regla del owner):
2024 → ACTUAL · 2025 → ACTUAL · 2026 → FORECAST Working · 2027 → BUDGET Working.

### Lo que queda

- Que el owner recorra las 29 y diga cuáles son un agujero del presupuesto 2027
  y cuáles un cambio de criterio contable. Se cruza con los **6 agujeros del
  2027** de [A0.-2](#a0-2).
- El ingreso de un escenario en modo checkbook se deriva de drivers y **no pasa
  por el mapeo de cuentas**, así que la clase 4 de 2027 no tiene traza por
  cuenta. No es un defecto de esta vista; es cómo se construye el presupuesto.

---

## A0.-3 · ✅ CERRADO (2026-08-16) — el archivo de actuales trae su propia verificación

**Owner, 2026-08-16 — y es el requisito que destraba clonar propiedades:**

> «Necesito que el upload de los resultados **tenga la verificación arriba versus
> el detalle abajo**. Sobre todo para las nuevas propiedades, que tengo que subir
> los actuales. Para Corcovado no hay problema, pero para las otras, **que debo
> empezar desde cero**, sí ocupo que tenga esa validación — o al menos quizás
> algunas **cuentas de control básico**: ingresos, GOP, EBITDA y net profit.
> Así el sistema **consolida el detalle y valida que estos resultados hagan
> match**.»

### Por qué esto va PRIMERO

En Corcovado hay tres años cargados: si algo entra mal, se nota comparando. **En
una propiedad nueva no hay contra qué comparar.** El archivo entra, el P&L sale,
cuadra consigo mismo, y nadie se entera hasta meses después. Es el modo de falla
que este sistema ya tuvo tres veces este mes — **el total cuadra y la plata está
en otro lado**.

La validación tiene que estar **en la puerta**, no en un reporte posterior.

### La forma del archivo

Un solo archivo, dos bloques:

```
┌─ VERIFICACIÓN (arriba) ─ los totales de control, por mes
│    Ingresos totales · GOP · EBITDA · Utilidad neta
├─ DETALLE (abajo) ─ el mayor, cuenta por cuenta, como hoy
```

El sistema **consolida el detalle** con el mapeo y **compara contra el bloque de
arriba**. Si no coinciden, **el upload no pasa** — o pasa marcado, pero nunca en
silencio.

Los cuatro son el mínimo que pidió el owner. Del análisis del 2026-08-16 sale que
el corte natural son **ocho buckets** (ingresos, gasto operativo, overhead, no
operativo, capital, financieros, depreciación, impuesto); **empezar por los
cuatro** y dejar los otros como aviso, no como bloqueo.

### Lo que ya está medido y hay que respetar

- ⚠️ **Validar por BUCKET, no línea por línea.** **34 de las 106 líneas del
  reporte no existen en el vocabulario del Resumen** (todos los `COS_*`, `COH_*`,
  `REV_FB_BEV`, `OH_CAFETERIA`, `OH_LAUNDRY`, `FINANCIAL_LOSSES`…). Un validador
  por línea daría 26–28 rojas por escenario **sin un solo error**, y el owner
  dejaría de mirarlo. Por bucket, el Actual 2025, el 2026 y el Working 2026 dan
  **cero**.
- ⚠️ **El impuesto va en su propia sección.** Es la única línea donde una
  diferencia puede significar «se subió una provisión que los libros no tienen»
  en vez de «el dato está mal». Mezclarlo hace que April 2026 se vea roto cuando
  su GOP y su EBT cuadran exactos.
- ⚠️ **Los forecast toman sus meses cerrados del Actual enlazado.** Cualquier
  comparación tiene que respetar `actuals_through` o mide meses que el reporte no
  usa — es lo que hizo creer que el `Working 2026` estaba desalineado cuando no
  lo estaba.
- El camino de carga ya existe (`POST /scenarios/import-gl-detail/`) y
  `tests/test_upload_viaje_redondo.py` prueba el viaje completo con números
  conocidos. **Es la prueba que protege a los hoteles que se cargan desde cero**:
  la verificación nueva se cuelga ahí.

### ✅ Cómo quedó (2026-08-16)

**El archivo.** La plantilla del Detalle sale con **once filas de control arriba**
(filas 1 a 12, el hueco que ya existía sobre el encabezado) y el mayor abajo,
como siempre. Cada fila trae `VERIF`, si bloquea o avisa, el código, el concepto
y los doce meses:

```
VERIFICACIÓN  Bloquea Sección  Código               Concepto            Ene … Dic
VERIF         SÍ      control  VER_INGRESOS         Ingresos totales
VERIF         aviso   desglose VER_GASTO_OPERATIVO  Gasto operativo (departamentos)
VERIF         aviso   desglose VER_OVERHEAD         Overhead
VERIF         SÍ      control  VER_GOP              GOP
VERIF         aviso   desglose VER_NO_OPERATIVO     No operativo (renta, fees, seguros)
VERIF         SÍ      control  VER_EBITDA           EBITDA
VERIF         aviso   desglose VER_CAPITAL          Capital (reserva + capex)
VERIF         aviso   desglose VER_FINANCIEROS      Financieros
VERIF         aviso   desglose VER_DEPRECIACION     Depreciación
VERIF         aviso   impuesto VER_IMPUESTO         Impuesto de renta
VERIF         SÍ      control  VER_UTILIDAD_NETA    Utilidad neta
── fila 13/14/15: el encabezado del Detalle, intacto ──
```

**Bajan llenos** con lo que hoy reporta el sistema — bajo, corrijo, subo — y en
un **forecast los meses cerrados salen en blanco**: esos el reporte los toma del
Actual enlazado, no del archivo. **Una celda vacía no se compara**, que es lo que
deja subir una propiedad nueva mes a mes.

**Cuando cuadra:** entra sin decir nada especial, y la pantalla muestra la
comparación igual — un control que solo se ve cuando revienta es un control del
que nadie sabe si funciona.

**Cuando no cuadra:** `409`, **sin haber escrito una sola fila** (la verificación
corre antes de cualquier `INSERT`), con la comparación bucket por bucket y mes
por mes. Para seguir hay que volver a subir con `confirmar_diferencias=true` —
botón «Entiendo la diferencia — subir igual». No se rechaza a secas: el owner
puede tener una razón legítima, pero tiene que **verla**.

**Lo medido, corriendo la puerta contra los seis escenarios de Corcovado**
(`python -m scripts.verificar_los_historicos`, solo lectura):

| escenario | resultado |
|---|---|
| `ACTUAL 2025` | **cuadra** — los once controles en 0,00 |
| `ACTUAL 2026` | **cuadra** — los once controles en 0,00 |
| `BUDGET Final 2026` | avisa: ±3.262,98 entre gasto operativo y overhead |
| `FORECAST April 2026` | avisa: ±1.725,26 del mismo corte + 17.881,10 de impuesto |
| `FORECAST Working 2026` | avisa: ±1.303,00 del mismo corte. **GOP, EBITDA y neto en 0,00** |
| `ACTUAL 2024` | **bloquea**: ingresos −3.085,07 · GOP y EBITDA −43.698,37 |

Las tres del `ACTUAL 2024` son las diferencias **ya conocidas y cerradas** (la
`8090`, las filas sin cuenta de Habitaciones, Innoceana), y su utilidad neta da
**0,00**: el ajuste cierra.

El ±3.262,98 / ±1.725,26 / ±1.303,00 que aparece en tres escenarios es **una sola
cuenta**: la `5603 «Costos 1»` del `0161`, que el mayor rutea a `COH_LAUNDRY`
(overhead) y el Resumen no puede expresar —es una de las 34 líneas ciegas—, así
que la cuenta cae en gasto operativo. **Es presentación pura: netea a cero dentro
del GOP**, y por eso avisa en vez de bloquear. Es exactamente el argumento de
validar por bucket.

⚠️ **Lo que la puerta destapó, y es del owner decidir:**

1. **El viaje redondo del `ACTUAL 2025` mueve $98,02.** Es el residuo conocido de
   que *los repartos no netean exacto* (Cafetería `0220` julio +685,93 y
   diciembre −230,26; Lavandería `0161` diciembre −357,51 = **+98,16**, punto 4
   de A0.0). Bajar y volver a subir sin tocar nada lo borra, y el GOP se mueve
   esos $98. Como el owner ya dijo que **no va a volver a subir Corcovado**,
   queda anotado y no se tocó.
2. **En modo REEMPLAZO (`merge=false`) la carga es asimétrica** y la puerta ahora
   lo dice: las contrapartidas de reparto sobreviven al borrado (correcto, el
   archivo no puede traerlas) pero el **gasto** de `0220`/`0161` que las
   compensa **sí se borra**, porque el parser lo excluye a propósito. Resultado:
   el overhead del `ACTUAL 2025` caería **−196.326,17**. La app siempre sube en
   `merge=true`, donde los dos lados se van juntos y netea, así que hoy no muerde
   — pero es plata de verdad y el arreglo mueve un resultado ya revisado.

**Dónde está:** `app/importers/verificacion.py` (puro, sin base) ·
`gl_detail_importer.parse_gl_detail` lee el bloque · `detail_excel` lo escribe ·
`scenarios_api.import_gl_detail` es la puerta · `scripts/verificar_los_historicos.py`
la corre contra lo que ya está cargado · 17 pruebas nuevas en
`tests/test_upload_viaje_redondo.py`.

⚠️ **La verificación es un CONTROL, no un origen.** Ni un centavo de lo que trae
llega a ninguna tabla, y hay una prueba que lo fija: si lo hiciera sería la
segunda fuente de plata que este bloque existe para cerrar.

---

## A0.-2 · ▶️ NUEVO (2026-08-16) — el Resumen VALIDA al Detalle, y hoy nadie avisa cuando dejan de cuadrar

### El modelo del owner, en sus palabras

> «`Forecast April` es la **foto** que tomé de abril; `Forecast Working` es la
> **versión viva** corriendo hasta que yo guarde otra versión para mayo,
> `Forecast May`, y así sucesivamente. Para todas las versiones **ambas deben ser
> válidas**. El **detalle** es importante porque es la forma de manejar reportes.
> El **validado** es la forma de decir que el detalle está bien y que el resumen
> valida eso. **Para mí ambos son importantes.**»

O sea que las dos fuentes tienen **roles distintos y complementarios**, y ninguna
es «la que gana»:

| | qué es | para qué sirve |
|---|---|---|
| **Detalle** (`actual_entries`) | el mayor, cuenta por cuenta | es **con lo que se reporta** |
| **Resumen** (`actual_pl_lines`) | el P&L ya sumado, 54 líneas × 12 meses | es **el control**: confirma que el detalle está bien |

**El Resumen no es una fuente alternativa: es la prueba de que el detalle es
correcto.** Cuando cuadran, el detalle está validado. Cuando no cuadran, hay algo
que arreglar — **no hay que elegir uno**.

### El defecto: el motor se calla

Hoy `_detalle_fino_si_cuadra` usa el detalle **solo si sus siete totales anuales
coinciden** con el Resumen; si no coinciden, **cae al Resumen sin decir nada**.
Para el modelo del owner eso está al revés: el desacuerdo es exactamente la
señal que él quiere ver, y el sistema la usa para elegir en silencio.

Peor: como el Resumen «gana», el P&L sigue saliendo y cuadrando consigo mismo,
así que **nada se ve raro**. Es el mismo modo de falla que ya costó caro dos
veces este mes: el total cuadra y la plata cambió de lugar sola.

### El caso vivo que lo destapó: `FORECAST Working 2026`

Medido el 2026-08-16:

- Su Resumen es **el Resumen de April con dos retoques a mano**: Mantenimiento
  **+12.000,00** y Ventas **+1.700,00**. De las 54 líneas solo difieren 8, y las
  otras 6 son el arrastre aritmético de esos 13.700 (GOP, EBITDA, EBT, impuesto,
  neto). **Ninguna línea de ingreso, costo ni planilla se movió.**
- Mientras tanto su Mayor **sí se actualizó**: **+26.617,09** de ingreso 4xxx
  contra April (5.015.348,01 vs 4.988.730,92) y +42.472,75 en total.

Conclusión: **el Resumen del Working nunca se regeneró.** Se heredó de la foto de
abril, se le tocaron dos líneas de overhead, y el mayor siguió actualizándose por
su cuenta. Hoy el Working reporta contra un control viejo.

### Qué hay que construir

1. **Un estado de validación por escenario**, visible: *«Resumen y Detalle
   cuadran»* / *«no cuadran, y acá está la diferencia por línea»*. Que el
   desacuerdo se **muestre**, no que se resuelva solo.
2. ~~**Regenerar el Resumen desde el Mayor** conservando los ajustes manuales.~~
   ❌ **SE CAE (2026-08-16).** Regenerar el Resumen **es, por definición,
   escribir encima de lo que se subió** — justo lo que el owner cerró ese día
   («no muevas nada en lo que se subió», `DECISIONES` §3.b). Y ya no hace falta:
   este paso nació cuando el Resumen era lo único que validaba al Detalle, y hoy
   **las cuentas de control del archivo** ([A0.-3](#a0-3)) hacen esa validación
   **en la puerta**. Owner: «ya lo tenía… metimos cuentas de controles».
   El Resumen conserva **un** trabajo: ser el origen donde el Mayor no puede
   reproducir — hoy el `ACTUAL 2024` y el `FORECAST April 2026`, los dos por
   decisión ya tomada.

3. ~~**Que guardar una foto exija que el escenario esté validado.**~~
   ⚠️ **NO TIENE SUPERFICIE VIVA (medido 2026-08-16).** El riesgo que describe
   —una foto que nace desalineada y nunca se vuelve a tocar— **hoy no existe**:

   | qué podría congelar | ¿congela números? | ¿alguna pantalla lo llama? |
   |---|---|---|
   | `cashflow_versions` desde escenario (`POST /cashflow-versions/working/`) | **sí** | **no** — está en `lib/api.ts`, ninguna pantalla la usa |
   | `cashflow_versions` desde Excel (`/import/`) | sí, pero sus filas vienen del archivo, no de un escenario | **no** |
   | `big_picture_versions` | **no** — guarda los % de crecimiento y **recomputa** desde la base | **sí**, `/planning/big-picture` |
   | copiar o archivar un escenario | no — recomputa con el motor de hoy ([[project_finplan_cwl_enllavar_no_congela]]) | sí |

   Poner el gate ahí sería **proteger una puerta por la que nadie pasa**.

3.b **Lo que SÍ está vivo y es el mismo riesgo:** `/planning/big-picture` elige
   un **escenario base** y construye el presupuesto 2027 entero encima, **sin
   decir si esa base cuadra**. Armar el 2027 sobre el `ACTUAL 2024` —que reporta
   desde el Resumen con $43.698 que no llegan al P&L— no avisa nada.
   El arreglo es barato y es el principio del paso 1: **que el desacuerdo se
   muestre**. `GET /reports/cuadre/{id}/` ya devuelve el veredicto con su motivo;
   falta mostrarlo al lado del selector de base. **No empezado.**

~~⚠️ La línea de **impuesto** se va a mover siempre: el motor la recalcula desde
el EBT y el Resumen carga la que se subió. Hay que decidir si el validador la
compara o la excluye~~ ✅ **DECIDIDO el 2026-08-16 — NO se toca**
(`DECISIONES_DEL_OWNER.md` §3.b): «no muevas nada en lo que se subió, dejá igual
los taxes… no recalcules nada».

Se construyó la exclusión y **se midió antes de proponerla**: hacía que el
`FORECAST April 2026` pasara a reportar desde el Detalle, y eso arrastraba cuál
impuesto se reporta — `INCOME_TAXES` 39.197,30 → 21.316,20 y `NET_PROFIT`
−40.189,78 → **−22.308,68**, o sea **$17.881,10** en un escenario `locked`, más
55 líneas re-expresadas. **Revertido**, y `quien_manda` verificado igual a lo
desplegado.

**La regla queda ampliada:** «en los históricos solo vale lo subido» **incluye el
impuesto**. El `April 2026` sigue mandando por Resumen a propósito.

---

### ✅ HECHO (2026-08-16) — paso 1: la compuerta juzga los meses correctos, y dice por qué

**No movió un solo número.** Verificado con `scripts/foto_lineas` (119 líneas ×
20 escenarios) aislando el cambio sobre HEAD limpio: *IDENTICO*.

1. **La compuerta ya no juzga los doce meses siempre**, sino los que el
   escenario **reporta con sus propias fuentes** (`recalculate.meses_propios`,
   espeja el desvío del rolling forecast). Un forecast con corte toma sus meses
   cerrados del ACTUAL enlazado: descuadrar por esos meses era medir dato que
   nadie lee.
2. **La elección dejó de ser muda.** `recalculate.veredicto_del_detalle`
   devuelve la decisión **con su motivo**, los meses evaluados y la diferencia
   de cada total de control que no cuadra. Se publica en
   `GET /reports/cuadre/{id}/` (campo `veredicto`), en
   `GET /reports/cuadre/?con_veredicto=1` (todos de una) y en
   `python -m scripts.quien_manda`.

#### Cuál manda hoy, y el descuadre que queda

| escenario | manda | meses que pesan | qué queda descuadrado |
|---|---|---|---|
| ACTUAL 2024 | resumen | 1–12 | ingreso −3.085,07 · opex +40.613,30 · **GOP/EBITDA −43.698,37** |
| ACTUAL 2025 | **detalle** | 1–12 | — |
| ACTUAL 2026 | **detalle** | 1–12 | — |
| BUDGET Final 2026 | resumen | 1–12 | opex ↔ overhead **3.262,98** (neto cero) |
| FORECAST April 2026 | resumen | 5–12 | opex ↔ overhead 1.725,26 · **impuesto +17.881,10** |
| FORECAST Working 2026 | resumen | 7–12 | opex ↔ overhead **1.303,00** (neto cero) |

**Ninguno cambió de lado**, que es por qué no se movió nada.

⚠️ **El Working 2026 no quedó cuadrado, quedó DIAGNOSTICADO.** Sobre 12 meses
descuadraban los 7 totales; respetando su corte, ingreso, GOP, EBITDA, EBT e
impuesto quedan en **cero diferencia** y sobrevive un solo traslado real:
**$1.303,00 de `OPEX_LAUNDRY` a `COH_LAUNDRY`** — el detalle manda la lavandería
a overhead y el resumen la deja en gasto operativo. Es una decisión de mapeo, no
ruido. Lo mismo, más grande, en el Budget Final 2026 ($3.262,98) y en el April
($1.725,26).

---

## A0.-1 · ✅ CONSTRUIDO (2026-08-16) — el provisionamiento se hace por departamento MADRE

Owner: **«los departamentos que se provisionan son los departamentos madres, y
cuando escogés una madre automáticamente adoptás todo el paquete»**.

Hoy la matriz de provisionamiento (`/master-data/provisioning`) lista los **39
departamentos sueltos**, hijos incluidos. O sea que se puede prender Housekeeping
y apagar Front Desk, cuando los dos son la misma Habitaciones — y peor, se puede
dejar una combinación que no existe en el negocio.

> ### ✅ Hecho el 2026-08-16 — y una cosa que hay que decidir
>
> La matriz pasó de **39 filas planas a 23 filas madre**. Cada una lleva su
> paquete adentro —hijos funcionales **y** sets de producto— y las cuatro
> casillas hablan por el paquete entero: los datos se suman y apagar arrastra.
> La expansión vive en el **backend** (`_expandir_al_paquete`), no en la
> pantalla: si la hiciera el navegador, otro cliente podría seguir dejando un
> hijo prendido con su madre apagada. Mandar un hijo suelto ahora da **422** con
> el código de la madre.
>
> **No se cambió el estado de NADA.** Sin migración, sin tocar
> `dept_enablement`: las 4 casillas apagadas de hoy siguen apagadas y ninguna
> otra se apagó. Está comprobado casilla por casilla en
> `test_provisionamiento_por_madre.py` con el catálogo real y el estado real.
>
> **▶️ LO QUE FALTA DECIDIR (owner):** el `0180` en PLANILLA **no se puede
> representar** con la regla nueva. Hoy la madre está apagada y sus cinco hijos
> —`0181` Gerencia, `0182` Finanzas, `0183` Compras, `0184` RRHH, `0186`
> Seguridad, los que llevan la planilla de Administración— están prendidos. Con
> un solo interruptor por paquete eso no existe. **No se resolvió**: la casilla
> sale marcada **«mixto»** en la pantalla, con el detalle de quién está apagado,
> y no se tocó nada — resolverlo hacia «apagado» escondería la planilla de los
> cinco, y hacia «prendido» borraría una decisión que alguien tomó. Las dos son
> cambios que nadie pidió. Es la única casilla mixta de toda la matriz.
>
> Sigue abierto de la sección de abajo: **el set no lleva interruptor propio**
> —derivarlo de «tiene unidades/porcentaje asignado»—, que es otra decisión del
> owner (hoy `0115` y `0116` están en cero y una regla derivada los apagaría).

### Qué hay que hacer

1. **La matriz muestra solo madres.** Un departamento es madre si no tiene
   `parent_dept_code`.

   **✅ RESUELTO (owner, 2026-08-15):** «la estructura `0110` conlleva implícito
   `0115` y `0116` como **estructura primaria**, y todos los hijos, que ya lleva
   por default». El paquete de una madre son **todos** los que cuelgan de ella:
   hijos funcionales **y** sets de producto.

   **Pero el set no lleva interruptor.** Owner, mismo día: «para Corcovado sí se
   activan `0115`/`0116`, pero quizás para otros hoteles no… y eso depende de si
   asigno **% / unidades disponibles**».

   O sea: **un set se activa solo, cuando la propiedad le asigna unidades o
   porcentaje.** No es una casilla que alguien prende — es una consecuencia del
   dato. Es el mismo criterio con el que se resolvió `lleva_gasto` el 14-ago:
   derivarlo, no mantenerlo a mano. Un hotel sin Villas simplemente nunca les
   asigna unidades, y desaparecen sin que nadie tenga que acordarse.

   ⚠️ **Hoy `0115` y `0116` están en CERO** — los porcentajes los tiene que
   cargar el owner. Así que la regla derivada, aplicada hoy, los apagaría. Al
   construir esto hay que decidir si el corte es «tiene unidades asignadas» o
   «existe la fila del set», y confirmarlo con el owner antes, porque Corcovado
   **sí** los quiere activos.

   ⚠️ Y el matiz que hay que respetar, porque «paquete» significa dos cosas
   distintas en dos lugares:

   | | qué agrupa | quién manda |
   |---|---|---|
   | **Provisionamiento** (visibilidad) | madre + hijos funcionales + sets | `parent_dept_code` a secas |
   | **Motor del P&L** (cálculo) | madre + hijos funcionales, **sin los sets** | `CHECKBOOK_DEPT_CONSOLIDATION` |

   El catálogo tiene 16 con padre; el motor consolida 14. Los dos de diferencia
   son justo `0115` y `0116`, que tienen `room_set = True` y **netean contra
   Rooms de otra forma**. Esta decisión une los dos criterios **solo para
   provisionar**: en el cálculo la bandera `room_set` sigue mandando, y los sets
   **siguen teniendo checkbook de gasto propio** (30 cuentas cada uno) — que es
   lo que sacarlos por error costó anteayer. Ver
   [`test_quien_lleva_gasto.py`](../backend/tests/test_quien_lleva_gasto.py).

   **Esto es lo primero multipropiedad de verdad del provisionamiento:** el
   paquete es igual para todos los hoteles, pero **qué se activa adentro sale del
   dato de cada propiedad**, no de una matriz que alguien mantiene.

2. **Elegir la madre arrastra el paquete.** Prender o apagar `0110` tiene que
   prender o apagar `0111`, `0112`, `0113` y `0114` con ella, en la dimensión que
   se tocó. La cadena sube recursiva (`0132 → 0130 → 0140`), así que el paquete
   se arma con `_cadena_de_padres`, no con un salto.
3. **Migrar lo que ya está apagado.** Hoy hay 4: `0156` en COST/OPEX/PAYROLL y
   **`0180` en PAYROLL**. Ese último es el que hay que mirar antes de migrar: si
   apagar la madre arrastra a los hijos, apagar `0180` en PAYROLL apagaría
   también `0181`, `0182`, `0183`, `0184` y `0186` — **que son justamente los que
   llevan la planilla de Administración**. Hay que preguntarle al owner si eso es
   lo que quiere o si ese apagado hoy significa otra cosa.

### Cómo se ve hoy la pantalla (para saber qué se está reemplazando)

`Master Data → Provisioning`, confirmado con captura del owner el 2026-08-15:

- **39 departamentos en una lista plana**, hijos incluidos y al mismo nivel que
  las madres. «4 casillas apagadas» de un total de 39 × 4.
- **Cuatro columnas por fila** —Ingreso · Planilla · OPEX · Costos— cada una con
  su casilla independiente, más un `descartar` por fila.
- Cada fila dice su parentesco en el subtítulo («hijo de 0110») y cuántas líneas
  tiene en todos los escenarios. Ese subtítulo ya sabe quién es hijo: la
  información está, lo que falta es que la **estructura** la use.
- `0115` y `0116` muestran «—» en Ingreso (no lo llevan) y sí Planilla, OPEX y
  Costos, con **180 líneas cada uno**.

Lo que se reemplaza es el **nivel de detalle**: hoy se puede prender Housekeeping
y apagar Front Desk, o dejar un hijo prendido con su madre apagada, y nada avisa.

### ⚠️ Lo que NO puede cambiar

**El provisionamiento filtra VISIBILIDAD, nunca el cálculo.** Un departamento
apagado sigue sumando en el P&L; solo deja de verse en los selectores. La
pantalla lo advierte antes de dejar apagar. Este cambio es de agrupación, y no
puede convertirse por accidente en un filtro de cálculo.

**Encaja con la regla del 14-ago** —«solo los departamentos padres pueden tener
checkbook de gastos»—: el provisionamiento pasa a hablar el mismo idioma que el
resto del sistema, en vez de ofrecer un nivel de detalle que ninguna otra
pantalla respeta.

---

## A0 · Abierto al 2026-08-14 — el mixer de canales y el escenario por defecto

> Lo de este día. Todo lo demás de la sección A es anterior y ya cerrado.

### A0.0 · ▶️ RETOMAR ACÁ — la plantilla del Detalle (2026-08-14, tarde)

La plantilla ya sale con la estructura del owner (`ORDEN PARA EL UPLOAD.xlsx` →
`seed_data/orden_plantilla.json`). Lo que sigue abierto, en orden de valor:

1. ~~**Consolidar 0240 en 0250 (Property Expenses).**~~ ✅ **CERRADO 2026-08-14**
   (commit `a4cba05`). Eran el mismo departamento con dos códigos: el dato en
   `0240`, las 10 reglas en `0250`. Se movió el dato, no se inactivó el código.
   * `belowgop_account_entries` **0240 → 0250** — 42 filas, 3.503.914,76.
   * `revenue_account_entries` **0250 → 280** — 12 filas, 1.024.549,60. Las 48xx
     de Miscelaneos/Sustainability no son gasto de la propiedad; es la misma
     corrección que `retag_0240_a_280.py` ya había hecho en `actual_entries`,
     sobre la tabla que quedó afuera.
   Las 54 filas llegaban a su línea por **FALLBACK** y ahora llegan a la **misma**
   línea por **regla exacta**. `scripts/consolidar_0240_en_0250.py` lo comprueba
   cuenta por cuenta y aborta si alguna cambiaría; `foto_pl_totales` antes/después
   dio **IDÉNTICO**. El `0240` ya no existe en ninguna tabla.
   El bloqueo de las «reglas propias de planilla y opex» lo cerró el owner:
   **«0250 no hay planilla, solo gastos de la propiedad»** — no le faltan reglas,
   le sobrarían. Ya tiene nombre en el catálogo («Gastos de la Propiedad») y está
   declarado en `SIN_NUCLEO_A_PROPOSITO` como el espejo del `280`.

2. ~~**13 cuentas resuelven por DESCARTE y 1 no tiene regla**~~ ✅ **YA NO
   QUEDA NINGUNA** — medido de nuevo el 2026-08-16 con
   `python -m scripts.auditoria_mapeo` contra producción: **`FALLBACK 0.00`**
   sobre las 1.097 reglas y las 119 líneas del reporte. Coincide con lo que ya
   había medido [A0.-4](#a0-4) sobre el catálogo entero (0 por descarte, 0 sin
   regla). Aquellas 13 se habían medido antes de que los gastos del propietario
   se rutearan por su línea sembrada, que era lo que las hacía figurar.
   **Lo único que sigue sin llegar al P&L es la `8090`** (punto 2.1): `DROP`,
   **−43.600,21** (los −43.698,37 del 2024 más los +98,16 del 2025), y el owner
   ya decidió el 15-ago que **queda como está** hasta que vuelva a subir 2024.

2.1. ⚠️ **La `8090` no llega al P&L.** Salió al medir lo de arriba: la cuenta
   `8090` «Financial Losses (ajuste recon.)» resuelve **DROP** —no tiene regla en
   ningún departamento—, así que sus **−43.698,37** del `Actual 2024` y **+98,16**
   del `Actual 2025` **no entran en ningún reporte**. La creó
   `scripts/ajuste_cuadre_2024.py` para cuadrar el 2024, y hoy el ajuste no se
   aplica. Es la «1 cuenta sin regla» del punto 2, con nombre y monto.
   ✅ **DECIDIDO el 2026-08-15 — queda como está** (`DECISIONES_DEL_OWNER.md` §1):
   «por ahora dejemos tal cual está. Si yo lo subo, decido qué cambio hacer».
   No es una pregunta abierta: se resuelve sola cuando vuelva a subir el 2024.

3. ~~**Unir Administración.**~~ ✅ **YA ESTÁ HECHO** — la nota decía «no
   empezado» y estaba vieja. Medido contra producción el 2026-08-16:

   | depto | reglas de planilla | reglas de gasto |
   |---|---|---|
   | `0180` Administración (madre) | 17 | **35** |
   | `0181` Gerencia | 17 | **0** |
   | `0184` Recursos Humanos | 17 | **0** |

   Es exactamente lo que pidió el owner: «`0181` y `0184` solo tienen planilla,
   sus gastos se postean en la `0180`». Coincide con el chequeo 6 de
   `auditoria_mapeo` («ninguno de los 14 departamentos hijos lleva gasto propio»)
   y con lo que `DECISIONES_DEL_OWNER.md` ya daba por cerrado el 14-ago. El
   `0186` Security no tiene ninguna regla y hereda del `0180` por la cadena de
   padres, que es el comportamiento correcto — no rutea por descarte.

4. **Los repartos no netean exacto** (solo Actual 2025, tres celdas): Cafetería
   0220 julio +685,93 y diciembre −230,26; Lavandería 0161 diciembre −357,51.
   El owner NO va a volver a subir Corcovado, así que queda como está salvo que
   decida lo contrario. Los demás escenarios cierran en cero.
   **▶ La parte de lavandería se midió entera el 2026-08-16: ver [A0.-5](#a0-5).**
   «Los demás escenarios cierran en cero» vale para los ACTUAL y para los seis
   presupuestos 2027, **no** para los tres de planificación 2026, que dejan la
   `5603` adentro del `0161` a propósito.

5. **El Actual 2024 no tiene el reparto**: Cafetería 0220 sin una sola fila y
   Lavandería 0161 solo con ingreso. El motor reparte desde el gasto del
   departamento, así que ese año no lleva costo de cafetería a ningún lado.

⚠️ **Lo que NO hay que rehacer:** desactivar las reglas de `4999`. Se intentó
creyendo que sobraban en 21 departamentos y **movía $92.176,75** de opex a
overhead en Budget Working 2027. `4999` es la cuenta donde el motor de
allocations deposita el crédito de reparto de cada departamento, y no tiene filas
en ninguna tabla del GL porque **la escribe el motor, no el upload**. Revertido y
verificado «IDÉNTICO». Lo que sí se hizo: sacarla de la plantilla, porque no se
digita.

---

### A0.1 · El mixer ya es operativo en 2027 — ✅ CERRADO (2026-08-15), **los seis**

Los seis presupuestos 2027 tenían `revenue_source = "checkbook"`: el ingreso eran
montos digitados, el motor de revenue ni se ejecutaba y el Net Factor era inerte.
La migración **116** pasó cinco de los seis a `drivers`, y la **117** el que
faltaba.

**Lo que se movió, por escenario** (los cinco son la misma carga):

| | antes | ahora | cambio |
|---|---|---|---|
| Ingresos | 5.997.346 | 5.826.131 | −171.215 (−2,9%) |
| GOP | 2.842.543 | 2.671.328 | −171.215 |
| Utilidad neta | 1.567.716 | 1.455.588 | −112.128 |

**El 100% viene del mix.** Medido antes de aplicar: noches ocupadas 4.981,8 y pax
8.967 **idénticos**, venta a tarifa rack $4.331.219 **idéntica**; lo único que
cambia es el Net Factor, 0,8220 (congelado en el checkbook) → 0,7970 (el del
mixer, ya escrito en las 456 tarifas el 14-ago).

⚠️ La estimación vieja de **−$181.000** quedó cerca pero no era el número: son
**−$171.215**. Estaba calculada como si el factor ya manejara el ingreso.

#### El `BUDGET Working 2027` — el sexto, ya adentro (migración 117)

Era la excepción: pasarlo mandaba a cero sus **$125.180 de Club Madresal**,
porque el driver del Club depositaba el ingreso en el checkbook y el camino de
`drivers` no lo leía. Owner, 15-ago: «solo quiero que trabaje **estándar como
todos los departamentos**».

Le faltaba una **lista**, no una rama de Club: las líneas planas del modo
`drivers` estaban escritas a mano (Spa, Retail, F&B misc, Innoceana, Lavandería)
y el Club no figuraba. Hoy la lista se deriva de las líneas de ingreso, y todo
driver deja su resultado en las **dos** fuentes por un camino compartido
(`app/api/_ingreso_de_driver.py`). **El Spa tenía el mismo agujero** y quedó
cubierto por el mismo mecanismo, sin mover ninguno de sus números.

| `BUDGET Working 2027` | antes | ahora | cambio |
|---|---|---|---|
| Ingresos | 6.449.238 | **6.374.026** | **−75.212** |
| GOP | 2.799.112 | 2.723.900 | −75.212 |
| Utilidad neta | 1.180.322 | 1.133.549 | −46.773 |
| REV_CLUB | 125.180 | 125.180 | **0 — intacto** |
| PROFIT_CLUB | −228.471 | −228.471 | **0 — intacto** |

−118.218 del mix (Room Revenue) y +43.006 de ocupación: el escenario tiene **8**
tipos de habitación cargados contra los **6** con que se congeló su checkbook.
**Los otros diecinueve escenarios quedaron idénticos línea por línea.**

Lo cuidan `tests/test_los_2027_leen_los_drivers.py` (que ningún 2027 vuelva a
quedarse afuera, y que la lista se siga derivando) y
`tests/test_los_drivers_llegan_al_pl.py` (que todo driver pase por el camino
compartido).

### A0.2 · «Crear copiando» copia del Budget 2035, que está VACÍO

En `app/scenarios/page.tsx` el `sourceId` (origen de la copia) **sí conserva el
bug del año más nuevo**: `all.sort((a,b) => b.year - a.year)` y después el primer
BUDGET ⇒ por defecto copia de **Budget 2035**, que no tiene datos. Un escenario
creado sin cambiar el desplegable a mano **nace en blanco**.

Probablemente explica por qué los Working 2028–2035 están vacíos. Se dejó sin
arreglar a propósito: hay que decidir cuál debe ser el origen por defecto.

Segundo defecto en el mismo archivo: `load` está en un `useCallback` con
dependencia `[sourceId]` y se dispara desde un `useEffect`, así que **cambiar el
origen del desplegable recarga toda la pantalla**, incluido
`ensureWorkingBudgets(2027, 2035)`.

### A0.3 · Preguntas del mixer sin contestar

1. **¿La OTA cobra 0% (cuadro del owner) o 20% (lo que usaba FinPlan)?** Sospecha:
   son cosas distintas — tarifa neta contra comisión — pero una de las dos está
   mal para el cálculo.
2. **Budget Final 2026 tiene UN solo mes** de canales cargado, y sus tarifas
   (0.8360) ya no coinciden con sus canales (0.8220). Gana la tarifa. El owner lo
   dejó afuera del mixer: «ya es lo que es».
3. Los tres canales de atribución —CRC direct, Direct groups, Executive personal—
   **no se pueden comparar contra lo que de verdad pasó**: Opera no registra quién
   trajo la reserva. Hay que digitarlo o sacarlo de un campo de agente del PMS.

### A0.4 · Menores, ya identificados

* **`reports/tax` no recuerda el escenario** a propósito: su botón Aplicar
  **escribe** los parámetros de impuesto en el escenario elegido. Se le arregló
  solo el default. Si el owner quiere memoria, es una línea.
* ~~**`components/TopNav.tsx` llama hooks condicionalmente**~~ ✅ **ARREGLADO
  (2026-08-16).** Los cuatro hooks del panel (`useRef`, `useState` y dos
  `useEffect`) vivían **debajo** del `return` temprano de los tabs de link
  directo, así que esos tabs salían sin llamarlos. Hoy no rompía —cada tab es
  una instancia con su `group` fijo— pero es una bomba con temporizador: el día
  que un tab gane o pierda su `href`, React aparea el estado de un hook con el
  de otro y **no se parece a un error, se parece a un menú poseído**. Los hooks
  subieron arriba del return; son inertes para un tab de link.
* **Working 2028–2035 sin recalcular** tras aplicar el mixer. Están vacíos, así
  que no urge. El botón «Recalcular» de Master Data → Canales los limpia en
  segundos. Verificar con `python -m scripts.quien_falta_recalcular`.
* ~~**Errores de lint previos**~~ ✅ **CERO ERRORES DE LINT (2026-08-16).**
  Eran **15**, no los dos que decía esta nota — la lista vieja se había escrito
  mirando una salida cortada. Además de los hooks del nav: `getBudgetScenario`
  importado y sin usar en **cinco** pantallas de checkbook, `MONTH_KEYS` que
  solo servía de tipo, un prop `depts` que el modal de costos ya no leía, una
  traducción `t` duplicada en no-operativos, `FTE_KEYS` muerto en planilla, la
  `i` de room-nights y dos comillas sin escapar en opex. `npm run lint` ahora da
  **0**, y `tsc` 0.

---

## A · Depende del owner (dato o decisión)

### A1 · $326,712 de Villas y Residencias — ✅ CERRADO (2026-08-12)

El ingreso de Rooms tenía dos fuentes que no decían lo mismo en el **Budget 2027
Working**:

| | |
|---|---|
| Drivers (las 8 categorías, tarifa × ocupación) | $3,886,972.74 |
| Línea `ROOMS` del checkbook — **la que lee el P&L** | $3,560,260.57 |
| **Diferencia** | **$326,712.17** |

Al abrirlo se vio de dónde salía: la línea del checkbook era **exactamente el
Standard**, mes a mes, con 5 centavos de redondeo en todo el año. Villas
($233,365.80) y Residencias ($93,346.32) se crearon después de que esa línea se
llenó, y nunca entraron. No era un descuadre difuso — era una omisión limpia.

**Qué se hizo.** Se empujó **solo la línea ROOMS**, mes a mes, con los valores
del motor (`room_type_breakdown`), y se recalculó el P&L. Octubre queda en cero
en las dos fuentes porque el mes está cerrado; el ajuste son 11 meses, entre
$27,389 y $30,324 cada uno. Después del cambio el P&L Full Detail del escenario
**no emite ningún aviso**.

**No se usó el botón «Llenar desde drivers» de la pantalla**, y conviene saber
por qué: ese botón reescribe **ocho** líneas —Food, Beverage, Tours, Transport,
Retail, Innoceana, Sustainability— con las tarifas que estén cargadas en la
pantalla en ese momento, y su cálculo de Room Revenue es una reimplementación
del frontend, no el mismo motor. Habría cerrado A1 y de paso movido cinco líneas
que no tenían nada malo.

**Los cinco 2027 enllavados no se tocaron** (Draft1 · Draft2 · Draft3 ·
Draft4-BIG · Final). Los cinco cargan la misma línea de $3,560,260.57 y van a
seguir mostrando el aviso de apertura de Rooms: son fotos cerradas, y decisión
del owner fue dejarlas así. Si algún día se quiere corregir Final, hay que
desenllavarlo y volver a enllavarlo.

**Si vuelve.** Ahora hay herramienta, no receta:

    python -m scripts.empujar_rooms_al_checkbook <scenario_id> --prod            # ensayo
    python -m scripts.empujar_rooms_al_checkbook <scenario_id> --prod --aplicar

Sin `--aplicar` no escribe: imprime el antes/después por mes y la apertura por
categoría. Se niega en escenarios enllavados, suma **todas** las categorías
activas del hotel (si nace otra, entra sola — que es justo lo que falló acá), y
es idempotente. El P&L Full Detail lo sigue avisando solo cuando la apertura de
Rooms no suma lo mismo que el consolidado.

### A2 · Diferencial cambiario (8045) — el diagnóstico de abajo ESTÁ MAL

> **Corregido el 2026-08-12.** Lo que sigue en esta sección era la lectura
> anterior y se dejó para que se vea el error. **No es «falta una fila en el
> archivo».**
>
> **Lo que pasa de verdad:** el motor **no tiene línea de salida
> `FINANCIAL_LOSSES`**. `_NONOP_LINE_TO_BUCKET` la mapea al cajón `bank_interest`
> y `calculate_full_pl` emite cajones, no los códigos del mapeo. Por eso
> `standard_pl_template()` nunca contiene esa línea, y `actual_pl_from_lines`
> —que solo rellena líneas del template— **ignora cualquier fila guardada con ese
> código**.
>
> O sea que el aviso «FINANCIAL LOSSES (detalle −274.89 vs resumen 0.00)» compara
> el GL contra una línea que estructuralmente no puede existir. **La plata no se
> pierde:** los totales (EBITDA_BEFORE, EBT, neto) se guardan del archivo y ya la
> incluyen, y `TOTAL_NON_OP` se deriva como `GOP − EBITDA_BEFORE`.
>
> **Comprobado a la mala:** se escribieron las 36 filas de apertura desde el GL y
> el aviso NO se movió, porque nada las lee. Se revirtieron enteras.
>
> **Y es más grande que la 8045.** El resumen subido trae solo CINCO líneas
> below-GOP (RENT, CAPITAL_RESERVE, DEPRECIATION, INCOME_TAXES, LARGE_CAPEX);
> el GL trae entre seis y nueve cuentas. Management Fee, Property Insurance,
> Other Expenses y Bank Interest **tampoco** tienen línea en el resumen. La
> apertura below-GOP de los escenarios importados no existe: solo existe el
> agregado.
>
> **✅ RESUELTO — el aviso dejó de mentir (2026-08-12).** El chequeo separaba mal
> DOS cosas y las reportaba igual:
>
> * **«sin apertura»** — el resumen trae CERO y el GL tiene monto. **No es un
>   descuadre:** los P&L importados suben el agregado below-GOP, no su desglose.
> * **«no cuadra»** — los dos traen monto y no coinciden. Eso sí es dato que se
>   contradice.
>
> Ahora son dos avisos distintos con dos textos distintos. Verificado contra
> producción: los tres escenarios pasaron de «no amarran con el resumen» a «el
> resumen no trae la apertura — no es un descuadre», que es la verdad. **El
> resultado de esos escenarios siempre estuvo bien.**
>
> Queda **abierto y es decisión del owner**: si se quiere ver el diferencial
> cambiario como renglón propio del P&L, hay que darle línea propia a
> `FINANCIAL_LOSSES` en el motor, separándola de `bank_interest`. Eso cambia la
> presentación below-GOP de **todos** los escenarios y **todas** las propiedades,
> así que no se hizo por cuenta propia.
>
> Afecta a **cinco** escenarios, no tres: Actual 2024, Actual 2025, Actual 2026,
> Forecast April 2026 y Forecast Working 2026.

<details>
<summary>Diagnóstico anterior (incorrecto), para referencia</summary>



El GL tiene una ganancia en la cuenta `8045` que el P&L cargado no incluye
(su snapshot trae solo cinco líneas below-GOP):

| escenario | diferencia |
|---|---|
| Forecast April 2026 | −$4,002.88 |
| Actual 2025 | −$274.88 |
| Actual 2024 | −$177.57 |

**No se corrigió a propósito:** falta una fila en el archivo, no un cálculo del
reporte, y dos de esos escenarios son historia enllavada. El aviso del reporte ya
nombra la línea y los dos montos.

</details>

### A3 · Descuadres generales de los actuals viejos

Medidos de nuevo el **2026-08-12**, corriendo el propio reporte. Son distintos de
A2 y sí son dato:

| escenario | descuadre detalle vs resumen |
|---|---|
| `Actual 2024` | ingresos **−$3,085.07** · gastos **+$40,613.30** |
| `Actual 2025` | gastos **−$455.68** |
| `Forecast April 2026` | **ninguno** — está limpio en este chequeo |

El 1.47% que decía la nota vieja es el gasto de 2024 expresado en porcentaje.

#### Diagnóstico línea por línea (2026-08-12) — ya está hecho

No es un descuadre: son **cuatro cosas distintas** mezcladas en un total.

**`Actual 2024` — lo que hay que preguntar a contabilidad:**

| línea | detalle (GL) | resumen | dif |
|---|---|---|---|
| `OPEX_ROOMS` | 394,940.48 | 354,327.21 | **+40,613.27** |
| `REV_INNOCEANA` | 138,874.06 | 141,959.13 | **−3,085.07** |
| `MGMT_FEE_3` | 98,770.42 | 93,842.27 | +4,928.15 |

Las dos primeras **son el descuadre que reporta el aviso** y son de verdad: las
dos hojas del mismo archivo no dicen lo mismo. En Rooms el GL trae $40,613 más de
gasto operativo; en Innoceana el resumen trae $3,085 más de ingreso. El
`MGMT_FEE_3` es el fee del 3%: el resumen lo calculó sobre una base distinta.

**`Actual 2025` — ninguna necesita arreglo:**

* `REV_SUSTAINABILITY` −5,666.01 y `REV_MISC_OTHER` +5,666.01 **se cancelan
  exactamente**: el resumen metió el ingreso misceláneo dentro de Sustainability.
  Línea equivocada, total correcto.
* `OH_CAFETERIA` +455.67 y `OH_LAUNDRY` −357.52 son el **residuo de los
  repartos**, no un error: el `0220` está excluido a propósito del P&L de
  actuales (`ACTUAL_EXCLUDED_DEPTS`) porque su costo ya viaja dentro de la
  planilla de cada departamento por el concepto 6025, y el `0161` se auto-netea
  por la 4900. Lo que sobra es lo que la cuenta de distribución no alcanzó a
  compensar.

**Lo demás de las dos listas es el problema de A2**, no de A3: `RENT`,
`PROPERTY_INSURANCE`, `OTHER_EXPENSES`, `BANK_INTEREST`, `DEPRECIATION`,
`FINANCIAL_LOSSES` y el par `CAPITAL_RESERVE`/`LARGE_CAPEX` aparecen con el motor
en 0 simplemente porque **el resumen subido no trae la apertura below-GOP**.

~~**Lo que queda es de contabilidad, no del sistema:** decidir cuál de las dos
hojas manda en los $40,613 de Rooms y en los $3,085 de Innoceana de 2024.~~
✅ **DECIDIDO el 2026-08-15 — queda como está** (`DECISIONES_DEL_OWNER.md` §2):
«tal cual está, así lo dejamos». No queda nada abierto acá.

### A4 · Apertura del room revenue — ✅ HABILITADA en el master (2026-08-12)

El GL traía todo el room revenue en la `4000`, con un nombre distinto por archivo
(2024 «Cancellations», 2025/2026 «No Show», Budget 2026 Final «Rooms»), así que
no había forma de saber cuánto era cada cosa. **El owner decidió abrirlo en tres
cuentas** y quedaron habilitadas en Master Data:

| cuenta | nombre | depto | línea del P&L |
|---|---|---|---|
| `4000` | Room Revenue | 0110 | `REV_ROOMS` |
| `4001` | Cancellations | 0110 | `REV_ROOMS` |
| `4002` | No Show | 0110 | `REV_ROOMS` |

**En el P&L consolidan las tres en Rooms**: la apertura es por CUENTA, no una
línea nueva del estado de resultados. El signo lo trae el GL — si una cancelación
se contabiliza en negativo, el `SUM` la resta. Se verificó que `4001` y `4002` no
las use ningún otro departamento, y hay prueba que lo vigila.

**Esto es preparación.** Hasta que la contabilidad empiece a contabilizar en las
cuentas nuevas van en cero y no cambia ningún número. El trabajo que queda es de
ellos, no del sistema.

#### El ADR — ✅ RESUELTO (2026-08-12)

El owner pidió que **el ADR salga SOLO de la 4000** — un no-show no ocupa
habitación, así que su ingreso no puede estar en el numerador de una tarifa por
habitación ocupada. Antes se derivaba de `REV_ROOMS`, la línea consolidada, así
que se habría inflado solo apenas las cuentas nuevas tuvieran dato — y sin aviso
posible, porque el ADR no tiene contra qué cuadrar.

**Ahora sale de `scenario_stats`**, que nunca pasó por las cuentas, ponderado por
noches ocupadas (el promedio simple le daría el mismo peso a un mes lleno que a
uno cerrado). **RevPAR** pasa a `ADR × ocupación` para no romper la identidad. Un
escenario sin estadísticas cargadas cae a la derivación vieja — ahí no hay
contaminación posible porque tampoco hay apertura de cuentas.

Lo cuidan `test_adr_sale_de_las_estadisticas_no_de_la_linea` y
`test_el_adr_agregado_pondera_por_noches_ocupadas` en `tests/test_pl_ytd.py`.

### A5 · Dato de prueba en la Cafetería (0220) — ✅ CERRADO, NO HAY (2026-08-12)

Una nota del **2026-08-09** marcó «$51,886 de dato de prueba dentro de 5
versiones 2027 ENLLAVADAS, incluida Final». **Es falso.** Se abrió el `0220` fila
por fila y el número está explicado al centavo.

Las cinco posiciones del departamento, idénticas en los seis escenarios 2027:

| código | puesto | salario CRC/mes |
|---|---|---|
| `0220-01` | STATION COOK 2 (COCINERO B) | 426,000 |
| `0220-02` | STATION COOK 2 (COCINERO B) | 374,000 |
| `0220-03` | STATION COOK 2 (COCINERO B) | 374,000 |
| `0220-04` | STATION COOK 2 (COCINERO B) | 374,000 |
| `0220-05` | STATION COOK 2 (COCINERO B) | 389,006 |

Las cinco tienen **nombre de empleado real** (no «VACANTE»), FTE 12/12 y salarios
de mercado. Suman `1,937,006 CRC/mes × 12 = 23,244,072 CRC/año`, y eso amarra
contra el concepto `c6000_sw` con 10 centavos de redondeo:

| | tipo de cambio | `c6000_sw` esperado | `c6000_sw` real |
|---|---|---|---|
| Draft1…Final (enllavados) | 530 | $43,856.74 | **$43,856.64** |
| Working | 460 | $50,530.59 | **$50,530.56** |

El resto de los conceptos —feriados, CCSS, aguinaldo, riesgos, vacaciones— los
deriva el motor de ese mismo S&W. O sea que **el 100% de los $63,116.11 está
explicado por las cinco personas**: no queda lugar para un fantasma de $51,886,
que además sería más grande que la planilla entera del departamento.

**Y la diferencia entre Working y los enllavados no es dato, es el tipo de
cambio:** los mismos salarios en colones, a 460 en vez de 530. Nadie cargó nada
de más.

---

## B · Trabajo identificado, listo para hacer

### B1 · Seis pares que rutean por FALLBACK — ✅ CERRADO (2026-08-12)

**Las dos hipótesis originales estaban mal las dos.** Ni «que lo corrija el GL»
ni «que lo aprenda la app»: la contabilidad **nunca mandó** esos códigos. El GL
trae **nombres** de departamento y es `gl_detail_importer.dept_code_from_name`
—una tabla de palabras clave nuestra— la que los traduce a códigos.

**Lavandería (`0161`/4700, 4701).** La tabla manda cualquier «lavander» al
`0161`, y el GL tiene UN solo departamento «Lavandería», así que el ingreso del
servicio llega etiquetado `0161` (*Laundry Operations*, overhead) mientras las
reglas estaban escritas para el `0162` (*Laundry Revenue*). **Se movieron las
tres reglas de ingreso (4700, 4701, 4702) al `0161`.** La línea destino no
cambió: sigue siendo `REV_LAUNDRY`. Confirmación de que el `0161` era lo
correcto: esas reglas ya traían `source_department='Departamento de Lavanderia'`,
el mismo string que las 39 reglas de gasto del `0161`, y `mapping_loader` deriva
el código de ese nombre — o sea que el `0162` del JSON contradecía al importador
y al cargador a la vez. Lo cuida `tests/test_lavanderia_rutea_exacto.py`.

**Misceláneos (`0240`/4800, 4860, 4880, 4890).** El `0240` no existe en el
catálogo: lo fabricó una versión vieja del importador (hoy manda
«miscel»/«sostenib» al `280` y «propiedad» al `0250`). **Se re-etiquetaron las 15
filas a `280`** con `scripts/retag_0240_a_280.py`, que verifica cuenta por cuenta
que ninguna cambie de línea del P&L y aborta si alguna lo hiciera. Ninguna
cambió: las 15 pasaron de FALLBACK a exacto en la MISMA línea.

**Por qué se hizo así y no parcheando el mapeo:** `account_mapping` no tiene
`hotel_id` a propósito — es compartido, y eso es lo que hace que un arreglo se
propague solo a las cuatro propiedades. Agregarle reglas al `0240` habría metido
en el estándar USALI compartido un código que no existe y que salió de un error
de traducción nuestro; Amarena, Oxígen y Ojochal lo habrían heredado.

<details>
<summary>Descripción original</summary>



Ingreso de lavandería cargado en el depto `0161` (la regla existe para el `0162`)
y misceláneos en el `0240` (existen para el `280`):

    0161 / 4700 · 0161 / 4701 · 0240 / 4800 · 0240 / 4860 · 0240 / 4880 · 0240 / 4890

**Aterrizan en la línea correcta y no se pierde plata** — por eso no urge. Lo
incómodo es que llegan por el último recurso del resolvedor. Se cierra agregando
seis reglas exactas en Master Data. ~10 minutos.

</details>

### B2 · A&B por outlet, y Bar Privado

Hoy A&B es un solo bloque (`0120`): comida, bebida y misceláneos en una sola
utilidad, así que no se ve si el restaurante gana y el bar pierde. «Por outlet»
es partirlo en centros de utilidad reales —Restaurante, Bar, Bar Privado, Room
Service— cada uno con ingreso, planilla, opex y utilidad, como quedó Rooms.

#### Estado real, medido el 2026-08-12

**La planilla YA está partida** y nadie lo había anotado: los seis presupuestos
2027 tienen 11 posiciones en el `0122` Kitchen y 8 en el `0123` Restaurant. Son
19 personas ya asignadas a su outlet. **Pero no se ve**, porque los dos
consolidan en el `0120` para el P&L: el dato existe y el reporte no.

**Todo lo demás está en un solo bloque**, sin excepción:

| fuente | dónde vive |
|---|---|
| OPEX | 44 filas, todas en `0120` |
| Costo de ventas | 14 filas, todas en `0120` |
| GL / actuales | 19–30 filas por año, todas en `0120` |
| Ingreso del checkbook | líneas `FOOD` y `BEVERAGE` |

⚠️ **Ojo con la última fila:** `FOOD` y `BEVERAGE` **no son outlets, son tipos de
producto**. La comida del restaurante y la del room service están en la misma
línea. Partir por outlet no es reusar esas dos líneas — es una dimensión
distinta y perpendicular.

#### El modelo que quiere el owner (2026-08-12)

No es «partir el bloque en cuatro». Es el modelo estándar de A&B:

* **Presupuestar por outlet**, con **covers** (clientes) y **cheque promedio** —
  no digitando un monto, sino `covers × cheque promedio`, que es como se maneja
  y como se explica una desviación.
* **Por tiempo de comida** (desayuno · almuerzo · cena): el cheque promedio de un
  desayuno y el de una cena no son el mismo número ni se mueven juntos.
* **Por restaurante / outlet**, y que **todo consolide** hacia arriba sin que
  haya que cuadrarlo a mano.
* **Venta de bebidas por TIPO y por OUTLET** — o sea dos dimensiones cruzadas:
  cerveza/licor/vino/no-alcohólica × restaurante/bar/room service.

Eso convierte a A&B en un motor de ingreso propio, del mismo porte que el de
Rooms (tarifa × ocupación por categoría). **No es trabajo de mapeo: es un
módulo.**

#### Qué bloquea, y qué NO

**Bloquea:** el GL trae **un solo** departamento de A&B, así que los escenarios
importados —los actuales, contra los que se compara— no tienen dato por outlet y
no lo van a tener hasta que la contabilidad lo codifique. Es la misma
conversación que la cuenta 4000 de A4: no se puede reportar lo que la fuente no
distingue. Presupuestar por outlet sin actuales por outlet da un plan contra el
que no se puede medir.

**Ya NO bloquea (2026-08-12):** `gl_detail_importer.dept_code_from_name` ahora
reconoce «restaurante»/«restaurant» → `0123` y «cocina»/«kitchen» → `0122`. Antes
un GL que dijera «Restaurante» caía en «sin departamento» y se omitía. Como los
dos departamentos cuelgan del `0120`, la plata sigue cayendo en A&B igual que
hoy: lo que se gana es que **el detalle por outlet no se pierde** cuando llegue.
Bar y Room Service NO se agregaron: todavía no existen como departamento, y
apuntar una palabra clave a un código inexistente sería peor que omitir. Lo cuida
`tests/test_outlets_de_ayb.py`.

#### 🔴 El hallazgo que reordena todo (2026-08-12)

**El archivo fuente TRAE el outlet en una columna propia, y el importador no la
lee.** El owner mostró la hoja de detalle:

```
4110  Food1        Outlet 1   Revenue  Ingreso Food         Departamento de A&B
4110  Food         Outlet 2   Revenue  Ingreso Food         Departamento de A&B
4110  Food         Outlet 3   Revenue  Ingreso Food         Departamento de A&B
4110  Food         Outlet 4   Revenue  Ingreso Food         Departamento de A&B
4120  NA Beverage  Outlet 1-4 …
4125  Beer1/Beer   Outlet 1-4 …
4130  Liquor       Outlet 1-4 …
4131  Wine         Outlet 1-4 …
4132  F&B Misc./.1/.2/.3  Outlet 1-4 …
```

Seis tipos de producto **× cuatro outlets = 24 filas**, con columnas `Outlet` y
`Venue Center`. La contabilidad **ya codifica la dimensión**.

**Y el importador la tira.** `_detect_gl_columns` detecta exactamente TRES
columnas —cuenta, departamento y nombre— y no tiene ningún concepto de outlet.
Como agrupa por `(dept_code, account_code)` y las cuatro filas de un tipo
comparten código de cuenta, **se suman en una sola**. El monto queda bien; la
apertura por outlet se pierde en la carga.

Por eso en el sistema solo se ven tres cuentas de ingreso de A&B (`4110`, `4125`,
`4132`): no es que la contabilidad mande poco, es que nosotros aplastamos.

✅ **Medido con el owner (2026-08-12): los Outlets 2, 3 y 4 están en CERO.** Solo
el Outlet 1 tiene monto.

O sea que **hoy no se pierde nada**: aplastar cuatro filas en una es inofensivo
cuando tres van en cero. No hay arreglo urgente ni hay que re-importar.

Pero deja la conclusión clara: **la estructura está completa y sin usar, en los
dos lados.** Outlets 2-4 vacíos, y las cuentas de Licor, Vino y Cerveza vacías
tanto en ingreso como en costo. **B2 no puede producir nada real hasta que
contabilidad cambie cómo contabiliza** — cualquier cosa que se construya antes
es una estructura vacía.

#### El costo NO tiene outlet — y eso define el diseño

La hoja de costo de A&B tiene 14 cuentas, **abiertas por tipo de producto y sin
columna de outlet**:

```
5101 Food Cost · 5102 Bar to Food · 5103 Freight on Food
5150 Bev Cost · 5151 Liquor Cost · 5152 Wine Cost · 5153 Beer Cost
5154 Other Cost · 5155 Food to Bar
5161-5165 F&B Misc Cost 1-5
```

**Qué se usa de verdad:**

| | actuales (GL) | Budget 2027 Working |
|---|---|---|
| `5101` Food Cost | ✔ todos los años | $238,822.26 |
| `5150` Bev Cost | ✔ todos los años | $67,666.33 |
| `5161` F&B Misc Cost | ✔ 2025 y 2026 | $0 |
| `5102` Bar to Food | solo 2024, **−$114,627** | $2,000 |
| `5151` Liquor · `5152` Wine · `5153` Beer · `5154` Other · `5155` Food to Bar | **nunca** | $0 |

Tres cosas salen de ahí:

1. **El costo de bebida tampoco está separado por tipo.** Todo en `Bev Cost`,
   igual que el ingreso está todo en `Beer1`. Las cuentas de Licor, Vino y
   Cerveza existen en los dos lados y están vacías en los dos.
2. **⚠️ La `5102` está usada con dos significados distintos.** En el catálogo y
   en los actuales es *Bar to Food*, una cuenta de **traslado** (en 2024 va en
   negativo, −$114,627, sacando costo de Alimentos). En el Budget 2027 aparece
   rotulada **«Food Cost 2»** con $2,000. Un traslado y un costo no son lo mismo:
   mientras convivan en la misma cuenta, esa línea **no es comparable entre 2024
   y 2027**.
3. **La consecuencia de diseño, y es la grande:** con el ingreso por outlet pero
   el costo solo por tipo de producto, **no se puede calcular utilidad por outlet
   sin repartir el costo**. Hay que decidir el criterio —¿por ingreso del outlet?
   ¿por covers?— y ese reparto es parte del módulo, no un detalle. Es lo que el
   documento llamaba «repartos de cocina» sin desarrollarlo.

`5102 Bar to Food` y `5155 Food to Bar` son las cuentas de traslado entre
categorías —las mismas que el P&L de referencia muestra como «Traslado de Bar a
Alimentos»— y existen precisamente porque los outlets se pasan producto. Están
en el diseño original; simplemente no se usan.

El P&L de referencia tiene el ingreso de A&B así — seis tipos de producto,
**cuatro renglones cada uno**:

```
Alimentos ×4 · Bebida sin Alcohol ×4 · Cerveza ×4 · Licor ×4 · Vino ×4 · A&B Varios ×4
```

Y el GL de Corcovado trae **solo TRES cuentas** en todo el departamento `0120`:

| cuenta | nombre | total cargado |
|---|---|---|
| `4110` | **Food1** | $3,309,132.29 |
| `4125` | **Beer1** | $1,118,050.95 |
| `4132` | F&B Misc. | $57,350.28 |

Los nombres lo dicen todo: **`Food1`** y **`Beer1`** son el primero de cuatro
espacios (`Food1..Food4`, `Beer1..Beer4`). Es el mismo patrón del Gift Shop, que
tiene `4301`–`4304` = «Ingreso Tienda #1..#4».

**Dos consecuencias:**

1. **Por outlet:** los cuatro espacios por tipo están ahí y contabilidad solo usa
   el #1. La dimensión de outlet **no hay que crearla — hay que nombrarla y
   usarla**. No hacen falta departamentos nuevos.
2. **Por tipo de bebida:** las cuentas `4120` Bebida sin Alcohol, `4130` Licor y
   `4131` Vino **existen en el mapeo y están en cero**. Todo el alcohol —$1.1
   millones— está dentro de «Beer1». El desglose por tipo que pidió el owner
   tampoco necesita cuentas nuevas: necesita que se usen las que ya están.

#### Recomendación corregida: B2 se parte en dos, y la primera va ANTES de clonar

La discusión «antes o después de Amarena» se resuelve al ver que B2 son **dos
trabajos de tamaño muy distinto**:

**(a) La dimensión producto × outlet — barata, y va AHORA.** Es definir el
convenio de nombres de los espacios que ya existen (`Food1`=Restaurante,
`Food2`=Room Service, …) y mapearlos. Al ser el plan de cuentas y el mapeo
**compartidos**, definirlo una vez sirve para las cuatro propiedades — que es
exactamente el argumento del owner: *«crear la complejidad de F&B antes de
gemelar, para que la estructura vaya para todos de una vez y no haya que
hacerlo uno por uno después»*. **Tiene razón**, y con más fuerza de la que
parecía: no es diseñar una estructura nueva, es estandarizar una que ya está.

**(b) El motor de presupuesto — grande, y puede esperar.** Covers × cheque
promedio, por tiempo de comida, por outlet. Eso sí es un módulo del porte del de
Rooms y no depende de (a) para diseñarse.

**Lo único que sigue bloqueado por contabilidad:** que empiecen a usar los
espacios. Mientras todo se postee en `Food1`/`Beer1`, la estructura estará lista
y vacía. Es la misma conversación que la 4000 de A4 — conviene llevarles **las
tres cosas juntas**: la 4000 en tres cuentas, A&B por outlet en los espacios que
ya existen, y el alcohol separado en Licor y Vino en vez de todo en Beer1.

**Private Bar — ✅ MODELADO (2026-08-12).** Ya no es un outlet que «acá no está».
El `0121` es el Private Bar: departamento propio fuera de A&B, grupo
`PRIVATE_BAR`, y **modelado como tienda** —compra producto y lo vende con su
margen— con las mismas cuentas del Gift Shop, por decisión del owner.

Qué quedó armado:

* 35 reglas de cuenta calcadas del `0165`: 4 de ingreso (`4301`–`4304`), 6 de
  costo de producto (`5203`–`5208`), los 17 conceptos de planilla (`6000`–`6030`)
  y 8 de opex (`7380`, `7400`, `7490`, `7665`, `7670`, `7675`, `7680`, `7685`).
* Tres líneas de reporte —`REV_PRIVATE_BAR`, `OPEX_PRIVATE_BAR`,
  `PROFIT_PRIVATE_BAR`— pegadas a las de A&B y sin empate de `display_order`.
* El puente `_MOTOR_TO_CANON`, que es lista fija: sin él el grupo sale del motor
  y nunca llega al P&L Full Detail.

**La trampa que casi se va viva:** compartir los números de cuenta con el Gift
Shop hacía que TODO el ingreso del Private Bar cayera en Retail, porque el rango
`43xx` es de la tienda. `build_actual_inputs` prefiere el departamento sobre el
rango, pero solo si el grupo tiene llave en `GROUP_TO_REVENUE_LINE` — y el grupo
nuevo no la tenía. Se agregó la llave `private_bar`. Lo cuida
`test_la_misma_cuenta_en_dos_deptos_no_se_mezcla`, que verifica que la 4301 en el
`0121` y en el `0165` no se mezclen. Es un fallo silencioso: los totales cuadran
y la plata está en la línea de al lado.

**Los reportes ya lo muestran (2026-08-12).** Se barrió toda la pila: Junta
(departamentos + líneas de ingreso), Revenue Mix, Big Picture, export Detalle a
Excel, importador de snapshots y el drill-down del P&L. Los checkbooks de costo y
OPEX ya lo mostraban solos porque leen el catálogo en vivo. Detalle de qué se
tocó y qué no, en el commit correspondiente.

Dos cosas que el barrido encontró y valen más que el barrido mismo:

* **Big Picture escribía cero en silencio.** `REV_CODE_FOR_GROUP` no tenía el
  grupo nuevo, así que al aplicar a Draft4-BIG el Private Bar habría quedado en
  cero sin avisar. Arreglado.
* **El export de Detalle lo mandaba al fondo.** La constante de orden `CANON` no
  lo conocía y las filas caían detrás del overhead. Arreglado.

### Decisiones del owner sobre el Private Bar — RESUELTAS (2026-08-12) ✅

Las cinco que abrió el split, contestadas. **No volver a proponerlas.**

1. **NO lleva el 10% de servicio de ley.** La base del servicio sigue siendo solo
   `REV_FB` (`cashflow_budget.py:977`, `_cashflow_criterios.py:134`) y así queda.
   No ampliar a `REV_FB + REV_PRIVATE_BAR`. El texto de ayuda del cash flow ya lo
   dice explícito.
2. **Se cobra TODO con tarjeta → 100%.** Hecho: `card_pct_private_bar` = 1.00
   (mig `101`), con su casilla en la pantalla fiscal. Antes caía en el residual
   «Otros» al 60%, y como esa venta venía de A&B —al 70%— el split se la había
   bajado sin avisar. ⚠️ Al agregar el % propio **hubo que restar el Private Bar
   del residual** de `tax.py`: `other = total − (rooms+fb+spa+tours+private_bar)`.
   Si alguien saca otra línea a % propio y no la resta, se cobra dos veces y la
   retención sale inflada **sin que nada lo delate**. Lo cuida
   `tests/test_tax_private_bar.py`.
3. **Se proyecta con % libre** (crecimiento) en Big Picture. NO manejarlo como %
   de Rooms al estilo Retail.
4. **Presupuestarle ingreso queda pendiente, y está bien así por ahora.** Faltan
   **cuatro** eslabones que van en el MISMO commit: `REVENUE_LINES`
   (`models/revenue_entry.py`), el campo en `RevenueResult`, su suma en
   `total_revenue` y `revenue_line_dict` (`recalculate.py`). ⚠️ `RevenueResult`
   es un dataclass **sin `slots`**: un `setattr` suelto NO falla — guarda el monto
   y el total lo ignora. El **costo** sí se puede presupuestar (opex y planilla
   van por departamento), así que un presupuesto muestra el bar con costo y venta
   cero.
5. **La presentación se deja como está:** el Private Bar queda dentro de «Resto» /
   «Other Revenue» en el Resumen Ejecutivo de Junta y en Summary, porque esas
   filas son residuales, no sumas de centros. Es correcto y no se duplica.

**Ojo con una cosa que NO es error:** la sección «Departamentos» de Junta filtra
los departamentos sin movimiento, así que el Private Bar **no aparece ahí hasta
que tenga el primer dato**. En «Ingresos» sí se ve, en cero.

El resto del B2 sigue igual: partir A&B en Restaurante · Bar · Room Service con
ingreso, planilla, opex y utilidad cada uno, más los repartos de cocina.

### B3 · Dos líneas MAPPED sin regla de cuenta

`MGMT_FEE_5_ROYALTIES` (desactivada a propósito en la Fase 1.A) y `LARGE_CAPEX`
(la 8020 lleva las dos líneas y la apertura solo existe a nivel de línea). Están
explicadas, no son deuda — quedan anotadas para que nadie las «arregle» sin leer.

### B4 · La columna YTD de estadísticas — ✅ CERRADO (2026-08-13)

En `/reports/ytd` las columnas «YTD Jun» y «Full Year» llamaban las dos a la
misma función, que sumaba los doce meses sin mirar el corte. Los renglones de
dólares sí lo respetaban, así que el reporte se contradecía consigo mismo —
dólares hasta junio, estadísticas del año entero— sin que nada avisara.

Ahora la función recibe el mes de corte y las tasas se **ponderan**: la
ocupación acumulada es noches ocupadas ÷ noches disponibles del período, no el
promedio de los porcentajes mensuales. Con meses de distinto tamaño —y con
octubre cerrado— las dos cosas no dan lo mismo. Prueba:
`test_ytd_respeta_el_corte.py`.

### B5 · Departamentos que perdían gasto — ✅ CERRADO (2026-08-13)

**Era una clase entera, no tres casos.** Empezó por el Spa y al medir el sistema
completo aparecieron **21 departamentos** con la misma fuga. Todos perdían
cuentas hacia Habitaciones sin dar error y con el GOP cuadrando: solo quedaba
Habitaciones inflado y el otro desinflado, en el mismo monto.

El patrón siempre era el mismo: el departamento no tenía regla para una cuenta
ni padre del cual heredarla, el resolvedor caía al FALLBACK y ganaba el
departamento de código menor — el `0110`.

**Lo más caro era la `4999`**: el crédito de reparto de *cualquier* departamento
le restaba a Habitaciones. Es el mismo error de los $92,108 de la migración 089,
que se había arreglado solo para Rooms, Cafetería y Lavandería.

Qué se hizo, con las decisiones del owner:

| | |
|---|---|
| Spa | `0140` es el padre; `0130` gerencia y `0132` planilla cuelgan de él |
| Utilities `0210` · Claro del Bosque `0205` | estaban amontonados bajo el mismo código; cada uno independiente en overhead |
| Tienda `0151` · Gift Shop `0165` | operativos, arriba del GOP, y **cada uno con su propia línea** de ingreso, gasto y utilidad |
| Laundry Revenue `0162` | es el departamento de INGRESO; `0161` lleva el gasto y reparte, y al cierre queda en cero. **No cuelga de `0161`** — el reparto los separa a propósito |
| Sales remoto `0191` | cuelga de `0190`. Hoy no se usa; si mañana se usa, hereda |
| Los otros 12 | se les dio el núcleo compartido sobre su propia línea |

**El núcleo** son las 29 cuentas que usa cualquier departamento tenga la
actividad que tenga —planilla, cargas, cafetería, cesantía, servicios
contratados, suscripciones, misceláneos, suministros, capacitación, uniformes—
más la `4999`. No es una lista inventada: es la que ya compartían los seis
departamentos de overhead que estaban bien.

**Única excepción, a propósito:** `280` Miscelaneos es solo ingreso y no tiene
costo (owner). Está anotada con su motivo en la prueba.

La prueba `test_departamentos_independientes.py` vigila la propiedad sobre
**todos** los departamentos activos, no una lista de casos: ninguno puede perder
una cuenta del núcleo, y ningún crédito de reparto puede restarle a otro.

**Ojo con el diagnóstico si vuelve:** `/mapping/unmapped/` no sirve — solo mira
`actual_entries` y cruza por cuenta sola, así que no ve los FALLBACK ni las
tablas del checkbook. El tab `/admin/control` sí los ve, escenario por escenario.

### B6 · Lo que falta para que un clon nazca sano

De la auditoría previa al clonado (2026-08-13). Lo que **rompe** ya está
arreglado o vigilado por prueba; esto es lo que queda, ordenado por riesgo.

1. **Una sola verdad del inventario de habitaciones** — ✅ **CERRADO**
   (backend 2026-08-13 · frontend 2026-08-14). Eran tres fuentes: la tabla
   `room_type_configs`, la constante `CWL_ROOM_TYPES` y una lista escrita a mano
   en la pantalla de tarifas. Hoy manda la tabla y ya no hay lista a mano.

   Lo del backend se cerró con el barrido del clonado: `_canonical_room_types()`
   y `_otb_units()` leen `room_type_configs`, así que Amarena ya no guardaría sus
   noches bajo «Sirena Suites» ni calcularía la ocupación del On The Books sobre
   las 30 unidades de Corcovado.

   **Lo del frontend resultó más grande de lo que decía esta nota, y no era solo
   de clones.** La pantalla apareaba seis nombres escritos a mano con los UUID de
   la base **por posición**, contra una lista de UUID ordenada como TEXTO. El
   orden alfabético de un número aleatorio no tiene relación con `sort_order`:
   con seis tipos hay 720 apareos posibles y uno solo correcto. **En Corcovado
   también estaba mal, desde siempre** — el rótulo del renglón no era el del tipo
   que se estaba editando. Los montos nunca se corrompieron (se guardan contra el
   `id`, y el importador de Excel sí respeta `sort_order`); lo que mentía era la
   etiqueta.

   Y de paso: un tipo **sin tarifa cargada** no entraba en esa lista, así que no
   salía en pantalla. En una propiedad nueva —sin ninguna tarifa todavía— la
   pantalla nacía vacía y no había dónde digitar la primera.

   Ahora los tipos salen de `/hotels/{HOTEL_ID}/room-types/`, que ya viene
   ordenado por `sort_order`, y el rótulo es `code · nombre` con el helper
   `rtLabel` — el código es lo canónico entre propiedades, el nombre es etiqueta.
   Lo vigila `test_tipos_de_habitacion_de_la_base.py` sobre **todo** el frontend,
   no sobre el archivo que falló: nadie puede volver a escribir un tipo a mano ni
   aparear por posición.

   **Y el conteo fijo tambien se limpio (2026-08-14, owner: «no quiero tener
   problemas con agregar mas habitaciones»).** El importador del Excel de revenue
   exigia EXACTAMENTE seis tipos y con ocho se negaba entero — Corcovado ya tiene
   ocho (SH07 Villas Deluxe, SH08 Residencia, 33 unidades), asi que ese endpoint
   estaba muerto sin que nadie lo notara, porque ninguna pantalla lo llama.

   Ahora el archivo declara para que `sort_order` trae fila
   (`SORT_ORDERS_DEL_EXCEL`) y `repartir_tipos_para_el_excel()` decide: importa
   los que cubre, **informa** en la respuesta (`sin_tocar`) los que el hotel
   tiene de mas, y solo se niega si al hotel le FALTA un tipo que el archivo si
   trae — ahi las tarifas no tendrian donde ir. Tener mas tipos que el archivo
   dejo de ser un error.

   Lo vigila `test_ningun_modulo_exige_un_numero_exacto_de_tipos`, que busca la
   FORMA (`len(room_types) == N`), no el numero 6: sirve igual cuando la proxima
   propiedad tenga cuarenta habitaciones.

   **Y el codigo quedo inmutable (2026-08-14, owner: «que los codigos no se
   muevan nunca, y los que se vayan agregando queden esclavos en sus posiciones
   de creacion»).** Habia tres formas de moverlo y ninguna daba error:

   * el `PUT` dejaba cambiar el `code` → ahora 409; lo que se edita es el
     NOMBRE. Rellenar un codigo VACIO si se permite (filas viejas sin codigo).
   * el `PUT` dejaba cambiar el `sort_order` → ahora 409. **El importador del
     Excel mapea sus filas por posicion**, asi que reordenar reasignaba tarifas
     a otra categoria en la siguiente importacion.
   * el `DELETE` borraba la fila → ahora **oculta** (`active=False`). Borrar
     liberaba el numero y el correlativo lo volvia a entregar: un `SH08` nuevo
     terminaba apuntando a otra categoria que la de la historia ya cargada. Como
     el auto-codigo cuenta tambien las ocultas, es una marca de agua que solo
     sube y un codigo no se reutiliza jamas.

   ⚠️ **No es un capricho tecnico y no se negocia:** el codigo es lo que liga la
   categoria entre escenarios, reportes y propiedades — el reporte de Junta
   cruza por codigo porque el `id` cambia entre escenarios y el nombre se edita.
   Si alguien pide «renumerar» o «reordenar» categorias, esta regla es la que lo
   prohibe.
2. **Semillas por hotel en archivo, no en constantes** — ✅ **lo que importaba,
   CERRADO** (2026-08-14). El paquete, las experiencias y los canales de venta
   viven en `app/seed_data/<HOTEL_ID>/*.json`. Sin carpeta, `semilla()` devuelve
   `None` y la pantalla nace en blanco. Los archivos de CWL salieron de las
   constantes valor por valor y hay prueba que lo verifica al centavo; los
   números viajan como texto y vuelven a `Decimal` (un `float` ahí se arrastra
   al P&L).

   **Y el nombre de los componentes pasó a ser del owner** («varias cosas no van
   a aplicar en otros hoteles […] podría usar un rate para calcular, pero no
   tiene como paquete»). Misma regla que los tipos de habitación: el CÓDIGO
   (`FOOD`, `ACTIVITIES`, `TRANSPORT`, `SUSTAINABILITY`) es con lo que el motor
   arma el ingreso y lo rutea al P&L, y no se toca; el RÓTULO se edita en
   Paquetes, por propiedad (tabla `component_labels`, mig 103). Vaciarlo devuelve
   el texto por defecto. Se guarda al salir del campo y NO con el botón Guardar,
   a propósito: la etiqueta es de la propiedad, no del escenario — juntas, un
   escenario enllavado bloquearía renombrar algo que no es suyo.

   **Queda de esta familia, y ninguno corrompe dato:** `CWL_OPEX_ACCOUNTS`
   (`opex_api`), `CWL_CHANNELS` (que es otra cosa: la lista de canales del
   reporte de mix, no una semilla), `DEFAULT_DRIVER_RATES` y el `TEMPLATE` de
   salary. El inventario vivo está en `SEMILLA_PENDIENTE`, dentro de
   `tests/test_un_hotel_por_instalacion.py`, y hay una prueba que impide que esa
   lista CREZCA y otra que obliga a sacar de ahí lo que ya se arregló.
3. ~~**Integración continua y un `/health` que diga qué corre**~~ ✅ **LAS DOS
   ESTÁN** — la nota decía «no hay `.github/workflows`» y está vieja. Verificado
   el 2026-08-16, después de un push real:

   * `.github/workflows/pruebas.yml` existe.
   * `GET /health` (sin auth) responde exactamente lo que pedía este punto:

     ```json
     {"status":"healthy","hotel_id":"CWL","hotel_name":"Corcovado Wilderness Lodge",
      "git_sha":"a87b4543153d","alembic_codigo":"117","alembic_base":"117",
      "migraciones_al_dia":true,"base_de_datos":"ok"}
     ```

   Y **sirve**: es lo que confirmó que el commit `a87b454` estaba vivo en
   producción. El endpoint de semillas pide token, así que sin `/health` no
   había forma de verificar el deploy desde afuera. Trae de yapa
   `alembic_codigo` vs `alembic_base` y `migraciones_al_dia`, que es justo el
   modo de falla de [[feedback_verificar_al_nivel_de_linea]] («verde no
   significa aplicado»).
4. **Departamentos como dato editable** — ✅ **BACKEND HECHO (2026-08-16)**,
   falta la pantalla.

   ⚠️ **La nota vieja era medio falsa y decía «grande».** Medido: el motor **ya
   lee la tabla** — `pl_engine.set_dept_catalog()` existe y `main.py` lo llama al
   arrancar, así que el mapa depto→grupo y la consolidación de hijos salen de
   `department_catalog` desde que se sembró. El propio seed lo dejó escrito como
   plan: «cuando luego el motor lea esta tabla en vez de sus constantes, el
   comportamiento no cambia». Lo que faltaba no era el motor: era **la puerta**.
   La tabla solo se cambiaba por SQL o migración, y el único `PUT` que existía
   —`provisioning/{hotel_id}/departments/`— **filtra visibilidad, no crea nada**.

   **Construido:** `app/api/catalogo_departamentos_api.py` —
   `GET/POST /department-catalog/` y `PUT /department-catalog/{code}/`
   (renombrar · mover de grupo · cambiar de padre · activar/desactivar).
   **No hay DELETE**, a propósito.

   **Las cinco barandas, y cada una es un modo de falla que este sistema ya
   tuvo:** el código no se edita ni se reutiliza —ni estando inactivo— · no se
   borra, se desactiva · el grupo tiene que existir **en el motor** (la lista se
   deriva de `pl_engine`, no se escribe a mano) · la cadena de padres no admite
   ciclos · no se desactiva una madre con hijos activos, y el aviso **los nombra**.

   ⚠️ **Renombrar NO toca `name_aliases`**, que es con lo que el importador
   reconoce la etiqueta del mayor (`"lavander"` → `0161`). Si lo arrastrara, la
   próxima importación dejaría de reconocer esas filas sin decirlo.

   14 pruebas en `tests/test_catalogo_de_departamentos_se_edita.py`.

   **El grupo del P&L NO se crea desde acá**, y es decisión del owner
   (2026-08-16): las cuatro propiedades usan **los mismos grupos**, así que
   `GROUP_NAMES` y los `*_GROUP_ORDER` quedan como constantes. Si algún día una
   propiedad necesita una línea propia, eso es trabajo aparte.

   ✅ **Y la pantalla también:** Master Data → **Departamentos**
   (`/master-data/departamentos`), pegada a Provisionamiento porque son el par —
   aquel decide **quién se ve** en cada propiedad, este **qué existe** en el
   grupo. El código sale con candado, el nombre es un campo, el grupo un
   desplegable de los válidos, y el pie avisa que un cambio de grupo, tipo o
   padre entra al P&L **en el próximo despliegue** (el motor toma el catálogo al
   arrancar) mientras que renombrar no espera nada.

   Baja a Excel — lo pidió una prueba, no el gusto:
   `test_todo_baja_a_excel` atrapó la pantalla sin botón. Y está bien que sea
   obligatorio: el catálogo en Excel es justo lo que se revisa **antes** de
   clonarle la propiedad a otro hotel.
5. **Consolidado de grupo, de solo lectura** (mediano-grande). Con bases
   separadas nadie suma los cuatro. Lo mínimo que sirve: cada backend expone
   `GET /api/consolidado/` (P&L por línea, 12 meses, USD) y una quinta app lee
   las cuatro URLs. No toca el modelo de despliegue ni el aislamiento.

### B7 · Plantillas de ida y vuelta — CERRADO lo que se pierde (2026-08-13)

**La norma (owner):** «yo bajo, corrijo y subo lo que guardé». La importación
borra las filas antes de escribir, así que todo lo que la plantilla no lleve se
pierde en el viaje — sin dar error, porque lo que sobrevive alcanza para que los
totales cuadren.

Corregido:

* **no-operativos** — `account_code` no salía en la plantilla ni se restauraba:
  bajar y subir dejaba en blanco la cuenta 8xxx de toda línea below-GOP.
* **no-operativos y OPEX** — el correlativo se recalculaba en cada importación,
  así que reordenar el Excel le cambiaba el código a una fila que nadie tocó.
  Ahora se respeta el que trae la fila; el correlativo es solo para las nuevas.
* **no-operativos** — una fila con código y montos pero SIN descripción se
  descartaba. La pantalla permite dejarla en blanco.

Y algo que salió al arreglarlo: la fila de encabezados se buscaba con
«contiene», y el texto de instrucciones nombra «Código» y «ENE-DIC» dentro de
una frase. Se la tragaba como cabecera y leía los encabezados como si fueran
datos.

**Las columnas se ubican ahora por su ENCABEZADO, no por posición.** Es lo que
permite agregar una sin romper los archivos que la gente ya tenga bajados: los
corrige durante días y los sube. Hay pruebas que suben un archivo *viejo* —al
que se le borró la columna nueva— y verifican que nada entre corrido.
Prueba: `test_plantillas_ida_y_vuelta.py`.

**Cerrado 2026-08-17** (verificado, sin mover un número — 1.541 pruebas):

* ~~`payroll`: la columna `SW Anual USD*` divide por el tipo de cambio de enero
  solamente~~ ✅ Ahora usa el TC **de cada mes**, igual que `calc_sw` (el motor):
  `SUMPRODUCT(FTE, {1/tc_ene,...,1/tc_dic}) × salario`. Antes además dividía por
  12 de más — `salary_amount` ya es mensual, no anual. Guardado con
  `test_payroll_excel_sw_anual.py` (compara contra el motor con TC subiendo
  fuerte durante el año, para que un TC parejo no tape el error).
* ~~`payroll`: el exportador pinta de rojo el FTE igual a cero~~ ✅ Mismo
  criterio que la pantalla (`payroll/fte/page.tsx`): 0 → gris, `0<FTE<0.5` →
  rojo, `0.5–1` → ámbar, `≥1` → negro-negrita.
* ~~`nonop`: lo que se escriba en `CAPITAL_RESERVE` duplica el driver de
  Management Fees~~ ⚠️ **Medido: no hay duplicación en ningún lado** —
  `calculate_budget_pl_from_mapping` REEMPLAZA la llave (`seeds["CAPITAL_RESERVE"]
  = total_rev × pct`), no la suma. Lo real, y no estaba avisado: con el % activo,
  lo que se tipee en esa hoja se descarta en silencio — mismo patrón (documentado
  y ya cerrado) de Management Fees, sin la nota. Se agregó el aviso en la propia
  hoja del Excel. Fijado con `test_capital_reserve_no_duplica.py`.
* ~~`costs`: la columna dice «Driver» y escribe el Modo~~ ✅ Se renombró a
  «Modo», que es lo que de verdad contiene (`MANUAL`/`DRIVER`).

**Sigue abierto** (es agregar columnas nuevas a la plantilla, no una corrección):

* `costs`: el Driver específico, el `% / Tarifa` y las tasas mensuales editables
  siguen sin plantilla — solo se ve el modo. Agregarlos es una plantilla más
  ancha con su propia lógica de importación, no un fix chico.
* `nonop`: `DEFAULT_NONOP_LINES` sigue generando 10 hojas contra las 5 manuales
  de la pantalla — es correcto (Capital Reserve y Large Capex son below-GOP
  pero no viven en el checkbook manual), y ahora la hoja de Capital Reserve
  avisa por qué.

---

## C · Decisiones tomadas que NO hay que rehacer

* **Sembrar 2028–2035**: el owner los copia cuando los necesite.
* **Ocupación de Villas/Residencias fuera de 2027**: se resuelve solo al copiar
  desde el Budget 2027 Working.
* **Las 30 cuentas de OPEX en Villas y Residencias**: se dejan. El costo llega
  por reparto; el owner confirmó que no las va a digitar por los dos lados.
* **Las 5 posiciones del 0180**: NO se borran. Son placeholders `(Actual GL)` que
  crea el importador para meter el costo real de planilla ($151k–$355k según el
  escenario) y solo existen en escenarios importados. En los 2027 el 0180 no
  tiene ninguna. Borrarlas reescribiría historia y volverían en la próxima carga.
* **La planilla no se siembra en blanco**: una línea de gasto vacía es una cuenta
  esperando monto; una fila de planilla vacía sería una persona que no existe.
* **Los departamentos «sueltos» están bien así** (owner, 2026-08-12):
  `0140` Departamento de Spa · `0151` Tienda / Gift Shop · `0184` Administración ·
  `0191` Sales & Marketing (remoto) · `0210` Utilities. **Son departamentos
  independientes, no hijos de nadie — NO colgarlos de un padre.** Utilities es
  Utilities y punto.

  Salieron a la luz revisando el `0121`, que en el camino cambió de destino dos
  veces — vale la pena leer el orden para no deshacerlo:

  1. El `0121` estaba en el grupo FB junto al `0122` Kitchen y el `0123`
     Restaurant, los tres **sin reglas de cuenta propias** (las 74 están en el
     `0120`), pero solo él sin padre. Los otros dos heredaban del `0120`; él caía
     al FALLBACK y su gasto de las 7xxx aterrizaba en `OPEX_ROOMS`.
  2. Se le puso padre `0120` (`28e95fb`).
  3. **El owner decidió otra cosa:** el `0121` no es un outlet de A&B sino el
     **Private Bar**, un centro de utilidad aparte con ingreso Y costo. Se le
     quitó el padre, salió del grupo FB y se le dio grupo propio `PRIVATE_BAR`.
     Ese es el estado final.

  Que ninguno de estos tenga padre es correcto. Lo que sí les falta —al Private
  Bar el primero, porque es el único que va a recibir plata— son **reglas propias
  en el mapeo**, no un padre. `tests/test_private_bar_aparte.py` los lleva
  anotados y falla si aparece un SÉPTIMO: no para colgarlo, sino para que alguien
  lo decida a conciencia en vez de descubrirlo en un P&L.

---

## D · Estado sano (verificado 2026-08-12)

* 0 cuentas sin mapear · 0 DROP · 0 reglas sin código de departamento
* Los seis escenarios 2027 cuadran ingreso, gasto **y below-GOP** contra el motor
  al centavo
* 695 pruebas

---

## E · Variables de entorno de cada propiedad (2026-08-13)

`.env.production` está commiteado y viaja a las cuatro propiedades, así que
**no puede llevar la URL de ninguna**. Cada proyecto de Vercel define lo suyo:

```
NEXT_PUBLIC_API_URL=https://<backend-de-esa-propiedad>/api
NEXT_PUBLIC_HOTEL_ID=<CWL|AMA|OXI|OJO>
```

**Corcovado ya las tiene cargadas.** Al abrir una propiedad nueva hay que
cargarlas ANTES del primer `vercel --prod`.

Si faltan, el build ahora **falla en Vercel con el mensaje** (`next.config.mjs`).
Antes no fallaba: `lib/api.ts` caía a `http://localhost:8000/api` y la app salía
a producción pidiéndole datos a la máquina de quien la abriera. En pantalla,
«Failed to fetch» y nada más. Pasó el 2026-08-13, al desplegar por primera vez
después de sacar la URL del archivo commiteado.

---

## Cierre del 18-ago-2026

Todo desplegado: backend `alembic 128`, frontend en Vercel. 1.816 pruebas.

### Necesita decisión o dato del owner

| # | qué | por qué importa |
|---|---|---|
| 1 | **El XML de Opera por MARKET CODE** | El que llegó como «mark» es byte por byte el mismo de países (MD5 `69aebba8…`). Sin él, **Channel Mix** y las cuentas **9000/9001** quedan vacías aunque el código esté arriba. El import lo detecta y responde 422. |
| 2 | **`CORP` y `GRP` sin canal** | Sus noches no entran a ningún canal. Están así a propósito desde el 14-ago; adivinarlas pondría noches en el canal equivocado y el total cuadraría igual. |
| ~~3~~ | ~~**`rooms_available` vacío**~~ | ✅ **CERRADO 2026-08-19 — estaba mal diagnosticado, no faltaba dato.** Medido contra producción: `rooms_available` está poblado en **11 de los 12 meses** y el checkbook produce la ocupación bien (75%, 76%, 65%…). El único mes en cero es **octubre, y es correcto: el lodge cierra**. 0 disponibles y 0 ocupadas no es un hueco, es el dato. |
| 4 | **El escenario de Budget no tiene mix** (Country ni Channel) | Por eso la columna Budget sale 0% y la variance +100pp. No es un defecto del cálculo. |

### Construido a medias

| # | qué | estado |
|---|---|---|
| ~~5~~ | ~~**Subir el checkbook lleno**~~ | ✅ **CERRADO 2026-08-19.** `POST /checkbook/{escenario}/{depto}/importar/`, con paso de confirmación: primero dice qué haría, después lo hace. Ver abajo. |

### Sin fuente de datos

| # | qué |
|---|---|
| 6 | **Kilos, covers y treatments** (9700-9704, 9110-9131, 9201) no se derivan, y hay prueba que lo impide. Inventarlas cuadraría el total y mentiría el desglose. |

### De arrastre

| # | qué |
|---|---|
| 7 | **Cash Flow Directo** — el owner dice que quedan números malos sin identificar; nunca dijo cuáles ni en qué tab. |
| 8 | **8.5.1 Análisis 2027** — dijo que «no quedó». Recibió Excel de tres hojas y quedó enganchado al escenario de arriba, pero **no se confirmó si el problema original era otro**. |


---

## ✅ Subir el checkbook lleno (2026-08-19)

La vuelta del archivo. Lo que la hacía delicada no era leerlo —`read.py` ya
existía— sino **invertir el mapeo sin equivocarse**.

### El defecto que había que no cometer

La bajada manda la línea n-ésima de una cuenta a la ranura `800 + n`, porque los
códigos de detalle de FinPlan (`''`, `001`…`011`) y los del formato del owner
(`800`…`810`) son listas distintas para la misma idea. Si la subida hubiera
buscado por CÓDIGO, no habría coincidido ninguna línea: **once líneas nuevas por
cuenta, las viejas con su monto viejo, y el total del departamento duplicado** —
con el archivo viéndose perfectamente normal.

Por eso el orden de la consulta (`account_code, detail_code`) está escrito igual
en los dos lados, y hay una prueba que falla si se separan.

### Las tres guardas que valen plata

* **El archivo tiene que ser de ESE departamento y ESE año.** Subir el de
  Habitaciones dentro de A&B reescribiría el departamento equivocado con montos
  que no son suyos, y el total general podría quedar parecido igual.
* **Las líneas en COLONES se convierten de vuelta.** El archivo muestra dólares,
  pero en una línea CRC el dato maestro son los colones y el dólar se *deriva*.
  Escribir el dólar directo sobrevive hasta el próximo recálculo y después se
  revierte solo, sin avisar. Si falta el TC de un mes, se rechaza: inventarlo
  sería inventar el dato maestro.
* **Una línea que vuelve vacía se pone en CERO, no se borra.** Borrarla correría
  las posiciones de las que siguen y la próxima bajada pondría los montos en
  ranuras distintas. La respuesta dice cuántas fueron, y la pantalla lo avisa en
  ámbar antes de confirmar.

Y si el archivo no cuadra consigo mismo —la fila 9 contra la suma de las
líneas— no se carga nada: eso pasa cuando alguien pega encima de una fórmula, y
cargar la mitad buena es peor.

⚠️ **Un bug lo encontró la prueba, no la lectura.** `get_tc_for_month` **lanza**
`ValueError` con la lista vacía en vez de devolver 0, así que la guarda del TC
reventaba con un 500 justo en el caso que venía a contestar con un 422 explicado.

**Lo que NO hace:** las noches disponibles/ocupadas que el archivo trae en las
celdas de captura **no se escriben** en `scenario_stats`. Se informan en la
respuesta. Llenar esa tabla desde un checkbook de GASTO sería un efecto que
nadie pidió — pero es justo el dato que le falta al punto 3 de esta lista, así
que está a un pedido de distancia.


---

## ✅ El `rooms_available` no faltaba (2026-08-19)

El punto decía que el `% Ocupación` del checkbook salía **0,0% en todos los
meses** por falta del dato de origen. Medido antes de arreglar nada:

| mes | ene | feb | mar | abr | may | jun | jul | ago | sep | oct | nov | dic |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| disponibles | 930 | 840 | 930 | 900 | 930 | 900 | 930 | 930 | 900 | **0** | 900 | 930 |
| ocupación | 75% | 76% | 65% | 37% | 25% | 19% | 36% | 27% | 9% | **—** | 46% | 66% |

Y se comprobó por el camino real —`_armar_config` del checkbook, contra el
Budget 2027 Final— no leyendo la tabla de costado.

⚠️ **El único mes en cero es octubre, y está bien: el lodge cierra.** 0
disponibles y 0 ocupadas no es un agujero, es el dato correcto. Es el mismo
octubre que aparece en la ayuda de la planilla: *«octubre con el lodge cerrado
no recibe nada»*.

**La lección, otra vez:** un punto sin medir no es un pendiente, es una nota
vieja. Este pasó un día entero en la lista de «espera dato del owner» sin que
faltara ningún dato.
