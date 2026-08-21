"""Provisionamiento — qué departamentos usa cada propiedad.

El sistema se armó tomando un poco de cada hotel del grupo: Corcovado tiene
tours, Amarena tiene Club Madresal y Área Recreativa, otro tendrá lavandería
propia y otro no. El catálogo USALI es UNO SOLO para el grupo —no se bifurca—
y lo que cambia entre propiedades es esta matriz: la propiedad arranca con el
estándar completo y en el provisionamiento se DESMARCA lo que no aplica.

Dos reglas que hacen esto seguro:

1. **Filtra la visibilidad, nunca el cálculo.** Un departamento apagado
   desaparece de los selectores y de las pantallas de carga. Si tiene datos
   cargados, esos datos SIGUEN sumando en el P&L. Si apagar un departamento
   borrara plata del estado de resultados, esconder algo sería una forma de
   cambiar los números sin dejar rastro.

2. **Apagar algo que tiene datos exige confirmación.** El endpoint devuelve
   cuántas posiciones de planilla, líneas de OPEX o de costo hay detrás de cada
   casilla, y se niega a apagarla sin `force`. La pregunta «¿esto lo usa esta
   propiedad?» y la pregunta «¿esto tiene datos?» son distintas, y contestar la
   primera a ciegas es como se pierde información.

3. **Se provisiona por departamento MADRE, y la madre arrastra el paquete.**
   La matriz no ofrece los 39 departamentos sueltos sino las 23 madres, cada
   una con sus hijos y sets adentro. Ver `_paquetes` más abajo: ahí está la
   diferencia entre el paquete de VISIBILIDAD (parentesco a secas) y el de
   CÁLCULO (donde la bandera `room_set` sigue mandando).
"""
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_admin
from app.db import get_db
from app.errores import ErrorApi
from app.i18n import DEFAULT_LOCALE, LOCALES, normalize_locale
from app.models.hotel import Hotel
from app.models.scenario import Scenario
from app.models.department_catalog import DepartmentCatalog
from app.models.dept_enablement import DeptEnablement, DIMENSIONES, SCOPE_KINDS
from app.models.payroll_position import PayrollPosition
from app.models.opex_entry import OpexEntry
from app.models.cost_entry import CostEntry
from app.api.payroll_position_report_api import CODIGO_GL

router = APIRouter(tags=["provisioning"])

DIM_LABEL = {
    "REVENUE": "Ingreso",
    "PAYROLL": "Planilla",
    "OPEX": "OPEX",
    "COST": "Costos",
    "PROPERTY": "Propiedad",
}
# Qué dimensiones tienen sentido para un departamento. El ingreso solo aplica a
# los que facturan; los gastos de propiedad son líneas below-GOP sin depto, así
# que no se ofrecen en la fila de un departamento.
DIMS_DEPT = ["REVENUE", "PAYROLL", "OPEX", "COST"]


# ── El paquete: se provisiona por departamento MADRE ──────────────────────────
# Owner, 2026-08-15: «los departamentos que se provisionan son los departamentos
# madres, y cuando escogés una madre automáticamente adoptás todo el paquete».
#
# Antes esta matriz listaba los 39 departamentos en fila plana, hijos al mismo
# nivel que las madres y con cuatro casillas independientes cada uno. Se podía
# prender Housekeeping y apagar Front Desk siendo los dos la misma Habitaciones,
# y nada avisaba. La información del parentesco ya estaba en la pantalla —cada
# fila decía «hijo de 0110»—; lo que faltaba era que la ESTRUCTURA la usara.
#
# ⚠️ «Paquete» significa dos cosas distintas en dos lugares, y las dos valen:
#
#   | | qué agrupa | quién manda | cuántos |
#   |---|---|---|---|
#   | Provisionamiento (visibilidad) | madre + hijos + sets | `parent_dept_code` | 16 hijos |
#   | Motor del P&L (cálculo)        | madre + hijos, SIN sets | `room_set` | 14 |
#
# Acá se usa `parent_dept_code` **a secas**: `0115` Villas y `0116` Residencias
# son sets de producto —no hijos funcionales— pero para PROVISIONAR van dentro
# del paquete de `0110` («la estructura 0110 conlleva implícito 0115 y 0116 como
# estructura primaria»). En el CÁLCULO la bandera `room_set` sigue mandando y los
# sets conservan su checkbook de gasto propio: por eso este módulo NO reusa
# `pl_engine._cadena_de_padres` ni `audit_api.es_hijo_funcional`, que contestan
# la otra pregunta. Sacar los sets del cálculo por error ya costó una corrección.

