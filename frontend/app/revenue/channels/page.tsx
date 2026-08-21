"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import MixerCanales from "@/components/MixerCanales";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import {
  getScenarios, getChannelsConfig,
  type Scenario,
} from "@/lib/api";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

interface ChEdit { channel: string; label: string; mix: string[]; comm: string[]; }

function pct(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[%, ]/g, ""));
  return isNaN(n) ? 0 : n;
}
// fracción "0.28" → "28" limpio
function toPct(s: string): string { return String(parseFloat((parseFloat(s) * 100 || 0).toFixed(4))); }

type SubTab = "mix" | "derivado";

export default function ChannelsPage() {
  /** ⚠️ Owner, 2026-08-17: *«todo en mixer… y que viaje acá. Es más, yo traería
   *  el mixer para acá, tiene más sentido: abro su sub-tab y ahí hago. Y para no
   *  mover nada de las conexiones, solo trae el número acá»*.
   *
   *  Antes las dos pantallas EDITABAN el mismo número con una sola dirección de
   *  sincronización: el mixer aplicaba acá (con `DELETE` + `INSERT`), y lo que
   *  se editaba acá **no volvía nunca** — y el próximo «Aplicar» lo pisaba sin
   *  avisar. Y la vuelta no era un olvido: no tiene solución única, porque acá
   *  hay 3 canales y en el mixer 7 sub-canales; repartir DIRECT al 12% entre sus
   *  cinco no se puede deducir.
   *
   *  Ahora se planifica en el sub-tab «Mix» y esta grilla **muestra el
   *  resultado**. Es el mismo componente del mixer, no una copia. */
  const [subtab, setSubtab] = useState<SubTab>("derivado");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("channels");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [chs, setChs] = useState<ChEdit[]>([]);
  const [seeded, setSeeded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const budget = elegir(all, "budget") ?? all[0];
        if (!budget) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(budget.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const res = await getChannelsConfig(sid);
      setChs(res.channels.map(c => ({
        channel: c.channel, label: c.label,
        mix: c.mix.map(toPct), comm: c.comm.map(toPct),
      })));
      setSeeded(res.seeded);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);








  // Net Factor por mes = Σ(mix × (1 − comm))
  const netFactor = MONTHS.map((_, mi) =>
    chs.reduce((s, c) => s + (pct(c.mix[mi]) / 100) * (1 - pct(c.comm[mi]) / 100), 0));
  const mixTotal = MONTHS.map((_, mi) => chs.reduce((s, c) => s + pct(c.mix[mi]), 0));


  const sel = scenarios.find(s => s.id === scenarioId);

  // Canal y Métrica son dos columnas de texto en pantalla; el exportador lleva
  // una sola, así que van juntas en el rótulo — igual que `editRows`.
  // Todo sale como FRACCIÓN: 28% viaja como 0.28, que es como Excel guarda un %.
  async function bajarExcel() {
    const filas: FilaCuadro[] = chs.flatMap(c => [
      { label: `${c.label} · Mix %`, valores: MONTHS.map((_m, mi) => pct(c.mix[mi]) / 100) },
      { label: `${c.label} · ${t("commission")}`, nivel: 1, valores: MONTHS.map((_m, mi) => pct(c.comm[mi]) / 100) },
    ]);
    filas.push({ label: t("totalMix"), valores: mixTotal.map(v => v / 100) });
    filas.push({ label: "Net Factor", es_total: true, valores: netFactor });
    try {
      await bajarCuadros("Canales_de_Venta", [{
        titulo: t("xlsTitle"),
        subtitulo: [sel ? `${sel.type} ${sel.version} ${sel.year}` : "", "Net Rate = Rack Rate × Net Factor"]
          .filter(Boolean).join(" · "),
        hoja: t("mixer.title"),
        columnas: [
          { label: `${t("mixer.colChannel")} · ${tc("metric")}`, ancho: 34, formato: "texto" },
          ...MONTHS.map(m => ({ label: m, ancho: 11, formato: "pct" as const })),
        ],
        filas,
      }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const btn = (enabled: boolean): React.CSSProperties => ({
    padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
    cursor: enabled ? "pointer" : "not-allowed",
    background: enabled ? "var(--brand)" : "var(--bg-surface)",
    color: enabled ? "#fff" : "var(--text-disabled)",
  });

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
        <div style={{ flex: 1 }} />
        {/* «Aplicar Ene a todos» y «Guardar» se fueron: acá ya no se edita. */}
        <button onClick={bajarExcel} disabled={loading || !chs.length} title={t("excelHint")}
          style={{ ...btn(!loading && !!chs.length), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      {/* Los dos sub-tabs: se planifica en «Mix», se mira el resultado acá. */}
      <div style={{ display: "flex", gap: 4, marginTop: 12, marginBottom: 14,
        borderBottom: "1px solid var(--border-subtle)" }}>
        {([["mix", t("tabMix")],
           ["derivado", t("tabDerived")]] as const).map(([k, etiqueta]) => (
          <button key={k} onClick={() => setSubtab(k)}
            style={{
              padding: "8px 16px", fontSize: 13, cursor: "pointer",
              border: "none", background: "transparent",
              borderBottom: `2px solid ${subtab === k ? "var(--brand)" : "transparent"}`,
              color: subtab === k ? "var(--brand)" : "var(--text-secondary)",
              fontWeight: subtab === k ? 700 : 400,
            }}>{etiqueta}</button>
        ))}
      </div>

      {subtab === "mix" && <MixerCanales />}

      {subtab === "derivado" && (<>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t.rich("derivedIntro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {seeded && <p style={{ color: "var(--accent-amber, #856404)", fontSize: 12, marginBottom: 8 }}>{t("defaults")}</p>}
      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 150 }}>{t("mixer.colChannel")}</th>
                <th style={{ textAlign: "left", minWidth: 90 }}>{tc("metric")}</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 62 }}>{m}</th>)}
              </tr>
            </thead>
            <tbody>
              {chs.map((c, ci) => (
                [
                  <tr key={`${ci}-mix`}>
                    <td rowSpan={2} style={{ textAlign: "left", verticalAlign: "middle", borderRight: "1px solid var(--border-medium)" }}>
                      {/* Nombre y borrado se manejan en el sub-tab Mix, que es
                          donde vive el dato. Acá solo se muestra. */}
                      <div style={{ display: "flex", alignItems: "center", gap: 4,
                        padding: "3px 6px", fontWeight: 500 }}>{c.label}</div>
                    </td>
                    <td style={{ textAlign: "left", color: "var(--text-secondary)" }}>Mix %</td>
                    {MONTHS.map((_, mi) => (
                      <td key={mi} style={{ padding: "1px 2px" }}>
                        <span className="mono" style={{ display: "block", textAlign: "right",
                          padding: "3px 6px", color: "var(--text-primary)" }}>{c.mix[mi]}</span>
                      </td>
                    ))}
                  </tr>,
                  <tr key={`${ci}-comm`} style={{ borderBottom: "1px solid var(--border-medium)" }}>
                    <td style={{ textAlign: "left", color: "var(--text-secondary)" }}>{t("commission")}</td>
                    {MONTHS.map((_, mi) => (
                      <td key={mi} style={{ padding: "1px 2px" }}>
                        <span className="mono" style={{ display: "block", textAlign: "right",
                          padding: "3px 6px", color: "var(--text-primary)" }}>{c.comm[mi]}</span>
                      </td>
                    ))}
                  </tr>,
                ]
              ))}
              <tr style={{ color: "var(--text-disabled)" }}>
                <td colSpan={2} style={{ textAlign: "left" }}>{t("totalMix")}</td>
                {mixTotal.map((t, mi) => (
                  <td key={mi} className="mono" style={{ textAlign: "right", color: Math.round(t) === 100 ? "var(--text-disabled)" : "var(--accent-red, #C0392B)" }}>
                    {t.toFixed(0)}%
                  </td>
                ))}
              </tr>
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td colSpan={2} style={{ textAlign: "left", color: "var(--brand)" }}>Net Factor</td>
                {netFactor.map((nf, mi) => (
                  <td key={mi} className="mono" style={{ textAlign: "right", color: "var(--brand)" }}>{nf.toFixed(4)}</td>
                ))}
              </tr>
            </tfoot>
          </table>
          <button onClick={() => setSubtab("mix")}
            style={{ marginTop: 14, padding: "8px 14px", fontSize: 13, borderRadius: 6,
              cursor: "pointer", border: "1px solid var(--brand)",
              background: "transparent", color: "var(--brand)", fontWeight: 600 }}>
            {t("goToMix")}
          </button>
        </div>
      )}
      </>)}
    </div>
  );
}
