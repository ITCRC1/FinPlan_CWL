"""P&L Full Detail — el reporte de máximo detalle (Fase 2).

**Qué es.** El P&L abierto CUENTA POR CUENTA, en la forma del Excel de Amarena
(`docs/fase2/PL_DETALLADO_FORMATO.xlsx`): un bloque por departamento, y adentro
de cada uno la misma plantilla —

    INGRESOS → COSTO DE VENTAS → NÓMINA → GASTOS OPERATIVOS → UTILIDAD NETA

— más el resumen arriba y los Gastos de Propiedad abajo. Doce meses y el año.

**Por qué existe** (decisión D5 del owner): «no hay reporte con máximo detalle».
CONVIVE con `/reports/pl-full` y `/reports/pl-by-dept`, no los reemplaza. Es la
vista con la que se audita el presupuesto línea por línea.

**El trabajo no era el dato, era el ensamblador.** El sistema ya tiene las 235
cuentas (`account_mapping` ≈ el catálogo del Excel) y el detalle cargado; lo que
no había era quién lo armara en este orden. `report_line_config` llega al nivel
de DEPARTAMENTO —13 líneas de ingreso, 13 de opex, 13 de utilidad, 9 de
overhead—, así que de las 781 líneas del Excel el P&L emitía como línea propia
solo ~10%. Acá se lee el detalle a nivel cuenta y se sube.

## Las tres decisiones de arquitectura

1. **El detalle por departamento es la fuente; el consolidado se DERIVA.** En el
   Excel son dos lecturas independientes del mismo libro sin una celda que las
   compare: cuadran por consistencia del origen, no por diseño. Acá el bloque
   RESUMEN sale del motor y se compara contra la suma del detalle — y la
   diferencia se devuelve. Un reporte de auditoría que no se audita a sí mismo
   no sirve para auditar nada.
2. **La etiqueta NO identifica.** El Excel tiene 83 etiquetas duplicadas. Cada
   fila va amarrada a `(departamento, cuenta)` y la etiqueta es decoración.
3. **Las filas ocultas del Excel son departamentos colapsados que SIGUEN
   sumando.** Acá los bloques son colapsables en la pantalla; nunca se excluyen
   del cálculo.

## Los 5 bugs del Excel que NO se replican

Los cinco salen de lo mismo: el archivo se armó para un ejercicio que arranca en
mayo y las fórmulas de enero–abril nunca se revisaron.

1. **Fila 78** — el overhead de enero a abril suma `D65:D77`, que **incluye la
   fila 65 (UTILIDAD OPERATIVA)**. Como GOP = 65 − 78, corrompe el GOP de esos
   cuatro meses. Acá cada subtotal se calcula desde sus componentes, nunca desde
   un rango que pueda tragarse un total.
2. **Fila 50** — enero–abril suma 9 líneas y mayo–diciembre 8 (se cae «Ingresos
   Varios»). Acá los 12 meses recorren la misma lista.
3. **Fila 942** — resta dos veces la nómina de Área Recreativa, porque las filas
   938 y 940 tienen la misma etiqueta y contenidos distintos. Acá la utilidad
   del bloque es `ingreso − (costo + nómina + opex)`, cada componente una vez.
4. **Fila 137** — descuenta dos líneas de Área Recreativa del opex total. Era
   una regla de negocio escondida en una fórmula; con Área Recreativa ya movida
   a overhead (migración 094) deja de hacer falta.
5. **Fila 76** — los meses salen de adentro y el total anual de afuera. Acá el
   anual es SIEMPRE la suma de los doce meses.

También se corrige el formato: los ratios «% de Ingresos del Depto.» y
«% Utilidad» venían con formato de MONEDA en el Excel (se leían `$0.35` en vez
de `35.0%`); acá viajan como porcentaje.
"""
from __future__ import annotations

import re
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.db import get_db
from app.engine import pl_engine
from app.engine.recalculate import (
    PAYROLL_ALL_COLS, compute_pl_month, load_report_line_config,
)
from app.models.actual_entry import ActualEntry
from app.models.allocation_entry import AllocationEntry
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.cost_entry import CostEntry
from app.models.department_catalog import DepartmentCatalog
from app.models.nonop_entry import NonOpEntry
from app.models.opex_entry import OpexEntry
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.scenario import Scenario
from app.hotel_actual import hotel_slug

router = APIRouter(tags=["pl-full-detail"])

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

# Las cuatro secciones de cada bloque de departamento, en el orden del Excel.
# La clase USALI de la cuenta decide en cuál cae, así que una cuenta nueva
# aterriza sola en su sección sin tocar código.
SECCIONES = [
    ("4", "INGRESOS", "ingresos"),
    ("5", "COSTO DE VENTAS", "costo"),
    ("6", "NÓMINA", "nomina"),
    ("7", "GASTOS OPERATIVOS", "opex"),
]

# Orden de los bloques, el del Excel. Un departamento con datos que no esté acá
# igual sale — al final, en su propio bloque: es preferible una tarjeta fuera de
# orden a plata que no aparece.
ORDEN_DEPTOS = [
    "0110", "0120", "0130", "0140", "0150", "0151", "0165", "260",
    "0161", "0162", "0250", "0280", "280",
    "0180", "0190", "0200", "0230", "0210", "0205", "0220", "270",
]

# Departamentos que el P&L de ACTUALES excluye a propósito porque su costo ya
# viaja repartido dentro de la planilla de cada departamento (concepto 6025).
# Mostrarlos acá los duplicaría — es el riesgo 6 del escaneo.
EXCLUIR_EN_IMPORTADOS = {"0220"}

# El departamento de habitaciones. Es el único que se abre en sets (Standard,
# Villas, Residencias) porque es el único que factura por categoría de unidad.
ROOMS = "0110"

# Bloque de último recurso para el ingreso cuyo departamento no se pudo resolver.
# Existe para que nunca se pierda plata en el camino: una fila fuera de lugar se
# ve y se corrige; una que no aparece, no.
SIN_DEPTO = "__otros_ingresos__"


def _clase(cuenta: str) -> str:
    c = (cuenta or "").strip()
    return c[0] if c else ""


def _hacer_es_ingreso(resolve):
    """¿Esta cuenta 4xxx es ingreso de verdad, o es un CRÉDITO DE REPARTO?

    Hay cuentas de clase 4 que no son ingreso: son el gasto que SE FUE a otro
    departamento cuando corre un reparto. La `4999` de Rooms y la **`4900` de
    Lavandería** son eso, y vienen en negativo.

    Se pregunta al mapeo en vez de tener una lista escrita a mano: si la cuenta
    NO resuelve a una línea `REV_*`, no es ingreso, y punto. Con la lista a mano
    la 4900 se colaba —eran los $18,852.40 que le faltaban al ingreso de Actual
    2026 y le sobraban al gasto, y los $47,613.19 del Budget 2026— y una cuenta
    de reparto nueva volvería a colarse el día que alguien la cree.
    """
    def es_ingreso(dept: str, cuenta: str) -> bool:
        if _clase(cuenta) != "4":
            return False
        m, _como = resolve(dept, cuenta)
        if not m:
            return True   # sin regla: se muestra como ingreso y el cuadre lo delata
        return str(m.get("report_line_code") or "").startswith("REV_")
    return es_ingreso


def _r(x: float) -> float:
    return round(x + 0.0, 2)


