# Comercialización / Readiness Multi-Cliente — FinPlan CWL

> **Estado:** EVALUADO (auditoría, 2026-06-29). No iniciado.
> **Pregunta del owner:** ¿Railway y el stack actual aguantan venderlo a muchos clientes, o hay que buscar una base más robusta?
> **Veredicto:** **NO hay que re-plataformar.** La carga no es el problema; la robustez del producto sí. Endurecer el stack actual (~3-5 semanas) → vendible. Re-plataformar solo con gatillos nombrados.
> **Depende de / complementa:** [[MULTIPROPERTY_PLAN]] (el aislamiento de tenant es el bloqueante M3, acá sube a #1).

---

## 1. Carga vs Robustez (la distinción clave)

- **Carga (¿aguanta el tráfico?):** SÍ, sin cambiar stack. Es B2B de baja concurrencia — pocos usuarios de finanzas por hotel, recalcs pesados pero infrecuentes; fact tables indexadas por `scenario_id`; payloads acotados (decenas de KB). Railway/Postgres/Vercel NO son el muro. Los únicos techos de carga son **auto-infligidos** (1 proceso uvicorn sin workers, pool default ~15 conexiones, recalc síncrono en el request, reportes que recomputan 12 meses por vista en vez de leer `PLLine` persistido) — todos tuneables en horas-a-días.
- **Robustez (¿se puede vender el mismo sistema compartido a clientes que no se conocen?):** ACÁ está el trabajo real, y es **correctitud/seguridad/operabilidad, no caballos de fuerza.** "Podés pagar un plan más grande de Railway con tarjeta; no podés pagar para salir de una fuga de datos entre clientes."

## 2. Techo realista del stack actual
Endurecido (tenancy por fila, pool tuneado, gunicorn workers/réplicas, reportes desde `PLLine`/cache, recalc a background cuando moleste): **~50-100+ hoteles / cientos de usuarios** antes de que la INFRA (no el código) fuerce re-plataformar. Dado el perfil low-traffic, el **techo comercial (ventas/soporte/onboarding) llega antes que el técnico.** Tratar 50-100 como zona-de-gatillo para re-evaluar CON métricas, no como muro a temer.

## 3. 🔴 Bloqueantes para vender (cerrar en Etapa 1 — ~3-5 semanas)

| # | Bloqueante | Dónde | Por qué es fatal | Esfuerzo |
|---|-----------|-------|------------------|----------|
| 1 | **Sin aislamiento de tenant (IDOR)** | `models/user.py` (sin hotel_id); routers toman `hotel_id`/`scenario_id` de la URL sin chequeo de ownership; `get_current_user` solo prueba que el user existe | El instante que entra un 2º cliente a la DB compartida, el cliente B itera IDs y lee las finanzas del cliente A. Brecha de confidencialidad, no feature gap | 1-2 sem |
| 2 | **Migraciones inline en cada deploy a prod, sin staging/CI** | `Procfile`/`railway.json`: `alembic upgrade head && python -m app.seed && uvicorn ...` | Una migración mala/que lockea falla el boot, reintenta 3x, servicio CAÍDO para TODOS los clientes a la vez. Blast radius = base entera de clientes en un push | 2-4 días |
| 3 | **Sin backups verificados / DR** | repo/docs (sin pg_dump, sin runbook) | Datos financieros de clientes sin restore probado = sin backup. Buyers B2B piden RPO/RTO | 1-2 días |
| 4 | **`SECRET_KEY` único con fallback inseguro + seed con password hardcodeado** | `auth.py:21` (`'dev-secret-change-me'`); `seed.py` (`'CWLintegrity2026'`, 9 users) | Si `SECRET_KEY` queda sin setear, bootea con clave pública conocida → cualquiera forja JWTs admin de TODOS los tenants. Sin rotación/key-versioning | 1-2 días |
| 5 | **CORS abierto a cualquier `*.vercel.app` con credenciales** | `main.py:30` `allow_origin_regex=r'https://.*\.vercel\.app'` + `allow_credentials=True` | Cualquier sitio en vercel.app puede hacer llamadas con credenciales. Bearer limita el riesgo pero amplía superficie | ~1 hora |

**Nota:** el JWT hand-rolled / pbkdf2 en sí está BIEN — no hace falta reemplazarlo, solo endurecer el secreto y quitar creds sembradas del path de boot.

## 4. Roadmap por etapas (gatillos, no ansiedad)

| Etapa | Gatillo | Trabajo |
|-------|---------|---------|
| **1 — Primeros clientes que pagan** | Cualquier cliente #2 ≠ CWL (antes de que su data comparta la DB) | Org/Tenant + User→Org→Hotel + dependency `require_hotel_access` en cada router (mata el IDOR); Railway staging + migraciones gateadas + snapshot pre-migrate; pg_dump nocturno off-Railway + restore probado; fail-fast en SECRET_KEY + quitar creds sembradas; pinear CORS. **~3-5 sem. Es la puerta para vender a alguien ≠ CWL.** |
| **2 — Madurez operativa (decenas)** | ~10+ tenants, O 1ª queja de lentitud, O pool exhausto observado | Sentry (FE+BE) + logs estructurados por tenant; tunear engine DB (pool_size/max_overflow/pool_pre_ping/pool_recycle); gunicorn `-k uvicorn.workers.UvicornWorker` 2-4 workers y/o 2 réplicas (`--proxy-headers`); servir reportes desde `PLLine` persistido/cache; arreglar 2 N+1 (bulk-load concept entries; dept totals una vez en allocations); audit log append-only (quién cambió qué forecast); `recalculate_scenario` a worker/queue (RQ + Railway worker) cuando la latencia moleste; drill de restore periódico |
| **3 — Enterprise / scale (re-plataformar SOLO si se dispara)** | Contrato SOC2/residencia/DB-por-tenant, O un tenant gigante, O saturación MEDIDA de Postgres que el plan más grande no absorbe (~100+ clientes) | Postgres a Neon/RDS (PITR + read replicas); DB-por-tenant para quien exija aislamiento/residencia; límites de concurrencia + rate-limiting por tenant en paths de cómputo pesado; auth dependency en endpoints caros de recalc/report. **NO hacer nada de esto preventivamente — esperar la métrica o el contrato** |

## 5. Decisiones del owner (con recomendación)

| Decisión | Recomendación |
|----------|---------------|
| **Modelo de tenancy:** DB compartida con scoping por fila vs DB-por-tenant | **DB compartida + tenancy por fila ahora.** DB-por-tenant es prematuro; híbrido después (aislar solo tenants con compliance/grandes) |
| **Modelo de acceso / agrupación** (revisado 2026-06-29 — ver §5b) | **NO árbol Org→Hoteles.** El **hotel es la unidad de aislamiento** (cuenta propia, default-deny). Acceso por **grants muchos-a-muchos** (principal→hoteles) + **grupos de consolidación** nombrados con su propio acceso. Maneja operador≠dueño y dueños aislados entre sí, que un árbol no podía |
| **Provisioning de clientes** (el seed CWL debe salir del path de deploy) | Script interno por cliente firmado (rápido) → UI de provisioning en Etapa 2. Quitar `python -m app.seed` + users hardcodeados del boot YA |
| **RPO/RTO de backups** | Nocturno off-Railway + restore probado para Etapa 1 (barato, responde la pregunta del buyer). PITR (Neon/RDS) solo si un contrato/tenant grande exige cero pérdida |
| **Gatillo para re-plataformar** | Adoptar los 3 gatillos nombrados (SOC2/residencia · saturación medida · ~100+ clientes). NO re-plataformar ahora. Instrumentar (Etapa 2) para VER la saturación venir |

## 5b. Modelo de acceso y consolidación (decidido 2026-06-29)

**Realidad del negocio:** The Costa Rica Collection existe pero los hoteles tienen **dueños diferentes** con intereses propios. Algunos (ej. Amarena) son de **otros dueños y el equipo solo OPERA**. Hay dueños que **no deben ver** los hoteles de otros. Por eso NO sirve un árbol "Org dueña de N hoteles".

**Modelo (grant-based, muchos-a-muchos):**
- **`hotel`** = unidad de aislamiento (cuenta propia, **default-deny**: sin grant no se ve nada).
- **`principal`** = identidad de acceso (usuario/cuenta). Tipos: **operador** (acceso amplio a los hoteles que opera), **dueño** (acceso a su(s) hotel(es)), **staff** (un hotel). ✅ El operador es un **principal con acceso amplio** (rol explícito), no un grupo más.
- **`access_grant`** `(principal_id, hotel_id, role)` — muchos-a-muchos. La frontera de seguridad.
- **`consolidation_group`** `(id, name)` + **`group_hotel`** `(group_id, hotel_id)` muchos-a-muchos (✅ **un hotel puede estar en VARIOS grupos**: ej. el grupo "operados por el equipo" Y el grupo de su dueño si comparte dueño con otro). El grupo tiene **su propio acceso** (quién ve el consolidado).

**🔑 Regla de oro de seguridad:** un reporte consolidado **solo agrega los hoteles que el viewer ya tiene en sus grants** = `(hoteles del grupo) ∩ (hoteles permitidos al viewer)`. El grupo NUNCA filtra de más → un dueño jamás ve la data de otro, ni siquiera dentro de una vista de grupo.

**Mapeo de casos:**
- Amarena (operan, no son dueños): dueño de Amarena → grant solo a Amarena; el operador → grant a Amarena + todos los operados.
- Dueños aislados: cada uno grant solo a su hotel; nunca acceso cruzado.
- Consolidado del operador: grupo "CRC operados" con todos, acceso solo para el operador; los dueños NO están en ese grupo.
- Dueño con 3 hoteles: grupo de esos 3, visible solo para él.

Esto **reemplaza** la decisión previa "Org→varios Hoteles". El aislamiento de tenant (bloqueante #1) ahora se implementa como: hotel default-deny + tabla `access_grant` chequeada en cada endpoint (`require_hotel_access`).

## 6. Resumen
- **Railway/Vercel/Postgres alcanzan para los primeros 50-100+ clientes** — no re-plataformar.
- **El trabajo real es robustez de producto, y el #1 es aislamiento de tenant** (fuga entre clientes = fatal). Ya estaba en el plan multi-propiedad; para comercializar es el bloqueante absoluto.
- **~3-5 semanas de endurecimiento** → vendible con seguridad. El aislamiento de tenant + Org→Hotel se construyen junto con la fundación multi-propiedad ([[MULTIPROPERTY_PLAN]] paso 2 + 7) — es el mismo trabajo, ahora con prioridad comercial.
