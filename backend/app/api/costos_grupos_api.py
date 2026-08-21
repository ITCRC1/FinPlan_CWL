# -*- coding: utf-8 -*-
"""Costos para Negociación de Grupos — el tarifario rack y el descuento máximo.

**Qué contesta esta pantalla.** No «cuánto cuesta» ni «cuánto cobramos», sino
la resta: *hasta acá podés bajar del rack antes de tocar el piso*. Regla del
owner (2026-08-19): los grupos se negocian DESDE la tarifa rack.

⚠️ **Editar el rack no mueve ningún P&L, y es a propósito.** El tarifario vive
en `cfg_tarifa_rack`, no en los `rate_cards` del escenario. Si viviera ahí,
editarlo movería el ingreso, el ingreso movería el costo unitario y el piso se
movería solo — exactamente lo que la validación 6 existe para atrapar. Acá el
precio es sólo el techo.

⚠️ **Los costos y las tarifas salen de escenarios distintos, a propósito.** Los
costos vienen del Forecast Working 2026 («la realidad», decisión del owner) y
las tarifas arrancan copiadas del Budget Working 2027, que es el único
escenario con tarifario. Las dos cosas viven en parámetros separados.
"""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth import get_current_user
from app.db import get_db
from app.engine import costos_grupos as cg
from app.hotel_actual import HOTEL_ID
from app.models.costos_grupos import CfgEscalon, CfgTarifaRack
from app.models.room_type_config import RoomTypeConfig
from app.models.scenario import Scenario

router = APIRouter(prefix="/costos-grupos", tags=["costos-grupos"])


class FilaRack(BaseModel):
    room_type_code: str
    mes: int
    rack: str
    neto: str
    pax: str


class GuardarRack(BaseModel):
    filas: list[FilaRack]


async def _escenario(db, clave: str) -> Scenario | None:
    """`TIPO/AÑO/VERSION` → el escenario. Devuelve None si no existe."""
    try:
        tipo, anio, version = clave.split("/")
    except ValueError:
        return None
    return (await db.execute(
        select(Scenario).where(Scenario.type == tipo, Scenario.year == int(anio),
                               Scenario.version == version)
    )).scalars().first()


