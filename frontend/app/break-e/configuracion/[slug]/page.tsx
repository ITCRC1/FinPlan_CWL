"use client";
/**
 * Break-E → Configuración → un departamento. Spec `FINPLAN_TAB_BREAK-E.md` §2.
 *
 * **Es el corazón del módulo.** Acá se define cuánto de cada cuenta es fijo, y
 * con 11,6x de apalancamiento operativo eso decide qué tan frágil es el negocio.
 * No es un formulario más.
 *
 * ⚠️ El spec dice «tres puntos de ocupación borran el resultado del año».
 * Medido con la matriz de sensibilidad: tres puntos se llevan el **89%**
 * ($250.146 → $28.420), y el que lo borra es **3,385 pp** — la holgura exacta
 * que reporta el propio modelo. La conclusión no cambia (el negocio es frágil),
 * pero la frase redondeada dice algo más fuerte de lo que el modelo sostiene.
 * Lo fija `test_cuanto_cuesta_cada_punto_de_ocupacion`.
 *
 * ## Lo que no se puede quitar de esta pantalla
 *
 * * **La columna Monto.** Sin ella se edita a ciegas: un 50% sobre $182.000 y un
 *   50% sobre $0 se ven igual en la pantalla y no significan lo mismo.
 * * **`% Variable` es el ÚNICO input.** El `% Fijo` se deriva en vivo al teclear
 *   y nunca se guarda — dos porcentajes almacenados pueden contradecirse.
 * * **La edición masiva.** Nadie va a teclear 467 porcentajes de a uno; sin
 *   esto, el módulo no se usa y los números quedan en la semilla.
 * * **El chip LÍNEA.** Esas filas no son una cuenta GL concreta sino una
 *   asignación por sección — el banner lo dice antes de que alguien ajuste.
 * * **El impuesto bloqueado**, con su leyenda. Sigue en la tabla para que el P&L
 *   cuadre, pero su porcentaje no se usa.
 *
 * Los sub-tabs se generan del catálogo (`be_department`), nunca de una lista
 * escrita acá: hay 8 departamentos esperando aparecer sin tocar código.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";

import {
  getBeDeptos, getBeClasificacion, setBePct, setBePctMasivo, resetBeDepto,
  type BeDepto, type BeFila,
} from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import { BarraContexto, useContextoBE, useVigencia, usd, pct } from "../../_contexto";

const TH: React.CSSProperties = {
  textAlign: "right", padding: "7px 8px", fontSize: 11, fontWeight: 700,
  textTransform: "uppercase", letterSpacing: ".04em",
};
const TD: React.CSSProperties = { padding: "5px 8px", fontSize: 13, textAlign: "right" };
const IZQ: React.CSSProperties = { ...TD, textAlign: "left" };
const CHIP = (bg: string, fg: string): React.CSSProperties => ({
  fontSize: 10, fontWeight: 700, padding: "2px 7px", borderRadius: 999,
  background: bg, color: fg, whiteSpace: "nowrap",
});

type Estado = "" | "guardando" | "guardado" | "error";

export default function ConfiguracionDepto() {
  const t = useTranslations("breakEven");
  const tc = useTranslations("common");
  const RICH = { b: (c: React.ReactNode) => <b>{c}</b> };
  const slug = String(useParams()?.slug ?? "");
  const [ctx, set, escenarios] = useContextoBE();
  const [deptos, setDeptos] = useState<BeDepto[]>([]);
  const [filas, setFilas] = useState<BeFila[]>([]);
  const [nombre, setNombre] = useState("");
  const [generaIngreso, setGeneraIngreso] = useState(true);
  const [err, setErr] = useState("");
  const [estado, setEstado] = useState<Record<string, Estado>>({});
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [masivo, setMasivo] = useState("");
  const [colapsadas, setColapsadas] = useState<Set<string>>(new Set());
  const [soloLinea, setSoloLinea] = useState(false);
  //: Sub-tab de sección activo. "" = todas.
  const [seccion, setSeccion] = useState("");
  //: Consolidar cuentas HERMANAS (la misma cuenta en varios dept_code del mismo
  //: departamento). Owner: «para Rooms no es necesario poner los 3
  //: departamentos, 0110-0115-0116, con solo uno y aplicás estándar».
  //: Encendido por defecto: Rooms pasa de 138 filas a ~46.
  const [consolidar, setConsolidar] = useState(true);
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const nuevaCarga = useVigencia();
  const cargar = useCallback(async () => {
    // `listo`, no `scenarioId`: sin el tipo del escenario el par es inventado.
    // `vigente()` descarta la respuesta que llegue tarde. Ver `_contexto`.
    if (!ctx.listo || !slug) return;
    const vigente = nuevaCarga();
    setErr("");
    try {
      const [cat, cla] = await Promise.all([
        getBeDeptos(), getBeClasificacion(slug, ctx.scenarioId, ctx.dataVersion, ctx.month)]);
      if (!vigente()) return;
      setDeptos(cat.departamentos);
      setFilas(cla.filas);
      setNombre(cla.departamento.name);
      setGeneraIngreso(cla.departamento.generates_revenue);
    } catch (e) { if (vigente()) setErr(String((e as Error).message || e)); }
  }, [slug, ctx.listo, ctx.scenarioId, ctx.dataVersion, ctx.month, nuevaCarga]);
  useEffect(() => { void cargar(); }, [cargar]);

  /** Las secciones que existen en este departamento, para los sub-tabs. */
  const listaSecciones = useMemo(() => {
    const s = new Set(filas.map(f => f.be_section || "—"));
    return [...s].sort();
  }, [filas]);

  /** Una fila VISIBLE puede representar varias hermanas.
   *
   * Hermanas = la misma cuenta en varios `dept_code` del mismo departamento.
   * Rooms tiene 46 líneas abiertas en 138 cuentas GL porque cada una existe en
   * `0110`, `0115` y `0116`. Editarlas de a una es teclear lo mismo tres veces
   * y arriesgarse a dejarlas distintas sin querer. Consolidadas, el % se aplica
   * a las tres — «aplicás estándar», que fue el pedido. */
  const visibles = useMemo(() => {
    let base = soloLinea ? filas.filter(f => f.map_source === "LINEA") : filas;
    if (seccion) base = base.filter(f => (f.be_section || "—") === seccion);
    if (!consolidar) return base.map(f => ({ f, hermanas: [f] }));

    const g = new Map<string, BeFila[]>();
    for (const f of base) {
      const k = `${f.be_section}||${f.account || f.pl_line}||${f.account_name}`;
      g.set(k, [...(g.get(k) ?? []), f]);
    }
    return [...g.values()].map(hs => ({
      // La fila que se muestra lleva la SUMA de las hermanas: sin eso, el monto
      // de la pantalla no cuadraría con el del departamento.
      f: {
        ...hs[0],
        amount: hs.reduce((a, x) => a + x.amount, 0),
        amount_variable: hs.reduce((a, x) => a + x.amount_variable, 0),
        amount_fixed: hs.reduce((a, x) => a + x.amount_fixed, 0),
      } as BeFila,
      hermanas: hs,
    }));
  }, [filas, soloLinea, seccion, consolidar]);

  const secciones = useMemo(() => {
    const g: Record<string, { f: BeFila; hermanas: BeFila[] }[]> = {};
    for (const v of visibles) (g[v.f.be_section || "—"] ||= []).push(v);
    return g;
  }, [visibles]);

  const tot = (xs: BeFila[], k: "amount" | "amount_variable" | "amount_fixed") =>
    xs.reduce((a, x) => a + (x[k] || 0), 0);
  const totV = (xs: { f: BeFila }[], k: "amount" | "amount_variable" | "amount_fixed") =>
    xs.reduce((a, x) => a + (x.f[k] || 0), 0);
  const nLinea = filas.filter(f => f.map_source === "LINEA").length;

  /** Autosave con rebote de 800 ms por fila. Nunca un «Guardar» global: se
   *  pierde al cambiar de tab, y esta pantalla se recorre departamento a
   *  departamento. */
  function editar(hermanas: BeFila[], valor: number) {
    const pv = Math.max(0, Math.min(100, valor)) / 100;
    const ids = new Set(hermanas.map(h => h.id));
    const clave = hermanas[0].id;
    setFilas(fs => fs.map(x => ids.has(x.id) ? {
      ...x, pct_variable: pv, pct_fixed: 1 - pv,
      amount_variable: x.amount * pv, amount_fixed: x.amount * (1 - pv),
    } : x));
    clearTimeout(timers.current[clave]);
    timers.current[clave] = setTimeout(async () => {
      setEstado(s => ({ ...s, [clave]: "guardando" }));
      try {
        // Una sola llamada para las hermanas: el endpoint masivo acepta ids
        // enumerados, así que no hay N peticiones ni riesgo de dejarlas
        // distintas si una falla a la mitad.
        if (ids.size === 1) await setBePct(clave, pv);
        else await setBePctMasivo({ pct_variable: pv, row_ids: [...ids] });
        setEstado(s => ({ ...s, [clave]: "guardado" }));
      } catch (e) {
        setEstado(s => ({ ...s, [clave]: "error" }));
        setErr(String((e as Error).message || e));
        void cargar();   // en error se revierte contra el servidor
      }
    }, 800);
  }

  async function aplicarMasivo(sec?: string) {
    const v = parseFloat(masivo);
    if (Number.isNaN(v) || v < 0 || v > 100) { setErr(t("errPctRango")); return; }
    setErr("");
    try {
      const ids = sec
        ? (secciones[sec] || []).flatMap(v => v.hermanas)
            .filter(f => !f.excluded_from_be).map(f => f.id)
        : [...sel];
      if (!ids.length) { setErr(t("errSinSeleccion")); return; }
      await setBePctMasivo({ pct_variable: v / 100, row_ids: ids });
      setSel(new Set()); await cargar();
    } catch (e) { setErr(String((e as Error).message || e)); }
  }

  async function restablecer() {
    if (!confirm(t("confirmarRestablecer", {
      nombre, n: filas.filter(f => !f.excluded_from_be).length,
    }))) return;
    try { await resetBeDepto(slug); await cargar(); }
    catch (e) { setErr(String((e as Error).message || e)); }
  }

  async function bajar() {
    await bajarCuadros(`break_even_${slug}`, [{
      titulo: t("clasificacionTitle", { nombre }),
      subtitulo: `${ctx.dataVersion} · ${ctx.month ? t("mesN", { n: ctx.month }) : t("fullYear")}`,
      hoja: nombre.slice(0, 28) || slug,
      columnas: [
        { label: tc("account"), ancho: 16, formato: "texto" },
        { label: t("colDescripcion"), ancho: 38, formato: "texto" },
        { label: t("colSeccion"), ancho: 20, formato: "texto" },
        { label: t("colAmount"), formato: "usd" }, { label: t("colPctVariable"), formato: "pct" },
        { label: t("colDollarVariable"), formato: "usd" }, { label: t("colDollarFijo"), formato: "usd" },
      ],
      filas: filas.map(f => ({
        label: f.map_source === "LINEA" ? t("chipLinea") : `${f.dept_code}:${f.account}`,
        valores: [f.account_name, f.be_section, f.amount, f.pct_variable,
                  f.amount_variable, f.amount_fixed],
      })),
    }]);
  }

  const activos = deptos.filter(d => d.activo);

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{t("configuracionTitle", { nombre: nombre || slug })}</h1>
      <BarraContexto ctx={ctx} set={set} escenarios={escenarios} />

      {/* Sub-tabs generados del CATÁLOGO, con scroll horizontal: con 15 el ancho
          se desborda y envolver a dos filas rompe la lectura. */}
      <div className="fin-scroll-x" style={{ display: "flex", gap: 6, marginBottom: 14,
        paddingBottom: 6, borderBottom: "1px solid var(--border-subtle)" }}>
        {activos.map(d => (
          <Link key={d.slug} href={`/break-e/configuracion/${d.slug}`}
            style={{
              padding: "6px 12px", borderRadius: 6, fontSize: 12.5, whiteSpace: "nowrap",
              textDecoration: "none",
              background: d.slug === slug ? "var(--brand)" : "transparent",
              color: d.slug === slug ? "#fff" : "var(--text-secondary)",
              border: "1px solid var(--border-subtle)",
            }}>{d.name}</Link>
        ))}
        {/* Los PENDIENTES también se ven, marcados. Ocultarlos hacía parecer
            que no existen — el owner preguntó por Club Madresal y no estaba.
            Existe en el catálogo; lo que no tiene es clasificación. */}
        {deptos.filter(d => !d.activo).map(d => (
          <Link key={d.slug} href={`/break-e/configuracion/${d.slug}`}
            title={t("deptoPendienteHelp")}
            style={{
              padding: "6px 12px", borderRadius: 6, fontSize: 12.5, whiteSpace: "nowrap",
              textDecoration: "none", opacity: .65,
              background: d.slug === slug ? "var(--brand)" : "transparent",
              color: d.slug === slug ? "#fff" : "var(--text-secondary)",
              border: "1px dashed var(--border-subtle)",
            }}>{d.name} ·</Link>
        ))}
        <Link href="/break-e/sin-clasificar"
          style={{ padding: "6px 12px", borderRadius: 6, fontSize: 12.5, whiteSpace: "nowrap",
            textDecoration: "none", color: "var(--text-secondary)",
            border: "1px dashed var(--border-subtle)" }}>{t("porDefecto100Fijo")}</Link>
      </div>

      {!generaIngreso && (
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 10 }}>
          {t.rich("noGeneraMargen", RICH)}
        </p>
      )}

      {nLinea > 0 && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 12, fontSize: 13,
          background: "rgba(255,193,7,.10)", border: "1px solid #c9971b", color: "#d6a626" }}>
          {t.rich("lineaBanner", { ...RICH, n: nLinea })}{" "}
          <button onClick={() => setSoloLinea(v => !v)}
            style={{ background: "none", border: "none", color: "inherit", cursor: "pointer",
              textDecoration: "underline", font: "inherit" }}>
            {soloLinea ? t("verTodas") : t("verSoloEsasLineas")}
          </button>
        </div>
      )}

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 12, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}

      {/* Sub-tabs por SECCIÓN: planilla, costo de ventas, gastos operativos…
          Con 55 líneas en un solo cuadro no se configura, se scrollea. */}
      <div className="fin-scroll-x" style={{ display: "flex", gap: 6, marginBottom: 10 }}>
        {["", ...listaSecciones].map(s => (
          <button key={s || "todas"} onClick={() => setSeccion(s)}
            style={{
              padding: "5px 11px", borderRadius: 6, fontSize: 12, cursor: "pointer",
              whiteSpace: "nowrap", border: "1px solid var(--border-subtle)",
              background: seccion === s ? "var(--bg-surface)" : "transparent",
              color: seccion === s ? "var(--text-primary)" : "var(--text-secondary)",
              fontWeight: seccion === s ? 700 : 400,
            }}>
            {s || t("todas")}{" "}
            <span style={{ opacity: .6 }}>
              {s ? filas.filter(f => (f.be_section || "—") === s).length : filas.length}
            </span>
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
        marginBottom: 12 }}>
        <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center",
          cursor: "pointer" }}
          title={t("consolidarHelp")}>
          <input type="checkbox" checked={consolidar}
            onChange={e => setConsolidar(e.target.checked)} />
          {t("consolidarHermanas")}
        </label>
        <span style={{ fontSize: 13 }}>
          {t.rich("totalesLinea", {
            ...RICH, n: filas.length,
            total: usd(tot(filas, "amount")),
            variable: usd(tot(filas, "amount_variable")),
            fijo: usd(tot(filas, "amount_fixed")),
          })}
        </span>
        <span style={{ flex: 1 }} />
        <label style={{ fontSize: 12.5 }}>
          {t("aplicarALaSeleccion", { n: sel.size })}{" "}
          <input value={masivo} onChange={e => setMasivo(e.target.value)}
            placeholder="%" style={{ width: 62, padding: "5px 7px", fontSize: 13,
              borderRadius: 5, border: "1px solid var(--border-subtle)",
              background: "var(--bg-input)", color: "var(--text-primary)" }} />
        </label>
        <button onClick={() => void aplicarMasivo()} style={{ padding: "7px 14px",
          borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600,
          border: "1px solid #1A7F4B", background: "transparent", color: "#1fa363" }}>
          {t("aplicar")}
        </button>
        <button onClick={() => void bajar()} style={{ padding: "7px 14px", borderRadius: 6,
          cursor: "pointer", fontSize: 13, border: "1px solid var(--border-medium)",
          background: "var(--bg-surface)", color: "var(--text-primary)" }}>⬇ Excel</button>
        <button onClick={() => void restablecer()} style={{ padding: "7px 14px",
          borderRadius: 6, cursor: "pointer", fontSize: 13,
          border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
          color: "var(--text-secondary)" }}>{t("restablecer")}</button>
      </div>

      <div className="fin-scroll-x">
        <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...TH, width: 30 }}></th>
              <th style={{ ...TH, textAlign: "left", width: 110 }}>{tc("account")}</th>
              <th style={{ ...TH, textAlign: "left" }}>{t("colDescripcion")}</th>
              <th style={TH}>{t("colAmount")}</th><th style={{ ...TH, width: 96 }}>{t("colPctVariable")}</th>
              <th style={TH}>{t("colPctFijo")}</th><th style={TH}>{t("colDollarVariable")}</th><th style={TH}>{t("colDollarFijo")}</th>
              <th style={{ ...TH, width: 70 }}></th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(secciones).map(([sec, xs]) => (
              <Fragment key={sec}>
                <tr style={{ background: "var(--bg-surface)" }}>
                  <td colSpan={9} style={{ ...IZQ, fontWeight: 700, fontSize: 12 }}>
                    <button onClick={() => setColapsadas(c => {
                      const n = new Set(c);
                      if (n.has(sec)) n.delete(sec); else n.add(sec);
                      return n;
                    })} style={{ background: "none", border: "none", cursor: "pointer",
                      color: "inherit", font: "inherit" }}>
                      {colapsadas.has(sec) ? "▸" : "▾"} {sec}
                    </button>
                    {" — "}{t("seccionResumen", { n: xs.length, monto: usd(totV(xs, "amount")) })}
                    <button onClick={() => void aplicarMasivo(sec)}
                      style={{ marginLeft: 10, background: "none", border: "none",
                        cursor: "pointer", color: "var(--brand)", fontSize: 11.5 }}>
                      {t("aplicarAlGrupo")}
                    </button>
                  </td>
                </tr>
                {!colapsadas.has(sec) && xs.map(({ f, hermanas }) => (
                  <tr key={f.id} style={{ opacity: f.excluded_from_be ? .6 : 1 }}>
                    <td style={TD}>
                      <input type="checkbox" checked={sel.has(f.id)}
                        disabled={f.excluded_from_be}
                        onChange={e => setSel(s => {
                          const n = new Set(s);
                          // Selecciona TODAS las hermanas: si no, «aplicar a la
                          // selección» dejaría dos códigos GL con % distinto.
                          for (const h of hermanas) {
                            if (e.target.checked) n.add(h.id); else n.delete(h.id);
                          }
                          return n;
                        })} />
                    </td>
                    <td style={IZQ}>
                      {f.map_source === "LINEA"
                        ? <span style={CHIP("rgba(201,151,27,.18)", "#d6a626")}
                            title={t("chipLineaHelp")}>
                            {t("chipLinea")}
                          </span>
                        : <span className="mono">
                            {hermanas.length > 1
                              ? <span title={t("codigosGl", { n: hermanas.length,
                                  codigos: hermanas.map(h => h.dept_code).join(", ") })}>
                                  {f.account} <span style={{ opacity: .6 }}>
                                    ×{hermanas.length}</span>
                                </span>
                              : `${f.dept_code}:${f.account}`}
                          </span>}
                    </td>
                    <td style={IZQ}>
                      {f.account_name}
                      {f.excluded_from_be && (
                        <span style={{ ...CHIP("rgba(150,150,150,.2)", "var(--text-secondary)"),
                          marginLeft: 8 }}
                          title={t("chipExcluidoHelp")}>
                          {t("chipExcluido")}
                        </span>
                      )}
                    </td>
                    <td style={TD}>{usd(f.amount)}</td>
                    <td style={TD}>
                      <input type="number" min={0} max={100} step={5}
                        disabled={f.excluded_from_be}
                        value={Math.round(f.pct_variable * 100)}
                        onChange={e => editar(hermanas, Number(e.target.value))}
                        style={{ width: 62, padding: "4px 6px", fontSize: 13, textAlign: "right",
                          borderRadius: 5, background: "var(--bg-input)",
                          color: "var(--text-primary)",
                          border: `1px solid ${estado[f.id] === "error"
                            ? "#c0392b" : "var(--border-subtle)"}` }} />
                    </td>
                    <td style={{ ...TD, color: "var(--text-secondary)" }}>{pct(f.pct_fixed, 0)}</td>
                    <td style={TD}>{usd(f.amount_variable)}</td>
                    <td style={TD}>{usd(f.amount_fixed)}</td>
                    <td style={{ ...TD, fontSize: 11, color: "var(--text-secondary)" }}>
                      {estado[f.id] === "guardando" ? tc("saving")
                        : estado[f.id] === "guardado" ? "✓"
                        : estado[f.id] === "error" ? tc("error") : ""}
                    </td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 14,
        maxWidth: 900, lineHeight: 1.6 }}>
        {t.rich("pctFijoNota", { ...RICH, code: (c: React.ReactNode) => <code>{c}</code> })}
      </p>
    </div>
  );
}
