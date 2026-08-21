"use client";
//
// Simulador de grupos — «grupo de 20 pax, 3 noches, en julio, a este precio:
// ¿lo tomo, y quién lo autoriza?».
//
// ⚠️ **Las dos vistas llaman a endpoints DISTINTOS.** En «Ventas» el costo no
// llega al navegador: no se esconde con CSS ni con un `if` de render, no
// viaja. Un vendedor con el costo a la vista negocia contra el costo, no
// contra el piso — y el spec lo pide en letras: «Sin costos visibles».
//
import { useCallback, useEffect, useState } from "react";
import IrA from "@/components/IrA";
import {
  simularGrupo, salidaVentasGrupo,
  type SimulacionGrupo, type SalidaVentas,
} from "@/lib/api";
import { bajarCuadros, type FilaCuadro } from "@/lib/exportCuadro";

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"];

function usd(v: string | null | undefined, dec = 2): string {
  const n = parseFloat(v ?? "0");
  if (isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: dec,
                                     maximumFractionDigits: dec });
}

// Los colores del semáforo salen de los tokens del tema, no de hexadecimales
// sueltos: en el tema oscuro un rojo fijo queda ilegible.
const COLOR: Record<string, string> = {
  verde: "var(--positive)",
  amarilla: "var(--warning, #B8860B)",
  roja: "var(--negative)",
  prohibida: "var(--negative)",
};
const ETIQUETA: Record<string, string> = {
  verde: "VERDE", amarilla: "AMARILLA", roja: "ROJA", prohibida: "PROHIBIDA",
};

type Vista = "interna" | "ventas";

