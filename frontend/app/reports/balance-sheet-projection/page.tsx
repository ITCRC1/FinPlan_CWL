"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getScenarios, getBalanceSheetProjection,
  type Scenario, type BalanceProjection,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const GOLD = "#c8a24a";
const m0 = (v: number) => { const s = "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); return v < 0 ? `(${s})` : s; };
const SECTION_TINT: Record<string, string> = { ASSET: "rgba(38,166,154,0.10)", LIABILITY: "rgba(214,153,69,0.10)", EQUITY: "rgba(120,144,224,0.12)" };

export default function BalanceProjectionPage() {
  const tc = useTranslations("common");
  const tCf = useTranslations("cfDirect");
  const t = useTranslations("bsProj");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se eligio
  // abre con el Budget preferido del owner.
  const [scnId, setScnId] = useEscenarioDe("reports/balance-sheet-projection:budget", scenarios, "budget", undefined, true);
  const [data, setData] = useState<BalanceProjection | null>(null);
  const [showAnchor, setShowAnchor] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError(null);
    try { setData(await getBalanceSheetProjection(id, 24)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scnId) load(scnId); }, [scnId, load]);

  const ay = data?.anchor_year ?? new Date().getFullYear();
  const am = data?.anchor_month ?? 0;       // último mes real (ancla)
  const horizon = data?.horizon ?? 24;
  // etiqueta de la columna t (0 = ancla+1)
  const colLabel = (t: number) => { const idx = am + t; return `${MONTHS[idx % 12]}-${String((ay + Math.floor(idx / 12)) % 100).padStart(2, "0")}`; };
  const anchorLabel = `${MONTHS[(am - 1 + 12) % 12]}-${String(ay % 100).padStart(2, "0")}`;

  /* La sangría del balance va en `nivel` (no en espacios pegados al texto) y los
     totales en `es_total`. La columna del ancla sale si está mostrada en pantalla. */
  async function bajarExcel() {
    if (!data || !data.lines.length) return;
    const filas: FilaCuadro[] = data.lines.map(ln => ({
      label: ln.label, nivel: ln.indent, es_total: ln.is_total,
      valores: showAnchor ? [ln.anchor, ...ln.values] : [...ln.values],
    }));
    const scn = scenarios.find(s => s.id === scnId);
    try {
      await bajarCuadros("Balance_Sheet_Proyectado", [{
        titulo: t("titulo"),
        subtitulo: `${scn ? scnLabel(scn) : ""}${t("excelSubtitulo", { meses: horizon, ancla: anchorLabel })}`,
        hoja: t("hoja"),
        columnas: [
          { label: tc("account"), ancho: 44, formato: "texto" },
          ...(showAnchor ? [{ label: t("colReal", { mes: anchorLabel }), ancho: 15, formato: "usd2" as const }] : []),
          ...Array.from({ length: horizon }, (_, t2) => ({ label: colLabel(t2), ancho: 14, formato: "usd2" as const })),
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { padding: "8px 8px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textAlign: "right", whiteSpace: "nowrap" };

  return (
    <div className="print-dashboard pag pag-ancha" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={scnId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 32, fontWeight: 800, margin: 0 }}><span style={{ color: "var(--text-primary)" }}>Balance Sheet </span><span style={{ color: "var(--brand)" }}>{t("proyectado")}</span></h1>
        <div style={{ fontSize: 13.5, color: "var(--text-secondary)", fontWeight: 600, marginTop: 4 }}>{t.rich("subtitulo", { meses: horizon, ancla: anchorLabel, gold: (c) => <b style={{ color: GOLD }}>{c}</b> })}</div>
      </div>

      <div className="no-print" style={{ display: "flex", gap: 12, justifyContent: "center", alignItems: "flex-end", margin: "16px 0 16px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("scenario")}</span><select value={scnId} onChange={e => setScnId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <label style={{ alignSelf: "flex-end", display: "flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", cursor: "pointer" }}><input type="checkbox" checked={showAnchor} onChange={e => setShowAnchor(e.target.checked)} /> {t("mostrarAncla")}</label>
        <button onClick={() => window.print()} style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{tc("print")}</button>
        <button onClick={bajarExcel} disabled={!data?.lines.length} title={t("excelBtnTitle", { meses: horizon, extra: showAnchor ? t("excelBtnTitleAncla") : "" })}
          style={{ alignSelf: "flex-end", padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: data?.lines.length ? "pointer" : "default", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", opacity: data?.lines.length ? 1 : 0.5 }}>⬇ Excel</button>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {!loading && data && data.lines.length > 0 && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
          <table style={{ borderCollapse: "collapse", minWidth: 1700, width: "100%" }}>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                <th style={{ ...th, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-header)", minWidth: 260 }}>{tc("account")}</th>
                {showAnchor && <th style={{ ...th, color: GOLD, borderRight: "2px solid var(--border-medium)" }}>{t("colReal", { mes: anchorLabel })}</th>}
                {Array.from({ length: horizon }, (_, t) => <th key={t} style={th}>{colLabel(t)}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.lines.map((ln, ri) => {
                const isGrand = ln.is_total && ["total assets", "total liabilities", "capital & liab"].some(k => ln.label.toLowerCase().includes(k));
                const tint = isGrand ? "linear-gradient(90deg,#16234d,#244481)" : (ln.is_total ? (SECTION_TINT[ln.section] ?? "rgba(255,255,255,0.03)") : (ri % 2 ? "rgba(255,255,255,0.012)" : "transparent"));
                const fg = isGrand ? "#fff" : (ln.is_total ? "var(--text-primary)" : "var(--text-secondary)");
                return (
                  <tr key={ri} style={{ borderTop: "1px solid var(--border-subtle)", background: tint }}>
                    <td style={{ padding: ln.is_total ? "9px 12px" : "6px 12px", paddingLeft: 12 + ln.indent * 14, fontSize: ln.is_total ? 12.5 : 12, fontWeight: ln.is_total ? 800 : 500, color: isGrand ? "#fff" : (ln.is_total ? "var(--text-primary)" : "var(--text-primary)"), whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 320, position: "sticky", left: 0, background: ln.is_total ? (isGrand ? "var(--accent-total)" : "var(--bg-elevated)") : "var(--bg-elevated)" }}>{ln.label}</td>
                    {showAnchor && <td className="mono" style={{ textAlign: "right", padding: "6px 8px", fontSize: 12, fontWeight: ln.is_total ? 800 : 600, color: GOLD, whiteSpace: "nowrap", borderRight: "2px solid var(--border-medium)" }}>{Math.abs(ln.anchor) < 0.5 ? "—" : m0(ln.anchor)}</td>}
                    {ln.values.map((v, t) => <td key={t} className="mono" style={{ textAlign: "right", padding: "6px 8px", fontSize: 12, fontWeight: ln.is_total ? 800 : 500, color: isGrand ? "#fff" : (v < 0 ? "var(--negative)" : fg), whiteSpace: "nowrap" }}>{Math.abs(v) < 0.5 ? "—" : m0(v)}</td>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!loading && (
        <div className="no-print" style={{ marginTop: 16, display: "flex", justifyContent: "center" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 980 }}>
            <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0 }}>i</span>
            <span style={{ lineHeight: 1.6 }}>
            {t.rich("nota", { ancla: anchorLabel, ultimo: t("lastRealBalance"), criterios: tCf("criteria"), b: (c) => <b>{c}</b> })}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
