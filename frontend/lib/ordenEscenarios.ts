import type { Scenario } from "@/lib/api";

/**
 * El orden en que el owner quiere ver los escenarios: el año que se está
 * presupuestando va primero y dentro de él manda el Budget Working, que es la
 * versión base de la que todo se deriva. Los años ya cerrados quedan al final,
 * del más reciente al más viejo. Una versión nueva cae sola en su año, sin
 * tener que tocar nada acá.
 *
 * Vive en un solo lugar a propósito: la pantalla de Tipo de Cambio ya lo tenía
 * y la de Salary Allocation ordenaba por año descendente, así que arrancaba en
 * el Budget Working 2035 —un año vacío, abierto para planeación larga— y la
 * pantalla salía sin nada. Dos pantallas con el mismo selector no pueden
 * discrepar sobre cuál es "el escenario de trabajo".
 */
export function ordenarEscenarios(todas: Scenario[]): Scenario[] {
  const enCurso = todas
    .filter(s => s.type === "BUDGET" && s.version.toLowerCase() === "working" && !s.is_locked)
    .map(s => s.year);
  const base = enCurso.length ? Math.min(...enCurso)
    : Math.min(...todas.map(s => s.year));

  const rango = (s: Scenario) => [
    s.year >= base ? 0 : 1,                          // futuro/en curso antes que pasado
    s.year >= base ? s.year : -s.year,               // futuro ascendente, pasado descendente
    s.version.toLowerCase() === "working" ? 0 : 1,   // Working primero en su año
    s.type === "BUDGET" ? 0 : s.type === "FORECAST" ? 1 : 2,
  ];

  return [...todas].sort((a, b) => {
    const [ra, rb] = [rango(a), rango(b)];
    for (let i = 0; i < ra.length; i++) if (ra[i] !== rb[i]) return ra[i] - rb[i];
    const [ca, cb] = [a.created_at ?? "", b.created_at ?? ""];
    return ca !== cb ? ca.localeCompare(cb) : a.version.localeCompare(b.version);
  });
}

// `escenarioDeArranque` vivia aca: era una TERCERA regla de «con cual abrir»
// —el primero de este orden—, en paralelo a `escenarioInicial.ts` y a lo que
// cada pantalla hacia a mano. Tres reglas para la misma pregunta terminan
// divergiendo sin que nada falle: cada pantalla abre en un escenario real, solo
// que en uno distinto. Se borro; la unica regla vive en `escenarioPreferido.ts`.
//
// Este modulo se queda con lo que si es suyo: el ORDEN de la lista, que es otra
// cosa. Que 2035 aparezca arriba del desplegable esta bien mientras no sea el
// elegido.
