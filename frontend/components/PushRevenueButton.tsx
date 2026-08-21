"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { pushRevenueToCheckbook } from "@/lib/api";

/**
 * Botón de los auxiliares de INGRESO (tarifas, ocupación, pax, canales, paquetes).
 *
 * El ingreso del presupuesto sale ÚNICAMENTE del checkbook de ingresos, así que
 * estas pantallas son la calculadora: este botón traslada el cálculo al checkbook,
 * que es lo que mueve el P&L. Muestra el antes/después y pide confirmación.
 */
export default function PushRevenueButton({
  scenarioId, disabled, onDone,
}: {
  scenarioId: string | null | undefined;
  disabled?: boolean;
  onDone?: () => void;
}) {
  const t = useTranslations("common");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const money = (n: number) => "$" + Math.round(n).toLocaleString("en-US");

  async function run() {
    if (!scenarioId) return;
    setBusy(true); setMsg(null);
    try {
      const prev = await pushRevenueToCheckbook(scenarioId, true);
      const cambios = prev.lineas.filter(l => Math.abs(l.dif) >= 1)
        .map(l => `  ${l.linea}: ${money(l.antes)} → ${money(l.despues)}`).join("\n");
      // Las noches van aparte del dinero: el ingreso puede calzar al centavo y la
      // ocupación estar cientos de noches atrás. Decir "sin cambios" mirando solo
      // la plata fue justamente lo que escondió esa diferencia.
      const noches = Math.round(prev.noches_despues ?? 0) - Math.round(prev.noches_antes ?? 0);
      const n = (v: number) => Math.round(v).toLocaleString("en-US");
      const lineaNoches = prev.noches_despues === undefined ? ""
        : t("pushRev.nights", { antes: n(prev.noches_antes ?? 0), despues: n(prev.noches_despues) }) +
          (noches ? `  (${noches > 0 ? "+" : ""}${n(noches)})\n\n` : "\n\n");
      const hayCambios = cambios || noches !== 0;
      const ok = window.confirm(
        t("pushRev.confirmHead") + "\n\n" +
        t("pushRev.total", { antes: money(prev.total_antes), despues: money(prev.total_despues) }) + "\n" +
        lineaNoches +
        (cambios ? t("pushRev.byLine", { lista: cambios }) + "\n\n" : "") +
        (hayCambios ? "" : t("pushRev.noChanges") + "\n\n") +
        t("pushRev.confirmAsk"));
      if (!ok) { setBusy(false); return; }
      const r = await pushRevenueToCheckbook(scenarioId, false);
      const nn = (r.noches_despues !== undefined && r.noches_antes !== r.noches_despues)
        ? t("pushRev.doneNights", { antes: n(r.noches_antes ?? 0), despues: n(r.noches_despues) }) : "";
      setMsg("✓ " + t("pushRev.done", {
        antes: money(r.total_antes), despues: money(r.total_despues), noches: nn,
      }));
      onDone?.();
      setTimeout(() => setMsg(null), 8000);
    } catch (e) {
      setMsg("✖ " + (e instanceof Error ? e.message : t("error")));
    } finally { setBusy(false); }
  }

  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <button
        onClick={run}
        disabled={busy || disabled || !scenarioId}
        title={t("pushRev.hint")}
        style={{
          padding: "7px 14px", fontSize: 12.5, fontWeight: 600, borderRadius: 6,
          border: "none", cursor: busy || disabled || !scenarioId ? "default" : "pointer",
          background: busy || disabled || !scenarioId ? "#555" : "var(--accent-excel)", color: "#fff",
        }}
      >
        {busy ? t("pushRev.running") : t("pushRev.button")}
      </button>
      {msg && (
        <span style={{ fontSize: 12, color: msg.startsWith("✓") ? "var(--accent-green, #1A7F4B)" : "var(--accent-red, #C0392B)" }}>
          {msg}
        </span>
      )}
    </span>
  );
}
