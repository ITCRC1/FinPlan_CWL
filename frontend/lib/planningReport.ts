import type {
  AllocationSummary, DetalleCelda, EstadisticasCierre, GastoEscenario,
  PLDetail, PLDetailFila, PosicionesVersion, Scenario,
} from "@/lib/api";
import type { Cuadro, ColumnaCuadro, FilaCuadro, FormatoCol } from "@/lib/exportCuadro";
import {
  componentesDelPL, OPERANDOS_DE_LA_CASCADA, resultadosDelPL, rotuloAmbito, suma,
} from "@/lib/tresCortes";

/**
 * El reporte de PLANNING: los doce meses de una versión y el año de todas.
 *
 * Owner, 2026-10-01, mirando el cierre y pidiéndolo para el Budget 2027:
 * *«quiero 12 meses, y full year para comparar con otras versiones»* · *«quizás
 * acá no necesitamos revisar mes, YTD o Full Year»* · *«ajustado todos los
 * reportes para que se pueda generar reportes para comparar todos. desde los
 * reportes, hasta los checkbooks»*.
 *
 * ## Por qué esta forma y no la del cierre
 *
 * El cierre contesta «cómo vamos»: por eso parte el año en mes, acumulado y año,
 * y repite las versiones en cada corte. Planning contesta otra cosa —«cómo queda
 * el año»— y ahí el acumulado a octubre no significa nada: lo que se mira es la
 * estacionalidad mes a mes y el total contra la versión anterior.
 *
 * ```
 *  rótulo │ Ene  Feb  …  Dic │ FY versión A │ FY versión B │ Variación
 *         └── sólo la A ─────┘└──────── todas las versiones ─────────┘
 * ```
 *
 * Quince columnas con dos versiones, contra las treinta y nueve que saldrían de
 * abrir cada mes por versión. El owner eligió esta: *«igual de legible que la
 * pantalla de hoy»*.
 *
 * ## ⚠️ Los CUATRO cuadros tienen las MISMAS columnas
 *
 * El P&L, las cinco aperturas, los cinco checkbooks y las estadísticas salen
 * todos de `armarCuadro`, con la misma `columnasPlanning`. No es economía de
 * líneas: es que la columna «Full Year» de la apertura de opex tiene que ser la
 * misma celda —mismo índice, misma fórmula, misma versión— que la del P&L. Con
 * dos constructores, el día que alguien agregue una versión comparada una de las
 * dos hojas apunta a la columna de al lado y resta las versiones cambiadas sin
 * que nada falle.
 *
 * ## ⚠️ Una definición para la pantalla y para el Excel
 *
 * Devuelve un `Cuadro`, que es lo que come `bajarCuadros`. La pantalla dibuja
 * **ese mismo objeto**: no hay una tabla en JSX y otra en el exportador, así que
 * no pueden decir cosas distintas. Es la misma regla que ya siguen el P&L de
 * tres cortes y los checkbooks.
 *
 * ## ⚠️ La columna del año es una FÓRMULA
 *
 * `suma_cols` sobre los doce meses: en el Excel baja como `=SUM(B5:M5)` y se
 * mueve si alguien corrige un mes. Las otras columnas de año —las de las
 * versiones comparadas— se quedan como número, porque sus doce meses no están
 * en la hoja y una fórmula no tendría a qué apuntar.
 */

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const MES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                   "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"];

const DOCE = Array.from({ length: 12 }, (_, i) => i);

/** Dónde empieza el bloque de años, base 0 sobre `columnas`: el rótulo más los
 *  doce meses. */
const BASE_ANIO = 13;

/** Debajo de esto una celda es cero, y una fila entera de ceros se esconde. */
const CENTAVO = 0.005;

/** El rótulo corto de una versión: «BUDGET Working 2027». */
export function rotuloDeVersion(
  escenarios: Scenario[], id: string, caida = "",
): string {
  const e = escenarios.find(x => x.id === id);
  return e ? `${e.type} ${e.version} ${e.year}` : (caida || id.slice(0, 8));
}

/** Las versiones que trae cualquiera de los cuatro endpoints: lo único que se
 *  les pide es saber cómo se llaman. */
export interface VersionPlanning { scenario_id?: string; escenario?: string }

/** Cómo se llama cada versión, por su índice. */
export function nombradorDeVersiones(
  versiones: VersionPlanning[], escenarios: Scenario[],
): (vi: number) => string {
  return vi => rotuloDeVersion(
    escenarios, versiones[vi]?.scenario_id ?? "", versiones[vi]?.escenario);
}

/** Qué dos versiones se restan. Sin pedido, la principal contra la primera
 *  comparada; con una sola versión, ninguna. */
export function parPorDefecto(
  cuantas: number, pedido?: [number, number],
): [number, number] | undefined {
  if (pedido) return pedido;
  return cuantas > 1 ? [0, 1] : undefined;
}

/**
 * ⚠️ **Las columnas, una sola vez para los cuatro cuadros.**
 *
 * Doce meses de la versión principal, un año por versión y la variación. La
 * columna de año de la principal baja como `=SUM(B5:M5)`; la de las comparadas,
 * no, porque sus meses no están en la hoja.
 */
