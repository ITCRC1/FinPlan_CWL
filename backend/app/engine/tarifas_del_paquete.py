# -*- coding: utf-8 -*-
"""Deriva las tarifas del Revenue Checkbook desde la experiencia base.

## Por qué existe

Owner, 2026-10-22, señalando los recuadros del checkbook: *«llena esto en forma
automática de la vista anterior al precio neto»*.

Los nueve recuadros del checkbook cargaban de `seed_data/<HOTEL>/driver_rates.json`
— un archivo FIJO POR HOTEL. Las inclusiones del paquete, en cambio, viven por
ESCENARIO (`pkg_experience_items`). Dos fuentes para el mismo precio, y una de
ellas no sabe de escenarios: en el `BUDGET Working 2027` la semilla decía Tours
342 y la pantalla mostraba 0, porque alguien lo había editado a mano.

Acá el paquete del escenario manda y la semilla queda de respaldo.

## Lo que esta función NO hace

**No toca el P&L.** Con `revenue_source = 'drivers'` —que es como están los seis
presupuestos 2027— el P&L calcula con `package_configs` (108/101/35/28), no con
estos recuadros ni con el paquete. Esto alinea la calculadora de la pantalla con
el paquete; que esas tarifas lleguen al estado de resultados es otra decisión y
otro cambio.

## El precio neto

Los recuadros guardan el **rack**, porque `fillFromDrivers` multiplica por el
factor neto del MES. Guardar el neto ahí lo descontaría dos veces. Por eso se
devuelven los dos: `tarifas` (rack, lo que va al recuadro) y `neto` (lo que la
pantalla muestra debajo, que es el precio que el owner pidió ver).

El neto NO es «rack × factor» para todas: el Sustainability Fee no comisiona,
así que su neto es su rack. Ver `CAJAS`.

## ⚠️ Una inclusión que no mapea NO vale cero

El `es_base` del modelo nació porque antes se buscaba la experiencia por su
nombre y renombrarla cambiaba el tab sin avisar. Acá pasa lo mismo un nivel más
abajo: las inclusiones se reconocen por su texto. Si alguien renombra «Tour San
Pedrillo» a algo que no diga «tour», la caja de Tours quedaría en cero y el
checkbook se llenaría con menos ingreso sin que nada chille.

Por eso todo lo que tiene precio y está habilitado pero no encuentra caja sale
en `sin_casa`, y la pantalla lo muestra. Un renombre se ve; no se traga.
"""
from __future__ import annotations

import unicodedata
from decimal import Decimal

#: A qué recuadro del checkbook va cada inclusión, en qué unidad se espera, y
#: si el canal le cobra comisión.
#:
#: El orden importa: la primera que coincide gana, así que lo más específico va
#: antes. «sustainability» antes que nada que pudiera comerse la palabra.
#:
#: ⚠️ **El Sustainability Fee NO lleva comisión.** Owner, 2026-10-22: *«al
#: sustainability fee no se le aplica descuento ya que no paga comisión, se
#: cobra en el hotel»*. Lo paga el huésped en recepción, así que la agencia no
#: toca esa plata y el factor neto no le aplica. Coincide con el motor, que ya
#: lo tiene `is_commissionable=False` en `package_configs`.
CAJAS: list[tuple[str, tuple[str, ...], str, bool]] = [
    # (caja del checkbook, palabras que la identifican, unidad, ¿comisiona?)
    ("sust_rate", ("sustainab", "sosteni"), "per pax/night", False),
    ("transport", ("transport", "traslado"), "per pax/stay", True),
    ("tours", ("tour", "excursi"), "per pax/stay", True),
    ("food", ("full pension", "pension completa", "meal", "comida",
              "alimentacion", "full board"), "per pax/night", True),
]

#: Las cajas a las que el canal NO les cobra comisión: su neto es su rack.
SIN_COMISION = {caja for caja, _p, _u, comisiona in CAJAS if not comisiona}

#: Las cajas que SUMAN varias inclusiones. Tours son dos (San Pedrillo + Caño) y
#: el recuadro pide el total por estadía; las demás son una sola.
ACUMULAN = {"tours"}


def _plano(s: str) -> str:
    """Minúsculas y sin tildes, para que «Alimentación» case con «alimentacion»."""
    sin = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in sin if not unicodedata.combining(c)).lower().strip()


def _caja_de(inclusion: str) -> tuple[str, str] | None:
    """Devuelve (caja, unidad esperada) o None si esa inclusión no tiene casa."""
    txt = _plano(inclusion)
    for caja, palabras, unidad, _comisiona in CAJAS:
        if any(p in txt for p in palabras):
            return caja, unidad
    return None


