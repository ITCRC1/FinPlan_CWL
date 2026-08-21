"use client";
//
// MASTER DATA — «Mi Resumen» (spec `COSTOS_GRUPOS.md` §5, sub-tab 3).
//
// Réplica del `FULL YEAR ANALYSIS 2026.xlsx` del owner: sus ocho bloques y sus
// columnas de temporada. Pedido textual: «dame ese tab, será MI RESUMEN» ·
// «toda la información está en FinPlan» · «es llamar todo ese detalle» ·
// «sólo 2, lado a lado, para ver Budget y Actual y Forecast».
//
// ⚠️ **No se carga nada.** Es una vista derivada: cada cifra sale del motor del
// escenario. Si un número está mal acá, está mal en el P&L — y ése es el punto.
//
// ⚠️ **Las columnas de temporada las decide `cfg_temporadas`.** Owner,
// 2026-08-20: «sólo mapeá tus datos, y demos esos como válidos» — así que no se
// imita el corte en dos del Excel ni se agrupa una temporada dentro de otra
// para que una comparación cuadre. Arriba se muestra qué meses entran en cada
// columna, que es lo único que hace falta para leerla.
//
import { useCallback, useEffect, useState } from "react";
import IrA from "@/components/IrA";
import {
  getScenarios, getMasterDataCostos,
  type Scenario, type ColumnaMaster, type FilaMaster,
} from "@/lib/api";
import { bajarCuadros, type FormatoCol } from "@/lib/exportCuadro";

const HOTEL = process.env.NEXT_PUBLIC_HOTEL_ID || "CWL";

// ⚠️ Los rótulos son sólo cosmética: **las columnas llegan del backend**, que
// las saca de `cfg_temporadas`. Si aparece una temporada nueva, sale sola con
// su propia clave y no hay que tocar esta lista.
const ROTULO: Record<string, string> = {
  ALTA: "Temp. Alta",
  MEDIA: "Temp. Media",
  BAJA: "Temp. Baja",
  ANIO: "Año Completo",
};
const rotulo = (c: string) => ROTULO[c] || c;

// ⚠️ **La divisoria entre escenarios va en UNA constante, no repetida en cada
// celda.** Es la línea que separa «lo que dice un escenario» de «lo que dice el
// otro»: si en alguna fila quedara distinta —o faltara— las dos mitades se
// leerían como una sola tabla, que es exactamente el error caro al comparar.
const DIVISORIA = "3px solid var(--text-secondary)";

/** El borde de la primera columna de cada escenario, salvo el primero. */
const corte = (i: number) => (i > 0 ? { borderLeft: DIVISORIA } : undefined);

const MES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

function n(v: string): number {
  const x = parseFloat(v);
  return isNaN(x) ? 0 : x;
}

function mostrar(v: string, formato: string): string {
  const x = n(v);
  if (formato === "pct") return (x * 100).toFixed(1) + "%";
  if (formato === "num") return x.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (formato === "num2") return x.toLocaleString("en-US", { minimumFractionDigits: 2,
                                                             maximumFractionDigits: 2 });
  return x.toLocaleString("en-US", { minimumFractionDigits: 2,
                                     maximumFractionDigits: 2 });
}

// El escenario con el que abre cada columna. El owner nombró Budget, Actual y
// Forecast: se ofrecen los tres y arranca comparando Forecast contra Actual,
// que es la pareja con la que se mira «la realidad» (decisión del 19-ago).
//
// ⚠️ **No se llama como la regla compartida, y eso importa.** La prueba que
// vigila «con cuál escenario abre cada pantalla» aceptaba el nombre suelto como
// señal de que se usaba esa regla — así que una función local con ese nombre
// pasaba el control EN VERDE mientras elegía por su cuenta. El guardián se
// corrigió para exigir además el import del módulo; el nombre se cambió acá
// para que no vuelva a confundirse.
function porTipo(todos: Scenario[], tipo: string): Scenario | undefined {
  const del = todos.filter(s => s.type === tipo);
  return del.find(s => s.version?.toLowerCase().includes("working")) || del[0];
}

