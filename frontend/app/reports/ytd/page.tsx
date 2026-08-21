"use client";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
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

// Line codes for the report rows
const REPORT_ROWS: { code: string; label: string; indent?: boolean; isTotal?: boolean; isMargin?: boolean }[] = [
  { code: "TOTAL_REVENUES",           label: "TOTAL REVENUE",          isTotal: true },
  { code: "TOTAL_OPERATING_EXPENSES", label: "Total Operating Exp.",    indent: true },
  { code: "TOTAL_OVERHEAD_EXPENSES",  label: "Total Overhead",          indent: true },
  { code: "TOTAL_GOP",                label: "GROSS OPERATING PROFIT",  isTotal: true },
  { code: "GOP_MARGIN",               label: "  GOP Margin %",          isMargin: true },
  { code: "TOTAL_NON_OP_EXPENSES",    label: "Non-Op Expenses",         indent: true },
  { code: "EBITDA_BEFORE_CAPITAL",    label: "EBITDA",                  isTotal: true },
  { code: "CAPITAL_EXPENSE",          label: "CapEx Reserve",           indent: true },
  { code: "EBITDA_AFTER_CAPITAL",     label: "EBITDA after CapEx" },
  { code: "FINANCIAL_EXPENSES",       label: "Financial Expenses",      indent: true },
  { code: "TOTAL_DEPRECIATIONS",      label: "Depreciation",            indent: true },
  { code: "EBT",                      label: "EBT" },
  { code: "INCOME_TAXES",             label: "Income Tax",              indent: true },
  { code: "NET_PROFIT",               label: "NET PROFIT",              isTotal: true },
  { code: "NET_MARGIN",               label: "  Net Margin %",          isMargin: true },
];

const KPI_ROWS = [
  { code: "occ",       label: "Occupancy %",      fmt: (n: number) => fmtPct(n) },
  { code: "adr",       label: "ADR",              fmt: (n: number) => n > 0 ? "$" + Math.round(n).toLocaleString() : "-" },
  { code: "revpar",    label: "RevPAR",           fmt: (n: number) => n > 0 ? "$" + Math.round(n).toLocaleString() : "-" },
  { code: "rooms_avail", label: "Rooms Available",fmt: (n: number) => n > 0 ? Math.round(n).toLocaleString() : "-" },
  { code: "rooms_occ",   label: "Rooms Occupied", fmt: (n: number) => n > 0 ? Math.round(n).toLocaleString() : "-" },
];

function lineVal(pl: PLMonthly | null, code: string, month: number): number {
  if (!pl) return 0;
  if (month === 0) return pl.annual[code] ?? 0;
  return pl.months.find(x => x.month === month)?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;
}
function lineValYTD(pl: PLMonthly | null, code: string, through: number): number {
  if (!pl || through === 0) return 0;
  let s = 0;
  for (let m = 1; m <= through; m++)
    s += pl.months.find(x => x.month === m)?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;
  return s;
}
function getDisplayVal(pl: PLMonthly | null, code: string, month: number, ytd = false): number {
  if (!pl) return 0;
  const base = ytd ? lineValYTD(pl, code, month) : lineVal(pl, code, month);
  if (code === "GOP_MARGIN") {
    const rev = ytd ? lineValYTD(pl, "TOTAL_REVENUES", month) : lineVal(pl, "TOTAL_REVENUES", month);
    const gop = ytd ? lineValYTD(pl, "TOTAL_GOP", month) : lineVal(pl, "TOTAL_GOP", month);
    return rev ? gop / rev : 0;
  }
  if (code === "NET_MARGIN") {
    const rev = ytd ? lineValYTD(pl, "TOTAL_REVENUES", month) : lineVal(pl, "TOTAL_REVENUES", month);
    const net = ytd ? lineValYTD(pl, "NET_PROFIT", month) : lineVal(pl, "NET_PROFIT", month);
    return rev ? net / rev : 0;
  }
  return base;
}
function getKpi(pl: PLMonthly | null, code: string, month: number): number {
  if (!pl || month === 0) return 0;
  const k = pl.months.find(x => x.month === month)?.kpis;
  if (!k) return 0;
  if (code === "occ") return k.occupancy_pct;
  if (code === "adr") return k.adr;
  if (code === "revpar") return k.revpar;
  if (code === "rooms_avail") return k.rooms_available;
  if (code === "rooms_occ") return k.rooms_occupied;
  return 0;
}
/**
 * Estadísticas acumuladas de enero a `through`.
 *
 * `through` NO era un parámetro: la función sumaba los doce meses siempre. Las
 * columnas «YTD Jun» y «Full Year» llamaban las dos a lo mismo, así que la de
 * YTD mostraba el año completo con el encabezado de junio. Los renglones de
 * dólares sí respetaban el corte (`lineValYTD`), así que el reporte se
 * contradecía consigo mismo sin que nada avisara.
 *
 * Las tasas se PONDERAN, no se promedian: la ocupación acumulada es
 * noches ocupadas ÷ noches disponibles del período, no el promedio de los
 * porcentajes mensuales. Con meses de tamaño distinto —y con octubre cerrado—
 * las dos cosas no dan lo mismo.
 */
