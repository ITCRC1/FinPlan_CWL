# -*- coding: utf-8 -*-
"""LA BASE DEL BREAK-EVEN: una sola proyección del GL, y todo el tab sale de ahí.

Owner, 2026-08-17: *«debés crear una tabla intermedia donde se mapee el GL en
REV, COST, OPEX y todo lo demás para que corra bien en el break even, que pase
por el filtro y de ahí se jale para el tab. Y que se valide que todos los datos
peguen con el P&L.»*

## Qué problema resuelve

`montos_del_escenario` devolvía **solo el costo** — con razón, porque las 612
reglas de clasificación son todas de costo. Pero eso dejaba a `DeptoBE.revenue`
sin quien lo llenara: el motor lo declara con un «lo pone quien llama» y no lo
ponía nadie. Resultado en pantalla: **los catorce departamentos con ingreso $0**,
el margen de contribución igual al costo variable en negativo, y el `% MC` en
«—» en todas las filas. El tab «Por Departamento» mostraba bien el costo y **no
podía mostrar margen**, que es para lo que existe.

Y no se veía como un error: se veía como un hotel que no vendió nada.

## La forma

Una fila por fila del GL, con **todo** resuelto de una vez: su línea del P&L, su
**sección** (`REVENUES` · `COST OF SALES` · `OPERATING EXPENSES` · …), su
departamento del break-even, y si es costo o ingreso. Después cada consumidor
**filtra** esa misma base:

    costos()                   -> la base de costo (idéntica a la de antes)
    ingreso_por_departamento() -> lo que le faltaba al tab
    validar_contra_pl()        -> que todo pegue

Antes había dos recorridos distintos del GL con dos criterios distintos. Uno
solo no puede contradecirse con el otro.

## ⚠️ Calculada, no guardada — y por qué

El owner eligió calculada. Es además la línea del sistema: *enllavar no congela
los números, todo reporte recomputa con el motor de hoy*. Una base de break-even
**guardada y vieja** daría un equilibrio que **se ve idéntico a uno correcto**,
que es justo el error que este módulo entero existe para evitar.

El gancho para congelarla el día que haga falta auditar un periodo cerrado ya
está puesto y es explícito (`be_classification_snapshot`), igual que
`cashflow_versions`. Congelar tiene que ser una decisión, nunca un efecto
secundario.

## Lo que NO se puede mover

* **La base de costo no cambia ni un centavo.** `costos()` reproduce el filtro
  anterior fila por fila. Hay prueba.
* **Una fila por fila del GL, jamás una por regla.** 612 reglas para 467 líneas:
  iterar reglas y sumar montos da **+39,9%**.
* **La lista de secciones de costo es BLANCA.** Con una negra, una sección nueva
  entraría al costo en silencio — y eso **baja** el equilibrio, o sea que el
  error se ve como una buena noticia.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import break_even as be
from app.engine import pl_engine
from app.models.break_even import BeDepartment
from app.models.scenario import Scenario

ZERO = Decimal("0")

#: Las secciones que son COSTO para el equilibrio. **Blanca a propósito.**
#: `TAX / NET PROFIT` entra porque su regla lo marca `excluded_from_be`: el motor
#: lo saca del costo fijo pero lo resta al neto, y sin él el neto no cierra
#: contra el P&L.
SECCIONES_DE_COSTO = frozenset({
    "COST OF SALES", "OPERATING EXPENSES", "OVERHEAD COST OF SALES",
    "OVERHEAD EXPENSES", "OWNER / NON-OP EXPENSES", "CAPITAL",
    "DEPRECIATION", "FINANCIAL EXPENSES", "TAX / NET PROFIT",
})

#: La sección de ingreso. Una sola, y también por lista blanca.
SECCION_DE_INGRESO = "REVENUES"

#: Debajo de esto, un departamento «netea cero» y se acepta que reparte todo su
#: costo. Cafetería y Lavandería miden 0,00 y 0,01; Rooms, que la marca por
#: cuenta también atrapaba, mide $553.855,85. Mil dólares deja pasar el redondeo
#: sin dejar pasar un departamento entero.
UMBRAL_NETEA_CERO = Decimal("1000")

#: Líneas que son TOTALES del propio reporte, no movimientos. Si entraran, cada
#: peso se contaría dos veces: una en su línea y otra en el total. Hoy el GL no
#: las trae; el día que las traiga, el error sería invisible porque los totales
#: seguirían cuadrando entre sí, al doble.
LINEAS_QUE_SON_TOTALES = frozenset({
    "TOTAL_REVENUES", "SEC_REVENUES", "TOTAL_OPERATING_EXPENSES",
    "SEC_OPERATING_EXPENSES", "TOTAL_OVERHEAD_EXPENSES", "SEC_OVERHEAD_EXPENSES",
    "TOTAL_NON_OP_EXPENSES", "TOTAL_OTHER_EXPENSES", "TOTAL_RENT_MGMT_FEES",
    "TOTAL_PROPERTY_INSURANCE", "TOTAL_DEPRECIATIONS", "TOTAL_GOP",
    "OPERATING_PROFIT", "SEC_OPERATING_PROFIT",
})


@dataclass(frozen=True)
class FilaBase:
    """Una fila del GL, con todo lo que hace falta para clasificarla."""
    dept_code: str
    account: str
    pl_line: str
    #: La sección del `report_line_config`. Vacía si la fila no resolvió línea.
    section: str
    amount: Decimal
    #: El departamento del break-even, por `be_department.dept_codes`. Vacío si
    #: ese código de GL no pertenece a ninguno.
    dept_slug: str
    #: El departamento REPARTE su costo a los demás (cafetería, lavandería): su
    #: crédito viaja en una cuenta de distribución y netea cero.
    reparte: bool

    @property
    def es_costo(self) -> bool:
        # Sin línea NO se puede saber si es costo. Se deja pasar como costo para
        # que caiga en «Por defecto: 100% fijo» y se VEA, en vez de descartarla
        # en silencio: una fila descartada no aparece en ninguna pantalla.
        return not self.section or self.section in SECCIONES_DE_COSTO

    @property
    def es_ingreso(self) -> bool:
        return self.section == SECCION_DE_INGRESO


@dataclass
class BaseBE:
    """La base entera, y los filtros que cada pantalla usa sobre ella."""
    filas: list[FilaBase] = field(default_factory=list)
    #: `slug -> genera ingreso`. Un departamento de soporte no lleva ingreso en
    #: `0`: va en `None`, porque un cero se lee como «no vendió».
    genera_ingreso: dict[str, bool] = field(default_factory=dict)
    #: Las líneas `REV_*` del P&L del escenario: `line_code -> monto`. Es la
    #: FUENTE del ingreso — ver `ingreso_por_departamento`.
    ingreso_pl: dict[str, Decimal] = field(default_factory=dict)
    #: `REV_ROOMS -> 'rooms'`. Sale del `account_mapping`, no escrito a mano.
    depto_de_linea: dict[str, str] = field(default_factory=dict)
    #: Lo que no se pudo cuadrar y NO se tapó. Ver
    #: `_completar_con_lo_que_calcula_el_pl`.
    avisos: list[str] = field(default_factory=list)

    # ── Los filtros ──────────────────────────────────────────────────────────

    def costos(self) -> list[be.Monto]:
        """La base de costo del equilibrio. **Idéntica a la de antes.**

        Los departamentos que reparten quedan fuera: reparten todo su costo y
        netean 0,00, así que no se contaban dos veces, pero ensuciaban «Por
        defecto: 100% fijo» con filas que sumaban un centavo — y eso hace
        parecer que falta clasificar plata donde no falta.
        """
        return [be.Monto(f.dept_code, f.account, f.pl_line, f.amount, f.dept_slug)
                for f in self.filas if f.es_costo and not f.reparte]

    def ingreso_por_departamento(self) -> dict[str, Decimal]:
        """Lo que le faltaba al tab. **Sale del P&L, no del GL.**

        ⚠️ **Y tuvo que ser así, medido.** La primera versión lo sacaba de
        `_sources`, igual que el costo, y en el **`BUDGET Working 2027` daba
        CERO** contra $6.374.026 del P&L. Un cero por «no hay filas» y un cero
        por «no vendió» se ven idénticos en pantalla.

        La causa son **dos** cosas, y ninguna es que falte el dato:

        1. **`_sources` no devuelve ingreso** para escenarios en modo
           `checkbook`: lee OPEX, Costos, Planilla y Repartos. Es una fuente de
           COSTO, y el tab de Control lo dice en su propio texto («payroll,
           OPEX, costs»).
        2. Y aunque lo devolviera, en esos escenarios **`revenue_entries` no es
           la fuente**: los seis presupuestos 2027 están en `revenue_source =
           'drivers'` desde el 15-ago, así que el ingreso lo calcula el motor
           con tarifas × ocupación × canales. La tabla es ahora un espejo que el
           recálculo mantiene al día — ver
           `recalculate.sincronizar_ingreso_al_checkbook`.

        Por eso el ingreso sale de las líneas `REV_*` del P&L: es la única
        fuente que existe en **todos** los escenarios, y pega contra el P&L por
        construcción, que es lo que el owner pidió.
        """
        out: dict[str, Decimal] = {}
        for linea, monto in self.ingreso_pl.items():
            slug = self.depto_de_linea.get(linea, "")
            if slug:
                out[slug] = out.get(slug, ZERO) + monto
        return out

    def ingreso_sin_departamento(self) -> Decimal:
        """Ingreso de una línea `REV_*` que no cae en ningún departamento.

        No se reparte ni se esconde: se informa. Sumarlo a alguno le daría a ese
        departamento un margen que no es suyo, y repartirlo se lo daría a todos.

        Desde que el mapa sale del `account_mapping` esto da **0,00** en los
        cinco escenarios medidos: las 19 líneas de ingreso tienen departamento.
        Queda igual, porque el día que se configure una línea nueva sin
        departamento tiene que verse, no desaparecer.
        """
        return sum((m for l, m in self.ingreso_pl.items()
                    if not self.depto_de_linea.get(l)), ZERO)

    def ingreso_del_gl_por_departamento(self) -> dict[str, Decimal]:
        """Lo mismo, pero leído del GL. **Es el control cruzado, no la fuente.**

        Donde el GL trae ingreso —los ACTUAL y los presupuestos importados de
        Excel— tiene que decir lo mismo que el P&L. Donde no lo trae, queda
        vacío, y esa diferencia es dato: dice que ese escenario se planificó por
        drivers.
        """
        out: dict[str, Decimal] = {}
        for f in self.filas:
            if f.es_ingreso and f.dept_slug:
                out[f.dept_slug] = out.get(f.dept_slug, ZERO) + f.amount
        return out

    def total_por_seccion(self) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for f in self.filas:
            k = f.section or "(sin línea)"
            out[k] = out.get(k, ZERO) + f.amount
        return out

    def total_ingreso(self) -> Decimal:
        """Todo el ingreso de la base: el que tiene departamento y el que no."""
        return sum(self.ingreso_pl.values(), ZERO)

    def total_ingreso_del_gl(self) -> Decimal:
        return sum((f.amount for f in self.filas if f.es_ingreso), ZERO)


# ─── Construcción ─────────────────────────────────────────────────────────────

async def construir(db: AsyncSession, scenario: Scenario, month: int = 0) -> BaseBE:
    """Arma la base del escenario. Una sola pasada por el GL."""
    from app.api.audit_api import _sources
    from app.engine.recalculate import (
        load_active_account_mappings, load_report_line_config,
    )

    filas_gl = await _sources(db, scenario, month)
    mappings = await load_active_account_mappings(db)
    resolve = pl_engine.construir_resolvedor(mappings)
    seccion_de = {r["line_code"]: r.get("section")
                  for r in await load_report_line_config(db)}

    # ── El puente GL → departamento del break-even ───────────────────────────
    #
    # Sale de `be_department.dept_codes` ('0110,0115,0116'), que es DATO y no una
    # lista en el código: una propiedad nueva con otros códigos queda cubierta
    # sola, y activar un departamento sigue siendo un UPDATE y no un despliegue.
    deptos = (await db.execute(select(BeDepartment))).scalars().all()
    slug_de_dept: dict[str, str] = {}
    genera: dict[str, bool] = {}
    for d in deptos:
        genera[d.slug] = bool(d.generates_revenue)
        for code in (d.dept_codes or "").split(","):
            code = code.strip()
            if code:
                slug_de_dept[code] = d.slug

    # ── Quién REPARTE de verdad ──────────────────────────────────────────────
    #
    # Se detecta por la CUENTA de distribución (misma marca que el motor del
    # P&L) **y además se comprueba que efectivamente netee cero**, que es la
    # condición que justifica sacarlo: «reparten todo su costo y netean 0,00».
    #
    # ⚠️ Sin la segunda mitad, la marca se lleva departamentos enteros. Medido en
    # el `BUDGET Working 2027`: el reparto de Villas y Residencias (0110 →
    # 0115/0116) asienta un crédito `4999` de −$92.176,74 **dentro del propio
    # 0110**, así que Rooms quedaba marcado como repartidor y se caía completo de
    # la base — **$553.855,87**, el departamento con el 59% del ingreso del
    # hotel. En pantalla Rooms mostraba **97,6% de margen de contribución**
    # contra el 82,9% del P&L, y el equilibrio salía $307.264 más bajo.
    #
    # Rooms no netea cero: netea $553.855,85. Cafetería (0220) y Lavandería
    # (0161) sí — 0,00 y 0,01 medidos —, y por eso siguen fuera.
    #
    # Verificado contra los cinco escenarios: con la comprobación del neto,
    # `BUDGET Final 2026`, `FORECAST April 2026`, `ACTUAL 2025` y `ACTUAL 2024`
    # quedan **idénticos al centavo**. Solo se mueve el 2027, que es donde estaba
    # el error.
    _marcados = {(f.get("dept_code") or "") for f in filas_gl
                 if str(f.get("account_code") or "") in pl_engine.ALLOCATION_ACCOUNTS}
    _neto: dict[str, Decimal] = {}
    for f in filas_gl:
        dept = f.get("dept_code") or ""
        if dept in _marcados:
            _neto[dept] = _neto.get(dept, ZERO) + Decimal(str(f.get("amount") or 0))
    reparten = {d for d in _marcados if abs(_neto.get(d, ZERO)) <= UMBRAL_NETEA_CERO}

    # Las líneas de ingreso configuradas, sin los totales del propio reporte.
    canonicas = {code for code, sec in seccion_de.items()
                 if sec == SECCION_DE_INGRESO and code not in LINEAS_QUE_SON_TOTALES}

    base = BaseBE(genera_ingreso=genera,
                  depto_de_linea=_lineas_de_ingreso_por_departamento(mappings, slug_de_dept),
                  ingreso_pl=await _ingreso_del_pl(db, scenario, month, canonicas))
    for f in filas_gl:
        monto = Decimal(str(f.get("amount") or 0))
        if not monto:
            continue
        dept = f.get("dept_code") or ""
        cuenta = str(f.get("account_code") or "")
        regla, _como = resolve(dept, cuenta)
        linea = (regla or {}).get("report_line_code", "") if regla else ""
        if linea in LINEAS_QUE_SON_TOTALES:
            continue
        seccion = (seccion_de.get(linea) or "") if linea else ""
        # Ni costo ni ingreso (KPIs, GOP, EBITDA…): no entra a la base. Se
        # descarta acá y no en cada filtro, para que no haya dos criterios.
        es_costo = not seccion or seccion in SECCIONES_DE_COSTO
        if not es_costo and seccion != SECCION_DE_INGRESO:
            continue
        base.filas.append(FilaBase(
            dept_code=dept, account=cuenta, pl_line=linea, section=seccion,
            amount=monto, dept_slug=slug_de_dept.get(dept, ""),
            reparte=dept in reparten,
        ))

    # ── Lo que el P&L CALCULA y el GL no puede traer ─────────────────────────
    #
    # El fee de gerencia, la reserva de capital y el impuesto salen de un
    # porcentaje del motor, no de una fila del mayor. Sin esto el equilibrio del
    # `Working 2027` salía $446.181,84 más bajo, y el neto del módulo declaraba
    # $2.882.508 contra $1.304.602 del reporte.
    from app.models.break_even import BeCostClassification
    reglas_gl: dict[str, tuple[str, str]] = {}
    for c in (await db.execute(
        select(BeCostClassification).where(
            BeCostClassification.property_id == scenario.hotel_id,
            BeCostClassification.map_source == "GL",
        ))).scalars().all():
        if c.account and c.pl_line not in reglas_gl:
            reglas_gl[c.pl_line] = (c.dept_code or "", c.account)

    base.avisos = await _completar_con_lo_que_calcula_el_pl(
        db, scenario, month, base, seccion_de, reglas_gl)
    return base


def _canonica(line_code: str) -> str:
    """El código CANÓNICO de una línea (el del `report_line_config`).

    ⚠️ **El motor expone DOS vocabularios** y `canonicalize_pl_lines` es
    ADITIVO: no borra el código viejo, agrega el nuevo. Así que un mismo peso
    aparece en `REV_TRANSPORT` **y** en `REV_TRANSPORTATION`.

    Sumar «todo lo que empiece con REV_» los cuenta a los dos. Medido en el
    `ACTUAL 2024`: el ingreso daba $2.120.135 contra $2.055.687 del P&L, y la
    diferencia era **exactamente** los $64.448,17 de Transportation — el mismo
    monto dos veces. `REV_CROWTHER`/`REV_CROWTHER_LAB` es el otro par.

    Un error de duplicado que cae justo sobre un departamento entero no se ve
    como duplicado: se ve como un departamento que vendió el doble.
    """
    par = pl_engine._MOTOR_TO_CANON.get(line_code)
    return par[0] if par else line_code


def _lineas_de_ingreso_por_departamento(
    mappings: list[dict], slug_de_dept: dict[str, str],
) -> dict[str, str]:
    """`REV_ROOMS -> 'rooms'`, leído del **mapeo de cuentas**.

    Owner, 2026-08-17: *«los canales entran al principio y los resultados que
    van al GL son el final del proceso»* · *«debe tomar todas las cuentas»* ·
    *«no debería de romperse»*.

    Y las cuentas **ya estaban**: `account_mapping` tiene las 19 líneas de
    ingreso con su departamento y sus cuentas GL — `REV_ROOMS` → `0110/4000`,
    `REV_SUSTAINABILITY` → `280/4880`, y así. No había nada que inventar; había
    que mirar la tabla correcta.

    ⚠️ **La primera versión derivaba esto de los grupos de `pl_engine`**
    (`dept_code → grupo → atributo → REV_*`) y perdía plata en silencio: los
    departamentos `280` (Misceláneos) y `0205` (Claro Huerta) caen en
    `OTHER_OVERHEAD` en esa cadena, así que `REV_MISC_OTHER` y
    `REV_SUSTAINABILITY` salían **sin departamento** — $308.405 en el
    `BUDGET Final 2026`. El P&L seguía cuadrando: el total del hotel no se
    movía, solo faltaba margen en departamentos que nadie estaba mirando.

    El `account_mapping` es la MISMA autoridad que resuelve el costo, y es la
    que el owner edita en Admin · Account Mapping. Un ingreso y un gasto del
    mismo departamento se resuelven ahora por el mismo camino: si mañana se
    mueve una cuenta de departamento, el ingreso la sigue sola.
    """
    out: dict[str, str] = {}
    for r in mappings:
        linea = _canonica(str(r.get("report_line_code") or ""))
        if not linea.startswith("REV_"):
            continue
        slug = slug_de_dept.get(str(r.get("dept_code") or "").strip())
        if slug:
            out.setdefault(linea, slug)
    return out


async def _ingreso_del_pl(db: AsyncSession, s: Scenario, month: int,
                          canonicas: set[str]) -> dict[str, Decimal]:
    """Las líneas de ingreso del P&L del escenario. La fuente del ingreso.

    Sale del **mismo** motor que el reporte para que no exista un segundo
    ingreso en el sistema: el tab tiene que dar el número del P&L, no uno
    parecido.

    ⚠️ **Solo las CANÓNICAS**, o sea las que existen en `report_line_config`.
    El motor emite además su vocabulario viejo, y sumar los dos duplica — ver
    `_canonica`. La lista es blanca y sale de la base: una línea de ingreso
    nueva entra sola el día que se configure, y una que no esté configurada no
    entra por accidente.
    """
    from app.engine.recalculate import compute_pl_month

    meses = range(1, 13) if not month else [month]
    out: dict[str, Decimal] = {}
    for m in meses:
        for ln in await compute_pl_month(db, s, m):
            if ln.line_code not in canonicas:
                continue
            out[ln.line_code] = (out.get(ln.line_code, ZERO)
                                 + Decimal(str(ln.amount_usd)))
    return out


# ─── Lo que el P&L calcula y el GL no tiene ───────────────────────────────────

#: Cuánto puede sobrar o faltar sin que se considere un hueco. Por debajo de
#: esto no se inyecta nada: es redondeo entre el mapeo y el motor.
TOLERANCIA_HUECO = Decimal("1")


async def _completar_con_lo_que_calcula_el_pl(
    db: AsyncSession, scenario: Scenario, month: int, base: BaseBE,
    seccion_de: dict[str, str], reglas_gl: dict[str, tuple[str, str]],
) -> list[str]:
    """Mete al costo las líneas que el P&L CALCULA y el GL no puede traer.

    ## El hueco, medido

    El fee de gerencia (3% del ingreso), la reserva de capital (4%) y el
    impuesto de renta **no existen como fila de GL**: el motor del P&L los
    calcula como porcentaje. La base los buscaba en el GL, no los encontraba, y
    el equilibrio salía sin ellos.

    En el `BUDGET Working 2027`: faltaban `MGMT_FEE_3` $191.220,79 y
    `CAPITAL_RESERVE` $254.961,05 —**$446.181,84**, la brecha exacta contra el
    P&L— más `INCOME_TAXES` $559.115,34. El módulo declaraba un neto de
    $2.882.508 contra $1.304.602 del reporte.

    ⚠️ **Y fallaba justo en los seis presupuestos 2027**, que son los que tienen
    esas líneas calculadas; los históricos las traen en el GL y cuadran. O sea
    que fallaba en el set con el que se planifica, y fallaba igual en los seis,
    así que el tab Comparar los mostraba consistentes entre sí.

    ## Las dos trampas, las dos medidas

    1. **Inyectar solo por `pl_line`** deja al impuesto sin regla —su regla es
       de cuenta (`0250/8060`), no de línea—, cae en «sin regla → 100% fijo» y
       aterriza DENTRO del costo fijo: el equilibrio se va a $4.090.837 en vez
       de $3.410.805. $680k de sobreestimación con cara de número correcto. Por
       eso cada monto se crea con su `(dept_code, account)` real.
    2. **Inyectar línea por línea sin comprobar el total** mete plata que no
       falta: en el `FORECAST April 2026` hay una reclasificación interna
       `CAPITAL_RESERVE ↔ LARGE_CAPEX` que aparenta $30.000 de hueco, y en el
       `ACTUAL 2024` las líneas ausentes suman $11.757 contra una brecha real de
       −$3.085. Por eso solo se inyecta **si las líneas ausentes explican la
       brecha total**; si no la explican, no se toca nada y se informa.

    Devuelve los avisos: si queda brecha sin explicar, se dice — un hueco que no
    se puede atribuir es exactamente lo que no puede pasar en silencio otra vez.
    """
    from app.engine.recalculate import compute_pl_month

    meses = range(1, 13) if not month else [month]
    del_pl: dict[str, Decimal] = {}
    rev = neto = impuesto = ZERO
    for m in meses:
        for ln in await compute_pl_month(db, scenario, m):
            v = Decimal(str(ln.amount_usd))
            code = ln.line_code
            if code == "TOTAL_REVENUES":
                rev += v
            elif code == "NET_PROFIT":
                neto += v
            elif code == "INCOME_TAXES":
                impuesto += v
            del_pl[code] = del_pl.get(code, ZERO) + v

    # Lo que la base ya tiene, por línea.
    ya: dict[str, Decimal] = {}
    for f in base.filas:
        if f.es_costo and not f.reparte:
            ya[f.pl_line] = ya.get(f.pl_line, ZERO) + f.amount

    # ⚠️ El impuesto NO cuenta acá. `costo_del_pl` lo resta —el costo del
    # equilibrio es `variable + fijo` y su regla lo marca `excluded_from_be`—,
    # así que sumarlo de este lado inventa una brecha del tamaño del impuesto.
    # Sin esto, el `BUDGET Final 2026` denunciaba un hueco de −$5.669,46 y el
    # `FORECAST April 2026` uno de −$21.316,24, teniendo los dos el costo
    # cuadrado a 4 centavos. Un aviso que se equivoca deja de leerse, y el día
    # que tenga razón tampoco se lee.
    costo_actual = sum(v for k, v in ya.items() if k != "INCOME_TAXES")
    # La identidad del reporte. El impuesto se suma aparte porque en el
    # equilibrio va excluido, no dentro del costo fijo.
    costo_del_pl = rev - neto - impuesto
    brecha = costo_del_pl - costo_actual

    # Candidatas: líneas de COSTO que el P&L tiene y la base **no tiene en
    # absoluto**. Una línea que ya está parcialmente no es un hueco: es una
    # diferencia de mapeo, y taparla sería inventar.
    candidatas = {
        code: monto for code, monto in del_pl.items()
        if code not in LINEAS_QUE_SON_TOTALES
        and seccion_de.get(code) in SECCIONES_DE_COSTO
        and abs(monto) > TOLERANCIA_HUECO
        and abs(ya.get(code, ZERO)) <= TOLERANCIA_HUECO
        and code in reglas_gl          # solo si sabemos su (depto, cuenta) real
        and code != "INCOME_TAXES"     # el impuesto va aparte, más abajo
    }

    avisos: list[str] = []
    suma = sum(candidatas.values(), ZERO)
    completado = ZERO
    if abs(brecha) > TOLERANCIA_HUECO and abs(suma - brecha) <= TOLERANCIA_HUECO:
        for code, monto in candidatas.items():
            dept, cuenta = reglas_gl[code]
            base.filas.append(FilaBase(
                dept_code=dept, account=cuenta, pl_line=code,
                section=seccion_de.get(code) or "", amount=monto,
                dept_slug=base.depto_de_linea.get(code, ""), reparte=False))
        completado = suma

    # El impuesto, siempre por su cuenta real para que su regla lo marque
    # excluido. Sin él el NETO del módulo no cierra contra el reporte.
    if abs(impuesto) > TOLERANCIA_HUECO and abs(ya.get("INCOME_TAXES", ZERO)) <= TOLERANCIA_HUECO:
        dept, cuenta = reglas_gl.get("INCOME_TAXES", ("0250", "8060"))
        base.filas.append(FilaBase(
            dept_code=dept, account=cuenta, pl_line="INCOME_TAXES",
            section=seccion_de.get("INCOME_TAXES") or "", amount=impuesto,
            dept_slug="", reparte=False))

    # ⚠️ El aviso se calcula AL FINAL, con todo ya inyectado. Calculado antes
    # denunciaba huecos que el propio paso siguiente cerraba — en el `FORECAST
    # April 2026` gritaba «faltan $21.316,24» cuando la brecha real terminaba en
    # 4 centavos. Un aviso que se equivoca deja de leerse, y entonces el día que
    # tenga razón tampoco se lee.
    residuo = brecha - completado
    if abs(residuo) > TOLERANCIA_HUECO:
        avisos.append(
            f"Quedan {float(residuo):,.2f} de diferencia contra el P&L que no se "
            f"pudieron atribuir a ninguna línea: no se completó nada, para no "
            f"inventar. Es el {float(abs(residuo) / costo_del_pl * 100):.3f}% "
            f"del costo." if costo_del_pl else
            f"Quedan {float(residuo):,.2f} sin atribuir.")
    return avisos


# ─── La validación que pidió el owner ─────────────────────────────────────────

#: Un centavo por línea es redondeo; más que esto es un error de mapeo.
TOLERANCIA = Decimal("0.05")


@dataclass
class Cuadre:
    """Si la base pega con el P&L, y por cuánto no."""
    concepto: str
    base: Decimal
    pl: Decimal

    @property
    def diferencia(self) -> Decimal:
        return self.base - self.pl

    @property
    def cuadra(self) -> bool:
        return abs(self.diferencia) <= TOLERANCIA


def validar_contra_pl(base: BaseBE, revenue_pl: Decimal) -> list[Cuadre]:
    """Los dos cuadres del ingreso.

    ⚠️ **Esto no es decoración.** El ingreso por departamento es nuevo, y un
    ingreso mal atribuido **no se ve**: el total del hotel queda igual y solo se
    mueve el margen de un departamento contra otro. Sin cuadre, la única señal
    sería que alguien se supiera el margen de memoria.

    El costo ya tiene el suyo —el neto del motor cierra contra el P&L a 4
    centavos— así que acá va el ingreso, que es lo que se agregó.

    1. **`REV_*` contra `TOTAL_REVENUES`.** Que las líneas sumen el total del
       P&L. No es tautológico aunque las dos salgan del motor: caza una línea
       `REV_*` nueva que el motor emita y esta capa no conozca.
    2. **Lo repartido contra el total.** Que la suma por departamento más lo que
       quedó sin departamento dé el total. Es lo que impide que una línea se
       pierda entre medio: se vería como un departamento con menos margen, no
       como un error.
    """
    pord = sum(base.ingreso_por_departamento().values(), ZERO)
    return [
        Cuadre("ingreso: líneas REV_* vs P&L", base.total_ingreso(), revenue_pl),
        Cuadre("ingreso: repartido vs total",
               pord + base.ingreso_sin_departamento(), base.total_ingreso()),
    ]
