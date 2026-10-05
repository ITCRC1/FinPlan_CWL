"use client";
/**
 * Un bloque de «Total Revenue por tipo de habitación»: el cuadro de doce meses
 * con sus filas de estadística al pie.
 *
 * Owner, 2026-10-04: *«necesito poder ver total revenue tarifa rack, y después
 * TOTAL REVENUE POR TIPO HABITACIÓN NET RATE Y TODO LO QUE SIGUE DE LAS
 * ESTADÍSTICAS»*.
 *
 * ## ⚠️ Un solo renderizador para los dos bloques
 *
 * El de rack y el de neto son la misma tabla con otra cifra adentro. Escritos
 * dos veces, el día que alguien agregue una fila al pie —o cambie un formato—
 * la agrega en uno y el otro queda distinto, y dos tablas que se leen una
 * debajo de la otra tienen que verse iguales o la comparación engaña.
 */
import { fmtUsd, fmtInt } from "@/lib/fmt";
import { rtLabel } from "@/lib/api";

export interface FilaTipo {
  id: string; code: string; name: string;
  /** Los doce meses de ESTE bloque: rack en uno, neto en el otro. */
  valores: number[];
}

export default function BloqueRevenue({
  meses, filas, totales, anual, noches, disponibles, totalNoches, totalDisp,
  titulo, nota, acento, mostrarNoches = true, rotulos,
}: {
  meses: string[];
  filas: FilaTipo[];
  totales: number[];
  anual: number;
  noches: number[];
  disponibles: number[];
  totalNoches: number;
  totalDisp: number;
  titulo: string;
  nota: string;
  /** El color del bloque: distingue el rack del neto de un vistazo. */
  acento: string;
  /** Las noches van una sola vez, en el bloque de abajo: son las MISMAS para
   *  los dos y repetirlas invita a buscarles una diferencia que no existe. */
  mostrarNoches?: boolean;
  rotulos: { anio: string; total: string; ocupadas: string; disponibles: string;
             ocupacion: string; adr: string; revpar: string };
}) {
  /** Sin base, la tarifa no es cero: no aplica. Un `$0.00` ahí se lee como
   *  «se vendió a cero», que es una afirmación sobre un mes sin ventas. */
  const tarifa = (rev: number, base: number) => (base ? fmtUsd(rev / base) : "—");
  /** ⚠️ Mismo criterio que la tarifa: sin noches disponibles la ocupación no es
   *  cero, no aplica. Un mes cerrado con «0,0%» se lee como un mes abierto que
   *  no vendió nada. */
  const ocupacion = (occ: number, disp: number) =>
    disp ? `${(occ / disp * 100).toFixed(1)}%` : "—";

  return (
    <div style={{ marginBottom: 26 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap",
                    marginBottom: 6 }}>
        <h2 style={{ fontSize: 15.5, fontWeight: 700, margin: 0, color: acento }}>
          {titulo}
        </h2>
        <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{nota}</span>
      </div>
      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table className="fin-table" style={{ minWidth: 1200 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", minWidth: 220 }}>Room Type</th>
              {meses.map(m => (
                <th key={m} style={{ textAlign: "right", minWidth: 86 }}>{m}</th>
              ))}
              <th style={{ textAlign: "right", minWidth: 110,
                           borderLeft: "1px solid var(--border-medium)" }}>
                {rotulos.anio}
              </th>
            </tr>
          </thead>
          <tbody>
            {filas.map(f => {
              const an = f.valores.reduce((s, v) => s + v, 0);
              return (
                <tr key={f.id}>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>
                    {rtLabel(f.code, f.name)}
                  </td>
                  {f.valores.map((v, mi) => (
                    <td key={mi} className="mono" style={{ textAlign: "right",
                        color: v ? "var(--text-primary)" : "var(--text-disabled)" }}>
                      {fmtUsd(v)}
                    </td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600,
                      borderLeft: "1px solid var(--border-medium)" }}>{fmtUsd(an)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border-medium)" }}>
              <td style={{ textAlign: "left" }}>{rotulos.total}</td>
              {totales.map((v, mi) => (
                <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmtUsd(v)}</td>
              ))}
              <td className="mono" style={{ textAlign: "right", color: acento,
                  borderLeft: "1px solid var(--border-medium)" }}>{fmtUsd(anual)}</td>
            </tr>
            {mostrarNoches && (
              <>
                <tr style={{ color: "var(--text-secondary)" }}>
                  <td style={{ textAlign: "left" }}>{rotulos.ocupadas}</td>
                  {noches.map((n, mi) => (
                    <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmtInt(n)}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right",
                      borderLeft: "1px solid var(--border-medium)" }}>{fmtInt(totalNoches)}</td>
                </tr>
                <tr style={{ color: "var(--text-secondary)" }}>
                  <td style={{ textAlign: "left" }}>{rotulos.disponibles}</td>
                  {disponibles.map((n, mi) => (
                    <td key={mi} className="mono" style={{ textAlign: "right" }}>{fmtInt(n)}</td>
                  ))}
                  <td className="mono" style={{ textAlign: "right",
                      borderLeft: "1px solid var(--border-medium)" }}>{fmtInt(totalDisp)}</td>
                </tr>
                {/* El % de ocupación, que es de donde sale todo lo de arriba y
                    no estaba (owner, 2026-10-04: «mete % de ocupación que no
                    está»). Va con las noches y no con las tarifas: es la misma
                    cifra que se digita en Ocupación. */}
                <tr style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                  <td style={{ textAlign: "left" }}>{rotulos.ocupacion}</td>
                  {noches.map((n, mi) => (
                    <td key={mi} className="mono" style={{ textAlign: "right" }}>
                      {ocupacion(n, disponibles[mi])}
                    </td>
                  ))}
                  <td className="mono" style={{ textAlign: "right",
                      borderLeft: "1px solid var(--border-medium)" }}>
                    {ocupacion(totalNoches, totalDisp)}
                  </td>
                </tr>
              </>
            )}
            <tr style={{ fontWeight: 600, color: acento }}>
              <td style={{ textAlign: "left" }}>{rotulos.adr}</td>
              {totales.map((v, mi) => (
                <td key={mi} className="mono" style={{ textAlign: "right" }}>
                  {tarifa(v, noches[mi])}
                </td>
              ))}
              <td className="mono" style={{ textAlign: "right",
                  borderLeft: "1px solid var(--border-medium)" }}>
                {tarifa(anual, totalNoches)}
              </td>
            </tr>
            <tr style={{ fontWeight: 600, color: acento }}>
              <td style={{ textAlign: "left" }}>{rotulos.revpar}</td>
              {totales.map((v, mi) => (
                <td key={mi} className="mono" style={{ textAlign: "right" }}>
                  {tarifa(v, disponibles[mi])}
                </td>
              ))}
              <td className="mono" style={{ textAlign: "right",
                  borderLeft: "1px solid var(--border-medium)" }}>
                {tarifa(anual, totalDisp)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
