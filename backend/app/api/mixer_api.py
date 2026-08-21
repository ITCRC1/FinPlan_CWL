# -*- coding: utf-8 -*-
"""El mixer: se planifica en los 7 sub-canales y los 3 se calculan.

**Lo que pidió el owner (2026-08-14).** «Hay que hacerle para todas las
versiones, versión forecast, todas las versiones que tienen auxiliares... a
partir de enero 2027, el forecast, el budget, todo lo que se construye ahí, como
auxiliar, tiene que dar con esos parámetros.» Budget Final 2026 queda afuera:
«ya es lo que es».

**Por qué APLICAR es un botón y no un efecto.** El mixer mueve el Net Factor de
0,8220 a 0,7970, y ese factor multiplica el ingreso de habitaciones de todo el
presupuesto: son −$79.209 en Budget 2026 y −$108.280 en Budget 2027. Un cambio
de ese tamaño no puede pasar porque alguien abrió una pantalla. Acá se ve el
antes, el después y la diferencia en plata; escribir es un acto aparte.

**Lo que el mixer NO toca:** un escenario enllavado ni un ACTUAL. El primero es
una foto histórica; el segundo registra lo que pasó, y su net factor es el que
hubo, no el que se quisiera.
"""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from app.auth import get_current_user
from app.db import get_session
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.engine import mixer_canales as mixer
from app.models.canal_comercial import CanalComercial
from app.models.canal_mix_escenario import ANUAL, CanalMixEscenario
from app.models.pl_line import PLLine
from app.models.rate_card import RateCard
from app.models.sales_channel_config import SalesChannelConfig
from app.models.scenario import Scenario

router = APIRouter()

#: Las líneas del P&L que el Net Factor multiplica. Si mañana se vuelve a partir
#: el ingreso de habitaciones, esta lista es el único lugar que hay que tocar.
LINEAS_DE_HABITACIONES = ("REV_ROOMS", "REV_ROOMS_OTHER")

#: ⚠️ **El factor NO toca solo habitaciones.** El motor lo aplica también a la
#: comida, la bebida, las actividades y el transporte del paquete
#: (`revenue_calculator`: `pax x tarifa x nf`). Es el mismo concepto que el
#: motor ya llama `total_package`.
#:
#: `REV_SUSTAINABILITY` queda AFUERA a propósito: es una cuota fija por persona
#: por noche y no paga comisión. Meterla inflaría la base y con ella la comisión
#: simulada, sin que nada lo delatara.
LINEAS_COMISIONABLES = LINEAS_DE_HABITACIONES + (
    "REV_FB", "REV_FB_BEV", "REV_FB_MISC", "REV_TOURS", "REV_TRANSPORTATION")


async def _canales_base(s) -> list[CanalComercial]:
    return list((await s.execute(
        select(CanalComercial).where(CanalComercial.activo.is_(True))
        .order_by(CanalComercial.orden))).scalars())


async def _canales_comision(s):
    """Los canales de comisión activos, en orden. Es una TABLA justamente para
    que agregar un cuarto sea un INSERT y no un despliegue."""
    from app.models.canal_comision import CanalComision
    return (await s.execute(
        select(CanalComision).where(CanalComision.activo.is_(True))
        .order_by(CanalComision.orden, CanalComision.code))).scalars().all()


async def _overrides(s, scenario_id: str) -> list[CanalMixEscenario]:
    if not scenario_id:
        return []
    return list((await s.execute(select(CanalMixEscenario).where(
        CanalMixEscenario.scenario_id == scenario_id))).scalars())


