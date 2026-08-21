"use client";
/**
 * Master Data — Tipo de Cambio.
 *
 * Una sola grilla: las versiones en filas, los 12 meses en columnas. Así se ve
 * todo de un vistazo y se edita en el mismo lugar.
 *
 * El TC vive POR VERSIÓN y está aislado: un budget arranca parejo (mismo dólar
 * todo el año); un forecast se va corrigiendo mes a mes conforme avanza el año,
 * sin mover el presupuesto del que salió. Cada mes se convierte con SU tipo de
 * cambio: salarios, CCSS, aguinaldo, vacaciones, reparto del INS y beneficios.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { ordenarEscenarios } from "@/lib/ordenEscenarios";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getTipoCambio, saveTipoCambio, recalculateScenario,
  type Scenario,
} from "@/lib/api";

const MES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

export default function TipoCambioPage() {
  const t = useTranslations("fx");
  const tCom = useTranslations("common");
  const tm = useTranslations("months");
  const MES = (tm.raw("short") as string[]) ?? MES_FALLBACK;
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [tc, setTc] = useState<Record<string, number[]>>({});
  const [sucios, setSucios] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      // Cada año se mantiene junto (la serie del 2027 no se parte) y el año que
      // se está presupuestando va primero. La regla vive en lib/ordenEscenarios
      // porque Salary Allocation usa el mismo selector: cuando estaba escrita
      // solo acá, esa pantalla ordenaba por año descendente y arrancaba en el
      // Working 2035, que está vacío.
      const todas = ordenarEscenarios(await getScenarios(HOTEL_ID));
      setScenarios(todas);
      const mapa: Record<string, number[]> = {};
      for (const s of todas) {
        const r = await getTipoCambio(s.id);
        mapa[s.id] = r.months.map(m => Number(m.tc_crc_usd ?? 0));
      }
      setTc(mapa); setSucios(new Set());
    } catch (e) { setError(e instanceof Error ? e.message : tCom("error")); }
    finally { setLoading(false); }
  }, [tCom]);

  useEffect(() => { cargar(); }, [cargar]);

  function editar(sid: string, mes: number, valor: string) {
    const n = parseFloat(valor);
    setTc(t => {
      const f = [...(t[sid] ?? Array(12).fill(0))];
      f[mes] = Number.isFinite(n) ? n : 0;
      return { ...t, [sid]: f };
    });
    setSucios(s => new Set(s).add(sid));
  }

  /** El arranque de un presupuesto: un solo dólar para los 12 meses. */
  function aplicarATodos(sid: string) {
    setTc(t => ({ ...t, [sid]: Array(12).fill((t[sid] ?? [])[0] ?? 0) }));
    setSucios(s => new Set(s).add(sid));
  }

  async function guardar(s: Scenario, recalcular: boolean) {
    setBusy(s.id); setMsg(null); setError(null);
    try {
      const porMes: Record<string, number> = {};
      (tc[s.id] ?? []).forEach((v, i) => { porMes[String(i + 1)] = v; });
      await saveTipoCambio(s.id, porMes, "Master Data — Tipo de Cambio");
      setSucios(prev => { const n = new Set(prev); n.delete(s.id); return n; });
      const nombre = `${s.year} ${s.type} ${s.version}`;
      if (recalcular) {
        const r = await recalculateScenario(s.id);
        const av = r?.avisos?.length ? ` · ${r.avisos.join(" · ")}` : "";
        setMsg(t("savedRecalc", { nombre, avisos: av }));
      } else {
        setMsg(t("savedOnly", { nombre }));
      }
    } catch (e) { setError(e instanceof Error ? e.message : t("saveError")); }
    finally { setBusy(null); }
  }

  async function bajarExcel() {
    setError(null);
    // Los meses van en crudo (₡512.50), no como cadena: el TC se usa para
    // dividir, y una columna de texto no divide nada.
    const filas: FilaCuadro[] = scenarios.map(s => {
      const f = tc[s.id] ?? Array(12).fill(0);
      const puestos = f.filter(x => x > 0);
      const prom = puestos.length ? puestos.reduce((a, b) => a + b, 0) / puestos.length : null;
      return {
        label: `${s.year} · ${s.type} · ${s.version}${s.is_locked ? " 🔒" : ""}`,
        // Un mes sin TC va vacío, no en cero: son cosas distintas y un cero
        // acá se leería como «el dólar valió nada».
        valores: [...f.map(v => (v > 0 ? v : null)), prom],
      };
    });
    try {
      await bajarCuadros("Tipo_De_Cambio", [{
        titulo: t("xlsTitle"),
        subtitulo: t("xlsSubtitle"),
        hoja: t("xlsSheet"),
        columnas: [
          { label: t("version"), ancho: 30, formato: "texto" },
          ...MES.map(m => ({ label: m, ancho: 10, formato: "usd2" as const })),
          { label: t("avg"), ancho: 12, formato: "usd2" as const },
        ],
        filas,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("xlsError"));
    }
  }

  const th: React.CSSProperties = {
    padding: "7px 6px", fontSize: 11, fontWeight: 600, textAlign: "center",
    color: "var(--text-secondary)", borderBottom: "1px solid var(--border-medium)",
    position: "sticky", top: 0, background: "var(--bg-surface)",
  };
  const btn = (on: boolean, primario = false): React.CSSProperties => ({
    padding: "4px 9px", fontSize: 11.5, borderRadius: 4, fontWeight: 600,
    cursor: on ? "pointer" : "not-allowed", whiteSpace: "nowrap",
    border: primario ? "none" : "1px solid var(--border-medium)",
    background: primario ? (on ? "var(--brand)" : "var(--bg-surface)") : "var(--bg-surface)",
    color: primario && on ? "#fff" : on ? "var(--text-primary)" : "var(--text-disabled)",
  });

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA />
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          {t("title")}
        </h1>
        <button onClick={bajarExcel} disabled={loading || !scenarios.length}
          title={t("xlsHint")}
          style={{ padding: "6px 12px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer",
            background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, maxWidth: 940, lineHeight: 1.7 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
        <br />
        {t.rich("movesHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, margin: "10px 0" }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, margin: "10px 0" }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{t("loadingVersions")}</div>
      ) : (
        <div className="fin-scroll-x" style={{ overflowX: "auto", border: "1px solid var(--border-medium)",
          borderRadius: 8, marginTop: 10 }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={{ ...th, textAlign: "left", minWidth: 215, left: 0, zIndex: 2 }}>{t("version")}</th>
                {MES.map(m => <th key={m} style={th}>{m}</th>)}
                <th style={{ ...th, textAlign: "right" }}>{t("avg")}</th>
                <th style={th}></th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map(s => {
                const f = tc[s.id] ?? Array(12).fill(0);
                const puestos = f.filter(x => x > 0);
                const prom = puestos.length ? puestos.reduce((a, b) => a + b, 0) / puestos.length : 0;
                const varia = new Set(puestos).size > 1;
                const vacio = puestos.length === 0;
                const sucio = sucios.has(s.id);
                const enero = f[0] || 0;
                return (
                  <tr key={s.id} style={{ borderBottom: "1px solid var(--border-subtle, #2a2a2a)" }}>
                    <td style={{ padding: "4px 10px", fontSize: 12.5, whiteSpace: "nowrap",
                      color: "var(--text-primary)" }}>
                      {s.year} · {s.type} · <b>{s.version}</b>
                      {s.is_locked && <span title={t("lockedTitle")}> 🔒</span>}
                      {varia && <span style={{ color: "var(--accent-gold, #856404)", fontSize: 11 }}
                        title={t("variesTitle")}> {t("varies")}</span>}
                      {vacio && <span style={{ color: "var(--accent-red, #C0392B)", fontSize: 11 }}
                        title={t("noFxTitle")}> · {t("noFx")}</span>}
                    </td>
                    {f.map((v, i) => {
                      const movido = i > 0 && enero > 0 && v > 0 && v !== enero;
                      return (
                        <td key={i} style={{ padding: 2, textAlign: "center" }}>
                          <input className="fin-input mono" value={String(v)}
                            disabled={s.is_locked}
                            title={v ? t("cellTitle", { monto: (530000 / v).toFixed(2) }) : t("noFxCell")}
                            style={{
                              width: 62, textAlign: "right", padding: "4px 6px", fontSize: 12,
                              color: movido ? "var(--accent-gold, #856404)" : undefined,
                            }}
                            onFocus={e => e.target.select()}
                            onChange={e => editar(s.id, i, e.target.value)} />
                        </td>
                      );
                    })}
                    <td style={{ padding: "4px 10px", fontSize: 12, textAlign: "right",
                      fontWeight: 600, fontVariantNumeric: "tabular-nums",
                      color: "var(--text-primary)" }}>
                      {prom ? prom.toFixed(2) : "—"}
                    </td>
                    <td style={{ padding: "4px 8px", whiteSpace: "nowrap" }}>
                      {!s.is_locked && (
                        <span style={{ display: "inline-flex", gap: 6 }}>
                          <button onClick={() => aplicarATodos(s.id)} disabled={!!busy}
                            title={t("applyAllTitle")}
                            style={btn(!busy)}>{t("applyAll")}</button>
                          <button onClick={() => guardar(s, false)}
                            disabled={!sucio || !!busy} style={btn(sucio && !busy)}>
                            {busy === s.id ? "…" : sucio ? tCom("save") : t("savedLabel")}
                          </button>
                          <button onClick={() => guardar(s, true)} disabled={!!busy}
                            title={t("saveRecalcTitle")}
                            style={btn(!busy, true)}>↻ {t("saveAndRecalc")}</button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 12, maxWidth: 940, lineHeight: 1.7 }}>
        {t("footHelp")}
      </p>
    </div>
  );
}
