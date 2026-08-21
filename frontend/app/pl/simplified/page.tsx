"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro, type FormatoCol } from "@/lib/exportCuadro";
import { getScenarios, getPLMonthly, type Scenario, type PLMonthly } from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
function fmtUSD(n: number) {
  if (Math.abs(n) < 0.5) return "-";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}
function fmtPct(n: number) { return Math.abs(n) < 0.0001 ? "-" : (n * 100).toFixed(1) + "%"; }

// ── Simplified P&L structure ────────────────────────────────────────────
// Shows major groupings only — no line-by-line detail
interface PLSection {
  title: string;
  rows: { code: string; label: string; indent?: boolean; isTotal?: boolean; isKpi?: boolean }[];
  dividerAfter?: boolean;
}

const STRUCTURE: PLSection[] = [
  {
    title: "REVENUE",
    rows: [
      { code: "TOTAL_REVENUES", label: "TOTAL REVENUE", isTotal: true },
    ],
    dividerAfter: true,
  },
  {
    title: "DEPARTMENTAL EXPENSES",
    rows: [
      { code: "TOTAL_OPERATING_EXPENSES", label: "Total Operating Expenses", indent: true },
      { code: "TOTAL_OVERHEAD_EXPENSES",  label: "Total Overhead Expenses",  indent: true },
      { code: "OPERATING_PROFIT",          label: "OPERATING PROFIT",          isTotal: true },
    ],
    dividerAfter: true,
  },
  {
    title: "GROSS OPERATING PROFIT",
    rows: [
      { code: "TOTAL_GOP",   label: "GOP",        isTotal: true },
      { code: "GOP_MARGIN",  label: "GOP Margin", indent: true, isKpi: true },
    ],
    dividerAfter: true,
  },
  {
    title: "NON-OPERATING & CAPITAL",
    rows: [
      { code: "TOTAL_NON_OP_EXPENSES",   label: "Non-Op Expenses",  indent: true },
      { code: "EBITDA_BEFORE_CAPITAL",   label: "EBITDA",           isTotal: true },
      { code: "CAPITAL_EXPENSE",          label: "CapEx Reserve",    indent: true },
      { code: "EBITDA_AFTER_CAPITAL",    label: "EBITDA after CapEx", isTotal: false },
    ],
    dividerAfter: true,
  },
  {
    title: "FINANCIAL & TAX",
    rows: [
      { code: "FINANCIAL_EXPENSES",  label: "Financial Expenses",  indent: true },
      { code: "TOTAL_DEPRECIATIONS", label: "Depreciation",        indent: true },
      { code: "EBT",                 label: "EBT",                 isTotal: false },
      { code: "INCOME_TAXES",        label: "Income Taxes",        indent: true },
      { code: "NET_PROFIT",          label: "NET PROFIT",          isTotal: true },
      { code: "NET_MARGIN",          label: "Net Margin",          indent: true, isKpi: true },
    ],
  },
];

// KPI: occupancy, ADR, RevPAR
const KPI_SECTION = [
  { code: "occ",    label: "Occupancy %" },
  { code: "adr",    label: "ADR" },
  { code: "revpar", label: "RevPAR" },
  { code: "rooms_avail", label: "Rooms Available" },
  { code: "rooms_occ",   label: "Rooms Occupied" },
];

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

function getKpiVal(pl: PLMonthly, code: string, m: number, ytd: boolean): number {
  const end = m === 0 ? 12 : m;
  const useRange = m === 0 || ytd;
  const singleMonth = !useRange && m > 0 ? pl.months.find(x => x.month === m)?.kpis : undefined;
  if (code === "occ") {
    if (!useRange && singleMonth) return singleMonth.occupancy_pct;
    let avail = 0, occ = 0;
    for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) { avail += k.rooms_available; occ += k.rooms_occupied; } }
    return avail ? occ / avail : 0;
  }
  if (code === "adr") {
    if (!useRange && singleMonth) return singleMonth.adr;
    let occ = 0, rev = 0;
    for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) { occ += k.rooms_occupied; rev += k.adr * k.rooms_occupied; } }
    return occ ? rev / occ : 0;
  }
  if (code === "revpar") {
    if (!useRange && singleMonth) return singleMonth.revpar;
    let avail = 0, rev = 0;
    for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) { avail += k.rooms_available; rev += k.adr * k.rooms_occupied; } }
    return avail ? rev / avail : 0;
  }
  if (code === "rooms_avail") {
    let s = 0;
    for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) s += k.rooms_available; }
    return s;
  }
  if (code === "rooms_occ") {
    let s = 0;
    for (let mm = 1; mm <= end; mm++) { const k = pl.months.find(x => x.month === mm)?.kpis; if (k) s += k.rooms_occupied; }
    return Math.round(s);
  }
  return 0;
}

