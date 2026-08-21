"use client";
/**
 * A dónde se puede saltar desde cada pantalla, y por qué.
 *
 * **El pedido (owner, 2026-08-19):** moverse entre pantallas «en forma
 * lógica», sin volver al menú.
 *
 * **Lógica quiere decir: el camino del dato.** No «todas con todas» — con 94
 * pantallas eso es un menú peor que el que ya hay. Los saltos que valen son los
 * que responden una pregunta que uno ya tiene en la cabeza mientras mira la
 * pantalla:
 *
 *   «¿de dónde sale este número?»   P&L → el checkbook que lo produce
 *   «¿y cuándo entra la plata?»     P&L → Cash Flow
 *   «¿por qué cobra así?»           Cash Flow → sus Criterios
 *   «¿esto en qué termina?»         Checkbook → P&L
 *
 * **El rótulo sale de `nav.items`**, el mismo que usa el menú. Es a propósito:
 * un segundo juego de nombres para las mismas pantallas se desincroniza el día
 * que se renombra una, y entonces el menú y el salto llaman distinto al mismo
 * lugar.
 *
 * **Agregar un salto es UNA línea acá.** No se toca la pantalla.
 */

export interface Destino {
  /** La ruta. */
  href: string;
  /** Clave en `nav.items` — de ahí sale el nombre, ya traducido. */
  item: string;
  /** Clave en `ira.porque` — la pregunta que este salto responde. */
  porque: string;
  /**
   * Qué coordenadas viajan. Por omisión, escenario y mes.
   *
   * ⚠️ Mandar de más no es gratis: el parámetro que el destino ignora igual
   * queda en la barra de direcciones, y alguien lo copia esperando que haga
   * algo. Un `mes` hacia una pantalla anual es exactamente eso.
   */
  lleva?: ReadonlyArray<"esc" | "mes" | "dep" | "cta">;
}

const SOLO_ESC = ["esc"] as const;

/**
 * El grafo. Clave = ruta de origen.
 *
 * Arranca por el circuito central —P&L ↔ Cash Flow ↔ Checkbook— que es el que
 * más se recorre y el que ejercita el contexto en el caso más exigente
 * (escenario + mes + departamento). Planning entra por sus checkbooks, que son
 * la punta donde se carga el dato.
 */