export function columnasPlanning(
  cuantas: number, nombre: (vi: number) => string,
  par: [number, number] | undefined, anchoRotulo = 34,
  /** De QUÉ versión son los doce meses. Owner, 2026-10-01: *«quiero que metas
   *  la opción de generar un 12 meses de Forecast y Budget 2026»*. */
  mv = 0,
  /** Qué OTRAS versiones abren sus doce meses, a la derecha del cuadro y cada
   *  una detrás de una columna en blanco. Owner, 2026-10-05: *«después de la
   *  línea roja … el Forecast 2027 Working, doce meses, y después con una
   *  columna de espacio viene 12 meses budget 2026 Final»*. */
  extras: number[] = [],
): ColumnaCuadro[] {
  /** Dónde empiezan los meses del bloque `e`: el hueco va primero. */
  const inicioExtra = (e: number) =>
    BASE_ANIO + cuantas + (par ? 1 : 0) + e * 13 + 1;
  /** Los doce meses de una versión, por su posición de arranque. */
  const docePartiendoDe = (desde: number) => DOCE.map((_m, i) => desde + i);
  return [
    { label: "Line Item", ancho: anchoRotulo, formato: "texto" },
    ...MESES.map((m, i) => ({
      label: m, sub: MES_LARGO[i], ancho: 13, formato: "usd2" as const,
      ...(i === 0 ? { abre_grupo: true } : {}),
    })),
    // ⚠️ El año de la versión que puso los meses ES la suma de esos doce, y baja
    // como `=SUM(B5:M5)`: es la celda que alguien va a querer ver moverse
    // cuando corrija un mes en la reunión.
    //
    // ⚠️ Las DEMÁS versiones traen su año y NADA MÁS —sin `suma_cols`—: sus doce
    // meses no están en la hoja, así que la fórmula no tendría a qué apuntar y
    // el exportador la tiraría igual, en silencio. Por eso la fórmula sigue a
    // `mv` y no se queda clavada en la primera columna de año.
    ...Array.from({ length: cuantas }, (_, vi) => {
      // ⚠️ La fórmula sigue a los MESES, no a la versión principal: una versión
      // cuyos doce meses ahora están en la hoja puede sumarlos de verdad, y la
      // que no los tiene se queda como número porque no tendría a qué apuntar.
      const e = extras.indexOf(vi);
      const desde = vi === mv ? 1 : (e >= 0 ? inicioExtra(e) : -1);
      return {
        label: "Full Year", sub: nombre(vi), ancho: 16, formato: "usd2" as const,
        ...(vi === 0 ? { abre_grupo: true } : {}),
        ...(desde > 0 ? { suma_cols: docePartiendoDe(desde) } : {}),
      };
    }),
    ...(par
      ? [{ label: "Variación", sub: `${nombre(par[0])} − ${nombre(par[1])}`,
           ancho: 16, formato: "usd2" as const,
           resta: [BASE_ANIO + par[0], BASE_ANIO + par[1]] as [number, number] }]
      : []),
    // ⚠️ Los bloques extra van al FINAL, después de la variación: así los
    // índices de `resta` y de `suma_cols` del bloque principal no se mueven.
    // Agregarlos en medio correría la columna de cada año y la variación
    // restaría dos versiones distintas sin que nada fallara.
    ...extras.flatMap(vi => [
      // La columna en blanco que pidió el owner: separa un bloque del otro y no
      // lleva número, para que nadie la lea como un mes en cero.
      { label: "", sub: "", ancho: 2, formato: "texto" as const },
      ...MESES.map((m, i) => ({
        label: m, sub: `${MES_LARGO[i]} · ${nombre(vi)}`, ancho: 13,
        formato: "usd2" as const,
        ...(i === 0 ? { abre_grupo: true } : {}),
      })),
    ]),
  ];
}

/** Una fila antes de volverse celdas: los doce meses de la principal y el año de
 *  cada versión. La variación la calcula `armarCuadro`, para que no haya dos
 *  maneras de restar. */
export interface FilaPlanning {
  label: string;
  /**
   * Los doce meses. `null` = esta fila no lleva números (encabezado de
   * sección): un cero ahí se leería como «sin movimiento».
   *
   * ⚠️ Es una FUNCIÓN de la versión, no un arreglo. Con un arreglo, abrir los
   * doce meses de una segunda versión obligaba a que cada constructor eligiera
   * por su cuenta de cuál versión eran — y siete constructores eligiendo por
   * separado es exactamente cómo una hoja termina mostrando el Forecast bajo el
   * rótulo del Budget sin que ningún total deje de cuadrar.
   *
   * Un arreglo suelto se sigue aceptando y vale sólo para el bloque principal:
   * las estadísticas lo usan porque sus meses se piden uno por uno.
   */
  meses?: ((vi: number) => (number | null)[] | null) | (number | null)[] | null;
  /** Uno por versión, en el orden en que vienen. */
  anios?: (number | null)[];
  es_total?: boolean;
  es_seccion?: boolean;
  nivel?: number;
  formato?: FormatoCol;
  suma_de?: number[];
  combina_filas?: [number, number][];
}

export interface OpcionesCuadro {
  titulo: string;
  subtitulo: string;
  hoja: string;
  anchoRotulo?: number;
  /** De qué versión son los doce meses. 0 = la principal. */
  mesesDe?: number;
  /** Qué otras versiones abren además sus doce meses, a la derecha. */
  extras?: number[];
}

/**
 * El `Cuadro` terminado. Los cuatro reportes de esta pantalla pasan por acá.
 *
 * ⚠️ La variación se calcula **de una sola manera**: `anios[a] − anios[b]`, con
 * el mismo par que le dio su `resta` a la columna. Si la pantalla restara por su
 * cuenta, el número y la fórmula del Excel podrían decir cosas distintas.
 */
export function armarCuadro(
  opciones: OpcionesCuadro, cuantas: number, nombre: (vi: number) => string,
  par: [number, number] | undefined, filas: FilaPlanning[],
): Cuadro {
  const mv = opciones.mesesDe ?? 0;
  // Una versión no puede abrir sus meses dos veces: la principal ya los tiene.
  const extras = (opciones.extras ?? []).filter(vi => vi !== mv && vi < cuantas);
  const columnas = columnasPlanning(cuantas, nombre, par, opciones.anchoRotulo,
                                    mv, extras);
  return {
    titulo: opciones.titulo,
    subtitulo: opciones.subtitulo,
    hoja: opciones.hoja.slice(0, 31),
    columnas,
    filas: filas.map((f): FilaCuadro => {
      // ⚠️ Una sección va SIN números, no en cero: un cero ahí se leería como
      // «este bloque no tuvo movimiento», que es una afirmación y no un hueco.
      if (f.meses === null) {
        return {
          label: f.label, es_seccion: f.es_seccion ?? true, nivel: f.nivel,
          formato: f.formato ?? "usd2",
          valores: columnas.slice(1).map(() => null),
        };
      }
      const anios = Array.from({ length: cuantas }, (_, vi) => f.anios?.[vi] ?? null);
      const d = par && anios[par[0]] !== null && anios[par[1]] !== null
        ? anios[par[0]]! - anios[par[1]]! : null;
      // ⚠️ El arreglo suelto vale SÓLO para el bloque principal. Repetirlo en
      // los extra pondría los mismos doce números bajo el rótulo de otra
      // versión: una hoja que se lee bien y miente. Sin dato, van en blanco.
      const doceDe = (vi: number, principal: boolean) =>
        typeof f.meses === "function" ? f.meses(vi)
          : (principal ? (f.meses ?? null) : null);
      const bloque = (vi: number, principal: boolean) => {
        const m = doceDe(vi, principal);
        return DOCE.map(i => (m ? m[i] ?? 0 : null));
      };
      return {
        label: f.label,
        es_total: f.es_total, es_seccion: f.es_seccion, nivel: f.nivel,
        formato: f.formato ?? "usd2",
        suma_de: f.suma_de, combina_filas: f.combina_filas,
        valores: [
          ...bloque(mv, true),
          ...anios,
          ...(par ? [d] : []),
          // Cada extra: la columna en blanco y sus doce meses.
          ...extras.flatMap(vi => [null, ...bloque(vi, false)]),
        ],
      };
    }),
  };
}

