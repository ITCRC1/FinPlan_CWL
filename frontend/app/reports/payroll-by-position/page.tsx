"use client";
import { useCallback, useEffect, useMemo, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getPayrollDepts, getPayrollByPosition,
  type Scenario, type Dept, type PayrollByPositionReport, type PayrollPositionRow,
} from "@/lib/api";

const HOTEL = HOTEL_ID;
const GOLD = "#c8a24a";
const MESES_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 10.5, textAlign: "left", padding: "8px 10px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.05em", background: "var(--bg-elevated)", whiteSpace: "nowrap" };
const thNum: CSSProperties = { ...th, textAlign: "right", textTransform: "none", letterSpacing: 0 };
const td: CSSProperties = { padding: "6px 10px", borderBottom: "1px solid var(--border-subtle)", fontSize: 12.5 };
const tdNum: CSSProperties = { padding: "6px 8px", textAlign: "right", fontSize: 12, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--border-subtle)", whiteSpace: "nowrap" };

const money = (v: number) => v === 0 ? "—" : (v < 0 ? "(" : "") + "$" +
  Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + (v < 0 ? ")" : "");

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

// Las cuatro que pidió el owner van primero: son las que se miran todos los
// meses. El resto queda a un click, no escondido.
const DESTACADOS = ["c6000_sw", "c6001_overtime", "c6010_commissions", "c6003_working_holiday"];
const GRUPO_KEY: Record<string, string> = {
  DEVENGADO: "grupoDevengado",
  CARGAS: "grupoCargas",
  BENEFICIOS: "grupoBeneficios",
};

type Vista = "resumen" | "concepto";