class _Acum:
    """Acumulador de (departamento, cuenta) → doce meses.

    La llave es `(depto, cuenta)` y NUNCA la etiqueta: el Excel tiene 83
    etiquetas repetidas, y amarrar por texto es cómo dos conceptos distintos
    terminan sumados en la misma fila.
    """

    def __init__(self) -> None:
        self.datos: dict[tuple[str, str], list[float]] = {}
        self.nombres: dict[tuple[str, str], str] = {}

    def add(self, dept: str, cuenta: str, mes_idx: int, monto, nombre: str = "") -> None:
        v = float(monto or 0)
        if not v:
            return
        k = ((dept or "").strip(), (cuenta or "").strip())
        fila = self.datos.get(k)
        if fila is None:
            fila = self.datos[k] = [0.0] * 12
        fila[mes_idx] += v
        if nombre and not self.nombres.get(k):
            self.nombres[k] = nombre

    def por_depto(self, dept: str) -> list[tuple[str, list[float]]]:
        return sorted(((c, v) for (d, c), v in self.datos.items() if d == dept),
                      key=lambda x: x[0])

    def por_deptos(self, depts: set[str]) -> list[tuple[str, list[float]]]:
        """Varios departamentos sumados cuenta a cuenta, como si fueran uno.

        Es lo que hace falta para consolidar Rooms: cuando el reparto está
        activo, el costo de las villas vive en su propio departamento (`0115`,
        `0116`) y el bloque del `0110` ya no es el total de habitaciones — es la
        parte que se quedó.
        """
        out: dict[str, list[float]] = {}
        for (d, c), v in self.datos.items():
            if d not in depts:
                continue
            fila = out.setdefault(c, [0.0] * 12)
            for i in range(12):
                fila[i] += v[i]
        return sorted(out.items())

    def deptos(self) -> set[str]:
        return {d for (d, _c) in self.datos}


async def _detalle_propio(db: AsyncSession, scenario: Scenario) -> _Acum:
    """El detalle cuenta × departamento × mes de UN escenario, sin mezclar.

    Dos caminos, según de dónde salga su P&L:

    * **importado** — todo viene del detalle GL (`actual_entries`), que ya trae
      las clases 4 a 8 con su departamento.
    * **checkbook** — se juntan los auxiliares. Ahí el INGRESO no tiene apertura
      por cuenta: sale de las rate cards a nivel de línea. No se inventa un
      prorrateo.
    """
    acum = _Acum()
    importado = getattr(scenario, "source_mode", "imported") != "checkbook"
    cd = pl_engine.consolidate_dept

    if importado:
        for e in (await db.execute(select(ActualEntry).where(
                ActualEntry.scenario_id == scenario.id))).scalars():
            dept = (e.dept_code or "").strip()
            if dept in EXCLUIR_EN_IMPORTADOS:
                continue
            for i, m in enumerate(MESES):
                acum.add(dept, e.account_code, i, getattr(e, m), e.account_name or "")
        return acum

    for Model in (RevenueAccountEntry, CostEntry, OpexEntry, BelowGopAccountEntry):
        for e in (await db.execute(select(Model).where(
                Model.scenario_id == scenario.id))).scalars():
            for i, m in enumerate(MESES):
                acum.add(cd(e.dept_code or ""), e.account_code, i, getattr(e, m),
                         getattr(e, "account_name", "") or "")

    for e in (await db.execute(select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario.id))).scalars():
        if not (1 <= (e.month or 0) <= 12):
            continue
        for col in PAYROLL_ALL_COLS:
            acum.add(cd(e.dept_code or ""), pl_engine.payroll_account_for_column(col),
                     e.month - 1, getattr(e, col, None))

    # Los repartos son una fuente más del P&L. Si no entran acá, el detalle
    # cuadra de menos y el reporte acusa un descuadre que no existe.
    for e in (await db.execute(select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario.id))).scalars():
        if 1 <= (e.month or 0) <= 12:
            acum.add(cd(e.target_dept or ""), e.account, e.month - 1, e.amount_usd)

    return acum


async def _cargar_detalle(db: AsyncSession, scenario: Scenario) -> _Acum:
    """El detalle del escenario **siguiendo el mismo corte que el P&L**.

    Un forecast «vivo» con `actuals_through = N` no se lee entero de sí mismo:
    los meses 1..N son la verdad registrada y el motor los toma del ACTUAL
    vinculado. Si el detalle no hiciera el mismo blend, el reporte mostraría la
    proyección de esos meses debajo de un resumen que muestra lo real, y la
    diferencia aparecería como un descuadre inventado — le pasaba al Forecast
    Working 2026: +124,824.69 de ingreso y +340,419.67 de gasto que no eran de
    nadie.
    """
    acum = await _detalle_propio(db, scenario)
    corte = int(getattr(scenario, "actuals_through", 0) or 0)
    if scenario.type != "FORECAST" or corte <= 0:
        return acum

    from app.engine.recalculate import linked_actual_scenario
    real = await linked_actual_scenario(db, scenario)
    if real is None:
        return acum
    del_real = await _detalle_propio(db, real)

    mezcla = _Acum()
    mezcla.nombres.update(acum.nombres)
    mezcla.nombres.update(del_real.nombres)
    for fuente, meses_de in ((del_real, range(0, corte)), (acum, range(corte, 12))):
        for (dept, cuenta), fila in fuente.datos.items():
            for i in meses_de:
                mezcla.add(dept, cuenta, i, fila[i])
    return mezcla


async def _ingreso_de_checkbook(
    db: AsyncSession, scenario: Scenario, con_gasto: set[str],
) -> dict[str, list[tuple[str, str, list[float]]]]:
    """El ingreso de un escenario de checkbook, puesto en su departamento.

    En estos escenarios el ingreso NO tiene apertura por cuenta: se presupuesta
    a nivel de línea (rate cards, capture rate del Spa, cuota del Club). Antes el
    reporte por eso mostraba los departamentos con puro gasto —Rooms salía con
    una «utilidad» de −$645,551— y el ingreso solo aparecía arriba, en el
    resumen. Un bloque que enseña la mitad de la ecuación no se puede leer.

    **No se prorratea por cuenta.** Cada línea entra como UNA fila con su nombre;
    las tres del Club además con su número, porque esas sí son cuentas
    (4500/4501/4502). Inventar una apertura por cuenta sería dibujar precisión
    que el dato no tiene.

    **A qué departamento va**, en este orden:

    1. Al del GRUPO con que el motor la empareja (`REVENUE_LINE_TO_GROUP` →
       `OPERATING_DEPT_GROUPS`), prefiriendo el departamento del grupo que TENGA
       gasto en este escenario. El grupo manda sobre la regla de mapeo porque el
       Spa factura por la 0130 y su gasto vive en la 0140: yendo por el mapeo, la
       0130 quedaría como un bloque de puro ingreso al lado de otro de puro gasto.
    2. Si la línea no tiene grupo —Sustainability y Misceláneos no son
       departamentos operativos—, al que diga `account_mapping` para su línea del
       P&L. Son $251k en el Budget 2027: demasiado para dejarlos en un cajón.
    3. Y si nada la ubica, a «Otros ingresos». Se ve fuera de lugar, pero no se
       pierde, y el cuadre de abajo lo delata igual.
    """
    if getattr(scenario, "source_mode", "imported") != "checkbook":
        return {}

    from app.engine.recalculate import (
        load_active_account_mappings, load_revenue_results, revenue_line_dict)
    from app.models.revenue_entry import REVENUE_LINE_ACCOUNT, REVENUE_LINE_LABELS

    # Departamento que el catálogo le da a cada línea REV_*. Si una línea tiene
    # reglas en varios departamentos gana el que más reglas tenga: es el dueño
    # de la línea, y los demás son casos sueltos.
    votos: dict[str, dict[str, int]] = {}
    for m in await load_active_account_mappings(db):
        lc = str(m.get("report_line_code") or "")
        d = (m.get("dept_code") or "").strip()
        if lc.startswith("REV_") and d:
            votos.setdefault(lc, {})[d] = votos.setdefault(lc, {}).get(d, 0) + 1
    depto_de_linea_pl = {
        lc: max(dd.items(), key=lambda kv: (kv[1], kv[0]))[0] for lc, dd in votos.items()
    }

    resultados = await load_revenue_results(db, scenario)
    por_linea: dict[str, list[float]] = {}
    for mes in range(1, 13):
        for linea, monto in revenue_line_dict(resultados[mes]).items():
            por_linea.setdefault(linea, [0.0] * 12)[mes - 1] += float(monto or 0)

    def depto_de(linea: str) -> str:
        grupo = pl_engine.REVENUE_LINE_TO_GROUP.get(linea)
        candidatos = pl_engine.OPERATING_DEPT_GROUPS.get(grupo or "", [])
        for d in candidatos:
            if d in con_gasto:
                return d
        if candidatos:
            return candidatos[0]
        del_mapeo = depto_de_linea_pl.get(
            pl_engine.REVENUE_LINE_TO_REPORT_LINE.get(linea, ""), "")
        return del_mapeo or SIN_DEPTO

    out: dict[str, list[tuple[str, str, list[float]]]] = {}
    for linea, meses in sorted(por_linea.items()):
        if not any(abs(v) > 0.005 for v in meses):
            continue
        code = linea.upper()
        etiqueta = REVENUE_LINE_LABELS.get(code, code.replace("_", " ").title())
        cuenta = (REVENUE_LINE_ACCOUNT.get(code) or ("", ""))[1]
        out.setdefault(depto_de(linea), []).append((etiqueta, cuenta, meses))
    return out