/* ═══════════════════════ 1 · El P&L ══════════════════════════════════════ */

/** Los doce meses de una fila para la versión `vi`, o `null` si no la trae. */
const mesesDe = (f: PLDetailFila, vi: number) => f.series?.[vi] ?? null;

/** El año de una fila para la versión `vi`. */
const anioDe = (f: PLDetailFila, vi: number) => {
  const s = mesesDe(f, vi);
  return s ? suma(s, DOCE) : null;
};

export interface OpcionesPlanning {
  /** El ámbito, para el título y el nombre de la hoja. */
  ambito: string;
  /** Qué dos versiones se restan, por su índice en `datos.versiones`.
   *  Sin esto, la principal contra la primera comparada. */
  par?: [number, number];
  /** Esconde las filas de detalle que están en cero en TODAS las versiones.
   *  Un presupuesto en construcción tiene muchas. */
  compacto?: boolean;
  /**
   * De QUÉ versión son los doce meses. 0 = la principal.
   *
   * Owner, 2026-10-01: *«quiero que metas la opción de generar un 12 meses de
   * Forecast y Budget 2026»*. El año de cada versión siempre está; lo que se
   * elige acá es de cuál se abre la estacionalidad.
   *
   * ⚠️ La fórmula `=SUM(B5:M5)` se mueve con esto: la columna de año que suma
   * sus meses es la de ESTA versión, no la primera. Dejarla clavada escribiría
   * una suma en una columna cuyos sumandos no están en la hoja — y el
   * exportador la descarta, así que la hoja pierde su fórmula más mirada sin
   * que nada avise.
   */
  mesesDe?: number;
  /** Qué OTRAS versiones abren además sus doce meses, a la derecha del cuadro.
   *  Owner, 2026-10-05: *«eso en todos los tabs, uno a uno»*. */
  extras?: number[];
}

/** Cómo se rotula de quién son los doce meses, para el título y la hoja. */
const deQuien = (nombre: (vi: number) => string, mv: number) =>
  mv ? ` · meses de ${nombre(mv)}` : "";

/**
 * El cuadro del P&L. `datos` viene de `/reports/pl-detail/{ambito}/`, que ya
 * manda los doce meses de cada fila por versión — los cortes se arman acá y no
 * se le piden al servidor.
 */
export function cuadroPlanning(
  datos: PLDetail, escenarios: Scenario[], opciones: OpcionesPlanning,
): Cuadro {
  const { ambito, compacto = false } = opciones;
  const versiones = datos.versiones ?? [];
  const nombre = nombradorDeVersiones(versiones, escenarios);
  const mv = Math.min(opciones.mesesDe ?? 0, Math.max(0, versiones.length - 1));

  // ⚠️ El arreglo EMITIDO, aparte: los ordinales de `suma_de` se cuentan sobre
  // él. El modo compacto saca filas, así que un índice contado sobre `datos`
  // apunta a otra en cuanto cambian los datos — y el exportador descarta la
  // fórmula que no cuadra sin decir nada.
  const emitidas = (datos.filas ?? []).filter(f =>
    f.tipo !== "esp"
    && (!compacto || f.tipo !== "det"
        // ⚠️ El operando de una resta de la cascada NO se esconde por estar en
        // cero: sin la fila, `resultadosDelPL` no lo encuentra y el resultado
        // —NET PROFIT, el primero— baja como número pegado. Medido.
        || OPERANDOS_DE_LA_CASCADA.has(f.rotulo)
        || (f.series ?? []).some(s => s && suma(s, DOCE) !== 0)));

  const par = parPorDefecto(versiones.length, opciones.par);

  const filas: FilaPlanning[] = emitidas.map(f => {
    // ⚠️ Los encabezados de sección van SIN números, no en cero: un cero ahí se
    // leería como «esta sección no tuvo movimiento».
    if (f.tipo === "sec") return { label: f.rotulo, es_seccion: true, meses: null };
    return {
      label: f.rotulo,
      es_total: f.tipo === "tot" || f.tipo === "sub",
      meses: vi => mesesDe(f, vi),
      anios: versiones.map((_v, vi) => anioDe(f, vi)),
    };
  });

  // ⚠️ Los subtotales suman el detalle que tienen arriba y los cinco resultados
  // de la cascada lo RESTAN. Es la MISMA tabla que usa el P&L del cierre
  // (`componentesDelPL` / `resultadosDelPL`): dos copias se separan en el primer
  // renglón que alguien agregue de un lado.
  componentesDelPL(emitidas).forEach((comp, i) => {
    if (comp) filas[i].suma_de = comp;
  });
  resultadosDelPL(emitidas).forEach((comb, i) => {
    if (comb) filas[i].combina_filas = comb;
  });

  return armarCuadro({
    titulo: `Planning Report ${datos.year} · ${rotuloAmbito(ambito)} · doce meses y año`,
    subtitulo: `Los doce meses son de ${nombre(mv)}; el año, de todas. Su `
      + `columna Full Year es la suma de sus meses.`,
    hoja: `Planning ${datos.year} ${rotuloAmbito(ambito)}${mv ? ` m${mv}` : ""}`,
    mesesDe: mv, extras: opciones.extras,
  }, versiones.length, nombre, par, filas);
}

/* ═════════════════ 2 · Las cinco aperturas por naturaleza ════════════════ */

/**
 * Las cinco aperturas del gasto y del ingreso, con el eje que usa cada una.
 *
 * ⚠️ El eje no es un detalle de presentación. El ingreso se abre por LÍNEA
 * porque un presupuesto de ingresos no tiene departamento; el gasto de propiedad
 * por CUENTA porque ahí todo cae en un solo departamento y abrirlo por depto
 * daría una fila. Es la misma regla del endpoint, y cambiarla de un lado deja la
 * pantalla leyendo claves que el servidor no indexó así.
 */
export const APERTURAS = [
  { clase: "revenue", rotulo: "Ingreso", eje: "por línea de ingreso" },
  { clase: "payroll", rotulo: "Planilla", eje: "por departamento" },
  { clase: "cost", rotulo: "Costo de ventas", eje: "por departamento" },
  { clase: "opex", rotulo: "Gastos operativos", eje: "por departamento" },
  { clase: "property", rotulo: "Gastos de propiedad", eje: "por cuenta" },
] as const;

export type ClaseApertura = (typeof APERTURAS)[number]["clase"];

/** ¿Este checkbook tiene algo debajo de la cuenta?
 *
 *  ⚠️ El costo de ventas y el ingreso no lo tienen, así que su hoja «con
 *  detalle» saldría idéntica a la normal. Dos hojas iguales con nombres
 *  distintos en un paquete de revisión hacen dudar de las dos. */