async def _net_factor_de_canales(s, scenario_id: str) -> Decimal | None:
    """El Net Factor que sale del mix de canales guardado.

    `None` si no hay canales — el caso de todos los Forecast, y es un dato en sí
    mismo: están corriendo con una sugerencia que nadie fijó.
    """
    filas = list((await s.execute(select(SalesChannelConfig).where(
        SalesChannelConfig.scenario_id == scenario_id))).scalars())
    if not filas:
        return None
    # POR MES. Sumar las 36 filas daría doce veces el factor. Y puede haber un
    # solo mes cargado y que no sea enero —a Budget Final 2026 le pasa—, así que
    # se toma el primer mes que exista en vez de asumir que es el 1.
    primer_mes = min(f.month for f in filas)
    return sum((f.mix_pct * (Decimal("1") - f.commission_pct)
                for f in filas if f.month == primer_mes), Decimal("0"))


async def _net_factor_de_tarifas(s, scenario_id: str) -> Decimal | None:
    """El factor efectivo de las tarifas: `net_rate / rack_rate`.

    ⚠️ **Esto es lo que de verdad manda.** El motor de revenue prefiere este
    factor sobre el del mix de canales (ver `revenue_calculator.calculate_revenue`),
    así que en un escenario con tarifas netas cargadas —que hoy son TODOS los que
    tienen datos— cambiar el mix escribe las filas y no mueve un solo número.
    """
    from app.engine.revenue_calculator import _effective_net_factor
    rcs = list((await s.execute(select(RateCard).where(
        RateCard.scenario_id == scenario_id))).scalars())
    return _effective_net_factor(rcs)


async def _net_factor_vigente(s, scenario_id: str) -> tuple[Decimal | None, str]:
    """El que el motor va a usar, y de dónde sale. En ese orden de precedencia:
    las tarifas primero, el mix después."""
    tarifas = await _net_factor_de_tarifas(s, scenario_id)
    if tarifas:
        return tarifas, "tarifas"
    canales = await _net_factor_de_canales(s, scenario_id)
    return (canales, "mix") if canales is not None else (None, "nada")


async def _suma_de_lineas(s, scenario_id: str, lineas) -> Decimal:
    total = (await s.execute(
        select(func.coalesce(func.sum(PLLine.amount_usd), 0)).where(
            PLLine.scenario_id == scenario_id,
            PLLine.line_code.in_(lineas)))).scalar()
    return Decimal(str(total or 0))


async def _ingreso_habitaciones(s, scenario_id: str) -> Decimal:
    return await _suma_de_lineas(s, scenario_id, LINEAS_DE_HABITACIONES)


async def _bases(s, scenario_id: str) -> dict:
    """Las tres bases sobre las que se puede simular, en NETO.

    ⚠️ Salen del P&L, o sea que **ya vienen con la comisión descontada**. Para
    repartirlas por canal hay que devolverlas a **rack** dividiendo por el factor
    vigente — el mix se aplica sobre la venta bruta y la comisión se resta de
    ahí. Esa division la hace la pantalla, que es donde el owner elige la base.
    """
    total = await _suma_de_lineas(s, scenario_id, ["TOTAL_REVENUES"])
    return {
        "rooms": float(await _ingreso_habitaciones(s, scenario_id)),
        "comisionable": float(await _suma_de_lineas(s, scenario_id, LINEAS_COMISIONABLES)),
        "total": float(total),
    }


def _impacto(rooms: Decimal, nf_hoy: Decimal | None, nf_nuevo: Decimal) -> dict:
    """Cuánto se mueve el ingreso de habitaciones al cambiar el factor.

    El ingreso guardado YA viene multiplicado por el factor de hoy, así que la
    regla es `rooms x (nf_nuevo / nf_hoy - 1)` — no `rooms x delta`.
    """
    if nf_hoy is None or not nf_hoy:
        return {"rooms_usd": float(rooms or 0), "delta_usd": None, "delta_pct": None}
    factor = nf_nuevo / nf_hoy - Decimal("1")
    return {"rooms_usd": float(rooms or 0),
            "delta_usd": float((rooms or 0) * factor), "delta_pct": float(factor)}