async def _clases_configuradas(
    db: AsyncSession, scenario: Scenario
) -> dict[str, set[str]]:
    """`{departamento: {clases USALI que tiene abiertas en el checkbook}}`.

    **Abierta ≠ con plata.** Una cuenta sembrada en cero no entra al acumulador
    —`_Acum.add` descarta los ceros— así que la sección entera desaparecía del
    bloque y el departamento parecía no tener ese tipo de gasto. El Club Madresal
    se veía con ingreso y planilla y nada más, cuando tiene sus 23 cuentas de
    OPEX y 2 de costo esperando que alguien las presupueste.

    No es lo mismo «este departamento no gasta en esto» que «todavía no lo he
    presupuestado», y el reporte tiene que poder decir la diferencia: con esto la
    sección sale con su total en cero en vez de desaparecer.

    Solo mira los auxiliares de la app. Un escenario importado no tiene filas en
    cero —el GL trae lo que pasó— así que ahí la sección sigue apareciendo solo
    cuando hay movimiento, que es lo correcto.
    """
    out: dict[str, set[str]] = {}
    for Model, clase in ((OpexEntry, "7"), (CostEntry, "5")):
        for dept in (await db.execute(select(Model.dept_code).where(
                Model.scenario_id == scenario.id).distinct())).scalars():
            d = pl_engine.consolidate_dept((dept or "").strip())
            out.setdefault(d, set()).add(clase)
    return out


async def _cuentas_de_propiedad(db: AsyncSession) -> set[str]:
    """Los códigos de las cuentas below-GOP del catálogo.

    Van todas al bloque de Gastos de Propiedad, con o sin saldo. No llevan
    departamento —son de la compañía, no de una operación— así que la lista es
    la misma para cualquier escenario y sale del mapeo, sin sembrar filas.

    Solo los códigos: el rótulo lo pone `_nombres_de_cuenta`, que es de donde
    salen los nombres del resto del reporte. Sacándolo de otra parte, la misma
    cuenta se llamaría distinto según en qué bloque aparezca — y el catálogo
    guarda las variantes juntas («RENT1 | RENT»), que es exactamente lo que esa
    función ya sabe limpiar.
    """
    from app.models.mapping import AccountMapping

    return {
        (m.account_code or "").strip()
        for m in (await db.execute(select(AccountMapping).where(
            AccountMapping.active_status == "YES"))).scalars()
        if _clase((m.account_code or "").strip()) == "8"
    }


async def _nombres_de_cuenta(db: AsyncSession) -> dict[str, str]:
    """Código de cuenta → nombre USALI del catálogo.

    Los nombres se quedan en inglés en los dos idiomas: están atados al GL y
    renombrarlos rompería el amarre contra la contabilidad (D2).

    **Cuál de las variantes.** El catálogo guarda los nombres con que la cuenta
    aparece en el libro, pegados con `|`: «RENT1 | RENT», «DEPRECIATION1 |
    DEPRECIATION2 | DEPRECIATION». Antes se tomaba la primera y la primera
    termina en dígito, así que el reporte decía «RENT1». Se prefiere la variante
    que NO termina en número, que es el nombre de verdad y las otras son sus
    repeticiones numeradas.

    **Y se elige igual siempre.** Antes ganaba la primera fila que devolviera la
    consulta —una cuenta puede tener reglas en varios departamentos, la `8005`
    tiene «OWNERS FEES» y «OWNERS FEE1»— y ese orden no está garantizado: el
    mismo reporte podía rotular distinto entre dos recargas. Es el mismo defecto
    que tenía el FALLBACK del resolvedor. Con el desempate por longitud y
    alfabético, la etiqueta no cambia sola.

    La etiqueta NUNCA identifica: la llave es `(departamento, cuenta)`. Esto es
    cosmético y no mueve un centavo.
    """
    from app.models.mapping import AccountMapping

    variantes: dict[str, set[str]] = {}
    for m in (await db.execute(select(AccountMapping).where(
            AccountMapping.active_status == "YES"))).scalars():
        code = (m.account_code or "").strip()
        if not code:
            continue
        for parte in (m.account_name_example or "").split("|"):
            parte = parte.strip()
            if parte:
                variantes.setdefault(code, set()).add(parte)

    def mejor(nombres: set[str]) -> str:
        limpios = [n for n in nombres if not n[-1:].isdigit()]
        if limpios:
            return sorted(limpios, key=lambda n: (-len(n), n))[0]
        # Ninguna variante limpia. Si todas son el MISMO nombre numerado —la
        # 8015 tiene «PROPERTY INSURANCE1» hasta la 5— el nombre es el tronco:
        # son la misma cuenta repetida, no cinco seguros distintos.
        troncos = {re.sub(r"\s*\d+$", "", n).strip() for n in nombres}
        if len(troncos) == 1:
            unico = troncos.pop()
            if unico:
                return unico
        return sorted(nombres, key=lambda n: (-len(n), n))[0]

    return {c: mejor(n) for c, n in variantes.items() if n}


def _fila(tipo: str, etiqueta: str, meses: list[float], *,
          cuenta: str = "", nivel: int = 1, clave: str = "") -> dict:
    # El total anual es SIEMPRE la suma de los doce meses. Es el bug de la fila
    # 76 del Excel, la única fila del archivo cuyos meses y cuyo anual salían de
    # fuentes distintas: si un día no coincidían, nada avisaba.
    return {"tipo": tipo, "nivel": nivel, "cuenta": cuenta,
            "etiqueta": etiqueta, "clave": clave or f"{tipo}|{cuenta}|{etiqueta}",
            "meses": [_r(v) for v in meses], "total": _r(sum(meses))}


def _pct(etiqueta: str, num: list[float], den: list[float]) -> dict:
    """Fila de ratio. Viaja como PORCENTAJE (0.35 = 35%), no como plata.

    En el Excel estas dos filas tenían formato de moneda y se leían `$0.35`.
    """
    meses = [(num[i] / den[i]) if den[i] else 0.0 for i in range(12)]
    tot_den, tot_num = sum(den), sum(num)
    f = _fila("pct", etiqueta, meses, nivel=2)
    f["total"] = round(tot_num / tot_den, 4) if tot_den else 0.0
    f["meses"] = [round(v, 4) for v in meses]
    return f


def _num(etiqueta: str, meses: list[float], *, dec: int = 1, clave: str = "") -> dict:
    """Fila de estadística: noches, unidades. No es plata, no lleva `$`."""
    f = _fila("stat", etiqueta, meses, nivel=2, clave=clave)
    f["meses"] = [round(v, dec) for v in meses]
    f["total"] = round(sum(meses), dec)
    return f