export const seAbre = (det: DetalleCelda) =>
  (det.filas ?? []).some(f => (f.subs ?? []).length > 0);

/**
 * Una apertura: una fila por departamento (o línea, o cuenta) y el total abajo.
 *
 * `gastos` viene de `/gasto-por-clase/?detalle=true`, que ya manda los doce meses
 * de cada clave por versión.
 *
 * ⚠️ **El TOTAL suma las filas que se ven.** En modo compacto se esconden las
 * claves que están en cero en TODAS las versiones: esconderlas no mueve la suma,
 * así que la fórmula sigue cuadrando. Esconder una fila con número la rompería —
 * y el exportador se comería la fórmula sin avisar.
 */
export function cuadroApertura(
  clase: ClaseApertura, gastos: GastoEscenario[], deptos: Record<string, string>,
  escenarios: Scenario[], opciones: OpcionesPlanning,
): Cuadro {
  const { compacto = false } = opciones;
  const nombre = nombradorDeVersiones(gastos, escenarios);
  const par = parPorDefecto(gastos.length, opciones.par);
  const mv = Math.min(opciones.mesesDe ?? 0, Math.max(0, gastos.length - 1));
  const meta = APERTURAS.find(a => a.clase === clase)!;

  const serie = (vi: number, k: string): number[] =>
    gastos[vi]?.detalle?.[clase]?.[k] ?? [];
  const anio = (vi: number, k: string) => suma(serie(vi, k), DOCE);

  // El nombre de una cuenta 8xxx puede venir en cualquiera de las versiones: la
  // que no tuvo movimiento en esa cuenta no la nombra.
  const nombreCuenta = (k: string) => {
    for (const g of gastos) { const n = g.nombres_cuenta?.[k]; if (n) return n; }
    return "";
  };
  const rotulo = (k: string) => {
    const n = clase === "property" ? nombreCuenta(k) : deptos[k];
    return n ? `${k} · ${n}` : k;
  };

  const claves = Array.from(new Set(
    gastos.flatMap(g => Object.keys(g.detalle?.[clase] ?? {}))))
    .filter(k => !compacto
                 || gastos.some((_g, vi) => Math.abs(anio(vi, k)) >= CENTAVO))
    // De mayor a menor por lo que pesa en la versión principal: lo que mueve la
    // aguja arriba, que es como se lee un presupuesto.
    .sort((a, b) => Math.abs(anio(0, b)) - Math.abs(anio(0, a)) || a.localeCompare(b));

  const filas: FilaPlanning[] = claves.map(k => ({
    label: rotulo(k),
    meses: vi => DOCE.map(i => serie(vi, k)[i] ?? 0),
    anios: gastos.map((_g, vi) => anio(vi, k)),
  }));
  filas.push({
    label: `TOTAL ${meta.rotulo.toUpperCase()}`,
    es_total: true,
    suma_de: claves.map((_k, i) => i),
    meses: vi => DOCE.map(i => claves.reduce((t, k) => t + (serie(vi, k)[i] ?? 0), 0)),
    anios: gastos.map((_g, vi) => claves.reduce((t, k) => t + anio(vi, k), 0)),
  });

  const anio0 = gastos[0]?.year ?? "";
  return armarCuadro({
    titulo: `Planning ${anio0} · ${meta.rotulo} · ${meta.eje}`
            + deQuien(nombre, mv),
    subtitulo: `Los doce meses son de ${nombre(mv)}; el año, de todas. El total `
      + `es la suma de las filas que se ven.`,
    hoja: `Apertura ${meta.rotulo}${mv ? ` m${mv}` : ""}`,
    anchoRotulo: 40, mesesDe: mv, extras: opciones.extras,
  }, gastos.length, nombre, par, filas);
}

/* ═══════════════ 3 · Los checkbooks, cuenta por cuenta ═══════════════════ */

/**
 * El checkbook de una clase: cada cuenta del mayor, agrupada por departamento.
 *
 * `det` viene de `/gasto-por-clase/detalle-de-celda/` con la clave vacía, que es
 * «toda la clase»: trae cada cuenta con su departamento y sus doce meses por
 * versión. Es el mismo detalle que se abre al hacer clic en una celda del
 * cierre — el owner lo pidió también acá: *«desde los reportes, hasta los
 * checkbooks»*.
 *
 * ⚠️ **Cada fila lleva su departamento.** Sumando por cuenta a secas, la 7065 de
 * Habitaciones y la 7065 del Club caían en la misma fila y el resultado no era
 * de nadie (owner, 2026-09-03). Por eso el agrupador es el par (depto, cuenta).
 */
