# Navegación entre pantallas — diagnóstico y plan

> **Estado al 2026-08-19.** Pedido del owner: *«que dentro de un tab me pueda
> mover a otro tab internamente sin tener que salir… en forma lógica, que se
> interactúen»*, y después: *«revisá las dependencias de las hojas y meté toda
> esa ayuda»*.
>
> **▶ ESTADO: las cuatro fases COMPLETAS. Lo que queda son dos decisiones del owner (ver el final).**

---

## El mecanismo (ya construido y en vivo)

Tres piezas. Agregar un salto es **una línea** en `rutas.ts`; no se toca la pantalla.

| Archivo | Qué hace |
|---|---|
| `frontend/lib/contexto.ts` | El contexto viaja en la URL: `?esc= &mes= &dep= &cta= &de=`. **La URL manda; si no dice nada, manda lo recordado.** |
| `frontend/lib/rutas.ts` | El grafo: `{ruta_origen: [destinos]}`. El rótulo se reusa de `nav.items` para que el menú y el salto no le pongan dos nombres al mismo lugar. |
| `frontend/components/IrA.tsx` | La barra, en los dos sentidos: «Ir a» y «‹ Volver». |

### ⚠️ Por qué el contexto va PRIMERO y no los botones

Medido el 19-ago: de **94 pantallas, 0 leían nada de la URL**. El escenario vive
en `localStorage` y —a propósito— se recuerda **por pantalla**. Un botón «ver el
Cash Flow» encima de eso lleva al cash flow de OTRO escenario, y **no falla**:
muestra un presupuesto real, el equivocado. Es el mismo modo de falla que mandó
todos los reportes a Working 2035.

---

## Hecho

* ****81 pantallas con la barra · 302 saltos declarados** — las cuatro fases, completas.**
  * Piloto (10): `/pl/full`, `/pl/simplified`, los tres de cash flow y los
    cinco checkbooks.
  * **Fase 1 — Planning completa (23)**: la cadena de Revenue entera, planilla
    y repartos, y el gobierno del presupuesto (`/board`, `/notes`,
    `/command`, `/planning/big-picture`, `/admin/control`).
  * **Fase 2 — Reportes y P&L completa (19)**: los seis reportes de P&L, los
    dos de planilla, OPEX/Costos, los de ingreso, Owner, Owners Q, Junta,
    Balance y Cierre de Mes.
  * **Fase 3 — Cash Flow, Break-Even, Operations y Marketing (17)**: las dos
    de cash flow que faltaban, las seis de Break-Even, las cinco de
    Operations, las dos de Marketing y las dos de Escenarios.
  * **Fase 4 — Master Data y Admin (12)**: el grupo que DEFINE. Acá el salto
    se da vuelta: no «¿de dónde salió este número?» sino **«cambiaste esto,
    ¿a qué le pegaste?»** — una pregunta que hasta ahora no tenía respuesta
    en ninguna pantalla.
* **18 pantallas de Planning migradas** a `usePlanningScenarioConUrl` (respetan
  el `?esc=`). Arreglaba un defecto en vivo: tres de ellas ya eran destino de
  saltos y llegaban con el escenario equivocado.
* **Cinco pantallas con llave propia** (`/allocations/salary`, `/board`,
  `/notes`, `/command`, `/admin/control`) atadas con `desdeUrl: true`. Todas de
  un solo selector; verificado antes de tocarlas.
* **Coordenada de cuenta (`?cta=`)** de punta a punta.
* Pruebas: `backend/tests/test_saltos_entre_pantallas.py` (13), 212 rótulos en cada idioma. La que vigila
  que cada pantalla del grafo monte la barra **se deriva del grafo**, no de una
  lista escrita a mano — la lista se olvida de actualizar justo cuando el grafo
  crece, que es cuando importa.

### Decisiones tomadas en la Fase 1

* **`/planning/big-picture` no emite NI recibe `esc`** (`lleva: []` en sus
  cuatro destinos, 0 selectores atados). Compara tres escenarios y además
  ESCRIBE sobre un cuarto: recibir el parámetro no es inútil, es empujar a
  escribir sobre el escenario que uno no eligió.
