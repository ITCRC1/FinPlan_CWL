"""Cash Flow MÉTODO DIRECTO — router.

Arma el flujo como cobros menos pagos, pero NO con un cálculo propio: los
criterios salen de la fuente única (`_cashflow_criterios`) y los movimientos de
capital de trabajo se leen del flujo INDIRECTO tal como quedan en esa pantalla.
Este método es una presentación de la misma caja, no un segundo modelo.

Conciliación verificada contra los ocho escenarios vivos de CWL: la brecha
máxima es de 6 centavos, que es el redondeo a dos decimales por fila. El
histórico de lo que estaba mal —el aguinaldo contado dos veces, la cola de
diciembre que enero no pagaba, el IVA que se pagaba sin acreditarse— está en
`docs/AUDITORIA_CASHFLOW_DOS_METODOS.md`.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.errores import ErrorApi
from app.i18n import DEFAULT_LOCALE
from app.textos import Idioma, t
from app.api._candado import candado
from app.api._cashflow_criterios import cargar_criterios, payroll_series, ventana_wc
from app.db import get_session
from app.models.scenario import Scenario
from app.models.cashflow_directo_config import CashFlowDirectoConfig
from app.models.cashflow_params import CashFlowParams
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_position import PayrollPosition
from app.models.exchange_rate import ExchangeRate, get_tc_for_month
from app.models.hotel import Hotel
from app.engine import cashflow_criterios as crit
from app.engine import renta_salario as renta
from app.engine.cashflow_budget import effective_timing_matrix
from app.engine.cashflow_directo import compute_cashflow_directo, DIRECT_DEFAULTS
from app.engine import recalculate as recalc
from app.engine import pl_engine
from app.engine.payroll_calculator import calc_base, total_entry
from app.importers.gl_detail_importer import ALLOC_EXCL_PAYROLL

router = APIRouter(tags=["cashflow-directo"])


async def _get_scenario_or_404(session, scenario_id: str) -> Scenario:
    scn = await session.get(Scenario, scenario_id)
    if not scn:
        raise ErrorApi(404, "escenario.no_encontrado")
    return scn


def _z() -> list[float]:
    return [0.0] * 12


def una_por_codigo_canonico(lineas) -> dict:
    """Colapsa los dos vocabularios del P&L a uno: {codigo_canonico: linea}.

    El motor emite la misma linea dos veces —`OPEXP_ROOMS` y su alias
    `OPEX_ROOMS`, mismo nombre visible y mismo monto— porque hay consumidores
    de cada vocabulario. Quien acumule por NOMBRE tiene que quedarse con una
    sola, o muestra el gasto al doble.

    Se queda la de mayor valor absoluto: es el criterio de `add_pl_aliases`,
    donde el vocabulario que no calculo la linea la trae en 0.
    """
    canon = {k: v[0] for k, v in pl_engine._MOTOR_TO_CANON.items()}
    fuera: dict[str, object] = {}
    for ln in lineas:
        code = canon.get(ln.line_code or "", ln.line_code or "")
        previa = fuera.get(code)
        if previa is None or abs(float(ln.amount_usd or 0)) > abs(
                float(previa.amount_usd or 0)):
            fuera[code] = ln
    return fuera


def codigos_canonicos(tabla: dict) -> dict:
    """Traduce las CLAVES de una tabla al vocabulario canonico.

    Existe para `_TOTALES`: sus claves eran las del motor (`TOTAL_OPEXP`) y al
    canonizar las lineas pasan a llegar como `TOTAL_OPERATING_EXPENSES`. Sin
    esta traduccion la base de gasto del metodo directo sale en CERO.
    """
    canon = {k: v[0] for k, v in pl_engine._MOTOR_TO_CANON.items()}
    return {canon.get(k, k): v for k, v in tabla.items()}


async def _lines_from_pl(session, scenario: Scenario):
    """Alimenta el motor directo con los datos REALES del escenario.

    Devuelve (revenue_lines, opex_lines, payroll_lines, prop, totales). Las tres
    primeras y `prop` son el DETALLE que se muestra en los auxiliares; `totales`
    es lo que se usa para calcular la caja, y sale de los totales del P&L para
    que la base sea idéntica a la del flujo indirecto.
    """
    # `pl_api` en diferido: importarlo arriba cierra un ciclo de imports.
    from app.api.pl_api import _pl_component

    # Se acumula por CÓDIGO, no por nombre.
    #
    # Antes la clave era el nombre visible y se ASIGNABA. Dos líneas distintas
    # del P&L se llaman las dos «Laundry» —el departamento ($2,493.77) y el
    # overhead de Laundry Operations ($3,579.44)— así que cada mes la segunda
    # pisaba a la primera y el gasto salía $2,493.77 corto: el GOP del método
    # directo daba $2,349,428 contra los $2,347,219 del P&L.
    #
    # La asignación (y no la suma) se conserva a propósito dentro de cada
    # código: el motor emite la misma línea bajo su código canónico y bajo su
    # alias, y sumar la contaría dos veces. Lo que se arregla es la colisión
    # entre códigos DISTINTOS que comparten nombre.
    por_codigo: dict[str, list[float]] = {}
    nombre_de: dict[str, str] = {}
    es_ingreso: dict[str, bool] = {}
    dept_de: dict[str, str] = {}
    prop = {"rent": _z(), "seguros": _z(), "capex": _z(), "otros": _z(),
            "honorarios": _z()}
    # LOS TOTALES DEL P&L son la base del cálculo de caja; las líneas de arriba
    # son el detalle que se muestra. Antes la caja se armaba sumando las líneas
    # sueltas, y eso arrastraba dos problemas: el motor emite cada línea bajo su
    # código canónico Y bajo su alias (mismo nombre visible), así que al fundir
    # por nombre se contaba dos veces; y la nómina se restaba línea por línea
    # emparejando por NOMBRE, que no siempre existe del otro lado. Con los
    # totales, la base de gasto de este método es EXACTAMENTE la del indirecto:
    # TOTAL_OPEXP + TOTAL_OVERHEAD + TOTAL_NON_OP.
    tot = {k: _z() for k in ("rev", "opex", "overhead", "nonop", "capex", "fb")}
    _TOTALES = {"TOTAL_REVENUES": "rev", "TOTAL_OPEXP": "opex",
                "TOTAL_OVERHEAD": "overhead", "TOTAL_NON_OP": "nonop"}

    # Las lineas llegan canonizadas, asi que esta tabla tambien: `TOTAL_OPEXP`
    # viaja como `TOTAL_OPERATING_EXPENSES`.
    _TOTALES = codigos_canonicos(_TOTALES)

    for m in range(1, 13):
        i = m - 1
        # ⚠️ UNA linea por codigo CANONICO, y por eso este paso existe.
        #
        # El motor emite la misma linea bajo sus dos vocabularios —`OPEXP_ROOMS`
        # y su alias `OPEX_ROOMS`, mismo nombre visible y mismo monto— y mas
        # abajo el detalle se acumula por NOMBRE con `+=`. En los escenarios que
        # traen los dos (los Actuals importados) eso mostraba **cada gasto al
        # doble**: Maintenance en $1,003,500 cuando son $501,750, Rooms en
        # $708,654 cuando son $354,327. Doce departamentos del Actual 2024, y el
        # honorario de administracion por el mismo motivo.
        #
        # El total del tab nunca se movio —sale de los TOTAL_* del P&L— asi que
        # la conciliacion contra el indirecto seguia dando $0.02 con la lista
        # mostrando el doble. Por eso no lo vio ninguna prueba.
        #
        # Se queda el monto de mayor valor absoluto, que es el criterio de
        # `add_pl_aliases`: cuando un vocabulario trae la linea en 0, manda el
        # otro.
        del_mes = una_por_codigo_canonico(
            await recalc.compute_pl_month(session, scenario, m))

        for code, ln in del_mes.items():
            amt = float(ln.amount_usd or 0)
            if code in _TOTALES:
                tot[_TOTALES[code]][i] = amt
                continue
            if "TOTAL" in code:
                continue
            name = ln.line_name or code
            if code == "REV_FB":
                tot["fb"][i] = amt
            # ⚠️ Quién es «gasto» lo decide `_pl_component`, NO una lista de
            # prefijos propia. Acá había una: `OPEX_`/`OPEXP_`/`OH_`/`OVH_`, sin
            # los bloques de **Cost of Sales** (`COS_`, `COH_`). Pero el total
            # de este tab sale de TOTAL_OPEXP + TOTAL_OVERHEAD + TOTAL_NON_OP, y
            # esos totales SÍ los incluyen: el desglose quedaba **$418,982 por
            # debajo de su propio total** —10.6% del costo del año— sin que
            # fallara nada. La caja siempre estuvo bien; lo que no cerraba era
            # la lista que existe para explicarla.
            #
            # Es el MISMO defecto que se corrigió en `pl_api` el 2026-08-14, en
            # la pantalla de al lado. Por eso ahora se llama a aquel
            # clasificador en vez de repetir sus prefijos: dos copias de esta
            # regla ya se desincronizaron una vez.
            #
            # Y arrastraba un segundo efecto peor de leer: la Cafetería aparecía
            # en **−92,861**, un costo negativo. Su comida son los $108,000 de
            # `COH_CAFETERIA`; sin esa fila solo se veía el crédito del reparto
            # a los departamentos que comen. Con las dos, el neto es +15,138.
            if (code.startswith("REV_")
                    or _pl_component(ln, "OPEX") or _pl_component(ln, "OVERHEAD")):
                por_codigo.setdefault(code, _z())[i] = amt
                nombre_de[code] = name
                es_ingreso[code] = code.startswith("REV_")
                # El grupo se mapea SOLO desde la línea de gasto del depto: es
                # la etiqueta con la que se rotula su planilla. Si un `COS_`
                # trajera dept_code, la nómina de F&B pasaría a llamarse «F&B
                # Food Cost».
                if ln.dept_code and not code.startswith(("COS_", "COH_")):
                    dept_de[code] = ln.dept_code
            elif code == "RENT":
                prop["rent"][i] = amt
            elif code in ("PROPERTY_INSURANCE", "PROPERTIES_INSURANCE"):
                prop["seguros"][i] = amt
            elif code == "CAPITAL_EXPENSE":
                prop["capex"][i] = amt
                tot["capex"][i] = amt
            elif code == "OTHER_EXPENSES":
                prop["otros"][i] = amt
            elif code in ("MGMT_FEE", "ROYALTIES",
                          "MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES"):
                # El honorario de administración se RECONSTRUÍA como un % de las
                # ventas mientras el P&L tiene la línea calculada. Si el fee está
                # cargado a mano el porcentaje ni siquiera aplica: el mismo
                # concepto daba $299,867 en una pantalla y $179,920 en la otra.
                #
                # Van los cuatro códigos a propósito: el vocabulario canónico usa
                # MGMT_FEE_3 / MGMT_FEE_5_ROYALTIES y el del motor usa MGMT_FEE /
                # ROYALTIES. Con solo los del motor, la fila salía en cero en los
                # escenarios armados en la app — que son casi todos.
                prop["honorarios"][i] += amt

    # Etiqueta visible, única. Cuando dos códigos comparten nombre se aclara con
    # el origen en vez de fundirlos: «Laundry» el departamento y «Laundry
    # (overhead)» el de la casa son dos cosas y la junta las lee distinto.
    repetido = {n for n in nombre_de.values()
                if sum(1 for x in nombre_de.values() if x == n) > 1}
    def etiqueta(code: str) -> str:
        n = nombre_de[code]
        if n not in repetido:
            return n
        return f"{n} (overhead)" if code.startswith(("OH_", "OVH_")) else n

    revenue_lines: dict[str, list[float]] = {}
    opex_lines: dict[str, list[float]] = {}
    group_label: dict[str, str] = {}   # grupo del depto → etiqueta de su opex
    for code, vals in por_codigo.items():
        destino = revenue_lines if es_ingreso[code] else opex_lines
        lab = etiqueta(code)
        acum = destino.setdefault(lab, _z())
        for i in range(12):
            acum[i] += vals[i]
        if not es_ingreso[code] and code in dept_de:
            group_label[dept_de[code]] = lab

    # ── Nómina por depto — SOLO PARA MOSTRAR ─────────────────────────────────
    # Ya no se resta del OPEX ni se vuelve a pagar aparte. El P&L trae la nómina
    # COMPLETA (los 17 conceptos, con CCSS patronal y aguinaldo) dentro de la
    # línea de cada departamento, y el gasto de caja sale de esos totales.
    #
    # El desglose anterior reconstruía la nómina desde cero —base imponible ×
    # (1 + CCSS) + 1/12 de aguinaldo— y restaba del OPEX solo la base. Eso dejaba
    # la CCSS, el aguinaldo y otros ocho conceptos DENTRO del bucket de
    # proveedores, y encima volvía a pagar el aguinaldo entero en diciembre:
    # ~$148,115 al año contados dos veces. Además la resta emparejaba por nombre
    # visible, así que la nómina de los departamentos cuyo nombre de grupo no
    # coincide con el de su línea del P&L (0205 «Claro Huerta», 280) se sumaba
    # sin restarse de nada.
    payroll_lines: dict[str, list[float]] = {}
    # Los 17 conceptos, agrupados como los lee una planilla: el bruto gravable,
    # las cargas patronales una por una y los beneficios. Sirve para mostrar de
    # dónde sale el costo y cuánto le queda al empleado en la mano.
    conceptos = {k: _z() for k in
                 ("bruto", "ccss_patronal", "aguinaldo", "ins", "vacaciones",
                  "cesantia", "incapacidades", "cafeteria", "transporte",
                  "vivienda", "otros")}
    _CONCEPTO_COL = {
        "ccss_patronal": "c6020_ccss", "aguinaldo": "c6021_aguinaldo",
        "ins": "c6022_occ_hazard", "vacaciones": "c6023_vacation_prov",
        "cesantia": "c6026_severance", "incapacidades": "c6004_disabilities",
        "cafeteria": "c6025_cafeteria", "transporte": "c6029_transport",
        "vivienda": "c6028_housing", "otros": "c6030_other",
    }
    entries = (await session.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario.id))).scalars().all()
    for e in entries:
        if e.dept_code in ALLOC_EXCL_PAYROLL or not (1 <= (e.month or 0) <= 12):
            continue    # Employee Dining / Laundry interna: allocation, fuera
        i = e.month - 1
        g = pl_engine.group_for_dept(e.dept_code)
        label = group_label.get(g) or pl_engine.GROUP_NAMES.get(g, g)
        payroll_lines.setdefault(label, _z())[i] += float(total_entry(e))
        conceptos["bruto"][i] += float(calc_base(e))
        for clave, col in _CONCEPTO_COL.items():
            conceptos[clave][i] += float(getattr(e, col, 0) or 0)
    tot["conceptos"] = conceptos

    return revenue_lines, opex_lines, payroll_lines, prop, tot


def _movimientos_del_indirecto(payload: dict) -> dict:
    """Traduce las filas del Cash Flow Budget al vocabulario del método directo.

    El indirecto muestra los gastos con signo negativo (son restas al resultado);
    acá se pasan a magnitud positiva porque el directo los presenta como pagos.
    """
    filas = {r.get("key"): r for r in (payload.get("rows") or []) if r.get("key")}

    def vals(clave):
        r = filas.get(clave)
        v = [float(x or 0) for x in ((r.get("values") if r else None) or [])]
        return (v + [0.0] * 12)[:12]

    gasto = [-(vals("OPEX")[i] + vals("OVERHEAD")[i] + vals("NONALLOC")[i])
             for i in range(12)]
    otros = [0.0] * 12
    for r in (payload.get("rows") or []):
        if r.get("section") == "Other Cash Movements":
            for i, x in enumerate((r.get("values") or [])[:12]):
                otros[i] += float(x or 0)
    mov = {k: vals(k) for k in ("WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP",
                                "WC_TAX", "WC_PROV", "WC_RENTTAX", "WC_SERVICE")}
    renta_row = vals("OTH_RENTA")
    otros = [otros[i] - renta_row[i] for i in range(12)]   # sale por su propia línea
    mov.update({"rev": vals("REVENUE"), "gasto": gasto,
                "capex": vals("SUBTOTAL_CAPEX"), "otros": otros,
                "renta": renta_row})
    return mov


@router.get("/scenarios/{scenario_id}/cashflow-directo/")
async def get_cashflow_directo(scenario_id: str, idioma: str = Idioma):
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        cfg = await session.get(CashFlowDirectoConfig, scenario_id)
        manual = (cfg.manual if cfg else {}) or {}
        revenue_lines, opex_lines, payroll_lines, prop, tot = await _lines_from_pl(session, scenario)
        cfp = (await session.execute(select(CashFlowParams).where(
            CashFlowParams.scenario_id == scenario_id))).scalar_one_or_none()
        opening = float(cfp.opening_cash) if cfp else 0.0

        # ── Criterios: UNA sola fuente para los dos métodos ──────────────────
        # Antes esta pantalla heredaba a mano cinco parámetros del indirecto,
        # bajo la condición `if "timing_matrix" not in params`. Eso tenía dos
        # agujeros: seis criterios de la hoja (retención de anticipos, servicio
        # F&B y su rezago, planilla tercerizada, aguinaldo y su mes de pago)
        # nunca cruzaban, y bastaba con apretar «Guardar» una vez en esta
        # pantalla —que persiste la matriz heredada— para que la condición no se
        # cumpliera nunca más y los criterios quedaran congelados en silencio.
        criterios, avisos = await cargar_criterios(session, scenario)
        params = crit.vista_directo(criterios)

        # El interruptor «Modelo de timing ACTIVO» ahora manda en LOS DOS. Antes
        # esta pantalla ni lo miraba: con el modelo apagado el indirecto volvía a
        # las partidas manuales y el directo seguía cobrando con la matriz, así
        # que los dos métodos quedaban en universos distintos sin decirlo.
        tot["payroll"] = await payroll_series(session, scenario)
        # La retención de renta del tab de Planilla es la MISMA que calcula el tab
        # de Retenciones, tramo por tramo y persona por persona. Antes salía de un
        # porcentaje plano que estaba en 0%, así que la planilla neta mostraba al
        # empleado llevándose plata que en realidad se le retiene y va a Hacienda.
        _ret = await _calcular_retenciones(session, scenario, criterios, idioma)
        tot.setdefault("conceptos", {})["renta"] = _ret["total_mes"]
        ventana: dict = {}
        avisos_timing: list[dict] = []
        if criterios.get("enabled"):
            tm = effective_timing_matrix(criterios)
            # La ventana de años vecinos es la MISMA que usa el indirecto: el año
            # siguiente aporta los depósitos que entran a fin de año, y el
            # anterior el saldo a crédito que se cobra en enero y —esto faltaba—
            # la cola de la factura de proveedores de diciembre.
            ventana, integrado = await ventana_wc(session, scenario)
            params = {**params, "timing_matrix": tm,
                      "timing_matrix_prev": criterios.get("timing_matrix_prev"),
                      "timing_matrix_next": criterios.get("timing_matrix_next")}
            # Cada fila de la matriz reparte el 100% de la venta de ese mes entre
            # los meses en que se cobra. Si no suma 1, se está inventando o
            # perdiendo caja. NO se normaliza en silencio: el número malo está en
            # los criterios y hay que arreglarlo ahí, no taparlo acá.
            avisos_timing = crit.avisos_matriz(tm)
        else:
            avisos.append({
                "tipo": "modelo_apagado",
                "detalle": t(idioma, "cashflow.timing_desactivado")})

        # Los movimientos FINALES del flujo indirecto. No se recalculan acá: se
        # leen de la otra pantalla tal como quedan, vengan del modelo de timing,
        # de un driver, de una celda pisada a mano o del Balance Sheet real de un
        # mes cerrado. Es lo que hace que los dos métodos coincidan en todos los
        # escenarios y no solo en un presupuesto limpio.
        from app.api.pl_api import _cashflow_budget_payload
        indirecto = await _cashflow_budget_payload(session, scenario)

    movimientos = _movimientos_del_indirecto(indirecto)
    result = compute_cashflow_directo(
        revenue_lines, opex_lines, payroll_lines, prop, params, opening, manual,
        totales=tot, ventana=ventana, movimientos=movimientos)
    return {**result, "defaults": DIRECT_DEFAULTS, "params": params, "manual": manual,
            "avisos_timing": avisos_timing, "avisos": avisos,
            "criterios_enabled": bool(criterios.get("enabled")),
            "renta": indirecto.get("renta")}


class DirectoConfigPayload(BaseModel):
    params: dict = {}
    manual: dict = {}


@router.put("/scenarios/{scenario_id}/cashflow-directo/")
async def save_cashflow_directo(scenario_id: str, payload: DirectoConfigPayload):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        await _get_scenario_or_404(session, scenario_id)
        cfg = await session.get(CashFlowDirectoConfig, scenario_id)
        if not cfg:
            cfg = CashFlowDirectoConfig(scenario_id=scenario_id)
            session.add(cfg)
        # Los DERIVADOS no se guardan. La pantalla recibe la matriz de timing, las
        # matrices vecinas y el revenue de los años vecinos ya resueltos, y los
        # mandaba de vuelta enteros al guardar. Desde ese momento el escenario
        # quedaba congelado: la matriz guardada le ganaba a la hoja de Criterios,
        # el revenue de los vecinos quedaba clavado en la foto de ese día, y la
        # validación de que cada fila sume 100% dejaba de correr.
        # Se conserva lo que esta pantalla NO administra —los tramos del impuesto
        # al salario se editan en su propio tab— para que guardar acá no los borre.
        previo = {k: v for k, v in (cfg.params or {}).items()
                  if k in ("tramos_renta", "renta_deduce_ccss", "renta_tasa",
                           "renta_pago_manual", "renta_mes_pago")}
        limpio = {**previo, **{k: v for k, v in (payload.params or {}).items()
                               if k not in crit.DERIVADOS}}
        # Un criterio COMPARTIDO guardado acá solo pisa a la hoja de Criterios si
        # se marca como override explícito. Sin la marca es el eco del default que
        # la pantalla precarga, y ese eco fue lo que desconectó las dos pantallas.
        explicitos = set(limpio.get(crit.MARCA_OVERRIDE) or [])
        limpio[crit.MARCA_OVERRIDE] = sorted(explicitos & crit.COMPARTIDOS)
        cfg.params = limpio
        cfg.manual = payload.manual or {}
        await session.commit()
    return {"ok": True}


async def _calcular_retenciones(session, scenario, criterios: dict,
                                idioma: str = DEFAULT_LOCALE) -> dict:
    """Retención de renta al salario, persona por persona y mes por mes.

    No se puede sacar con un porcentaje plano sobre la masa salarial: el impuesto
    es progresivo y mensual, así que depende de CÓMO esté repartida la planilla.
    Muchos salarios bajos quedan enteros exentos mientras unos pocos sueldos
    altos concentran toda la retención — en Budget 2027, 5 de 122 empleados.

    Lo consumen el tab de Retenciones y el de Planilla: tienen que decir lo mismo.
    """
    scenario_id = scenario.id
    tramos = renta.normalizar_tramos(criterios.get("tramos_renta"))
    obrera = float(criterios.get("ccss_obrera_rate") or 0)
    deducir = bool(criterios.get("renta_deduce_ccss",
                                 renta.DEDUCIR_CCSS_POR_DEFECTO))

    # Los tramos están en colones y la planilla en dólares, así que hace falta el
    # tipo de cambio. Un escenario sin tipos cargados NO puede tumbar el flujo
    # entero: se cae al TC por defecto del hotel y, si tampoco hay, la retención
    # queda en cero CON aviso — un cero explicado, no un 500.
    tasas = (await session.execute(select(ExchangeRate).where(
        ExchangeRate.scenario_id == scenario_id))).scalars().all()
    avisos_tc: list[str] = []
    try:
        tc_mes = [float(get_tc_for_month(tasas, m)) for m in range(1, 13)]
    except ValueError:
        hotel = await session.get(Hotel, scenario.hotel_id)
        respaldo = float(getattr(hotel, "tc_usd_default", 0) or 0)
        tc_mes = [respaldo] * 12
        avisos_tc.append(
            t(idioma, "cashflow.tc_del_hotel", tc=f"₡{respaldo:,.2f}") if respaldo else
            t(idioma, "cashflow.sin_tc_ni_del_hotel"))

    posiciones = {p.id: p for p in (await session.execute(select(PayrollPosition).where(
        PayrollPosition.scenario_id == scenario_id))).scalars().all()}
    entries = (await session.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario_id))).scalars().all()

    por_persona: dict[str, dict] = {}
    total_mes = [0.0] * 12
    base_mes = [0.0] * 12
    for e in entries:
        m = e.month or 0
        if not (1 <= m <= 12) or e.dept_code in ALLOC_EXCL_PAYROLL:
            continue
        pos = posiciones.get(e.position_id)
        base_usd = float(calc_base(e))
        det = renta.retencion_persona(base_usd, tc_mes[m - 1], tramos, obrera, deducir)
        clave = e.position_id
        fila = por_persona.setdefault(clave, {
            "position_id": clave,
            "empleado": (pos.employee_name if pos else "") or "VACANTE",
            "puesto": pos.position_name if pos else "",
            "dept_code": e.dept_code,
            "dept_name": pos.dept_name if pos else "",
            "base_usd": [0.0] * 12,
            "impuesto_usd": [0.0] * 12,
            "tramo": [0] * 12,
        })
        fila["base_usd"][m - 1] += det["base_usd"]
        fila["impuesto_usd"][m - 1] += det["impuesto_usd"]
        fila["tramo"][m - 1] = det["tramo"]
        total_mes[m - 1] += det["impuesto_usd"]
        base_mes[m - 1] += det["base_usd"]

    filas = sorted(por_persona.values(), key=lambda f: -sum(f["impuesto_usd"]))
    for f in filas:
        f["base_anual"] = round(sum(f["base_usd"]), 2)
        f["impuesto_anual"] = round(sum(f["impuesto_usd"]), 2)
        f["afecto"] = f["impuesto_anual"] > 0.005
        f["base_usd"] = [round(x, 2) for x in f["base_usd"]]
        f["impuesto_usd"] = [round(x, 2) for x in f["impuesto_usd"]]

    afectos = sum(1 for f in filas if f["afecto"])
    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "tramos": renta.resumen_tramos(tramos),
        "tc_mes": [round(x, 4) for x in tc_mes],
        "deduce_ccss": deducir,
        "ccss_obrera_rate": obrera,
        "empleados": filas,
        "total_mes": [round(x, 2) for x in total_mes],
        "base_mes": [round(x, 2) for x in base_mes],
        "total_anual": round(sum(total_mes), 2),
        "base_anual": round(sum(base_mes), 2),
        "empleados_afectos": afectos,
        "empleados_total": len(filas),
        "avisos": avisos_tc,
    }


@router.get("/scenarios/{scenario_id}/retenciones/")
async def get_retenciones(scenario_id: str, idioma: str = Idioma):
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        criterios, _ = await cargar_criterios(session, scenario)
        return await _calcular_retenciones(session, scenario, criterios, idioma)


class TramosPayload(BaseModel):
    tramos: list[dict] = []
    deduce_ccss: bool = True
    renta_tasa: float | None = None
    renta_pago_manual: float | None = None
    renta_mes_pago: int | None = None


@router.put("/scenarios/{scenario_id}/retenciones/tramos/")
async def save_tramos(scenario_id: str, payload: TramosPayload):
    """Guarda la tabla de tramos del escenario. Los tramos los fija Hacienda y
    cambian por año, así que viven con el escenario y no en el código."""
    async with get_session() as session:
        await candado(session, scenario_id)
        await _get_scenario_or_404(session, scenario_id)
        cfg = await session.get(CashFlowDirectoConfig, scenario_id)
        if not cfg:
            cfg = CashFlowDirectoConfig(scenario_id=scenario_id)
            session.add(cfg)
        nuevo = {**(cfg.params or {}),
                 "tramos_renta": renta.normalizar_tramos(payload.tramos),
                 "renta_deduce_ccss": bool(payload.deduce_ccss)}
        if payload.renta_tasa is not None:
            nuevo["renta_tasa"] = float(payload.renta_tasa)
        if payload.renta_pago_manual is not None:
            nuevo["renta_pago_manual"] = max(0.0, float(payload.renta_pago_manual))
        if payload.renta_mes_pago is not None:
            nuevo["renta_mes_pago"] = min(12, max(1, int(payload.renta_mes_pago)))
        cfg.params = nuevo
        await session.commit()
    return {"ok": True}