export function cuadroCheckbook(
  det: DetalleCelda, escenarios: Scenario[], opciones: OpcionesPlanning,
): Cuadro {
  const { compacto = false } = opciones;
  const versiones = det.versiones ?? [];
  const nombre = nombradorDeVersiones(versiones, escenarios);
  const par = parPorDefecto(versiones.length, opciones.par);
  const mv = Math.min(opciones.mesesDe ?? 0, Math.max(0, versiones.length - 1));
  const meta = APERTURAS.find(a => a.clase === det.clase);

  const serie = (f: { series: Record<string, number[]> }, vi: number): number[] =>
    f.series?.[versiones[vi]?.scenario_id ?? ""] ?? [];
  const anio = (f: { series: Record<string, number[]> }, vi: number) =>
    suma(serie(f, vi), DOCE);

  const visibles = (det.filas ?? []).filter(f =>
    !compacto || versiones.some((_v, vi) => Math.abs(anio(f, vi)) >= CENTAVO));

  // Por departamento, y dentro de cada uno por lo que pesa.
  const grupos = new Map<string, typeof visibles>();
  for (const f of visibles) {
    const k = `${f.dept_code}\u0000${f.dept_name}`;
    (grupos.get(k) ?? grupos.set(k, []).get(k)!).push(f);
  }

  const filas: FilaPlanning[] = [];
  /** Dónde quedó el subtotal de cada departamento: el TOTAL los suma a ellos,
   *  no a las cuentas, para no contar dos veces. */
  const subtotales: number[] = [];

  for (const [k, cuentas] of Array.from(grupos.entries())
         .sort((a, b) => a[0].localeCompare(b[0]))) {
    const [code, name] = k.split("\u0000");
    cuentas.sort((a, b) => Math.abs(anio(b, mv)) - Math.abs(anio(a, mv))
                           || a.cuenta.localeCompare(b.cuenta));
    filas.push({ label: `${code} · ${name || "(sin departamento)"}`,
                 es_seccion: true, meses: null });
    /** Los ordinales de las filas de CUENTA, que son las que suma el subtotal
     *  del departamento. Con sub-líneas en el medio, `desde + i` ya no alcanza:
     *  apuntaría a una sub-línea y el subtotal saldría mal. */
    const deCuenta: number[] = [];
    for (const f of cuentas) {
      deCuenta.push(filas.length);
      const subs = (f.subs ?? []).filter(x =>
        !compacto || Object.values(x.series).some(
          sr => Math.abs(suma(sr, DOCE)) >= CENTAVO));
      filas.push({
        label: `${f.cuenta} · ${f.nombre || ""}`.trim().replace(/ ·\s*$/, ""),
        nivel: 1,
        // ⚠️ La cuenta suma sus sub-líneas SÓLO si las tiene. Donde la versión
        // lee del mayor no hay sub-líneas, la suma no da la celda y el
        // exportador deja el número del motor — que es lo correcto.
        es_total: subs.length > 0,
        suma_de: subs.length
          ? subs.map((_x, k) => filas.length + 1 + k) : undefined,
        meses: vi => DOCE.map(i => serie(f, vi)[i] ?? 0),
        anios: versiones.map((_v, vi) => anio(f, vi)),
      });
      for (const x of subs) {
        filas.push({
          label: `${x.code ? `${x.code} · ` : ""}${x.nombre || "(sin descripción)"}`,
          nivel: 2,
          // ⚠️ La versión que NO abrió no va en cero: va vacía. Un cero diría
          // «esta sub-línea existe y vale nada», y lo que pasa es otra cosa.
          meses: vi => DOCE.map(i => x.series[versiones[vi]?.scenario_id ?? ""]?.[i] ?? null),
          anios: versiones.map(v => {
            const sr = x.series[v.scenario_id ?? ""];
            return sr ? suma(sr, DOCE) : null;
          }),
        });
      }
    }
    subtotales.push(filas.length);
    filas.push({
      label: `Total ${code}`,
      es_total: true,
      suma_de: deCuenta,
      meses: vi => DOCE.map(i => cuentas.reduce((t, f) => t + (serie(f, vi)[i] ?? 0), 0)),
      anios: versiones.map((_v, vi) => cuentas.reduce((t, f) => t + anio(f, vi), 0)),
    });
  }

  filas.push({
    label: `TOTAL ${(meta?.rotulo ?? det.rotulo ?? det.clase).toUpperCase()}`,
    es_total: true,
    // ⚠️ Suma los SUBTOTALES, no las cuentas: sumar las dos cosas contaría cada
    // peso dos veces, y el exportador tiraría la fórmula por no cuadrar.
    suma_de: subtotales,
    meses: vi => DOCE.map(i => visibles.reduce((t, f) => t + (serie(f, vi)[i] ?? 0), 0)),
    anios: versiones.map((_v, vi) => visibles.reduce((t, f) => t + anio(f, vi), 0)),
  });

  const fuente = versiones[0]?.fuente ? ` · ${versiones[0].fuente}` : "";
  // ⚠️ El nombre de la hoja dice si está abierta o no. Las dos versiones del
  // mismo checkbook conviven en el Budget Package, y dos hojas que se llaman
  // igual obligan al escritor a inventarle un sufijo a una de las dos.
  const abierto = (det.filas ?? []).some(f => (f.subs ?? []).length > 0);
  return armarCuadro({
    titulo: `Planning · Checkbook ${meta?.rotulo ?? det.clase}`
            + (abierto ? " · abierto en sub-líneas" : " · cuenta por cuenta"),
    subtitulo: `Los doce meses son de ${nombre(mv)}${fuente}; el año, de `
      + `todas. Cada fila lleva su departamento.`
      + (abierto ? " Debajo de cada cuenta, de qué está hecha." : ""),
    hoja: `${abierto ? "Detalle" : "Checkbook"} ${meta?.rotulo ?? det.clase}`
          + (mv ? ` m${mv}` : ""),
    anchoRotulo: abierto ? 52 : 46, mesesDe: mv, extras: opciones.extras,
  }, versiones.length, nombre, par, filas);
}

/* ════════════════════ 4 · Las estadísticas del año ═══════════════════════ */

/**
 * Qué estadística es cada fila y cómo se mira.
 *
 * ⚠️ **La unidad decide si el año se puede sumar.** Las noches y el ingreso sí;
 * la ocupación, el ADR y el RevPAR NO —son razones, y el promedio de doce
 * promedios no es el promedio del año—. Por eso el año de esas filas se le pide
 * al servidor con el período completo en vez de sumarse acá.
 *
 * No hace falta apagarles la fórmula a mano: el exportador escribe `=SUM(...)`
 * sólo cuando da lo mismo que el número que vino, así que en una fila de razón
 * se queda con el número. El resguardo está en el escritor, no en la confianza.
 */
export const ESTADISTICAS = [
  { campo: "rooms_available", rotulo: "Noches disponibles", formato: "num" },
  { campo: "rooms_occupied", rotulo: "Noches ocupadas", formato: "num" },
  { campo: "guests", rotulo: "Huéspedes", formato: "num" },
  { campo: "occupancy_pct", rotulo: "Ocupación %", formato: "pct", razon: true },
  { campo: "rooms_revenue", rotulo: "Ingreso de habitaciones", formato: "usd2" },
  { campo: "adr", rotulo: "ADR", formato: "usd2", razon: true },
  { campo: "revpar", rotulo: "RevPAR", formato: "usd2", razon: true },
  { campo: "revpar_bruto", rotulo: "RevPAR (ingreso total)", formato: "usd2", razon: true },
  { campo: "club_pagando", rotulo: "Club · socios pagando", formato: "num1", razon: true },
  { campo: "club_revenue", rotulo: "Club · ingreso", formato: "usd2" },
  { campo: "club_cuota_promedio", rotulo: "Club · cuota promedio", formato: "usd2", razon: true },
] as const;

export interface EstadisticasPlanning {
  /** Los doce meses de CADA versión: `mesesPorVersion[vi][mes]`.
   *
   * ⚠️ Uno por versión y no uno solo. Es el único de los siete cuadros cuyos
   * meses no vienen en la misma respuesta que el año —se piden mes por mes—,
   * así que es el único que podía quedarse mostrando una sola versión mientras
   * los otros seis abrían tres. */
  mesesPorVersion: (EstadisticasCierre | null)[][];
  /** El año completo de cada versión, pedido con el período entero. */
  anios: (EstadisticasCierre | null)[];
  versiones: VersionPlanning[];
}

/**
 * El cuadro de estadísticas. A diferencia de los otros tres, **el año no se suma
 * acá**: se le pide al servidor con `desde=1&hasta=12`, porque la ocupación, el
 * ADR y el promedio de socios del año no son la suma de los doce meses.
 *
 * Owner, 2026-09-02: *«cuando presentes un YTD socios pagando, quiero que me des
 * un promedio de los meses y no que sume»*. Ese promedio lo calcula el servidor
 * sobre los meses CON socios; rehacerlo acá sería una segunda definición.
 */
