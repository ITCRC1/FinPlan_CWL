"use client";
//
// Guillermo — estado, cola, historial y configuración (`docs/GUILLERMO.md`).
//
// ⚠️ **Sin esta pantalla el sistema es una caja negra.** El spec lo dice del
// motor de reglas (§7.4) y vale para todo: un proceso que decide y no muestra
// qué decidió no se puede auditar, y por lo tanto no se puede confiar.
//
import { useCallback, useEffect, useState } from "react";
import IrA from "@/components/IrA";
import Guillermo, { type GuillermoState } from "@/components/Guillermo";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getEstadoGuillermo, getConfigGuillermo, saveConfigGuillermo,
  getImportacionesGuillermo, getExcepcionesGuillermo, getFaltantesGuillermo, getCuadreGuillermo,
  getNivelesGuillermo, getRecalculosGuillermo, correrRecalculoGuillermo,
  getIAGuillermo, correrRondaGuillermo, type ConexionIA,
  getManifiestoGuillermo, crearEsperadoGuillermo, editarEsperadoGuillermo,
  borrarEsperadoGuillermo, type ReporteEsperado,
  getCorreoGuillermo, type EstadoCorreo,
  resolverExcepcionGuillermo,
  type EstadoGuillermo, type LoteImport, type ExcepcionGuillermo,
  type ReporteFaltante, type CuadreEscenario,
  type NivelGuillermo, type RecalculoEscenario,
} from "@/lib/api";

const COLOR: Record<string, string> = {
  // ⚠️ Gris = «todavía no lo encendieron». No está bien, no está roto.
  gris: "var(--text-disabled)",
  verde: "var(--positive)",
  ambar: "var(--warning, #B8860B)",
  rojo: "var(--negative)",
};

// Una fila en blanco para declarar un reporte nuevo. `cobertura` de default
// porque es la verificación que funciona hacia atrás y no depende de que el
// registro de subidas tenga historial.
const ESPERADO_VACIO: ReporteEsperado = {
  report_id: "", notas: "", frecuencia: "monthly", verifica: "cobertura",
  objetivo: "", gracia_dias: 0, obligatorio: true, activo: true,
  patron: "", formato: "", tamano_min: 0,
};

