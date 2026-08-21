"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getAuditTrace, getMappingHealth, uploadTemplateUrl, validateUpload,
  type Scenario, type AuditTrace, type MappingHealth, type TraceRow,
  type ValidateUploadResult,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { recalcularYContar } from "@/lib/recalcular";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const money = (n: number) =>
  (n < 0 ? "(" : "") + "$" + Math.abs(Math.round(n)).toLocaleString("en-US") + (n < 0 ? ")" : "");

// El color queda acá; la etiqueta y la explicación salen del catálogo
// (`control.mode.*`), porque son texto que el usuario lee.
const MODE_STYLE: Record<string, { bg: string; fg: string; k: string }> = {
  exact: { bg: "rgba(26,127,75,.15)", fg: "#1fa363", k: "exact" },
  "dept-agnostic": { bg: "rgba(133,100,4,.18)", fg: "#c9a227", k: "deptAgnostic" },
  FALLBACK: { bg: "rgba(200,90,20,.18)", fg: "#e08b3e", k: "fallback" },
  DROP: { bg: "rgba(192,57,43,.20)", fg: "#e0798a", k: "drop" },
};

export default function ControlPage() {
  const tc = useTranslations("common");
  // `t` ya está tomado más abajo (data.totales). El hook va con otro nombre.
  const tCtl = useTranslations("control");
  const tm = useTranslations("months");
  const MESES = tm.raw("long") as string[];
  // El estilo (color) es de la pantalla; la etiqueta y la ayuda, del catálogo.
  const modeSty = (mode: string, fb = "exact") => {
    const st = MODE_STYLE[mode] ?? MODE_STYLE[fb];
    return { ...st, label: tCtl(`mode.${st.k}.label`), help: tCtl(`mode.${st.k}.help`) };
  };
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner. El 2027 estaba escrito aca, pero
  // sin mirar la version: con varios Budget 2027 (Working, draft4-BIG) auditaba
  // el que quedara primero, y si no habia ninguno caia en el ano mas alto.
  const [scenarioId, setScenarioId] = useEscenarioDe("admin/control:budget", scenarios, "budget", undefined, true);
  const [month, setMonth] = useState(0);
  const [data, setData] = useState<AuditTrace | null>(null);
  const [health, setHealth] = useState<MappingHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [soloProblemas, setSoloProblemas] = useState(false);
  const [vfile, setVfile] = useState<File | null>(null);
  const [vres, setVres] = useState<ValidateUploadResult | null>(null);
  const [vbusy, setVbusy] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        // El orden es solo para leer la lista desplegable (Budget, Forecast,
        // Actual; dentro de cada uno el ano mas nuevo arriba). Cual queda
        // elegido lo decide `useEscenarioDe`, no la posicion en la lista.
        const order = { BUDGET: 0, FORECAST: 1, ACTUAL: 2 } as Record<string, number>;
        setScenarios([...all].sort((a, b) =>
          (order[a.type] ?? 9) - (order[b.type] ?? 9) || b.year - a.year));
        setHealth(await getMappingHealth());
      } catch (e) { setErr(e instanceof Error ? e.message : tc("error")); }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async (sid: string, m: number) => {
    if (!sid) return;
    setLoading(true); setErr(null); setMsg(null);
    try { setData(await getAuditTrace(sid, m)); }
    catch (e) { setErr(e instanceof Error ? e.message : tc("error")); setData(null); }
    finally { setLoading(false); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (scenarioId) load(scenarioId, month); }, [scenarioId, month, load]);

  async function handleRecalc() {
    if (!scenarioId) return;
    setRecalc(true); setMsg(null); setErr(null);
    try {
      const aviso = await recalcularYContar(scenarioId, tCtl("recalcOk"));
      await load(scenarioId, month);
      setMsg(aviso);
    } catch (e) { setErr(e instanceof Error ? e.message : tCtl("recalcErr")); }
    finally { setRecalc(false); }
  }

  // El filtro completo, SIN el techo de 500. La pantalla recorta para no morir
  // pintando; el Excel se lleva todo lo que el filtro deja pasar.
  const rowsFiltradas = useMemo(() => {
    let r: TraceRow[] = data?.rows ?? [];
    if (soloProblemas) r = r.filter(x => x.mode === "DROP" || x.mode === "FALLBACK");
    // Varios términos, todos tienen que estar. Con un solo término no se podía
    // pedir "la cuenta 6000 DE actividades": buscar 6000 traía las 18 cuentas
    // 6000 de todos los departamentos. Ahora "0150 6000" deja justo ese par,
    // con sus entradas y salidas.
    const terminos = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (terminos.length) {
      r = r.filter(x => {
        const texto = `${x.account_code} ${x.account_name} ${x.dept_code} ${x.dept_name} ${x.line_name} ${x.line_code ?? ""} ${x.origin}`.toLowerCase();
        return terminos.every(t => texto.includes(t));
      });
    }
    return r;
  }, [data, q, soloProblemas]);
  const rows = useMemo(() => rowsFiltradas.slice(0, 500), [rowsFiltradas]);

  const sel = scenarios.find(s => s.id === scenarioId);

  /* ── Bajar a Excel ─────────────────────────────────────────────────────────
     Todo lo que la pantalla tiene cargado, con el escenario y el período
     elegidos: el semáforo, las cuentas de control, el saldo por línea y el
     detalle de dónde cae cada cuenta (este último completo, sin el techo de 500
     que usa la tabla para no morir pintando). Si hay un archivo validado, sus
     filas con problema salen también.

     Los códigos van como TEXTO a propósito: un dept_code "0110" pasado a número
     queda en 110 y deja de casar con nada — justo el error que esta pantalla
     existe para cazar. */
  async function bajarExcel() {
    if (!data) return;
    setExporting(true); setErr(null);
    try {
      const tt = data.totales;
      const periodo = month === 0 ? tCtl("fullYear") : MESES[month - 1];
      const sub = `${sel ? `${sel.type} · ${sel.version} · ${sel.year}` : ""} · ${periodo}`;
      const cuadros: Cuadro[] = [];

      // 1 · Semáforo de ruteo + salud del mapeo
      const resumen: FilaCuadro[] = [
        { label: tCtl("xls.routingPeriod"), es_total: true, valores: [null] },
        { label: tCtl("rowsExact"), nivel: 1, formato: "num", valores: [tt.filas_exact] },
        { label: tCtl("xls.noDeptLong"), nivel: 1, formato: "num", valores: [tt.filas_dept_agnostic] },
        { label: tCtl("xls.fallbackLong"), nivel: 1, formato: "num", valores: [tt.filas_FALLBACK] },
        { label: tCtl("rowsDrop"), nivel: 1, formato: "num", valores: [tt.filas_DROP] },
        { label: tCtl("xls.sourceRows"), nivel: 1, formato: "num", valores: [tt.filas_fuente] },
        { label: tCtl("xls.sourceAmount"), nivel: 1, formato: "usd", valores: [tt.monto_fuente] },
        { label: tCtl("amountLost"), nivel: 1, formato: "usd", valores: [tt.monto_perdido_DROP] },
      ];
      if (health) {
        resumen.push(
          { label: tCtl("xls.mappingHealth"), es_total: true, valores: [null] },
          { label: tCtl("xls.activeRules"), nivel: 1, formato: "num", valores: [health.reglas_activas] },
          { label: tCtl("xls.rulesNoDeptCode"), nivel: 1, formato: "num", valores: [health.reglas_sin_dept_code] },
          { label: tCtl("xls.deptDependentAccounts"), nivel: 1, formato: "num", valores: [health.cuentas_multi_linea] },
          { label: tCtl("xls.ambiguousPairs"), nivel: 1, formato: "num", valores: [health.pares_ambiguos_total] },
        );
      }
      cuadros.push({
        titulo: tCtl("xls.summaryTitle"),
        subtitulo: health ? `${sub} · ${health.veredicto}` : sub,
        hoja: tCtl("xls.summarySheet"),
        columnas: [
          { label: tc("concept"), ancho: 46, formato: "texto" },
          { label: tCtl("xls.value"), ancho: 18, formato: "num" },
        ],
        filas: resumen,
      });

      // 2 · Cuentas de control del P&L
      cuadros.push({
        titulo: tCtl("xls.controlAccountsTitle"),
        subtitulo: sub,
        hoja: tCtl("xls.controlAccountsSheet"),
        columnas: [
          { label: tCtl("xls.controlAccount"), ancho: 40, formato: "texto" },
          { label: tCtl("xls.amountUsd"), ancho: 18, formato: "usd" },
        ],
        filas: Object.entries(data.pl_control).map(([k, v]) => ({ label: k, valores: [v] })),
      });

      // 3 · Saldo por línea del P&L
      cuadros.push({
        titulo: tCtl("byLineTitle"),
        subtitulo: `${sub} ${tCtl("byLineHint")}`,
        hoja: tCtl("xls.byLineSheet"),
        columnas: [
          { label: tc("line"), ancho: 40, formato: "texto" },
          { label: tc("code"), ancho: 14, formato: "texto" },
          { label: tCtl("section"), ancho: 22, formato: "texto" },
          { label: tCtl("sumSources"), ancho: 16, formato: "usd" },
          { label: "P&L", ancho: 16, formato: "usd" },
          { label: "Δ", ancho: 14, formato: "usd" },
          { label: tCtl("depts"), ancho: 34, formato: "texto" },
        ],
        filas: data.by_line.map(l => ({
          label: l.line_name,
          // Δ vacío cuando cuadra: en pantalla es «—», y un 0 de verdad diría
          // otra cosa (que la línea existe y da cero).
          valores: [l.line_code, l.section, l.amount_sources, l.amount_pl,
            l.ok ? null : l.dif, l.depts.join(", ")],
        })),
      });

      // 4 · Detalle: dónde cae cada cuenta
      cuadros.push({
        titulo: tCtl("whereEachLands"),
        subtitulo: `${sub} · ${tCtl("rowsOf", { n: rowsFiltradas.length, total: data.rows.length })}`
          + (soloProblemas ? tCtl("xls.onlyProblemsSuffix") : "")
          + (q.trim() ? tCtl("xls.searchSuffix", { q: q.trim() }) : ""),
        hoja: tCtl("xls.detailSheet"),
        columnas: [
          { label: tCtl("origin"), ancho: 18, formato: "texto" },
          { label: tc("deptCode"), ancho: 11, formato: "texto" },
          { label: tc("department"), ancho: 28, formato: "texto" },
          { label: tc("account"), ancho: 10, formato: "texto" },
          { label: tCtl("xls.accountName"), ancho: 30, formato: "texto" },
          { label: tCtl("xls.amountUsd"), ancho: 15, formato: "usd" },
          { label: tCtl("xls.plLine"), ancho: 32, formato: "texto" },
          { label: tCtl("routing"), ancho: 15, formato: "texto" },
          { label: tCtl("xls.usesDeptRuleCol"), ancho: 18, formato: "texto" },
        ],
        filas: rowsFiltradas.map(r => ({
          label: r.origin,
          valores: [
            r.dept_code, r.dept_name, r.account_code, r.account_name, r.amount,
            r.line_code ? r.line_name : tCtl("notInPL"),
            modeSty(r.mode).label,
            r.mode === "FALLBACK" && r.fallback_from ? r.fallback_from : "",
          ],
        })),
      });

      // 5 · Validación del archivo subido, si hay uno validado en pantalla
      if (vres) {
        const malas = vres.detalle.filter(d => !d.ok);
        cuadros.push({
          titulo: tCtl("xls.fileValidationTitle"),
          subtitulo: `${vres.veredicto} · ` + tCtl("xls.fileValidationSub",
            { filas: vres.filas, ok: vres.filas_ok, problema: vres.filas_con_problema }),
          hoja: tCtl("xls.fileValidationSheet"),
          columnas: [
            { label: tCtl("row"), ancho: 8, formato: "texto" },
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 28, formato: "texto" },
            { label: tc("account"), ancho: 10, formato: "texto" },
            { label: tCtl("xls.amountUsd"), ancho: 15, formato: "usd" },
            { label: tCtl("problem"), ancho: 48, formato: "texto" },
          ],
          filas: [
            ...malas.map(d => {
              const st = modeSty(d.mode, "DROP");
              return {
                label: String(d.fila),
                valores: [d.dept_code, d.dept_name, d.account_code,
                  d.monto, `${st.label} — ${st.help}`],
              };
            }),
            { label: tCtl("xls.amountArriving"), es_total: true, valores: ["", "", "", vres.monto_que_llega, ""] },
            { label: tCtl("xls.amountWouldBeLost"), es_total: true, valores: ["", "", "", vres.monto_que_se_perderia, ""] },
          ],
        });
      }

      await bajarCuadros("Control_Ruteo", cuadros);
    } catch (e) {
      setErr(e instanceof Error ? e.message : tCtl("excelError"));
    } finally {
      setExporting(false);
    }
  }

  const card: React.CSSProperties = { background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "14px 16px", marginBottom: 16 };
  const inp: React.CSSProperties = { padding: "6px 10px", borderRadius: 6, background: "var(--bg-input, #1b2130)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", fontSize: 13 };
  const t = data?.totales;

  return (
    <div className="pag pag-ancha" style={{ padding: 22 }}>
      <IrA esc={scenarioId} />
      <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>
        {tCtl("title")}
      </h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16, maxWidth: "78ch" }}>
        {tCtl.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {/* Salud del mapeo */}
      {health && (
        <div style={{ ...card, borderColor: health.riesgo_misruteo ? "var(--accent-red, #C0392B)" : "var(--accent-green, #1A7F4B)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: health.riesgo_misruteo ? "var(--accent-red, #C0392B)" : "var(--accent-green, #1A7F4B)" }}>
            {health.veredicto}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6, display: "flex", gap: 18, flexWrap: "wrap" }}>
            <span>{tCtl("activeRules")}<b>{health.reglas_activas.toLocaleString()}</b></span>
            <span>{tCtl("noDept")}<b style={{ color: health.reglas_sin_dept_code ? "var(--accent-red, #C0392B)" : undefined }}>{health.reglas_sin_dept_code}</b></span>
            <span>{tCtl("deptDependent")}<b>{health.cuentas_multi_linea}</b></span>
            <span>{tCtl("ambiguousPairs")}<b>{health.pares_ambiguos_total}</b></span>
            {health.mapeos_a_linea_inexistente.length > 0 && (
              <span style={{ color: "var(--accent-red, #C0392B)" }}>{tCtl("pointToMissing", { lineas: health.mapeos_a_linea_inexistente.join(", ") })}</span>
            )}
          </div>
        </div>
      )}

      {/* Controles */}
      <div style={{ ...card, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>{tCtl("version")}&nbsp;
          <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} style={inp}>
            {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>{tCtl("period")}&nbsp;
          <select value={month} onChange={e => setMonth(Number(e.target.value))} style={inp}>
            <option value={0}>{tCtl("fullYear")}</option>
            {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
        </label>
        <button onClick={handleRecalc} disabled={recalc || !scenarioId || sel?.is_locked}
          title={tc("recalc.hint")}
          style={{ padding: "8px 16px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 600, background: recalc ? "#555" : "var(--brand)", color: "#fff" }}>
          {recalc ? tc("recalc.running") : tc("recalc.button")}
        </button>
        <button onClick={() => load(scenarioId, month)} disabled={loading}
          style={{ padding: "8px 14px", borderRadius: 6, border: "1px solid var(--border-medium)", cursor: "pointer", fontSize: 13, background: "transparent", color: "var(--text-secondary)" }}>
          {loading ? "…" : tCtl("refresh")}
        </button>
        <button onClick={bajarExcel} disabled={exporting || !data}
          title={tCtl("excelHint")}
          style={{ padding: "8px 14px", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600, background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          {exporting ? tCtl("generating") : "⬇ Excel"}
        </button>
        {sel?.is_locked &&<span style={{ fontSize: 12, color: "var(--accent-amber, #856404)" }}>{tCtl("locked")}</span>}
      </div>
      {/* Plantilla + validación previa */}
      <div style={card}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{tCtl("uploadValidated")}</div>
        <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10, maxWidth: "76ch" }}>
          {tCtl.rich("templateHelp", {
            hoja: tCtl("valid"),
            b: (c: React.ReactNode) => <b>{c}</b>,
          })}
        </p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <a href={uploadTemplateUrl()} style={{ padding: "8px 14px", borderRadius: 6, background: "var(--brand)", color: "#fff", fontSize: 13, fontWeight: 600, textDecoration: "none" }}>{tCtl("downloadTemplate")}</a>
          <input type="file" accept=".xlsx" onChange={e => { setVfile(e.target.files?.[0] ?? null); setVres(null); }} className="fin-input" />
          <button disabled={!vfile || vbusy} onClick={async () => {
            if (!vfile) return;
            setVbusy(true); setErr(null);
            try { setVres(await validateUpload(vfile)); }
            catch (e) { setErr(e instanceof Error ? e.message : tc("error")); }
            finally { setVbusy(false); }
          }} style={{ padding: "8px 14px", borderRadius: 6, border: "none", cursor: vfile ? "pointer" : "default", fontSize: 13, fontWeight: 600, background: vfile && !vbusy ? "var(--accent-excel)" : "#555", color: "#fff" }}>
            {vbusy ? tCtl("validating") : tCtl("validateFile")}
          </button>
        </div>
        {vres && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: vres.filas_con_problema ? "var(--accent-red, #C0392B)" : "var(--accent-green, #1A7F4B)" }}>{vres.veredicto}</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 8px", display: "flex", gap: 16, flexWrap: "wrap" }}>
              <span>{tCtl("rowsLabel")} <b>{vres.filas}</b></span>
              <span>OK: <b style={{ color: "var(--accent-green, #1A7F4B)" }}>{vres.filas_ok}</b></span>
              <span>{tCtl("withProblem")}<b style={{ color: vres.filas_con_problema ? "var(--accent-red, #C0392B)" : undefined }}>{vres.filas_con_problema}</b></span>
              <span>{tCtl("amountArriving")}<b className="mono">{money(vres.monto_que_llega)}</b></span>
              {vres.monto_que_se_perderia > 0 && <span style={{ color: "var(--accent-red, #C0392B)" }}>{tCtl("wouldBeLost")}<b className="mono">{money(vres.monto_que_se_perderia)}</b></span>}
            </div>
            {vres.filas_con_problema > 0 && (
              <div className="fin-scroll-x" style={{ overflowX: "auto", maxHeight: 260, overflowY: "auto" }}>
                <table className="fin-table" style={{ width: "100%", minWidth: 700 }}>
                  <thead><tr><th style={{ textAlign: "left" }}>{tCtl("row")}</th><th style={{ textAlign: "left" }}>{tc("dept")}</th><th style={{ textAlign: "left" }}>{tc("account")}</th><th style={{ textAlign: "right" }}>{tCtl("amount")}</th><th style={{ textAlign: "left" }}>{tCtl("problem")}</th></tr></thead>
                  <tbody>{vres.detalle.filter(d => !d.ok).slice(0, 100).map((d, i) => {
                    const st = modeSty(d.mode, "DROP");
                    return (<tr key={i}>
                      <td style={{ textAlign: "left" }} className="mono">{d.fila}</td>
                      <td style={{ textAlign: "left", fontSize: 12 }}>{d.dept_name || d.dept_code || "—"}</td>
                      <td style={{ textAlign: "left" }} className="mono">{d.account_code}</td>
                      <td style={{ textAlign: "right" }} className="mono">{money(d.monto)}</td>
                      <td style={{ textAlign: "left", fontSize: 11.5, color: st.fg }}>{st.label} — {st.help}</td>
                    </tr>);
                  })}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 10 }}>{msg}</div>}
      {err && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 10 }}>{err}</div>}

      {data && data.avisos?.length > 0 && data.avisos.map((a, i) => (
        <div key={i} style={{ ...card, borderColor: "var(--accent-amber, #856404)", background: "rgba(133,100,4,.08)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--accent-amber, #856404)" }}>⚠ {a.titulo}</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 5, maxWidth: "88ch", lineHeight: 1.5 }}>{a.detalle}</div>
        </div>
      ))}

      {data && t && (
        <>
          {/* Semáforo de ruteo */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10, marginBottom: 16 }}>
            {[
              { k: tCtl("rowsExact"), v: t.filas_exact, c: "var(--accent-green, #1A7F4B)" },
              { k: tCtl("rowsNoDept"), v: t.filas_dept_agnostic, c: "#c9a227" },
              { k: tCtl("rowsFallback"), v: t.filas_FALLBACK, c: "#e08b3e" },
              { k: tCtl("rowsDrop"), v: t.filas_DROP, c: "var(--accent-red, #C0392B)" },
              { k: tCtl("amountLost"), v: money(t.monto_perdido_DROP), c: t.monto_perdido_DROP ? "var(--accent-red, #C0392B)" : "var(--text-secondary)" },
            ].map(x => (
              <div key={x.k} style={{ background: "var(--bg-surface)", border: "1px solid var(--border-medium)", borderRadius: 8, padding: "10px 12px" }}>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: ".04em" }}>{x.k}</div>
                <div style={{ fontSize: 19, fontWeight: 800, color: x.c, fontFamily: "var(--font-mono)" }}>{x.v}</div>
              </div>
            ))}
          </div>

          {/* Cuentas de control del P&L */}
          <div style={card}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>{tCtl("controlAccounts")}</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 10 }}>
              {Object.entries(data.pl_control).map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 10.5, color: "var(--text-secondary)" }}>{k}</div>
                  <div className="mono" style={{ fontSize: 16, fontWeight: 700, color: v < 0 ? "var(--accent-red, #C0392B)" : "var(--text-primary)" }}>{money(v)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Saldo por línea del P&L */}
          <div style={card}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>
              {tCtl("byLineTitle")} <span style={{ fontWeight: 400, color: "var(--text-secondary)", fontSize: 12 }}>{tCtl("byLineHint")}</span>
            </div>
            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
              <table className="fin-table" style={{ width: "100%", minWidth: 720 }}>
                <thead><tr>
                  <th style={{ textAlign: "left" }}>{tc("line")}</th>
                  <th style={{ textAlign: "left" }}>{tCtl("section")}</th>
                  <th style={{ textAlign: "right" }}>{tCtl("sumSources")}</th>
                  <th style={{ textAlign: "right" }}>P&amp;L</th>
                  <th style={{ textAlign: "right" }}>Δ</th>
                  <th style={{ textAlign: "center" }}>{tCtl("depts")}</th>
                </tr></thead>
                <tbody>{data.by_line.map(l => (
                  <tr key={l.line_code}>
                    <td style={{ textAlign: "left", fontWeight: 500 }}>{l.line_name}
                      <div style={{ fontSize: 10, color: "var(--text-disabled)" }}>{l.line_code}</div></td>
                    <td style={{ textAlign: "left", fontSize: 11, color: "var(--text-secondary)" }}>{l.section}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{money(l.amount_sources)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{money(l.amount_pl)}</td>
                    <td className="mono" style={{ textAlign: "right", color: l.ok ? "var(--text-disabled)" : "var(--accent-red, #C0392B)", fontWeight: l.ok ? 400 : 700 }}>{l.ok ? "—" : money(l.dif)}</td>
                    <td style={{ textAlign: "center", fontSize: 11, color: "var(--text-secondary)" }}>{l.depts.join(", ")}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
              {tCtl("deltaNote")}
            </p>
          </div>

          {/* Detalle: dónde cae cada cuenta */}
          <div style={card}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{tCtl("whereEachLands")}</div>
              <input value={q} onChange={e => setQ(e.target.value)} placeholder={tCtl("searchHint")} style={{ ...inp, minWidth: 330 }} />
              <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
                <input type="checkbox" checked={soloProblemas} onChange={e => setSoloProblemas(e.target.checked)} />
                {tCtl("onlyProblems")}
              </label>
              <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>{tCtl("rowsOf", { n: rows.length, total: data.rows.length })}</span>
            </div>
            <div className="fin-scroll-x" style={{ overflowX: "auto", maxHeight: 560, overflowY: "auto" }}>
              <table className="fin-table" style={{ width: "100%", minWidth: 860 }}>
                <thead><tr>
                  <th style={{ textAlign: "left" }}>{tCtl("origin")}</th>
                  <th style={{ textAlign: "left" }}>{tc("department")}</th>
                  <th style={{ textAlign: "left" }}>{tc("account")}</th>
                  <th style={{ textAlign: "right" }}>{tCtl("amount")}</th>
                  <th style={{ textAlign: "left" }}>{tCtl("plLine")}</th>
                  <th style={{ textAlign: "center" }}>{tCtl("routing")}</th>
                </tr></thead>
                <tbody>{rows.map((r, i) => {
                  const st = modeSty(r.mode);
                  return (
                    <tr key={i}>
                      <td style={{ textAlign: "left", fontSize: 11.5, color: "var(--text-secondary)" }}>{r.origin}</td>
                      <td style={{ textAlign: "left", fontSize: 12 }}>{r.dept_name}
                        <span style={{ color: "var(--text-disabled)", fontSize: 10.5 }}> · {r.dept_code}</span></td>
                      <td style={{ textAlign: "left", fontSize: 12 }}>
                        <span className="mono" style={{ fontWeight: 700 }}>{r.account_code}</span>
                        <span style={{ color: "var(--text-secondary)" }}> {r.account_name}</span></td>
                      <td className="mono" style={{ textAlign: "right" }}>{money(r.amount)}</td>
                      <td style={{ textAlign: "left", fontSize: 12, color: r.line_code ? "var(--text-primary)" : "var(--accent-red, #C0392B)" }}>
                        {r.line_code ? r.line_name : tCtl("notInPL")}
                        {r.mode === "FALLBACK" && r.fallback_from && (
                          <div style={{ fontSize: 10, color: "#e08b3e" }}>{tCtl("usesDeptRule", { dept: r.fallback_from })}</div>
                        )}
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <span title={st.help} style={{ fontSize: 10.5, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: st.bg, color: st.fg, whiteSpace: "nowrap" }}>{st.label}</span>
                      </td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </div>
            {data.rows.length > rows.length && (
              <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>{tCtl("showingFirst", { n: rows.length })}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