@router.get("/canales/mixer/")
async def ver_mixer(
    scenario_id: str = Query(""), month: int = Query(ANUAL, ge=0, le=12),
    _=Depends(get_current_user),
):
    """Los 7 sub-canales resueltos, los 3 derivados y qué cambia en plata."""
    async with get_session() as s:
        base = await _canales_base(s)
        overs = await _overrides(s, scenario_id)
        resueltos = mixer.resolver(base, overs, month)
        destinos = await _canales_comision(s)
        derivados = mixer.derivar(resueltos, [d.code for d in destinos])
        nf_nuevo = mixer.net_factor(derivados)

        nf_hoy, manda = None, "nada"
        rooms = Decimal("0")
        bases = {"rooms": 0.0, "comisionable": 0.0, "total": 0.0}
        if scenario_id:
            nf_hoy, manda = await _net_factor_vigente(s, scenario_id)
            rooms = await _ingreso_habitaciones(s, scenario_id)
            bases = await _bases(s, scenario_id)

    return {
        "scenario_id": scenario_id,
        "month": month,
        "subcanales": [{
            "code": c.code, "nombre": c.nombre, "entrada": c.entrada,
            # Del DATO (`rueda_a`), no de un diccionario con default a DIRECT.
            "destino": mixer.destino_de(c),
            "eje": "entrada" if c.entrada else "atribucion",
            "mix_pct": float(c.mix_pct), "comision_pct": float(c.comision_pct),
            "origen": c.origen,
        } for c in resueltos],
        "derivados": [{
            "channel": d.channel, "mix_pct": float(d.mix_pct),
            "commission_pct": float(d.commission_pct),
        } for d in derivados],
        # La lista de destinos, para que la grilla arme el desplegable de
        # «rueda a» con lo que existe y no con tres códigos escritos a mano.
        "canales": [{"code": d.code, "nombre": d.nombre, "orden": d.orden}
                    for d in destinos],
        "mix_suma": float(mixer.suma_del_mix(resueltos)),
        "mix_cierra": mixer.mix_cierra(resueltos),
        "net_factor_nuevo": float(nf_nuevo),
        "net_factor_hoy": float(nf_hoy) if nf_hoy is not None else None,
        # De donde sale el factor que el motor usa HOY. Si dice "tarifas", el mix
        # es decorativo mientras no se regeneren las tarifas netas.
        "manda": manda,
        # En NETO: la pantalla las devuelve a rack dividiendo por `net_factor_hoy`.
        "bases": bases,
        "impacto": _impacto(rooms, nf_hoy, nf_nuevo) if scenario_id else None,
    }


class FilaMix(BaseModel):
    code: str
    month: int = ANUAL
    mix_pct: Decimal
    comision_pct: Decimal
    #: Solo lo usa `guardar_base`: cambiar a dónde rueda un sub-canal es una
    #: decisión de la BASE, no una excepción de un escenario. `None` = no tocar.
    rueda_a: str | None = None


@router.put("/canales/mixer/{scenario_id}/")
async def guardar_mixer(scenario_id: str, filas: list[FilaMix],
                        _=Depends(get_current_user)):
    """Guarda la EXCEPCIÓN de un escenario.

    Una lista vacía borra el anual y el escenario vuelve a heredar el mix base.
    """
    async with get_session() as s:
        esc = (await s.execute(select(Scenario).where(
            Scenario.id == scenario_id))).scalar_one_or_none()
        if esc is None:
            raise ErrorApi(404, "escenario.no_encontrado")
        if esc.is_locked:
            raise ErrorApi(409, "escenario.enllavado",
                           escenario=f"{esc.type} {esc.version} {esc.year}")

        # Se reemplaza SOLO lo de los meses que vienen: guardar el anual no puede
        # borrar en silencio una excepción de marzo que alguien puso aparte.
        meses = {f.month for f in filas} or {ANUAL}
        await s.execute(delete(CanalMixEscenario).where(
            CanalMixEscenario.scenario_id == scenario_id,
            CanalMixEscenario.month.in_(meses)))
        for f in filas:
            s.add(CanalMixEscenario(
                id=str(uuid.uuid4()), scenario_id=scenario_id, code=f.code[:30],
                month=f.month, mix_pct=f.mix_pct, comision_pct=f.comision_pct))
        await s.commit()
    return {"guardadas": len(filas), "scenario_id": scenario_id}


