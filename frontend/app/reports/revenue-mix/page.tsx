"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getPLCompare, getPLMonthly,
  type Scenario, type PLCompare, type PLColumn,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
/** El ORDEN de despliegue y la etiqueta. Ya NO es la lista de qué se muestra:
 *  lo que el motor traiga y no esté acá sale al final, en vez de perderse.
 *
 *  ⚠️ Tres cosas estaban mal acá:
 *   · `REV_TRANSPORT` **no existe**. La línea es `REV_TRANSPORTATION`; ese
 *     código solo vive como alias legacy. Esa fila mostraba $0 desde siempre,
 *     en pantalla y en el Excel. Bug viejo, anterior al corte del A&B.
 *   · Faltaban 8 líneas de ingreso. El TOTAL sí sale de `TOTAL_REVENUES`, así
 *     que el total quedaba bien y **las filas no sumaban al total** — sin fila
 *     residual ni aviso, o sea invisible.
 *   · La etiqueta «F&B (Food + Beverage + Misc)» mentía: desde el corte
 *     `REV_FB` es solo comida.
 */
const REV: [string, string][] = [
  ["REV_ROOMS", "Rooms"],
  ["REV_ROOMS_OTHER", "Other Rooms Revenue"],
  ["REV_FB", "F&B Food"],
  ["REV_FB_BEV", "F&B Beverage"],
  ["REV_FB_MISC", "F&B Miscellaneous"],
  ["REV_PRIVATE_BAR", "Private Bar"],
  ["REV_SPA", "Spa"],
  ["REV_TOURS", "Tours"],
  ["REV_TIENDA", "Tienda"],
  ["REV_RETAIL", "Gift Shop"],
  ["REV_TRANSPORTATION", "Transportation"],
  ["REV_LAUNDRY", "Laundry"],
  ["REV_INNOCEANA", "Innoceana"],
  ["REV_CROWTHER_LAB", "Crowther Lab"],
  ["REV_CLARO_HUERTA", "Claro del Bosque"],
  ["REV_CLUB", "Club Madresal"],
  ["REV_AREC", "Área Recreativa"],
  ["REV_SUSTAINABILITY", "Sustainability Fee"],
  ["REV_MISC_OTHER", "Other / Misc Revenue"],
];
const money0 = (v: number) => { const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return v < 0 ? `(${s})` : s; };
const pctv = (v: number | null) => v == null ? "n/a" : (v >= 0 ? "" : "-") + Math.abs(v * 100).toFixed(0) + "%";

