import type { Scenario, PLColumn } from "@/lib/api";
import type { Rol } from "@/lib/escenarioPreferido";

/**
 * Una columna de la presentación.
 *
 * La PRIMERA es la que se está presentando (el "driver", p.ej. Budget 2027
 * Working) y va resaltada; las demás son comparaciones, en el orden que el
 * usuario las eligió. La variación se lee entre la primera y la segunda, que es
 * la comparación principal.
 *
 * El orden de la tabla es el orden de los selectores: lo que elegís arriba es
 * lo que ves abajo. Reordenar por fecha por detrás confunde más de lo que ayuda.
 */
export interface Version {
  id: string;
  label: string;
  col?: PLColumn;
}

/**
 * Los tres puestos de la presentación, en orden: el que se presenta y sus dos
 * comparaciones. Tres columnas de datos más sus dos deltas entran cómodas en
 * pantalla; con cuatro la tabla empezaba a apretarse.
 *
 * El `rol` es lo que cada puesto SIGNIFICA, y de ahí sale con qué escenario
 * abre: el presupuesto que se está armando, el forecast del año en curso y el
 * último ejercicio cerrado. La `llave` es una por puesto —no una sola para la
 * pantalla— porque si no, elegir en un desplegable le cambiaría el escenario a
 * los otros dos.
 */
export const PUESTOS: { llave: string; rol: Rol }[] = [
  { llave: "reports/junta:presenta", rol: "budget" },
  { llave: "reports/junta:comp1",    rol: "forecast" },
  { llave: "reports/junta:comp2",    rol: "actual" },
];

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };

export function scnLabel(s: Scenario): string {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version))
    ? `${t} ${s.year}`
    : `${t} ${s.year} · ${s.version}`;
}

/** Escenarios agrupados para el desplegable: primero lo más reciente y
 *  relevante, no los presupuestos lejanos que casi nunca se presentan. */
export function paraSelector(scenarios: Scenario[]): Scenario[] {
  const ORDEN_TIPO: Record<string, number> = { BUDGET: 0, FORECAST: 1, ACTUAL: 2 };
  return [...scenarios].sort((a, b) => {
    if (a.year !== b.year) return b.year - a.year;                  // más nuevo primero
    return (ORDEN_TIPO[a.type] ?? 9) - (ORDEN_TIPO[b.type] ?? 9);
  });
}

/* La selección inicial vivía acá, con su propia idea de qué año presentar
   (`new Date().getFullYear() + 1`). Ahora la da `useEscenarioDe` desde los
   `PUESTOS` de arriba: una sola regla, escrita en `lib/escenarioPreferido.ts`,
   y de paso cada puesto recuerda lo último que el usuario eligió. */
