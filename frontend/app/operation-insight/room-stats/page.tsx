"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip, LabelList } from "recharts";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getRevenueByRoomType, importRoomStats, getRoomStatsEntry, saveRoomStatsEntry, rtLabel,
  type Scenario, type RevenueByRoomType, type RoomTypeRow,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

type EntryRow = { room_type_name: string; units: number; nights_available: number; no: string; pax: string; rev: string };
const ENTRY_COLS: ("no"|"pax"|"rev")[] = ["no", "pax", "rev"];
const numF = (v: string) => { const n = parseFloat((v || "").toString().replace(/[, $]/g, "")); return isNaN(n) ? 0 : n; };

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const TYPE_LABEL: Record<string,string> = { ACTUAL:"Actual", BUDGET:"Budget", FORECAST:"Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual","from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}
const money = (v: number) => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money0 = (v: number) => "$" + Math.round(v).toLocaleString("en-US");
const int = (v: number) => Math.round(v).toLocaleString("en-US");

// Paleta navy/gold (como la referencia ejecutiva)
const PALETTE = ["#C8A24A", "#1F3A6E", "#6E86B8", "#34508A", "#9FB2D0", "#E7DBBE", "#4A6298", "#B9863A"];

export default function OperationRoomStatsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("roomStats");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Las estadisticas de habitacion se cargan sobre el presupuesto en armado, y
  // la pantalla se acuerda de cual se estaba trabajando.
  const [rsId, setRsId] = useEscenarioDe("operation-insight/room-stats:budget", scenarios, "budget", undefined, true);
  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(5);
  const [rs, setRs] = useState<RevenueByRoomType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // Carga/edición manual del mes (copy-paste)
  const [editing, setEditing] = useState(false);
  const [entryRows, setEntryRows] = useState<EntryRow[]>([]);
  const [entrySaving, setEntrySaving] = useState(false);
  const [entryMsg, setEntryMsg] = useState<string | null>(null);

  async function openEntry() {
    if (!rsId) return;
    setEntryMsg(null);
    try {
      const d = await getRoomStatsEntry(rsId, month);
      setEntryRows(d.rows.map(r => ({ room_type_name: r.room_type_name, units: r.units, nights_available: r.nights_available,
        no: r.nights_occupied ? String(r.nights_occupied) : "", pax: r.pax ? String(r.pax) : "", rev: r.revenue ? String(r.revenue) : "" })));
      setEditing(true);
    } catch (e) { setEntryMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }
  function setEntryCell(ri: number, col: "no"|"pax"|"rev", v: string) {
    setEntryRows(prev => prev.map((r, i) => i === ri ? { ...r, [col]: v } : r));
  }
  function handleEntryPaste(ri: number, ci: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const grid = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setEntryRows(prev => {
      const next = prev.map(r => ({ ...r }));
      grid.forEach((cells, dr) => {
        const r = ri + dr; if (r >= next.length) return;
        cells.forEach((cell, dc) => { const c = ci + dc; if (c >= ENTRY_COLS.length) return; next[r][ENTRY_COLS[c]] = String(numF(cell)); });
      });
      return next;
    });
  }
  async function saveEntry() {
    if (!rsId) return;
    setEntrySaving(true); setEntryMsg(null);
    try {
      const payload = entryRows.map(r => ({ room_type_name: r.room_type_name, units: r.units, nights_occupied: numF(r.no), revenue: numF(r.rev), pax: numF(r.pax) }));
      const res = await saveRoomStatsEntry(rsId, month, payload);
      setEntryMsg(t("guardadoMes", { mes: MONTHS[month-1], filas: res.rows_saved }));
      const d = await getRevenueByRoomType(rsId); setRs(d); setYear(d.year);
      setEditing(false);
    } catch (e) { setEntryMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
    finally { setEntrySaving(false); }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !rsId) return;
    setUploading(true); setUploadMsg(null);
    try {
      const r = await importRoomStats(rsId, file, false);
      setUploadMsg(t("cargado", { meses: r.months_present.join(", "), filas: r.rows, rev: r.total_revenue.toLocaleString("en-US") }));
      const d = await getRevenueByRoomType(rsId); setRs(d); setYear(d.year);
    } catch (ex) {
      setUploadMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

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

  useEffect(() => {
    if (!rsId) { setRs(null); return; }
    setLoading(true);
    getRevenueByRoomType(rsId).then(d => { setRs(d); setYear(d.year); }).catch(e => setError(e instanceof Error ? e.message : "Error")).finally(() => setLoading(false));
  }, [rsId]);

  // `acc` incluye "Other Rooms Revenue" (units=0, ingreso sin tipo asociado —
  // p.ej. no-show, penalidades). `rows` la saca de la tabla/torta por categoría
  // porque no tiene ocupación ni ADR que mostrar; pero su plata SIGUE siendo
  // ingreso real y tiene que sumar al Total Revenue — antes desaparecía
  // callada del KPI y del Excel, sin que la fila filtrada avisara que faltaba.
  const { rows, otherRevenue } = useMemo(() => {
    if (!rs) return { rows: [] as (RoomTypeRow & { pct_of_total: number })[], otherRevenue: 0 };
    const acc: Record<string, RoomTypeRow> = {};
    for (const rt of rs.room_types)
      acc[rt.id] = { room_type_id: rt.id, room_type_code: rt.code, room_type_name: rt.name, units: rt.units, nights_available: 0, nights_occupied: 0, occupancy_pct: 0, revenue: 0, adr: 0, pax: 0 };
    for (const mo of rs.months) {
      if (mo.month > month) continue;
      for (const r of mo.rows) {
        const a = acc[r.room_type_id]; if (!a) continue;
        a.nights_available += r.nights_available; a.nights_occupied += r.nights_occupied;
        a.revenue += r.revenue; a.pax += r.pax;
      }
    }
    const all = Object.values(acc);
    const other = all.filter(a => a.units === 0).reduce((s, a) => s + a.revenue, 0);
    const total = all.reduce((s, a) => s + a.revenue, 0);
    const filtered = all
      .map(a => ({ ...a, occupancy_pct: a.nights_available ? a.nights_occupied / a.nights_available : 0, adr: a.nights_occupied ? a.revenue / a.nights_occupied : 0, pct_of_total: total ? a.revenue / total : 0 }))
      .filter(a => a.units > 0)
      .sort((x, y) => y.revenue - x.revenue);
    return { rows: filtered, otherRevenue: other };
  }, [rs, month]);

  const tot = rows.reduce((t, r) => ({ units: t.units + r.units, na: t.na + r.nights_available, no: t.no + r.nights_occupied, rev: t.rev + r.revenue, pax: t.pax + r.pax }),
    { units: 0, na: 0, no: 0, rev: 0 + otherRevenue, pax: 0 });
  const occTotal = tot.na ? tot.no / tot.na : 0;
  const adrTotal = tot.no ? tot.rev / tot.no : 0;

  // Executive Insight
  const insight = useMemo(() => {
    if (!rows.length) return "";
    const topRev = rows[0];
    const topAdr = [...rows].sort((a, b) => b.adr - a.adr)[0];
    const topOcc = [...rows].sort((a, b) => b.occupancy_pct - a.occupancy_pct)[0];
    return t("insightAdr", { name: topAdr.room_type_name, adr: money(topAdr.adr) })
      + (topAdr.room_type_id === topRev.room_type_id
          ? t("insightMismo", { pct: (topRev.pct_of_total*100).toFixed(1) })
          : t("insightOtro", { name: topRev.room_type_name, pct: (topRev.pct_of_total*100).toFixed(1) }))
      + t("insightOcc", { name: topOcc.room_type_name, occ: (topOcc.occupancy_pct*100).toFixed(1), total: (occTotal*100).toFixed(1) });
  }, [rows, occTotal, t]);

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // El mismo cuadro que está en pantalla, con el escenario y el corte YTD que el
  // usuario tenga puestos. Se le agregan las noches disponibles/ocupadas (que en
  // pantalla viven en las tarjetas KPI) para que el archivo se baste solo.
  async function bajarExcel() {
    setUploadMsg(null);
    if (!rows.length) { setUploadMsg(`Error: ${t("noRowsExport")}`); return; }
    const filas: FilaCuadro[] = rows.map(r => ({
      label: rtLabel(r.room_type_code, r.room_type_name),
      valores: [r.units, r.nights_available, r.nights_occupied, r.occupancy_pct, r.adr, r.revenue, r.pax, r.pct_of_total],
    }));
    if (otherRevenue !== 0) {
      filas.push({
        label: t("otherRoomsRevenue"),
        valores: [0, 0, 0, 0, 0, otherRevenue, 0, tot.rev ? otherRevenue / tot.rev : 0],
      });
    }
    filas.push({
      label: "TOTAL", es_total: true,
      valores: [tot.units, tot.na, tot.no, occTotal, adrTotal, tot.rev, tot.pax, 1],
    });
    const scn = scenarios.find(s => s.id === rsId);
    try {
      await bajarCuadros("Room_Stats", [{
        titulo: `Rooms Statistics · YTD ${MONTHS_EN[month - 1]} ${year}`,
        subtitulo: t("excelSubtitulo", { scn: scn ? scnLabel(scn) : "", mes: MONTHS[month - 1] }),
        hoja: "Room Stats",
        columnas: [
          { label: "Room Category", ancho: 34, formato: "texto" },
          { label: "Units", ancho: 9, formato: "num" },
          { label: t("nochesDisp"), ancho: 13, formato: "num" },
          { label: t("nochesOcup"), ancho: 13, formato: "num" },
          { label: "Occupancy", ancho: 12, formato: "pct" },
          { label: "ADR", ancho: 13, formato: "usd2" },
          { label: "Total Revenue", ancho: 16, formato: "usd" },
          { label: "Total Pax", ancho: 12, formato: "num" },
          { label: "% Mix Revenue", ancho: 13, formato: "pct" },
        ],
        filas,
      }]);
    } catch (e) { setUploadMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 5, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const th: React.CSSProperties = { textAlign: "right", padding: "5px 10px", fontSize: 10.5, color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase", whiteSpace: "nowrap" };
  const td: React.CSSProperties = { textAlign: "right", padding: "3px 8px", fontSize: 12.5 };

  const KPI = ({ label, value }: { label: string; value: string }) => (
    <div style={{ flex: "1 1 0", minWidth: 110, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 12px", textAlign: "center" }}>
      <div style={{ fontSize: 10.5, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 8 }}>{label}</div>
      <div className="mono" style={{ fontSize: 22, fontWeight: 800, color: "var(--text-primary)" }}>{value}</div>
    </div>
  );

  const pieData = rows.map((r, i) => ({ name: rtLabel(r.room_type_code, r.room_type_name), value: r.revenue, pct: r.pct_of_total, fill: PALETTE[i % PALETTE.length] }));

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "20px 24px 48px" }}>
      <IrA esc={rsId} />
      {/* Banner */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
        <div style={{ flex: 1, minWidth: 280, background: "linear-gradient(90deg, var(--bg-header), #1b2a52)", border: "1px solid var(--border-medium)", borderLeft: "4px solid #C8A24A", borderRadius: 8, padding: "12px 20px" }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
            Rooms Statistics <span style={{ color: "#C8A24A" }}>YTD {MONTHS_EN[month-1]} {year}</span>
          </h1>
        </div>
        <div className="no-print" style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <button onClick={openEntry} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--positive)", color: "#fff", border: "none", alignSelf: "flex-end" }}>{t("cargarEditar", { mes: MONTHS[month-1] })}</button>
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: "none" }} onChange={handleUpload} />
          <button onClick={() => fileRef.current?.click()} disabled={uploading} title={t("subirExcelTitle")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: uploading ? "default" : "pointer", background: "var(--bg-elevated)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", alignSelf: "flex-end" }}>{uploading ? t("uploading") : "⬆ Excel"}</button>
          <button onClick={bajarExcel} title={t("bajarExcelTitle")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)", alignSelf: "flex-end" }}>⬇ Excel</button>
          <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", alignSelf: "flex-end" }}>{tc("print")}</button>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("scenario")}</span>
            <select value={rsId} onChange={e => setRsId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("ytdThrough")}</span>
            <select value={month} onChange={e => setMonth(Number(e.target.value))} style={sel}>{MONTHS.map((m, i) => <option key={i+1} value={i+1} style={{ background: "var(--bg-input)" }}>{m}</option>)}</select>
          </div>
        </div>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {uploadMsg && <div style={{ color: uploadMsg.startsWith("Error") ? "var(--negative)" : "var(--positive)", fontSize: 12.5, marginBottom: 8 }}>{uploadMsg}</div>}
      {entryMsg && <div style={{ color: entryMsg.startsWith("Error") ? "var(--negative)" : "var(--positive)", fontSize: 12.5, marginBottom: 8 }}>{entryMsg}</div>}

      {/* Panel de carga/edición manual (copy-paste) */}
      {editing && (
        <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--positive)", borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
          <div style={{ padding: "10px 16px", background: "rgba(38,166,154,0.1)", borderBottom: "1px solid var(--border-medium)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700 }}>{t("cargarTitulo", { mes: MONTHS[month-1], year, scn: scenarios.find(s => s.id === rsId) ? scnLabel(scenarios.find(s => s.id === rsId)!) : "" })}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={saveEntry} disabled={entrySaving} style={{ padding: "6px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: entrySaving ? "default" : "pointer", background: "var(--positive)", color: "#fff", border: "none" }}>{entrySaving ? tc("saving") : t("guardarMes")}</button>
              <button onClick={() => setEditing(false)} style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5, cursor: "pointer", background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{tc("close")}</button>
            </div>
          </div>
          <div style={{ padding: "8px 14px", fontSize: 11.5, color: "var(--text-secondary)" }}>{t("pasteHint")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-medium)", background: "var(--bg-header)" }}>
                <th style={{ textAlign: "left", padding: "5px 10px", fontSize: 10.5, color: "var(--text-secondary)", fontWeight: 700 }}>Room Type</th>
                <th style={{ ...th, fontSize: 10.5 }}>Units</th>
                <th style={{ ...th, fontSize: 10.5 }}>{t("nochesDisp")}</th>
                <th style={{ ...th, fontSize: 10.5, color: "var(--brand)" }}>{t("nochesOcup")}</th>
                <th style={{ ...th, fontSize: 10.5, color: "var(--brand)" }}>Pax</th>
                <th style={{ ...th, fontSize: 10.5, color: "var(--brand)" }}>Revenue</th>
              </tr>
            </thead>
            <tbody>
              {entryRows.map((r, ri) => (
                <tr key={r.room_type_name} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "3px 10px", fontSize: 12.5, color: "var(--text-primary)" }}>{r.room_type_name}</td>
                  <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{r.units || "—"}</td>
                  <td className="mono" style={{ ...td, color: "var(--text-secondary)" }}>{r.nights_available || "—"}</td>
                  {ENTRY_COLS.map((col, ci) => (
                    <td key={col} style={{ padding: "2px 4px" }}>
                      <input className="mono" value={r[col]} onChange={e => setEntryCell(ri, col, e.target.value)} onPaste={e => handleEntryPaste(ri, ci, e)} onFocus={e => e.target.select()}
                        style={{ width: "100%", textAlign: "right", padding: "4px 6px", background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 3, color: "var(--text-primary)", fontSize: 12.5, outline: "none" }} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>{tc("loading")}</div>}

      {!loading && rows.length === 0 && (
        <div style={{ padding: 14, fontSize: 12.5, color: "var(--text-secondary)", background: "var(--bg-elevated)", borderRadius: 8 }}>
          {t.rich("sinDrivers", { b: (c) => <b>{c}</b> })}
        </div>
      )}

      {!loading && rows.length > 0 && <>
        {/* KPI cards */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          <KPI label="Units" value={int(tot.units)} />
          <KPI label={t("kpiTotalNoches")} value={int(tot.na)} />
          <KPI label={t("kpiNochesOcupadas")} value={int(tot.no)} />
          <KPI label="Occupancy" value={(occTotal*100).toFixed(1)+"%"} />
          <KPI label="ADR" value={money(adrTotal)} />
          <KPI label="Total Pax" value={int(tot.pax)} />
          <KPI label="Total Revenue" value={money(tot.rev)} />
        </div>
        {otherRevenue !== 0 && (
          <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: -10, marginBottom: 16 }}>
            {t.rich("incluyeOther", { monto: money(otherRevenue), b: (c) => <b>{c}</b> })}
          </div>
        )}

        {/* Charts row */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
          {/* Revenue by Room Category */}
          <div style={{ flex: "1 1 520px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, textAlign: "center" }}>Revenue by Room Category</div>
            <ResponsiveContainer width="100%" height={Math.max(180, rows.length * 38)}>
              <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 64, top: 4, bottom: 4 }}>
                <XAxis type="number" tickFormatter={v => `$${Math.round(v/1000)}K`} tick={{ fill: "var(--text-secondary)", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="room_type_name" width={170} tick={{ fill: "var(--text-secondary)", fontSize: 10.5 }} axisLine={false} tickLine={false} />
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} labelStyle={{ color: "var(--text-primary)" }} formatter={(v: any) => [money0(Number(v)), "Revenue"]} />
                <Bar dataKey="revenue" fill="#1F3A6E" radius={[0,4,4,0]}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  <LabelList dataKey="revenue" position="right" formatter={(v: any) => money0(Number(v))} style={{ fill: "var(--text-primary)", fontSize: 10.5, fontWeight: 600 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Revenue Mix donut */}
          <div style={{ flex: "1 1 360px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "14px 16px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10, textAlign: "center" }}>Revenue Mix</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <ResponsiveContainer width={200} height={200}>
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={52} outerRadius={88} paddingAngle={1} stroke="none">
                    {pieData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                  </Pie>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  <Tooltip contentStyle={{ background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 }} formatter={(v: any, _n: any, p: any) => [money0(Number(v)) + ` (${((p?.payload?.pct ?? 0)*100).toFixed(1)}%)`, ""]} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ flex: 1, minWidth: 150, display: "flex", flexDirection: "column", gap: 5 }}>
                {pieData.map((d, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: d.fill, flexShrink: 0 }} />
                    <span style={{ flex: 1, color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{d.name}</span>
                    <span className="mono" style={{ fontWeight: 700, color: "var(--text-primary)" }}>{(d.pct*100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Performance table + Executive Insight */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "stretch" }}>
          <div style={{ flex: "2 1 560px", minWidth: 0, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ padding: "10px 16px", background: "var(--bg-header)", borderBottom: "1px solid var(--border-medium)", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, textAlign: "center" }}>Room Category Performance</div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-medium)" }}>
                  <th style={{ textAlign: "left", padding: "6px 12px", fontSize: 10.5, color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase" }}>Room Category</th>
                  {["Units","Rooms Occupied","Occupancy","ADR","Total Revenue","Total Pax"].map(h => <th key={h} style={{ textAlign: "right", padding: "6px 12px", fontSize: 10.5, color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase" }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.room_type_id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    {/* Padding vertical mas alto: un nombre de categoria largo envuelve
                        a 2 lineas y con 5px quedaba pegado al borde de arriba y abajo
                        — apenas espacio para leerlo. */}
                    <td style={{ padding: "10px 12px", fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.35 }}>{rtLabel(r.room_type_code, r.room_type_name)}</td>
                    <td className="mono" style={{ textAlign: "right", padding: "10px 12px", fontSize: 12.5, verticalAlign: "middle" }}>{r.units}</td>
                    <td className="mono" style={{ textAlign: "right", padding: "10px 12px", fontSize: 12.5, verticalAlign: "middle" }}>{int(r.nights_occupied)}</td>
                    <td className="mono" style={{ textAlign: "right", padding: "10px 12px", fontSize: 12.5, verticalAlign: "middle" }}>{(r.occupancy_pct*100).toFixed(1)}%</td>
                    <td className="mono" style={{ textAlign: "right", padding: "10px 12px", fontSize: 12.5, verticalAlign: "middle" }}>{money(r.adr)}</td>
                    <td className="mono" style={{ textAlign: "right", padding: "10px 12px", fontSize: 12.5, verticalAlign: "middle" }}>{money(r.revenue)}</td>
                    <td className="mono" style={{ textAlign: "right", padding: "10px 12px", fontSize: 12.5, verticalAlign: "middle" }}>{int(r.pax)}</td>
                  </tr>
                ))}
                <tr style={{ borderTop: "2px solid var(--border-medium)", background: "rgba(255,255,255,0.03)" }}>
                  <td style={{ padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>TOTAL</td>
                  <td className="mono" style={{ textAlign: "right", padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>{tot.units}</td>
                  <td className="mono" style={{ textAlign: "right", padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>{int(tot.no)}</td>
                  <td className="mono" style={{ textAlign: "right", padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>{(occTotal*100).toFixed(1)}%</td>
                  <td className="mono" style={{ textAlign: "right", padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>{money(adrTotal)}</td>
                  <td className="mono" style={{ textAlign: "right", padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>{money(tot.rev)}</td>
                  <td className="mono" style={{ textAlign: "right", padding: "6px 12px", fontSize: 12.5, fontWeight: 700 }}>{int(tot.pax)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div style={{ flex: "1 1 300px", minWidth: 0, background: "rgba(200,162,74,0.08)", border: "1px solid #C8A24A", borderRadius: 8, padding: "16px 18px" }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: "#C8A24A", textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 10 }}>💡 Executive Insight</div>
            <div style={{ fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.65 }}>{insight}</div>
          </div>
        </div>
      </>}
    </div>
  );
}