async def _bloques_de_rooms(
    db: AsyncSession, scenario: Scenario, nombres_cuenta: dict[str, str],
    consolidado: dict,
) -> list[dict]:
    """Rooms abierto en cuatro bloques fijos: consolidado, Standard, Villas,
    Residencias — cada uno con estadísticas, ingreso, nómina, opex y utilidad.

    **El consolidado es el que cuenta.** Se recibe ya armado, por el mismo camino
    que todos los demás departamentos, para que siga amarrando contra el resumen.
    Los tres de abajo son una APERTURA del mismo dinero: van marcados
    `es_apertura` y **no se suman a ningún total**. Sumarlos contaría Rooms dos
    veces — y como el consolidado ya cuadra contra el motor, el descuadre
    aparecería en el reporte que existe justamente para detectar descuadres.

    De dónde sale cada cosa: el ingreso y las noches se parten por CATEGORÍA de
    habitación (`SH07`→Villas, `SH08`→Residencia); el costo se parte por el
    reparto de Rooms. Hoy los porcentajes del reparto están en cero, así que el
    costo se queda entero en Standard y los sets muestran ingreso sin costo. No
    es un error del reporte: es que el reparto no se ha cargado, y verlo así es
    exactamente lo que hace falta para darse cuenta.

    **Solo aplica a los escenarios armados en la app.** Los sets se calculan
    leyendo los auxiliares (opex, planilla, repartos) y las tarifas por
    categoría; un escenario importado tiene su P&L en el GL y esas tablas
    contienen otra cosa. En el Budget 2026 Final la diferencia daba $79,268 de
    gasto — no es un error del dato: son dos fuentes distintas del mismo
    departamento, y ponerlas una debajo de la otra confunde más que la falta.
    """
    from app.api.rooms_sets_api import rooms_por_set

    if getattr(scenario, "source_mode", "imported") != "checkbook":
        consolidado["apertura_no_aplica"] = True
        return [consolidado]

    try:
        data = await rooms_por_set(scenario.id, db)
    except Exception:  # noqa: BLE001 — la apertura no puede tumbar el reporte
        return [consolidado]

    filas_set = data.get("rows", [])

    # **Sin ingreso por set no hay apertura que mostrar.** El ingreso de los sets
    # sale de las tarifas y la ocupación POR CATEGORÍA; un escenario importado no
    # las tiene, así que cada set saldría con su costo y cero ingreso — una
    # «utilidad» de −$321,124 debajo de un consolidado de +$1,385,006. Es
    # exactamente el defecto que se vino a arreglar, un nivel más abajo.
    if not any(any(f["revenue"]) for f in filas_set):
        return [consolidado]

    # Cuando SÍ hay apertura, se muestra aunque no cierre contra el consolidado —
    # pero se dice de cuánto es la diferencia. En el Budget 2027 Working son
    # $326,712 de Villas y Residencias que los drivers facturan y la línea del
    # checkbook no tiene: esconder los bloques taparía el hallazgo, y el owner
    # los pidió fijos justamente para poder mirar esto.
    dif_ing = sum(sum(f["revenue"]) for f in filas_set) - consolidado["ingreso_anual"]
    dif_gas = sum(sum(f["costo"]) for f in filas_set) - consolidado["gasto_anual"]
    if abs(dif_ing) > 1.0 or abs(dif_gas) > 1.0:
        consolidado["apertura_no_cuadra"] = {
            "dif_ingresos": _r(dif_ing), "dif_gastos": _r(dif_gas)}

    bloques = [consolidado]
    for f in filas_set:
        rev, disp, occ = f["revenue"], f["noches_disponibles"], f["noches_ocupadas"]
        clave = f["key"]
        filas: list[dict] = []

        filas.append(_fila("seccion", "ESTADÍSTICAS", [0.0] * 12, nivel=0,
                           clave=f"ROOMS|{clave}|SEC|STAT"))
        filas.append(_num("Unidades", [float(f["unidades"])] * 12, dec=0,
                          clave=f"ROOMS|{clave}|UNIDADES"))
        filas[-1]["total"] = f["unidades"]          # son las mismas, no doce veces
        filas.append(_num("Noches disponibles", disp, clave=f"ROOMS|{clave}|DISP"))
        filas.append(_num("Noches ocupadas", occ, clave=f"ROOMS|{clave}|OCUP"))
        filas.append(_pct("Ocupación", occ, disp))
        filas.append(_fila("detalle", "ADR", [
            _r(rev[i] / occ[i]) if occ[i] else 0.0 for i in range(12)],
            nivel=2, clave=f"ROOMS|{clave}|ADR"))
        filas[-1]["total"] = _r(sum(rev) / sum(occ)) if sum(occ) else 0.0
        filas.append(_fila("detalle", "RevPAR", [
            _r(rev[i] / disp[i]) if disp[i] else 0.0 for i in range(12)],
            nivel=2, clave=f"ROOMS|{clave}|REVPAR"))
        filas[-1]["total"] = _r(sum(rev) / sum(disp)) if sum(disp) else 0.0

        filas.append(_fila("seccion", "INGRESOS", [0.0] * 12, nivel=0,
                           clave=f"ROOMS|{clave}|SEC|4"))
        filas.append(_fila("detalle", "Room Revenue", rev,
                           clave=f"ROOMS|{clave}|REV"))
        filas.append(_fila("subtotal", "Total Ingresos", rev, nivel=1,
                           clave=f"ROOMS|{clave}|TOT|4"))

        # El costo, cuenta por cuenta, agrupado por clase USALI como en los demás
        # bloques. Sale del mismo recorrido que arma los cubos del set.
        gasto = [0.0] * 12
        for clase, titulo, _key in SECCIONES:
            if clase == "4":
                continue
            delaclase = sorted((c, v) for c, v in f.get("detalle", {}).items()
                               if _clase(c) == clase)
            if not delaclase:
                continue
            filas.append(_fila("seccion", titulo, [0.0] * 12, nivel=0,
                               clave=f"ROOMS|{clave}|SEC|{clase}"))
            suma = [0.0] * 12
            for cuenta, meses in delaclase:
                filas.append(_fila("detalle", nombres_cuenta.get(cuenta) or cuenta,
                                   meses, cuenta=cuenta,
                                   clave=f"ROOMS|{clave}|{cuenta}"))
                for i in range(12):
                    suma[i] += meses[i]
            filas.append(_fila("subtotal", f"Total {titulo.title()}", suma,
                               nivel=1, clave=f"ROOMS|{clave}|TOT|{clase}"))
            for i in range(12):
                gasto[i] += suma[i]

        # El crédito de reparto (la 4999) es gasto que SE FUE, no ingreso. Su
        # cuenta es de clase 4, así que el recorrido de arriba —que solo mira 5,
        # 6 y 7— lo deja fuera. Va en su propia sección y SUMA AL GASTO en
        # negativo: sin esto, Rooms Standard mostraría el costo entero, incluido
        # el que entregó a las villas.
        reparto = sorted((c, v) for c, v in f.get("detalle", {}).items()
                         if _clase(c) == "4")
        if reparto:
            filas.append(_fila("seccion", "REPARTOS", [0.0] * 12, nivel=0,
                               clave=f"ROOMS|{clave}|SEC|REP"))
            for cuenta, meses in reparto:
                filas.append(_fila("detalle", nombres_cuenta.get(cuenta) or cuenta,
                                   meses, cuenta=cuenta,
                                   clave=f"ROOMS|{clave}|REP|{cuenta}"))
                for i in range(12):
                    gasto[i] += meses[i]

        utilidad = [rev[i] - gasto[i] for i in range(12)]
        filas.append(_fila("total", "UTILIDAD NETA", utilidad, nivel=0,
                           clave=f"ROOMS|{clave}|UTILIDAD"))
        filas.append(_pct("% de Ingresos del Depto.", gasto, rev))
        filas.append(_pct("% Utilidad", utilidad, rev))

        bloques.append({
            "clave": f"ROOMS|{clave}",
            "dept_code": f.get("dept_code") or "",
            "titulo": f["name"],
            "titulo_en": "",
            "tipo": "OPERATIVO",
            # No se suma a ningún total: es el consolidado de arriba, abierto.
            "es_apertura": True,
            "apertura_de": "0110",
            "ingreso_anual": _r(sum(rev)),
            "gasto_anual": _r(sum(gasto)),
            "utilidad_anual": _r(sum(utilidad)),
            "filas": filas,
        })
    return bloques


