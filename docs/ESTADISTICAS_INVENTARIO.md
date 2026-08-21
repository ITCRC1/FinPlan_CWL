# Inventario de estadísticas — qué hay, qué falta, dónde vive

Fecha del escaneo: 2026-08-14. Cuatro escaneos en paralelo sobre todo el
repositorio (habitaciones/ingreso, repartos y A&B, planilla, y el camino de la
cuenta clase 9 de punta a punta).

> **Para qué es esto.** El owner pidió (2026-08-14) una lista de todo lo que el
> sistema cuenta —o podría contar— para abrir cuentas clase 9 y dejarlas ligadas.
> Esta es esa lista. No es una propuesta: es lo que hay hoy.

---

## Lo primero, porque cambia todo lo demás

**Hoy «cuenta clase 9» significa exactamente tres códigos escritos a mano** en un
diccionario de Python — `gl_detail_importer.py:65`:

```python
STAT_BY_ACCT = {"9010": "rooms_available", "9020": "rooms_occupied", "9060": "guests"}
```

Tres. Y si llega en un archivo **cualquier otra** cuenta 9xxx, **el importador
la descarta en silencio absoluto**. No entra a `unmapped`, no entra a
`sin_cuenta`, no sale en la vista previa, no aparece en ningún log. El
`continue` está fuera del `if`.

**Corrección al primer informe (verificado 2026-08-14 contra producción).**
Escribí que el catálogo contable tenía 9.292 cuentas 9xxx cargadas, siguiendo lo
que dice `CLAUDE.md` §18 y lo que exige `tests/test_importers.py`. En la base de
producción la tabla `accounts` tiene **cero filas** — el catálogo nunca se
importó. Existe el importador y existe la prueba; el dato no está. Por eso la
lista de cuentas estadísticas **no puede colgar de esa tabla**: vive en
`app/seed_data/stats_catalog.json` y se siembra en cada arranque, igual que el
mapeo del P&L.

Contraste que vale anotar: una fila **sin** código de cuenta hoy tumba la carga
con un 422 (la defensa que se puso por los $40,613.30 del Actual 2024). Una fila
**con** código de cuenta clase 9 desconocido pasa de largo sin decir nada.

Y no hay dónde ponerlas: `scenario_stats` es una tabla de **cinco columnas
fijas** (`rooms_available`, `rooms_occupied`, `guests`, `occupancy_pct`, `adr`),
una fila por escenario × mes. **No existe ninguna tabla clave/valor.** Los
modelos `StatisticalEntry` y `StatisticalSummary` están documentados en
`CLAUDE.md` §18.5 con todo detalle — y no existen en el código. Cero
ocurrencias, ninguna migración.

Precedente de cuánto cuesta una estadística nueva con el diseño actual: los
socios del Club Madresal son **cuatro números por mes** y necesitaron migración
propia (098), modelo propio, API propia, router, dataset de copia y prueba. Y ni
siquiera entran por cuenta del GL: se cargan a mano por su propio endpoint.

---

## A. Existen y ya tienen cuenta clase 9 — 3

| Cuenta | Qué es | Dónde aterriza |
|---|---|---|
| 9010 | Habitaciones disponibles | `scenario_stats.rooms_available` |
| 9020 | Habitaciones ocupadas | `scenario_stats.rooms_occupied` |
| 9060 | Huéspedes | `scenario_stats.guests` |

De estas tres se **derivan** ocupación % y ADR al consolidar. RevPAR ni se
guarda: se calcula al leer.

---

## B. Existen como dato guardado, pero SIN cuenta — 14

| # | Estadística | Dónde vive hoy | Granularidad |
|---|---|---|---|
| B1 | Noches disponibles | `actual_room_stats.nights_available` | escenario × tipo hab × mes |
| B2 | Noches ocupadas | `actual_room_stats.nights_occupied` | escenario × tipo hab × mes |
| B3 | Pax | `actual_room_stats.pax` | escenario × tipo hab × mes |
| B4 | Ocupación % (presupuesto) | `occupancy_budgets.occupancy_pct` | escenario × tipo hab × mes |
| B5 | Rooms / guests On The Books | `on_the_books_entries` | escenario × semana × mes |
| B6 | Rooms vendidas por día | `otb_daily_occ.rooms_sold` | escenario × semana × mes × día |
| B7 | Mix por canal (rooms y pax) | `channel_mix_entries.value` | escenario × mes × canal × métrica |
| B8 | Mix por país | `country_mix_entries.value` | escenario × mes × país × métrica |
| B9 | Socios Club Madresal (4 conteos) | `club_membership_stats` | escenario × mes |
| B10 | Kilos de linen | `laundry_allocation_configs.kilos_monthly` | escenario × depto × mes |
| B11 | Kilos de uniformes | `laundry_params.kilos_uniformes` | escenario (promedio) |
| B12 | Kilos de ropa de huéspedes | `laundry_params.kilos_huespedes` | escenario (promedio) |
| B13 | FTE | `payroll_positions.fte_jan…fte_dec` | escenario × **posición** × mes |
| B14 | KPIs históricos (avail/occ/guests/ADR/RevPAR) | `historical_kpis` | hotel × año × mes |

