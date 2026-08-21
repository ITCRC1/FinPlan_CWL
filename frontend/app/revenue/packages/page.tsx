"use client";
import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import { HOTEL_ID } from "@/lib/hotel";
import { useHotel } from "@/lib/useHotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getScenarios, getPackagesConfig, savePackages, updateComponentLabel,
  type Scenario, type PackageComponent,
} from "@/lib/api";

interface CompEdit { component: string; label: string; rate: string; comm: boolean; }

function num(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[$, ]/g, ""));
  return isNaN(n) ? 0 : n;
}
const fmtUsd = (n: number) => n ? "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";

export default function PackagesPage() {
  const hotel = useHotel();
  const tc = useTranslations("common");
  const t = useTranslations("packages");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // El selector se acuerda de lo ultimo elegido EN ESTA pantalla, y si nunca se
  // eligio abre con el preferido del owner. El ano ya no va escrito aca: estaba
  // clavado en 2026 y seguia mostrando ese presupuesto despues del corte.
  const [scenarioId, setScenarioId] = useEscenarioDe("revenue/packages:budget", scenarios, "budget");
  const [comps, setComps] = useState<CompEdit[]>([]);
  const [bevPct, setBevPct] = useState("34");   // % del food
  const [seeded, setSeeded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        // La eleccion del escenario la hace `useEscenarioDe` cuando llega la
        // lista: aca solo se carga.
        setScenarios(all);
        if (!all.length) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      } finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const res = await getPackagesConfig(sid);
      setComps(res.components.map((c: PackageComponent) => ({
        component: c.component, label: c.label,
        rate: String(parseFloat(c.rate_per_pax_night)), comm: c.is_commissionable,
      })));
      setBevPct(String(parseFloat(res.bev_food_ratio) * 100));
      setSeeded(res.seeded); setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  /**
   * El RÓTULO del componente se edita y se guarda por propiedad; el CÓDIGO no se
   * toca (el motor calcula por `FOOD`, `ACTIVITIES`… y moverlo cambiaría de
   * línea el ingreso). Dejarlo en blanco devuelve el texto por defecto.
   *
   * Se guarda al salir del campo y no con el botón de Guardar: la etiqueta es de
   * la PROPIEDAD, no del escenario, y mezclarla con el guardado de tarifas haría
   * que un escenario enllavado bloqueara renombrar algo que no es suyo.
   */
  function setLabel(i: number, v: string) {
    setComps(prev => prev.map((c, idx) => idx === i ? { ...c, label: v } : c));
  }
  async function guardarLabel(i: number) {
    const c = comps[i];
    if (!c) return;
    try {
      const r = await updateComponentLabel(HOTEL_ID, c.component, c.label);
      setComps(prev => prev.map((x, idx) => idx === i ? { ...x, label: r.label } : x));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSavingName"));
    }
  }

  function setRate(i: number, v: string) {
    setComps(prev => prev.map((c, idx) => idx === i ? { ...c, rate: v } : c)); setDirty(true);
  }
  function toggleComm(i: number) {
    setComps(prev => prev.map((c, idx) => idx === i ? { ...c, comm: !c.comm } : c)); setDirty(true);
  }

  const foodRate = num(comps.find(c => c.component === "FOOD")?.rate ?? "0");
  const bevRate = foodRate * (num(bevPct) / 100);
  // total del paquete por pax/noche = suma componentes + beverage
  const totalPkg = comps.reduce((s, c) => s + num(c.rate), 0) + bevRate;

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const payload = comps.map(c => ({
        component: c.component, rate_per_pax_night: num(c.rate), is_commissionable: c.comm,
      }));
      const res = await savePackages(scenarioId, payload, num(bevPct) / 100);
      setSeeded(false); setDirty(false);
      setMsg(t("savedN", { n: res.saved }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally { setSaving(false); }
  }

  const sel = scenarios.find(s => s.id === scenarioId);

  // `Comisionable` es una casilla, no un número: viaja pegada al rótulo de la
  // fila. El exportador solo acepta números en las columnas de valores.
  async function bajarExcel() {
    const filas: FilaCuadro[] = comps.map(c => ({
      label: `${c.label} · ${c.comm ? t("isCommissionable") : t("notCommissionable")}`,
      valores: [num(c.rate), null],
    }));
    filas.push({
      label: t("beverageRow"),
      valores: [bevRate, num(bevPct) / 100],   // el % va como fracción
    });
    filas.push({ label: t("totalPerPaxNight"), es_total: true, valores: [totalPkg, null] });
    try {
      await bajarCuadros("Paquete_CWL", [{
        titulo: t("xlsTitle"),
        subtitulo: sel ? `${sel.type} ${sel.version} ${sel.year}` : undefined,
        hoja: t("title"),
        columnas: [
          { label: t("component"), ancho: 38, formato: "texto" },
          { label: t("ratePerPaxNight"), ancho: 18, formato: "usd2" },
          { label: t("pctOfFood"), ancho: 12, formato: "pct" },
        ],
        filas,
      }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  const btn = (en: boolean): React.CSSProperties => ({
    padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
    cursor: en ? "pointer" : "not-allowed",
    background: en ? "var(--brand)" : "var(--bg-surface)", color: en ? "#fff" : "var(--text-disabled)",
  });
  const td: React.CSSProperties = { padding: "6px 10px" };

  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={loading || !comps.length} title={t("excelHint")}
          style={{ ...btn(!loading && !!comps.length), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked} style={btn(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 12 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {seeded && <p style={{ color: "var(--accent-amber, #856404)", fontSize: 12, marginBottom: 8 }}>{t("suggested", { hotel: hotel.corto })}</p>}
      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <table className="fin-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>{t("component")}</th>
              <th style={{ textAlign: "right" }}>{t("ratePerPaxNight")}</th>
              <th style={{ textAlign: "center" }}>{t("commissionable")}</th>
            </tr>
          </thead>
          <tbody>
            {comps.map((c, i) => (
              <tr key={c.component}>
                <td style={{ ...td, textAlign: "left" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="mono" title={t("fixedCodeHint")}
                      style={{ color: "var(--text-disabled)", fontSize: 11, minWidth: 92 }}>
                      {c.component}
                    </span>
                    <input className="fin-input" value={c.label}
                      onChange={e => setLabel(i, e.target.value)}
                      onBlur={() => guardarLabel(i)}
                      placeholder={t("labelPlaceholder")}
                      title={t("labelHint")}
                      style={{ width: "100%", fontWeight: 500 }} />
                  </div>
                </td>
                <td style={td}>
                  <div style={{ display: "flex", alignItems: "center", gap: 2, justifyContent: "flex-end" }}>
                    <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>$</span>
                    <input className="fin-input mono" value={c.rate} disabled={sel?.is_locked}
                      onChange={e => setRate(i, e.target.value)} onFocus={e => e.target.select()}
                      style={{ width: 90, textAlign: "right" }} />
                  </div>
                </td>
                <td style={{ ...td, textAlign: "center" }}>
                  <input type="checkbox" checked={c.comm} disabled={sel?.is_locked} onChange={() => toggleComm(i)} />
                </td>
              </tr>
            ))}
            {/* Beverage derivado del ratio del food */}
            <tr>
              <td style={{ ...td, textAlign: "left", fontWeight: 500 }}>Beverage</td>
              <td style={td}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
                  <input className="fin-input mono" value={bevPct} disabled={sel?.is_locked}
                    onChange={e => { setBevPct(e.target.value); setDirty(true); }} onFocus={e => e.target.select()}
                    style={{ width: 56, textAlign: "right" }} />
                  <span style={{ color: "var(--text-disabled)", fontSize: 11 }}>{t("pctOfFood")}</span>
                  <span className="mono" style={{ color: "var(--text-secondary)", minWidth: 70, textAlign: "right" }}>= {fmtUsd(bevRate)}</span>
                </div>
              </td>
              <td style={{ ...td, textAlign: "center", color: "var(--text-disabled)", fontSize: 12 }}>{t("inheritsFood")}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
              <td style={{ ...td, textAlign: "left", color: "var(--brand)" }}>{t("totalPerPaxNight")}</td>
              <td className="mono" style={{ ...td, textAlign: "right", color: "var(--brand)" }}>{fmtUsd(totalPkg)}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  );
}
