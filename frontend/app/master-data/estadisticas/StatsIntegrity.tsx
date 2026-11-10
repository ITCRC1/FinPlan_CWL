"use client";
/**
 * Master Data → Estadísticas → «Stats»: las estadísticas de Integrity al mes.
 *
 * Owner, 2026-11-10: «puedes ponerla en otro sub tab para no mezclar» · «la
 * contabilidad manda» · «solo full month».
 *
 * **Solo lee.** El dato es el Balance de Comprobación que se sube en la
 * Auditoría del mayor: no hay otra carga ni plantilla. En Integrity el nivel 6
 * de la cuenta es el día (lo pone Opera, igual que en el ingreso); el backend lo
 * suma y acá se ve solo el mes.
 *
 * Va aparte del catálogo de FinPlan (la otra pestaña) a propósito: este usa los
 * códigos de Integrity homologados y no alimenta ningún total.
 */
import { Fragment, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { getStatsIntegrity, type StatsIntegrityVista } from "@/lib/api";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";

const BTN: React.CSSProperties = {
  padding: "7px 14px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 13, fontWeight: 600,
};
const TD: React.CSSProperties = { padding: "4px 8px", fontSize: 12, whiteSpace: "nowrap", textAlign: "left" };
const NUM: React.CSSProperties = { ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" };

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

export default function StatsIntegrity() {
  const t = useTranslations("statsInt");
  const anioHoy = new Date().getFullYear();
  const [anio, setAnio] = useState<number>(anioHoy + (new Date().getMonth() >= 10 ? 1 : 0));
  const [vista, setVista] = useState<StatsIntegrityVista | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set());
  const [depto, setDepto] = useState("");
  const [soloConDato, setSoloConDato] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCargando(true); setError(null);
    getStatsIntegrity(anio)
      .then(v => { if (vivo) setVista(v); })
      .catch(e => { if (vivo) { setVista(null); setError(e instanceof Error ? e.message : String(e)); } })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [anio]);

  const MESES = useMemo(() => t("meses").split(","), [t]);
  const deptos = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of vista?.cuentas ?? []) if (c.depto) m.set(c.depto, c.depto_nombre);
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [vista]);

  const cuentasPorGrupo = useMemo(() => {
    const m = new Map<string, StatsIntegrityVista["cuentas"]>();
    for (const c of vista?.cuentas ?? []) {
      if (depto && c.depto !== depto) continue;
      if (soloConDato && !c.con_dato) continue;
      const l = m.get(c.grupo) ?? [];
      l.push(c); m.set(c.grupo, l);
    }
    return m;
  }, [vista, depto, soloConDato]);

  function alternar(g: string) {
    setAbiertos(prev => {
      const n = new Set(prev);
      if (n.has(g)) n.delete(g); else n.add(g);
      return n;
    });
  }

  function bajarExcel() {
    if (!vista) return;
    const columnas: ColumnaCuadro[] = [
      { label: t("colCuenta"), ancho: 30, formato: "texto" },
      { label: t("colConcepto"), ancho: 26, formato: "texto" },
      { label: t("colDescripcion"), ancho: 46, formato: "texto" },
      { label: t("colDepto"), ancho: 20, formato: "texto" },
      { label: t("colUnidad"), ancho: 12, formato: "texto" },
      { label: t("colEnIntegrity"), ancho: 12, formato: "texto" },
      ...MESES.map(m => ({ label: m, ancho: 10, formato: "num1" as const })),
      { label: t("colAnio"), ancho: 12, formato: "num1",
        suma_cols: Array.from({ length: 12 }, (_, i) => 7 + i) },
    ];
    const filas: FilaCuadro[] = [];
    for (const g of vista.grupos) {
      const cs = cuentasPorGrupo.get(g.grupo) ?? [];
      if (!cs.length) continue;
      filas.push({ label: `${g.grupo} · ${g.concepto}`, es_seccion: true,
                   valores: new Array(columnas.length - 1).fill(null) });
      for (const c of cs) {
        filas.push({ label: c.codigo, nivel: 1, valores: [
          c.concepto, c.descripcion, `${c.depto} ${c.depto_nombre}`.trim(), c.unidad,
          c.en_integrity ? t("si") : t("crear"),
          ...c.meses.map(v => v ?? null), c.total || null,
        ]});
      }
    }
    bajarCuadros(`Stats_Integrity_${anio}`, [{
      titulo: t("excelTitulo", { anio }),
      subtitulo: t("excelSubtitulo", { version: vista.version_catalogo }),
      hoja: "Stats", columnas, filas,
    }]).catch(e => setError(e instanceof Error ? e.message : String(e)));
  }

  const b = (c: React.ReactNode) => <strong>{c}</strong>;
  const cargados = vista?.meses_cargados ?? [];

  return (
    <div>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 940, marginBottom: 14 }}>
        {t.rich("intro", { b })}
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
        <span style={{ fontSize: 12.5, fontWeight: 600 }}>{t("anio")}:</span>
        <select value={anio} onChange={e => setAnio(Number(e.target.value))} style={{ ...BTN, fontWeight: 400 }}>
          {[anioHoy - 1, anioHoy, anioHoy + 1, anioHoy + 2].map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span style={{ fontSize: 12.5, fontWeight: 600, marginLeft: 8 }}>{t("depto")}:</span>
        <select value={depto} onChange={e => setDepto(e.target.value)} style={{ ...BTN, fontWeight: 400 }}>
          <option value="">{t("todos")}</option>
          {deptos.map(([d, n]) => <option key={d} value={d}>{d} {n}</option>)}
        </select>
        <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center", marginLeft: 8 }}>
          <input type="checkbox" checked={soloConDato} onChange={e => setSoloConDato(e.target.checked)} />
          {t("soloConDato")}
        </label>
        <button onClick={bajarExcel} disabled={!vista}
          style={{ ...BTN, marginLeft: "auto", background: "var(--accent-excel)", color: "#fff", border: "none" }}>
          {t("excel")}
        </button>
      </div>

      {/* Qué meses tienen balanza guardada */}
      <div style={{ padding: "10px 14px", borderRadius: 8, marginBottom: 14, fontSize: 12.5,
        background: "var(--bg-surface)", border: "1px solid var(--border-medium)" }}>
        {cargados.length
          ? t.rich("mesesCargados", { b, meses: cargados.map(m => MESES[m - 1]).join(", "), anio })
          : t("sinBalanza", { anio })}
        {vista && (
          <div style={{ marginTop: 6, color: vista.cuentas_con_dato ? "var(--positive)" : "var(--text-secondary)" }}>
            {vista.cuentas_con_dato
              ? t("conDato", { n: vista.cuentas_con_dato })
              : t("sinClase9")}
          </div>
        )}
      </div>

      {error && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 12.5,
          background: "rgba(192,57,43,0.12)", border: "1px solid rgba(192,57,43,0.45)" }}>{error}</div>
      )}

      {vista && vista.fuera_de_catalogo.length > 0 && (
        <div style={{ padding: "10px 14px", borderRadius: 8, marginBottom: 14, fontSize: 12.5,
          background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.45)" }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>
            {t("fuera", { n: vista.fuera_de_catalogo.length })}
          </div>
          {vista.fuera_de_catalogo.slice(0, 12).map(f => (
            <div key={f.clave} className="mono" style={{ fontSize: 11.5 }}>
              {f.clave} · {t("total")}: {fmt(f.total)}
            </div>
          ))}
          {vista.fuera_de_catalogo.length > 12 && <div>…</div>}
        </div>
      )}

      {cargando && <div style={{ color: "var(--text-secondary)", fontSize: 12.5 }}>{t("cargando")}</div>}

      {vista && (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                {[t("colCuenta"), t("colConcepto"), t("colUnidad"), t("colCuentas")].map(h => (
                  <th key={h} style={{ ...TD, textAlign: "left", color: "var(--brand)", fontWeight: 700, position: "static" }}>{h}</th>
                ))}
                {MESES.map((m, i) => (
                  <th key={m} style={{ ...NUM, color: cargados.includes(i + 1) ? "var(--brand)" : "var(--text-disabled)",
                    fontWeight: 700, position: "static" }}>{m}</th>
                ))}
                <th style={{ ...NUM, color: "var(--brand)", fontWeight: 700, position: "static" }}>{t("colAnio")}</th>
              </tr>
            </thead>
            <tbody>
              {vista.grupos.map(g => {
                const cs = cuentasPorGrupo.get(g.grupo) ?? [];
                if (!cs.length) return null;
                const abierto = abiertos.has(g.grupo);
                const totalGrupo = cs.reduce((s, c) => s + (c.total || 0), 0);
                const mesesGrupo = Array.from({ length: 12 }, (_, i) =>
                  cs.some(c => c.meses[i] !== null) ? cs.reduce((s, c) => s + (c.meses[i] ?? 0), 0) : null);
                return (
                  <Fragment key={g.grupo}>
                    <tr onClick={() => alternar(g.grupo)} style={{ cursor: "pointer", background: "var(--bg-elevated)" }}>
                      <td className="mono" style={{ ...TD, fontWeight: 700 }}>{abierto ? "▾" : "▸"} {g.grupo}</td>
                      <td style={{ ...TD, fontWeight: 600 }}>{g.concepto}</td>
                      <td style={{ ...TD, color: "var(--text-secondary)" }}>{g.unidad}</td>
                      <td style={{ ...TD, color: "var(--text-secondary)" }}>
                        {cs.length}{g.con_dato ? ` · ${t("conDatoCorto", { n: cs.filter(c => c.con_dato).length })}` : ""}
                      </td>
                      {mesesGrupo.map((v, i) => <td key={i} style={{ ...NUM, fontWeight: 600 }}>{fmt(v)}</td>)}
                      <td style={{ ...NUM, fontWeight: 700 }}>{totalGrupo ? fmt(totalGrupo) : "—"}</td>
                    </tr>
                    {abierto && cs.map(c => (
                      <tr key={c.clave} title={[c.nivel3, c.nivel4, c.nivel5, c.nivel7, c.nota].filter(Boolean).join(" · ")}>
                        <td className="mono" style={{ ...TD, paddingLeft: 22, fontSize: 11.5 }}>
                          {c.codigo}
                          {!c.en_integrity && (
                            <span style={{ marginLeft: 6, fontSize: 10, color: "var(--warning, #E6A817)" }}>{t("crear")}</span>
                          )}
                        </td>
                        <td style={{ ...TD, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis" }}>
                          {c.descripcion}
                          {c.cuenta_ingreso && (
                            <span style={{ color: "var(--text-disabled)" }}> · {t("ingreso")} {c.cuenta_ingreso}</span>
                          )}
                        </td>
                        <td style={{ ...TD, color: "var(--text-secondary)", maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis" }}>{c.depto} {c.depto_nombre}</td>
                        <td style={TD} />
                        {c.meses.map((v, i) => (
                          <td key={i} style={{ ...NUM, color: v === null ? "var(--text-disabled)" : undefined }}>{fmt(v)}</td>
                        ))}
                        <td style={{ ...NUM, fontWeight: 600 }}>{c.con_dato ? fmt(c.total) : "—"}</td>
                      </tr>
                    ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 14, maxWidth: 940 }}>
        {t.rich("nota", { b })}
      </p>
    </div>
  );
}