def _cadena_de_padres(dept_code: str, padre_de: dict[str, str]) -> list[str]:
    """Padres de un departamento, del más cercano al más lejano.

    La cadena SUBE recursiva —`0132 → 0130 → 0140`—, así que el paquete no se
    arma con un salto: si se mirara solo el padre inmediato, la planilla del Spa
    quedaría colgando de `0130`, que a su vez es hijo, y `0140` mostraría un
    paquete incompleto. Corta ante un ciclo: un padre mal capturado no puede
    colgar la pantalla.
    """
    salida: list[str] = []
    actual = (dept_code or "").strip()
    vistos = {actual}
    while True:
        padre = (padre_de.get(actual) or "").strip()
        if not padre or padre in vistos:
            return salida
        salida.append(padre)
        vistos.add(padre)
        actual = padre


def _madre_de(dept_code: str, padre_de: dict[str, str]) -> str:
    """La raíz del árbol: la madre que se provisiona. Una madre es su propia
    madre (no tiene `parent_dept_code`).

    Solo cuentan los ancestros que EXISTEN en el catálogo: un padre apuntado a
    un código que ya no está dejaría al hijo colgando de una fila que nadie
    pinta, y desaparecería de la pantalla sin dar error. Ante la duda, el hijo
    se muestra como su propia madre — de más, nunca de menos.
    """
    cadena = [p for p in _cadena_de_padres(dept_code, padre_de) if p in padre_de]
    return cadena[-1] if cadena else (dept_code or "").strip()


def _paquetes(catalogo) -> tuple[dict[str, str], dict[str, list[str]]]:
    """`(madre_de_cada_uno, {madre: [miembros]})`, en el orden del catálogo.

    La madre va primero en su propio paquete: es la que lleva el interruptor.
    """
    padre_de = {
        (d.dept_code or "").strip(): (d.parent_dept_code or "").strip()
        for d in catalogo
    }
    madre_de = {c: _madre_de(c, padre_de) for c in padre_de}
    paquete: dict[str, list[str]] = {c: [c] for c, m in madre_de.items() if m == c}
    for d in catalogo:
        c = (d.dept_code or "").strip()
        if madre_de[c] != c:
            paquete[madre_de[c]].append(c)
    return madre_de, paquete


async def _conteos(db: AsyncSession, hotel_id: str) -> dict[str, dict[str, int]]:
    """Cuántos datos hay detrás de cada (departamento, dimensión), en TODOS los
    escenarios de la propiedad.

    Es lo que convierte «apagá lo que no uses» en una decisión informada: sin
    esto, el owner apaga un departamento creyendo que está vacío y lo que hace
    es esconder de la pantalla plata que sigue en el P&L.
    """
    escenarios = [s.id for s in (await db.execute(
        select(Scenario).where(Scenario.hotel_id == hotel_id))).scalars()]
    out: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(DIMS_DEPT, 0))
    if not escenarios:
        return out

    for Model, dim in ((PayrollPosition, "PAYROLL"), (OpexEntry, "OPEX"),
                       (CostEntry, "COST")):
        q = (select(Model.dept_code, func.count())
             .where(Model.scenario_id.in_(escenarios))
             .group_by(Model.dept_code))
        if Model is PayrollPosition:
            # Las filas sintéticas «(Actual GL)» —una por departamento y por
            # escenario de actuales— NO son personas: traen el costo del GL.
            # Contarlas hacía ver planilla en departamentos que solo llevan
            # gasto: Rooms, A&B y Spa aparecían con 5 «posiciones» que eran
            # cinco escenarios del mismo marcador, y la pantalla contradecía la
            # estructura real (la madre lleva OPEX, los hijos llevan planilla).
            q = q.where(Model.position_code != CODIGO_GL)
        for dept, n in (await db.execute(q)).all():
            out[(dept or "").strip()][dim] = int(n)
    return out


