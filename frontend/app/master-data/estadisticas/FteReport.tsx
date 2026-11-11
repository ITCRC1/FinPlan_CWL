"use client";
/**
 * Master Data → Estadísticas → «FTE»: el reporte de FTE por depto y puesto.
 *
 * Owner, 2026-11-10: «ocupo que me generes un reporte de FTE basado en las horas
 * que se reportan en la planilla o en Budget» · «al menos por ahora el Budget
 * Working 2027» · «el FTE debe ser por position y las horas deben ser por
 * position que viene de la contabilidad» · «las posiciones correctas son las
 * que hay en FinPlan».
 *
 * Plan = las posiciones de la planilla de FinPlan (su FTE y FTE × la base del
 * mes). Real = las horas que registra contabilidad en Integrity por puesto
 * (9980-9986) convertidas al set 9902-9905. Las posiciones de FinPlan caen en
 * un puesto de Integrity según la homologación (`puestos_integrity_CWL.json`).
 * Solo lee.
 */
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { getReporteFte, getScenarios, type ReporteFte, type Scenario } from "@/lib/api";
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
type Tipo = "fte" | "horas";
interface Fila { label: string; meses: Meses | null; tipo: Tipo; nivel: 0 | 1 | 2 | 3;
  real?: boolean; negrita?: boolean; aviso?: string }

function fmt(v: number | null | undefined, tipo: Tipo): string {
  if (v === null || v === undefined) return "—";
  return tipo === "fte" ? v.toFixed(2) : v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}
/** FTE del año = promedio de los meses con dato; horas = suma. */
function anual(m: Meses, tipo: Tipo): number | null {
  const v = m.filter((x): x is number => x !== null);
  if (!v.length) return null;
  const s = v.reduce((a, x) => a + x, 0);
  return tipo === "fte" ? s / v.length : s;
}

