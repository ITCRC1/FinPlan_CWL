# FinPlan CWL

Planificación y análisis financiero hotelero bajo USALI. Construye Budget y
Forecast dentro del sistema, importa los Actuals de Integrity/QuickBooks, y
genera el P&L y el reporte de propietarios.

**Un hotel = un despliegue con su propia base.** No es multi-tenant: el mismo
repo se despliega N veces con variables distintas. Ver
[docs/CLONAR_PROPIEDAD.md](docs/CLONAR_PROPIEDAD.md).

| | |
|---|---|
| Backend | FastAPI · SQLAlchemy async · PostgreSQL · Python **3.12** |
| Frontend | Next.js 14 · TypeScript · Tailwind · Node **24** |
| Migraciones | Alembic (head actual: **136**) |
| Pruebas | 3.671 con pytest |
| Despliegue | Railway (backend y frontend) |

La especificación funcional completa está en [CLAUDE.md](CLAUDE.md) — 30
secciones con las reglas de negocio, el catálogo de cuentas y el modelo de
datos. Este README es solo el punto de entrada operativo.

---

## Arrancar en local

Necesitás PostgreSQL, Python 3.12 y Node 24.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Creá `backend/.env` a partir de `backend/.env.example`. Después:

```bash
.venv\Scripts\python -m alembic upgrade head   # crea el esquema (136 migraciones)
.venv\Scripts\python -m app.seed               # siembra el motor contable
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

Documentación de la API en `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm ci
```

Creá `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api
NEXT_PUBLIC_HOTEL_ID=CWL
```

```bash
npm run dev     # http://localhost:3000
```

### Pruebas

```bash
cd backend && python -m pytest        # 3.671 pruebas
cd frontend && npx tsc --noEmit       # tipos
cd frontend && npm run build          # build de producción
```

Corren solas en cada push (`.github/workflows/pruebas.yml`).

---

## Mapa del repo

```
backend/
  app/
    api/          endpoints por dominio (revenue, payroll, costs, opex, pl…)
    engine/       el cálculo: P&L, revenue, planilla, allocations, KPIs
    importers/    lectura de los Excel de origen
    models/       tablas SQLAlchemy
    seed_data/    JSON que el seed re-afirma en CADA arranque
  alembic/versions/   136 migraciones
  scripts/      herramientas de operación (respaldo, auditoría, cuadres)
  tests/
frontend/
  app/          105 pantallas (App Router)
  components/   15 componentes compartidos
  lib/api.ts    todas las llamadas al backend
  messages/     textos es/en
docs/           22 documentos — ver el índice al final
data/           Excel de referencia
*.xlsx          Excel de origen que leen los importadores (vía DATA_DIR)
```

---

## Desplegar

Dos servicios de Railway sobre el mismo repo, más un PostgreSQL.

| Servicio | Root Directory | Config |
|---|---|---|
| backend | `backend` | `backend/railway.json` |
| frontend | `frontend` | `frontend/railway.json` |
| cron *(opcional)* | `backend` | `backend/railway.cron.json` |

El Root Directory **no es opcional**: cada servicio tiene su `railway.json`,
`requirements.txt` / `package.json` adentro de su carpeta, no en la raíz.

### Variables

**Backend**

| Variable | Nota |
|---|---|
| `DATABASE_URL` | Poner `${{Postgres.DATABASE_URL}}`. El código la normaliza a `+asyncpg` solo. |
| `SECRET_KEY` | Firma los JWT. El default `dev-secret-change-me` permite falsificar sesiones. |
| `CORS_ORIGINS` | URL exacta del frontend, separadas por coma. Sin esto el navegador bloquea todo. |
| `HOTEL_ID` `HOTEL_NAME` `HOTEL_ROOMS` `HOTEL_TC_USD` | ⚠️ Los defaults son los de Corcovado. Un hotel nuevo sin estas nace llamándose Corcovado, con 30 habitaciones y TC 530. |

**Frontend**

```
NEXT_PUBLIC_API_URL=https://<backend>/api      ← con /api, sin barra final
NEXT_PUBLIC_HOTEL_ID=<ID>
```

---

## Respaldo y restauración

Es la única forma soportada de mover una instalación completa. **Reimportar los
Excel no la reproduce**: los conceptos manuales de planilla, los allocations y
las versiones enllavadas no salen de ningún Excel, y la diferencia no avisa
porque los totales siguen cuadrando.

```bash
cd backend

# Sacar todo el dato a CSV (una tabla por archivo) + manifiesto
python -m scripts.exportar_base --destino C:\ruta\respaldo
python -m scripts.exportar_base --destino C:\ruta --sin-usuarios   # para entregar a terceros

