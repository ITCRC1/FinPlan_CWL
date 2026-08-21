"use client";
import { useCallback, useEffect, useState, CSSProperties } from "react";
import { useTranslations } from "next-intl";
import {
  getClubMembership, saveClubMembership,
  type ClubMembership, type ClubMembershipFila,
} from "@/lib/api";

/**
 * Carga de socios del Club Madresal.
 *
 * **No es plata.** El Club vende acceso a las instalaciones del hotel; detrás
 * hay un desarrollo inmobiliario que no es parte de este P&L. La cuota de
 * acceso ya vive en el ingreso del departamento 260 — este conteo explica de
 * dónde sale. Por eso viaja con los estadísticos y no toca ninguna línea del
 * estado de resultados.
 *
 * **El total del año es diciembre, no la suma.** Son socios: sumar los doce
 * meses daría 1.500 donde hay 129.
 *
 * **Se apaga solo.** El componente no se dibuja si el departamento 260 está
 * desmarcado en Provisionamiento (el backend manda `visible: false`). El día
 * que el Club se opere por fuera del hotel se desmarca ahí, sin tocar código.
 *
 * Los doce meses van en una sola grilla —no mes por mes como los room stats—
 * porque son cuatro números por mes y el owner los tiene juntos en su Excel:
 * así puede pegar la tabla entera de una.
 */
const CAMPOS = ["total", "condicionados", "pagando", "acuerdo_pago"] as const;
type Campo = (typeof CAMPOS)[number];

const th: CSSProperties = { color: "var(--text-secondary)", fontWeight: 600, fontSize: 11, textAlign: "left", padding: "7px 10px", borderBottom: "1px solid var(--border-medium)", textTransform: "uppercase", letterSpacing: "0.05em", background: "var(--bg-elevated)" };
const thNum: CSSProperties = { ...th, textAlign: "right", textTransform: "none", letterSpacing: 0 };