#: Cuánto del Sustainability Fee se cobra de verdad.
#:
#: Owner, 2026-10-22: *«el sustainability fee se calcula al 90 % ya que algunas
#: personas no pagan entonces le hago un descuento»*.
#:
#: ⚠️ Es un supuesto de COBRO, no un precio. La tarifa sigue siendo $30,97; lo
#: que cambia es cuánta se recauda. Por eso no vive en la tabla de inclusiones
#: —ahí el precio tiene que ser el precio— sino acá, y el checkbook lo muestra
#: en su propio recuadro («% que no paga»). El valor sale de la semilla del
#: hotel, que es donde el checkbook ya lo tenía; esta constante es el respaldo.
#:
#: Va en PORCENTAJE (10 = 10 %), igual que el recuadro de la pantalla y que
#: `driver_rates.json`. Ver `cobrado_de_sustainability`.
SUST_NO_PAGA_DEFECTO = Decimal("10")


def cobrado_de_sustainability(no_paga: Decimal | float | None = None) -> Decimal:
    """La fracción del fee que se recauda: 1 − el % que no paga.

    `no_paga` va en **porcentaje**: 10 son diez por ciento.

    ⚠️ **Una fracción se rechaza, no se interpreta.** Aceptar las dos formas
    parece cómodo hasta que llega el borde: con la regla «si es menor que 1 es
    fracción», un `0.5` sería 50 % y un `1.5` sería 1,5 % — dos vecinos con
    significados a cien veces de distancia, y los dos resultados se ven
    plausibles. Acá un valor entre 0 y 1 es ambiguo y se dice en voz alta.
    """
    p = Decimal(str(SUST_NO_PAGA_DEFECTO if no_paga is None else no_paga))
    if 0 < p < 1:
        raise ValueError(
            f"% que no paga ambiguo: {no_paga!r}. Va en porcentaje (10 = 10 %); "
            f"para {p * 100:g} % escriba {p * 100:g}.")
    if not (0 <= p < 100):
        raise ValueError(f"% que no paga fuera de rango: {no_paga!r}")
    return Decimal("1") - p / Decimal("100")


def a_tarifas_del_motor(
    derivado: dict, no_paga: Decimal | float | None = None,
) -> dict[str, Decimal]:
    """Pasa las tarifas del paquete a lo que el motor del P&L consume.

    El motor (`package_configs`) guarda TODO **por pax-noche**. El paquete tiene
    inclusiones por estadía. La conversión es ÷ noches de la experiencia:

        Tours      342 / estadía ÷ 3 noches = 114,00 / pax-noche
        Transporte 150 / estadía ÷ 3 noches =  50,00 / pax-noche
        Food       126 / pax-noche          = 126,00  (ya está en la unidad)
        Sustain.    30,97 × 90 %            =  27,873 (ver abajo)

    ⚠️ **El 90 % del Sustainability se mete en la tarifa del motor** porque el
    motor no tiene dónde guardar un supuesto de cobro: su fórmula es
    `pax-noche × tarifa` y nada más. Mientras eso sea así, el número que guarda
    es *lo que se recauda*, no *lo que se cobra*. Queda dicho acá y en el valor
    que se escribe, para que nadie lo lea como un precio y lo «corrija» a 30,97.

    ⚠️ **El Sustainability no comisiona.** El motor ya lo sabe
    (`is_commissionable=False`); esta función no toca esa bandera.
    """
    t = derivado.get("tarifas") or {}
    noches = Decimal(str(derivado.get("nights") or 0)) or Decimal("1")
    fuera: dict[str, Decimal] = {}
    if t.get("food") is not None:
        fuera["FOOD"] = Decimal(str(t["food"]))
    if t.get("tours") is not None:
        fuera["ACTIVITIES"] = (Decimal(str(t["tours"])) / noches
                               ).quantize(Decimal("0.0001"))
    if t.get("transport") is not None:
        fuera["TRANSPORT"] = (Decimal(str(t["transport"])) / noches
                              ).quantize(Decimal("0.0001"))
    if t.get("sust_rate") is not None:
        fuera["SUSTAINABILITY"] = (
            Decimal(str(t["sust_rate"])) * cobrado_de_sustainability(no_paga)
        ).quantize(Decimal("0.0001"))
    return fuera


