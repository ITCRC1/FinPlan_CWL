"use client";
/**
 * El cuadro de cierre del owner: Mes · YTD · Full Year, lado a lado.
 *
 * Owner, 2026-08-27, mostrando su formato: *«ese es un formato que suelo usar,
 * donde pongo el mes que cierro, pongo el acumulado y a la vez el Full Year,
 * con las líneas más importantes»*, y después *«acá tiene que haber al menos 2
 * versiones más —actual, budget, forecast, actual del año pasado— pero
 * escogibles»*.
 *
 * **Por qué los tres cortes a la vez y no el selector que ya existe.** El botón
 * Mes/YTD/Año sirve para mirar UNO. Este cuadro sirve para otra cosa: ver si lo
 * que pasó en el mes ya movió el acumulado y si eso alcanza para cambiar el
 * año. Esa lectura necesita los tres en la misma línea de ojo — saltar entre
 * botones la rompe, que es por lo que el owner los tiene juntos en su Excel.
 *
 * **Las líneas son las suyas**: los diez totales de la cascada más los cuatro
 * por naturaleza del pie. Sin detalle por departamento, a propósito: para eso
 * está la vista Cascada.
 *
 * ⚠️ El bloque de abajo —planilla, opex, costo, propiedad— es un MEMO, no una
 * reconciliación. En el propio Excel del owner suma los cuatro y nada más: no
 * cierra contra la utilidad porque son otro corte del mismo gasto. El cuadre de
 * verdad es el de la vista Cascada, que compara contra el motor.
 */
import type { PLDetail } from "@/lib/api";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** Los totales del cuadro del owner, en su orden. */
const CLAVE = [
  "TOTAL REVENUES",
  "Total Operationg expenses",
  "OPERATING PROFIT",
  "TOTAL OVERHEAD EXPENSES",
  "TOTAL GROSS OPERATING PROFIT",
  "TOTAL NON OP EXPENSES",
  "EBITDA BEFORE CAPITAL",
  "EBITDA AFTER CAPITAL",
  "EARNINGS BEFORE INCOME TAXES",
  "NET PROFIT",
];

const CLASES: [string, string][] = [
  ["payroll", "Total Payroll and Benefits"],
  ["opex", "Total Operating Expenses"],
  ["cost", "Total Cost"],
  ["property", "Total Property Expenses"],
];

