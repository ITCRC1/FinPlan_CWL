# Abrir una propiedad nueva (AMA, OXI, OJO)

> Escrito para arrancar en frío. Al 2026-08-14 el código está verificado: **no
> hay que tocarlo**. Abrir una propiedad es crear infraestructura y poner
> variables. **Auditoría de seguridad, 2026-08-17: sin bloqueadores** — ver la
> sección al final.

## Lo primero: el modelo

**Un hotel = un despliegue aparte, con su propia base. No es multi-tenant.**

**El REPO es UNO SOLO.** Corcovado y Amarena salen del mismo código, desplegado
dos veces con variables distintas. No se saca un fork:

* Un arreglo se hace una vez y se despliega N veces. Con forks, cada arreglo hay
  que portarlo a mano y a los tres meses las propiedades divergen sin que nadie
  lo note.
* El motor, el mapeo del P&L y las migraciones viajan **como código**, no como
  filas de una base compartida. Esa es la contrapartida real del modelo: «una vez
  arreglado» son N deploys, y por eso conviene que sea N deploys **del mismo
  commit**.

## Las dos propiedades no se abren igual

**Corcovado se COPIA. Los otros tres NACEN.** Medido en producción el
2026-08-14:

| | Filas | Cómo llega a la propiedad nueva |
|---|---:|---|
| Lo que cargó el owner | **37.515** | **Solo con un dump de la base.** No se reproduce reimportando |
| Lo que repone el seed | **1.388** | **Solo, en cada arranque**, desde el JSON del repo |

Las 1.388 son la maquinaria contable: `account_mapping` (1.172),
`report_line_config`, `department_catalog`, `stat_accounts`, `market_codes` y
`canales_comerciales`. **No son de ningún hotel en particular.**

> ⚠️ Por eso **«en cero» no es «vacío e inservible»**: una propiedad nueva nace
> con **cero dato de negocio y el motor completo**. Eso es justo lo que hace que
> la carga histórica tenga dónde aterrizar — sin el mapeo, un GL subido no cae en
> ninguna línea del P&L.

### Corcovado: dump y restore, NO reimportar

Los 37.515 registros incluyen cosas que **ningún Excel reproduce**:

* `payroll_concept_entries` (9.856) — los conceptos manuales de planilla. **Y
  «Recalcular» NO los repone**: solo repone SW, CCSS y aguinaldo.
* `allocation_entries` (3.353) y `pl_manual_inputs` (72).
* Las **cinco versiones 2027 enllavadas**, que son fotos históricas.
* `sales_channel_configs` (507) y las 456 tarifas del mixer aplicado.

Reimportar los Excel daría un Corcovado **parecido y distinto**, y la diferencia
no avisaría: los totales seguirían cuadrando.

    pg_dump  <base actual>  →  pg_restore  <base del proyecto CWL nuevo>

Los datos ya vienen estampados con `hotel_id = 'CWL'`, así que entran tal cual.

### AMA, OXI, OJO: base vacía y a cargar

Base nueva sin restaurar nada. El arranque siembra las 1.388 filas del motor y
**nada más**: sin tipos de habitación, sin usuarios, sin paquete. El owner sube
la historia de cada uno.

### ⚠️ Dos Corcovados a la vez

Si la instalación actual **se queda como base original** y además se crea la
copia de Corcovado, desde ese momento hay **dos bases de Corcovado**, y cada una
va a envejecer por su lado. Conviene decidir **cuál es la que manda** el mismo
día que se hace la copia — y que la otra quede como archivo, no como app en uso.

---

## Verificación del 2026-08-14 — el código ya está listo

| Qué se revisó | Estado |
|---|---|
| Literales `"CWL"` en el backend | **6, todos legítimos**: comentarios, el default documentado y guardas deliberadas del seed |
| Literales `"CWL"` en el frontend | **1**: el default de `lib/hotel.ts`, documentado |
| Identidad del hotel | Sale del entorno (`app/hotel_actual.py`, `lib/hotel.ts`) |
| Tipos de habitación | Salen de `room_type_configs`; a un hotel ≠ CWL el seed **no le inventa ninguno** |
| Usuarios del equipo | El equipo de Corcovado **no** se siembra en otro hotel |
| Semillas (paquete, experiencias, canales) | Por carpeta `app/seed_data/<HOTEL_ID>/`. **Sin carpeta, las pantallas nacen en blanco** — que es la verdad |

