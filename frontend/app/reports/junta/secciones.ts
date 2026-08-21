/**
 * Secciones de la Presentación a la Junta.
 *
 * Mapean el PowerPoint que el owner arma cada año (50 diapositivas, 67 imágenes
 * pegadas a mano). No son 50 pantallas: hay ~9 formas distintas, y dos de ellas
 * se repetían slide por slide para cada departamento y cada área de gasto. Acá
 * eso colapsa en UNA sección con selector.
 *
 * Cada sección se puede ver sola (modo pantalla, para la reunión) o encadenada
 * con todas las demás (modo documento, para imprimir a PDF de una sola pasada).
 */

export type SeccionId =
  | "resumen"
  | "volumen"
  | "precio"
  | "ingresos"
  | "departamentos"
  | "planilla"
  | "gastos"
  | "capital"
  | "cashflow"
  | "otb";

export interface Seccion {
  id: SeccionId;
  /** Diapositivas del PPT original que absorbe (para no perder la trazabilidad). */
  slides: string;
}

// ⚠️ Acá NO va texto: el título y la pregunta de cada lámina viven en el
// catálogo (`junta.sec_<id>_titulo` / `_pregunta`). Este archivo es un `.ts` de
// nivel de módulo — no puede llamar al traductor— y además la guarda que
// comprueba que toda clave exista **solo miraba los `.tsx`**, así que estos
// veinte textos eran invisibles para todo el sistema de idiomas.
export const SECCIONES: Seccion[] = [
  {
    id: "resumen",
        slides: "45",
  },
  {
    id: "volumen",
        slides: "6-7, 10-11",
  },
  {
    id: "precio",
        slides: "8-9",
  },
  {
    id: "ingresos",
        slides: "12-14",
  },
  {
    id: "departamentos",
        slides: "18-29",
  },
  {
    id: "planilla",
        slides: "30-31, 33",
  },
  {
    id: "gastos",
        slides: "32, 34-44",
  },
  {
    id: "capital",
        slides: "46-47",
  },
  {
    id: "cashflow",
        slides: "48-49",
  },
  {
    // Aparte del cash flow: no es una proyección del presupuesto sino un hecho
    // del año en curso —lo que ya está vendido— y sale de otra fuente, los
    // cortes semanales de reservas. Mezclarlas en un solo tab obligaba a
    // explicar en la junta por qué una tabla habla del 2027 y la otra del 2026.
    id: "otb",
        slides: "50",
  },
];

/** Las que NO se construyen: son narrativa que el owner escribe cada año, no
 *  datos. Meterlas acá obligaría a mantener un editor de texto. Se quedan en el
 *  PowerPoint o entran como nota al pie de la sección que corresponda. */
export const NO_SON_DATOS = [
  { slide: "2", que: "Contexto macroeconómico" },
  { slide: "15-17", que: "Iniciativas estratégicas" },
];
