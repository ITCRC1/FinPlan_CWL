"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getCheckbookDeptos, getCheckbookPreview, urlCheckbookExcel, authHeaders,
  subirCheckbook,
  type Scenario, type CheckbookDepto, type CheckbookPreview, type CheckbookSubida,
} from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

/**
 * Opex Checkbook Planning — el archivo de captura de gastos por departamento.
 *
 * El formato lo definió el owner y vive en `docs/CHECKBOOK_FORMATO.md`; los
 * motores que lo generan y lo leen están en `app/checkbook/` y no se tocan.
 * Esta pantalla solo elige el escenario y el departamento.
 *
 * ⚠️ El archivo baja **precargado** con lo que ese departamento ya tiene en el
 * escenario —descripciones de detalle incluidas— y con las referencias de los
 * tres años anteriores. Antes salía en blanco, y bajarlo era perder lo cargado.
 */
export default function OpexCheckbookPage() {
  const t = useTranslations("opexCheckbook");
  const tc = useTranslations("common");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scnId, setScnId] = useEscenarioDe("reports/opex-checkbook", scenarios, "budget", undefined, true);
  const [deptos, setDeptos] = useState<CheckbookDepto[]>([]);
  const [dept, setDept] = useState("");
  const [detalles, setDetalles] = useState(11);
  const [prev, setPrev] = useState<CheckbookPreview | null>(null);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  /** Escenario elegido a mano para cada año de referencia. Vacío = la regla
   *  por defecto (Forecast el anterior, Actual el previo). */
  const [refs, setRefs] = useState<Record<string, string>>({});
  /** La subida es en dos pasos: primero dice qué haría, después lo hace.
   *  Vaciar líneas es legítimo —el owner borró una fila— pero no puede pasar
   *  sin que lo vea antes. */
  const archivoRef = useRef<HTMLInputElement>(null);
  const [pendiente, setPendiente] = useState<{ f: File; r: CheckbookSubida } | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [hecho, setHecho] = useState<CheckbookSubida | null>(null);

  async function elegirArchivo(f: File | null) {
    if (!f || !dept) return;
    setMsg(null); setHecho(null); setPendiente(null); setSubiendo(true);
    try {
      setPendiente({ f, r: await subirCheckbook(scnId, dept, f, true) });
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSubiendo(false);
      if (archivoRef.current) archivoRef.current.value = "";
    }
  }

  async function confirmar() {
    if (!pendiente) return;
    setSubiendo(true); setMsg(null);
    try {
      setHecho(await subirCheckbook(scnId, dept, pendiente.f, false));
      setPendiente(null);
      verPreview();   // la pantalla vuelve a leer lo que quedó guardado
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSubiendo(false);
    }
  }

  useEffect(() => {
    getScenarios(HOTEL_ID).then(setScenarios)
      .catch(e => setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`))
      .finally(() => setCargando(false));
  }, []);

  // Los departamentos son los que TIENEN gasto en el escenario elegido. Al
  // cambiar de escenario la lista cambia, así que el departamento se re-elige.
  useEffect(() => {
    if (!scnId) return;
    setPrev(null); setRefs({});
    getCheckbookDeptos(scnId).then(r => {
      setDeptos(r.departamentos);
      setDept(d => (r.departamentos.some(x => x.dept_code === d) ? d
                    : (r.departamentos[0]?.dept_code ?? "")));
    }).catch(() => { setDeptos([]); setDept(""); });
  }, [scnId]);

  const verPreview = useCallback(async () => {
    if (!scnId || !dept) { setPrev(null); return; }
    setMsg(null);
    try { setPrev(await getCheckbookPreview(scnId, dept, detalles, refs)); }
    catch (e) { setPrev(null); setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }, [scnId, dept, detalles, refs]);
  useEffect(() => { verPreview(); }, [verPreview]);

  async function bajar() {
    if (!scnId || !dept) return;
    setMsg(null);
    try {
      const res = await fetch(urlCheckbookExcel(scnId, dept, detalles, refs), { headers: authHeaders() });
      if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
      // El nombre lo pone el servidor, sacado de la fila 1 del tab Budget. Si
      // la pantalla armara el suyo, serían dos nombres para el mismo archivo y
      // tarde o temprano dirían cosas distintas.
      const dispo = res.headers.get("Content-Disposition") ?? "";
      const delServidor = /filename="([^"]+)"/.exec(dispo)?.[1];
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = delServidor || `CHECKBOOK_${dept}_${prev?.anio_version ?? ""}.xlsx`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`); }
  }

  const sel: React.CSSProperties = {
    background: "var(--bg-input)", color: "var(--text-primary)",
    border: "1px solid var(--border-medium)", borderRadius: 5,
    padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer",
  };
  const th: React.CSSProperties = {
    textAlign: "left", padding: "7px 12px", fontSize: 10.5,
    color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase",
  };

  return (
    <div className="pag pag-media" style={{ padding: "22px 26px 48px" }}>
      <IrA esc={scnId} />
      <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
        Opex Checkbook <span style={{ color: "var(--brand)" }}>Planning</span>
      </h1>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 18px" }}>
        {t.rich("intro", {
          b: (c: React.ReactNode) => (
            <b style={{ color: "var(--text-primary)" }}>{c}</b>
          ),
        })}
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 16 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={th}>{tc("scenario")}</span>
          <select value={scnId} onChange={e => setScnId(e.target.value)} style={{ ...sel, minWidth: 200 }}>
            {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={th}>{tc("department")}</span>
          <select value={dept} onChange={e => setDept(e.target.value)} style={{ ...sel, minWidth: 300 }}>
            {deptos.map(d => (
              <option key={d.dept_code} value={d.dept_code} style={{ background: "var(--bg-input)" }}>
                {d.dept_code} · {d.dept_name} ({t("nCuentas", { n: d.cuentas })})
              </option>
            ))}
            {!deptos.length && <option value="">{t("sinDeptos")}</option>}
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={th}>{t("lineasPorCuenta")}</span>
          <select value={detalles} onChange={e => setDetalles(Number(e.target.value))} style={sel}>
            {[5, 8, 11, 15, 20].map(n => <option key={n} value={n} style={{ background: "var(--bg-input)" }}>{n}</option>)}
          </select>
        </div>
        <button onClick={bajar} disabled={!prev}
          style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5,
                   cursor: prev ? "pointer" : "default", background: "var(--positive)",
                   color: "#fff", border: "none", opacity: prev ? 1 : 0.5 }}>
          {t("bajarCheckbook")}
        </button>
        <input ref={archivoRef} type="file" accept=".xlsx" style={{ display: "none" }}
               onChange={e => elegirArchivo(e.target.files?.[0] ?? null)} />
        <button onClick={() => archivoRef.current?.click()} disabled={!prev || subiendo}
          title={t("subirAyuda")}
          style={{ padding: "7px 16px", fontSize: 12, fontWeight: 700, borderRadius: 5,
                   cursor: prev && !subiendo ? "pointer" : "default",
                   background: "var(--brand)", color: "#fff", border: "none",
                   opacity: prev && !subiendo ? 1 : 0.5 }}>
          {subiendo ? tc("loading") : t("subirCheckbook")}
        </button>
      </div>

      {pendiente && (
        <div style={{ marginBottom: 14, padding: "12px 14px", borderRadius: 8,
                      background: "var(--bg-elevated)", border: "1px solid var(--brand)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>{t("vaAHacer")}</div>
          <div style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.7 }}>
            {t("resumenLineas", {
              act: pendiente.r.lineas_actualizadas,
              nuevas: pendiente.r.lineas_nuevas,
              vaciadas: pendiente.r.lineas_vaciadas,
            })}
            {pendiente.r.lineas_en_colones > 0 && (
              <div style={{ marginTop: 6 }}>
                {t("enColones", { n: pendiente.r.lineas_en_colones })}
              </div>
            )}
            {pendiente.r.lineas_vaciadas > 0 && (
              <div style={{ marginTop: 6, color: "var(--warning)", fontWeight: 600 }}>
                {t("avisoVaciadas", { n: pendiente.r.lineas_vaciadas })}
              </div>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button onClick={confirmar} disabled={subiendo}
              style={{ padding: "6px 14px", fontSize: 12, fontWeight: 700, borderRadius: 5,
                       cursor: "pointer", background: "var(--brand)", color: "#fff", border: "none" }}>
              {t("confirmarSubida")}
            </button>
            <button onClick={() => setPendiente(null)}
              style={{ padding: "6px 14px", fontSize: 12, borderRadius: 5, cursor: "pointer",
                       background: "transparent", color: "var(--text-secondary)",
                       border: "1px solid var(--border-medium)" }}>
              {tc("cancel")}
            </button>
          </div>
        </div>
      )}

      {hecho && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 8, fontSize: 12.5,
                      background: "var(--bg-elevated)", border: "1px solid var(--positive)",
                      color: "var(--positive)" }}>
          {t("subido", {
            act: hecho.lineas_actualizadas,
            nuevas: hecho.lineas_nuevas,
            vaciadas: hecho.lineas_vaciadas,
          })}
        </div>
      )}

      {msg && (
        <div style={{ fontSize: 12.5, marginBottom: 12, padding: "8px 12px", borderRadius: 6,
                      border: "1px solid var(--negative)", color: "var(--negative)" }}>{msg}</div>
      )}
      {cargando && <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</div>}

      {prev && (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
            {[[tc("department"), prev.departamento], [tc("year"), String(prev.anio_version)],
              [t("cuentas"), String(prev.cuentas)],
              [t("filasDeCaptura"), String(prev.filas_de_captura)]].map(([l, v], i) => (
              <div key={i} style={{ flex: "1 1 0", minWidth: 150, background: "var(--bg-elevated)",
                                    border: "1px solid var(--border-medium)", borderRadius: 8, padding: "12px 14px" }}>
                <div style={{ ...th, padding: 0, marginBottom: 5 }}>{l}</div>
                <div style={{ fontSize: 15, fontWeight: 700 }}>{v}</div>
              </div>
            ))}
          </div>

          {/* ⚠️ De qué escenario salió cada año. Sin esto, «TOTAL 2026» en el
              archivo no dice si es el Final o el Working de ese año — y en
              FinPlan un mismo año tiene varios. */}
          <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)",
                        borderRadius: 8, overflow: "hidden", marginBottom: 16 }}>
            <div style={{ ...th, padding: "9px 14px", borderBottom: "1px solid var(--border-medium)" }}>
              {t("referenciasPrecargadas")}
            </div>
            {Object.keys(prev.referencias).length === 0 ? (
              <div style={{ padding: "10px 14px", fontSize: 12.5, color: "var(--warning)" }}>
                {t("sinAniosAnteriores", {
                  a1: String(prev.anio_version - 1),
                  a2: String(prev.anio_version - 2),
                })}
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <tbody>
                  {Object.entries(prev.referencias).sort((a, b) => Number(b[0]) - Number(a[0])).map(([anio, r]) => (
                    <tr key={anio} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "7px 14px", fontSize: 13, fontWeight: 700 }}>TOTAL {anio}</td>
                      <td style={{ padding: "5px 14px" }}>
                        {/* Se puede cambiar: la regla —Forecast el anterior,
                            Actual el previo— es un default, no una imposición. */}
                        <select value={r.escenario_id}
                          onChange={e => setRefs(v => ({ ...v, [anio]: e.target.value }))}
                          style={{ ...sel, minWidth: 240, fontSize: 12.5 }}>
                          {r.opciones.map(o => (
                            <option key={o.id} value={o.id} style={{ background: "var(--bg-input)" }}>{o.label}</option>
                          ))}
                        </select>
                      </td>
                      <td style={{ padding: "7px 14px", fontSize: 12.5, color: "var(--text-secondary)", textAlign: "right" }}>
                        {t("cuentasConDato", { n: r.cuentas })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)",
                        borderRadius: 8, overflow: "hidden" }}>
            <div style={{ ...th, padding: "9px 14px", borderBottom: "1px solid var(--border-medium)" }}>
              {t("cuentasDelArchivo")}
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <tbody>
                {prev.cuentas_detalle.map(c => (
                  <tr key={c.cuenta} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                    <td className="mono" style={{ padding: "5px 14px", fontSize: 12.5, width: 90 }}>{c.cuenta}</td>
                    <td style={{ padding: "5px 14px", fontSize: 12.5 }}>{c.descripcion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12, fontStyle: "italic" }}>
            {t("hojaProtegida")}
          </p>
        </>
      )}
    </div>
  );
}