⚠️ **NO crear `app/seed_data/AMA/`** copiando la de Corcovado. Nacer en blanco es
correcto: una pantalla con el tour a San Pedrillo y el transporte Sierpe/Drake
está a un clic de que alguien guarde el producto de otro hotel.

---

## Los pasos

### 1. Base de datos y backend (Railway)

Proyecto nuevo, con su Postgres. **No se comparte base con Corcovado.**

Variables del servicio backend:

| Variable | Valor para AMA | Nota |
|---|---|---|
| `HOTEL_ID` | `AMA` | ⚠️ Sin esto **queda CWL** y el hotel nace llamándose Corcovado |
| `HOTEL_NAME` | `Amarena Canvas Beach Hotel` | Encabezado de los Excel del servidor |
| `HOTEL_SHORT_NAME` | `Amarena` | Nombre de archivo de las descargas |
| `HOTEL_ROOMS` | *el real* | ⚠️ **El default es 30 — las de Corcovado** |
| `HOTEL_TC_USD` | *el real* | ⚠️ **El default es 530 — el de Corcovado** |
| `DATABASE_URL` | del Postgres del proyecto | `postgresql+asyncpg://…` |
| `SECRET_KEY` | uno nuevo | **No reusar el de Corcovado** |
| `SEED_TEAM_CWL` | *no poner* | Si se pone, siembra el equipo de Corcovado en otro hotel |

`HOTEL_ROOMS` y `HOTEL_TC_USD` son los dos peligrosos: **tienen default y el
default es de Corcovado**. Un despliegue sin ellos arranca con números que se ven
perfectamente normales y están mal. Si todavía no se saben, ponerlos igual —
en `0` para habitaciones y el TC del día— y corregir después en Master Data →
Provisionamiento, que es donde vive la verdad.

El arranque corre solo (`Procfile`): `alembic upgrade head` → `python -m app.seed`
→ `uvicorn`.

### 2. Frontend (Vercel)

Proyecto nuevo apuntando al **mismo repo**, carpeta `frontend`.

| Variable | Valor |
|---|---|
| `NEXT_PUBLIC_API_URL` | la URL del backend de **esta** propiedad + `/api` |
| `NEXT_PUBLIC_HOTEL_ID` | `AMA` |
| `NEXT_PUBLIC_HOTEL_NAME` | `Amarena Canvas Beach Hotel` |
| `NEXT_PUBLIC_HOTEL_SHORT_NAME` | `Amarena` |

⚠️ **`NEXT_PUBLIC_API_URL` es el error que ya pasó una vez**: sin ella el deploy
queda **verde** y apuntando a `localhost`. Se ve desplegado y no funciona.

⚠️ Tienen que llevar el prefijo `NEXT_PUBLIC_`: sin él, Next no las expone al
navegador y llegan `undefined`.

### 3. Primer usuario

El seed **no** crea usuarios en un hotel que no sea CWL — son personas de otra
propiedad. Hay que crear el primer administrador de Amarena a mano.

### 4. Cargar la propiedad, en este orden

1. **Master Data → Provisionamiento**: nombre, habitaciones, TC.
2. **Tipos de habitación**: acá nacen los códigos (`BL01`, `BI02`…). ⚠️ **El
   código no se mueve nunca**: es lo que liga la categoría entre escenarios,
   reportes y propiedades. Se puede editar el nombre; el código y el orden no.
3. **Paquete / experiencias / canales**: nacen en blanco a propósito.
4. **Escenarios**: crear el primero. ⚠️ **NO usar «crear copiando» sin revisar el
   origen** — hoy propone el Budget del año más nuevo, que está vacío (ver
   `PENDIENTES.md` A0.2).

---

## Verificación de que el clon nació sano

```bash
curl -s https://<backend-nuevo>/health
```

Y en la base nueva, que sea SU hotel y no el de Corcovado:

```sql
SELECT id, name, rooms, tc_usd_default FROM hotels;
-- tiene que decir AMA, no CWL
SELECT count(*) FROM room_type_configs;
-- tiene que dar 0: los tipos los carga el owner
SELECT count(*) FROM users;
-- 0 o solo los que se crearon a mano
```

Si `hotels` dice `CWL`, la variable `HOTEL_ID` no llegó: **el hotel ya quedó
creado con el id equivocado** y hay que corregirlo antes de cargar nada, porque
todo lo que se cargue después cuelga de ese id.