@router.get("/reports/pl-full-detail/{scenario_id}/")
async def pl_full_detail(
    scenario_id: str,
    incluir_vacios: bool = Query(False, description="mostrar cuentas en cero"),
    db: AsyncSession = Depends(get_db),
):
    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise ErrorApi(404, "escenario.no_encontrado")

    acum = await _cargar_detalle(db, scenario)
    from app.engine.recalculate import load_active_account_mappings
    es_ingreso = _hacer_es_ingreso(
        pl_engine.construir_resolvedor(await load_active_account_mappings(db)))
    hay_ingreso_detalle = any(
        es_ingreso(d, c) for (d, c), v in acum.datos.items()
        if any(abs(x) > 0.005 for x in v))
    nombres_cuenta = await _nombres_de_cuenta(db)
    catalogo = {d.dept_code: d for d in (await db.execute(
        select(DepartmentCatalog))).scalars()}

    # ── Bloque RESUMEN — sale del motor, es la verdad contra la que se cuadra ──
    report_lines = await load_report_line_config(db)
    orden_linea = {r["line_code"]: r.get("display_order", 9999) for r in report_lines}
    nombre_linea = {r["line_code"]: r.get("line_name", r["line_code"]) for r in report_lines}
    seccion_linea = {r["line_code"]: r.get("section", "") for r in report_lines}
    tipo_linea = {r["line_code"]: r.get("line_type", "MAPPED") for r in report_lines}

    pl: dict[str, list[float]] = {}
    for mes in range(1, 13):
        for ln in await compute_pl_month(db, scenario, mes):
            pl.setdefault(ln.line_code, [0.0] * 12)[mes - 1] += float(ln.amount_usd)

    resumen = []
    for code in sorted((c for c in pl if c in orden_linea), key=lambda c: orden_linea[c]):
        lt = tipo_linea.get(code, "MAPPED")
        resumen.append(_fila(
            "total" if lt.startswith("CALCULATED") else "detalle",
            nombre_linea.get(code, code), pl[code],
            nivel=0 if lt.startswith("CALCULATED") else 1, clave=f"RESUMEN|{code}",
        ))
        resumen[-1]["seccion"] = seccion_linea.get(code, "")
        resumen[-1]["line_code"] = code

    # ── Bloques por departamento ─────────────────────────────────────────────
    # El ingreso de los escenarios de checkbook entra acá: sin él, cada bloque
    # mostraba solo el gasto y la «utilidad» del departamento era su costo en
    # negativo.
    # **Qué es «apagado» para un REPORTE.** En las pantallas de carga la pregunta
    # es por dimensión: el 0180 está apagado para planilla porque la gente vive
    # en sus hijos, pero sí tiene OPEX. Acá la pregunta es otra —«¿este hotel usa
    # este departamento?»— y solo se contesta que no cuando está apagado en TODAS
    # las dimensiones que le aplican. Con «apagado en alguna» el 0180 se caería
    # del reporte teniendo $406,696 de gasto.
    from app.api._apagados import apagados_por_dimension
    from app.api.provisioning_api import DIMS_DEPT

    _apagados_dim = await apagados_por_dimension(db, scenario.hotel_id)
    _cuenta: dict[str, int] = {}
    for _dim, _codigos in _apagados_dim.items():
        if _dim not in DIMS_DEPT:
            continue
        for _d in _codigos:
            _cuenta[_d] = _cuenta.get(_d, 0) + 1
    apagados_del_hotel = {d for d, n in _cuenta.items() if n >= len(DIMS_DEPT)}
    escondidos_con_plata: list[str] = []

    ingreso_cb = await _ingreso_de_checkbook(db, scenario, acum.deptos())
    # Qué secciones tiene ABIERTAS cada departamento, aunque estén en cero. Sin
    # esto, un departamento recién sembrado parece no tener OPEX ni costo.
    configuradas = await _clases_configuradas(db, scenario)
    if ingreso_cb:
        hay_ingreso_detalle = True

    # Los sets de Rooms (Villas, Residencias) NO llevan bloque propio: cuando el
    # reparto está activo su costo vive en su departamento, y con un bloque cada
    # uno el «consolidado» del 0110 no consolidaba nada — era la parte que se
    # quedó, con las villas listadas aparte y sin ingreso. Se suman al bloque
    # consolidado de Rooms y se abren abajo, en la apertura.
    from app.engine.recalculate import rooms_family
    _fam_rooms, sets_rooms = await rooms_family(db, ROOMS)
    deptos_rooms = {ROOMS} | set(sets_rooms)

    con_datos = acum.deptos() | set(ingreso_cb)
    if con_datos & deptos_rooms:
        con_datos = (con_datos - deptos_rooms) | {ROOMS}
    orden = [d for d in ORDEN_DEPTOS if d in con_datos]
    orden += sorted(d for d in con_datos if d not in ORDEN_DEPTOS and d != SIN_DEPTO)
    if SIN_DEPTO in con_datos:
        orden.append(SIN_DEPTO)   # al final: es el cajón de lo que no se ubicó

    bloques = []
    tot_ingreso = [0.0] * 12
    tot_gasto = [0.0] * 12

    for dept in orden:
        cuentas = (acum.por_deptos(deptos_rooms) if dept == ROOMS
                   else acum.por_depto(dept))
        filas_ingreso = list(ingreso_cb.get(dept, []))
        if dept == ROOMS:
            for d in sets_rooms:
                filas_ingreso += ingreso_cb.get(d, [])
        cat = catalogo.get(dept)
        # El below-GOP tiene bloque propio abajo: no es un departamento.
        cuentas = [(c, v) for c, v in cuentas if _clase(c) != "8"]
        if not cuentas and not filas_ingreso:
            continue

        filas: list[dict] = []
        subtot: dict[str, list[float]] = {}
        for clase, titulo, key in SECCIONES:
            de_la_seccion = [
                (c, v) for c, v in cuentas
                if (_clase(c) == clase and (clase != "4" or es_ingreso(dept, c)))
            ]
            if clase == "7":
                # Los créditos de reparto (4999 de Rooms, 4900 de Lavandería) son
                # gasto que SE FUE: van con el opex, en negativo, no como ingreso.
                de_la_seccion += [(c, v) for c, v in cuentas
                                  if _clase(c) == "4" and not es_ingreso(dept, c)]
            # El ingreso a nivel de línea del checkbook entra en INGRESOS, junto
            # a las cuentas 4xxx de los escenarios importados. Un escenario tiene
            # uno u otro camino, nunca los dos.
            del_checkbook = filas_ingreso if clase == "4" else []
            # La sección sale igual si el departamento la tiene abierta con las
            # cuentas en cero: es la diferencia entre «no gasta en esto» y
            # «todavía no lo presupuesté», y el bloque tiene que mostrarla.
            abierta = clase in configuradas.get(dept, set())
            if not de_la_seccion and not del_checkbook and not abierta and not incluir_vacios:
                subtot[key] = [0.0] * 12
                continue
            filas.append(_fila("seccion", titulo, [0.0] * 12, nivel=0,
                               clave=f"{dept}|SEC|{clase}"))
            suma = [0.0] * 12
            for etiqueta, cuenta, meses in del_checkbook:
                filas.append(_fila("detalle", etiqueta, meses, cuenta=cuenta,
                                   clave=f"{dept}|LINEA|{etiqueta}"))
                for i in range(12):
                    suma[i] += meses[i]
            for cuenta, meses in de_la_seccion:
                if not incluir_vacios and not any(abs(v) > 0.005 for v in meses):
                    continue
                etiqueta = (nombres_cuenta.get(cuenta)
                            or acum.nombres.get((dept, cuenta)) or cuenta)
                filas.append(_fila("detalle", etiqueta, meses, cuenta=cuenta,
                                   clave=f"{dept}|{cuenta}"))
                for i in range(12):
                    suma[i] += meses[i]
            filas.append(_fila("subtotal", f"Total {titulo.title()}", suma, nivel=1,
                               clave=f"{dept}|TOT|{clase}"))
            subtot[key] = suma

        ingreso = subtot.get("ingresos", [0.0] * 12)
        gasto = [subtot.get("costo", [0.0] * 12)[i]
                 + subtot.get("nomina", [0.0] * 12)[i]
                 + subtot.get("opex", [0.0] * 12)[i] for i in range(12)]
        # Bug 3 del Excel (fila 942): allá la nómina se restaba dos veces porque
        # dos filas compartían etiqueta. Acá cada componente entra UNA vez.
        utilidad = [ingreso[i] - gasto[i] for i in range(12)]
        filas.append(_fila("total", "UTILIDAD NETA", utilidad, nivel=0,
                           clave=f"{dept}|UTILIDAD"))
        filas.append(_pct("% de Ingresos del Depto.", gasto, ingreso))
        filas.append(_pct("% Utilidad", utilidad, ingreso))

        for i in range(12):
            tot_ingreso[i] += ingreso[i]
            tot_gasto[i] += gasto[i]

        # **Esconder en el reporte, con la regla del owner: solo si está en
        # cero.** «Se revisa que el departamento esté en 0 y después se esconde;
        # se esconde porque no se usa para ese hotel.» Un departamento apagado
        # que TIENE plata se muestra igual —y con el aviso de abajo—, porque la
        # matriz filtra visibilidad y nunca resta del P&L: si escondiera un
        # bloque con dinero, el reporte mostraría menos de lo que el estado de
        # resultados cobra, que es la única cosa que este reporte no puede hacer.
        if apagados_del_hotel and dept in apagados_del_hotel:
            if not any(abs(v) > 0.005 for v in ingreso + gasto):
                continue
            escondidos_con_plata.append(
                f"{cat.dept_name if cat else dept} (${sum(ingreso) - sum(gasto):,.2f})")

        bloque = {
            "clave": dept,
            "dept_code": dept,
            "titulo": ("Otros ingresos (sin departamento)" if dept == SIN_DEPTO
                       else (cat.dept_name if cat else dept)),
            "titulo_en": (cat.name_en if cat else ""),
            "tipo": "OVERHEAD" if (cat and cat.pl_kind == "OVERHEAD") else "OPERATIVO",
            "es_apertura": False,
            "ingreso_anual": _r(sum(ingreso)),
            "gasto_anual": _r(sum(gasto)),
            "utilidad_anual": _r(sum(utilidad)),
            "filas": filas,
        }
        if dept == ROOMS:
            # Rooms se abre en cuatro: el consolidado (este) y sus tres sets.
            # Los sets no se suman a nada — son este mismo dinero, abierto.
            bloque["titulo"] += " (consolidado)"
            bloques.extend(await _bloques_de_rooms(db, scenario, nombres_cuenta, bloque))
        else:
            bloques.append(bloque)

    # ── Gastos de Propiedad (below-GOP) ──────────────────────────────────────
    #
    # El impuesto de renta va abajo del GOP pero NO es un gasto de la propiedad:
    # tiene su propia línea en el resumen, después del EBT. Se deja fuera del
    # bloque por los DOS lados —ni su cuenta en el detalle ni su línea en el
    # cuadre—, porque excluirlo de uno solo descuadra el bloque: en el Actual
    # 2026 eran $123,179 que aparecían en el detalle y no del otro lado.
    LINEA_IMPUESTO = "INCOME_TAXES"
    def es_impuesto(cta: str) -> bool:
        return pl_engine.nonop_line_for_account(cta) == LINEA_IMPUESTO

    propiedad: list[dict] = []
    bg: dict[str, list[float]] = {}
    nombres_bg: dict[str, str] = {}
    for (_d, cuenta), meses in acum.datos.items():
        if _clase(cuenta) != "8" or es_impuesto(cuenta):
            continue
        fila = bg.setdefault(cuenta, [0.0] * 12)
        for i in range(12):
            fila[i] += meses[i]
    for (d, cuenta), n in acum.nombres.items():
        if _clase(cuenta) == "8" and n:
            nombres_bg.setdefault(cuenta, n)
    # El mini-checkbook del propietario NO pasa por el mapeo de cuentas: siembra
    # la línea del reporte directo. Se lista por su línea, que es su identidad.
    for e in (await db.execute(select(NonOpEntry).where(
            NonOpEntry.scenario_id == scenario.id))).scalars():
        meses = [float(getattr(e, m) or 0) for m in MESES]
        if not any(abs(v) > 0.005 for v in meses):
            continue
        if e.report_line_code == LINEA_IMPUESTO:
            continue
        propiedad.append(_fila(
            "detalle",
            (e.detail_desc or e.account_name or e.report_line_code),
            meses, cuenta=(e.account_code or ""),
            clave=f"NONOP|{e.report_line_code}|{e.detail_code}"))
        propiedad[-1]["line_code"] = e.report_line_code
    for cuenta in sorted(bg):
        meses = bg[cuenta]
        if not incluir_vacios and not any(abs(v) > 0.005 for v in meses):
            continue
        etiqueta = nombres_cuenta.get(cuenta) or nombres_bg.get(cuenta) or cuenta
        f = _fila("detalle", etiqueta, meses, cuenta=cuenta, clave=f"BG|{cuenta}")
        f["line_code"] = pl_engine.nonop_line_for_account(cuenta) or ""
        propiedad.append(f)
    # **Las cuentas de propiedad salen TODAS, tengan saldo o no.** Son once en el
    # catálogo y el bloque mostraba las dos con movimiento: parecía que el resto
    # no existiera, cuando lo que pasa es que no se han presupuestado. Igual que
    # las secciones de los departamentos, la ausencia y el cero son cosas
    # distintas y el reporte tiene que decir cuál es.
    #
    # A diferencia de OPEX y costos, acá no hace falta sembrar nada en la base:
    # estas cuentas no tienen departamento, son las mismas para todo escenario,
    # así que la lista sale del catálogo directo.
    ya_estan = {(f.get("cuenta") or "").strip() for f in propiedad}
    for cuenta in sorted(await _cuentas_de_propiedad(db)):
        if cuenta in ya_estan or es_impuesto(cuenta):
            continue
        f = _fila("detalle", nombres_cuenta.get(cuenta) or cuenta, [0.0] * 12,
                  cuenta=cuenta, clave=f"BG|{cuenta}")
        f["line_code"] = pl_engine.nonop_line_for_account(cuenta) or ""
        propiedad.append(f)
    # Por número de cuenta, como se lee un mayor. Si no, las que se agregaron en
    # cero quedan todas al final y el bloque parece dos listas pegadas.
    propiedad.sort(key=lambda f: ((f.get("cuenta") or "zzzz"), f["etiqueta"]))

    # **Lo que abajo del GOP no pasa por una cuenta.**
    #
    # El honorario de administración y la reserva de capital se calculan con un
    # PORCENTAJE sobre los ingresos: el motor los siembra a nivel de LÍNEA y
    # nunca existe una fila de cuenta con ese monto. Este bloque leía cuentas,
    # así que no los veía — el resumen decía $842,577 abajo del GOP y el detalle
    # mostraba $414,000. Faltaban $428,577 que el P&L sí está cobrando.
    #
    # No se inventa una cuenta para taparlo: se agrega la línea con su nombre y
    # se dice de dónde sale. Y como el monto se toma del motor, el bloque cierra
    # contra el P&L por construcción, no por coincidencia.
    #
    # El impuesto de renta queda FUERA a propósito: está abajo del GOP pero no es
    # un gasto de la propiedad, y meterlo acá inflaría el bloque con algo que el
    # resumen ya muestra en su lugar.
    por_linea: dict[str, float] = {}
    for f in propiedad:
        lc = f.get("line_code") or ""
        if lc:
            por_linea[lc] = por_linea.get(lc, 0.0) + f["total"]
    for code in pl_engine._NONOP_LINE_TO_BUCKET:
        if code == LINEA_IMPUESTO:
            continue
        meses_linea = pl.get(code)
        if not meses_linea:
            continue
        resto = [meses_linea[i] for i in range(12)]
        for f in propiedad:
            if (f.get("line_code") or "") == code:
                for i in range(12):
                    resto[i] -= f["meses"][i]
        if not any(abs(v) > 0.005 for v in resto):
            continue
        f = _fila("detalle", f"{nombre_linea.get(code, code)} (calculado)", resto,
                  clave=f"BG|DRIVER|{code}")
        f["line_code"] = code
        f["nota"] = ("Sale de un porcentaje sobre los ingresos, no de una cuenta "
                     "del checkbook.")
        propiedad.append(f)

    if propiedad:
        # El total suma las filas con monto; las que se agregaron en cero no lo
        # mueven — están para que se vea qué falta, no para cambiar la cifra.
        suma = [sum(f["meses"][i] for f in propiedad) for i in range(12)]
        propiedad.append(_fila("total", "TOTAL GASTOS DE PROPIEDAD", suma, nivel=0,
                               clave="BG|TOTAL"))

    # ── Rooms abierto en sus tres sets (D7) ──────────────────────────────────
    kpis = await _kpis_por_set(db, scenario)

    # ── Socios del Club Madresal: estadístico, no plata ──────────────────────
    # El Club vende ACCESO a las instalaciones; el desarrollo inmobiliario de
    # atrás no es parte de este P&L. La cuota de acceso ya está en REV_CLUB —
    # esto explica de dónde sale. Va arriba, con los KPIs, no en ninguna línea.
    from app.api.club_stats_api import (
        CAMPOS as CLUB_CAMPOS, ETIQUETAS as CLUB_ETIQUETAS,
        cierre as club_cierre, club_visible, membresias_por_mes,
    )
    club = None
    if await club_visible(db, scenario.hotel_id):
        mm, cargados = await membresias_por_mes(db, scenario.id)
        club = {
            "filas": [{"campo": c, "etiqueta": CLUB_ETIQUETAS[c],
                       "meses": mm[c], "total_anio": club_cierre(mm[c], cargados)}
                      for c in CLUB_CAMPOS],
            "hay_datos": any(any(mm[c]) for c in CLUB_CAMPOS),
            # El anual es el saldo de diciembre, NO la suma: son socios.
            "total_es_cierre": True,
        }

    # ── El cuadre: el reporte se audita contra el motor ──────────────────────
    def _pl(code: str) -> list[float]:
        return pl.get(code, [0.0] * 12)

    # El bloque de abajo del GOP también se audita. No lo hacía, y por eso el
    # faltante del honorario y la reserva —$428,577— vivió ahí sin que nada lo
    # señalara: el cuadre solo miraba ingresos y gastos operativos.
    bg_pl = [0.0] * 12
    for code in pl_engine._NONOP_LINE_TO_BUCKET:
        if code == LINEA_IMPUESTO:
            continue
        for i, v in enumerate(pl.get(code) or []):
            bg_pl[i] += v
    bg_detalle = [sum(f["meses"][i] for f in propiedad if f["tipo"] == "detalle")
                  for i in range(12)]
    dif_bg = _r(sum(bg_detalle) - sum(bg_pl))

    ingreso_pl = _pl("TOTAL_REVENUES")
    gasto_pl = [_pl("TOTAL_OPERATING_EXPENSES")[i] + _pl("TOTAL_OVERHEAD_EXPENSES")[i]
                for i in range(12)]
    dif_ing = _r(sum(tot_ingreso) - sum(ingreso_pl))
    dif_gas = _r(sum(tot_gasto) - sum(gasto_pl))

    # El cuadre del ingreso solo tiene sentido si el escenario TIENE el ingreso
    # abierto por cuenta. En los que salen de rate cards no lo tiene, y marcar
    # eso como descuadre sería llamar error a una decisión: prorratear el
    # ingreso por cuenta es inventar números.
    ing_ok = (not hay_ingreso_detalle) or abs(dif_ing) <= 1.0
    gas_ok = abs(dif_gas) <= 1.0
    bg_ok = abs(dif_bg) <= 1.0

    avisos = []
    if not acum.datos:
        avisos.append("Este escenario no tiene NADA cargado en las tablas de "
                      "detalle: el reporte sale en cero. No es un error del "
                      "reporte, es que no hay dato.")
    elif not hay_ingreso_detalle:
        avisos.append(
            "Este escenario no trae el ingreso abierto por cuenta: sale de las "
            "rate cards a nivel de línea. Los bloques de departamento muestran "
            f"el costo, no el ingreso — el total del resumen (${sum(ingreso_pl):,.2f}) "
            "sí está completo. Prorratearlo por cuenta sería inventar números.")
    if not gas_ok or (hay_ingreso_detalle and not ing_ok):
        detalle_desc = []
        if hay_ingreso_detalle and not ing_ok:
            detalle_desc.append(f"ingresos {dif_ing:+,.2f}")
        if not gas_ok:
            detalle_desc.append(f"gastos {dif_gas:+,.2f}")
        avisos.append(
            f"El detalle no amarra con el resumen: {' · '.join(detalle_desc)}. "
            "El resumen sale del snapshot que se subió y el detalle sale del "
            "GL del mismo archivo: cuando no coinciden, el que está mal es el "
            "dato, no el reporte. Se ve cuenta por cuenta en /admin/control, y "
            "la Vista previa del importador lo revisa antes de subir.")
    if any(b.get("apertura_no_aplica") for b in bloques):
        avisos.append(
            "Rooms no se abre en Standard / Villas / Residencias en este "
            "escenario: la apertura se calcula con las tarifas y la ocupación "
            "por categoría y con los auxiliares de la app, y este escenario trae "
            "su P&L importado del GL. Son dos fuentes distintas del mismo "
            "departamento; mostrarlas juntas diría un número que no es de acá.")
    nocuadra = next((b.get("apertura_no_cuadra") for b in bloques
                     if b.get("apertura_no_cuadra")), None)
    if nocuadra:
        partes = []
        if abs(nocuadra["dif_ingresos"]) > 1.0:
            partes.append(f"ingreso {nocuadra['dif_ingresos']:+,.2f}")
        if abs(nocuadra["dif_gastos"]) > 1.0:
            partes.append(f"gasto {nocuadra['dif_gastos']:+,.2f}")
        avisos.append(
            "La apertura de Rooms (Standard / Villas / Residencias) NO suma lo "
            f"mismo que el consolidado: {' · '.join(partes)}. Los sets se arman "
            "con las tarifas y la ocupación POR CATEGORÍA; el consolidado usa la "
            "línea de ingreso del checkbook, que es la que ve el P&L. Cuando la "
            "diferencia es positiva, los drivers están facturando categorías que "
            "esa línea todavía no incluye — se sincroniza volviendo a empujar "
            "los drivers al checkbook de ingresos. El consolidado es el que manda.")
    if abs(dif_bg) > 1.0:
        # Decir CUÁL línea y por cuánto, no solo el total. Un descuadre con
        # nombre se arregla; uno que es solo una cifra se queda ahí. Los tres
        # escenarios importados que no amarraban resultaron ser todos la misma
        # línea —diferencial cambiario, cuenta 8045— y eso no se veía.
        # Hay DOS cosas distintas acá y llamarlas igual costó una sesión entera
        # persiguiendo un fantasma:
        #
        #  · «sin apertura» — el resumen subido trae CERO en esa línea y el GL
        #    tiene monto. No es un descuadre del dato: los P&L importados traen
        #    el agregado below-GOP y no su desglose, así que esas líneas nunca
        #    vinieron en el archivo. Escribirlas a mano no arregla nada (el
        #    motor ni siquiera emite algunas, ej. FINANCIAL_LOSSES, que colapsa
        #    en el cajón bank_interest).
        #  · «no cuadra» — el resumen SÍ trae monto y no coincide con el GL. Eso
        #    sí es dato que se contradice y hay que ir a ver.
        sin_apertura, no_cuadran = [], []
        for code in pl_engine._NONOP_LINE_TO_BUCKET:
            if code == LINEA_IMPUESTO:
                continue
            del_motor = sum(pl.get(code) or [])
            del_detalle = sum(f["total"] for f in propiedad
                              if f["tipo"] == "detalle" and (f.get("line_code") or "") == code)
            if abs(del_detalle - del_motor) <= 1.0:
                continue
            etiqueta = nombre_linea.get(code, code)
            if abs(del_motor) <= 1.0:
                sin_apertura.append(f"{etiqueta} ({del_detalle:,.2f})")
            else:
                no_cuadran.append(
                    f"{etiqueta} (detalle {del_detalle:,.2f} "
                    f"vs resumen {del_motor:,.2f})")

        if no_cuadran:
            avisos.append(
                f"Los Gastos de Propiedad no amarran con el resumen: {dif_bg:+,.2f}"
                " — " + " · ".join(no_cuadran)
                + ". El detalle sale del GL y el resumen del P&L que se subió, "
                  "los dos del mismo archivo: cuando los dos traen monto y no "
                  "coinciden, el que está mal es el dato.")
        if sin_apertura:
            avisos.append(
                "El resumen subido no trae la apertura de los Gastos de "
                "Propiedad: " + " · ".join(sin_apertura) + " existen en el GL y "
                "el resumen solo trae el agregado. **No es un descuadre** — el "
                "resultado del escenario está bien, porque EBITDA, EBT e impuesto "
                "se guardan tal cual vienen y `TOTAL_NON_OP` se deriva de "
                "`GOP − EBITDA Before`. Lo que falta es el desglose, y para tenerlo "
                "el archivo tendría que subir esas líneas.")
    if escondidos_con_plata:
        avisos.append(
            "Estos departamentos están apagados en Provisionamiento pero TIENEN "
            "movimiento, así que se muestran igual: " + " · ".join(escondidos_con_plata)
            + ". Esconder es de la vista y nunca resta del P&L — un bloque con "
              "plata escondido haría que el reporte mostrara menos de lo que el "
              "estado de resultados cobra. Se esconden solos cuando queden en cero.")
    if kpis.get("diluyen"):
        avisos.append(
            "Sin ocupación cargada: " + ", ".join(kpis["diluyen"]) + ". Sus "
            "unidades SÍ suman noches disponibles al consolidado, así que "
            "diluyen la ocupación general y el RevPAR del hotel.")

    return {
        "scenario_id": scenario.id,
        "scenario": f"{scenario.type} {scenario.version} {scenario.year}",
        "year": scenario.year,
        "source_mode": getattr(scenario, "source_mode", "imported"),
        "moneda": "USD",
        "avisos": avisos,
        "kpis": kpis,
        "club": club,
        "resumen": resumen,
        "bloques": bloques,
        "propiedad": propiedad,
        "cuadre": {
            "ingresos_detalle": _r(sum(tot_ingreso)),
            "ingresos_pl": _r(sum(ingreso_pl)),
            "dif_ingresos": dif_ing,
            "gastos_detalle": _r(sum(tot_gasto)),
            "gastos_pl": _r(sum(gasto_pl)),
            "dif_gastos": dif_gas,
            "propiedad_detalle": _r(sum(bg_detalle)),
            "propiedad_pl": _r(sum(bg_pl)),
            "dif_propiedad": dif_bg,
            "gop_pl": _r(sum(_pl("TOTAL_GOP"))),
            "net_pl": _r(sum(_pl("NET_PROFIT"))),
            "ingreso_por_cuenta": hay_ingreso_detalle,
            "ok": ing_ok and gas_ok and bg_ok,
        },
    }


