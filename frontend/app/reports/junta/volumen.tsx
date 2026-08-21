"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { rtLabel, type PLMonthly, type RevenueByRoomType, type RoomTypeRow } from "@/lib/api";
import type { Version } from "./versiones";
import { relativo } from "./bloques";

/**
 * Sub-vistas de Volumen: el año, el trimestre y el tipo de habitación.
 *
 * El anual dice cuánta gente vino; el trimestre dice CUÁNDO, que en un lodge con
 * octubre cerrado es media conversación; y el tipo de habitación dice QUÉ se
 * llenó, que es lo que decide dónde poner tarifa.
 */

const GOLD = "#c8a24a";
const MESES_Q = [
  { lab: "Q1", meses: [0, 1, 2], det: "rangeQ1" },
  { lab: "Q2", meses: [3, 4, 5], det: "rangeQ2" },
  { lab: "Q3", meses: [6, 7, 8], det: "rangeQ3" },
  { lab: "Q4", meses: [9, 10, 11], det: "rangeQ4" },
];

const conteo = (v: number) => Math.round(v).toLocaleString("en-US");
const pct1 = (v: number) => v.toFixed(1) + "%";
const dinero0 = (v: number) => "$" + Math.round(v).toLocaleString("en-US");

const th: React.CSSProperties = { padding: "7px 9px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.3, textAlign: "right", whiteSpace: "nowrap" };
const thL: React.CSSProperties = { ...th, textAlign: "left" };
const td: React.CSSProperties = { padding: "7px 9px", fontSize: 12.5, textAlign: "right", fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap" };
const tdL: React.CSSProperties = { ...td, textAlign: "left" };
const sub: React.CSSProperties = { ...td, color: "var(--text-secondary)" };

function chip(activo: boolean): React.CSSProperties {
  return {
    padding: "5px 11px", fontSize: 11.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
    background: activo ? "var(--brand)" : "var(--bg-input)",
    color: activo ? "#fff" : "var(--text-primary)",
    border: `1px solid ${activo ? "var(--brand)" : "var(--border-medium)"}`,
  };
}

function Delta({ a, b, fmt, puntos }: { a: number; b: number; fmt: (v: number) => string; puntos?: boolean }) {
  const d = a - b;
  const rel = puntos ? null : relativo(a, b);
  const color = Math.abs(d) < 0.005 ? "var(--text-disabled)" : d > 0 ? "var(--positive, #1A7F4B)" : "var(--negative)";
  return (
    <td className="mono" style={{ ...td, color }}>
      {puntos ? `${d >= 0 ? "+" : ""}${d.toFixed(1)} pp` : fmt(d)}
      {rel !== null && <span style={{ fontSize: 10.5, opacity: 0.75, marginLeft: 6 }}>{rel >= 0 ? "+" : ""}{rel.toFixed(1)}%</span>}
    </td>
  );
}

// ─── Volumen por trimestre, comparando versiones ─────────────────────────────
type MetricaQ = "ocupadas" | "ocupacion" | "huespedes";

/** Ocupación del trimestre = noches ocupadas ÷ noches disponibles del trimestre.
 *  NO el promedio de los porcentajes mensuales: con meses de peso distinto —y
 *  octubre cerrado— el promedio simple da un número que no existe. */
function valorQ(m: PLMonthly | undefined, meses: number[], k: MetricaQ): number {
  if (!m?.months?.length) return 0;
  const ms = meses.map(i => m.months[i]).filter(Boolean);
  const ocu = ms.reduce((s, x) => s + (x.kpis.rooms_occupied ?? 0), 0);
  if (k === "ocupadas") return ocu;
  if (k === "huespedes") return ms.reduce((s, x) => s + (x.kpis.guests ?? 0), 0);
  const disp = ms.reduce((s, x) => s + (x.kpis.rooms_available ?? 0), 0);
  return disp ? ocu / disp * 100 : 0;
}

export function VolumenPorTrimestre({ vs, mensuales }: {
  vs: Version[]; mensuales: Record<string, PLMonthly | null>;
}) {
  const t = useTranslations("junta");
  const tc = useTranslations("common");
  const [met, setMet] = useState<MetricaQ>("ocupadas");
  const esPct = met === "ocupacion";
  const fmt = esPct ? pct1 : conteo;
  const principal = vs[0];
  if (!principal || !mensuales[principal.id]) {
    return <div style={{ color: "var(--text-secondary)", fontSize: 12.5, padding: 14 }}>{t("loadingMonthly")}</div>;
  }

  // Los chips eligen la métrica: son control de pantalla, no filas del estado
  // financiero. ADR y RevPAR se quedan como están —son canónicos.
  const METRICAS_Q: { key: MetricaQ; label: string }[] = [
    { key: "ocupadas", label: t("roomsOccupied") },
    { key: "ocupacion", label: t("occupancy") },
    { key: "huespedes", label: tc("guests") },
  ];

  const filas = [...MESES_Q, { lab: tc("year"), meses: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], det: "rangeYear" }];

  return (
    <>
      <div className="no-print" style={{ display: "flex", gap: 5, marginBottom: 12, flexWrap: "wrap" }}>
        {METRICAS_Q.map(m => (
          <button key={m.key} onClick={() => setMet(m.key)} style={chip(met === m.key)}>{m.label}</button>
        ))}
      </div>
      <table className="fin-table" style={{ width: "100%" }}>
        <thead><tr>
          <th style={{ ...thL, minWidth: 150 }}>{t("quarter")}</th>
          <th style={{ ...th, color: "var(--brand)" }}>{principal.label}</th>
          {vs.slice(1).map(v => (
            <>
              <th key={v.id} style={th}>{v.label}</th>
              <th key={`${v.id}-d`} style={{ ...th, color: GOLD }}>Δ vs {vs[0]?.label}</th>
            </>
          ))}
        </tr></thead>
        <tbody>
          {filas.map((q, i) => {
            const esAnio = i === filas.length - 1;
            const a = valorQ(mensuales[principal.id] ?? undefined, q.meses, met);
            return (
              <tr key={q.lab} style={{ borderTop: esAnio ? "2px solid var(--border-medium)" : "1px solid var(--border-subtle)" }}>
                <td style={{ ...tdL, fontWeight: esAnio ? 800 : 600 }}>
                  {q.lab} <span style={{ fontSize: 10.5, color: "var(--text-disabled)", fontWeight: 500 }}>{t(q.det)}</span>
                </td>
                <td className="mono" style={{ ...td, fontWeight: esAnio ? 800 : 700 }}>{fmt(a)}</td>
                {vs.slice(1).map(v => {
                  const m = mensuales[v.id];
                  if (!m) return <><td key={v.id} style={sub}>—</td><td key={`${v.id}-d`} style={td}>—</td></>;
                  const b = valorQ(m, q.meses, met);
                  return (
                    <>
                      <td key={v.id} className="mono" style={sub}>{fmt(b)}</td>
                      <Delta key={`${v.id}-d`} a={a} b={b} fmt={fmt} puntos={esPct} />
                    </>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {esPct && (
        <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 8, lineHeight: 1.5 }}>
          {t("quarterOccNote")}
        </div>
      )}
    </>
  );
}

// ─── Volumen por tipo de habitación y trimestre ──────────────────────────────
type MetricaRT = "ocupadas" | "ocupacion" | "pax" | "revenue" | "adr";

export function VolumenPorTipo({ datos, vs }: {
  datos: Record<string, RevenueByRoomType | null>; vs: Version[];
}) {
  const t = useTranslations("junta");
  const tc = useTranslations("common");
  const [met, setMet] = useState<MetricaRT>("ocupadas");
  // Un PERÍODO por vez para poder comparar versiones: los cuatro trimestres por
  // tres versiones con sus deltas serían quince columnas y no se lee proyectado.
  const [per, setPer] = useState(4);   // 4 = año
  const periodos = [...MESES_Q, { lab: tc("year"), meses: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], det: "rangeYear" }];
  const meses = periodos[per].meses;

  const principal = vs[0];
  const base = principal && datos[principal.id];
  if (!base?.room_types?.length) {
    return <div style={{ color: "var(--text-secondary)", fontSize: 12.5, padding: 14 }}>{t("noRoomDetail")}</div>;
  }

  /** Agrega el período por tipo. Ocupación y ADR NO se suman: se recomponen de
   *  sus bases (noches y revenue), si no darían el promedio de promedios. */
  const valor = (d: RevenueByRoomType | null | undefined, rtId: string): number => {
    if (!d) return 0;
    const filas = meses
      .map(i => d.months.find(m => m.month === i + 1)?.rows.find(r => r.room_type_id === rtId))
      .filter(Boolean) as RoomTypeRow[];
    const suma = (f: (r: RoomTypeRow) => number) => filas.reduce((s, r) => s + (f(r) || 0), 0);
    const ocu = suma(r => r.nights_occupied);
    if (met === "ocupadas") return ocu;
    if (met === "pax") return suma(r => r.pax);
    if (met === "revenue") return suma(r => r.revenue);
    if (met === "adr") return ocu ? suma(r => r.revenue) / ocu : 0;
    const disp = suma(r => r.nights_available);
    return disp ? ocu / disp * 100 : 0;
  };

  const total = (d: RevenueByRoomType | null | undefined): number => {
    if (!d) return 0;
    if (met === "ocupacion" || met === "adr") {
      const filas = meses.flatMap(i => d.months.find(m => m.month === i + 1)?.rows ?? []);
      const ocu = filas.reduce((s, r) => s + (r.nights_occupied || 0), 0);
      if (met === "adr") return ocu ? filas.reduce((s, r) => s + (r.revenue || 0), 0) / ocu : 0;
      const disp = filas.reduce((s, r) => s + (r.nights_available || 0), 0);
      return disp ? ocu / disp * 100 : 0;
    }
    return (d.room_types ?? []).reduce((s, rt) => s + valor(d, rt.id), 0);
  };

  const METRICAS_RT: { key: MetricaRT; label: string }[] = [
    { key: "ocupadas", label: t("nightsOccupied") },
    { key: "ocupacion", label: t("occupancy") },
    { key: "pax", label: tc("guests") },
    { key: "revenue", label: t("revenue") },
    { key: "adr", label: "ADR" },   // canónico: no se traduce
  ];

  const esPct = met === "ocupacion";
  const fmt = esPct ? pct1
    : met === "revenue" || met === "adr" ? dinero0
      : conteo;

  /** El mismo tipo puede tener otro id en otro escenario; se cruza por CÓDIGO,
   *  que es fijo entre escenarios y propiedades. */
  const idEquivalente = (d: RevenueByRoomType | null | undefined, code?: string, name?: string) =>
    d?.room_types.find(r => (code && r.code === code) || r.name === name)?.id;

  return (
    <>
      <div className="no-print" style={{ display: "flex", gap: 5, marginBottom: 8, flexWrap: "wrap" }}>
        {METRICAS_RT.map(m => (
          <button key={m.key} onClick={() => setMet(m.key)} style={chip(met === m.key)}>{m.label}</button>
        ))}
      </div>
      <div className="no-print" style={{ display: "flex", gap: 5, marginBottom: 12, flexWrap: "wrap" }}>
        {periodos.map((q, i) => (
          <button key={q.lab} onClick={() => setPer(i)} style={{ ...chip(per === i), fontSize: 11, padding: "4px 10px" }}>
            {q.lab}
          </button>
        ))}
      </div>

      <table className="fin-table" style={{ width: "100%" }}>
        <thead><tr>
          <th style={{ ...thL, minWidth: 240 }}>{t("roomTypeCol", { periodo: periodos[per].lab })}</th>
          <th style={{ ...th, color: "var(--brand)" }}>{principal.label}</th>
          {vs.slice(1).map(v => (
            <>
              <th key={v.id} style={th}>{v.label}</th>
              <th key={`${v.id}-d`} style={{ ...th, color: GOLD }}>Δ vs {vs[0]?.label}</th>
            </>
          ))}
        </tr></thead>
        <tbody>
          {base.room_types.map(rt => {
            const a = valor(base, rt.id);
            return (
              <tr key={rt.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={tdL}>{rtLabel(rt.code, rt.name)}</td>
                <td className="mono" style={{ ...td, fontWeight: 700 }}>{fmt(a)}</td>
                {vs.slice(1).map(v => {
                  const d = datos[v.id];
                  const eq = idEquivalente(d, rt.code, rt.name);
                  if (!d || !eq) return <><td key={v.id} style={sub}>—</td><td key={`${v.id}-d`} style={td}>—</td></>;
                  const b = valor(d, eq);
                  return (
                    <>
                      <td key={v.id} className="mono" style={sub}>{fmt(b)}</td>
                      <Delta key={`${v.id}-d`} a={a} b={b} fmt={fmt} puntos={esPct} />
                    </>
                  );
                })}
              </tr>
            );
          })}
          <tr style={{ borderTop: "2px solid var(--border-medium)" }}>
            <td style={{ ...tdL, fontWeight: 800 }}>{tc("total")}</td>
            <td className="mono" style={{ ...td, fontWeight: 800 }}>{fmt(total(base))}</td>
            {vs.slice(1).map(v => {
              const d = datos[v.id];
              if (!d) return <><td key={v.id} style={sub}>—</td><td key={`${v.id}-d`} style={td}>—</td></>;
              return (
                <>
                  <td key={v.id} className="mono" style={{ ...sub, fontWeight: 800 }}>{fmt(total(d))}</td>
                  <Delta key={`${v.id}-d`} a={total(base)} b={total(d)} fmt={fmt} puntos={esPct} />
                </>
              );
            })}
          </tr>
        </tbody>
      </table>
    </>
  );
}
