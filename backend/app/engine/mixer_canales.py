# -*- coding: utf-8 -*-
"""El mixer: de los 7 canales comerciales se derivan los demás.

**La idea del owner (2026-08-14).** «El primero es planteamiento general, y
después hay que hacer un mixer para derivar las otras.»

Es la salida al problema de las tres listas. En vez de mantener tres tablas que
se desincronizan —y ya se habían desincronizado—, **una sola se planifica y las
otras se calculan**:

    7 canales comerciales  (mix % + comisión %)     <-- ACÁ se planifica
              |
              +--> 3 canales de comisión (TA/OTA/DIRECT)  -> Net Factor -> P&L
              +--> 5 canales del PMS                      -> comparar con Opera

**La derivación.** Cada canal comercial rueda a un canal de comisión. El mix del
destino es la SUMA de los mixes que caen ahí; su comisión es el **promedio
ponderado por mix** —no el simple—, porque lo que se paga depende de cuánto
volumen pasa por cada uno.

⚠️ **Lo que el mixer destapa.** Hoy `SalesChannelConfig` tiene `DIRECT` con
comisión **0%**: FinPlan cree que la venta directa no cuesta nada. El cuadro del
owner dice que paga entre 7% y 10%. Como el Net Factor multiplica el ingreso de
habitaciones de todo el presupuesto, esa diferencia mueve el neto del año — y
nada la delataba, porque cada tabla se veía razonable por su lado.
"""
from dataclasses import dataclass
from decimal import Decimal

#: ⚠️ **YA NO SE USA PARA DECIDIR.** Queda solo como el mapa del que salió el
#: backfill de la migración 120, para poder auditar de dónde vino cada destino.
#:
#: Era el «rueda a»: un diccionario de seis entradas, con `DIRECT` de default.
#: Un sub-canal nuevo cuya `entrada` no estuviera acá **caía a DIRECT en
#: silencio** — 9,27% de comisión en vez del 30% de TA, o sea ingreso de MÁS. No
#: fallaba: facturaba mal. Hoy el destino es la columna
#: `canales_comerciales.rueda_a`, que se elige y se ve.
ENTRADA_A_COMISION = {
    "Travel Agent": "TA",
    "OTA": "OTA",
    "Direct Client": "DIRECT",
    "Website": "DIRECT",
    "INHOUSE": "DIRECT",
    "": "DIRECT",
}

#: Respaldo de los destinos cuando nadie pasó la lista (pruebas del motor puro).
#: La lista de verdad es la tabla `canales_comision` — por eso `derivar()` la
#: recibe: para que agregar un cuarto canal sea un INSERT y no un despliegue.
DERIVADOS = ("TA", "OTA", "DIRECT")


def destino_de(canal) -> str:
    """A qué canal de comisión rueda un sub-canal.

    Sale de `rueda_a`. Si la fila todavía no lo tiene —solo puede pasar con un
    objeto viejo en memoria, la columna es NOT NULL— se cae al diccionario para
    no romper, pero eso ya no es el camino normal.
    """
    directo = getattr(canal, "rueda_a", "") or ""
    if directo:
        return directo
    return ENTRADA_A_COMISION.get(getattr(canal, "entrada", "") or "", "DIRECT")

ZERO = Decimal("0")
UNO = Decimal("1")


@dataclass(frozen=True)
class CanalResuelto:
    """Un canal comercial con el mix y la comisión que le tocan en ese
    escenario y ese mes, después de la cascada."""
    code: str
    nombre: str
    entrada: str
    mix_pct: Decimal
    comision_pct: Decimal
    #: De dónde salió el valor: "base", "escenario" o "mes". Sirve para que la
    #: pantalla muestre qué se heredó y qué alguien escribió a mano.
    origen: str = "base"


@dataclass(frozen=True)
class CanalDerivado:
    channel: str
    mix_pct: Decimal
    commission_pct: Decimal

    @property
    def aporte_neto(self) -> Decimal:
        return self.mix_pct * (UNO - self.commission_pct)


def _dec(v) -> Decimal:
    return Decimal(str(v or 0))


def resolver(base: list, overrides: list, month: int = 0) -> list[CanalResuelto]:
    """La cascada: mes puntual -> anual del escenario -> base del canal.

    `base` son los `CanalComercial` (el mix que aplica cuando nadie dijo otra
    cosa). `overrides` son los `CanalMixEscenario` de UN escenario. `month=0`
    pide el valor anual.

    Un escenario sin nada guardado devuelve el base tal cual — que es
    justamente lo que hace que un escenario nuevo nazca bien.
    """
    anual = {o.code: o for o in overrides if o.month == 0}
    mensual = {o.code: o for o in overrides if o.month == month} if month else {}

    out = []
    for c in base:
        mix, com, origen = _dec(c.mix_pct), _dec(c.comision_pct), "base"
        if c.code in anual:
            mix, com, origen = _dec(anual[c.code].mix_pct), _dec(anual[c.code].comision_pct), "escenario"
        if c.code in mensual:
            mix, com, origen = _dec(mensual[c.code].mix_pct), _dec(mensual[c.code].comision_pct), "mes"
        out.append(CanalResuelto(
            code=c.code, nombre=getattr(c, "nombre", "") or c.code,
            entrada=getattr(c, "entrada", "") or "",
            mix_pct=mix, comision_pct=com, origen=origen))
    return out