export default function ClubMembershipEditor({ scenarioId, meses }: {
  scenarioId: string; meses: string[];
}) {
  const t = useTranslations("clubStats");
  const tc = useTranslations("common");
  const [data, setData] = useState<ClubMembership | null>(null);
  const [val, setVal] = useState<Record<Campo, string[]>>(
    () => Object.fromEntries(CAMPOS.map(c => [c, Array(12).fill("")])) as Record<Campo, string[]>);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const cargar = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const d = await getClubMembership(id);
      setData(d);
      const nv = Object.fromEntries(CAMPOS.map(c => [c, Array(12).fill("")])) as Record<Campo, string[]>;
      d.filas.forEach((f: ClubMembershipFila) => {
        if ((CAMPOS as readonly string[]).includes(f.campo))
          nv[f.campo as Campo] = f.meses.map(v => (v ? String(v) : ""));
      });
      setVal(nv);
    } catch { setData(null); }
  }, []);

  useEffect(() => { cargar(scenarioId); }, [scenarioId, cargar]);

  if (!data || !data.visible) return null;

  const num = (s: string) => { const n = parseInt((s || "").replace(/[^\d-]/g, ""), 10); return isNaN(n) ? 0 : n; };
  // El total del año es DICIEMBRE (el último mes con dato), no la suma.
  const cierre = (fila: string[]) => {
    for (let i = 11; i >= 0; i--) { const n = num(fila[i]); if (n) return n; }
    return 0;
  };

  /** Pegar desde Excel: llena hacia la derecha y hacia abajo desde la casilla. */
  function pegar(e: React.ClipboardEvent, campoIdx: number, mesIdx: number) {
    const texto = e.clipboardData.getData("text");
    if (!texto.includes("\t") && !texto.includes("\n")) return;
    e.preventDefault();
    const filas = texto.replace(/\r/g, "").split("\n").filter(l => l.length);
    setVal(prev => {
      const nv = { ...prev };
      filas.forEach((linea, i) => {
        const campo = CAMPOS[campoIdx + i];
        if (!campo) return;
        const cols = linea.split("\t");
        nv[campo] = [...prev[campo]];
        cols.forEach((c, j) => {
          const m = mesIdx + j;
          if (m < 12) nv[campo][m] = c.trim().replace(/[^\d-]/g, "");
        });
      });
      return nv;
    });
  }

  async function guardar() {
    setBusy(true); setMsg("");
    try {
      const payload = Array.from({ length: 12 }, (_, m) => ({
        month: m + 1,
        total: num(val.total[m]),
        condicionados: num(val.condicionados[m]),
        pagando: num(val.pagando[m]),
        acuerdo_pago: num(val.acuerdo_pago[m]),
      }));
      const d = await saveClubMembership(scenarioId, payload);
      setData(d);
      setMsg(t("saved"));
    } catch (e) { setMsg(e instanceof Error ? e.message : "Error"); }
    finally { setBusy(false); }
  }

  const etiqueta = (c: Campo) =>
    data.filas.find(f => f.campo === c)?.etiqueta ?? c;

  return (
    <div style={{ marginTop: 26 }}>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{t("title")}</h2>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0", maxWidth: "80ch" }}>
        {t("hint")}
      </p>
      <div className="fin-sticky" style={{ marginTop: 8, background: "var(--bg-elevated)",
        border: "1px solid var(--border-medium)", borderRadius: 10, overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 1080 }}>
          <thead>
            <tr>
              <th style={{ ...th, minWidth: 240 }}>{tc("concept")}</th>
              {meses.map(m => <th key={m} style={{ ...thNum, minWidth: 68 }}>{m}</th>)}
              <th style={{ ...thNum, minWidth: 86, borderLeft: "1px solid var(--border-medium)" }}>
                {t("yearTotal")}
              </th>
            </tr>
          </thead>
          <tbody>
            {CAMPOS.map((c, ci) => (
              <tr key={c} style={ci === 0 ? { fontWeight: 700 } : undefined}>
                <td style={{ padding: "4px 10px", fontSize: 12.5,
                  borderBottom: "1px solid var(--border-subtle)",
                  paddingLeft: ci === 0 ? 10 : 24 }}>{etiqueta(c)}</td>
                {Array.from({ length: 12 }, (_, m) => (
                  <td key={m} style={{ padding: 2, borderBottom: "1px solid var(--border-subtle)" }}>
                    <input
                      className="fin-input mono"
                      value={val[c][m]}
                      onChange={e => setVal(p => {
                        const nv = { ...p, [c]: [...p[c]] };
                        nv[c][m] = e.target.value.replace(/[^\d-]/g, "");
                        return nv;
                      })}
                      onPaste={e => pegar(e, ci, m)}
                      style={{ width: "100%", textAlign: "right", fontSize: 12,
                               padding: "3px 6px", fontVariantNumeric: "tabular-nums" }}
                    />
                  </td>
                ))}
                <td className="mono" style={{ padding: "4px 10px", textAlign: "right",
                  fontSize: 12.5, fontWeight: 700, borderLeft: "1px solid var(--border-medium)",
                  borderBottom: "1px solid var(--border-subtle)",
                  fontVariantNumeric: "tabular-nums" }}>
                  {cierre(val[c]) || ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 8, flexWrap: "wrap" }}>
        <button onClick={guardar} disabled={busy}
          style={{ padding: "6px 14px", fontSize: 12.5, fontWeight: 700, borderRadius: 6,
            cursor: busy ? "default" : "pointer", background: "var(--positive)",
            color: "#fff", border: "none" }}>
          {busy ? tc("saving") : t("save")}
        </button>
        <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>{t("pasteHint")}</span>
        {msg && <span style={{ fontSize: 12.5, color: "var(--positive)" }}>{msg}</span>}
      </div>
      <p style={{ fontSize: 11.5, color: "#C8A24A", marginTop: 6 }}>{t("totalNote")}</p>
    </div>
  );
}
