"use client";
/**
 * El resumen de una página: siete líneas, doce meses — Actual y Budget.
 *
 * Owner, 2026-09-02: *«metamos un sub tab en cierre de mes solamente de 4
 * líneas por mes: Total revenue una línea y abajo Payroll and benefits, opex,
 * cost and property expenses; se totaliza Total expenses y se pone un neto.
 * Esto que sea 12 meses»* y, enseguida, *«y abajo haces lo mismo pero para
 * budget para que se pueda ver»*.
 *
 * **El gasto va por NATURALEZA, no por departamento.** Es la diferencia con el
 * resto de los sub-tabs: acá no importa quién gastó sino en qué —planilla,
 * costo de ventas, opex, gasto de propiedad—, que es como se lee un resumen de
 * una página.
 *
 * ⚠️ **Total Expenses incluye el gasto de propiedad**, así que el Neto de este
 * cuadro es el resultado DESPUÉS de propiedad — no es el GOP. En el P&L
 * Statement el gasto de propiedad va debajo del GOP y por eso los dos totales
 * se llaman distinto. Confundirlos sería leer el GOP donde dice Net.
 *
 * ## Las dos tablas comparten las COLUMNAS
 *
 * El Actual se movió de marzo a julio y el Budget de junio a diciembre. Si cada
 * tabla eligiera sus propios meses, la primera columna de arriba sería marzo y
 * la de abajo junio — y quedarían una sobre otra invitando a compararlas.
 * Por eso los meses se calculan sobre la UNIÓN de los dos: se pierde algo de
 * ancho y se gana que mirar hacia abajo signifique algo.
 *
 * ## De dónde sale cada mitad
 *
 * El ingreso del P&L (`/pl/{id}/doce-meses/`) y el gasto de
 * `/gasto-por-clase/`. Son dos consultas, igual que en el P&L Statement, y por
 * la misma razón: el gasto por naturaleza no existe como línea del P&L —el
 * motor lo agrupa por departamento— y el ingreso por naturaleza no significa
 * nada.
 */
import { sembrarTres } from "@/lib/escenarioPreferido";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getGastoPorClase, getPLDoceMeses,
         type GastoEscenario, type Scenario } from "@/lib/api";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

const TD: React.CSSProperties = {
  padding: "5px 10px", textAlign: "right", fontSize: 12, whiteSpace: "nowrap",
};
const SEL: React.CSSProperties = {
  padding: "5px 9px", fontSize: 12, borderRadius: 5,
  border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)",
};

/** El escenario con el que abrir, para un papel.
 *
 *  ⚠️ Usa `sembrarTres` —la regla del owner— y NO `escenarios.find(...)`.
 *  Esa era la versión anterior, copiada en los cuatro sub-tabs: devolvía el
 *  PRIMERO de ese tipo, y `GET /scenarios/` ordena por año descendente, así
 *  que el primer BUDGET de la lista es el Working **2035**. Cada sub-tab abría
 *  en un presupuesto real, vacío y de otro año — sin que nada fallara. */
function primeroDe(escenarios: Scenario[], tipo: string): string {
  const tres = sembrarTres(escenarios);
  const id = tipo === "ACTUAL" ? tres.actual
    : tipo === "BUDGET" ? tres.budget
    : tipo === "FORECAST" ? tres.forecast : "";
  // El respaldo se queda: si NO hay ninguno de ese tipo, mejor mostrar algo
  // que un selector en blanco sin explicación.
  return id || escenarios.find(s => s.type === tipo)?.id || escenarios[0]?.id || "";
}

/** Lo que se dibuja de un escenario: siete series de doce meses. */
export type Datos = {
  ingreso: number[];
  payroll: number[]; cost: number[]; opex: number[]; property: number[];
  totalGasto: number[]; neto: number[];
};

const VACIO: Datos = {
  ingreso: Array(12).fill(0), payroll: Array(12).fill(0),
  cost: Array(12).fill(0), opex: Array(12).fill(0),
  property: Array(12).fill(0), totalGasto: Array(12).fill(0),
  neto: Array(12).fill(0),
};