def derivar(canales: list, destinos: list[str] | None = None) -> list[CanalDerivado]:
    """De los sub-canales comerciales a los canales de comisión.

    `canales` son objetos con `.mix_pct`, `.comision_pct` y `.rueda_a`.
    `destinos` es la lista de canales de comisión (la tabla `canales_comision`);
    si no viene, se usan los tres de siempre.

    ⚠️ **Un destino que no esté en la lista igual sale**, al final. Antes esto
    iteraba una constante de tres y **descartaba en silencio** lo que rodara a
    otro lado: agregar un canal cuarto habría hecho desaparecer su mix del
    derivado, bajando la suma por debajo de 100% sin que nada avisara.
    """
    acum: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for c in canales:
        acum.setdefault(destino_de(c), []).append(
            (_dec(getattr(c, "mix_pct", 0)), _dec(getattr(c, "comision_pct", 0))))

    orden = list(destinos) if destinos else list(DERIVADOS)
    # Lo que rueda a un destino que no está en la lista no se pierde: se agrega
    # al final para que se VEA en pantalla y en la suma.
    orden += [d for d in acum if d not in orden]

    out = []
    for destino in orden:
        partes = acum.get(destino, [])
        mix = sum((m for m, _ in partes), ZERO)
        # ⚠️ Promedio PONDERADO por mix, no simple. Con el simple, un canal
        # marginal con comisión alta pesaría igual que el que trae el volumen —
        # y la comisión derivada saldría más alta de lo que se paga.
        com = (sum((m * c for m, c in partes), ZERO) / mix) if mix else ZERO
        out.append(CanalDerivado(destino, mix, com))
    return out


def net_factor(derivados: list[CanalDerivado]) -> Decimal:
    """`Σ(mix × (1 − comisión))`. La misma fórmula que ya usa el motor
    (`sales_channel_config.compute_net_factor`), para que el mixer no invente
    otra manera de calcular lo mismo."""
    return sum((d.aporte_neto for d in derivados), ZERO)


def suma_del_mix(canales: list) -> Decimal:
    return sum((_dec(getattr(c, "mix_pct", 0)) for c in canales), ZERO)


def mix_cierra(canales: list, tolerancia: Decimal = Decimal("0.0001")) -> bool:
    """El mix tiene que dar 100%. Si no, el Net Factor sale de una base que no es
    el total y el error se propaga a todo el ingreso de habitaciones."""
    return abs(suma_del_mix(canales) - UNO) <= tolerancia


# ── A qué escenarios manda el mixer ─────────────────────────────────────────
#
# Owner (2026-08-14): «hay que hacerle para todas las versiones, versión
# forecast, todas las versiones que tienen auxiliares... se supone que no voy a
# subir budget final 2026, porque ya es lo que es. Pero a partir de enero 2027,
# el forecast, el budget, todo lo que se construye ahí, como auxiliar, tiene que
# dar con esos parámetros.»
#
#: Desde este año el mixer manda. Antes es historia y no se reescribe.
DESDE_EL_ANO = 2027

#: Los que se CONSTRUYEN. Un ACTUAL no se planifica: registra lo que pasó, y su
#: net factor es el que hubo, no el que se quisiera.
TIPOS_QUE_SE_CONSTRUYEN = ("BUDGET", "FORECAST")


def gobierna(scenario) -> tuple[bool, str]:
    """¿El mixer manda sobre este escenario? Devuelve `(sí, por qué no)`.

    Se devuelve el motivo y no solo el booleano para que la pantalla pueda
    mostrar la lista COMPLETA con el porqué de cada exclusión. Un escenario que
    desaparece de la lista se lee como «no existe»; uno que aparece diciendo por
    qué quedó afuera se puede discutir.
    """
    # ⚠️ Se devuelve la CLAVE del motivo y sus datos, no la frase. El motor no
    # se entera del idioma (`tests/test_i18n_locale.py`); quien contesta la
    # petición la resuelve con `app/textos.py`. Misma regla que el `line_code`.
    if getattr(scenario, "is_locked", False):
        return False, "mixer.motivo_enllavado", {}
    if scenario.type not in TIPOS_QUE_SE_CONSTRUYEN:
        return False, "mixer.motivo_tipo", {"tipo": scenario.type}
    if scenario.year < DESDE_EL_ANO:
        return False, "mixer.motivo_anio", {"anio": scenario.year, "desde": DESDE_EL_ANO}
    return True, "", {}
