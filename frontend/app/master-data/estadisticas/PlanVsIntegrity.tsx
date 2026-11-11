"use client";
/**
 * Master Data → Estadísticas → «Stats» → Plan vs. Integrity.
 *
 * Owner, 2026-11-10: «quiero mapear budget 2027 y forecast 2026 working separado
 * por rooms y Villas» · «available rooms per room type» · «occupied room per
 * room type» · «las estadísticas de spa, laundry» · «budget y forecast y
 * actual… revisa también 2024-2025-2026» · «regular hours».
 *
 * **Solo lee.** El plan no se recalcula acá: las noches por tipo son las de
 * «Ingresos por tipo» (o, en un Forecast rodante, las del ACTUAL enlazado para
 * los meses cerrados), el Spa es su ingreso ÷ el precio promedio y los kilos son
 * los de la config del reparto. Lo de Integrity es la balanza guardada, sumada
 * al mes con el nivel 7 (tipo de habitación) del catálogo homologado.
 */
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { getPlanVsIntegrity, getScenarios, type PlanVsIntegrity as Vista, type Scenario } from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";

const BTN: React.CSSProperties = {
  padding: "7px 14px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 13, fontWeight: 600,
};
const TD: React.CSSProperties = { padding: "4px 8px", fontSize: 12, whiteSpace: "nowrap", textAlign: "left" };
const NUM: React.CSSProperties = { ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" };

type Meses = (number | null)[];
type Tipo = "num" | "pct" | "fte";

function fmt(v: number | null | undefined, tipo: Tipo = "num"): string {
  if (v === null || v === undefined) return "—";
  if (tipo === "pct") return `${(v * 100).toFixed(1)}%`;
  if (tipo === "fte") return v.toFixed(2);
  return v.toLocaleString("en-US", { maximumFractionDigits: 1 });
}
function sumar(m: Meses): number | null {
  return m.some(v => v !== null) ? m.reduce<number>((s, v) => s + (v ?? 0), 0) : null;
}
function promedio(m: Meses): number | null {
  const v = m.filter((x): x is number => x !== null);
  return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
}
/** Ocupación del año: suma de ocupadas ÷ suma de disponibles (no el promedio de %). */
function ocupAnual(ocu: Meses, disp: Meses): number | null {
  const o = sumar(ocu), d = sumar(disp);
  return o !== null && d ? o / d : null;
}

interface Fila { label: string; meses: Meses; anual: number | null; tipo: Tipo; nivel: 0 | 1 | 2;
  real?: boolean; titulo?: string; negrita?: boolean }

export default function PlanVsIntegrity({ anio }: { anio: number }) {
  const t = useTranslations("statsInt");
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  // El eje es el AÑO de la pestaña: la lista ya viene filtrada a ese año, y el
  // preferido es el Working del Budget, después el del Forecast, el Forecast
  // vigente y, si no hay ninguno de esos (2024, 2025), el Actual.
  const preferido = useCallback((del: Scenario[]) =>
    del.find(s => s.type === "BUDGET" && /working/i.test(s.version))
      ?? del.find(s => s.type === "FORECAST" && /working/i.test(s.version))
      ?? del.find(s => s.is_current_forecast) ?? del.find(s => s.type === "ACTUAL") ?? del[0], []);
  const [sid, setSid] = useEscenarioDe("master-data/stats:plan", escenarios, "budget", preferido);
  const [vista, setVista] = useState<Vista | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const MESES = useMemo(() => t("meses").split(","), [t]);

  // Los BUDGET y FORECAST del año; por defecto el «Working» (o el Forecast Current).
  useEffect(() => {
    let vivo = true;
    getScenarios(HOTEL_ID).then(todos => {
      if (!vivo) return;
      const orden = (t: string) => ["BUDGET", "FORECAST", "ACTUAL"].indexOf(t);
      const del = todos.filter(s => s.year === anio && orden(s.type) >= 0)
        .sort((a, b) => orden(a.type) - orden(b.type) || a.version.localeCompare(b.version));
      setEscenarios(del);
    }).catch(e => { if (vivo) setError(e instanceof Error ? e.message : String(e)); });
    return () => { vivo = false; };
  }, [anio]);

  useEffect(() => {
    // Lo recordado puede ser de otro año: hasta que el hook caiga al preferido
    // del año nuevo, no se pide nada.
    if (!sid || !escenarios.some(s => s.id === sid)) { setVista(null); return; }
    let vivo = true;
    setCargando(true); setError(null);
    getPlanVsIntegrity(anio, sid)
      .then(v => { if (vivo) setVista(v); })
      .catch(e => { if (vivo) { setVista(null); setError(e instanceof Error ? e.message : String(e)); } })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [anio, sid, escenarios]);

  /** Las filas de la tabla, en orden: se usan igual en pantalla y en el Excel. */
  const secciones = useMemo(() => {
    if (!vista) return [] as { titulo: string; filas: Fila[] }[];
    const out: { titulo: string; filas: Fila[] }[] = [];
    const real = t("planReal");
    for (const d of vista.habitaciones) {
      const filas: Fila[] = [];
      for (const ti of d.tipos) {
        filas.push({ label: `${ti.codigo} · ${ti.nombre}`, meses: new Array(12).fill(null), anual: null,
          tipo: "num", nivel: 1, negrita: true,
          titulo: t("planUnidades", { n: ti.unidades, cuenta: ti.cuenta }) });
        filas.push({ label: t("planDisponibles"), meses: ti.disponibles, anual: sumar(ti.disponibles), tipo: "num", nivel: 2 });
        filas.push({ label: t("planOcupadas"), meses: ti.ocupadas, anual: sumar(ti.ocupadas), tipo: "num", nivel: 2 });
        filas.push({ label: t("planOcupacion"), meses: ti.ocupacion, anual: ocupAnual(ti.ocupadas, ti.disponibles), tipo: "pct", nivel: 2 });
        filas.push({ label: real, meses: ti.real_ocupadas, anual: sumar(ti.real_ocupadas), tipo: "num", nivel: 2, real: true });
      }
      const tot = d.total;
      filas.push({ label: t("planTotalDepto", { depto: d.rotulo }), meses: new Array(12).fill(null), anual: null,
        tipo: "num", nivel: 1, negrita: true });
      filas.push({ label: t("planDisponibles"), meses: tot.disponibles, anual: sumar(tot.disponibles), tipo: "num", nivel: 2, negrita: true });
      filas.push({ label: t("planOcupadas"), meses: tot.ocupadas, anual: sumar(tot.ocupadas), tipo: "num", nivel: 2, negrita: true });
      filas.push({ label: t("planOcupacion"), meses: tot.ocupacion, anual: ocupAnual(tot.ocupadas, tot.disponibles), tipo: "pct", nivel: 2, negrita: true });
      filas.push({ label: real, meses: tot.real_ocupadas, anual: sumar(tot.real_ocupadas), tipo: "num", nivel: 2, negrita: true, real: true });
      out.push({ titulo: `${d.depto} · ${d.rotulo}`, filas });
    }
    if (vista.sin_tipo) {
      const st = vista.sin_tipo;
      const occ = st.ocupadas.map((o, i) => (o !== null && st.disponibles[i]) ? o / (st.disponibles[i] as number) : null);
      out.push({ titulo: vista.fuente === "forecast_rodante" ? t("planSinTipo") : t("planSinTipoTotal"), filas: [
        { label: t("planDisponibles"), meses: st.disponibles, anual: sumar(st.disponibles), tipo: "num", nivel: 2 },
        { label: t("planOcupadas"), meses: st.ocupadas, anual: sumar(st.ocupadas), tipo: "num", nivel: 2 },
        { label: t("planOcupacion"), meses: occ, anual: ocupAnual(st.ocupadas, st.disponibles), tipo: "pct", nivel: 2 },
      ]});
    }
    out.push({ titulo: t("planSpa"), filas: [
      { label: t("planTratamientos"), meses: vista.spa.plan, anual: sumar(vista.spa.plan), tipo: "num", nivel: 2 },
      { label: t("planRealCuentas", { cuentas: vista.spa.cuentas }), meses: vista.spa.real, anual: sumar(vista.spa.real),
        tipo: "num", nivel: 2, real: true },
    ]});
    const lav: Fila[] = vista.lavanderia.plan.map(f => ({
      label: `${f.rotulo} (${f.cuenta})`, meses: f.plan, anual: sumar(f.plan), tipo: "num" as Tipo, nivel: 2 as const }));
    for (const [c, m] of Object.entries(vista.lavanderia.real)) {
      lav.push({ label: t("planRealCuentas", { cuentas: c }), meses: m, anual: sumar(m), tipo: "num", nivel: 2, real: true });
    }
    out.push({ titulo: t("planLavanderia"), filas: lav });

    // Horas regulares por depto de planilla: el plan (días del mes × 8 × FTE) y la 9980.
    // Sin `horas` (un backend anterior a esta sección, en medio de un deploy)
    // la sección no aparece; el resto de la tabla se dibuja igual.
    if (!vista.horas) return out;
    const hs: Fila[] = [];
    // Las horas de un FTE completo en cada mes, para leer las de cada depto.
    if (vista.horas.horas_por_fte) {
      const h = vista.horas.horas_por_fte;
      hs.push({ label: t("planHorasPorFte"), meses: h, anual: sumar(h), tipo: "num", nivel: 1, negrita: true });
    }
    if (vista.horas.horas_por_fte_real) {
      const h = vista.horas.horas_por_fte_real;
      hs.push({ label: t("planRealCuentas", { cuentas: "9979" }), meses: h, anual: sumar(h), tipo: "num",
        nivel: 1, negrita: true, real: true });
    }
    for (const d of vista.horas.deptos) {
      hs.push({ label: `${d.depto} · ${d.nombre}`.replace(/ · $/, ""), meses: d.plan, anual: sumar(d.plan),
        tipo: "num", nivel: 2 });
      hs.push({ label: t("planRealCuentas", { cuentas: "9980" }), meses: d.real, anual: sumar(d.real),
        tipo: "num", nivel: 2, real: true });
    }
    const ht = vista.horas.total;
    hs.push({ label: t("planHorasTotal"), meses: ht.plan, anual: sumar(ht.plan), tipo: "num", nivel: 2, negrita: true });
    hs.push({ label: t("planRealCuentas", { cuentas: "9980" }), meses: ht.real, anual: sumar(ht.real),
      tipo: "num", nivel: 2, negrita: true, real: true });
    // El FTE del hotel con la misma base: horas ÷ (días del mes × 8). El anual
    // es el promedio de los meses con dato, no la suma.
    if (ht.fte_plan) hs.push({ label: t("planFte"), meses: ht.fte_plan, anual: promedio(ht.fte_plan),
      tipo: "fte", nivel: 2, negrita: true });
    if (ht.fte_real) hs.push({ label: t("planFteReal"), meses: ht.fte_real, anual: promedio(ht.fte_real),
      tipo: "fte", nivel: 2, negrita: true, real: true });
    out.push({ titulo: t("planHoras"), filas: hs });
    return out;
  }, [vista, t]);

  function bajarExcel() {
    if (!vista) return;
    const columnas: ColumnaCuadro[] = [
      { label: t("planConcepto"), ancho: 44, formato: "texto" },
      ...MESES.map(m => ({ label: m, ancho: 10, formato: "num1" as const })),
      { label: t("colAnio"), ancho: 12, formato: "num1" },
    ];
    const filas: FilaCuadro[] = [];
    for (const s of secciones) {
      filas.push({ label: s.titulo, es_seccion: true, valores: new Array(13).fill(null) });
      for (const f of s.filas) {
        filas.push({ label: f.label, nivel: f.nivel, ...(f.tipo === "pct" ? { formato: "pct" as const } : {}),
          valores: [...f.meses, f.anual] });
      }
    }
    const esc = vista.escenario;
    bajarCuadros(`Plan_vs_Integrity_${esc.type}_${esc.version}_${anio}`.replace(/\s+/g, "_"), [{
      titulo: t("planExcelTitulo", { tipo: esc.type, version: esc.version, anio }),
      subtitulo: t("planExcelSubtitulo"), hoja: "Plan vs Integrity", columnas, filas,
    }]).catch(e => setError(e instanceof Error ? e.message : String(e)));
  }

  const b = (c: React.ReactNode) => <strong>{c}</strong>;

  return (
    <div style={{ marginBottom: 26 }}>
      <h3 style={{ fontSize: 15, fontWeight: 700, margin: "4px 0 6px" }}>{t("planTitulo")}</h3>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 940, marginBottom: 12 }}>
        {t.rich("planIntro", { b })}
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{t("planEscenario")}:</span>
        <select value={sid} onChange={e => setSid(e.target.value)} style={{ ...BTN, fontWeight: 400 }}
          disabled={!escenarios.length}>
          {!escenarios.length && <option value="">{t("planSinEscenarios", { anio })}</option>}
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version}{s.is_current_forecast ? " ★" : ""}</option>
          ))}
        </select>
        <button onClick={bajarExcel} disabled={!vista}
          style={{ ...BTN, marginLeft: "auto", background: "var(--accent-excel)", color: "#fff", border: "none" }}>
          {t("excel")}
        </button>
      </div>

      {vista?.fuente === "actual_sin_tipo" && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
          {t.rich("planActualSinTipo", { b })}
        </div>
      )}
      {vista?.fuente === "forecast_rodante" && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
          {t.rich("planRodante", { b, corte: MESES[vista.escenario.actuals_through - 1] ?? "" })}
        </div>
      )}
      {error && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 12, fontSize: 12.5,
          background: "rgba(192,57,43,0.12)", border: "1px solid rgba(192,57,43,0.45)" }}>{error}</div>
      )}
      {cargando && <div style={{ color: "var(--text-secondary)", fontSize: 12.5 }}>{t("cargando")}</div>}

      {vista && (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th style={{ ...TD, color: "var(--brand)", fontWeight: 700, position: "static" }}>{t("planConcepto")}</th>
                {MESES.map(m => (
                  <th key={m} style={{ ...NUM, color: "var(--brand)", fontWeight: 700, position: "static" }}>{m}</th>
                ))}
                <th style={{ ...NUM, color: "var(--brand)", fontWeight: 700, position: "static" }}>{t("colAnio")}</th>
              </tr>
            </thead>
            <tbody>
              {secciones.map(s => (
                <Fragment key={s.titulo}>
                  <tr style={{ background: "var(--bg-elevated)" }}>
                    <td colSpan={14} style={{ ...TD, fontWeight: 700 }}>{s.titulo}</td>
                  </tr>
                  {s.filas.map((f, i) => {
                    const encabezado = f.nivel === 1;
                    const color = f.real ? "var(--brand)" : undefined;
                    return (
                      <tr key={i} title={f.titulo}>
                        <td style={{ ...TD, paddingLeft: f.nivel === 2 ? 26 : 12, fontWeight: f.negrita ? 600 : 400,
                          color: f.real ? "var(--brand)" : encabezado ? "var(--text-primary)" : "var(--text-secondary)" }}>
                          {f.label}
                        </td>
                        {encabezado
                          ? <td colSpan={13} style={TD} />
                          : <>
                              {f.meses.map((v, j) => (
                                <td key={j} style={{ ...NUM, fontWeight: f.negrita ? 600 : 400,
                                  color: v === null ? "var(--text-disabled)" : color }}>{fmt(v, f.tipo)}</td>
                              ))}
                              <td style={{ ...NUM, fontWeight: 700, color }}>{fmt(f.anual, f.tipo)}</td>
                            </>}
                      </tr>
                    );
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 10, maxWidth: 940 }}>
        {t.rich("planNota", { b })}
      </p>
    </div>
  );
}
