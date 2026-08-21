# GUILLERMO — ingesta autónoma de reportes

**Proyecto:** FinPlan CWL · **Versión:** 0.4 · **Autor del original:** Bismark Rodríguez García

> **v0.3 → v0.4.** El original se escribió sin mirar lo que FinPlan ya tiene. Se midió
> el código antes de tocar nada y aparecieron tres choques con la arquitectura real y
> cinco piezas que el spec proponía construir y que **ya existen**. Esta versión corrige
> eso y reordena las fases para que la primera sea entregable.
>
> Las cuatro decisiones de fondo las tomó el owner el **2026-08-19** y están marcadas
> ✅ abajo. El documento original queda como referencia; **manda éste**.

---

## 0. Lo que ya existe — leer antes de crear una tabla

Medido contra el repo el 2026-08-19. **El spec proponía construir cinco cosas que ya
están**:

| El original pedía | Ya existe en FinPlan |
|---|---|
| `mapping_rules` — origen → cuenta | **`mapeo_origen`** (`models/mapeo_origen.py:39`): `(hotel, origen, cuenta, depto)` → cuenta interna, con precedencia depto-específica, flag `activo`, CRUD y pantalla en `/admin/origenes` |
| Reporte de filas sin mapear | `GET /mapping/unmapped/` (`api/mapping_api.py:186`) |
| Validación de totales al subir | `importers/verificacion.py` — **11 controles, 4 bloqueantes** |
| Preview antes de escribir | `dry_run` (`scenarios_api.py:1646`) y `origenes/aterrizaje.previsualizar()` |
| Regla «sin mapeo no entra» | `origenes/traductor.py:1-11` — ya es la norma |

Además hay **26 endpoints de subida** y **18 parsers** (XLSX y XML). La capa de ingesta
no hay que inventarla: hay que **registrarla**.

### Los cuatro huecos reales

1. **No existe identidad de archivo.** Ni checksum, ni nombre, ni tamaño guardado.
   **Subir el mismo archivo dos veces no se detecta.** ← el más grave, y el más barato.
2. **No hay historial de importaciones.** La respuesta HTTP es efímera; no queda traza
   de quién subió qué ni cuándo.
3. **Las excepciones se pierden.** Las filas rechazadas se devuelven y se van.
4. ~~**No hay parser CSV ni PDF.** Todo es XLSX o XML.~~ ✅ **Deja de ser un hueco
   (owner, 2026-08-20): «todos serán XML de Opera», «los uploads de Opera serán
   Excel».** No hay CSV ni PDF en el camino, así que los 18 parsers que ya existen
   —todos XLSX y XML— cubren el formato. Era una suposición sobre el formato, no un
   requisito.

---

## 1. Propósito y principio rector

Que los reportes lleguen completos, correctos y a tiempo, sin que nadie tenga que
acordarse. Sin cambios respecto del original.

> **Guillermo puede decidir, pero no puede esconder.**
> Cada decisión queda escrita, atribuida, explicable y reversible.

---

## 2. Runtime (D-0) — ✅ RESUELTO

El original razonaba: *«FinPlan corre en Vercel (serverless), Guillermo no puede vivir
dentro de la app»*. Cierto para el frontend — **pero el backend de FinPlan CWL ya es un
proceso persistente en Railway**, y ahí ya viven las credenciales y la conexión a la base.

**Decisión:** Guillermo es un paquete **dentro del backend existente**, disparado por un
cron de Railway. Sin repo nuevo, sin base nueva, sin credenciales nuevas.

Se conserva del original —y es buena idea— la **pureza de `core/`**:

```
backend/app/guillermo/
  core/        # validadores, reglas, normalización — sin I/O de red ni disco
  sources/     # FolderSource | MailSource | SftpSource | OhipSource
  runners/
    worker.py  # entry point del cron de Railway
    local.py   # entry point Windows, solo si hace falta el puente
```

⚠️ **No hay entorno de staging.** El original pedía «preview / staging — nunca
producción». FinPlan tiene **una sola base**. La salvaguarda equivalente, y es
suficiente, son dos: la Fase 0 es **puramente aditiva** (solo registra) y el modo sombra
**no escribe nada**.

### 2.1 ✅ El cron — construido 2026-08-20 (pendiente 17)

`app/guillermo/cron.py` + `backend/railway.cron.json`. Es lo que faltaba para que
Guillermo recorra sin que nadie apriete el botón.

**La hora vive en la base, no en el crontab.** `daily_run_at` (06:00 por default) es un
parámetro que el owner edita en la pantalla. Si además estuviera escrito en el crontab
habría **dos fuentes de verdad para el mismo dato** y cambiarlo en la app no movería
nada. Así que el crontab dispara **cada 30 minutos** y el módulo decide si toca:

