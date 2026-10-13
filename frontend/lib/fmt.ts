// Formato numérico consistente para los reportes de Ingresos.
//  - montos  → signo $ + 2 decimales            ($1,234.56)
//  - %       → 1 decimal por defecto             (39.8%)
//  - enteros → sin decimales (pax, rooms, etc.)  (7,854)
// El 0 / vacío se muestra como "—" para tablas limpias.

function toNum(v: number | string | null | undefined): number {
  if (typeof v === "number") return v;
  if (v == null) return NaN;
  return parseFloat(String(v).replace(/[, $%]/g, ""));
}

/** Monto en USD: "$1,234.56". 0/vacío → "—". */
export function fmtUsd(v: number | string | null | undefined): string {
  const n = toNum(v);
  if (!n || isNaN(n)) return "—";
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Porcentaje a partir de una FRACCIÓN (0.398 → "39.8%"). 0/vacío → "—". */
export function fmtPct(frac: number | string | null | undefined, decimals = 1): string {
  const n = toNum(frac);
  if (!n || isNaN(n)) return "—";
  return (n * 100).toLocaleString("en-US", {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  }) + "%";
}

/** Entero con separador de miles (pax, rooms occupied/available). 0/vacío → "—". */
export function fmtInt(v: number | string | null | undefined): string {
  const n = toNum(v);
  if (!n || isNaN(n)) return "—";
  return Math.round(n).toLocaleString("en-US");
}

/** Valor para INPUTS editables de dinero: 2 decimales, sin separador de miles
 *  (para que sea editable/parseable). "408249.0000" → "408249.00". */
export function money2(v: number | string | null | undefined): string {
  const n = toNum(v);
  return isNaN(n) ? "0.00" : n.toFixed(2);
}

/** Valor para INPUTS editables de cantidades enteras (units, pax, rooms). "30.0000" → "30". */
export function int0(v: number | string | null | undefined): string {
  const n = toNum(v);
  return isNaN(n) ? "0" : String(Math.round(n));
}

/** Número con N decimales y separador de miles, sin signo (factores, tarifas sueltas). */
export function fmtNum(v: number | string | null | undefined, decimals = 2): string {
  const n = toNum(v);
  if (!n || isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
}

/**
 * Una fracción a su porcentaje, SIN la cola del punto flotante.
 *
 * Owner, 2026-10-13, sobre la grilla de canales: *«corrige esto»*, con las
 * celdas editadas mostrando `55.0000` y desbordando la casilla mientras las
 * demás decían `60` limpio.
 *
 * No era el guardado: era `fraccion * 100` en JavaScript. Las que se ven mal
 * son exactamente las que no tienen representación binaria exacta —y eso
 * explica celda por celda lo que él circuló:
 *
 *     0.55 * 100 = 55.00000000000001     0.28 * 100 = 28.000000000000004
 *     0.07 * 100 =  7.000000000000001    0.60 * 100 = 60            (limpio)
 *     0.26 * 100 = 26            (limpio)   0.05 * 100 = 5          (limpio)
 *
 * Se redondea a 4 decimales del PORCENTAJE y no a menos: la fracción se guarda
 * como `Numeric(8, 6)`, así que cuatro es exactamente lo que cabe. Con menos se
 * perdería una comisión real como 26,8300%; con más vuelve la cola.
 *
 * ⚠️ Devuelve un NÚMERO, no texto: estos valores siguen a una casilla de
 * entrada y a sumas. Formatear acá obligaría a cada pantalla a desformatear.
 */
export function pctDeFraccion(v: number | string | null | undefined): number {
  const n = typeof v === "number" ? v : parseFloat(String(v ?? 0));
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 1e6) / 1e4;
}