function fecha(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("es-CR", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function GuillermoPage() {
  const [e, setE] = useState<EstadoGuillermo | null>(null);
  const [cfg, setCfg] = useState<{ clave: string; valor: string; descripcion: string }[]>([]);
  const [lotes, setLotes] = useState<LoteImport[]>([]);
  const [cola, setCola] = useState<ExcepcionGuillermo[]>([]);
  const [faltan, setFaltan] = useState<ReporteFaltante[]>([]);
  const [cuadre, setCuadre] = useState<CuadreEscenario[]>([]);
  const [cuadreResumen, setCuadreResumen] = useState<Record<string, number | boolean> | null>(null);
  const [niveles, setNiveles] = useState<NivelGuillermo[]>([]);
  const [nivelActual, setNivelActual] = useState("bajo");
  const [recalcs, setRecalcs] = useState<RecalculoEscenario[]>([]);
  const [corriendo, setCorriendo] = useState(false);
  const [ia, setIa] = useState<ConexionIA | null>(null);
  // El manifiesto de ESTA propiedad (D-1). Vacío es una respuesta válida.
  const [manifiesto, setManifiesto] = useState<ReporteEsperado[]>([]);
  const [listas, setListas] = useState<{ verificaciones: string[]; frecuencias: string[] }>(
    { verificaciones: [], frecuencias: [] });
  const [nuevo, setNuevo] = useState<ReporteEsperado>({ ...ESPERADO_VACIO });
  const [correo, setCorreo] = useState<EstadoCorreo | null>(null);
  const [recorriendo, setRecorriendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  // Qué estado del gato se está mirando en la caja de muestra.
  const [vista, setVista] = useState<GuillermoState>("pending");

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [a, b, c, d, f, q, nv, rc, ai, mf, co] = await Promise.all([
        getEstadoGuillermo(),
        getConfigGuillermo(),
        getImportacionesGuillermo(),
        getExcepcionesGuillermo("pending"),
        // ⚠️ Puede fallar solo si el backend todavía no tiene el manifiesto;
        // eso NO puede dejar la pantalla entera sin cargar.
        getFaltantesGuillermo().catch(() => ({ reportes: [] })),
        getCuadreGuillermo().catch(() => ({ resumen: null, escenarios: [] })),
        getNivelesGuillermo().catch(() => ({ actual: "bajo", niveles: [] })),
        getRecalculosGuillermo().catch(() => ({ escenarios: [] })),
        getIAGuillermo().catch(() => null),
        getManifiestoGuillermo().catch(() => ({
          hotel_id: "", reportes: [], verificaciones: [], frecuencias: [] })),
        getCorreoGuillermo().catch(() => null),
      ]);
      setE(a); setCfg(b.parametros); setLotes(c.lotes); setCola(d.excepciones);
      setFaltan(f.reportes);
      setManifiesto(mf.reportes);
      setListas({ verificaciones: mf.verificaciones, frecuencias: mf.frecuencias });
      setCorreo(co);
      setCuadre(q.escenarios);
      setCuadreResumen(q.resumen as Record<string, number | boolean> | null);
      setNiveles(nv.niveles); setNivelActual(nv.actual);
      setRecalcs(rc.escenarios);
      setIa(ai);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  async function guardar(clave: string, valor: string) {
    setError(null); setAviso(null);
    try {
      await saveConfigGuillermo(clave, valor);
      setAviso(`${clave} = ${valor}`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo guardar");
    }
  }

  // ── El manifiesto ────────────────────────────────────────────────────────
  //
  // ⚠️ Agregar un reporte hace que su ausencia se convierta en una excepción;
  // sacarlo lo vuelve invisible. Por eso cada acción recarga y avisa qué pasó:
  // un manifiesto que cambia en silencio es un Guillermo que reclama o calla
  // sin que nadie sepa por qué.
  async function agregarEsperado() {
    setError(null); setAviso(null);
    try {
      await crearEsperadoGuillermo(nuevo);
      setAviso(`«${nuevo.report_id}» entró al manifiesto`);
      setNuevo({ ...ESPERADO_VACIO });
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo agregar");
    }
  }

  async function guardarEsperado(r: ReporteEsperado) {
    setError(null); setAviso(null);
    try {
      await editarEsperadoGuillermo(r.id as string, r);
      setAviso(`«${r.report_id}» actualizado`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo guardar");
    }
  }

  async function quitarEsperado(r: ReporteEsperado) {
    setError(null); setAviso(null);
    try {
      await borrarEsperadoGuillermo(r.id as string);
      setAviso(`«${r.report_id}» salió del manifiesto: deja de reclamarse`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo quitar");
    }
  }

  // El historial es una traza de auditoría: tiene que poder salir de la app
  // para adjuntarse a una conversación con Finanzas.
  async function bajarExcel() {
    setError(null);
    try {
      await bajarCuadros("Guillermo", [
        {
          titulo: "Qué archivos entraron",
          subtitulo: "El checksum es del CONTENIDO: renombrar no hace otro archivo",
          hoja: "Historial",
          // ⚠️ El exportador arma «etiqueta + números», sin columnas de texto.
          // La traza se arma en la etiqueta en vez de perder datos: quién y
          // desde qué puerta importan tanto como el tamaño.
          columnas: [
            { label: "Cuándo · archivo · checksum · quién · puerta", ancho: 110,
              formato: "texto" },
            { label: "Tamaño (bytes)", ancho: 16, formato: "num" },
          ],
          filas: lotes.flatMap(b =>
            (b.archivos.length ? b.archivos : [null]).map((f): FilaCuadro => ({
              label: [fecha(b.iniciado_en), f?.nombre || "—", f?.checksum || "—",
                      f?.subido_por || b.disparado_por || "—", b.endpoint]
                .join("  ·  "),
              nivel: 1,
              valores: [f ? f.tamano : 0],
            }))),
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo bajar el Excel");
    }
  }

  // ⚠️ Corre sólo cuando el owner lo aprieta. Decisión suya (2026-08-20):
  // «yo podría hacer unas 30 actualizaciones y no quiero que me pegue a cada
  // rato — yo podría después de 10 horas de trabajo revisar eso».
  // La ronda: recorre los chequeos y deja cada hallazgo en la cola.
  async function recorrer() {
    setRecorriendo(true); setError(null); setAviso(null);
    try {
      const r = await correrRondaGuillermo();
      setAviso(`${r.abiertas} abiertos · ${r.nuevas} nuevos · `
        + `${r.cerradas} se resolvieron`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo recorrer");
    } finally { setRecorriendo(false); }
  }

  async function correrRecalculo(ids: string[]) {
    setCorriendo(true); setError(null); setAviso(null);
    try {
      const r = await correrRecalculoGuillermo(ids);
      setAviso(`recalculados ${r.corridos} · saltados ${r.saltados} · `
        + `fallaron ${r.fallaron}`);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo recalcular");
    } finally { setCorriendo(false); }
  }

  async function resolver(id: string, decision: "approved" | "rejected") {
    setError(null);
    try {
      await resolverExcepcionGuillermo(id, decision);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo resolver");
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          Guillermo
        </h1>
        <div style={{ flex: 1 }} />
        {/* Recorrer: revisa todo y deja cada hallazgo en la cola. No escribe
            en el modelo financiero — sólo anota. */}
        <button onClick={recorrer} disabled={recorriendo}
          style={{ padding: "6px 14px", borderRadius: 6, fontSize: 13,
                   fontWeight: 600, cursor: recorriendo ? "default" : "pointer",
                   border: "1px solid var(--brand)",
                   background: recorriendo ? "transparent" : "var(--brand)",
                   color: recorriendo ? "var(--text-disabled)" : "#fff" }}>
          {recorriendo ? "Recorriendo…" : "Recorrer ahora"}
        </button>
        <button onClick={bajarExcel} disabled={lotes.length === 0}
          style={{ padding: "6px 14px", borderRadius: 6, fontSize: 13,
                   fontWeight: 600, cursor: "pointer", background: "transparent",
                   color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      {error && <div style={{ color: "var(--negative)", fontSize: 13, marginTop: 10 }}>{error}</div>}
      {aviso && <div style={{ color: "var(--positive)", fontSize: 13, marginTop: 10 }}>{aviso}</div>}
      {cargando && <div style={{ color: "var(--text-secondary)", padding: 20 }}>Cargando…</div>}

      {e && (
        <>
          {/* ── Estado ────────────────────────────────────────────────────── */}
          <div style={{
            marginTop: 16, padding: "14px 18px", borderRadius: 10,
            border: "1px solid var(--border)",
            borderLeft: `4px solid ${COLOR[e.color] ?? "var(--border)"}`,
            display: "flex", gap: 32, flexWrap: "wrap", alignItems: "center",
          }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Estado</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: COLOR[e.color] }}>
                {e.mensaje || e.state}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Autonomía</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>
                {e.autonomia === "shadow" ? "Sombra — no escribe nada" : "Asistido"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Última ronda</div>
              <div style={{ fontSize: 15 }}>{fecha(e.ultima_ronda)}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>Pendientes</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{e.pendientes}</div>
            </div>
          </div>

          {/* ── Acá SÍ se lo ve, siempre ──────────────────────────────────
              En el resto de la app Guillermo aparece sólo cuando tiene algo
              que decir —su permanencia ES la alerta—, así que hoy, en `off`,
              no sale por ningún lado. Pero ésta es su pantalla: no verlo acá
              nunca sería raro, y además deja probar cómo se ve en cada estado
              sin tener que provocar el estado de verdad. */}
          <div style={{ marginTop: 20, padding: "10px 16px 4px", borderRadius: 10,
                        border: "1px solid var(--border)", maxWidth: 940 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center",
                          flexWrap: "wrap", marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Así se ve:
              </span>
              {(["off", "idle", "running", "pending", "stuck"] as GuillermoState[]).map(v => (
                <button key={v} onClick={() => setVista(v)}
                  style={{ padding: "3px 10px", fontSize: 12, borderRadius: 5,
                           cursor: "pointer", border: "1px solid var(--border)",
                           background: vista === v ? "var(--brand)" : "transparent",
                           color: vista === v ? "#fff" : "var(--text-secondary)" }}>
                  {v === "off" ? "apagado" : v === "idle" ? "al día"
                    : v === "running" ? "corriendo" : v === "pending"
                      ? "con pendientes" : "trabado"}
                </button>
              ))}
              <span style={{ fontSize: 11.5, color: "var(--text-disabled)" }}>
                {vista === "off" && "no aparece: todavía no arrancó — es el estado de hoy"}
                {vista === "idle" && "no aparece: nada que reportar, duerme"}
                {vista === "running" && "cruza la pantalla y se va"}
                {vista === "pending" && "se sienta y se queda hasta que resuelvas"}
                {vista === "stuck" && "cola rápida y orejas atrás — no se va solo"}
              </span>
            </div>
            {/* El componente es `position: fixed`, así que acá se lo encierra
                en una caja con altura propia para verlo en su lugar. */}
            <div style={{ position: "relative", height: 130, overflow: "hidden" }}>
              <div style={{ position: "absolute", inset: 0,
                            transform: "translateX(-24px)" }}>
                <Guillermo state={vista} pendingCount={e.pendientes || 4}
                          arrastrable={false} />
              </div>
              {(vista === "off" || vista === "idle") && (
                <div style={{ position: "absolute", inset: 0, display: "flex",
                              alignItems: "center", color: "var(--text-disabled)",
                              fontSize: 13, fontStyle: "italic" }}>
                  (no aparece)
                </div>
              )}
            </div>
          </div>

          {/* ⚠️ El manifiesto vacío se DICE. Un Guillermo que nunca reclama
              nada se ve igual que uno que no tiene nada que reclamar. */}
          {e.sin_manifiesto && (
            <div style={{
              marginTop: 12, padding: "12px 16px", borderRadius: 8,
              border: "1px solid var(--negative)", fontSize: 12.5,
              color: "var(--text-secondary)", lineHeight: 1.6, maxWidth: 940,
            }}>
              <b style={{ color: "var(--negative)" }}>No hay reportes esperados configurados.</b>{" "}
              Sin manifiesto, Guillermo <b>no puede verificar si llegó todo</b> — no es que
              esté todo bien, es que no tiene contra qué comparar. Definirlo es la
              decisión <b>D-1</b>: qué reportes, en qué formato, con qué frecuencia y
              cuáles obligatorios.
            </div>
          )}

          {/* ── Capacidades ───────────────────────────────────────────────
              ⚠️ Lo que crece entre niveles es CUÁNDO actúa, no QUÉ decide
              solo. En los tres, una propuesta del modelo va a la cola y ahí
              se detiene. */}
          {niveles.length > 0 && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28,
                           marginBottom: 8 }}>
                Qué tanto lo dejás hacer
              </h2>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {niveles.map(n => {
                  const activo = n.clave === nivelActual;
                  return (
                    <button key={n.clave}
                      onClick={() => guardar("autonomy_level", n.clave)}
                      style={{ flex: "1 1 260px", textAlign: "left",
                               padding: "12px 14px", borderRadius: 8,
                               cursor: "pointer",
                               border: `2px solid ${activo ? "var(--brand)"
                                 : "var(--border)"}`,
                               background: "transparent" }}>
                      <div style={{ fontWeight: 700, fontSize: 14,
                                    color: activo ? "var(--brand)"
                                      : "var(--text-primary)" }}>
                        {n.nombre}{activo ? "  ·  actual" : ""}
                      </div>
                      <div style={{ fontSize: 12, marginTop: 5, lineHeight: 1.5,
                                    color: "var(--text-secondary)" }}>
                        {n.resumen}
                      </div>
                    </button>
                  );
                })}
              </div>
              <p style={{ fontSize: 12, color: "var(--text-disabled)",
                          marginTop: 8, maxWidth: 940 }}>
                En los tres niveles, una propuesta del modelo <b>va a la cola y
                ahí se detiene</b>. Lo único que se auto-aplica son reglas que un
                humano aprobó antes — eso no cambia ni en el nivel más alto.
              </p>
            </>
          )}

          {/* ── El botón del recálculo ──────────────────────────────────── */}
          {recalcs.length > 0 && (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 14,
                            marginTop: 28, marginBottom: 6, flexWrap: "wrap" }}>
                <h2 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>
                  Recalcular
                </h2>
                <button onClick={() => correrRecalculo([])} disabled={corriendo}
                  style={{ padding: "5px 14px", borderRadius: 6, fontSize: 13,
                           fontWeight: 600,
                           cursor: corriendo ? "default" : "pointer",
                           border: "1px solid var(--brand)",
                           background: corriendo ? "transparent" : "var(--brand)",
                           color: corriendo ? "var(--text-disabled)" : "#fff" }}>
                  {corriendo ? "Corriendo…" : "Correr todos ahora"}
                </button>
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  No corre solo: hacé todos los cambios que quieras y apretá
                  cuando termines.
                </span>
              </div>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 700 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", minWidth: 220 }}>Escenario</th>
                      <th style={{ textAlign: "left" }}>Último recálculo</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {recalcs.map(r => (
                      <tr key={r.id}>
                        <td style={{ textAlign: "left" }}>
                          {r.nombre}{r.enllavado ? " 🔒" : ""}</td>
                        <td style={{ textAlign: "left",
                                     color: r.ultimo ? "var(--text-primary)"
                                       : "var(--text-disabled)" }}>
                          {r.ultimo ? fecha(r.ultimo) : "nunca"}</td>
                        <td style={{ textAlign: "right" }}>
                          <button onClick={() => correrRecalculo([r.id])}
                            disabled={corriendo || r.enllavado}
                            title={r.enllavado ? "enllavado" : ""}
                            style={{ padding: "2px 10px", fontSize: 12,
                                     borderRadius: 5,
                                     cursor: r.enllavado ? "default" : "pointer",
                                     border: "1px solid var(--border)",
                                     background: "transparent",
                                     color: r.enllavado ? "var(--text-disabled)"
                                       : "var(--text-primary)" }}>
                            Recalcular
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* ── Todo auxiliar contra el GL ─────────────────────────────── */}
          {cuadreResumen && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28,
                           marginBottom: 4 }}>
                Los auxiliares contra el GL
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5,
                          marginBottom: 10, maxWidth: 940 }}>
                {/* ⚠️ Tres estados, no dos. «No se puede verificar» NO es
                    «cuadra»: pintarlo verde haría que catorce presupuestos
                    salgan al día sin que nadie haya comparado nada. */}
                <b>{String(cuadreResumen.cuadran)}</b> cuadran ·{" "}
                <b style={{ color: "var(--negative)" }}>
                  {String(cuadreResumen.descuadres_nuevos)}
                </b>{" "}descuadran sin explicación ·{" "}
                {String(cuadreResumen.descuadres_conocidos)} descuadran por un
                motivo ya documentado ·{" "}
                <b style={{ color: "var(--warning, #B8860B)" }}>
                  {String(cuadreResumen.sin_verificar)}
                </b>{" "}<b>no se pueden verificar</b> — no tienen detalle del
                mayor contra el cual comparar, que no es lo mismo que estar bien.
              </p>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 940 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", minWidth: 210 }}>Escenario</th>
                      <th style={{ textAlign: "left" }}>Estado</th>
                      <th style={{ textAlign: "right" }}>Peor diferencia</th>
                      <th style={{ textAlign: "left" }}>Qué pasa</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cuadre.filter(c => c.estado !== "cuadra").map(c => {
                      const nuevo = c.estado === "no_cuadra" && !c.conocida;
                      const color = nuevo ? "var(--negative)"
                        : c.estado === "sin_verificar" ? "var(--warning, #B8860B)"
                          : "var(--text-secondary)";
                      return (
                        <tr key={c.escenario}>
                          <td style={{ textAlign: "left", fontWeight: 500 }}>
                            {c.escenario}</td>
                          <td style={{ textAlign: "left", color,
                                       fontWeight: nuevo ? 700 : 400 }}>
                            {nuevo ? "descuadra" : c.estado === "sin_verificar"
                              ? "no se puede verificar" : "descuadre conocido"}
                          </td>
                          <td className="mono" style={{ textAlign: "right", color }}>
                            {c.peor_diferencia
                              ? `$${c.peor_diferencia.toLocaleString("en-US",
                                  { minimumFractionDigits: 2,
                                    maximumFractionDigits: 2 })}`
                              : "—"}</td>
                          {/* ⚠️ La acción primero. Un número sin el mes manda
                              a abrir una investigación; con el mes, manda a
                              subir un archivo. */}
                          <td style={{ textAlign: "left", fontSize: 12,
                                       color: "var(--text-secondary)" }}>
                            {c.que_hacer && (
                              <div style={{ color: "var(--text-primary)",
                                            fontWeight: 600, marginBottom: 2 }}>
                                {c.que_hacer}
                              </div>
                            )}
                            {c.conocida || c.motivo}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* ── Qué falta subir ───────────────────────────────────────────
              La primera pregunta que Guillermo contesta de verdad. */}
          {faltan.length > 0 && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28,
                           marginBottom: 4 }}>
                Qué falta subir
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: 12.5,
                          marginBottom: 10, maxWidth: 940 }}>
                {/* ⚠️ Cada fila dice CÓMO se la verificó. No es un detalle:
                    «no se subió» y «no puedo saberlo» son cosas distintas, y
                    mezclarlas convierte el aviso en ruido. */}
                Cada reporte dice cómo se lo midió. Lo que se mide por
                <b> cobertura</b> o por <b>fecha de actualización</b> vale hacia
                atrás; lo que se mide por <b>última subida</b> sólo puede hablar
                desde que arrancó el registro.
              </p>
              <div className="fin-sticky" style={{ overflowX: "auto" }}>
                <table className="fin-table" style={{ minWidth: 940 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", minWidth: 220 }}>Reporte</th>
                      <th style={{ textAlign: "left" }}>Cada</th>
                      <th style={{ textAlign: "left" }}>Cómo se mide</th>
                      <th style={{ textAlign: "left" }}>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {faltan.map(f => (
                      <tr key={f.report_id}>
                        <td style={{ textAlign: "left", fontWeight: 500 }}>
                          {f.etiqueta}</td>
                        <td style={{ textAlign: "left", fontSize: 12,
                                     color: "var(--text-secondary)" }}>
                          {f.frecuencia === "daily" ? "día" : "mes"}</td>
                        <td style={{ textAlign: "left", fontSize: 12,
                                     color: "var(--text-secondary)" }}>
                          {f.como_se_mide}</td>
                        <td style={{ textAlign: "left",
                                     color: f.al_dia ? "var(--positive)"
                                                     : "var(--negative)",
                                     fontWeight: f.al_dia ? 400 : 600 }}>
                          {f.mensaje}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* ── La cola ───────────────────────────────────────────────────── */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8 }}>
            Cola de excepciones
          </h2>
          {cola.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
              Nada pendiente.
            </p>
          ) : (
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table className="fin-table" style={{ minWidth: 940 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Tipo</th>
                    <th style={{ textAlign: "left" }}>Valor original</th>
                    <th style={{ textAlign: "left" }}>Normalizado</th>
                    <th style={{ textAlign: "left" }}>Propuesta</th>
                    <th style={{ textAlign: "right" }}>Confianza</th>
                    <th style={{ textAlign: "left" }}>Por qué</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {cola.map(x => (
                    <tr key={x.id}>
                      <td style={{ textAlign: "left" }}>{x.tipo}</td>
                      <td style={{ textAlign: "left" }}>{x.valor_crudo}</td>
                      <td style={{ textAlign: "left" }} className="mono">
                        {x.valor_normalizado}</td>
                      <td style={{ textAlign: "left" }}>{x.destino_sugerido || "—"}</td>
                      <td style={{ textAlign: "right" }} className="mono">
                        {(parseFloat(x.confianza) * 100).toFixed(0)}%</td>
                      {/* ⚠️ El «por qué» es obligatorio por el principio rector:
                          puede decidir, pero no puede esconder. */}
                      <td style={{ textAlign: "left", fontSize: 12,
                                   color: "var(--text-secondary)" }}>
                        {x.rationale || "—"}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button onClick={() => resolver(x.id, "approved")}
                          style={{ marginRight: 6, padding: "3px 10px", fontSize: 12,
                                   borderRadius: 5, cursor: "pointer",
                                   border: "1px solid var(--positive)",
                                   background: "transparent", color: "var(--positive)" }}>
                          Aprobar</button>
                        <button onClick={() => resolver(x.id, "rejected")}
                          style={{ padding: "3px 10px", fontSize: 12, borderRadius: 5,
                                   cursor: "pointer", border: "1px solid var(--negative)",
                                   background: "transparent", color: "var(--negative)" }}>
                          Rechazar</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Los avisos por correo ──────────────────────────────────────
              ⚠️ Sin esto el dead-man switch sólo grita adentro de esta
              pantalla: si nadie la abre, un Guillermo trabado se ve igual que
              uno al día. Y cuando NO puede mandar, dice por qué — «no llegó
              correo» tiene que poder contestarse sin adivinar. */}
          {correo && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28,
                           marginBottom: 8 }}>
                Avisos por correo
              </h2>
              <div style={{
                padding: "14px 18px", borderRadius: 10,
                border: "1px solid var(--border)",
                borderLeft: `4px solid ${correo.configurado ? "var(--positive)"
                  : "var(--warning, #B8860B)"}`, maxWidth: 940,
              }}>
                <div style={{ fontSize: 15, fontWeight: 700,
                              color: correo.configurado ? "var(--positive)"
                                : "var(--warning, #B8860B)" }}>
                  {correo.configurado
                    ? `Avisa a ${correo.destinatarios.length}`
                    : "No puede avisar"}
                </div>
                <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                            margin: "6px 0 0", lineHeight: 1.6 }}>
                  {correo.motivo}
                </p>
                {correo.destinatarios.length > 0 && (
                  <p style={{ fontSize: 12.5, margin: "6px 0 0" }}
                     className="mono">
                    {correo.destinatarios.join(" · ")}
                  </p>
                )}
                <p style={{ fontSize: 12, color: "var(--text-secondary)",
                            margin: "10px 0 0", lineHeight: 1.6 }}>
                  Se manda: el <b>rojo del dead-man switch</b> (una vez por día,
                  desde los tics en que la ronda no corre), el de{" "}
                  <b>hallazgos nuevos</b> (sólo si hay algo nuevo — uno diario
                  que casi siempre dice cero se aprende a saltear) y el{" "}
                  <b>resumen semanal</b>, que va aunque no haya nada: es el
                  único aviso cuya ausencia significa que el canal está roto.
                </p>
                <p style={{ fontSize: 12, color: "var(--text-secondary)",
                            margin: "8px 0 0", lineHeight: 1.6 }}>
                  Las credenciales del servidor van en el entorno del backend
                  (<span className="mono">
                    {correo.variables_de_entorno.join(", ")}</span>) —{" "}
                  <b>nunca en el repositorio ni acá</b>. A quién avisarle se
                  carga en{" "}
                  <span className="mono">{correo.clave_destinatarios}</span>,
                  abajo en Configuración.
                </p>
              </div>
            </>
          )}

          {/* ── El manifiesto: qué espera ESTA propiedad ───────────────────
              ⚠️ Es la decisión D-1 y es POR PROPIEDAD (owner, 2026-08-20:
              «cada propiedad decide cómo manejar a Guillermo»). Antes sólo se
              podía sembrar desde el código: al clonar, una propiedad nueva
              heredaba el manifiesto de Corcovado y arrancaba reclamando cinco
              reportes que nadie le prometió. */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 4 }}>
            Qué reportes espera esta propiedad
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10,
                      maxWidth: 940 }}>
            Esto es lo que Guillermo reclama cuando no llega. <b>Vacío es una respuesta
            válida</b>: quiere decir que todavía no se decidió qué se espera, y el
            semáforo lo dice en vez de dar por bueno lo que no puede ver.
            {" "}<b>Cobertura</b> mira hasta qué período hay dato y funciona hacia atrás;
            {" "}<b>última subida</b> mira el registro de archivos, que arrancó el
            20-ago-2026 y no puede hablar de antes.
          </p>
          {manifiesto.length === 0 && (
            <p style={{ color: "var(--warning, #B8860B)", fontSize: 13, marginBottom: 10 }}>
              Esta propiedad todavía no declaró ningún reporte. Guillermo no reclama nada.
            </p>
          )}
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 940 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Reporte</th>
                  <th style={{ textAlign: "left" }}>Nombre visible</th>
                  <th style={{ textAlign: "left" }}>Cada</th>
                  <th style={{ textAlign: "left" }}>Se verifica por</th>
                  <th style={{ textAlign: "left" }}>Contra</th>
                  <th style={{ textAlign: "right" }}>Gracia</th>
                  <th style={{ textAlign: "center" }}>Obligatorio</th>
                  <th style={{ textAlign: "center" }}>Activo</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {manifiesto.map(r => (
                  <tr key={r.id}>
                    <td style={{ textAlign: "left" }} className="mono">{r.report_id}</td>
                    <td style={{ textAlign: "left" }}>{r.notas}</td>
                    <td style={{ textAlign: "left" }}>{r.frecuencia}</td>
                    <td style={{ textAlign: "left" }}>{r.verifica}</td>
                    <td style={{ textAlign: "left", fontSize: 12 }} className="mono">
                      {r.objetivo}</td>
                    <td style={{ textAlign: "right" }} className="mono">{r.gracia_dias}</td>
                    <td style={{ textAlign: "center" }}>{r.obligatorio ? "sí" : "no"}</td>
                    <td style={{ textAlign: "center" }}>
                      <input type="checkbox" checked={r.activo}
                             onChange={ev => guardarEsperado({ ...r, activo: ev.target.checked })} />
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button className="fin-btn" onClick={() => quitarEsperado(r)}
                              title="Sale del manifiesto y deja de reclamarse">×</button>
                    </td>
                  </tr>
                ))}
                <tr>
                  <td style={{ textAlign: "left" }}>
                    <input className="fin-input" value={nuevo.report_id} placeholder="otb_xml"
                           onChange={ev => setNuevo({ ...nuevo, report_id: ev.target.value })} />
                  </td>
                  <td style={{ textAlign: "left" }}>
                    <input className="fin-input" value={nuevo.notas} placeholder="On the Books"
                           onChange={ev => setNuevo({ ...nuevo, notas: ev.target.value })} />
                  </td>
                  <td style={{ textAlign: "left" }}>
                    <select className="fin-input" value={nuevo.frecuencia}
                            onChange={ev => setNuevo({ ...nuevo, frecuencia: ev.target.value })}>
                      {listas.frecuencias.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </td>
                  <td style={{ textAlign: "left" }}>
                    <select className="fin-input" value={nuevo.verifica}
                            onChange={ev => setNuevo({ ...nuevo, verifica: ev.target.value })}>
                      {listas.verificaciones.map(v => <option key={v} value={v}>{v}</option>)}
                    </select>
                  </td>
                  <td style={{ textAlign: "left" }}>
                    <input className="fin-input" value={nuevo.objetivo} placeholder="actual_pl_lines"
                           onChange={ev => setNuevo({ ...nuevo, objetivo: ev.target.value })} />
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <input className="fin-input" type="number" value={nuevo.gracia_dias}
                           style={{ width: 60, textAlign: "right" }}
                           onChange={ev => setNuevo({ ...nuevo, gracia_dias: Number(ev.target.value) || 0 })} />
                  </td>
                  <td style={{ textAlign: "center" }}>
                    <input type="checkbox" checked={nuevo.obligatorio}
                           onChange={ev => setNuevo({ ...nuevo, obligatorio: ev.target.checked })} />
                  </td>
                  <td />
                  <td style={{ textAlign: "right" }}>
                    <button className="fin-btn" onClick={agregarEsperado}
                            disabled={!nuevo.report_id.trim() || !nuevo.objetivo.trim()}>
                      Agregar
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* ── Historial ─────────────────────────────────────────────────── */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 4 }}>
            Qué archivos entraron
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: 12.5, marginBottom: 10,
                      maxWidth: 940 }}>
            Antes esto <b>no existía</b>: la respuesta de cada subida era efímera y no
            quedaba traza. Si un total no cuadraba, no había forma de saber qué entró.
            El <span className="mono">checksum</span> es del contenido, así que renombrar
            un archivo no lo convierte en otro.
          </p>
          {lotes.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
              Todavía no se registró ninguna subida.
            </p>
          ) : (
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table className="fin-table" style={{ minWidth: 940 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Cuándo</th>
                    <th style={{ textAlign: "left" }}>Archivo</th>
                    <th style={{ textAlign: "left" }}>Checksum</th>
                    <th style={{ textAlign: "right" }}>Tamaño</th>
                    <th style={{ textAlign: "left" }}>Quién</th>
                    <th style={{ textAlign: "left" }}>Puerta</th>
                  </tr>
                </thead>
                <tbody>
                  {lotes.flatMap(b => (b.archivos.length ? b.archivos : [null]).map((f, i) => (
                    <tr key={`${b.id}-${i}`}>
                      <td style={{ textAlign: "left" }}>{fecha(b.iniciado_en)}</td>
                      <td style={{ textAlign: "left" }}>{f?.nombre || "—"}</td>
                      <td style={{ textAlign: "left" }} className="mono">
                        {f?.checksum || "—"}</td>
                      <td style={{ textAlign: "right" }} className="mono">
                        {f ? f.tamano.toLocaleString("en-US") : "—"}</td>
                      <td style={{ textAlign: "left" }}>{f?.subido_por || b.disparado_por || "—"}</td>
                      <td style={{ textAlign: "left", fontSize: 12,
                                   color: "var(--text-secondary)" }}>{b.endpoint}</td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          )}

          {/* ── La conexión con Claude ─────────────────────────────────────
              ⚠️ Se muestra el payload EXACTO antes de que salga nada. Poder
              ver lo que se enviaría es lo que hace revisable la minimización
              de datos: una lista de campos prohibidos que nadie mira no
              protege de nada. */}
          {ia && (
            <>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28,
                           marginBottom: 8 }}>
                Conexión con Claude
              </h2>
              <div style={{
                padding: "14px 18px", borderRadius: 10,
                border: "1px solid var(--border)",
                borderLeft: `4px solid ${ia.conectado ? "var(--positive)"
                  : "var(--warning, #B8860B)"}`, maxWidth: 940,
              }}>
                <div style={{ fontSize: 15, fontWeight: 700,
                              color: ia.conectado ? "var(--positive)"
                                : "var(--warning, #B8860B)" }}>
                  {ia.conectado ? "Conectado" : "Sin conectar"}
                </div>
                <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                            margin: "6px 0 0", lineHeight: 1.6 }}>
                  {ia.motivo}
                  {!ia.conectado && (
                    <>
                      {" "}La llave va en <span className="mono">
                      {ia.donde_va_la_llave}</span> — <b>nunca en el repositorio
                      ni en el frontend</b>. Esa parte la hacés vos.
                    </>
                  )}
                </p>

                <div style={{ display: "flex", gap: 28, flexWrap: "wrap",
                              marginTop: 14 }}>
                  <div style={{ flex: "1 1 320px" }}>
                    <div style={{ fontSize: 11, fontWeight: 700,
                                  color: "var(--positive)" }}>PARA QUÉ SE USA</div>
                    <ul style={{ margin: "4px 0 0", paddingLeft: 18,
                                 fontSize: 12.5, lineHeight: 1.7,
                                 color: "var(--text-secondary)" }}>
                      {ia.para_que_se_usa.map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  </div>
                  <div style={{ flex: "1 1 320px" }}>
                    <div style={{ fontSize: 11, fontWeight: 700,
                                  color: "var(--negative)" }}>PARA QUÉ NO</div>
                    <ul style={{ margin: "4px 0 0", paddingLeft: 18,
                                 fontSize: 12.5, lineHeight: 1.7,
                                 color: "var(--text-secondary)" }}>
                      {ia.para_que_NO_se_usa.map((x, i) => <li key={i}>{x}</li>)}
                    </ul>
                  </div>
                </div>

                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700,
                                color: "var(--text-primary)" }}>
                    LO ÚNICO QUE SALDRÍA DE LA APP{" "}
                    <span style={{ fontWeight: 400,
                                   color: ia.ejemplo_limpio ? "var(--positive)"
                                     : "var(--negative)" }}>
                      {ia.ejemplo_limpio ? "· verificado limpio"
                        : `· ${ia.ejemplo_motivos.join(" · ")}`}
                    </span>
                  </div>
                  <pre className="mono" style={{
                    marginTop: 6, padding: "10px 12px", borderRadius: 6,
                    background: "var(--bg-surface)", fontSize: 11.5,
                    overflowX: "auto", lineHeight: 1.5,
                    border: "1px solid var(--border)",
                  }}>{JSON.stringify(ia.ejemplo_de_payload, null, 2)}</pre>
                  <p style={{ fontSize: 12, color: "var(--text-secondary)",
                              marginTop: 6, lineHeight: 1.6 }}>
                    El ejemplo trae un correo y un teléfono a propósito, para que
                    se vea que <b>salen tapados</b>. Ni un monto viaja: el modelo
                    elige una cuenta, no calcula.
                  </p>
                </div>
              </div>
            </>
          )}

          {/* ── Configuración ─────────────────────────────────────────────── */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8 }}>
            Configuración
          </h2>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 940 }}>
              <tbody>
                {cfg.map(p => (
                  <tr key={p.clave}>
                    <td style={{ textAlign: "left", fontWeight: 500, width: 240 }}
                        className="mono">{p.clave}</td>
                    <td style={{ width: 200 }}>
                      <input className="fin-input mono" defaultValue={p.valor}
                        onBlur={ev => {
                          if (ev.target.value !== p.valor) guardar(p.clave, ev.target.value);
                        }}
                        style={{ width: "100%", padding: "3px 6px" }} />
                    </td>
                    <td style={{ textAlign: "left", fontSize: 12,
                                 color: "var(--text-secondary)" }}>{p.descripcion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-disabled)", marginTop: 10,
                      maxWidth: 940 }}>
            Cambiar la configuración exige el rol <span className="mono">guillermo_approver</span>{" "}
            (o admin). Acá vive <span className="mono">autonomy_level</span>, o sea el
            permiso de escribir en el modelo financiero.
          </p>
        </>
      )}
    </div>
  );
}