* **`/board` y `/notes` llevan `dep`** (y `notes` también `mes`). Son las únicas
  del sistema con el `dept_code` como dato de primera clase, así que el salto no
  abre «el checkbook», abre el departamento que hay que completar.
* **Los tres sin escenario** — `/revenue/inventory`, `/revenue/availability`,
  `/revenue/room-nights` — montan `<IrA />` pelada: su dato es del HOTEL, no de
  un escenario.

---

## Las 5 cosas que el mapeo cambió del plan

### 1. Hay **16 pantallas de comparación**, no 2

Muestran dos o más escenarios lado a lado. **El `?esc=` entra en UN solo
selector**; si entra en todos, la comparación se hace contra sí misma y da
variación **cero** — que no se lee como error sino como «no cambió nada».

> **CONVENCIÓN, decidida en la Fase 2: se ata siempre la columna de `budget`.**
> Es la que se planifica y de donde vienen los saltos. Mantener la MISMA ranura
> en todas importa más que cuál sea: así un salto siempre aterriza en el mismo
> lugar conceptual, y quien lee el código no tiene que averiguar la regla de
> cada pantalla. Lo vigila `test_una_pantalla_de_comparacion_ata_UNA_sola_columna_a_la_url`.

| Pantalla | Escenarios | Atada | Estado |
|---|---|---|---|
| `/reports/pl-full` | 5 | `:budget` | ✅ Fase 2 |
| `/break-e/comparar` | 4 | **ninguna** (ver abajo) | ✅ Fase 3 |
| `/month-end/pl` | 4 ranuras | **ninguna** — emite nomás; tocar `varA`/`varB` anula la variación | ✅ Fase 2 |
| `/dashboard` | 4 | rol `budget` (llave `dashboard:main`) | ✅ Fase 4 |
| `/reports/pl-by-dept-compare` | 3 | `:budget` | ✅ Fase 2 |
| `/reports/revenue-mix` | 3 | `:budget` | ✅ Fase 2 |
| `/reports/junta` | 3 | **ninguna** — sus puestos salen de llaves calculadas (`PUESTOS[i].llave`) | ✅ Fase 2 |
| `/reports/owners-q` | 3 posiciones | **ninguna** — su selección son tres posiciones, no un id | ✅ Fase 2 |
| `/planning/big-picture` | 3 | **ninguna** (además ESCRIBE) | ✅ Fase 1 |
| `/reports/pl-ytd` · `/reports/summary` · `/reports/ytd` | 2 | `:budget` | ✅ Fase 2 |
| `/operation-insight/summary` · `/headcounts` | 2 | `:budget` | ✅ Fase 3 |
| `/marketing-insight/channel-mix` · `/country` | 2 | `:budget` | ✅ Fase 3 |

⚠️ **`/command` compara sin que se note**: sus tres referencias viven en
`useState` plano, no en `useEscenarioDe`. Contar selectores **no lo detecta**.
Hoy atarle el principal es seguro; si alguien migra esas tres, se rompe.

⚠️ **`/break-e/comparar`**: su propio código documenta que está exenta a
propósito — su criterio anterior la abría en Working 2035 vacío. Meterle un
`esc` pisa una de las cuatro casillas con algo que nadie eligió y las otras tres
siguen igual: la comparación se ve normal y es otra.

### 2. Dos pantallas donde recibir el escenario es **peligroso**

| Pantalla | Por qué |
|---|---|
| `/reports/tax` | «Aplicar» **escribe** los parámetros fiscales en el escenario del selector. El código **a propósito no recuerda** la elección, para que nadie aplique una tasa sobre un escenario que no eligió. |
| `/scenarios` | Es el **emisor**. Preseleccionar una fila junto a **borrar** y **enllavar** es la peor combinación. |

**Consecuencia de diseño: hay pantallas que EMITEN contexto y no lo RECIBEN.**

### 3. `dep` no es un solo tipo de dato