@router.get("/provisioning/hotels/")
async def propiedades(db: AsyncSession = Depends(get_db)):
    """Las propiedades del grupo, con cuántos departamentos tiene apagados cada
    una. Hoy solo existe CWL; la pantalla ya funciona igual el día que se creen
    Amarena, Oxígen y Ojochal."""
    hoteles = (await db.execute(select(Hotel).order_by(Hotel.id))).scalars().all()
    apagados: dict[str, int] = defaultdict(int)
    for r in (await db.execute(select(DeptEnablement).where(
            DeptEnablement.enabled.is_(False)))).scalars():
        apagados[r.hotel_id] += 1
    return {"hotels": [{"id": h.id, "name": h.name, "short_name": h.short_name,
                        "apagados": apagados.get(h.id, 0),
                        "default_locale": getattr(h, "default_locale", DEFAULT_LOCALE)}
                       for h in hoteles]}


# ── Nombre visible de la propiedad ────────────────────────────────────────────
# Lo que la app muestra donde hoy decía «Corcovado»: el encabezado del dashboard,
# los títulos de reporte y los nombres de archivo exportado.
#
# **El `id` NO se edita, y no es un olvido.** El código del hotel es la llave con
# la que están amarrados escenarios, tipos de habitación, planilla y todo el
# dato. Cambiarlo desde una pantalla dejaría huérfano el histórico entero sin
# ningún aviso. El `id` se fija UNA vez, al provisionar, por variable de entorno
# (`HOTEL_ID`); el nombre se cambia acá cuantas veces se quiera.

class IdentidadBody(BaseModel):
    name: str
    short_name: str


@router.get("/provisioning/{hotel_id}/identidad/")
async def leer_identidad(hotel_id: str, db: AsyncSession = Depends(get_db)):
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")
    return {"id": hotel.id, "name": hotel.name, "short_name": hotel.short_name}


