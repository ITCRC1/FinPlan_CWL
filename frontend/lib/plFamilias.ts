/**
 * Las FAMILIAS de líneas del P&L: qué códigos suman «Rooms» y cuáles «A&B».
 *
 * **Por qué existe (2026-08-14).** El ingreso de habitaciones y el de A&B se
 * partieron en varias líneas. Media docena de pantallas seguían leyendo
 * `REV_ROOMS` y `REV_FB` sueltos, y todas mostraban de menos:
 *
 *   · Monthly Summary y P&L Statement — subestimaban A&B y Rooms
 *   · reports/summary — mismo mix, mismo error
 *   · reports/junta — la mezcla que ve la junta
 *   · planning/big-picture — el residual dejó de ser residual
 *
 * ⚠️ **Y el error no se veía**, que es lo que lo hace peligroso: casi todas
 * calculan «Otros» como el RESIDUO (Total − Rooms − A&B), así que lo que
 * faltaba caía ahí en silencio y el cuadro seguía cuadrando contra el total.
 *
 * Cada pantalla con su propia lista se desincroniza sola. Acá hay una.
 *
 * **Sumar la familia es correcto en los DOS caminos del motor**: donde el split
 * existe, la línea base es solo su parte; donde no existe —el resumen importado
 * del Actual, que es más grueso— las otras vienen en cero. No hay doble conteo.
 */

/** Habitaciones: la venta pura (cta 4000) más cancelaciones y no-shows. */
export const FAM_ROOMS = ["REV_ROOMS", "REV_ROOMS_OTHER"] as const;

/** Alimentos y bebidas: comida, bebida y misceláneos. */
export const FAM_FB = ["REV_FB", "REV_FB_BEV", "REV_FB_MISC"] as const;

/** A&B incluyendo el Private Bar, para los cuadros que lo consolidan.
 *
 *  ⚠️ La línea `REV_PRIVATE_BAR` **no es un bar**: sus cuentas se llaman
 *  «Ingreso Tienda» y sus costos son ropa y zapatos. Se incluye acá porque los
 *  cuadros que la usaban ya lo hacían; no porque sea A&B de verdad. */
export const FAM_FB_CON_BAR = [...FAM_FB, "REV_PRIVATE_BAR"] as const;

/** Suma una familia sobre un buscador de líneas. */
export function familia(
  codigos: readonly string[],
  valor: (code: string) => number,
): number {
  return codigos.reduce((s, c) => s + (valor(c) || 0), 0);
}
