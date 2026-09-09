"use client";
/**
 * De qué está hecha una celda del cuadro, sin salir de la pantalla.
 *
 * Owner, 2026-09-03: *«toco la línea de Rooms Revenue y me abre el detalle, sin
 * ir… si abro payroll de Rooms se me despliegan los GL que suman eso, como un
 * cuadro sin salir a la otra ventana… así voy presentando y puedo ver los
 * detalles de una vez»*.
 *
 * ## Es una ventana, no un modal
 *
 * Owner, enseguida: *«que la ventana que se abre se pueda mover para darle
 * visibilidad al número que se quiere presentar»*.
 *
 * ⚠️ **Por eso NO hay fondo oscuro.** La primera versión era un modal clásico
 * con el velo encima; con eso, poder arrastrarla no sirve de nada — el cuadro
 * de atrás queda igual de tapado, sólo que por el velo en vez de por el panel.
 * Sacar el velo es lo que hace que moverla signifique algo, y de paso deja
 * seguir tocando otras líneas con la ventana abierta.
 *
 * Se cierra con Escape o con la ×. **No** con un clic afuera: sin velo, un clic
 * afuera es alguien señalando un número en la pantalla de atrás, y cerrarla ahí
 * sería exactamente lo contrario de lo que se pidió.
 *
 * ## Mes y acumulado, siempre los dos
 *
 * Owner: *«sólo sale el mes, pero no el acumulado; debés ponerlo, hay
 * espacio»*. Cada versión trae sus dos columnas.
 *
 * ⚠️ Los dos cortes se calculan sobre la MISMA serie de doce meses que manda el
 * backend: el mes es una posición y el acumulado la suma hasta ahí. No son dos
 * consultas, así que no pueden diferir entre sí.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef,
         useState } from "react";
import { createPortal } from "react-dom";

import { getComentariosPL, getDetalleDeCelda, guardarComentarioPL,
         type DetalleCelda as Datos } from "@/lib/api";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

const TD: React.CSSProperties = {
  padding: "4px 9px", textAlign: "right", fontSize: 11.5, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = { padding: "4px 10px", fontSize: 11.5 };
const BL = "2px solid var(--border-medium)";

export interface Celda {
  clase: string;
  /** Departamento, cuenta o línea. Vacío = la clase entera. */
  clave: string;
  titulo: string;
  /** Dónde se tocó, en coordenadas de la ventana.
   *
   *  ⚠️ La ventana abre AHÍ y no arriba de todo. Owner, 2026-09-03: «se queda
   *  arriba… si estás muy abajo debés ir hasta arriba a buscarlo; debe salir
   *  muy cercano de donde está la fuente». Un cuadro de sesenta filas se
   *  recorre hasta el final, y una ventana que aparece fuera de la vista se
   *  lee como que no pasó nada. */
  origen?: { x: number; y: number };
}

/** La llave con la que se guarda la nota de una celda.
 *
 *  ⚠️ Lleva la clase Y la clave: `payroll` de Rooms y `opex` de Rooms son dos
 *  celdas distintas y merecen dos notas distintas. Con sólo el departamento,
 *  escribir una pisaría la otra.
 */
export const refDeCelda = (c: Celda) => `celda:${c.clase}:${c.clave || "*"}`;

