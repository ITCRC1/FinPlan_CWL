"use client";
/**
 * Master Data → El setup de la cuenta.
 *
 * **Por qué existe (owner, 2026-08-16).** «Lo que sí quiero que se cumpla es que
 * el setup de la cuenta esté claro: qué es ingreso, qué es costo, qué es gasto y
 * qué es gastos de la propiedad; qué departamento; y dónde debe aparecer en el
 * P&L, para que se alinee con los demás años.»
 *
 * Es lo que hace CLONABLE una propiedad: antes de copiarle el mapeo a Amarena,
 * Oxigen y Ojochal hay que poder recorrerlo de una sentada y decir «esto está
 * bien». La respuesta ya existía —el mapeo está sano— pero repartida en once
 * chequeos de un script, una columna de una plantilla de Excel y un tab que
 * primero pide elegir un escenario.
 *
 * ⚠️ **Acá no se escribe ni un rótulo a mano.** Todo viene del backend, que lo
 * saca del mapeo, del catálogo de departamentos, de la configuración de líneas
 * y del MISMO resolvedor del motor del P&L. Una lista mantenida aparte se
 * desincroniza: así esta app llegó a mostrar 22 departamentos con 38 en la base.
 *
 * Se filtra en el navegador porque son ~1.100 filas y el owner necesita cruzar
 * clase con departamento sin esperar un viaje al servidor por cada clic.
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import IrA from "@/components/IrA";
import {
  getSetupCuenta, setupCuentaExcelUrl,
  type SetupCuenta, type SetupFila, type SetupDesalineada,
} from "@/lib/api";

const BTN: React.CSSProperties = {
  padding: "9px 18px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 14, fontWeight: 600,
  textDecoration: "none", display: "inline-block",
};
const CHIP = (activo: boolean): React.CSSProperties => ({
  padding: "5px 12px", borderRadius: 999, cursor: "pointer", fontSize: 12.5,
  fontWeight: 600, border: `1px solid ${activo ? "#1A7F4B" : "var(--border-subtle)"}`,
  background: activo ? "rgba(26,127,75,.16)" : "transparent",
  color: activo ? "#1fa363" : "var(--text-secondary)",
});
// El encabezado se pega solo: `thead th` ya es sticky en el CSS de la app, y
// `fin-sticky` / `fin-scroll-x` lo hacen resolver contra el CONTENEDOR y no
// contra el nav. Clavarle `top` acá lo empujaría 44px adentro de la caja y le
// taparía la primera fila (ver test_encabezado_no_tapa_la_primera_fila).
const TH: React.CSSProperties = {
  textAlign: "left", padding: "7px 8px", fontSize: 11, fontWeight: 700,
  letterSpacing: ".03em", color: "var(--text-secondary)", whiteSpace: "nowrap",
  borderBottom: "1px solid var(--border-medium)",
};
const TD: React.CSSProperties = {
  padding: "5px 8px", fontSize: 12.5, borderBottom: "1px solid var(--border-subtle)",
  whiteSpace: "nowrap",
};

const money = (n: number) =>
  (n < 0 ? "(" : "") + "$" + Math.abs(Math.round(n)).toLocaleString("en-US") + (n < 0 ? ")" : "");

/** El color de la respuesta a la pregunta 4. Verde = no hay nada que hacer. */
const COMO_COLOR: Record<string, string> = {
  exact: "#1fa363",
  parent: "#1fa363",
  "dept-agnostic": "#1fa363",
  siembra: "#1fa363",
  FALLBACK: "#e08b3e",
  DROP: "#e0798a",
  "siembra-rota": "#e0798a",
};

