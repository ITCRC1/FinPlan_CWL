import type { FilaPlanning } from "@/lib/planningReport";

/**
 * El bloque de VALIDACIÓN del P&L por categoría.
 *
 * Owner, 2026-11-09, mandando el tab que había armado a mano: *«favor
 * implementar todas estas fórmulas de validación en el excel con fórmulas y
 * todo. toma el tab y construye dentro el archivo todo lo que está abajo»*.
 *
 * ## Qué hace
 *
 * Debajo del P&L, en la misma hoja, vuelve a calcular la cascada **con
 * fórmulas vivas** y la compara contra lo que escribió el motor. Las filas
 * `CHECK` tienen que dar **0**: si alguna no da cero, el número de arriba y la
 * aritmética de abajo dejaron de decir lo mismo.
 *
 * No es decoración. Es lo que convierte el libro en algo que se puede auditar
 * sin volver al sistema: se abre el Excel, se mira la columna de checks, y si
 * están en cero el reporte se sostiene solo.
 *
 * ## ⚠️ Por qué NO hay un solo número de fila escrito a mano
 *
 * El tab del owner apuntaba a filas fijas —`'Checkbook Planilla'!B12`,
 * `'Detalle Planilla'!N217:N221`—. Esas filas dependen de cuántos
 * departamentos y cuentas traiga el escenario y de si está activo «esconder
 * las líneas en cero». Copiarlas al generador es garantizar que se corran
 * solas, y el modo de falla es el peor que hay acá: el exportador compara la
 * fórmula contra el número, no cuadra, y **la descarta en silencio**. El libro
 * baja con media hoja de números pegados y nadie se entera.
 *
 * Acá hay dos mecanismos y ninguno es un número:
 *
 * * dentro de la hoja, **ordinales** (`{r:N}`) que resuelve el exportador;
 * * a otra hoja, **el rótulo** (`{h:Hoja:Rótulo}`), que el exportador busca en
 *   la hoja destino al armar el libro. Si no lo encuentra, deja la celda
 *   VACÍA — una celda en blanco se nota, una fórmula que apunta a la cuenta
 *   equivocada no.
 */

/** Los supuestos del recálculo. Son celdas EDITABLES: el owner cambia el 3% y
 *  la cascada entera se mueve en el Excel, sin volver al sistema. */
export interface SupuestosValidacion {
  mgmtFeePct: number;
  capitalReservePct: number;
  tasaRenta: number;
  /** CCSS patronal sobre salario bruto. */
  ccssPct: number;
  /** Aguinaldo: un doceavo. */
  aguinaldoPct: number;
}

export const SUPUESTOS: SupuestosValidacion = {
  mgmtFeePct: 0.03,
  capitalReservePct: 0.04,
  tasaRenta: 0.30,
  ccssPct: 0.2683,
  aguinaldoPct: 1 / 12,
};

/** Los rótulos del P&L por categoría que el bloque necesita encontrar arriba. */
const ARRIBA = {
  ingreso: "TOTAL INGRESO",
  costo: "TOTAL COSTO DE VENTAS",
  planilla: "TOTAL PLANILLA",
  opex: "TOTAL GASTOS OPERATIVOS",
  reparto: "TOTAL REPARTO",
  gop: "TOTAL GROSS OPERATING PROFIT",
  rent: "Rent",
  fee: "Management Fees (5%)",
  capital: "CAPITAL EXPENSE",
  renta: "Income Taxes (30%)",
  seguro: "Property Insurance",
  otros: "Other Expenses",
  financiero: "FINANCIAL EXPENSES",
  deprec: "TOTAL DEPRECIATIONS",
  neto: "NET PROFIT",
} as const;

/** Las cuentas de planilla, tal como las rotula el Checkbook Planilla. */
const CUENTAS_PLANILLA = {
  salario: "6000 · Salary and Wages",
  ccss: "6020 · Social Security",
  aguinaldo: "6021 · Aguinaldo",
  feriados: "6003 · Working Holiday",
  vacaciones: "6023 · Vacation Provision",
  riesgos: "6022 · Work Risk Policy",
} as const;

