"use client";
import { useCallback, useEffect, useMemo, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import IrA from "@/components/IrA";
import {
  getScenarios, getPLFullDetail, plFullDetailExcelUrl,
  type Scenario, type PLFullDetail, type PLDetalleFila, type PLDetalleSet,
  type ClubMembershipFila,
} from "@/lib/api";

const HOTEL = HOTEL_ID;
const GOLD = "#c8a24a";
// Los meses salen de `months.short` del catálogo; esto queda de respaldo.
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                        "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 11, textAlign: "left", padding: "8px 12px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.06em", background: "var(--bg-elevated)" };
const thNum: CSSProperties = { ...th, textAlign: "right", padding: "8px 8px", textTransform: "none", letterSpacing: 0 };
const tdNum: CSSProperties = { padding: "5px 8px", textAlign: "right", fontSize: 12, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--border-subtle)", whiteSpace: "nowrap" };

/** El cero NO se imprime — es la convención del Excel y deja respirar la grilla. */
function money(v: number): string {
  if (!v || Math.abs(v) < 0.005) return "";
  const s = "$" + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
  return v < 0 ? `(${s})` : s;
}
function pct1(v: number): string {
  if (!v) return "";
  return (v * 100).toFixed(1) + "%";
}
const rojoSiNegativo = (v: number) => (v < 0 ? { color: "var(--negative)" } : undefined);

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version))
    ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

/** El estilo de cada tipo de fila. En el Excel la jerarquía no está en la
 *  sangría (`indent = 0` en las 1,007 filas) sino en el color de relleno; acá
 *  se usan las dos cosas, que es lo que hace legible una tabla de 700 filas. */
function estiloFila(f: PLDetalleFila): CSSProperties {
  if (f.tipo === "seccion")
    return { background: "var(--bg-elevated)", fontWeight: 700, fontSize: 11,
             textTransform: "uppercase", letterSpacing: "0.06em", color: GOLD };
  if (f.tipo === "total")
    return { fontWeight: 700, background: "rgba(200,162,74,0.07)" };
  if (f.tipo === "subtotal")
    return { fontWeight: 600, borderTop: "1px solid var(--border-medium)" };
  if (f.tipo === "pct")
    return { fontSize: 11.5, color: "var(--text-secondary)", fontStyle: "italic" };
  // Estadística: noches, unidades. No es plata — se distingue para que nadie
  // lea «12,410» como dólares.
  if (f.tipo === "stat")
    return { fontSize: 11.5, color: "var(--text-secondary)" };
  return {};
}

function Filas({ filas }: { filas: PLDetalleFila[] }) {
  return (
    <>
      {filas.map(f => {
        const esPct = f.tipo === "pct";
        const esStat = f.tipo === "stat";
        const fmt = esPct ? pct1
          : esStat ? (v: number) => (v ? v.toLocaleString("en-US", { maximumFractionDigits: 1 }) : "")
          : money;
        return (
          <tr key={f.clave} style={estiloFila(f)}>
            <td style={{ padding: "5px 12px", fontSize: 12.5,
                         borderBottom: "1px solid var(--border-subtle)",
                         paddingLeft: 12 + f.nivel * 14, whiteSpace: "nowrap" }}>
              {f.cuenta && (
                <span style={{ color: "var(--text-secondary)", fontSize: 10.5,
                               fontVariantNumeric: "tabular-nums", marginRight: 8 }}>
                  {f.cuenta}
                </span>
              )}
              {f.etiqueta}
            </td>
            {f.meses.map((v, i) => (
              <td key={i} style={{ ...tdNum, ...(esPct ? {} : rojoSiNegativo(v)) }}>
                {fmt(v)}
              </td>
            ))}
            <td style={{ ...tdNum, fontWeight: 700,
                         borderLeft: "1px solid var(--border-medium)",
                         ...(esPct ? {} : rojoSiNegativo(f.total)) }}>
              {fmt(f.total)}
            </td>
          </tr>
        );
      })}
    </>
  );
}

