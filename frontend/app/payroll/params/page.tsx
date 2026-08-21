"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getScenarios, getPayrollParams, savePayrollParams, type Scenario,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";

const btn = (enabled: boolean): React.CSSProperties => ({
  padding: "8px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600, border: "none",
  cursor: enabled ? "pointer" : "not-allowed",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function PayrollParamsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("payrollParams");
  const tm = useTranslations("months");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [ccssPct, setCcssPct] = useState("26.83");      // % editable
  const [aguDiv, setAguDiv] = useState("12");
  // Drivers de los 9 conceptos que se calculan por regla. Nacen en cero: mientras
  // no se llenen, el número de la planilla no cambia.
  const [drv, setDrv] = useState<Record<string, string>>({
    overtime_pct: "0", bonus_pct: "0", vacaciones_rate: "0", severance_annual_rate: "0",
    cafeteria_daily_crc: "0", transport_monthly_crc: "0",
    housing_monthly_crc: "0", other_monthly_crc: "0", ins_annual_crc: "0",
  });
  const [cal, setCal] = useState<Record<string, number[]>>({
    working_days: Array(12).fill(0), holidays: Array(12).fill(0),
    days_off: Array(12).fill(0),
    calendar_days: [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
  });
  const [seeded, setSeeded] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
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
        const b = elegir(all, "budget") ?? all[0];
        if (!b) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(b.id));
      } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const p = await getPayrollParams(sid);
      setCcssPct(String(parseFloat(p.ccss_rate) * 100));
      setAguDiv(String(parseFloat(p.aguinaldo_divisor)));
      setDrv({
        overtime_pct: String((parseFloat(p.overtime_pct) || 0) * 100),
        bonus_pct: String((parseFloat(p.bonus_pct) || 0) * 100),
        vacaciones_rate: String((parseFloat(p.vacaciones_rate) || 0) * 100),
        severance_annual_rate: String((parseFloat(p.severance_annual_rate) || 0) * 100),
        cafeteria_daily_crc: String(parseFloat(p.cafeteria_daily_crc) || 0),
        transport_monthly_crc: String(parseFloat(p.transport_monthly_crc) || 0),
        housing_monthly_crc: String(parseFloat(p.housing_monthly_crc) || 0),
        other_monthly_crc: String(parseFloat(p.other_monthly_crc) || 0),
        ins_annual_crc: String(parseFloat(p.ins_annual_crc) || 0),
      });
      setCal({
        working_days: p.working_days ?? Array(12).fill(0),
        holidays: p.holidays ?? Array(12).fill(0),
        days_off: p.days_off ?? Array(12).fill(0),
        calendar_days: p.calendar_days ?? [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
      });
      setSeeded(p.seeded); setDirty(false);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  const sel = scenarios.find(s => s.id === scenarioId);
  const ccssFrac = (parseFloat(ccssPct) || 0) / 100;
  const agu = parseFloat(aguDiv) || 12;

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const pct = (k: string) => (parseFloat(drv[k]) || 0) / 100;
      const crc = (k: string) => parseFloat(drv[k]) || 0;
      await savePayrollParams(scenarioId, ccssFrac, agu, {
        overtime_pct: pct("overtime_pct"),
        bonus_pct: pct("bonus_pct"),
        vacaciones_rate: pct("vacaciones_rate"),
        severance_annual_rate: pct("severance_annual_rate"),
        cafeteria_daily_crc: crc("cafeteria_daily_crc"),
        transport_monthly_crc: crc("transport_monthly_crc"),
        housing_monthly_crc: crc("housing_monthly_crc"),
        other_monthly_crc: crc("other_monthly_crc"),
        ins_annual_crc: crc("ins_annual_crc"),
        working_days: cal.working_days,
        holidays: cal.holidays,
        days_off: cal.days_off,
        calendar_days: cal.calendar_days,
      });
      setSeeded(false); setDirty(false);
      setMsg(t("saved"));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("errorSaving")); }
    finally { setSaving(false); }
  }

  async function handleRecalc() {
    if (!scenarioId) return;
    setRecalc(true); setMsg(null);
    try {
      if (dirty) await handleSave();
      const aviso = await recalcularYContar(scenarioId, t("recalcDone"));
      setMsg(aviso);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : t("errorRecalc")); }
    finally { setRecalc(false); }
  }

  const field = (label: string, hint: string, value: string, onChange: (v: string) => void, suffix?: string) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 18 }}>
      <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input className="fin-input mono" value={value} disabled={sel?.is_locked}
          onChange={e => { onChange(e.target.value); setDirty(true); }} onFocus={e => e.target.select()}
          style={{ width: 120, textAlign: "right" }} />
        {suffix && <span style={{ color: "var(--text-disabled)", fontSize: 12 }}>{suffix}</span>}
      </div>
      <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{hint}</span>
    </div>
  );

  const driver = (label: string, hint: string, key: string, suffix: string) =>
    field(label, hint, drv[key] ?? "0",
      (v: string) => setDrv(d => ({ ...d, [key]: v })), suffix);

  const MES = (tm.raw("short") as string[]) ?? ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

  const calendario = (label: string, key: string) => (
    <div style={{ marginBottom: 16 }}>
      <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>{label}</span>
      <div style={{ display: "flex", gap: 4, marginTop: 6, flexWrap: "wrap" }}>
        {(cal[key] ?? Array(12).fill(0)).map((v, i) => (
          <label key={i} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 10, color: "var(--text-disabled)", textAlign: "center" }}>{MES[i]}</span>
            <input className="fin-input mono" value={String(v)} disabled={sel?.is_locked}
              onFocus={e => e.target.select()}
              onChange={e => {
                const n = parseInt(e.target.value, 10);
                setCal(c => {
                  const copia = [...(c[key] ?? Array(12).fill(0))];
                  copia[i] = Number.isFinite(n) ? n : 0;
                  return { ...c, [key]: copia };
                });
                setDirty(true);
              }}
              style={{ width: 44, textAlign: "center", padding: "4px 2px" }} />
          </label>
        ))}
      </div>
    </div>
  );

  const seccion: React.CSSProperties = {
    fontSize: 14, fontWeight: 700, color: "var(--text-primary)",
    marginTop: 26, marginBottom: 4, paddingTop: 16,
    borderTop: "1px solid var(--border-medium)",
  };
  const sub: React.CSSProperties = {
    fontSize: 12, fontWeight: 600, color: "var(--text-secondary)",
    textTransform: "uppercase", letterSpacing: 0.4, marginTop: 18, marginBottom: 10,
  };
  const nota: React.CSSProperties = {
    fontSize: 12, color: "var(--text-secondary)", marginBottom: 12, lineHeight: 1.6,
  };

  return (
    <div className="pag pag-lectura" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} className="fin-input" style={{ minWidth: 220 }}>
          {scenarios.map(s => <option key={s.id} value={s.id}>{s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}</option>)}
        </select>
      </div>
      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6, marginBottom: 16 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b>, alcance: t("perYear") })}
        <br />{t("introFormulas")}
      </p>

      {seeded && <p style={{ color: "var(--accent-amber, #856404)", fontSize: 12, marginBottom: 8 }}>{t("usingDefaults")}</p>}
      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <div style={{ border: "1px solid var(--border-medium)", borderRadius: 8, padding: 20, background: "var(--bg-surface)" }}>
          {field(t("ccssLabel"), t("ccssHint"), ccssPct, setCcssPct, "%")}
          {field(t("aguinaldoLabel"), t("aguinaldoHint"), aguDiv, setAguDiv)}

          <h2 style={seccion}>{t("autoConcepts")}</h2>
          <p style={nota}>
            {t.rich("autoConceptsHelp", { b: (c: React.ReactNode) => <b>{c}</b>, excel: t("benefitsExcel") })}
          </p>

          <h3 style={sub}>{t("provisionOnBase")}</h3>
          {driver(t("vacationLabel"), t("vacationHint"), "vacaciones_rate", "%")}

          <h3 style={sub}>{t("workRisk")}</h3>
          <p style={nota}>
            {t.rich("insHelp", { b: (c: React.ReactNode) => <b>{c}</b>, monto: t("yearAmount") })}
            <br />{t.rich("insCafeteria", { b: (c: React.ReactNode) => <b>{c}</b>, cafe: t("cafeteriaNotHere") })}
          </p>
          {driver(t("insLabel"), t("insHint"), "ins_annual_crc", t("insSuffix"))}

          <h2 style={seccion}>{t("yearCalendar")}</h2>
          <p style={nota}>
            {t("calendarHelp")}
            <br />
            {t.rich("cafeteriaHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
          </p>
          {calendario(t("calHolidays"), "holidays")}
          {calendario(t("calDaysOff"), "days_off")}
          {calendario(t("calDays"), "calendar_days")}

          <div style={{ marginTop: 18, padding: "10px 12px", borderRadius: 6,
                        background: "var(--bg-input)", fontSize: 12,
                        color: "var(--text-secondary)", lineHeight: 1.7 }}>
            {t.rich("manualConcepts", { b: (c: React.ReactNode) => <b>{c}</b> })}
            <br />{t("manualConceptsList")}
            <br /><br />
            {t("manualConceptsBase")}
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked} style={btn(!saving && dirty && !sel?.is_locked)}>
              {saving ? tc("saving") : dirty ? tc("save") : t("savedBtn")}
            </button>
            <button onClick={handleRecalc} disabled={recalc || sel?.is_locked} style={btn(!recalc && !sel?.is_locked)}>
              {recalc ? tc("recalc.running") : t("recalcBtn")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