@router.patch("/provisioning/{hotel_id}/identidad/")
async def cambiar_identidad(
    hotel_id: str, body: IdentidadBody,
    _admin=Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """Solo admin. Cambia el nombre visible; el código del hotel no se toca."""
    nombre = (body.name or "").strip()
    corto = (body.short_name or "").strip()
    if not nombre:
        raise ErrorApi(422, "propiedad.nombre_vacio")
    if not corto:
        # Sin nombre corto se cae al código, que siempre identifica bien la
        # propiedad — más vale eso que un encabezado en blanco.
        corto = hotel_id
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")
    hotel.name = nombre
    hotel.short_name = corto
    await db.commit()
    return {"id": hotel.id, "name": hotel.name, "short_name": hotel.short_name}


# ── Cambiar el CÓDIGO de la propiedad ─────────────────────────────────────────
# El código es la llave con la que están amarrados escenarios, planilla, tarifas
# y todo el resto: 26 tablas lo llevan. Por eso cambiarlo NO es un update de una
# fila — es una migración, y se hace en una transacción o no se hace.
#
# Se recorre `information_schema` en vez de una lista escrita a mano: una tabla
# nueva con `hotel_id` que alguien agregue mañana entra sola. Una lista fija se
# quedaría corta en silencio y dejaría dato huérfano, que es exactamente lo que
# esto viene a evitar.

CODIGO_VALIDO = re.compile(r"^[A-Z0-9]{2,10}$")


class CodigoBody(BaseModel):
    codigo: str


@router.patch("/provisioning/{hotel_id}/codigo/")
async def cambiar_codigo(
    hotel_id: str, body: CodigoBody,
    _admin=Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """Solo admin. Renombra el código y ARRASTRA todo el dato con él."""
    nuevo = (body.codigo or "").strip().upper()
    if not CODIGO_VALIDO.match(nuevo):
        raise ErrorApi(422, "propiedad.codigo_invalido")
    if nuevo == hotel_id:
        return {"id": hotel_id, "migradas": {}, "sin_cambios": True}

    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")
    if await db.get(Hotel, nuevo):
        raise ErrorApi(409, "propiedad.codigo_ya_existe", codigo=nuevo)

    # Las tablas que llevan hotel_id, preguntadas al esquema.
    tablas = (await db.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name = 'hotel_id' AND table_schema = 'public' "
        "ORDER BY table_name"))).scalars().all()

    # 1) La fila nueva primero: las llaves foráneas apuntan a `hotels.id`, así
    #    que el padre tiene que existir antes de mover a los hijos. Se copia la
    #    fila entera cambiando solo el id — las columnas salen del esquema para
    #    no tener que enumerarlas acá y que una columna nueva se pierda callada.
    columnas = (await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'hotels' AND table_schema = 'public' "
        "ORDER BY ordinal_position"))).scalars().all()
    destino = ", ".join(f'"{c}"' for c in columnas)
    origen = ", ".join(":nuevo" if c == "id" else f'"{c}"' for c in columnas)
    await db.execute(text(
        f"INSERT INTO hotels ({destino}) SELECT {origen} FROM hotels WHERE id = :viejo"
    ).bindparams(nuevo=nuevo, viejo=hotel_id))

    # 2) Todo el dato se muda.
    migradas: dict[str, int] = {}
    for t in tablas:
        r = await db.execute(text(
            f'UPDATE "{t}" SET hotel_id = :nuevo WHERE hotel_id = :viejo'
        ).bindparams(nuevo=nuevo, viejo=hotel_id))
        if r.rowcount:
            migradas[t] = r.rowcount

    # 3) Y recién ahí se va la fila vieja, ya sin hijos colgando.
    await db.execute(text("DELETE FROM hotels WHERE id = :viejo").bindparams(viejo=hotel_id))
    await db.commit()
    return {"id": nuevo, "anterior": hotel_id, "migradas": migradas,
            "filas": sum(migradas.values())}


# ── Idioma de la propiedad (decisión D1) ──────────────────────────────────────
# Se fija ACÁ, al provisionar: es el idioma con el que abre la app para
# cualquiera que entre a este hotel. Cada usuario puede pisarlo después con el
# botón del header, y eso se guarda en `users.locale`. Ver `app/i18n.py`, que es
# el único lugar donde se decide cuál gana.

class LocaleBody(BaseModel):
    locale: str


@router.get("/provisioning/{hotel_id}/locale/")
async def leer_idioma(hotel_id: str, db: AsyncSession = Depends(get_db)):
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")
    return {"hotel_id": hotel.id,
            "default_locale": getattr(hotel, "default_locale", DEFAULT_LOCALE),
            "opciones": list(LOCALES)}


@router.patch("/provisioning/{hotel_id}/locale/")
async def cambiar_idioma(
    hotel_id: str, body: LocaleBody,
    _admin=Depends(get_current_admin), db: AsyncSession = Depends(get_db),
):
    """Solo admin: mueve el default de la propiedad.

    A quien tenga preferencia propia guardada NO le cambia nada — para eso
    `users.locale` es nullable (`NULL` = «usá el del hotel»).
    """
    nuevo = normalize_locale(body.locale)
    if nuevo is None:
        raise ErrorApi(422, "propiedad.locale_invalido", opciones=LOCALES)
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")
    hotel.default_locale = nuevo
    await db.commit()
    return {"hotel_id": hotel.id, "default_locale": nuevo}