/** Fila de la tabla grande. Aparte para que React no repinte las 1.100. */
function Fila({ f, anios }: { f: SetupFila; anios: number[] }) {
  const t = useTranslations("setupCuenta");
  const problema = !f.limpia;
  return (
    <tr style={{
      background: problema ? "rgba(192,57,43,.10)"
        : f.desalineada ? "rgba(133,100,4,.10)" : undefined,
    }}>
      <td style={{ ...TD, fontWeight: 600 }}>{f.clase_nombre}</td>
      <td style={{ ...TD, fontFamily: "var(--font-mono, monospace)" }}>{f.cuenta}</td>
      <td style={{ ...TD, whiteSpace: "normal", maxWidth: 220 }}>{f.cuenta_nombre || "—"}</td>
      <td style={{ ...TD, whiteSpace: "normal", maxWidth: 200 }}>
        {f.dept_name}
        <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>
          {f.dept_code ? ` · ${f.dept_code}` : ""}
        </span>
      </td>
      <td style={{ ...TD, fontSize: 11.5, color: "var(--text-secondary)" }}>
        {f.dept_tipo}{f.dept_padre ? t("dePadre", { padre: f.dept_padre }) : ""}
      </td>
      <td style={{ ...TD, whiteSpace: "normal", maxWidth: 230 }}>
        {f.linea_nombre || "—"}
        <div style={{ fontSize: 10.5, color: "var(--text-secondary)" }}>
          {f.linea_code}{f.seccion ? ` · ${f.seccion}` : ""}
        </div>
      </td>
      <td style={{ ...TD, color: COMO_COLOR[f.como] ?? "var(--text-primary)", fontWeight: 600 }}>
        {f.como_nombre}
        {f.regla_de && (
          <span style={{ color: "var(--text-secondary)", fontWeight: 400 }}>
            {" "}({f.regla_de})
          </span>
        )}
      </td>
      <td style={{ ...TD, textAlign: "center" }}>
        {!f.con_movimiento
          ? <span style={{ color: "var(--text-secondary)" }}>{t("sinDato")}</span>
          : f.desalineada
            ? <span style={{ color: "#c9a227", fontWeight: 700 }}>{t("revisar")}</span>
            : <span style={{ color: "#1fa363" }}>{t("si")}</span>}
      </td>
      {anios.map(a => (
        <td key={a} style={{ ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
          {f.montos[String(a)] !== undefined ? money(f.montos[String(a)]) : ""}
        </td>
      ))}
    </tr>
  );
}

/** La pregunta 5, cuenta por cuenta: la matriz línea × año. */
function Desalineada({ d, anios }: { d: SetupDesalineada; anios: number[] }) {
  const t = useTranslations("setupCuenta");
  return (
    <div style={{
      border: "1px solid var(--border-subtle)", borderLeft: "3px solid #c9a227",
      borderRadius: 8, background: "var(--bg-surface)", padding: "12px 14px",
      marginBottom: 12,
    }}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
        <strong style={{ fontSize: 14 }}>{d.cuenta}</strong>
        <span style={{ fontSize: 13 }}>{d.cuenta_nombre || "—"}</span>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{d.clase_nombre}</span>
        <span style={{ marginLeft: "auto", fontSize: 13, fontWeight: 700, color: "#c9a227" }}>
          {t("enJuego", { monto: money(d.monto_en_juego) })}
        </span>
      </div>
      <div className="fin-scroll-x" style={{ marginTop: 8 }}>
        <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 620 }}>
          <thead>
            <tr>
              <th style={TH}>{t("thLineaPl")}</th>
              <th style={TH}>{t("thDeptos")}</th>
              {anios.map(a => (
                <th key={a} style={{ ...TH, textAlign: "right" }}>{a}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.lineas.map(ln => {
              const porAnio = new Map(ln.celdas.map(c => [c.anio, c]));
              return (
                <tr key={ln.linea_code}>
                  <td style={{ ...TD, whiteSpace: "normal" }}>
                    {ln.linea_nombre}
                    <div style={{ fontSize: 10.5, color: "var(--text-secondary)" }}>
                      {ln.linea_code}
                    </div>
                  </td>
                  <td style={{ ...TD, fontSize: 11.5, color: "var(--text-secondary)" }}>
                    {ln.deptos.join(", ") || "—"}
                  </td>
                  {anios.map(a => {
                    const c = porAnio.get(a);
                    if (!c) return (
                      <td key={a} style={{
                        ...TD, textAlign: "right", fontSize: 11,
                        color: "var(--text-secondary)", fontStyle: "italic",
                      }}>{t("cuentaNoUsada")}</td>
                    );
                    if (c.estado === "usa") return (
                      <td key={a} style={{
                        ...TD, textAlign: "right", fontVariantNumeric: "tabular-nums",
                      }}>{money(c.monto)}</td>
                    );
                    // El hueco que importa: el departamento estaba vivo ese año
                    // y la cuenta igual no cayó en esta línea.
                    // ⚠️ `c.estado` es un CÓDIGO, no un rótulo: las dos
                    // comparaciones de acá arriba dependen de su texto exacto y
                    // una prueba lo fija. Se compara el código y se MUESTRA la
                    // etiqueta del catálogo — antes se pintaba crudo y la
                    // pantalla decía «no se usó» con la app en inglés, mientras
                    // el Excel de esta misma pantalla ya salía traducido.
                    const importa = c.estado === "no se usó";
                    const rotuloEstado = importa
                      ? t("estadoNoSeUso")
                      : c.estado === "el depto no estaba"
                        ? t("estadoDeptoNoEstaba")
                        : c.estado;
                    return (
                      <td key={a} style={{
                        ...TD, textAlign: "right", fontSize: 11, fontStyle: "italic",
                        color: importa ? "#c9a227" : "var(--text-secondary)",
                        fontWeight: importa ? 700 : 400,
                        background: importa ? "rgba(133,100,4,.12)" : undefined,
                      }}>{rotuloEstado}</td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const TECHO = 400;   // cuántas filas se pintan; el Excel se lleva todo

export default function SetupCuentaPage() {
  const t = useTranslations("setupCuenta");
  const tc = useTranslations("common");
  const [datos, setDatos] = useState<SetupCuenta | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clase, setClase] = useState("");
  const [depto, setDepto] = useState("");
  const [q, setQ] = useState("");
  const [soloRevisar, setSoloRevisar] = useState(false);
  const [conDato, setConDato] = useState(false);
  const [tab, setTab] = useState<"cuentas" | "alineacion">("cuentas");

  useEffect(() => {
    (async () => {
      try { setDatos(await getSetupCuenta()); }
      catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setCargando(false); }
    })();
  }, [tc]);

  const anios = datos?.resumen.anios_comparados ?? [];

  const filtradas = useMemo(() => {
    let r: SetupFila[] = datos?.filas ?? [];
    if (clase) r = r.filter(f => f.clase === clase);
    if (depto) r = r.filter(f => f.dept_code === depto);
    if (soloRevisar) r = r.filter(f => !f.limpia || f.desalineada);
    if (conDato) r = r.filter(f => f.con_movimiento);
    const t = q.trim().toLowerCase();
    if (t) r = r.filter(f =>
      f.cuenta.toLowerCase().includes(t) ||
      f.cuenta_nombre.toLowerCase().includes(t) ||
      f.dept_name.toLowerCase().includes(t) ||
      f.dept_code.toLowerCase().includes(t) ||
      f.linea_code.toLowerCase().includes(t) ||
      f.linea_nombre.toLowerCase().includes(t));
    return r;
  }, [datos, clase, depto, q, soloRevisar, conDato]);

  const desalineadas = useMemo(() => {
    let r: SetupDesalineada[] = datos?.desalineadas ?? [];
    if (clase) r = r.filter(d => d.clase === clase);
    const t = q.trim().toLowerCase();
    if (t) r = r.filter(d =>
      d.cuenta.toLowerCase().includes(t) || d.cuenta_nombre.toLowerCase().includes(t));
    return r;
  }, [datos, clase, q]);

  const b = (c: React.ReactNode) => <strong>{c}</strong>;
  const i = (c: React.ReactNode) => <em>{c}</em>;

  return (
    <div className="pag pag-ancha" style={{ padding: "20px 24px" }}>
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>
        {t("titulo")}
      </h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 6, maxWidth: 900 }}>
        {t.rich("intro", { b })}
      </p>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 18, maxWidth: 900 }}>
        {t.rich("intro2", { b })}
      </p>

      {cargando && <div style={{ fontSize: 13 }}>{t("cargandoCatalogo")}</div>}
      {error && (
        <div style={{
          border: "1px solid #C0392B", borderRadius: 8, padding: 14,
          color: "#C0392B", fontSize: 13,
        }}>{error}</div>
      )}

      {datos && (
        <>
          {/* Resumen */}
          <div style={{
            display: "flex", gap: 22, flexWrap: "wrap", marginBottom: 16,
            padding: "12px 16px", border: "1px solid var(--border-subtle)",
            borderRadius: 8, background: "var(--bg-surface)",
          }}>
            {[
              { k: t("kpiCombinaciones"), v: datos.resumen.filas, c: undefined },
              { k: t("kpiCuentas"), v: datos.resumen.cuentas, c: undefined },
              { k: t("kpiLimpias"), v: datos.resumen.limpias, c: "#1fa363" },
              { k: t("kpiPorDescarte"), v: datos.resumen.por_descarte, c: datos.resumen.por_descarte ? "#e08b3e" : undefined },
              { k: t("kpiSinRegla"), v: datos.resumen.sin_regla, c: datos.resumen.sin_regla ? "#e0798a" : undefined },
              { k: t("kpiARevisar"), v: datos.resumen.desalineadas, c: datos.resumen.desalineadas ? "#c9a227" : undefined },
              { k: t("kpiSinMovimiento"), v: datos.resumen.sin_movimiento, c: undefined },
            ].map(x => (
              <div key={x.k}>
                <div style={{ fontSize: 20, fontWeight: 700, color: x.c ?? "var(--text-primary)" }}>
                  {x.v.toLocaleString("en-US")}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{x.k}</div>
              </div>
            ))}
          </div>

          <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 16 }}>
            {t("aniosMirados")}{" "}
            {datos.anios.map(a => `${a.anio} → ${a.escenario}`).join("  ·  ")}
          </p>

          {/* Tabs + descargas */}
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
            <button onClick={() => setTab("cuentas")}
                    style={{ ...BTN, ...(tab === "cuentas" ? { borderColor: "#1A7F4B", color: "#1fa363" } : {}) }}>
              {t("tabCuentas")}
            </button>
            <button onClick={() => setTab("alineacion")}
                    style={{ ...BTN, ...(tab === "alineacion" ? { borderColor: "#1A7F4B", color: "#1fa363" } : {}) }}>
              {t("tabAlineacion", { n: datos.resumen.desalineadas })}
            </button>
            <a href={setupCuentaExcelUrl()} style={{ ...BTN, marginLeft: "auto" }}>
              {t("bajarExcel")}
            </a>
            <a href={setupCuentaExcelUrl(true)} style={BTN}>
              {t("soloRevisar")}
            </a>
          </div>

          {/* Filtros */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{t("queEsFiltro")}</span>
            <button style={CHIP(!clase)} onClick={() => setClase("")}>{t("todas")}</button>
            {datos.clases.map(c => (
              <button key={c.clase} style={CHIP(clase === c.clase)}
                      onClick={() => setClase(clase === c.clase ? "" : c.clase)}>
                {c.nombre} ({c.cuentas})
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14, flexWrap: "wrap" }}>
            <select value={depto} onChange={e => setDepto(e.target.value)}
                    style={{
                      padding: "6px 10px", borderRadius: 6, fontSize: 13,
                      border: "1px solid var(--border-medium)",
                      background: "var(--bg-surface)", color: "var(--text-primary)",
                    }}>
              <option value="">{t("todosLosDeptos")}</option>
              {datos.departamentos.map(d => (
                <option key={d.dept_code || "(sin)"} value={d.dept_code}>
                  {d.dept_code ? `${d.dept_code} · ` : ""}{d.dept_name} — {d.dept_tipo}
                </option>
              ))}
            </select>
            <input value={q} onChange={e => setQ(e.target.value)}
                   placeholder={t("buscarPh")}
                   style={{
                     padding: "6px 10px", borderRadius: 6, fontSize: 13, minWidth: 260,
                     border: "1px solid var(--border-medium)",
                     background: "var(--bg-surface)", color: "var(--text-primary)",
                   }} />
            <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={soloRevisar}
                     onChange={e => setSoloRevisar(e.target.checked)} />
              {t("soloRevisar")}
            </label>
            <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={conDato}
                     onChange={e => setConDato(e.target.checked)} />
              {t("soloConMovimiento")}
            </label>
          </div>

          {tab === "cuentas" ? (
            <>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
                {t("nCombinaciones", { n: filtradas.length.toLocaleString("en-US") })}
                {filtradas.length > TECHO && t("techo", { n: TECHO })}
              </div>
              <div className="fin-sticky"
                   style={{ border: "1px solid var(--border-subtle)", borderRadius: 8 }}>
                <table style={{ borderCollapse: "collapse", width: "100%" }}>
                  <thead>
                    <tr>
                      <th style={TH}>{t("th1QueEs")}</th>
                      <th style={TH}>{tc("account")}</th>
                      <th style={TH}>{tc("name")}</th>
                      <th style={TH}>{t("th2Departamento")}</th>
                      <th style={TH}>{t("thTipo")}</th>
                      <th style={TH}>{t("th3LineaPl")}</th>
                      <th style={TH}>{t("th4Como")}</th>
                      <th style={{ ...TH, textAlign: "center" }}>{t("th5Alinea")}</th>
                      {anios.map(a => (
                        <th key={a} style={{ ...TH, textAlign: "right" }}>{a}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtradas.slice(0, TECHO).map(f => (
                      <Fila key={`${f.dept_code}|${f.cuenta}|${f.linea_code}`} f={f} anios={anios} />
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <>
              <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 12, maxWidth: 900 }}>
                {t.rich("alineacionAyuda", { b, i })}
              </p>
              {desalineadas.length === 0 ? (
                <div style={{ fontSize: 13, color: "#1fa363", fontWeight: 600 }}>
                  {t("todoAlineado")}
                </div>
              ) : desalineadas.map(d => (
                <Desalineada key={d.cuenta} d={d} anios={anios} />
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