export default function SimuladorGruposPage() {
  const [vista, setVista] = useState<Vista>("interna");
  const [habitaciones, setHabitaciones] = useState("10");
  const [noches, setNoches] = useState("3");
  const [pax, setPax] = useState("20");
  const [mes, setMes] = useState(7);
  const [precio, setPrecio] = useState("550");
  const [amenidades, setAmenidades] = useState("0");

  const [sim, setSim] = useState<SimulacionGrupo | null>(null);
  const [ven, setVen] = useState<SalidaVentas | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const correr = useCallback(async () => {
    setCargando(true);
    setError(null);
    const c = {
      habitaciones: parseInt(habitaciones) || 0,
      noches: parseInt(noches) || 0,
      pax: parseInt(pax) || 0,
      mes,
      precio_pax_noche: precio || undefined,
      amenidades_usd: amenidades || "0",
    };
    try {
      if (vista === "ventas") {
        // ⚠️ Sólo este endpoint. El otro ni se llama: el costo no viaja.
        setSim(null);
        setVen(await salidaVentasGrupo(c));
      } else {
        setVen(null);
        setSim(await simularGrupo(c));
      }
    } catch (e) {
      setSim(null);
      setVen(null);
      setError(e instanceof Error ? e.message : "no se pudo calcular");
    } finally {
      setCargando(false);
    }
  }, [vista, habitaciones, noches, pax, mes, precio, amenidades]);

  useEffect(() => { correr(); }, [correr]);

  // ── Excel ─────────────────────────────────────────────────────────────────
  //
  // ⚠️ **Respeta la vista.** En modo Ventas el archivo lleva sólo los precios:
  // un Excel que se baja desde la vista sin costos y sale con los costos
  // adentro es peor que no tener la vista, porque el archivo se reenvía.
  // Además el costo ni siquiera está en memoria — `sim` es null.
  async function bajarExcel() {
    const cab = `${habitaciones} hab × ${noches} noches × ${pax} pax · `
      + `${MESES[mes - 1]}`;
    try {
      if (ven) {
        await bajarCuadros("Grupo_Precio_Minimo", [{
          titulo: "Precio mínimo del grupo",
          subtitulo: `${cab} · ${ven.temporada}`
            + (ven.zona ? ` · semáforo ${ETIQUETA[ven.zona]} — autoriza ${ven.autoriza}` : ""),
          hoja: "Precio minimo",
          columnas: [
            { label: "", ancho: 44, formato: "texto" },
            { label: "$ / pax / noche", ancho: 16, formato: "usd2" },
            { label: "$ / pax / estadía", ancho: 16, formato: "usd2" },
            { label: "Total del grupo", ancho: 16, formato: "usd2" },
          ],
          filas: [
            { label: "Recomendado", nivel: 1, valores: [
              parseFloat(ven.precio_minimo.recomendado_pax_noche),
              parseFloat(ven.precio_minimo.recomendado_pax_estadia),
              parseFloat(ven.precio_minimo.recomendado_total)] },
            { label: "Límite — por debajo hace falta autorización", nivel: 1, valores: [
              parseFloat(ven.precio_minimo.limite_pax_noche),
              parseFloat(ven.precio_minimo.limite_pax_estadia),
              parseFloat(ven.precio_minimo.limite_total)] },
          ] as FilaCuadro[],
        }]);
        return;
      }
      if (!sim) return;
      await bajarCuadros("Grupo_Simulacion", [
        {
          titulo: "Precio mínimo por piso",
          subtitulo: `${cab} · ${sim.temporada} · costos de ${sim.escenario}`
            + (sim.marginal_estimado ? " · ⚠️ Piso 1 estimado" : ""),
          hoja: "Pisos",
          columnas: [
            { label: "", ancho: 34, formato: "texto" },
            { label: "$ / pax / noche", ancho: 16, formato: "usd2" },
            { label: "$ / pax / estadía", ancho: 16, formato: "usd2" },
            { label: "Total del grupo", ancho: 16, formato: "usd2" },
          ],
          filas: ([
            ["Piso 1 · marginal", "marginal"],
            ["Piso 2 · departamental", "departamental"],
            ["Piso 3 · integral", "integral"],
            ["Piso 4 · con margen protegido", "con_margen"],
          ] as const).map(([et, k]): FilaCuadro => ({
            label: et, nivel: 1, valores: [
              parseFloat(sim.minimos.por_pax_noche[k]),
              parseFloat(sim.minimos.por_pax_estadia[k]),
              parseFloat(sim.minimos.ingreso[k])],
          })),
        },
        {
          titulo: "De qué está hecho el costo",
          subtitulo: sim.prorrateados.join(" · "),
          hoja: "Costo",
          columnas: [
            { label: "Componente", ancho: 34, formato: "texto" },
            { label: "USD", ancho: 16, formato: "usd2" },
          ],
          filas: ([
            ["Habitaciones", "habitaciones"], ["Alimentos y bebidas", "fb"],
            ["Tours", "tours"], ["Transporte", "transporte"], ["Spa", "spa"],
            ["Amenidades", "amenidades"], ["Escalones", "escalones"],
            ["Overhead absorbido", "overhead"], ["Costo total", "total"],
          ] as const).map(([et, k]): FilaCuadro => ({
            label: et, nivel: k === "total" ? 0 : 1,
            valores: [parseFloat(sim.costo[k])],
          })),
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo bajar el Excel");
    }
  }

  const btn = (on: boolean): React.CSSProperties => ({
    padding: "6px 14px", borderRadius: 6, fontSize: 13, fontWeight: 600,
    cursor: "pointer", border: "1px solid var(--border)",
    background: on ? "var(--brand)" : "var(--bg-surface)",
    color: on ? "#fff" : "var(--text-secondary)",
  });

  const campo = (etq: string, v: string, set: (s: string) => void,
                 ancho = 90) => (
    <label style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{etq}</span>
      <input className="fin-input mono" value={v} onChange={e => set(e.target.value)}
        onFocus={e => e.target.select()}
        style={{ width: ancho, textAlign: "right", padding: "4px 6px" }} />
    </label>
  );

  const zona = sim?.propuesta.zona ?? ven?.zona ?? null;
  const autoriza = sim?.propuesta.autoriza ?? ven?.autoriza ?? null;

  return (
    <div className="pag pag-media" style={{ padding: 24 }}>
      <IrA />

      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          Simulador de grupos
        </h1>
        <div style={{ flex: 1 }} />
        <button onClick={bajarExcel} disabled={!sim && !ven}
          style={{ ...btn(false), color: "var(--positive)",
                   border: "1px solid var(--positive)", background: "transparent" }}>
          ⬇ Excel
        </button>
        <div style={{ display: "flex", gap: 4 }}>
          {(["interna", "ventas"] as Vista[]).map(v => (
            <button key={v} onClick={() => setVista(v)} style={btn(vista === v)}>
              {v === "interna" ? "Vista interna" : "Vista Ventas"}
            </button>
          ))}
        </div>
      </div>

      {vista === "ventas" && (
        <div style={{
          border: "1px solid var(--border)", borderLeft: "3px solid var(--positive)",
          borderRadius: 6, padding: "10px 14px", marginTop: 12,
          fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6,
        }}>
          <b style={{ color: "var(--text-primary)" }}>Esta vista no recibe costos.</b>{" "}
          No están escondidos: el navegador llama a otro endpoint y el costo nunca
          viaja. Se puede mostrar en una mesa de negociación.
        </div>
      )}

      {/* ── Los datos del grupo ─────────────────────────────────────────── */}
      <div style={{
        display: "flex", gap: 14, alignItems: "flex-end", flexWrap: "wrap",
        marginTop: 20, padding: "14px 16px", borderRadius: 8,
        border: "1px solid var(--border)", background: "var(--bg-surface)",
      }}>
        {campo("Habitaciones", habitaciones, setHabitaciones, 90)}
        {campo("Noches", noches, setNoches, 70)}
        {campo("Pax", pax, setPax, 70)}
        <label style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Mes</span>
          <select value={mes} onChange={e => setMes(parseInt(e.target.value))}
            className="fin-input" style={{ minWidth: 130, padding: "4px 6px" }}>
            {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </label>
        {campo("$ / pax / noche", precio, setPrecio, 110)}
        {vista === "interna" && campo("Amenidades $", amenidades, setAmenidades, 100)}
      </div>

      {error && (
        <div style={{ color: "var(--negative)", fontSize: 13, marginTop: 14 }}>{error}</div>
      )}
      {cargando && (
        <div style={{ color: "var(--text-secondary)", padding: 16 }}>Calculando…</div>
      )}

      {/* ── El semáforo ─────────────────────────────────────────────────── */}
      {zona && (
        <div style={{
          marginTop: 20, padding: "14px 18px", borderRadius: 8,
          border: `2px solid ${COLOR[zona]}`,
          display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        }}>
          <span style={{ fontSize: 22, fontWeight: 800, color: COLOR[zona],
                         letterSpacing: 0.5 }}>
            {ETIQUETA[zona]}
          </span>
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {/* ⚠️ La zona sin la autorización deja la decisión en el aire: la
                roja no es «no», es «sí con el GG y Finanzas». */}
            Autoriza: <b style={{ color: "var(--text-primary)" }}>{autoriza}</b>
          </span>
        </div>
      )}

      {/* ── VISTA VENTAS ────────────────────────────────────────────────── */}
      {ven && (
        <>
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8,
                       color: "var(--text-primary)" }}>
            Precio mínimo · {MESES[ven.mes - 1]} ({ven.temporada})
          </h2>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 560 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", minWidth: 200 }}></th>
                  <th style={{ textAlign: "right" }}>$ / pax / noche</th>
                  <th style={{ textAlign: "right" }}>$ / pax / estadía</th>
                  <th style={{ textAlign: "right" }}>Total del grupo</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ textAlign: "left", fontWeight: 700 }}>Recomendado</td>
                  <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                    ${usd(ven.precio_minimo.recomendado_pax_noche)}</td>
                  <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                    ${usd(ven.precio_minimo.recomendado_pax_estadia)}</td>
                  <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                    ${usd(ven.precio_minimo.recomendado_total)}</td>
                </tr>
                <tr>
                  <td style={{ textAlign: "left" }}>Límite — por debajo hace falta autorización</td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    ${usd(ven.precio_minimo.limite_pax_noche)}</td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    ${usd(ven.precio_minimo.limite_pax_estadia)}</td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    ${usd(ven.precio_minimo.limite_total)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 10 }}>
            Por debajo del límite: <b>{ven.bajo_el_limite_requiere}</b>.
          </p>
        </>
      )}

      {/* ── VISTA INTERNA ───────────────────────────────────────────────── */}
      {sim && (
        <>
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8,
                       color: "var(--text-primary)" }}>
            Precio mínimo por pax por noche · {MESES[sim.mes - 1]} ({sim.temporada})
          </h2>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 640 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", minWidth: 240 }}></th>
                  <th style={{ textAlign: "right" }}>$ / pax / noche</th>
                  <th style={{ textAlign: "right" }}>$ / pax / estadía</th>
                  <th style={{ textAlign: "right" }}>Total del grupo</th>
                </tr>
              </thead>
              <tbody>
                {([
                  ["Piso 1 · marginal", "marginal"],
                  ["Piso 2 · departamental", "departamental"],
                  ["Piso 3 · integral", "integral"],
                  ["Piso 4 · con margen protegido", "con_margen"],
                ] as const).map(([et, k]) => (
                  <tr key={k}>
                    <td style={{ textAlign: "left",
                                 fontWeight: k === "con_margen" ? 700 : 400 }}>
                      {et}
                      {k === "marginal" && sim.marginal_estimado && (
                        <span style={{ color: "var(--negative)", fontSize: 11,
                                       marginLeft: 6 }}>estimado</span>
                      )}
                    </td>
                    <td className="mono" style={{ textAlign: "right",
                          fontWeight: k === "con_margen" ? 700 : 400 }}>
                      ${usd(sim.minimos.por_pax_noche[k])}</td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      ${usd(sim.minimos.por_pax_estadia[k])}</td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      ${usd(sim.minimos.ingreso[k])}</td>
                  </tr>
                ))}
                {sim.propuesta.ingreso && (
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 700,
                                 color: zona ? COLOR[zona] : undefined }}>
                      Propuesta
                    </td>
                    <td className="mono" style={{ textAlign: "right", fontWeight: 700,
                          color: zona ? COLOR[zona] : undefined }}>${usd(precio)}</td>
                    <td className="mono" style={{ textAlign: "right" }}>—</td>
                    <td className="mono" style={{ textAlign: "right", fontWeight: 700,
                          color: zona ? COLOR[zona] : undefined }}>
                      ${usd(sim.propuesta.ingreso)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8,
                       color: "var(--text-primary)" }}>
            De qué está hecho el costo
          </h2>
          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 460, maxWidth: 620 }}>
              <tbody>
                {([
                  ["Habitaciones", "habitaciones"], ["Alimentos y bebidas", "fb"],
                  ["Tours", "tours"], ["Transporte", "transporte"],
                  ["Spa", "spa"], ["Amenidades", "amenidades"],
                  ["Escalones", "escalones"], ["Overhead absorbido", "overhead"],
                ] as const).map(([et, k]) => (
                  <tr key={k}>
                    <td style={{ textAlign: "left" }}>{et}</td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      ${usd(sim.costo[k])}</td>
                  </tr>
                ))}
                <tr>
                  <td style={{ textAlign: "left", fontWeight: 700 }}>Costo total</td>
                  <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                    ${usd(sim.costo.total)}</td>
                </tr>
                {sim.propuesta.margen && (
                  <tr>
                    <td style={{ textAlign: "left", fontWeight: 700 }}>
                      Margen contra la propuesta
                    </td>
                    <td className="mono" style={{ textAlign: "right", fontWeight: 700,
                          color: parseFloat(sim.propuesta.margen) >= 0
                            ? "var(--positive)" : "var(--negative)" }}>
                      ${usd(sim.propuesta.margen)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28, marginBottom: 8,
                       color: "var(--text-primary)" }}>
            Desplazamiento
          </h2>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", maxWidth: 800 }}>
            {sim.desplazamiento.aplica ? (
              <>
                Desplaza <b>{usd(sim.desplazamiento.noches, 0)}</b> habitación-noches,
                con un ADR esperado de <b>${usd(sim.desplazamiento.adr_esperado)}</b> —
                contribución desplazada <b>${usd(sim.desplazamiento.contribucion)}</b>,
                ya sumada a los pisos de arriba.
              </>
            ) : (
              <>No aplica: {sim.desplazamiento.motivo}. Ocupación del mes{" "}
                <b>{(parseFloat(sim.desplazamiento.ocupacion_pct) * 100).toFixed(1)}%</b>,
                con <b>{usd(sim.desplazamiento.habitaciones_libres, 0)}</b> habitación-noches
                libres.</>
            )}
          </p>

          {/* ⚠️ Esto NO es una nota al pie. Un costo prorrateado que se presenta
              como medido convierte un supuesto en un compromiso contractual. */}
          {sim.prorrateados.length > 0 && (
            <div style={{
              marginTop: 24, padding: "12px 16px", borderRadius: 8,
              border: "1px solid var(--negative)",
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--negative)",
                            marginBottom: 6 }}>
                Qué de esto NO está medido
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5,
                           color: "var(--text-secondary)", lineHeight: 1.7 }}>
                {sim.prorrateados.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}

          <p style={{ fontSize: 11.5, color: "var(--text-disabled)", marginTop: 16 }}>
            Costos de {sim.escenario} · comisión del tarifario{" "}
            {(parseFloat(sim.comision) * 100).toFixed(2)}%
          </p>
        </>
      )}
    </div>
  );
}
