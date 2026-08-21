"use client";
//
// Escalones de costo — Costos para Negociación de Grupos §4.4.
//
// **La tabla existía, el motor la leía y nadie la podía llenar.** Sin escalones
// cargados, el modelo SUBESTIMA los grupos grandes — que son justo los que se
// negocian. El guía adicional, el vehículo que no cabe, el turno extra de
// cocina, el bloque de habitaciones que hay que abrir: nada de eso entraba al
// costo, y el piso salía más barato que la realidad con cara de medido.
//
// ⚠️ Por eso la pantalla dice EN VOZ ALTA cuando la lista está vacía. Un cero
// que significa «nadie lo cargó» leído como «no hay costo extra» es el error
// caro, y no se distingue solo.
//
import { useCallback, useEffect, useState } from "react";
import IrA from "@/components/IrA";
import {
  getEscalones, crearEscalon, editarEscalon, borrarEscalon, type Escalon,
} from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";

// Qué mide cada driver, en castellano. El motor sólo sabe evaluar estos tres:
// uno fuera de la lista no falla al guardar, **falla en silencio al simular**.
const QUE_MIDE: Record<string, string> = {
  pax: "personas del grupo",
  hab_grupo: "habitaciones del grupo",
  pax_tour: "personas en tour",
};

function num(v: string): number {
  const n = parseFloat((v || "").toString().replace(/[, $]/g, ""));
  return isNaN(n) ? 0 : n;
}

const VACIO: Escalon = {
  dept_code: "", driver: "pax", umbral: "", costo_adicional: "",
  descripcion: "", activo: true,
};

