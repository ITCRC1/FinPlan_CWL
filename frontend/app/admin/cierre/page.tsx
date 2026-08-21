"use client";
//
// Cierre de períodos — qué meses son ACTUAL y cuáles son FORECAST.
//
// Owner, 2026-08-20: «debería haber un tab en admin para cerrar períodos y dar a
// entender qué meses son actuales y qué meses son forecast» · «yo subo y cierro
// el mes para indicar que los actuales vienen del GL y el forecast viene de los
// checkbooks».
//
// ⚠️ El corte es UN número (`actuals_through`) y hasta hoy sólo se movía como
// efecto de un import: mirabas un forecast y no sabías qué mitad era realidad y
// qué mitad era plan.
//
// ⚠️ **Abrir un mes MUEVE NÚMEROS**, no es un cambio de vista: devuelve ese mes
// al checkbook (al plan) y con él cambian el P&L, el cash flow y todo lo que
// cuelga. Por eso la apertura pide confirmación con los meses nombrados.
//
import { useCallback, useEffect, useState } from "react";
import IrA from "@/components/IrA";
import { getScenarios, type Scenario } from "@/lib/api";
import { getCierre, moverCorte, type Cierre } from "@/lib/cierre";
import { bajarCuadros, type FormatoCol } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";

export default function CierrePeriodosPage() {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [sel, setSel] = useState("");
  const [c, setC] = useState<Cierre | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string[]>([]);

  useEffect(() => {
    getScenarios(HOTEL_ID).then(todos => {
      // Sólo los FORECAST tienen corte: el cierre es de ellos.
      const f = todos.filter(s => s.type === "FORECAST");
      setEscenarios(f);
      // Arranca en el Forecast «Current», que es el único que avanza solo.
      setSel((f.find(s => s.is_current_forecast) || f[0])?.id || "");
      if (!f.length) setCargando(false);
    }).catch(() => setCargando(false));
  }, []);

  const cargar = useCallback(async () => {
    if (!sel) return;
    setCargando(true); setError(null);
    try { setC(await getCierre(sel)); }
    catch (err) { setError(err instanceof Error ? err.message : "no se pudo cargar"); }
    finally { setCargando(false); }
  }, [sel]);

  useEffect(() => { cargar(); }, [cargar]);

  async function mover(corte: number) {
    if (!c) return;
    setError(null); setAviso([]);
    const abre = corte < c.corte;
    if (abre) {
      const meses = c.meses.filter(m => m.mes > corte && m.mes <= c.corte)
                           .map(m => m.nombre).join(", ");
      // ⚠️ El texto nombra los meses. «¿Confirmás?» a secas no dice qué se
      // pierde de vista, y lo que se pierde es la realidad.
      if (!window.confirm(
        `Abrir ${meses} devuelve esos meses al checkbook (al plan).\n\n` +
        "El P&L y el cash flow van a cambiar. ¿Seguir?")) return;
    }
    try {
      const r = await moverCorte(sel, corte, abre);
      setAviso(r.avisos || []);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo mover el corte");
    }
  }

  // El estado del cierre es una traza: qué mes ya venía del GL cuando se emitió
  // un reporte. Tiene que poder salir de la app.
  async function bajar() {
    if (!c) return;
    setError(null);
    try {
      await bajarCuadros("Cierre de periodos", [{
        titulo: "Cierre de períodos",
        subtitulo: `${c.escenario.etiqueta} · corte en ${c.corte} · ` +
          (c.actual_enlazado ? `actuales de ${c.actual_enlazado.etiqueta}`
                             : "SIN escenario ACTUAL enlazado"),
        hoja: "Cierre",
        columnas: [
          { label: "Mes", ancho: 16, formato: "texto" as FormatoCol },
          { label: "Estado", ancho: 20, formato: "texto" as FormatoCol },
          { label: "De dónde sale", ancho: 34, formato: "texto" as FormatoCol },
          { label: "Dato en el GL", ancho: 16, formato: "texto" as FormatoCol },
          { label: "Aviso", ancho: 46, formato: "texto" as FormatoCol },
        ],
        filas: c.meses.map(m => ({
          label: m.nombre,
          valores: [
            m.estado === "ACTUAL" ? "Actual (cerrado)" : "Forecast",
            m.fuente,
            m.tiene_dato ? "sí" : "—",
            m.aviso || "",
          ],
        })),
      }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo bajar");
    }
  }

  const celda: React.CSSProperties = {
    padding: "8px 10px", borderBottom: "1px solid var(--border)",
  };

  return (
    <div className="pag-media">
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
        Cierre de períodos
      </h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 13,
                  marginBottom: 14, maxWidth: 880, lineHeight: 1.65 }}>
        Cerrar un mes dice: <b>este mes ya viene del GL</b>. Los meses cerrados
        los reporta el escenario ACTUAL; los abiertos salen del{" "}
        <b>checkbook</b> de este forecast.
      </p>

      {escenarios.length > 0 && (
        <label style={{ fontSize: 12.5, display: "inline-block", marginBottom: 14 }}>
          <div style={{ color: "var(--text-secondary)", marginBottom: 3 }}>
            Forecast
          </div>
          <select className="fin-input" value={sel} onChange={e => setSel(e.target.value)}
                  style={{ minWidth: 280 }}>
            {escenarios.map(s => (
              <option key={s.id} value={s.id}>
                {s.type} {s.year} {s.version}{s.is_current_forecast ? " · Current" : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      {!cargando && escenarios.length === 0 && (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
          No hay escenarios FORECAST: el cierre de períodos es de ellos.
        </p>
      )}

      {error && <p style={{ color: "var(--negative)", fontSize: 13 }}>{error}</p>}
      {aviso.map((a, i) => (
        <p key={i} style={{ color: "var(--warning, #B8860B)", fontSize: 13,
                            fontWeight: 600 }}>{a}</p>
      ))}
      {cargando && (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Cargando…</p>
      )}

      {c && !cargando && (
        <>
          <div style={{ marginBottom: 10 }}>
            <button className="fin-btn" onClick={bajar}>⬇ Excel</button>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                      marginBottom: 12, maxWidth: 880, lineHeight: 1.6 }}>
            Corte actual: <b>{c.corte === 0 ? "ningún mes cerrado"
              : `hasta ${c.meses[c.corte - 1]?.nombre}`}</b>.{" "}
            {c.actual_enlazado
              ? <>Los cerrados los reporta <b>{c.actual_enlazado.etiqueta}</b>.</>
              : <b style={{ color: "var(--negative)" }}>
                  No hay escenario ACTUAL enlazado para este año.
                </b>}
            {c.avanza_solo && " Este forecast avanza el corte solo al subir actuales."}
          </p>

          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 820 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Mes</th>
                  <th style={{ textAlign: "left" }}>Estado</th>
                  <th style={{ textAlign: "left" }}>De dónde sale</th>
                  <th style={{ textAlign: "left" }}>Dato en el GL</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {c.meses.map(m => (
                  <tr key={m.mes}>
                    <td style={{ ...celda, fontWeight: 600 }}>{m.nombre}</td>
                    <td style={{ ...celda, color: m.estado === "ACTUAL"
                      ? "var(--positive)" : "var(--text-secondary)",
                      fontWeight: m.estado === "ACTUAL" ? 700 : 400 }}>
                      {m.estado === "ACTUAL" ? "Actual (cerrado)" : "Forecast"}
                    </td>
                    <td style={{ ...celda, fontSize: 12.5,
                                 color: "var(--text-secondary)" }}>{m.fuente}</td>
                    <td style={{ ...celda, fontSize: 12.5 }}>
                      {m.tiene_dato
                        ? <span style={{ color: "var(--positive)" }}>sí</span>
                        : <span style={{ color: "var(--text-disabled)" }}>—</span>}
                      {m.aviso && (
                        <div style={{ color: "var(--negative)", fontSize: 12,
                                      marginTop: 2 }}>⚠ {m.aviso}</div>
                      )}
                    </td>
                    <td style={{ ...celda, textAlign: "right" }}>
                      {m.mes === c.corte ? (
                        <button className="fin-btn" onClick={() => mover(m.mes - 1)}>
                          Abrir {m.nombre}
                        </button>
                      ) : m.mes === c.corte + 1 ? (
                        <button className="fin-btn" onClick={() => mover(m.mes)}>
                          Cerrar {m.nombre}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ⚠️ La consecuencia que nadie ve, dicha acá: el checkbook de un mes
              cerrado sigue editable y editarlo no mueve nada. */}
          <div style={{
            padding: "12px 16px", borderRadius: 10, maxWidth: 880, marginTop: 16,
            border: "1px solid var(--border)",
            borderLeft: "4px solid var(--warning, #B8860B)",
            fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.65,
          }}>
            {c.nota}
          </div>
        </>
      )}
    </div>
  );
}
