"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getCapitalDetail, createCapitalProject, updateCapitalProject, deleteCapitalProject,
  downloadCapitalExcel, uploadCapitalExcel,
  type CapitalDetail, type CapitalProjectRow, type CapitalPatch,
} from "@/lib/api";
import { GOLD } from "./bloques";

const MESES = ["jan", "feb", "mar", "apr", "may", "jun",
  "jul", "aug", "sep", "oct", "nov", "dec"] as const;
const ETIQ_FALLBACK = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
/** Proyecto + 12 meses + Total + la columna de borrar. Derivado y no quemado:
 *  el 15 a mano ya se había quedado viejo una vez. */
const COLUMNAS = 1 + ETIQ_FALLBACK.length + 1 + 1;

/** Dólares, sin centavos. El cero sale vacío en las celdas de captura para que
 *  se vea de un golpe en qué meses cae el gasto; en los totales sí se escribe. */
const dinero = (v: number) => v ? `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "";
const dineroTot = (v: number) => `$${(v || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

const th: React.CSSProperties = {
  padding: "7px 6px", fontSize: 10, fontWeight: 800, textAlign: "right",
  color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: 0.4,
};
const thL: React.CSSProperties = { ...th, textAlign: "left" };

const botonSec: React.CSSProperties = {
  padding: "6px 12px", fontSize: 11.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
  background: "var(--bg-input)", color: "var(--text-primary)", border: "1px solid var(--border-medium)",
};

/**
 * Detalle de proyectos de capital: qué se compra, en qué área, en qué mes.
 *
 * Editable en el lugar donde se presenta. La lista se arma acá y no en un Excel
 * aparte, que era el problema: el total llegaba al presupuesto pero el "cuándo"
 * se quedaba afuera y no había forma de cruzarlo con la caja.
 *
 * Cada celda guarda al salir del campo (no hay botón de guardar). Si el guardado
 * falla, el valor vuelve al que tenía y se avisa — nunca queda en pantalla un
 * número que no está en la base.
 */
export function CapitalDetalle({ scenarioId, etiqueta }: { scenarioId: string; etiqueta: string }) {
  const tc = useTranslations("common");
  const t = useTranslations("junta");
  const tm = useTranslations("months");
  const ETIQ = (tm.raw("short") as string[]) ?? ETIQ_FALLBACK;
  const [data, setData] = useState<CapitalDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const archivo = useRef<HTMLInputElement>(null);

  /* El encabezado de la tabla es pegajoso (`thead th { position: sticky }`), así
     que al bajar tapaba la banda del área que quedaba justo debajo — por eso la
     primera, Navy Fleet, se veía "sin nombre". La banda también se fija, pegada
     debajo del encabezado: además de no perderse, ahora se sabe siempre en qué
     área se está parado. El desnivel se mide del DOM en vez de quemarlo, para
     que no se rompa si cambia el alto del encabezado. */
  const thead = useRef<HTMLTableSectionElement>(null);
  const [topArea, setTopArea] = useState(74);
  useEffect(() => {
    const medir = () => {
      const th0 = thead.current?.querySelector("th");
      if (!th0 || !thead.current) return;
      const top = parseFloat(getComputedStyle(th0).top);
      setTopArea((Number.isFinite(top) ? top : 44) + thead.current.offsetHeight);
    };
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, [data]);

  const cargar = useCallback(async () => {
    if (!scenarioId) return;
    setCargando(true); setError(null);
    try { setData(await getCapitalDetail(scenarioId)); }
    catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setCargando(false); }
  }, [scenarioId, tc]);
  useEffect(() => { cargar(); }, [cargar]);

  /** Guarda un campo y refresca los totales. Ante error, recarga: es preferible
   *  perder la edición a mostrar un total que no cuadra con lo guardado. */
  const guardar = async (id: string, patch: CapitalPatch) => {
    setGuardando(id);
    try { await updateCapitalProject(scenarioId, id, patch); await cargar(); }
    catch (e) { setError(e instanceof Error ? e.message : t("saveFailed")); await cargar(); }
    finally { setGuardando(null); }
  };

  const agregar = async (area: string) => {
    // Al final de TODO, no al final del área: `sort_order` no es único, y darle
    // «el último del área + 1» lo hacía chocar con el primero de la siguiente.
    // Con el empate, el orden dentro del área lo desempataba el id —un uuid— y
    // los renglones se barajaban entre recargas. La pantalla y el Excel agrupan
    // por área igual, así que el renglón nuevo aparece donde tiene que aparecer.
    const orden = Math.max(0, ...(data?.entries.map(e => e.sort_order) ?? [])) + 1;
    try { await createCapitalProject(scenarioId, { area, name: "", sort_order: orden }); await cargar(); }
    catch (e) { setError(e instanceof Error ? e.message : t("addFailed")); }
  };

  const bajar = async () => {
    setError(null);
    try {
      const blob = await downloadCapitalExcel(scenarioId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "Capital Project.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : t("downloadFailed")); }
  };

  const subir = async (file: File) => {
    // Reemplaza la lista completa: se avisa antes, porque lo que se borró en el
    // Excel se borra acá y eso no se deshace.
    if (!confirm(t("replaceConfirm", { archivo: file.name, n: data?.entries.length ?? 0, escenario: etiqueta }))) return;
    setError(null); setCargando(true);
    try {
      const antes = data?.entries.length ?? 0;
      const r = await uploadCapitalExcel(scenarioId, file);
      // Se dice el antes y el después, sin interpretar por qué cambió: los que
      // faltan pueden ser renglones vacíos que el Excel no lleva, o filas que el
      // dueño borró a propósito, y desde acá no se distinguen.
      setAviso(t("uploaded", { n: r.count, total: r.total.toLocaleString("en-US", { maximumFractionDigits: 0 }) })
        + (r.count !== antes ? t("uploadedBefore", { antes }) : ""));
      await cargar();
    } catch (e) { setError(e instanceof Error ? e.message : t("uploadFailed")); setCargando(false); }
  };

  const borrar = async (row: CapitalProjectRow) => {
    if (row.name && !confirm(t("deleteConfirm", { nombre: row.name }))) return;
    try { await deleteCapitalProject(scenarioId, row.id); await cargar(); }
    catch (e) { setError(e instanceof Error ? e.message : t("deleteFailed")); }
  };

  if (cargando && !data) return <div style={{ padding: 20, color: "var(--text-secondary)" }}>{tc("loading")}</div>;
  if (error && !data) return <div style={{ padding: 20, color: "var(--negative)" }}>{error}</div>;
  if (!data) return null;

  // Áreas en el orden en que aparecen los renglones — el orden en que se presenta.
  const areas = data.areas.map(a => a.area);
  const porArea = (a: string) => data.entries.filter(e => (e.area || t("noArea")) === a);

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
        <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
          {t("projectsInAreas", { proyectos: data.entries.length, areas: areas.length })} · {etiqueta}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="no-print" onClick={bajar} style={botonSec}>⤓ {t("downloadExcel")}</button>
          <button className="no-print" onClick={() => archivo.current?.click()} style={botonSec}>⤒ {t("uploadExcel")}</button>
          <input ref={archivo} type="file" accept=".xlsx" style={{ display: "none" }}
            onChange={e => { const f = e.target.files?.[0]; e.target.value = ""; if (f) subir(f); }} />
          <div className="mono" style={{ fontSize: 20, fontWeight: 800, color: GOLD }}>
            {dineroTot(data.total)}
          </div>
        </div>
      </div>

      {aviso && (
        <div className="no-print" style={{ marginBottom: 10, padding: "8px 12px", borderRadius: 6, fontSize: 12,
          background: "var(--bg-input)", border: "1px solid var(--border-medium)", color: "var(--text-secondary)" }}>
          {aviso}
        </div>
      )}

      {error && (
        <div className="no-print" style={{ marginBottom: 10, padding: "8px 12px", borderRadius: 6, fontSize: 12,
          background: "var(--bg-input)", border: "1px solid var(--negative)", color: "var(--negative)" }}>
          {error}
        </div>
      )}

      <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
        <table className="fin-table" style={{ width: "100%", minWidth: 1080 }}>
          <thead ref={thead}>
            <tr>
              <th style={{ ...thL, minWidth: 230 }}>{t("project")}</th>
              {ETIQ.map(m => <th key={m} style={{ ...th, minWidth: 66 }}>{m}</th>)}
              <th style={{ ...th, color: GOLD }}>{tc("total")}</th>
              <th className="no-print" style={{ ...th, width: 34 }} />
            </tr>
          </thead>
          <tbody>
            {areas.map(area => {
              const filas = porArea(area);
              const tot = data.areas.find(a => a.area === area);
              return (
                <>
                  <tr key={`a-${area}`}>
                    <td colSpan={COLUMNAS} style={{
                      position: "sticky", top: topArea, zIndex: 1,
                      padding: "8px 10px", fontSize: 11, fontWeight: 800,
                      color: GOLD, textTransform: "uppercase", letterSpacing: 0.6,
                      // Fondo sólido, no transparente: la fila se monta sobre las
                      // otras al fijarse y sin relleno se leerían encimadas.
                      background: "var(--bg-elevated)",
                      borderTop: "2px solid var(--border-medium)",
                      borderBottom: `1px solid ${GOLD}44`,
                    }}>
                      {area}
                    </td>
                  </tr>
                  {filas.map(row => (
                    <tr key={row.id} style={{ borderTop: "1px solid var(--border-subtle)",
                      opacity: guardando === row.id ? 0.5 : 1 }}>
                      <td style={{ padding: "3px 6px" }}>
                        <Texto valor={row.name} placeholder={t("projectName")}
                          onGuardar={v => guardar(row.id, { name: v })} />
                      </td>
                      {MESES.map(m => (
                        <td key={m} style={{ padding: "3px 4px" }}>
                          <Numero valor={row[m]} onGuardar={v => guardar(row.id, { [m]: v } as CapitalPatch)} />
                        </td>
                      ))}
                      <td className="mono" style={{ padding: "3px 6px", textAlign: "right", fontWeight: 800 }}>
                        {dinero(row.total)}
                      </td>
                      <td className="no-print" style={{ padding: "3px 4px", textAlign: "center" }}>
                        <button onClick={() => borrar(row)} title={t("delete")}
                          style={{ background: "none", border: "none", cursor: "pointer",
                            color: "var(--text-disabled)", fontSize: 14, lineHeight: 1 }}>×</button>
                      </td>
                    </tr>
                  ))}
                  <tr key={`t-${area}`} style={{ borderTop: "1px solid var(--border-medium)" }}>
                    <td style={{ padding: "4px 6px" }}>
                      <button className="no-print" onClick={() => agregar(area)}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 0,
                          fontSize: 11.5, fontWeight: 700, color: "var(--brand)" }}>
                        {t("addTo", { area })}
                      </button>
                    </td>
                    {MESES.map(m => (
                      <td key={m} className="mono" style={{ padding: "4px 4px", textAlign: "right",
                        fontSize: 11.5, fontWeight: 700, color: "var(--text-secondary)" }}>
                        {dinero(tot?.[m] ?? 0)}
                      </td>
                    ))}
                    <td className="mono" style={{ padding: "4px 6px", textAlign: "right", fontWeight: 800, color: GOLD }}>
                      {dineroTot(tot?.total ?? 0)}
                    </td>
                    <td className="no-print" />
                  </tr>
                </>
              );
            })}
            <tr style={{ borderTop: "2px solid var(--border-medium)" }}>
              <td style={{ padding: "9px 6px", fontWeight: 800 }}>{t("totalInvestment")}</td>
              {MESES.map(m => (
                <td key={m} className="mono" style={{ padding: "9px 4px", textAlign: "right", fontWeight: 800 }}>
                  {dinero(data.months[m] ?? 0)}
                </td>
              ))}
              <td className="mono" style={{ padding: "9px 6px", textAlign: "right", fontWeight: 800, color: GOLD }}>
                {dineroTot(data.total)}
              </td>
              <td className="no-print" />
            </tr>
          </tbody>
        </table>
      </div>

      <NuevaArea onCrear={async nombre => { await agregar(nombre); }} />

      <div style={{ marginTop: 14, fontSize: 11.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>
        {t("capitalFootNote")}
      </div>
    </>
  );
}

/** Campo de texto que guarda al salir. Mantiene su propio borrador para no
 *  pelear con el refresco: si guardara en cada tecla, cada letra sería un viaje.
 *  Va alineado a la izquierda con estilo explícito — la clase `fin-input` alinea
 *  a la derecha, que es lo correcto para montos y lo contrario para un nombre. */
function Texto({ valor, placeholder, onGuardar }: {
  valor: string; placeholder?: string; onGuardar: (v: string) => void;
}) {
  const [v, setV] = useState(valor);
  useEffect(() => { setV(valor); }, [valor]);
  return (
    <input className="fin-input" value={v} placeholder={placeholder}
      onChange={e => setV(e.target.value)}
      onBlur={() => { if (v !== valor) onGuardar(v); }}
      onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      style={{ width: "100%", fontSize: 12.5, padding: "3px 6px", border: "1px solid transparent",
        background: "transparent", color: "var(--text-primary)", textAlign: "left" }}
      onFocus={e => { e.target.style.borderColor = "var(--border-medium)"; e.target.style.background = "var(--bg-input)"; }}
      onBlurCapture={e => { e.target.style.borderColor = "transparent"; e.target.style.background = "transparent"; }} />
  );
}

/** Celda de monto. Vacía cuando es cero: una tabla de 12 meses llena de ceros
 *  esconde justamente lo que se quiere ver, que es en qué meses cae el gasto. */
function Numero({ valor, onGuardar }: { valor: number; onGuardar: (v: number) => void }) {
  // En reposo se muestra con $ y separadores; al entrar al campo se muestra el
  // número pelado, que es lo que se puede escribir encima sin pelear con el
  // formato. Escribir "$1,500" también funciona: se limpia al guardar.
  const [editando, setEditando] = useState(false);
  const [v, setV] = useState(valor ? String(valor) : "");
  useEffect(() => { if (!editando) setV(valor ? String(valor) : ""); }, [valor, editando]);
  return (
    <input className="fin-input mono" inputMode="decimal"
      value={editando ? v : dinero(valor)}
      onChange={e => setV(e.target.value)}
      onFocus={e => {
        setEditando(true); setV(valor ? String(valor) : "");
        e.target.style.borderColor = "var(--border-medium)"; e.target.style.background = "var(--bg-input)";
        requestAnimationFrame(() => e.target.select());
      }}
      onBlur={e => {
        setEditando(false);
        const n = parseFloat(v.replace(/[,$\s]/g, "")) || 0;
        if (n !== valor) onGuardar(n);
        e.target.style.borderColor = "transparent"; e.target.style.background = "transparent";
      }}
      onKeyDown={e => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      style={{ width: "100%", fontSize: 12, padding: "3px 5px", textAlign: "right",
        border: "1px solid transparent", background: "transparent", color: "var(--text-primary)" }} />
  );
}

function NuevaArea({ onCrear }: { onCrear: (nombre: string) => Promise<void> }) {
  const t = useTranslations("junta");
  const tc = useTranslations("common");
  const [abierto, setAbierto] = useState(false);
  const [nombre, setNombre] = useState("");
  if (!abierto) {
    return (
      <button className="no-print" onClick={() => setAbierto(true)}
        style={{ marginTop: 12, padding: "6px 12px", fontSize: 11.5, fontWeight: 700, borderRadius: 5,
          cursor: "pointer", background: "var(--bg-input)", color: "var(--text-primary)",
          border: "1px solid var(--border-medium)" }}>
        {t("newArea")}
      </button>
    );
  }
  return (
    <div className="no-print" style={{ marginTop: 12, display: "flex", gap: 6 }}>
      <input className="fin-input" autoFocus value={nombre} placeholder={t("areaName")}
        onChange={e => setNombre(e.target.value)}
        onKeyDown={async e => { if (e.key === "Enter" && nombre.trim()) { await onCrear(nombre.trim()); setNombre(""); setAbierto(false); } }}
        style={{ fontSize: 12.5, padding: "5px 8px", minWidth: 220 }} />
      <button onClick={async () => { if (nombre.trim()) { await onCrear(nombre.trim()); setNombre(""); setAbierto(false); } }}
        style={{ padding: "5px 12px", fontSize: 11.5, fontWeight: 700, borderRadius: 5, cursor: "pointer",
          background: "var(--brand)", color: "#fff", border: "1px solid var(--brand)" }}>{t("create")}</button>
      <button onClick={() => { setAbierto(false); setNombre(""); }}
        style={{ padding: "5px 12px", fontSize: 11.5, borderRadius: 5, cursor: "pointer",
          background: "transparent", color: "var(--text-secondary)", border: "1px solid var(--border-medium)" }}>{tc("cancel")}</button>
    </div>
  );
}
