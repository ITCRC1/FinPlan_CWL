"use client";
/**
 * Cuentas del mayor por mes — el reporte de conciliación.
 *
 * Owner, 2026-11-05, mostrando el mismo reporte de otra app: *«que lo pongas
 * en el tab Reports al final para poder conciliar los resultados… que traiga
 * todas las cuentas… y que exista un proceso de validación interno para que
 * pegue con los reportes»*.
 *
 * ⚠️ **El signo lo decide el backend.** Acá no se invierte nada: los montos
 * llegan con el ingreso ya en negativo, porque la grilla, el resumen, el Excel
 * y la validación tienen que sumar lo mismo y cuatro lugares invirtiendo por
 * su cuenta es la forma conocida de que el cuarto no coincida.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getScenarios, getGl, getGlValidacion,
  type Scenario, type GlRespuesta, type GlValidacion, type GlRow,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID, hotelShort } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import IrA from "@/components/IrA";

const TYPE_LABEL: Record<string, string> = {
  ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast",
};
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version))
    ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

/** Negativo entre paréntesis, como lo escribe la contabilidad. */
const usd = (n: number) => {
  if (!n) return "—";
  const s = "$" + Math.abs(n).toLocaleString("en-US",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
};

type Tab = "detalle" | "resumen" | "validacion";

export default function GlReportPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("gl");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useEscenarioDe(
    "reports/gl:actual", scenarios, "actual", undefined, true);
  const [tab, setTab] = useState<Tab>("detalle");
  const [data, setData] = useState<GlRespuesta | null>(null);
  const [val, setVal] = useState<GlValidacion | null>(null);
  const [busca, setBusca] = useState("");
  const [cat, setCat] = useState("");
  const [loading, setLoading] = useState(true);
  const [valLoading, setValLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try { setScenarios(await getScenarios(HOTEL_ID)); }
      catch (e) { setError(e instanceof Error ? e.message : "Error"); }
      finally { setLoading(false); }
    })();
  }, []);

  useEffect(() => {
    if (!scenarioId) return;
    setLoading(true); setError(null); setVal(null);
    getGl(scenarioId)
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setLoading(false));
  }, [scenarioId]);

  // La validación se pide sólo cuando se abre su pestaña: calcula el P&L de
  // los doce meses y no tiene por qué pagarse al mirar el detalle.
  useEffect(() => {
    if (tab !== "validacion" || !scenarioId || val || valLoading) return;
    setValLoading(true);
    getGlValidacion(scenarioId)
      .then(setVal)
      .catch(e => setError(e instanceof Error ? e.message : "Error"))
      .finally(() => setValLoading(false));
  }, [tab, scenarioId, val, valLoading]);

  const categorias = useMemo(
    () => [...new Set((data?.rows ?? []).map(r => r.categoria))].sort(),
    [data]);

  const filas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (data?.rows ?? []).filter(r =>
      (!cat || r.categoria === cat)
      && (!q || [r.dept_code, r.dept_name, r.account_code, r.account_name,
                 r.pl_line_code, r.pl_line_name, r.codigo_corporativo]
            .some(v => (v || "").toLowerCase().includes(q))));
  }, [data, busca, cat]);

  const exportExcel = useCallback(async () => {
    if (!data) return;
    // ⚠️ **TODAS las filas, no las filtradas.** El Excel es el papel de la
    // conciliación: si sale con el filtro puesto, le faltan cuentas y la suma
    // ya no da la utilidad — o sea que deja de servir para lo único que sirve.
    // El buscador y el filtro de categoría son para mirar en pantalla.
    const detalle: FilaCuadro[] = (data.rows ?? []).map(r => ({
      label: `${r.dept_code} ${r.dept_name} · ${r.account_code} ${r.account_name}`,
      nivel: 0,
      valores: [...r.meses, r.total],
    }));
    const resumen: FilaCuadro[] = data.resumen.map(f => ({
      label: t(`cat.${f.categoria}`) + (f.suma ? "" : ` (${t("noSuma")})`),
      nivel: 0, es_total: f.categoria === "NET",
      valores: [...f.meses, f.total],
    }));
    const columnas = [
      { label: t("colAccount"), ancho: 52, formato: "texto" as const },
      ...MESES.map(m => ({ label: m, ancho: 14, formato: "usd" as const })),
      { label: tc("annual"), ancho: 16, formato: "usd" as const },
    ];
    try {
      await bajarCuadros(`gl_por_mes_${data.meta.year}`, [
        { titulo: `${t("title")} — ${hotelShort()} ${data.meta.year}`,
          subtitulo: t("signNote"), hoja: t("tabDetail"),
          columnas, filas: detalle },
        { titulo: `${t("title")} — ${t("tabSummary")}`,
          subtitulo: t("signNote"), hoja: t("tabSummary"),
          columnas, filas: resumen },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el Excel");
    }
  }, [data, MESES, t, tc]);

  const td: React.CSSProperties = {
    textAlign: "right", padding: "4px 10px", fontSize: 11.5,
    fontFamily: "var(--font-mono)", whiteSpace: "nowrap",
  };
  const th: React.CSSProperties = {
    textAlign: "right", padding: "6px 10px", fontSize: 11,
    whiteSpace: "nowrap",
  };

  const meta = data?.meta;

  return (
    <div className="pag pag-lectura" style={{ padding: "24px 28px 64px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "flex-start", marginBottom: 14,
                    flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>
            {t("title")} — {hotel.corto}{meta ? ` ${meta.year}` : ""}
          </h1>
          <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            {t("subtitle")}
          </p>
        </div>
        <button onClick={exportExcel} disabled={!data} title={t("excelHint")}
          style={{ padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                   background: "var(--accent-excel)", color: "#fff",
                   border: "none", fontSize: 13, fontWeight: 600 }}>
          ⬇ Excel
        </button>
      </div>

      <div style={{ display: "flex", gap: 14, alignItems: "flex-end",
                    marginBottom: 14, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>
            {tc("scenario")}
          </div>
          <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
                  className="fin-input" style={{ minWidth: 220 }}>
            {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
          </select>
        </div>
        {tab === "detalle" && (
          <>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>
                {t("search")}
              </div>
              <input value={busca} onChange={e => setBusca(e.target.value)}
                     placeholder={t("searchPlaceholder")} className="fin-input"
                     style={{ minWidth: 280, textAlign: "left" }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>
                {t("category")}
              </div>
              <select value={cat} onChange={e => setCat(e.target.value)}
                      className="fin-input">
                <option value="">{t("allCategories")}</option>
                {categorias.map(c => <option key={c} value={c}>{t(`cat.${c}`)}</option>)}
              </select>
            </div>
          </>
        )}
      </div>

      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border-medium)",
                    marginBottom: 12 }}>
        {(["detalle", "resumen", "validacion"] as Tab[]).map(k => (
          <button key={k} onClick={() => setTab(k)}
            style={{ padding: "7px 16px", fontSize: 12.5, cursor: "pointer",
                     background: tab === k ? "var(--bg-elevated)" : "transparent",
                     color: tab === k ? "var(--text-primary)" : "var(--text-secondary)",
                     border: "none",
                     borderBottom: tab === k ? "2px solid var(--brand)" : "2px solid transparent",
                     fontWeight: tab === k ? 600 : 400 }}>
            {k === "detalle" ? t("tabDetail")
              : k === "resumen" ? t("tabSummary") : t("tabValidation")}
          </button>
        ))}
      </div>

      {/* La convención de signo, dicha donde se lee. Sin esto un número entre
          paréntesis se interpreta al revés y el reporte miente sin fallar. */}
      {meta && (
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 10 }}>
          <b>{meta.cuentas}</b> {t("accounts")} · {meta.filas} {t("rows")} · {t("signNote")}
        </p>
      )}

      {meta && !meta.completo && (
        <div style={{ fontSize: 12, color: "var(--accent-amber, #856404)",
                      background: "rgba(245,158,11,0.08)",
                      border: "1px solid var(--accent-amber, #856404)",
                      borderRadius: 4, padding: "9px 13px", marginBottom: 12 }}>
          ⚠ {t("incomplete")}
        </div>
      )}

      {error && <div style={{ color: "var(--negative, #C0392B)", fontSize: 13,
                              marginBottom: 8 }}>{error}</div>}

      {loading ? <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
        : !data ? null : tab === "detalle" ? (
        <div className="fin-scroll-x fin-sticky" style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1500 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border-medium)",
                           color: "var(--text-secondary)" }}>
                <th style={{ ...th, textAlign: "left" }}>{t("colDept")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("colDeptName")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("colGl")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("colGlDesc")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("colPlLine")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("colCorporate")}</th>
                <th style={{ ...th, textAlign: "left" }}>{t("colCategory")}</th>
                {MESES.map(m => <th key={m} style={th}>{m}</th>)}
                <th style={{ ...th, fontWeight: 700 }}>{tc("annual")}</th>
              </tr>
            </thead>
            <tbody>
              {filas.map(r => <FilaGl key={`${r.dept_code}|${r.account_code}|${r.outlet}`}
                                      r={r} td={td} t={t} />)}
              {!filas.length && (
                <tr><td colSpan={20} style={{ padding: 20, fontSize: 12,
                        color: "var(--text-secondary)" }}>{t("noRows")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : tab === "resumen" ? (
        <div className="fin-scroll-x fin-sticky" style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1100 }}>
            <thead>
              <tr style={{ borderBottom: "2px solid var(--border-medium)",
                           color: "var(--text-secondary)" }}>
                <th style={{ ...th, textAlign: "left" }}>{t("colCategory")}</th>
                {MESES.map(m => <th key={m} style={th}>{m}</th>)}
                <th style={{ ...th, fontWeight: 700 }}>{tc("annual")}</th>
              </tr>
            </thead>
            <tbody>
              {data.resumen.map(f => (
                <tr key={f.categoria}
                    style={{ borderTop: f.categoria === "NET"
                      ? "2px solid var(--border-medium)" : "1px solid var(--border-subtle)",
                      fontWeight: f.categoria === "NET" ? 700 : 400 }}>
                  <td style={{ padding: "5px 10px", fontSize: 12 }}>
                    {t(`cat.${f.categoria}`)}
                    {!f.suma && <span style={{ color: "var(--text-disabled)",
                                               fontSize: 10, marginLeft: 6 }}>
                      {t("noSuma")}</span>}
                  </td>
                  {f.meses.map((v, i) => <td key={i} style={td}>{usd(v)}</td>)}
                  <td style={{ ...td, fontWeight: 700 }}>{usd(f.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 10 }}>
            {t("netIsProfit")}
          </p>
        </div>
      ) : (
        <Validacion v={val} cargando={valLoading} t={t} tc={tc} />
      )}
    </div>
  );
}


function FilaGl({ r, td, t }: {
  r: GlRow; td: React.CSSProperties; t: ReturnType<typeof useTranslations>;
}) {
  const izq: React.CSSProperties = { padding: "4px 10px", fontSize: 11.5,
                                     whiteSpace: "nowrap" };
  // Una cuenta que no llega al P&L no puede verse igual que una que sí llega.
  const roja = r.mapeo === "DROP";
  return (
    <tr style={{ borderTop: "1px solid var(--border-subtle)",
                 background: roja ? "rgba(239,83,80,0.07)" : undefined }}>
      <td style={izq}>{r.dept_code}</td>
      <td style={{ ...izq, color: "var(--text-secondary)" }}>{r.dept_name}</td>
      <td style={{ ...izq, fontWeight: 600 }}>{r.account_code}</td>
      <td style={izq}>{r.account_name || "—"}</td>
      <td style={{ ...izq, color: roja ? "var(--negative)" : "var(--text-secondary)" }}>
        {r.pl_line_code
          ? <>{r.pl_line_code}{r.pl_line_name ? ` · ${r.pl_line_name}` : ""}</>
          : t("noMapping")}
        {r.mapeo === "FALLBACK" && (
          <span title={t("fallbackHint")} style={{ marginLeft: 5,
                color: "var(--accent-amber, #856404)" }}>⚠</span>
        )}
        {r.mapeo_cambio && (
          <span title={t("changedHint")} style={{ marginLeft: 5,
                color: "var(--text-disabled)" }}>⟳</span>
        )}
      </td>
      <td style={{ ...izq, color: "var(--text-disabled)" }}>
        {r.codigo_corporativo || "—"}
      </td>
      <td style={{ ...izq, color: "var(--text-secondary)" }}>
        {t(`cat.${r.categoria}`)}
        {r.clase_discrepa && (
          <span title={t("classHint")} style={{ marginLeft: 5,
                color: "var(--text-disabled)" }}>※</span>
        )}
      </td>
      {r.meses.map((v, i) => <td key={i} style={td}>{usd(v)}</td>)}
      <td style={{ ...td, fontWeight: 700 }}>{usd(r.total)}</td>
    </tr>
  );
}


function Validacion({ v, cargando, t, tc }: {
  v: GlValidacion | null; cargando: boolean;
  t: ReturnType<typeof useTranslations>; tc: ReturnType<typeof useTranslations>;
}) {
  if (cargando || !v) {
    return <div style={{ color: "var(--text-secondary)", padding: 24 }}>
      {tc("loading")}</div>;
  }
  const ok = v.cuadra === true;
  const naplica = v.cuadra === null;
  const color = naplica ? "var(--text-secondary)"
    : ok ? "var(--positive)" : "var(--negative)";

  const bloques: { clave: string; filas: typeof v.sin_mapeo; total?: number;
                   grave: boolean }[] = [
    { clave: "sinMapeo", filas: v.sin_mapeo, total: v.sin_mapeo_total, grave: true },
    { clave: "porDescarte", filas: v.por_descarte, total: v.por_descarte_total, grave: false },
    { clave: "claseDiscrepa", filas: v.clase_discrepa, total: v.clase_discrepa_total, grave: false },
    { clave: "mapeoCambio", filas: v.mapeo_cambio, grave: false },
  ];

  return (
    <div>
      <div style={{ border: `1px solid ${color}`, borderRadius: 6,
                    padding: "14px 18px", marginBottom: 18,
                    background: naplica ? "var(--bg-elevated)"
                      : ok ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.07)" }}>
        <div style={{ fontSize: 15, fontWeight: 700, color, marginBottom: 6 }}>
          {naplica ? t("notApplicable") : ok ? t("ties") : t("doesNotTie")}
        </div>
        {v.motivo && (
          <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>
            {t(`motivo.${v.motivo}`, { mes: v.motivo_mes })}
          </p>
        )}
        <table style={{ fontSize: 12.5, fontFamily: "var(--font-mono)" }}>
          <tbody>
            <tr><td style={{ paddingRight: 18 }}>{t("sumOfRows")}</td>
                <td style={{ textAlign: "right" }}>{usd(v.total_reporte)}</td></tr>
            <tr><td style={{ paddingRight: 18 }}>{t("minusNetProfit")}</td>
                <td style={{ textAlign: "right" }}>{usd(v.esperado)}</td></tr>
            <tr style={{ fontWeight: 700, borderTop: "1px solid var(--border-medium)" }}>
              <td style={{ paddingRight: 18 }}>{t("difference")}</td>
              <td style={{ textAlign: "right", color }}>{usd(v.diferencia)}</td></tr>
          </tbody>
        </table>
      </div>

      {bloques.map(b => b.filas.length > 0 && (
        <div key={b.clave} style={{ marginBottom: 18 }}>
          <h2 style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 2,
                       color: b.grave ? "var(--negative)" : "var(--text-primary)" }}>
            {t(`${b.clave}.title`)} — {b.filas.length}
            {b.total !== undefined && ` · ${usd(b.total)}`}
          </h2>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 6 }}>
            {t(`${b.clave}.why`)}
          </p>
          <table style={{ borderCollapse: "collapse", fontSize: 11.5 }}>
            <tbody>
              {b.filas.map(f => (
                <tr key={`${f.dept_code}|${f.account_code}`}
                    style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "3px 10px" }}>{f.dept_code}</td>
                  <td style={{ padding: "3px 10px", fontWeight: 600 }}>{f.account_code}</td>
                  <td style={{ padding: "3px 10px" }}>{f.account_name || "—"}</td>
                  <td style={{ padding: "3px 10px", color: "var(--text-secondary)" }}>
                    {f.pl_line_code || ""}</td>
                  <td style={{ padding: "3px 10px", textAlign: "right",
                               fontFamily: "var(--font-mono)" }}>{usd(f.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {v.aplica_igualdad && v.por_linea.length > 0 && (
        <div>
          <h2 style={{ fontSize: 13.5, fontWeight: 700, marginBottom: 2 }}>
            {t("porLinea.title")} — {v.por_linea.length}
          </h2>
          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 6 }}>
            {t("porLinea.why")}
          </p>
          <table style={{ borderCollapse: "collapse", fontSize: 11.5 }}>
            <thead>
              <tr style={{ color: "var(--text-secondary)" }}>
                <th style={{ textAlign: "left", padding: "3px 10px" }}>{t("colPlLine")}</th>
                <th style={{ textAlign: "right", padding: "3px 10px" }}>{t("fromGl")}</th>
                <th style={{ textAlign: "right", padding: "3px 10px" }}>{t("fromPl")}</th>
                <th style={{ textAlign: "right", padding: "3px 10px" }}>{t("difference")}</th>
              </tr>
            </thead>
            <tbody>
              {v.por_linea.map(l => (
                <tr key={l.pl_line_code} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "3px 10px" }}>{l.pl_line_code}</td>
                  <td style={{ padding: "3px 10px", textAlign: "right",
                               fontFamily: "var(--font-mono)" }}>{usd(l.gl)}</td>
                  <td style={{ padding: "3px 10px", textAlign: "right",
                               fontFamily: "var(--font-mono)" }}>{usd(l.pl)}</td>
                  <td style={{ padding: "3px 10px", textAlign: "right",
                               fontFamily: "var(--font-mono)",
                               color: "var(--negative)" }}>{usd(l.diferencia)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
