"use client";
/**
 * Con qué escenario abre cada pantalla, y que no se mueva de ahí.
 *
 * **El problema (owner, 2026-08-14).** «Lo dejo en Working 2027 y aparece en
 * Working 2035.» Cada pantalla traía su propia versión de
 * `sort((a, b) => b.year - a.year)[0]` — «el año más nuevo»— copiada a mano en
 * cuarenta archivos. El día que se crearon los Working 2028 a 2035, el más nuevo
 * pasó a ser 2035 y todos los reportes se fueron ahí. Nada fallaba: cada
 * pantalla mostraba un presupuesto real, solo que el equivocado.
 *
 * Y ninguna recordaba la elección: cada visita volvía a empezar.
 *
 * **Dos cosas distintas, y las dos hacen falta:**
 *
 * 1. `elegir()` — con cuál ABRE la primera vez, según la regla del owner.
 * 2. `useEscenarioRecordado()` — que después NO se mueva: se guarda lo último
 *    que se eligió, por pantalla.
 *
 * Se recuerda **por pantalla** y no en una sola llave global a propósito: un
 * reporte de Actual 2024 y uno de Budget 2027 son vistas distintas, y compartir
 * la selección haría que abrir uno le cambiara el escenario al otro. El
 * escenario compartido de Planning (`planningScenario`) sigue existiendo para lo
 * que sí es una sola cosa que se está editando.
 */
import { useCallback, useEffect, useState } from "react";

import { useContexto, useFijarContexto } from "@/lib/contexto";

/** Lo mínimo que este módulo necesita saber de un escenario. */
export interface EscenarioMin {
  id: string;
  type: string;     // 'ACTUAL' | 'BUDGET' | 'FORECAST'
  year: number;
  version: string;
  /**
   * El forecast «Current»: el vivo, el que la base marca como vigente y al que
   * apuntan las cargas. Puede no venir según el endpoint, por eso es opcional.
   */
  is_current_forecast?: boolean;
}

/** Los papeles que una pantalla puede necesitar. */
export type Rol = "budget" | "forecast" | "actual" | "actualAnterior";

/**
 * La regla del owner (2026-08-14): «quiero que la base sea Budget Working 2027,
 * Forecast Working 2026, Actual 2025, Actual 2024».
 *
 * ⚠️ **Estos años se cambian ACÁ y en ningún otro lado.** Están escritos y no
 * derivados del reloj a propósito: el corte de un ciclo de planificación lo
 * decide el owner, no la fecha del sistema — el mismo criterio que ya rige el
 * rolling forecast, que avanza por dato y no por calendario.
 *
 * Si el escenario nombrado no existe, se cae por la cadena de `elegir()` en vez
 * de quedar en blanco.
 */
export const PREFERENCIA: Record<Rol, { type: string; year: number; version?: string }> = {
  budget:         { type: "BUDGET",   year: 2027, version: "Working" },
  forecast:       { type: "FORECAST", year: 2026, version: "Working" },
  // 2026-08-19, owner: «quiero que esté siempre Budget 2027, Forecast 2026,
  // Actual 2025, Actual 2024». Los dos ACTUAL RETROCEDEN un año respecto del
  // 17-ago, y no es un cambio de opinión al azar: el Actual 2026 está a medio
  // subir (junio no está cargado), así que abría comparando contra un año
  // incompleto — y un año incompleto no se ve incompleto, se ve malo.
  actual:         { type: "ACTUAL",   year: 2025 },
  actualAnterior: { type: "ACTUAL",   year: 2024 },
};

/**
 * Generación de las preferencias guardadas.
 *
 * ⚠️ **Subir este número borra, UNA vez, lo que cada navegador tenga recordado.**
 * Hace falta porque recordar es exactamente lo que hace pegajoso a un valor
 * malo: el owner, 2026-08-17: *«siempre que abro andan por 2034-2035»*. La regla
 * ya decía Working 2027 desde el 14-ago, pero **el id equivocado ya estaba
 * guardado**, y lo guardado le gana al default — para siempre y en silencio.
 *
 * De dónde salió ese id: `GET /scenarios/` ordena por **año descendente**
 * (`scenarios_api.py`), así que `all[0]` —el respaldo de 23 pantallas de
 * Planning— era **Budget Working 2035**. Y como Planning comparte UNA sola
 * llave, alcanzaba con que una pantalla cayera ahí una vez para arrastrar a
 * todas las demás.
 *
 * Subilo solo cuando cambie la regla y haya que despegar lo viejo. No es un
 * «borrá las preferencias» de rutina: lo que el owner elija DESPUÉS tiene que
 * quedarse quieto, que es todo el punto de este módulo.
 */
export const GENERACION = "2026-08-19-actuales-2025-2024";
const LLAVE_GEN = "finplan_esc_generacion";

/**
 * Descarta las preferencias de una generación anterior. Idempotente y barata:
 * corre una vez por navegador y después solo compara dos strings.
 *
 * Se limpian las dos familias porque el valor malo viajaba por las dos: las
 * llaves por pantalla (`finplan_esc_*`) y la compartida de Planning.
 */