def _aplica(dept, dim: str) -> bool:
    """El ingreso solo se ofrece donde el departamento factura: prender
    «Ingreso» en Mantenimiento no querría decir nada."""
    return dim != "REVENUE" or bool(dept.is_revenue_dept)


def _filas_por_madre(
    catalogo, apagados: set[tuple[str, str]], conteos: dict[str, dict[str, int]],
) -> tuple[list[dict], int]:
    """Las filas de la matriz —una por madre— y cuántas casillas salen mixtas.

    Es una función PURA a propósito, separada de la consulta: así una prueba
    puede pasarle el catálogo real y el estado apagado real y comprobar casilla
    por casilla que lo que hay guardado se sigue mostrando igual. Con esto
    adentro del endpoint solo se podría verificar leyendo el código.
    """
    madre_de, paquete = _paquetes(catalogo)
    por_codigo = {(d.dept_code or "").strip(): d for d in catalogo}

    filas: list[dict] = []
    mixtos = 0
    for d in catalogo:
        codigo = (d.dept_code or "").strip()
        if madre_de.get(codigo) != codigo:
            continue                                  # es hijo: va en el paquete
        miembros = [por_codigo[c] for c in paquete[codigo]]

        dims = {}
        for dim in DIMS_DEPT:
            aplicables = [m for m in miembros if _aplica(m, dim)]
            off = [m.dept_code for m in aplicables
                   if (m.dept_code, dim) in apagados]
            mixto = 0 < len(off) < len(aplicables)
            if mixto:
                mixtos += 1
            dims[dim] = {
                "enabled": not off,
                "aplica": bool(aplicables),
                "datos": sum(int(conteos.get(m.dept_code, {}).get(dim, 0))
                             for m in miembros),
                # Quién del paquete está apagado. Con una madre sola es ella
                # misma; con hijos es lo que explica un estado mixto.
                "apagados": off,
                "mixto": mixto,
                "miembros": len(aplicables),
            }
        filas.append({
            "dept_code": codigo,
            "dept_name": d.dept_name,
            "name_en": d.name_en,
            "pl_kind": d.pl_kind,
            "pl_group": d.default_pl_group,
            # Siempre vacío: las filas de esta matriz son madres. Se deja la
            # llave para no romper a quien la lea.
            "parent_dept_code": "",
            "is_revenue_dept": bool(d.is_revenue_dept),
            "is_allocation_source": bool(d.is_allocation_source),
            "room_set": bool(getattr(d, "room_set", False)),
            "paquete": [{
                "dept_code": m.dept_code,
                "dept_name": m.dept_name,
                "room_set": bool(getattr(m, "room_set", False)),
                "es_madre": m.dept_code == codigo,
            } for m in miembros],
            "dims": dims,
            "datos_totales": sum(
                int(v) for m in miembros
                for v in conteos.get(m.dept_code, {}).values()),
        })
    return filas, mixtos


@router.get("/provisioning/{hotel_id}/departments/")
async def matriz_departamentos(hotel_id: str, db: AsyncSession = Depends(get_db)):
    """Una fila por departamento MADRE, con su paquete adentro.

    El catálogo tiene 39 departamentos y 16 de ellos cuelgan de otro, así que
    esta matriz tiene 23 filas. Cada una lleva el paquete completo —madre, hijos
    funcionales y sets de producto— y las cuatro casillas hablan por el paquete
    entero: los datos se suman, y apagar arrastra a todos.

    **El estado mixto se REPORTA, no se resuelve.** Si la madre está apagada y
    sus hijos prendidos —o al revés—, la casilla sale `mixto` con el detalle de
    quién está apagado, y no se toca nada. Es una decisión que ya tomó alguien y
    que la regla nueva no puede representar; normalizarla acá cambiaría la
    visibilidad de departamentos sin que nadie lo pidiera.
    """
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")

    catalogo = (await db.execute(
        select(DepartmentCatalog).order_by(
            DepartmentCatalog.display_order, DepartmentCatalog.dept_code))).scalars().all()

    apagados: set[tuple[str, str]] = {
        (r.scope_key, r.dimension)
        for r in (await db.execute(select(DeptEnablement).where(
            DeptEnablement.hotel_id == hotel_id,
            DeptEnablement.scope_kind == "DEPT"))).scalars()
        if not r.enabled
    }
    conteos = await _conteos(db, hotel_id)

    filas, mixtos = _filas_por_madre(catalogo, apagados, conteos)

    return {
        "hotel_id": hotel_id,
        "hotel_name": hotel.name,
        "dimensiones": [{"key": k, "label": DIM_LABEL[k]} for k in DIMS_DEPT],
        "rows": filas,
        "apagados": len(apagados),
        "total_departamentos": len(catalogo),
        "total_madres": len(filas),
        "mixtos": mixtos,
    }