export default function RevenueMixPage() {
  const tc = useTranslations("common");
  const t = useTranslations("revMix");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla —con su
  // propia llave, o uno le pisaria el escenario al otro— y si nunca se eligio
  // abre con el preferido del owner para ese papel.
  const [actId, setActId] = useEscenarioDe("reports/revenue-mix:actual", scenarios, "actual");
  const [budId, setBudId] = useEscenarioDe("reports/revenue-mix:budget", scenarios, "budget", undefined, true);
  // El "Reforecast" es la proyeccion del año en curso: mismo papel que cualquier
  // otro forecast, y por eso lo elige la regla y no un `version` que diga
  // "reforecast" — ese nombre no lo garantiza nadie.
  const [rfId, setRfId] = useEscenarioDe("reports/revenue-mix:forecast", scenarios, "forecast");
  const [month, setMonth] = useState(5);
  const [data, setData] = useState<PLCompare | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La elección de los tres escenarios la hace `useEscenarioDe` cuando
        // llega la lista: acá solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  // Mes por defecto = último mes con revenue del Actual. Se calcula UNA sola vez:
  // después manda el selector de mes, y recalcularlo al cambiar de escenario le
  // movería el mes al usuario por debajo de la mano.
  const mesAuto = useRef(false);
  useEffect(() => {
    if (!actId || mesAuto.current) return;
    mesAuto.current = true;
    (async () => {
      try {
        const pm = await getPLMonthly(actId);
        let maxM = 0;
        pm.months.forEach(m => { const t = m.lines.find(l => l.line_code === "TOTAL_REVENUES")?.amount_usd ?? 0; if (t) maxM = Math.max(maxM, m.month); });
        if (maxM) setMonth(maxM);
      } catch { /* si no hay mensual, queda el mes que ya estaba */ }
    })();
  }, [actId]);

  const load = useCallback(async (aid: string, bid: string, rid: string, m: number) => {
    if (!aid || !bid) return;
    setLoading(true); setError(null);
    const ids = rid && rid !== aid && rid !== bid ? [aid, bid, rid] : [aid, bid];
    try { setData(await getPLCompare(ids, m)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (actId && budId) load(actId, budId, rfId, month); }, [actId, budId, rfId, month, load]);

  const av = data?.versions.find(v => v.scenario_id === actId);
  const bv = data?.versions.find(v => v.scenario_id === budId);
  const rv = data?.versions.find(v => v.scenario_id === rfId);
  const showRf = !!rfId && !!rv;
  const amt = (col: PLColumn | undefined, code: string) => col?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;
  const pc = (a: number, b: number) => b ? (a - b) / b : (a ? null : 0);   // var % (a vs b)

  /** Las líneas del motor que no están en `REV`. No se pierden: van al final.
   *  Una lista fija se queda corta callada cada vez que nace una línea. */
  const extras = useMemo(() => {
    const conocidas = new Set(REV.map(([c]) => c));
    const vistas = new Map<string, string>();
    for (const v of [av, bv, rv]) {
      for (const h of ["month", "ytd", "full"] as const) {
        for (const l of v?.[h]?.lines ?? []) {
          if (l.line_code.startsWith("REV_") && !conocidas.has(l.line_code)) {
            vistas.set(l.line_code, l.line_name || l.line_code);
          }
        }
      }
    }
    return Array.from(vistas.entries()) as [string, string][];
  }, [av, bv, rv]);

  const rows = useMemo(() => [...REV, ...extras].map(([code, label]) => {
    const aM = amt(av?.month, code), bM = amt(bv?.month, code), rM = amt(rv?.month, code);
    const aY = amt(av?.ytd, code), bY = amt(bv?.ytd, code), rY = amt(rv?.ytd, code);
    return { code, label,
             aM, bM, rM, vM: aM - bM, vMp: pc(aM, bM), vMr: aM - rM, vMrp: pc(aM, rM),
             aY, bY, rY, vY: aY - bY, vYp: pc(aY, bY), vYr: aY - rY, vYrp: pc(aY, rY) };
  }), [av, bv, rv, extras]); // eslint-disable-line react-hooks/exhaustive-deps

  const tot = useMemo(() => ({
    aM: amt(av?.month, "TOTAL_REVENUES"), bM: amt(bv?.month, "TOTAL_REVENUES"), rM: amt(rv?.month, "TOTAL_REVENUES"),
    aY: amt(av?.ytd, "TOTAL_REVENUES"), bY: amt(bv?.ytd, "TOTAL_REVENUES"), rY: amt(rv?.ytd, "TOTAL_REVENUES"),
  }), [av, bv, rv]); // eslint-disable-line react-hooks/exhaustive-deps
  const totVM = tot.aM - tot.bM, totVY = tot.aY - tot.bY;
  const totVMr = tot.aM - tot.rM, totVYr = tot.aY - tot.rY;
  const growM = tot.bM ? totVM / tot.bM : null, growY = tot.bY ? totVY / tot.bY : null;

  const monthLeaders = [...rows].filter(r => r.vM > 0).sort((a, b) => b.vM - a.vM).slice(0, 5);
  const ytdLeaders = [...rows].filter(r => r.vY > 0).sort((a, b) => b.vY - a.vY).slice(0, 5);
  const negatives = [...rows].filter(r => r.vY < -1).sort((a, b) => a.vY - b.vY).slice(0, 4);
  const drivers = ytdLeaders.slice(0, 3).map(r => r.label.replace(/ \(.*\)/, "")).join(", ") || "—";

  /* Las dos mitades del cuadro (mes y YTD) con sus columnas de comparación y
     variación, más la columna del Reforecast cuando está elegido. Los % van como
     fracción y `null` cuando la base es cero: eso es "no aplica", no un 0%. */
  async function bajarExcel() {
    if (!data) return;
    const mesLbl = MONTHS_EN[month - 1];
    const linea = (r: typeof rows[number]): (number | null)[] => [
      r.aM, r.bM, r.vM, r.vMp, ...(showRf ? [r.rM, r.vMrp] : []),
      r.aY, r.bY, r.vY, r.vYp, ...(showRf ? [r.rY, r.vYrp] : []),
    ];
    const filas: FilaCuadro[] = rows.map(r => ({ label: r.label, nivel: 1, valores: linea(r) }));
    filas.push({
      label: "TOTAL", nivel: 0, es_total: true,
      valores: [
        tot.aM, tot.bM, totVM, growM, ...(showRf ? [tot.rM, pc(tot.aM, tot.rM)] : []),
        tot.aY, tot.bY, totVY, growY, ...(showRf ? [tot.rY, pc(tot.aY, tot.rY)] : []),
      ],
    });

    // Lo que la pantalla resume en las tarjetas, en número y con su propio formato.
    const insights: FilaCuadro[] = [
      { label: t("indicadores"), nivel: 0, es_total: true, valores: [null] },
      { label: `Revenue ${MONTHS[month - 1]} (Actual)`, nivel: 1, valores: [tot.aM] },
      { label: `Revenue ${MONTHS[month - 1]} · var % vs Budget`, nivel: 1, formato: "pct", valores: [growM] },
      { label: "Revenue YTD (Actual)", nivel: 1, valores: [tot.aY] },
      { label: "Revenue YTD · var % vs Budget", nivel: 1, formato: "pct", valores: [growY] },
      { label: t("lideresMesExcel", { mes: MONTHS[month - 1] }), nivel: 0, es_total: true, valores: [null] },
      ...(monthLeaders.length
        ? monthLeaders.map((r, i) => ({ label: `${i + 1}. ${r.label}`, nivel: 1, valores: [r.vM] }))
        : [{ label: "—", nivel: 1, valores: [null] }]),
      { label: t("lideresYtdExcel"), nivel: 0, es_total: true, valores: [null] },
      ...(ytdLeaders.length
        ? ytdLeaders.map((r, i) => ({ label: `${i + 1}. ${r.label}`, nivel: 1, valores: [r.vY] }))
        : [{ label: "—", nivel: 1, valores: [null] }]),
      { label: t("negativosTitulo"), nivel: 0, es_total: true, valores: [null] },
      ...(negatives.length
        ? negatives.map((r, i) => ({ label: `${i + 1}. ${r.label}`, nivel: 1, valores: [r.vY] }))
        : [{ label: t("sinNegativos"), nivel: 1, valores: [null] }]),
    ];

    const grupo = (t2: string) => [
      { label: `${t2} · Actual`, ancho: 15, formato: "usd2" as const },
      { label: `${t2} · Budget`, ancho: 15, formato: "usd2" as const },
      { label: `${t2} · Var $`, ancho: 15, formato: "usd2" as const },
      { label: `${t2} · Var %`, ancho: 11, formato: "pct" as const },
      ...(showRf ? [
        { label: `${t2} · Reforecast`, ancho: 15, formato: "usd2" as const },
        { label: `${t2} · Var % vs RF`, ancho: 13, formato: "pct" as const },
      ] : []),
    ];
    try {
      await bajarCuadros(`Revenue_Mix_${mesLbl}`, [
        {
          titulo: `Revenue Mix Performance — ${mesLbl} ${av?.year ?? ""}`,
          subtitulo: `Actual vs Budget${showRf ? " vs Reforecast" : ""}${t("excelSubtituloCola")}`,
          hoja: "Revenue Mix",
          columnas: [
            { label: t("revenueLine"), ancho: 34, formato: "texto" },
            ...grupo(t("mesMensual", { mes: mesLbl })),
            ...grupo(`YTD ${mesLbl}`),
          ],
          filas,
        },
        {
          titulo: t("resumenEjecutivo"), subtitulo: `${mesLbl} ${av?.year ?? ""} · USD`, hoja: t("resumenHoja"),
          columnas: [{ label: tc("concept"), ancho: 44, formato: "texto" }, { label: t("monto"), ancho: 16, formato: "usd2" }],
          filas: insights,
        },
      ]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { padding: "7px 10px", fontSize: 10.5, color: "#fff", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.3, textAlign: "right", whiteSpace: "nowrap" };
  const td: React.CSSProperties = { padding: "6px 10px", fontSize: 12.5, textAlign: "right", whiteSpace: "nowrap" };
  const varColor = (v: number) => Math.abs(v) < 1 ? "var(--text-secondary)" : v >= 0 ? "var(--positive)" : "var(--negative)";
  const insightCard: React.CSSProperties = { background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "12px 14px", marginBottom: 12 };

  return (
    <div className="print-dashboard pag pag-ancha" style={{ padding: "22px 26px 48px" }}>
      <IrA esc={budId} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Revenue Mix <span style={{ color: "var(--brand)" }}>Performance</span> — {MONTHS_EN[month-1]} {av?.year ?? ""}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>Actual vs Budget{showRf ? " vs Reforecast" : ""}{t("subtituloCola")}</p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{tc("print")}</button>
          <button onClick={bajarExcel} disabled={!data} title={t("excelBtnTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: data ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", alignSelf: "flex-end", opacity: data ? 1 : 0.5 }}>⬇ Excel</button>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("month")}</span><select value={month} onChange={e => setMonth(Number(e.target.value))} style={sel}>{MONTHS.map((m, i) => <option key={i} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Actual</span><select value={actId} onChange={e => setActId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Budget</span><select value={budId} onChange={e => setBudId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Reforecast</span><select value={rfId} onChange={e => setRfId(e.target.value)} style={sel}><option value="" style={{ background: "var(--bg-input)" }}>{tc("noneDash")}</option>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        </div>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {/* KPI strip */}
      {!loading && data && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          {[
            [`Revenue ${MONTHS[month-1]}`, money0(tot.aM), growM, "var(--brand)"],
            ["Revenue YTD", money0(tot.aY), growY, "var(--positive)"],
          ].map(([l, v, g, c], i) => (
            <div key={i} style={{ flex: "1 1 220px", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 6 }}>{l as string}</div>
              <div className="mono" style={{ fontSize: 22, fontWeight: 800, color: c as string }}>{v as string}</div>
              {g != null && <div style={{ fontSize: 12, fontWeight: 700, color: (g as number) >= 0 ? "var(--positive)" : "var(--negative)", marginTop: 2 }}>{(g as number) >= 0 ? "▲" : "▼"} {Math.abs((g as number) * 100).toFixed(0)}% vs Budget</div>}
            </div>
          ))}
          <div style={{ flex: "2 1 320px", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 6 }}>{t("topDrivers")}</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: "var(--brand)" }}>🏆 {drivers}</div>
          </div>
        </div>
      )}

      {!loading && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Tabla principal */}
          <div style={{ width: "100%", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden" }}>
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: "var(--bg-header)" }}>
                    <th style={{ ...th, textAlign: "left" }} rowSpan={2}>{t("revenueLine")}</th>
                    <th style={{ ...th, textAlign: "center", borderLeft: "1px solid var(--border-medium)", color: "var(--brand)" }} colSpan={showRf ? 6 : 4}>{t("mesMensual", { mes: MONTHS_EN[month-1] })}</th>
                    <th style={{ ...th, textAlign: "center", borderLeft: "1px solid var(--border-medium)", color: "var(--positive)" }} colSpan={showRf ? 6 : 4}>YTD {MONTHS_EN[month-1]}</th>
                  </tr>
                  <tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                    <th style={{ ...th, borderLeft: "1px solid var(--border-medium)" }}>Actual</th><th style={th}>Budget</th><th style={th}>Var $</th><th style={th}>Var %</th>
                    {showRf && <><th style={{ ...th, color: "#d8a657" }}>Reforecast</th><th style={{ ...th, color: "#d8a657" }}>Var %</th></>}
                    <th style={{ ...th, borderLeft: "1px solid var(--border-medium)" }}>Actual</th><th style={th}>Budget</th><th style={th}>Var $</th><th style={th}>Var %</th>
                    {showRf && <><th style={{ ...th, color: "#d8a657" }}>Reforecast</th><th style={{ ...th, color: "#d8a657" }}>Var %</th></>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.code} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "6px 12px", fontSize: 12.5, fontWeight: 600, color: "var(--text-primary)" }}>{r.label}</td>
                      <td className="mono" style={{ ...td, borderLeft: "1px solid var(--border-medium)" }}>{money0(r.aM)}</td>
                      <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{money0(r.bM)}</td>
                      <td className="mono" style={{ ...td, fontWeight: 700, color: varColor(r.vM) }}>{money0(r.vM)}</td>
                      <td className="mono" style={{ ...td, color: varColor(r.vM) }}>{pctv(r.vMp)}</td>
                      {showRf && <><td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{money0(r.rM)}</td><td className="mono" style={{ ...td, color: varColor(r.vMr) }}>{pctv(r.vMrp)}</td></>}
                      <td className="mono" style={{ ...td, borderLeft: "1px solid var(--border-medium)" }}>{money0(r.aY)}</td>
                      <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{money0(r.bY)}</td>
                      <td className="mono" style={{ ...td, fontWeight: 700, color: varColor(r.vY) }}>{money0(r.vY)}</td>
                      <td className="mono" style={{ ...td, color: varColor(r.vY) }}>{pctv(r.vYp)}</td>
                      {showRf && <><td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{money0(r.rY)}</td><td className="mono" style={{ ...td, color: varColor(r.vYr) }}>{pctv(r.vYrp)}</td></>}
                    </tr>
                  ))}
                  <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(58,111,216,0.08)", fontWeight: 800 }}>
                    <td style={{ padding: "7px 12px", fontSize: 13, fontWeight: 800 }}>TOTAL</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, borderLeft: "1px solid var(--border-medium)" }}>{money0(tot.aM)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{money0(tot.bM)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: varColor(totVM) }}>{money0(totVM)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: varColor(totVM) }}>{pctv(growM)}</td>
                    {showRf && <><td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{money0(tot.rM)}</td><td className="mono" style={{ ...td, fontWeight: 800, color: varColor(totVMr) }}>{pctv(pc(tot.aM, tot.rM))}</td></>}
                    <td className="mono" style={{ ...td, fontWeight: 800, borderLeft: "1px solid var(--border-medium)" }}>{money0(tot.aY)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{money0(tot.bY)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: varColor(totVY) }}>{money0(totVY)}</td>
                    <td className="mono" style={{ ...td, fontWeight: 800, color: varColor(totVY) }}>{pctv(growY)}</td>
                    {showRf && <><td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{money0(tot.rY)}</td><td className="mono" style={{ ...td, fontWeight: 800, color: varColor(totVYr) }}>{pctv(pc(tot.aY, tot.rY))}</td></>}
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={{ padding: "8px 14px", fontSize: 11, color: "var(--text-secondary)", fontStyle: "italic", borderTop: "1px solid var(--border-medium)" }}>{t("nota")}</div>
          </div>

          {/* Executive insights */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
            <div style={{ ...insightCard, flex: "1 1 300px", marginBottom: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--positive)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>{t("lideresMes", { mes: MONTHS[month-1] })}</div>
              {monthLeaders.length ? monthLeaders.map((r, i) => (
                <div key={r.code} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, padding: "3px 0" }}><span style={{ color: "var(--text-primary)" }}>{i+1}. {r.label.replace(/ \(.*\)/, "")}</span><span className="mono" style={{ fontWeight: 700, color: "var(--positive)" }}>+{money0(r.vM)}</span></div>
              )) : <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>—</div>}
            </div>
            <div style={{ ...insightCard, flex: "1 1 300px", marginBottom: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--positive)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>{t("ytdLeaders")}</div>
              {ytdLeaders.length ? ytdLeaders.map((r, i) => (
                <div key={r.code} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, padding: "3px 0" }}><span style={{ color: "var(--text-primary)" }}>{i+1}. {r.label.replace(/ \(.*\)/, "")}</span><span className="mono" style={{ fontWeight: 700, color: "var(--positive)" }}>+{money0(r.vY)}</span></div>
              )) : <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>—</div>}
            </div>
            <div style={{ ...insightCard, flex: "1 1 300px", marginBottom: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--negative)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>{t("negativosCard")}</div>
              {negatives.length ? negatives.map((r, i) => (
                <div key={r.code} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, padding: "3px 0" }}><span style={{ color: "var(--text-primary)" }}>{i+1}. {r.label.replace(/ \(.*\)/, "")}</span><span className="mono" style={{ fontWeight: 700, color: "var(--negative)" }}>{money0(r.vY)}</span></div>
              )) : <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("sinNegativosPunto")}</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