# Meterlo en otra base. Por defecto SOLO VERIFICA.
python -m alembic upgrade head
python -m scripts.importar_base --origen C:\ruta\respaldo             # verifica
python -m scripts.importar_base --origen C:\ruta\respaldo --aplicar   # escribe
```

`--url` apunta a una base distinta de la del `.env` — sirve para restaurar
directo contra Railway.

El import corre en **una sola transacción** y al final cuenta tabla por tabla
contra el manifiesto. Ese conteo es lo único que prueba que llegó completo: un
CSV truncado se copia sin dar error.

Después de restaurar, correr **Admin → Chequeo** en la app y comparar contra el
origen.

---

## Las trampas

Modos de falla que ya ocurrieron y que **no dan error** — el total sigue
cuadrando y la plata cambia de lugar sola.

**El seed manda sobre el mapeo.** `app/seed_mapping.py` corre en cada deploy y
re-afirma campo por campo `account_mapping` y `report_line_config` desde
`app/seed_data/mapping_pl.json`. Una migración que toque esas dos tablas y no
cambie también el JSON **se revierte sola en el próximo deploy**. Pasó con las
migraciones 093/094/095. Blindado por `tests/test_seed_manda_sobre_mapeo.py`.

**Departamentos de allocation.** 0220 (comida de empleados) y 0161 (lavandería
interna) reparten su gasto y no entran a los totales operativos. La regla vive
en `ALLOCATION_EXCLUDE` (`app/importers/gl_detail_importer.py`) y la blinda
`tests/test_gl_allocation.py`. Se aplica sola a cualquier mes que se suba.

**`NEXT_PUBLIC_*` se hornea al compilar.** Cambiar una de esas variables exige
**Redeploy** del frontend, no Restart. Si falta `NEXT_PUBLIC_API_URL`, el build
falla a propósito (`next.config.mjs`): antes salía a producción apuntando a
`localhost` y moría con «Failed to fetch», sin avisar.

**El bootstrap del admin se cierra solo.** `POST /api/auth/bootstrap` crea el
primer admin, pero se niega con `409` apenas existe cualquier usuario. Con
`HOTEL_ID=CWL` el seed siembra nueve `collaborator` en el mismo arranque, así
que **en un despliegue CWL nuevo nunca se puede crear un admin por la API** — hay
que promover uno por SQL. En un hotel que no sea CWL no se siembra nadie y el
bootstrap funciona.

**`DATA_DIR` no existe en el servidor.** Los endpoints que importan Excel leen
una ruta local (`C:/FinPlan_CWL` por defecto). En Railway fallan. Los datos se
cargan desde una máquina, no desde la app.

---

## Documentación

**Operación**
[CLONAR_PROPIEDAD.md](docs/CLONAR_PROPIEDAD.md) · abrir una propiedad nueva ·
[PROVISIONING_MASTER_DATA_PLAN.md](docs/PROVISIONING_MASTER_DATA_PLAN.md) ·
[INTEGRACIONES.md](docs/INTEGRACIONES.md) ·
[GUILLERMO.md](docs/GUILLERMO.md) — ingesta autónoma de reportes

**Contabilidad y reportes**
[CHECKBOOK_FORMATO.md](docs/CHECKBOOK_FORMATO.md) ·
[OWNERS_Q.md](docs/OWNERS_Q.md) ·
[COSTOS_GRUPOS.md](docs/COSTOS_GRUPOS.md) ·
[MIXER_DE_CANALES.md](docs/MIXER_DE_CANALES.md) ·
[ESTADISTICAS_INVENTARIO.md](docs/ESTADISTICAS_INVENTARIO.md) ·
[AUDITORIA_CASHFLOW_DOS_METODOS.md](docs/AUDITORIA_CASHFLOW_DOS_METODOS.md)

**Estado y decisiones**
[PENDIENTES.md](docs/PENDIENTES.md) — el registro más grande y más vivo ·
[DECISIONES_DEL_OWNER.md](docs/DECISIONES_DEL_OWNER.md) ·
[COMMERCIALIZATION_READINESS.md](docs/COMMERCIALIZATION_READINESS.md) ·
[PLAN_DE_CIERRE.md](docs/PLAN_DE_CIERRE.md)

**Planes**
[PLAN_FASES_1_Y_2.md](docs/PLAN_FASES_1_Y_2.md) ·
[I18N_PLAN.md](docs/I18N_PLAN.md) ·
[NAVEGACION_ENTRE_PANTALLAS.md](docs/NAVEGACION_ENTRE_PANTALLAS.md) ·
[PORTING_TOURS_PLANNING_CASHFLOW.md](docs/PORTING_TOURS_PLANNING_CASHFLOW.md)

> [MULTIPROPERTY_PLAN.md](docs/MULTIPROPERTY_PLAN.md) quedó **supersedido**
> (2026-08-17) por `CLONAR_PROPIEDAD.md`. Se conserva por el historial.