**Nueve tablas distintas, sin modelo común, sin unidad declarada, sin llave a
`accounts`.** Cada una con su propia granularidad y su propia pantalla.

Ojo con B10–B12: **están casi todos en cero o en nulo.** Los kilos mensuales
nacen vacíos; los de uniformes y huéspedes arrancan en cero, y esos dos definen
el costo de la lavandería de huéspedes.

---

## C. Se calculan, se muestran, y no quedan guardadas — 10

| # | Estadística | Dónde se calcula |
|---|---|---|
| C1 | Tratamientos de spa | frontend `revenue/spa/page.tsx:100` (`pax × captureFrac`) |
| C2 | Personas que pasan por el spa | no es concepto propio: hoy es igual a tratamientos |
| C3 | Pax de tours | implícito en `revenue_calculator.py:181` (`noches × avg_pax`) |
| C4 | Pax de transporte / bote | implícito en `revenue_calculator.py:186`, misma fórmula |
| C5 | Headcount por departamento | `payroll_position_report_api.py` |
| C6 | FTE promedio | `sum(fte)/12` |
| C7 | Pax promedio efectivo | `revenue_calculator.py:172` |
| C8 | RevPAR | tres definiciones distintas conviviendo (ver abajo) |
| C9 | Pax diario del XML de Opera | **se parsea y se tira** al persistir |
| C10 | GAP / pickup / pace OTB | `components/OnTheBooksPanel.tsx` |

---

## D. No existen en ninguna parte — 11

| # | Estadística | Cuenta documentada en CLAUDE.md |
|---|---|---|
| D1 | Covers de A&B — desayuno | 9110–9132 |
| D2 | Covers de A&B — almuerzo | 9110–9132 |
| D3 | Covers de A&B — cena | 9110–9132 |
| D4 | Customers de A&B (personas distintas) | 9110–9132 |
| D5 | Noches por segmento de mercado (13 segmentos) | 9000-0110-xxx |
| D6 | Horas regulares | 9980–9985 |
| D7 | Horas extras | 9980–9985 |
| D8 | Horas de incapacidad | 9980–9985 |
| D9 | Horas de vacaciones tomadas | 9980–9985 |
| D10 | Horas de feriados / días libres | 9980–9985 |
| D11 | Pasajeros / viajes de bote como concepto propio | 9500–9503 |

Las de A&B son las más ausentes de todas: el grep de
`covers|customers|cubiertos|comensales` sobre el repo entero devuelve solo falsos
positivos. El sistema factura la comida como noches × pax × tarifa. **Nunca
cuenta un plato.**

Las horas tampoco: la planilla no tiene ni una columna de horas. El sobretiempo
es un **porcentaje del salario** (`overtime_pct`), no horas contadas.

---

## Cosas que aparecieron de paso y hay que arreglar

1. **Las tarifas de comida no coinciden.** Backend `package_config.py:17` dice
   desayuno 18 / almuerzo 36 / cena 54 = **108**. Frontend
   `revenue/package-components/page.tsx:29-33` dice 21 / 42 / 63 = **126**. Dos
   verdades sobre la misma comida, y la del frontend está escrita a mano en el
   archivo, no en la base.

2. **El driver KILOS del costo está roto.** `costs_api.py:539-547` nunca le pasa
   `kilos=` al calculador: cualquier línea de costo que use ese criterio calcula
   **cero, en silencio**.

3. **Tres RevPAR distintos.** `pl_api.py:101` usa `ADR × occ / disponibles`;
   `revenue_calculator.py:96` usa `ingreso de habitaciones / disponibles`;
   `operation-insight/summary/page.tsx:30` usa **ingreso total** / disponibles —
   eso último es TRevPAR, etiquetado «RevPAR».

4. **Dos definiciones de habitaciones disponibles.** El calculador usa días de
   calendario fijos y **no descuenta el mes cerrado**; la pantalla de room-nights
   sí lo descuenta.

5. **Dos universos de canales que no se hablan.** `channel_mix_entries` usa
   Travel Agency / Direct + Website / OTA / Other-In-House;
   `sales_channel_configs` usa TA / OTA / DIRECT.