@router.put("/canales/base/")
async def guardar_base(filas: list[FilaMix], _=Depends(get_current_user)):
    """Guarda el mix BASE — el que aplica a todo lo que no tiene excepción.

    Es lo que hace que un escenario NUEVO nazca con estos parámetros, así que es
    el lugar donde se arregla el mix una sola vez en vez de escenario por
    escenario.

    **Sobrevive al redeploy.** El seed de canales es no destructivo: inserta lo
    que falta y no pisa la comisión ni el mix una vez que alguien los cargó (ver
    `seed_canales_comerciales.py`). O sea que esto no se revierte solo — que es
    justo lo que sí pasa con las tablas del mapeo.
    """
    # El mix se valida ANTES de escribir: uno que no cierra deja el Net Factor
    # sobre una base que no es el total, y eso se propaga a TODO el sistema —
    # no a un escenario, porque esta es la base de la que heredan todos.
    suma = sum((f.mix_pct for f in filas), Decimal("0"))
    if abs(suma - Decimal("1")) > Decimal("0.0001"):
        raise ErrorApi(422, "mixer.mix_no_cierra", suma=float(suma))

    async with get_session() as s:
        actuales = {c.code: c for c in await _canales_base(s)}
        desconocidos = [f.code for f in filas if f.code not in actuales]
        if desconocidos:
            # Un código que no existe se guardaría en la nada y el mix quedaría
            # incompleto sin que nada avise.
            raise ErrorApi(422, "mixer.canales_desconocidos",
                           canales=", ".join(desconocidos))
        # Cambiar el destino se valida contra la tabla: si el canal no existe,
        # el mix quedaría rodando a la nada y desaparecería del derivado.
        from app.models.canal_comision import CanalComision
        destinos = {d.code for d in await _canales_comision(s)}
        malos = [f.rueda_a for f in filas
                 if f.rueda_a and f.rueda_a not in destinos]
        if malos:
            raise ErrorApi(422, "mixer.canales_comision_inexistentes",
                           canales=", ".join(sorted(set(malos))))
        for f in filas:
            actuales[f.code].mix_pct = f.mix_pct
            actuales[f.code].comision_pct = f.comision_pct
            if f.rueda_a:
                actuales[f.code].rueda_a = f.rueda_a
        await s.commit()
    return {"guardados": len(filas), "suma": float(suma)}


@router.get("/canales/mixer/escenarios/")
async def escenarios(idioma: str = Idioma, _=Depends(get_current_user)):
    """TODOS los escenarios, con el impacto y —si no aplica— por qué no.

    La lista va completa a propósito. Un escenario que desaparece se lee como
    «no existe»; uno que aparece diciendo por qué quedó afuera se puede discutir.
    """
    async with get_session() as s:
        base = await _canales_base(s)
        destinos_codes = [d.code for d in await _canales_comision(s)]
        escs = list((await s.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type, Scenario.version))).scalars())
        out = []
        for e in escs:
            aplica, mot_clave, mot_params = mixer.gobierna(e)
            motivo = t(idioma, mot_clave, **mot_params) if mot_clave else ""
            derivados = mixer.derivar(
                mixer.resolver(base, await _overrides(s, e.id)), destinos_codes)
            nf_nuevo = mixer.net_factor(derivados)
            nf_hoy, manda = await _net_factor_vigente(s, e.id)
            rooms = await _ingreso_habitaciones(s, e.id)
            out.append({
                "id": e.id, "nombre": f"{e.type} {e.version} {e.year}",
                "year": e.year, "type": e.type, "version": e.version,
                "locked": e.is_locked,
                "aplica": aplica, "motivo": motivo,
                "net_factor_hoy": float(nf_hoy) if nf_hoy is not None else None,
                "net_factor_nuevo": float(nf_nuevo),
                "manda": manda,
                "impacto": _impacto(rooms, nf_hoy, nf_nuevo),
            })
    return {"escenarios": out, "desde_el_ano": mixer.DESDE_EL_ANO}


