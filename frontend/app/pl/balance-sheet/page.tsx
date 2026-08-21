"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getBalanceSheetPeriods, getBalanceSheetMatrix, importBalanceSheet, balanceSheetTemplateUrl,
  type Scenario, type BalanceSheetPeriod, type BalanceSheetMatrixRow,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const MONTHS_SHORT_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

const GOLD = "#c8a24a";
const m2 = (v: number, sym = "$") => (v < 0 ? "(" : "") + sym + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (v < 0 ? ")" : "");
const SECTION_TINT: Record<string, string> = { ASSET: "rgba(38,166,154,0.10)", LIABILITY: "rgba(214,153,69,0.10)", EQUITY: "rgba(120,144,224,0.12)" };

export default function BalanceSheetPage() {
  const tc = useTranslations("common");
  const t = useTranslations("balance");
  const tMonths = useTranslations("months");
  const MONTHS_SHORT = (tMonths.raw("short") as string[]) ?? MONTHS_SHORT_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scnId, setScnId] = useState("");
  const [periods, setPeriods] = useState<BalanceSheetPeriod[]>([]);
  const [year, setYear] = useState(0);
  const [rows, setRows] = useState<BalanceSheetMatrixRow[]>([]);
  const [months, setMonths] = useState<number[]>([]);
  const [cur, setCur] = useState<"usd" | "crc">("usd");
  const [tplKey, setTplKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        const act = all.filter(s => s.type === "ACTUAL").sort((a, b) => b.year - a.year)[0];
        setScnId(act?.id ?? all[0]?.id ?? "");
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const loadPeriods = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const res = await getBalanceSheetPeriods(id);
      setPeriods(res.periods);
      if (res.periods.length) { setYear(res.periods[0].year); }
      else { setYear(0); setRows([]); setMonths([]); }
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
  }, []);
  useEffect(() => { if (scnId) loadPeriods(scnId); }, [scnId, loadPeriods]);

  // mes por defecto para la plantilla = siguiente al último cargado
  const nextYM: [number, number] | null = periods.length
    ? (periods[0].month === 12 ? [periods[0].year + 1, 1] : [periods[0].year, periods[0].month + 1])
    : null;
  useEffect(() => { if (nextYM) setTplKey(`${nextYM[0]}-${nextYM[1]}`); }, [periods]); // eslint-disable-line react-hooks/exhaustive-deps
  // opciones del selector: mes nuevo (siguiente) + meses ya cargados (re-cargar/corregir)
  const tplOptions = [
    ...(nextYM ? [{ year: nextYM[0], month: nextYM[1], isNew: true }] : []),
    ...periods.map(p => ({ year: p.year, month: p.month, isNew: false })),
  ];

  const load = useCallback(async (id: string, y: number) => {
    if (!id || !y) { setRows([]); setMonths([]); return; }
    setLoading(true); setError(null);
    try { const res = await getBalanceSheetMatrix(id, y); setRows(res.rows); setMonths(res.months); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scnId && year) load(scnId, year); }, [scnId, year, load]);
  const years = Array.from(new Set(periods.map(p => p.year))).sort((a, b) => b - a);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !scnId) return;
    setBusy(true); setMsg(null); setError(null);
    try {
      const dry = await importBalanceSheet(scnId, f, true);
      const chk = dry.check?.[0];
      const ok = chk && chk.total_assets != null && chk.total_liab_equity != null
        && Math.abs(chk.total_assets - chk.total_liab_equity) < 1;
      const periodsTxt = dry.periods.map(p => `${MONTHS_EN[p.month - 1].slice(0, 3)} ${p.year}`).join(", ");
      const confirmMsg = t("dryRun", { periodos: dry.periods.length, lista: periodsTxt, lineas: dry.lines })
        + (chk ? t("dryRunCheck", {
            mes: MONTHS_EN[chk.month - 1], year: chk.year,
            assets: chk.total_assets?.toLocaleString("en-US") ?? "",
            liab: chk.total_liab_equity?.toLocaleString("en-US") ?? "",
            veredicto: ok ? t("cuadra") : t("noCuadra"),
          }) : "")
        + t("dryRunPregunta");
      if (!window.confirm(confirmMsg)) { setBusy(false); if (fileRef.current) fileRef.current.value = ""; return; }
      const res = await importBalanceSheet(scnId, f, false);
      setMsg(t("importado", { celdas: res.rows_saved ?? 0, periodos: res.periods.length }));
      await loadPeriods(scnId);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  /* Sale en la moneda que esté puesta en pantalla. En CRC no se usa el formato
     de dólar: pondría "$" sobre colones, que es peor que no poner nada. El mes
     sin dato queda VACÍO (null) — no es un cero cargado. */
  async function bajarExcel() {
    if (!rows.length) return;
    const filas: FilaCuadro[] = rows.map(r => {
      const vals = cur === "usd" ? r.usd : r.crc;
      return {
        label: r.label, nivel: r.indent, es_total: r.is_total,
        valores: MONTHS_SHORT.map((_m, mi) => { const v = vals[mi + 1]; return v === undefined ? null : v; }),
      };
    });
    const scn = scenarios.find(s => s.id === scnId);
    try {
      await bajarCuadros(`Balance_Sheet_${year}`, [{
        titulo: "Balance Sheet",
        subtitulo: `${scn ? scnLabel(scn) : ""} · ${t("eneDic", { year })} · ${cur === "usd" ? "USD" : "CRC"}`,
        hoja: `Balance ${year}`,
        columnas: [
          { label: tc("account"), ancho: 44, formato: "texto" },
          ...MONTHS_SHORT.map(m => ({ label: m, ancho: 15, formato: (cur === "usd" ? "usd2" : "num") as "usd2" | "num" })),
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const seg = (active: boolean): React.CSSProperties => ({ padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", background: active ? "var(--brand)" : "transparent", color: active ? "#fff" : "var(--text-secondary)", border: "none" });
  const segWrap: React.CSSProperties = { display: "flex", border: "1px solid var(--border-medium)", borderRadius: 6, overflow: "hidden", background: "var(--bg-input)" };

  return (
    <div className="print-dashboard pag pag-ancha" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={scnId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 34, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}>
          <span style={{ color: "var(--text-primary)" }}>Balance </span><span style={{ color: "var(--brand)" }}>Sheet</span>
        </h1>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 6 }}>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
          <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 600 }}>{t("title")}<span style={{ color: GOLD, fontWeight: 800 }}>|</span> {year ? t("eneDic", { year }) : "—"}</span>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
        </div>
      </div>

      <div className="no-print" style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "flex-end", margin: "16px 0 22px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("scenario")}</span><select value={scnId} onChange={e => setScnId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("year")}</span>
          <select value={year || ""} onChange={e => setYear(Number(e.target.value))} style={sel} disabled={!years.length}>
            {!years.length && <option value="">{t("sinDatos")}</option>}
            {years.map(y => <option key={y} value={y} style={{ background: "var(--bg-input)" }}>{y}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("currency")}</span>
          <div style={segWrap}><button onClick={() => setCur("usd")} style={seg(cur === "usd")}>USD</button><button onClick={() => setCur("crc")} style={seg(cur === "crc")}>CRC</button></div>
        </div>
        {periods.length > 0 && (() => {
          const [ty, tm] = tplKey ? tplKey.split("-").map(Number) : [nextYM![0], nextYM![1]];
          return (
            <>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("templateMonth")}</span>
                <select value={tplKey} onChange={e => setTplKey(e.target.value)} style={sel}>
                  {tplOptions.map(o => (
                    <option key={`${o.year}-${o.month}`} value={`${o.year}-${o.month}`} style={{ background: "var(--bg-input)" }}>
                      {MONTHS_EN[o.month - 1]} {o.year}{o.isNew ? t("tplNuevo") : t("tplRecargar")}
                    </option>
                  ))}
                </select>
              </div>
              <a href={balanceSheetTemplateUrl(scnId, ty, tm)} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", textDecoration: "none" }} title={t("plantillaTitle", { mes: MONTHS_EN[tm - 1], year: ty })}>{t("plantillaBtn")}</a>
            </>
          );
        })()}
        <button onClick={() => fileRef.current?.click()} disabled={busy} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: busy ? "default" : "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", opacity: busy ? 0.6 : 1 }}>{busy ? t("procesando") : t("subirExcel")}</button>
        <input ref={fileRef} type="file" accept=".xlsx,.xls" onChange={onUpload} style={{ display: "none" }} />
        <button onClick={bajarExcel} disabled={!rows.length} title={t("excelBtnTitle", { moneda: cur === "usd" ? "USD" : "CRC" })}
          style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: rows.length ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", opacity: rows.length ? 1 : 0.5 }}>⬇ Excel</button>
        <button onClick={() => window.print()} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{tc("print")}</button>
      </div>

      {msg && <div style={{ color: "var(--positive)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {!loading && rows.length > 0 && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", minWidth: 1180, width: "100%" }}>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                <th style={{ textAlign: "left", padding: "10px 18px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.6, position: "sticky", left: 0, background: "var(--bg-header)", zIndex: 2, minWidth: 230 }}>{tc("account")}</th>
                {MONTHS_SHORT.map((m, mi) => (
                  <th key={mi} style={{ textAlign: "right", padding: "10px 12px", fontSize: 10, fontWeight: 800, color: months.includes(mi + 1) ? "var(--text-secondary)" : "var(--text-disabled)", textTransform: "uppercase", letterSpacing: 0.4, minWidth: 86 }}>{m}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const vals = cur === "usd" ? r.usd : r.crc;
                const isHeader = r.is_total && r.indent === 0 && ["asset", "liabilit", "capital"].some(k => r.label.toLowerCase().includes(k));
                const tint = isHeader ? SECTION_TINT[r.section] : (r.is_total ? "rgba(255,255,255,0.03)" : (i % 2 ? "rgba(255,255,255,0.015)" : "transparent"));
                const stickyBg = isHeader ? "var(--bg-surface)" : "var(--bg-elevated)";
                return (
                  <tr key={i} style={{ borderTop: "1px solid var(--border-subtle)", background: tint }}>
                    <td style={{ padding: isHeader ? "11px 18px" : "8px 18px", paddingLeft: 18 + r.indent * 18, fontSize: isHeader ? 14 : 13, fontWeight: r.is_total ? 800 : 500, color: isHeader ? "var(--brand)" : (r.is_total ? "var(--text-primary)" : "var(--text-secondary)"), textTransform: isHeader ? "uppercase" : "none", letterSpacing: isHeader ? 0.5 : 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 320, position: "sticky", left: 0, background: stickyBg, zIndex: 1 }}>{r.label}</td>
                    {MONTHS_SHORT.map((_, mi) => {
                      const v = vals[mi + 1] ?? 0;
                      return (
                        <td key={mi} className="mono" style={{ textAlign: "right", padding: "8px 12px", fontSize: r.is_total ? 13 : 12.5, fontWeight: r.is_total ? 800 : 600, color: v < 0 ? "var(--negative)" : (r.is_total ? "var(--text-primary)" : "var(--text-secondary)") }}>{Math.abs(v) < 0.005 ? "" : m2(v, cur === "usd" ? "$" : "₡")}</td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!loading && rows.length === 0 && !error && (
        <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center", marginTop: 24, lineHeight: 1.6 }}>
          {periods.length === 0
            ? <>{t("noBalance")}<br />{t("uploadHint")}<b>Balance Sheet</b>{t.rich("uploadHintCola", { boton: t("subirExcel"), b: (c: React.ReactNode) => <b>{c}</b> })}</>
            : <>{t("sinDatosAnio", { year })}</>}
        </div>
      )}

      {!loading && (
        <div className="no-print" style={{ marginTop: 18, display: "flex", justifyContent: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 760 }}>
            <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0 }}>i</span>
            {t.rich("excelHelp", { b: (c: React.ReactNode) => <b>{c}</b>, month: t("templateMonth"), check: t("check") })}
          </div>
        </div>
      )}
    </div>
  );
}
