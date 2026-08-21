"use client";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { recalculateScenario } from "@/lib/api";

/**
 * Botón de recálculo compartido de los auxiliares del budget.
 *
 * Recalcula las fórmulas de planilla (SW, CCSS, aguinaldo) y refresca el P&L con
 * lo que hay en los auxiliares. El P&L del budget se arma al vuelo desde los
 * checkbooks, así que después de esto lo que ves en el P&L es lo que hay cargado.
 */
export default function RecalcButton({
  scenarioId, disabled, onDone, label,
}: {
  scenarioId: string | null | undefined;
  disabled?: boolean;
  onDone?: () => void;
  label?: string;
}) {
  const t = useTranslations("common");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function run() {
    if (!scenarioId) return;
    setBusy(true); setMsg(null);
    try {
      const r = await recalculateScenario(scenarioId);
      const avisos: string[] = r?.avisos ?? [];
      if (avisos.length) {
        // Algo no se pudo recalcular (p.ej. escenario sin tipo de cambio). Antes
        // esto salía en silencio y el mensaje decía "recalculado" igual.
        setMsg(`⚠ ${avisos.join(" · ")}`);
      } else {
        setMsg(t("recalc.done"));
        setTimeout(() => setMsg(null), 6000);
      }
      // El aviso de líneas obligatorias tiene que volver a preguntar: recalcular
      // es exactamente el momento en que una línea pasa de cero a tener dato (o
      // al revés). Va por evento y no por prop para no obligar a cada una de las
      // siete pantallas que usan este botón a cablear un contador.
      window.dispatchEvent(new CustomEvent("finplan:recalculado", { detail: { scenarioId } }));
      onDone?.();
    } catch (e) {
      setMsg(`✖ ${e instanceof Error ? e.message : t("error")}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <button
        onClick={run}
        disabled={busy || disabled || !scenarioId}
        title={t("recalc.hint")}
        style={{
          padding: "7px 14px", fontSize: 12.5, fontWeight: 600, borderRadius: 6,
          border: "none", cursor: busy || disabled || !scenarioId ? "default" : "pointer",
          background: busy || disabled || !scenarioId ? "#555" : "var(--brand)", color: "#fff",
        }}
      >
        {busy ? t("recalc.running") : (label ?? t("recalc.button"))}
      </button>
      {msg && (
        <span style={{
          fontSize: 12, maxWidth: 480,
          color: msg.startsWith("✓") ? "var(--accent-green, #1A7F4B)"
            : msg.startsWith("⚠") ? "var(--accent-gold, #856404)"
              : "var(--accent-red, #C0392B)",
        }}>
          {msg}
        </span>
      )}
      <a href="/admin/control" title={t("recalc.viewControlHint")}
        style={{ fontSize: 11.5, color: "var(--text-secondary)", textDecoration: "none", borderBottom: "1px dotted var(--border-medium)" }}>
        {t("recalc.viewControl")}
      </a>
    </span>
  );
}