class Aplicar(BaseModel):
    scenario_ids: list[str]
    #: Reescribir también la tarifa neta como `rack x factor`.
    #:
    #: ⚠️ Sin esto, aplicar NO mueve un número en ningún escenario que tenga
    #: tarifas cargadas —que hoy son todos los que tienen datos—, porque el motor
    #: prefiere `net_rate / rack_rate` sobre el mix. Va en falso por defecto: es
    #: pisar la tarifa neta que vino del Excel, y eso se decide, no se hereda.
    regenerar_tarifas: bool = False


@router.post("/canales/mixer/aplicar/")
async def aplicar(cuerpo: Aplicar, _=Depends(get_current_user),
                  idioma: str = Idioma):
    """Escribe los 3 derivados en `sales_channel_configs`, los 12 meses.

    Es el único punto donde el mixer cambia un número del presupuesto.

    Se escriben los 12 meses aunque el mix sea anual: el motor lee mes a mes, y
    dejar meses sin fila los haría caer a un default distinto — que es
    exactamente el estado en que está hoy Budget Final 2026, con un solo mes.
    """
    escritos, saltados = [], []
    async with get_session() as s:
        destinos_codes = [d.code for d in await _canales_comision(s)]
        base = await _canales_base(s)
        for sid in cuerpo.scenario_ids:
            esc = (await s.execute(select(Scenario).where(
                Scenario.id == sid))).scalar_one_or_none()
            if esc is None:
                saltados.append({"id": sid, "nombre": sid,
                                 "motivo": t(idioma, "mixer.escenario_no_existe")})
                continue
            nombre = f"{esc.type} {esc.version} {esc.year}"
            aplica, mot_clave, mot_params = mixer.gobierna(esc)
            motivo = t(idioma, mot_clave, **mot_params) if mot_clave else ""
            if not aplica:
                saltados.append({"id": sid, "nombre": nombre, "motivo": motivo})
                continue

            overs = await _overrides(s, sid)
            resueltos = mixer.resolver(base, overs)
            # El mix se valida ANTES de escribir. Uno que no suma 100% deja el
            # Net Factor sobre una base que no es el total, y eso se propaga a
            # todo el ingreso sin que nada falle ni avise.
            if not mixer.mix_cierra(resueltos):
                saltados.append({
                    "id": sid, "nombre": nombre,
                    "motivo": t(idioma, "mixer.mix_no_cierra",
                                suma=f"{float(mixer.suma_del_mix(resueltos)):.1%}")})
                continue

            await s.execute(delete(SalesChannelConfig).where(
                SalesChannelConfig.scenario_id == sid))
            nf_por_mes: dict[int, Decimal] = {}
            for m in range(1, 13):
                derivados = mixer.derivar(
                    mixer.resolver(base, overs, m), destinos_codes)
                nf_por_mes[m] = mixer.net_factor(derivados)
                for d in derivados:
                    s.add(SalesChannelConfig(
                        id=str(uuid.uuid4()), scenario_id=sid, hotel_id=esc.hotel_id,
                        channel=d.channel, month=m,
                        mix_pct=d.mix_pct, commission_pct=d.commission_pct))

            tarifas = 0
            if cuerpo.regenerar_tarifas:
                # `net_rate = rack x factor`. Es lo que hace que el cambio de
                # comisión llegue al número: si solo se escriben los canales, el
                # motor sigue leyendo la tarifa neta vieja y nada se mueve.
                rcs = list((await s.execute(select(RateCard).where(
                    RateCard.scenario_id == sid))).scalars())
                for rc in rcs:
                    if not rc.rack_rate:
                        continue
                    rc.net_rate = (rc.rack_rate * nf_por_mes.get(rc.month, nf_por_mes[1])
                                   ).quantize(Decimal("0.01"))
                    tarifas += 1

            escritos.append({"id": sid, "nombre": nombre, "tarifas": tarifas})
        await s.commit()

    avisos = []
    if escritos:
        avisos.append(t(idioma, "mixer.hay_que_recalcular"))
        if not cuerpo.regenerar_tarifas:
            avisos.append(t(idioma, "mixer.canales_si_tarifas_no"))
    return {"aplicados": escritos, "saltados": saltados,
            "regenero_tarifas": cuerpo.regenerar_tarifas,
            "aviso": " ".join(avisos)}