| regla | por qué |
|---|---|
| antes de `daily_run_at`, no corre | — |
| ya corrió hoy **por cron**, no corre | sin esto, disparar cada 30 min daría **48 rondas por día**. Una prueba recorre las 48 y exige que corra 1 |
| una ronda **manual** no cuenta | apretar el botón a las 05:00 no puede saltear el recorrido **ni el latido** del día |
| tarde sí, nunca no | si el contenedor estuvo caído a las 06:00 y vuelve a las 09:00, corre a las 09:00 |

⚠️ **Los crons de Railway corren en UTC.** `06:00` en `report_timezone`
(America/Costa_Rica) **no** es `06:00` UTC — sería medianoche, seis horas antes y todos
los días. La conversión se hace en el módulo, y hay una prueba que la fija. Por eso entra
`tzdata` en `requirements.txt`: sin la base de zonas, `ZoneInfo` no resuelve.

**Qué ronda corre.** `ronda_de_control`, que **no escribe en el modelo financiero**: sólo
recorre qué falta subir y si los auxiliares amarran con el GL, y anota. La otra
(`runner.correr_ronda`) necesita una fuente que le traiga archivos y hoy **no tiene ni un
llamador** — espera D-2 y D-4. Conectarla es cambiar una función, no reescribir el cron.

⚠️ **Y una decisión que el owner puede revertir en una línea.** `corre_solo` sólo es
`True` en el nivel «alto», que además prende `importa` y `recalcula`. Exigirlo para esta
ronda obligaría a **darle permiso de escritura para que pueda mirar**, y sin ronda no hay
latido: el dead-man switch se pondría rojo en un sistema sano. Así que el recorrido va en
todos los niveles —`encola` ya está prendido desde el más bajo— y `corre_solo` sigue
gobernando lo que sí escribe. Los textos de los niveles se corrigieron para que la
pantalla diga eso y no otra cosa. Para volver atrás:
`if not puede(modo, "corre_solo"): return`.

**El servicio de Railway** — ✅ creado el 2026-08-20: `finplan-cwl-guillermo`, en el
proyecto `dependable-communication`, mismo repo, root `/backend`, con `DATABASE_URL`
apuntando al mismo Postgres y `HOTEL_ID=CWL` explícito.

⚠️ **La ruta del config as code se resuelve desde la RAÍZ del repo**, no desde el root
directory: va `backend/railway.cron.json`. Con `railway.cron.json` a secas el build falla
**en segundos y sin una sola línea de log** — y esa ausencia de log ES la pista: si el
builder hubiera arrancado, habría salida.

Verificado en producción el mismo día: primer tic 14:30 UTC → «son las **08:30** y la
ronda es a las 06:00», batch `shadowed`, 6 hallazgos abiertos y **0 nuevos** (no duplicó
los del botón), contenedor adentro y afuera en 2 s. El tic siguiente, 15:01 UTC → «ya
corrió hoy a las 08:30». **No corre
`alembic upgrade head` ni el seed**: dos servicios migrando a la vez es una carrera que
nadie quiere depurar. `restartPolicyType: NEVER`, porque reintentar una ronda que acaba
de fallar no la arregla — la próxima es en 30 minutos.

---

## 3. Alcance

**Dentro:** adquisición, validación, importación vía la API que ya existe, cola de
excepciones, motor de reglas, notificaciones, presencia en la UI.

**Fuera:** chat analítico · escritura hacia Opera · el CHECKBOOK de gastos (D-3, default
confirmado: solo Opera — el camino del GL ya tiene su propia puerta en `origenes/`).

---

## 4. Autonomía — dos niveles

Sin cambios: **Sombra** (procesa, no escribe) y **Asistido** (importa; auto-aplica
**solo** reglas aprobadas por un humano).

> Una propuesta del modelo **nunca** se aplica sola.

⚠️ **Hueco del original, sin resolver:** el criterio para pasar de 0 a 1 es «≥2 semanas
con acierto ≥95%», pero en sombra no se escribe nada — **¿contra qué se compara?** Para
que esa métrica exista, alguien tiene que importar en paralelo a mano y comparar. **Hasta
que se defina el comparador, el paso de 0 a 1 es una decisión humana, no una métrica.**

---

## 5. Modelo de datos — corregido

### 5.1 ✅ La identidad de la propiedad es `hotel_id`, texto

El original pedía `property_id uuid FK → properties`. **No existe tabla `properties`**:
es `hotels`, con llave de texto de 10 (`CWL`, `AMA`, `OXI`, `OJO`), y hay ~60 tablas con
esa clave foránea.

