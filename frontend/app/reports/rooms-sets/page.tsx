"use client";
import { useCallback, useEffect, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getRoomsSetsReport,
  type Scenario, type RoomsSetsReport, type RoomsSetRow,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const HOTEL = HOTEL_ID;
const GOLD = "#c8a24a";
const MESES_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 11, textAlign: "left", padding: "9px 12px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.06em", background: "var(--bg-elevated)" };
const thNum: CSSProperties = { ...th, textAlign: "right", padding: "9px 8px", textTransform: "none", letterSpacing: 0 };
const td: CSSProperties = { padding: "8px 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 13 };
const tdNum: CSSProperties = { padding: "8px", textAlign: "right", fontSize: 12.5, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--border-subtle)", whiteSpace: "nowrap" };

const money = (v: number) => (v < 0 ? "(" : "") + "$" +
  Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + (v < 0 ? ")" : "");
const pct1 = (v: number) => (v * 100).toFixed(1) + "%";

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

type Metrica = "costo" | "revenue" | "payroll" | "opex" | "distribucion";
const METRICAS: { key: Metrica; labelKey: string }[] = [
  { key: "costo", labelKey: "mCosto" },
  { key: "payroll", labelKey: "mPlanilla" },
  { key: "opex", labelKey: "mOpex" },
  { key: "distribucion", labelKey: "mReparto" },
  { key: "revenue", labelKey: "mIngreso" },
];

export default function RoomsSetsReportPage() {
  const tc = useTranslations("common");
  const t = useTranslations("roomsSets");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [data, setData] = useState<RoomsSetsReport | null>(null);
  const [metrica, setMetrica] = useState<Metrica>("costo");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL);
        if (!all.length) { setError(tc("noScenarios", { hotel: HOTEL_ID })); setLoading(false); return; }
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error"); setLoading(false);
      }
    })();
  }, [setScenarioId]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError("");
    try { setData(await getRoomsSetsReport(id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(scenarioId); }, [scenarioId, load]);

  const serie = (r: RoomsSetRow): number[] => r[metrica];

  /* El detalle mensual sale con las CINCO métricas, no solo con la que está
     seleccionada en pantalla: el botón de arriba es un filtro de vista, y el que
     baja el archivo lo abre para comparar. Ocupación y margen van en fracción. */
  async function bajarExcel() {
    if (!data) return;
    const resumen: FilaCuadro[] = data.rows.map(r => {
      const nd = r.noches_disponibles.reduce((a, b) => a + b, 0);
      const no = r.noches_ocupadas.reduce((a, b) => a + b, 0);
      return {
        label: r.name + (r.es_residuo ? t("residuoSuf") : ""), nivel: 0,
        valores: [
          r.costo_anual, r.revenue_anual, r.unidades, r.categorias.length, nd, no,
          nd > 0 ? no / nd : null,
          r.revenue_anual > 0 ? (r.revenue_anual - r.costo_anual) / r.revenue_anual : null,
        ],
      };
    });
    const ndT = data.rows.reduce((a, r) => a + r.noches_disponibles.reduce((x, y) => x + y, 0), 0);
    const noT = data.rows.reduce((a, r) => a + r.noches_ocupadas.reduce((x, y) => x + y, 0), 0);
    resumen.push({
      label: t("consolidadoExcel"), nivel: 0, es_total: true,
      valores: [
        data.consolidado.costo_anual, data.consolidado.revenue_anual, data.consolidado.unidades, null,
        ndT, noT, ndT > 0 ? noT / ndT : null,
        data.consolidado.revenue_anual > 0
          ? (data.consolidado.revenue_anual - data.consolidado.costo_anual) / data.consolidado.revenue_anual : null,
      ],
    });

    const VACIA: (number | null)[] = Array(13).fill(null);
    const mensual: FilaCuadro[] = [];
    for (const m of METRICAS) {
      mensual.push({ label: t(m.labelKey), nivel: 0, es_total: true, valores: VACIA });
      for (const r of data.rows) {
        const s = r[m.key];
        mensual.push({ label: r.name, nivel: 1, valores: [...s, s.reduce((a, b) => a + b, 0)] });
      }
      const cons = Array.from({ length: 12 }, (_, mi) => data.rows.reduce((a, r) => a + r[m.key][mi], 0));
      mensual.push({ label: t("consolidadoMetrica", { metrica: t(m.labelKey) }), nivel: 0, es_total: true,
                     valores: [...cons, cons.reduce((a, b) => a + b, 0)] });
    }

    const scn = scenarios.find(s => s.id === scenarioId);
    try {
      await bajarCuadros("Rooms_Sets", [
        {
          titulo: t("excelTituloResumen"),
          subtitulo: `${scn ? scnLabel(scn) : ""} · ${data.year} · USD`, hoja: t("hojaResumen"),
          columnas: [
            { label: "Set", ancho: 32, formato: "texto" },
            { label: t("colCostoAnual"), ancho: 15, formato: "usd" },
            { label: t("colIngresoAnual"), ancho: 15, formato: "usd" },
            { label: t("colUnidades"), ancho: 11, formato: "num" },
            { label: t("colCategorias"), ancho: 11, formato: "num" },
            { label: t("colNochesDisp"), ancho: 18, formato: "num" },
            { label: t("colNochesOcup"), ancho: 17, formato: "num" },
            { label: t("colOcupacion"), ancho: 12, formato: "pct" },
            { label: t("colMargen"), ancho: 11, formato: "pct" },
          ],
          filas: resumen,
        },
        {
          titulo: t("excelTituloMensual"),
          subtitulo: `${scn ? scnLabel(scn) : ""} · ${data.year}${t("excelSubMensualCola")}`, hoja: t("monthByMonth"),
          columnas: [
            { label: "Set", ancho: 34, formato: "texto" },
            ...MESES.map(m => ({ label: m, ancho: 13, formato: "usd" as const })),
            { label: tc("year"), ancho: 15, formato: "usd" as const },
          ],
          filas: mensual,
        },
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: "24px 20px 60px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
        </select>
        <button onClick={bajarExcel} disabled={!data} title={t("excelBtnTitle")}
          style={{ padding: "5px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: data ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", opacity: data ? 1 : 0.5 }}>⬇ Excel</button>
      </div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6, maxWidth: "76ch" }}>
        {t.rich("intro", { b: (c) => <b>{c}</b> })}
      </p>

      {error && <div style={{ color: "var(--negative)", fontSize: 12.5, marginTop: 10 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", padding: 40, textAlign: "center" }}>{tc("loading")}</div>}

      {data && !loading && (
        <>
          {!data.cuadra && (
            <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 8, fontSize: 12.5, background: "rgba(239,83,80,0.10)", color: "var(--negative)", border: "1px solid var(--negative)" }}>
              {t("noCuadra", { monto: money(data.asiento_neto) })}
            </div>
          )}
          {!data.hay_reparto && (
            <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 8, fontSize: 12.5, background: "rgba(200,162,74,0.10)", color: GOLD, border: `1px solid ${GOLD}` }}>
              {t.rich("sinReparto", { b: (c) => <b>{c}</b> })}
            </div>
          )}

          {/* ── Tarjetas por set ─────────────────────────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fit, minmax(250px, 1fr))`, gap: 14, marginTop: 18 }}>
            {data.rows.map(r => {
              const nd = r.noches_disponibles.reduce((a, b) => a + b, 0);
              const no = r.noches_ocupadas.reduce((a, b) => a + b, 0);
              return (
                <div key={r.key} style={{ background: "var(--bg-elevated)", border: `1px solid ${r.es_residuo ? "var(--border-medium)" : GOLD}`, borderRadius: 10, padding: "14px 16px" }}>
                  <div style={{ fontSize: 10.5, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                    {r.dept_code || t("deptFallback")} {r.es_residuo && t("residuo")}
                  </div>
                  <div style={{ fontSize: 17, fontWeight: 700, marginTop: 2 }}>{r.name}</div>
                  <div style={{ display: "flex", gap: 18, marginTop: 10 }}>
                    <div>
                      <div style={{ fontSize: 10.5, color: "var(--text-secondary)" }}>{t("yearCost")}</div>
                      <div className="mono" style={{ fontSize: 17, fontWeight: 700, color: GOLD }}>{money(r.costo_anual)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10.5, color: "var(--text-secondary)" }}>{t("mIngreso")}</div>
                      <div className="mono" style={{ fontSize: 17, fontWeight: 700 }}>{money(r.revenue_anual)}</div>
                    </div>
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.6 }}>
                    {t("unidadesCategorias", { u: r.unidades, c: r.categorias.length })}<br />
                    {t("ocupacionLinea", { ocup: nd > 0 ? pct1(no / nd) : "—" })}{" "}
                    {r.revenue_anual > 0 ? t("margen", { pct: pct1((r.revenue_anual - r.costo_anual) / r.revenue_anual) }) : t("sinIngreso")}
                  </div>
                  {r.categorias.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-disabled)" }}>
                      {r.categorias.map(c => `${c.code} ${c.name} (${c.units})`).join(" · ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── Detalle mensual ──────────────────────────────────────────── */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 30, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{t("monthByMonth")}</h2>
            {METRICAS.map(m => (
              <button key={m.key} onClick={() => setMetrica(m.key)}
                style={{ padding: "5px 12px", fontSize: 12, borderRadius: 6, cursor: "pointer", background: metrica === m.key ? GOLD : "transparent", color: metrica === m.key ? "#1a1a1a" : "var(--text-secondary)", border: `1px solid ${metrica === m.key ? GOLD : "var(--border-medium)"}`, fontWeight: metrica === m.key ? 700 : 500 }}>
                {t(m.labelKey)}
              </button>
            ))}
          </div>

          <div className="fin-sticky" style={{ marginTop: 12, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 980 }}>
              <thead>
                <tr>
                  <th style={{ ...th, minWidth: 180 }}>Set</th>
                  {MESES.map(m => <th key={m} style={thNum}>{m}</th>)}
                  <th style={thNum}>{tc("year")}</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map(r => (
                  <tr key={r.key}>
                    <td style={{ ...td, fontWeight: r.es_residuo ? 500 : 700 }}>{r.name}</td>
                    {serie(r).map((v, m) => <td key={m} style={tdNum}>{money(v)}</td>)}
                    <td style={{ ...tdNum, fontWeight: 700 }}>
                      {money(serie(r).reduce((a, b) => a + b, 0))}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td style={{ ...td, fontWeight: 800, borderTop: "2px solid var(--border-medium)" }}>
                    {t("consolidado")}
                    <div style={{ fontWeight: 400, fontSize: 10.5, color: "var(--text-secondary)" }}>
                      {t("loQueVeElPl")}
                    </div>
                  </td>
                  {Array.from({ length: 12 }, (_, m) => (
                    <td key={m} style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)" }}>
                      {money(data.rows.reduce((a, r) => a + serie(r)[m], 0))}
                    </td>
                  ))}
                  <td style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)", color: GOLD }}>
                    {money(data.rows.reduce((a, r) => a + serie(r).reduce((x, y) => x + y, 0), 0))}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12, maxWidth: "76ch" }}>
            {t.rich("notaResiduo", { b: (c) => <b>{c}</b> })}
          </p>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8, maxWidth: "76ch" }}>
            {t.rich("notaSuma", { b: (c) => <b>{c}</b> })}
          </p>
        </>
      )}
    </div>
  );
}