function getKpiRange(pl: PLMonthly | null, code: string, through: number): number {
  if (!pl || through < 1) return 0;
  const meses = pl.months.filter(m => m.month <= through);
  let avail = 0, occ = 0, rev = 0;
  for (const m of meses) {
    avail += m.kpis.rooms_available;
    occ += m.kpis.rooms_occupied;
    rev += m.kpis.adr * m.kpis.rooms_occupied;   // ingreso de habitaciones del mes
  }
  if (code === "occ")         return avail ? occ / avail : 0;
  if (code === "adr")         return occ ? rev / occ : 0;
  if (code === "revpar")      return avail ? rev / avail : 0;
  if (code === "rooms_avail") return avail;
  if (code === "rooms_occ")   return occ;
  return 0;
}

const SEL: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };

// Unidad de cada estadística: sin esto el Excel pinta la ocupación (0.65) como
// un número suelto en vez de un porcentaje.
const KPI_FORMATO: Record<string, FormatoCol> = {
  occ: "pct", adr: "usd2", revpar: "usd2", rooms_avail: "num", rooms_occ: "num",
};

export default function YTDReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("ytd");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [plById, setPlById]       = useState<Record<string, PLMonthly>>({});
  // El principal es el real y el de comparacion el presupuesto. Cada uno se
  // acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se eligio abre
  // con el preferido del owner.
  const [mainId, setMainId]       = useEscenarioDe("reports/ytd:actual", scenarios, "actual");
  const [compId, setCompId]       = useEscenarioDe("reports/ytd:budget", scenarios, "budget", undefined, true);
  const [through, setThrough]     = useState(12); // which month we report through
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

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
    const toLoad = [mainId, compId].filter(id => id && !plById[id]);
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
  }, [mainId, compId]); // eslint-disable-line react-hooks/exhaustive-deps

  const pl1 = plById[mainId] ?? null;
  const pl2 = plById[compId] ?? null;
  const scn1 = scenarios.find(s => s.id === mainId);
  const scn2 = scenarios.find(s => s.id === compId);

  // months to show: 1..through + YTD col + Full Year col
  const monthCols = useMemo(() => Array.from({ length: through }, (_, i) => i + 1), [through]);

  const exportExcel = useCallback(async () => {
    if (!pl1) return;
    const ytdCol = `YTD ${MONTHS[through-1]}`;
    const compCol = scn2 ? `${scnLabel(scn2)} YTD` : t("comparacionYtd");
    // El Excel lleva las MISMAS columnas que la pantalla: los meses, el YTD, la
    // comparación con su Var, y el año completo. Antes se comía la comparación.
    const columnas: ColumnaCuadro[] = [
      { label: scn1 ? scnLabel(scn1) : tc("line"), ancho: 32, formato: "texto" },
      ...monthCols.map(m => ({ label: MONTHS[m-1], formato: "usd" as FormatoCol })),
      { label: ytdCol, formato: "usd" as FormatoCol },
      ...(pl2 ? [
        { label: compCol, formato: "usd" as FormatoCol },
        { label: "Var", ancho: 12, formato: "usd" as FormatoCol },
      ] : []),
      { label: "Full Year", formato: "usd" as FormatoCol },
    ];
    const vacia = new Array(columnas.length - 1).fill(null) as (number|null)[];
    const filas: FilaCuadro[] = [{ label: "STATISTICS", es_total: true, valores: vacia }];

    for (const kpi of KPI_ROWS) {
      const ytd = getKpiRange(pl1, kpi.code, through);
      const anual = getKpiRange(pl1, kpi.code, 12);
      filas.push({
        label: kpi.label, nivel: 1, formato: KPI_FORMATO[kpi.code] ?? "num",
        valores: [
          ...monthCols.map(m => getKpi(pl1, kpi.code, m)),
          ytd,                                                     // hasta el mes elegido
          ...(pl2 ? [getKpiRange(pl2, kpi.code, through), null] : []),   // la pantalla deja Var en blanco
          anual,                                                   // los doce meses
        ],
      });
    }

    filas.push({ label: "P&L", es_total: true, valores: vacia });
    for (const r of REPORT_ROWS) {
      const ytdV = getDisplayVal(pl1, r.code, through, true);
      const compV = pl2 ? getDisplayVal(pl2, r.code, through, true) : null;
      filas.push({
        label: r.label.trim(), nivel: r.indent || r.isMargin ? 1 : 0, es_total: !!r.isTotal,
        formato: r.isMargin ? "pct" : undefined,
        valores: [
          ...monthCols.map(m => getDisplayVal(pl1, r.code, m)),
          ytdV,
          ...(pl2 ? [compV, compV === null ? null : ytdV - compV] : []),
          getDisplayVal(pl1, r.code, 0),
        ],
      });
    }

    try {
      await bajarCuadros(`YTD_Report_Thru_${MONTHS[through-1]}`, [{
        titulo: `YTD Owner Report — ${hotel.corto}`,
        subtitulo: t("excelSubtitulo", { hotel: hotel.nombre, mes: MONTHS[through-1] }),
        hoja: "YTD Report",
        columnas, filas,
      }]);
    } catch (e) {
      // Con `setError` esta pantalla reemplaza el reporte entero por el mensaje;
      // para un fallo de descarga alcanza con avisar sin perder lo que se ve.
      alert(e instanceof Error ? e.message : t("excelFallo"));
    }
  }, [pl1, pl2, scn1, scn2, monthCols, through, hotel, t, tc]);

  // El error se mira ANTES que el "cargando": si el P&L falla, `pl1` se queda
  // en nulo y la condicion de abajo taparia el mensaje con un cartel eterno.
  if (error)   return <div style={{ padding: 32, color: "var(--negative)" }}>{error}</div>;
  // El P&L ya no viaja junto con la lista de escenarios: se pide recien cuando
  // se sabe cual quedo elegido. Sin la segunda condicion la pantalla
  // parpadearia en blanco entre una cosa y la otra.
  if (loading || (mainId && !pl1)) return <div style={{ padding: 32, color: "var(--text-secondary)" }}>{tc("loading")}</div>;

  // header column widths for the scrollable table
  const COL_W = 90; // px per month col
  const LABEL_W = 220;

  function RowCells({ rowCode, isMargin, isTotal }: { rowCode: string; isMargin?: boolean; isTotal?: boolean }) {
    return (
      <>
        {monthCols.map(m => {
          const v = getDisplayVal(pl1, rowCode, m);
          const color = v < 0 ? "var(--negative)" : "var(--text-primary)";
          return (
            <td key={m} className="mono" style={{ padding: "4px 8px", textAlign: "right", fontSize: 12, minWidth: COL_W, color, fontWeight: isTotal ? 700 : 400 }}>
              {isMargin ? fmtPct(v) : fmtUSD(v)}
            </td>
          );
        })}
        {/* YTD */}
        {(() => {
          const ytdV = getDisplayVal(pl1, rowCode, through, true);
          const compYtdV = pl2 ? getDisplayVal(pl2, rowCode, through, true) : null;
          const delta = compYtdV !== null ? ytdV - compYtdV : null;
          const isExpense = rowCode.includes("EXPENSES") || rowCode.includes("TAXES");
          const isGood = delta !== null && (isExpense ? delta < 0 : delta > 0);
          const dColor = delta === null || Math.abs(delta) < 0.5 ? "var(--text-secondary)" : (isGood ? "var(--positive)" : "var(--negative)");
          return (
            <>
              <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontSize: 12, minWidth: COL_W, fontWeight: isTotal ? 700 : 400, color: ytdV < 0 ? "var(--negative)" : "var(--positive)", borderLeft: "2px solid var(--border-medium)" }}>
                {isMargin ? fmtPct(ytdV) : fmtUSD(ytdV)}
              </td>
              {pl2 && (
                <>
                  <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontSize: 12, minWidth: COL_W, fontWeight: isTotal ? 700 : 400, color: compYtdV !== null && compYtdV < 0 ? "var(--negative)" : "var(--text-secondary)" }}>
                    {compYtdV !== null ? (isMargin ? fmtPct(compYtdV) : fmtUSD(compYtdV)) : "—"}
                  </td>
                  <td className="mono" style={{ padding: "4px 6px", textAlign: "right", fontSize: 11, minWidth: 72, color: dColor }}>
                    {delta !== null ? (delta >= 0 ? "+" : "") + (isMargin ? fmtPct(delta) : fmtUSD(delta)) : "—"}
                  </td>
                </>
              )}
              {/* Full Year */}
              <td className="mono" style={{ padding: "4px 8px", textAlign: "right", fontSize: 12, minWidth: COL_W, fontWeight: isTotal ? 700 : 400, color: "var(--text-secondary)", borderLeft: "1px solid var(--border-medium)" }}>
                {isMargin ? fmtPct(getDisplayVal(pl1, rowCode, 0)) : fmtUSD(getDisplayVal(pl1, rowCode, 0))}
              </td>
            </>
          );
        })()}
      </>
    );
  }

  const ytdLabel = `YTD ${MONTHS[through - 1]}`;
  const compYtdLabel = pl2 && scn2 ? `${scnLabel(scn2)} YTD` : "";

  return (
    <>
    <style>{`
      @media print {
        body * { visibility: hidden; }
        #ytd-print, #ytd-print * { visibility: visible; }
        #ytd-print { position: absolute; inset: 0; padding: 16px; }
        .no-print { display: none !important; }
        table { font-size: 9px !important; }
        td, th { padding: 3px 5px !important; }
      }
    `}</style>
    <div className="pag pag-ancha" style={{ padding: "24px 28px 64px" }}>
      <IrA esc={compId} />
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>YTD Owner Report — {hotel.corto}</h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("subtitulo", { hotel: hotel.nombre })}</p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button onClick={exportExcel} style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer", background: "var(--accent-excel)", color: "#fff", border: "none", fontSize: 13, fontWeight: 600 }}>⬇ Excel</button>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", fontSize: 13, fontWeight: 600 }}>🖨 PDF</button>
        </div>
      </div>

      {/* Controls */}
      <div className="no-print" style={{ display: "flex", gap: 16, alignItems: "flex-end", marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.5, marginBottom: 4, textTransform: "uppercase" }}>{t("mainScenario")}</div>
          <select value={mainId} onChange={e => setMainId(e.target.value)} style={SEL}>
            {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.5, marginBottom: 4, textTransform: "uppercase" }}>{t("compareWith")}</div>
          <select value={compId} onChange={e => setCompId(e.target.value)} style={SEL}>
            <option value="" style={{ background: "var(--bg-input)" }}>{tc("none")}</option>
            {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
          </select>
        </div>
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.5, marginBottom: 4, textTransform: "uppercase" }}>{t("reportThrough")}</div>
          <select value={through} onChange={e => setThrough(Number(e.target.value))} style={SEL}>
            {MONTHS.map((m, i) => (
              <option key={i+1} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Scrollable table */}
      <div id="ytd-print" className="fin-sticky" style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: 12, minWidth: 900 }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--border-medium)" }}>
              <th style={{ textAlign: "left", padding: "6px 8px", minWidth: LABEL_W, fontSize: 11, color: "var(--text-secondary)", position: "sticky", left: 0, background: "var(--bg-base)", zIndex: 2 }}>
                {scn1 ? scnLabel(scn1) : "—"}
              </th>
              {monthCols.map(m => (
                <th key={m} style={{ textAlign: "right", padding: "6px 8px", minWidth: COL_W, fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>{MONTHS[m-1]}</th>
              ))}
              {/* YTD cols */}
              <th style={{ textAlign: "right", padding: "6px 8px", minWidth: COL_W, fontSize: 11, fontWeight: 700, color: "var(--positive)", borderLeft: "2px solid var(--border-medium)" }}>{ytdLabel}</th>
              {pl2 && <>
                <th style={{ textAlign: "right", padding: "6px 8px", minWidth: COL_W, fontSize: 11, fontWeight: 600, color: "var(--text-secondary)" }}>{compYtdLabel}</th>
                <th style={{ textAlign: "right", padding: "6px 6px", minWidth: 72, fontSize: 11, color: "var(--text-secondary)" }}>Var</th>
              </>}
              {/* Full Year */}
              <th style={{ textAlign: "right", padding: "6px 8px", minWidth: COL_W, fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", borderLeft: "1px solid var(--border-medium)" }}>Full Year</th>
            </tr>
          </thead>
          <tbody>
            {/* KPI block */}
            <tr>
              <td colSpan={monthCols.length + (pl2 ? 4 : 3)} style={{ padding: "12px 8px 4px", fontSize: 10, fontWeight: 700, letterSpacing: 0.8, color: "var(--text-secondary)", textTransform: "uppercase", borderBottom: "1px solid var(--border-medium)", position: "sticky", left: 0 }}>
                Statistics
              </td>
            </tr>
            {KPI_ROWS.map(kpi => (
              <tr key={kpi.code}>
                <td style={{ padding: "4px 8px 4px 22px", color: "var(--text-secondary)", fontSize: 12, position: "sticky", left: 0, background: "var(--bg-base)" }}>{kpi.label}</td>
                {monthCols.map(m => (
                  <td key={m} className="mono" style={{ padding: "4px 8px", textAlign: "right", minWidth: COL_W, fontSize: 12, color: "var(--text-primary)" }}>{kpi.fmt(getKpi(pl1, kpi.code, m))}</td>
                ))}
                {/* YTD = average for rates, sum for counts */}
                <td className="mono" style={{ padding: "4px 8px", textAlign: "right", minWidth: COL_W, fontSize: 12, color: "var(--positive)", fontWeight: 600, borderLeft: "2px solid var(--border-medium)" }}>
                  {kpi.fmt(getKpiRange(pl1, kpi.code, through))}
                </td>
                {pl2 && <>
                  <td className="mono" style={{ padding: "4px 8px", textAlign: "right", minWidth: COL_W, fontSize: 12, color: "var(--text-secondary)" }}>{kpi.fmt(getKpiRange(pl2, kpi.code, through))}</td>
                  <td className="mono" style={{ padding: "4px 6px", minWidth: 72 }} />
                </>}
                <td className="mono" style={{ padding: "4px 8px", textAlign: "right", minWidth: COL_W, fontSize: 12, color: "var(--text-secondary)", borderLeft: "1px solid var(--border-medium)" }}>
                  {kpi.fmt(getKpiRange(pl1, kpi.code, 12))}
                </td>
              </tr>
            ))}

            {/* P&L rows */}
            <tr>
              <td colSpan={monthCols.length + (pl2 ? 4 : 3)} style={{ padding: "12px 8px 4px", fontSize: 10, fontWeight: 700, letterSpacing: 0.8, color: "var(--text-secondary)", textTransform: "uppercase", borderBottom: "1px solid var(--border-medium)", position: "sticky", left: 0 }}>
                P&L
              </td>
            </tr>
            {REPORT_ROWS.map(row => (
              <tr key={row.code} style={{
                borderTop: row.isTotal ? "1px solid var(--border-medium)" : undefined,
                background: row.isTotal ? "rgba(255,255,255,0.02)" : undefined,
              }}>
                <td style={{
                  padding: "4px 8px",
                  paddingLeft: row.indent ? 22 : 8,
                  fontWeight: row.isTotal ? 700 : 400,
                  color: row.isTotal ? "var(--text-primary)" : "var(--text-secondary)",
                  fontSize: 12,
                  position: "sticky", left: 0,
                  background: row.isTotal ? "var(--bg-elevated)" : "var(--bg-base)",
                  minWidth: LABEL_W,
                }}>
                  {row.label}
                </td>
                <RowCells rowCode={row.code} isMargin={row.isMargin} isTotal={row.isTotal} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
    </>
  );
}
