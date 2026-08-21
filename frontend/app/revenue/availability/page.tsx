"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { getRoomTypes } from "@/lib/api";
import { fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const HOTEL = HOTEL_ID;

const excelBtn: React.CSSProperties = {
  padding: "7px 14px", fontSize: 12.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};
const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
// Quarter tint per month (echoes the source spreadsheet's Q coloring)
const Q_TINT = ["#FBF5C8","#FBF5C8","#FBF5C8","#F2D7D2","#F2D7D2","#F2D7D2",
                "#CFE8F0","#CFE8F0","#CFE8F0","transparent","transparent","transparent"];

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate(); // month1: 1-12
}

export default function AvailabilityPage() {
  const tc = useTranslations("common");
  const t = useTranslations("availability");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [year, setYear] = useState(2026);
  const [units, setUnits] = useState(0);
  const [closed, setClosed] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await getRoomTypes(HOTEL);
        setUnits(res.total_units);
        setClosed(new Set(res.closed_months));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Días = 0 en meses cerrados (mismo dato que alimenta el resto de pantallas).
  const days = useMemo(
    () => MONTHS.map((_, i) => (closed.has(i + 1) ? 0 : daysInMonth(year, i + 1))),
    [year, closed],
  );
  const nights = useMemo(() => days.map(d => d * units), [days, units]);
  const totalNights = nights.reduce((s, v) => s + v, 0);

  const numTd: React.CSSProperties = { textAlign: "right", padding: "6px 10px", fontFamily: "var(--font-mono)" };

  // ── Excel: el mismo cuadro, con las noches como número ────────────────────
  async function bajarExcel() {
    const cerrados = MONTHS.filter((_m, i) => closed.has(i + 1));
    try {
      await bajarCuadros("Disponibilidad", [{
        titulo: `${t("title")} ${year}`,
        subtitulo: t("xlsSubtitle") +
          (cerrados.length ? t("xlsClosedMonths", { meses: cerrados.join(", ") }) : ""),
        hoja: t("sheet"),
        columnas: [
          { label: tc("concept"), ancho: 30, formato: "texto" },
          ...MONTHS.map(m => ({ label: `${m} ${String(year).slice(2)}`, ancho: 10, formato: "num" as const })),
          { label: tc("year"), ancho: 14, formato: "num" as const },
        ],
        filas: [
          // El anual de "units" no existe (no se suman unidades) → celda vacía.
          { label: "Units Available", valores: [...MONTHS.map(() => units), null] },
          { label: "Day per month", valores: [...days, days.reduce((s, v) => s + v, 0)] },
          { label: "Total Nights Available", es_total: true, valores: [...nights, totalNights] },
        ],
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          {t("title")}
        </h1>
        <select value={year} onChange={e => setYear(parseInt(e.target.value))} className="fin-input" style={{ width: 110 }}>
          {[2024, 2025, 2026, 2027, 2028].map(y => <option key={y} value={y}>{y}</option>)}
        </select>
        <button onClick={bajarExcel} title={t("excelHint")} style={excelBtn}>⬇ Excel</button>
      </div>
      <div style={{ marginTop: 16 }} />

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1000 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 170 }}></th>
                {MONTHS.map((m, i) => (
                  <th key={m} style={{
                    textAlign: "right", minWidth: 64,
                    // trimestre como línea inferior — el texto usa el color del tema (siempre visible)
                    borderBottom: `3px solid ${Q_TINT[i] === "transparent" ? "var(--border-medium)" : Q_TINT[i]}`,
                  }}>
                    {m} {String(year).slice(2)}
                  </th>
                ))}
                <th style={{ textAlign: "right", minWidth: 90, borderLeft: "1px solid var(--border)" }}>{tc("year")}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ textAlign: "left", color: "var(--text-secondary)" }}>Units Available</td>
                {days.map((_, i) => <td key={i} style={numTd}>{units}</td>)}
                <td style={{ ...numTd, borderLeft: "1px solid var(--border)", color: "var(--text-disabled)" }}>—</td>
              </tr>
              <tr>
                <td style={{ textAlign: "left", color: "var(--text-secondary)" }}>Day per month</td>
                {days.map((d, i) => <td key={i} style={numTd}>{fmtInt(d)}</td>)}
                <td style={{ ...numTd, borderLeft: "1px solid var(--border)" }}>{fmtInt(days.reduce((s, v) => s + v, 0))}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>Total Nights Available</td>
                {nights.map((n, i) => <td key={i} style={numTd}>{fmtInt(n)}</td>)}
                <td style={{ ...numTd, borderLeft: "1px solid var(--border)" }}>{fmtInt(totalNights)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