@router.get("/reports/pl-full-detail/{scenario_id}/export/")
async def exportar_pl_full_detail(
    scenario_id: str,
    incluir_vacios: bool = Query(False, description="incluir cuentas en cero"),
    db: AsyncSession = Depends(get_db),
):
    """El mismo reporte, en `.xlsx`.

    Arma el payload con la MISMA función que sirve la pantalla y se lo pasa al
    exportador. Si el Excel calculara por su cuenta, podría decir algo distinto
    a lo que se ve en pantalla y no habría forma de saber cuál creer.
    """
    from fastapi.responses import Response
    from app.export.pl_full_detail_excel import build_pl_full_detail_workbook

    data = await pl_full_detail(scenario_id, incluir_vacios, db)
    nombre = f"{hotel_slug()}_PL_Full_Detail_{data['scenario'].replace(' ', '_')}.xlsx"
    return Response(
        content=build_pl_full_detail_workbook(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


async def _kpis_por_set(db: AsyncSession, scenario: Scenario) -> dict:
    """Rooms abierto en Standard / Villas / Residencias, cada uno con ocupación,
    ADR y RevPAR (decisión D7).

    Reusa `/reports/rooms-sets/`, que ya devuelve por set el ingreso, el costo,
    las noches disponibles y las ocupadas mes a mes. Acá solo se derivan los tres
    ratios:

        ocupación = noches ocupadas / noches disponibles
        ADR       = ingreso / noches ocupadas
        RevPAR    = ingreso / noches disponibles

    ⚠️ Las unidades de un set sin ocupación cargada **igual suman noches
    disponibles al consolidado**: diluyen la ocupación general y el RevPAR del
    hotel. Por eso cada set viaja con `sin_ocupacion`, para que la pantalla lo
    pueda decir en vez de mostrar un cero que parece un dato.
    """
    from app.api.rooms_sets_api import rooms_por_set

    try:
        data = await rooms_por_set(scenario.id, db)
    except Exception:  # noqa: BLE001 — un KPI que falla no puede tumbar el reporte
        return {"sets": [], "consolidado": None, "disponible": False}

    def ratios(rev: list[float], disp: list[float], occ: list[float]) -> dict:
        return {
            "ocupacion": [round(occ[i] / disp[i], 4) if disp[i] else 0.0 for i in range(12)],
            "adr": [_r(rev[i] / occ[i]) if occ[i] else 0.0 for i in range(12)],
            "revpar": [_r(rev[i] / disp[i]) if disp[i] else 0.0 for i in range(12)],
        }

    sets = []
    for f in data.get("rows", []):
        rev, disp, occ = f["revenue"], f["noches_disponibles"], f["noches_ocupadas"]
        s = {
            "clave": f["key"], "nombre": f["name"], "unidades": f["unidades"],
            "noches_disponibles": disp, "noches_ocupadas": occ,
            "revenue": rev, "costo": f["costo"],
            "revenue_anual": f["revenue_anual"], "costo_anual": f["costo_anual"],
            "sin_ocupacion": sum(occ) == 0 and sum(disp) > 0,
            **ratios(rev, disp, occ),
        }
        s["ocupacion_anual"] = round(sum(occ) / sum(disp), 4) if sum(disp) else 0.0
        s["adr_anual"] = _r(sum(rev) / sum(occ)) if sum(occ) else 0.0
        s["revpar_anual"] = _r(sum(rev) / sum(disp)) if sum(disp) else 0.0
        sets.append(s)

    disp_c = [sum(s["noches_disponibles"][i] for s in sets) for i in range(12)]
    occ_c = [sum(s["noches_ocupadas"][i] for s in sets) for i in range(12)]
    rev_c = [sum(s["revenue"][i] for s in sets) for i in range(12)]
    consolidado = {
        "nombre": "Rooms (consolidado)",
        "unidades": sum(s["unidades"] for s in sets),
        "noches_disponibles": disp_c, "noches_ocupadas": occ_c, "revenue": rev_c,
        "revenue_anual": _r(sum(rev_c)),
        "ocupacion_anual": round(sum(occ_c) / sum(disp_c), 4) if sum(disp_c) else 0.0,
        "adr_anual": _r(sum(rev_c) / sum(occ_c)) if sum(occ_c) else 0.0,
        "revpar_anual": _r(sum(rev_c) / sum(disp_c)) if sum(disp_c) else 0.0,
        **ratios(rev_c, disp_c, occ_c),
    }
    return {"sets": sets, "consolidado": consolidado, "disponible": True,
            "diluyen": [s["nombre"] for s in sets if s["sin_ocupacion"]]}
