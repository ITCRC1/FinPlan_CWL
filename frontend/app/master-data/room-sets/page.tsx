"use client";
import { useCallback, useEffect, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import RecalcButton from "@/components/RecalcButton";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getRoomTypes, updateRoomType, getRoomDepartments, getScenarios,
  getRoomsAllocConfig, saveRoomsAllocConfig,
  type RoomType, type RoomDepartment, type Scenario, type RoomsAllocConfig,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const HOTEL = HOTEL_ID;
const GOLD = "#c8a24a";
const MESES_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 11, textAlign: "left", padding: "10px 12px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.06em" };
const td: CSSProperties = { padding: "9px 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 13 };
const thNum: CSSProperties = { ...th, textAlign: "right", padding: "8px 6px", textTransform: "none", letterSpacing: 0 };
const tdNum: CSSProperties = { padding: "5px 6px", textAlign: "right", fontSize: 12, fontVariantNumeric: "tabular-nums", borderBottom: "1px solid var(--border-subtle)", whiteSpace: "nowrap" };

const money = (v: number) => (v < 0 ? "(" : "") + "$" +
  Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + (v < 0 ? ")" : "");

const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

export default function RoomSetsPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const t = useTranslations("roomSets");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [rows, setRows] = useState<RoomType[]>([]);
  const [sets, setSets] = useState<RoomDepartment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [cfg, setCfg] = useState<RoomsAllocConfig | null>(null);
  const [pct, setPct] = useState<Record<string, number[]>>({});   // dept → 12 % (0-100)
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [rt, dp] = await Promise.all([getRoomTypes(HOTEL), getRoomDepartments(HOTEL)]);
      setRows(rt.room_types); setSets(dp);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, [tc]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL);
        if (!all.length) return;
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch { /* la parte de arriba funciona sin escenario */ }
    })();
  }, [setScenarioId]);

  const loadCfg = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const c = await getRoomsAllocConfig(id);
      setCfg(c);
      // En pantalla se escribe 30, en la base vive 0.30. Mezclarlos es la forma
      // clásica de repartir cien veces de más, así que la conversión pasa acá y
      // en un solo lugar.
      setPct(Object.fromEntries(c.rows.map(r => [
        r.dept_code, r.pct_monthly.map(v => Math.round(v * 10000) / 100),
      ])));
      setDirty(false);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
  }, [tc]);

  useEffect(() => { loadCfg(scenarioId); }, [scenarioId, loadCfg]);

  async function asignar(id: string, dept_code: string) {
    setMsg(""); setError("");
    setRows(rs => rs.map(r => (r.id === id ? { ...r, dept_code } : r)));
    try {
      await updateRoomType(HOTEL, id, { dept_code });
      setMsg(t("saved"));
    } catch (e) {
      setError(e instanceof Error ? t("saveFailed", { detalle: e.message }) : tc("error"));
      load();
    }
  }

  function setPctMes(dept: string, mes: number, valor: number) {
    setPct(p => {
      const fila = [...(p[dept] ?? Array(12).fill(0))];
      fila[mes] = valor;
      return { ...p, [dept]: fila };
    });
    setDirty(true);
  }

  /** Copia el valor de enero a los doce meses: casi siempre el reparto es
      parejo y escribirlo doce veces invita a equivocarse en uno. */
  function replicarEnero(dept: string) {
    setPct(p => ({ ...p, [dept]: Array(12).fill((p[dept] ?? [0])[0] ?? 0) }));
    setDirty(true);
  }

  async function guardar() {
    setSaving(true); setMsg(""); setError("");
    try {
      await saveRoomsAllocConfig(scenarioId, Object.entries(pct).map(([dept_code, v]) => ({
        dept_code, pct_monthly: v.map(x => (x || 0) / 100), active: true,
      })));
      setMsg(t("pctSaved"));
      await loadCfg(scenarioId);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setSaving(false); }
  }

  // El set por defecto es Rooms: una categoría sin asignar se comporta como
  // siempre y su costo se queda en el departamento de habitaciones.
  const setDe = (r: RoomType) => r.dept_code || "0110";
  const porSet = sets.map(s => ({
    ...s,
    tipos: rows.filter(r => setDe(r) === s.dept_code),
    unidades: rows.filter(r => setDe(r) === s.dept_code).reduce((a, r) => a + (r.units || 0), 0),
  }));

  const destinos = cfg?.rows ?? [];
  const totalMes = (m: number) => destinos.reduce((a, d) => a + ((pct[d.dept_code] ?? [])[m] ?? 0), 0);
  const montoMes = (dept: string, m: number) =>
    ((cfg?.base_mensual[m] ?? 0) * ((pct[dept] ?? [])[m] ?? 0)) / 100;
  const restoMes = (m: number) => (cfg?.base_mensual[m] ?? 0) * (1 - totalMes(m) / 100);

  // ── Bajar a Excel ──────────────────────────────────────────────────────────
  // Dos hojas. En la primera, cada SET es una banda y sus categorías cuelgan con
  // sangría (el set es texto, así que no puede ser una columna de valor: se lee
  // mejor como jerarquía). En la segunda, el reparto mensual: por cada destino
  // baja la fila de % y la fila de monto, que es justo lo que la pantalla apila
  // dentro de la misma celda.
  async function bajarExcel() {
    setError(""); setMsg("");
    const cuadros: Cuadro[] = [];

    if (rows.length) {
      const filas: FilaCuadro[] = [];
      for (const s of porSet) {
        filas.push({
          label: `${s.dept_code} · ${s.dept_name}${s.es_padre ? ` · ${t("receivesGL")}` : ""}`,
          es_total: true, valores: [s.unidades, s.tipos.length],
        });
        for (const r of s.tipos) filas.push({ label: `${r.code} · ${r.name}`, nivel: 1, valores: [r.units, null] });
      }
      cuadros.push({
        titulo: t("xlsCatTitle"),
        subtitulo: t("xlsCatSubtitle"),
        hoja: t("xlsCatSheet"),
        columnas: [
          { label: t("colSetCategory"), ancho: 46, formato: "texto" },
          { label: t("units"), ancho: 12, formato: "num" },
          { label: tc("category"), ancho: 12, formato: "num" },
        ],
        filas,
      });
    }

    if (cfg) {
      const meses = Array.from({ length: 12 }, (_, m) => m);
      const filas: FilaCuadro[] = [{
        label: t("arrivedAtRooms"), es_total: true, formato: "usd",
        valores: [...cfg.base_mensual, cfg.base_mensual.reduce((a, b) => a + b, 0)],
      }];
      for (const d of destinos) {
        filas.push({
          label: `${d.dept_name} · ${t("pctOfRooms")}`, nivel: 1, formato: "pct",
          valores: [...meses.map(m => ((pct[d.dept_code] ?? [])[m] ?? 0) / 100), null],
        });
        filas.push({
          label: `${d.dept_name} · ${t("amount")}`, nivel: 1, formato: "usd",
          valores: [...meses.map(m => montoMes(d.dept_code, m)),
                    meses.reduce((a, m) => a + montoMes(d.dept_code, m), 0)],
        });
      }
      filas.push({
        label: `Rooms Standard · ${t("pctResidual")}`, es_total: true, formato: "pct",
        valores: [...meses.map(m => (100 - totalMes(m)) / 100), null],
      });
      filas.push({
        label: `Rooms Standard · ${t("amount")}`, es_total: true, formato: "usd",
        valores: [...meses.map(m => restoMes(m)), meses.reduce((a, m) => a + restoMes(m), 0)],
      });
      const scn = scenarios.find(s => s.id === scenarioId);
      cuadros.push({
        titulo: t("xlsSplitTitle"),
        subtitulo: t("xlsSplitSubtitle", { escenario: scn ? scnLabel(scn) : "" }),
        hoja: t("xlsSplitSheet"),
        columnas: [
          { label: t("set"), ancho: 40, formato: "texto" },
          ...MESES.map(m => ({ label: m, ancho: 13, formato: "usd" as const })),
          { label: tc("year"), ancho: 15, formato: "usd" as const },
        ],
        filas,
      });
    }

    if (!cuadros.length) { setError(t("noDataToExport")); return; }
    try { await bajarCuadros("Room_Sets", cuadros); }
    catch (e) { setError(e instanceof Error ? e.message : t("xlsError")); }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: "24px 20px 60px" }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, margin: 0 }}>{t("title")}</h1>
        <button onClick={bajarExcel} title={t("xlsHint")}
          style={{ padding: "6px 14px", fontSize: 12.5, fontWeight: 700, borderRadius: 8, cursor: "pointer", background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>⬇ Excel</button>
      </div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6, maxWidth: "70ch" }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {msg && <div style={{ color: "var(--positive)", fontSize: 12.5, marginTop: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--negative)", fontSize: 12.5, marginTop: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 40, textAlign: "center" }}>{tc("loading")}</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "18px 0" }}>
            {porSet.map(s => (
              <div key={s.dept_code} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 10, padding: "12px 16px", minWidth: 170 }}>
                <div style={{ fontSize: 10.5, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700 }}>
                  {s.dept_name}{s.es_padre && ` · ${t("receivesGL")}`}
                </div>
                <div className="mono" style={{ fontSize: 19, fontWeight: 700, color: GOLD, marginTop: 3 }}>
                  {s.unidades} <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>{t("unitsLower")}</span>
                </div>
                <div style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                  {t("nCategories", { n: s.tipos.length })}
                </div>
              </div>
            ))}
          </div>

          {/* `fin-sticky`: hay una regla global que pega el encabezado de TODA
              tabla al viewport (top 44px). Sin un contenedor que scrollee por su
              cuenta, la primera fila se mete debajo del encabezado y desaparece
              — acá se comía BL01 con sus 6 unidades. */}
          <div className="fin-sticky" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12 }}>
            <table style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ ...th, background: "var(--bg-elevated)" }}>{tc("code")}</th>
                  <th style={{ ...th, background: "var(--bg-elevated)" }}>{tc("category")}</th>
                  <th style={{ ...th, textAlign: "right", background: "var(--bg-elevated)" }}>{t("units")}</th>
                  <th style={{ ...th, background: "var(--bg-elevated)" }}>{t("set")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id}>
                    <td style={{ ...td, width: 90 }}>
                      <span className="mono" style={{ color: "var(--text-disabled)" }}>{r.code}</span>
                    </td>
                    <td style={{ ...td, fontWeight: 500 }}>{r.name}</td>
                    <td style={{ ...td, textAlign: "right" }}>
                      <span className="mono">{r.units}</span>
                    </td>
                    <td style={{ ...td, width: 220 }}>
                      <select value={setDe(r)} onChange={e => asignar(r.id, e.target.value)}
                        style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)", width: "100%" }}>
                        {sets.map(s => (
                          <option key={s.dept_code} value={s.dept_code}>
                            {s.dept_code} · {s.dept_name}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 12, maxWidth: "70ch" }}>
            {t.rich("codeHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
          </p>

          {/* ── Distribución del costo por mes ───────────────────────────── */}
          <div style={{ marginTop: 40, display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>{t("costSplit")}</h2>
            <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
              style={{ padding: "5px 10px", fontSize: 12.5, borderRadius: 6, background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)" }}>
              {scenarios.map(s => <option key={s.id} value={s.id}>{scnLabel(s)}</option>)}
            </select>
            {scenarioId && <RecalcButton scenarioId={scenarioId} onDone={() => loadCfg(scenarioId)} />}
          </div>
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 6, maxWidth: "76ch" }}>
            {t.rich("splitHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
          </p>

          {!cfg ? (
            <div style={{ color: "var(--text-secondary)", padding: 24, fontSize: 12.5 }}>
              {t("pickScenario")}
            </div>
          ) : (
            <>
              <div className="fin-sticky" style={{ marginTop: 14, background: "var(--bg-elevated)", border: "1px solid var(--border-medium)", borderRadius: 12, overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 940 }}>
                  <thead>
                    <tr>
                      <th style={{ ...th, background: "var(--bg-elevated)", minWidth: 190 }}>{t("set")}</th>
                      {MESES.map(m => <th key={m} style={{ ...thNum, background: "var(--bg-elevated)" }}>{m}</th>)}
                      <th style={{ ...thNum, background: "var(--bg-elevated)" }}>{tc("year")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ ...td, color: "var(--text-secondary)", fontSize: 12 }}>
                        {t("arrivedAtRooms")}
                      </td>
                      {(cfg.base_mensual).map((b, m) => (
                        <td key={m} style={{ ...tdNum, color: "var(--text-secondary)" }}>{money(b)}</td>
                      ))}
                      <td style={{ ...tdNum, color: "var(--text-secondary)", fontWeight: 700 }}>
                        {money(cfg.base_mensual.reduce((a, b) => a + b, 0))}
                      </td>
                    </tr>

                    {destinos.map(d => (
                      <tr key={d.dept_code}>
                        <td style={{ ...td }}>
                          <div style={{ fontWeight: 600 }}>{d.dept_name}</div>
                          <button onClick={() => replicarEnero(d.dept_code)}
                            style={{ marginTop: 3, fontSize: 10.5, padding: "2px 7px", borderRadius: 5, background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)", cursor: "pointer" }}>
                            {t("applyJanToYear")}
                          </button>
                        </td>
                        {Array.from({ length: 12 }, (_, m) => (
                          <td key={m} style={{ ...tdNum }}>
                            <input type="number" min={0} max={100} step={0.5}
                              value={(pct[d.dept_code] ?? [])[m] ?? 0}
                              onChange={e => setPctMes(d.dept_code, m, parseFloat(e.target.value) || 0)}
                              style={{ width: 56, padding: "3px 5px", fontSize: 12, textAlign: "right", borderRadius: 5, background: "var(--bg-input)", color: "var(--text-primary)", border: `1px solid ${totalMes(m) > 100 ? "var(--negative)" : "var(--border-medium)"}` }} />
                            <div style={{ fontSize: 10, color: "var(--text-disabled)", marginTop: 1 }}>
                              {money(montoMes(d.dept_code, m))}
                            </div>
                          </td>
                        ))}
                        <td style={{ ...tdNum, fontWeight: 700 }}>
                          {money(Array.from({ length: 12 }, (_, m) => montoMes(d.dept_code, m)).reduce((a, b) => a + b, 0))}
                        </td>
                      </tr>
                    ))}

                    <tr>
                      <td style={{ ...td, fontWeight: 700, borderTop: "2px solid var(--border-medium)" }}>
                        Rooms Standard <span style={{ fontWeight: 400, color: "var(--text-secondary)", fontSize: 11 }}>· {t("residual")}</span>
                      </td>
                      {Array.from({ length: 12 }, (_, m) => (
                        <td key={m} style={{ ...tdNum, borderTop: "2px solid var(--border-medium)", color: totalMes(m) > 100 ? "var(--negative)" : "inherit" }}>
                          <div style={{ fontWeight: 700 }}>{(100 - totalMes(m)).toFixed(1)}%</div>
                          <div style={{ fontSize: 10, color: "var(--text-disabled)" }}>{money(restoMes(m))}</div>
                        </td>
                      ))}
                      <td style={{ ...tdNum, borderTop: "2px solid var(--border-medium)", fontWeight: 700 }}>
                        {money(Array.from({ length: 12 }, (_, m) => restoMes(m)).reduce((a, b) => a + b, 0))}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {Array.from({ length: 12 }, (_, m) => m).some(m => totalMes(m) > 100) && (
                <div style={{ color: "var(--negative)", fontSize: 12.5, marginTop: 10 }}>
                  {t("over100")}
                </div>
              )}

              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
                <button onClick={guardar} disabled={!dirty || saving}
                  style={{ padding: "8px 18px", fontSize: 13, fontWeight: 600, borderRadius: 8, cursor: dirty ? "pointer" : "default", background: dirty ? GOLD : "var(--bg-input)", color: dirty ? "#1a1a1a" : "var(--text-disabled)", border: "none" }}>
                  {saving ? tc("saving") : t("savePct")}
                </button>
                <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                  {t.rich("saveNoMoney", { b: (c: React.ReactNode) => <b>{c}</b> })}
                </span>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
