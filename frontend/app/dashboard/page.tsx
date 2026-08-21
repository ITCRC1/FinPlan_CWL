"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line,
} from "recharts";
import { getScenarios, getPLMonthly, getFlowThrough, type Scenario, type PLMonthly, type FlowThrough } from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

// Los meses salen de `months.short` del catálogo; esto queda de respaldo.
const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
function fmtK(n: number) {
  if (Math.abs(n) >= 1_000_000) return `$${(n/1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000)     return `$${Math.round(n/1_000)}K`;
  return `$${Math.round(n)}`;
}
function fmtUSD(n: number) {
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}
function fmtPct(n: number) { return (n * 100).toFixed(1) + "%"; }

function lineVal(pl: PLMonthly, code: string, m: number, ytd = false): number {
  if (m === 0) return pl.annual[code] ?? 0;
  if (ytd) {
    let s = 0;
    for (let mm = 1; mm <= m; mm++)
      s += pl.months.find(x => x.month === mm)?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;
    return s;
  }
  return pl.months.find(x => x.month === m)?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;
}
function kpiOcc(pl: PLMonthly, m: number, ytd: boolean) {
  const end = m === 0 ? 12 : m; const useRange = m === 0 || ytd;
  if (!useRange) return pl.months.find(x => x.month === m)?.kpis.occupancy_pct ?? 0;
  let avail = 0, occ = 0;
  for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) { avail += k.rooms_available; occ += k.rooms_occupied; } }
  return avail ? occ / avail : 0;
}
function kpiADR(pl: PLMonthly, m: number, ytd: boolean) {
  const end = m === 0 ? 12 : m; const useRange = m === 0 || ytd;
  if (!useRange) return pl.months.find(x => x.month === m)?.kpis.adr ?? 0;
  let occ = 0, rev = 0;
  for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) { occ += k.rooms_occupied; rev += k.adr * k.rooms_occupied; } }
  return occ ? rev / occ : 0;
}
function kpiRevPAR(pl: PLMonthly, m: number, ytd: boolean) {
  const end = m === 0 ? 12 : m; const useRange = m === 0 || ytd;
  if (!useRange) return pl.months.find(x => x.month === m)?.kpis.revpar ?? 0;
  let avail = 0, rev = 0;
  for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) { avail += k.rooms_available; rev += k.adr * k.rooms_occupied; } }
  return avail ? rev / avail : 0;
}

const SEL: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };

const PL_ROWS = [
  { code: "TOTAL_REVENUES",           label: "Total Revenue",        strong: false },
  { code: "TOTAL_OPERATING_EXPENSES", label: "Total Operating Exp.", strong: false },
  { code: "OPERATING_PROFIT",          label: "Operating Profit",     strong: false },
  { code: "TOTAL_OVERHEAD_EXPENSES",   label: "Total Overhead",       strong: false },
  { code: "TOTAL_GOP",                 label: "GOP",                  strong: true  },
  { code: "TOTAL_NON_OP_EXPENSES",     label: "Non-Op Expenses",      strong: false },
  { code: "EBITDA_BEFORE_CAPITAL",     label: "EBITDA",               strong: true  },
  { code: "EBITDA_AFTER_CAPITAL",      label: "EBITDA after CapEx",   strong: false },
  { code: "EBT",                       label: "EBT",                  strong: false },
  { code: "NET_PROFIT",                label: "Net Profit",           strong: true  },
];

export default function DashboardPage() {
  const hotel = useHotel();
  const t  = useTranslations("dashboard");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [plById, setPlById]       = useState<Record<string, PLMonthly>>({});
  // Los cuatro selectores ofrecen TODOS los escenarios.
  //
  // ⚠️ Antes filtraba a Budget/Forecast de 2026 en adelante, y eran DOS filtros
  // que se sumaban: el tipo dejaba fuera a los ACTUAL y el año dejaba fuera a
  // 2025 y 2024. Resultado: los dos años cerrados contra los que el owner
  // quiere comparar **no se podían elegir ni a mano** (owner, 2026-08-19: «no
  // veo varias versiones acá»). No se veía como un filtro: se veía como si esos
  // escenarios no existieran.
  const selectable = useMemo(() => scenarios, [scenarios]);
  // El principal y la primera comparacion si tienen un papel — el forecast en
  // curso contra el presupuesto en armado — y se acuerdan de lo ultimo elegido.
  const [mainId, setMainId]       = useEscenarioDe("dashboard:main",  selectable, "budget", undefined, true);
  const [compId, setCompId]       = useEscenarioDe("dashboard:comp",  selectable, "forecast");
  const [comp2Id, setComp2Id]     = useEscenarioDe("dashboard:comp2", selectable, "actual");
  const [comp3Id, setComp3Id]     = useEscenarioDe("dashboard:comp3", selectable, "actualAnterior");
  const [flow, setFlow]           = useState<FlowThrough | null>(null);
  const [month, setMonth]         = useState(0);
  const [ytd, setYtd]             = useState(false);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        if (!all.length) { setError(tc("noScenarios", { hotel: hotel.id })); return; }
        // El orden es el del dropdown, no la elección: quién abre en cada
        // selector lo deciden `useEscenarioDe` y el efecto de abajo. Los P&L
        // los trae el efecto que llena `plById` con lo que falte.
        setScenarios([...all].sort((a, b) =>
          a.year !== b.year ? b.year - a.year :
          (["ACTUAL","BUDGET","FORECAST"].indexOf(a.type) - ["ACTUAL","BUDGET","FORECAST"].indexOf(b.type))
        ));
      } catch (e) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // ⚠️ Acá vivía el defecto que el owner vio en pantalla (2026-08-19).
  //
  // Las comparaciones 2 y 3 se llenaban «con lo que quedara libre» de la lista,
  // y la lista va de mayor a menor año: lo que quedaba libre era **Budget 2035
  // y Budget 2034**, que están vacíos. El Dashboard abría comparando contra
  // cero y mostraba variaciones de +$5,2M como si el presupuesto entero fuera
  // ganancia. No fallaba — comparaba contra escenarios reales, solo que sin un
  // número adentro.
  //
  // Ahora los cuatro selectores tienen el papel que el owner pidió
  // («Budget 2027, Forecast 2026, Actual 2025, Actual 2024»), resuelto por
  // `lib/escenarioPreferido`, que es la única regla de con-cuál-abrir que tiene
  // la app. Y como los cuatro pasan por `useEscenarioDe`, lo que el owner
  // cambie a mano se recuerda: la regla decide la PRIMERA vez, no siempre.

  useEffect(() => {
    const toLoad = [mainId, compId, comp2Id].filter(id => id && !plById[id]);
    if (!toLoad.length) return;
    (async () => {
      const pls = await Promise.all(toLoad.map(async id => [id, await getPLMonthly(id)] as const));
      setPlById(prev => ({ ...prev, ...Object.fromEntries(pls) }));
    })();
  }, [mainId, compId, comp2Id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mainId) { setFlow(null); return; }
    const uy = ytd && month > 0;
    getFlowThrough(mainId, month, uy, [compId, comp2Id, comp3Id]).then(setFlow).catch(() => setFlow(null));
  }, [mainId, compId, comp2Id, comp3Id, month, ytd]);

  const mainPL = plById[mainId] ?? null;
  const compPL = plById[compId] ?? null;
  const comp2PL = plById[comp2Id] ?? null;
  const useYtd = ytd && month > 0;

  // Meses visibles según el selector: Full Year = 1..12; YTD = 1..mes;
  // Mes = el mes elegido + el anterior (contexto; enero queda solo, no hay previo).
  const chartData = useMemo(() => {
    const ms = month === 0 ? Array.from({ length: 12 }, (_, i) => i + 1)
             : useYtd     ? Array.from({ length: month }, (_, i) => i + 1)
             : month > 1   ? [month - 1, month]
             :              [month];
    return ms.map(m => ({
      label: MONTHS[m - 1],
      main_rev: mainPL ? lineVal(mainPL, "TOTAL_REVENUES", m) / 1000 : null,
      comp_rev: compPL ? lineVal(compPL, "TOTAL_REVENUES", m) / 1000 : null,
      comp2_rev: comp2PL ? lineVal(comp2PL, "TOTAL_REVENUES", m) / 1000 : null,
      main_gop: mainPL ? lineVal(mainPL, "TOTAL_GOP", m) / 1000 : null,
      comp_gop: compPL ? lineVal(compPL, "TOTAL_GOP", m) / 1000 : null,
      comp2_gop: comp2PL ? lineVal(comp2PL, "TOTAL_GOP", m) / 1000 : null,
    }));
  }, [mainPL, compPL, comp2PL, month, useYtd]);

  const gopMargin = useMemo(() => {
    if (!mainPL) return null;
    const rev = lineVal(mainPL, "TOTAL_REVENUES", month, useYtd), gop = lineVal(mainPL, "TOTAL_GOP", month, useYtd);
    return rev ? gop / rev : null;
  }, [mainPL, month, useYtd]);

  const mainScn = scenarios.find(s => s.id === mainId);
  const compScn = scenarios.find(s => s.id === compId);
  const comp2Scn = scenarios.find(s => s.id === comp2Id);

  // Las 2 comparaciones para las tarjetas KPI (Comparar 1 y 2)
  const cLab = compScn ? scnLabel(compScn) : t("compareWith");
  const c2Lab = comp2Scn ? scnLabel(comp2Scn) : t("compare2");
  const lineComps = (code: string) => [
    { value: compPL ? lineVal(compPL, code, month, useYtd) : null, label: cLab },
    { value: comp2PL ? lineVal(comp2PL, code, month, useYtd) : null, label: c2Lab },
  ];
  const kpiComps = (fn: (pl: PLMonthly, m: number, y: boolean) => number) => [
    { value: compPL ? fn(compPL, month, useYtd) : null, label: cLab },
    { value: comp2PL ? fn(comp2PL, month, useYtd) : null, label: c2Lab },
  ];

  if (loading) return <div style={{ padding: 40, color: "var(--text-secondary)" }}>{t("loading")}</div>;
  if (error)   return <div style={{ padding: 40, color: "var(--negative)" }}>{error}</div>;

  const viewLabel = month === 0 ? tc("fullYear") : (useYtd ? "YTD " : "") + MONTHS[month - 1];

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // El Dashboard es más tarjeta que tabla, así que baja lo que sí es tabular:
  // las tarjetas KPI (que son una tabla de métrica × versión), el P&L resumen,
  // la serie mensual que alimenta los dos gráficos y el Flow Through. Todo con
  // la vista (Full Year / mes / YTD) y las versiones que estén seleccionadas.
  //
  // El error va por `alert` a propósito: `setError` en esta pantalla reemplaza
  // TODO el contenido por el mensaje, y perder el dashboard porque falló una
  // descarga sería peor que el fallo.
  async function bajarExcel() {
    const nMain = mainScn ? scnLabel(mainScn) : t("main");
    const cuadros: Cuadro[] = [];
    const usd: FormatoCol = "usd";

    // 1) Tarjetas KPI — cada fila tiene su unidad, por eso el formato va por fila.
    if (mainPL) {
      const kpiFila = (label: string, formato: FormatoCol, get: (pl: PLMonthly) => number): FilaCuadro => {
        const v1 = get(mainPL);
        const v2 = compPL ? get(compPL) : null, v3 = comp2PL ? get(comp2PL) : null;
        return {
          label, formato,
          valores: [v1,
            ...(compPL ? [v2, v2 !== null ? v1 - v2 : null] : []),
            ...(comp2PL ? [v3, v3 !== null ? v1 - v3 : null] : [])],
        };
      };
      cuadros.push({
        titulo: `KPIs · ${viewLabel}`,
        subtitulo: t("xls.kpisSub", { esc: nMain }),
        hoja: "KPIs",
        columnas: [
          { label: tc("indicator"), ancho: 24, formato: "texto" },
          { label: nMain, ancho: 20, formato: usd },
          ...(compPL ? [{ label: cLab, ancho: 20, formato: usd }, { label: `Δ vs ${cLab}`, ancho: 18, formato: usd }] : []),
          ...(comp2PL ? [{ label: c2Lab, ancho: 20, formato: usd }, { label: `Δ vs ${c2Lab}`, ancho: 18, formato: usd }] : []),
        ],
        filas: [
          kpiFila("Total Revenue", "usd", pl => lineVal(pl, "TOTAL_REVENUES", month, useYtd)),
          kpiFila("GOP", "usd", pl => lineVal(pl, "TOTAL_GOP", month, useYtd)),
          kpiFila("Net Profit", "usd", pl => lineVal(pl, "NET_PROFIT", month, useYtd)),
          kpiFila("Occupancy %", "pct", pl => kpiOcc(pl, month, useYtd)),
          kpiFila("ADR", "usd2", pl => kpiADR(pl, month, useYtd)),
          kpiFila("RevPAR", "usd2", pl => kpiRevPAR(pl, month, useYtd)),
        ],
      });

      // 2) P&L resumen — todas las filas en dólares, así que el formato va por columna.
      cuadros.push({
        titulo: t("plSummary", { vista: viewLabel }),
        subtitulo: t("xls.plSub", { esc: nMain }),
        hoja: t("xls.plSheet"),
        columnas: [
          { label: tc("concept"), ancho: 32, formato: "texto" },
          { label: nMain, ancho: 20, formato: usd },
          ...(compPL ? [{ label: cLab, ancho: 20, formato: usd }, { label: `Var $ vs ${cLab}`, ancho: 18, formato: usd }, { label: "Var %", ancho: 11, formato: "pct" as const }] : []),
          ...(comp2PL ? [{ label: c2Lab, ancho: 20, formato: usd }, { label: `Var $ vs ${c2Lab}`, ancho: 18, formato: usd }, { label: "Var %", ancho: 11, formato: "pct" as const }] : []),
        ],
        filas: PL_ROWS.map(row => {
          const v1 = lineVal(mainPL, row.code, month, useYtd);
          const v2 = compPL ? lineVal(compPL, row.code, month, useYtd) : null;
          const v3 = comp2PL ? lineVal(comp2PL, row.code, month, useYtd) : null;
          const d = v2 !== null ? v1 - v2 : null, d2 = v3 !== null ? v1 - v3 : null;
          return {
            label: row.label, es_total: row.strong,
            valores: [v1,
              ...(compPL ? [v2, d, d !== null && v2 && Math.abs(v2) > 0.5 ? d / Math.abs(v2) : null] : []),
              ...(comp2PL ? [v3, d2, d2 !== null && v3 && Math.abs(v3) > 0.5 ? d2 / Math.abs(v3) : null] : [])],
          };
        }),
      });

      // 3) La serie que dibujan los dos gráficos, en dólares completos (en pantalla van en $K).
      const ms = month === 0 ? Array.from({ length: 12 }, (_, i) => i + 1)
               : useYtd     ? Array.from({ length: month }, (_, i) => i + 1)
               : month > 1  ? [month - 1, month]
               :              [month];
      cuadros.push({
        titulo: t("xls.monthlyTitle", { vista: viewLabel }),
        subtitulo: t("xls.monthlySub"),
        hoja: t("xls.monthlySheet"),
        columnas: [
          { label: tc("month"), ancho: 14, formato: "texto" },
          { label: `Revenue · ${nMain}`, ancho: 20, formato: usd },
          ...(compPL ? [{ label: `Revenue · ${cLab}`, ancho: 20, formato: usd }] : []),
          ...(comp2PL ? [{ label: `Revenue · ${c2Lab}`, ancho: 20, formato: usd }] : []),
          { label: `GOP · ${nMain}`, ancho: 20, formato: usd },
          ...(compPL ? [{ label: `GOP · ${cLab}`, ancho: 20, formato: usd }] : []),
          ...(comp2PL ? [{ label: `GOP · ${c2Lab}`, ancho: 20, formato: usd }] : []),
        ],
        filas: ms.map(m => ({
          label: MONTHS[m - 1],
          valores: [
            lineVal(mainPL, "TOTAL_REVENUES", m),
            ...(compPL ? [lineVal(compPL, "TOTAL_REVENUES", m)] : []),
            ...(comp2PL ? [lineVal(comp2PL, "TOTAL_REVENUES", m)] : []),
            lineVal(mainPL, "TOTAL_GOP", m),
            ...(compPL ? [lineVal(compPL, "TOTAL_GOP", m)] : []),
            ...(comp2PL ? [lineVal(comp2PL, "TOTAL_GOP", m)] : []),
          ],
        })),
      });
    }

    // 4) Flow Through
    if (flow && flow.has_data && flow.rows.length) {
      cuadros.push({
        titulo: t("flowThrough", { vista: viewLabel }),
        subtitulo: t("xls.flowSub", { esc: nMain }),
        hoja: "Flow Through",
        columnas: [
          { label: tc("concept"), ancho: 32, formato: "texto" },
          ...flow.comparison_ids.map(cid => {
            const cs = scenarios.find(s => s.id === cid);
            return { label: `vs ${cs ? scnLabel(cs) : "—"}`, ancho: 20, formato: usd };
          }),
        ],
        filas: flow.rows.map(r => ({
          label: r.concept,
          es_total: r.concept === "Net Profit" || r.concept === "EBITDA Before Capital",
          valores: r.variances,
        })),
      });
    }

    if (!cuadros.length) { alert(t("xls.noData")); return; }
    try { await bajarCuadros("Dashboard", cuadros); }
    catch (e) { alert(e instanceof Error ? e.message : t("xls.error")); }
  }

  function KpiCard({ label, main, comps, fmt, goodIfPositive = true }: {
    label: string; main: number | null;
    comps: { value: number | null; label: string }[];
    fmt: (n: number) => string; goodIfPositive?: boolean;
  }) {
    return (
      <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "16px 18px" }}>
        <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.6, color: "var(--text-secondary)", textTransform: "uppercase", marginBottom: 10 }}>{label}</div>
        <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: main !== null && main < 0 ? "var(--negative)" : "var(--text-primary)", marginBottom: 6 }}>
          {main !== null ? fmt(main) : "—"}
        </div>
        {comps.map((c, i) => {
          if (c.value === null) return null;
          const delta = main !== null ? main - c.value : null;
          const isGood = delta !== null && (goodIfPositive ? delta >= 0 : delta <= 0);
          const dColor = delta === null || Math.abs(delta) < 0.001 ? "var(--text-secondary)" : (isGood ? "var(--positive)" : "var(--negative)");
          return (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: i > 0 ? 6 : 0 }}>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>{c.label}: {fmt(c.value)}</div>
              {delta !== null && <div className="mono" style={{ fontSize: 11, fontWeight: 600, color: dColor }}>{delta >= 0 ? "+" : ""}{fmt(delta)}</div>}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "28px 32px" }}>
      <IrA esc={mainId} />
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }} title={hotel.nombre}>FinPlan <span style={{ color: "var(--brand)" }}>{hotel.id}</span> — {t("title")}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("subtitle", { vista: viewLabel, hotel: hotel.nombre })}</p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <button onClick={bajarExcel} title={t("excelHint")} style={{
            padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer",
            alignSelf: "flex-end", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
          }}>⬇ Excel</button>
          <button onClick={() => window.print()} style={{
            padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer",
            alignSelf: "flex-end", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)",
          }}>{tc("print")}</button>
          {([[t("main"), mainId, setMainId, false], [t("compareWith"), compId, setCompId, true], [t("compare2"), comp2Id, setComp2Id, true], [t("compare3"), comp3Id, setComp3Id, true]] as const).map(([label, val, set, allowNone]) => (
            <div key={label} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.5, textTransform: "uppercase" }}>{label}</span>
              <select value={val} onChange={e => set(e.target.value)} style={SEL}>
                {allowNone && <option value="" style={{ background: "var(--bg-input)" }}>{tc("none")}</option>}
                {selectable.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* Month selector */}
      <div className="no-print" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 28, flexWrap: "wrap" }}>
        {[tc("fullYear"), ...MONTHS].map((label, i) => (
          <button key={i} onClick={() => setMonth(i)} style={{
            padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer",
            fontWeight: month === i ? 700 : 400,
            background: month === i ? "var(--brand)" : "var(--bg-elevated)",
            color: month === i ? "#fff" : "var(--text-secondary)",
            border: `1px solid ${month === i ? "var(--brand)" : "var(--border-medium)"}`,
          }}>{label}</button>
        ))}
        {month > 0 && <>
          <span style={{ color: "var(--border-medium)", margin: "0 4px" }}>|</span>
          {([tc("month"), "YTD"] as const).map(lbl => {
            const isYtdBtn = lbl === "YTD", active = isYtdBtn === ytd;
            return (
              <button key={lbl} onClick={() => setYtd(isYtdBtn)} style={{
                padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer", fontWeight: 700,
                background: active ? "var(--positive)" : "var(--bg-elevated)",
                color: active ? "#fff" : "var(--text-secondary)",
                border: `1px solid ${active ? "var(--positive)" : "var(--border-medium)"}`,
              }}>{lbl}</button>
            );
          })}
        </>}
      </div>

      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 14, marginBottom: 28 }}>
        <KpiCard label="Total Revenue" main={mainPL ? lineVal(mainPL,"TOTAL_REVENUES",month,useYtd) : null} comps={lineComps("TOTAL_REVENUES")} fmt={fmtK} />
        <KpiCard label="GOP"           main={mainPL ? lineVal(mainPL,"TOTAL_GOP",month,useYtd)       : null} comps={lineComps("TOTAL_GOP")} fmt={fmtK} />
        <KpiCard label="Net Profit"    main={mainPL ? lineVal(mainPL,"NET_PROFIT",month,useYtd)      : null} comps={lineComps("NET_PROFIT")} fmt={fmtK} />
        <KpiCard label="Occupancy %"   main={mainPL ? kpiOcc(mainPL,month,useYtd)    : null} comps={kpiComps(kpiOcc)} fmt={fmtPct} />
        <KpiCard label="ADR"           main={mainPL ? kpiADR(mainPL,month,useYtd)    : null} comps={kpiComps(kpiADR)} fmt={n => "$" + Math.round(n).toLocaleString()} />
        <KpiCard label="RevPAR"        main={mainPL ? kpiRevPAR(mainPL,month,useYtd) : null} comps={kpiComps(kpiRevPAR)} fmt={n => "$" + Math.round(n).toLocaleString()} />
      </div>

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 28 }}>
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "18px 20px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("monthlyRevenue")}</div>
          <ResponsiveContainer width="100%" height={190}>
            <BarChart data={chartData} barCategoryGap="30%">
              <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}K`} width={46} />
              <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} labelStyle={{ color: "var(--text-primary)", fontWeight: 700 }}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={(v: any, name: any) => [`$${Math.round(Number(v))}K`, String(name).startsWith("comp2") ? (comp2Scn ? scnLabel(comp2Scn) : t("compare2")) : String(name).startsWith("comp") ? (compScn ? scnLabel(compScn) : t("compareWith")) : (mainScn ? scnLabel(mainScn) : t("main"))]} />
              {mainPL && <Bar dataKey="main_rev" fill="#2962FF" radius={[3,3,0,0]} name="main_rev" />}
              {compPL && <Bar dataKey="comp_rev" fill="#1a3f7a" radius={[3,3,0,0]} name="comp_rev" />}
              {comp2PL && <Bar dataKey="comp2_rev" fill="#BA7517" radius={[3,3,0,0]} name="comp2_rev" />}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "18px 20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5 }}>{t("monthlyGop")}</div>
            {gopMargin !== null && <div style={{ fontSize: 11, fontWeight: 700, color: "var(--positive)" }}>{t("margin", { vista: viewLabel })}: {fmtPct(gopMargin)}</div>}
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <LineChart data={chartData}>
              <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}K`} width={46} />
              <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} labelStyle={{ color: "var(--text-primary)", fontWeight: 700 }}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                formatter={(v: any, name: any) => [`$${Math.round(Number(v))}K`, String(name).startsWith("comp2") ? (comp2Scn ? scnLabel(comp2Scn) : t("compare2")) : String(name).startsWith("comp") ? (compScn ? scnLabel(compScn) : t("compareWith")) : (mainScn ? scnLabel(mainScn) : t("main"))]} />
              {mainPL && <Line type="monotone" dataKey="main_gop" stroke="#26A69A" strokeWidth={2} dot={{ r: 3, fill: "#26A69A" }} name="main_gop" />}
              {compPL && <Line type="monotone" dataKey="comp_gop" stroke="#1a5c55" strokeWidth={2} strokeDasharray="4 2" dot={{ r: 2, fill: "#1a5c55" }} name="comp_gop" />}
              {comp2PL && <Line type="monotone" dataKey="comp2_gop" stroke="#BA7517" strokeWidth={2} strokeDasharray="2 2" dot={{ r: 2, fill: "#BA7517" }} name="comp2_gop" />}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Fila inferior: P&L Resumen (izq) + Flow Through (der), lado a lado para imprimir en 1 hoja */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
      {/* P&L Summary table */}
      <div style={{ flex: "2 1 560px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "18px 20px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("plSummary", { vista: viewLabel })}</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
              <th style={{ textAlign: "left", padding: "5px 8px", fontSize: 11, color: "var(--text-secondary)", width: "40%" }} />
              <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>{mainScn ? scnLabel(mainScn) : t("main")}</th>
              {compPL && <>
                <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>{compScn ? scnLabel(compScn) : t("compareWith")}</th>
                <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, color: "var(--text-secondary)" }}>{tc("variance")} $</th>
                <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, color: "var(--text-secondary)" }}>{tc("variance")} %</th>
              </>}
              {comp2PL && <>
                <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>{comp2Scn ? scnLabel(comp2Scn) : t("compare2")}</th>
                <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, color: "var(--text-secondary)" }}>{tc("variance")} $</th>
                <th style={{ textAlign: "right", padding: "5px 8px", fontSize: 11, color: "var(--text-secondary)" }}>{tc("variance")} %</th>
              </>}
            </tr>
          </thead>
          <tbody>
            {PL_ROWS.map(row => {
              const v1 = mainPL ? lineVal(mainPL, row.code, month, useYtd) : null;
              const v2 = compPL ? lineVal(compPL, row.code, month, useYtd) : null;
              const v3 = comp2PL ? lineVal(comp2PL, row.code, month, useYtd) : null;
              const isExp = row.code.includes("EXPENSES");
              const d  = v1 !== null && v2 !== null ? v1 - v2 : null;
              const p  = d !== null && v2 && Math.abs(v2) > 0.5 ? d / Math.abs(v2) : null;
              const vc = d === null || Math.abs(d) < 0.5 ? "var(--text-secondary)" : ((isExp ? d < 0 : d > 0) ? "var(--positive)" : "var(--negative)");
              const d2 = v1 !== null && v3 !== null ? v1 - v3 : null;
              const p2 = d2 !== null && v3 && Math.abs(v3) > 0.5 ? d2 / Math.abs(v3) : null;
              const vc2 = d2 === null || Math.abs(d2) < 0.5 ? "var(--text-secondary)" : ((isExp ? d2 < 0 : d2 > 0) ? "var(--positive)" : "var(--negative)");
              return (
                <tr key={row.code} style={{ borderTop: row.strong ? "1px solid var(--border-medium)" : undefined, background: row.strong ? "rgba(255,255,255,0.02)" : undefined }}>
                  <td style={{ padding: "5px 8px", fontWeight: row.strong ? 700 : 400, color: row.strong ? "var(--text-primary)" : "var(--text-secondary)" }}>{row.label}</td>
                  <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontWeight: row.strong ? 700 : 400, color: v1 !== null && v1 < 0 ? "var(--negative)" : "var(--text-primary)" }}>{v1 !== null ? fmtUSD(v1) : "—"}</td>
                  {compPL && <>
                    <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontWeight: row.strong ? 700 : 400, color: v2 !== null && v2 < 0 ? "var(--negative)" : "var(--text-primary)" }}>{v2 !== null ? fmtUSD(v2) : "—"}</td>
                    <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontWeight: row.strong ? 700 : 400, color: vc, fontSize: 12 }}>{d !== null ? (d >= 0 ? "+" : "") + fmtUSD(d) : "—"}</td>
                    <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontSize: 11, color: vc }}>{p !== null ? `${p >= 0 ? "+" : ""}${(p*100).toFixed(1)}%` : "—"}</td>
                  </>}
                  {comp2PL && <>
                    <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontWeight: row.strong ? 700 : 400, color: v3 !== null && v3 < 0 ? "var(--negative)" : "var(--text-primary)" }}>{v3 !== null ? fmtUSD(v3) : "—"}</td>
                    <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontWeight: row.strong ? 700 : 400, color: vc2, fontSize: 12 }}>{d2 !== null ? (d2 >= 0 ? "+" : "") + fmtUSD(d2) : "—"}</td>
                    <td className="mono" style={{ padding: "5px 8px", textAlign: "right", fontSize: 11, color: vc2 }}>{p2 !== null ? `${p2 >= 0 ? "+" : ""}${(p2*100).toFixed(1)}%` : "—"}</td>
                  </>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Flow Through Analysis — variación por categoría de la vista principal vs cada comparación */}
      {flow && flow.has_data && flow.rows.length > 0 && (
        <div style={{ flex: "1 1 360px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "12px 16px", background: "rgba(245,158,11,0.12)", borderBottom: "1px solid var(--border-medium)" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
              {t("flowThrough", { vista: viewLabel })}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
              {t("flowThroughHint")} — <b style={{ color: "var(--text-primary)" }}>{mainScn ? scnLabel(mainScn) : "—"}</b>
            </div>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ textAlign: "center", padding: "6px 16px", fontSize: 11, color: "var(--text-secondary)" }}>{tc("concept")}</th>
                {flow.comparison_ids.map(cid => {
                  const cs = scenarios.find(s => s.id === cid);
                  return (
                    <th key={cid} style={{ textAlign: "center", padding: "6px 16px", fontSize: 11, fontWeight: 700, color: "var(--text-primary)" }}>
                      {t("versus", { escenario: cs ? scnLabel(cs) : "—" })}<div style={{ fontSize: 10, fontWeight: 400, color: "var(--text-secondary)" }}>{t("varianceUsd")}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {flow.rows.map(r => {
                const strong = r.concept === "Net Profit" || r.concept === "EBITDA Before Capital";
                return (
                  <tr key={r.concept} style={{ borderTop: strong ? "1px solid var(--border-medium)" : undefined, background: strong ? "rgba(255,255,255,0.02)" : undefined }}>
                    <td style={{ padding: "6px 16px", fontWeight: strong ? 700 : 400, color: strong ? "var(--text-primary)" : "var(--text-secondary)" }}>{r.concept}</td>
                    {r.variances.map((vv, i) => {
                      const good = vv >= 0;
                      const amt = Math.abs(vv).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                      return (
                        <td key={i} className="mono" style={{ padding: "6px 16px", textAlign: "center", fontWeight: 700, color: good ? "var(--positive)" : "var(--negative)" }}>
                          {good ? "" : "("}${amt}{good ? "" : ")"}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      </div>
    </div>
  );
}
