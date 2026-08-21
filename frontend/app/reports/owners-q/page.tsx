"use client";
/**
 * Reports → Owners Q — el reporte mensual de P&L al propietario (POR/PAR).
 *
 * 33 columnas no caben en una pantalla, así que los seis bloques comparativos
 * se pliegan. Arranca mostrando lo que se mira siempre: el mes y el acumulado
 * del actual, con su presupuesto.
 *
 * Lo que NO se toca acá: la sangría y el orden de las filas vienen del
 * catálogo, no del código. El propietario lo lee por posición de fila.
 *
 * El tema es el del proyecto —variables CSS sobre fondo oscuro—, no clases de
 * Tailwind con colores propios: una pantalla que se pinta sola termina con
 * letra gris sobre gris el día que alguien mira el tema oscuro.
 */
import { CSSProperties, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import IrA from "@/components/IrA";
import {
  getOwnersQ, getOwnersQCobertura, downloadOwnersQExcel, crearOwnersQSnapshot,
  getOwnersQSnapshots, getOwnersQEscenarios, getOwnersQPeriodos,
  type OwnersQReporte, type OwnersQFila, type OwnersQSnapshot,
  type OwnersQEscenario, type OwnersQSeleccion, type OwnersQPeriodo,
} from "@/lib/api";

/** Las tres posiciones del reporte y qué va en cada una por defecto.
 *
 *  `budget` y `py` son COLUMNAS del formato, no una obligación: el owner puede
 *  poner ahí un Forecast Working, un Final, u otro mes. Lo que se envía
 *  es el default; salirse de él es una decisión visible, no un accidente.
 *
 *  El título y la ayuda de cada una salen del catálogo de idioma; acá queda
 *  solo la llave, que es lo que no cambia entre idiomas. */
const POSICIONES = [
  { key: "actual" as const },
  { key: "budget" as const },
  { key: "py" as const },
];

const GOLD = "#c8a24a";

/** Los 17 períodos, de respaldo LOCAL.
 *
 *  La lista buena la manda el backend —es su verdad— pero no puede ser la
 *  única: si esa llamada falla, el desplegable se queda SIN UNA SOLA OPCIÓN y
 *  la pantalla no dice por qué. Pasó de verdad en la ventana entre el
 *  despliegue del frontend y el del backend. Un control vacío y callado es
 *  peor que uno desactualizado. */
function periodosFallback(
  meses: string[], trimestres: string[], fullYear: string,
): OwnersQPeriodo[] {
  return [
    ...meses.map((etiqueta, i) => ({
      clave: `M${String(i + 1).padStart(2, "0")}`, etiqueta,
      tipo: "mes" as const, mes_cierre: i + 1,
    })),
    { clave: "Q1", etiqueta: trimestres[0], tipo: "trimestre" as const, mes_cierre: 3 },
    { clave: "Q2", etiqueta: trimestres[1], tipo: "trimestre" as const, mes_cierre: 6 },
    { clave: "Q3", etiqueta: trimestres[2], tipo: "trimestre" as const, mes_cierre: 9 },
    { clave: "Q4", etiqueta: trimestres[3], tipo: "trimestre" as const, mes_cierre: 12 },
    { clave: "FY", etiqueta: fullYear, tipo: "anio" as const, mes_cierre: 12 },
  ];
}
/** Los seis bloques de 4 columnas + los cuatro de variación.
 *  El título de cada uno sale del catálogo de idioma (ver `BLOQUE_TITULO`). */
const BLOQUES = [
  { key: "ptd_act", cols: ["A", "B", "C", "D"], base: true, varia: false },
  { key: "ptd_bud", cols: ["E", "F", "G", "H"], base: true, varia: false },
  { key: "ptd_vb", cols: ["I", "J"], base: true, varia: true },
  { key: "ptd_py", cols: ["K", "L", "M", "N"], base: false, varia: false },
  { key: "ptd_vpy", cols: ["O", "P"], base: false, varia: true },
  { key: "ytd_act", cols: ["R", "S", "T", "U"], base: true, varia: false },
  { key: "ytd_bud", cols: ["V", "W", "X", "Y"], base: false, varia: false },
  { key: "ytd_vb", cols: ["Z", "AA"], base: false, varia: true },
  { key: "ytd_py", cols: ["AB", "AC", "AD", "AE"], base: false, varia: false },
  { key: "ytd_vpy", cols: ["AF", "AG"], base: false, varia: true },
];

/** Qué mide cada columna. `% Rev`, `POR`, `PAR` y `% Var` son nomenclatura
 *  USALI y quedan igual en los dos idiomas; `valor` y `dif` se traducen. */
const SUB: Record<string, string> = {
  A: "valor", B: "pctRev", C: "por", D: "par",
  E: "valor", F: "pctRev", G: "por", H: "par",
  I: "dif", J: "pctVar",
  K: "valor", L: "pctRev", M: "por", N: "par",
  O: "dif", P: "pctVar",
  R: "valor", S: "pctRev", T: "por", U: "par",
  V: "valor", W: "pctRev", X: "por", Y: "par",
  Z: "dif", AA: "pctVar",
  AB: "valor", AC: "pctRev", AD: "por", AE: "par",
  AF: "dif", AG: "pctVar",
};

const ES_PCT = new Set(["B", "F", "J", "L", "P", "S", "W", "AA", "AC", "AG"]);

// ── Estilos, todos sobre las variables del tema ──────────────────────────────
const th: CSSProperties = {
  color: "var(--text-secondary)", fontWeight: 600, fontSize: 11,
  padding: "7px 10px", background: "var(--bg-header)",
  borderBottom: "1px solid var(--border-medium)", whiteSpace: "nowrap",
};
const tdNum: CSSProperties = {
  padding: "4px 10px", textAlign: "right", fontSize: 12,
  fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
  borderBottom: "1px solid var(--border-subtle)",
};
const boton: CSSProperties = {
  background: "var(--bg-elevated)", color: "var(--text-primary)",
  border: "1px solid var(--border-medium)", borderRadius: 6,
  padding: "6px 12px", fontSize: 12, cursor: "pointer",
};
const botonPrincipal: CSSProperties = {
  ...boton, background: "var(--brand)", borderColor: "var(--brand)", color: "#fff",
};
const campo: CSSProperties = {
  background: "var(--bg-input)", color: "var(--text-primary)",
  border: "1px solid var(--border-medium)", borderRadius: 4,
  padding: "5px 8px", fontSize: 12, outline: "none",
};
const etiquetaCampo: CSSProperties = {
  display: "block", fontSize: 10.5, color: "var(--text-secondary)",
  textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 3,
};

function aviso(tono: "error" | "alerta" | "neutro"): CSSProperties {
  const color = tono === "error" ? "var(--negative)"
    : tono === "alerta" ? "var(--warning)" : "var(--text-secondary)";
  return {
    border: `1px solid ${color}`, borderRadius: 8, padding: "10px 12px",
    fontSize: 12, color: "var(--text-primary)",
    background: "var(--bg-surface)", borderLeftWidth: 3,
  };
}

function fmt(valor: string | null, col: string, code: string): string {
  if (valor === null || valor === undefined) return "";
  const n = Number(valor);
  if (Number.isNaN(n)) return "";
  if (code === "STAT_OCC" || ES_PCT.has(col)) {
    return (n * 100).toLocaleString("es-CR",
      { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  }
  const s = Math.abs(n).toLocaleString("es-CR",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}

/** El estilo de cada tipo de fila. La jerarquía tiene que leerse sin números. */
function estiloFila(f: OwnersQFila): CSSProperties {
  if (f.line_type === "HEADER")
    return {
      background: "var(--bg-elevated)", fontWeight: 700, fontSize: 11,
      textTransform: "uppercase", letterSpacing: "0.06em", color: GOLD,
    };
  if (f.line_type === "SUBTOTAL" || f.line_type === "CALC")
    return {
      fontWeight: 700, background: "rgba(200,162,74,0.07)",
      borderTop: "1px solid var(--border-medium)", color: "var(--text-primary)",
    };
  // Estadística: noches, ADR, ocupación. No es plata — se distingue para que
  // nadie lea «162,00» como dólares.
  if (f.line_type === "STAT")
    return { fontSize: 11.5, color: "var(--text-secondary)" };
  return {};
}

export default function OwnersQPage() {
  const t = useTranslations("ownersQ");
  const tc = useTranslations("common");

  const POS_TITULO: Record<string, string> = {
    actual: t("posActual"), budget: t("posComparar"), py: t("posYContra"),
  };
  const POS_AYUDA: Record<string, string> = {
    actual: t("posAyudaActual"), budget: t("posAyudaBudget"), py: t("posAyudaPy"),
  };
  const BLOQUE_TITULO: Record<string, string> = {
    ptd_act: t("blkPtdAct"), ptd_bud: t("blkPtdBud"), ptd_vb: t("blkPtdVb"),
    ptd_py: t("blkPtdPy"), ptd_vpy: t("blkPtdVpy"), ytd_act: t("blkYtdAct"),
    ytd_bud: t("blkYtdBud"), ytd_vb: t("blkYtdVb"), ytd_py: t("blkYtdPy"),
    ytd_vpy: t("blkYtdVpy"),
  };
  const SUB_TITULO: Record<string, string> = {
    valor: t("subValor"), dif: t("subDif"),
    pctRev: "% Rev", por: "POR", par: "PAR", pctVar: "% Var",
  };
  const PERIODOS_FALLBACK = useMemo(() => periodosFallback(
    t.raw("mesesLargos") as string[],
    t.raw("trimestres") as string[],
    tc("fullYear"),
  ), [t, tc]);

  const hoy = new Date();
  const [anio, setAnio] = useState(hoy.getFullYear());
  // Arranca en el mes cerrado más reciente, que es lo que se reporta.
  const [periodo, setPeriodo] = useState(`M${String(Math.max(1, hoy.getMonth())).padStart(2, "0")}`);
  const [periodosBackend, setPeriodosBackend] = useState<OwnersQPeriodo[] | null>(null);
  const periodosDisp = periodosBackend ?? PERIODOS_FALLBACK;
  const [convencion, setConvencion] = useState<"favorable" | "raw">("favorable");
  const [escenarios, setEscenarios] = useState<OwnersQEscenario[]>([]);
  const [seleccion, setSeleccion] = useState<
    Partial<Record<"actual" | "budget" | "py", OwnersQSeleccion>>>({});
  const [rep, setRep] = useState<OwnersQReporte | null>(null);
  const [cobertura, setCobertura] =
    useState<Awaited<ReturnType<typeof getOwnersQCobertura>> | null>(null);
  const [snaps, setSnaps] = useState<OwnersQSnapshot[]>([]);
  const [abiertos, setAbiertos] = useState<Set<string>>(
    new Set(BLOQUES.filter(b => b.base).map(b => b.key)));
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true); setError(null);
    try {
      const [r, c, s] = await Promise.all([
        getOwnersQ(anio, periodo, { convencion, seleccion }),
        getOwnersQCobertura().catch(() => null),
        getOwnersQSnapshots().catch(() => []),
      ]);
      setRep(r); setCobertura(c); setSnaps(s);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error");
    } finally { setCargando(false); }
  }, [anio, periodo, convencion, seleccion]);

  useEffect(() => { void cargar(); }, [cargar]);
  useEffect(() => {
    getOwnersQEscenarios().then(setEscenarios).catch(() => {});
    // Si el backend responde, manda él; si no, quedan los de respaldo. Lo que
    // NO puede pasar es que el desplegable se quede vacío.
    getOwnersQPeriodos()
      .then(p => { if (p?.length) setPeriodosBackend(p); })
      .catch(() => {});
  }, []);

  const elegir = (pos: "actual" | "budget" | "py", campo: "escenario" | "periodo",
                  valor: string | null) =>
    setSeleccion(prev => ({ ...prev, [pos]: { ...prev[pos], [campo]: valor || null } }));

  const volverAlEstandar = () => setSeleccion({});

  const bajar = async () => {
    setBajando(true);
    try {
      const blob = await downloadOwnersQExcel(anio, periodo, { convencion, seleccion });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const aa = String(anio % 100).padStart(2, "0");
      const tramo = periodo.startsWith("M")
        ? ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
           "NOV", "DEC"][Number(periodo.slice(1)) - 1] + aa
        : periodo === "FY" ? `FY${aa}` : `${periodo}_${aa}`;
      a.href = url;
      a.download = `SCP_CWL_${tramo}_Statement_of_Income.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorBajar"));
    } finally { setBajando(false); }
  };

  const publicar = async () => {
    // Un snapshot es «lo que se ENVIÓ», y se envía un mes con
    // los tres bloques por defecto. Congelar un trimestre, el año, o una
    // comparación armada a mano guardaría como enviado algo que nunca se envió.
    if (!rep?.es_estandar) {
      alert(t("soloEstandar"));
      return;
    }
    if (!confirm(t("confirmarCongelar", {
      periodo: rep.periodo_etiqueta, anio: String(anio), convencion,
    }))) return;
    try {
      const r = await crearOwnersQSnapshot({ anio, mes: rep!.mes, convencion });
      alert(t("congeladoOk", { version: String(r.version) }));
      setSnaps(await getOwnersQSnapshots());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorPublicar"));
    }
  };

  const toggle = (k: string) => setAbiertos(prev => {
    const n = new Set(prev);
    if (n.has(k)) n.delete(k); else n.add(k);
    return n;
  });

  const visibles = BLOQUES.filter(b => abiertos.has(b.key));
  const publicado = snaps.find(s => s.anio === anio && s.mes === rep?.mes);

  // ── Barra de scroll horizontal ARRIBA ────────────────────────────────────
  // La tabla tiene 33 columnas y 48 filas: la barra de abajo queda fuera de la
  // pantalla y hay que recorrer el reporte entero para llegar a ella. Esta es
  // una copia sincronizada, pegada arriba, donde sí se ve.
  const grilla = useRef<HTMLDivElement>(null);
  const barra = useRef<HTMLDivElement>(null);
  const [anchoGrilla, setAnchoGrilla] = useState(0);

  useLayoutEffect(() => {
    const g = grilla.current;
    if (!g) return;
    const medir = () => setAnchoGrilla(g.scrollWidth);
    medir();
    // Si cambian los bloques visibles o el ancho de la ventana, el largo de la
    // barra tiene que seguirlos o deja de representar lo que se puede recorrer.
    const ro = new ResizeObserver(medir);
    ro.observe(g);
    return () => ro.disconnect();
  }, [rep, visibles.length]);

  /** Las dos barras mueven la misma tabla, sin rebotar entre sí.
   *
   *  Se asigna SOLO si difiere. Si ya son iguales el navegador no dispara otro
   *  `scroll`, así que el rebote se corta solo y no hace falta cerrojo.
   *
   *  Había uno, liberado con `requestAnimationFrame`, y estaba mal: `rAF` no
   *  corre cuando la pestaña no está componiendo, así que el cerrojo se
   *  quedaba trabado y la sincronización moría en un sentido. Se vio
   *  probándolo, no leyéndolo.
   *
   *  Los refs se leen AL HACER SCROLL, no al renderizar: en el primer render
   *  todavía son `null` y el manejador quedaría mudo para siempre. */
  const espeja = useCallback((
    desde: React.RefObject<HTMLDivElement | null>,
    hacia: React.RefObject<HTMLDivElement | null>,
  ) => () => {
    const a = desde.current, b = hacia.current;
    if (!a || !b || b.scrollLeft === a.scrollLeft) return;
    b.scrollLeft = a.scrollLeft;
  }, []);

  return (
    <div className="pag pag-ancha" style={{ padding: 20 }}>
      <IrA />
      <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0,
                   color: "var(--text-primary)" }}>
        Owners Q
      </h1>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0" }}>
        {t.rich("subtitulo", {
          mono: (c: React.ReactNode) => <span className="mono">{c}</span>,
        })}
      </p>

      {/* Barra de control */}
      <div style={{
        display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 12,
        marginTop: 14, padding: 12, borderRadius: 10,
        background: "var(--bg-surface)", border: "1px solid var(--border-medium)",
      }}>
        <label>
          <span style={etiquetaCampo}>{tc("year")}</span>
          <input type="number" value={anio} onChange={e => setAnio(Number(e.target.value))}
                 style={{ ...campo, width: 88 }} />
        </label>
        <label>
          <span style={etiquetaCampo}>{t("periodo")}</span>
          <select value={periodo} onChange={e => setPeriodo(e.target.value)}
                  style={{ ...campo,
                           borderColor: rep && !rep.es_un_mes
                             ? "var(--warning)" : "var(--border-medium)" }}>
            {periodosDisp.map(p => (
              <option key={p.clave} value={p.clave}>{p.etiqueta}</option>
            ))}
          </select>
        </label>
        <label>
          <span style={etiquetaCampo}>{t("convencion")}</span>
          <select value={convencion}
                  onChange={e => setConvencion(e.target.value as "favorable" | "raw")}
                  style={campo}>
            <option value="favorable">{t("convFavorable")}</option>
            <option value="raw">{t("convRaw")}</option>
          </select>
        </label>
        <div style={{ flex: 1 }} />
        {rep && !rep.es_estandar && (
          <button onClick={volverAlEstandar}
                  style={{ ...boton, borderColor: "var(--warning)",
                           color: "var(--warning)" }}>
            {t("volverEstandar")}
          </button>
        )}
        <button onClick={bajar} disabled={bajando || !rep}
                style={{ ...botonPrincipal, opacity: bajando || !rep ? 0.5 : 1 }}>
          {bajando ? t("generando") : t("bajarExcel")}
        </button>
        <button onClick={publicar} disabled={!rep?.es_estandar}
                title={rep && !rep.es_estandar
                  ? t("congelarSoloEstandarAyuda")
                  : t("congelarAyuda")}
                style={{ ...boton, opacity: rep?.es_estandar ? 1 : 0.45,
                         cursor: rep?.es_estandar ? "pointer" : "not-allowed" }}>
          {t("congelar")}
        </button>
      </div>

      {/* Qué va en cada una de las tres posiciones */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8, padding: 12,
        borderRadius: 10, background: "var(--bg-surface)",
        border: `1px solid ${rep && !rep.es_estandar ? "var(--warning)" : "var(--border-medium)"}`,
      }}>
        {POSICIONES.map(pos => {
          const b = rep?.bloques?.[pos.key];
          const propio = !!(seleccion[pos.key]?.escenario || seleccion[pos.key]?.periodo);
          return (
            <div key={pos.key} style={{ minWidth: 250 }}>
              <span style={etiquetaCampo}>
                {POS_TITULO[pos.key]}{" "}
                <span style={{ textTransform: "none", letterSpacing: 0, opacity: 0.6 }}>
                  {POS_AYUDA[pos.key]}
                </span>
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <select value={seleccion[pos.key]?.escenario ?? ""}
                        onChange={e => elegir(pos.key, "escenario", e.target.value)}
                        style={{ ...campo, flex: 1,
                                 borderColor: propio ? "var(--warning)" : "var(--border-medium)" }}>
                  <option value="">
                    {b ? t("porDefectoCon", { etiqueta: b.etiqueta }) : t("porDefecto")}
                  </option>
                  {escenarios.map(e => (
                    <option key={e.id} value={e.id}>{e.etiqueta}</option>
                  ))}
                </select>
                {/* Un bloque puede correr sobre OTRO mes: junio contra mayo. */}
                <select value={seleccion[pos.key]?.periodo ?? ""}
                        onChange={e => elegir(pos.key, "periodo", e.target.value || null)}
                        title={t("periodoDeEstaPosicion")}
                        style={{ ...campo, width: 128,
                                 borderColor: propio ? "var(--warning)" : "var(--border-medium)" }}>
                  <option value="">{t("mismoPeriodo")}</option>
                  {periodosDisp.map(p => (
                    <option key={p.clave} value={p.clave}>{p.etiqueta}</option>
                  ))}
                </select>
              </div>
            </div>
          );
        })}
      </div>

      {/* Avisos que no se pueden ignorar */}
      <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
        {rep && !rep.es_estandar && (
          <div style={aviso("alerta")}>
            <b>{t("noEstandarTitulo")}</b>{" "}
            {!rep.es_un_mes && <>{t.rich("noEstandarMes", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              periodo: rep.periodo_etiqueta,
            })} </>}{t("noEstandarResto")}{" "}
            {/* ⚠️ La posición viaja JUNTO al bloque. Antes era
                `.map(...).filter(Boolean).map((b, i) => POSICIONES[i])`: al
                filtrar un bloque nulo los índices se corren, y la etiqueta
                pasa a nombrar el escenario EQUIVOCADO. En un reporte que va a
                los dueños, eso es peor que no mostrarlo. */}
            {POSICIONES.map(p => ({ p, b: rep.bloques?.[p.key] }))
              .filter(x => x.b)
              .map(({ p, b }) => `${POS_TITULO[p.key]} = ${b!.etiqueta} (${b!.periodo_etiqueta})`)
              .join(" · ")}
          </div>
        )}
        {error && <div style={aviso("error")}>{error}</div>}

        {cobertura && !cobertura.ok && (
          <div style={aviso("error")}>
            {t.rich("cobertura", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              code: (c: React.ReactNode) => <code>{c}</code>,
              lista: cobertura.huerfanas.join(", ") || "—",
            })}
          </div>
        )}

        {rep && rep.identidades_falladas.length > 0 && (
          <div style={aviso("alerta")}>
            {t.rich("noCuadra", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              n: rep.identidades_falladas.length,
            })}
            <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {rep.identidades_falladas.slice(0, 6).map((x, i) => (
                <li key={i}>
                  {t("identidadFila", {
                    identidad: x.identidad, columna: x.columna,
                    esperado: x.esperado, obtenido: x.obtenido,
                  })}
                </li>
              ))}
            </ul>
          </div>
        )}

        {rep && rep.verificacion_d1.ok === false && (
          <div style={aviso("alerta")}>
            {t.rich("d1NoVerifica", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              i: (c: React.ReactNode) => <i>{c}</i>,
              brecha: rep.verificacion_d1.brecha ?? "",
              otroIngreso: rep.verificacion_d1.rev_rooms_other ?? "",
              delta: rep.verificacion_d1.delta ?? "",
            })}
          </div>
        )}

        {publicado && (
          <div style={aviso("neutro")}>
            {t.rich("yaCongelado", {
              b: (c: React.ReactNode) => <b>{c}</b>,
              code: (c: React.ReactNode) => <code>{c}</code>,
              version: String(publicado.version),
              convencion: publicado.convencion,
              mapeo: publicado.mapping_version,
            })}
          </div>
        )}

        {rep && rep.excepciones.length > 0 && (
          <details style={aviso("neutro")}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>
              {t("panelExcepciones", { n: rep.excepciones.length })}
            </summary>
            <table style={{ width: "100%", marginTop: 8, borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...th, textAlign: "left" }}>{tc("dept")}</th>
                  <th style={{ ...th, textAlign: "left" }}>{tc("account")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("monto")}</th>
                  <th style={{ ...th, textAlign: "left" }}>{t("filaDestino")}</th>
                </tr>
              </thead>
              <tbody>
                {rep.excepciones.map((e, i) => (
                  <tr key={i}>
                    <td style={{ ...tdNum, textAlign: "left" }}>{e.dept_code || "—"}</td>
                    <td style={{ ...tdNum, textAlign: "left" }}>{e.account_code}</td>
                    <td style={tdNum}>
                      {Number(e.monto).toLocaleString("es-CR", { minimumFractionDigits: 2 })}
                    </td>
                    <td style={{ ...tdNum, textAlign: "left" }}>{e.fila_destino}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </div>

      {/* Qué bloques mostrar */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 14 }}>
        {BLOQUES.map(b => {
          const on = abiertos.has(b.key);
          return (
            <button key={b.key} onClick={() => toggle(b.key)}
                    style={{
                      ...boton, borderRadius: 999, padding: "4px 12px", fontSize: 11,
                      background: on ? "var(--brand)" : "var(--bg-elevated)",
                      borderColor: on ? "var(--brand)" : "var(--border-medium)",
                      color: on ? "#fff" : "var(--text-secondary)",
                    }}>
              {BLOQUE_TITULO[b.key]}
            </button>
          );
        })}
      </div>

      {cargando && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 14 }}>
          {tc("loading")}
        </div>
      )}

      {rep && !cargando && (
        <>
        {/* `fin-scroll-x` es la convención de la app para un contenedor que
            scrollea en horizontal. Acá adentro no hay tabla —solo el espaciador
            que le da largo a la barra— pero la clase se declara igual: la regla
            existe para que nadie tenga que revisar caso por caso. */}
        <div ref={barra} className="fin-scroll-x fin-scroll-espejo"
             onScroll={espeja(barra, grilla)}
             style={{
               marginTop: 10,
               border: "1px solid var(--border-medium)",
               borderBottom: "none", borderRadius: "8px 8px 0 0",
               background: "var(--bg-surface)",
             }}>
          <div style={{ width: anchoGrilla, height: 1 }} />
        </div>
        <div ref={grilla} className="fin-sticky"
             onScroll={espeja(grilla, barra)}
             style={{
               background: "var(--bg-base)",
               border: "1px solid var(--border-medium)",
               borderTop: "none", borderRadius: "0 0 10px 10px",
             }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={{
                  ...th, position: "sticky", left: 0, zIndex: 5, minWidth: 320,
                  textAlign: "left", fontSize: 12, color: "var(--text-primary)",
                }}>
                  {rep.periodo_etiqueta} {anio}
                </th>
                {visibles.map(b => (
                  <th key={b.key} colSpan={b.cols.length}
                      style={{
                        ...th, textAlign: "center",
                        color: b.varia ? "var(--warning)" : GOLD,
                        borderLeft: "1px solid var(--border-medium)",
                        textTransform: "uppercase", letterSpacing: "0.05em",
                      }}>
                    {BLOQUE_TITULO[b.key]}
                  </th>
                ))}
              </tr>
              <tr>
                <th style={{ ...th, position: "sticky", left: 0, zIndex: 5 }} />
                {visibles.flatMap(b => b.cols.map((c, i) => (
                  <th key={c} style={{
                    ...th, textAlign: "right", fontSize: 10.5,
                    borderLeft: i === 0 ? "1px solid var(--border-medium)" : undefined,
                  }}>
                    {SUB_TITULO[SUB[c]]}
                  </th>
                )))}
              </tr>
            </thead>
            <tbody>
              {rep.filas.map(f => {
                const est = estiloFila(f);
                // El fondo de la celda pegada tiene que ser OPACO y el mismo de
                // su fila: si es transparente, las columnas pasan por debajo al
                // hacer scroll y la etiqueta se vuelve ilegible.
                const fondo = (est.background as string) || "var(--bg-base)";
                return (
                  <tr key={f.report_code} style={est}>
                    <td style={{
                      ...tdNum, textAlign: "left", position: "sticky", left: 0, zIndex: 2,
                      background: fondo, paddingLeft: 10 + (f.indent - 1) * 16,
                      color: est.color ?? "var(--text-primary)",
                      fontWeight: est.fontWeight,
                    }} title={t("tituloFila", { n: String(f.row_no), code: f.report_code })}>
                      {f.label}
                    </td>
                    {visibles.flatMap(b => b.cols.map((c, i) => {
                      const v = f.celdas[c];
                      const n = v === null ? null : Number(v);
                      return (
                        <td key={c} style={{
                          ...tdNum,
                          borderLeft: i === 0 ? "1px solid var(--border-medium)" : undefined,
                          color: n !== null && n < 0 ? "var(--negative)" : undefined,
                        }}>
                          {f.line_type === "HEADER" ? "" : fmt(v, c, f.report_code)}
                        </td>
                      );
                    }))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        </>
      )}

      {rep && (
        <p style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 8 }}>
          {t.rich("pie", {
            i: (c: React.ReactNode) => <i>{c}</i>,
            ptd: String(rep.rooms_available_ptd),
            ytd: String(rep.rooms_available_ytd),
            mapeo: rep.mapping_version,
          })}
        </p>
      )}
    </div>
  );
}