@router.get("/tarifario/")
async def leer_tarifario(db=Depends(get_db), _=Depends(get_current_user)):
    """Las 96 celdas editables + el nombre de cada categoría.

    Devuelve también las categorías SIN tarifa, con el rack en cero: una
    categoría que falta se ve; una que no aparece, no.
    """
    tipos = sorted(
        (await db.execute(
            select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID)
        )).scalars().all(),
        key=lambda r: r.sort_order,
    )
    filas = {
        (f.room_type_code, f.mes): f for f in (await db.execute(
            select(CfgTarifaRack).where(CfgTarifaRack.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    fuera = []
    for t in tipos:
        fuera.append({
            "room_type_code": t.code,
            "nombre": t.short_name,
            "orden": t.sort_order,
            "unidades": t.units,
            "meses": [
                {
                    "mes": m,
                    "rack": str(filas[(t.code, m)].rack) if (t.code, m) in filas else "0",
                    "neto": str(filas[(t.code, m)].neto) if (t.code, m) in filas else "0",
                    "pax": str(filas[(t.code, m)].pax) if (t.code, m) in filas else "0",
                }
                for m in range(1, 13)
            ],
        })
    return {"categorias": fuera}


@router.put("/tarifario/")
async def guardar_tarifario(cuerpo: GuardarRack, db=Depends(get_db),
                            _=Depends(get_current_user)):
    """Guarda sólo lo que llega. Lo que no venga, no se toca."""
    codigos = {
        r.code for r in (await db.execute(
            select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    existentes = {
        (f.room_type_code, f.mes): f for f in (await db.execute(
            select(CfgTarifaRack).where(CfgTarifaRack.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    guardadas = 0
    for f in cuerpo.filas:
        if f.room_type_code not in codigos:
            # ⚠️ Un código que no existe se RECHAZA, no se guarda callado: una
            # fila huérfana no se vería en ninguna pantalla y el owner creería
            # haber editado algo.
            raise HTTPException(
                400, f"categoría desconocida: {f.room_type_code}")
        if not 1 <= f.mes <= 12:
            raise HTTPException(400, f"mes fuera de rango: {f.mes}")
        try:
            rack, neto, pax = Decimal(f.rack), Decimal(f.neto), Decimal(f.pax)
        except (InvalidOperation, ValueError):
            raise HTTPException(
                400, f"número inválido en {f.room_type_code}/{f.mes}")
        if rack < 0 or neto < 0 or pax < 0:
            raise HTTPException(
                400, f"valor negativo en {f.room_type_code}/{f.mes}")

        fila = existentes.get((f.room_type_code, f.mes))
        if fila is None:
            fila = CfgTarifaRack(hotel_id=HOTEL_ID,
                                 room_type_code=f.room_type_code, mes=f.mes)
            db.add(fila)
        fila.rack, fila.neto, fila.pax = rack, neto, pax
        guardadas += 1

    await db.commit()
    return {"guardadas": guardadas}


@router.get("/descuentos/")
async def tabla_de_descuentos(db=Depends(get_db),
                              _=Depends(get_current_user)):
    """`descuento_max = 1 − piso / rack`, por categoría y por MES.

    ⚠️ Va por mes y no por temporada porque el rack BAJA en temporada baja
    justo cuando el piso sube: en setiembre Agujas vale $400 contra un piso de
    $1.012,56. Un promedio por temporada taparía el mes que duele.
    """
    par = await cg.cargar_parametros(db, HOTEL_ID)
    comp = await cg.cargar_composicion(db, HOTEL_ID)

    sc = await _escenario(db, par.get("escenario_base", ""))
    if sc is None:
        raise HTTPException(
            409, f"el escenario base no existe: {par.get('escenario_base')}")

    meses = await cg.hechos_mensuales(db, sc, HOTEL_ID)
    por_temporada: dict[str, list] = {}
    for m in meses:
        if m.temporada:
            por_temporada.setdefault(m.temporada, []).append(m)

    # La comisión sale del propio tarifario. ⚠️ NO de `compute_net_factor`,
    # que hasta el 2026-08-20 devolvía 9,5640 (sumaba los doce meses sin
    # dividir). Ese defecto YA ESTÁ ARREGLADO; el módulo sigue leyéndolo del
    # tarifario porque es el precio contra el que se negocia, no un promedio.
    de_enero = await cg.tarifas_rack(db, HOTEL_ID, 1)
    factor = cg.factor_neto_del_rack(de_enero)
    comision = (Decimal("1") - factor) if factor is not None else Decimal("0")

    pisos_por_temporada = {
        t: cg.pisos_habitacion(ms, comp, par, comision,
                               par.get("metodo_absorcion", "M2"), meses)
        for t, ms in por_temporada.items()
    }

    filas = []
    marginal_estimado = False
    for m in meses:
        p = pisos_por_temporada.get(m.temporada)
        if p is None:
            continue
        marginal_estimado = marginal_estimado or p.marginal_estimado
        racks = await cg.tarifas_rack(db, HOTEL_ID, m.mes)
        for d in cg.descuentos(racks, p.con_margen):
            filas.append({
                "mes": m.mes, "temporada": m.temporada,
                "cerrado": m.dias_abiertos == 0,
                "categoria": d.nombre, "orden": d.orden,
                "rack": str(d.rack), "piso": str(d.piso),
                "descuento_max": str(d.descuento_max),
                "alcanza": d.alcanza,
            })

    return {
        "escenario_costos": par.get("escenario_base"),
        "comision": str(comision),
        "factor_neto": str(factor) if factor is not None else None,
        # ⚠️ Que la pantalla TIENE que mostrar: un Piso 1 estimado parece
        # medido y no lo está.
        "marginal_estimado": marginal_estimado,
        "pisos": {
            t: {
                "marginal": str(p.marginal),
                "departamental": str(p.departamental),
                "integral": str(p.integral),
                "con_margen": str(p.con_margen),
                "costo_propio": str(p.costo_propio),
                "overhead_unitario": str(p.overhead_unitario),
                "meses": sorted(x.mes for x in por_temporada[t]),
                # ⚠️ La pantalla TIENE que mostrar esto: la temporada BAJA se
                # apoya en UN mes con 82 habitaciones ocupadas. El piso es
                # correcto y es frágil, y las dos cosas importan.
                "meses_con_ocupacion": sorted(
                    x.mes for x in por_temporada[t] if x.hab_ocupadas > 0),
            }
            for t, p in pisos_por_temporada.items()
        },
        "filas": filas,
    }


# ── Los escalones (§4.4) — la puerta que faltaba ─────────────────────────────
#
# ⚠️ **La tabla existe, el motor la lee y NADIE la podía llenar.** Sin escalones
# cargados, `escalones_aplicables` devuelve lista vacía y el modelo **subestima
# los grupos grandes** — que son justo los que se negocian. El guía adicional,
# el vehículo que no cabe, el turno extra de cocina, el bloque de habitaciones
# que hay que abrir: nada de eso entraba al costo.
#
# ⚠️ Y la lista vacía **no es lo mismo que «no aplica»**. La respuesta lo dice
# explícito para que la pantalla no muestre un cero silencioso: un cero que
# significa «nadie lo cargó» leído como «no hay costo extra» es un piso más
# barato que la realidad, y encima con cara de medido.

# Los drivers que el motor sabe evaluar (`escalones_aplicables`). Uno fuera de
# esta lista no falla al guardar: **falla en silencio al simular**, porque el
# motor no lo encuentra y saltea la regla. Se rechaza acá.
DRIVERS = ("pax", "hab_grupo", "pax_tour")


class FilaEscalon(BaseModel):
    dept_code: str = ""
    driver: str
    umbral: str
    costo_adicional: str
    descripcion: str = ""
    activo: bool = True


def _decimal(valor: str, campo: str) -> Decimal:
    try:
        return Decimal(str(valor).replace(",", "").strip() or "0")
    except (InvalidOperation, AttributeError):
        raise HTTPException(400, f"«{valor}» no es un número en {campo}")


def _valida_escalon(f: FilaEscalon) -> tuple[Decimal, Decimal]:
    if f.driver not in DRIVERS:
        raise HTTPException(
            400, f"driver desconocido: «{f.driver}». El motor sólo sabe "
                 f"evaluar: {', '.join(DRIVERS)}")
    umbral = _decimal(f.umbral, "umbral")
    costo = _decimal(f.costo_adicional, "costo adicional")
    # ⚠️ Un umbral en cero se cruza SIEMPRE: dejaría de ser un escalón y se
    # volvería un costo fijo de todo grupo, disfrazado de excepción.
    if umbral <= 0:
        raise HTTPException(
            400, "el umbral tiene que ser mayor que cero: uno en cero lo "
                 "cruzan todos los grupos y deja de ser un escalón")
    if costo <= 0:
        raise HTTPException(400, "el costo adicional tiene que ser mayor que cero")
    return umbral, costo


def _escalon_sale(e: CfgEscalon) -> dict:
    return {"id": e.id, "dept_code": e.dept_code, "driver": e.driver,
            "umbral": str(e.umbral), "costo_adicional": str(e.costo_adicional),
            "descripcion": e.descripcion, "activo": e.activo}


@router.get("/escalones/")
async def leer_escalones(db=Depends(get_db), _=Depends(get_current_user)):
    filas = sorted((await db.execute(
        select(CfgEscalon).where(CfgEscalon.hotel_id == HOTEL_ID)
    )).scalars().all(), key=lambda e: (e.driver, float(e.umbral)))
    return {
        "escalones": [_escalon_sale(e) for e in filas],
        "drivers": list(DRIVERS),
        # ⚠️ Explícito, no deducible del largo de la lista: la pantalla tiene
        # que poder decir «nadie los cargó» en vez de mostrar un cero.
        "sin_cargar": len(filas) == 0,
    }


@router.post("/escalones/")
async def crear_escalon(f: FilaEscalon, db=Depends(get_db),
                        _=Depends(get_current_user)):
    umbral, costo = _valida_escalon(f)
    fila = CfgEscalon(hotel_id=HOTEL_ID, dept_code=f.dept_code[:10],
                      driver=f.driver, umbral=umbral, costo_adicional=costo,
                      descripcion=f.descripcion[:200], activo=f.activo)
    db.add(fila)
    await db.commit()
    return _escalon_sale(fila)


@router.put("/escalones/{escalon_id}/")
async def editar_escalon(escalon_id: str, f: FilaEscalon, db=Depends(get_db),
                         _=Depends(get_current_user)):
    umbral, costo = _valida_escalon(f)
    fila = (await db.execute(
        select(CfgEscalon).where(CfgEscalon.id == escalon_id,
                                 CfgEscalon.hotel_id == HOTEL_ID)
    )).scalars().first()
    if fila is None:
        raise HTTPException(404, "ese escalón no existe")
    fila.dept_code = f.dept_code[:10]
    fila.driver = f.driver
    fila.umbral = umbral
    fila.costo_adicional = costo
    fila.descripcion = f.descripcion[:200]
    fila.activo = f.activo
    await db.commit()
    return _escalon_sale(fila)


@router.delete("/escalones/{escalon_id}/")
async def borrar_escalon(escalon_id: str, db=Depends(get_db),
                         _=Depends(get_current_user)):
    """⚠️ Borrar un escalón **abarata los grupos grandes** desde la próxima
    simulación. Para dejar de aplicarlo sin perder la definición está
    `activo`."""
    fila = (await db.execute(
        select(CfgEscalon).where(CfgEscalon.id == escalon_id,
                                 CfgEscalon.hotel_id == HOTEL_ID)
    )).scalars().first()
    if fila is None:
        raise HTTPException(404, "ese escalón no existe")
    await db.delete(fila)
    await db.commit()
    return {"borrado": escalon_id}
