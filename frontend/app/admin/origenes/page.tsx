"use client";
/**
 * Orígenes de datos — el puente entre las cuentas de otro sistema y las de acá.
 *
 * Oxígen y Ojochal llevan la contabilidad en QuickBooks; Corcovado va a traer la
 * suya de un backoffice por API; hoy todo entra por Excel. Lo que cambia entre
 * sistemas es el código de cuenta. El catálogo USALI de este lado no.
 *
 * Esta pantalla carga ese puente. **Es dato, no código** — por eso abrir una
 * propiedad nueva es cargar su mapeo acá y no un desarrollo.
 *
 * Se guarda ENTERO (bulk), no fila por fila: la forma de trabajar del owner es
 * bajar, corregir y subir. El backend valida antes de borrar, así que un archivo
 * con la misma cuenta dos veces se rechaza sin haber tocado nada.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  getOrigenes, getMapeoOrigen, guardarMapeoOrigen,
  type ReglaOrigen, type EstadoOrigen,
} from "@/lib/api";
import { bajarCuadros, type Cuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const BTN: React.CSSProperties = {
  padding: "6px 14px", borderRadius: 6, cursor: "pointer", fontSize: 12,
  fontWeight: 600, border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)",
};
const BTN_PRIMARY: React.CSSProperties = { ...BTN, background: "var(--brand)", color: "#fff", border: "none" };
const TD: React.CSSProperties = { padding: "3px 4px" };

function filaVacia(): ReglaOrigen {
  return {
    cuenta_origen: "", nombre_origen: "", dept_origen: "",
    account_code: "", dept_code: "", outlet: "", activo: true, nota: "",
  };
}

export default function OrigenesPage() {
  const t = useTranslations("origins");
  const tc = useTranslations("common");
  const [origen, setOrigen] = useState("QUICKBOOKS");
  const [estado, setEstado] = useState<EstadoOrigen[]>([]);
  const [reglas, setReglas] = useState<ReglaOrigen[]>([]);
  const [sucio, setSucio] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState("");

  const ORIGENES = [
    { clave: "QUICKBOOKS", label: "QuickBooks", nota: t("notaQuickbooks") },
    { clave: "BACKOFFICE", label: "Backoffice", nota: t("notaBackoffice") },
    { clave: "ARCHIVO", label: t("origenArchivo"), nota: t("notaArchivo") },
  ];

  const cargar = useCallback(async (o: string) => {
    setCargando(true); setError(null); setMsg(null);
    try {
      const [est, mapeo] = await Promise.all([getOrigenes(), getMapeoOrigen(o)]);
      setEstado(est.origenes);
      setReglas(mapeo.reglas);
      setSucio(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorCargando"));
    } finally {
      setCargando(false);
    }
  }, [t]);

  useEffect(() => { cargar(origen); }, [origen, cargar]);

  function set(i: number, campo: keyof ReglaOrigen, valor: string | boolean) {
    setReglas(prev => prev.map((r, idx) => idx === i ? { ...r, [campo]: valor } : r));
    setSucio(true);
  }
  function agregar() { setReglas(prev => [filaVacia(), ...prev]); setSucio(true); }
  function quitar(i: number) { setReglas(prev => prev.filter((_, idx) => idx !== i)); setSucio(true); }

  async function guardar() {
    setGuardando(true); setError(null); setMsg(null);
    try {
      const limpias = reglas.filter(r => r.cuenta_origen.trim() && r.account_code.trim());
      const r = await guardarMapeoOrigen(origen, limpias);
      setMsg(t("guardadoN", { n: r.reglas }));
      await cargar(origen);
    } catch (e: unknown) {
      // El backend valida ANTES de borrar, así que un error acá significa que el
      // mapeo anterior sigue intacto. Vale decirlo: si no, uno cree que perdió todo.
      setError((e instanceof Error ? e.message : t("errorGuardar"))
        + t("nadaSeGuardo"));
    } finally {
      setGuardando(false);
    }
  }

  function bajarExcel() {
    const cuadro: Cuadro = {
      titulo: t("excelTitulo", { origen }),
      subtitulo: t("excelSubtitulo"),
      hoja: t("hojaMapeo"),
      columnas: [
        { label: t("colCuentaOrigen"), ancho: 18, formato: "texto" },
        { label: t("colNombreOrigen"), ancho: 34, formato: "texto" },
        { label: t("colDeptoOrigen"), ancho: 16, formato: "texto" },
        { label: t("colCuentaFinplan"), ancho: 16, formato: "texto" },
        { label: t("colDeptoFinplan"), ancho: 16, formato: "texto" },
        { label: t("colOutlet"), ancho: 14, formato: "texto" },
        { label: t("colActivo"), ancho: 10, formato: "texto" },
        { label: t("colNota"), ancho: 34, formato: "texto" },
      ],
      // Todas las columnas son texto: un código de cuenta con ceros a la
      // izquierda deja de serlo si el Excel lo toma como número.
      filas: reglas.map(r => ({
        label: r.cuenta_origen,
        valores: [r.nombre_origen, r.dept_origen, r.account_code, r.dept_code,
                  r.outlet, r.activo ? t("si") : t("no"), r.nota],
      })),
    };
    bajarCuadros(`Mapeo_${origen}`, [cuadro]);
  }

  const visibles = reglas
    .map((r, i) => ({ r, i }))
    .filter(({ r }) => {
      const t = filtro.trim().toLowerCase();
      if (!t) return true;
      return [r.cuenta_origen, r.nombre_origen, r.dept_origen, r.account_code, r.dept_code]
        .some(v => (v ?? "").toLowerCase().includes(t));
    });

  const activo = estado.find(e => e.origen === origen);
  const b = (c: React.ReactNode) => <strong>{c}</strong>;
  const em = (c: React.ReactNode) => <em>{c}</em>;

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA />
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{t("titulo")}</h1>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 16, maxWidth: 900 }}>
        {t.rich("intro", { b })}
      </p>

      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {ORIGENES.map(o => {
          const est = estado.find(e => e.origen === o.clave);
          const sel = o.clave === origen;
          return (
            <button key={o.clave} onClick={() => { if (!sucio || confirm(t("confirmCambio"))) setOrigen(o.clave); }}
              style={{
                ...BTN, background: sel ? "var(--brand)" : "var(--bg-surface)",
                color: sel ? "#fff" : "var(--text-secondary)", border: sel ? "none" : BTN.border,
              }}>
              {o.label}
              <span style={{ opacity: 0.75, marginLeft: 6, fontSize: 11 }}>
                {o.nota} · {est ? est.reglas_activas : 0}
              </span>
            </button>
          );
        })}
      </div>

      {activo && !activo.listo_para_importar && (
        <div style={{
          padding: "9px 12px", borderRadius: 6, marginBottom: 14, fontSize: 12.5,
          background: "rgba(230,168,23,0.12)", border: "1px solid rgba(230,168,23,0.4)",
          color: "var(--text-primary)",
        }}>
          {t.rich("sinReglas", { b })}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
        <button onClick={agregar} style={BTN}>{t("masRegla")}</button>
        <button onClick={guardar} disabled={!sucio || guardando} style={{ ...BTN_PRIMARY, opacity: (!sucio || guardando) ? 0.5 : 1 }}>
          {guardando ? tc("saving") : sucio ? tc("save") : t("guardado")}
        </button>
        <button onClick={bajarExcel} style={BTN}>{t("excelBtn")}</button>
        <input value={filtro} onChange={e => setFiltro(e.target.value)}
          placeholder={t("buscarPh")}
          style={{ ...BTN, cursor: "text", fontWeight: 400, minWidth: 220 }} />
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {t("deN", { v: visibles.length, n: reglas.length })}
        </span>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 12.5, marginBottom: 10 }}>{error}</div>}
      {msg && <div style={{ color: "var(--positive)", fontSize: 12.5, marginBottom: 10 }}>{msg}</div>}

      {cargando ? (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</div>
      ) : (
        <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th colSpan={3} style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                  {t("enElOrigen")}
                </th>
                <th colSpan={3} style={{ textAlign: "left", color: "var(--brand)" }}>
                  {t("enFinplan")}
                </th>
                <th colSpan={3}></th>
              </tr>
              <tr>
                <th style={{ textAlign: "left" }}>{tc("account")}</th>
                <th style={{ textAlign: "left" }}>{tc("name")}</th>
                <th style={{ textAlign: "left" }} title={t("tituloDeptoOpcional")}>
                  {tc("dept")} <span style={{ opacity: 0.6 }}>{t("opcional")}</span>
                </th>
                <th style={{ textAlign: "left" }}>{tc("account")}</th>
                <th style={{ textAlign: "left" }}>{tc("dept")}</th>
                <th style={{ textAlign: "left" }}>{t("colOutlet")}</th>
                <th>{t("activa")}</th>
                <th style={{ textAlign: "left" }}>{t("colNota")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visibles.map(({ r, i }) => (
                <tr key={r.id ?? `nueva-${i}`} style={{ opacity: r.activo ? 1 : 0.5 }}>
                  <td style={TD}><input className="fin-input mono" value={r.cuenta_origen}
                    onChange={e => set(i, "cuenta_origen", e.target.value)} style={{ width: 120 }} /></td>
                  <td style={TD}><input className="fin-input" value={r.nombre_origen}
                    onChange={e => set(i, "nombre_origen", e.target.value)} style={{ width: 240 }} /></td>
                  <td style={TD}><input className="fin-input" value={r.dept_origen}
                    onChange={e => set(i, "dept_origen", e.target.value)} style={{ width: 120 }}
                    placeholder={t("cualquiera")} /></td>
                  <td style={TD}><input className="fin-input mono" value={r.account_code}
                    onChange={e => set(i, "account_code", e.target.value)} style={{ width: 100 }} /></td>
                  <td style={TD}><input className="fin-input mono" value={r.dept_code}
                    onChange={e => set(i, "dept_code", e.target.value)} style={{ width: 90 }} /></td>
                  <td style={TD}><input className="fin-input" value={r.outlet}
                    onChange={e => set(i, "outlet", e.target.value)} style={{ width: 110 }} /></td>
                  <td style={{ ...TD, textAlign: "center" }}>
                    <input type="checkbox" checked={r.activo}
                      onChange={e => set(i, "activo", e.target.checked)} />
                  </td>
                  <td style={TD}><input className="fin-input" value={r.nota}
                    onChange={e => set(i, "nota", e.target.value)} style={{ width: 220 }} /></td>
                  <td style={{ ...TD, textAlign: "center" }}>
                    <button onClick={() => quitar(i)} aria-label={t("quitarRegla")}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-disabled)", fontSize: 15 }}>×</button>
                  </td>
                </tr>
              ))}
              {visibles.length === 0 && (
                <tr><td colSpan={9} style={{ padding: 14, fontSize: 12.5, color: "var(--text-secondary)" }}>
                  {reglas.length === 0 ? t("sinReglasTodavia") : t("ningunaCoincide")}
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 14, maxWidth: 900 }}>
        {t.rich("pie", { b, em })}
      </p>
    </div>
  );
}
