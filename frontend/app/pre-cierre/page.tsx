"use client";
/**
 * Pre-Cierre — la revisión integral de los actuales antes de declararlos finales.
 *
 * Se sube el estado de resultados CRUDO de Integrity, el sistema arma la hoja
 * de revisión y entrega el informe de varianzas y discrepancias. Recién cuando
 * convence, se pasa a Final.
 *
 * ## El orden de las pestañas no es casual
 *
 * **Hallazgos va primero.** Es la razón de ser del módulo: hasta hoy la
 * revisión pasaba por el ojo de una persona sobre un Excel de 104 MB, y por ahí
 * podía entrar cualquier cosa. Poner la hoja primero invitaría a mirar los
 * totales —que casi siempre cuadran— y saltarse lo que no cuadra.
 *
 * **Y se muestra lo que NO se pudo revisar.** «No se miró» y «está bien» se ven
 * igual en una lista vacía.
 *
 * ## Subir de nuevo es lo normal
 *
 * El mismo mes se sube muchas veces: se corrige un error de posteo y se vuelve
 * a subir, hasta el cierre acordado. Por eso el formulario no desaparece
 * después de la primera carga y la pantalla dice en qué vuelta va.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import {
  precierreExcelUrl, cambiosPrecierre, descartarPrecierre,
  hallazgosPrecierre, listarPrecierres,
  pasarPrecierreAFinal, subirPrecierre, verPrecierre,
  type PrecierreCambios, type PrecierreFilaHoja, type PrecierreHallazgo,
  type PrecierreResumen,
} from "@/lib/api";

const MESES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"];

const COLOR: Record<string, string> = {
  critico: "#B42318", aviso: "#B54708", info: "#475467",
};
const FONDO: Record<string, string> = {
  critico: "#FEF3F2", aviso: "#FFFAEB", info: "#F9FAFB",
};

const usd = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

type Pestana = "hallazgos" | "hoja" | "cambios" | "descargas";

export default function PreCierrePage() {
  const t = useTranslations("precierre");
  const hoy = new Date();

  const [lista, setLista] = useState<PrecierreResumen[]>([]);
  const [id, setId] = useState<string | null>(null);
  const [pestana, setPestana] = useState<Pestana>("hallazgos");

  const [archivo, setArchivo] = useState<File | null>(null);
  const [tc, setTc] = useState("");
  const [mes, setMes] = useState(hoy.getMonth() || 12);
  const [anio, setAnio] = useState(hoy.getFullYear());
  const [subiendo, setSubiendo] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [hoja, setHoja] = useState<PrecierreFilaHoja[]>([]);
  const [estado, setEstado] = useState<string>("");
  const [hallazgos, setHallazgos] = useState<PrecierreHallazgo[]>([]);
  const [cambios, setCambios] = useState<PrecierreCambios | null>(null);
  const [sinRevisar, setSinRevisar] = useState<string[]>([]);
  const [comparativos, setComparativos] = useState<Record<string, string>>({});
  const [umbralMonto, setUmbralMonto] = useState(5000);
  const [umbralPct, setUmbralPct] = useState(10);
  const [abierto, setAbierto] = useState<string | null>(null);

  const recargarLista = useCallback(async () => {
    try { setLista((await listarPrecierres()).precierres); } catch { /* nada */ }
  }, []);

  useEffect(() => { void recargarLista(); }, [recargarLista]);

  /**
   * Abrir solo el borrador VIVO, sin tener que buscarlo entre los chips.
   *
   * Owner, 2026-09-11: con diez vueltas de agosto los ocho chips visibles
   * decían «descartado» y no había ninguno seleccionado, así que la pantalla se
   * veía vacía y parecía que la subida no había entrado. El orden del backend ya
   * pone el más nuevo primero; esto además lo ABRE.
   *
   * Solo cuando no hay nada elegido: si el owner clickeó una vuelta vieja a
   * propósito, no se la movemos abajo de los pies.
   */
  useEffect(() => {
    if (id || !lista.length) return;
    const vivo = lista.find(p => p.estado === "borrador") ?? lista[0];
    if (vivo) setId(vivo.id);
  }, [lista, id]);

  const cargar = useCallback(async (pid: string) => {
    setError(null);
    try {
      const [d, h, c] = await Promise.all([
        verPrecierre(pid),
        hallazgosPrecierre(pid, { umbralMonto, umbralPct }),
        cambiosPrecierre(pid),
      ]);
      setHoja(d.hoja);
      setEstado(d.estado);
      setHallazgos(h.hallazgos);
      setCambios(c);
      setSinRevisar(h.sin_revisar);
      setComparativos(h.comparativos);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [umbralMonto, umbralPct]);

  useEffect(() => { if (id) void cargar(id); }, [id, cargar]);

  async function subir() {
    if (!archivo || !tc) return;
    setSubiendo(true); setError(null); setAviso(null);
    try {
      const r = await subirPrecierre(archivo, { tc, mes, anio });
      setId(r.id);
      // Owner, 2026-09-11: «necesito que cada vez que suba se guarde la versión
      // anterior y compare qué tanto cambió versus la versión, y la varianza».
      // Eso ya se calcula; lo que faltaba era llegar. En la primera vuelta del
      // mes no hay contra qué comparar, así que se queda en hallazgos.
      if (r.reemplaza_a) setPestana("cambios");
      setAviso(r.reemplaza_a
        ? t("vueltaN", { n: r.vuelta, archivo: r.reemplaza_a.archivo })
        : t("cargado", { filas: r.filas }));
      await recargarLista();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setSubiendo(false); }
  }

  async function pasarAFinal(confirmar: boolean) {
    if (!id) return;
    setError(null); setAviso(null);
    try {
      const r = await pasarPrecierreAFinal(id, { confirmarDiferencias: confirmar });
      setAviso(t("pasado", { n: r.hallazgos_abiertos ?? 0 }));
      setEstado("pasado_a_final");
      await recargarLista();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  //: Qué le falta al formulario, en el orden en que se llena. `null` = listo.
  const falta = !archivo ? t("faltaArchivo") : !tc ? t("faltaTc") : null;
  const criticos = hallazgos.filter(h => h.gravedad === "critico").length;
  const dl = id ? precierreExcelUrl(id) : null;

  return (
    <main style={{ padding: "24px 28px", maxWidth: 1180, margin: "0 auto" }}>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>{t("titulo")}</h1>
      <p style={{ color: "var(--text-secondary)", marginBottom: 20, maxWidth: 760 }}>
        {t("bajada")}
      </p>

      {/* ── Subir ─────────────────────────────────────────────────────────── */}
      <section style={caja}>
        <div style={{ display: "flex", gap: 14, alignItems: "flex-end", flexWrap: "wrap" }}>
          <Campo etiqueta={t("archivo")}>
            <input type="file" accept=".xlsx"
                   onChange={e => setArchivo(e.target.files?.[0] ?? null)} />
          </Campo>
          <Campo etiqueta={t("tc")} ayuda={t("tcAyuda")}>
            <input value={tc} onChange={e => setTc(e.target.value)}
                   placeholder="454.75" inputMode="decimal" style={input} />
          </Campo>
          <Campo etiqueta={t("mes")}>
            <select value={mes} onChange={e => setMes(Number(e.target.value))} style={input}>
              {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </Campo>
          <Campo etiqueta={t("anio")}>
            <input type="number" value={anio} onChange={e => setAnio(Number(e.target.value))}
                   style={{ ...input, width: 90 }} />
          </Campo>
          {/* ⚠️ El botón DICE por qué no se puede, y se ve apagado.
              Antes usaba `style={boton}` a secas: deshabilitado quedaba igual
              de azul y con el cursor de mano, así que se clickeaba y no pasaba
              nada. El tipo de cambio es el caso típico: su placeholder gris se
              lee como un valor ya puesto. */}
          <button onClick={subir} disabled={!!falta || subiendo}
                  title={falta ?? undefined}
                  style={{ ...boton, opacity: (falta || subiendo) ? 0.45 : 1,
                           cursor: (falta || subiendo) ? "not-allowed" : "pointer" }}>
            {subiendo ? t("subiendo") : t("subir")}
          </button>
          {falta && !subiendo && (
            <span style={{ fontSize: 12, color: "var(--text-secondary)",
                           alignSelf: "center" }}>{falta}</span>
          )}
        </div>
        {lista.length > 0 && (
          <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {/* ⚠️ La HORA y el TC en el chip, no solo el mes y el estado.
                Con diez vueltas del mismo mes todos decían «Agosto 2026 ·
                descartado» y eran indistinguibles: no había forma de saber cuál
                era cuál, ni de notar que faltaba el vivo (owner, 2026-09-11). */}
            {lista.slice(0, 8).map(p => (
              <button key={p.id} onClick={() => setId(p.id)}
                      style={{ ...chip, ...(p.id === id ? chipActivo : {}),
                               ...(p.estado === "borrador"
                                   ? { fontWeight: 700,
                                       borderColor: "var(--brand)" } : {}) }}>
                {MESES[p.mes - 1]} {p.anio}
                {p.creado_en ? " · " + new Date(p.creado_en).toLocaleTimeString(
                  undefined, { hour: "2-digit", minute: "2-digit" }) : ""}
                {p.tc ? ` · ${p.tc}` : ""}
                {" · "}{t(`estado.${p.estado}`)}
              </button>
            ))}
          </div>
        )}
      </section>

      {aviso && <Nota tono="ok">{aviso}</Nota>}
      {error && <Nota tono="mal">{error}</Nota>}

      {id && (
        <>
          {estado !== "pasado_a_final" && (
            <Nota tono="ojo">{t("todaviaNoEsta")}</Nota>
          )}

          <nav style={{ display: "flex", gap: 4, margin: "18px 0 12px" }}>
            {(["hallazgos", "hoja", "cambios", "descargas"] as Pestana[]).map(p => (
              <button key={p} onClick={() => setPestana(p)}
                      style={{ ...tab, ...(pestana === p ? tabActivo : {}) }}>
                {t(`tab.${p}`)}
                {p === "hallazgos" && criticos > 0 && (
                  <span style={pill}>{criticos}</span>
                )}
              </button>
            ))}
          </nav>

          {pestana === "hallazgos" && (
            <Hallazgos
              hallazgos={hallazgos} sinRevisar={sinRevisar}
              comparativos={comparativos}
              umbralMonto={umbralMonto} umbralPct={umbralPct}
              setUmbralMonto={setUmbralMonto} setUmbralPct={setUmbralPct}
              abierto={abierto} setAbierto={setAbierto} t={t} />
          )}
          {pestana === "hoja" && dl && (
            <Hoja filas={hoja} hojaExcelUrl={dl.hoja} t={t} />
          )}
          {pestana === "cambios" && <Cambios datos={cambios} t={t} />}
          {pestana === "descargas" && dl && <Descargas dl={dl} t={t} />}

          {/* ── Pasar a Final ─────────────────────────────────────────────── */}
          {estado !== "pasado_a_final" && (
            <section style={{ ...caja, marginTop: 20 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
                {t("final.titulo")}
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 12 }}>
                {hallazgos.length > 0
                  ? t("final.conHallazgos", { n: hallazgos.length, criticos })
                  : t("final.sinHallazgos")}
              </p>
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => pasarAFinal(false)} style={boton}>
                  {t("final.pasar")}
                </button>
                <button onClick={() => pasarAFinal(true)} style={botonSecundario}>
                  {t("final.pasarConfirmando")}
                </button>
                <button onClick={async () => {
                  if (!id) return;
                  await descartarPrecierre(id); setId(null); await recargarLista();
                }} style={botonSuave}>
                  {t("final.descartar")}
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}

/* ── Hallazgos ─────────────────────────────────────────────────────────────── */

/**
 * El detalle de un hallazgo, como TABLA cuando habla de cuentas.
 *
 * Antes era `JSON.stringify(...slice(0, 30))`. Owner, 2026-09-11: «solo que me
 * diga qué cuentas no están subiendo cuando estoy en proceso de subida». Un
 * volcado de JSON recortado a 30 no contesta esa pregunta: no se puede leer de
 * un vistazo, no se puede ordenar por monto y, si son más de 30, esconde
 * justamente las que faltan.
 *
 * Se muestran TODAS, ordenadas por monto descendente — lo que más plata mueve
 * primero — dentro de un contenedor con scroll propio. Las referencias que no
 * hablan de cuentas (por ejemplo `{ linea: "REV_ROOMS" }`) siguen cayendo al
 * volcado de siempre: inventarles columnas sería peor.
 */
function Referencias({ filas }: { filas: Array<Record<string, unknown>> }) {
  const esDeCuentas = filas.length > 0 && filas.every(f => "cuenta" in f);
  if (!esDeCuentas) {
    return <pre style={pre}>{JSON.stringify(filas.slice(0, 30), null, 1)}</pre>;
  }
  const conLinea = filas.some(f => f.linea);
  const orden = [...filas].sort(
    (a, b) => Math.abs(Number(b.monto ?? 0)) - Math.abs(Number(a.monto ?? 0)));
  const total = orden.reduce((s, f) => s + Number(f.monto ?? 0), 0);
  const th: React.CSSProperties = {
    textAlign: "left", padding: "4px 8px", fontSize: 11, fontWeight: 700,
    textTransform: "uppercase", letterSpacing: .3, color: "var(--text-secondary)",
    borderBottom: "1px solid var(--border-medium)", position: "sticky", top: 0,
    background: "var(--bg-surface)",
  };
  const td: React.CSSProperties = {
    padding: "3px 8px", borderBottom: "1px solid var(--border-subtle)",
    whiteSpace: "nowrap",
  };
  const num: React.CSSProperties = {
    ...td, textAlign: "right", fontVariantNumeric: "tabular-nums",
    fontFamily: "var(--font-mono)",
  };
  return (
    <div style={{ maxHeight: 320, overflow: "auto", marginTop: 6,
                  border: "1px solid var(--border-subtle)", borderRadius: 4 }}>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
        <thead>
          <tr>
            <th style={th}>Cuenta</th>
            <th style={th}>Depto</th>
            <th style={th}>Descripción</th>
            {conLinea && <th style={th}>Cayó en</th>}
            <th style={{ ...th, textAlign: "right" }}>US$</th>
          </tr>
        </thead>
        <tbody>
          {orden.map((f, i) => (
            <tr key={`${String(f.cuenta)}-${i}`}>
              <td style={{ ...td, fontFamily: "var(--font-mono)" }}>{String(f.cuenta ?? "")}</td>
              <td style={{ ...td, fontFamily: "var(--font-mono)" }}>{String(f.depto ?? "")}</td>
              <td style={{ ...td, whiteSpace: "normal" }}>{String(f.nombre ?? "")}</td>
              {conLinea && <td style={td}>{String(f.linea ?? "")}</td>}
              <td style={num}>{usd(Number(f.monto ?? 0))}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td style={{ ...td, fontWeight: 700 }} colSpan={conLinea ? 4 : 3}>
              {orden.length} filas
            </td>
            <td style={{ ...num, fontWeight: 700 }}>{usd(total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}


function Hallazgos({ hallazgos, sinRevisar, comparativos, umbralMonto, umbralPct,
                     setUmbralMonto, setUmbralPct, abierto, setAbierto, t }: {
  hallazgos: PrecierreHallazgo[]; sinRevisar: string[];
  comparativos: Record<string, string>;
  umbralMonto: number; umbralPct: number;
  setUmbralMonto: (n: number) => void; setUmbralPct: (n: number) => void;
  abierto: string | null; setAbierto: (s: string | null) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <>
      <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 12,
                    flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {t("umbrales")}
        </span>
        <label style={etiquetaChica}>US$
          <input type="number" value={umbralMonto} style={{ ...input, width: 90 }}
                 onChange={e => setUmbralMonto(Number(e.target.value))} />
        </label>
        <label style={etiquetaChica}>%
          <input type="number" value={umbralPct} style={{ ...input, width: 70 }}
                 onChange={e => setUmbralPct(Number(e.target.value))} />
        </label>
        {Object.entries(comparativos).map(([k, v]) => (
          <span key={k} style={chip}>{k}: {v}</span>
        ))}
      </div>

      {hallazgos.length === 0 && (
        <Nota tono="ok">{t("sinHallazgos")}</Nota>
      )}

      {hallazgos.map(h => (
        <article key={h.clave}
                 style={{ ...caja, borderLeft: `4px solid ${COLOR[h.gravedad]}`,
                          background: FONDO[h.gravedad], marginBottom: 10 }}>
          <button onClick={() => setAbierto(abierto === h.clave ? null : h.clave)}
                  style={{ all: "unset", cursor: "pointer", display: "block", width: "100%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 700, color: COLOR[h.gravedad],
                               textTransform: "uppercase", letterSpacing: .4 }}>
                  {t(`gravedad.${h.gravedad}`)} · {t("nivel", { n: h.nivel })}
                </span>
                <div style={{ fontWeight: 600, marginTop: 2 }}>{h.titulo}</div>
              </div>
              {h.monto !== 0 && (
                <div style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700,
                              whiteSpace: "nowrap" }}>
                  US$ {usd(h.monto)}
                </div>
              )}
            </div>
            <p style={{ fontSize: 13, marginTop: 6, color: "var(--text-secondary)" }}>
              {h.detalle}
            </p>
          </button>
          {abierto === h.clave && (
            <div style={{ marginTop: 10, fontSize: 13, display: "grid", gap: 8 }}>
              <p><b>{t("porque")}</b> {h.porque}</p>
              <p><b>{t("queHacer")}</b> {h.que_hacer}</p>
              {h.referencias.length > 0 && (
                <details>
                  <summary style={{ cursor: "pointer" }}>
                    {t("verDetalle", { n: h.referencias.length })}
                  </summary>
                  <Referencias filas={h.referencias} />
                </details>
              )}
            </div>
          )}
        </article>
      ))}

      {/* ⚠️ Lo que NO se pudo revisar. Una lista de hallazgos vacía puede
          significar «está todo bien» o «no se miró nada». */}
      {sinRevisar.length > 0 && (
        <section style={{ ...caja, marginTop: 14 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, marginBottom: 6 }}>
            {t("sinRevisar")}
          </h3>
          <ul style={{ fontSize: 13, color: "var(--text-secondary)", paddingLeft: 18 }}>
            {sinRevisar.map(x => <li key={x}>{x}</li>)}
          </ul>
        </section>
      )}
    </>
  );
}

/* ── La hoja de revisión ───────────────────────────────────────────────────── */

function Hoja({ filas, hojaExcelUrl, t }: {
  filas: PrecierreFilaHoja[]; hojaExcelUrl: string;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    // `fin-scroll-x`: la convención de la app para un contenedor que scrollea
    // en horizontal. Sin ella el encabezado pegajoso se corre 44px y tapa la
    // primera fila — no da error, el dato está bien, y sólo se nota mirando.
    <div className="fin-scroll-x" style={{ ...caja, overflowX: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "baseline", marginBottom: 10, gap: 12 }}>
        <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {t("hojaAyuda")}
        </p>
        {/* La descarga va ACÁ, junto al cuadro. Mandar al usuario a otra
            pestaña para bajar lo que está mirando es una pestaña de más. */}
        <a href={hojaExcelUrl} style={{ fontSize: 13, whiteSpace: "nowrap" }}>
          {t("bajarEstaHoja")}
        </a>
      </div>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
        <tbody>
          {filas.map(f => {
            const total = f.etiqueta === f.etiqueta.toUpperCase();
            return (
              <tr key={f.fila} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={{ padding: "5px 10px", fontWeight: total ? 700 : 400 }}>
                  {f.etiqueta}
                </td>
                <td style={{ padding: "5px 10px", textAlign: "right",
                             fontVariantNumeric: "tabular-nums",
                             fontWeight: total ? 700 : 400 }}>
                  {f.actual == null ? "" : usd(f.actual)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ── Qué cambió ────────────────────────────────────────────────────────────── */
/**
 * El diff contra la vuelta anterior del mismo mes.
 *
 * ⚠️ **«Desaparecieron» va con aviso y no es decoración.** Una cuenta que se
 * movió salta a la vista porque el total cambia; una que se fue no hace ruido
 * en ningún total, porque el total baja con ella. Es el único de los tres
 * grupos que hay que leer aunque esté vacío.
 */
function Cambios({ datos, t }: {
  datos: PrecierreCambios | null;
  t: ReturnType<typeof useTranslations>;
}) {
  if (!datos) return null;
  if (!datos.anterior) {
    return <div style={caja}>
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        {t("cambios.primera")}
      </p>
    </div>;
  }
  const cuando = datos.anterior.creado_en
    ? new Date(datos.anterior.creado_en).toLocaleString()
    : "";
  const grupos: [string, PrecierreCambios["movidas"], string | null][] = [
    ["cambios.movidas", datos.movidas, null],
    ["cambios.nuevas", datos.nuevas, null],
    ["cambios.ausentes", datos.ausentes, "cambios.ausentesOjo"],
  ];
  const nada = !datos.movidas.length && !datos.nuevas.length && !datos.ausentes.length;

  return (
    <div style={caja}>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 4 }}>
        {t("cambios.contra", { archivo: datos.anterior.archivo, cuando })}
      </p>
      {datos.tc_cambio && (
        <p style={{ fontSize: 12, color: COLOR.aviso, marginBottom: 8 }}>
          {t("cambios.tcCambio")}
        </p>
      )}
      {/* ⚠️ NO es un total contable. Es la suma cruda de los renglones
          —ingresos y gastos juntos— y sirve para detectar que algo se movió,
          nada más. El rótulo lo dice y la nota de abajo lo repite: un número
          con pinta de resultado del mes, en una pantalla de cierre, se lee
          como resultado del mes. */}
      <p style={{ fontSize: 13, marginBottom: 2 }}>
        <strong>{t("cambios.totalMes")}:</strong>{" "}
        {datos.total_antes == null ? "" : usd(datos.total_antes)} →{" "}
        {datos.total_ahora == null ? "" : usd(datos.total_ahora)}
        {datos.delta_total != null && Math.abs(datos.delta_total) >= 0.01 && (
          <span style={{ color: datos.delta_total > 0 ? COLOR.info : COLOR.critico }}>
            {"  ("}{datos.delta_total > 0 ? "+" : ""}{usd(datos.delta_total)}{")"}
          </span>
        )}
      </p>
      <p style={{ fontSize: 11.5, color: "var(--text-secondary)", marginBottom: 14 }}>
        {t("cambios.totalMesOjo")}
      </p>

      {nada && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {t("cambios.sinCambios")}
        </p>
      )}

      {grupos.map(([clave, filas, ojo]) => filas.length > 0 && (
        <section key={clave} style={{ marginBottom: 18 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>
            {t(clave)} · {filas.length}
          </h3>
          {ojo && (
            <p style={{ fontSize: 11.5, color: COLOR.aviso, marginBottom: 6 }}>
              {t(ojo)}
            </p>
          )}
          <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12.5 }}>
              <thead>
                <tr style={{ textAlign: "left", color: "var(--text-secondary)" }}>
                  <th style={th}>#</th>
                  <th style={th}>Cuenta</th>
                  <th style={th}>Descripción</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("cambios.antes")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("cambios.ahora")}</th>
                  <th style={{ ...th, textAlign: "right" }}>{t("cambios.delta")}</th>
                </tr>
              </thead>
              <tbody>
                {filas.map(f => {
                  const delta = f.delta ?? (f.mes_usd - (f.mes_usd_antes ?? 0));
                  return (
                    <tr key={`${clave}-${f.cuenta}`}
                        style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={td}>{f.fila}</td>
                      <td style={{ ...td, whiteSpace: "nowrap" }}>{f.cuenta}</td>
                      <td style={td}>{f.descripcion}</td>
                      <td style={tdNum}>
                        {f.mes_usd_antes == null ? "—" : usd(f.mes_usd_antes)}
                      </td>
                      <td style={tdNum}>{usd(f.mes_usd)}</td>
                      <td style={{ ...tdNum,
                                   color: delta < 0 ? COLOR.critico : COLOR.info }}>
                        {delta > 0 ? "+" : ""}{usd(delta)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

const th: React.CSSProperties = { padding: "4px 8px", fontWeight: 600 };
const td: React.CSSProperties = { padding: "4px 8px" };
const tdNum: React.CSSProperties = {
  padding: "4px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums",
};

/* ── Descargas ─────────────────────────────────────────────────────────────── */

function Descargas({ dl, t }: {
  dl: ReturnType<typeof precierreExcelUrl>;
  t: ReturnType<typeof useTranslations>;
}) {
  const items: [keyof typeof dl, string][] = [
    ["detalle", "dl.detalle"], ["hoja", "dl.hoja"],
    ["filas", "dl.filas"], ["listado", "dl.listado"],
  ];
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {items.map(([k, clave]) => (
        <a key={k} href={dl[k]} style={{ ...caja, textDecoration: "none",
                                         display: "block", color: "inherit" }}>
          <div style={{ fontWeight: 600 }}>{t(`${clave}.titulo`)}</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {t(`${clave}.que`)}
          </div>
        </a>
      ))}
    </div>
  );
}

/* ── Piezas chicas ─────────────────────────────────────────────────────────── */

function Campo({ etiqueta, ayuda, children }: {
  etiqueta: string; ayuda?: string; children: React.ReactNode;
}) {
  return (
    <label style={{ display: "grid", gap: 3 }}>
      <span style={{ fontSize: 12, fontWeight: 600 }}>{etiqueta}</span>
      {children}
      {ayuda && <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{ayuda}</span>}
    </label>
  );
}

function Nota({ tono, children }: { tono: "ok" | "mal" | "ojo"; children: React.ReactNode }) {
  const c = { ok: ["#067647", "#ECFDF3"], mal: ["#B42318", "#FEF3F2"],
              ojo: ["#B54708", "#FFFAEB"] }[tono];
  return (
    <div style={{ margin: "12px 0", padding: "10px 14px", borderRadius: 8,
                  background: c[1], color: c[0], fontSize: 13,
                  border: `1px solid ${c[0]}22` }}>
      {children}
    </div>
  );
}

const caja: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 10, padding: 16,
};
const input: React.CSSProperties = {
  padding: "6px 9px", border: "1px solid var(--border)", borderRadius: 6,
  fontSize: 14, background: "var(--surface)", color: "var(--text-primary)",
};
const boton: React.CSSProperties = {
  padding: "8px 16px", borderRadius: 7, border: "none", cursor: "pointer",
  background: "var(--brand)", color: "#fff", fontWeight: 600, fontSize: 14,
};
const botonSecundario: React.CSSProperties = {
  ...boton, background: "transparent", color: "var(--brand)",
  border: "1px solid var(--brand)",
};
const botonSuave: React.CSSProperties = {
  ...botonSecundario, color: "var(--text-secondary)", border: "1px solid var(--border)",
};
const tab: React.CSSProperties = {
  padding: "7px 14px", border: "none", background: "transparent", cursor: "pointer",
  fontSize: 14, borderBottom: "2px solid transparent", color: "var(--text-secondary)",
};
const tabActivo: React.CSSProperties = {
  color: "var(--brand)", borderBottom: "2px solid var(--brand)", fontWeight: 600,
};
const chip: React.CSSProperties = {
  padding: "3px 10px", borderRadius: 20, border: "1px solid var(--border)",
  fontSize: 12, background: "var(--surface)", cursor: "pointer",
  color: "var(--text-secondary)",
};
const chipActivo: React.CSSProperties = {
  borderColor: "var(--brand)", color: "var(--brand)", fontWeight: 600,
};
const pill: React.CSSProperties = {
  marginLeft: 6, background: "#B42318", color: "#fff", borderRadius: 20,
  padding: "0 7px", fontSize: 11, fontWeight: 700,
};
const etiquetaChica: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 5, fontSize: 13,
};
const pre: React.CSSProperties = {
  fontSize: 11, background: "var(--surface-2, #0000000a)", padding: 10,
  borderRadius: 6, overflowX: "auto", maxHeight: 260,
};