# ═══════════════════════════════════════════════════════════════════════════════
# CREAR Y BORRAR — owner 2026-08-17: «tenés que dejarme crear más mix y borrar
# también, y que el derivado lo tome… pero deben estar sincronizados para que
# ruede donde corresponde»
# ═══════════════════════════════════════════════════════════════════════════════

class SubCanalNuevo(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    nombre: str = ""
    #: A qué canal de comisión rueda. **Obligatorio y validado contra la tabla.**
    #: Es el corazón del pedido: antes se deducía de `entrada` con un default a
    #: DIRECT, así que un sub-canal nuevo rodaba mal y en silencio.
    rueda_a: str
    #: Vacío = este canal describe QUIÉN trajo la reserva, no por dónde entró.
    entrada: str = ""
    mix_pct: Decimal = Decimal("0")
    comision_pct: Decimal = Decimal("0")


class CanalNuevo(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    nombre: str = ""
    orden: int = 0


def _fraccion(v: Decimal, campo: str) -> Decimal:
    """Acepta 55 o 0.55 y devuelve fracción. La grilla manda enteros."""
    d = Decimal(str(v))
    if d < 0:
        raise ErrorApi(422, "mixer.campo_negativo", campo=campo)
    if d > 1:
        d = d / Decimal("100")
    if d > 1:
        raise ErrorApi(422, "mixer.campo_pasa_de_100", campo=campo)
    return d


@router.get("/canales/comision/")
async def listar_canales_comision(_=Depends(get_current_user)):
    """Los canales de comisión, con cuántos sub-canales cuelgan de cada uno.

    El conteo es lo que le dice a la pantalla cuáles se pueden borrar: uno con
    sub-canales colgando **no**, porque el mix quedaría rodando a un destino que
    no existe.
    """
    async with get_session() as s:
        canales = await _canales_comision(s)
        base = await _canales_base(s)
    cuelgan: dict[str, int] = {}
    for c in base:
        cuelgan[mixer.destino_de(c)] = cuelgan.get(mixer.destino_de(c), 0) + 1
    return {"canales": [
        {"code": d.code, "nombre": d.nombre, "orden": d.orden,
         "subcanales": cuelgan.get(d.code, 0),
         "se_puede_borrar": cuelgan.get(d.code, 0) == 0}
        for d in canales]}


@router.post("/canales/comision/", status_code=201)
async def crear_canal_comision(cuerpo: CanalNuevo, _=Depends(get_current_user)):
    """Un canal de comisión nuevo. A partir de acá los sub-canales pueden rodar
    ahí, y el derivado lo toma solo — no hay constante que actualizar."""
    from app.models.canal_comision import CanalComision
    async with get_session() as s:
        if await s.get(CanalComision, cuerpo.code):
            raise ErrorApi(409, "mixer.canal_ya_existe", canal=cuerpo.code)
        s.add(CanalComision(code=cuerpo.code, nombre=cuerpo.nombre or cuerpo.code,
                            orden=cuerpo.orden, activo=True))
        await s.commit()
    return {"creado": cuerpo.code}


@router.delete("/canales/comision/{code}/", status_code=200)
async def borrar_canal_comision(code: str, _=Depends(get_current_user)):
    """⚠️ Se niega si tiene sub-canales colgando.

    Borrarlo igual dejaría su mix apuntando a un destino inexistente, y ese mix
    **desaparecería del derivado**: la suma bajaría de 100% y el Net Factor se
    calcularía sobre una base que no es el total. Nada fallaría.
    """
    from app.models.canal_comision import CanalComision
    async with get_session() as s:
        d = await s.get(CanalComision, code)
        if d is None:
            raise ErrorApi(404, "mixer.canal_no_existe", canal=code)
        base = await _canales_base(s)
        cuelgan = [c.code for c in base if mixer.destino_de(c) == code]
        if cuelgan:
            raise ErrorApi(409, "mixer.canal_con_subcanales", canal=code,
                           n=len(cuelgan), subcanales=", ".join(cuelgan))
        await s.delete(d)
        await s.commit()
    return {"borrado": code}


@router.post("/canales/subcanal/", status_code=201)
async def crear_subcanal(cuerpo: SubCanalNuevo, _=Depends(get_current_user)):
    """Un sub-canal nuevo en el mix base.

    ⚠️ **`rueda_a` se valida contra la tabla.** Es toda la diferencia con lo de
    antes: el destino ya no se adivina desde `entrada` con un default a DIRECT
    —que cobraba 9,27% en vez del 30% de TA y por lo tanto inflaba el ingreso—,
    se elige y tiene que existir.

    El mix arranca en lo que se mande (típicamente 0) y **la suma sigue teniendo
    que dar 100% para poder aplicarlo**: eso lo valida `aplicar`, que es donde el
    mix llega al dinero. Crear con la suma en 103% se permite a propósito, para
    poder acomodar las filas de a una sin que la pantalla se trabe.
    """
    from app.models.canal_comision import CanalComision
    async with get_session() as s:
        if await s.get(CanalComercial, cuerpo.code):
            raise ErrorApi(409, "mixer.subcanal_ya_existe", subcanal=cuerpo.code)
        if await s.get(CanalComision, cuerpo.rueda_a) is None:
            raise ErrorApi(422, "mixer.rueda_a_invalido", destino=cuerpo.rueda_a)
        maximo = max([c.orden for c in await _canales_base(s)] or [0])
        s.add(CanalComercial(
            code=cuerpo.code, nombre=cuerpo.nombre or cuerpo.code,
            rueda_a=cuerpo.rueda_a, entrada=cuerpo.entrada,
            mix_pct=_fraccion(cuerpo.mix_pct, "mix"),
            comision_pct=_fraccion(cuerpo.comision_pct, "comisión"),
            orden=maximo + 1, activo=True))
        await s.commit()
    return {"creado": cuerpo.code, "rueda_a": cuerpo.rueda_a}


@router.delete("/canales/subcanal/{code}/", status_code=200)
async def borrar_subcanal(code: str, _=Depends(get_current_user),
                          idioma: str = Idioma):
    """Borra un sub-canal del mix base y sus excepciones por escenario.

    Las excepciones se borran con él a propósito: una fila de
    `canal_mix_escenario` apuntando a un `code` que ya no existe no se ve en
    ninguna pantalla y no la limpia nadie.

    Devuelve la suma del mix que queda, porque después de borrar **casi nunca da
    100%** y la pantalla tiene que decirlo antes de que alguien aplique.
    """
    async with get_session() as s:
        c = await s.get(CanalComercial, code)
        if c is None:
            raise ErrorApi(404, "mixer.subcanal_no_existe", subcanal=code)
        borradas = (await s.execute(
            delete(CanalMixEscenario).where(CanalMixEscenario.code == code)
        )).rowcount or 0
        await s.delete(c)
        await s.commit()
        quedan = await _canales_base(s)
    suma = mixer.suma_del_mix(quedan)
    return {
        "borrado": code,
        "excepciones_borradas": borradas,
        "mix_suma": float(suma),
        "mix_cierra": mixer.mix_cierra(quedan),
        "aviso": None if mixer.mix_cierra(quedan) else t(
            idioma, "mixer.mix_quedo_incompleto", suma=f"{float(suma):.1%}"),
    }