const usd = (n: number | null) =>
  n === null || n === undefined ? "—"
    : Math.abs(n) < 0.005 ? "—"
      : (n < 0 ? "(" : "") + "$" + Math.abs(n).toLocaleString("en-US",
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");
const num = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const pctv = (n: number) => (n * 100).toFixed(1) + "%";

const TD: React.CSSProperties = {
  padding: "3px 7px", textAlign: "right", fontSize: 11.5, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = { padding: "3px 9px", fontSize: 12 };
const IZQ: React.CSSProperties = { borderLeft: "2px solid var(--border-medium)" };

export default function Cierre({ datos, mes }: { datos: PLDetail; mes: number }) {
  const vs = datos.versiones;
  const n = vs.length;
  const hayVar = n >= 2;
  const porBloque = n + (hayVar ? 2 : 0);

  const cortes = [
    { id: "mes", rotulo: MESES[mes - 1], idx: [mes - 1] },
    { id: "ytd", rotulo: `YTD ${MESES[mes - 1]}`,
      idx: Array.from({ length: mes }, (_, i) => i) },
    { id: "full", rotulo: "Full Year",
      idx: Array.from({ length: 12 }, (_, i) => i) },
  ];

  const suma = (serie: number[] | null | undefined, idx: number[]) =>
    serie ? idx.reduce((s, i) => s + (serie[i] ?? 0), 0) : null;

  const porRotulo = (r: string) => datos.filas.find(f => f.rotulo === r);

  /** Una fila del cuadro: por cada corte, una celda por versión + Var $ + Var %. */
  const fila = (rotulo: string, series: (number[] | null | undefined)[],
                fuerte = false) => (
    <tr key={rotulo} style={{ background: fuerte ? "var(--bg-subtle)" : undefined }}>
      <td style={{ ...TDL, fontWeight: fuerte ? 700 : 500 }}>{rotulo}</td>
      {cortes.map(c => {
        const vals = series.map(s => suma(s, c.idx));
        const a = vals[0] ?? null;
        const b = hayVar ? (vals[1] ?? null) : null;
        const d = a !== null && b !== null ? a - b : null;
        // Sobre base cero no hay porcentaje: un 0% o un ∞ serían una lectura
        // inventada, y con enero a mayo en cero el caso se da seguido.
        const p = d !== null && b ? d / Math.abs(b) : null;
        const col = (v: number | null) =>
          v !== null && v < 0 ? "var(--negative)" : undefined;
        return (
          <_Grupo key={c.id}>
            {vals.map((v, k) => (
              <td key={k} className="mono" style={{ ...TD,
                ...(k === 0 ? IZQ : {}),
                fontWeight: fuerte && k === 0 ? 700 : 400,
                color: col(v ?? null) ?? (k ? "var(--text-secondary)" : undefined),
              }}>{usd(v ?? null)}</td>
            ))}
            {hayVar && (
              <>
                <td className="mono" style={{ ...TD, fontWeight: fuerte ? 700 : 400,
                  color: col(d) }}>{usd(d)}</td>
                <td className="mono" style={{ ...TD, color: col(d) }}>
                  {p === null ? "—" : (p * 100).toFixed(1) + "%"}
                </td>
              </>
            )}
          </_Grupo>
        );
      })}
    </tr>
  );

  const sum = (idx: number[], s: number[]) =>
    idx.reduce((t, i) => t + (s[i] ?? 0), 0);

  /** Las estadísticas: razones que se rederivan, nunca se suman. */
  const stat = (etiqueta: string,
                f: (idx: number[], k: PLDetail["versiones"][number]["kpis"]) => number,
                fmt: (x: number) => string) => (
    <tr key={etiqueta}>
      <td style={{ ...TDL, fontWeight: 500 }}>{etiqueta}</td>
      {cortes.map(c => (
        <_Grupo key={c.id}>
          {vs.map((v, k) => (
            <td key={k} className="mono" style={{ ...TD, ...(k === 0 ? IZQ : {}),
              fontWeight: k === 0 ? 600 : 400,
              color: k ? "var(--text-secondary)" : undefined,
            }}>{fmt(f(c.idx, v.kpis))}</td>
          ))}
          {hayVar && <><td /><td /></>}
        </_Grupo>
      ))}
    </tr>
  );

  const totalClases = (i: number) =>
    CLASES.map(([k]) => datos.clases[i]?.[k] ?? Array(12).fill(0))
      .reduce((s, x) => s.map((v, j) => v + (x[j] ?? 0)), Array(12).fill(0));

  return (
    <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
      <table className="fin-table" style={{ minWidth: 320 + cortes.length * porBloque * 105 }}>
        <thead>
          <tr>
            <th style={{ ...TDL, textAlign: "left" }} rowSpan={2}>ACCOUNT DESCRIPTION</th>
            {cortes.map(c => (
              <th key={c.id} colSpan={porBloque}
                  style={{ ...TD, ...IZQ, textAlign: "center", fontWeight: 800 }}>
                {c.rotulo}
              </th>
            ))}
          </tr>
          <tr>
            {cortes.map(c => (
              <_Grupo key={c.id}>
                {vs.map((v, k) => (
                  <th key={k} style={{ ...TD, ...(k === 0 ? IZQ : {}), fontSize: 10.5,
                    fontWeight: 700, color: "var(--text-secondary)" }}>
                    {v.escenario}
                  </th>
                ))}
                {hayVar && (
                  <>
                    <th style={{ ...TD, fontSize: 10.5, fontWeight: 700,
                      color: "var(--text-secondary)" }}>Var $</th>
                    <th style={{ ...TD, fontSize: 10.5, fontWeight: 700,
                      color: "var(--text-secondary)" }}>Var %</th>
                  </>
                )}
              </_Grupo>
            ))}
          </tr>
        </thead>
        <tbody>
          {stat("Total available Rooms", (i, k) => sum(i, k.rooms_available), num)}
          {stat("Total Rooms Occupied", (i, k) => sum(i, k.rooms_occupied), num)}
          {stat("Total Guests", (i, k) => sum(i, k.guests), num)}
          {stat("% Occupancy", (i, k) => {
            const a = sum(i, k.rooms_available);
            return a ? sum(i, k.rooms_occupied) / a : 0;
          }, pctv)}
          {stat("Average Daily Room Only", (i, k) => {
            const o = sum(i, k.rooms_occupied);
            return o ? sum(i, k.rooms_revenue) / o : 0;
          }, x => usd(x))}
          {stat("Total RevPAR", (i, k) => {
            const a = sum(i, k.rooms_available);
            return a ? sum(i, k.rooms_revenue) / a : 0;
          }, x => usd(x))}

          <tr><td colSpan={1 + cortes.length * porBloque} style={{ height: 9 }} /></tr>

          {CLAVE.map(r => {
            const f = porRotulo(r);
            return f ? fila(r, f.series, true) : null;
          })}

          <tr><td colSpan={1 + cortes.length * porBloque} style={{ height: 9 }} /></tr>

          {CLASES.map(([k, r]) => fila(r, datos.clases.map(c => c[k])))}
          {fila("Total Operating and Property Expenses",
                datos.clases.map((_c, i) => totalClases(i)), true)}
        </tbody>
      </table>
    </div>
  );
}

/** Agrupa las celdas de un bloque sin meter un elemento en la tabla. */
function _Grupo({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
