/**
 * El armador del Budget Package, compartido.
 *
 * Owner, 2026-11-06: *«automatiza este [libro] de una, así como está… cada
 * tab»*. El libro se refresca desde Excel con «Actualizar todo», y para eso lo
 * tiene que poder armar un SERVIDOR (`app/api/paquete/route.ts`), no sólo el
 * botón de la pantalla.
 *
 * ⚠️ **Es el MISMO armador que el botón, no una copia.** Antes vivía dentro de
 * `app/planning/report/page.tsx`. Un paquete que juntara las hojas por su
 * cuenta en el servidor sería una segunda definición de cada hoja — y el Excel
 * que se refresca diría cosas distintas del que se baja con el botón, sin que
 * nada falle. La pantalla y la ruta llaman a `hojasDe` y `armarPaquete` de acá.
 *
 * La pantalla le pasa lo que ya tiene en memoria (`cache`) para no volver a
 * pedirlo; la ruta no le pasa nada y se pide todo.
 */
import {
  getAllocationSummary, getDetalleDeCelda, getEstadisticasCierre,
  getGastoPorClase, getPLDetail, getPosiciones,
  type AllocationSummary, type DetalleCelda, type EstadisticasCierre,
  type GastoEscenario, type PLDetail, type PosicionesVersion, type Scenario,
} from "@/lib/api";
import type { Cuadro } from "@/lib/exportCuadro";
import {
  APERTURAS, cuadroApertura, cuadroCheckbook, cuadroEstadisticas, cuadroPlanning,
  cuadroPosiciones, cuadroReparto, METRICAS_POSICION, seAbre, tiposDeReparto,
} from "@/lib/planningReport";

export const AMBITOS = [
  { id: "consolidado", rotulo: "Consolidado", ayuda: "Hotel + Club Madresal" },
  { id: "hotel", rotulo: "Hotel", ayuda: "Sin el Club Madresal" },
  { id: "club", rotulo: "Club Madresal", ayuda: "Sólo el departamento 260" },
] as const;

export const VISTAS = [
  { id: "pl", rotulo: "P&L", ayuda: "La cascada completa, por ámbito" },
  { id: "aperturas", rotulo: "Aperturas", ayuda: "Por departamento, línea y cuenta" },
  { id: "checkbooks", rotulo: "Checkbooks", ayuda: "Cuenta por cuenta del mayor" },
  { id: "detalle", rotulo: "Checkbooks con detalle",
    ayuda: "Cada cuenta abierta en sus sub-líneas: 800 · Coral, 801 · Fumigación…" },
  { id: "plantilla", rotulo: "Plantilla",
    ayuda: "Posiciones por departamento, con salario y FTE" },
  { id: "reparto", rotulo: "Reparto",
    ayuda: "Cafetería y lavandería: cuánto se repartió y con qué base" },
  { id: "estadisticas", rotulo: "Estadísticas", ayuda: "Noches, ocupación, ADR, Club" },
] as const;

const DOCE = Array.from({ length: 12 }, (_, i) => i + 1);

export interface StatsPaquete {
  mesesPorVersion: (EstadisticasCierre | null)[][];
  anios: (EstadisticasCierre | null)[];
}
export interface RepartoPaquete {
  resumen: (AllocationSummary | null)[];
  deptos: Record<string, string>;
}
export interface GastosPaquete {
  escenarios: GastoEscenario[];
  departamentos: Record<string, string>;
}
export interface OpcionesPaquete {
  compacto: boolean;
  ambito: string;
  mesesDe: number;
  extras: number[];
}

/** Lo que la pantalla ya cargó, para no volver a pedirlo. Todo es opcional. */
export interface CachePaquete {
  pl?: { ambito: string; datos: PLDetail } | null;
  gastos?: GastosPaquete | null;
  libro?: Record<string, DetalleCelda>;
  plantilla?: PosicionesVersion[] | null;
  reparto?: RepartoPaquete | null;
  stats?: StatsPaquete | null;
}

export interface ContextoPaquete {
  principal: string;
  otros: string[];
  escenarios: Scenario[];
  op: OpcionesPaquete;
  cache?: CachePaquete;
}

/** La misma llave con la que se guarda un checkbook: la clase y si está
 *  abierto. Sin el `abrir` en la llave, pedir el detalle devolvía el cuadro
 *  sin abrir que ya estaba en memoria. */
export const llaveLibro = (c: string, abrir: boolean) => `${c}${abrir ? ":abierto" : ""}`;

/** Las versiones que abren sus doce meses a la DERECHA: todas las elegidas
 *  menos la que ya los abre a la izquierda. Owner, 2026-10-05: *«después de
 *  la línea roja … doce meses, y con una columna de espacio, otros doce»*. */
export function extrasDe(ids: string[], mesesDe: number): number[] {
  return ids.map((_id, i) => i).filter(i => i !== mesesDe);
}

/** Las estadísticas: los doce meses de cada versión, uno por llamada, y el año
 *  de cada versión con el período completo.
 *
 *  ⚠️ El año NO se suma acá. La ocupación, el ADR y el promedio de socios del
 *  año no son la suma de los doce meses, y el servidor ya sabe calcularlos
 *  sobre el período: rehacerlo de este lado sería una segunda definición de la
 *  misma cifra. */