`Contexto.dep` es el código (`0110`, `600`). Pero `/reports/junta` usa familias
del P&L (`ROOMS`, `FB`, con alias `TRANSPORT`) y `/reports/summary` usa
`FAM_ROOMS`/`FAM_FB`. **Esas dos tienen que omitir `dep`** o se rompen en
silencio.

### 4. Tres pantallas editan el MISMO dato por dos puertas

No es un salto, pero decide qué destinos tienen sentido:

* `closed_months` → `/revenue/master` y `/revenue/room-nights`
* `pax_per_night` → `/revenue/master` y `/revenue/pax`
* `units` → `/revenue/master` y `/revenue/inventory`

### 5. Corrección a un supuesto mío

`/revenue/room-nights` **no** consume ocupación: muestra noches *disponibles*
(`units × días`). Quien consume `/revenue/occupancy` es `/revenue/pax`,
`/revenue/spa`, `/revenue/total-revenue` y `/revenue/checkbook`.

---

## ⚠️ Aparte del alcance: 3 pantallas muertas que ESCRIBEN en producción

Sin entrada en ningún menú, pero editan las mismas tablas que las vivas.
**Decisión del owner**, no de navegación.

| Ruta | Líneas | Qué es |
|---|---|---|
| `/revenue/rates` | 541 | Grilla monolítica de tarifas/net rate/pax. Parece la versión anterior de lo que hoy está partido en Rack Rates + Net Rate + Canales + Componentes |
| `/revenue/packages` | 249 | Editor de componentes de paquete. `/revenue/rates` **documenta** que los rótulos «se editan en Paquetes» — la app describe una pantalla inalcanzable |
| `/revenue/kpis` | 289 | Occupancy/ADR/RevPAR histórico. Se solapa con `Room Stats` y `YTD Summary` |

`/marketing-insight` es un placeholder «work in progress» sin enlaces entrantes.

Opciones: borrarlas · darles entrada en el menú · dejarlas y documentarlo.

---

## Qué falta

### ✅ Fase 1 — Planning (23 pantallas) — HECHA 2026-08-19

Escrita en `rutas.ts`, con `<IrA>` montada y 55 claves `ira.porque` nuevas en
los dos catálogos.

**La cadena de Revenue es una cadena real, no un menú.** Cada pantalla produce
el insumo de la siguiente:

```
inventory ─┬─> availability ──> room-nights
           └─> master ──> occupancy ──> pax ──> package-components
                            │                        │
rack-rates ──> net-rate <── channels                 v
     └──────────> total-revenue ──> revenue/checkbook ──> P&L
```

Pares de planilla (el caso que el owner pidió por nombre):

* `/payroll/fte` ↔ `/payroll/checkbook` — **la vuelta falta y es la valiosa.**
  Verificado: `/payroll/fte` no tiene endpoint propio, reconstruye el detalle
  llamando dept por dept a los MISMOS endpoints que pinta el checkbook.
* `/payroll/params` → checkbook · fte · allocations/salary
* `/allocations/config` → payroll/fte (es la base del reparto) · opex/checkbook
* `/allocations/salary` → payroll/checkbook (el roster que reasigna)

⚠️ `/allocations/salary` usa `useEscenarioDe` con clave propia, **fuera** del
escenario compartido de Planning: un salto desde payroll llega a otro escenario
sin avisar. Necesita `desdeUrl: true`.

**`/board` y `/notes` son los mejores candidatos para `lleva: ["esc","dep"]`**:
cada fila ES un `{sección, ref}` donde `ref` es el mismo `dept_code` que
selecciona el checkbook. `/notes` guarda además el mes → `["esc","mes","dep"]`.

### ✅ Fase 2 — Reportes y P&L (19) — HECHA 2026-08-19

El mejor del sistema: **`/reports/expenses`**, cuyo selector de tipo (OPEX /
Costos / Ingresos / Below-GOP) mapea **uno a uno** con los cuatro checkbooks.

Otros pares fuertes: `pl-by-dept` → `payroll-dept` + `expenses` + `opex/checkbook`
· `payroll-dept` ↔ `payroll-by-position` ↔ `payroll/checkbook`
· `month-end/pl` → `import-actuals` (donde se arregla un mes que no cuadra).

