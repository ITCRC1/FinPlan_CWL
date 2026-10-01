"use client";
/**
 * Piezas compartidas del módulo PACING: contexto de datos, controles, tablas.
 *
 * ⚠️ El cálculo NO vive acá. Todo número sale de `/pacing/analisis`
 * (`backend/app/engine/pacing.py`); esta capa sólo lo dibuja. La única cuenta
 * que se hace en el navegador es la del Presupuesto, porque es lo que el usuario
 * está escribiendo.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode, type CSSProperties } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  getPacingAnalisis, type PacingAnalisis, type PacingEscenario, type PacingFuente, type PacingKind,
} from "@/lib/api";

export const TABS = [
  "resumen", "posicion", "comparativo", "meta", "noviembre-2026", "diciembre-2026", "presupuesto",
  "curva", "pickup", "cancelaciones", "alertas", "cargas",
] as const;
export type PacingTab = typeof TABS[number];
/** Los tabs de un mes traen su propio análisis: los filtros del módulo no les aplican. */
const SIN_FILTROS: readonly PacingTab[] = ["noviembre-2026", "diciembre-2026"];

export interface Filtros { year?: number; kind: PacingKind; escenario: PacingEscenario; fuente: PacingFuente }
const LLAVE = "finplan_pacing_filtros";
const INICIAL: Filtros = { kind: "total", escenario: "avail", fuente: "auto" };

function leerFiltros(): Filtros {
  try {
    const v = JSON.parse(localStorage.getItem(LLAVE) || "{}");
    return { ...INICIAL, ...v };
  } catch { return INICIAL; }
}
function guardarFiltros(f: Filtros) {
  try { localStorage.setItem(LLAVE, JSON.stringify(f)); } catch { /* modo privado: no pasa nada */ }
}

interface Ctx {
  datos: PacingAnalisis | null; cargando: boolean; error: string | null;
  filtros: Filtros; setFiltros: (f: Partial<Filtros>) => void; recargar: () => void;
}
const PacingCtx = createContext<Ctx | null>(null);
export function usePacing(): Ctx {
  const c = useContext(PacingCtx);
  if (!c) throw new Error("usePacing fuera de PacingShell");
  return c;
}

/** Meses cortos del catálogo. */
export function useMeses(): string[] {
  const tm = useTranslations("months");
  return (tm.raw("short") as string[]) ?? ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];
}

// ───────────────────────────── formato ─────────────────────────────
export const n0 = (v: number | null | undefined) =>
  v == null || isNaN(v) ? "—" : Math.round(v).toLocaleString("en-US");
export const usd0 = (v: number | null | undefined) =>
  v == null || isNaN(v) ? "—" : (v < 0 ? "-$" : "$") + Math.abs(Math.round(v)).toLocaleString("en-US");
export const pct = (v: number | null | undefined, d = 0) =>
  v == null || !isFinite(v) ? "—" : (v * 100).toFixed(d) + "%";
export const signo = (v: number, f: (x: number) => string) => (v > 0 ? "+" : "") + f(v);
export const colorDe = (v: number | null | undefined) =>
  v == null || Math.abs(v) < 1e-9 ? "var(--text-secondary)" : v > 0 ? "var(--positive)" : "var(--negative)";