function getDisplayVal(pl: PLMonthly, code: string, m: number, ytd: boolean): number {
  if (code === "GOP_MARGIN") {
    const rev = lineVal(pl, "TOTAL_REVENUES", m, ytd);
    const gop = lineVal(pl, "TOTAL_GOP", m, ytd);
    return rev ? gop / rev : 0;
  }
  if (code === "NET_MARGIN") {
    const rev = lineVal(pl, "TOTAL_REVENUES", m, ytd);
    const net = lineVal(pl, "NET_PROFIT", m, ytd);
    return rev ? net / rev : 0;
  }
  return lineVal(pl, code, m, ytd);
}

const SEL: React.CSSProperties = {
  background: "var(--bg-input)", color: "var(--text-primary)",
  border: "1px solid var(--border-medium)", borderRadius: 5,
  padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer",
};

export default function SimplifiedPLPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("pl");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios]  = useState<Scenario[]>([]);
  const [plById, setPlById]        = useState<Record<string, PLMonthly>>({});
  // Columna 1 = el real, columna 2 = el presupuesto contra el que se compara.
  // Cada una con su llave: si compartieran una, elegir en la primera le
  // cambiaria el escenario a la segunda.
  const [col1Id, setCol1Id]        = useEscenarioDe("pl/simplified:actual", scenarios, "actual");
  const [col2Id, setCol2Id]        = useEscenarioDe("pl/simplified:budget", scenarios, "budget", undefined, true);
  const [month, setMonth]          = useState(0);
  const [ytd, setYtd]              = useState(false);
  const [loading, setLoading]      = useState(true);
  const [error, setError]          = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        if (!all.length) { setError(t("sinEscenarios")); return; }
        const sorted = [...all].sort((a, b) =>
          a.year !== b.year ? b.year - a.year :
          (["ACTUAL","BUDGET","FORECAST"].indexOf(a.type) - ["ACTUAL","BUDGET","FORECAST"].indexOf(b.type))
        );
        // El orden es solo para el desplegable; la eleccion la hace
        // `useEscenarioDe` cuando llega la lista, y el efecto de abajo trae el
        // P&L de lo que quede elegido.
        setScenarios(sorted);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error");
      } finally {
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const toLoad = [col1Id, col2Id].filter(id => id && !plById[id]);
    if (!toLoad.length) return;
    (async () => {
      try {
        const pls = await Promise.all(toLoad.map(async id => [id, await getPLMonthly(id)] as const));
        setPlById(prev => ({ ...prev, ...Object.fromEntries(pls) }));
      } catch (e) {
        // Este pedido ya no viaja dentro del try de la carga inicial: sin este
        // aviso, un P&L que falla dejaria la pantalla girando para siempre.
        setError(e instanceof Error ? e.message : "Error");
      }
    })();
  }, [col1Id, col2Id]); // eslint-disable-line react-hooks/exhaustive-deps

  const pl1 = plById[col1Id] ?? null;
  const pl2 = plById[col2Id] ?? null;
  const useYtd = ytd && month > 0;
  const scn1 = scenarios.find(s => s.id === col1Id);
  const scn2 = scenarios.find(s => s.id === col2Id);

  const exportExcel = useCallback(async () => {
    if (!pl1) return;
    const viewLbl = month === 0 ? "Full Year" : (useYtd ? "YTD " : "") + MONTHS[month - 1];
    const hayDos = !!pl2;
    const usd: FormatoCol = "usd";
    const columnas: ColumnaCuadro[] = [
      { label: "Simplified P&L", ancho: 34, formato: "texto" },
      { label: scn1 ? scnLabel(scn1) : "Col 1", formato: usd },
      ...(hayDos ? [
        { label: scn2 ? scnLabel(scn2) : "Col 2", formato: usd },
        { label: "Var $", formato: usd },
        { label: "Var %", ancho: 10, formato: "pct" as FormatoCol },
      ] : []),
    ];
    const vacia = new Array(columnas.length - 1).fill(null) as (number|null)[];
    // Mismo orden que la pantalla: primero las estadísticas, después el P&L.
    const filas: FilaCuadro[] = [{ label: "STATISTICS", es_total: true, valores: vacia }];
    for (const kpi of KPI_SECTION) {
      const v1 = getKpiVal(pl1, kpi.code, month, useYtd);
      const v2 = pl2 ? getKpiVal(pl2, kpi.code, month, useYtd) : null;
      const d  = v2 === null ? null : v1 - v2;
      const p  = d !== null && v2 !== null && Math.abs(v2) > 0.5 ? d / Math.abs(v2) : null;
      filas.push({
        label: kpi.label, nivel: 1,
        // La ocupación es una fracción: sin esto sale como "1" en vez de "65%".
        formato: kpi.code === "occ" ? "pct" : undefined,
        valores: [v1, ...(hayDos ? [v2, d, p] : [])],
      });
    }
    for (const sec of STRUCTURE) {
      filas.push({ label: sec.title, es_total: true, valores: vacia });
      for (const row of sec.rows) {
        const v1 = getDisplayVal(pl1, row.code, month, useYtd);
        const v2 = pl2 ? getDisplayVal(pl2, row.code, month, useYtd) : null;
        const d  = v2 === null ? null : v1 - v2;
        const p  = d !== null && v2 !== null && Math.abs(v2) > 0.5 ? d / Math.abs(v2) : null;
        const esMargen = row.code.includes("MARGIN");
        filas.push({
          label: row.label, nivel: row.indent ? 1 : 0, es_total: !!row.isTotal,
          formato: esMargen ? "pct" : undefined,
          valores: [v1, ...(hayDos ? [v2, d, p] : [])],
        });
      }
    }
    try {
      await bajarCuadros(`SimplifiedPL_${viewLbl.replace(/\s/g,"_")}`, [{
        titulo: `Simplified P&L — ${hotel.corto}`,
        subtitulo: `${viewLbl} · USD`,
        hoja: `Simplified PL ${viewLbl}`,
        columnas, filas,
      }]);
    } catch (e) {
      // `setError` acá reemplaza la pantalla entera por el mensaje; para una
      // descarga fallida basta con avisar sin perder el reporte.
      alert(e instanceof Error ? e.message : t("excelFallo"));
    }
  }, [pl1, pl2, scn1, scn2, month, useYtd, hotel, t]);

  // El error se mira ANTES que el "cargando": si el P&L falla, `pl1` se queda
  // en nulo y la condicion de abajo taparia el mensaje con un cartel eterno.
  if (error)   return <div style={{ padding: 32, color: "var(--negative)" }}>{error}</div>;
  // El P&L ya no viaja junto con la lista de escenarios: se pide recien cuando
  // se sabe cual quedo elegido. Sin la segunda condicion la pantalla
  // parpadearia en blanco entre una cosa y la otra.
  if (loading || (col1Id && !pl1)) return <div style={{ padding: 32, color: "var(--text-secondary)" }}>{tc("loading")}</div>;

  const viewLabel = month === 0 ? "Full Year" : (useYtd ? "YTD " : "") + MONTHS[month - 1];

  function Cell({ pl, code, isKpi }: { pl: PLMonthly | null; code: string; isKpi?: boolean }) {
    if (!pl) return <td className="mono" style={{ padding: "5px 10px", textAlign: "right", color: "var(--text-secondary)" }}>—</td>;
    const val = isKpi ? getDisplayVal(pl, code, month, useYtd) : lineVal(pl, code, month, useYtd);
    const isMargin = code.includes("MARGIN");
    const color = val < 0 ? "var(--negative)" : "var(--text-primary)";
    return (
      <td className="mono" style={{ padding: "5px 10px", textAlign: "right", color }}>
        {isMargin ? fmtPct(val) : fmtUSD(val)}
      </td>
    );
  }

  function VarCells({ code, isKpi }: { code: string; isKpi?: boolean }) {
    if (!pl1 || !pl2) return <><td /><td /></>;
    const v1 = isKpi ? getDisplayVal(pl1, code, month, useYtd) : lineVal(pl1, code, month, useYtd);
    const v2 = isKpi ? getDisplayVal(pl2, code, month, useYtd) : lineVal(pl2, code, month, useYtd);
    const d  = v1 - v2;
    const p  = Math.abs(v2) > 0.5 ? d / Math.abs(v2) : null;
    const isMargin = code.includes("MARGIN");
    const isExpenseCode = code.includes("EXPENSES") || code.includes("TAXES") || code.includes("EXPENSE");
    const isGood = isExpenseCode ? d < 0 : d > 0;
    const color = Math.abs(d) < 0.5 ? "var(--text-secondary)" : (isGood ? "var(--positive)" : "var(--negative)");
    return (
      <>
        <td className="mono" style={{ padding: "5px 10px", textAlign: "right", color, fontSize: 12 }}>
          {isMargin ? (d >= 0 ? "+" : "") + fmtPct(d) : (d >= 0 ? "+" : "") + fmtUSD(d)}
        </td>
        <td className="mono" style={{ padding: "5px 8px", textAlign: "right", color, fontSize: 11 }}>
          {p !== null ? `${p >= 0 ? "+" : ""}${(p * 100).toFixed(1)}%` : "—"}
        </td>
      </>
    );
  }

  const hasTwoCols = !!pl2;

  return (
    <>
    <style>{`
      @media print {
        body * { visibility: hidden; }
        #simplified-print, #simplified-print * { visibility: visible; }
        #simplified-print { position: absolute; inset: 0; padding: 24px; }
        .no-print { display: none !important; }
        table { font-size: 10px !important; }
      }
    `}</style>
    <div className="pag pag-lectura" style={{ padding: "28px 28px 64px" }}>
      <IrA esc={col2Id} />
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("simplifiedTitle", { hotel: hotel.corto })}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("vistaEjecutiva")} · {viewLabel} · USD</p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button onClick={exportExcel} style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer", background: "var(--accent-excel)", color: "#fff", border: "none", fontSize: 13, fontWeight: 600 }}>⬇ Excel</button>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", fontSize: 13, fontWeight: 600 }}>🖨 PDF</button>
        </div>
      </div>

      {/* Scenario selectors */}
      <div className="no-print" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 20, padding: "14px 18px", background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8 }}>
        {([
          { label: t("columna", { n: 1 }), val: col1Id, set: setCol1Id, allowNone: false },
          { label: t("columnaComparar", { n: 2 }), val: col2Id, set: setCol2Id, allowNone: true },
        ] as const).map(({ label, val, set, allowNone }) => (
          <div key={label}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.5, marginBottom: 6, textTransform: "uppercase" }}>{label}</div>
            <select value={val} onChange={e => set(e.target.value)} style={{ ...SEL, width: "100%" }}>
              {allowNone && <option value="" style={{ background: "var(--bg-input)" }}>{tc("none")}</option>}
              {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
            </select>
          </div>
        ))}
      </div>

      {/* Month selector */}
      <div className="no-print" style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 24, flexWrap: "wrap" }}>
        {["Full Year", ...MONTHS].map((label, i) => (
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
          {([[ "Mes", tc("month") ], [ "YTD", "YTD" ]] as const).map(([lbl, txt]) => {
            const isYtdBtn = lbl === "YTD", active = isYtdBtn === ytd;
            return (
              <button key={lbl} onClick={() => setYtd(isYtdBtn)} style={{
                padding: "5px 11px", fontSize: 12, borderRadius: 5, cursor: "pointer", fontWeight: 700,
                background: active ? "var(--positive)" : "var(--bg-elevated)",
                color: active ? "#fff" : "var(--text-secondary)",
                border: `1px solid ${active ? "var(--positive)" : "var(--border-medium)"}`,
              }}>{txt}</button>
            );
          })}
        </>}
      </div>

      {/* Simplified P&L table */}
      <div id="simplified-print">
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border-medium)" }}>
              <th style={{ textAlign: "left", padding: "6px 8px", width: "40%", fontSize: 11, color: "var(--text-secondary)" }}>
                {hotel.corto} · {viewLabel}
              </th>
              <th style={{ textAlign: "right", padding: "6px 10px", fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{scn1 ? scnLabel(scn1) : "—"}</th>
              {hasTwoCols && <>
                <th style={{ textAlign: "right", padding: "6px 10px", fontSize: 12, fontWeight: 700, color: "var(--text-primary)" }}>{scn2 ? scnLabel(scn2) : "—"}</th>
                <th style={{ textAlign: "right", padding: "6px 10px", fontSize: 11, color: "var(--text-secondary)" }}>Var $</th>
                <th style={{ textAlign: "right", padding: "6px 8px",  fontSize: 11, color: "var(--text-secondary)" }}>Var %</th>
              </>}
            </tr>
          </thead>
          <tbody>
            {/* Statistics header */}
            <tr>
              <td colSpan={hasTwoCols ? 5 : 2} style={{ padding: "14px 8px 5px", fontSize: 10, fontWeight: 700, letterSpacing: 0.8, color: "var(--text-secondary)", textTransform: "uppercase", borderBottom: "1px solid var(--border-medium)" }}>
                Statistics
              </td>
            </tr>
            {KPI_SECTION.map(kpi => {
              const v1 = pl1 ? getKpiVal(pl1, kpi.code, month, useYtd) : null;
              const v2 = pl2 ? getKpiVal(pl2, kpi.code, month, useYtd) : null;
              const d  = v1 !== null && v2 !== null ? v1 - v2 : null;
              const p  = d !== null && v2 && Math.abs(v2) > 0.5 ? d / Math.abs(v2) : null;
              const isPct = kpi.code === "occ";
              const isAmt = kpi.code === "adr" || kpi.code === "revpar";
              const fmt = (v: number) => isPct ? fmtPct(v) : isAmt ? "$" + Math.round(v).toLocaleString() : Math.round(v).toLocaleString();
              const dColor = d === null || Math.abs(d) < 0.001 ? "var(--text-secondary)" : (d > 0 ? "var(--positive)" : "var(--negative)");
              return (
                <tr key={kpi.code}>
                  <td style={{ padding: "4px 8px 4px 22px", color: "var(--text-secondary)", fontSize: 12 }}>{kpi.label}</td>
                  <td className="mono" style={{ padding: "4px 10px", textAlign: "right", fontSize: 12, color: "var(--text-primary)" }}>{v1 !== null ? fmt(v1) : "—"}</td>
                  {hasTwoCols && <>
                    <td className="mono" style={{ padding: "4px 10px", textAlign: "right", fontSize: 12, color: "var(--text-primary)" }}>{v2 !== null ? fmt(v2) : "—"}</td>
                    <td className="mono" style={{ padding: "4px 10px", textAlign: "right", fontSize: 11, color: dColor }}>{d !== null ? (d >= 0 ? "+" : "") + fmt(d) : "—"}</td>
                    <td className="mono" style={{ padding: "4px 8px",  textAlign: "right", fontSize: 11, color: dColor }}>{p !== null ? `${p >= 0 ? "+" : ""}${(p*100).toFixed(1)}%` : "—"}</td>
                  </>}
                </tr>
              );
            })}

            {/* P&L sections */}
            {STRUCTURE.map(sec => (
              <Fragment key={sec.title}>
                <tr>
                  <td colSpan={hasTwoCols ? 5 : 2} style={{ padding: "14px 8px 5px", fontSize: 10, fontWeight: 700, letterSpacing: 0.8, color: "var(--text-secondary)", textTransform: "uppercase", borderBottom: "1px solid var(--border-medium)" }}>
                    {sec.title}
                  </td>
                </tr>
                {sec.rows.map(row => {
                  const isTotal = row.isTotal;
                  return (
                    <tr key={row.code} style={{
                      background: isTotal ? "rgba(255,255,255,0.02)" : undefined,
                      borderTop: isTotal ? "1px solid var(--border-medium)" : undefined,
                    }}>
                      <td style={{
                        padding: "5px 8px",
                        paddingLeft: row.indent ? 22 : 8,
                        fontWeight: isTotal ? 700 : 400,
                        color: isTotal ? "var(--text-primary)" : "var(--text-secondary)",
                        fontSize: 13,
                      }}>
                        {row.label}
                      </td>
                      <Cell pl={pl1} code={row.code} isKpi={row.isKpi} />
                      {hasTwoCols && <>
                        <Cell pl={pl2} code={row.code} isKpi={row.isKpi} />
                        <VarCells code={row.code} isKpi={row.isKpi} />
                      </>}
                    </tr>
                  );
                })}
                {sec.dividerAfter && (
                  <tr><td colSpan={hasTwoCols ? 5 : 2} style={{ height: 4 }} /></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
    </>
  );
}