export default function DetalleCelda({ celda, scenarioIds, mes, horizonte, onCerrar }: {
  celda: Celda;
  scenarioIds: string[];
  mes: number;
  horizonte: "month" | "ytd" | "full";
  onCerrar: () => void;
}) {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    setDatos(null); setError(null);
    getDetalleDeCelda(scenarioIds, celda.clase, celda.clave)
      .then(d => { if (vivo) setDatos(d); })
      .catch(e => { if (vivo) setError(e instanceof Error ? e.message : "No se pudo cargar"); });
    return () => { vivo = false; };
  }, [scenarioIds, celda.clase, celda.clave]);

  /* ── La nota del mes ──────────────────────────────────────────────────────
   *
   * Owner, 2026-09-03: *«una vez que abrimos el popup, abajo de los números
   * abrir un box para editar comentarios… que sea grande… y este se guarde con
   * la versión del mes, con el mes. Y si cambio de mes, que se me abra otra
   * opción para agregar notas»*.
   *
   * ⚠️ **Se guarda con el MES**, así que cambiar de mes trae otra nota — vacía
   * si no se escribió. Es lo que se pidió y además es lo correcto: la
   * explicación de julio no explica agosto, y una nota sin mes se arrastraría a
   * todos los cierres siguientes diciendo algo que ya no es cierto.
   *
   * Y con la VERSIÓN de la ranura 1, la que se está explicando: la ventana
   * compara tres, pero la nota responde «por qué MI actual dio esto».
   */
  const escNota = scenarioIds[0] || "";
  const ref = refDeCelda(celda);
  const [nota, setNota] = useState("");
  const [notaCargada, setNotaCargada] = useState(false);
  const [guardando, setGuardando] = useState(false);
  /** Lo que está guardado en la base. Comparar contra esto es lo que dice si
   *  hay algo pendiente — y evita guardar de nuevo lo mismo cuando el botón
   *  roba el foco del campo y dispara el `onBlur`. */
  const [guardado, setGuardado] = useState("");

  useEffect(() => {
    if (!escNota) return;
    let vivo = true;
    setNotaCargada(false);
    getComentariosPL(escNota, mes)
      .then(r => {
        if (!vivo) return;
        const t = r.comentarios?.[ref] ?? "";
        setNota(t); setGuardado(t); setNotaCargada(true);
      })
      .catch(() => { if (vivo) { setNota(""); setGuardado(""); setNotaCargada(true); } });
    return () => { vivo = false; };
  }, [escNota, mes, ref]);

  /** Guarda al salir del campo, no en cada tecla: por tecla serían treinta
   *  llamadas por nota, y una carrera entre ellas donde gana la que conteste
   *  última — que no es la última que se escribió. */
  const sucio = notaCargada && nota.trim() !== guardado.trim();

  const guardarNota = useCallback(async () => {
    if (!escNota || !notaCargada) return;
    const texto = nota.trim();
    if (texto === guardado.trim()) return;   // nada que guardar
    setGuardando(true);
    try {
      await guardarComentarioPL(escNota, ref, mes, texto);
      setGuardado(texto);
    } catch {
      // Lo escrito queda en el campo y el botón sigue en «Guardar»: perderlo
      // por un fallo de red sería lo peor que puede hacer una nota.
    } finally {
      setGuardando(false);
    }
  }, [escNota, notaCargada, ref, mes, nota, guardado]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onCerrar(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onCerrar]);

  /* ── Arrastrar ────────────────────────────────────────────────────────────
   *
   * `null` = todavía sin mover: la ventana se centra sola. En cuanto se
   * arrastra pasa a coordenadas fijas.
   *
   * ⚠️ Se usan eventos de PUNTERO y no de mouse: en una presentación esto se
   * maneja igual desde una pantalla táctil, y `pointer*` cubre los dos con el
   * mismo código. Y `setPointerCapture` es lo que evita que el arrastre se
   * corte si el cursor sale del encabezado — sin eso, mover rápido la suelta a
   * mitad de camino.
   */
  const [pos, setPos] = useState<{ x: number; y: number } | null>(
    celda.origen ? { x: celda.origen.x + 14, y: celda.origen.y + 16 } : null);
  const panel = useRef<HTMLDivElement | null>(null);
  const agarre = useRef<{ dx: number; dy: number } | null>(null);

  const alAgarrar = (e: React.PointerEvent) => {
    const caja = panel.current?.getBoundingClientRect();
    if (!caja) return;
    agarre.current = { dx: e.clientX - caja.left, dy: e.clientY - caja.top };
    setPos({ x: caja.left, y: caja.top });
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const alMover = (e: React.PointerEvent) => {
    const g = agarre.current;
    const caja = panel.current?.getBoundingClientRect();
    if (!g || !caja) return;
    // Se deja siempre un pedazo dentro de la pantalla: una ventana arrastrada
    // fuera del borde no se puede recuperar sin recargar.
    const x = Math.min(Math.max(e.clientX - g.dx, 8 - caja.width + 120),
                       window.innerWidth - 120);
    const y = Math.min(Math.max(e.clientY - g.dy, 0), window.innerHeight - 44);
    setPos({ x, y });
  };
  const alSoltar = () => { agarre.current = null; };

  /** Que entre en la pantalla, ya dibujada.
   *
   *  ⚠️ Abrir junto al clic no alcanza: si se tocó una línea del final, la
   *  ventana nace medio metro por debajo del borde y no se ve. El alto real no
   *  se sabe hasta que está dibujada, así que se mide y se sube — en un efecto
   *  DE DISEÑO (`useLayoutEffect`), que corre antes de pintar: con
   *  `useEffect` se vería el salto.
   *
   *  Corre una sola vez, al abrir. Después manda el usuario: reacomodarla
   *  cuando ya la movió a mano sería quitársela de donde la puso. */
  const acomodada = useRef(false);
  useLayoutEffect(() => {
    // ⚠️ Sólo cuando el cuadro ya está dibujado. Con «cargando…» el panel mide
    // sesenta píxeles: medirlo ahí y darlo por acomodado deja la ventana
    // colgando fuera de la pantalla en cuanto llegan las filas.
    if (acomodada.current || !celda.origen || !datos) return;
    const caja = panel.current?.getBoundingClientRect();
    if (!caja || !caja.height) return;
    acomodada.current = true;
    const margen = 12;
    let { x, y } = { x: celda.origen.x + 14, y: celda.origen.y + 16 };
    if (y + caja.height > window.innerHeight - margen) {
      // No entra abajo: se prueba ARRIBA del punto tocado, que deja el número
      // a la vista; y si tampoco entra, se pega al borde de arriba.
      y = Math.max(margen, celda.origen.y - caja.height - 10);
    }
    if (x + caja.width > window.innerWidth - margen) {
      x = Math.max(margen, window.innerWidth - caja.width - margen);
    }
    setPos({ x, y });
  }, [celda.origen, datos]);

  /** Los dos cortes, sobre la misma serie de doce meses.
   *
   *  ⚠️ El «mes» sigue al cuadro de atrás: si arriba dice julio, acá dice
   *  julio. El acumulado va de enero a ese mes. Con el horizonte en «año
   *  completo» los dos son el año, y entonces se muestra una sola columna —dos
   *  columnas iguales invitan a buscarles la diferencia. */
  const cortes = useMemo(() => {
    if (horizonte === "full") {
      return [{ rotulo: `${new Date().getFullYear()}`, meses: Array.from({ length: 12 }, (_, i) => i) }];
    }
    return [
      { rotulo: MESES[mes - 1], meses: [mes - 1] },
      { rotulo: `YTD ${MESES[mes - 1]}`, meses: Array.from({ length: mes }, (_, i) => i) },
    ];
  }, [horizonte, mes]);

  const suma = useCallback((serie: number[] | undefined, meses: number[]) =>
    meses.reduce((a, i) => a + ((serie ?? [])[i] ?? 0), 0), []);

  const versiones = datos?.versiones ?? [];
  const filas = useMemo(() => {
    const todos = cortes.flatMap(c => c.meses);
    const f = (datos?.filas ?? []).map(x => ({
      ...x,
      peso: versiones.reduce(
        (a, v) => a + Math.abs(suma(x.series[v.scenario_id], todos)), 0),
    }));
    // Lo más grande primero: en una presentación, lo que explica el número
    // tiene que estar arriba y no a diez filas de distancia.
    return f.filter(x => x.peso >= 0.005).sort((a, b) => b.peso - a.peso);
  }, [datos, versiones, suma, cortes]);

  const estilo: React.CSSProperties = pos
    ? { position: "fixed", left: pos.x, top: pos.y }
    : { position: "fixed", left: "50%", top: 90, transform: "translateX(-50%)" };

  /* ⚠️ **Un portal a `document.body`, y no es adorno.**
   *
   * `Transicion.tsx` envuelve CADA página en `.pag-entra`, que lleva una
   * animación sobre `transform` con `fill-mode: both`. Un ancestro con
   * transform se vuelve el bloque contenedor de sus descendientes
   * `position: fixed`, así que el `top` de esta ventana se medía desde el tope
   * del contenido de la página y no desde el de la pantalla: por eso salía
   * siempre arriba, por más que se le pasara la posición del clic
   * (owner, 2026-09-03: «está siempre arriba»).
   *
   * Sacarla del árbol la vuelve inmune a eso —y a cualquier transform que se
   * agregue mañana en cualquier ancestro—, que es lo que no se puede lograr
   * corrigiendo la hoja de estilos: bastaría un `transform` nuevo en cualquier
   * contenedor para que el defecto volviera sin que nada fallara.
   *
   * `montado` existe porque `document` no existe al dibujar en el servidor.
   */
  const [montado, setMontado] = useState(false);
  useEffect(() => { setMontado(true); }, []);
  if (!montado) return null;

  return createPortal((
    <div ref={panel} style={{
      ...estilo, zIndex: 1000,
      background: "var(--bg-surface)", borderRadius: 12,
      border: "1px solid var(--border-medium)",
      boxShadow: "0 18px 50px rgba(0,0,0,0.30)",
      maxWidth: "min(1120px, 96vw)", maxHeight: "80vh",
      display: "flex", flexDirection: "column",
    }}>
      {/* El encabezado es el asa. `touchAction: none` evita que el navegador
          se quede con el gesto y lo convierta en scroll de la página. */}
      <div
        onPointerDown={alAgarrar}
        onPointerMove={alMover}
        onPointerUp={alSoltar}
        onPointerCancel={alSoltar}
        style={{
          padding: "11px 16px", borderBottom: "1px solid var(--border)",
          display: "flex", alignItems: "baseline", gap: 11, flexWrap: "wrap",
          cursor: "move", touchAction: "none", userSelect: "none",
          borderRadius: "12px 12px 0 0",
        }}>
        <span style={{ color: "var(--text-disabled)", fontSize: 14 }}>⠿</span>
        <b style={{ fontSize: 14 }}>{celda.titulo}</b>
        <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
          {datos?.rotulo}
        </span>
        <button onClick={onCerrar} title="Cerrar (Esc)" style={{
          marginLeft: "auto", border: "none", background: "transparent",
          fontSize: 20, cursor: "pointer", color: "var(--text-secondary)",
          lineHeight: 1,
        }}>×</button>
      </div>

      <div style={{ padding: "10px 16px 16px", overflow: "auto" }}>
        {!datos && !error && (
          <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>cargando…</p>
        )}
        {error && <p style={{ fontSize: 12, color: "var(--negative)" }}>{error}</p>}

        {datos && (
          <>
            <div className="fin-scroll-x">
              <table style={{ borderCollapse: "collapse", minWidth: 520 }}>
                <thead>
                  <tr>
                    <th rowSpan={2} style={{
                      ...TDL, textAlign: "left", fontWeight: 800, minWidth: 210,
                      position: "static", verticalAlign: "bottom",
                      borderBottom: "2px solid var(--text-primary)",
                    }}>
                      Cuenta
                    </th>
                    {versiones.map(v => (
                      <th key={v.scenario_id} colSpan={cortes.length} style={{
                        ...TD, textAlign: "center", fontWeight: 800,
                        position: "static", borderLeft: BL,
                        borderBottom: "1px solid var(--border-medium)",
                      }}>
                        {v.escenario}
                        <div style={{ fontWeight: 400, fontSize: 10,
                                      color: "var(--text-secondary)" }}>
                          {v.fuente}
                        </div>
                      </th>
                    ))}
                  </tr>
                  <tr>
                    {versiones.map(v => cortes.map((c, j) => (
                      <th key={`${v.scenario_id}-${c.rotulo}`} style={{
                        ...TD, fontWeight: 700, fontSize: 10.5,
                        position: "static", minWidth: 96,
                        color: "var(--text-secondary)",
                        ...(j === 0 ? { borderLeft: BL } : {}),
                        borderBottom: "2px solid var(--text-primary)",
                      }}>
                        {c.rotulo}
                      </th>
                    )))}
                  </tr>
                </thead>
                <tbody>
                  {filas.map(f => (
                    <tr key={f.cuenta}>
                      <td style={TDL}>
                        <span className="mono" style={{ color: "var(--text-secondary)",
                                                        marginRight: 7 }}>
                          {f.cuenta}
                        </span>
                        {f.nombre}
                      </td>
                      {versiones.map(v => cortes.map((c, j) => {
                        const x = suma(f.series[v.scenario_id], c.meses);
                        return (
                          <td key={`${v.scenario_id}-${c.rotulo}`} className="mono"
                              style={{ ...TD,
                                ...(j === 0 ? { borderLeft: BL } : {}),
                                color: x < 0 ? "var(--negative)" : undefined }}>
                            {usd(x)}
                          </td>
                        );
                      }))}
                    </tr>
                  ))}
                  {/* El total tiene que dar EXACTAMENTE la celda que se tocó.
                      Si no da, el desplegable está explicando otra cosa. */}
                  <tr style={{ background: "var(--bg-elevated, #EDF1F5)" }}>
                    <td style={{ ...TDL, fontWeight: 800,
                                 borderTop: "2px solid var(--text-primary)" }}>
                      TOTAL
                    </td>
                    {versiones.map(v => cortes.map((c, j) => {
                      const x = filas.reduce(
                        (a, f) => a + suma(f.series[v.scenario_id], c.meses), 0);
                      return (
                        <td key={`${v.scenario_id}-${c.rotulo}`} className="mono"
                            style={{ ...TD, fontWeight: 800,
                              borderTop: "2px solid var(--text-primary)",
                              ...(j === 0 ? { borderLeft: BL } : {}),
                              color: x < 0 ? "var(--negative)" : undefined }}>
                          {usd(x)}
                        </td>
                      );
                    }))}
                  </tr>
                  {!filas.length && (
                    <tr><td colSpan={versiones.length * cortes.length + 1}
                            style={{ ...TDL, color: "var(--text-secondary)" }}>
                      No hay detalle por cuenta para este corte.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* ── La nota del mes ──────────────────────────────────────── */}
            <div style={{ marginTop: 14 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8,
                            marginBottom: 4 }}>
                <span style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: .6,
                               textTransform: "uppercase",
                               color: "var(--text-secondary)" }}>
                  Nota · {MESES[mes - 1]}
                </span>
                {/* ⚠️ El estado se DICE siempre, no sólo mientras guarda.
                    Owner, 2026-09-03: «y que guarda… no sé si se necesita un
                    botón de guardar ahí mismo». El problema no era que no
                    guardara —guarda al salir del campo— sino que no había
                    forma de saberlo, y en una reunión eso es escribir la
                    explicación y quedarse con la duda. */}
                <span style={{ fontSize: 11,
                               color: sucio ? "var(--negative)" : "var(--text-disabled)" }}>
                  {guardando ? "guardando…" : sucio ? "sin guardar" : "guardada"}
                </span>
              </div>
              <textarea
                value={nota}
                // `sucio` se deduce comparando con lo guardado, así que
                // escribir no necesita tocar ninguna otra bandera.
                onChange={e => setNota(e.target.value)}
                onBlur={guardarNota}
                placeholder={`Explicá acá qué pasó en ${MESES[mes - 1]}. Se guarda al salir del campo, y baja con el Word.`}
                onKeyDown={e => {
                  // Ctrl/Cmd + Enter guarda sin sacar la mano del teclado.
                  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                    e.preventDefault(); guardarNota();
                  }
                }}
                style={{
                  width: "100%", minHeight: 96, resize: "vertical",
                  padding: "9px 11px", fontSize: 12.5, lineHeight: 1.55,
                  borderRadius: 8,
                  border: `1px solid ${sucio ? "var(--negative)" : "var(--border-medium)"}`,
                  background: "var(--bg-surface)", color: "var(--text-primary)",
                  fontFamily: "inherit",
                }} />

              {/* El botón NO reemplaza al guardado automático: lo confirma.
                  Guardar sólo con el botón haría que salirse del campo sin
                  tocarlo pierda lo escrito, que es peor que la duda. */}
              <div style={{ display: "flex", alignItems: "center", gap: 10,
                            marginTop: 7 }}>
                <button
                  onClick={guardarNota}
                  disabled={!sucio || guardando}
                  style={{
                    padding: "6px 15px", fontSize: 12.5, fontWeight: 600,
                    borderRadius: 6, border: "none",
                    cursor: sucio && !guardando ? "pointer" : "default",
                    background: sucio ? "var(--brand)" : "var(--bg-elevated, #EDF1F5)",
                    color: sucio ? "#fff" : "var(--text-disabled)",
                  }}>
                  {guardando ? "Guardando…" : sucio ? "Guardar" : "Guardada"}
                </button>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  Se guarda sola al salir del campo. Ctrl+Enter también.
                </span>
              </div>
            </div>

            {versiones.some(v => v.agregado) && (
              <p style={{ fontSize: 11, color: "var(--text-secondary)",
                          marginTop: 9, lineHeight: 1.55, maxWidth: 720 }}>
                ⚠️ En las versiones marcadas <b>Auxiliar</b>, el ingreso se
                presupuesta por <b>línea</b> y algunas líneas agrupan varias
                cuentas del mayor —<code>ROOMS</code> son la 4000, la 4001 y la
                4002—. Esa fila sale con el nombre de la línea y no con una
                cuenta: elegir una de las que agrupa sería inventarla.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  ), document.body);
}
