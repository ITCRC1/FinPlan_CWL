"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { getRoomTypes, setClosedMonths, rtLabel, type RoomType } from "@/lib/api";
import { fmtInt } from "@/lib/fmt";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const HOTEL = HOTEL_ID;
const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const excelBtn: React.CSSProperties = {
  padding: "7px 14px", fontSize: 12.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
  background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)",
};

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

export default function RoomNightsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("roomNights");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const [year, setYear] = useState(2026);
  const [rooms, setRooms] = useState<RoomType[]>([]);
  const [closed, setClosed] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await getRoomTypes(HOTEL);
        setRooms(res.room_types);
        setClosed(new Set(res.closed_months));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const days = useMemo(
    () => MONTHS.map((_, i) => (closed.has(i + 1) ? 0 : daysInMonth(year, i + 1))),
    [year, closed],
  );

  // Toggle open/closed and persist to the hotel (formula-driven, shared by all tabs).
  async function toggleMonth(m1: number) {
    const next = new Set(closed);
    if (next.has(m1)) next.delete(m1); else next.add(m1);
    setClosed(next);
    try {
      await setClosedMonths(HOTEL, [...next].sort((a, b) => a - b));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSavingClosed"));
    }
  }

  const monthTotals = days.map(d =>
    rooms.reduce((s, r) => s + r.units * d, 0));
  const grandTotal = monthTotals.reduce((s, v) => s + v, 0);

  const numTd: React.CSSProperties = { textAlign: "right", padding: "5px 9px", fontFamily: "var(--font-mono)" };
  const fmt = fmtInt;

  // ── Excel: la misma grilla, con las noches como número ────────────────────
  async function bajarExcel() {
    const cerrados = MONTHS.filter((_m, i) => closed.has(i + 1));
    const filas: FilaCuadro[] = rooms.map(r => {
      const cells = days.map(d => r.units * d);
      return {
        label: rtLabel(r.code, r.name), nivel: 1,
        valores: [...cells, cells.reduce((s, v) => s + v, 0)],
      };
    });
    filas.push({ label: tc("total"), es_total: true, valores: [...monthTotals, grandTotal] });
    try {
      await bajarCuadros("Room_Nights_Available", [{
        titulo: `Total Room Nights Available per Category — ${year}`,
        subtitulo: t("xlsSubtitle") +
          (cerrados.length ? t("xlsClosedMonths", { meses: cerrados.join(", ") }) : ""),
        hoja: "Room Nights",
        columnas: [
          { label: tc("category"), ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: `${m} ${String(year).slice(2)}`, ancho: 10, formato: "num" as const })),
          { label: tc("year"), ancho: 14, formato: "num" as const },
        ],
        filas,
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
          Total Room Nights Available per Category
        </h1>
        <select value={year} onChange={e => setYear(parseInt(e.target.value))} className="fin-input" style={{ width: 110 }}>
          {[2024, 2025, 2026, 2027, 2028].map(y => <option key={y} value={y}>{y}</option>)}
        </select>
        <button onClick={bajarExcel} title={t("excelHint")} style={excelBtn}>⬇ Excel</button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t("intro")}
      </p>

      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1050 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 230 }}>{tc("category")}</th>
                {MONTHS.map((m, i) => {
                  const isClosed = closed.has(i + 1);
                  return (
                    <th
                      key={m}
                      onClick={() => toggleMonth(i + 1)}
                      title={isClosed ? t("closedClickOpen") : t("openClickClose")}
                      style={{
                        textAlign: "right", minWidth: 58, cursor: "pointer",
                        background: isClosed ? "#BFD4E8" : "transparent",
                        color: isClosed ? "#1a3a5c" : "inherit",
                      }}
                    >
                      {m} {String(year).slice(2)}
                    </th>
                  );
                })}
                <th style={{ textAlign: "right", minWidth: 80, borderLeft: "1px solid var(--border)" }}>{tc("year")}</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map(r => {
                const cells = days.map(d => r.units * d);
                const annual = cells.reduce((s, v) => s + v, 0);
                return (
                  <tr key={r.id}>
                    <td style={{ textAlign: "left" }}>{rtLabel(r.code, r.name)}</td>
                    {cells.map((v, i) => (
                      <td key={i} style={{ ...numTd, background: closed.has(i + 1) ? "#EAF1F8" : "transparent" }}>
                        {v ? fmt(v) : <span style={{ color: "var(--text-disabled)" }}>—</span>}
                      </td>
                    ))}
                    <td style={{ ...numTd, fontWeight: 600, borderLeft: "1px solid var(--border)" }}>{fmt(annual)}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>{tc("total")}</td>
                {monthTotals.map((t, i) => (
                  <td key={i} style={{ ...numTd, background: closed.has(i + 1) ? "#EAF1F8" : "transparent" }}>{fmt(t)}</td>
                ))}
                <td style={{ ...numTd, borderLeft: "1px solid var(--border)" }}>{fmt(grandTotal)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
