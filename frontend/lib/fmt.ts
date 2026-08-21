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
