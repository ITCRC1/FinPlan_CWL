"use client";
/**
 * Mis libros: los Excels del owner en un solo lugar.
 *
 * Owner, 2026-11-24: «tengo versiones por todos lados… quiero ir a un lugar solo
 * y bajar mis proyectos, mis creaciones, pero que no se rompa nada» y «no quiero
 * llenarme de versiones».
 *
 * - El archivo se sube y se baja TAL CUAL: la app no lo abre. El Power Query
 *   viaja adentro y se actualiza en Excel con la llave, como siempre.
 * - Uno por nombre. Subir con el mismo nombre lo reemplaza y guarda solo la
 *   versión anterior, para volver atrás si se subió algo mal.
 *
 * Owner, 2026-11-24: «podemos crear sub tabs acá… ya si no se mezclan» y «es un
 * mismo repositorio solo que organizado por estos sub tabs».
 *
 * - Los sub-tabs son SOLO vista: el repositorio es uno y el nombre sigue siendo
 *   la llave. Por eso el aviso de «ya existe» mira TODOS los libros, no los del
 *   tab abierto — si no, subir «Cierre octubre» en Budget teniéndolo en Cierre
 *   reemplazaría el otro sin que se vea venir.
 * - Un libro ya subido se mueve de tab con el desplegable de su fila.
 */
import { useEffect, useRef, useState } from "react";
import {
  getCarpetasDeLibros, getLibros, getStoredUser, libroUrl, moverLibro, quitarLibro,
  subirLibro, volverLibroAAnterior, TITULO_BUDGET_PACKAGE,
  type CarpetaConteo, type CarpetaLibro, type Libro,
} from "@/lib/api";

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;
const cuando = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("es-CR", { dateStyle: "medium", timeStyle: "short" }) : "—";