export function limpiarSiEsDeOtraGeneracion(): void {
  if (typeof window === "undefined") return;
  try {
    if (localStorage.getItem(LLAVE_GEN) === GENERACION) return;
    for (const k of Object.keys(localStorage)) {
      if (k.startsWith("finplan_esc_") && k !== LLAVE_GEN) localStorage.removeItem(k);
    }
    localStorage.removeItem("finplan_planning_scenario");
    localStorage.setItem(LLAVE_GEN, GENERACION);
  } catch {
    /* ver `recordado`: que no se caiga la pantalla por no poder limpiar */
  }
}

const norm = (v: string | undefined) => (v || "").trim().toLowerCase();

/**
 * El escenario con el que abrir, para un papel dado.
 *
 * La cadena, de más específico a menos:
 *   año + versión exactos → año exacto → versión en el año más CERCANO al
 *   preferido → el del tipo más cercano al año preferido → nada.
 *
 * ⚠️ El último escalón usa el año más cercano al preferido y **no el más
 * nuevo**: ordenar por año descendente es justamente lo que mandaba todo a
 * Working 2035.
 */
export function elegir<T extends EscenarioMin>(escenarios: T[], rol: Rol): T | undefined {
  const p = PREFERENCIA[rol];
  const delTipo = escenarios.filter(e => e.type === p.type);
  if (!delTipo.length) return undefined;

  // El forecast «Current» le gana al año escrito: es el que la base marca como
  // vigente y al que apuntan las cargas. Varias pantallas ya lo preferían y al
  // unificar la regla ese atajo se habría perdido — el año en `PREFERENCIA` es
  // el respaldo para cuando nadie marcó ninguno.
  if (rol === "forecast") {
    const vigente = delTipo.find(e => e.is_current_forecast);
    if (vigente) return vigente;
  }

  if (p.version) {
    const exacto = delTipo.find(e => e.year === p.year && norm(e.version) === norm(p.version));
    if (exacto) return exacto;
  }
  const porAno = delTipo.filter(e => e.year === p.year);
  if (porAno.length) {
    return (p.version && porAno.find(e => norm(e.version) === norm(p.version))) || porAno[0];
  }
  const cercano = (lista: T[]) =>
    [...lista].sort((a, b) => Math.abs(a.year - p.year) - Math.abs(b.year - p.year))[0];
  if (p.version) {
    const conVersion = delTipo.filter(e => norm(e.version) === norm(p.version));
    if (conVersion.length) return cercano(conVersion);
  }
  return cercano(delTipo);
}

/**
 * El escenario de un AÑO concreto, para las pantallas cuyo eje está atado a un
 * calendario y no al ciclo de planificación.
 *
 * Caso real: `marketing-insight/daily-occupancy` arma sus semanas con
 * `WEEKS_2026`, fijo. Abrirla con el Actual 2025 —que es lo que manda la regla
 * general— pondría etiquetas de un año sobre datos de otro, y el gráfico se
 * vería perfectamente normal. Mientras el eje sea fijo, el escenario también
 * tiene que serlo.
 */
export function elegirDelAno<T extends EscenarioMin>(
  escenarios: T[], type: string, year: number,
): T | undefined {
  const delTipo = escenarios.filter(e => e.type === type);
  return delTipo.find(e => e.year === year)
    ?? [...delTipo].sort((a, b) => Math.abs(a.year - year) - Math.abs(b.year - year))[0];
}

/**
 * Los dos ACTUAL que el owner pidió, del más reciente al anterior.
 * Sirve para los reportes que comparan dos años cerrados.
 */
export function elegirActuales<T extends EscenarioMin>(escenarios: T[]): T[] {
  return [elegir(escenarios, "actual"), elegir(escenarios, "actualAnterior")]
    .filter((e): e is T => !!e)
    // Un mismo escenario no puede ocupar los dos lugares: si solo hay un ACTUAL,
    // se devuelve uno y no el mismo repetido, que se leería como dos años.
    .filter((e, i, a) => a.findIndex(x => x.id === e.id) === i);
}

const LLAVE = (pantalla: string) => `finplan_esc_${pantalla}`;

/**
 * «El usuario eligió NINGUNO», que no es lo mismo que «todavía no eligió».
 *
 * Varias pantallas tienen columnas opcionales con un «— sin comparación». Sin
 * este centinela, guardar `""` es indistinguible de no haber guardado nada, y
 * al recargar volvía el último escenario real: el usuario apagaba una columna y
 * reaparecía sola. Es el mismo «no se queda quieto» que esto viene a arreglar.
 */
const NINGUNO = "__ninguno__";

/**
 * Lo último que se eligió en esa pantalla.
 * Devuelve `null` si nunca se eligió, y `""` si se eligió «ninguno».
 */
export function recordado(pantalla: string): string | null {
  if (typeof window === "undefined") return null;
  limpiarSiEsDeOtraGeneracion();
  try {
    const v = localStorage.getItem(LLAVE(pantalla));
    if (v === null) return null;
    return v === NINGUNO ? "" : v;
  } catch {
    // localStorage puede fallar (modo privado, cuota). Que no se caiga la
    // pantalla entera por no poder recordar una preferencia.
    return null;
  }
}

