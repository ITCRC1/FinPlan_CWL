"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import type { PLColumn, PayrollDeptReport, PLMonthly, CashFlowBudget, PLByDept } from "@/lib/api";
import type { Version } from "./versiones";

/**
 * Bloques de contenido de la Presentación a la Junta.
 *
 * Todos trabajan sobre una SERIE: la PRIMERA columna es la que se está
 * presentando (el driver) y va resaltada; las demás son comparaciones, en el
 * orden que el usuario las eligió. La variación se lee entre la primera y la
 * segunda, que es la comparación principal.
 */

export const GOLD = "#c8a24a";
const MESES_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

export const linea = (c: PLColumn | undefined, code: string) =>
  c?.lines.find(l => l.line_code === code)?.amount_usd ?? 0;

export const dinero = (v: number) => {
  const s = "$" + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
  return Math.abs(v) < 0.5 ? "—" : (v < 0 ? `(${s})` : s);
};
const conteo = (v: number) => Math.round(v).toLocaleString("en-US");
const pct1 = (v: number) => v.toFixed(1) + "%";
const money2 = (v: number) => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const th: React.CSSProperties = { padding: "7px 9px", fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.3, textAlign: "right", whiteSpace: "nowrap" };
const thL: React.CSSProperties = { ...th, textAlign: "left" };
const td: React.CSSProperties = { padding: "7px 9px", fontSize: 12.5, textAlign: "right", fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap" };
const tdL: React.CSSProperties = { ...td, textAlign: "left" };
const sub: React.CSSProperties = { ...td, color: "var(--text-secondary)" };

function Vacio({ que }: { que: string }) {
  const t = useTranslations("junta");
  return (
    <div style={{ border: "1px dashed var(--border-medium)", borderRadius: 8, padding: "18px", textAlign: "center", color: "var(--text-secondary)", fontSize: 12.5 }}>
      {t("noDataFor", { que })}
    </div>
  );
}

/** Encabezado: el escenario que se presenta y, detrás, cada comparación seguida
 *  de su variación CONTRA ÉL. Así la junta lee "contra el presupuesto anterior
 *  estamos +X, contra el forecast +Y" sin tener que restar de cabeza. */
function Cabecera({ vs, primera }: { vs: Version[]; primera: string }) {
  return (
    <thead>
      <tr>
        <th style={{ ...thL, minWidth: 190, width: "22%" }}>{primera}</th>
        <th style={{ ...th, color: "var(--brand)" }}>{vs[0]?.label}</th>
        {vs.slice(1).map(v => (
          <>
            <th key={v.id} style={th}>{v.label}</th>
            <th key={`${v.id}-d`} style={{ ...th, color: GOLD }}>Δ vs {vs[0]?.label}</th>
          </>
        ))}
      </tr>
    </thead>
  );
}

/**
 * Variación relativa, o `null` cuando no se puede decir sin mentir.
 *
 * Dos trampas, las dos vistas en esta presentación:
 *
 * Base NEGATIVA: `(a/b − 1)` cambia de sentido y el % contradice al monto que
 * tiene al lado. Un GOP que sube de −$100,000 a −$50,000 mostraba «$50,000» en
 * verde con un «−50.0%». Se divide entre |b|, que conserva el signo de la
 * mejora.
 *
 * Base CASI cero: el guard de `b !== 0` no alcanza. La fila «Resto» del resumen
 * es una resta de tres flotantes y en un hotel sin otros ingresos da residuos
 * tipo 1.4e-10 en vez de cero exacto; ahí el monto salía «—» y al lado un
 * «+2,850,000,000,000.0%». `flowThrough` ya blindaba esto con un umbral; acá
 * faltaba.
 */
export function relativo(a: number, b: number): number | null {
  if (Math.abs(b) < 1) return null;
  return (a - b) / Math.abs(b) * 100;
}

/** Variación del escenario presentado contra UNA comparación: monto y %, juntos.
 *  En porcentajes va en PUNTOS y sin ratio: decir que la ocupación "subió 41%"
 *  cuando pasó de 30.8% a 43.5% confunde; son 12.7 puntos. */
function CeldaVar({ a, b, puntos, fmt }: {
  a: number; b: number; puntos?: boolean; fmt: (v: number) => string;
}) {
  const d = a - b;
  const rel = puntos ? null : relativo(a, b);
  const color = Math.abs(d) < 0.005 ? "var(--text-disabled)" : d > 0 ? "var(--positive, #1A7F4B)" : "var(--negative)";
  return (
    <td className="mono" style={{ ...td, color }}>
      {puntos ? `${d >= 0 ? "+" : ""}${d.toFixed(1)} pp` : fmt(d)}
      {rel !== null && (
        <span style={{ fontSize: 10.5, opacity: 0.75, marginLeft: 6 }}>
          {rel >= 0 ? "+" : ""}{rel.toFixed(1)}%
        </span>
      )}
    </td>
  );
}

type Formato = "dinero" | "conteo" | "pct" | "money2" | "razon";
const razon = (v: number) => v.toFixed(2);
const fmtDe = (f: Formato) =>
  f === "conteo" ? conteo : f === "pct" ? pct1 : f === "money2" ? money2 : f === "razon" ? razon : dinero;

export type FilaSerie = {
  /** Clave de traducción del rótulo. Ausente = el `label` es DATO (nombre de
   *  departamento o de línea que la API ya nombra) y no se traduce.
   *  `@common.x` significa que la clave vive en el namespace compartido. */
  lk?: string;
  label: string; formato: Formato;
  /** La versión llega como segundo argumento para las filas que no salen del
   *  P&L —el desglose por departamento, p.ej.— y necesitan buscar por escenario. */
  get: (c?: PLColumn, v?: Version) => number;
  fuerte?: boolean; grupo?: string; puntos?: boolean; sangria?: boolean;
};

/** Tabla genérica de la serie: una fila por indicador, una columna por versión. */
export function TablaSerie({ vs, filas, primera }: { vs: Version[]; filas: FilaSerie[]; primera: string }) {
  const t = useTranslations("junta");
  const tc = useTranslations("common");
  if (!vs.length || !vs.some(v => v.col)) return <Vacio que={t("thisSection")} />;
  return (
    <table className="fin-table" style={{ width: "100%" }}>
      <Cabecera vs={vs} primera={primera} />
      <tbody>
        {filas.map(f => {
          const fmt = fmtDe(f.formato);
          return (
            <>
              {f.grupo && (
                <tr key={`g-${f.grupo}`}>
                  <td colSpan={vs.length * 2} style={{ padding: "12px 9px 3px", fontSize: 10, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {f.grupo}
                  </td>
                </tr>
              )}
              <tr key={f.label} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ ...tdL, fontWeight: f.fuerte ? 800 : 600, paddingLeft: f.sangria ? 24 : undefined }}>{f.lk ? (f.lk.startsWith("@") ? tc(f.lk.slice(8)) : t(f.lk)) : f.label}</td>
                <td className="mono" style={{ ...td, fontWeight: f.fuerte ? 800 : 700 }}>
                  {vs[0]?.col ? fmt(f.get(vs[0].col, vs[0])) : "—"}
                </td>
                {vs.slice(1).map(v => (
                  <>
                    <td key={v.id} className="mono" style={sub}>{v.col ? fmt(f.get(v.col, v)) : "—"}</td>
                    {v.col && vs[0]?.col
                      ? <CeldaVar key={`${v.id}-d`} a={f.get(vs[0].col, vs[0])} b={f.get(v.col, v)} puntos={f.puntos} fmt={fmt} />
                      : <td key={`${v.id}-d`} style={td}>—</td>}
                  </>
                ))}
              </tr>
            </>
          );
        })}
      </tbody>
    </table>
  );
}

// ─── Resumen Ejecutivo (slide 45) ────────────────────────────────────────────
const trevpor = (c?: PLColumn) => {
  const o = c?.kpis.rooms_occupied ?? 0;
  return o ? linea(c, "TOTAL_REVENUES") / o : 0;
};

export const FILAS_RESUMEN: FilaSerie[] = [
  { grupo: "Volumen", label: "Habitaciones disponibles", formato: "conteo", get: c => c?.kpis.rooms_available ?? 0 },
  { label: "Habitaciones ocupadas", formato: "conteo", get: c => c?.kpis.rooms_occupied ?? 0 },
  { label: "Huéspedes", lk: "@common.guests", formato: "conteo", get: c => c?.kpis.guests ?? 0 },
  { label: "Ocupación", lk: "occupancy", formato: "pct", puntos: true, get: c => (c?.kpis.occupancy_pct ?? 0) * 100 },
  { grupo: "Precio", label: "ADR", formato: "money2", get: c => c?.kpis.adr ?? 0 },
  { label: "RevPAR", formato: "money2", get: c => c?.kpis.revpar ?? 0 },
  { label: "TRevPOR", formato: "money2", get: trevpor },
  { grupo: "Ingresos", label: "Ingreso total", formato: "dinero", fuerte: true, get: c => linea(c, "TOTAL_REVENUES") },
  { label: "Habitaciones", formato: "dinero", get: c => linea(c, "REV_ROOMS") },
  { label: "A&B", formato: "dinero", get: c => linea(c, "REV_FB") },
  { label: "Resto", formato: "dinero", get: c => linea(c, "TOTAL_REVENUES") - linea(c, "REV_ROOMS") - linea(c, "REV_FB") },
  { grupo: "Resultado", label: "GOP", formato: "dinero", fuerte: true, get: c => linea(c, "GOP") },
  { label: "Margen GOP", formato: "pct", puntos: true, get: c => { const r = linea(c, "TOTAL_REVENUES"); return r ? linea(c, "GOP") / r * 100 : 0; } },
  { label: "EBITDA", formato: "dinero", fuerte: true, get: c => linea(c, "EBITDA_BEFORE") },
  { label: "Utilidad neta", formato: "dinero", fuerte: true, get: c => linea(c, "NET_PROFIT") },
];

/** Volumen y precio van SEPARADOS: son dos preguntas distintas —cuánta gente
 *  viene y a qué precio se le vende— y mezclarlas en una tabla obliga a la junta
 *  a saltar entre unidades. En el PowerPoint también eran diapositivas aparte. */
export const FILAS_VOLUMEN: FilaSerie[] = [
  { label: "Habitaciones disponibles", lk: "roomsAvailable", formato: "conteo", get: c => c?.kpis.rooms_available ?? 0 },
  { label: "Habitaciones ocupadas", lk: "roomsOccupied", formato: "conteo", fuerte: true, get: c => c?.kpis.rooms_occupied ?? 0 },
  { label: "Huéspedes", lk: "@common.guests", formato: "conteo", get: c => c?.kpis.guests ?? 0 },
  { label: "Ocupación", lk: "occupancy", formato: "pct", puntos: true, fuerte: true, get: c => (c?.kpis.occupancy_pct ?? 0) * 100 },
  { label: "Huéspedes por habitación ocupada", lk: "guestsPerOccupiedRoom", formato: "razon", get: c => {
      const o = c?.kpis.rooms_occupied ?? 0; return o ? (c?.kpis.guests ?? 0) / o : 0; } },
];

export const FILAS_PRECIO: FilaSerie[] = [
  { label: "ADR", formato: "money2", fuerte: true, get: c => c?.kpis.adr ?? 0 },
  { label: "RevPAR", formato: "money2", fuerte: true, get: c => c?.kpis.revpar ?? 0 },
  { label: "TRevPOR (ingreso total por hab. ocupada)", lk: "trevporLong", formato: "money2", get: trevpor },
  { label: "Ingreso de habitaciones", lk: "roomsRevenue", formato: "dinero", get: c => linea(c, "REV_ROOMS") },
  { label: "Ingreso fuera de habitación por hab. ocupada", lk: "nonRoomRevPerOccupied", formato: "money2", get: c => {
      const o = c?.kpis.rooms_occupied ?? 0;
      return o ? (linea(c, "TOTAL_REVENUES") - linea(c, "REV_ROOMS")) / o : 0; } },
];

// ─── Estacionalidad: una fila por versión + su variación ─────────────────────
/** Doce meses por tres versiones no entran como columnas, así que se invierte:
 *  una FILA por versión y una fila de variación debajo. `modo` decide la métrica
 *  —Volumen mira ocupación, Precio mira tarifa— para no mezclar unidades. */
export function Estacionalidad({ mensuales, vs, modo }: {
  mensuales: Record<string, PLMonthly | null>; vs: Version[]; modo: "volumen" | "precio";
}) {
  const t = useTranslations("junta");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const principal = vs[0];
  if (!principal || !mensuales[principal.id]?.months?.length) return null;
  type Mes = NonNullable<PLMonthly["months"]>[number];
  const metricas = modo === "volumen"
    ? [
      // La banda nombra la MISMA métrica que el chip de `volumen.tsx`: van con
      // las mismas claves para que no digan una cosa distinta cada una.
      { lab: t("occupancy"), val: (m: Mes) => (m.kpis.occupancy_pct ?? 0) * 100, fmt: pct1, puntos: true },
      { lab: t("roomsOccupied"), val: (m: Mes) => m.kpis.rooms_occupied ?? 0, fmt: conteo },
      { lab: tc("guests"), val: (m: Mes) => m.kpis.guests ?? 0, fmt: conteo },
    ]
    : [
      { lab: "ADR", val: (m: Mes) => m.kpis.adr ?? 0, fmt: (v: number) => "$" + Math.round(v).toLocaleString("en-US") },
      { lab: "RevPAR", val: (m: Mes) => m.kpis.revpar ?? 0, fmt: (v: number) => "$" + Math.round(v).toLocaleString("en-US") },
    ];
  return (
    <>
      <div style={{ fontSize: 10.5, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5, margin: "18px 0 6px" }}>
        {t("seasonality")}
      </div>
      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table className="fin-table" style={{ width: "100%" }}>
          <thead><tr>
            <th style={{ ...thL, minWidth: 210 }}></th>
            {MESES.map(m => <th key={m} style={{ ...th, minWidth: 52 }}>{m}</th>)}
          </tr></thead>
          <tbody>
            {metricas.map(met => (
              <>
                <tr key={`h-${met.lab}`}>
                  <td colSpan={13} style={{ padding: "12px 9px 3px", fontSize: 10, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {met.lab}
                  </td>
                </tr>
                {vs.map((v, i) => {
                  const m = mensuales[v.id];
                  return (
                    <tr key={`${met.lab}-${v.id}`} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                      <td style={{ ...tdL, fontWeight: i === 0 ? 800 : 600, color: i === 0 ? "var(--brand)" : "var(--text-secondary)" }}>{v.label}</td>
                      {MESES.map((_, j) => (
                        <td key={j} className="mono" style={i === 0 ? { ...td, fontWeight: 700 } : sub}>
                          {m?.months?.[j] ? met.fmt(met.val(m.months[j])) : "—"}
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {vs.slice(1).map(v => {
                  const a = mensuales[principal.id], b = mensuales[v.id];
                  if (!a || !b) return null;
                  return (
                    <tr key={`d-${met.lab}-${v.id}`} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                      <td style={{ ...tdL, fontSize: 11.5, color: GOLD }}>Δ vs {v.label}</td>
                      {MESES.map((_, j) => {
                        const x = a.months?.[j], y = b.months?.[j];
                        if (!x || !y) return <td key={j} style={td}>—</td>;
                        const d = met.val(x) - met.val(y);
                        const base = met.val(y);
                        const rel = (!met.puntos && base !== 0) ? (met.val(x) / base - 1) * 100 : null;
                        const color = Math.abs(d) < 0.005 ? "var(--text-disabled)" : d > 0 ? "var(--positive, #1A7F4B)" : "var(--negative)";
                        return (
                          <td key={j} className="mono" style={{ ...td, fontSize: 11, color }}>
                            {met.puntos ? `${d >= 0 ? "+" : ""}${d.toFixed(1)}pp` : met.fmt(d)}
                            {rel !== null && <div style={{ fontSize: 9.5, opacity: 0.7 }}>{rel >= 0 ? "+" : ""}{rel.toFixed(0)}%</div>}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ─── Departamentos con Flow Through (18-29) ──────────────────────────────────
/** `key` = sufijo de la línea del P&L (REV_/OPEX_/PROFIT_); `grupo` = cómo se
 *  llama el mismo departamento en el desglose por depto. Casi siempre coinciden;
 *  Transporte es la excepción (la línea dice TRANSPORTATION, el grupo TRANSPORT). */
export const DEPARTAMENTOS = [
  { key: "ROOMS", label: "Habitaciones" },
  { key: "FB", label: "A&B" },
  { key: "PRIVATE_BAR", label: "Private Bar" },
  { key: "SPA", label: "Spa" },
  { key: "TOURS", label: "Tours y Actividades" },
  { key: "TRANSPORTATION", label: "Transporte", grupo: "TRANSPORT" },
  { key: "TIENDA", label: "Tienda" },
  { key: "RETAIL", label: "Gift Shop" },
  { key: "INNOCEANA", label: "Innoceana" },
  { key: "LAUNDRY", label: "Lavandería" },
  { key: "SUSTAINABILITY", label: "Sustainability Fee" },
  { key: "CLUB", label: "Club Madresal" },
];

/** Flow Through = cuánto de cada dólar ADICIONAL de ingreso llega al resultado.
 *
 *  El cociente EXPLOTA cuando el ingreso casi no se mueve: −$607 de variación
 *  contra +$190,324 de resultado da −31,364%. Aritmética correcta y basura como
 *  información — proyectado en una junta, peor que no mostrar nada. Si el
 *  ingreso quedó plano, la mejora vino de COSTOS y eso se dice con palabras.
 */
type FT = { pct: number } | { plano: true; dProf: number } | null;

function flowThrough(a: PLColumn, b: PLColumn, key: string): FT {
  const revA = linea(a, `REV_${key}`), revB = linea(b, `REV_${key}`);
  const dRev = revA - revB;
  const dProf = linea(a, `PROFIT_${key}`) - linea(b, `PROFIT_${key}`);
  const base = Math.max(Math.abs(revA), Math.abs(revB));
  if (base < 1) return null;
  if (Math.abs(dRev) < base * 0.02) return { plano: true, dProf };
  return { pct: dProf / dRev * 100 };
}

/**
 * Los departamentos con movimiento.
 *
 * El filtro mira ingreso, gasto Y resultado, no solo ingreso: un departamento
 * que gasta y no factura —lavandería con su ingreso ruteado al overhead, por
 * ejemplo— desaparecía del tab entero, sin botón y sin forma de mirar su
 * pérdida.
 */
function departamentosConDatos(vs: Version[]) {
  return DEPARTAMENTOS.filter(d => vs.some(v =>
    Math.abs(linea(v.col, `REV_${d.key}`)) > 0.5
    || Math.abs(linea(v.col, `OPEX_${d.key}`)) > 0.5
    || Math.abs(linea(v.col, `PROFIT_${d.key}`)) > 0.5));
}

export function Departamentos({ vs, sel, onSel, porDepto, documento }: {
  vs: Version[]; sel: string; onSel: (k: string) => void;
  porDepto: Record<string, PLByDept | null>;
  documento?: boolean;
}) {
  const t = useTranslations("junta");
  if (!vs[0]?.col) return <Vacio que={t("qDepartments")} />;
  const conDatos = departamentosConDatos(vs);
  const sela = conDatos.find(x => x.key === sel) ?? conDatos[0];
  if (!sela) return <Vacio que={t("qDepartments")} />;

  return (
    <>
      <div className="no-print" style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 14 }}>
        {conDatos.map(x => (
          <button key={x.key} onClick={() => onSel(x.key)}
            style={{
              padding: "5px 10px", fontSize: 11.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
              background: x.key === sela.key ? "var(--brand)" : "var(--bg-input)",
              color: x.key === sela.key ? "#fff" : "var(--text-primary)",
              border: `1px solid ${x.key === sela.key ? "var(--brand)" : "var(--border-medium)"}`,
            }}>{x.label}</button>
        ))}
      </div>
      {/* En documento van TODOS: esta sección absorbe una diapositiva por
          departamento del PowerPoint original, y el PDF salía con una sola
          porque el selector es de pantalla. */}
      {(documento ? conDatos : [sela]).map((d, i) => (
        <div key={d.key} style={i > 0 ? { marginTop: 28 } : undefined}>
          <UnDepartamento vs={vs} d={d} porDepto={porDepto} />
        </div>
      ))}
    </>
  );
}

function UnDepartamento({ vs, d, porDepto }: {
  vs: Version[]; d: typeof DEPARTAMENTOS[number];
  porDepto: Record<string, PLByDept | null>;
}) {
  const t = useTranslations("junta");
  const tc = useTranslations("common");
  const ult = vs[0]?.col;
  const prev = vs.length >= 2 ? vs[1]?.col : undefined;
  if (!ult) return null;

  const ft = prev ? flowThrough(ult, prev, d.key) : null;
  const pctFT = ft && "pct" in ft ? ft.pct : null;

  /** El P&L da el gasto directo del depto en UNA línea (OPEX_x). El desglose
   *  —planilla, gasto operativo, costo de venta— sale del reporte por
   *  departamento. Suman exactamente OPEX_x; si por alguna razón no cuadraran,
   *  abajo se dice en vez de repartir la diferencia a ojo.
   *
   *  El reparto entre departamentos NO va en fila aparte: es planilla, gasto o
   *  costo que se movió de depto, y entra donde corresponde según la cuenta en
   *  que cayó. Tours es el caso claro — entrega salario a otros departamentos,
   *  así que su planilla ya sale neta. Como fila suelta se leía como una
   *  categoría de gasto que no existe, y encima negativa. */
  const parte = (...campos: ("payroll" | "opex" | "cost" | "alloc_payroll" | "alloc_opex" | "alloc_cost" | "alloc_other")[]) =>
    (_c?: PLColumn, v?: Version) => {
      const g = v && porDepto[v.id]?.departments.find(x => x.group === (d.grupo ?? d.key));
      return g ? campos.reduce((s, k) => s + (g[k] ?? 0), 0) : 0;
    };
  const desglosado = (v?: Version) => !!(v && porDepto[v.id]);
  const hayDesglose = vs.some(desglosado);
  const planilla = parte("payroll", "alloc_payroll");
  const gastoOper = parte("opex", "alloc_opex");
  const costoVenta = parte("cost", "alloc_cost");
  const descuadre = (c?: PLColumn, v?: Version) => {
    if (!desglosado(v)) return 0;
    return linea(c, `OPEX_${d.key}`)
      - (planilla(c, v) + gastoOper(c, v) + costoVenta(c, v));
  };
  const hayDescuadre = vs.some(v => Math.abs(descuadre(v.col, v)) > 0.5);

  const filas: FilaSerie[] = [
    { label: "Ingreso", formato: "dinero", fuerte: true, get: c => linea(c, `REV_${d.key}`) },
    { label: "Gasto directo", formato: "dinero", fuerte: true, get: c => linea(c, `OPEX_${d.key}`) },
    ...(hayDesglose ? ([
      { label: "Planilla", formato: "dinero", sangria: true, get: planilla },
      { label: "Gasto operativo", formato: "dinero", sangria: true, get: gastoOper },
      { label: "Costo de venta", formato: "dinero", sangria: true, get: costoVenta },
      ...(hayDescuadre
        ? [{ label: "Sin clasificar", lk: "unclassified", formato: "dinero", sangria: true, get: descuadre }]
        : []),
    ] as FilaSerie[]) : []),
    { label: "Resultado", formato: "dinero", fuerte: true, get: c => linea(c, `PROFIT_${d.key}`) },
    {
      label: "Margen", formato: "pct", puntos: true,
      get: c => { const r = linea(c, `REV_${d.key}`); return r ? linea(c, `PROFIT_${d.key}`) / r * 100 : 0; },
    },
  ];

  return (
    <>
      <div style={{ fontSize: 15, fontWeight: 800, marginBottom: 10 }}>{d.label}</div>
      <TablaSerie vs={vs} filas={filas} primera={tc("concept")} />

      {pctFT !== null && (
        <div style={{ marginTop: 14, background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: "12px 16px" }}>
          <div style={{ fontSize: 10, fontWeight: 800, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4 }}>
            Flow Through · {vs[0].label} vs {vs[1].label}
          </div>
          <div className="mono" style={{ fontSize: 22, fontWeight: 800, color: GOLD, margin: "4px 0 6px" }}>{pct1(pctFT)}</div>
          <div style={{ fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>
            {t("flowThroughNarrative", { pct: pct1(pctFT) })}{" "}
            {pctFT >= 60 ? t("conversionHigh")
              : pctFT >= 30 ? t("conversionMid")
                : t("conversionLow")}
          </div>
        </div>
      )}
      {ft && "plano" in ft && (
        <div style={{ marginTop: 14, fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          {t.rich("flatNarrative", {
            version: vs[1].label,
            verbo: ft.dProf >= 0 ? t("improves") : t("falls"),
            monto: dinero(Math.abs(ft.dProf)),
            m: (c: React.ReactNode) => <b style={{ color: ft.dProf >= 0 ? GOLD : "var(--negative)" }}>{c}</b>,
            b: (c: React.ReactNode) => <b>{c}</b>,
          })}
        </div>
      )}
    </>
  );
}

// ─── Planilla y Headcount (30-31, 33) ────────────────────────────────────────
export function PlanillaHeadcount({ vs, reportes }: { vs: Version[]; reportes: Record<string, PayrollDeptReport | null> }) {
  const tc = useTranslations("common");
  const t = useTranslations("junta");
  const ult = vs[0];
  const rep = ult && reportes[ult.id];
  if (!rep?.depts?.length) return <Vacio que={t("qPayroll")} />;
  const orden = [...rep.depts].sort((a, b) => b.total_annual - a.total_annual);
  return (
    <>
      <table className="fin-table" style={{ width: "100%", marginBottom: 16 }}>
        <Cabecera vs={vs} primera={tc("total")} />
        <tbody>
          {([[t("people"), (r: PayrollDeptReport) => r.totals.headcount, conteo],
             [t("avgFte"), (r: PayrollDeptReport) => r.totals.fte_avg, (v: number) => v.toFixed(1)],
             [t("totalCost"), (r: PayrollDeptReport) => r.totals.total_annual, dinero]] as const).map(([lab, get, fmt]) => {
            const rp = reportes[ult.id];
            const a = rp ? get(rp) : 0;
            return (
              <tr key={lab} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ ...tdL, fontWeight: 700 }}>{lab}</td>
                <td className="mono" style={{ ...td, fontWeight: 800 }}>{rp ? fmt(a) : "—"}</td>
                {vs.slice(1).map(v => {
                  const r = reportes[v.id];
                  return (
                    <>
                      <td key={v.id} className="mono" style={sub}>{r ? fmt(get(r)) : "—"}</td>
                      {r && rp
                        ? <CeldaVar key={`${v.id}-d`} a={a} b={get(r)} fmt={fmt} />
                        : <td key={`${v.id}-d`} style={td}>—</td>}
                    </>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ fontSize: 10.5, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
        {t("byDepartment")}
      </div>
      <table className="fin-table" style={{ width: "100%" }}>
        <thead><tr>
          <th style={{ ...thL, minWidth: 190 }}>{tc("department")}</th>
          <th style={{ ...th, color: "var(--brand)" }}>{ult.label}</th>
          {vs.slice(1).map(v => (
            <>
              <th key={v.id} style={th}>{v.label}</th>
              <th key={`${v.id}-d`} style={{ ...th, color: GOLD }}>Δ vs {vs[0]?.label}</th>
            </>
          ))}
        </tr></thead>
        <tbody>
          {orden.map(dp => (
            <tr key={dp.dept_code} style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <td style={tdL}>{dp.dept_name || dp.dept_code}</td>
              <td className="mono" style={{ ...td, fontWeight: 700 }}>{dinero(dp.total_annual)}</td>
              {vs.slice(1).map(v => {
                // Se cruza por CÓDIGO de departamento: el registro es distinto en
                // cada escenario, así que por id no cruzaría nada.
                const otro = reportes[v.id]?.depts.find(x => x.dept_code === dp.dept_code);
                if (!otro) return <><td key={v.id} style={sub}>—</td><td key={`${v.id}-d`} style={td}>—</td></>;
                return (
                  <>
                    <td key={v.id} className="mono" style={sub}>{dinero(otro.total_annual)}</td>
                    <CeldaVar key={`${v.id}-d`} a={dp.total_annual} b={otro.total_annual} fmt={dinero} />
                  </>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// ─── Caja (49-50) ────────────────────────────────────────────────────────────
/** El resumen SÍ compara versiones; el detalle mes a mes queda solo del
 *  escenario presentado: doce meses por tres versiones no se lee, y el flujo de
 *  un actual cerrado al lado de un presupuesto invita a comparar cosas que no
 *  son comparables. */
export function Caja({ cajas, vs }: { cajas: Record<string, CashFlowBudget | null>; vs: Version[] }) {
  const tc = useTranslations("common");
  const t = useTranslations("junta");
  const tm = useTranslations("months");
  const MESES = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  // Doce meses por tres versiones no entra como columnas: se elige el concepto y
  // las versiones pasan a ser filas, con su Δ debajo. Mismo patrón que la
  // estacionalidad.
  const [concepto, setConcepto] = useState("ENDING_CASH");
  const principal = vs[0];
  const cf = principal && cajas[principal.id];
  if (!cf?.rows?.length) return <Vacio que={t("qCash")} />;

  const fila = (c: CashFlowBudget | null | undefined, k: string) => c?.rows.find(r => r.key === k);
  /* El motor guarda el CapEx como salida POSITIVA y lo RESTA:
       net_change = NOI − CapEx + WC + Otros   (cashflow_budget.py)
     Mostrarlo crudo hacía que la columna no sumara: con Budget 2027,
     2,065,299 + 239,894 − 783,461 daba 1,521,732 contra los 1,041,944
     impresos abajo. Se niega al mostrarlo, igual que hace la pantalla
     canónica de Cash Flow Budget, para que la junta pueda sumar la columna
     de arriba a abajo y le dé. */
  const SIGNO: Record<string, number> = { SUBTOTAL_CAPEX: -1 };
  const valor = (c: CashFlowBudget | null | undefined, k: string): number => {
    if (k === "OTROS") return otros(c);
    const r = fila(c, k);
    if (!r) return 0;
    // Los saldos no se suman: el del año es el de diciembre.
    if (k === "BEGINNING_CASH") return r.values?.[0] ?? 0;
    if (k === "ENDING_CASH") return r.values?.[11] ?? 0;
    return (r.full_year ?? 0) * (SIGNO[k] ?? 1);
  };

  /** Lo mismo pero de un mes, para la tabla de abajo: sin esto el mes a mes
   *  mostraba el CapEx con el signo contrario al del resumen de arriba, en la
   *  misma pantalla. */
  const mes = (c: CashFlowBudget | null | undefined, k: string, j: number): number => {
    if (k === "OTROS") {
      return mes(c, "NET_CHANGE", j) - mes(c, "NET_OPERATING_INCOME", j)
        - mes(c, "SUBTOTAL_CAPEX", j) - mes(c, "SUBTOTAL_WC", j);
    }
    return (fila(c, k)?.values?.[j] ?? 0) * (SIGNO[k] ?? 1);
  };
  const hayFila = (c: CashFlowBudget | null | undefined, k: string) =>
    k === "OTROS" ? !!c : !!fila(c, k);

  /* «Otros movimientos» es un residuo y no una fila del motor: ahí viven
     aportes, tipo de cambio, cuenta de casa y —el que importa— el ajuste a
     caja real de los meses cerrados. Sin esta fila, en un ACTUAL la columna
     no cerraba aunque el signo del CapEx estuviera bien. Se deriva de la
     identidad del motor para que sume por construcción. */
  const otros = (c: CashFlowBudget | null | undefined): number =>
    valor(c, "NET_CHANGE") - valor(c, "NET_OPERATING_INCOME")
    - valor(c, "SUBTOTAL_CAPEX") - valor(c, "SUBTOTAL_WC");

  const resumen = [
    { k: "NET_OPERATING_INCOME", lab: "Resultado operativo" },
    { k: "SUBTOTAL_CAPEX", lab: "Inversión de capital" },
    { k: "SUBTOTAL_WC", lab: "Capital de trabajo" },
    { k: "OTROS", lab: "Otros movimientos" },
    { k: "NET_CHANGE", lab: "Variación de caja del año", fuerte: true },
    { k: "BEGINNING_CASH", lab: "Caja inicial" },
    { k: "ENDING_CASH", lab: "Caja final", fuerte: true },
  ];

  return (
    <>
      <table className="fin-table" style={{ width: "100%", marginBottom: 20 }}>
        <thead><tr>
          <th style={{ ...thL, minWidth: 210 }}>{tc("concept")}</th>
          <th style={{ ...th, color: "var(--brand)" }}>{principal.label}</th>
          {vs.slice(1).map(v => (
            <>
              <th key={v.id} style={th}>{v.label}</th>
              <th key={`${v.id}-d`} style={{ ...th, color: GOLD }}>Δ vs {vs[0]?.label}</th>
            </>
          ))}
        </tr></thead>
        <tbody>
          {resumen.map(r => {
            const a = valor(cf, r.k);
            return (
              <tr key={r.k} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ ...tdL, fontWeight: r.fuerte ? 800 : 600 }}>{r.lab}</td>
                <td className="mono" style={{ ...td, fontWeight: r.fuerte ? 800 : 700, color: a < 0 ? "var(--negative)" : "var(--text-primary)" }}>{dinero(a)}</td>
                {vs.slice(1).map(v => {
                  const c = cajas[v.id];
                  if (!c) return <><td key={v.id} style={sub}>—</td><td key={`${v.id}-d`} style={td}>—</td></>;
                  return (
                    <>
                      <td key={v.id} className="mono" style={sub}>{dinero(valor(c, r.k))}</td>
                      <CeldaVar key={`${v.id}-d`} a={a} b={valor(c, r.k)} fmt={dinero} />
                    </>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="no-print" style={{ display: "flex", gap: 5, margin: "0 0 10px", flexWrap: "wrap" }}>
        {resumen.map(r => (
          <button key={r.k} onClick={() => setConcepto(r.k)}
            style={{
              padding: "5px 11px", fontSize: 11.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
              background: concepto === r.k ? "var(--brand)" : "var(--bg-input)",
              color: concepto === r.k ? "#fff" : "var(--text-primary)",
              border: `1px solid ${concepto === r.k ? "var(--brand)" : "var(--border-medium)"}`,
            }}>{r.lab}</button>
        ))}
      </div>
      <div style={{ fontSize: 10.5, fontWeight: 800, color: GOLD, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
        {t("monthByMonth")} · {resumen.find(r => r.k === concepto)?.lab}
      </div>
      <table className="fin-table" style={{ width: "100%" }}>
        <thead><tr>
          <th style={{ ...thL, minWidth: 210 }}></th>
          {MESES.map(m => <th key={m} style={{ ...th, minWidth: 58 }}>{m}</th>)}
          <th style={{ ...th, color: "var(--brand)" }}>{tc("year")}</th>
        </tr></thead>
        <tbody>
          {vs.map((v, i) => {
            const c = cajas[v.id];
            const hay = hayFila(c, concepto);
            return (
              <tr key={v.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ ...tdL, fontWeight: i === 0 ? 800 : 600, color: i === 0 ? "var(--brand)" : "var(--text-secondary)" }}>{v.label}</td>
                {MESES.map((_, j) => (
                  <td key={j} className="mono" style={i === 0 ? { ...td, fontWeight: 700 } : sub}>
                    {hay ? dinero(mes(c, concepto, j)) : "—"}
                  </td>
                ))}
                <td className="mono" style={{ ...td, fontWeight: 800 }}>{c ? dinero(valor(c, concepto)) : "—"}</td>
              </tr>
            );
          })}
          {vs.slice(1).map(v => {
            if (!hayFila(cf, concepto) || !hayFila(cajas[v.id], concepto)) return null;
            return (
              <tr key={`d-${v.id}`} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td style={{ ...tdL, fontSize: 11.5, color: GOLD }}>Δ vs {v.label}</td>
                {MESES.map((_, j) => {
                  const d = mes(cf, concepto, j) - mes(cajas[v.id], concepto, j);
                  const color = Math.abs(d) < 0.5 ? "var(--text-disabled)" : d > 0 ? "var(--positive, #1A7F4B)" : "var(--negative)";
                  return <td key={j} className="mono" style={{ ...td, fontSize: 11, color }}>{dinero(d)}</td>;
                })}
                <td className="mono" style={{ ...td, fontSize: 11, fontWeight: 800, color: GOLD }}>
                  {dinero(valor(cf, concepto) - valor(cajas[v.id], concepto))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
