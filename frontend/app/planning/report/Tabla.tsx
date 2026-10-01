"use client";
/**
 * La tabla del Planning Report: dibuja un `Cuadro`, el MISMO objeto que baja al
 * Excel.
 *
 * ⚠️ Está acá afuera a propósito. Los cuatro sub-reportes —P&L, aperturas,
 * checkbooks y estadísticas— pasan por este único renderizador: con una tabla
 * por pantalla, la del P&L y la del checkbook se separan en el primer retoque
 * que alguien haga de un lado, y las dos se ven igual de bien.
 *
 * Owner, 2026-08-27, sobre el defecto que esto evita: *«el excel no baja lo que
 * está viendo»*.
 */
import type { Cuadro, FormatoCol } from "@/lib/exportCuadro";

const TD: React.CSSProperties = {
  padding: "4px 10px", textAlign: "right", fontSize: 12, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = {
  padding: "4px 10px", fontSize: 12, textAlign: "left",
};

/** Un número con el formato de su columna o de su fila.
 *
 *  ⚠️ `null` deja la celda VACÍA y cero escribe un guion: no son lo mismo. Una
 *  cuenta sin presupuesto y una en cero se leen distinto, y en un reporte de
 *  planificación la diferencia es justamente lo que se está mirando. */
function celda(v: number | string | null, formato: FormatoCol): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (formato === "texto") return String(v);
  if (formato === "pct") {
    return Math.abs(v) < 1e-9 ? "—" : `${(v * 100).toFixed(1)}%`;
  }
  const dec = formato === "num" ? 0 : formato === "num1" ? 1 : 2;
  if (Math.abs(v) < (dec ? 0.5 / 10 ** dec : 0.5)) return "—";
  const n = Math.abs(v).toLocaleString("en-US",
    { minimumFractionDigits: dec, maximumFractionDigits: dec });
  return v < 0 ? `(${n})` : n;
}

export default function Tabla({ cuadro }: { cuadro: Cuadro }) {
  return (
    <div className="fin-scroll-x" style={{ overflowX: "auto", maxHeight: "72vh" }}>
      <table className="fin-table"
             style={{ minWidth: 320 + cuadro.columnas.length * 88 }}>
        <thead>
          <tr>
            {cuadro.columnas.map((c, i) => (
              <th key={i} style={{ ...(i ? TD : TDL), position: "sticky", top: 0,
                                   background: "var(--bg-header)", zIndex: 1,
                                   borderLeft: c.abre_grupo
                                     ? "2px solid var(--border-medium)" : undefined }}>
                <div>{c.label}</div>
                {c.sub && (
                  <div style={{ fontWeight: 400, fontSize: 10.5,
                                color: "var(--text-secondary)" }}>{c.sub}</div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cuadro.filas.map((f, i) => (
            <tr key={i} style={{
              background: f.es_seccion ? "var(--bg-elevated)"
                : f.es_total ? "var(--bg-surface)" : undefined,
            }}>
              <td style={{ ...TDL,
                fontWeight: f.es_seccion || f.es_total ? 700 : 400,
                paddingLeft: 10 + (f.nivel ?? 0) * 14 }}>
                {f.label}
              </td>
              {f.valores.map((v, j) => {
                const fmt = f.formato ?? cuadro.columnas[j + 1]?.formato ?? "usd2";
                return (
                  <td key={j} className="mono" style={{ ...TD,
                    fontWeight: f.es_total ? 700 : 400,
                    borderLeft: cuadro.columnas[j + 1]?.abre_grupo
                      ? "2px solid var(--border-medium)" : undefined,
                    color: typeof v === "number" && v < 0
                      ? "var(--negative)" : undefined,
                  }}>{celda(v, fmt)}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
