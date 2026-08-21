# -*- coding: utf-8 -*-
"""Costos para Negociación de Grupos — la capa de lectura y sus validaciones.

Fase 1 del spec `COSTOS_GRUPOS.md`: armar los hechos mensuales y correr las
validaciones 1 a 3.

⚠️ **Acá no se carga nada: se LEE del motor.** El spec describe cuatro tablas
`fact_*`; ninguna se creó. El P&L mensual, el overhead y los no-operativos ya
los produce `compute_pl_month`, y los volúmenes ya viven en `scenario_stats` y
`statistical_entries`. Copiarlos sería tener dos fuentes del mismo número — y
la copia se queda vieja el día que alguien recalcula, sin que nada falle.

⚠️ **Regla del grano (spec §3.2): todo es MENSUAL.** Las temporadas se agregan
desde meses, nunca al revés. Eso es lo que permite cotizar un grupo que cruza
temporadas, y lo que evita el promedio de promedios que el spec prohíbe en §4.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.costos_grupos import CfgParametro, CfgTemporada
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

TOLERANCIA = Decimal("1")   # spec §6: tolerancia de $1 en las reconciliaciones


@dataclass
class MesDeCostos:
    """Los hechos de un mes, tal como salen del motor."""
    mes: int
    temporada: str
    dias_abiertos: int
    revenue_por_dept: dict[str, Decimal] = field(default_factory=dict)
    costo_por_dept: dict[str, Decimal] = field(default_factory=dict)
    overhead_por_componente: dict[str, Decimal] = field(default_factory=dict)
    no_operativo: Decimal = Decimal("0")
    #: `TOTAL_REVENUES` del P&L. ⚠️ No es la suma de `revenue_por_dept`: es el
    #: total que calcula el motor. Tenerlo aparte es lo que permite CONTROLAR
    #: que un cuadro por departamento no se haya dejado una línea afuera.
    total_revenue_pl: Decimal = Decimal("0")
    #: Toda línea del P&L que no es ingreso, opex, overhead ni total: renta,
    #: management fee, seguro, reserva de capital, capital mayor, depreciación…
    #: ⚠️ Se guardan SUELTAS y no sólo su total, porque el Master Data del spec
    #: (§5, sub-tab 3) las muestra una por una — y un bloque de seis filas
    #: rellenado desde un total sería un desglose inventado.
    otras_lineas: dict[str, Decimal] = field(default_factory=dict)
    # Volúmenes. Hoy sólo habitaciones tiene dato real — ver `origen_volumen`.
    hab_disponibles: int = 0
    hab_ocupadas: Decimal = Decimal("0")
    noches_huesped: Decimal = Decimal("0")

    @property
    def costo_total(self) -> Decimal:
        return sum(self.costo_por_dept.values(), Decimal("0"))

    @property
    def overhead_total(self) -> Decimal:
        return sum(self.overhead_por_componente.values(), Decimal("0"))


async def cargar_parametros(db: AsyncSession, hotel_id: str) -> dict[str, str]:
    filas = (await db.execute(
        select(CfgParametro).where(CfgParametro.hotel_id == hotel_id)
    )).scalars().all()
    return {f.clave: f.valor for f in filas}


async def cargar_temporadas(db: AsyncSession, hotel_id: str) -> dict[int, CfgTemporada]:
    filas = (await db.execute(
        select(CfgTemporada).where(CfgTemporada.hotel_id == hotel_id)
    )).scalars().all()
    return {f.mes: f for f in filas}


async def escenario_base(db: AsyncSession, hotel_id: str) -> Scenario | None:
    """El escenario del que sale todo, según `cfg_parametros.escenario_base`.

    Formato `TIPO/AÑO/VERSION`. Decisión del owner (2026-08-19):
    `FORECAST/2026/Working`. Importa cuál sea: entre escenarios la capacidad
    anual va de 10.020 a 10.950 habitaciones-noche —según tengan octubre
    cerrado o no— y eso mueve el overhead por habitación de $216 a $198, un 9%
    del piso.
    """
    par = await cargar_parametros(db, hotel_id)
    crudo = par.get("escenario_base", "")
    partes = crudo.split("/")
    if len(partes) != 3:
        return None
    tipo, anio, version = partes
    q = select(Scenario).where(
        Scenario.type == tipo, Scenario.year == int(anio), Scenario.version == version
    )
    return (await db.execute(q)).scalars().first()


async def hechos_mensuales(db: AsyncSession, sc: Scenario,
                           hotel_id: str) -> list[MesDeCostos]:
    """Los doce meses, leídos del motor. Sin copiar nada a una tabla."""
    from app.api.cashflow_directo_api import una_por_codigo_canonico
    from app.api.pl_api import _pl_component
    from app.engine.recalculate import compute_pl_month

    temporadas = await cargar_temporadas(db, hotel_id)
    stats = {
        s.month: s for s in (await db.execute(
            select(ScenarioStat).where(ScenarioStat.scenario_id == sc.id)
        )).scalars().all()
    }

    fuera: list[MesDeCostos] = []
    for m in range(1, 13):
        t = temporadas.get(m)
        mes = MesDeCostos(
            mes=m,
            temporada=t.temporada if t else "",
            dias_abiertos=t.dias_abiertos if t else 0,
        )
        for code, ln in una_por_codigo_canonico(
                await compute_pl_month(db, sc, m)).items():
            monto = Decimal(str(ln.amount_usd or 0))
            if code.startswith("TOTAL"):
                if code == "TOTAL_NON_OP_EXPENSES":
                    mes.no_operativo = monto
                elif code == "TOTAL_REVENUES":
                    mes.total_revenue_pl = monto
                continue
            if code.startswith("REV_"):
                mes.revenue_por_dept[code] = monto
            elif _pl_component(ln, "OPEX"):
                mes.costo_por_dept[code] = monto
            elif _pl_component(ln, "OVERHEAD"):
                mes.overhead_por_componente[code] = monto
            else:
                # ⚠️ Antes esto se DESCARTABA. Son las líneas de abajo del GOP
                # —renta, fee, seguro, capital— y el Master Data las pide una
                # por una. Guardarlas es aditivo: ningún consumidor de antes
                # mira este diccionario.
                mes.otras_lineas[code] = monto

        st = stats.get(m)
        if st:
            mes.hab_disponibles = int(st.rooms_available or 0)
            mes.hab_ocupadas = Decimal(str(st.rooms_occupied or 0))
            mes.noches_huesped = Decimal(str(st.guests or 0))
        fuera.append(mes)
    return fuera


# ─── Validaciones obligatorias (spec §6) ─────────────────────────────────────

@dataclass
class Hallazgo:
    control: str
    pasa: bool
    detalle: str


async def validar(db: AsyncSession, sc: Scenario, hotel_id: str) -> list[Hallazgo]:
    """Las tres de la Fase 1. Ninguna corrida se publica sin pasarlas."""
    from app.api.cashflow_directo_api import una_por_codigo_canonico
    from app.engine.recalculate import compute_pl_month

    meses = await hechos_mensuales(db, sc, hotel_id)
    fuera: list[Hallazgo] = []

    # 1 · Reconciliación de costos: las partes por departamento tienen que dar
    #     el total del P&L. Es la misma clase de defecto que ya apareció en el
    #     tab de Proveedores, donde el desglose quedaba $418.982 corto contra
    #     su propio total sin que fallara nada.
    peor_mes, peor_dif = 0, Decimal("0")
    for m in range(1, 13):
        d = una_por_codigo_canonico(await compute_pl_month(db, sc, m))
        total = Decimal(str(d["TOTAL_OPERATING_EXPENSES"].amount_usd or 0)) \
            if "TOTAL_OPERATING_EXPENSES" in d else Decimal("0")
        partes = meses[m - 1].costo_total
        dif = total - partes
        if abs(dif) > abs(peor_dif):
            peor_mes, peor_dif = m, dif
    fuera.append(Hallazgo(
        "1 · costos por departamento = costo del P&L",
        abs(peor_dif) <= TOLERANCIA,
        f"peor mes {peor_mes or '—'}: diferencia ${peor_dif:,.2f}",
    ))

    # 2 · Reconciliación de overhead.
    #
    # ⚠️ El spec pide «Σ overhead asignado por cualquier método = overhead
    # total», y con el método por defecto eso es IMPOSIBLE de cumplir: M2
    # reparte entre habitaciones DISPONIBLES y el piso lo aplica a una
    # habitación VENDIDA. Con 71,86% de ocupación se asignaría el 71,86% del
    # overhead y faltaría el resto — no por un error, sino porque la parte de
    # las habitaciones vacías no la paga ningún grupo.
    #
    # Lo que sí tiene que cuadrar, y es lo que se controla acá, es que los
    # COMPONENTES del overhead sumen el overhead total. Quien garantiza que el
    # año cierre es la Golden Rate (§4.7), que divide entre ocupadas.
    peor_mes, peor_dif = 0, Decimal("0")
    for m in range(1, 13):
        d = una_por_codigo_canonico(await compute_pl_month(db, sc, m))
        total = Decimal(str(d["TOTAL_OVERHEAD_EXPENSES"].amount_usd or 0)) \
            if "TOTAL_OVERHEAD_EXPENSES" in d else Decimal("0")
        dif = total - meses[m - 1].overhead_total
        if abs(dif) > abs(peor_dif):
            peor_mes, peor_dif = m, dif
    fuera.append(Hallazgo(
        "2 · componentes de overhead = overhead total",
        abs(peor_dif) <= TOLERANCIA,
        f"peor mes {peor_mes or '—'}: diferencia ${peor_dif:,.2f}",
    ))

    # 3 · Cuadre de capacidad.
    #
    # ⚠️ El spec lo escribe como «= 10.020», un número fijo, y eso falla en la
    # mitad de los escenarios: el Budget Working 2027 y los Actuals tienen
    # octubre ABIERTO y suman 10.950. Se compara contra el calendario
    # configurado, que es quien sabe qué meses están cerrados.
    # ⚠️ Las habitaciones salen del HOTEL, no de una constante. Son 30 en CWL,
    # pero este módulo se clona a Amarena, Oxígen y Ojochal — y un 30 escrito
    # acá daría un cuadre falso en las tres sin fallar en ninguna.
    from app.models.hotel import Hotel
    hotel = await db.get(Hotel, hotel_id)
    habitaciones = int(getattr(hotel, "rooms", 0) or 0)

    temporadas = await cargar_temporadas(db, hotel_id)
    esperado = sum(t.dias_abiertos for t in temporadas.values()) * habitaciones
    real = sum(x.hab_disponibles for x in meses)
    fuera.append(Hallazgo(
        "3 · capacidad del escenario = calendario configurado",
        esperado == real,
        f"escenario {real:,} · calendario {esperado:,} "
        f"({habitaciones} hab) · diferencia {real - esperado:,}",
    ))
    return fuera


# ─── Fase 2 · costos unitarios y absorción ───────────────────────────────────
#
# ⚠️ Las fórmulas de acá NO salieron del spec: salieron de PROBARLAS contra las
# semillas del §7, que existen justo para eso. Cinco de siete reproducen al
# centavo; las dos que no, y por qué, están anotadas donde corresponde.

# ⚠️ La composición ya NO vive acá: es configuración editable
# (), sembrada desde . El
# owner lo pidió a propósito de Sustainability, y tenía razón: la composición
# es donde uno se equivoca y donde cada propiedad difiere.


def _suma(acc: dict[str, Decimal], codigos) -> Decimal:
    return sum((acc.get(c, Decimal("0")) for c in codigos), Decimal("0"))


async def cargar_composicion(db: AsyncSession, hotel_id: str) -> dict:
    """De qué líneas del P&L se compone cada concepto. **Editable** (pedido del
    owner, 2026-08-19): sale de `cfg_composicion_costos`, no del código.

    ⚠️ El caso que lo pidió: la semilla del spec para el Sustainability Fee sólo
    cerraba sumándole «Other / Misc», porque en el libro de origen eran un mismo
    cubo. **El owner decidió separarlos**, y con eso Sustainability pasa de
    $92,12 a $54,38 por habitación ocupada. Ese tipo de decisión no puede vivir
    en el código.

    Si la tabla está vacía cae a la semilla, para que el módulo funcione en una
    propiedad recién clonada antes de que nadie la configure.
    """
    from app.models.costos_grupos import CfgComposicion
    filas = (await db.execute(
        select(CfgComposicion).where(
            CfgComposicion.hotel_id == hotel_id, CfgComposicion.activa.is_(True))
    )).scalars().all()
    if not filas:
        from app.seed_costos_grupos import COMPOSICION
        return {k: list(v) for k, v in COMPOSICION.items()}
    fuera: dict = {}
    for f in filas:
        fuera.setdefault((f.concepto, f.rol), []).append(f.line_code)
    return fuera


def costos_unitarios(meses: list[MesDeCostos], comp: dict) -> dict[str, Decimal]:
    """Costo por unidad de servicio, para el conjunto de meses que se le pase.

    ⚠️ Suma de costos ÷ suma de volúmenes, **nunca promedio de promedios**
    (spec §4.1). Con promedio de promedios, un mes de baja ocupación pesa lo
    mismo que uno lleno y el unitario sale inventado.
    """
    costo: dict[str, Decimal] = {}
    for m in meses:
        for c, v in m.costo_por_dept.items():
            costo[c] = costo.get(c, Decimal("0")) + v
        for c, v in m.revenue_por_dept.items():
            costo[c] = costo.get(c, Decimal("0")) + v

    ocup = sum((m.hab_ocupadas for m in meses), Decimal("0"))
    hues = sum((m.noches_huesped for m in meses), Decimal("0"))
    disp = Decimal(sum(m.hab_disponibles for m in meses))
    oh = sum((m.overhead_total for m in meses), Decimal("0"))

    def por(monto: Decimal, base: Decimal) -> Decimal:
        return monto / base if base else Decimal("0")

    fuera = {
        "hab_propio_por_ocupada": por(_suma(costo, comp.get(("ROOMS", "propio"), [])), ocup),
        "fb_propio_por_huesped": por(_suma(costo, comp.get(("FB", "propio"), [])), hues),
        "fb_venta_por_huesped": por(_suma(costo, comp.get(("FB", "venta"), [])), hues),
        "tours_venta_por_huesped": por(_suma(costo, comp.get(("TOURS", "venta"), [])), hues),
        "tours_propio_por_huesped": por(_suma(costo, comp.get(("TOURS", "propio"), [])), hues),
        "transp_propio_por_ocupada": por(
            _suma(costo, comp.get(("TRANSPORTATION", "propio"), [])), ocup),
        "spa_propio_por_huesped": por(_suma(costo, comp.get(("SPA", "propio"), [])), hues),
        "sustainability_por_ocupada": por(_suma(costo, comp.get(("SUSTAINABILITY", "ingreso"), [])), ocup),
        "sustainability_por_huesped": por(_suma(costo, comp.get(("SUSTAINABILITY", "ingreso"), [])), hues),
        "overhead_por_disponible": por(oh, disp),
        "overhead_por_ocupada": por(oh, ocup),
    }
    return fuera


def absorcion(meses: list[MesDeCostos], metodo: str = "M2",
              tratamiento: str = "B",
              ciclo: list[MesDeCostos] | None = None) -> Decimal:
    """Overhead por habitación-noche, según el método (spec §4.2).

    ⚠️ **M1 está prohibido para pisos y por eso no se implementa acá.** Repartir
    el overhead como % del revenue es circular: si se concede un descuento, baja
    el revenue y baja el overhead asignado en la misma proporción, así que el
    piso se mueve junto con el precio y nunca se alcanza. Vive sólo en el
    sub-tab de conciliación.

    M2 (default) divide entre DISPONIBLES: estable entre temporadas ($207 /
    $221 / $216), que es lo que hace negociable un piso.
    M3 divide entre OCUPADAS: recupera todo el overhead, pero se mueve con la
    ocupación — un mes flojo sube el piso justo cuando hay que vender más.
    """
    if metodo == "M1":
        raise ValueError(
            "M1 (revenue share) es circular y está prohibido para pisos — "
            "spec §1 y §4.2. Sólo se usa en la conciliación con el P&L.")
    # ⚠️ Tratamiento del mes cerrado (spec §2.1). Con B —el default— el
    # overhead unitario es el del CICLO ANUAL, igual en las tres temporadas.
    #
    # Sin esto, una temporada que contiene el mes cerrado absorbe su costo sola:
    # medido, el piso de BAJA daba .715 por habitacion-noche. El spec lo
    # advierte con todas las letras — «ningun grupo compra eso y la operacion
    # rechaza el unico negocio disponible en el mes mas flojo».
    #
    # A se sigue pudiendo calcular, y sirve: es el diagnostico de cuanto cuesta
    # tener el hotel cerrado.
    base_meses = (ciclo or meses) if tratamiento == "B" else meses
    oh = sum((m.overhead_total for m in base_meses), Decimal("0"))
    meses = base_meses
    if metodo == "M3":
        base = sum((m.hab_ocupadas for m in meses), Decimal("0"))
    else:
        base = Decimal(sum(m.hab_disponibles for m in meses))
    return oh / base if base else Decimal("0")


# ─── Fase 3 · los pisos de precio (spec §4.3) ────────────────────────────────

def gross_up(costo: Decimal, fee: Decimal, comision: Decimal,
             margen: Decimal = Decimal("0")) -> Decimal:
    """De costo a precio.

    ⚠️ El fee y la comisión son porcentajes **sobre el precio**, no costos
    fijos, así que no se suman al costo: se despejan. Cobrar `costo + 25%`
    deja corto — sobre un precio de 100 con 25% de comisión quedan 75, no 80.

    Si los porcentajes suman 1 o más, no hay precio que alcance: se avisa en vez
    de devolver un número enorme o negativo, que es lo que hace una división
    por casi-cero.
    """
    resto = Decimal("1") - fee - comision - margen
    if resto <= 0:
        raise ValueError(
            f"fee {fee} + comisión {comision} + margen {margen} no dejan margen "
            f"para cubrir el costo: no hay precio que alcance")
    return costo / resto


@dataclass
class Pisos:
    """Los cuatro pisos de la habitación-noche, en dólares."""
    marginal: Decimal          # 1 — sólo variable, para capacidad ociosa
    departamental: Decimal     # 2 — costo propio, sin overhead
    integral: Decimal          # 3 — costo propio + overhead
    con_margen: Decimal        # 4 — integral + margen protegido
    # De qué se compone, para poder auditarlo sin rehacer la cuenta
    costo_propio: Decimal
    costo_variable: Decimal
    overhead_unitario: Decimal
    credito_sustainability: Decimal
    # ⚠️ True = el Piso 1 NO se calculó con una clasificación fijo/variable
    # real; cayó al costo propio completo. Es conservador a propósito. Quien
    # lo muestre TIENE que decirlo: un Piso 1 que parece medido y no lo está
    # es peor que no tenerlo.
    marginal_estimado: bool = False


def pisos_habitacion(meses: list[MesDeCostos], comp: dict, par: dict[str, str],
                     comision: Decimal, metodo: str = "M2",
                     ciclo: list[MesDeCostos] | None = None) -> Pisos:
    """Los cuatro pisos por habitación-noche (spec §4.3).

    ⚠️ **Ninguno de estos números depende del precio, y esa es toda la idea del
    módulo** (§1). El costo va en dólares por unidad física y el overhead se
    reparte por habitación disponible. Si alguna vez un piso se moviera al
    conceder un descuento, hay un porcentaje sobre revenue infiltrado — que es
    exactamente lo que mide la validación 6.
    """
    # ⚠️ Bajo el tratamiento B, un mes CERRADO no aporta su costo propio a la
    # temporada: no tiene noches que lo absorban, asi que dividir por las de su
    # vecino infla el unitario sin que nadie pueda comprarlo. Su costo lo lleva
    # el ciclo anual, igual que el overhead.
    trat = par.get("tratamiento_mes_cerrado", "B")
    abiertos = [m for m in meses if m.dias_abiertos > 0] if trat == "B" else meses
    cu = costos_unitarios(abiertos or meses, comp)
    fee = Decimal(par.get("management_fee_pct", "0.03"))
    margen = Decimal(par.get("margen_protegido_pct", "0.15"))

    propio = cu["hab_propio_por_ocupada"]
    oh = absorcion(meses, metodo, trat, ciclo)

    # El variable de Habitaciones sale de la clasificación fijo/variable, que
    # comparte criterio con Break-Even. Mientras no esté cargada, el Piso 1 se
    # apoya en el costo propio completo y queda MARCADO — un piso marginal
    # inflado rechaza negocio que convenía, y uno inventado lo regala.
    variable = _suma(
        {c: v for m in abiertos for c, v in m.costo_por_dept.items()},
        comp.get(("ROOMS", "venta"), []),
    )
    ocup = sum((m.hab_ocupadas for m in abiertos), Decimal("0"))
    variable_unit = variable / ocup if ocup else Decimal("0")

    # ⚠️ Habitaciones NO tiene línea de costo de venta en USALI, así que esa
    # suma da CERO —no «poco»— y el Piso 1 salía en $0,00: «regalalo». El
    # comentario de arriba ya decía que había que caer al costo propio; el
    # código no lo hacía. Medido contra producción: $0,00 en las tres
    # temporadas del Forecast Working 2026.
    marginal_estimado = variable_unit <= 0
    if marginal_estimado:
        variable_unit = propio

    # Crédito del Sustainability Fee. Apagado por defecto: si el aporte a
    # conservación es su contrapartida, el fee NO es margen libre y acreditarlo
    # sobrestima el margen del grupo (spec §8, hueco 1).
    credito = (cu["sustainability_por_ocupada"]
               if par.get("sustainability_libre", "NO") == "SI" else Decimal("0"))

    def piso(costo: Decimal, m: Decimal) -> Decimal:
        return gross_up(costo, fee, comision, m) - credito

    return Pisos(
        marginal=piso(variable_unit, Decimal("0")),
        departamental=piso(propio, Decimal("0")),
        integral=piso(propio + oh, Decimal("0")),
        con_margen=piso(propio + oh, margen),
        costo_propio=propio,
        costo_variable=variable_unit,
        overhead_unitario=oh,
        credito_sustainability=credito,
        marginal_estimado=marginal_estimado,
    )


# ─── Fase 4 · la Golden Rate (spec §4.7) ─────────────────────────────────────

@dataclass
class GoldenRate:
    """La tarifa por habitacion-noche que cubre TODO."""
    tarifa: Decimal
    requerido: Decimal
    costo_propio_rooms: Decimal
    overhead: Decimal
    no_operativo: Decimal
    capital: Decimal
    contribucion_ajena: Decimal
    hab_ocupadas: Decimal
    # De donde salio cada contribucion, para poder discutirla sin rehacer la cuenta
    detalle_contribucion: dict[str, Decimal] = field(default_factory=dict)


def golden_rate(meses: list[MesDeCostos], comp: dict, par: dict[str, str],
                comision: Decimal, margen: Decimal = Decimal("0")) -> GoldenRate:
    """Lo unico que Ventas tiene que memorizar.

    ⚠️ **Se calcula sobre el AÑO COMPLETO, nunca sobre una temporada** — regla
    dura del spec, y con motivo: aislada, la temporada alta parece necesitar
    mucho menos porque en esos meses el volumen es alto y los demas
    departamentos aportan de sobra. Esa base ignora el mes cerrado, la
    temporada baja y la estructura que corre los doce meses. Vender alta contra
    una Golden Rate estacional destruye el año.

    ⚠️ **La resta de la contribucion ajena es lo que la distingue de un piso
    departamental.** F&B, tours, transporte y el fee ya absorben parte de la
    estructura; cobrarla otra vez en la tarifa de habitacion da un numero
    inflado que nadie puede vender.

    ⚠️ Y ojo con el signo: un departamento que PIERDE plata tiene contribucion
    negativa, asi que restarla SUBE la tarifa. Es correcto —esa perdida la
    tiene que cubrir alguien— pero es al reves de lo que uno espera al «sumar
    un departamento», y con Club Madresal no es un detalle.
    """
    costo = _acumular_lista([m.costo_por_dept for m in meses])
    ingreso = _acumular_lista([m.revenue_por_dept for m in meses])

    propio_rooms = _suma(costo, comp.get(("ROOMS", "propio"), []))
    oh = sum((m.overhead_total for m in meses), Decimal("0"))
    nonop = sum((m.no_operativo for m in meses), Decimal("0"))
    capital = Decimal("0")   # el spec lo deja fuera por defecto (§3.1)

    # Todos los demas departamentos — decision del owner (2026-08-19).
    detalle: dict[str, Decimal] = {}
    for (concepto, rol) in comp:
        if rol != "ingreso" or concepto == "ROOMS":
            continue
        rev = _suma(ingreso, comp.get((concepto, "ingreso"), []))
        cst = _suma(costo, comp.get((concepto, "propio"), []))
        detalle[concepto] = rev - cst
    ajena = sum(detalle.values(), Decimal("0"))

    requerido = propio_rooms + oh + nonop + capital - ajena
    ocup = sum((m.hab_ocupadas for m in meses), Decimal("0"))
    fee = Decimal(par.get("management_fee_pct", "0.03"))
    unitario = requerido / ocup if ocup else Decimal("0")

    return GoldenRate(
        tarifa=gross_up(unitario, fee, comision, margen) if unitario > 0 else Decimal("0"),
        requerido=requerido, costo_propio_rooms=propio_rooms, overhead=oh,
        no_operativo=nonop, capital=capital, contribucion_ajena=ajena,
        hab_ocupadas=ocup, detalle_contribucion=detalle,
    )


def _acumular_lista(ds: list[dict[str, Decimal]]) -> dict[str, Decimal]:
    fuera: dict[str, Decimal] = {}
    for d in ds:
        for c, v in d.items():
            fuera[c] = fuera.get(c, Decimal("0")) + v
    return fuera


# ─── El resumen fully loaded aprobado por la Junta (spec §5, Bloque A) ───────
#
# Réplica de «PROPUESTA DE DESCUENTOS — COSTO FULLY LOADED» del owner, base
# Actual YTD abril 2026. Toda la aritmética está verificada contra su reporte y
# vive en `tests/test_costos_grupos_resumen_porcentual.py`, que es la prueba de
# aceptación: si deja de dar, el motor dejó de decir lo que la Junta aprobó.

#: Lo que dice la última columna de su cuadro.
ESTADO_OK = "Techo bruto antes de pérdida"
ESTADO_PIERDE = "Tarifa actual no cubre costo"


@dataclass
class FilaFullyLoaded:
    """Un departamento, en dólares y en % de su propio revenue."""
    concepto: str
    revenue: Decimal
    costo_departamento: Decimal          # $ — payroll + costo de venta + opex propio
    costo_departamento_pct: Decimal
    overhead: Decimal                    # $ — asignado POR REVENUE
    overhead_pct: Decimal
    fee: Decimal                         # $
    fee_pct: Decimal
    costo_fully_loaded_pct: Decimal      # los tres juntos, sobre el revenue
    utilidad: Decimal                    # $
    margen_actual: Decimal               # %
    descuento_maximo: Decimal            # % — el margen con el fee devuelto

    @property
    def cubre(self) -> bool:
        return self.utilidad >= 0

    @property
    def estado(self) -> str:
        return ESTADO_OK if self.cubre else ESTADO_PIERDE


@dataclass
class ResumenFullyLoaded:
    """La banda de totales de arriba del cuadro, y las filas."""
    filas: list[FilaFullyLoaded]
    revenue: Decimal
    costo_departamental: Decimal
    overhead: Decimal
    fee: Decimal
    utilidad: Decimal
    margen_ponderado: Decimal
    overhead_pct: Decimal

    @property
    def pierden(self) -> list[str]:
        """Los departamentos cuya tarifa actual no cubre el costo. Se listan
        aparte porque son los que hay que mirar primero."""
        return [f.concepto for f in self.filas if not f.cubre]


def resumen_fully_loaded(meses: list[MesDeCostos], comp: dict,
                         par: dict[str, str],
                         conceptos: list[str] | None = None) -> ResumenFullyLoaded:
    """El cuadro «PROPUESTA DE DESCUENTOS — COSTO FULLY LOADED» del owner.

    Fórmulas verificadas contra su reporte YTD abril 2026, al centavo:

        overhead_pct   = overhead total / revenue total       ← PLANO, por revenue
        overhead_$     = overhead_pct × revenue del depto
        fee_$          = fee_pct × revenue del depto
        utilidad       = revenue − costo propio − overhead_$ − fee_$
        margen         = utilidad / revenue
        descuento_max  = margen / (1 − fee_pct)

    ⚠️ **El overhead se asigna POR REVENUE a todos los departamentos, y eso NO
    es lo que hace `pisos_habitacion`.** Ahí se absorbe por habitación-noche y
    se carga sólo a Habitaciones, porque cargárselo además a F&B o a Tours lo
    contaría dos veces dentro del mismo paquete (§4.2). Las dos cosas están
    bien y sirven para cosas distintas: este cuadro es para **leer el P&L y
    fijar techos de comisión**; el piso de precio sale del otro camino. El §5
    del spec lo dice y exige que la pantalla lo advierta.

    ⚠️ **El descuento máximo devuelve el fee.** Si la tarifa baja, el fee —que
    es un % de la venta— baja con ella: por eso el límite no es el margen pelado
    sino `margen / (1 − fee)`. Sin ese gross-up el techo sale más bajo que el
    real y se rechaza negocio que sí convenía.

    ⚠️ **Un departamento que pierde NO se recorta a cero.** En el cuadro del
    owner la Tienda da −2,1% de margen y −2,2% de descuento, con el estado
    «tarifa actual no cubre costo». Mostrar 0% diría «no podés descontar»
    cuando la verdad es «ya estás debajo del costo», que es otra conversación.
    """
    costo = _acumular_lista([m.costo_por_dept for m in meses])
    ingreso = _acumular_lista([m.revenue_por_dept for m in meses])
    fee_pct = Decimal(par.get("management_fee_pct", "0.03"))

    overhead_total = sum((m.overhead_total for m in meses), Decimal("0"))
    revenue_total = sum(ingreso.values(), Decimal("0"))
    oh_pct = (overhead_total / revenue_total) if revenue_total else Decimal("0")

    orden = conceptos or sorted({c for c, _ in comp})
    filas: list[FilaFullyLoaded] = []
    for concepto in orden:
        rev = _suma(ingreso, comp.get((concepto, "ingreso"), []))
        # ⚠️ Un departamento sin ingreso se SALTEA en vez de salir en 0%: el
        # porcentaje sería una división por cero disfrazada, y una fila en cero
        # se lee como «no cuesta nada».
        if rev <= 0:
            continue
        propio = _suma(costo, comp.get((concepto, "propio"), []))
        oh = oh_pct * rev
        fee = fee_pct * rev
        utilidad = rev - propio - oh - fee
        margen = utilidad / rev
        filas.append(FilaFullyLoaded(
            concepto=concepto, revenue=rev,
            costo_departamento=propio, costo_departamento_pct=propio / rev,
            overhead=oh, overhead_pct=oh_pct,
            fee=fee, fee_pct=fee_pct,
            costo_fully_loaded_pct=(propio + oh + fee) / rev,
            utilidad=utilidad, margen_actual=margen,
            descuento_maximo=(margen / (Decimal("1") - fee_pct)
                              if fee_pct != 1 else margen),
        ))

    # ⚠️ La banda de arriba suma **las filas mostradas**, no el P&L entero. El
    # cuadro del owner analiza seis departamentos y su «Revenue analizado» son
    # esos seis: poner el revenue total del hotel haría que el margen ponderado
    # no cerrara contra las filas que están debajo.
    rev_t = sum((f.revenue for f in filas), Decimal("0"))
    util_t = sum((f.utilidad for f in filas), Decimal("0"))
    return ResumenFullyLoaded(
        filas=filas,
        revenue=rev_t,
        costo_departamental=sum((f.costo_departamento for f in filas), Decimal("0")),
        overhead=sum((f.overhead for f in filas), Decimal("0")),
        fee=sum((f.fee for f in filas), Decimal("0")),
        utilidad=util_t,
        margen_ponderado=(util_t / rev_t) if rev_t else Decimal("0"),
        overhead_pct=oh_pct,
    )


# ─── Fase 4b · comision maxima por capas (spec §4.8) ─────────────────────────

@dataclass
class CapasComision:
    """Cuanta comision aguanta un departamento antes de dejar de cubrirse."""
    concepto: str
    capa1: Decimal            # cubre el Costo Total Integral, margen cero
    capa2: Decimal            # CTI + margen protegido
    margen_integral: Decimal  # 1 - fee - C/R sobre el revenue NETO
    factor_neto: Decimal      # 1 - comision ya embebida en el revenue
    costo: Decimal
    revenue_neto: Decimal


def comision_maxima(meses: list[MesDeCostos], comp: dict, par: dict[str, str],
                    factores: dict[str, Decimal],
                    metodo: str = "M2") -> list[CapasComision]:
    """Responde: **cuanta comision aguanta esta tarifa antes de no cubrirse.**

    Es distinto del descuento maximo aunque la aritmetica se parezca: la
    comision no baja la tarifa publicada, baja lo que el hotel recibe.

    ⚠️ **El gross-up es obligatorio y es donde esta la trampa.** El revenue del
    P&L de CWL ya viene NETO de comision de agencias. Calcular `c_max` contra
    ese revenue descuenta la comision DOS VECES y el techo sale artificialmente
    bajo — o sea, se rechaza negocio que si convenia.

        R_bruto = revenue_neto / (1 - c_actual)

    ⚠️ Y `c_actual` es por DEPARTAMENTO, no global. Habitaciones y paquetes
    vendidos por agencia llevan comision embebida; tienda, spa y consumos en
    sitio se venden directo — su factor es 1.0, y aplicarles el gross-up seria
    inventar un techo que no existe.

    Cuando el factor es 1.0, la Capa 1 tiene que dar EXACTAMENTE el Margen
    Integral. Si no coincide, hay un gross-up mal aplicado — es la validacion 7
    del spec, y esta como prueba.
    """
    costo = _acumular_lista([m.costo_por_dept for m in meses])
    ingreso = _acumular_lista([m.revenue_por_dept for m in meses])
    fee = Decimal(par.get("management_fee_pct", "0.03"))
    margen = Decimal(par.get("margen_protegido_pct", "0.15"))
    oh_unit = absorcion(meses, metodo, par.get("tratamiento_mes_cerrado", "B"))
    ocup = sum((m.hab_ocupadas for m in meses), Decimal("0"))

    fuera: list[CapasComision] = []
    for concepto in sorted({c for c, _ in comp}):
        rev = _suma(ingreso, comp.get((concepto, "ingreso"), []))
        if rev <= 0:
            continue
        c_propio = _suma(costo, comp.get((concepto, "propio"), []))
        # El overhead se absorbe por habitacion-noche y se carga a Habitaciones:
        # cargarselo tambien a F&B o tours seria contarlo dos veces adentro del
        # mismo paquete (spec §4.2).
        c_total = c_propio + (oh_unit * ocup if concepto == "ROOMS" else Decimal("0"))

        factor = factores.get(concepto, Decimal("1"))
        r_bruto = rev / factor if factor else rev
        k = c_total / r_bruto if r_bruto else Decimal("0")

        fuera.append(CapasComision(
            concepto=concepto,
            capa1=Decimal("1") - fee - k,
            capa2=Decimal("1") - fee - margen - k,
            margen_integral=Decimal("1") - fee - (c_total / rev if rev else Decimal("0")),
            factor_neto=factor, costo=c_total, revenue_neto=rev,
        ))
    return fuera


def erosion_combinada(descuento: Decimal, comision: Decimal) -> Decimal:
    """Comision y descuento se MULTIPLICAN, no se suman (spec §4.8).

    Un 20% de descuento con 25% de comision erosiona 40%, no 45%. Sumarlos
    sobrestima el daño y hace rechazar negocio que convenia.
    """
    return Decimal("1") - (Decimal("1") - descuento) * (Decimal("1") - comision)


# ─── Fase 7 · el rack y el descuento máximo ──────────────────────────────────
#
# Regla del owner (2026-08-19): **los grupos se negocian desde la tarifa rack.**
# El piso dice cuál es el mínimo; el rack dice desde dónde se baja. Lo que
# Ventas necesita no es ninguno de los dos por separado sino la resta:
# «hasta acá podés bajar».
#
# ⚠️ El rack vive SÓLO en los escenarios BUDGET. El escenario base del módulo
# —Forecast Working 2026— tiene CERO tarifas, cero canales y cero paquetes. Por
# eso los costos y las tarifas salen de escenarios distintos, y por eso
# `escenario_tarifas` es un parámetro aparte y no una suposición.


@dataclass
class TarifaRack:
    """Una tarifa publicada, por tipo de habitación y mes."""
    room_type_id: str
    nombre: str
    orden: int
    rack: Decimal
    neto: Decimal
    pax: Decimal

    @property
    def factor_neto(self) -> Decimal:
        """Lo que queda después de la comisión del canal. 0,7970 hoy."""
        return (self.neto / self.rack) if self.rack else Decimal("0")


@dataclass
class Descuento:
    """Cuánto se puede bajar del rack antes de tocar el piso."""
    nombre: str
    orden: int
    rack: Decimal
    piso: Decimal
    descuento_max: Decimal
    # ⚠️ False = el rack publicado NO cubre el piso. No es un descuento chico:
    # es que ese tipo de habitación se vende bajo costo aun a tarifa plena.
    alcanza: bool


async def tarifas_rack(db: AsyncSession, hotel_id: str,
                       mes: int) -> list[TarifaRack]:
    """El tarifario del MÓDULO para un mes, con el nombre de cada categoría.

    ⚠️ Sale de `cfg_tarifa_rack`, **no** de los `rate_cards` del escenario, y
    esa separación es el módulo entero. Si el rack viviera en el escenario,
    editarlo movería el ingreso, el ingreso movería el costo unitario y el piso
    se movería solo — justo lo que la validación 6 existe para atrapar. Acá el
    precio sólo es el techo: mover el rack mueve el descuento, nunca el piso.

    Devuelve lista vacía si no hay tarifario, que es la verdad, no un error.
    """
    from app.models.costos_grupos import CfgTarifaRack
    from app.models.room_type_config import RoomTypeConfig

    # ⚠️ Se une por CÓDIGO. El nombre es una etiqueta renombrable; el código
    # es fijo por categoría.
    tipos = {
        r.code: r for r in (await db.execute(
            select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == hotel_id)
        )).scalars().all()
    }
    filas = (await db.execute(
        select(CfgTarifaRack).where(CfgTarifaRack.hotel_id == hotel_id,
                                    CfgTarifaRack.mes == mes)
    )).scalars().all()

    fuera: list[TarifaRack] = []
    for f in filas:
        t = tipos.get(f.room_type_code)
        fuera.append(TarifaRack(
            room_type_id=f.room_type_code,
            nombre=t.short_name if t else f.room_type_code,
            orden=t.sort_order if t else 99,
            rack=Decimal(str(f.rack or 0)),
            neto=Decimal(str(f.neto or 0)),
            pax=Decimal(str(f.pax or 0)),
        ))
    return sorted(fuera, key=lambda x: (x.orden, x.nombre))


def factor_neto_del_rack(racks: list[TarifaRack]) -> Decimal | None:
    """El factor neto que sale del propio tarifario.

    ⚠️ Existe para NO usar `compute_net_factor(channels)`, que en producción
    devuelve **9,5639** para los 36 canales del Budget Working 2027 — un factor
    mayor que 1 multiplicaría el ingreso por nueve. Hoy no se ve porque el motor
    prefiere el de las tarifas; acá se toma el mismo camino a propósito.
    """
    con_rack = [r for r in racks if r.rack > 0]
    if not con_rack:
        return None
    total_rack = sum((r.rack for r in con_rack), Decimal("0"))
    total_neto = sum((r.neto for r in con_rack), Decimal("0"))
    return (total_neto / total_rack) if total_rack else None


def descuentos(racks: list[TarifaRack], piso: Decimal) -> list[Descuento]:
    """`descuento_max = 1 − piso / rack`, por tipo de habitación.

    El piso ya viene con el gross-up puesto (fee + comisión + margen), así que
    es un precio BRUTO y se compara contra el rack sin más conversiones.

    ⚠️ El piso es UNO para todo el hotel y el rack va de $596 a $1.700. O sea
    que «le damos 40% a los grupos» puede ser holgado en una suite y estar bajo
    costo en la categoría estándar. Ese contraste es el punto de esta tabla.
    """
    fuera: list[Descuento] = []
    for r in racks:
        if r.rack <= 0:
            continue
        d = Decimal("1") - (piso / r.rack)
        fuera.append(Descuento(
            nombre=r.nombre, orden=r.orden, rack=r.rack, piso=piso,
            descuento_max=d, alcanza=d > 0,
        ))
    return fuera


# ─── Fase 8 · el grupo concreto: ensamblador, desplazamiento y semáforo ──────
#
# Hasta acá el módulo contesta «cuánto cuesta una habitación-noche». Esto
# contesta la pregunta que se hace en la mesa: *«grupo de 20 pax, 3 noches, en
# julio, a este precio — ¿lo tomo?»*.


@dataclass
class Desplazamiento:
    """Lo que el grupo hace perder al ocupar habitaciones que se habrían
    vendido igual (spec §4.5).

    ⚠️ **Se mide sobre la ocupación PROMEDIO del mes, y eso lo subestima.** Un
    mes al 73% puede tener diez días llenos: el promedio dice que sobran
    habitaciones y la realidad dice que no. Mientras el módulo no lea la
    ocupación por FECHA, este número es un piso del desplazamiento, no el
    desplazamiento.
    """
    aplica: bool
    noches_desplazadas: Decimal
    adr_esperado: Decimal
    contribucion_desplazada: Decimal
    por_habitacion_noche: Decimal
    # Lo que se usó para decidir, para poder discutirlo sin rehacer la cuenta
    ocupacion_pct: Decimal
    habitaciones_libres: Decimal
    motivo: str


def desplazamiento(meses: list[MesDeCostos], hab_noches_grupo: Decimal,
                   fee: Decimal, comision_fit: Decimal,
                   cu_hab_variable: Decimal,
                   umbral_ocupacion: Decimal = Decimal("0")) -> Desplazamiento:
    """`contribución = noches × [ADR × (1 − fee − comisión) − CU variable]`.

    ⚠️ El umbral por defecto es **0**, o sea: se calcula el desplazamiento
    FÍSICO y nada más. Subirlo es una decisión de política —«por debajo de tal
    ocupación asumimos que no desplazamos»— y esconde negocio desplazado, así
    que no se inventa un default.
    """
    disp = Decimal(sum(m.hab_disponibles for m in meses))
    ocup = sum((m.hab_ocupadas for m in meses), Decimal("0"))
    rev = sum((m.revenue_por_dept.get("REV_ROOMS", Decimal("0"))
               for m in meses), Decimal("0"))

    pct = (ocup / disp) if disp else Decimal("0")
    libres = disp - ocup
    adr = (rev / ocup) if ocup else Decimal("0")

    if pct < umbral_ocupacion:
        return Desplazamiento(
            False, Decimal("0"), adr, Decimal("0"), Decimal("0"), pct, libres,
            "ocupación por debajo del umbral de política")
    if hab_noches_grupo <= libres:
        return Desplazamiento(
            False, Decimal("0"), adr, Decimal("0"), Decimal("0"), pct, libres,
            "el grupo cabe en las habitaciones libres del período")

    noches = hab_noches_grupo - libres
    margen_fit = adr * (Decimal("1") - fee - comision_fit) - cu_hab_variable
    # ⚠️ Si el FIT que se desplaza deja MENOS que su propio costo variable, el
    # desplazamiento es una ganancia, no una pérdida. Se pone en cero: sumarlo
    # con signo negativo BAJARÍA el piso, y ningún piso puede bajar porque
    # llegue un grupo.
    contrib = max(Decimal("0"), noches * margen_fit)
    return Desplazamiento(
        True, noches, adr, contrib,
        contrib / hab_noches_grupo if hab_noches_grupo else Decimal("0"),
        pct, libres, "el grupo excede las habitaciones libres")


@dataclass
class Escalon:
    """Un costo que aparece al cruzar un umbral (spec §4.4)."""
    descripcion: str
    driver: str
    umbral: Decimal
    costo: Decimal


def escalones_aplicables(reglas: list, pax: Decimal,
                         habitaciones: Decimal) -> list[Escalon]:
    """Los escalones que el grupo cruza. El guía adicional, el vehículo que no
    cabe, el turno extra de cocina, el bloque que hay que abrir.

    ⚠️ Sin reglas cargadas devuelve lista vacía, y eso **subestima los grupos
    grandes** — que son justo los que se negocian. Quien muestre esto tiene que
    decir que la lista está vacía; un cero silencioso se lee como «no aplica».
    """
    valores = {"pax": pax, "hab_grupo": habitaciones, "pax_tour": pax}
    fuera: list[Escalon] = []
    for r in reglas:
        v = valores.get(r.driver)
        if v is None or v <= Decimal(str(r.umbral)):
            continue
        fuera.append(Escalon(r.descripcion or r.driver, r.driver,
                             Decimal(str(r.umbral)),
                             Decimal(str(r.costo_adicional))))
    return fuera


@dataclass
class CostoDelGrupo:
    """El costo de un grupo concreto y sus cuatro precios mínimos."""
    habitaciones: Decimal
    noches: Decimal
    pax: Decimal
    hab_noches: Decimal
    noches_huesped: Decimal
    # Los componentes, para poder discutir la cifra sin rehacerla
    costo_habitaciones: Decimal
    costo_fb: Decimal
    costo_tours: Decimal
    costo_transporte: Decimal
    costo_spa: Decimal
    costo_amenidades: Decimal
    costo_escalones: Decimal
    overhead: Decimal
    variable: Decimal
    propio: Decimal
    costo_total: Decimal
    desplazamiento: Desplazamiento
    escalones: list[Escalon]
    # Precio mínimo por pax por NOCHE, contra cada piso
    minimo_pax_noche: dict[str, Decimal]
    minimo_pax_estadia: dict[str, Decimal]
    ingreso_minimo: dict[str, Decimal]
    # ⚠️ True = el Piso 1 sale IGUAL al Piso 2 porque falta la clasificación
    # fijo/variable. Dos pisos idénticos se leen como coincidencia; no lo son.
    marginal_estimado: bool
    # ⚠️ Qué partes son PRORRATEO y no medición. La pantalla las tiene que
    # nombrar: un costo prorrateado que se presenta como medido convierte un
    # supuesto en un compromiso contractual.
    prorrateados: list[str]


def _prorrateados(cu: dict, reglas: list, marginal_estimado: bool) -> list[str]:
    """Qué componentes son prorrateo y no medición (spec §8, huecos 5 a 7)."""
    fuera = []
    if marginal_estimado:
        # ⚠️ Lo primero de la lista a propósito: cuando esto pasa, el Piso 1
        # sale IDÉNTICO al Piso 2, y dos pisos iguales se leen como que el
        # modelo los calculó y coincidieron. No coincidieron: falta el dato.
        fuera.append(
            "Piso 1: NO está medido — falta la clasificación fijo/variable, "
            "así que cae al costo propio y sale igual al Piso 2")
    if cu.get("spa_propio_por_huesped", Decimal("0")) > 0:
        fuera.append("spa: prorrateado sobre noches-huésped — faltan tratamientos")
    if cu.get("tours_propio_por_huesped", Decimal("0")) > 0:
        fuera.append("tours: prorrateado sobre noches-huésped — faltan salidas y pax por tour")
    if cu.get("transp_propio_por_ocupada", Decimal("0")) > 0:
        fuera.append("transporte: prorrateado sobre habitación-noche — faltan vehículo y ruta")
    if not reglas:
        fuera.append("escalones: NO hay reglas cargadas — los grupos grandes salen subestimados")
    # ⚠️ Siempre, no sólo cuando da cero. Medido contra producción: al grano
    # MENSUAL el desplazamiento no se activa nunca en Corcovado — el mes más
    # lleno del Forecast 2026 (febrero, 81,4%) deja 156 habitación-noches
    # libres contra las 30 que pide un grupo de 10 habitaciones por 3 noches.
    # Un «$0 de desplazamiento» presentado como medición diría que el grupo no
    # desplaza nada, cuando lo que pasa es que el promedio del mes esconde los
    # días llenos. El dato diario existe: está en On the Books.
    fuera.append(
        "desplazamiento: medido sobre el promedio MENSUAL — al grano mensual "
        "no se activa nunca; hace falta la ocupación por fecha (On the Books)")
    return fuera


def ensamblar_grupo(meses: list[MesDeCostos], comp: dict, par: dict,
                    comision: Decimal, habitaciones: Decimal, noches: Decimal,
                    pax: Decimal, reglas_escalon: list | None = None,
                    amenidades_usd: Decimal = Decimal("0"),
                    ciclo: list[MesDeCostos] | None = None,
                    umbral_desplazamiento: Decimal = Decimal("0"),
                    meses_del_grupo: list[MesDeCostos] | None = None) -> CostoDelGrupo:
    """El ensamblador del spec §4.6, con desplazamiento y escalones.

    ⚠️ `meses` da los COSTOS UNITARIOS (la temporada entera, para no promediar
    promedios) y `meses_del_grupo` da el DESPLAZAMIENTO (sólo las fechas del
    grupo). Medir el desplazamiento contra la temporada completa lo apaga
    siempre: 30 habitación-noches contra las 3.258 libres de una temporada
    nunca desplazan nada, y el número saldría en cero sin que sea verdad.
    """
    trat = par.get("tratamiento_mes_cerrado", "B")
    abiertos = [m for m in meses if m.dias_abiertos > 0] if trat == "B" else meses
    cu = costos_unitarios(abiertos or meses, comp)
    fee = Decimal(par.get("management_fee_pct", "0.03"))
    margen = Decimal(par.get("margen_protegido_pct", "0.15"))
    oh_unit = absorcion(meses, par.get("metodo_absorcion", "M2"), trat, ciclo)

    hab_noches = habitaciones * noches
    noches_huesped = pax * noches

    c_hab = cu["hab_propio_por_ocupada"] * hab_noches
    c_fb = cu["fb_propio_por_huesped"] * noches_huesped
    c_tours = cu["tours_propio_por_huesped"] * noches_huesped
    c_transp = cu["transp_propio_por_ocupada"] * hab_noches
    c_spa = cu["spa_propio_por_huesped"] * noches_huesped
    oh = oh_unit * hab_noches

    esc = escalones_aplicables(reglas_escalon or [], pax, habitaciones)
    c_esc = sum((e.costo for e in esc), Decimal("0"))

    # ⚠️ El variable de Habitaciones. Mientras falte la clasificación
    # fijo/variable cae al costo propio completo, igual que en el Piso 1: un
    # marginal inventado regala negocio.
    var_total = _suma({c: v for m in abiertos for c, v in m.costo_por_dept.items()},
                      comp.get(("ROOMS", "venta"), []))
    ocup_tot = sum((m.hab_ocupadas for m in abiertos), Decimal("0"))
    marginal_estimado = not (ocup_tot and var_total > 0)
    cu_var = cu["hab_propio_por_ocupada"] if marginal_estimado \
        else var_total / ocup_tot

    desp = desplazamiento(meses_del_grupo or meses, hab_noches, fee, comision,
                          cu_var, umbral_desplazamiento)

    variable = cu_var * hab_noches + c_fb + c_tours + c_transp + c_spa
    propio = c_hab + c_fb + c_tours + c_transp + c_spa + amenidades_usd + c_esc
    total = propio + oh

    def minimo(costo: Decimal, m: Decimal) -> Decimal:
        return gross_up(costo + desp.contribucion_desplazada, fee, comision, m)

    ingreso = {
        "marginal": minimo(variable + amenidades_usd + c_esc, Decimal("0")),
        "departamental": minimo(propio, Decimal("0")),
        "integral": minimo(total, Decimal("0")),
        "con_margen": minimo(total, margen),
    }
    pn = pax * noches
    return CostoDelGrupo(
        habitaciones=habitaciones, noches=noches, pax=pax,
        hab_noches=hab_noches, noches_huesped=noches_huesped,
        costo_habitaciones=c_hab, costo_fb=c_fb, costo_tours=c_tours,
        costo_transporte=c_transp, costo_spa=c_spa,
        costo_amenidades=amenidades_usd, costo_escalones=c_esc,
        overhead=oh, variable=variable, propio=propio, costo_total=total,
        desplazamiento=desp, escalones=esc,
        ingreso_minimo=ingreso,
        minimo_pax_noche={k: (v / pn if pn else Decimal("0"))
                          for k, v in ingreso.items()},
        minimo_pax_estadia={k: (v / pax if pax else Decimal("0"))
                            for k, v in ingreso.items()},
        marginal_estimado=marginal_estimado,
        prorrateados=_prorrateados(cu, reglas_escalon or [], marginal_estimado),
    )


# El semáforo del spec §4.9. Las zonas coinciden con la matriz que ya aprobó la
# Junta; sólo cambia la unidad de porcentaje a dólares.
ZONAS = {
    "verde": "Gerente departamental / Comercial",
    "amarilla": "Finance Controller + Gerente General",
    "roja": "GG + Finanzas, con capacidad ociosa documentada y sin desplazamiento",
    "prohibida": "No autorizado",
}


def semaforo(ingreso_propuesto: Decimal, minimos: dict[str, Decimal]) -> str:
    """Verde ≥ Piso 4 · Amarilla ≥ Piso 3 · Roja ≥ Piso 1 · Prohibida debajo."""
    if ingreso_propuesto >= minimos["con_margen"]:
        return "verde"
    if ingreso_propuesto >= minimos["integral"]:
        return "amarilla"
    if ingreso_propuesto >= minimos["marginal"]:
        return "roja"
    return "prohibida"