export default function PayrollByPositionPage() {
  const tc = useTranslations("common");
  const t = useTranslations("payrollPos");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [depts, setDepts] = useState<Dept[]>([]);
  const [dept, setDept] = useState("");
  const [data, setData] = useState<PayrollByPositionReport | null>(null);
  const [vista, setVista] = useState<Vista>("resumen");
  const [concepto, setConcepto] = useState("c6000_sw");
  const [todos, setTodos] = useState(false);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL);
        if (!all.length) { setError(tc("noScenarios", { hotel: HOTEL_ID })); setLoading(false); return; }
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch (e) { setError(e instanceof Error ? e.message : "Error"); setLoading(false); }
    })();
  }, [setScenarioId]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async (id: string, d: string) => {
    if (!id) return;
    setLoading(true); setError("");
    try {
      const [rep, ds] = await Promise.all([
        getPayrollByPosition(id, d),
        getPayrollDepts(id).catch(() => [] as Dept[]),
      ]);
      setData(rep); setDepts(ds);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(scenarioId, dept); }, [scenarioId, dept, load]);

  const filas = useMemo(() => {
    if (!data) return [];
    const t = q.trim().toLowerCase();
    if (!t) return data.rows;
    return data.rows.filter(r =>
      r.position_code.toLowerCase().includes(t) ||
      r.position_name.toLowerCase().includes(t) ||
      (r.employee_name || "").toLowerCase().includes(t));
  }, [data, q]);

  const columnas = useMemo(() => {
    if (!data) return [];
    return todos ? data.conceptos : data.conceptos.filter(c => DESTACADOS.includes(c.key));
  }, [data, todos]);

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // Dos hojas, las dos vistas de la pantalla, ambas con el depto y la búsqueda
  // ya aplicados: la de posiciones (con las columnas de concepto que estén a la
  // vista) y la del concepto elegido mes a mes.
  //
  // El CÓDIGO va como TEXTO, en su columna. Es la llave con la que se amarran
  // los reportes de planilla y tiene forma `0111-01`: si viajara como número,
  // Excel se come el cero de adelante y la llave deja de servir.
  async function bajarExcel() {
    if (!data) return;
    setError("");
    const idPos = (r: PayrollPositionRow) => r.position_code || t("sinCodigo");
    const cabPos = [
      { label: tc("code"), ancho: 12, formato: "texto" as const },
      { label: t("position"), ancho: 34, formato: "texto" as const },
      { label: tc("employee"), ancho: 26, formato: "texto" as const },
      { label: tc("dept"), ancho: 10, formato: "texto" as const },
      { label: t("ftePromCol"), ancho: 11, formato: "usd2" as const },
    ];
    const cuadros: Cuadro[] = [];
    const scn = scenarios.find(s => s.id === scenarioId);
    const sub = `${scn ? scnLabel(scn) : `${tc("year")} ${data.year}`} · ${dept || t("allDeptsLower")}`
      + `${q.trim() ? t("filtroSub", { q: q.trim() }) : ""} · USD`;

    // Hoja 1 — por posición
    {
      const fila = (r: PayrollPositionRow): FilaCuadro => ({
        label: idPos(r),
        valores: [r.position_name, r.employee_name, r.dept_code, r.fte_prom,
          ...columnas.map(c => r.anual[c.key] ?? 0),
          r.devengado, r.cargas, r.beneficios, r.costo],
      });
      const suma = (f: (r: PayrollPositionRow) => number) => filas.reduce((a, r) => a + f(r), 0);
      cuadros.push({
        titulo: t("excelTituloPos"),
        subtitulo: sub,
        hoja: t("vistaPorPosicion"),
        columnas: [...cabPos,
          ...columnas.map(c => ({ label: `${c.code} ${c.label}`, ancho: 14, formato: "usd" as const })),
          { label: t("devengado"), ancho: 14, formato: "usd" as const },
          { label: t("cargas"), ancho: 14, formato: "usd" as const },
          { label: t("beneficios"), ancho: 14, formato: "usd" as const },
          { label: t("costoTotal"), ancho: 15, formato: "usd" as const },
        ],
        filas: [
          ...filas.map(fila),
          { label: tc("total"), es_total: true,
            valores: [null, null, null, suma(r => r.fte_prom),
              ...columnas.map(c => suma(r => r.anual[c.key] ?? 0)),
              suma(r => r.devengado), suma(r => r.cargas), suma(r => r.beneficios), suma(r => r.costo)] },
        ],
      });
    }

    // Hoja 2 — el concepto elegido, mes a mes
    {
      const c = data.conceptos.find(x => x.key === concepto);
      const mes = (r: PayrollPositionRow, m: number) => (r.meses[concepto] ?? [])[m] ?? 0;
      cuadros.push({
        titulo: t("excelTituloConcepto", { concepto: c ? `${c.code} ${c.label}` : concepto }),
        subtitulo: `${sub}${c ? ` · ${GRUPO_KEY[c.grupo] ? t(GRUPO_KEY[c.grupo]) : ""}` : ""}`,
        hoja: c ? `${c.code} ${t("mesAMes")}` : t("mesAMes"),
        columnas: [...cabPos,
          ...MESES.map(m => ({ label: m, ancho: 12, formato: "usd" as const })),
          { label: tc("year"), ancho: 15, formato: "usd" as const },
        ],
        filas: [
          ...filas.map(r => ({
            label: idPos(r),
            valores: [r.position_name, r.employee_name, r.dept_code, r.fte_prom,
              ...Array.from({ length: 12 }, (_, m) => mes(r, m)), r.anual[concepto] ?? 0],
          })),
          { label: tc("total"), es_total: true,
            valores: [null, null, null, filas.reduce((a, r) => a + r.fte_prom, 0),
              ...Array.from({ length: 12 }, (_, m) => filas.reduce((a, r) => a + mes(r, m), 0)),
              filas.reduce((a, r) => a + (r.anual[concepto] ?? 0), 0)] },
        ],
      });
    }

    try {
      await bajarCuadros(`Planilla_Por_Posicion_${data.year}${dept ? "_" + dept : ""}`, cuadros);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("excelFallo"));
    }
  }

  const aud = data?.auditoria;

  return (
    <div className="pag pag-ancha" style={{ padding: "24px 20px 60px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 25, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
        </select>
        <select value={dept} onChange={e => setDept(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          <option value="">{t("allDepts")}</option>
          {depts.map(d => <option key={d.dept_code} value={d.dept_code}>{d.dept_code} — {d.dept_name}</option>)}
        </select>
        <button onClick={bajarExcel} disabled={!data}
          title={t("excelBtnTitle")}
          style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer",
            background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 6, maxWidth: "80ch" }}>
        {t.rich("intro", { b: (c) => <b>{c}</b> })}
      </p>

      {error && <div style={{ color: "var(--negative)", fontSize: 12.5, marginTop: 10 }}>{error}</div>}

      {/* ── Auditoría del código ────────────────────────────────────────── */}
      {aud && (
        <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 8, fontSize: 12.5,
          background: aud.limpio ? "rgba(38,166,154,0.10)" : "rgba(239,83,80,0.10)",
          color: aud.limpio ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${aud.limpio ? "var(--positive)" : "var(--negative)"}` }}>
          {aud.limpio ? (
            <>{t("audLimpio", { posiciones: aud.posiciones, codigos: aud.codigos_unicos })}</>
          ) : (
            <>
              {aud.duplicados.length > 0 && (
                <div>{t.rich("audDuplicados", { n: aud.duplicados.length, b: (c) => <b>{c}</b> })}{" "}
                  {aud.duplicados.slice(0, 5).map(d => d.position_code).join(", ")}
                  {aud.duplicados.length > 5 && "…"}</div>
              )}
              {aud.sin_codigo.length > 0 && (
                <div style={{ marginTop: aud.duplicados.length ? 6 : 0 }}>
                  {t.rich("audSinCodigo", { n: aud.sin_codigo.length, b: (c) => <b>{c}</b> })}{" "}
                  {aud.sin_codigo.slice(0, 4).map(s => `${s.dept_code} ${s.position_name}`).join(" · ")}
                  {aud.sin_codigo.length > 4 && "…"}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {loading && <div style={{ color: "var(--text-secondary)", padding: 40, textAlign: "center" }}>{tc("loading")}</div>}

      {data && !loading && (
        <>
          {/* ── Totales ──────────────────────────────────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginTop: 16 }}>
            {[
              [t("devengado"), data.totales.devengado],
              [t("cargasProvisiones"), data.totales.cargas],
              [t("beneficios"), data.totales.beneficios],
              [t("costoTotal"), data.totales.costo],
            ].map(([l, v], i) => (
              <div key={l as string} style={{ background: "var(--bg-elevated)", border: `1px solid ${i === 3 ? GOLD : "var(--border-medium)"}`, borderRadius: 10, padding: "12px 16px" }}>
                <div style={{ fontSize: 10.5, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>{l}</div>
                <div className="mono" style={{ fontSize: 19, fontWeight: 700, color: i === 3 ? GOLD : "inherit", marginTop: 2 }}>
                  {money(v as number)}
                </div>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 22, flexWrap: "wrap" }}>
            <button onClick={() => setVista("resumen")}
              style={{ padding: "5px 12px", fontSize: 12, borderRadius: 6, cursor: "pointer", background: vista === "resumen" ? GOLD : "transparent", color: vista === "resumen" ? "#1a1a1a" : "var(--text-secondary)", border: `1px solid ${vista === "resumen" ? GOLD : "var(--border-medium)"}`, fontWeight: vista === "resumen" ? 700 : 500 }}>
              {t("vistaPorPosicion")}
            </button>
            <button onClick={() => setVista("concepto")}
              style={{ padding: "5px 12px", fontSize: 12, borderRadius: 6, cursor: "pointer", background: vista === "concepto" ? GOLD : "transparent", color: vista === "concepto" ? "#1a1a1a" : "var(--text-secondary)", border: `1px solid ${vista === "concepto" ? GOLD : "var(--border-medium)"}`, fontWeight: vista === "concepto" ? 700 : 500 }}>
              {t("vistaConcepto")}
            </button>
            {vista === "concepto" && (
              <select value={concepto} onChange={e => setConcepto(e.target.value)}
                style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
                {data.conceptos.map(c => <option key={c.key} value={c.key}>{c.code} {c.label}</option>)}
              </select>
            )}
            {vista === "resumen" && (
              <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                <input type="checkbox" checked={todos} onChange={e => setTodos(e.target.checked)} />
                {t("los17")}
              </label>
            )}
            <input value={q} onChange={e => setQ(e.target.value)} placeholder={t("searchHint")}
              style={{ padding: "5px 10px", fontSize: 12, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", minWidth: 240, marginLeft: "auto" }} />
          </div>

          <div className="fin-sticky" style={{ marginTop: 12, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ ...th, minWidth: 86 }}>{tc("code")}</th>
                  <th style={{ ...th, minWidth: 190 }}>{t("position")}</th>
                  <th style={{ ...th, minWidth: 150 }}>{tc("employee")}</th>
                  <th style={thNum}>FTE</th>
                  {vista === "resumen" ? (
                    <>
                      {columnas.map(c => (
                        <th key={c.key} style={thNum} title={`${c.code} · ${GRUPO_KEY[c.grupo] ? t(GRUPO_KEY[c.grupo]) : ""}`}>
                          {c.label}
                        </th>
                      ))}
                      <th style={{ ...thNum, color: GOLD }}>{t("costo")}</th>
                    </>
                  ) : (
                    <>
                      {MESES.map(m => <th key={m} style={thNum}>{m}</th>)}
                      <th style={{ ...thNum, color: GOLD }}>{tc("year")}</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {filas.map(r => (
                  <tr key={r.position_id}>
                    <td style={{ ...td }}>
                      <span className="mono" style={{ color: r.position_code ? GOLD : "var(--negative)", fontWeight: 600, fontSize: 11.5 }}>
                        {r.position_code || t("sinCodigo")}
                      </span>
                    </td>
                    <td style={{ ...td, fontWeight: 500 }}>
                      {r.position_name}
                      <div style={{ fontSize: 10.5, color: "var(--text-disabled)" }}>{r.dept_code}</div>
                    </td>
                    <td style={{ ...td, color: "var(--text-secondary)" }}>{r.employee_name}</td>
                    <td style={{ ...tdNum }}>{r.fte_prom.toFixed(2)}</td>
                    {vista === "resumen" ? (
                      <>
                        {columnas.map(c => (
                          <td key={c.key} style={tdNum}>{money(r.anual[c.key] ?? 0)}</td>
                        ))}
                        <td style={{ ...tdNum, fontWeight: 700, color: GOLD }}>{money(r.costo)}</td>
                      </>
                    ) : (
                      <>
                        {(r.meses[concepto] ?? []).map((v, m) => (
                          <td key={m} style={tdNum}>{money(v)}</td>
                        ))}
                        <td style={{ ...tdNum, fontWeight: 700, color: GOLD }}>
                          {money(r.anual[concepto] ?? 0)}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
                <tr>
                  <td colSpan={3} style={{ ...td, fontWeight: 800, borderTop: "2px solid var(--border-medium)" }}>
                    {tc("total")} {q && t("filasDe", { n: filas.length, total: data.rows.length })}
                  </td>
                  <td style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)" }}>
                    {filas.reduce((a, r) => a + r.fte_prom, 0).toFixed(2)}
                  </td>
                  {vista === "resumen" ? (
                    <>
                      {columnas.map(c => (
                        <td key={c.key} style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)" }}>
                          {money(filas.reduce((a, r) => a + (r.anual[c.key] ?? 0), 0))}
                        </td>
                      ))}
                      <td style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)", color: GOLD }}>
                        {money(filas.reduce((a, r) => a + r.costo, 0))}
                      </td>
                    </>
                  ) : (
                    <>
                      {Array.from({ length: 12 }, (_, m) => (
                        <td key={m} style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)" }}>
                          {money(filas.reduce((a, r) => a + ((r.meses[concepto] ?? [])[m] ?? 0), 0))}
                        </td>
                      ))}
                      <td style={{ ...tdNum, fontWeight: 800, borderTop: "2px solid var(--border-medium)", color: GOLD }}>
                        {money(filas.reduce((a, r) => a + (r.anual[concepto] ?? 0), 0))}
                      </td>
                    </>
                  )}
                </tr>
              </tbody>
            </table>
          </div>

          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12, maxWidth: "80ch" }}>
            {t.rich("notaCodigo", { code: t("code"), b: (c) => <b>{c}</b> })}
          </p>
        </>
      )}
    </div>
  );
}
