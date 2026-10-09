"use client";

/**
 * El USALI dentro de la aplicación.
 *
 * Owner, 2026-10-08: *«yo quiero subir el pdf y que el documento viva en la app
 * y se use para análisis»*.
 *
 * Esta es la ETAPA 1 de tres: el documento vive acá y se consulta.
 * **Todavía no marca nada.** El puente contra las cuentas de Integrity (etapa 2)
 * y las reglas de discrepancia (etapa 3) vienen después, y en ese orden a
 * propósito: una regla nueva que marca cien cosas el primer mes no se revisa,
 * se ignora.
 */
import { useCallback, useEffect, useState } from "react";

import { api, getToken } from "@/lib/api";

const BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

interface Estado {
  hay: boolean;
  archivo?: string;
  paginas?: number;
  paginas_con_texto?: number;
  items?: number;
  items_confirmados?: number;
  definiciones?: number;
  /** Los renglones aprobados de los 14 Schedules: la otra mitad
   *  del libro. El diccionario da ejemplos de articulos; el
   *  Schedule da el renglon del reporte. */
  renglones?: number;
  subido_en?: string | null;
  subido_por?: string;
  cruce?: Record<string, number>;
  schedules?: { schedule: string; items: number }[];
}

interface Fila {
  item: string; schedule: string; cuenta: string;
  confianza: string; paginas: string;
}

interface Definicion { cuenta: string; texto: string; pagina: number }