// ───────────────────────────── estilos ─────────────────────────────
export const card: CSSProperties = {
  background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 16,
};
export const th: CSSProperties = {
  padding: "6px 8px", fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", textAlign: "right",
  borderBottom: "1px solid var(--border-medium)", whiteSpace: "nowrap", position: "sticky", top: 0,
  background: "var(--bg-surface)",
};
export const td: CSSProperties = {
  padding: "5px 8px", fontSize: 12, textAlign: "right", borderBottom: "1px solid var(--border-subtle)",
  whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums",
};
export const tdL: CSSProperties = { ...td, textAlign: "left" };
export const filaTotal: CSSProperties = { fontWeight: 700, background: "var(--bg-elevated)" };
export const boton: CSSProperties = {
  padding: "6px 12px", fontSize: 12, borderRadius: 6, border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)", cursor: "pointer",
};
export const botonPrimario: CSSProperties = { ...boton, background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" };
export const select: CSSProperties = { ...boton, padding: "5px 8px" };
export const tooltipStyle = {
  contentStyle: { background: "var(--bg-input)", border: "1px solid var(--border-medium)", borderRadius: 6, fontSize: 12 },
  labelStyle: { color: "var(--text-primary)", fontWeight: 700 },
};

export function Tabla({ children, minWidth = 900 }: { children: ReactNode; minWidth?: number }) {
  return (
    <div style={{ overflowX: "auto", border: "1px solid var(--border-subtle)", borderRadius: 8, background: "var(--bg-surface)" }}>
      <table style={{ borderCollapse: "collapse", width: "100%", minWidth }}>{children}</table>
    </div>
  );
}

export function Kpi({ titulo, valor, sub, color }: { titulo: string; valor: string; sub?: ReactNode; color?: string }) {
  return (
    <div style={{ ...card, padding: 14, minWidth: 0 }}>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: ".04em" }}>{titulo}</div>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 4, color: color ?? "var(--text-primary)" }}>{valor}</div>
      {sub && <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

export function Aviso({ children, tipo = "info" }: { children: ReactNode; tipo?: "info" | "alerta" | "error" }) {
  const c = tipo === "error" ? "var(--negative)" : tipo === "alerta" ? "var(--warning)" : "var(--brand)";
  return (
    <div style={{ borderLeft: `3px solid ${c}`, background: "var(--bg-elevated)", padding: "8px 12px",
                  borderRadius: 4, fontSize: 12, color: "var(--text-primary)", margin: "8px 0" }}>{children}</div>
  );
}

const ESTADOS = ["supera", "rn_arriba_ingreso_abajo", "cerca", "debajo", "nuevo", "sin_actividad"] as const;
export function Estado({ e, cerrado }: { e: string; cerrado?: boolean }) {
  const te = useTranslations("pacing.estado");
  const c: Record<string, string> = {
    supera: "var(--positive)", rn_arriba_ingreso_abajo: "var(--warning)", cerca: "var(--brand)",
    debajo: "var(--negative)", nuevo: "var(--positive)", sin_actividad: "var(--text-secondary)",
  };
  if (cerrado) return <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{te("cerrado")}</span>;
  const clave = (ESTADOS as readonly string[]).includes(e) ? e as typeof ESTADOS[number] : "sin_actividad";
  return <span style={{ fontSize: 11, fontWeight: 600, color: c[clave] }}>{te(clave)}</span>;
}

// ───────────────────────────── el marco ─────────────────────────────
export function PacingShell({ tab, children }: { tab: PacingTab; children: ReactNode }) {
  const t = useTranslations("pacing");
  const [filtros, setF] = useState<Filtros>(INICIAL);
  const [listo, setListo] = useState(false);
  const [datos, setDatos] = useState<PacingAnalisis | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { setF(leerFiltros()); setListo(true); }, []);
  const setFiltros = useCallback((f: Partial<Filtros>) => {
    setF(prev => { const n = { ...prev, ...f }; guardarFiltros(n); return n; });
  }, []);
  const recargar = useCallback(() => setTick(x => x + 1), []);

  useEffect(() => {
    if (!listo) return;
    let vivo = true;
    setCargando(true); setError(null);
    getPacingAnalisis(filtros)
      .then(d => { if (vivo) setDatos(d); })
      .catch(e => { if (vivo) setError(String(e?.message ?? e)); })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [filtros, listo, tick]);

  const valor = useMemo(() => ({ datos, cargando, error, filtros, setFiltros, recargar }),
    [datos, cargando, error, filtros, setFiltros, recargar]);
  const anios = datos?.anios ?? [];

  return (
    <PacingCtx.Provider value={valor}>
      <div style={{ padding: "16px 20px", maxWidth: 1600, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>{t("titulo")}</h1>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
              {datos && !datos.vacio
                ? t("subtitulo", { corte: datos.corte ?? "—", fotos: datos.fotos.length, reservas: n0(datos.reservas.cuenta) })
                : t("subtituloVacio")}
            </div>
          </div>
          {tab !== "cargas" && !SIN_FILTROS.includes(tab) && datos && !datos.vacio && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <label style={{ fontSize: 12 }}>{t("filtros.anio")}{" "}
                <select style={select} value={datos.anio ?? ""} onChange={e => setFiltros({ year: Number(e.target.value) })}>
                  {anios.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </label>
              <div style={{ display: "flex", border: "1px solid var(--border-medium)", borderRadius: 6, overflow: "hidden" }}>
                {(["total", "rooms"] as const).map(k => (
                  <button key={k} onClick={() => setFiltros({ kind: k })}
                    style={{ ...boton, border: "none", borderRadius: 0,
                             background: filtros.kind === k ? "var(--brand)" : "var(--bg-surface)",
                             color: filtros.kind === k ? "#fff" : "var(--text-primary)" }}>
                    {t(k === "total" ? "filtros.total" : "filtros.rooms")}
                  </button>
                ))}
              </div>
              <label style={{ fontSize: 12 }}>{t("filtros.escenario")}{" "}
                <select style={select} value={filtros.escenario} onChange={e => setFiltros({ escenario: e.target.value as PacingEscenario })}>
                  {(["avail", "add", "mult", "otb"] as const).map(k => <option key={k} value={k}>{t(`escenarios.${k}`)}</option>)}
                </select>
              </label>
              <label style={{ fontSize: 12 }}>{t("filtros.fuente")}{" "}
                <select style={select} value={filtros.fuente} onChange={e => setFiltros({ fuente: e.target.value as PacingFuente })}>
                  {(["auto", "snap", "resv", "rm"] as const).map(k => <option key={k} value={k}>{t(`fuentes.${k}`)}</option>)}
                </select>
              </label>
            </div>
          )}
        </div>

        <nav style={{ display: "flex", gap: 2, borderBottom: "1px solid var(--border-subtle)", margin: "14px 0 16px", overflowX: "auto" }}>
          {TABS.map(k => (
            <Link key={k} href={`/pacing/${k}`} style={{
              padding: "8px 12px", fontSize: 12, whiteSpace: "nowrap", textDecoration: "none",
              color: k === tab ? "var(--text-primary)" : "var(--text-secondary)", fontWeight: k === tab ? 600 : 400,
              borderBottom: `2px solid ${k === tab ? "var(--brand)" : "transparent"}`,
            }}>{t(`tabs.${k}`)}</Link>
          ))}
        </nav>

        {error && <Aviso tipo="error">{error}</Aviso>}
        {cargando && !datos && <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("cargando")}</div>}
        {tab !== "cargas" && datos?.vacio && (
          <Aviso tipo="alerta">{t("sinDatos")} <Link href="/pacing/cargas">{t("irACargas")}</Link></Aviso>
        )}
        {(tab === "cargas" || (datos && !datos.vacio)) && children}
      </div>
    </PacingCtx.Provider>
  );
}