Y sobre todo: **FinPlan no es multi-propiedad en una base — es una instalación por
hotel** (`app/hotel_actual.py:1-6`: *«un hotel = un proyecto aparte»*), con `HOTEL_ID` en
el entorno.

«Propiedad nueva sin migración» **ya se cumple**, por la vía contraria: se levanta un
proyecto nuevo. Adoptar el modelo del original significaría convertir la app a
multi-tenant — rehacer la llave de `hotels` y las foráneas de decenas de tablas. **Eso es
un proyecto aparte y Guillermo no lo arrastra.**

**Decisión: `hotel_id String(10)`, igual que todo el resto.**

### 5.2 `import_batches`

`id` · `hotel_id` · `scenario_id` (nullable) · `periodo_desde` / `periodo_hasta` ·
`frecuencia` · `estado` (§5.5) · `origen` · `modo` (`shadow`/`assisted`) ·
`iniciado_en` / `terminado_en` · `lineas_total` / `lineas_auto` / `lineas_pendientes` ·
`disparado_por` · timestamps.

### 5.3 `import_files` — donde vive el hueco #1

`batch_id` · `nombre` · **`checksum` (sha256)** · `tamano` · `report_id` · resultado por
nivel · mensaje · `subido_por` · timestamps.

**Constraint anti-doble-import:** `UNIQUE (hotel_id, scenario_id, checksum)`.

⚠️ **La política de duplicado sigue el patrón que FinPlan ya usa**, no uno nuevo: igual
que `confirmar_diferencias` (`scenarios_api.py:1658`), un reimport devuelve **409 con el
motivo** y solo procede con un flag explícito. Nunca importa dos veces en silencio, y
nunca bloquea sin salida.

### 5.4 ✅ Mapeo: se EXTIENDE `mapeo_origen`, no se crea una tabla nueva

`mapeo_origen` ya resuelve «cuenta externa → cuenta interna». Guillermo necesita además
«texto libre → cuenta interna». **Se le agrega una columna de texto normalizado**,
conservando su lógica de precedencia y su pantalla.

**Normalización obligatoria en ambos lados** (del original, §7.4 — es su mejor aporte):

1. `UPPER` · 2. sin tildes ni diacríticos · 3. sin puntuación · 4. espacios colapsados ·
5. `TRIM`

```
MANT. PISCINA QUÍMICOS  →  MANT PISCINA QUIMICOS
Mant  piscina quimicos  →  MANT PISCINA QUIMICOS   ← mismo match
```

Sobre el texto normalizado: **match exacto**. Sin regex, sin fuzzy.

⚠️ Hoy `mapeo_origen` **no normaliza nada** (`origenes/traductor.py:21` solo hace
`.strip()`). La normalización ya existe bien hecha en `importers/verificacion.py:130-148`
— **se reusa esa, no se escribe otra.**

**Por qué una tabla y no dos:** dos tablas de mapeo son dos pantallas donde el owner
tiene que acordarse de cuál mira. Es exactamente el problema de las dos tablas de rack
que se arregló el mismo día.

**Congelamiento:** editar una regla **NO** recalcula batches ya importados.

### 5.5 Máquina de estados

`queued → running → {failed | validated | pending_review}` ·
`validated → {imported | shadowed}` · `pending_review → {validated | failed}` ·
`imported → reverted`.

Terminales: `failed`, `imported`, `reverted`, `shadowed`. `reverted` deja rastro.

---

## 6. ✅ Período cerrado — reformulado

El original pedía: *«si el mes está cerrado, el import falla y avisa — sin override, sin
flag»*. **Eso contradice una decisión ya tomada y documentada, y además se contradice a
sí mismo.**

**Lo medido:**

- **Hoy no existe ningún chequeo que rechace escribir sobre un mes cerrado.** No es un
  olvido: `engine/meses_cerrados.py:49-54` dice que el candado por grilla se evaluó y se
  descartó — *«cubría lo chico y dejaba abierto el recálculo: seguridad falsa»*. Lo que
  hay es `divergencia()`, que **avisa** comparando contra la última foto.
- **El corte de meses cerrados avanza SOLO como consecuencia del propio import**
  (`scenarios_api.py:1583-1586`): subir actuales de agosto cierra agosto. Con la regla
  del original, **el segundo import del mismo mes fallaría siempre** — y eso rompe dos
  casos que el propio original resuelve: el reporte que llega tarde (§13.1) y el
  duplicado con política `replace` (§13.2).

**Decisión — dos niveles, uno duro y uno visible:**