export function cuadroEstadisticas(
  datos: EstadisticasPlanning, escenarios: Scenario[], opciones: OpcionesPlanning,
): Cuadro {
  const { compacto = false } = opciones;
  const nombre = nombradorDeVersiones(datos.versiones, escenarios);
  const par = parPorDefecto(datos.versiones.length, opciones.par);

  const val = (e: EstadisticasCierre | null, campo: string): number | null => {
    const v = e ? (e as unknown as Record<string, number | null>)[campo] : null;
    return v === null || v === undefined ? null : Number(v);
  };

  const filas: FilaPlanning[] = ESTADISTICAS
    // El Club no existe en todas las propiedades, y una fila de guiones no dice
    // nada: `null` es «esta propiedad no tiene Club», distinto de cero socios.
    .filter(s => !compacto || datos.anios.some(a => val(a, s.campo) !== null))
    .map(s => ({
      label: s.rotulo,
      formato: s.formato as FormatoCol,
      meses: vi => (datos.mesesPorVersion[vi] ?? []).map(m => val(m, s.campo)),
      anios: datos.anios.map(a => val(a, s.campo)),
    }));

  const anio0 = datos.anios[0]?.year
    ?? datos.mesesPorVersion.flat().find(Boolean)?.year ?? "";
  return armarCuadro({
    titulo: `Planning ${anio0} · Estadísticas · doce meses y año`,
    subtitulo: `${nombre(0)} — los doce meses son de esta versión; el año, de `
      + `todas. ⚠️ La ocupación, el ADR, el RevPAR y los socios del año NO son `
      + `la suma de los meses: se piden con el período completo.`,
    hoja: `Estadísticas`,
    anchoRotulo: 30, mesesDe: opciones.mesesDe ?? 0, extras: opciones.extras,
  }, datos.versiones.length, nombre, par, filas);
}

/* ═════════════ 5 · La plantilla: posiciones, salario y FTE ═══════════════ */

/** Qué se mira de cada posición. Son dos cifras distintas y no se mezclan. */
export const METRICAS_POSICION = [
  { id: "fte", rotulo: "FTE", formato: "num1" as FormatoCol,
    ayuda: "0.00 a 1.00 por mes · el año es la suma, como en el Reporte FTE" },
  { id: "sw", rotulo: "Sueldo USD", formato: "usd2" as FormatoCol,
    ayuda: "salario × FTE ÷ TC del mes, calculado por el motor (cuenta 6000)" },
] as const;

export type MetricaPosicion = (typeof METRICAS_POSICION)[number]["id"];

/** El salario contratado, con su moneda, para el rótulo de la fila. */
const salarioEnRotulo = (monto: number, moneda: string) => {
  if (!monto) return "";
  const simbolo = moneda === "USD" ? "$" : moneda === "CRC" ? "₡" : "";
  return ` · ${simbolo}${monto.toLocaleString("en-US",
    { maximumFractionDigits: 0 })}${simbolo ? "" : ` ${moneda}`}`;
};

/**
 * La plantilla completa: cada posición con su salario y sus doce FTE.
 *
 * Owner, 2026-10-01: *«quisiera también bajar las posiciones por departamento
 * con salario y FTE»* · *«este FTE report también en el tab»*.
 *
 * Es el Reporte FTE que ya está en Planning —departamento, posición, empleado,
 * doce meses y total— pero comparando versiones, que es lo que no se podía
 * hacer ahí.
 *
 * ⚠️ **El salario va en el rótulo y la métrica en las celdas.** El salario
 * contratado está en colones o en dólares según la posición: ponerlo en una
 * columna de números haría una suma de dos monedas, que no es ninguna cifra.
 * Lo que sí se suma —y cuadra contra la 6000 del P&L— es el sueldo del mes en
 * dólares, que es la otra métrica.
 *
 * ⚠️ **Una posición que no existe en una versión va VACÍA, no en cero.** Un
 * cero diría «esta plaza está presupuestada sin carga»; lo que pasa es que esa
 * versión no la tiene. Se emparejan por departamento + posición + empleado,
 * porque el `id` cambia al clonar un escenario.
 */