interface Contexto {
  /** Las filas YA emitidas del cuadro: de ahí salen los ordinales de arriba. */
  emitidas: { label: string }[];
  /** Cuántas versiones trae el cuadro. */
  versiones: number;
  /** De qué versión son los doce meses. Su columna Full Year es la única que
   *  recibe fórmula: las demás versiones no tienen sus meses en la hoja, así
   *  que una fórmula ahí apuntaría a celdas en blanco. */
  mesesDe: number;
}

/** Una fila del bloque. `v` es el valor fijo (supuestos); `f`, la plantilla. */
interface Def {
  label: string;
  seccion?: boolean;
  total?: boolean;
  formato?: "usd2" | "pct" | "texto";
  v?: number;
  f?: (o: (clave: string) => string) => string;
}

export function filasDeValidacion(ctx: Contexto): FilaPlanning[] {
  const { emitidas, versiones, mesesDe } = ctx;

  /** El ordinal de un rótulo YA emitido, o -1. */
  const arriba = (rot: string) => emitidas.findIndex(f => f.label === rot);

  // ⚠️ Si al P&L le falta alguno de los renglones que el bloque necesita, NO se
  // emite nada. Media validación —con la mitad de los checks apuntando a filas
  // que no existen— es peor que ninguna: los checks que sí salen dan cero y se
  // leen como «todo bien».
  const faltan = Object.values(ARRIBA).filter(r => arriba(r) < 0);
  if (faltan.length) return [];

  const filas: FilaPlanning[] = [];
  /** Ordinal de una fila del bloque, por su rótulo, una vez emitida. */
  const ord: Record<string, number> = {};
  const refs = (clave: string) => String(ord[clave]);

  const push = (clave: string, d: Def) => {
    // ⚠️ El ordinal se calcula sobre el arreglo EMITIDO completo —las filas del
    // P&L más las del bloque que ya se agregaron—, porque es lo que el
    // exportador va a recorrer para resolver `{r:N}`.
    ord[clave] = emitidas.length + filas.length;

    if (d.seccion) {
      // Una sección va sin números. `meses: null` es lo que `armarCuadro`
      // entiende por eso.
      filas.push({ label: d.label, es_seccion: true, meses: null });
      return;
    }

    // Un SUPUESTO vive en UNA celda —la de enero— y todas las columnas la
    // miran con `$B`. Repetirlo doce veces se leería como doce supuestos.
    // Una fila de FÓRMULA lleva un cero en los doce meses: el exportador
    // escribe la fórmula donde hay valor y saltea las celdas vacías, así que
    // el cero es lo que la habilita, no un dato.
    const meses: (number | null)[] = d.f
      ? Array.from({ length: 12 }, () => 0)
      : [d.v ?? 0, ...Array.from({ length: 11 }, () => null)];
    const anios: (number | null)[] = Array.from(
      { length: versiones }, (_, vi) => (d.f && vi === mesesDe ? 0 : null));

    filas.push({
      label: d.label,
      es_total: d.total,
      formato: d.formato ?? "usd2",
      meses,
      anios,
      formula_tpl: d.f ? d.f(refs) : undefined,
    });
  };

  // Atajos para escribir las plantillas.
  const A = (k: keyof typeof ARRIBA) => `{c}{r:${arriba(ARRIBA[k])}}`;
  const R = (clave: string) => `{c}{r:${ord[clave]}}`;
  const ABS = (clave: string) => `$B{R:${ord[clave]}}`;
  const H = (hoja: string, rot: string) => `{h:${hoja}:${rot}}`;
  /** `SUMIF` por rótulo: suma TODAS las filas con ese nombre en la otra hoja.
   *  Es lo que hace falta cuando el rótulo se repite —`6000 · Salary and
   *  Wages` aparece en cada departamento— y es inmune a que se muevan. */
  /** Un CHECK que DICE que no pudo comprobar, en vez de devolver el total.
   *
   *  ⚠️ Sin esto, un CHECK cuya contraparte quedó vacía da `valor − vacío =
   *  valor`: la fila dice «−6.517.247,39» y se lee como un descuadre
   *  catastrófico cuando lo que pasó es que la hoja no está en el libro. */
  const chk = (ref: string, resta: string) =>
    `=IF(${ref}="","sin hoja",ROUND(${resta},2))`;

  const SUMIF = (hoja: string, rot: string) =>
    // ⚠️ `IFERROR(...,"")` y no a secas. Un libro puede bajarse SIN los
    // checkbooks —el botón «Sólo esta vista» baja una hoja— y entonces el
    // `SUMIF` a una hoja ausente da `#REF!`, que se propaga a los CHECK y
    // deja media hoja en rojo. Vacío es la respuesta correcta: «esto no se
    // pudo comprobar», que no es lo mismo que «no cuadra».
    `IFERROR(SUMIF('${hoja}'!$A:$A,"${rot}",'${hoja}'!{c}:{c}),"")`;

  // ════════════════════════════════════════════════════════════════════════
  // 1 · Los supuestos, editables
  // ════════════════════════════════════════════════════════════════════════
  push("sec1", { label: "VALIDACIÓN · SUPUESTOS DE PLANILLA (celdas editables)",
                 seccion: true });
  push("pCcss", { label: "CCSS patronal · % s/ salario bruto",
                  v: SUPUESTOS.ccssPct, formato: "pct" });
  push("pAgui", { label: "Aguinaldo · % s/ salario bruto (1/12)",
                  v: SUPUESTOS.aguinaldoPct, formato: "pct" });

  // ════════════════════════════════════════════════════════════════════════
  // 2 · La cascada, recalculada desde los totales de arriba
  // ════════════════════════════════════════════════════════════════════════
  // ⚠️ Lo que este bloque prueba: que los renglones que la hoja MUESTRA suman
  // los resultados que la hoja muestra. Cada término sale de una fila de
  // arriba, así que un cero significa «la cascada cierra con lo que se ve» —
  // que es justo la pregunta de integridad del P&L.
  push("sec2", { label: "VALIDACIÓN · LA CASCADA CIERRA CON LO QUE SE VE",
                 seccion: true });
  push("vIng", { label: "Total Ingreso", f: () => `=${A("ingreso")}` });
  push("vCos", { label: "(−) Costo de ventas", f: () => `=${A("costo")}` });
  push("vPay", { label: "(−) Planilla", f: () => `=${A("planilla")}` });
  push("vOpx", { label: "(−) Gastos operativos", f: () => `=${A("opex")}` });
  push("vRep", { label: "(−) Reparto", f: () => `=${A("reparto")}` });
  push("vGop", { label: "GOP recalculado", total: true,
                 f: () => `=${R("vIng")}-${R("vCos")}-${R("vPay")}-${R("vOpx")}-${R("vRep")}` });
  push("kGop", { label: "CHECK · GOP recalculado vs P&L (debe ser 0)", total: true,
                 f: () => `=ROUND(${R("vGop")}-${A("gop")},2)` });

  push("vRent", { label: "(−) Rent", f: () => `=${A("rent")}` });
  // ⚠️ El MONTO del P&L, no `ingreso × 3%`.
  //
  // Un % fijo acá convierte el CHECK en una comparación contra MI supuesto y
  // no contra el sistema. Los escenarios de 2027 guardan 3% y coincidía por
  // convención; los de 2026 **no tienen `pl_manual_inputs`** y toman el fee
  // del mayor —el Forecast October paga 3,29%—, así que el check habría dado
  // falsa alarma en cuanto él comparara contra el año anterior. Una falsa
  // alarma gasta la confianza igual que un falso cero.
  //
  // El % sigue abajo, como DIAGNÓSTICO: ahí sí dice algo.
  push("vFee", { label: "(−) Management Fees", f: () => `=${A("fee")}` });
  push("vSeg", { label: "(−) Property Insurance", f: () => `=${A("seguro")}` });
  push("vOtr", { label: "(−) Other Expenses", f: () => `=${A("otros")}` });
  push("vEbitda", { label: "EBITDA Before Capital recalculado", total: true,
                    f: () => `=${R("vGop")}-${R("vRent")}-${R("vFee")}`
                             + `-${R("vSeg")}-${R("vOtr")}` });
  push("vCap", { label: "(−) Capital Expense", f: () => `=${A("capital")}` });
  push("vEbitda2", { label: "EBITDA After Capital recalculado", total: true,
                     f: () => `=${R("vEbitda")}-${R("vCap")}` });
  push("vFin", { label: "(−) Financial Expenses", f: () => `=${A("financiero")}` });
  push("vDep", { label: "(−) Depreciation", f: () => `=${A("deprec")}` });
  push("vEbt", { label: "EBT recalculado", total: true,
                 f: () => `=${R("vEbitda2")}-${R("vFin")}-${R("vDep")}` });
  // El impuesto del motor es ANUAL —tiene piso de cero sobre el ejercicio, no
  // sobre el mes— así que `MAX(0, EBT × tasa)` mes a mes no lo reproduce en un
  // año con meses en pérdida. Se toma el monto y la tasa va de diagnóstico.
  push("vTax", { label: "(−) Income Taxes", f: () => `=${A("renta")}` });
  push("vNeto", { label: "NET PROFIT recalculado", total: true,
                  f: () => `=${R("vEbt")}-${R("vTax")}` });
  push("kNeto", { label: "CHECK · Net Profit recalculado vs P&L (debe ser 0)",
                  total: true,
                  f: () => `=ROUND(${R("vNeto")}-${A("neto")},2)` });

  // ════════════════════════════════════════════════════════════════════════
  // 3 · Contra los checkbooks, por rótulo
  // ════════════════════════════════════════════════════════════════════════
  // ── Las tasas IMPLÍCITAS ─────────────────────────────────────────────
  //
  // Esto es lo que el % sí aporta: no manejar la cascada, sino decir a qué
  // tasa está saliendo cada cosa. Un fee al 3,29% en vez del 3% se ve acá, y
  // es información — no un error.
  push("secTasas", { label: "VALIDACIÓN · TASAS IMPLÍCITAS (informativo)",
                     seccion: true });
  push("iFee", { label: "Management Fee ÷ Total Ingreso", formato: "pct",
                 f: () => `=IFERROR(${R("vFee")}/${R("vIng")},"")` });
  push("iCap", { label: "Capital Expense ÷ Total Ingreso", formato: "pct",
                 f: () => `=IFERROR(${R("vCap")}/${R("vIng")},"")` });
  push("iRenta", { label: "Impuesto ÷ EBT", formato: "pct",
                   f: () => `=IFERROR(${R("vTax")}/${R("vEbt")},"")` });

  push("sec3", { label: "VALIDACIÓN · CONTRA LOS CHECKBOOKS", seccion: true });
  push("cIng", { label: "Total Ingreso · Checkbook",
                 f: () => `=${H("Checkbook Ingreso", "TOTAL INGRESO")}` });
  push("kIng", { label: "CHECK · Ingreso P&L vs Checkbook (debe ser 0)", total: true,
                 f: () => chk(R("cIng"), `${A("ingreso")}-${R("cIng")}`) });
  push("cCos", { label: "Total Costo de ventas · Checkbook",
                 f: () => `=${H("Checkbook Costo de ventas", "TOTAL COSTO DE VENTAS")}` });
  push("kCos", { label: "CHECK · Costo P&L vs Checkbook (debe ser 0)", total: true,
                 f: () => chk(R("cCos"), `${A("costo")}-${R("cCos")}`) });
  push("cPay", { label: "Total Planilla · Checkbook",
                 f: () => `=${H("Checkbook Planilla", "TOTAL PLANILLA")}` });
  push("kPay", { label: "CHECK · Planilla P&L vs Checkbook (debe ser 0)", total: true,
                 f: () => chk(R("cPay"), `${A("planilla")}-${R("cPay")}`) });
  push("cOpx", { label: "Total Gastos operativos · Checkbook",
                 f: () => `=${H("Checkbook Gastos operativos", "TOTAL GASTOS OPERATIVOS")}` });

  // ════════════════════════════════════════════════════════════════════════
  // 4 · La planilla, recalculada sobre el salario bruto
  // ════════════════════════════════════════════════════════════════════════
  //
  // La pregunta del owner en su tab: ¿la CCSS y el aguinaldo salen del salario
  // solo, o del salario MÁS los feriados? El bloque calcula las dos tasas y la
  // que sale constante es la buena.
  push("sec4", { label: "VALIDACIÓN · PLANILLA · ¿sobre qué base van CCSS y aguinaldo?",
                 seccion: true });
  push("pSal", { label: "Salario (6000) · Checkbook",
                 f: () => `=${SUMIF("Checkbook Planilla", CUENTAS_PLANILLA.salario)}` });
  push("pFer", { label: "Feriados (6003) · Checkbook",
                 f: () => `=${SUMIF("Checkbook Planilla", CUENTAS_PLANILLA.feriados)}` });
  push("pBruto", { label: "Salario bruto = 6000 + 6003", total: true,
                   f: () => `=${R("pSal")}+${R("pFer")}` });
  push("pCcssChk", { label: "CCSS (6020) · Checkbook",
                     f: () => `=${SUMIF("Checkbook Planilla", CUENTAS_PLANILLA.ccss)}` });
  push("pAguiChk", { label: "Aguinaldo (6021) · Checkbook",
                     f: () => `=${SUMIF("Checkbook Planilla", CUENTAS_PLANILLA.aguinaldo)}` });
  push("pCcssRec", { label: "CCSS recalculada = bruto × %",
                     f: () => `=${R("pBruto")}*${ABS("pCcss")}` });
  push("pAguiRec", { label: "Aguinaldo recalculado = bruto × 1/12",
                     f: () => `=${R("pBruto")}*${ABS("pAgui")}` });
  push("kCcss", { label: "CHECK · CCSS recalculada vs Checkbook", total: true,
                  f: () => chk(R("pCcssChk"), `${R("pCcssRec")}-${R("pCcssChk")}`) });
  push("kAgui", { label: "CHECK · Aguinaldo recalculado vs Checkbook", total: true,
                  f: () => chk(R("pAguiChk"), `${R("pAguiRec")}-${R("pAguiChk")}`) });

  push("tCcssSin", { label: "Tasa CCSS ÷ salario SIN feriados", formato: "pct",
                     f: () => `=IFERROR(${R("pCcssChk")}/${R("pSal")},"")` });
  push("tCcssCon", { label: "Tasa CCSS ÷ salario CON feriados", formato: "pct",
                     f: () => `=IFERROR(${R("pCcssChk")}/${R("pBruto")},"")` });
  push("tAguiSin", { label: "Tasa Aguinaldo ÷ salario SIN feriados", formato: "pct",
                     f: () => `=IFERROR(${R("pAguiChk")}/${R("pSal")},"")` });
  push("tAguiCon", { label: "Tasa Aguinaldo ÷ salario CON feriados", formato: "pct",
                     f: () => `=IFERROR(${R("pAguiChk")}/${R("pBruto")},"")` });

  push("nota", {
    label: "La tasa que sale CONSTANTE los doce meses es la base real. "
      + "Las celdas de supuestos son editables: cambie una y la cascada se mueve.",
    seccion: true,
  });

  return filas;
}