1. **Duro:** Guillermo respeta el **candado del escenario** (`status='locked'` → 409).
   Ya existe, ya es duro, y cubre el caso real de «esto no se toca más».
2. **Visible:** para el mes cerrado usa `divergencia()`. Si un mes cerrado se movió,
   **genera una excepción PERSISTIDA en la cola** en vez de seguir callado. Hoy eso es
   solo un aviso en pantalla que se pierde al recargar — **así queda más fuerte que
   ahora, no más débil.**

⚠️ **Y una regla propia:** en modo sombra Guillermo **no avanza `actuals_through`**. Un
proceso que se auto-cierra el mes que acaba de leer no se puede auditar.

⚠️ **Falso amigo:** `hotels.closed_months` **no es cierre contable** — son los meses en
que el hotel no opera (CWL cierra octubre). No tiene relación con permisos de escritura.

---

## 7. Autorización — el rol nuevo rompe los endpoints de admin

`ROLES = ("admin", "collaborator")` (`models/user.py:7`), columna `String(20)` **sin
constraint**: agregar `guillermo_approver` (18 caracteres, entra) **no requiere
migración**.

⚠️ **Pero `get_current_admin` compara `role != "admin"` literal** (`app/auth.py:100`),
así que un `guillermo_approver` quedaría **rechazado por los 12 endpoints de
administración**. Hay que reescribir esa comparación, no solo agregar el rol.

⚠️ **Hueco preexistente que debilita el control:** `PATCH /scenarios/{id}/status/`
(`scenarios_api.py:492-505`) **no exige admin**. Cualquier colaborador puede enllavar y
desenllavar un escenario hoy. Si el candado va a ser la salvaguarda dura de §6, esto hay
que cerrarlo primero.

---

## 8. Dónde entra la IA (y dónde no)

Sin cambios respecto del original, que acá está bien:

- Esquema, tipos, fechas, totales, cuadre → **código, nunca IA**.
- Match contra reglas → **código**, lookup exacto normalizado.
- Concepto no reconocido → propuesta de IA, que **va a la cola y ahí se detiene**.
- **Los números nunca los produce el modelo.** Toda cifra viene de una query.
- **PII:** al modelo solo va el concepto contable y el catálogo de cuentas candidatas.
  Lista de campos prohibidos verificada en tests.
- Los archivos de Opera son **entrada no confiable**: contenido delimitado y etiquetado
  como datos; nada adentro es una instrucción.

---

## 9. Detector de falso positivo — corregido

El original: *«si el total se mueve más de `variance_alert_pct` contra el período
anterior comparable»*. **No define «comparable», y en Corcovado eso importa**: setiembre
corre al 9,1% de ocupación y febrero al 81,4%. Comparar contra el mes anterior dispararía
la alerta todos los meses y la volvería ruido.

**Decisión: el comparable es el MISMO MES del año anterior**, no el mes anterior.

> Lo peor no es que falle. Es que importe mal y no diga nada.

---

## 10. Presencia en la UI

Sin cambios: header con semáforo, huellas en pantallas, y el gato (§10.2 del original,
que queda tal cual — está en Fase 3 y no bloquea nada).

**Regla dura que se conserva:** Guillermo es la cara, no la autoridad. Los errores son
específicos y técnicos —`falta Manager Report del 18-ago, no se importó nada`— nunca en
voz de gato.

⚠️ **Observación de proporción:** el gato tiene 90 líneas de spec; **D-8 —qué pares de
reportes deben cuadrar y con qué tolerancia— tiene dos, y sigue sin resolver.** El nivel
3 de validación es, según el propio original, *«lo que distingue "los archivos están" de
"los datos sirven"»*. Esa es la pieza que decide si Guillermo sirve.

---

## 11. Fases — reordenadas para que la primera sea entregable

La Fase 1 del original exigía manifiesto + validación + tablas + estados + config +
heartbeat + correo + entorno preview **antes de entregar nada**, y depende de D-1, que no
está resuelto.

### ✅ Fase 0 — Identidad de archivo *(aprobada, en construcción)*

`import_batches` + `import_files` con checksum, colgadas de los endpoints de subida que
**ya existen**. **No cambia ningún comportamiento: solo registra**, y rechaza el reimport
del mismo archivo con 409 + flag explícito.

Cierra el hueco #1, es puramente aditiva, no depende de ninguna decisión pendiente, y
**sirve aunque Guillermo nunca se termine.**

### Fase 1 — La ronda en modo sombra
Manifiesto (`expected_reports`) + validación niveles 1 y 2, reusando los parsers que ya
existen. Máquina de estados, config, heartbeat. **No escribe en FinPlan.**