export function cuadroPosiciones(
  versiones: PosicionesVersion[], escenarios: Scenario[],
  opciones: OpcionesPlanning & { metrica?: MetricaPosicion },
): Cuadro {
  const { compacto = false, metrica = "fte" } = opciones;
  const nombre = nombradorDeVersiones(versiones, escenarios);
  const par = parPorDefecto(versiones.length, opciones.par);
  const mv = Math.min(opciones.mesesDe ?? 0, Math.max(0, versiones.length - 1));
  const meta = METRICAS_POSICION.find(m => m.id === metrica)!;

  /** ⚠️ Por departamento + posición + empleado, NO por `id`: al clonar un
   *  escenario las posiciones nacen con id nuevo, y emparejar por id dejaría
   *  cada versión en su propia fila — el cuadro entero en diagonal. */
  const llaveDe = (p: { dept_code: string; position_name: string;
                        employee_name: string }) =>
    `${p.dept_code}\u0000${p.position_name}\u0000${p.employee_name}`;

  /** Una plaza agrupada: cuántas son y cuánto suman entre todas.
   *
   *  ⚠️ **Se SUMAN, no se pisa una con otra.** Tres «ROOM ATTENDANT · VACANTE»
   *  en Ama de Llaves son tres plazas con la misma llave, y quedarse con la
   *  última borraba las otras dos. Medido el 2026-10-01 en el Budget Working
   *  2027: la hoja decía $289.813,08 contra los $305.465,16 de la cuenta 6000
   *  del checkbook — 15.652,08 que desaparecían sin que nada fallara, porque un
   *  total más chico se ve igual de bien que uno correcto. */
  interface Plaza {
    n: number;
    muestra: PosicionesVersion["posiciones"][number];
    fte: number[];
    sw: number[];
  }
  const porVersion = versiones.map(v => {
    const m = new Map<string, Plaza>();
    for (const p of v.posiciones ?? []) {
      const k = llaveDe(p);
      const a = m.get(k);
      if (!a) {
        m.set(k, { n: 1, muestra: p, fte: [...(p.fte ?? [])], sw: [...(p.sw ?? [])] });
      } else {
        a.n += 1;
        DOCE.forEach(i => { a.fte[i] = (a.fte[i] ?? 0) + (p.fte?.[i] ?? 0); });
        DOCE.forEach(i => { a.sw[i] = (a.sw[i] ?? 0) + (p.sw?.[i] ?? 0); });
      }
    }
    return m;
  });
  const serie = (vi: number, k: string) => porVersion[vi]?.get(k)?.[metrica] ?? null;
  const anioPos = (vi: number, k: string) => {
    const s = serie(vi, k);
    return s ? suma(s, DOCE) : null;
  };

  const llaves = Array.from(new Set(porVersion.flatMap(m => Array.from(m.keys()))))
    .filter(k => !compacto
                 || versiones.some((_v, vi) => Math.abs(anioPos(vi, k) ?? 0) >= CENTAVO));

  const grupos = new Map<string, string[]>();
  for (const k of llaves) {
    const p = porVersion.find(m => m.has(k))!.get(k)!.muestra;
    const g = `${p.dept_code}\u0000${p.dept_name}`;
    (grupos.get(g) ?? grupos.set(g, []).get(g)!).push(k);
  }

  const filas: FilaPlanning[] = [];
  const subtotales: number[] = [];
  for (const [g, ks] of Array.from(grupos.entries()).sort((a, b) =>
         a[0].localeCompare(b[0]))) {
    const [code, name] = g.split("\u0000");
    ks.sort((a, b) => (anioPos(mv, b) ?? 0) - (anioPos(mv, a) ?? 0) || a.localeCompare(b));
    filas.push({ label: `${code} · ${name || "(sin departamento)"}`,
                 es_seccion: true, meses: null });
    const desde = filas.length;
    for (const k of ks) {
      const z = porVersion.find(m => m.has(k))!.get(k)!;
      const p = z.muestra;
      filas.push({
        // Dos «ROOM ATTENDANT · VACANTE» son dos plazas, no una fila repetida:
        // se juntan con el conteo delante, que es como se lee una planilla.
        label: `${p.position_name || "(sin nombre)"}`
               + `${z.n > 1 ? ` x${z.n}` : ""} · `
               + `${p.employee_name || "VACANTE"}`
               + salarioEnRotulo(p.salary_amount, p.salary_currency),
        nivel: 1,
        formato: meta.formato,
        meses: vi => DOCE.map(i => serie(vi, k)?.[i] ?? null),
        anios: versiones.map((_v, vi) => anioPos(vi, k)),
      });
    }
    subtotales.push(filas.length);
    filas.push({
      label: `Total ${code}`,
      es_total: true, formato: meta.formato,
      suma_de: ks.map((_k, i) => desde + i),
      meses: vi => DOCE.map(i => ks.reduce((t, k) => t + (serie(vi, k)?.[i] ?? 0), 0)),
      anios: versiones.map((_v, vi) =>
        ks.reduce((t, k) => t + (anioPos(vi, k) ?? 0), 0)),
    });
  }
  filas.push({
    label: `TOTAL ${meta.rotulo.toUpperCase()}`,
    es_total: true, formato: meta.formato,
    suma_de: subtotales,
    meses: vi => DOCE.map(i => llaves.reduce((t, k) => t + (serie(vi, k)?.[i] ?? 0), 0)),
    anios: versiones.map((_v, vi) =>
      llaves.reduce((t, k) => t + (anioPos(vi, k) ?? 0), 0)),
  });

  return armarCuadro({
    titulo: `Planning · Plantilla · ${meta.rotulo} por departamento y posición`,
    subtitulo: `Los doce meses son de ${nombre(mv)} — ${meta.ayuda}. El `
      + `salario contratado va al lado del nombre, en su moneda: sumarlo `
      + `mezclaría colones con dólares.`,
    hoja: `Plantilla ${meta.rotulo}${mv ? ` m${mv}` : ""}`,
    anchoRotulo: 52, mesesDe: mv, extras: opciones.extras,
  }, versiones.length, nombre, par, filas);
}

/* ═══════ 6 · El reparto de Cafetería y Lavandería, y con qué se hizo ═════ */

/**
 * Los repartos que este sistema conoce por su nombre. Los que no están acá
 * salen igual, con el código crudo: es mejor mostrarlos sin rótulo bonito que
 * esconder un reparto que movió plata.
 */
export const REPARTOS = [
  { id: "CAFETERIA", rotulo: "Cafetería",
    fuente: "0220 · se reparte entre los departamentos que comen en la propiedad" },
  { id: "LAUNDRY", rotulo: "Lavandería",
    fuente: "0161 · la lencería por kilos y los uniformes por FTE" },
  { id: "ROOMS", rotulo: "Habitaciones",
    fuente: "se reparte por posición" },
  { id: "SALARY", rotulo: "Salarios",
    fuente: "porciones de una plaza repartidas entre varios departamentos" },
] as const;

/** Cómo se lee cada base, y con qué formato.
 *
 *  ⚠️ Ninguna es dinero: son personas, kilos o plazas. Con el formato de dólares
 *  «700,00» al lado de «$6.461,04» invita a leer la base como un monto. */
const BASES: Record<string, { rotulo: string; formato: FormatoCol }> = {
  FTE:      { rotulo: "FTE", formato: "num1" },
  KILOS:    { rotulo: "Kilos", formato: "num1" },
  POSITION: { rotulo: "Posiciones", formato: "num1" },
};

export interface RepartoPlanning {
  versiones: VersionPlanning[];
  /** El resumen del motor, por versión. */
  resumen: (AllocationSummary | null)[];
  deptos?: Record<string, string>;
}

/** Los tipos de reparto que ALGUNA versión tiene, en el orden conocido primero.
 *
 *  ⚠️ Salen de los datos. Una lista fija de dos dejaba fuera los repartos de
 *  Habitaciones y de salarios que CWL sí tiene — y un reparto que no se ve es
 *  plata que se movió sin que el reporte lo diga. */
export function tiposDeReparto(resumen: (AllocationSummary | null)[]): string[] {
  const vistos = new Set<string>();
  for (const r of resumen) {
    for (const [k, v] of Object.entries(r ?? {})) {
      if (k !== "BASES" && v && Object.keys(v).length) vistos.add(k);
    }
  }
  const conocidos = REPARTOS.map(x => x.id as string).filter(x => vistos.has(x));
  return [...conocidos, ...Array.from(vistos).filter(x => !conocidos.includes(x)).sort()];
}

/**
 * Cuánto recibió cada departamento del reparto, y CON QUÉ peso.
 *
 * Owner, 2026-10-01: *«el tab de allocation de laundry y cafetería, con todos
 * los parámetros y distribución, kilos FTE para distribuir»*.
 *
 * Un bloque con lo repartido en dólares y uno por cada BASE que ese reparto usó
 * —el FTE, los kilos, las posiciones—. Con el reparto solo, «Habitaciones
 * $7.023» no se puede discutir; con el peso al lado, sí.
 *
 * ⚠️ **El peso es `basis_value`: el número que el motor USÓ.** Volver a sumar
 * el FTE de la plantilla o los kilos de la configuración daría una segunda
 * definición del mismo reparto — coincidiría casi siempre, y el día que no, el
 * cuadro explicaría un reparto que no ocurrió.
 *
 * ⚠️ **Cada base en su propio bloque.** La lavandería de CWL reparte la
 * lencería por kilos y los uniformes por FTE: en una sola fila serían kilos
 * sumados con personas.
 *
 * ⚠️ **El departamento que reparte entra en NEGATIVO y por eso el total da
 * cero.** Cafetería y Lavandería se vacían contra los que las consumen; que la
 * suma cierre en cero ES la regla, no un reparto vacío.
 */