export const SALTOS: Record<string, Destino[]> = {
  // ── P&L ────────────────────────────────────────────────────────────────
  "/pl/full": [
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "cuandoEntra", lleva: SOLO_ESC },
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "deDondeIngreso", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "deDondeGasto" },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "deDondePlanilla" },
    { href: "/pl/simplified", item: "plSimplified", porque: "mismoResumido", lleva: SOLO_ESC },
  ],
  "/pl/simplified": [
    { href: "/pl/full", item: "plFullYear", porque: "mismoDetallado", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "cuandoEntra", lleva: SOLO_ESC },
  ],

  // ── Cash Flow ──────────────────────────────────────────────────────────
  "/reports/cashflow-budget": [
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "otraVista" },
    { href: "/reports/cashflow-criteria", item: "cashflowCriteria", porque: "porQueCobraAsi", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "elDevengado", lleva: SOLO_ESC },
  ],
  "/reports/cashflow-directo": [
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "otraVista" },
    { href: "/reports/cashflow-criteria", item: "cashflowCriteria", porque: "porQueCobraAsi", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "elDevengado", lleva: SOLO_ESC },
  ],
  "/reports/cashflow-criteria": [
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "verEfecto", lleva: SOLO_ESC },
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "verEfecto", lleva: SOLO_ESC },
  ],

  // ── Planning: los checkbooks, donde se carga el dato ────────────────────
  "/revenue/checkbook": [
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "elTotal", lleva: SOLO_ESC },
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "cuandoSeCobra", lleva: SOLO_ESC },
  ],
  "/opex/checkbook": [
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "cuandoSePaga", lleva: SOLO_ESC },
  ],
  "/payroll/checkbook": [
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
    { href: "/payroll/fte", item: "fteReport", porque: "cuantaGente" },
    { href: "/payroll/params", item: "payrollParams", porque: "conQueTasas", lleva: SOLO_ESC },
  ],
  "/costs/checkbook": [
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "cuandoSePaga", lleva: SOLO_ESC },
  ],
  "/nonop/checkbook": [
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "cuandoSePaga", lleva: SOLO_ESC },
    { href: "/nonop/management-fees", item: "managementFees", porque: "lasOtrasBelowGop", lleva: SOLO_ESC },
  ],

  // ═══ PLANNING · la cadena de Revenue ═══════════════════════════════════
  //
  // Esto NO es un menú alternativo: es una cadena de dependencia real, donde
  // cada pantalla produce el insumo de la siguiente.
  //
  //   inventory ─┬─> availability ──> room-nights
  //              └─> master ──> occupancy ──> pax ──> package-components
  //                                │                        │
  //   rack-rates ──> net-rate <── channels                  v
  //        └──────────> total-revenue ──> revenue/checkbook ──> P&L
  //
  // ⚠️ Corrección a un supuesto que traíamos mal: `/revenue/room-nights` **no**
  // consume ocupación — muestra noches DISPONIBLES (`units × días`). Quien
  // consume `/revenue/occupancy` es pax, spa, total-revenue y el checkbook.
  "/revenue/master": [
    { href: "/revenue/occupancy", item: "occupancy", porque: "sobreEstasUnidades", lleva: SOLO_ESC },
    { href: "/revenue/pax", item: "pax", porque: "mismoDatoDosPuertas", lleva: SOLO_ESC },
    { href: "/revenue/inventory", item: "inventory", porque: "mismoDatoDosPuertas", lleva: SOLO_ESC },
    { href: "/revenue/room-nights", item: "roomNights", porque: "mismoDatoDosPuertas", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "verEfecto", lleva: SOLO_ESC },
  ],
  "/revenue/inventory": [
    { href: "/revenue/master", item: "yearMasterData", porque: "mismoDatoDosPuertas", lleva: SOLO_ESC },
    { href: "/revenue/rack-rates", item: "rackRates", porque: "tipoNuevoSinTarifa", lleva: SOLO_ESC },
    { href: "/revenue/occupancy", item: "occupancy", porque: "tipoNuevoSinOcupacion", lleva: SOLO_ESC },
    { href: "/revenue/availability", item: "availability", porque: "elMultiplicador", lleva: SOLO_ESC },
  ],
  "/revenue/availability": [
    { href: "/revenue/room-nights", item: "roomNights", porque: "elMismoAbiertoPorTipo", lleva: SOLO_ESC },
    { href: "/revenue/inventory", item: "inventory", porque: "elMultiplicador", lleva: SOLO_ESC },
    { href: "/revenue/occupancy", item: "occupancy", porque: "esElDenominador", lleva: SOLO_ESC },
  ],
  "/revenue/room-nights": [
    { href: "/revenue/availability", item: "availability", porque: "elTotalAgregado", lleva: SOLO_ESC },
    { href: "/revenue/occupancy", item: "occupancy", porque: "cerrarMesPoneCero", lleva: SOLO_ESC },
    { href: "/revenue/master", item: "yearMasterData", porque: "mismoDatoDosPuertas", lleva: SOLO_ESC },
  ],
  "/revenue/occupancy": [
    { href: "/revenue/pax", item: "pax", porque: "generaLasNoches", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "verEfecto", lleva: SOLO_ESC },
    { href: "/revenue/spa", item: "spaCapture", porque: "dimensionaElSpa", lleva: SOLO_ESC },
    { href: "/revenue/availability", item: "availability", porque: "esElDenominador", lleva: SOLO_ESC },
  ],
  "/revenue/pax": [
    { href: "/revenue/occupancy", item: "occupancy", porque: "generaLasNoches", lleva: SOLO_ESC },
    { href: "/revenue/package-components", item: "packageComponents", porque: "seCosteaPorPax", lleva: SOLO_ESC },
    { href: "/costs/checkbook", item: "costOfSales", porque: "escalaConElPax", lleva: SOLO_ESC },
    { href: "/revenue/master", item: "yearMasterData", porque: "mismoDatoDosPuertas", lleva: SOLO_ESC },
  ],
  "/revenue/rack-rates": [
    { href: "/revenue/net-rate", item: "netRate", porque: "rackPorFactor", lleva: SOLO_ESC },
    { href: "/revenue/channels", item: "channels", porque: "elFactorQueCastiga", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "verEfecto", lleva: SOLO_ESC },
    { href: "/revenue/inventory", item: "inventory", porque: "deDondeSalenLasFilas", lleva: SOLO_ESC },
  ],
  "/revenue/channels": [
    { href: "/revenue/net-rate", item: "netRate", porque: "rackPorFactor", lleva: SOLO_ESC },
    { href: "/revenue/rack-rates", item: "rackRates", porque: "elRackSobreElQueAplica", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "verEfecto", lleva: SOLO_ESC },
    { href: "/marketing-insight/channel-mix", item: "channelMix", porque: "elPlanContraElReal", lleva: SOLO_ESC },
  ],
  "/revenue/net-rate": [
    { href: "/revenue/rack-rates", item: "rackRates", porque: "unFactorDelCalculo", lleva: SOLO_ESC },
    { href: "/revenue/channels", item: "channels", porque: "unFactorDelCalculo", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "netoPorNoches", lleva: SOLO_ESC },
  ],
  "/revenue/package-components": [
    { href: "/revenue/channels", item: "channels", porque: "cargaLaMismaConfig", lleva: SOLO_ESC },
    { href: "/costs/checkbook", item: "costOfSales", porque: "elCostoDelComponente", lleva: SOLO_ESC },
    { href: "/revenue/pax", item: "pax", porque: "elVolumenQueAplica", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "elIngresoNoRooms", lleva: SOLO_ESC },
  ],
  "/revenue/spa": [
    { href: "/revenue/occupancy", item: "occupancy", porque: "dimensionaElSpa", lleva: SOLO_ESC },
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "dondeQuedaAsentado", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "dondeSumaAlTotal", lleva: SOLO_ESC },
  ],
  "/revenue/club": [
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "dondeQuedaAsentado", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "dondeSumaAlTotal", lleva: SOLO_ESC },
  ],
  "/revenue/total-revenue": [
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "destinoDelPush", lleva: SOLO_ESC },
    { href: "/revenue/occupancy", item: "occupancy", porque: "unFactorDelCalculo", lleva: SOLO_ESC },
    { href: "/revenue/rack-rates", item: "rackRates", porque: "unFactorDelCalculo", lleva: SOLO_ESC },
    { href: "/revenue/channels", item: "channels", porque: "unFactorDelCalculo", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
  ],

  // ═══ PLANNING · planilla y repartos ════════════════════════════════════
  //
  // ⚠️ `/payroll/fte` es el caso que el owner pidió por nombre, parado en esa
  // pantalla: «desde acá me gustaría ir al checkbook de salarios y desde
  // salarios venir al FTE».
  //
  // Verificado en el código: FTE **no tiene endpoint propio**. Reconstruye el
  // detalle llamando dept por dept a LOS MISMOS endpoints que pinta el
  // checkbook. Son la misma tabla con otro grano, así que la dependencia es
  // real y va en los dos sentidos. La ida ya existía; la vuelta es esta, y es
  // la valiosa: se ve un FTE raro y hay que ir a editar la posición, que solo
  // se puede allá.
  "/payroll/fte": [
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeEdita", lleva: SOLO_ESC },
    { href: "/payroll/params", item: "payrollParams", porque: "conQueTasas", lleva: SOLO_ESC },
    { href: "/allocations/config", item: "allocationConfig", porque: "esLaBaseDelReparto", lleva: SOLO_ESC },
    { href: "/allocations/salary", item: "salaryAllocation", porque: "reasignaEstasPosiciones", lleva: SOLO_ESC },
  ],
  "/payroll/params": [
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "elCostoQueCalculan", lleva: SOLO_ESC },
    { href: "/payroll/fte", item: "fteReport", porque: "laGenteQueValorizan", lleva: SOLO_ESC },
    { href: "/allocations/salary", item: "salaryAllocation", porque: "usaLasMismasTasas", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
  ],
  "/allocations/config": [
    { href: "/payroll/fte", item: "fteReport", porque: "esLaBaseDelReparto", lleva: SOLO_ESC },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeCorrigeLaBase", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "elCostoAReparto", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "verEfecto", lleva: SOLO_ESC },
  ],
  "/allocations/salary": [
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "elRosterQueReasigna", lleva: SOLO_ESC },
    { href: "/payroll/params", item: "payrollParams", porque: "usaLasMismasTasas", lleva: SOLO_ESC },
    { href: "/payroll/fte", item: "fteReport", porque: "laGenteQueSeMueve", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "verEfecto", lleva: SOLO_ESC },
  ],
  "/nonop/management-fees": [
    { href: "/pl/full", item: "plFullYear", porque: "leeYEscribeAhi", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "laBaseDelPorcentaje", lleva: SOLO_ESC },
    { href: "/nonop/checkbook", item: "ownerExpenses", porque: "lasOtrasBelowGop", lleva: SOLO_ESC },
  ],

  // ═══ PLANNING · gobierno del presupuesto ═══════════════════════════════
  //
  // ⚠️ `/board` y `/notes` son las ÚNICAS del sistema que tienen el código de
  // departamento como dato de primera clase: cada fila **es** un
  // `{sección, ref}` donde `ref` es el mismo `dept_code` que selecciona el
  // checkbook. Por eso llevan `dep` — el salto no abre «el checkbook», abre
  // justo el departamento que hay que completar. `/notes` guarda además el
  // mes, así que lleva los tres.
  "/board": [
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "loQueHayQueCompletar" },
    { href: "/opex/checkbook", item: "opexByDept", porque: "loQueHayQueCompletar" },
    { href: "/costs/checkbook", item: "costOfSales", porque: "loQueHayQueCompletar" },
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "loQueHayQueCompletar", lleva: SOLO_ESC },
    { href: "/notes", item: "notes", porque: "loComentadoDeEstaSeccion" },
  ],
  "/notes": [
    { href: "/board", item: "teamBoard", porque: "dondeSeAsignaYAprueba", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "lasCoordenadasDeLaNota" },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "lasCoordenadasDeLaNota" },
    { href: "/costs/checkbook", item: "costOfSales", porque: "lasCoordenadasDeLaNota" },
  ],
  // ⚠️ `/command` COMPARA sin que se note: sus tres referencias viven en
  // `useState` plano y no en `useEscenarioDe`, así que contar selectores no lo
  // detecta. Atarle el principal es seguro HOY —los comparativos no se tocan—
  // pero si alguien migra esas tres a `useEscenarioDe`, se rompe en silencio.
  "/command": [
    { href: "/board", item: "teamBoard", porque: "elDetalleDelAvance", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "deDondeSalenLosKpi", lleva: SOLO_ESC },
    { href: "/planning/big-picture", item: "bigPicture", porque: "mismaComparacionEditable", lleva: [] },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "losKpiDeRooms", lleva: SOLO_ESC },
  ],
  // ⚠️ Big Picture compara TRES escenarios y además ESCRIBE sobre un cuarto.
  // No emite `esc` hacia ningún lado (`lleva: []`): un solo parámetro pondría
  // las tres columnas en el mismo escenario y el crecimiento saldría 0%.
  "/planning/big-picture": [
    { href: "/pl/full", item: "plFullYear", porque: "loQueElAplicarEscribe", lleva: [] },
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "dondeAterrizaRevenue", lleva: [] },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeAterrizaPlanilla", lleva: [] },
    { href: "/command", item: "command", porque: "mismasReferenciasEnLectura", lleva: [] },
  ],
  "/admin/control": [
    { href: "/pl/full", item: "plFullYear", porque: "elNumeroQueLaTrazaExplica", lleva: SOLO_ESC },
    { href: "/admin/mapping", item: "accountMapping", porque: "arreglarFallbackYDrop", lleva: [] },
    { href: "/opex/checkbook", item: "opexByDept", porque: "elOrigenEditable" },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "elOrigenEditable" },
  ],

  // ═══ REPORTES · de vuelta al dato que los produce ══════════════════════
  //
  // Estos casi todos CONSUMEN. El salto que vale es el inverso al de
  // Planning: no «¿en qué termina esto?» sino «¿de dónde salió este número?».
  //
  // ⚠️ Siete de estas pantallas COMPARAN dos o más escenarios. El `?esc=` se
  // ata siempre a la columna de **budget** —la que se planifica y de donde
  // vienen los saltos— y nunca a más de una: alimentarlas todas dejaría la
  // variación en CERO, que se lee como «no cambió nada» y no como un error.
  "/reports/expenses": [
    // El mejor salto del sistema: el selector de tipo de esta pantalla
    // (OPEX / Costos / Ingresos / Below-GOP) mapea UNO A UNO con los cuatro
    // checkbooks. No es una aproximación, es la misma partición.
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCargaEsteGasto" },
    { href: "/costs/checkbook", item: "costOfSales", porque: "dondeSeCargaEsteGasto" },
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "dondeSeCargaEsteIngreso", lleva: SOLO_ESC },
    { href: "/nonop/checkbook", item: "ownerExpenses", porque: "dondeSeCargaBelowGop", lleva: SOLO_ESC },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "enQueLineaCae" },
  ],
  "/reports/pl-by-dept": [
    { href: "/reports/payroll-dept", item: "payrollDeptReport", porque: "laPlanillaDeEsteDepto" },
    { href: "/reports/expenses", item: "expenses", porque: "elGastoAbiertoPorCuenta" },
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCargaEsteGasto" },
    { href: "/reports/pl-by-dept-compare", item: "plByDeptCompare", porque: "contraOtrosEscenarios" },
    { href: "/pl/full", item: "plFullYear", porque: "elConsolidado", lleva: SOLO_ESC },
  ],
  "/reports/pl-by-dept-compare": [
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "unSoloEscenario" },
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCorrigeLaDesviacion" },
    { href: "/reports/payroll-dept", item: "payrollDeptReport", porque: "siLaVariacionEsDePlanilla" },
  ],
  "/reports/pl-full-detail": [
    { href: "/reports/expenses", item: "expenses", porque: "elMismoDetallePorCuenta", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCargaEsteGasto", lleva: SOLO_ESC },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeCargaEstaPlanilla", lleva: SOLO_ESC },
    { href: "/master-data/setup-cuenta", item: "setupCuenta", porque: "aQueLineaVaEstaCuenta", lleva: [] },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "elMismoCorteporDepto", lleva: SOLO_ESC },
  ],
  "/reports/pl-ytd": [
    { href: "/reports/summary", item: "execSummary", porque: "elMismoResumidoUnaPagina", lleva: SOLO_ESC },
    { href: "/month-end/pl", item: "monthEndPL", porque: "elDesgloseQueExplicaLaVariacion", lleva: SOLO_ESC },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "elMismoMesPorDepto", lleva: SOLO_ESC },
    { href: "/admin/import-actuals", item: "importActuals", porque: "siElMesNoCuadra", lleva: [] },
  ],
  "/reports/pl-full": [
    { href: "/pl/full", item: "plFullYear", porque: "mismoDetallado", lleva: SOLO_ESC },
    { href: "/reports/pl-ytd", item: "plYtd", porque: "elMismoCortadoAlMes", lleva: SOLO_ESC },
    { href: "/reports/pl-by-dept-compare", item: "plByDeptCompare", porque: "laMismaComparacionPorDepto", lleva: SOLO_ESC },
    { href: "/scenarios", item: "scenarios", porque: "dondeSeCreanLasColumnas", lleva: [] },
  ],
  "/reports/summary": [
    // ⚠️ Sin `dep`: acá el «departamento» son familias del P&L (FAM_ROOMS,
    // FAM_FB), no códigos. Mandarle un `0110` lo rompe en silencio.
    { href: "/reports/pl-ytd", item: "plYtd", porque: "elDetalleCompleto", lleva: SOLO_ESC },
    { href: "/reports/revenue-mix", item: "revenueMix", porque: "lasMismasFamiliasAbiertas", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "cuandoEntra", lleva: SOLO_ESC },
  ],
  "/reports/ytd": [
    { href: "/reports/pl-ytd", item: "plYtd", porque: "elDetalleCompleto", lleva: SOLO_ESC },
    { href: "/reports/revenue-by-room", item: "revenueByRoom", porque: "losMismosDriversDeHabitacion", lleva: SOLO_ESC },
    { href: "/reports/summary", item: "execSummary", porque: "elMismoResumidoUnaPagina", lleva: SOLO_ESC },
  ],
  "/reports/revenue-mix": [
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "dondeSeCargaEsteIngreso", lleva: SOLO_ESC },
    { href: "/reports/revenue-by-room", item: "revenueByRoom", porque: "abreLaLineaMasGrande", lleva: SOLO_ESC },
    { href: "/reports/expenses", item: "expenses", porque: "elMismoIngresoPorCuenta", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "elTotalContraElQueSuma", lleva: SOLO_ESC },
  ],
  "/reports/revenue-by-room": [
    { href: "/revenue/occupancy", item: "occupancy", porque: "produceLasNochesOcupadas", lleva: SOLO_ESC },
    { href: "/revenue/rack-rates", item: "rackRates", porque: "deDondeSaleElAdr", lleva: SOLO_ESC },
    { href: "/revenue/inventory", item: "inventory", porque: "lasUnidadesPorTipo", lleva: SOLO_ESC },
    { href: "/reports/rooms-sets", item: "roomsSets", porque: "losMismosTiposAgrupados", lleva: SOLO_ESC },
  ],
  "/reports/rooms-sets": [
    { href: "/master-data/room-sets", item: "roomSets", porque: "laDefinicionDeEstosSets", lleva: [] },
    { href: "/reports/revenue-by-room", item: "revenueByRoom", porque: "elMismoSinAgrupar", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "elCostoDeEstosDeptos" },
  ],
  "/reports/payroll-dept": [
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeEdita" },
    { href: "/reports/payroll-by-position", item: "payrollPositionReport", porque: "elMismoTotalPorPosicion" },
    { href: "/payroll/params", item: "payrollParams", porque: "conQueTasas", lleva: SOLO_ESC },
    { href: "/payroll/fte", item: "fteReport", porque: "laGenteDetrasDelMonto", lleva: SOLO_ESC },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "enQueLineaCae" },
  ],
  "/reports/payroll-by-position": [
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeEdita" },
    { href: "/reports/payroll-dept", item: "payrollDeptReport", porque: "elRollupDelMismoDato" },
    { href: "/payroll/params", item: "payrollParams", porque: "conQueTasas", lleva: SOLO_ESC },
    { href: "/operation-insight/headcounts", item: "headcounts", porque: "elMismoDeptoComoDotacion" },
  ],
  "/reports/owner": [
    { href: "/reports/owners-q", item: "ownersQ", porque: "elOtroReporteAlPropietario", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "elPlCompletoDetras", lleva: SOLO_ESC },
    { href: "/revenue/rack-rates", item: "rackRates", porque: "deDondeSaleElAdr", lleva: SOLO_ESC },
    { href: "/notes", item: "notes", porque: "deDondeSalenSusComentarios", lleva: SOLO_ESC },
  ],
  "/reports/owners-q": [
    { href: "/admin/import-actuals", item: "importActuals", porque: "laColumnaActualEsGlCargado", lleva: [] },
    { href: "/master-data/setup-cuenta", item: "setupCuenta", porque: "aQueLineaVaEstaCuenta", lleva: [] },
    { href: "/reports/owner", item: "ownerReport", porque: "elOtroReporteAlPropietario", lleva: [] },
    { href: "/month-end/pl", item: "monthEndPL", porque: "elCierreDelMismoMes", lleva: [] },
  ],
  "/reports/opex-checkbook": [
    { href: "/reports/expenses", item: "expenses", porque: "elResultadoDeLoCargado" },
    { href: "/opex/checkbook", item: "opexByDept", porque: "laMismaCargaEditable" },
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "elDeptoQueAcabaDeCargar" },
  ],
  "/pl/balance-sheet": [
    { href: "/reports/balance-sheet-projection", item: "balanceSheetProjection", porque: "laVersionProyectada", lleva: SOLO_ESC },
    { href: "/admin/import-actuals", item: "importActuals", porque: "elGlContraElQueSeLee", lleva: [] },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "elCapitalDeTrabajoSeApoyaAca", lleva: SOLO_ESC },
    { href: "/month-end/pl", item: "monthEndPL", porque: "elCierreDelMismoMes", lleva: SOLO_ESC },
  ],
  // ⚠️ Junta: sin `dep` — su «departamento» son familias del P&L (ROOMS, FB,
  // con alias TRANSPORT), no códigos. Y no recibe `esc`: sus tres puestos
  // salen de llaves calculadas, así que atar uno pediría desarmar esa lista.
  "/reports/junta": [
    { href: "/pl/full", item: "plFullYear", porque: "elPlCompletoDetras", lleva: SOLO_ESC },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "laSeccionDeDeptos", lleva: SOLO_ESC },
    { href: "/reports/payroll-dept", item: "payrollDeptReport", porque: "laSeccionDePlanilla", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "laSeccionDeCashflow", lleva: SOLO_ESC },
    { href: "/reports/revenue-by-room", item: "revenueByRoom", porque: "laSeccionDeVolumen", lleva: SOLO_ESC },
  ],
  "/month-end/pl": [
    { href: "/admin/import-actuals", item: "importActuals", porque: "siElMesNoCuadra", lleva: [] },
    { href: "/master-data/setup-cuenta", item: "setupCuenta", porque: "cuentaMalClasificada", lleva: [] },
    { href: "/reports/owners-q", item: "ownersQ", porque: "elMismoMesParaElPropietario", lleva: [] },
    { href: "/pl/balance-sheet", item: "balanceSheet", porque: "elBalanceDelMesQueSeCierra", lleva: SOLO_ESC },
    { href: "/reports/pl-ytd", item: "plYtd", porque: "elMismoActualVsBudget", lleva: SOLO_ESC },
  ],

  // ═══ CASH FLOW · lo que faltaba del grupo ══════════════════════════════
  "/reports/balance-sheet-projection": [
    { href: "/pl/balance-sheet", item: "balanceSheet", porque: "elAnclaQueSeRueda", lleva: SOLO_ESC },
    { href: "/reports/cashflow-criteria", item: "cashflowCriteria", porque: "losMismosCriterios", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "laCajaQueCuadraCadaMes", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "loQueAlimentaPatrimonio", lleva: SOLO_ESC },
  ],
  // ⚠️ Tax EMITE pero no RECIBE, y no es una sutileza: su botón «Aplicar»
  // ESCRIBE los parámetros fiscales en el escenario del selector. El código
  // ya evita recordar la elección justamente para que nadie aplique una tasa
  // sobre un escenario que no eligió; un `?esc=` entrante lo preseleccionaría
  // y reintroduciría ese riesgo. Por eso no lleva `desdeUrl`.
  "/reports/tax": [
    { href: "/pl/full", item: "plFullYear", porque: "deDondeSaleElEbt", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "laRetencionEsSalidaDeCaja", lleva: SOLO_ESC },
    { href: "/pl/simplified", item: "plSimplified", porque: "mismoResumido", lleva: SOLO_ESC },
  ],

  // ═══ BREAK-EVEN ════════════════════════════════════════════════════════
  //
  // Break-Even consume `compute_pl_month` — EL MISMO motor que produce
  // `/pl/full`, no un endpoint aparte. Así que el salto al P&L no es una
  // analogía: es el mismo número, partido en fijo y variable.
  //
  // Las seis pantallas comparten UN escenario y UN período entre sí
  // (`_contexto.tsx`), así que moverse dentro del tab ya arrastra el contexto.
  "/break-e/resumen": [
    { href: "/pl/full", item: "plFullYear", porque: "elMismoNumeroSinPartir", lleva: SOLO_ESC },
    { href: "/break-e/por-departamento", item: "bePorDepartamento", porque: "elMismoPorDepto", lleva: SOLO_ESC },
    { href: "/break-e/mensual", item: "beMensual", porque: "elEquilibrioRealMesAMes", lleva: SOLO_ESC },
    { href: "/break-e/sin-clasificar", item: "beSinClasificar", porque: "loQueSeTomo100Fijo", lleva: SOLO_ESC },
  ],
  "/break-e/por-departamento": [
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "elMismoDeptoSinPartir", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCargaEsteGasto" },
    { href: "/break-e/configuracion", item: "beConfiguracion", porque: "dondeSeDecideElPorcentaje", lleva: SOLO_ESC },
    { href: "/break-e/resumen", item: "beResumen", porque: "elConsolidado", lleva: SOLO_ESC },
  ],
  "/break-e/sensibilidad": [
    { href: "/break-e/resumen", item: "beResumen", porque: "elPuntoDePartidaDeLaMatriz", lleva: SOLO_ESC },
    { href: "/revenue/occupancy", item: "occupancy", porque: "laOcupacionQueSeFlexiona", lleva: SOLO_ESC },
    { href: "/break-e/mensual", item: "beMensual", porque: "elEquilibrioRealMesAMes", lleva: SOLO_ESC },
  ],
  "/break-e/mensual": [
    { href: "/pl/full", item: "plFullYear", porque: "laEstacionalidadSaleDeAhi", lleva: SOLO_ESC },
    { href: "/break-e/resumen", item: "beResumen", porque: "elConsolidado", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "mesSinEquilibrioEsCajaNegativa", lleva: SOLO_ESC },
  ],
  // ⚠️ Comparar NO emite escenario (`lleva: []`). Muestra CUATRO versiones a
  // la vez, así que «el escenario de esta pantalla» no existe: mandar uno
  // sería elegir una de las cuatro por el usuario. Y su propio código ya
  // documenta que está exenta del criterio automático porque el anterior la
  // abría en un Working 2035 vacío.
  "/break-e/comparar": [
    { href: "/break-e/resumen", item: "beResumen", porque: "elDetalleDeUnaSolaColumna", lleva: [] },
    { href: "/scenarios", item: "scenarios", porque: "dondeSeCreanLasColumnas", lleva: [] },
    { href: "/pl/full", item: "plFullYear", porque: "deDondeSaleElCostoTotal", lleva: [] },
  ],
  "/break-e/sin-clasificar": [
    { href: "/break-e/configuracion", item: "beConfiguracion", porque: "dondeSeDecideElPorcentaje", lleva: SOLO_ESC },
    { href: "/admin/mapping", item: "accountMapping", porque: "cuentaHuerfanaOSinMapear", lleva: [] },
    { href: "/admin/import-actuals", item: "importActuals", porque: "porDondeEntraUnaCuentaNueva", lleva: [] },
    { href: "/break-e/resumen", item: "beResumen", porque: "elEfectoDeDecidir", lleva: SOLO_ESC },
  ],

  // ═══ OPERATIONS ════════════════════════════════════════════════════════
  "/operation-insight/summary": [
    { href: "/reports/pl-ytd", item: "plYtd", porque: "elMismoEndpointLineaPorLinea", lleva: SOLO_ESC },
    { href: "/operation-insight/room-stats", item: "roomStats", porque: "dondeSeCarganEstasNoches", lleva: SOLO_ESC },
    { href: "/reports/revenue-mix", item: "revenueMix", porque: "elCortePorLineaDeIngreso", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "elPlCompletoDetras", lleva: SOLO_ESC },
  ],
  "/operation-insight/room-stats": [
    { href: "/reports/revenue-by-room", item: "revenueByRoom", porque: "elMismoDatoComoReporte", lleva: SOLO_ESC },
    { href: "/operation-insight/summary", item: "opsSummary", porque: "estasNochesSonElDenominador", lleva: SOLO_ESC },
    { href: "/revenue/room-nights", item: "roomNights", porque: "lasNochesPresupuestadas", lleva: SOLO_ESC },
    { href: "/break-e/resumen", item: "beResumen", porque: "elRespaldoDeLasNoches", lleva: SOLO_ESC },
  ],
  "/operation-insight/headcounts": [
    { href: "/payroll/fte", item: "fteReport", porque: "elMismoRosterPorPosicion", lleva: SOLO_ESC },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeCargaEsteRoster" },
    { href: "/reports/payroll-dept", item: "payrollDeptReport", porque: "elMismoEndpointComoReporte" },
    { href: "/pl/full", item: "plFullYear", porque: "enQueTermina", lleva: SOLO_ESC },
  ],
  // ⚠️ Ops KPI es una tabla de TEXTO LIBRE: no computa nada. Sus destinos son
  // de dónde salen los números que alguien copia a mano en «Target/Actual» —
  // dependencia débil y anotada como tal, no una inventada.
  "/operation-insight/ops-kpi": [
    { href: "/operation-insight/summary", item: "opsSummary", porque: "deDondeSeCopianEstosNumeros", lleva: SOLO_ESC },
    { href: "/operation-insight/room-stats", item: "roomStats", porque: "deDondeSeCopianEstosNumeros", lleva: SOLO_ESC },
  ],
  // ⚠️ On the Books se mueve por SEMANA, no por mes: un `?mes=` acá no
  // significa nada, por eso `SOLO_ESC` en todos.
  "/operation-insight/on-the-books": [
    { href: "/pl/full", item: "plFullYear", porque: "elBudgetContraElQuePacea", lleva: SOLO_ESC },
    { href: "/revenue/room-nights", item: "roomNights", porque: "lasNochesPresupuestadas", lleva: SOLO_ESC },
    { href: "/operation-insight/room-stats", item: "roomStats", porque: "loQueFinalmenteSeMaterializo", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "elGapEsRiesgoDeCaja", lleva: SOLO_ESC },
  ],

  // ═══ MARKETING ═════════════════════════════════════════════════════════
  //
  // El par plan/medición: `/revenue/channels` planifica el mix y la comisión
  // que MANEJAN el ingreso presupuestado; acá se mide el real, que entra por
  // el XML de Opera. NO comparten tabla — y por eso justamente el salto vale.
  "/marketing-insight/channel-mix": [
    { href: "/revenue/channels", item: "channels", porque: "dondeSePlanificaEsteMix", lleva: SOLO_ESC },
    { href: "/marketing-insight/country", item: "country", porque: "elMismoXmlOtroCorte", lleva: SOLO_ESC },
    { href: "/master-data/estadisticas", item: "statistics", porque: "esteMixAlimentaLaClase9", lleva: SOLO_ESC },
    { href: "/master-data/canales", item: "canales", porque: "elCatalogoDeCanales", lleva: [] },
  ],
  "/marketing-insight/country": [
    { href: "/marketing-insight/channel-mix", item: "channelMix", porque: "elMismoXmlOtroCorte", lleva: SOLO_ESC },
    { href: "/operation-insight/room-stats", item: "roomStats", porque: "lasNochesQueEsteMixReparte", lleva: SOLO_ESC },
    { href: "/master-data/estadisticas", item: "statistics", porque: "esteMixAlimentaLaClase9", lleva: SOLO_ESC },
  ],

  // ═══ ESCENARIOS ════════════════════════════════════════════════════════
  //
  // ⚠️ `/scenarios` EMITE pero no RECIBE. Es el CRUD del escenario mismo:
  // preseleccionar una fila al lado de los botones de borrar y enllavar es la
  // peor combinación posible. Por eso no lleva `desdeUrl`.
  "/scenarios": [
    { href: "/admin/import-actuals", item: "importActuals", porque: "dondeSeLlenaElActual", lleva: [] },
    { href: "/pl/full", item: "plFullYear", porque: "queProduceEsteEscenario", lleva: [] },
    { href: "/break-e/comparar", item: "beComparar", porque: "compararLasVersionesCreadas", lleva: [] },
  ],
  "/admin/import-actuals": [
    { href: "/pl/full", item: "plFullYear", porque: "dondeAterrizaElGl", lleva: [] },
    { href: "/admin/mapping", item: "accountMapping", porque: "lasCuentasQueNoMapearon", lleva: [] },
    { href: "/break-e/sin-clasificar", item: "beSinClasificar", porque: "cuentaNuevaEntra100Fija", lleva: [] },
    { href: "/month-end/pl", item: "monthEndPL", porque: "elCierreDelMismoMes", lleva: [] },
    { href: "/scenarios", item: "scenarios", porque: "laVersionSobreLaQueEscribe", lleva: [] },
  ],

  // ═══ MASTER DATA Y ADMIN · «cambiaste esto → mirá el efecto» ════════════
  //
  // Este grupo es el único que NO consume: **define**. Así que el salto útil
  // se da vuelta. En Planning la pregunta es «¿de dónde salió este número?»;
  // acá es «¿a qué le pegué?» — y esa pregunta hoy no tiene respuesta en
  // ninguna pantalla.
  //
  // 💡 El patrón ya existía en el sistema: `/master-data/lineas-obligatorias`
  // enlaza cada fila a la pantalla donde se carga el dato que falta. Esto lo
  // generaliza, no lo inventa.
  "/master-data/tipo-cambio": [
    { href: "/pl/full", item: "plFullYear", porque: "elResultadoDelRecalculo", lleva: SOLO_ESC },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "salariosYCargasSeConvierten", lleva: SOLO_ESC },
    { href: "/reports/cashflow-directo", item: "cashflowDirect", porque: "elCobroEnColonesTambien", lleva: SOLO_ESC },
    { href: "/admin/control", item: "control", porque: "laTrazaDelEscenarioRecalculado", lleva: SOLO_ESC },
  ],
  "/master-data/room-sets": [
    { href: "/reports/rooms-sets", item: "roomsSets", porque: "elReporteDeEstosSets", lleva: SOLO_ESC },
    { href: "/reports/revenue-by-room", item: "revenueByRoom", porque: "dependeDeEsteReparto", lleva: SOLO_ESC },
    { href: "/revenue/inventory", item: "inventory", porque: "losMismosTiposDelOtroLado", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "elResultadoDelRecalculo", lleva: SOLO_ESC },
  ],
  "/admin/mapping": [
    { href: "/master-data/setup-cuenta", item: "setupCuenta", porque: "laVistaDeLecturaDeEsteMapeo", lleva: [] },
    { href: "/admin/control", item: "control", porque: "elSemaforoDeEsteMapeo", lleva: [] },
    { href: "/pl/full", item: "plFullYear", porque: "elDestinoDeTodaCuentaMapeada", lleva: [] },
    { href: "/admin/origenes", item: "origenes", porque: "elEslabonAnterior", lleva: [] },
  ],
  "/master-data/setup-cuenta": [
    { href: "/admin/mapping", item: "accountMapping", porque: "dondeSeCorrigeLoDesalineado", lleva: [] },
    { href: "/master-data/departamentos", item: "departamentos", porque: "elCatalogoQueCruza", lleva: [] },
    { href: "/master-data/chequeo", item: "chequeo", porque: "elOtroDiagnosticoPrevio", lleva: [] },
    { href: "/pl/full", item: "plFullYear", porque: "elEfectoDeLaLineaResuelta", lleva: [] },
  ],
  "/master-data/estadisticas": [
    { href: "/operation-insight/headcounts", item: "headcounts", porque: "seCalculaSobreEstasCuentas", lleva: SOLO_ESC },
    { href: "/operation-insight/ops-kpi", item: "opsKpi", porque: "seCalculaSobreEstasCuentas", lleva: SOLO_ESC },
    { href: "/operation-insight/room-stats", item: "roomStats", porque: "seCalculaSobreEstasCuentas", lleva: SOLO_ESC },
    { href: "/reports/payroll-dept", item: "payrollDeptReport", porque: "lasHorasSeValidanPorDepto", lleva: SOLO_ESC },
  ],
  // ⚠️ Es la MISMA pantalla que Planning → Sales Channels (las dos montan
  // `MixerCanales`). El salto existe justamente para que nadie se pregunte si
  // son dos cosas distintas.
  "/master-data/canales": [
    { href: "/revenue/channels", item: "channels", porque: "esLaMismaPantalla", lleva: SOLO_ESC },
    { href: "/revenue/net-rate", item: "netRate", porque: "elMixYLaComisionDanElNeto", lleva: SOLO_ESC },
    { href: "/revenue/total-revenue", item: "totalRevenue", porque: "verEfecto", lleva: SOLO_ESC },
    { href: "/marketing-insight/channel-mix", item: "channelMix", porque: "laLecturaDelMixReal", lleva: SOLO_ESC },
  ],
  "/master-data/chequeo": [
    { href: "/master-data/provisioning", item: "provisioning", porque: "dondeSeArreglaLaIdentidad", lleva: [] },
    { href: "/admin/mapping", item: "accountMapping", porque: "elMotorSinSembrarSeVeAca", lleva: [] },
    { href: "/master-data/lineas-obligatorias", item: "lineasObligatorias", porque: "elPar_instalacionVsEscenario", lleva: [] },
    { href: "/master-data/departamentos", item: "departamentos", porque: "elCatalogoQueCruza", lleva: [] },
  ],
  "/master-data/lineas-obligatorias": [
    { href: "/revenue/checkbook", item: "revenueCheckbook", porque: "dondeSeCargaLoQueFalta", lleva: SOLO_ESC },
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCargaLoQueFalta", lleva: SOLO_ESC },
    { href: "/payroll/checkbook", item: "payrollByDept", porque: "dondeSeCargaLoQueFalta", lleva: SOLO_ESC },
    { href: "/pl/full", item: "plFullYear", porque: "elReporteQueQuedaConElAgujero", lleva: SOLO_ESC },
    { href: "/master-data/chequeo", item: "chequeo", porque: "elPar_instalacionVsEscenario", lleva: [] },
  ],
  // ⚠️ El PAR: este define QUÉ EXISTE, provisioning define QUIÉN SE VE. Son
  // dos preguntas distintas y la confusión entre ellas ya costó tiempo.
  "/master-data/departamentos": [
    { href: "/master-data/provisioning", item: "provisioning", porque: "elPar_existeVsSeVe", lleva: [] },
    { href: "/admin/mapping", item: "accountMapping", porque: "cadaCuentaLlevaEsteCodigo", lleva: [] },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "dondeAparecenRenombrados", lleva: [] },
    { href: "/opex/checkbook", item: "opexByDept", porque: "dondeSeCargaSuGasto", lleva: [] },
  ],
  "/master-data/provisioning": [
    { href: "/master-data/departamentos", item: "departamentos", porque: "elPar_existeVsSeVe", lleva: [] },
    { href: "/master-data/chequeo", item: "chequeo", porque: "verificarDespuesDeCopiar", lleva: [] },
    { href: "/reports/pl-by-dept", item: "plByDept", porque: "elEfectoDeApagarUnDepto", lleva: [] },
  ],
  "/admin/origenes": [
    { href: "/admin/import-actuals", item: "importActuals", porque: "elArchivoSeTraduceConEstasReglas", lleva: [] },
    { href: "/admin/mapping", item: "accountMapping", porque: "elEslabonSiguiente", lleva: [] },
    { href: "/admin/control", item: "control", porque: "dondeSeValidaElArchivo", lleva: [] },
  ],
  "/dashboard": [
    { href: "/pl/full", item: "plFullYear", porque: "elPlCompletoDetras", lleva: SOLO_ESC },
    { href: "/reports/summary", item: "execSummary", porque: "laVersionLargaDeEstosKpi", lleva: SOLO_ESC },
    { href: "/reports/cashflow-budget", item: "cashflowBudget", porque: "cuandoEntra", lleva: SOLO_ESC },
    { href: "/operation-insight/summary", item: "opsSummary", porque: "elDetalleOperativo", lleva: SOLO_ESC },
  ],

  // ⚠️ NO están acá, y es una decisión: `/admin/users` y `/admin/apariencia`
  // no tienen ninguna dependencia de dato con el resto del sistema. Inventarles
  // saltos para que «no les falte nada» degradaría los que sí significan algo:
  // el valor de esta barra es que cada destino responda una pregunta real.
};

/** Los saltos de una ruta. Vacío si esa pantalla todavía no está en el grafo. */
export function saltosDe(pathname: string): Destino[] {
  return SALTOS[pathname] ?? [];
}