### ✅ Fase 3 — Cash Flow, Break-Even, Operations, Marketing (17) — HECHA 2026-08-19

* Break-Even consume `compute_pl_month` — **el mismo motor que `/pl/full`**. El
  salto está fundado: es el mismo número partido en fijo/variable.
* `/operation-insight/headcounts` ↔ `/payroll/fte` — mismo roster
  (`PayrollPosition`), distinto grano.
* `/marketing-insight/channel-mix` ↔ `/revenue/channels` — uno es el **plan** y
  el otro la **medición**; no comparten tabla, y por eso el salto vale.
* `/break-e/configuracion` es un redirect puro: **no montar barra**.
* Las 6 pantallas de Break-E ya comparten escenario y período entre sí.

### ✅ Fase 4 — Master Data y Admin (12) — HECHA 2026-08-19

Este grupo **no consume, DEFINE**. El salto valioso es otro:
**«cambiaste esto → andá a ver el efecto»**.

* `/master-data/tipo-cambio` → P&L, planilla, cash flow (su botón ya recalcula)
* `/admin/mapping` ↔ `/master-data/setup-cuenta` (el segundo es la vista de
  lectura del primero) ↔ `/admin/control` (su semáforo)
* `/master-data/departamentos` ↔ `/master-data/provisioning` — **son el par**:
  uno define QUÉ existe, el otro QUIÉN se ve
* `/admin/import-actuals` → `/pl/full` · `/admin/mapping` ·
  `/break-e/sin-clasificar` (una cuenta GL nueva entra como 100% fija, en
  silencio)

**Sin dependencia clara** (no forzar): `/admin/users`, `/admin/apariencia`.

💡 **`/master-data/lineas-obligatorias` YA hace esto**: cada fila enlaza a la
pantalla donde se carga el dato faltante (`<a href={f.pantalla}>`). El patrón ya
existe en el sistema — esto lo generaliza, no lo inventa.

---

## Reglas para escribir en `rutas.ts`

1. **La justificación es una dependencia de datos vista en el código**, no una
   intuición. «Sin dependencia clara» es una respuesta válida.
2. **`lleva` solo las coordenadas que el destino entiende.** Un `mes` hacia una
   pantalla anual queda igual en la barra de direcciones, donde alguien lo copia
   esperando que haga algo.
3. **Antes de atar `?esc=`**: contar las llamadas a `useEscenarioDe`. Más de una
   = comparación.
4. **Antes de atar `?esc=`**: ¿la pantalla ESCRIBE sobre el escenario del
   selector? Si sí, no recibe.

---

## Lo que queda: dos decisiones del owner

1. **Las 3 pantallas muertas que escriben en producción** (ver la sección de
   arriba). Borrarlas · darles entrada en el menú · dejarlas documentadas.

2. **Revisar el grafo con ojo de usuario.** Los 302 saltos están fundados en
   una dependencia de datos vista en el código, pero *fundado* no es lo mismo
   que *útil*: un salto correcto que nadie quiere hacer solo ocupa lugar.
   Sacar uno es borrar una línea.

## Dos pantallas quedaron FUERA a propósito

`/admin/users` y `/admin/apariencia` no tienen ninguna dependencia de dato con
el resto del sistema. Inventarles saltos para que «no les falte nada»
degradaría los que sí significan algo: el valor de esta barra es que cada
destino responda una pregunta real.

## Lo que este trabajo dejó además de la navegación

* **Un defecto en vivo corregido**: 18 pantallas de Planning ignoraban el
  `?esc=`, y tres ya eran destino de saltos — llegaban con el escenario
  equivocado sin fallar.
* **Las pantallas son enlazables.** Antes no se podía decir «mirá ESTO», solo
  «entrá y buscá». Hoy `…/pl/full?esc=<id>` abre lo mismo que ve el otro.
* **El mapa de dependencias del sistema**, que no existía escrito en ningún
  lado, y las trampas que solo se ven al recorrerlo entero (las 16 pantallas
  de comparación, las que escriben sobre el escenario del selector, los tres
  datos editables por dos puertas).