function Cabecera({ meses, concepto, totalAnio }: {
  meses: string[]; concepto: string; totalAnio: string;
}) {
  return (
    <thead>
      <tr>
        <th style={{ ...th, minWidth: 300, position: "sticky", left: 0, zIndex: 2 }}>
          {concepto}
        </th>
        {meses.map(m => <th key={m} style={{ ...thNum, minWidth: 76 }}>{m}</th>)}
        <th style={{ ...thNum, minWidth: 92, borderLeft: "1px solid var(--border-medium)" }}>
          {totalAnio}
        </th>
      </tr>
    </thead>
  );
}

function Tabla({ children }: { children: React.ReactNode }) {
  // `fin-sticky` pega el <thead> al viewport (top: 44px). Sin un contenedor que
  // scrollee por su cuenta, la primera fila queda escondida — ya pasó dos veces.
  return (
    <div className="fin-sticky" style={{ marginTop: 10, background: "var(--bg-elevated)",
      border: "1px solid var(--border-medium)", borderRadius: 10, overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1180 }}>
        {children}
      </table>
    </div>
  );
}

function BloqueKPIs({ sets, consolidado }: { sets: PLDetalleSet[]; consolidado: PLDetalleSet | null }) {
  const t = useTranslations("plDetail");
  if (!sets.length) return null;
  const filas = [...sets, ...(consolidado ? [consolidado] : [])];
  return (
    <div className="fin-sticky" style={{ marginTop: 10, background: "var(--bg-elevated)",
      border: "1px solid var(--border-medium)", borderRadius: 10, overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 900 }}>
        <thead>
          <tr>
            <th style={{ ...th, minWidth: 200 }}>{t("roomSet")}</th>
            <th style={thNum}>{t("units")}</th>
            <th style={thNum}>{t("nightsAvailable")}</th>
            <th style={thNum}>{t("nightsOccupied")}</th>
            <th style={thNum}>{t("occupancy")}</th>
            <th style={thNum}>ADR</th>
            <th style={thNum}>RevPAR</th>
            <th style={thNum}>{t("revenue")}</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((s, i) => {
            const esTotal = consolidado != null && i === filas.length - 1;
            const disp = s.noches_disponibles.reduce((a, b) => a + b, 0);
            const ocup = s.noches_ocupadas.reduce((a, b) => a + b, 0);
            return (
              <tr key={s.clave ?? s.nombre}
                  style={esTotal ? { fontWeight: 700, background: "rgba(200,162,74,0.07)" } : undefined}>
                <td style={{ padding: "7px 12px", fontSize: 12.5,
                             borderBottom: "1px solid var(--border-subtle)" }}>
                  {s.nombre}
                  {s.sin_ocupacion && (
                    <span title={t("noOccupancyHint")}
                          style={{ marginLeft: 8, fontSize: 10.5, color: GOLD }}>
                      {t("noOccupancyLoaded")}
                    </span>
                  )}
                </td>
                <td style={tdNum}>{s.unidades || ""}</td>
                <td style={tdNum}>{disp ? Math.round(disp).toLocaleString("en-US") : ""}</td>
                <td style={tdNum}>{ocup ? Math.round(ocup).toLocaleString("en-US") : ""}</td>
                <td style={tdNum}>{pct1(s.ocupacion_anual)}</td>
                <td style={tdNum}>{money(s.adr_anual)}</td>
                <td style={tdNum}>{money(s.revpar_anual)}</td>
                <td style={tdNum}>{money(s.revenue_anual)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Socios del Club Madresal.
 *
 *  Va acá arriba, con los KPIs, y no en una línea del P&L, porque **no es
 *  dinero**: el Club vende acceso a las instalaciones y la cuota ya está en el
 *  ingreso del departamento. Esto explica de dónde sale esa cuota.
 *
 *  El total del año es el saldo de DICIEMBRE, no la suma — son socios. Sumar
 *  121 + 121 + 123… daría 1.500 donde hay 129.
 *
 *  Aparece solo si el departamento 260 está habilitado para la propiedad. El
 *  día que el Club se opere por fuera, se desmarca en Provisionamiento y esto
 *  desaparece sin tocar código. */
function BloqueClub({ filas, meses }: { filas: ClubMembershipFila[]; meses: string[] }) {
  const t = useTranslations("plDetail");
  const hayDatos = filas.some(f => f.meses.some(v => v) || f.total_anio);
  return (
    <>
      <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 22, marginBottom: 0 }}>
        {t("clubTitle")}
      </h2>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0", maxWidth: "78ch" }}>
        {t("clubHint")}
      </p>
      <div className="fin-sticky" style={{ marginTop: 8, background: "var(--bg-elevated)",
        border: "1px solid var(--border-medium)", borderRadius: 10, overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1180 }}>
          <thead>
            <tr>
              <th style={{ ...th, minWidth: 300 }}>{t("concept")}</th>
              {meses.map(m => <th key={m} style={{ ...thNum, minWidth: 76 }}>{m}</th>)}
              <th style={{ ...thNum, minWidth: 92, borderLeft: "1px solid var(--border-medium)" }}>
                {t("totalYear")}
              </th>
            </tr>
          </thead>
          <tbody>
            {!hayDatos && (
              <tr><td colSpan={14} style={{ padding: "10px 12px", fontSize: 12.5,
                color: "var(--text-secondary)" }}>{t("clubNoData")}</td></tr>
            )}
            {hayDatos && filas.map((f, i) => (
              <tr key={f.campo} style={i === 0 ? { fontWeight: 700 } : undefined}>
                <td style={{ padding: "5px 12px", fontSize: 12.5,
                  borderBottom: "1px solid var(--border-subtle)",
                  paddingLeft: i === 0 ? 12 : 26 }}>{f.etiqueta}</td>
                {f.meses.map((v, j) => (
                  <td key={j} style={tdNum}>{v ? v.toLocaleString("en-US") : ""}</td>
                ))}
                <td style={{ ...tdNum, fontWeight: 700,
                  borderLeft: "1px solid var(--border-medium)" }}>
                  {f.total_anio ? f.total_anio.toLocaleString("en-US") : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 11.5, color: GOLD, marginTop: 6 }}>{t("clubTotalNote")}</p>
    </>
  );
}

export default function PLFullDetailPage() {
  const hotel = useHotel();
  const t  = useTranslations("plDetail");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [data, setData] = useState<PLFullDetail | null>(null);
  const [vacios, setVacios] = useState(false);
  const [abiertos, setAbiertos] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL);
        if (!all.length) { setError(tc("noScenarios", { hotel: hotel.id })); setLoading(false); return; }
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error"); setLoading(false);
      }
    })();
  }, [setScenarioId]);

  const load = useCallback(async (id: string, v: boolean) => {
    if (!id) return;
    setLoading(true); setError("");
    try { setData(await getPLFullDetail(id, v)); }
    catch (e) { setError(e instanceof Error ? e.message : "Error"); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(scenarioId, vacios); }, [scenarioId, vacios, load]);

  // Los bloques arrancan colapsados: son 700 filas. En el Excel las 265 filas
  // ocultas eran departamentos enteros colapsados que SEGUÍAN sumando; acá pasa
  // lo mismo — colapsar es de la vista, el total ya está calculado.
  // Rooms y sus tres sets arrancan ABIERTOS: el owner los pidió fijos, es la
  // apertura que se mira siempre. Los demás siguen colapsados — son 700 filas.
  useEffect(() => {
    if (!data) return;
    setAbiertos(a => ({
      ...Object.fromEntries(data.bloques
        .filter(b => b.es_apertura || b.apertura_de || b.clave === "0110")
        .map(b => [b.clave, true])),
      ...a,
    }));
  }, [data]);

  const toggle = (k: string) => setAbiertos(a => ({ ...a, [k]: !a[k] }));
  const todos = (on: boolean) => setAbiertos(
    Object.fromEntries((data?.bloques ?? []).map(b => [b.clave, on])));

  const cuadre = data?.cuadre;
  const semaforo = useMemo(() => {
    if (!cuadre) return null;
    if (cuadre.ok) return { color: "var(--positive)", texto: t("tiesOk") };
    return { color: "var(--negative)", texto: t("tiesFail") };
  }, [cuadre, t]);

  return (
    <div className="pag pag-ancha" style={{ padding: "24px 20px 60px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
        </select>
        {scenarioId && (
          <a href={plFullDetailExcelUrl(scenarioId, vacios)}
             title={t("excelHint")}
             style={{ padding: "5px 12px", fontSize: 12.5, borderRadius: 6, textDecoration: "none",
               background: "var(--bg-elevated)", color: "var(--text-primary)",
               border: `1px solid ${GOLD}` }}>
            ⬇ Excel
          </a>
        )}
      </div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6, maxWidth: "78ch" }}>
        {t("intro")}
      </p>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8, maxWidth: "78ch", borderLeft: `3px solid ${GOLD}`, paddingLeft: 12 }}>
        {t("auditNote")}
      </p>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginTop: 12 }}>{error}</div>}
      {loading && <div style={{ color: "var(--text-secondary)", padding: 40, textAlign: "center" }}>{tc("loading")}</div>}

      {data && !loading && (
        <>
          {semaforo && cuadre && (
            <div style={{ marginTop: 14, padding: "10px 14px", borderRadius: 8, fontSize: 12.5,
              border: `1px solid ${semaforo.color}`, color: semaforo.color,
              display: "flex", gap: 18, flexWrap: "wrap", alignItems: "center" }}>
              <b>{semaforo.texto}</b>
              <span style={{ color: "var(--text-secondary)" }}>
                {t("revenues")}: {t("detail")} {money(cuadre.ingresos_detalle)} vs {t("summary")} {money(cuadre.ingresos_pl)}
                {cuadre.ingreso_por_cuenta ? ` · Δ ${money(cuadre.dif_ingresos) || "$0"}` : ` · ${t("noAccountBreakdown")}`}
              </span>
              <span style={{ color: "var(--text-secondary)" }}>
                {t("expenses")}: {t("detail")} {money(cuadre.gastos_detalle)} vs {t("summary")} {money(cuadre.gastos_pl)} · Δ {money(cuadre.dif_gastos) || "$0"}
              </span>
              <span style={{ color: "var(--text-secondary)" }}>
                GOP {money(cuadre.gop_pl)} · {t("net")} {money(cuadre.net_pl)}
              </span>
            </div>
          )}

          {data.avisos.map((a, i) => (
            <div key={i} style={{ marginTop: 10, padding: "10px 14px", borderRadius: 8, fontSize: 12.5,
              background: "rgba(200,162,74,0.08)", border: `1px solid ${GOLD}`, color: "var(--text-primary)", maxWidth: "92ch" }}>
              {a}
            </div>
          ))}

          {data.kpis.disponible && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 26, marginBottom: 0 }}>
                {t("roomsBySet")}
              </h2>
              <BloqueKPIs sets={data.kpis.sets} consolidado={data.kpis.consolidado} />
            </>
          )}

          {data.club && <BloqueClub filas={data.club.filas} meses={MESES} />}

          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 26, marginBottom: 0 }}>{t("summaryBlock")}</h2>
          <Tabla>
            <Cabecera meses={MESES} concepto={tc("concept")} totalAnio={t("totalYear")} />
            <tbody><Filas filas={data.resumen} /></tbody>
          </Tabla>

          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 26, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{t("byDepartment")}</h2>
            <button onClick={() => todos(true)} style={btn}>{tc("openAll")}</button>
            <button onClick={() => todos(false)} style={btn}>{tc("closeAll")}</button>
            <label style={{ fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
              title={t("zerosHint")}>
              <input type="checkbox" checked={vacios} onChange={e => setVacios(e.target.checked)} />
              {tc("showZeros")}
            </label>
          </div>

          {data.bloques.map(b => (
            // Los sets de Rooms van sangrados: son el consolidado de arriba
            // abierto, no departamentos más. Sin la sangría, cuatro tarjetas
            // iguales invitan a sumarlas — y eso contaría Rooms dos veces.
            <div key={b.clave} style={{ marginTop: b.es_apertura ? 6 : 12,
                                        marginLeft: b.es_apertura ? 26 : 0 }}>
              <button onClick={() => toggle(b.clave)}
                style={{ display: "flex", alignItems: "center", gap: 10, width: "100%",
                  padding: b.es_apertura ? "7px 14px" : "9px 14px", borderRadius: 8,
                  cursor: "pointer", textAlign: "left",
                  background: b.es_apertura ? "transparent" : "var(--bg-elevated)",
                  border: `1px ${b.es_apertura ? "dashed" : "solid"} var(--border-medium)`,
                  color: "var(--text-primary)",
                  fontSize: b.es_apertura ? 12.5 : 13.5, fontWeight: 700 }}>
                <span style={{ color: GOLD, width: 12 }}>{abiertos[b.clave] ? "▾" : "▸"}</span>
                <span style={{ color: "var(--text-secondary)", fontSize: 11,
                               fontVariantNumeric: "tabular-nums" }}>{b.dept_code}</span>
                {b.titulo}
                {b.es_apertura && (
                  <span style={{ fontSize: 10, color: "var(--text-secondary)", fontWeight: 400,
                                 border: "1px dashed var(--border-medium)", borderRadius: 4, padding: "1px 6px" }}>
                    {t("breakdownChip")}
                  </span>
                )}
                {b.tipo === "OVERHEAD" && (
                  <span style={{ fontSize: 10, color: "var(--text-secondary)", fontWeight: 400,
                                 border: "1px solid var(--border-medium)", borderRadius: 4, padding: "1px 6px" }}>
                    {t("overhead")}
                  </span>
                )}
                <span style={{ marginLeft: "auto", display: "flex", gap: 18, fontWeight: 400,
                               fontSize: 12, color: "var(--text-secondary)",
                               fontVariantNumeric: "tabular-nums" }}>
                  <span>{t("revenue")} {money(b.ingreso_anual) || "—"}</span>
                  <span>{t("expenses")} {money(b.gasto_anual) || "—"}</span>
                  <span style={{ ...rojoSiNegativo(b.utilidad_anual), fontWeight: 700 }}>
                    {t("profit")} {money(b.utilidad_anual) || "—"}
                  </span>
                </span>
              </button>
              {abiertos[b.clave] && (
                <Tabla>
                  <Cabecera meses={MESES} concepto={tc("concept")} totalAnio={t("totalYear")} />
                  <tbody><Filas filas={b.filas} /></tbody>
                </Tabla>
              )}
            </div>
          ))}

          {data.propiedad.length > 0 && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 26, marginBottom: 0 }}>
                {t("propertyExpenses")}
              </h2>
              <Tabla>
                <Cabecera meses={MESES} concepto={tc("concept")} totalAnio={t("totalYear")} />
                <tbody><Filas filas={data.propiedad} /></tbody>
              </Tabla>
            </>
          )}
        </>
      )}
    </div>
  );
}

const btn: CSSProperties = {
  padding: "4px 12px", fontSize: 12, borderRadius: 6, cursor: "pointer",
  background: "transparent", color: "var(--text-secondary)",
  border: "1px solid var(--border-medium)",
};
