"use client";
/**
 * EL AVISO: qué línea que el histórico usa quedó en cero en este escenario.
 *
 * Es el par de la verificación del upload. Aquélla cuida los **actuales** en la
 * puerta (el archivo trae sus totales de control arriba). Ésta cuida los
 * **presupuestos**, que no traen totales de control porque nadie los declaró
 * todavía: su forma de fallar no es un número que no cuadra, es una línea que
 * no está.
 *
 * **Por qué importa (owner, 2026-08-16).** Está por clonar propiedades y el
 * presupuesto 2027 tiene líneas con regla de mapeo y sin un centavo de dato
 * —`OH_UTILITIES` vale 275.927 en 2025 y está en cero—, y **cada propiedad
 * clonada las hereda**. Un GOP 2027 mejor que el 2025 no es buena noticia si es
 * un GOP sin luz, sin renta y sin seguro.
 *
 * **AVISA, NO BLOQUEA.** Un presupuesto en construcción tiene líneas vacías con
 * todo derecho. Por eso esto es una franja que se puede cerrar, no un modal.
 *
 * Se pinta al abrir el escenario y después de recalcular (`recargar` cambia).
 * Cuando no falta nada, no dibuja nada: un aviso que aparece siempre deja de
 * leerse.
 */
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { getAvisoObligatorias, type AvisoObligatorias } from "@/lib/api";

const USD = (n: number) =>
  n.toLocaleString("en-US", { maximumFractionDigits: 0 });

export default function AvisoLineasObligatorias({
  scenarioId, recargar = 0,
}: {
  scenarioId: string | null | undefined;
  /** Cambiar este número vuelve a preguntar (p. ej. después de recalcular). */
  recargar?: number;
}) {
  const t = useTranslations("validation");
  const tc = useTranslations("common");
  const [aviso, setAviso] = useState<AvisoObligatorias | null>(null);
  const [abierto, setAbierto] = useState(false);
  const [cerrado, setCerrado] = useState(false);
  const [tras, setTras] = useState(0);

  // Recalcular es justo el momento en que una línea pasa de cero a tener dato,
  // o al revés. `RecalcButton` avisa por evento desde cualquiera de las siete
  // pantallas donde vive, sin que ninguna tenga que cablear nada.
  useEffect(() => {
    const oir = () => setTras(n => n + 1);
    window.addEventListener("finplan:recalculado", oir);
    return () => window.removeEventListener("finplan:recalculado", oir);
  }, []);

  useEffect(() => {
    let vivo = true;
    setAviso(null);
    setCerrado(false);
    if (!scenarioId) return;
    getAvisoObligatorias(scenarioId)
      .then(r => { if (vivo) setAviso(r); })
      // Que el aviso falle no puede romper la pantalla que lo hospeda: es un
      // control, y un control roto tiene que desaparecer, no estorbar.
      .catch(() => { if (vivo) setAviso(null); });
    return () => { vivo = false; };
  }, [scenarioId, recargar, tras]);

  if (!aviso || cerrado || !aviso.hay_lista) return null;
  if (!aviso.vacio && aviso.cuantas_faltan === 0) return null;

  const franja: React.CSSProperties = {
    border: "1px solid var(--accent-gold, #856404)",
    background: "color-mix(in srgb, var(--accent-gold, #856404) 12%, transparent)",
    borderRadius: 6, padding: "10px 14px", margin: "10px 0", fontSize: 13,
  };

  if (aviso.vacio) {
    return (
      <div style={franja}>
        <strong>{t("mandatory.emptyTitle")}</strong>{" "}
        {t("mandatory.empty", { n: aviso.obligatorias })}
        <button onClick={() => setCerrado(true)} style={BTN_CERRAR}>{tc("close")}</button>
      </div>
    );
  }

  return (
    <div style={franja}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
        <strong>
          {t("mandatory.title", { faltan: aviso.cuantas_faltan, total: aviso.obligatorias })}
        </strong>
        <span style={{ color: "var(--text-secondary)" }}>
          {t("mandatory.worth", { usd: USD(aviso.magnitud_historica_usd) })}
        </span>
        <button onClick={() => setAbierto(v => !v)} style={BTN_LINK}>
          {abierto ? t("mandatory.hide") : t("mandatory.show")}
        </button>
        <a href="/master-data/lineas-obligatorias" style={BTN_LINK as React.CSSProperties}>
          {t("mandatory.report")}
        </a>
        <button onClick={() => setCerrado(true)} style={BTN_CERRAR}>{tc("close")}</button>
      </div>

      {/* No bloquea: se dice por qué, para que nadie lo lea como un error. */}
      <div style={{ color: "var(--text-secondary)", marginTop: 4, fontSize: 12 }}>
        {t("mandatory.notBlocking")}
        {aviso.meses_no_revisados.length > 0 && (
          <> {t("mandatory.monthsSkipped", {
            meses: aviso.meses_no_revisados.map(m => String(m).padStart(2, "0")).join(", "),
            motivo: aviso.motivo_meses_no_revisados,
          })}</>
        )}
      </div>

      {abierto && (
        <table style={{ marginTop: 8, borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
              <th style={TD}>{tc("line")}</th>
              <th style={TD}>{tc("name")}</th>
              <th style={{ ...TD, textAlign: "right" }}>{t("mandatory.historic")}</th>
              <th style={TD}>{t("mandatory.where")}</th>
            </tr>
          </thead>
          <tbody>
            {aviso.faltan.map(f => (
              <tr key={f.line_code}>
                <td style={{ ...TD, fontFamily: "monospace" }}>{f.line_code}</td>
                <td style={TD}>{f.nombre}</td>
                <td style={{ ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {USD(f.referencia_usd)}{" "}
                  <span style={{ color: "var(--text-secondary)" }}>({f.referencia_anio})</span>
                </td>
                <td style={TD}>
                  {f.pantalla
                    ? <a href={f.pantalla} style={{ color: "var(--brand)" }}>{f.donde_se_carga}</a>
                    : f.donde_se_carga}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const TD: React.CSSProperties = {
  padding: "3px 8px", borderBottom: "1px solid var(--border-subtle, #3334)",
};
const BTN_LINK: React.CSSProperties = {
  background: "none", border: "none", padding: 0, cursor: "pointer",
  color: "var(--brand)", fontSize: 12.5, textDecoration: "none",
};
const BTN_CERRAR: React.CSSProperties = {
  ...BTN_LINK, marginLeft: "auto", color: "var(--text-secondary)",
};
