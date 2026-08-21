"use client";
//
// SUMMARY COST — la vista de entrada del tab (spec `COSTOS_GRUPOS.md` §5).
//
// El orden del spec es deliberado: **el resumen va de primero**. Quien abre el
// tab —operación, Ventas, Gerencia— ve el número que necesita sin recorrer el
// motor. El detalle de cómo se llegó ahí vive en los otros sub-tabs.
//
// Es una vista DERIVADA: no acepta entradas y no recalcula por su cuenta. Sale
// del mismo motor que las otras pantallas, así que no puede decir otra cosa.
//
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import IrA from "@/components/IrA";
import MesesElegidos from "@/components/MesesElegidos";
import {
  getResumenGrupos, getScenarios,
  type ResumenGrupos, type Scenario,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"];
const TEMPORADAS = ["ALTA", "MEDIA", "BAJA"];

const n = (v: string | undefined) => parseFloat(v ?? "0");
const usd = (v: string | undefined, d = 2) =>
  n(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v: string | undefined) => (n(v) * 100).toFixed(1) + "%";

const NOMBRE: Record<string, string> = {
  ROOMS: "Habitaciones", FB: "Alimentos y bebidas", TOURS: "Tours",
  TRANSPORTATION: "Transporte", SPA: "Spa", RETAIL: "Tienda",
  LAUNDRY: "Lavandería", CLUB: "Club Madresal", INNOCEANA: "Innoceana",
  SUSTAINABILITY: "Sustainability Fee", MISC_OTHER: "Otros / Misc",
};

export default function ResumenCostosPage() {
  const [mes, setMes] = useState<number>(1);
  const [periodo, setPeriodo] = useState<"full" | "ytd" | "mes">("full");
  // Los meses MARCADOS. Vacío = manda el período.
  const [meses, setMeses] = useState<number[]>([]);
  const [temporada, setTemporada] = useState<string>("");
  // ⚠️ La base por defecto la decide el BACKEND (`cfg_parametros.escenario_base`).
  // Acá vacío = «la configurada»; elegir otra es un filtro de lectura y no
  // reescribe el parámetro que gobierna los Pisos y la Golden Rate.
  const [escenarioId, setEscenarioId] = useState<string>("");
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [r, setR] = useState<ResumenGrupos | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const datos = await getResumenGrupos({
        periodo, mes, meses, temporada: temporada || undefined,
        escenarioId: escenarioId || undefined,
      });
      setR(datos);
      // ⚠️ Al pedir YTD, las casillas se marcan CON LO QUE EL BACKEND ELIGIÓ.
      // El corte lo sabe él (`actuals_through`), así que adivinarlo acá daría
      // una selección distinta de la que se está mostrando.
      if (periodo === "ytd" && meses.length === 0 && datos.seleccion?.meses) {
        setMeses(datos.seleccion.meses);
        setPeriodo("full");
      }
    } catch (e) {
      setR(null);
      setError(e instanceof Error ? e.message : "no se pudo calcular");
    } finally {
      setCargando(false);
    }
  }, [periodo, mes, meses, temporada, escenarioId]);

  useEffect(() => {
    // Sólo para poblar el desplegable de Base.
    getScenarios(process.env.NEXT_PUBLIC_HOTEL_ID || "CWL")
      .then(setEscenarios).catch(() => setEscenarios([]));
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  async function bajarExcel() {
    if (!r || r.vacio) return;
    try {
      await bajarCuadros("Resumen_Costos", [
        {
          titulo: "Cuánta comisión aguanta cada departamento",
          subtitulo: "⚠️ Sirve para leer el P&L y fijar techos de comisión — NO para fijar pisos de precio",
          hoja: "Comision",
          columnas: [
            { label: "Departamento", ancho: 28, formato: "texto" },
            { label: "Costo total", ancho: 15, formato: "usd2" },
            { label: "Revenue neto", ancho: 15, formato: "usd2" },
            { label: "Margen integral", ancho: 15, formato: "pct" },
            { label: "Capa 1", ancho: 12, formato: "pct" },
            { label: "Capa 2", ancho: 12, formato: "pct" },
          ],
          filas: (r.bloque_a ?? []).map((x): FilaCuadro => ({
            label: NOMBRE[x.concepto] ?? x.concepto, nivel: 1,
            valores: [n(x.costo), n(x.revenue_neto), n(x.margen_integral),
                      n(x.capa1), n(x.capa2)],
          })),
        },
        {
          titulo: "Dólares por unidad de servicio",
          subtitulo: (r.calidad ?? []).join(" · "),
          hoja: "Por driver",
          columnas: [
            { label: "Concepto", ancho: 34, formato: "texto" },
            { label: "USD", ancho: 14, formato: "usd2" },
          ],
          filas: ([
            ["Habitaciones · por habitación-noche", "hab_propio_por_ocupada"],
            ["A&B · por noche-huésped", "fb_propio_por_huesped"],
            ["Tours · por noche-huésped", "tours_propio_por_huesped"],
            ["Transporte · por habitación-noche", "transp_propio_por_ocupada"],
            ["Spa · por noche-huésped", "spa_propio_por_huesped"],
            ["Overhead · por habitación DISPONIBLE", "overhead_por_disponible"],
            ["Overhead · por habitación OCUPADA", "overhead_por_ocupada"],
          ] as const).map(([et, k]): FilaCuadro => ({
            label: et, nivel: 1,
            valores: [n((r.bloque_b as unknown as Record<string, string>)[k])],
          })),
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo bajar el Excel");
    }
  }

  const sel = { display: "flex", flexDirection: "column" as const, gap: 3 };
  const et = { fontSize: 11, color: "var(--text-secondary)" };

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA />

      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          Resumen de costos
        </h1>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={!r || !!r.vacio}
          style={{ padding: "6px 14px", borderRadius: 6, fontSize: 13, fontWeight: 600,
                   cursor: "pointer", background: "transparent",
                   color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "flex-end", flexWrap: "wrap",
                    marginTop: 16, padding: "12px 16px", borderRadius: 8,
                    border: "1px solid var(--border)", background: "var(--bg-surface)" }}>
        {/* Los tres selectores del §5: independientes y combinables. */}
        <label style={sel}>
          <span style={et}>Base</span>
          <select className="fin-input" style={{ minWidth: 210, padding: "4px 6px" }}
            value={escenarioId} onChange={e => setEscenarioId(e.target.value)}>
            <option value="">La configurada{r?.base_configurada
              ? ` (${r.base_configurada})` : ""}</option>
            {escenarios.map(s => (
              <option key={s.id} value={s.id}>{s.type} {s.year} {s.version}</option>
            ))}
          </select>
        </label>
        <label style={sel}>
          <span style={et}>Temporada</span>
          <select className="fin-input" style={{ minWidth: 120, padding: "4px 6px" }}
            value={temporada} onChange={e => setTemporada(e.target.value)}>
            <option value="">Todas</option>
            {TEMPORADAS.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        {/* ⚠️ Los meses van DESPLEGADOS y no en un desplegable de uno solo:
            con el anterior, pedir «junio y julio» era imposible. */}
        <label style={{ ...sel, flex: "1 1 100%" }}>
          <span style={et}>Meses</span>
          <MesesElegidos meses={meses} onChange={setMeses}
                         onYtd={() => { setMeses([]); setPeriodo("ytd"); }} />
        </label>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 8 }}>
          <Link href="/cost/pisos" className="fin-input"
            style={{ padding: "6px 12px", fontSize: 12.5, textDecoration: "none",
                     color: "var(--text-primary)" }}>Price Floors ›</Link>
          <Link href="/cost/simulador" className="fin-input"
            style={{ padding: "6px 12px", fontSize: 12.5, textDecoration: "none",
                     color: "var(--text-primary)" }}>Group Simulator ›</Link>
        </div>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginTop: 14 }}>{error}</div>}
      {cargando && <div style={{ color: "var(--text-secondary)", padding: 20 }}>Calculando…</div>}

      {/* ⚠️ La combinación vacía se DICE. Un cero que en realidad es «no hay
          meses» se lee como «no hay costo», que es lo contrario. */}
      {r?.vacio && (
        <div style={{ marginTop: 20, padding: "14px 18px", borderRadius: 8,
                      border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
          {r.motivo}
        </div>
      )}

      {r && !r.vacio && (
        <>
          {/* ── C · la Golden Rate, arriba: es el número que resume todo ──── */}
          <div style={{ marginTop: 24, padding: "18px 22px", borderRadius: 10,
                        border: "1px solid var(--border)",
                        borderLeft: "4px solid var(--brand)" }}>
            <div style={{ display: "flex", gap: 40, flexWrap: "wrap", alignItems: "flex-end" }}>
              <div>
                <div style={et}>Golden Rate · lo que hace falta por habitación-noche</div>
                <div style={{ fontSize: 30, fontWeight: 800, color: "var(--text-primary)" }}>
                  ${usd(r.bloque_c?.tarifa)}
                </div>
              </div>
              <div>
                <div style={et}>ADR real del período</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text-secondary)" }}>
                  ${usd(r.bloque_c?.adr_real)}
                </div>
              </div>
              <div>
                <div style={et}>Brecha</div>
                <div style={{ fontSize: 24, fontWeight: 800,
                              color: n(r.bloque_c?.brecha) >= 0
                                ? "var(--positive)" : "var(--negative)" }}>
                  {n(r.bloque_c?.brecha) >= 0 ? "+" : "−"}${usd(
                    String(Math.abs(n(r.bloque_c?.brecha))))}
                </div>
              </div>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 12,
                        marginBottom: 0, maxWidth: 940, lineHeight: 1.6 }}>
              Cubre el costo propio de Habitaciones (${usd(r.bloque_c?.costo_propio_rooms, 0)}),
              todo el overhead (${usd(r.bloque_c?.overhead, 0)}) y los no operativos
              (${usd(r.bloque_c?.no_operativo, 0)}), <b>descontando</b> lo que los demás
              departamentos aportan (${usd(r.bloque_c?.contribucion_ajena, 0)}).
              {" "}<b>Siempre anual</b>, aunque el filtro sea de un mes: aislada, la temporada
              alta parece necesitar mucho menos, y vender alta contra una Golden Rate
              estacional destruye el año.
            </p>
          </div>

          {/* ── B · dólares por driver ─────────────────────────────────────── */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 30, marginBottom: 8,
                       color: "var(--text-primary)" }}>
            Dólares por unidad de servicio — la que se usa para negociar
          </h2>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            <div className="fin-sticky" style={{ overflowX: "auto", flex: "1 1 380px" }}>
              <table className="fin-table" style={{ minWidth: 360 }}>
                <tbody>
                  {([
                    ["Habitaciones · por habitación-noche", "hab_propio_por_ocupada"],
                    ["A&B · por noche-huésped", "fb_propio_por_huesped"],
                    ["Tours · por noche-huésped", "tours_propio_por_huesped"],
                    ["Transporte · por habitación-noche", "transp_propio_por_ocupada"],
                    ["Spa · por noche-huésped", "spa_propio_por_huesped"],
                    ["Overhead · por habitación DISPONIBLE", "overhead_por_disponible"],
                    ["Overhead · por habitación OCUPADA", "overhead_por_ocupada"],
                  ] as const).map(([lbl, k]) => (
                    <tr key={k}>
                      <td style={{ textAlign: "left" }}>{lbl}</td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        ${usd((r.bloque_b as unknown as Record<string, string>)[k])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="fin-sticky" style={{ overflowX: "auto", flex: "1 1 320px" }}>
              <table className="fin-table" style={{ minWidth: 300 }}>
                <tbody>
                  {([
                    ["Piso 1 · marginal", "marginal"],
                    ["Piso 2 · departamental", "departamental"],
                    ["Piso 3 · integral", "integral"],
                    ["Piso 4 · con margen protegido", "con_margen"],
                  ] as const).map(([lbl, k]) => (
                    <tr key={k}>
                      <td style={{ textAlign: "left",
                                   fontWeight: k === "con_margen" ? 700 : 400 }}>
                        {lbl}
                        {k === "marginal" && r.bloque_b?.marginal_estimado && (
                          <span style={{ color: "var(--negative)", fontSize: 11,
                                         marginLeft: 6 }}>estimado</span>
                        )}
                      </td>
                      <td className="mono" style={{ textAlign: "right",
                            fontWeight: k === "con_margen" ? 700 : 400 }}>
                        ${usd(r.bloque_b?.pisos?.[k])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── A · porcentual ─────────────────────────────────────────────── */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 30, marginBottom: 6,
                       color: "var(--text-primary)" }}>
            Cuánta comisión aguanta cada departamento
          </h2>
          {/* ⚠️ La advertencia que el spec pide EXPLÍCITAMENTE (§5, bloque A). */}
          <div style={{ border: "1px solid var(--negative)", borderRadius: 6,
                        padding: "9px 13px", marginBottom: 10, maxWidth: 940,
                        fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>
            <b style={{ color: "var(--negative)" }}>Estos porcentajes NO fijan pisos de precio.</b>{" "}
            Sirven para leer el P&amp;L y para poner techos de comisión. En vista mensual el
            overhead como % del revenue oscila fuertísimo entre meses — es efecto del
            denominador, no de la estructura. Los pisos se fijan en dólares, arriba.
          </div>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 860 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", minWidth: 200 }}>Departamento</th>
                  <th style={{ textAlign: "right" }}>Costo total</th>
                  <th style={{ textAlign: "right" }}>Revenue neto</th>
                  <th style={{ textAlign: "right" }}>Factor neto</th>
                  <th style={{ textAlign: "right" }}>Margen integral</th>
                  <th style={{ textAlign: "right" }}>Comisión máx. · cubre costo</th>
                  <th style={{ textAlign: "right" }}>Comisión máx. · con margen</th>
                </tr>
              </thead>
              <tbody>
                {(r.bloque_a ?? []).map(x => (
                  <tr key={x.concepto}>
                    <td style={{ textAlign: "left" }}>{NOMBRE[x.concepto] ?? x.concepto}</td>
                    <td className="mono" style={{ textAlign: "right" }}>${usd(x.costo, 0)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>${usd(x.revenue_neto, 0)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{n(x.factor_neto).toFixed(2)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{pct(x.margen_integral)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{pct(x.capa1)}</td>
                    <td className="mono" style={{ textAlign: "right", fontWeight: 600 }}>{pct(x.capa2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Pie · calidad del dato ─────────────────────────────────────── */}
          {(r.calidad ?? []).length > 0 && (
            <div style={{ marginTop: 26, padding: "12px 16px", borderRadius: 8,
                          border: "1px solid var(--negative)" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--negative)",
                            marginBottom: 6 }}>
                Qué de esto NO está medido
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5,
                           color: "var(--text-secondary)", lineHeight: 1.7 }}>
                {(r.calidad ?? []).map((x, i) => <li key={i}>{x}</li>)}
              </ul>
            </div>
          )}

          <p style={{ fontSize: 11.5, color: "var(--text-disabled)", marginTop: 16 }}>
            {r.escenario} · comisión {pct(r.parametros?.comision)} · margen protegido{" "}
            {pct(r.parametros?.margen_protegido)} · fee {pct(r.parametros?.fee)} ·
            absorción {r.parametros?.metodo_absorcion} · meses{" "}
            {(r.seleccion?.meses ?? []).length} ({(r.seleccion?.meses_con_ocupacion ?? []).length}{" "}
            con ocupación)
          </p>
        </>
      )}
    </div>
  );
}
