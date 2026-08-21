# -*- coding: utf-8 -*-
"""Motor del punto de equilibrio. PURO: no toca la base ni sabe de HTTP.

Spec: `FINPLAN_BREAK_EVEN.md` §3. Se mantiene puro por la regla de `CLAUDE.md`
(«el engine/ es puro Python sin dependencias de UI»), y acá esa regla paga doble:
la prueba de aceptación del módulo son nueve números exactos, y poder correrlos
sin base de datos es lo que permite verificarlos.

## La resolución, que es donde se pierde plata en silencio (§2.6)

Para cada monto del P&L se busca su regla en este orden:

1. **exacta** — `(dept_code, account)`
2. **por línea** — `(pl_line)` con `map_source = 'LINEA'`
3. **ninguna** → el monto toma el **criterio por defecto: 100% FIJO**, y se
   registra en `sin_clasificar` para que se vea. Nunca se asume variable y nunca
   falla en silencio.

⚠️ **Ojo con el nombre.** El owner lo corrigió (2026-08-17): *«si al menos tiene
fijo 100% entonces ya tiene un criterio, no sin clasificar»*. Y es exacto — esos
montos **están adentro del cálculo**, contados como fijos; lo que falta no es la
clasificación sino que alguien la confirme. El campo se sigue llamando
`sin_clasificar` porque así lo nombra el spec (`be_unclassified`), pero **la
pantalla dice «Por defecto: 100% fijo»**, que es lo que de verdad pasa.

El orden 3 no es cortesía: el catálogo GL crece, y una cuenta nueva asumida
variable **infla el margen de contribución y baja artificialmente el
equilibrio** — o sea, el error se ve como una buena noticia.

## Las guardas (§3.4)

Ninguna devuelve cero disfrazado de respuesta:

* `CM% ≤ 0` → las métricas de equilibrio en `None` y un motivo escrito. Un cero
  ahí se lee como «el equilibrio es cero», que es lo contrario de lo que pasa.
* `REV = 0` → ratios en 0, sin división por cero.
* `ROOMS_AVAILABLE = 0` → métricas de habitaciones en `None`, no en cero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")

#: Debajo de este porcentaje del ingreso, el resultado se considera
#: **indistinguible de cero** para el apalancamiento operativo. No es un umbral
#: de tolerancia contable: es el punto donde `CM / EBT` deja de describir nada
#: porque el denominador es ruido. 1% del ingreso deja intacto el caso de la
#: prueba de aceptación (EBT = 5,7% del ingreso → 11,6x) y saca los dos
#: escenarios que hoy están pegados al equilibrio.
UMBRAL_EBT_DESPRECIABLE = Decimal("0.01")

# ⚠️ CLAVES, no frases. El motor no se entera del idioma
# (`tests/test_i18n_locale.py`): el texto vive en `app/textos.py` y lo resuelve
# quien contesta la petición. Ver `break_even_api._motivo()`.
MSG_APALANCAMIENTO_EN_EL_EQUILIBRIO = "be.apalancamiento_en_el_equilibrio"
MSG_APALANCAMIENTO_RUIDO = "be.apalancamiento_ruido"
UNO = Decimal("1")

#: Sin esto, una llamada podría calcular sobre la versión equivocada — y un
#: equilibrio calculado sobre la base equivocada se ve idéntico a uno correcto.
DATA_VERSIONS = ("ACTUAL", "BUDGET", "FORECAST")

MSG_MC_NEGATIVO = "be.margen_contribucion_negativo"


class VersionDeDatoRequerida(ValueError):
    """`data_version` no vino, o no es una de las tres. NO hay default."""


def exigir_data_version(v: str | None) -> str:
    if not v or v not in DATA_VERSIONS:
        raise VersionDeDatoRequerida(
            f"data_version es obligatorio y debe ser uno de {DATA_VERSIONS}; "
            f"llegó {v!r}. No hay valor implícito: un punto de equilibrio "
            f"calculado sobre la versión equivocada se ve igual que uno correcto.")
    return v


@dataclass(frozen=True)
class Regla:
    """Una fila de `be_cost_classification`, sin la base de datos encima."""
    dept_slug: str
    dept_code: str
    account: str
    pl_line: str
    pct_variable: Decimal
    map_source: str = "GL"
    excluded_from_be: bool = False
    be_section: str = ""
    account_name: str = ""


@dataclass(frozen=True)
class Monto:
    """Un monto del P&L a clasificar. `dept_code`/`account` vacíos = agregado."""
    dept_code: str
    account: str
    pl_line: str
    amount: Decimal
    #: El departamento del break-even AL QUE PERTENECE EL MONTO. Lo pone quien
    #: arma la base (`_be_base`), que es quien conoce `be_department.dept_codes`.
    #:
    #: ⚠️ Existe porque el corte por departamento se armaba desde la REGLA que
    #: resolvía el monto, no desde el monto. Con una regla `LINEA` —que es un
    #: respaldo por sección, no una cuenta de un departamento— la plata se
    #: acreditaba al departamento de la regla. Medido en el `Working 2027`:
    #: **$357.183,11** mal atribuidos. El total y el equilibrio quedaban bien, y
    #: por eso no se veía: solo se contradecían dos pantallas del mismo tab.
    dept_slug: str = ""


@dataclass
class SinClasificar:
    dept_code: str
    account: str
    pl_line: str
    amount: Decimal


@dataclass
class DeptoBE:
    """Lo que le toca a un departamento. `revenue` lo pone quien llama: el motor
    clasifica COSTO, y el ingreso por departamento viene del P&L."""
    slug: str
    variable_cost: Decimal = ZERO
    fixed_cost: Decimal = ZERO
    excluded_cost: Decimal = ZERO
    revenue: Decimal = ZERO

    @property
    def total_cost(self) -> Decimal:
        return self.variable_cost + self.fixed_cost + self.excluded_cost

    @property
    def contribution_margin(self) -> Decimal:
        return self.revenue - self.variable_cost

    @property
    def cm_pct(self) -> Decimal | None:
        """`None` si no genera ingreso: un % de margen sobre cero no existe, y
        mostrarlo como 0% haría pensar que el departamento no aporta margen."""
        if self.revenue == ZERO:
            return None
        return self.contribution_margin / self.revenue


@dataclass
class Resultado:
    #: 0 = año completo. Lo llena quien llama; lo usa `equilibrio_mensual`.
    month: int = 0

    # Estado de resultados en costeo variable
    revenue: Decimal = ZERO
    variable_cost: Decimal = ZERO
    fixed_cost: Decimal = ZERO
    excluded_cost: Decimal = ZERO
    contribution_margin: Decimal = ZERO
    cm_pct: Decimal = ZERO
    ebt: Decimal = ZERO
    net: Decimal = ZERO

    # Punto de equilibrio. `None` cuando la guarda de CM% ≤ 0 se dispara.
    be_revenue: Decimal | None = None
    be_pct_of_revenue: Decimal | None = None
    margin_of_safety: Decimal | None = None
    margin_of_safety_pct: Decimal | None = None
    operating_leverage: Decimal | None = None
    #: `BE_REV / 12`. ⚠️ Es un PRORRATEO LINEAL y la UI tiene que rotularlo así:
    #: en CWL la ocupación va de 52% en febrero a 0,7% en septiembre, o sea que
    #: un umbral plano no describe ningún mes real.
    be_revenue_monthly_linear: Decimal | None = None

    #: Ingreso necesario para una utilidad objetivo: (FC + meta) / CM%.
    revenue_meta: Decimal | None = None

    #: Por qué el apalancamiento vino en `None`. Vacío si trae número.
    operating_leverage_motivo: str = ""

    # Métricas de habitaciones. Suponen MEZCLA DE INGRESOS CONSTANTE (§3.1).
    rooms_mix: Decimal | None = None
    be_room_nights: Decimal | None = None
    be_occupancy: Decimal | None = None
    be_trevpar: Decimal | None = None

    #: Corte por departamento: slug -> DeptoBE. Lo consume el tab
    #: «Por Departamento», y es lo que se compara contra el P&L.
    por_departamento: dict[str, "DeptoBE"] = field(default_factory=dict)

    motivo: str = ""
    sin_clasificar: list[SinClasificar] = field(default_factory=list)
    #: Reglas que no encontraron ni un monto: cuenta borrada o renombrada.
    reglas_huerfanas: list[str] = field(default_factory=list)

    @property
    def hay_equilibrio(self) -> bool:
        return self.be_revenue is not None


def _indexar(reglas: list[Regla]) -> tuple[dict, dict]:
    """(exactas por (dept_code, account), por línea) — la segunda solo LINEA."""
    exactas, por_linea = {}, {}
    for r in reglas:
        if r.account:
            exactas[(r.dept_code, r.account)] = r
        if r.map_source == "LINEA":
            # El spec §2.6 garantiza EXACTAMENTE una fila por `pl_line` en las
            # LINEA (en la v1 había hasta 9 compitiendo y la resolución era
            # ambigua). Si alguna vez vuelven a chocar, gana la primera y hay
            # una prueba que lo caza antes de que llegue acá.
            por_linea.setdefault(r.pl_line, r)
    return exactas, por_linea


def resolver(monto: Monto, exactas: dict, por_linea: dict) -> Regla | None:
    """Los tres pasos del §2.6. `None` = no hay regla → 100% fijo."""
    r = exactas.get((monto.dept_code, monto.account))
    if r is not None:
        return r
    return por_linea.get(monto.pl_line)


def calcular(
    *,
    data_version: str,
    revenue: Decimal,
    revenue_rooms: Decimal = ZERO,
    montos: list[Monto],
    reglas: list[Regla],
    adr: Decimal = ZERO,
    rooms_available: Decimal = ZERO,
    utilidad_objetivo: Decimal = ZERO,
) -> Resultado:
    """El cálculo entero del §3. `data_version` es obligatorio y sin default."""
    exigir_data_version(data_version)

    res = Resultado(revenue=revenue)
    usadas: set[int] = set()

    # El indexado se hace UNA vez, no por monto.
    exactas, por_linea = _indexar(reglas)

    for m in montos:
        regla = resolver(m, exactas, por_linea)
        if regla is None:
            # Paso 3: 100% fijo y a la lista. Nunca variable, nunca en silencio.
            res.fixed_cost += m.amount
            res.sin_clasificar.append(
                SinClasificar(m.dept_code, m.account, m.pl_line, m.amount))
            # ⚠️ Y ADEMÁS al departamento, si el monto sabe cuál es. Sin esto,
            # una fila sin regla entra al TOTAL y desaparece del corte por
            # departamento: las dos pantallas del mismo tab dejan de sumar lo
            # mismo, y la que miente es la que el usuario usa para decidir.
            #
            # Medido: el crédito del reparto de Villas y Residencias
            # (`0110:4999`, −$92.176,74) no tiene regla propia. Sin esta línea,
            # Rooms mostraba **$738.209** de costo contra los $646.032,60 del
            # P&L — el total cerraba igual, porque la plata sí estaba sumada.
            if m.dept_slug:
                d = res.por_departamento.setdefault(
                    m.dept_slug, DeptoBE(slug=m.dept_slug))
                d.fixed_cost += m.amount
            continue
        usadas.add(id(regla))
        # El departamento sale del MONTO. Solo si el monto no lo trae se cae a
        # la regla — ver `Monto.dept_slug`.
        slug = m.dept_slug or regla.dept_slug
        d = res.por_departamento.setdefault(slug, DeptoBE(slug=slug))
        if regla.excluded_from_be:
            # El impuesto de renta: sigue sumando al P&L, no al costo fijo.
            res.excluded_cost += m.amount
            d.excluded_cost += m.amount
            continue
        pv = Decimal(str(regla.pct_variable))
        res.variable_cost += m.amount * pv
        res.fixed_cost += m.amount * (UNO - pv)
        d.variable_cost += m.amount * pv
        d.fixed_cost += m.amount * (UNO - pv)

    res.reglas_huerfanas = [
        (f"{r.dept_code}:{r.account}" if r.account else r.pl_line)
        for r in reglas if id(r) not in usadas
    ]

    res.contribution_margin = res.revenue - res.variable_cost
    res.ebt = res.contribution_margin - res.fixed_cost
    res.net = res.ebt - res.excluded_cost

    # Guarda: REV = 0 → ratios en 0, sin dividir por cero.
    if res.revenue == ZERO:
        res.cm_pct = ZERO
        res.motivo = "no hay ingreso en el periodo: los ratios quedan en cero"
        return res

    res.cm_pct = res.contribution_margin / res.revenue

    # Guarda: CM% ≤ 0 → equilibrio en None CON motivo, nunca cero ni blanco.
    if res.cm_pct <= ZERO:
        res.motivo = MSG_MC_NEGATIVO
        return res

    res.be_revenue = res.fixed_cost / res.cm_pct
    res.be_pct_of_revenue = res.be_revenue / res.revenue
    res.margin_of_safety = res.revenue - res.be_revenue
    res.margin_of_safety_pct = res.margin_of_safety / res.revenue
    res.be_revenue_monthly_linear = res.be_revenue / Decimal("12")
    # ── Apalancamiento operativo ────────────────────────────────────────────
    #
    # Cuántas veces amplifica el resultado un cambio en ventas: `CM / EBT`. Con
    # `EBT = 0` es infinito, y eso se dice con None, no con un número enorme.
    #
    # ⚠️ **Y con EBT CASI cero también.** La versión anterior solo miraba el cero
    # exacto, así que el `FORECAST April 2026` —EBT de −$993 sobre $5,19 M de
    # ingreso, o sea prácticamente en el equilibrio— mostraba en pantalla
    # **−3.213,1x**. El número es aritméticamente correcto y no significa nada:
    # a medida que el resultado se acerca a cero el cociente tiende a infinito,
    # y el signo lo decide un redondeo. El owner lo vio y preguntó qué era ese
    # desmadre; tenía razón, es ruido con formato de dato.
    #
    # Lo que sí informa cuando el EBT es despreciable ya está en pantalla, y
    # mejor dicho: el **margen de seguridad** (acá, −$1.616 · 0,0%).
    if res.ebt == ZERO:
        res.operating_leverage = None
        res.operating_leverage_motivo = MSG_APALANCAMIENTO_EN_EL_EQUILIBRIO
    elif abs(res.ebt) < res.revenue * UMBRAL_EBT_DESPRECIABLE:
        res.operating_leverage = None
        res.operating_leverage_motivo = MSG_APALANCAMIENTO_RUIDO
    else:
        res.operating_leverage = res.contribution_margin / res.ebt

    if utilidad_objetivo:
        res.revenue_meta = (res.fixed_cost + utilidad_objetivo) / res.cm_pct

    # Guarda: sin habitaciones disponibles, las métricas de cuarto van en None.
    if rooms_available and adr:
        res.rooms_mix = revenue_rooms / res.revenue
        res.be_room_nights = (res.be_revenue * res.rooms_mix) / adr
        res.be_occupancy = res.be_room_nights / rooms_available
        res.be_trevpar = res.be_revenue / rooms_available

    return res


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2 — sensibilidad y equilibrio mensual con estacionalidad
# ═══════════════════════════════════════════════════════════════════════════════

#: Los rangos del modelo de referencia. Configurables desde la API, pero el
#: default reproduce la hoja SENSIBILIDAD del Excel.
OCUPACION_MIN = Decimal("0.20")
OCUPACION_MAX = Decimal("0.60")
OCUPACION_PASO = Decimal("0.025")
ADR_MIN = Decimal("0.80")
ADR_MAX = Decimal("1.20")
ADR_PASO = Decimal("0.05")


def _rango(desde: Decimal, hasta: Decimal, paso: Decimal) -> list[Decimal]:
    out, x = [], desde
    while x <= hasta + paso / 10:          # + paso/10: tolerancia de Decimal
        out.append(x)
        x += paso
    return out


@dataclass
class Sensibilidad:
    ocupaciones: list[Decimal]
    factores_adr: list[Decimal]
    #: `celdas[i][j]` = resultado antes de impuestos con `ocupaciones[i]` y
    #: `factores_adr[j]`. `None` si no se puede calcular (mezcla o ADR en cero).
    celdas: list[list[Decimal | None]]
    #: Coordenadas de la celda que corresponde al presupuesto real, para que la
    #: pantalla la marque. `None` si la ocupación presupuestada cae fuera.
    celda_presupuesto: tuple[int, int] | None = None
    motivo: str = ""


def sensibilidad(
    *,
    cm_pct: Decimal,
    fixed_cost: Decimal,
    rooms_available: Decimal,
    adr: Decimal,
    rooms_mix: Decimal,
    occ_presupuestada: Decimal | None = None,
    ocupaciones: list[Decimal] | None = None,
    factores_adr: list[Decimal] | None = None,
) -> Sensibilidad:
    """Matriz ocupación × factor de ADR → resultado antes de impuestos.

        EBT(o, k) = [ (o · habitaciones_disponibles · ADR·k) / mezcla_rooms ] · CM% − FC

    O sea: se escala el ingreso de HABITACIONES por ocupación y por el factor de
    tarifa, y se extrapola a ingreso TOTAL dividiendo por la mezcla de Rooms.
    Es la misma fórmula del modelo de referencia.

    ⚠️ **Los tres supuestos que la matriz hereda, y que la pantalla debe declarar:**

    1. **La mezcla de ingresos se mantiene constante.** Si la ocupación cae al
       20%, esto asume que Spa, Tours y A&B caen en la misma proporción. En la
       práctica no: los costos de esos departamentos no siguen a Rooms.
    2. **`CM%` se mantiene constante.** Es el % de la clasificación actual; si el
       owner cambia los porcentajes, la matriz entera se mueve.
    3. **`FC` se mantiene constante.** Un costo fijo lo es dentro de un rango; a
       20% de ocupación media parte del «fijo» no se incurre.

    Nada de esto la invalida —es el modelo estándar de CVP— pero una matriz de
    17×9 celdas se lee como una predicción, y no lo es.
    """
    occ = ocupaciones or _rango(OCUPACION_MIN, OCUPACION_MAX, OCUPACION_PASO)
    adrs = factores_adr or _rango(ADR_MIN, ADR_MAX, ADR_PASO)

    if rooms_mix <= ZERO or adr <= ZERO or rooms_available <= ZERO:
        return Sensibilidad(
            occ, adrs, [[None] * len(adrs) for _ in occ],
            motivo=("sin mezcla de Rooms, ADR o habitaciones disponibles no hay "
                    "cómo escalar el ingreso: la matriz no se puede calcular"))

    celdas: list[list[Decimal | None]] = []
    for o in occ:
        fila: list[Decimal | None] = []
        for k in adrs:
            ingreso_rooms = o * rooms_available * (adr * k)
            ingreso_total = ingreso_rooms / rooms_mix
            fila.append(ingreso_total * cm_pct - fixed_cost)
        celdas.append(fila)

    marca = None
    if occ_presupuestada is not None:
        # La más cercana, no la exacta: la ocupación real casi nunca cae justo
        # en un paso de 2,5 pp.
        i = min(range(len(occ)), key=lambda n: abs(occ[n] - occ_presupuestada))
        j = min(range(len(adrs)), key=lambda n: abs(adrs[n] - UNO))
        marca = (i, j)

    return Sensibilidad(occ, adrs, celdas, celda_presupuesto=marca)


@dataclass
class MesBE:
    month: int
    revenue: Decimal = ZERO
    variable_cost: Decimal = ZERO
    fixed_cost: Decimal = ZERO
    excluded_cost: Decimal = ZERO
    cm_pct: Decimal | None = None
    be_revenue: Decimal | None = None
    #: `revenue − be_revenue`. Negativo = el mes no llegó a su equilibrio.
    holgura: Decimal | None = None
    motivo: str = ""


def equilibrio_mensual(meses: list[Resultado]) -> list[MesBE]:
    """El equilibrio mes a mes, con los costos fijos y la mezcla de CADA mes.

    Es lo que reemplaza al prorrateo lineal de la Fase 1. `BE_REV/12` daba
    ~$333.036 todos los meses, y en CWL **eso no describe ningún mes real**: la
    ocupación va de 52% en febrero a 0,7% en septiembre, y el lodge cierra en
    octubre.

    ⚠️ **Un mes puede no tener equilibrio, y eso es un dato, no un error.** En
    temporada baja el ingreso no alcanza a cubrir el costo fijo del mes a ningún
    volumen: ahí `be_revenue` queda en `None` con su motivo. Rellenarlo con un
    cero o con el promedio anual sería inventar que ese mes cierra.

    Recibe un `Resultado` por mes —ya calculado con `calcular`— y no los montos
    crudos, para que el mensual y el anual usen exactamente el mismo motor.
    """
    out = []
    for r in meses:
        m = MesBE(month=r.month,
                  revenue=r.revenue, variable_cost=r.variable_cost,
                  fixed_cost=r.fixed_cost, excluded_cost=r.excluded_cost,
                  cm_pct=r.cm_pct if r.revenue else None,
                  be_revenue=r.be_revenue, motivo=r.motivo)
        if r.be_revenue is not None:
            m.holgura = r.revenue - r.be_revenue
        out.append(m)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# EQUILIBRIO EN NOCHES — la formulación del owner (2026-08-17)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EquilibrioEnNoches:
    """El equilibrio expresado en NOCHES, con su validación de costo.

    Owner, 2026-08-17: la vista que usa de verdad es ésta, no la de ingreso.

        ingreso_por_noche = ingreso_total / noches_ocupadas
        costo_var_noche   = costo_variable / noches_ocupadas
        contribucion      = ingreso_por_noche − costo_var_noche
        NOCHES_EQUILIBRIO = costo_fijo / contribucion
        %_ocupacion_eq    = noches_equilibrio / noches_disponibles
        varianza          = noches_ocupadas − noches_equilibrio

    ⚠️ **Es la MISMA fórmula que `BE_REV = FC / CM%`**, y conviene saberlo:

        FC / (Rev/N − VC/N) = FC·N / (Rev − VC) = N · FC/CM

    pero expresada por noche **no necesita el supuesto de mezcla constante** que
    sí necesita derivar noches desde el ingreso de equilibrio vía `MIX_ROOMS/ADR`.
    Por eso es la formulación mejor de las dos, y no solo otra presentación.

    ⚠️ **La contribución por noche puede ser NEGATIVA**, y entonces las noches de
    equilibrio salen negativas. No es un error de signo: significa que **cada
    noche vendida pierde plata** — a ese nivel de tarifa y de costo variable, no
    hay volumen que alcance. En el junio real de CWL pasa: $821,07 de ingreso por
    noche contra $864,57 de costo variable. Un `None` ahí escondería el dato más
    importante del mes, así que se devuelve el número con su bandera.
    """
    #: Entradas, para que la pantalla pueda mostrar la cadena completa.
    revenue: Decimal = ZERO
    variable_cost: Decimal = ZERO
    fixed_cost: Decimal = ZERO
    nights_occupied: Decimal = ZERO
    nights_available: Decimal = ZERO

    revenue_per_night: Decimal | None = None
    variable_cost_per_night: Decimal | None = None
    contribution_per_night: Decimal | None = None
    be_nights: Decimal | None = None
    be_occupancy_pct: Decimal | None = None
    occupancy_pct: Decimal | None = None
    variance_nights: Decimal | None = None
    #: `True` cuando la contribución por noche es ≤ 0: cada noche pierde plata.
    pierde_por_noche: bool = False
    #: Gasto promedio por mes del periodo — la fila «Average Expense per month».
    average_expense_per_month: Decimal | None = None

    # ── Validación: que el costo cierre CONTRA EL P&L ────────────────────────
    #: `costo del equilibrio − costo del P&L`. **`None` = no se controló**, que
    #: no es lo mismo que «cuadra»: la versión anterior comparaba las partes
    #: contra su propia suma y por eso daba 0,00 aunque faltaran $1,58 M.
    validacion_costo: Decimal | None = None

    @property
    def cuadra(self) -> bool | None:
        """`None` cuando no hubo con qué comparar. La UI tiene que distinguir
        «sin control» de «cuadra»: pintar de verde lo que nadie midió es
        exactamente como pasaron desapercibidos $1.577.905,52."""
        if self.validacion_costo is None:
            return None
        return abs(self.validacion_costo) < Decimal("0.50")


def equilibrio_en_noches(
    *,
    revenue: Decimal,
    variable_cost: Decimal,
    fixed_cost: Decimal,
    nights_occupied: Decimal,
    nights_available: Decimal,
    meses: int = 12,
    costo_del_pl: Decimal | None = None,
) -> EquilibrioEnNoches:
    """La cadena completa de la imagen del owner, incluida su validación.

    `costo_del_pl` es el costo total del MISMO periodo según el P&L. Es lo único
    que convierte la fila «Validations» en un control: sin un número traído de
    afuera, comparar las partes contra su propia suma no puede fallar nunca.
    """
    r = EquilibrioEnNoches(
        revenue=revenue, variable_cost=variable_cost, fixed_cost=fixed_cost,
        nights_occupied=nights_occupied, nights_available=nights_available,
    )
    total = variable_cost + fixed_cost
    # ⚠️ **Esta línea decía `variable + fijo - total`, con `total` derivado dos
    # renglones arriba de esos mismos dos números: daba CERO siempre.** Probado
    # con entradas absurdas (variable 999.999.999, fijo −500) seguía dando 0 y
    # «cuadra». Era un port fiel de la fila azul del Excel, donde el Total era un
    # dato INDEPENDIENTE tecleado aparte y la resta significaba algo; al derivar
    # el total de las partes, quedó el semáforo sin el control detrás.
    #
    # Y no era inocuo: mientras ese ✓ verde estuvo puesto, el `BUDGET Working
    # 2027` mostraba un neto de $2.882.508 contra $1.304.602 del P&L —
    # **$1.577.906 de costo que la base no tenía**— y la única validación de la
    # pantalla decía «$0,00 ✓».
    #
    # El control de verdad es contra el P&L, que es un número que este cálculo
    # NO produce: lo pone quien llama (`costo_del_pl`). Sin él, `None` — que la
    # UI muestra como «sin control», no como «cuadra».
    r.validacion_costo = None if costo_del_pl is None else total - costo_del_pl
    if meses:
        r.average_expense_per_month = total / Decimal(str(meses))
    if nights_available:
        r.occupancy_pct = nights_occupied / nights_available

    if not nights_occupied:
        # Sin noches vendidas no hay ingreso por noche que calcular. Se dice, no
        # se rellena con cero — un cero acá se leería como «no ingresa nada por
        # noche», que es distinto de «no hubo noches».
        return r

    r.revenue_per_night = revenue / nights_occupied
    r.variable_cost_per_night = variable_cost / nights_occupied
    r.contribution_per_night = r.revenue_per_night - r.variable_cost_per_night
    if r.contribution_per_night == ZERO:
        return r
    r.pierde_por_noche = r.contribution_per_night < ZERO
    r.be_nights = fixed_cost / r.contribution_per_night
    if nights_available:
        r.be_occupancy_pct = r.be_nights / nights_available
    r.variance_nights = nights_occupied - r.be_nights
    return r