export function armar(rev: number[], g: GastoEscenario | null): Datos {
  const d: Datos = {
    ingreso: rev,
    payroll: Array(12).fill(0), cost: Array(12).fill(0),
    opex: Array(12).fill(0), property: Array(12).fill(0),
    totalGasto: Array(12).fill(0), neto: Array(12).fill(0),
  };
  for (const m of g?.meses ?? []) {
    const i = m.month - 1;
    d.payroll[i] = Number(m.payroll || 0);
    d.cost[i] = Number(m.cost || 0);
    d.opex[i] = Number(m.opex || 0);
    d.property[i] = Number(m.property || 0);
  }
  for (let i = 0; i < 12; i++) {
    d.totalGasto[i] = d.payroll[i] + d.cost[i] + d.opex[i] + d.property[i];
    d.neto[i] = d.ingreso[i] - d.totalGasto[i];
  }
  return d;
}

/** Un escenario cargado, o `null` mientras carga. */
function useResumen(scenarioId: string) {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    if (!scenarioId) { setDatos(null); return; }
    setError(null);
    try {
      const [pl, gc] = await Promise.all([
        getPLDoceMeses(scenarioId),
        getGastoPorClase([scenarioId], false),
      ]);
      const rev = Array(12).fill(0);
      for (const m of pl.meses) {
        const l = m.lines.find(x => x.line_code === "TOTAL_REVENUES");
        rev[m.month - 1] = l ? l.amount_usd : 0;
      }
      setDatos(armar(rev, gc.escenarios[0] ?? null));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el año");
      setDatos(null);
    }
  }, [scenarioId]);

  useEffect(() => { cargar(); }, [cargar]);
  return { datos, error };
}

/** Las siete lineas, declaradas UNA vez.
 *
 *  ⚠️ Las usan la tabla de la pantalla y el capitulo del Word. Escribirlas dos
 *  veces seria que un dia el documento diga algo que la pantalla no dice. */
export function filasResumen(datos: Datos): {
  label: string; serie: number[]; fuerte?: boolean;
  sangria?: boolean; borde?: boolean;
}[] {
  return [
    { label: "Total Revenue", serie: datos.ingreso, fuerte: true, borde: true },
    { label: "Payroll and Benefits", serie: datos.payroll, sangria: true },
    { label: "Cost of Sales", serie: datos.cost, sangria: true },
    { label: "Operating Expenses", serie: datos.opex, sangria: true },
    { label: "Property Expenses", serie: datos.property, sangria: true },
    { label: "Total Expenses", serie: datos.totalGasto, fuerte: true },
    { label: "Net", serie: datos.neto, fuerte: true, borde: true },
  ];
}