export async function cargarStats(ids: string[]): Promise<StatsPaquete> {
  const unoNulo = async (id: string, d: number, h: number) =>
    getEstadisticasCierre(id, d, h).catch(() => null);
  const [mesesPorVersion, anios] = await Promise.all([
    // ⚠️ Los doce meses de CADA versión, no sólo de la elegida: desde que el
    // cuadro abre varias a la derecha, pedir una sola dejaba esas columnas en
    // blanco justo en la hoja donde el owner mira la estacionalidad.
    Promise.all(ids.map(id => Promise.all(DOCE.map(m => unoNulo(id, m, m))))),
    Promise.all(ids.map(id => unoNulo(id, 1, 12))),
  ]);
  return { mesesPorVersion, anios };
}

/** El reparto de las dos: el resumen del motor por versión, más los nombres de
 *  departamento, que viven en el endpoint de gasto. */
export async function cargarReparto(ids: string[]): Promise<RepartoPaquete> {
  const [resumen, deptos] = await Promise.all([
    Promise.all(ids.map(id => getAllocationSummary(id).catch(() => null))),
    getGastoPorClase(ids, false).then(r => r.departamentos ?? {}).catch(() => ({})),
  ]);
  return { resumen, deptos };
}

export function statsACuadro(
  s: StatsPaquete, ids: string[], escenarios: Scenario[],
  op: { ambito: string; compacto: boolean; mesesDe?: number; extras?: number[] },
): Cuadro {
  return cuadroEstadisticas({ ...s, versiones: s.anios.map((a, i) => ({
    scenario_id: ids[i], escenario: a?.escenario })) }, escenarios, op);
}

/** Todas las hojas de una vista. Las usa el botón de la vista, el del paquete
 *  completo y la ruta del Excel en vivo: las tres bajan exactamente lo mismo. */
export async function hojasDe(v: string, ctx: ContextoPaquete): Promise<Cuadro[]> {
  const { principal, otros, escenarios, op } = ctx;
  const cache = ctx.cache ?? {};
  const ids = [principal, ...otros];
  const out: Cuadro[] = [];
  if (v === "pl") {
    for (const a of AMBITOS) {
      const d = cache.pl && cache.pl.ambito === a.id ? cache.pl.datos
        : await getPLDetail(a.id, principal, otros).catch(() => null);
      if (d) out.push(cuadroPlanning(d, escenarios, { ...op, ambito: a.id }));
    }
  } else if (v === "aperturas") {
    let g = cache.gastos;
    if (!g) {
      const r = await getGastoPorClase(ids, true);
      g = { escenarios: r.escenarios, departamentos: r.departamentos ?? {} };
    }
    for (const a of APERTURAS) {
      out.push(cuadroApertura(a.clase, g.escenarios, g.departamentos,
                              escenarios, op));
    }
  } else if (v === "checkbooks" || v === "detalle") {
    const abrir = v === "detalle";
    for (const a of APERTURAS) {
      const d = cache.libro?.[llaveLibro(a.clase, abrir)]
        ?? await getDetalleDeCelda(ids, a.clase, "", 0, abrir).catch(() => null);
      // ⚠️ La clase que no tiene nada debajo de la cuenta NO baja dos veces.
      // Su hoja «con detalle» saldría idéntica a la normal, y dos hojas
      // iguales con nombres distintos hacen dudar de las dos.
      if (d && (!abrir || seAbre(d))) out.push(cuadroCheckbook(d, escenarios, op));
    }
  } else if (v === "plantilla") {
    const ps = cache.plantilla ?? (await getPosiciones(ids)).escenarios;
    // Las DOS métricas: el FTE dice cuánta gente y el sueldo cuánto cuesta.
    // Quien revisa un presupuesto mira las dos, y una sola obliga a volver.
    for (const m of METRICAS_POSICION) {
      out.push(cuadroPosiciones(ps, escenarios, { ...op, metrica: m.id }));
    }
  } else if (v === "reparto") {
    const r = cache.reparto ?? await cargarReparto(ids);
    // ⚠️ Los tipos salen de los DATOS. Con la lista fija de dos, CWL bajaba
    // el paquete sin su reparto de Habitaciones ni el de salarios — plata que
    // se movió y que el libro no mencionaba.
    for (const t of tiposDeReparto(r.resumen)) {
      out.push(cuadroReparto(t,
        { versiones: r.resumen.map((_x, i) => ({ scenario_id: ids[i] })), ...r },
        escenarios, op));
    }
  } else {
    out.push(statsACuadro(cache.stats ?? await cargarStats(ids), ids, escenarios, op));
  }
  return out;
}

/**
 * El BUDGET PACKAGE: las siete vistas en un solo libro.
 *
 * Owner, 2026-10-01: *«esto debe ser un Budget Package para revisión
 * rápida»*. Veintitrés hojas —P&L por ámbito, las cinco aperturas, los cinco
 * checkbooks, los abiertos en sub-líneas, la plantilla en FTE y en sueldo, los
 * repartos y las estadísticas— con el índice adelante.
 *
 * Una vista que falla no se lleva el paquete entero: se avisa con `alFallar` y
 * las demás bajan. Un libro de veintitrés hojas que no baja por una es peor
 * que uno de veintidós que sí.
 */
export async function armarPaquete(
  ctx: ContextoPaquete, alFallar?: (rotulo: string) => void,
): Promise<Cuadro[]> {
  const cuadros: Cuadro[] = [];
  for (const v of VISTAS) {
    try {
      cuadros.push(...await hojasDe(v.id, ctx));
    } catch {
      alFallar?.(v.rotulo);
    }
  }
  return cuadros;
}
