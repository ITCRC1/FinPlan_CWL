"use client";
/**
 * Control de tipo de cambio desactualizado.
 *
 * Las líneas del checkbook marcadas en colones guardan los colones como dato
 * maestro y derivan el dólar con el TC de cada mes. Si alguien mueve el TC y
 * nadie recalcula, el P&L sigue mostrando el dólar anterior — y un análisis
 * hecho sobre esa cifra sale mal sin que nada lo advierta.
 *
 * Este aviso lo detecta y lo empuja. Va en las pantallas donde se carga
 * (Costos, OPEX), donde se cambia el TC, y en el P&L: quien LEE el número
 * también tiene que enterarse.
 */
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { getEstadoMoneda, type EstadoMoneda } from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";

export default function AvisoMoneda({ scenarioId }: { scenarioId?: string | null }) {
  const t = useTranslations("fx");
  const tc = useTranslations("common");
  const [estado, setEstado] = useState<EstadoMoneda | null>(null);
  const [recalculando, setRecalculando] = useState(false);
  const [listo, setListo] = useState(false);
  const [falla, setFalla] = useState<string | null>(null);

  const revisar = useCallback(async () => {
    if (!scenarioId) { setEstado(null); return; }
    try { setEstado(await getEstadoMoneda(scenarioId)); } catch { setEstado(null); }
  }, [scenarioId]);

  useEffect(() => { revisar(); setListo(false); }, [revisar]);

  if (!estado || estado.desactualizadas === 0) return null;

  const n = estado.desactualizadas;
  const sinTC = estado.sin_tipo_de_cambio;

  async function empujar() {
    if (!scenarioId) return;
    setRecalculando(true); setFalla(null);
    try {
      const aviso = await recalcularYContar(scenarioId, tc("recalc.done"));
      await revisar();
      // Solo se declara «listo» si el recálculo salió limpio. Antes se ponía
      // listo pasara lo que pasara: el aviso rojo desaparecía y el P&L seguía
      // con los dólares viejos.
      if (aviso.startsWith("⚠")) setFalla(aviso);
      else setListo(true);
    } catch (e) {
      // Sin esto la excepción se iba como promesa sin capturar: el botón dejaba
      // de girar y en pantalla no pasaba nada.
      setFalla(`✖ ${e instanceof Error ? e.message : t("outdated.recalcFail")}`);
    } finally { setRecalculando(false); }
  }

  return (
    <div style={{
      margin: "10px 0 16px", padding: "12px 16px", borderRadius: 6,
      background: "rgba(192,57,43,0.10)", border: "1px solid var(--accent-red, #C0392B)",
      display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap",
    }}>
      <span style={{ fontSize: 20, lineHeight: 1 }}>⚠</span>
      <div style={{ flex: 1, minWidth: 280 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--accent-red, #C0392B)" }}>
          {listo
            ? t("outdated.done")
            : sinTC
              ? t("outdated.noRate", { n })
              : t("outdated.stale", { n })}
        </div>
        {!listo && (
          <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 3, lineHeight: 1.6 }}>
            {sinTC
              ? t("outdated.noRateHelp")
              : <>{t.rich("outdated.staleHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
                 {estado.detalle.length > 0 && (
                   <> {t("outdated.example", {
                     lista: estado.detalle.slice(0, 3).map(d =>
                       `${d.dept_code}/${d.account_code}`).join(" · "),
                     mas: n > 3 ? t("outdated.more", { n: n - 3 }) : "",
                   })}</>
                 )}</>}
          </div>
        )}
        {falla && (
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-red, #C0392B)", marginTop: 6 }}>
            {falla}
          </div>
        )}
      </div>
      {!sinTC && !listo && (
        <button onClick={empujar} disabled={recalculando} style={{
          padding: "8px 16px", fontSize: 12.5, fontWeight: 700, borderRadius: 5,
          border: "none", cursor: recalculando ? "default" : "pointer",
          background: recalculando ? "#555" : "var(--accent-red, #C0392B)", color: "#fff",
        }}>
          {recalculando ? tc("recalc.running") : tc("recalc.button")}
        </button>
      )}
    </div>
  );
}