async def experiencias_del_escenario(session, scenario_id: str) -> list[dict]:
    """Las experiencias guardadas, en la forma que `tarifas_del_paquete` espera.

    Lee la BD directamente y **no cae a la semilla** si no hay ninguna. El
    endpoint sí sugiere una plantilla para que la pantalla no salga en blanco;
    acá una sugerencia sería una tarifa inventada escribiéndose sola en el
    motor.
    """
    from sqlalchemy import select

    from app.models.package_menu import PkgExperience, PkgExperienceItem

    exps = (await session.execute(
        select(PkgExperience).where(PkgExperience.scenario_id == scenario_id)
        .order_by(PkgExperience.sort_order))).scalars().all()
    if not exps:
        return []
    items = (await session.execute(
        select(PkgExperienceItem).where(
            PkgExperienceItem.experience_id.in_([e.id for e in exps]))
        .order_by(PkgExperienceItem.sort_order))).scalars().all()
    por_exp: dict[str, list] = {}
    for it in items:
        por_exp.setdefault(it.experience_id, []).append(it)
    # Si ninguna trae la marca (dato anterior a `es_base`), vale la primera —
    # el mismo criterio del endpoint, para que no muestren cosas distintas.
    hay_base = any(getattr(e, "es_base", False) for e in exps)
    return [
        {"name": e.name, "nights": e.nights, "days": e.days,
         "es_base": bool(getattr(e, "es_base", False)) if hay_base else (i == 0),
         "items": [{"inclusion": it.inclusion, "unit": it.unit,
                    "unit_price": it.unit_price, "enabled": it.enabled}
                   for it in por_exp.get(e.id, [])]}
        for i, e in enumerate(exps)
    ]


async def sincronizar_tarifas_del_motor(session, scenario) -> list[dict]:
    """Baja las tarifas del paquete a `package_configs`, que es lo que calcula.

    ## El desfase que esto cierra

    Owner, 2026-10-22: *«asegúrate que el checkbook calcule en función de estos
    rates»*.

    Había **tres** lugares con la tarifa del mismo tour y ninguno hablaba con
    los otros:

        pkg_experience_items   San Pedrillo 168 + Caño 174 = 342 / estadía
        driver_rates.json      tours 342   (semilla FIJA POR HOTEL)
        package_configs        ACTIVITIES 101 / pax-noche   <- el único que calcula

    El 101 venía del `Budget2026_Revenue_CORCO.xlsx` (Snorkeling $48 + PN Walk
    $53) y los seis presupuestos 2027 lo heredaron sin que nadie lo revisara,
    mientras las tarifas de habitación subían 20,9 %. Nada lo señalaba: el P&L
    cuadraba, la pantalla mostraba 342, y las dos cosas eran ciertas en su
    propio archivo.

    ## Por qué corre en el RECÁLCULO y no solo al guardar

    Primero lo puse solo en el guardado del paquete. Owner, el mismo día,
    mirando la pantalla: *«no hay donde guardar acá»* — y tenía razón: el
    guardado es automático y el botón queda apagado cuando nada cambió. Un
    escenario cuyo paquete ya estaba escrito no tenía forma de llegar al motor
    sin hacerle una edición falsa.

    Acá corre en las dos partes, que es la misma regla que ya sigue
    `sincronizar_ingreso_al_checkbook`: el sub-mayor y el motor quedan iguales
    al modelo cada vez que el escenario se recalcula, sin depender de que
    alguien se acuerde de apretar algo.

    ⚠️ **Solo donde el paquete es el insumo.** Un ACTUAL trae su número de un
    archivo; reescribirle las tarifas no cambia su P&L pero le ensucia los
    auxiliares, que es exactamente el destrozo invisible que el recálculo ya
    evita preguntando por el ORIGEN y no por el tipo.

    ⚠️ **Una línea sin tarifa NO se pone en cero.** Si una inclusión se renombra
    y cae en `sin_casa`, su componente queda intacto. Escribir cero la borraría
    del presupuesto y el total seguiría viéndose plausible.

    Devuelve qué cambió, para que el recálculo pueda avisarlo: una tarifa que se
    mueve sola y en silencio es el modo de falla más caro que tiene el sistema.
    """
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.package_config import PackageConfig
    from app.seed_data import semilla

    exps = await experiencias_del_escenario(session, scenario.id)
    derivado = tarifas_del_paquete(exps)
    if not derivado.get("disponible"):
        return []
    # El «% que no paga» vive en la semilla del hotel, que es donde el checkbook
    # ya lo tenía. Sin semilla manda el respaldo del módulo.
    no_paga = ((semilla("driver_rates") or {}).get("tarifas") or {}).get("sust_non_pay")
    nuevas = a_tarifas_del_motor(derivado, no_paga)
    if not nuevas:
        return []

    filas = {r.component: r for r in (await session.execute(
        select(PackageConfig).where(PackageConfig.scenario_id == scenario.id)
    )).scalars().all()}

    movidas: list[dict] = []
    for comp, tarifa in nuevas.items():
        fila = filas.get(comp)
        if fila is None:
            session.add(PackageConfig(
                id=str(_uuid.uuid4()), scenario_id=scenario.id,
                hotel_id=scenario.hotel_id, component=comp,
                rate_per_pax_night=tarifa,
                # El Sustainability no comisiona: lo paga el huésped en el hotel.
                is_commissionable=(comp != "SUSTAINABILITY")))
            movidas.append({"componente": comp, "antes": None,
                            "despues": float(tarifa)})
            continue
        antes = Decimal(str(fila.rate_per_pax_night or 0))
        if antes != tarifa:
            fila.rate_per_pax_night = tarifa
            movidas.append({"componente": comp, "antes": float(antes),
                            "despues": float(tarifa)})
    await session.flush()
    return movidas