6. **`actual_room_stats` se ata por NOMBRE de tipo de habitación**, sin llave.
   Justo lo que los códigos fijos (BL01, BI02…) existen para evitar. Renombrar un
   tipo desconecta el histórico.

7. **Dos definiciones de headcount.** El anual cuenta filas; el mensual cuenta
   posiciones con FTE mayor que cero.

8. **Las 9 líneas `KPI_*` de `report_line_config` son decorativas.** El motor las
   salta explícitamente (`pl_engine.py:1064`). Tres de ellas
   (`KPI_ROOMS_PER_DAY`, `KPI_PACKAGE_INCOME`, `KPI_ROOM_PACKAGE_INCOME`) no
   tienen quién las emita.

9. **`ops_kpi_entries` es texto libre.** `kpi`, `target`, `actual` son `String`.
   Lo que se digite ahí no se suma, no se compara y no se grafica.

10. **La vacante numerada no se detecta.** El frontend compara contra la cadena
    exacta `"VACANTE"`, así que «VACANTE 2» cuenta como persona.

---

## Lo que decidió el owner (2026-08-14)

> «Hay que subirlos **por departamento y por posición**. Seguramente haya que
> construir uno especial solo para subir estadísticos, que tenga las mismas
> cualidades del archivo que sube los actuales.»

Eso cierra la discusión de diseño: **la estadística necesita dimensiones**
—departamento, posición, tipo de habitación, punto de venta— y `scenario_stats`,
con sus cinco columnas por escenario × mes, no tiene dónde ponerlas.

Camino que sigue de ahí:

* una tabla de estadísticas **con dimensiones**, no una columna por concepto;
* el catálogo de cuentas 9xxx pasa a ser la llave de verdad, no un adorno;
* un archivo propio de carga con las mismas cualidades que el de actuales:
  se baja con lo que ya hay, se corrige, se sube, **las columnas se ubican por
  encabezado**, y **la fila que no se reconoce da error en vez de perderse**;
* las tres cuentas de hoy (9010/9020/9060) siguen aterrizando donde aterrizan,
  para no mover nada de lo que ya reporta.

---

## Dimensiones que pidió el owner (2026-08-14, segundo mensaje)

> «Por la procedencia. Habitaciones por canal, ventas por canal. Ventas,
> habitaciones y pax por país, por market codes.»

Esto agranda la lista de **dimensiones**, no la de conceptos:

| Dimensión | Estado hoy |
|---|---|
| Departamento | existe en todo el sistema, **no** en la estadística |
| Posición | existe en planilla (`payroll_positions`), **no** en la estadística |
| Tipo de habitación | existe en `actual_room_stats`, **atado por nombre, sin llave** |
| Canal | existe en `channel_mix_entries` — solo `rooms` y `pax` |
| País / procedencia | existe en `country_mix_entries` — solo `rooms` y `pax` |
| **Market code / segmento** | **no existe.** Documentado en CLAUDE.md §18.2 (13 segmentos), sin implementar |
| Punto de venta (outlet) | la columna existe en `actual_entries` (mig. 102), lleva plata, no cantidades |

Lo que falta concretamente sobre lo que ya hay:

* **Ventas por canal** y **ventas por país** no existen. Las dos tablas de mix
  solo guardan `rooms` y `pax`; no hay métrica de dinero.
* **Pax por canal** sí existe; **pax por país** también.
* **Market code** no existe en ninguna de las dos tablas ni en ningún lado.
* Los **dos universos de canales** siguen sin hablarse: `channel_mix_entries`
  (Travel Agency / Direct + Website / OTA / Other-In-House) contra
  `sales_channel_configs` (TA / OTA / DIRECT). Antes de abrir ventas por canal
  hay que decidir cuál manda, o van a salir dos cifras distintas de lo mismo.

### ⚠️ La trampa de «ventas por canal»

Habitaciones, pax y kilos son cantidades: viven en clase 9 sin discutirle nada al
P&L. **Las ventas no.** Un ingreso de habitaciones abierto por canal es la misma
plata que ya reporta `REV_ROOMS`, partida de otra forma.

Si se carga por separado, el día que la suma de los canales no dé igual al P&L
hay **dos verdades sobre el mismo dinero** y ninguna avisa — que es exactamente
como aparecieron los $40,613 y los $71,556 de este mismo mes.

Regla que se sigue: la venta por canal / país / segmento se guarda como
**apertura**, y hay una prueba que exige que sume al ingreso del P&L del mes. Si
no cuadra, la carga falla; no se guarda torcida.