export default function MisLibrosPage() {
  const [libros, setLibros] = useState<Libro[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [titulo, setTitulo] = useState(TITULO_BUDGET_PACKAGE);
  const [carpetas, setCarpetas] = useState<CarpetaConteo[]>([]);
  const [tab, setTab] = useState<CarpetaLibro>("CIERRE");
  const [nota, setNota] = useState("");
  const [subiendo, setSubiendo] = useState(false);
  const [esAdmin, setEsAdmin] = useState(false);
  const archivo = useRef<HTMLInputElement>(null);

  async function cargar() {
    try {
      const [ls, cs] = await Promise.all([getLibros(), getCarpetasDeLibros()]);
      setLibros(ls); setCarpetas(cs); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Error"); }
  }
  useEffect(() => { setEsAdmin(getStoredUser()?.role === "admin"); cargar(); }, []);

  async function subir(file: File, tituloElegido: string, carpeta: CarpetaLibro = tab) {
    const t = tituloElegido.trim();
    if (!t) { setMsg("✖ Ponele un nombre al libro."); return; }
    const existe = libros?.find(l => l.titulo.toLowerCase() === t.toLowerCase());
    if (existe && !confirm(`«${existe.titulo}» ya existe. ¿Reemplazarlo por ${file.name}?\n\nEl actual (${existe.nombre_archivo}) queda como versión anterior, por si hay que volver.`)) return;
    setSubiendo(true); setMsg(null);
    try {
      const r = await subirLibro(t, file, nota, carpeta);
      setMsg(`✓ «${r.titulo}» quedó guardado (${r.nombre_archivo}, ${mb(r.tamano)}).`);
      setNota("");
      await cargar();
    } catch (e) {
      setMsg(`✖ ${e instanceof Error ? e.message : "No se pudo subir"}`);
    } finally {
      setSubiendo(false);
      if (archivo.current) archivo.current.value = "";
    }
  }

  const reemplazarRef = useRef<HTMLInputElement>(null);
  const [aReemplazar, setAReemplazar] = useState<string>("");

  function rotulo(c: CarpetaLibro): string {
    return carpetas.find(x => x.clave === c)?.rotulo ?? c;
  }
  async function mover(l: Libro, destino: CarpetaLibro) {
    if (destino === l.carpeta) return;
    try {
      await moverLibro(l.id, destino);
      setMsg(`✓ «${l.titulo}» pasó a «${rotulo(destino)}».`);
      await cargar();
    } catch (e) { setMsg(`✖ ${e instanceof Error ? e.message : "No se pudo mover"}`); }
  }
  const enTab = (libros ?? []).filter(l => l.carpeta === tab);

  const boton = (color = "var(--brand)"): React.CSSProperties => ({
    padding: "4px 10px", fontSize: 12, borderRadius: 4, border: "none", cursor: "pointer",
    background: color, color: "#fff", fontWeight: 600, textDecoration: "none",
    display: "inline-block", lineHeight: "18px",
  });
  const link: React.CSSProperties = {
    fontSize: 11.5, color: "var(--text-secondary)", cursor: "pointer", background: "none",
    border: "none", textDecoration: "underline", padding: 0,
  };

  return (
    <div className="pag" style={{ padding: "18px 22px", maxWidth: 1100 }}>
      <h1 style={{ fontSize: 19, fontWeight: 700, margin: "0 0 4px" }}>Mis libros</h1>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", margin: "0 0 16px" }}>
        Tus archivos en un solo lugar: Excel, Word, PDF, PowerPoint o cualquier otro. Se guardan y se
        bajan tal cual; un Excel con Power Query se abre, se pega la llave y se hace «Actualizar todo»
        como siempre. Uno por nombre:
        subir uno nuevo con el mismo nombre lo reemplaza y guarda solo el anterior.
        Los tabs de abajo <b>solo organizan la vista</b>: es un mismo repositorio, y un
        libro se mueve de tab sin volver a subirlo.
      </p>

      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border-medium)",
                    marginBottom: 14, flexWrap: "wrap" }}>
        {carpetas.map(c => (
          <button key={c.clave} onClick={() => setTab(c.clave)}
            style={{ padding: "7px 14px", fontSize: 12.5, cursor: "pointer", background: "none",
                     border: "none", borderBottom: "2px solid " + (tab === c.clave ? "var(--brand)" : "transparent"),
                     color: tab === c.clave ? "var(--text-primary)" : "var(--text-secondary)",
                     fontWeight: tab === c.clave ? 600 : 400 }}>
            {c.rotulo}{" "}
            <span style={{ color: "var(--text-secondary)", fontWeight: 400 }}>({c.libros})</span>
          </button>
        ))}
      </div>

      {esAdmin && (
        <div style={{ border: "1px solid var(--border-medium)", borderRadius: 6, padding: 12,
                      marginBottom: 16, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <strong style={{ fontSize: 12.5 }}>Subir a «{rotulo(tab)}»</strong>
          <input value={titulo} onChange={e => setTitulo(e.target.value)} placeholder="Nombre del libro"
            list="titulos-libros"
            style={{ flex: "1 1 260px", padding: "5px 8px", fontSize: 12.5, borderRadius: 4,
                     border: "1px solid var(--border-medium)", background: "var(--bg-input)",
                     color: "var(--text-primary)" }} />
          <datalist id="titulos-libros">
            {(libros ?? []).map(l => <option key={l.id} value={l.titulo} />)}
          </datalist>
          <input value={nota} onChange={e => setNota(e.target.value)} placeholder="Nota (opcional)"
            style={{ flex: "1 1 200px", padding: "5px 8px", fontSize: 12.5, borderRadius: 4,
                     border: "1px solid var(--border-medium)", background: "var(--bg-input)",
                     color: "var(--text-primary)" }} />
          <input ref={archivo} type="file" style={{ display: "none" }}
            onChange={e => { const f = e.target.files?.[0]; if (f) subir(f, titulo); }} />
          <button onClick={() => archivo.current?.click()} disabled={subiendo} style={boton()}>
            {subiendo ? "Subiendo…" : "↑ Elegir archivo y subir"}
          </button>
        </div>
      )}

      {msg && (
        <div style={{ marginBottom: 12, fontSize: 12.5,
                      color: msg.startsWith("✓") ? "var(--positive)" : "var(--negative)" }}>{msg}</div>
      )}
      {error && <div style={{ color: "var(--negative)", fontSize: 12.5 }}>⚠ {error}</div>}
      {libros === null && !error && <p style={{ color: "var(--text-secondary)" }}>Cargando…</p>}
      {libros !== null && enTab.length === 0 && (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          {libros.length === 0
            ? `Todavía no hay libros. ${esAdmin ? "Subí el primero arriba." : "Pedile al administrador que suba uno."}`
            : `No hay nada en «${rotulo(tab)}». Hay ${libros.length} libro(s) en los otros tabs: se mueven desde la columna «Carpeta» de cada fila.`}
        </p>
      )}

      <input ref={reemplazarRef} type="file" style={{ display: "none" }}
        onChange={e => {
          const f = e.target.files?.[0];
          const l = libros?.find(x => x.titulo === aReemplazar);
          if (f && aReemplazar) subir(f, aReemplazar, l?.carpeta ?? tab);
        }} />

      {enTab.length > 0 && (
        <table className="fin-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Libro</th>
              <th style={{ textAlign: "left" }}>Archivo</th>
              <th style={{ textAlign: "left" }}>Subido</th>
              <th style={{ textAlign: "left" }}>Versión anterior</th>
              <th style={{ textAlign: "left" }}>Carpeta</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {enTab.map(l => (
              <tr key={l.id}>
                <td style={{ textAlign: "left", fontWeight: 600 }}>
                  {l.titulo}
                  {l.titulo === TITULO_BUDGET_PACKAGE && (
                    <div style={{ fontSize: 11, fontWeight: 400, color: "var(--text-secondary)" }}>
                      el del botón azul de Budget Package
                    </div>
                  )}
                  {l.nota && <div style={{ fontSize: 11, fontWeight: 400, color: "var(--text-secondary)" }}>{l.nota}</div>}
                </td>
                <td style={{ textAlign: "left", fontSize: 12 }}>{l.nombre_archivo}<br />
                  <span style={{ color: "var(--text-secondary)" }}>{mb(l.tamano)}</span></td>
                <td style={{ textAlign: "left", fontSize: 12 }}>{cuando(l.subido_el)}<br />
                  <span style={{ color: "var(--text-secondary)" }}>{l.subido_por ?? ""}</span></td>
                <td style={{ textAlign: "left", fontSize: 12 }}>
                  {l.anterior ? (
                    <>
                      <a href={libroUrl(l.id, true)} style={{ color: "var(--text-secondary)" }}>
                        {l.anterior.nombre_archivo}</a><br />
                      <span style={{ color: "var(--text-secondary)" }}>{cuando(l.anterior.subido_el)}</span>
                      {esAdmin && (
                        <div>
                          <button style={link} onClick={async () => {
                            if (!confirm(`¿Volver «${l.titulo}» a ${l.anterior!.nombre_archivo}?\n\nEl actual queda como anterior: se puede deshacer.`)) return;
                            try { await volverLibroAAnterior(l.id); setMsg(`✓ «${l.titulo}» volvió a la versión anterior.`); await cargar(); }
                            catch (e) { setMsg(`✖ ${e instanceof Error ? e.message : "No se pudo"}`); }
                          }}>↺ volver a esta</button>
                        </div>
                      )}
                    </>
                  ) : <span style={{ color: "var(--text-disabled)" }}>—</span>}
                </td>
                <td style={{ textAlign: "left", fontSize: 12 }}>
                  {esAdmin ? (
                    <select value={l.carpeta} onChange={e => mover(l, e.target.value as CarpetaLibro)}
                      title="Mover a otro sub-tab. El archivo no se toca."
                      style={{ padding: "3px 6px", fontSize: 12, borderRadius: 4,
                               border: "1px solid var(--border-medium)", background: "var(--bg-input)",
                               color: "var(--text-primary)" }}>
                      {carpetas.map(c => <option key={c.clave} value={c.clave}>{c.rotulo}</option>)}
                    </select>
                  ) : rotulo(l.carpeta)}
                </td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <a href={libroUrl(l.id)} style={boton("var(--accent-excel, #1D6F42)")}>⬇ Bajar</a>{" "}
                  {esAdmin && (
                    <>
                      <button style={boton()} disabled={subiendo}
                        onClick={() => { setAReemplazar(l.titulo); reemplazarRef.current?.click(); }}>
                        ↑ Reemplazar</button>{" "}
                      <button style={link} onClick={async () => {
                        if (!confirm(`¿Quitar «${l.titulo}» de la app?\n\nSe borran el archivo y su versión anterior, y no se pueden recuperar. Tu copia en la computadora no se toca.`)) return;
                        try { await quitarLibro(l.id); setMsg(`✓ «${l.titulo}» se quitó.`); await cargar(); }
                        catch (e) { setMsg(`✖ ${e instanceof Error ? e.message : "No se pudo"}`); }
                      }}>Quitar</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