export default function MasterDataPage() {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [columnas, setColumnas] = useState<ColumnaMaster[]>([]);
  const [claves, setClaves] = useState<string[]>([]);
  const [mesesPorCol, setMesesPorCol] = useState<Record<string, number[]>>({});
  const [sinTemporada, setSinTemporada] = useState<number[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const todos = await getScenarios(HOTEL);
        setEscenarios(todos);
        setA(porTipo(todos, "FORECAST")?.id || todos[0]?.id || "");
        setB(porTipo(todos, "ACTUAL")?.id || "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "no se pudieron leer los escenarios");
        setCargando(false);
      }
    })();
  }, []);

  const cargar = useCallback(async () => {
    if (!a) return;
    setCargando(true);
    setError(null);
    try {
      const r = await getMasterDataCostos(a, b || undefined);
      setColumnas(r.columnas);
      setClaves(r.columnas_clave);
      setMesesPorCol(r.meses_por_columna);
      setSinTemporada(r.meses_sin_temporada);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo calcular");
    } finally {
      setCargando(false);
    }
  }, [a, b]);

  useEffect(() => { cargar(); }, [cargar]);

  async function bajar() {
    setError(null);
    try {
      await bajarCuadros("Master Data", columnas.flatMap(c =>
        c.bloques.map(bl => ({
          titulo: `${bl.titulo} — ${c.escenario.etiqueta}`,
          subtitulo: "Vista derivada: todo sale del motor del escenario",
          hoja: `${bl.clave}-${c.escenario.tipo}`.slice(0, 28),
          columnas: [
            { label: "Concepto", ancho: 34, formato: "texto" as FormatoCol },
            ...claves.map(c => ({
              label: rotulo(c),
              formato: (bl.filas[0]?.formato === "pct" ? "pct" : "usd") as FormatoCol,
            })),
          ],
          filas: bl.filas.map(f => ({
            label: f.label,
            es_total: !!f.es_total,
            formato: (f.formato === "pct" ? "pct"
              : f.formato === "num" ? "num" : "usd") as FormatoCol,
            valores: claves.map(c => n(f.valores[c])),
          })),
        }))));
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo bajar");
    }
  }

  const bloques = columnas[0]?.bloques || [];

  return (
    <div className="pag-ancha">
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4,
                   textAlign: "center" }}>
        Master Data — Mi Resumen
      </h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 13,
                  marginBottom: 12, maxWidth: 940, lineHeight: 1.65,
                  marginLeft: "auto", marginRight: "auto", textAlign: "center" }}>
        El P&amp;L por departamento, partido por temporada. <b>No se carga nada</b>:
        cada cifra sale del motor del escenario. Si un número está mal acá, está
        mal en el P&amp;L.
      </p>

      {/* Dos escenarios lado a lado, como pidió el owner. */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 14,
                    justifyContent: "center" }}>
        {[{ v: a, set: setA, t: "Columna izquierda" },
          { v: b, set: setB, t: "Columna derecha" }].map((sel, i) => (
          <label key={i} style={{ fontSize: 12.5 }}>
            <div style={{ color: "var(--text-secondary)", marginBottom: 3 }}>{sel.t}</div>
            <select className="fin-input" value={sel.v}
                    onChange={ev => sel.set(ev.target.value)}
                    style={{ minWidth: 260 }}>
              {i === 1 && <option value="">— sola una columna —</option>}
              {escenarios.map(s => (
                <option key={s.id} value={s.id}>
                  {s.type} {s.year} {s.version}
                </option>
              ))}
            </select>
          </label>
        ))}
        <div style={{ alignSelf: "flex-end" }}>
          <button className="fin-btn" onClick={bajar} disabled={cargando || !columnas.length}>
            ⬇ Excel
          </button>
        </div>
      </div>

      {/* ⚠️ Qué meses entran en cada columna, a la vista. Sin esto hay que
          abrir `cfg_temporadas` para poder leer la tabla — y una diferencia de
          calendario se confunde con un error de cálculo. */}
      {claves.length > 1 && (
        <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10,
                    textAlign: "center" }}>
          {claves.filter(c => c !== "ANIO").map(c => (
            <span key={c} style={{ marginRight: 18 }}>
              <b>{rotulo(c)}:</b>{" "}
              {(mesesPorCol[c] || []).map(m => MES[m]).join(" · ") || "—"}
            </span>
          ))}
        </p>
      )}

      {sinTemporada.length > 0 && (
        <div style={{
          padding: "12px 16px", borderRadius: 10, maxWidth: 940,
          border: "1px solid var(--border)",
          borderLeft: "4px solid var(--warning, #B8860B)", marginBottom: 16,
          fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6,
        }}>
          <b>{sinTemporada.map(m => MES[m]).join(" · ")}</b> no tiene temporada
          asignada en <span className="mono">cfg_temporadas</span>. Su plata{" "}
          <b>entra al Año Completo</b> y no aparece en ninguna columna de
          temporada — por eso las columnas pueden no sumar el año.
        </div>
      )}

      {error && <p style={{ color: "var(--negative)", fontSize: 13 }}>{error}</p>}
      {cargando && (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Calculando…</p>
      )}

      {!cargando && bloques.map((bl, bi) => (
        <div key={bl.clave} style={{ marginBottom: 26 }}>
          {/* Centrado, para que el título quede sobre su propia tabla y no
              pegado al borde izquierdo de la pantalla. */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6,
                       textAlign: "center" }}>
            {bl.titulo}
          </h2>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table"
                   style={{ minWidth: 940, margin: "0 auto" }}>
              <thead>
                <tr>
                  <th rowSpan={2} style={{ textAlign: "left" }}>Concepto</th>
                  {columnas.map((c, i) => (
                    <th key={c.escenario.id} colSpan={claves.length}
                        style={{ textAlign: "center", fontSize: 13.5,
                                 letterSpacing: 0.3, ...corte(i) }}>
                      {c.escenario.etiqueta}
                    </th>
                  ))}
                </tr>
                <tr>
                  {columnas.map((c, i) => claves.map((k, j) => (
                    <th key={`${c.escenario.id}-${k}`}
                        style={{ textAlign: "right", fontSize: 11.5,
                                 ...(j === 0 ? corte(i) : undefined) }}>
                      {rotulo(k)}
                    </th>
                  )))}
                </tr>
              </thead>
              <tbody>
                {bl.filas.map((f: FilaMaster, fi) => (
                  <tr key={f.label} style={f.es_total
                    ? { fontWeight: 700, background: "var(--bg-total, transparent)" }
                    : undefined}>
                    <td style={{ textAlign: "left" }} title={f.nota || undefined}>
                      {f.label}
                      {f.nota && (
                        <span style={{ color: "var(--warning, #B8860B)" }}> ⚠</span>
                      )}
                    </td>
                    {columnas.map((c, i) => claves.map((k, j) => {
                      const fila = c.bloques[bi]?.filas[fi];
                      return (
                        <td key={`${c.escenario.id}-${k}`}
                            style={{ textAlign: "right",
                                     ...(j === 0 ? corte(i) : undefined) }}
                            className="mono">
                          {fila ? mostrar(fila.valores[k], fila.formato) : "—"}
                        </td>
                      );
                    }))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
