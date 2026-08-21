"use client";
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getOpsKpi, saveOpsKpi,
  type Scenario, type OpsKpiRow,
} from "@/lib/api";
import { bajarCuadros, num, type FilaCuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

const GOLD = "#c8a24a";
const COLS: { key: keyof OpsKpiRow; labelKey: string; flex: number; left?: boolean }[] = [
  { key: "kpi", labelKey: "colKpi", flex: 3, left: true },
  { key: "target", labelKey: "colTarget", flex: 1 },
  { key: "actual", labelKey: "colActual", flex: 1 },
  { key: "owner", labelKey: "colOwner", flex: 1.4, left: true },
  { key: "action", labelKey: "colAction", flex: 3, left: true },
];
const BLANK_ROWS = 3;
const blank = (): OpsKpiRow => ({ kpi: "", target: "", actual: "", owner: "", action: "" });
const blankRows = (n: number) => Array.from({ length: n }, blank);
const isEmpty = (r: OpsKpiRow) => !r.kpi.trim() && !r.target.trim() && !r.actual.trim() && !r.owner.trim() && !r.action.trim();

/**
 * Target y Actual son texto libre: acá conviven "85%", "$1,200" y "menos de 3
 * días". Solo se convierte a número lo que es un número de punta a punta — si
 * hay una palabra de por medio se devuelve `null` y la celda queda vacía, en
 * vez de inventar un 3 a partir de "menos de 3 días". El texto original nunca
 * se pierde: viaja completo en la fila de detalle.
 */
function numeroSuelto(v: string): { n: number | null; pct: boolean } {
  const m = /^([-+]?)\s*[$₡]?\s*([\d.,]+)\s*(%?)$/.exec((v || "").trim());
  if (!m) return { n: null, pct: false };
  const n = num(m[2]);
  if (n === null) return { n: null, pct: false };
  const signo = m[1] === "-" ? -1 : 1;
  return m[3] === "%" ? { n: (signo * n) / 100, pct: true } : { n: signo * n, pct: false };
}

export default function OpsKpiPage() {
  const tc = useTranslations("common");
  const t = useTranslations("opsKpi");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // La grilla se carga y se guarda contra el escenario elegido: si no se acuerda
  // de cual era, cada visita empieza a escribir en otro.
  // El `?esc=` entra acá aunque el rol sea `actual` y no `budget`: la
  // convención de atar la columna de budget existe para las pantallas que
  // COMPARAN, donde hay que elegir cuál de varias recibe. Esta tiene un solo
  // selector, así que no hay ambigüedad que resolver.
  const [scnId, setScnId] = useEscenarioDe("operation-insight/ops-kpi:actual", scenarios, "actual", undefined, true);
  const [grid, setGrid] = useState<OpsKpiRow[]>(blankRows(BLANK_ROWS));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true); setError(null); setMsg(null);
    try {
      const res = await getOpsKpi(id);
      setGrid([...res.rows, ...blankRows(BLANK_ROWS)]);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (scnId) load(scnId); }, [scnId, load]);

  function setCell(ri: number, key: keyof OpsKpiRow, v: string) {
    setGrid(prev => prev.map((row, i) => i === ri ? { ...row, [key]: v } : row));
  }
  function addRows() { setGrid(prev => [...prev, ...blankRows(3)]); }
  function delRow(ri: number) { setGrid(prev => prev.filter((_, i) => i !== ri)); }

  // ci = índice de columna (0..4 en orden de COLS)
  function paste(ri: number, ci: number, e: React.ClipboardEvent) {
    const text = e.clipboardData.getData("text");
    if (!text.includes("\t") && !text.includes("\n")) return;
    e.preventDefault();
    const cells = text.replace(/\r/g, "").split("\n").filter(l => l.length).map(l => l.split("\t"));
    setGrid(prev => {
      const next = prev.map(r => ({ ...r }));
      const need = ri + cells.length - next.length;
      for (let k = 0; k < need + 1; k++) next.push(blank());
      cells.forEach((rowc, dr) => {
        const r = ri + dr;
        rowc.forEach((cell, dc) => {
          const c = ci + dc;
          if (c >= 0 && c < COLS.length) next[r][COLS[c].key] = cell.trim();
        });
      });
      return next;
    });
  }

  async function save() {
    if (!scnId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const payload = grid.filter(r => !isEmpty(r)).map(r => ({
        kpi: r.kpi.trim(), target: r.target.trim(), actual: r.actual.trim(),
        owner: r.owner.trim(), action: r.action.trim(),
      }));
      const res = await saveOpsKpi(scnId, payload);
      const s = scenarios.find(x => x.id === scnId);
      setMsg(t("guardado", { scn: s ? scnLabel(s) : scnId, filas: res.rows_saved }));
      load(scnId);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
    finally { setSaving(false); }
  }

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // Este cuadro es de TEXTO libre en las cinco columnas, y el exportador de la
  // casa solo lleva números en las celdas de valor. Así que cada KPI baja en dos
  // filas: la de arriba con el indicador y sus Target/Actual cuando son números
  // de verdad (sumables), y debajo una línea de detalle con el texto completo
  // —Target, Actual, Responsable y Acción tal como están en pantalla— para que
  // no se pierda nada.
  async function bajarExcel() {
    setError(null);
    const llenas = grid.filter(r => !isEmpty(r));
    if (!llenas.length) { setError(t("sinFilasExport")); return; }
    const filas: FilaCuadro[] = [];
    for (const r of llenas) {
      const tg = numeroSuelto(r.target), ac = numeroSuelto(r.actual);
      filas.push({
        label: r.kpi.trim() || t("sinNombre"),
        es_total: true,
        formato: tg.pct || ac.pct ? "pct" : "num",
        valores: [tg.n, ac.n],
      });
      const detalle = [
        r.target.trim() && `${t("colTarget")}: ${r.target.trim()}`,
        r.actual.trim() && `${t("colActual")}: ${r.actual.trim()}`,
        r.owner.trim() && `${t("colOwner")}: ${r.owner.trim()}`,
        r.action.trim() && `${t("colAction")}: ${r.action.trim()}`,
      ].filter(Boolean).join(" · ");
      if (detalle) filas.push({ label: detalle, nivel: 1, valores: [null, null] });
    }
    const s = scenarios.find(x => x.id === scnId);
    try {
      await bajarCuadros("Ops_KPI", [{
        titulo: t("excelTitulo"),
        subtitulo: t("excelSubtitulo", { scn: s ? scnLabel(s) : "" }),
        hoja: "Ops KPI",
        columnas: [
          { label: t("excelColKpi"), ancho: 84, formato: "texto" },
          { label: t("colTarget"), ancho: 14, formato: "num" },
          { label: t("colActual"), ancho: 14, formato: "num" },
        ],
        filas,
      }]);
    } catch (e) { setError(e instanceof Error ? e.message : t("excelFallo")); }
  }

  const sel: React.CSSProperties = { background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", borderRadius: 6, padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer" };
  const inp: React.CSSProperties = { width: "100%", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-subtle)", borderRadius: 4, padding: "6px 8px", fontSize: 13 };
  const th: React.CSSProperties = { padding: "10px 10px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.6, textAlign: "left" };

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "20px 20px 44px" }}>
      <IrA esc={scnId} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 34, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}>
          <span style={{ color: "var(--text-primary)" }}>Ops </span><span style={{ color: "var(--brand)" }}>KPI</span>
        </h1>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10, marginTop: 6 }}>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
          <span style={{ fontSize: 14, color: "var(--text-secondary)", fontWeight: 600 }}>{t("title")}<span style={{ color: GOLD, fontWeight: 800 }}>|</span>{t("columns")}</span>
          <span style={{ height: 2, width: 60, background: "var(--border-medium)" }} />
        </div>
      </div>

      <div className="no-print" style={{ display: "flex", gap: 10, justifyContent: "center", alignItems: "flex-end", margin: "16px 0 20px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}><span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{tc("scenario")}</span><select value={scnId} onChange={e => setScnId(e.target.value)} style={sel}>{scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}</select></div>
        <button onClick={addRows} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>{t("addRows")}</button>
        <button onClick={save} disabled={saving || !scnId} style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: saving ? "default" : "pointer", background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)", opacity: saving ? 0.6 : 1 }}>{saving ? tc("saving") : `💾 ${tc("save")}`}</button>
        <button onClick={bajarExcel} title={t("excelBtnTitle")} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
        <button onClick={() => window.print()} style={{ padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>{tc("print")}</button>
      </div>

      {msg && <div style={{ color: "var(--positive)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginBottom: 8, textAlign: "center" }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", fontSize: 13, textAlign: "center" }}>{tc("loading")}</div>}

      {!loading && (
        <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", tableLayout: "fixed" }}>
            <colgroup>
              {COLS.map(c => <col key={c.key} style={{ width: `${c.flex * 14}%` }} />)}
              <col style={{ width: "36px" }} />
            </colgroup>
            <thead>
              <tr style={{ background: "var(--bg-header)" }}>
                {COLS.map(c => <th key={c.key} style={{ ...th, textAlign: c.left ? "left" : "center" }}>{t(c.labelKey)}</th>)}
                <th style={{ ...th, textAlign: "center" }}></th>
              </tr>
            </thead>
            <tbody>
              {grid.map((row, ri) => (
                <tr key={ri} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  {COLS.map((c, ci) => (
                    <td key={c.key} style={{ padding: "3px 6px" }}>
                      <input value={row[c.key]} onChange={e => setCell(ri, c.key, e.target.value)} onPaste={e => paste(ri, ci, e)} style={{ ...inp, textAlign: c.left ? "left" : "center" }} />
                    </td>
                  ))}
                  <td style={{ padding: "3px 4px", textAlign: "center" }}>
                    <button onClick={() => delRow(ri)} title={t("eliminarFila")} style={{ background: "transparent", border: "none", color: "var(--text-disabled)", cursor: "pointer", fontSize: 15, lineHeight: 1 }}>×</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="no-print" style={{ marginTop: 18, display: "flex", justifyContent: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "11px 20px", fontSize: 12.5, color: "var(--text-secondary)", maxWidth: 820 }}>
          <span style={{ width: 22, height: 22, borderRadius: "50%", background: "var(--brand)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0 }}>i</span>
          {t("hint")}
        </div>
      </div>
    </div>
  );
}