export default function EscalonesPage() {
  const [filas, setFilas] = useState<Escalon[]>([]);
  const [drivers, setDrivers] = useState<string[]>([]);
  const [sinCargar, setSinCargar] = useState(false);
  const [nuevo, setNuevo] = useState<Escalon>({ ...VACIO });
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await getEscalones();
      setFilas(r.escalones);
      setDrivers(r.drivers);
      setSinCargar(r.sin_cargar);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  async function agregar() {
    setError(null); setAviso(null);
    try {
      await crearEscalon(nuevo);
      setAviso(`«${nuevo.descripcion || nuevo.driver}» agregado: desde la próxima simulación los grupos que lo crucen cuestan más`);
      setNuevo({ ...VACIO });
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo agregar");
    }
  }

  async function guardar(e: Escalon) {
    setError(null); setAviso(null);
    try {
      await editarEscalon(e.id as string, e);
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo guardar");
    }
  }

  async function quitar(e: Escalon) {
    setError(null); setAviso(null);
    try {
      await borrarEscalon(e.id as string);
      setAviso("Escalón borrado: los grupos grandes vuelven a salir más baratos");
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo borrar");
    }
  }

  // ⚠️ El Excel se lleva el aviso de la lista vacía. Bajar un archivo con
  // cero filas y sin explicación es cómo un «nadie lo cargó» se transforma, a
  // dos manos de distancia, en un «no hay costos por escalón».
  async function bajar() {
    setError(null);
    try {
      await bajarCuadros("Escalones de costo", [{
        titulo: "Escalones de costo",
        subtitulo: sinCargar
          ? "SIN CARGAR: la lista vacía no significa que no haya escalones — los grupos grandes salen más baratos que la realidad"
          : "Se suman al costo del grupo ANTES del gross-up. El umbral se cruza con MAYOR QUE",
        hoja: "Escalones",
        columnas: [
          { label: "Qué aparece", ancho: 34, formato: "texto" },
          { label: "Se mide por", ancho: 24, formato: "texto" },
          { label: "A partir de", formato: "num" },
          { label: "Costo adicional", formato: "usd" },
          { label: "Depto", formato: "texto" },
          { label: "Aplica", formato: "texto" },
        ],
        filas: filas.map(e => ({
          label: e.descripcion || e.driver,
          valores: [
            QUE_MIDE[e.driver] || e.driver,
            num(e.umbral),
            num(e.costo_adicional),
            e.dept_code || "—",
            e.activo ? "sí" : "no",
          ],
        })),
      }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo bajar");
    }
  }

  const listo = nuevo.umbral.trim() !== "" && nuevo.costo_adicional.trim() !== "";

  return (
    <div className="pag-media">
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
        Escalones de costo
      </h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 13,
                  marginBottom: 14, maxWidth: 860, lineHeight: 1.65 }}>
        Costos que <b>aparecen al cruzar un umbral</b>: el guía adicional, el
        vehículo que no cabe, el turno extra de cocina, el bloque de
        habitaciones que hay que abrir. Se suman al costo del grupo{" "}
        <b>antes</b> del gross-up, así que mueven los cuatro pisos y el
        descuento máximo.
      </p>

      {sinCargar && !cargando && (
        <div style={{
          padding: "12px 16px", borderRadius: 10, maxWidth: 860,
          border: "1px solid var(--border)",
          borderLeft: "4px solid var(--warning, #B8860B)", marginBottom: 16,
        }}>
          <div style={{ fontWeight: 700, color: "var(--warning, #B8860B)",
                        fontSize: 14 }}>
            No hay ningún escalón cargado
          </div>
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                      margin: "6px 0 0", lineHeight: 1.6 }}>
            Eso <b>no quiere decir que no haya costos por escalón</b>: quiere
            decir que nadie los cargó. Mientras la lista esté vacía, los grupos
            grandes salen <b>más baratos que la realidad</b> — y son justo los
            que se negocian.
          </p>
        </div>
      )}

      <div style={{ marginBottom: 12 }}>
        <button className="fin-btn" onClick={bajar} disabled={cargando}>
          ⬇ Excel
        </button>
      </div>

      {error && (
        <p style={{ color: "var(--negative)", fontSize: 13 }}>{error}</p>
      )}
      {aviso && (
        <p style={{ color: "var(--positive)", fontSize: 13 }}>{aviso}</p>
      )}

      {cargando ? (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Cargando…</p>
      ) : (
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 860 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Qué aparece</th>
                <th style={{ textAlign: "left" }}>Se mide por</th>
                <th style={{ textAlign: "right" }}>A partir de</th>
                <th style={{ textAlign: "right" }}>Costo adicional</th>
                <th style={{ textAlign: "left" }}>Depto</th>
                <th style={{ textAlign: "center" }}>Aplica</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filas.map(e => (
                <tr key={e.id}>
                  <td style={{ textAlign: "left" }}>{e.descripcion || "—"}</td>
                  <td style={{ textAlign: "left" }}>
                    {QUE_MIDE[e.driver] || e.driver}
                  </td>
                  <td style={{ textAlign: "right" }} className="mono">
                    {e.umbral}
                  </td>
                  <td style={{ textAlign: "right" }} className="mono">
                    {e.costo_adicional}
                  </td>
                  <td style={{ textAlign: "left" }} className="mono">
                    {e.dept_code || "—"}
                  </td>
                  <td style={{ textAlign: "center" }}>
                    <input type="checkbox" checked={e.activo}
                           onChange={ev => guardar({ ...e, activo: ev.target.checked })} />
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button className="fin-btn" onClick={() => quitar(e)}
                            title="Borrar abarata los grupos grandes. Para dejar de aplicarlo sin perderlo, destildá «Aplica»">
                      ×
                    </button>
                  </td>
                </tr>
              ))}
              <tr>
                <td style={{ textAlign: "left" }}>
                  <input className="fin-input" value={nuevo.descripcion}
                         placeholder="Guía adicional"
                         onChange={ev => setNuevo({ ...nuevo, descripcion: ev.target.value })} />
                </td>
                <td style={{ textAlign: "left" }}>
                  <select className="fin-input" value={nuevo.driver}
                          onChange={ev => setNuevo({ ...nuevo, driver: ev.target.value })}>
                    {drivers.map(d => (
                      <option key={d} value={d}>{QUE_MIDE[d] || d}</option>
                    ))}
                  </select>
                </td>
                <td style={{ textAlign: "right" }}>
                  <input className="fin-input" value={nuevo.umbral} placeholder="20"
                         style={{ width: 90, textAlign: "right" }}
                         onChange={ev => setNuevo({ ...nuevo, umbral: ev.target.value })} />
                </td>
                <td style={{ textAlign: "right" }}>
                  <input className="fin-input" value={nuevo.costo_adicional}
                         placeholder="150" style={{ width: 110, textAlign: "right" }}
                         onChange={ev => setNuevo({ ...nuevo, costo_adicional: ev.target.value })} />
                </td>
                <td style={{ textAlign: "left" }}>
                  <input className="fin-input" value={nuevo.dept_code}
                         placeholder="0150" style={{ width: 80 }}
                         onChange={ev => setNuevo({ ...nuevo, dept_code: ev.target.value })} />
                </td>
                <td />
                <td style={{ textAlign: "right" }}>
                  <button className="fin-btn" onClick={agregar} disabled={!listo}>
                    Agregar
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <p style={{ color: "var(--text-secondary)", fontSize: 12,
                  marginTop: 14, maxWidth: 860, lineHeight: 1.6 }}>
        ⚠️ El umbral se cruza con <b>mayor que</b>, no «mayor o igual»: un
        escalón a partir de 20 personas no lo paga un grupo de exactamente 20.
        Y un umbral en cero no se acepta — lo cruzarían todos los grupos, así
        que sería un costo fijo disfrazado de excepción.
      </p>
    </div>
  );
}
