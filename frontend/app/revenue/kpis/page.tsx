"use client";
import { useEffect, useState, useRef } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import {
  getHistoricalKpis, getMonthlyRevenue, getBudgetScenario,
  statsExcelUrl, importStatsExcel,
  type HistoricalKpi, type MonthlyRevenue,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

function fmt(v: string | number, decimals = 0) {
  const n = Number(v);
  if (isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
function fmtPct(v: string | number) {
  const n = Number(v);
  if (isNaN(n) || n === 0) return "—";
  return (n * 100).toFixed(1) + "%";
}
function fmtUsd(v: string | number) {
  const n = Number(v);
  if (isNaN(n)) return "—";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? "(" + s + ")" : s;
}

function VarBadge({ a, b, isRevenue = true }: { a: number; b: number; isRevenue?: boolean }) {
  if (!a || !b) return <span style={{ color: "var(--text-disabled)" }}>—</span>;
  const diff = b - a;
  const pct = (diff / Math.abs(a)) * 100;
  const positive = isRevenue ? diff > 0 : diff < 0;
  const color = positive ? "var(--positive)" : diff === 0 ? "var(--neutral)" : "var(--negative)";
  return (
    <span className="mono" style={{ color, fontSize: 11 }}>
      {diff > 0 ? "↑" : "↓"} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

interface KpiRow {
  label: string;
  key2024: string;
  key2025: string;
  keyBudget: string;
  format: (v: string | number) => string;
  isRevenue?: boolean;
}

const ROWS: KpiRow[] = [
  { label: "% Occupancy",    key2024: "occupancy_pct",  key2025: "occupancy_pct",  keyBudget: "occupancy_pct",  format: fmtPct },
  { label: "ADR",            key2024: "adr_usd",        key2025: "adr_usd",        keyBudget: "adr",            format: fmtUsd },
  { label: "RevPAR",         key2024: "revpar_usd",     key2025: "revpar_usd",     keyBudget: "revpar",         format: fmtUsd },
  { label: "Rooms Occupied", key2024: "rooms_occupied", key2025: "rooms_occupied", keyBudget: "rooms_occupied", format: (v) => fmt(v, 0) },
  { label: "Room Revenue",   key2024: "revenue_usd",    key2025: "revenue_usd",    keyBudget: "rooms",          format: fmtUsd, isRevenue: true },
  { label: "Total Guests",   key2024: "guests",         key2025: "guests",         keyBudget: "guests",         format: (v) => fmt(v, 0) },
];

export default function KpisPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [month, setMonth]       = useState(1);
  const [hist, setHist]         = useState<HistoricalKpi[]>([]);
  const [budget, setBudget]     = useState<MonthlyRevenue[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [scenarioId, setScId]   = useState<string | null>(null);
  const [xlsxMsg, setXlsxMsg]  = useState<string | null>(null);
  const [xlsxUp, setXlsxUp]    = useState(false);
  const fileRef                  = useRef<HTMLInputElement>(null);

  async function handleXlsxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !scenarioId) return;
    setXlsxUp(true); setXlsxMsg(null);
    try {
      const r = await importStatsExcel(scenarioId, file);
      setXlsxMsg(`✓ ${r.imported} meses importados. Recalculá el revenue para actualizar el P&L.`);
    } catch (ex: unknown) {
      setXlsxMsg(`Error: ${ex instanceof Error ? ex.message : String(ex)}`);
    } finally {
      setXlsxUp(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const [h, sc] = await Promise.all([
          getHistoricalKpis(HOTEL_ID),
          getBudgetScenario(HOTEL_ID, 2026),
        ]);
        setHist(h);
        if (sc) {
          setScId(sc.id);
          const rev = await getMonthlyRevenue(sc.id);
          setBudget(rev);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Error cargando datos");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const h2024 = hist.find(h => h.year === 2024 && h.month === month);
  const h2025 = hist.find(h => h.year === 2025 && h.month === month);
  const bgt = budget.find(b => b.month === month);

  // Chart data — all 12 months
  const chartData = MONTHS.map((name, i) => {
    const m = i + 1;
    const y24 = hist.find(h => h.year === 2024 && h.month === m);
    const y25 = hist.find(h => h.year === 2025 && h.month === m);
    const b = budget.find(b => b.month === m);
    return {
      name,
      "2024 Occ": y24 ? Number((Number(y24.occupancy_pct) * 100).toFixed(1)) : 0,
      "2025 Occ": y25 ? Number((Number(y25.occupancy_pct) * 100).toFixed(1)) : 0,
      "2026 Bdg": b ? Number((Number(b.occupancy_pct) * 100).toFixed(1)) : 0,
      "Rev 2024": y24 ? Math.round(Number(y24.revenue_usd)) : 0,
      "Rev 2025": y25 ? Math.round(Number(y25.revenue_usd)) : 0,
      "Rev 2026": b ? Math.round(Number(b.rooms)) : 0,
    };
  });

  return (
    <div className="pag pag-media">
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, color: "var(--text-primary)", fontWeight: 600 }}>
            Key Indicators
          </h2>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 12 }}>
            Comparativo 2024 Actual · 2025 Actual · 2026 Budget
          </p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
          {MONTHS.map((m, i) => (
            <button key={m} onClick={() => setMonth(i + 1)} style={{
              padding: "4px 10px", fontSize: 12,
              background: month === i + 1 ? "var(--brand)" : "var(--bg-surface)",
              color: month === i + 1 ? "#fff" : "var(--text-secondary)",
              border: "1px solid var(--border-medium)", borderRadius: 3, cursor: "pointer",
            }}>{m}</button>
          ))}
          <div style={{ width: 1, height: 20, background: "var(--border-medium)", margin: "0 4px" }} />
          {scenarioId && (
            <a href={statsExcelUrl(scenarioId)} download style={{
              padding: "4px 12px", fontSize: 12, borderRadius: 3, textDecoration: "none",
              background: "var(--bg-elevated)", color: "var(--text-secondary)",
              border: "1px solid var(--border-medium)", lineHeight: "20px", display: "inline-block",
            }}>⬇ Excel KPIs</a>
          )}
          <input ref={fileRef} type="file" accept=".xlsx" style={{ display: "none" }} onChange={handleXlsxUpload} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={xlsxUp || !scenarioId}
            style={{
              padding: "4px 12px", fontSize: 12, borderRadius: 3,
              background: xlsxUp ? "var(--bg-elevated)" : "#1E3A5F",
              color: xlsxUp ? "var(--text-disabled)" : "#90CAF9",
              border: "1px solid #2962FF", cursor: xlsxUp ? "default" : "pointer",
            }}
          >{xlsxUp ? "Subiendo..." : "↑ KPIs"}</button>
        </div>
      </div>
      {xlsxMsg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: xlsxMsg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: xlsxMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${xlsxMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>{xlsxMsg}</div>
      )}

      {loading && (
        <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>
      )}
      {error && (
        <div style={{ color: "var(--negative)", padding: "12px 16px", background: "var(--bg-surface)", borderRadius: 4, marginBottom: 16 }}>
          ⚠ {error}
          <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-secondary)" }}>
            Asegurate que el backend esté corriendo en http://localhost:8000 y que hayas importado los datos con POST /hotels/CWL/historical/import/ y POST /scenarios/&#123;id&#125;/revenue/import/
          </p>
        </div>
      )}

      {/* KPI comparison table */}
      {!loading && (
        <div className="fin-sticky" style={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 6, marginBottom: 24 }}>
          <table className="fin-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", width: 160 }}>{tc("indicator")}</th>
                <th>2024 Actual</th>
                <th>2025 Actual</th>
                <th>vs 2024</th>
                <th style={{ color: "var(--brand)" }}>2026 Budget</th>
                <th>vs 2025</th>
                <th style={{ color: "var(--text-disabled)" }}>2026 Forecast</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map(row => {
                const v24 = h2024 ? (h2024 as unknown as Record<string, string>)[row.key2024] : undefined;
                const v25 = h2025 ? (h2025 as unknown as Record<string, string>)[row.key2025] : undefined;
                const vb  = bgt   ? (bgt   as unknown as Record<string, string>)[row.keyBudget] : undefined;
                return (
                  <tr key={row.label}>
                    <td style={{ color: "var(--text-primary)", fontWeight: 500 }}>{row.label}</td>
                    <td className="mono">{v24 ? row.format(v24) : "—"}</td>
                    <td className="mono">{v25 ? row.format(v25) : "—"}</td>
                    <td><VarBadge a={Number(v24)} b={Number(v25)} isRevenue={row.isRevenue} /></td>
                    <td className="mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                      {vb ? row.format(vb) : "—"}
                    </td>
                    <td><VarBadge a={Number(v25)} b={Number(vb)} isRevenue={row.isRevenue} /></td>
                    <td style={{ color: "var(--text-disabled)" }}>—</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Charts */}
      {!loading && chartData.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Occupancy line chart */}
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "16px 8px 8px" }}>
            <p style={{ margin: "0 0 12px 12px", fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>
              % Ocupación mensual
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData} margin={{ left: 0, right: 12 }}>
                <XAxis dataKey="name" tick={{ fill: "#787B86", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#787B86", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => v + "%"} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 4, fontSize: 11 }}
                  formatter={(v) => [Number(v).toFixed(1) + "%"]}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: "#787B86" }} />
                <Line type="monotone" dataKey="2024 Occ" stroke="#787B86" dot={false} strokeWidth={1.5} />
                <Line type="monotone" dataKey="2025 Occ" stroke="#F59E0B" dot={false} strokeWidth={1.5} />
                <Line type="monotone" dataKey="2026 Bdg" stroke="#2962FF" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Room Revenue bar chart */}
          <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "16px 8px 8px" }}>
            <p style={{ margin: "0 0 12px 12px", fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>
              Room Revenue mensual (USD)
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} margin={{ left: 0, right: 12 }} barSize={6}>
                <XAxis dataKey="name" tick={{ fill: "#787B86", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#787B86", fontSize: 10 }} axisLine={false} tickLine={false}
                  tickFormatter={v => "$" + (v / 1000).toFixed(0) + "k"} />
                <Tooltip
                  contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 4, fontSize: 11 }}
                  formatter={(v) => ["$" + Number(v).toLocaleString("en-US")]}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: "#787B86" }} />
                <Bar dataKey="Rev 2024" fill="#787B86" />
                <Bar dataKey="Rev 2025" fill="#F59E0B" />
                <Bar dataKey="Rev 2026" fill="#2962FF" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