export default function UsaliPage() {
  const [estado, setEstado] = useState<Estado | null>(null);
  const [q, setQ] = useState("");
  const [schedule, setSchedule] = useState("");
  const [filas, setFilas] = useState<Fila[]>([]);
  const [total, setTotal] = useState(0);
  const [buscando, setBuscando] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState("");
  /** La cuenta abierta, con lo que el libro dice que incluye. */
  const [abierta, setAbierta] = useState<
    { cuenta: string; definiciones: Definicion[]; items: Fila[] } | null>(null);

  const cargarEstado = useCallback(async () => {
    try {
      setEstado(await api.get<Estado>("/usali/estado/"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo leer el estado");
    }
  }, []);

  useEffect(() => { void cargarEstado(); }, [cargarEstado]);

  const buscar = useCallback(async () => {
    setBuscando(true);
    try {
      const r = await api.get<{ total: number; filas: Fila[] }>(
        `/usali/buscar/?q=${encodeURIComponent(q)}`
        + `&schedule=${encodeURIComponent(schedule)}`);
      setFilas(r.filas);
      setTotal(r.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo buscar");
    } finally {
      setBuscando(false);
    }
  }, [q, schedule]);

  useEffect(() => {
    if (!estado?.hay) return;
    const t = setTimeout(() => { void buscar(); }, 250);
    return () => clearTimeout(t);
  }, [estado?.hay, buscar]);

  /** El archivo que el servidor rechazo por repetido, esperando confirmacion.
   *
   *  ⚠️ El guard de reimport es correcto —frena la subida doble por error— pero
   *  en esta pantalla «reemplazar» ES la intencion: el libro se vuelve a subir
   *  cuando el lector aprendio a sacarle algo mas. Sin este boton el mensaje
   *  pedia `permitir_reimport=true`, un parametro que ninguna parte de la UI
   *  podia mandar. Ya habia pasado en el cierre de agosto 2026 por otra ruta y
   *  costo una tarde; esta es la misma falla en otro lado. */
  const [repetido, setRepetido] = useState<File | null>(null);

  async function subir(f: File, igual = false) {
    setSubiendo(true);
    setError("");
    setRepetido(null);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const token = getToken();
      const res = await fetch(
        `${BASE}/usali/subir/${igual ? "?permitir_reimport=true" : ""}`, {
        method: "POST", body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const j = await res.json();
      if (!res.ok) {
        // 409 «ya subido» no es un error: es una pregunta. Se guarda el archivo
        // para poder contestarla sin volver a elegirlo del disco.
        if (res.status === 409) {
          setRepetido(f);
        }
        throw new Error(typeof j?.detail === "string" ? j.detail
          : j?.detail?.mensaje || j?.detail?.detalle || `HTTP ${res.status}`);
      }
      await cargarEstado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo subir");
    } finally {
      setSubiendo(false);
    }
  }

  async function bajarExcel() {
    try {
      const token = getToken();
      const res = await fetch(
        `${BASE}/usali/excel/?q=${encodeURIComponent(q)}`
        + `&schedule=${encodeURIComponent(schedule)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "USALI_catalogo.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo bajar el Excel");
    }
  }

  async function abrir(cuenta: string) {
    try {
      setAbierta(await api.get(
        `/usali/definicion/?cuenta=${encodeURIComponent(cuenta)}`));
    } catch { /* si no hay definición, no se abre nada */ }
  }

  const td: React.CSSProperties = { fontSize: 12.5, padding: "5px 8px" };
  const th: React.CSSProperties = {
    ...td, fontWeight: 700, textAlign: "left", background: "var(--bg-header)",
    color: "#fff", fontSize: 11.5,
  };

  return (
    <div style={{ padding: 20, maxWidth: 1180 }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 2 }}>
        USALI — Uniform System of Accounts for the Lodging Industry
      </h1>
      <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 14 }}>
        El estándar, dentro del sistema: qué artículo va en qué departamento y en
        qué cuenta, y qué dice el libro que incluye cada cuenta. Por ahora es
        consulta — todavía no marca discrepancias.
      </p>

      {error && (
        <p style={{ fontSize: 12.5, color: "var(--negative)", marginBottom: 10 }}>
          {error}
        </p>
      )}

      {/* El 409 «ya subido» no es un error que se lea y se cierre: es una
          pregunta con una sola respuesta sensata acá. El archivo ya está en
          memoria, así que contestarla no obliga a buscarlo otra vez en el
          disco. */}
      {repetido && !subiendo && (
        <div style={{ marginBottom: 12, padding: "10px 12px", borderRadius: 6,
                      border: "1px solid var(--warning)",
                      background: "var(--bg-elevated)" }}>
          <div style={{ fontSize: 12.5, marginBottom: 8 }}>
            Es el mismo archivo que ya está cargado. Subirlo de nuevo es lo
            correcto cuando el sistema aprendió a leerle algo más — hoy, los{" "}
            <b>renglones de los 14 Schedules</b>. El diccionario y las
            definiciones se releen idénticos: no se pierde nada.
          </div>
          <button onClick={() => void subir(repetido, true)}
                  style={{ fontSize: 12, padding: "5px 12px", borderRadius: 5,
                           cursor: "pointer", fontWeight: 600,
                           border: "1px solid var(--brand)",
                           background: "var(--brand)", color: "#fff" }}>
            Subirlo igual
          </button>
          <button onClick={() => { setRepetido(null); setError(""); }}
                  style={{ fontSize: 12, padding: "5px 12px", borderRadius: 5,
                           marginLeft: 8, cursor: "pointer",
                           border: "1px solid var(--border-medium)",
                           background: "var(--bg-input)",
                           color: "var(--text-primary)" }}>
            Dejarlo como está
          </button>
        </div>
      )}

      {/* ── lo que hay cargado ─────────────────────────────────────────── */}
      <div style={{ border: "1px solid var(--border-medium)", borderRadius: 6,
                    padding: 12, marginBottom: 16,
                    background: "var(--bg-surface)" }}>
        {estado?.hay ? (
          <>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              {estado.archivo}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {estado.paginas} páginas ({estado.paginas_con_texto} con texto) ·{" "}
              <b>{estado.items?.toLocaleString()}</b> artículos del diccionario,{" "}
              {estado.items_confirmados?.toLocaleString()} confirmados por los dos
              ordenamientos del libro ·{" "}
              <b>{estado.definiciones}</b> definiciones de cuenta ·{" "}
              <b>{estado.renglones}</b> renglones de los 14 Schedules
              {estado.subido_en && (
                <> · subido {new Date(estado.subido_en).toLocaleDateString()}
                  {estado.subido_por ? ` por ${estado.subido_por}` : ""}</>
              )}
            </div>
          </>
        ) : (
          <div style={{ fontSize: 13 }}>
            Todavía no hay ningún documento cargado.
          </div>
        )}
        <label style={{ display: "inline-block", marginTop: 10, fontSize: 12,
                        padding: "5px 12px", borderRadius: 5,
                        cursor: subiendo ? "wait" : "pointer",
                        border: "1px solid var(--border-medium)",
                        background: "var(--bg-input)" }}>
          {subiendo ? "leyendo el PDF…"
            : estado?.hay ? "⬆ Reemplazar el documento" : "⬆ Subir el PDF del USALI"}
          <input type="file" accept="application/pdf" disabled={subiendo}
                 style={{ display: "none" }}
                 onChange={e => { const f = e.target.files?.[0]; if (f) void subir(f); }} />
        </label>
        {estado?.hay && (
          <span style={{ fontSize: 11.5, color: "var(--text-secondary)",
                         marginLeft: 10 }}>
            Subir otro reemplaza el que está: nunca hay dos ediciones conviviendo.
          </span>
        )}
      </div>

      {estado?.hay && (
        <>
          {/* ── la búsqueda ──────────────────────────────────────────── */}
          <div style={{ display: "flex", gap: 8, alignItems: "center",
                        marginBottom: 10, flexWrap: "wrap" }}>
            <input value={q} onChange={e => setQ(e.target.value)}
                   placeholder="¿dónde va…? — combustible, uniformes, comisiones…"
                   style={{ fontSize: 13, padding: "6px 10px", borderRadius: 5,
                            minWidth: 330,
                            border: "1px solid var(--border-medium)",
                            background: "var(--bg-input)",
                            color: "var(--text-primary)" }} />
            <select value={schedule} onChange={e => setSchedule(e.target.value)}
                    style={{ fontSize: 12.5, padding: "6px 8px", borderRadius: 5 }}>
              <option value="">Todos los departamentos</option>
              {(estado.schedules ?? []).map(s => (
                <option key={s.schedule} value={s.schedule}>
                  {s.schedule} — {s.items}
                </option>
              ))}
            </select>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {buscando ? "buscando…"
                : `${filas.length} de ${total.toLocaleString()}`}
            </span>
            {/* ⚠️ Baja lo que se está viendo, filtros incluidos. Y sirve de
                verdad: con las ~1.950 filas afuera se arma el puente contra las
                cuentas de Integrity. La tercera hoja trae los renglones
                aprobados de cada Schedule, y dice cuáles NO tienen lista —el 3,
                Other Operated Departments, donde viven el Spa y los tours—. */}
            <button onClick={() => void bajarExcel()}
                    title="Diccionario, definiciones y renglones del reporte, en tres hojas"
                    style={{ fontSize: 12, padding: "5px 11px", borderRadius: 5,
                             cursor: "pointer", fontWeight: 600,
                             border: "1px solid var(--border-medium)",
                             background: "var(--bg-input)",
                             color: "var(--text-primary)" }}>⬇ Excel</button>
          </div>

          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              <th style={th}>Artículo</th>
              <th style={th}>Departamento</th>
              <th style={th}>Cuenta</th>
              <th style={th}>Origen</th>
            </tr></thead>
            <tbody>
              {filas.map((f, i) => (
                <tr key={f.item + f.schedule + f.cuenta + i}
                    style={{ background: i % 2 ? "var(--bg-surface)" : "transparent" }}>
                  <td style={td}>{f.item}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{f.schedule}</td>
                  <td style={td}>
                    <button onClick={() => void abrir(f.cuenta)}
                            title="Ver qué dice el libro que incluye esta cuenta"
                            style={{ fontSize: 12.5, padding: 0, border: "none",
                                     background: "none", cursor: "pointer",
                                     color: "var(--brand)", textAlign: "left" }}>
                      {f.cuenta}
                    </button>
                  </td>
                  <td style={{ ...td, fontSize: 11, whiteSpace: "nowrap",
                               color: f.confianza === "confirmado"
                                 ? "var(--text-secondary)" : "var(--warning)" }}>
                    {/* La confianza viaja con el dato: el libro trae el
                        diccionario dos veces y «confirmado» quiere decir que los
                        dos ordenamientos coinciden. */}
                    {f.confianza === "confirmado" ? "confirmado" : "de un solo lado"}
                    {f.paginas ? ` · p. ${f.paginas}` : ""}
                  </td>
                </tr>
              ))}
              {!filas.length && !buscando && (
                <tr><td colSpan={4} style={{ ...td, color: "var(--text-secondary)" }}>
                  Sin resultados.
                </td></tr>
              )}
            </tbody>
          </table>
        </>
      )}

      {/* ── la definición de una cuenta ─────────────────────────────── */}
      {abierta && (
        <>
          <span onClick={() => setAbierta(null)}
                style={{ position: "fixed", inset: 0, zIndex: 40,
                         background: "rgba(0,0,0,0.45)" }} />
          <div style={{ position: "fixed", zIndex: 41, top: "8%", left: "50%",
                        transform: "translateX(-50%)", width: "min(760px, 92vw)",
                        maxHeight: "80vh", overflowY: "auto", padding: 18,
                        borderRadius: 8, border: "1px solid var(--border-medium)",
                        background: "var(--bg-surface)",
                        boxShadow: "0 12px 40px rgba(0,0,0,0.45)" }}>
            <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "start", gap: 12 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
                {abierta.cuenta}
              </h2>
              <button onClick={() => setAbierta(null)}
                      style={{ border: "none", background: "none", cursor: "pointer",
                               fontSize: 18, color: "var(--text-secondary)" }}>×</button>
            </div>
            {abierta.definiciones.length ? abierta.definiciones.map((d, i) => (
              <div key={i} style={{ marginTop: 10 }}>
                <div style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                  {d.cuenta} · página {d.pagina}
                </div>
                <p style={{ fontSize: 13, lineHeight: 1.5, textAlign: "justify" }}>
                  {d.texto}
                </p>
              </div>
            )) : (
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                          marginTop: 10 }}>
                El libro no trae una definición con ese nombre exacto. Abajo, los
                artículos que el diccionario manda a esta cuenta.
              </p>
            )}
            {abierta.items.length > 0 && (
              <>
                <div style={{ fontSize: 12, fontWeight: 600, marginTop: 14,
                              marginBottom: 4 }}>
                  Lo que va acá, según el diccionario ({abierta.items.length})
                </div>
                <div style={{ fontSize: 12.5, columns: 2, columnGap: 24,
                              color: "var(--text-primary)" }}>
                  {abierta.items.map((it, i) => (
                    <div key={i} style={{ breakInside: "avoid", padding: "1px 0" }}>
                      {it.item}
                      <span style={{ color: "var(--text-secondary)" }}>
                        {" "}· {it.schedule}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