---

## Lo que NO hay que hacer

* **No copiar `app/seed_data/CWL/`** a la carpeta de la nueva propiedad.
* **No reusar `SECRET_KEY`.**
* **No compartir la base** con Corcovado.
* **No poner `SEED_TEAM_CWL`.**
* **No sacar un fork del repo** (ver arriba).

---

## Auditoría de seguridad (2026-08-17) — sin bloqueadores

Se revisó si algo del login/permisos asume una sola instalación. Resultado:
clonar y desplegar funciona sin tocar código. Detalle:

| Qué se revisó | Resultado |
|---|---|
| Email de admin hardcodeado en el código | **No existe.** `is_admin` sale solo de `User.role == "admin"` en la base — ninguna cuenta tiene privilegio por ser quien es |
| Cómo nace el primer usuario de una propiedad nueva | `POST /auth/bootstrap` — funciona **una sola vez**, mientras la tabla de usuarios está vacía, y se cierra sola apenas existe el primero. No es una fila que haya que insertar a mano en la base |
| CORS — ¿el frontend nuevo puede hablarle al backend nuevo? | Sí, sin tocar código: además del dominio actual, el backend acepta **cualquier** `*.vercel.app` (`app/main.py`) |
| Límite de pedidos / lista de IPs | No existe ninguno — no hay nada de eso que asuma una sola propiedad |
| `SECRET_KEY` compartida entre propiedades | **Punto real a cuidar** (no es un bloqueador, es un cuidado al desplegar): el código trae un valor por defecto (`dev-secret-change-me`) si la variable no está puesta. Dos propiedades sin `SECRET_KEY` seteada quedarían firmando con el mismo secreto genérico. Por eso ya está en la tabla de variables arriba: **`SECRET_KEY` — uno nuevo, no reusar** |
| `User.email` único en la tabla | Es único **dentro de cada base**, no entre propiedades — como cada propiedad tiene su base aparte, el mismo correo (ej. `brodriguez7301@gmail.com`) se puede repetir como admin en las 4 sin que choquen entre sí |

---

## Códigos, contraseñas y usuarios maestros — dónde van

**Nunca en este archivo.** Este documento está en el repositorio de código; una
contraseña o un `SECRET_KEY` real committeado queda en el historial de git para
siempre, aunque se borre después.

**Los códigos de propiedad SÍ son públicos** (no son secretos, son la llave con
la que se arma todo el dato) — esos quedan documentados en
[`CLAUDE.md`](../CLAUDE.md), tabla de identidad del proyecto:

| Código | Propiedad |
|---|---|
| `CWL` | Corcovado Wilderness Lodge — la instalación actual |
| `AMA` | Amarena Canvas Beach Hotel |
| `OXI` | Oxígen |
| `OJO` | Ojochal |

**Lo que sí es secreto** — `SECRET_KEY` de cada backend, contraseña del primer
admin de cada propiedad, y cualquier credencial de Railway/Vercel — va en un
archivo **aparte, NUNCA en git**: `docs/CREDENTIALS.local.md` (mismo patrón que
ya usa `C:\DAILY-OPS`). Al día de hoy ese archivo no existe en este repo porque
**todavía no se abrió ninguna propiedad nueva** — no hay nada real que anotar
ahí. Se crea recién cuando se hace el primer bootstrap de AMA/OXI/OJO, con esta
forma:

```markdown
# Credenciales FinPlan — NO COMMITEAR (agregar a .gitignore)

## CWL — Corcovado (producción actual)
- Railway backend: <URL del proyecto Railway, no la del deploy>
- SECRET_KEY: (vive en Railway, no se copia acá)
- Admin: brodriguez7301@gmail.com

## AMA — Amarena
- Railway backend: <proyecto nuevo>
- Vercel frontend: <proyecto nuevo>
- SECRET_KEY: (vive en Railway, no se copia acá)
- Admin creado por bootstrap: <email> — contraseña la conoce solo quien la creó
```

La `SECRET_KEY` en sí **ni siquiera conviene anotarla acá**: vive en las
variables de entorno de Railway, que ya es el lugar seguro para eso — el
archivo local es para no perder la lista de *qué proyecto es cuál* y *quién es
el admin de cada uno*, no para duplicar el secreto en un segundo lugar.