class ToggleRow(BaseModel):
    # `dept_code` es SIEMPRE una madre: el endpoint lo abre en todo el paquete.
    # Mandar un hijo devuelve 422 con el código de la madre que corresponde.
    dept_code: str
    dimension: str
    enabled: bool
    notes: str = ""


class ToggleBody(BaseModel):
    rows: list[ToggleRow]
    force: bool = False          # apagar aunque haya datos cargados
    updated_by: str = ""


def _expandir_al_paquete(rows, catalogo) -> dict[tuple[str, str], "ToggleRow"]:
    """`{(dept_code, dimensión): decisión}` — cada casilla que llega, abierta en
    todas las filas de su paquete.

    Un hijo suelto se RECHAZA en vez de tratarse como su madre: quien lo mandó
    quería tocar un solo departamento, y eso es exactamente lo que esta regla
    elimina. Tratarlo en silencio como la madre haría lo contrario de lo pedido
    y encima sin avisar.

    Pura y afuera del endpoint para que una prueba pueda comprobar el arrastre
    sin base de datos.
    """
    madre_de, paquete = _paquetes(catalogo)
    por_codigo = {(d.dept_code or "").strip(): d for d in catalogo}

    objetivo: dict[tuple[str, str], ToggleRow] = {}
    for r in rows:
        codigo = (r.dept_code or "").strip()
        madre = madre_de.get(codigo)
        if madre is not None and madre != codigo:
            raise ErrorApi(422, "provisionamiento.hijo_suelto",
                           departamento=codigo, madre=madre)
        for m in paquete.get(codigo, [codigo]):
            dept = por_codigo.get(m)
            # No se escribe donde la dimensión no aplica: una fila «REVENUE
            # apagado» en Villas diría que alguien lo decidió, cuando Villas no
            # lleva ingreso.
            if dept is not None and not _aplica(dept, r.dimension):
                continue
            objetivo[(m, r.dimension)] = r
    return objetivo