export default function FteReport() {
  const t = useTranslations("statsInt");
  const anioHoy = new Date().getFullYear();
  const [anio, setAnio] = useState<number>(anioHoy + (new Date().getMonth() >= 10 ? 1 : 0));
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const preferido = useCallback((del: Scenario[]) =>
    del.find(s => s.type === "BUDGET" && /working/i.test(s.version))
      ?? del.find(s => s.type === "FORECAST" && /working/i.test(s.version))
      ?? del.find(s => s.is_current_forecast) ?? del[0], []);
  const [sid, setSid] = useEscenarioDe("master-data/stats:fte", escenarios, "budget", preferido);
  const [vista, setVista] = useState<ReporteFte | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [verPosiciones, setVerPosiciones] = useState(false);
  const MESES = useMemo(() => t("meses").split(","), [t]);

  useEffect(() => {
    let vivo = true;
    getScenarios(HOTEL_ID).then(todos => {
      if (!vivo) return;
      const orden = (x: string) => ["BUDGET", "FORECAST", "ACTUAL"].indexOf(x);
      setEscenarios(todos.filter(s => s.year === anio && orden(s.type) >= 0)
        .sort((a, b) => orden(a.type) - orden(b.type) || a.version.localeCompare(b.version)));
    }).catch(e => { if (vivo) setError(e instanceof Error ? e.message : String(e)); });
    return () => { vivo = false; };
  }, [anio]);

  useEffect(() => {
    if (!sid || !escenarios.some(s => s.id === sid)) { setVista(null); return; }
    let vivo = true;
    setCargando(true); setError(null);
    getReporteFte(anio, sid)
      .then(v => { if (vivo) setVista(v); })
      .catch(e => { if (vivo) { setVista(null); setError(e instanceof Error ? e.message : String(e)); } })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [anio, sid, escenarios]);

  const filas = useMemo(() => {
    if (!vista) return [] as Fila[];
    const out: Fila[] = [];
    const conHoras = vista.hay_horas;
    const reales = (h: Record<string, Meses>, s: Record<string, Meses>, nivel: 2 | 3, negrita = false) => {
      if (!conHoras) return;
      out.push({ label: t("fteHorasReales"), meses: h["9980"], tipo: "horas", nivel, real: true, negrita });
      for (const c of Object.keys(vista.set_nombres)) {
        out.push({ label: `${c} · ${vista.set_nombres[c]}`, meses: s[c], tipo: "fte", nivel, real: true, negrita });
      }
    };
    out.push({ label: t("planHorasPorFte"), meses: vista.base, tipo: "horas", nivel: 2, negrita: true });
    for (const d of vista.deptos) {
      out.push({ label: `${d.depto} · ${d.nombre}`.replace(/ · $/, ""), meses: null, tipo: "fte", nivel: 0 });
      for (const p of d.puestos) {
        out.push({ label: `${p.puesto} · ${p.nombre || t("fteSinNombre")}`, meses: null, tipo: "fte", nivel: 1,
          aviso: p.revisar ? t("fteRevisar") : undefined });
        out.push({ label: t("fteFtePlan"), meses: p.fte_plan, tipo: "fte", nivel: 2 });
        out.push({ label: t("fteHorasPlan"), meses: p.horas_plan, tipo: "horas", nivel: 2 });
        reales(p.horas, p.set, 2);
        if (verPosiciones) for (const x of p.posiciones) {
          out.push({ label: `${x.codigo} · ${x.nombre} · ${x.empleado}`, meses: x.fte, tipo: "fte", nivel: 3,
            aviso: x.revisar ? x.nota : undefined });
        }
      }
      if (d.sin_puesto.length) {
        out.push({ label: t("fteSinPuesto"), meses: null, tipo: "fte", nivel: 1, aviso: d.sin_puesto[0]?.nota });
        const fte = Array.from({ length: 12 }, (_, i) => d.sin_puesto.reduce((a, x) => a + x.fte[i], 0));
        out.push({ label: t("fteFtePlan"), meses: fte, tipo: "fte", nivel: 2 });
        if (verPosiciones) for (const x of d.sin_puesto) {
          out.push({ label: `${x.codigo} · ${x.nombre} · ${x.empleado}`, meses: x.fte, tipo: "fte", nivel: 3 });
        }
      }
      out.push({ label: t("fteTotalDepto"), meses: d.fte_plan, tipo: "fte", nivel: 2, negrita: true });
      out.push({ label: t("fteHorasPlan"), meses: d.horas_plan, tipo: "horas", nivel: 2, negrita: true });
      reales(d.horas, d.set, 2, true);
    }
    out.push({ label: t("fteTotalHotel"), meses: null, tipo: "fte", nivel: 0 });
    out.push({ label: t("fteFtePlan"), meses: vista.total.fte_plan, tipo: "fte", nivel: 2, negrita: true });
    out.push({ label: t("fteHorasPlan"), meses: vista.total.horas_plan, tipo: "horas", nivel: 2, negrita: true });
    reales(vista.total.horas, vista.total.set, 2, true);
    return out;
  }, [vista, verPosiciones, t]);

  function bajarExcel() {
    if (!vista) return;
    const columnas: ColumnaCuadro[] = [
      { label: t("planConcepto"), ancho: 52, formato: "texto" },
      ...MESES.map(m => ({ label: m, ancho: 10, formato: "num1" as const })),
      { label: t("colAnio"), ancho: 12, formato: "num1" },
    ];
    const cuadro: FilaCuadro[] = filas.map(f => f.meses === null
      ? { label: f.label, es_seccion: f.nivel === 0, nivel: f.nivel === 0 ? undefined : 1, valores: new Array(13).fill(null) }
      : { label: f.label, nivel: Math.min(f.nivel, 2) as 0 | 1 | 2, valores: [...f.meses, anual(f.meses, f.tipo)] });
    const esc = vista.escenario;
    bajarCuadros(`FTE_${esc.type}_${esc.version}_${anio}`.replace(/\s+/g, "_"), [{
      titulo: t("fteExcelTitulo", { tipo: esc.type, version: esc.version, anio }),
      subtitulo: t("fteExcelSubtitulo"), hoja: "FTE", columnas, filas: cuadro,
    }]).catch(e => setError(e instanceof Error ? e.message : String(e)));
  }

  const b = (c: React.ReactNode) => <strong>{c}</strong>;

  return (
    <div>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 940, marginBottom: 12 }}>
        {t.rich("fteIntro", { b })}
      </p>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{t("anio")}:</span>
        <select value={anio} onChange={e => setAnio(Number(e.target.value))} style={{ ...BTN, fontWeight: 400 }}>
          {[anioHoy - 1, anioHoy, anioHoy + 1, anioHoy + 2].map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{t("planEscenario")}:</span>
        <select value={sid} onChange={e => setSid(e.target.value)} style={{ ...BTN, fontWeight: 400 }}
          disabled={!escenarios.length}>
          {!escenarios.length && <option value="">{t("planSinEscenarios", { anio })}</option>}
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version}{s.is_current_forecast ? " ★" : ""}</option>
          ))}
        </select>
        <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={verPosiciones} onChange={e => setVerPosiciones(e.target.checked)} />
          {t("fteVerPosiciones")}
        </label>
        <button onClick={bajarExcel} disabled={!vista}
          style={{ ...BTN, marginLeft: "auto", background: "var(--accent-excel)", color: "#fff", border: "none" }}>
          {t("excel")}
        </button>
      </div>

      {vista && !vista.hay_horas && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
          {t.rich("fteSinHoras", { b, anio })}
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
              {filas.map((f, i) => {
                if (f.meses === null) {
                  return (
                    <tr key={i} style={f.nivel === 0 ? { background: "var(--bg-elevated)" } : undefined}>
                      <td colSpan={14} style={{ ...TD, fontWeight: 700, paddingLeft: f.nivel === 0 ? 8 : 16 }}>
                        {f.label}
                        {f.aviso && <span title={f.aviso} style={{ marginLeft: 8, fontWeight: 400, fontSize: 11,
                          color: "var(--warning)" }}>⚠ {f.aviso}</span>}
                      </td>
                    </tr>
                  );
                }
                const color = f.real ? "var(--brand)" : undefined;
                return (
                  <tr key={i}>
                    <td title={f.aviso} style={{ ...TD, paddingLeft: f.nivel === 3 ? 44 : 28, fontWeight: f.negrita ? 600 : 400,
                      fontSize: f.nivel === 3 ? 11.5 : 12,
                      color: f.real ? "var(--brand)" : f.nivel === 3 ? "var(--text-secondary)" : "var(--text-primary)" }}>
                      {f.label}{f.aviso ? " ⚠" : ""}
                    </td>
                    {f.meses.map((v, j) => (
                      <td key={j} style={{ ...NUM, fontWeight: f.negrita ? 600 : 400,
                        color: v === null ? "var(--text-disabled)" : color }}>{fmt(v, f.tipo)}</td>
                    ))}
                    <td style={{ ...NUM, fontWeight: 700, color }}>{fmt(anual(f.meses, f.tipo), f.tipo)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