export function cuadroReparto(
  tipo: string, datos: RepartoPlanning, escenarios: Scenario[],
  opciones: OpcionesPlanning,
): Cuadro {
  const { compacto = false } = opciones;
  const nombre = nombradorDeVersiones(datos.versiones, escenarios);
  const par = parPorDefecto(datos.versiones.length, opciones.par);
  const mv = Math.min(opciones.mesesDe ?? 0,
                      Math.max(0, datos.versiones.length - 1));
  const meta = REPARTOS.find(r => r.id === tipo);
  const rotuloTipo = meta?.rotulo ?? tipo;
  const deptos = datos.deptos ?? {};

  const plata = (vi: number, k: string): number[] | null =>
    (datos.resumen[vi]?.[tipo] as Record<string, number[]> | undefined)?.[k] ?? null;
  const basesDe = (vi: number) =>
    (datos.resumen[vi]?.BASES as
      Record<string, Record<string, Record<string, number[]>>> | undefined)?.[tipo] ?? {};
  const peso = (vi: number, base: string, k: string): number[] | null =>
    basesDe(vi)[base]?.[k] ?? null;
  const total12 = (s: number[] | null) => (s ? suma(s, DOCE) : null);

  const claves = Array.from(new Set(datos.resumen.flatMap(r =>
    Object.keys((r?.[tipo] as Record<string, number[]> | undefined) ?? {}))))
    .filter(k => !compacto
                 || datos.resumen.some((_r, vi) =>
                      Math.abs(total12(plata(vi, k)) ?? 0) >= CENTAVO))
    .sort((a, b) => Math.abs(total12(plata(mv, b)) ?? 0)
                    - Math.abs(total12(plata(mv, a)) ?? 0) || a.localeCompare(b));

  const rotulo = (k: string) => (deptos[k] ? `${k} · ${deptos[k]}` : k);
  const filas: FilaPlanning[] = [];

  // ⚠️ Una hoja en blanco se lee como «esto está roto». Si el escenario no
  // tiene el reparto calculado, la hoja lo dice: es un dato del presupuesto
  // —falta correrlo— y no un hueco del reporte.
  if (!claves.length) {
    return armarCuadro({
      titulo: `Planning · Reparto de ${rotuloTipo} · sin calcular`,
      subtitulo: `${nombre(0)} — este escenario no tiene reparto de `
        + `${rotuloTipo} calculado. Se corre desde Planning → Allocation; hasta `
        + `entonces su gasto queda donde está.`,
      hoja: `Reparto ${rotuloTipo}`,
      anchoRotulo: 40, mesesDe: mv, extras: opciones.extras,
    }, datos.versiones.length, nombre, par, [{
      label: `Sin reparto de ${rotuloTipo} calculado en este escenario`,
      es_seccion: true, meses: null,
    }]);
  }

  // ── Bloque 1: lo repartido, en dólares ────────────────────────────────
  filas.push({ label: `Reparto de ${rotuloTipo} (USD)`, es_seccion: true,
               meses: null });
  const desde = filas.length;
  for (const k of claves) {
    filas.push({
      label: rotulo(k), nivel: 1,
      meses: vi => DOCE.map(i => plata(vi, k)?.[i] ?? null),
      anios: datos.versiones.map((_v, vi) => total12(plata(vi, k))),
    });
  }
  filas.push({
    label: "TOTAL (el reparto tiene que dar cero)", es_total: true,
    suma_de: claves.map((_k, i) => desde + i),
    meses: vi => DOCE.map(i => claves.reduce((t, k) => t + (plata(vi, k)?.[i] ?? 0), 0)),
    anios: datos.versiones.map((_v, vi) =>
      claves.reduce((t, k) => t + (total12(plata(vi, k)) ?? 0), 0)),
  });

  // ── Un bloque por BASE ────────────────────────────────────────────────
  const usadas = Array.from(new Set(
    datos.versiones.flatMap((_v, vi) => Object.keys(basesDe(vi))))).sort();
  for (const base of usadas) {
    const info = BASES[base] ?? { rotulo: base, formato: "num1" as FormatoCol };
    const conPeso = Array.from(new Set(datos.versiones.flatMap((_v, vi) =>
      Object.keys(basesDe(vi)[base] ?? {}))))
      .sort((a, b) => Math.abs(total12(peso(mv, base, b)) ?? 0)
                      - Math.abs(total12(peso(mv, base, a)) ?? 0)
                      || a.localeCompare(b));
    if (!conPeso.length) continue;
    filas.push({ label: `Base del reparto · ${info.rotulo}`, es_seccion: true,
                 meses: null });
    const d2 = filas.length;
    for (const k of conPeso) {
      filas.push({
        label: rotulo(k), nivel: 1, formato: info.formato,
        meses: vi => DOCE.map(i => peso(vi, base, k)?.[i] ?? null),
        anios: datos.versiones.map((_v, vi) => total12(peso(vi, base, k))),
      });
    }
    filas.push({
      label: `TOTAL ${info.rotulo.toUpperCase()}`, es_total: true,
      formato: info.formato,
      suma_de: conPeso.map((_k, i) => d2 + i),
      meses: vi => DOCE.map(i =>
        conPeso.reduce((t, k) => t + (peso(vi, base, k)?.[i] ?? 0), 0)),
      anios: datos.versiones.map((_v, vi) =>
        conPeso.reduce((t, k) => t + (total12(peso(vi, base, k)) ?? 0), 0)),
    });
  }

  return armarCuadro({
    titulo: `Planning · Reparto de ${rotuloTipo}`
            + (meta ? ` · ${meta.fuente}` : ""),
    subtitulo: `Los doce meses son de ${nombre(mv)} — cuánto recibió cada `
      + `departamento y con qué peso se repartió. La fila en NEGATIVO es el `
      + `departamento que reparte: su crédito contra los que consumen, y por `
      + `eso el total da cero. El peso es el que usó el motor, no uno `
      + `recalculado acá.`,
    hoja: `Reparto ${rotuloTipo}`,
    anchoRotulo: 40, mesesDe: mv, extras: opciones.extras,
  }, datos.versiones.length, nombre, par, filas);
}
