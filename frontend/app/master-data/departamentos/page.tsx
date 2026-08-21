"use client";
/**
 * Master Data → Departamentos.
 *
 * **Por qué existe (B6.4).** El motor ya leía `department_catalog`
 * (`pl_engine.set_dept_catalog()` corre al arrancar), pero la tabla solo se
 * cambiaba por SQL o migración. O sea: la capacidad existía y no había puerta.
 *
 * El caso que la motiva es del owner (2026-08-16): *«es posible que algunos
 * departamentos en Amarena quisiéramos renombrarlos, pero quizás sea más fácil
 * hacerlo después de clonar»*. Editar sobre una propiedad que YA tiene datos
 * es el caso principal, no el borde — y por eso lo que más se cuida es que
 * renombrar no arrastre nada.
 *
 * ⚠️ **El código está bloqueado a propósito, y no es un detalle de UI.** Es la
 * llave con la que el mapeo, la planilla, los reportes y las otras propiedades
 * se refieren al departamento. El nombre es etiqueta; el código no se mueve.
 * Misma regla que el código de categoría de habitación y el de posición.
 *
 * ⚠️ **No hay botón de borrar.** Se desactiva. Borrar libera el número y el
 * correlativo lo vuelve a entregar.
 *
 * Las validaciones de verdad viven en el backend
 * (`catalogo_departamentos_api.py`): esta pantalla las muestra, no las repite.
 * Repetirlas acá sería una segunda lista que se queda vieja.
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import {
  getDeptCatalogo, crearDept, editarDept, type DeptCatalogo,
} from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const BTN: React.CSSProperties = {
  padding: "9px 18px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 14, fontWeight: 600,
};
const TH: React.CSSProperties = {
  textAlign: "left", padding: "7px 8px", fontSize: 11, fontWeight: 700,
  textTransform: "uppercase", letterSpacing: ".04em",
};
const TD: React.CSSProperties = { padding: "6px 8px", fontSize: 13 };
const INP: React.CSSProperties = {
  width: "100%", padding: "5px 7px", fontSize: 13, borderRadius: 5,
  border: "1px solid var(--border-subtle)", background: "var(--bg-input)",
  color: "var(--text-primary)",
};

type Borrador = Partial<DeptCatalogo> & { dept_code: string };

export default function DepartamentosPage() {
  const t = useTranslations("deptCatalog");
  const tc = useTranslations("common");
  const [filas, setFilas] = useState<DeptCatalogo[]>([]);
  const [grupos, setGrupos] = useState<string[]>([]);
  const [kinds, setKinds] = useState<string[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [filtro, setFiltro] = useState("");
  const [verInactivos, setVerInactivos] = useState(false);
  const [edicion, setEdicion] = useState<Record<string, Partial<DeptCatalogo>>>({});
  const [nuevo, setNuevo] = useState<Borrador | null>(null);

  async function cargar() {
    setCargando(true); setError("");
    try {
      const r = await getDeptCatalogo();
      setFilas(r.departamentos); setGrupos(r.grupos); setKinds(r.pl_kinds);
    } catch (e) { setError(String((e as Error).message || e)); }
    finally { setCargando(false); }
  }
  useEffect(() => { void cargar(); }, []);

  const visibles = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    return filas.filter(d => (verInactivos || d.active)
      && (!q || d.dept_code.toLowerCase().includes(q)
        || (d.dept_name || "").toLowerCase().includes(q)
        || (d.default_pl_group || "").toLowerCase().includes(q)));
  }, [filas, filtro, verInactivos]);

  function set(code: string, patch: Partial<DeptCatalogo>) {
    setEdicion(e => ({ ...e, [code]: { ...(e[code] || {}), ...patch } }));
  }

  async function guardar(code: string) {
    const cambios = edicion[code];
    if (!cambios || !Object.keys(cambios).length) return;
    setError(""); setMsg("");
    try {
      const r = await editarDept(code, cambios);
      setFilas(f => f.map(d => d.dept_code === code ? r.departamento : d));
      setEdicion(e => Object.fromEntries(
        Object.entries(e).filter(([k]) => k !== code)));
      setMsg(`${code}: ${r.cambios.join(", ")}. ${r.aviso}`);
    } catch (e) { setError(String((e as Error).message || e)); }
  }

  /** El catálogo entero a Excel — es lo que se revisa ANTES de clonarle la
   *  propiedad a otro hotel, y en pantalla son ~37 filas de ocho columnas. Baja
   *  lo VISIBLE, para que el filtro sirva de recorte. */
  async function bajar() {
    setError("");
    try {
      await bajarCuadros("catalogo_departamentos", [{
        titulo: t("excelTitulo"),
        subtitulo: t("deN", { v: visibles.length, n: filas.length })
          + (verInactivos ? t("incluyeInactivos") : t("soloActivos")),
        hoja: t("hojaDepartamentos"),
        columnas: [
          { label: tc("code"), ancho: 12, formato: "texto" },
          { label: tc("name"), ancho: 34, formato: "texto" },
          { label: t("grupoPl"), ancho: 20, formato: "texto" },
          { label: t("tipo"), ancho: 14, formato: "texto" },
          { label: t("padre"), ancho: 14, formato: "texto" },
          { label: t("aliasMayor"), ancho: 26, formato: "texto" },
          { label: t("activo"), ancho: 10, formato: "texto" },
        ],
        filas: visibles.map(d => ({
          label: d.dept_code,
          valores: [
            d.dept_name, d.default_pl_group || t("porCuenta"), d.pl_kind,
            d.parent_dept_code || "", (d.name_aliases || []).join(", "),
            d.active ? t("si") : t("no"),
          ],
        })),
      }]);
    } catch (e) { setError(String((e as Error).message || e)); }
  }

  async function crear() {
    if (!nuevo) return;
    setError(""); setMsg("");
    try {
      const r = await crearDept(nuevo);
      setFilas(f => [...f, r.departamento]);
      setNuevo(null);
      setMsg(`${t("creado", { code: r.departamento.dept_code })} ${r.aviso}`);
    } catch (e) { setError(String((e as Error).message || e)); }
  }

  const b = (c: React.ReactNode) => <b>{c}</b>;

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA />
      <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 4 }}>{t("titulo")}</h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 14, maxWidth: 900 }}>
        {t.rich("intro", { b })}
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <input value={filtro} onChange={e => setFiltro(e.target.value)}
          placeholder={t("buscarPh")}
          style={{ ...INP, width: 280 }} />
        <label style={{ fontSize: 13, display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={verInactivos}
            onChange={e => setVerInactivos(e.target.checked)} />
          {t("verInactivos")}
        </label>
        <button style={BTN} onClick={() => setNuevo({ dept_code: "", dept_name: "", pl_kind: kinds[0] || "OPERATING", default_pl_group: "" })}>
          {t("nuevoDeptoBtn")}
        </button>
        <button style={BTN} onClick={() => void bajar()}>{t("excelBtn")}</button>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {t("deN", { v: visibles.length, n: filas.length })}
        </span>
      </div>

      {error && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 12, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {error}
        </div>
      )}
      {msg && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 12, fontSize: 13,
          background: "rgba(26,127,75,.12)", border: "1px solid #1A7F4B", color: "#1fa363" }}>
          {msg}
        </div>
      )}

      {nuevo && (
        <div style={{ padding: 14, borderRadius: 8, marginBottom: 14,
          border: "1px solid var(--border-medium)", background: "var(--bg-surface)" }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>{t("nuevoDepto")}</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>{tc("code")}
              <input value={nuevo.dept_code} onChange={e => setNuevo({ ...nuevo, dept_code: e.target.value })}
                style={{ ...INP, width: 90 }} placeholder="0170" />
            </label>
            <label style={{ fontSize: 11, color: "var(--text-secondary)", flex: 1, minWidth: 200 }}>{tc("name")}
              <input value={nuevo.dept_name || ""} onChange={e => setNuevo({ ...nuevo, dept_name: e.target.value })}
                style={INP} />
            </label>
            <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("grupoPl")}
              <select value={nuevo.default_pl_group || ""} onChange={e => setNuevo({ ...nuevo, default_pl_group: e.target.value })}
                style={{ ...INP, width: 180 }}>
                <option value="">{t("porCuentaSinGrupo")}</option>
                {grupos.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("tipo")}
              <select value={nuevo.pl_kind || ""} onChange={e => setNuevo({ ...nuevo, pl_kind: e.target.value })}
                style={{ ...INP, width: 130 }}>
                {kinds.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>{t("padre")}
              <select value={nuevo.parent_dept_code || ""} onChange={e => setNuevo({ ...nuevo, parent_dept_code: e.target.value || null })}
                style={{ ...INP, width: 170 }}>
                <option value="">{t("ninguno")}</option>
                {filas.filter(d => d.active).map(d => (
                  <option key={d.dept_code} value={d.dept_code}>{d.dept_code} · {d.dept_name}</option>
                ))}
              </select>
            </label>
            <button style={{ ...BTN, borderColor: "#1A7F4B", color: "#1fa363" }} onClick={() => void crear()}>{t("crear")}</button>
            <button style={BTN} onClick={() => setNuevo(null)}>{tc("cancel")}</button>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 9 }}>
            {t("avisoCodigoFijo")}
          </div>
        </div>
      )}

      {cargando ? <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tc("loading")}</div> : (
        <div className="fin-scroll-x">
          <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ ...TH, width: 78 }}>{tc("code")}</th>
                <th style={TH}>{tc("name")}</th>
                <th style={{ ...TH, width: 170 }}>{t("grupoPl")}</th>
                <th style={{ ...TH, width: 130 }}>{t("tipo")}</th>
                <th style={{ ...TH, width: 180 }}>{t("padre")}</th>
                <th style={{ ...TH, width: 190 }}>{t("aliasMayor")}</th>
                <th style={{ ...TH, width: 86 }}>{t("activo")}</th>
                <th style={{ ...TH, width: 96 }}></th>
              </tr>
            </thead>
            <tbody>
              {visibles.map(d => {
                const e = edicion[d.dept_code] || {};
                const v = <K extends keyof DeptCatalogo>(k: K) =>
                  (e[k] !== undefined ? e[k] : d[k]) as DeptCatalogo[K];
                const sucio = Object.keys(e).length > 0;
                return (
                  <tr key={d.dept_code} style={{ opacity: d.active ? 1 : .5 }}>
                    <td style={{ ...TD, fontFamily: "var(--font-mono, monospace)", fontWeight: 700 }}
                      title={t("tituloLlave")}>
                      {d.dept_code} 🔒
                    </td>
                    <td style={TD}>
                      <input value={String(v("dept_name") ?? "")}
                        onChange={ev => set(d.dept_code, { dept_name: ev.target.value })}
                        style={INP} />
                    </td>
                    <td style={TD}>
                      <select value={String(v("default_pl_group") ?? "")}
                        onChange={ev => set(d.dept_code, { default_pl_group: ev.target.value })}
                        style={INP}>
                        <option value="">{t("porCuenta")}</option>
                        {grupos.map(g => <option key={g} value={g}>{g}</option>)}
                      </select>
                    </td>
                    <td style={TD}>
                      <select value={String(v("pl_kind") ?? "")}
                        onChange={ev => set(d.dept_code, { pl_kind: ev.target.value })}
                        style={INP}>
                        {kinds.map(k => <option key={k} value={k}>{k}</option>)}
                      </select>
                    </td>
                    <td style={TD}>
                      <select value={String(v("parent_dept_code") ?? "")}
                        onChange={ev => set(d.dept_code, { parent_dept_code: ev.target.value || null })}
                        style={INP}>
                        <option value="">{t("ninguno")}</option>
                        {filas.filter(x => x.dept_code !== d.dept_code).map(x => (
                          <option key={x.dept_code} value={x.dept_code}>{x.dept_code} · {x.dept_name}</option>
                        ))}
                      </select>
                    </td>
                    <td style={{ ...TD, fontSize: 12, color: "var(--text-secondary)" }}
                      title={t("tituloAlias")}>
                      {(d.name_aliases || []).join(", ") || "—"}
                    </td>
                    <td style={TD}>
                      <input type="checkbox" checked={Boolean(v("active"))}
                        onChange={ev => set(d.dept_code, { active: ev.target.checked })} />
                    </td>
                    <td style={TD}>
                      {sucio && (
                        <button style={{ ...BTN, padding: "5px 12px", fontSize: 12.5, borderColor: "#1A7F4B", color: "#1fa363" }}
                          onClick={() => void guardar(d.dept_code)}>{tc("save")}</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 14, maxWidth: 900 }}>
        {t.rich("pie", { b })}
      </p>
    </div>
  );
}