function Tabla({ datos, columnas }: { datos: Datos; columnas: number[] }) {
  const FILAS = filasResumen(datos);
  return (
    <div className="fin-scroll-x">
      <table style={{ borderCollapse: "collapse", minWidth: 560 }}>
        <thead>
          <tr>
            <th style={{ ...TD, textAlign: "left", minWidth: 210,
                         borderBottom: "1px solid var(--border-medium)" }}>
              Line Item
            </th>
            {columnas.map(i => (
              <th key={i} style={{ ...TD, fontWeight: 700, minWidth: 108,
                                   borderBottom: "1px solid var(--border-medium)" }}>
                {MESES[i]}
              </th>
            ))}
            <th style={{ ...TD, fontWeight: 800, minWidth: 120,
                         borderLeft: "2px solid var(--border-medium)",
                         borderBottom: "1px solid var(--border-medium)" }}>
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {FILAS.map(f => (
            <tr key={f.label} style={{
              borderTop: f.borde ? "1px solid var(--border-medium)" : undefined,
              background: f.fuerte ? "var(--bg-surface)" : undefined,
            }}>
              <td style={{ padding: "5px 10px", fontSize: 12.5,
                           fontWeight: f.fuerte ? 800 : 500,
                           paddingLeft: f.sangria ? 24 : 10 }}>
                {f.label}
              </td>
              {columnas.map(i => (
                <td key={i} style={{ ...TD, fontWeight: f.fuerte ? 800 : 400,
                      color: f.serie[i] < 0 ? "var(--negative)" : undefined }}>
                  {usd(f.serie[i])}
                </td>
              ))}
              <td style={{ ...TD, fontWeight: 800,
                    borderLeft: "2px solid var(--border-medium)",
                    color: columnas.reduce((s, i) => s + f.serie[i], 0) < 0
                      ? "var(--negative)" : undefined }}>
                {usd(columnas.reduce((s, i) => s + f.serie[i], 0))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ResumenDoceMeses({ escenarios, inicial }: {
  escenarios: Scenario[];
  inicial?: string;
}) {
  const [vActual, setVActual] = useState("");
  const [vBudget, setVBudget] = useState("");

  useEffect(() => {
    if (!escenarios.length) return;
    // El de arriba arranca en un ACTUAL y el de abajo en un BUDGET. `inicial`
    // —la ranura 1 de la pantalla— queda de respaldo detrás de cada uno: casi
    // siempre trae el ACTUAL, y ponerlo primero abriría el Budget mostrando el
    // Actual, que es el defecto que ya se corrigió en el sub-tab de 12 meses.
    setVActual(x => x || primeroDe(escenarios, "ACTUAL") || inicial || "");
    setVBudget(x => x || primeroDe(escenarios, "BUDGET") || inicial || "");
  }, [escenarios, inicial]);

  const arriba = useResumen(vActual);
  const abajo = useResumen(vBudget);

  /** ⚠️ Los meses son la UNIÓN de los dos cuadros. Con columnas propias, la
   *  primera de arriba sería marzo y la de abajo junio, una sobre otra
   *  invitando a compararlas. */
  const columnas = useMemo(() => {
    const todos = Array.from({ length: 12 }, (_, i) => i);
    const vivo = (d: Datos | null, i: number) =>
      !!d && (Math.abs(d.ingreso[i]) >= 0.005 || Math.abs(d.totalGasto[i]) >= 0.005);
    const vivos = todos.filter(i => vivo(arriba.datos, i) || vivo(abajo.datos, i));
    return vivos.length ? vivos : todos;
  }, [arriba.datos, abajo.datos]);

  const bloque = (titulo: string, valor: string,
                  setValor: (v: string) => void,
                  r: { datos: Datos | null; error: string | null }) => (
    <div style={{ marginBottom: 26 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center",
                    flexWrap: "wrap", marginBottom: 8 }}>
        <b style={{ fontSize: 13, color: "var(--brand)" }}>{titulo}</b>
        <select value={valor} onChange={e => setValor(e.target.value)} style={SEL}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
          ))}
        </select>
        {!r.datos && !r.error && (
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>cargando…</span>
        )}
        {r.error && <span style={{ fontSize: 12, color: "var(--negative)" }}>{r.error}</span>}
      </div>
      <Tabla datos={r.datos ?? VACIO} columnas={columnas} />
    </div>
  );

  return (
    <div>
      {bloque("ACTUAL", vActual, setVActual, arriba)}
      {bloque("BUDGET", vBudget, setVBudget, abajo)}

      <p style={{ fontSize: 11.5, color: "var(--text-secondary)",
                  maxWidth: 820, lineHeight: 1.6 }}>
        ⚠️ <b>Total Expenses incluye el gasto de propiedad</b>, así que{" "}
        <b>Net</b> es el resultado después de propiedad — <b>no es el GOP</b>.
        En el P&amp;L Statement el gasto de propiedad va debajo del GOP; acá las
        cuatro naturalezas van juntas, como se pidió este cuadro.
        Los dos cuadros comparten los meses para que mirar hacia abajo compare
        el mismo período.
      </p>
    </div>
  );
}