export function recordar(pantalla: string, id: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LLAVE(pantalla), id || NINGUNO);
  } catch {
    /* ver `recordado` */
  }
}

/**
 * El escenario de una pantalla: recuerda lo último elegido y, si nunca se
 * eligió, abre con el preferido del owner.
 *
 * ```ts
 * const [escenarios, setEscenarios] = useState<Scenario[]>([]);
 * const [budgetId, setBudgetId] = useEscenarioDe("reports/pl-ytd:budget", escenarios, "budget");
 * ```
 *
 * **Todo va adentro del hook a propósito.** La versión que dejaba a la pantalla
 * elegir el default tenía una carrera: el hook lee `localStorage` en un efecto y
 * la pantalla fijaba el default en otro, así que según cuál corriera primero el
 * default podía pisar lo recordado. Con la elección acá dentro no hay dos
 * efectos compitiendo, y ninguna pantalla puede equivocarse en el orden.
 *
 * - `pantalla` es la llave donde se recuerda. Poné una por selector: una
 *   pantalla con Actual y Budget usa `"...:actual"` y `"...:budget"`, o los dos
 *   selectores se pisarían entre sí.
 * - `escenarios` puede llegar vacío en el primer render; el default se aplica
 *   cuando llegan.
 * - Si el id recordado ya no existe (escenario borrado), cae al preferido en vez
 *   de quedar en un selector en blanco.
 */
export function useEscenarioDe<T extends EscenarioMin>(
  pantalla: string,
  escenarios: T[],
  rol: Rol,
  /**
   * Reemplaza la regla general para esta pantalla. Para las que tienen el eje
   * atado a un calendario fijo — ver `elegirDelAno`. Pasala memoizada o como
   * constante: si cambia de identidad en cada render, el efecto se repite.
   */
  preferido?: (escenarios: T[]) => T | undefined,
  /**
   * Que el `?esc=` de la dirección le GANE a lo recordado, y que elegir otro
   * escenario lo escriba ahí. Es lo que hace que un salto entre pantallas
   * llegue mostrando lo mismo, y que un link se pueda pasar por correo.
   *
   * ⚠️ **Opt-in, y no por prudencia: por corrección.** Hay pantallas con DOS
   * selectores —una columna Actual y otra Budget, con llaves `...:actual` y
   * `...:budget`— y un solo `?esc=` en la URL pondría las dos en el mismo
   * escenario. La comparación quedaría contra sí misma, dando variaciones de
   * cero que se leen como «no cambió nada». Prenderlo en una pantalla de dos
   * selectores es un error; por eso hay que pedirlo.
   */
  desdeUrl?: boolean,
): [string, (id: string) => void] {
  const [id, setId] = useState("");
  const { esc: escUrl } = useContexto();
  const fijar = useFijarContexto();
  // Que ya se leyó `localStorage`. Sin esto, un `""` recordado («ninguno») no se
  // distingue del estado inicial y el default se lo comería.
  const [hidratado, setHidratado] = useState(false);

  useEffect(() => {
    // La dirección primero: es de dónde te mandaron, y le gana a lo que esta
    // pantalla recuerde de la última vez. Solo si el escenario existe — un id
    // de un link viejo apuntando a un escenario borrado cae a la cadena normal
    // en vez de dejar el selector en blanco.
    if (desdeUrl && escUrl && escenarios.some(e => e.id === escUrl)) {
      setId(escUrl);
      setHidratado(true);
      return;
    }
    // Se lee DESPUÉS de montar: `localStorage` no existe en el render del
    // servidor y leerlo antes rompe la hidratación de Next.
    const guardado = recordado(pantalla);
    if (guardado !== null) {
      // Un id recordado que ya no existe (escenario borrado) no sirve: se cae al
      // preferido en vez de dejar el selector en un id fantasma.
      const vive = guardado === "" || !escenarios.length
        || escenarios.some(e => e.id === guardado);
      if (vive) {
        setId(prev => (hidratado ? prev : guardado));
        setHidratado(true);
        return;
      }
    }
    setHidratado(true);
    if (!escenarios.length) return;
    setId(prev => {
      if (prev && escenarios.some(e => e.id === prev)) return prev;
      const elegido = preferido ? preferido(escenarios) : elegir(escenarios, rol);
      return (elegido ?? escenarios[0])?.id ?? "";
    });
  }, [pantalla, escenarios, rol, preferido, hidratado, desdeUrl, escUrl]);

  const cambiar = useCallback((v: string) => {
    setId(v);
    setHidratado(true);
    // Se recuerda TAMBIÉN el vacío: apagar una columna es una elección.
    recordar(pantalla, v);
    // Y se escribe en la dirección, para que la pantalla siga siendo enlazable
    // después de cambiar de escenario. `replace`: cambiar el selector no es
    // navegar, y con `push` el botón «atrás» retrocedería selector por selector.
    if (desdeUrl) fijar({ esc: v || undefined });
  }, [pantalla, desdeUrl, fijar]);

  return [id, cambiar];
}