@router.put("/provisioning/{hotel_id}/departments/")
async def guardar_matriz(
    hotel_id: str, body: ToggleBody, db: AsyncSession = Depends(get_db),
):
    """Guarda solo los DELTAS, y siempre por PAQUETE.

    Se recibe la madre y se escribe sobre ella y sobre todos los que cuelgan de
    ella —hijos funcionales y sets—: «cuando escogés una madre automáticamente
    adoptás todo el paquete» (owner). La expansión vive acá y no en la pantalla
    a propósito: si la hiciera el navegador, cualquier otro cliente podría dejar
    un hijo prendido con su madre apagada, que es justo lo que esto viene a
    cerrar.

    Prender borra la fila (vuelve al default) en vez de escribir `enabled=true`:
    así la tabla solo contiene lo que de verdad se apagó y una propiedad nueva
    sigue arrancando completa.
    """
    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")

    for r in body.rows:
        if r.dimension not in DIMENSIONES:
            raise ErrorApi(422, "provisionamiento.dimension_desconocida",
                           dimension=r.dimension)

    catalogo = (await db.execute(
        select(DepartmentCatalog).order_by(
            DepartmentCatalog.display_order, DepartmentCatalog.dept_code))).scalars().all()
    objetivo = _expandir_al_paquete(body.rows, catalogo)

    conteos = await _conteos(db, hotel_id)
    con_datos = [
        (dept, dim, conteos.get(dept, {}).get(dim, 0))
        for (dept, dim), r in objetivo.items()
        if not r.enabled and conteos.get(dept, {}).get(dim, 0)
    ]
    if con_datos and not body.force:
        detalle = ", ".join(
            f"{d} en {DIM_LABEL.get(dim, dim)} ({n} líneas)" for d, dim, n in con_datos[:6])
        if len(con_datos) > 6:
            detalle += "…"
        raise ErrorApi(409, "provisionamiento.datos_cargados", detalle=detalle)

    existentes = {
        (r.scope_key, r.dimension): r
        for r in (await db.execute(select(DeptEnablement).where(
            DeptEnablement.hotel_id == hotel_id,
            DeptEnablement.scope_kind == "DEPT"))).scalars()
    }

    apagados = prendidos = 0
    for (dept_code, dimension), r in objetivo.items():
        fila = existentes.get((dept_code, dimension))
        if r.enabled:
            if fila is not None:
                await db.delete(fila)        # vuelve al default (prendido)
                prendidos += 1
            continue
        if fila is None:
            fila = DeptEnablement(
                hotel_id=hotel_id, scope_kind="DEPT",
                scope_key=dept_code, dimension=dimension)
            db.add(fila)
        fila.enabled = False
        fila.notes = r.notes
        fila.updated_by = body.updated_by
        apagados += 1

    await db.commit()
    return {"ok": True, "apagados": apagados, "prendidos": prendidos,
            # Cuántas casillas se tocaron de verdad: se recibieron N madres y se
            # escribieron sobre todo el paquete. La pantalla lo dice para que
            # «apagué una» y «se apagaron seis» no sea una sorpresa.
            "casillas": len(objetivo), "recibidas": len(body.rows),
            "con_datos": [{"dept_code": d, "dimension": dim, "lineas": n}
                          for d, dim, n in con_datos]}


@router.post("/provisioning/{hotel_id}/copiar-de/{origen_id}/")
async def copiar_de(
    hotel_id: str, origen_id: str, db: AsyncSession = Depends(get_db),
):
    """Clona la matriz de otra propiedad como punto de partida.

    Provisionar el segundo hotel del grupo es casi siempre «como el primero,
    menos estas tres cosas». Arrancar de cero obliga a repasar 40 departamentos
    para volver a decidir lo mismo.
    """
    for hid in (hotel_id, origen_id):
        if await db.get(Hotel, hid) is None:
            raise ErrorApi(404, "propiedad.no_encontrada_id", propiedad=hid)
    if hotel_id == origen_id:
        raise ErrorApi(422, "provisionamiento.origen_igual_destino")

    origen = (await db.execute(select(DeptEnablement).where(
        DeptEnablement.hotel_id == origen_id))).scalars().all()
    actuales = (await db.execute(select(DeptEnablement).where(
        DeptEnablement.hotel_id == hotel_id))).scalars().all()
    for r in actuales:
        await db.delete(r)
    await db.flush()

    for r in origen:
        db.add(DeptEnablement(
            hotel_id=hotel_id, scope_kind=r.scope_kind, scope_key=r.scope_key,
            dimension=r.dimension, enabled=r.enabled,
            notes=f"copiado de {origen_id}"))
    await db.commit()
    return {"ok": True, "copiadas": len(origen), "reemplazadas": len(actuales)}


async def depts_habilitados(
    db: AsyncSession, hotel_id: str, dimension: str,
) -> set[str] | None:
    """Los departamentos APAGADOS de una propiedad en una dimensión.

    Devuelve el conjunto a esconder, o `None` si no hay nada apagado — que es el
    caso normal y le permite a quien llama saltarse el filtro por completo.

    Vive acá y no copiado en cada selector: si la regla de resolución se
    duplica, una copia se queda atrás y dos pantallas muestran departamentos
    distintos para la misma propiedad.
    """
    filas = (await db.execute(select(DeptEnablement).where(
        DeptEnablement.hotel_id == hotel_id,
        DeptEnablement.scope_kind == "DEPT",
        DeptEnablement.dimension == dimension,
        DeptEnablement.enabled.is_(False)))).scalars().all()
    return {r.scope_key for r in filas} or None