### Fase 2 — Nivel asistido
Importación real. Cola de excepciones con propuesta de IA. `mapeo_origen` extendido con
texto normalizado. Validación nivel 3 (bloqueada por D-8) y detector de falso positivo.
Rol `guillermo_approver` + arreglo de `get_current_admin`.

### Fase 3 — Presencia
Header, huellas, el gato, comandos, resumen semanal.

#### ✅ Los avisos por correo — construidos 2026-08-20 (pendiente 20)

`app/guillermo/correo.py` + `GET /guillermo/correo/` + la sección de la pantalla.
Sin esto el dead-man switch **sólo grita adentro de FinPlan**: si nadie abre la app,
un Guillermo trabado se ve igual que uno al día.

Tres avisos, y cada uno calla por una razón distinta:

| aviso | cuándo | por qué así |
|---|---|---|
| rojo del dead-man switch | latido vencido, **una vez por día** | 47 correos iguales enseñan a filtrar el remitente |
| hallazgos nuevos | **sólo si hay algo nuevo** | uno diario que casi siempre dice «0 nuevos» se aprende a saltear, y con él se saltea el que sí traía algo |
| resumen semanal | su día, **aunque no haya nada** | es el único aviso cuya AUSENCIA significa algo: los otros callan cuando no hay novedad, así que su silencio no prueba que el canal viva |

⚠️ **El vigilante vive en los tics en que la ronda NO corre.** Un dead-man switch que
vive dentro del proceso que vigila no puede avisar cuando ese proceso muere; pero el
cron despierta 48 veces por día y 47 no tienen nada que hacer.

⚠️ **Y el vigilante NO late.** Escribir un latido al avisar silenciaría la alarma que se
acaba de disparar: el próximo tic vería el latido fresco y diría que todo está bien.

⚠️ Las credenciales SMTP van en el **entorno**, igual que la llave del modelo. Los
destinatarios (`notify_emails`) van en la base porque son la decisión **D-5 de cada
propiedad**, y nacen vacíos.

### Fase 4 — Fuente automática
Migrar a Scheduled Reports o a OHIP. `core/` no se toca — solo cambia el `ReportSource`.

---

## 12. Decisiones pendientes — actualizadas

| # | Decisión | Estado |
|---|---|---|
| **D-0** | Runtime | ✅ **Resuelto**: paquete dentro del backend de Railway + cron |
| **D-3** | ¿Solo Opera o también el CHECKBOOK? | ✅ **Solo Opera** (el GL ya tiene `origenes/`) |
| **D-6** | Definición de «período cerrado» | ✅ **Resuelto** en §6 — la pregunta original estaba mal planteada |
| **D-1** | Qué reportes, formato, frecuencia, obligatorios | ✅ **Resuelto 2026-08-20.** XML de Operations y Marketing diarios; actuales y Balance Sheet mensuales |
| **D-8** | Qué debe cuadrar | ✅ **Reformulado 2026-08-20.** El owner lo pidió más ancho: «todo auxiliar contra el GL, en todos los tabs, cada despliegue». Construido sobre `veredicto_del_detalle`. 🔴 Sigue abierto qué pares de REPORTES DE OPERA cuadran entre sí — eso espera D-1 y D-2 |
| **D-2** | ¿El Manager Report sale en CSV/XLSX en vez de PDF? | ✅ **Resuelta 2026-08-20: XML de Opera; los uploads, Excel.** Ni CSV ni PDF — no hay parser nuevo que escribir |
| **D-4** | ¿OHIP habilitado en la licencia? | 🔴 Del owner. Bloquea la Fase 4 |
| **D-5** | Quién recibe notificaciones y quién aprueba | 🔴 Del owner |
| **D-7** | Cuántos archivos por día por propiedad | 🔴 Del owner. Dimensionamiento |
| **D-9** | *(nueva)* ¿Contra qué se mide la tasa de acierto del modo sombra? | 🔴 Del owner. §4 |

---

## Apéndice — controles no negociables

1. **Reversibilidad total.** Batch completo con un botón. Nunca línea por línea.
2. **Candado de escenario respetado** (§6). Y cerrar el hueco de `PATCH /status/` (§7).
3. **Kill switch.** Apaga Guillermo entero y devuelve todo a carga manual.
4. **Auditoría completa.** Cada llamada al modelo: entrada, propuesta, confianza,
   decisión humana, timestamp.
5. **Heartbeat / dead-man switch.** Sin heartbeat: correo rojo + status rojo. Es lo que
   hace que el silencio signifique «todo bien» en vez de «no sé».
