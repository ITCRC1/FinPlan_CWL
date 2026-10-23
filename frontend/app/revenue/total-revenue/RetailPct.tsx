"use client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { setRetailPct, type Scenario } from "@/lib/api";

// Retail (Gift Shop) = % × Rooms del P&L, por escenario. El motor lo aplica en
// cada mes que calcula (migración 156); acá solo se lee y se guarda el %.
export default function RetailPct({ scenario, onSaved }: {
  scenario: Scenario | undefined;
  onSaved: (pct: number) => void;
}) {
  const t = useTranslations("totalRev");
  const [val, setVal] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setVal(scenario?.retail_pct != null ? String(scenario.retail_pct) : "");
    setMsg(null);
  }, [scenario?.id, scenario?.retail_pct]);

  if (!scenario) return null;
  const locked = scenario.is_locked;
  const pct = parseFloat(val.replace(",", "."));
  const changed = isFinite(pct) && pct !== scenario.retail_pct;

  async function save() {
    if (!scenario || !isFinite(pct) || pct < 0 || pct > 100) { setMsg("✖ " + t("retailPctInvalid")); return; }
    setSaving(true); setMsg(null);
    try {
      const r = await setRetailPct(scenario.id, pct);
      onSaved(r.retail_pct);
      setMsg("✓ " + t("retailPctSaved"));
    } catch (e) {
      setMsg("✖ " + (e instanceof Error ? e.message : String(e)));
    } finally { setSaving(false); }
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", margin: "4px 0 12px",
                  padding: "10px 14px", borderRadius: 6, background: "var(--bg-surface)",
                  border: "1px solid var(--border-medium)", fontSize: 13 }}>
      <b>{t("retailPctLabel")}</b>
      <input className="fin-input" value={val} disabled={locked || saving}
        onChange={e => setVal(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && changed) save(); }}
        style={{ width: 80, textAlign: "right" }} inputMode="decimal" />
      <span>% × {t("retailPctBase")}</span>
      <button onClick={save} disabled={locked || saving || !changed}
        style={{ padding: "6px 14px", fontSize: 12.5, fontWeight: 600, borderRadius: 6, border: "none",
                 cursor: locked || !changed ? "default" : "pointer",
                 background: locked || !changed ? "#888" : "var(--accent-excel)", color: "#fff" }}>
        {saving ? "…" : t("retailPctSave")}
      </button>
      <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>{t("retailPctHint")}</span>
      {msg && <span style={{ color: msg.startsWith("✖") ? "var(--accent-red, #C0392B)" : "var(--accent-green, #1A7F4B)" }}>{msg}</span>}
    </div>
  );
}