# ─── Qué tabs y reportes ve esta propiedad ───────────────────────────────────
#
# Owner, 2026-08-20: «así como los departamentos se van a limitar, así se van a
# limitar los reportes y los tabs principales» · «todo debe poderse esconder y
# habilitar».
#
# ⚠️ **El catálogo de lo que existe NO está acá.** Vive en la barra
# (`components/TopNav.tsx`), que ya es la lista de lo que hay: copiarla al
# backend sería una segunda lista que habría que acordarse de actualizar, y este
# proyecto ya pagó dos veces por una escrita a mano (el Club Madresal, y siete
# líneas de ingreso en Master Data). Acá se guarda **sólo lo apagado**.
#
# ⚠️ **Esto esconde de la barra; NO es un permiso.** La ruta sigue respondiendo:
# quien escriba la URL entra igual. Es navegación, no seguridad — y es
# justamente lo que hace seguro poder apagarlo TODO, incluida esta pantalla:
# aunque se esconda, se vuelve entrando a su URL.


class TabFila(BaseModel):
    scope_kind: str          # TAB | ITEM
    clave: str
    visible: bool


class TabsBody(BaseModel):
    rows: list[TabFila]


@router.get("/provisioning/{hotel_id}/tabs/")
async def leer_tabs(hotel_id: str, db: AsyncSession = Depends(get_db)):
    """Qué está apagado. **Vacío significa que se ve todo**, no que no hay nada."""
    from app.api._apagados import tabs_apagados

    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")

    apagados = await tabs_apagados(db, hotel_id)
    return {
        "hotel_id": hotel_id,
        "apagados": apagados,
        "total_apagados": sum(len(v) for v in apagados.values()),
        "nota": ("Esconde de la barra; no es un permiso. La ruta sigue "
                 "respondiendo si se entra por la URL."),
    }


@router.put("/provisioning/{hotel_id}/tabs/")
async def guardar_tabs(hotel_id: str, body: TabsBody,
                       db: AsyncSession = Depends(get_db)):
    """Guarda sólo los DELTAS.

    ⚠️ **Prender BORRA la fila** en vez de escribir `visible=true`: así la tabla
    contiene sólo lo que de verdad se apagó, y una propiedad nueva —o una que se
    resetee— sigue viendo todo sin depender de que alguien haya escrito 96
    filas.
    """
    from app.models.tab_enablement import (SCOPE_KINDS as SCOPES_TAB,
                                           TabEnablement)

    hotel = await db.get(Hotel, hotel_id)
    if hotel is None:
        raise ErrorApi(404, "propiedad.no_encontrada")

    for r in body.rows:
        if r.scope_kind not in SCOPES_TAB:
            raise ErrorApi(422, "provisionamiento.scope_desconocido",
                           scope=r.scope_kind)

    existentes = {
        (r.scope_kind, r.clave): r
        for r in (await db.execute(select(TabEnablement).where(
            TabEnablement.hotel_id == hotel_id))).scalars().all()
    }

    apagados = prendidos = 0
    for r in body.rows:
        fila = existentes.get((r.scope_kind, r.clave))
        if r.visible:
            if fila is not None:
                await db.delete(fila)
                prendidos += 1
        elif fila is None:
            db.add(TabEnablement(hotel_id=hotel_id, scope_kind=r.scope_kind,
                                 clave=r.clave[:60], visible=False))
            apagados += 1

    await db.commit()
    from app.api._apagados import tabs_apagados

    return {"apagados": apagados, "prendidos": prendidos,
            "estado": await tabs_apagados(db, hotel_id)}
