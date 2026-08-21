"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, Legend, CartesianGrid, LabelList } from "recharts";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import {
  getScenarios, getChannelMix, getChannelMixEntry, saveChannelMixEntry, getPanoramaCanales,
  importChannelXml, CountryXmlElegirMes, CountryXmlPisaria,
  urlExcelCanales, urlPlantillaCanales, subirPlantillaCanales, authHeaders,
  type Scenario, type ChannelMix, type ChannelMixEntryRow, type ChannelMetric, type PanoramaCanales,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
const ICONS: Record<string,string> = {
  "Travel Agency": "👥", "Direct Client + Website": "💻", "OTA": "🌐", "Other / In-House": "🏨",
};
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const numF = (v: string) => { const n = parseFloat((v || "").toString().replace(/[, %]/g, "")); return isNaN(n) ? 0 : n; };
const pct1 = (v: number) => (v * 100).toFixed(2) + "%";
const pp1 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(2) + "pp";

export default function ChannelMixPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("channelMix");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Cada selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca
  // se eligio abre con el preferido del owner.
  const [actId, setActId] = useEscenarioDe("marketing-insight/channel-mix:actual", scenarios, "actual");
  const [budId, setBudId] = useEscenarioDe("marketing-insight/channel-mix:budget", scenarios, "budget", undefined, true);
  const [ytd, setYtd] = useState(12);
  const [metric, setMetric] = useState<ChannelMetric>("rooms");
  const [act, setAct] = useState<ChannelMix | null>(null);
  const [bud, setBud] = useState<ChannelMix | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  // editor
  const [editing, setEditing] = useState(false);
  const [editScn, setEditScn] = useState("");
  const [channels, setChannels] = useState<string[]>([]);
  const [grid, setGrid] = useState<string[][]>([]);   // [12][nChannels]
  const [saving, setSaving] = useState(false);

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

  // YTD por defecto = último mes con datos del Actual (métrica rooms). Se hace
  // una sola vez, cuando el Actual queda resuelto: si se recalculara en cada
  // cambio de escenario le pisaría al usuario el YTD que eligió a mano.
  const yaFijoYtd = useRef(false);
  useEffect(() => {
    if (!actId || yaFijoYtd.current) return;
    yaFijoYtd.current = true;
    (async () => {
      try {
        const e = await getChannelMixEntry(actId, "rooms");
        let maxM = 0;
        e.rows.forEach(r => { if (r.values.some(v => v)) maxM = Math.max(maxM, r.month); });
        if (maxM) setYtd(maxM);
      } catch { /* ignore */ }
    })();
  }, [actId]);

  const load = useCallback(async (aid: string, bid: string, y: number, mt: ChannelMetric) => {
    if (!aid || !bid) return;
    setLoading(true); setError(null);
    try { const [a, b] = await Promise.all([getChannelMix(aid, y, mt), getChannelMix(bid, y, mt)]); setAct(a); setBud(b); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (actId && budId) load(actId, budId, ytd, metric); }, [actId, budId, ytd, metric, load]);

  /** Las DOS capas. «A mí me gustaría hacer varias capas: la general y también
   *  la detallada» (owner, 18-ago-2026).
   *
   *  El resumen es por CANAL —los KPI groups de Opera— y el detalle es por
   *  MARKET CODE, que es el átomo del que sale todo. El detalle no guarda nada
   *  aparte: la relación código → canal vive en `market_codes` (Master Data) y
   *  las dos vistas salen de ahí, así que el resumen no puede discrepar del
   *  detalle porque se deriva de él. */
  const [capa, setCapa] = useState<"resumen" | "detalle">("resumen");
  const xmlRef = useRef<HTMLInputElement>(null);
  const plaRef = useRef<HTMLInputElement>(null);
  const [pendiente, setPendiente] = useState<File | null>(null);

  /** Bajar un .xlsx que el backend genera. Va con `authHeaders`, así que no
   *  puede ser un <a href> pelado. */
  async function bajarArchivo(url: string, nombre: string) {
    setMsgXml(null);
    try {
      const res = await fetch(url, { headers: authHeaders() });
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = nombre;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (ex) { setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`); }
  }

  /** Sube la plantilla. Primero REVISA y recién con el segundo clic guarda:
   *  reemplaza el detalle entero del escenario y recalcula el resumen. */
  async function subirPlantilla(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f || !actId) return;
    setSubiendo(true); setMsgXml(null);
    try {
      const r = await subirPlantillaCanales(actId, f, false);
      const sc = r.sin_canal.length
        ? t("sinCanalAviso", { codes: r.sin_canal.join(", ") })
        : "";
      if (!r.total_cambios) { setMsgXml(t("archivoSinCambios") + sc); setPendiente(null); }
      else {
        const det = r.cambios.slice(0, 6).map(c =>
          `${c.code} (${c.metric === "rooms" ? t("abrevHab") : "pax"}): ${c.antes ?? "—"} → ${c.ahora ?? "—"}`).join(" · ");
        setMsgXml(t("revision", { n: r.total_cambios, filas: r.filas, det })
          + (r.total_cambios > 6 ? t("revisionMas", { n: r.total_cambios - 6 }) : "") + sc
          + t("revisionAplicar"));
        setPendiente(f);
      }
    } catch (ex) { setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`); setPendiente(null); }
    finally { setSubiendo(false); if (plaRef.current) plaRef.current.value = ""; }
  }

  async function guardarPlantilla() {
    if (!pendiente || !actId) return;
    setSubiendo(true);
    try {
      const r = await subirPlantillaCanales(actId, pendiente, true);
      setMsgXml(t("guardadoPlantilla", { n: r.total_cambios, celdas: r.celdas ?? 0 }));
      setPendiente(null);
      load(actId, budId, ytd, metric);
    } catch (ex) { setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`); }
    finally { setSubiendo(false); }
  }
  const [subiendo, setSubiendo] = useState(false);
  const [msgXml, setMsgXml] = useState<string | null>(null);
  const [xmlMeses, setXmlMeses] = useState<{ archivo: File; meses: number[] } | null>(null);
  const [xmlPisaria, setXmlPisaria] = useState<{ archivo: File; mes: number } | null>(null);

  /** Sube el XML de market codes. Mismas dos reglas que en Country Mix: un mes
   *  por vez, y no pisar lo corregido a mano. Los 409 no son fallos — son la
   *  pregunta que falta o la decisión que hay que tomar. */
  async function correrImport(f: File, sobrescribir: boolean, mes?: number) {
    if (!actId) return;
    setSubiendo(true); setMsgXml(null);
    try {
      const r = await importChannelXml(actId, f, { sobrescribir, month: mes });
      const sc = r.sin_canal.length
        ? t("xmlSinCanal", { n: r.sin_canal.length })
          + r.sin_canal.slice(0, 6).map(x => t("xmlSinCanalCode", { code: x.code, noches: Math.round(x.noches) })).join(" · ")
          + t("xmlSinCanalFin")
        : "";
      setMsgXml(t("xmlCargado", {
        mes: MONTHS[r.month - 1], year: r.year,
        noches: Math.round(r.total_noches).toLocaleString("en-US"),
        pax: Math.round(r.total_pax).toLocaleString("en-US"),
        canales: r.canales.length, filas: r.filas_detalle,
      }) + sc);
      setXmlMeses(null); setXmlPisaria(null);
      load(actId, budId, ytd, metric);
    } catch (ex) {
      if (ex instanceof CountryXmlElegirMes) { setXmlMeses({ archivo: f, meses: ex.meses }); setMsgXml(ex.message); }
      else if (ex instanceof CountryXmlPisaria) { setXmlPisaria({ archivo: f, mes: ex.meses[0] }); setMsgXml(`⚠️ ${ex.message}`); }
      else { setMsgXml(`Error: ${ex instanceof Error ? ex.message : String(ex)}`); setXmlMeses(null); setXmlPisaria(null); }
    } finally { setSubiendo(false); }
  }
  const [codigos, setCodigos] = useState<PanoramaCanales["market_codes"]>([]);
  useEffect(() => {
    getPanoramaCanales().then(p => setCodigos(p.market_codes)).catch(() => setCodigos([]));
  }, []);

  /** Los market codes agrupados por su canal, en el orden de la tabla. */
  const porCanal = useMemo(() => {
    const m = new Map<string, PanoramaCanales["market_codes"]>();
    for (const c of codigos) {
      if (!c.activo) continue;
      const k = c.canal || "";        // vacío = sin canal, y se muestra así
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(c);
    }
    return [...m.entries()].sort((a, b) => (a[0] ? 0 : 1) - (b[0] ? 0 : 1));
  }, [codigos]);

  const rows = useMemo(() => {
    if (!act) return [];
    return act.channels.map(c => {
      const bc = bud?.channels.find(x => x.channel === c.channel);
      const aPct = c.pct, bPct = bc?.pct ?? 0;
      return { channel: c.channel, aPct, bPct, varpp: (aPct - bPct) * 100 };
    });
  }, [act, bud]);
  const chart = rows.map(r => ({ channel: r.channel, Actual: +(r.aPct*100).toFixed(2), Budget: +(r.bPct*100).toFixed(2) }));

  async function openEditor() {
    const target = editScn || actId;
    if (!target) return;
    setMsg(null);
    try {
      const e = await getChannelMixEntry(target, metric);
      setChannels(e.channels);
      setGrid(e.rows.map(r => r.values.map(v => v ? String(v) : "")));
      setEditScn(target);
      setEditing(true);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }
  async function reloadEditor(target: string) {
    try { const e = await getChannelMixEntry(target, metric); setChannels(e.channels); setGrid(e.rows.map(r => r.values.map(v => v ? String(v) : ""))); }
    catch { /* ignore */ }
  }
  function setCell(mi: number, ci: number, v: string) { setGrid(prev => prev.map((row, i) => i === mi ? row.map((c, j) => j === ci ? v : c) : row)); }
  function paste(mi: number, ci: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const cells = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setGrid(prev => {
      const next = prev.map(r => [...r]);
      cells.forEach((rowc, dr) => { const m = mi + dr; if (m >= next.length) return; rowc.forEach((cell, dc) => { const c = ci + dc; if (c >= channels.length) return; next[m][c] = String(numF(cell)); }); });
      return next;
    });
  }
  async function saveEntry() {
    if (!editScn) return;
    setSaving(true); setMsg(null);
    try {
      const payload: ChannelMixEntryRow[] = grid.map((row, i) => ({ month: i + 1, values: row.map(c => numF(c)) }));
      const res = await saveChannelMixEntry(editScn, payload, metric);
      setMsg(t("guardadoEntry", { metric: metric === "pax" ? "Pax" : t("metricRooms"), scn: scenarios.find(s => s.id === editScn) ? scnLabel(scenarios.find(s => s.id === editScn)!) : editScn, n: res.rows_saved }));
      setEditing(false);
      load(actId, budId, ytd, metric);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setSaving(false); }
  }

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // El cuadro de pantalla con la métrica y el corte YTD puestos. Los % van como
  // fracción y la variación en puntos también (0.0123 = +1.23pp).
  async function bajarExcel() {
    setMsg(null);
    if (!act || !rows.length) { setMsg(`Error: ${t("noDataExport")}`); return; }
    const filas: FilaCuadro[] = rows.map(r => ({
      label: r.channel, valores: [r.aPct, r.bPct, r.varpp / 100],
    }));
    filas.push({
      label: "TOTAL", es_total: true,
      valores: [rows.reduce((t, r) => t + r.aPct, 0),
                rows.reduce((t, r) => t + r.bPct, 0),
                rows.reduce((t, r) => t + r.varpp, 0) / 100],
    });
    const aScn = scenarios.find(s => s.id === actId), bScn = scenarios.find(s => s.id === budId);
    try {
      await bajarCuadros("Channel_Mix", [{
        titulo: "Channel Mix vs Budget",
        subtitulo: t("excelSubtitulo", { a: aScn ? scnLabel(aScn) : "Actual", b: bScn ? scnLabel(bScn) : "Budget", mes: MONTHS[ytd - 1], metric: metric === "pax" ? "Pax" : t("metricRooms") }),
        hoja: "Channel Mix",
        columnas: [
          { label: "Channel", ancho: 30, formato: "texto" },
          { label: `Actual YTD ${MONTHS[ytd - 1]}`, ancho: 18, formato: "pct" },
          { label: "Budget", ancho: 14, formato: "pct" },
          { label: "Variance (pp)", ancho: 15, formato: "pct" },
        ],
        filas,
      }]);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { padding: "8px 14px", fontSize: 11, color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.4 };
  const td: React.CSSProperties = { padding: "9px 14px", fontSize: 14, textAlign: "right" };
  const inp: React.CSSProperties = { width: "100%", textAlign: "right", padding: "4px 6px", background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 3, color: "var(--text-primary)", fontSize: 12.5, outline: "none" };

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "22px 26px 48px" }}>
      <IrA esc={budId} />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Channel Mix <span style={{ color: "var(--brand)" }}>vs Budget</span></h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>{t("subtitle", { hotel: hotel.nombre })}<b style={{ color: "var(--text-primary)" }}>YTD {MONTHS[ytd-1]}</b> · <b style={{ color: "var(--text-primary)" }}>{metric === "pax" ? "Pax" : t("metricRooms")}</b> · {t("variancePp")}</p>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("metric")}</span>
            <div style={{ display: "flex", border: "1px solid var(--border-medium)", borderRadius: 5, overflow: "hidden" }}>
              {(["rooms", "pax"] as ChannelMetric[]).map(mt => (
                <button key={mt} onClick={() => setMetric(mt)} style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none", background: metric === mt ? "var(--brand)" : "var(--bg-input)", color: metric === mt ? "#fff" : "var(--text-secondary)" }}>{mt === "rooms" ? t("metricRooms") : "Pax"}</button>
              ))}
            </div>
          </div>
          <input ref={xmlRef} type="file" accept=".xml,.XML" style={{ display: "none" }} onChange={e => { const f = e.target.files?.[0]; if (f) correrImport(f, false); if (xmlRef.current) xmlRef.current.value = ""; }} />
          <button onClick={() => xmlRef.current?.click()} disabled={subiendo}
            title={t("xmlTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: subiendo ? "default" : "pointer", background: "var(--accent-xml)", color: "#fff", border: "none", alignSelf: "flex-end", opacity: subiendo ? 0.6 : 1 }}>
            {subiendo ? t("uploading") : "⬆ XML Opera"}
          </button>
          <button onClick={() => { setEditScn(actId); openEditor(); }} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--positive)", color: "#fff", border: "none", alignSelf: "flex-end" }}>{t("loadChannels")}</button>
          <button onClick={() => bajarArchivo(urlExcelCanales(actId), `ChannelMix_${actId.slice(0, 8)}.xlsx`)}
            title={t("excelTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", alignSelf: "flex-end" }}>⬇ Excel</button>
          <input ref={plaRef} type="file" accept=".xlsx,.XLSX" style={{ display: "none" }} onChange={subirPlantilla} />
          <button onClick={() => bajarArchivo(urlPlantillaCanales(actId), `ChannelMix_plantilla_${actId.slice(0, 8)}.xlsx`)}
            title={t("plantillaTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--brand)", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{t("plantillaBtn")}</button>
          <button onClick={() => plaRef.current?.click()} disabled={subiendo}
            title={t("plantillaUpTitle")}
            style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: subiendo ? "default" : "pointer", background: "var(--brand)", color: "#fff", border: "none", alignSelf: "flex-end", opacity: subiendo ? 0.6 : 1 }}>{t("plantillaUpBtn")}</button>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{tc("print")}</button>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("ytdThrough")}</span><select value={ytd} onChange={e => setYtd(Number(e.target.value))} style={sel}>{MONTHS.map((m, i) => <option key={i} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Actual</span><select value={actId} onChange={e => setActId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>Budget</span><select value={budId} onChange={e => setBudId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        </div>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {msg && <div style={{ color: msg.startsWith("Error") ? "var(--negative)" : "var(--positive)", fontSize: 12.5, marginBottom: 8 }}>{msg}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {/* Editor */}
      {editing && (
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--positive)", borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ padding: "10px 16px", background: "rgba(38,166,154,0.1)", borderBottom: "1px solid var(--border-medium)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{t("loadTitle")}</span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 700 }}>{tc("saveIn")}</span>
              <select value={editScn} onChange={e => { setEditScn(e.target.value); reloadEditor(e.target.value); }} style={{ ...sel, padding: "4px 8px", fontSize: 12 }}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select>
              <button onClick={saveEntry} disabled={saving} style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: saving ? "default" : "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>{saving ? tc("saving") : `💾 ${tc("save")}`}</button>
              <button onClick={() => setEditing(false)} style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{tc("close")}</button>
            </div>
          </div>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead><tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...th, textAlign: "left" }}>{tc("month")}</th>
                {channels.map(ch => <th key={ch} style={{ ...th, textAlign: "right", color: "var(--brand)" }}>{ICONS[ch] ?? ""} {ch}</th>)}
              </tr></thead>
              <tbody>
                {grid.map((row, mi) => (
                  <tr key={mi} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "3px 14px", fontSize: 12.5 }}>{MONTHS[mi]}</td>
                    {row.map((c, ci) => (
                      <td key={ci} style={{ padding: "2px 6px" }}><input className="mono" value={c} onChange={e => setCell(mi, ci, e.target.value)} onPaste={e => paste(mi, ci, e)} onFocus={e => e.target.select()} style={inp} /></td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "8px 14px", fontSize: 11.5, color: "var(--text-secondary)" }}>{t("pasteHint")}</div>
        </div>
      )}

      {msgXml && (
        <div style={{ fontSize: 12.5, marginBottom: 10, padding: "8px 12px", borderRadius: 6, whiteSpace: "pre-line",
                      border: `1px solid ${msgXml.startsWith("Error") ? "var(--negative)" : msgXml.startsWith("⚠️") ? "var(--warning)" : "var(--positive)"}`,
                      background: "rgba(255,255,255,.03)",
                      color: msgXml.startsWith("Error") ? "var(--negative)" : msgXml.startsWith("⚠️") ? "var(--warning)" : "var(--positive)" }}>
          {msgXml}
          {xmlMeses && (
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {xmlMeses.meses.map(m => (
                <button key={m} disabled={subiendo} onClick={() => correrImport(xmlMeses.archivo, false, m)}
                  style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "none" }}>{MONTHS[m - 1]}</button>
              ))}
              <button onClick={() => { setXmlMeses(null); setMsgXml(null); }}
                style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{tc("cancel")}</button>
            </div>
          )}
          {pendiente && (
            <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button onClick={guardarPlantilla} disabled={subiendo}
                style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>{t("saveChanges")}</button>
              <button onClick={() => { setPendiente(null); setMsgXml(null); }}
                style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{t("discard")}</button>
            </div>
          )}
          {xmlPisaria && (
            <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button disabled={subiendo} onClick={() => correrImport(xmlPisaria.archivo, true, xmlPisaria.mes)}
                style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--negative)", color: "#fff", border: "none" }}>
                {t("overwriteXml", { mes: MONTHS[xmlPisaria.mes - 1] })}
              </button>
              <button onClick={() => { setXmlPisaria(null); setMsgXml(null); }}
                style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{t("leaveAsIs")}</button>
            </div>
          )}
        </div>
      )}

      {!loading && act && bud && <>
        {/* Las dos capas: resumen por canal, detalle por market code. */}
        <div className="no-print" style={{ display: "inline-flex", border: "1px solid var(--border-medium)", borderRadius: 6, overflow: "hidden", marginBottom: 14 }}>
          {(([["resumen", t("capaResumen")], ["detalle", t("capaDetalle")]]) as [("resumen" | "detalle"), string][]).map(([k, lbl]) => (
            <button key={k} onClick={() => setCapa(k)}
              style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", border: "none",
                       background: capa === k ? "var(--brand)" : "var(--bg-elevated)",
                       color: capa === k ? "#fff" : "var(--text-secondary)" }}>{lbl}</button>
          ))}
        </div>

        {capa === "detalle" && (
          <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, marginBottom: 18, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                  <th style={{ ...th, textAlign: "left" }}>Market codes</th>
                  <th style={{ ...th, textAlign: "left" }}>{t("colCanal")}</th>
                  <th style={{ ...th, textAlign: "left" }}>{t("colDetalle")}</th>
                </tr>
              </thead>
              <tbody>
                {porCanal.map(([canal, cods]) => (
                  <tr key={canal || "(sin canal)"} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td style={{ padding: "9px 14px", fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
                      {cods.map(c => c.code).join(" + ")}
                    </td>
                    <td style={{ padding: "9px 14px", fontSize: 13, fontWeight: 700, color: canal ? "var(--brand)" : "var(--warning)" }}>
                      {canal ? <><span style={{ marginRight: 6 }}>{ICONS[canal] ?? ""}</span>{canal}</> : t("sinCanalAsignado")}
                    </td>
                    <td style={{ padding: "9px 14px", fontSize: 11.5, color: "var(--text-secondary)" }}>
                      {cods.map(c => c.nombre).filter(Boolean).join(" · ")}
                    </td>
                  </tr>
                ))}
                {!porCanal.length && (
                  <tr><td colSpan={3} style={{ padding: "12px 14px", fontSize: 12.5, color: "var(--text-secondary)" }}>
                    {t("noMarketCodes")}
                  </td></tr>
                )}
              </tbody>
            </table>
            <div style={{ padding: "9px 14px", fontSize: 11.5, color: "var(--text-secondary)", borderTop: "1px solid var(--border-subtle)" }}>
              {t.rich("detalleNota", { b: (c) => <b>{c}</b> })}
            </div>
          </div>
        )}

        {/* Tabla */}
        <div className="fin-sticky" hidden={capa !== "resumen"} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, marginBottom: 18 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)" }}>
                <th style={{ ...th, textAlign: "left" }}>Channel</th>
                <th style={{ ...th, textAlign: "right" }}>Actual YTD {MONTHS[ytd-1]}</th>
                <th style={{ ...th, textAlign: "right" }}>Budget</th>
                <th style={{ ...th, textAlign: "right" }}>Variance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.channel} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "9px 14px", fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}><span style={{ marginRight: 8 }}>{ICONS[r.channel] ?? ""}</span>{r.channel}</td>
                  <td className="mono" style={{ ...td, fontWeight: 700, color: "var(--text-primary)" }}>{pct1(r.aPct)}</td>
                  <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{pct1(r.bPct)}</td>
                  <td className="mono" style={{ ...td, fontWeight: 800, color: Math.abs(r.varpp) < 0.005 ? "var(--text-secondary)" : r.varpp >= 0 ? "var(--positive)" : "var(--negative)" }}>{pp1(r.varpp)}</td>
                </tr>
              ))}
              <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(58,111,216,0.08)", fontWeight: 800 }}>
                <td style={{ padding: "9px 14px", fontSize: 14, fontWeight: 800 }}>TOTAL</td>
                <td className="mono" style={{ ...td, fontWeight: 800 }}>{pct1(rows.reduce((t, r) => t + r.aPct, 0))}</td>
                <td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{pct1(rows.reduce((t, r) => t + r.bPct, 0))}</td>
                <td className="mono" style={{ ...td, fontWeight: 800, color: "var(--text-secondary)" }}>{pp1(rows.reduce((t, r) => t + r.varpp, 0))}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Gráfico Actual vs Budget por canal */}
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "16px 18px" }}>
          <div style={{ fontSize: 14, fontWeight: 700, textAlign: "center", marginBottom: 8 }}>{t("actualVsBudget")}</div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chart} margin={{ top: 22, right: 16, left: 8, bottom: 4 }} barCategoryGap="26%">
              <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
              <XAxis dataKey="channel" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `${v}%`} width={42} />
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} formatter={(v: any, n: any) => [`${v}%`, n]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="Actual" fill="#3A6FD8" radius={[2,2,0,0]}>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <LabelList dataKey="Actual" position="top" fill="#9fb4e0" fontSize={10} formatter={(v: any) => `${v}%`} />
              </Bar>
              <Bar dataKey="Budget" fill="#6b7280" radius={[2,2,0,0]}>
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <LabelList dataKey="Budget" position="top" fill="#9aa1ad" fontSize={10} formatter={(v: any) => `${v}%`} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {!act.has_data && <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12 }}>{t("noChannels")}<b>{t("loadChannels")}</b>{t("noChannelsTail")}</p>}
        <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 12, fontStyle: "italic" }}>{t("notePp")}</p>
      </>}
    </div>
  );
}
