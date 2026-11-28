---
description: Replica una mejora de CWL en Amarena, Oxygen y Garden — revisa anclas, prueba, valida, commitea y empuja
argument-hint: <commit(s) de CWL o descripcion> [a: amarena,oxygen,garden]   — por ejemplo "aa69c69" o "los ultimos 3 commits" o "357f756 a: oxygen"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent, SendMessage
---

Replica en los otros FinPlan lo que pidio el owner: `$ARGUMENTS`

Si no dice QUE portar, mostrale los ultimos 10 commits de CWL (`git log --oneline -10`)
y preguntale cuales. Si no dice A DONDE, son los tres: Amarena, Oxygen y Garden.

## Los cuatro repos

| Propiedad | Carpeta | Servicio backend (Railway) |
|---|---|---|
| Corcovado `CWL` — **origen** | `C:\Users\User\Documents\FinPlan_CWL` | `FinPlan_CWL_Backend` |
| Amarena `AMA` | `C:\Users\User\Documents\FinPlan_Amarena` | `FinPlan_Amarena-Backend` |
| Oxígen `OXI` | `C:\Users\User\Documents\FinPlan_Oxygen` | `FinPlan_Oxygen Backend` (con espacio) |
| Ojochal Gardens `OJO` | `C:\Users\User\Documents\FinPlan Garden` | `FinPlan_Gardens_Backend` |

Railway despliega solo desde `main` de cada repo al recibir el push.

## La regla de oro: son clones que DIVERGIERON

El motor es el mismo, pero el codigo no esta igual en los cuatro. **Nunca copiar
archivos enteros de CWL encima de otro repo**: se pisa lo propio de esa propiedad
(su identidad sale de `app/hotel_actual.py` y `lib/hotel.ts`, nunca de un literal).
Casos reales que rompieron o casi rompen:

* En CWL `parse_gl_detail(...)` corre DESPUES de resolver el escenario; en los otros
  tres, ANTES. El mismo bloque en el mismo ancla daba `NameError` en cada subida.
* En CWL `frontend/app/month-end/pl-detail/` es OTRA pantalla; en los otros es copia
  de `reports/pl-detail`.
* Los numeros de linea no coinciden (la misma funcion puede estar 250 lineas mas abajo).

## Paso a paso — por cada repo destino

### 1. Preparar
* `git status -sb`: si hay cambios sin commitear que no son tuyos, **no los toques**
  ni los mezcles con el port; avisale al owner. Archivos `??` sueltos (Excels,
  `Claude outputs/`) no se agregan nunca.
* `git pull` si esta atras de `origin/main`.

### 2. Revisar que el cambio encaje
* Saca el diff en CWL: `git diff <commit>~1 <commit> -- <rutas>` (sin `CLAUDE.md`
  ni archivos propios de CWL como `seed_data/CWL/...`).
* `git apply --check -p1 <diff>` en el destino. Si aplica limpio, igual **lee el
  contexto**: que el ancla exista no garantiza que el orden del codigo alrededor sea
  el mismo. Si no aplica, porta a mano bloque por bloque, buscando cada ancla con Grep.
* Migraciones de Alembic: **renumerar** segun la cabeza de ese repo (`ls backend/alembic/versions`),
  y ajustar `down_revision`. Nunca dos migraciones con el mismo numero.
* ⚠️ Si el cambio toca `account_mapping` o `report_line_config`: el seed
  (`app/seed_data/mapping_pl.json`) **manda en cada deploy**. Una migracion sin el
  JSON se revierte sola. Ver la regla en el `CLAUDE.md` de cada repo.

### 3. Probar
* Tests del area tocada primero, despues la suite entera:
  `cd backend && python -m pytest -q -p no:cacheprovider`
* Si algo falla, comprobar si ya fallaba ANTES del port:
  `git stash -q && python -m pytest -q <los que fallaron>; git stash pop -q`.
  Fallas que ya estaban no frenan el port, pero se reportan. Fallas NUEVAS: se
  arreglan antes de seguir.
* Fallas previas conocidas (2026-11): `test_mixer_editable::test_la_semilla_obliga_a_declarar_el_destino`
  en CWL/Amarena/Oxygen; `test_usali` (4, ModuleNotFound) en CWL; `test_inventario_fijo_del_mes` (2) y
  `test_word_todas_las_vistas` en Amarena.
* Frontend, si se toco: `cd frontend && npx tsc --noEmit`.

### 4. Commit y push
* Mismo titulo que el commit de CWL; en el cuerpo: «Mismo arreglo que CWL `<hash>`»
  y lo que hubo que adaptar en este repo.
* `git push origin main`. Si el permiso de la sesion lo bloquea, decirlo y dejar el
  commit local — no buscar otra via.

### 5. Validar contra produccion (si aplica y si hay permiso)
Despues del deploy (`RAILWAY_GIT_COMMIT_SHA` del proceso = el commit nuevo), correr
un script de SOLO LECTURA dentro del contenedor. Ver «Correr un script en produccion».
Si el clasificador niega la lectura de produccion: **no insistir ni rodear**; dejarlo
como pendiente (paso 6) y decirlo.

### 6. Dejar constancia
* Si algo quedo pendiente (push, validacion, una adaptacion dudosa), anotarlo en la
  memoria de ESE proyecto (`C:\Users\User\.claude\projects\C--Users-User-Documents-FinPlan-<X>\memory\`)
  con el hash y que falta. Cuando se complete, **borrar la nota** para que no confunda.

## Correr un script en produccion

`railway` existe solo en el sandbox de Claude (el owner no lo tiene). Desde la carpeta
del repo (que ya esta `railway link`-eado):

* El Python de la app es `/opt/venv/bin/python` y el codigo esta en `/app`
  (`PYTHONPATH=/app`). El Python del shell (`python`) NO tiene las dependencias.
* `greenlet` necesita `libstdc++`: tomar `LD_LIBRARY_PATH` y `DATABASE_URL` del
  proceso 1: `export $(cat /proc/1/environ | tr '\0' '\n' | grep -E '^(LD_LIBRARY_PATH|DATABASE_URL)=' | xargs)`.
* Pasar el script en base64 dentro del comando (`echo <b64> | base64 -d > /tmp/x.py`).
  Un argumento de mas de ~20 KB da «Argument list too long»: subir en trozos de 6 KB
  con `printf %s <trozo> >> /tmp/x.b64`, uno por `railway ssh`.
* El motor necesita el catalogo de departamentos cargado como en el startup de la app:
  `set_dept_catalog(...)` con las filas de `DepartmentCatalog` antes de llamar al P&L.
* Para probar codigo NUEVO antes del deploy sin tocar la app que corre: `cp -r /app /tmp/appnew`,
  pisar ahi los archivos cambiados y correr con `PYTHONPATH=/tmp/appnew`. Borrar `/tmp/appnew` al terminar.

## Varios destinos a la vez

Los tres repos son independientes: si el port es grande, se pueden hacer en paralelo
(un subagente por repo, cada uno con este procedimiento y SOLO su carpeta). Si ya hay
sesiones de port vivas para Amarena/Oxygen/Garden, mandarles el encargo con
SendMessage en vez de arrancar de cero: ya conocen las diferencias de su repo.

## Lo que se le reporta al owner

Una tabla por repo: commit (hash), push si/no, tests (pasan / fallas previas / nuevas),
validacion en produccion (cuadra / pendiente / no aplica), y que hubo que adaptar.
Lo que quedo pendiente, en una linea por repo.