def tarifas_del_paquete(
    experiencias: list[dict], factor_neto: Decimal | float | None = None,
) -> dict:
    """Saca las tarifas del checkbook de la experiencia marcada `es_base`.

    `experiencias` es la lista que devuelve `get_package_components`: cada una
    con `name`, `nights`, `days`, `es_base` e `items`.

    Devuelve siempre la misma forma; `disponible=False` cuando no hay de dónde
    sacarlas, para que la pantalla no tenga que adivinar si el cero es un cero
    o una ausencia.
    """
    vacio = {"disponible": False, "experiencia": None, "nights": 0, "days": 0,
             "tarifas": {}, "neto": {}, "detalle": [], "sin_casa": [],
             "unidad_rara": [], "factor_neto": float(factor_neto or 0)}
    if not experiencias:
        return vacio

    # La marcada; si ninguna la trae (dato viejo), vale la primera — el mismo
    # criterio que usa `get_package_components`, para que las dos pantallas
    # nunca muestren experiencias distintas.
    base = next((e for e in experiencias if e.get("es_base")), experiencias[0])
    items = base.get("items") or []
    if not items:
        return {**vacio, "experiencia": base.get("name")}

    tarifas: dict[str, Decimal] = {}
    detalle: dict[str, list[str]] = {}
    sin_casa: list[str] = []
    unidad_rara: list[dict] = []

    for it in items:
        precio = it.get("unit_price")
        if precio in (None, ""):
            continue                      # Lodging viene sin precio: entra por el rack
        precio = Decimal(str(precio))
        if not precio:
            continue                      # cero explícito: no es una tarifa
        if not it.get("enabled", True):
            continue                      # apagada en el Excel del paquete

        casa = _caja_de(it.get("inclusion", ""))
        if casa is None:
            sin_casa.append(it.get("inclusion", ""))
            continue
        caja, unidad_esperada = casa

        # La unidad decide contra qué se multiplica. Si no es la que el recuadro
        # espera, el monto sale mal por un factor de `nights` y nada lo diría:
        # se avisa en vez de aceptarlo.
        unidad = _plano(it.get("unit", ""))
        if unidad and _plano(unidad_esperada) not in unidad:
            unidad_rara.append({"inclusion": it.get("inclusion", ""),
                                "unidad": it.get("unit", ""),
                                "esperada": unidad_esperada, "caja": caja})

        if caja in ACUMULAN:
            tarifas[caja] = tarifas.get(caja, Decimal("0")) + precio
        else:
            tarifas[caja] = precio
        detalle.setdefault(caja, []).append(it.get("inclusion", ""))

    if not tarifas:
        return {**vacio, "experiencia": base.get("name"),
                "sin_casa": sin_casa}

    nf = Decimal(str(factor_neto or 0))
    # El neto de lo que NO comisiona es su propio rack: el huésped lo paga en
    # recepción y la agencia no toca esa plata. Ver `SIN_COMISION`.
    neto = {k: float(((v if k in SIN_COMISION else v * nf)
                      ).quantize(Decimal("0.01"))) for k, v in tarifas.items()}

    return {
        "disponible": True,
        "experiencia": base.get("name"),
        "nights": int(base.get("nights") or 0),
        "days": int(base.get("days") or 0),
        "factor_neto": float(nf),
        "tarifas": {**{k: float(v) for k, v in tarifas.items()},
                    "nights_per_stay": int(base.get("nights") or 0) or 1},
        "neto": neto,
        "detalle": [{"caja": k, "inclusiones": v,
                     "rack": float(tarifas[k]), "neto": neto[k]}
                    for k, v in sorted(detalle.items())],
        "sin_casa": sin_casa,
        "unidad_rara": unidad_rara,
    }
