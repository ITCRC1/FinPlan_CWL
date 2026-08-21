"use client";
//
// PROPUESTA DE DESCUENTOS — COSTO FULLY LOADED (spec `COSTOS_GRUPOS.md` §5).
//
// Réplica del reporte que la Junta aprobó. Pedido del owner (2026-08-20):
// «quiero tener un tab así, resumido» y después «podés ampliar ese summary que
// quede más claro».
//
// ⚠️ **La advertencia del §5 va arriba y no en letra chica.** Estos porcentajes
// sirven para leer el P&L y fijar techos de comisión, NO para fijar pisos de
// precio: acá el overhead va asignado por revenue a TODOS los departamentos,
// mientras que el piso lo calcula el otro camino absorbiéndolo por
// habitación-noche y cargándolo sólo a Habitaciones (§4.2). Las dos cosas están
// bien; usar una por la otra es cómo se regala margen o se rechaza negocio.
//
// ⚠️ **Un departamento que pierde se muestra en NEGATIVO, no recortado a cero.**
// En el cuadro del owner la Tienda da −2,1%: mostrar 0% diría «no podés
// descontar» cuando la verdad es «ya estás debajo del costo».
//
import { useCallback, useEffect, useState } from "react";
import IrA from "@/components/IrA";
import MesesElegidos from "@/components/MesesElegidos";
import {
  getFullyLoaded, getScenarios,
  type FullyLoaded, type FilaFullyLoaded, type Scenario,
} from "@/lib/api";
import { bajarCuadros, type FormatoCol } from "@/lib/exportCuadro";

const NOMBRE: Record<string, string> = {
  ROOMS: "Habitaciones",
  FB: "F&B",
  SPA: "Spa",
  RETAIL: "Tienda",
  TOURS: "Tours y Actividades",
  TRANSPORTATION: "Transporte",
  LAUNDRY: "Laundry",
  CLUB: "Club",
  INNOCEANA: "Innoceana",
  SUSTAINABILITY: "Sustainability Fee",
  MISC_OTHER: "Otros",
};

const HOTEL = process.env.NEXT_PUBLIC_HOTEL_ID || "CWL";

// ⚠️ Temporada y período son INDEPENDIENTES (§5). Antes «año completo» estaba
// metido en el desplegable de temporada, así que no se podía pedir «año
// completo × temporada alta» — que es justo la vista con la que se negocia.
const TEMPORADAS = [
  { v: "", t: "Todas las temporadas" },
  { v: "ALTA", t: "Temporada alta" },
  { v: "MEDIA", t: "Temporada media" },
  { v: "BAJA", t: "Temporada baja" },
];

const MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"];

function usd(v: string): string {
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  const s = Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2,
                                                  maximumFractionDigits: 2 });
  // Negativos entre paréntesis, como en el reporte del owner.
  return n < 0 ? `($${s})` : `$${s}`;
}

function pct(v: string): string {
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  const s = (Math.abs(n) * 100).toFixed(1) + "%";
  return n < 0 ? `(${s})` : s;
}

const rojo = (v: string) => (parseFloat(v) < 0 ? "var(--negative)" : undefined);

export default function DescuentosPage() {
  const [temporada, setTemporada] = useState("ALTA");
  const [periodo, setPeriodo] = useState<"full" | "ytd" | "mes">("full");
  const [mes, setMes] = useState(1);
  const [meses, setMeses] = useState<number[]>([]);
  const [escenarioId, setEscenarioId] = useState("");
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [d, setD] = useState<FullyLoaded | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Sólo para poblar el desplegable: la base por defecto la decide el
    // backend, que es donde vive `escenario_base`.
    getScenarios(HOTEL).then(setEscenarios).catch(() => setEscenarios([]));
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const datos = await getFullyLoaded({
        periodo, mes, meses, temporada: temporada || undefined,
        escenarioId: escenarioId || undefined,
      });
      setD(datos);
      // El corte del YTD lo sabe el backend; acá sólo se refleja.
      if (periodo === "ytd" && meses.length === 0 && datos.seleccion?.meses) {
        setMeses(datos.seleccion.meses);
        setPeriodo("full");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo calcular");
    } finally {
      setCargando(false);
    }
  }, [periodo, mes, meses, temporada, escenarioId]);

  useEffect(() => { cargar(); }, [cargar]);

  async function bajar() {
    if (!d || d.vacio) return;
    setError(null);
    try {
      await bajarCuadros("Propuesta de descuentos", [{
        titulo: "Propuesta de descuentos — costo fully loaded",
        subtitulo: `${d.escenario} · ${d.seleccion?.etiqueta || ""} · ${d.advertencia}`,
        hoja: "Descuentos",
        columnas: [
          { label: "Departamento", ancho: 26, formato: "texto" as FormatoCol },
          { label: "Revenue", formato: "usd" as FormatoCol },
          { label: "Costo dept.", formato: "usd" as FormatoCol },
          { label: "Costo dept. %", formato: "pct" as FormatoCol },
          { label: "Overhead", formato: "usd" as FormatoCol },
          { label: "Overhead %", formato: "pct" as FormatoCol },
          { label: "Fee", formato: "usd" as FormatoCol },
          { label: "Costo fully loaded %", formato: "pct" as FormatoCol },
          { label: "Utilidad", formato: "usd" as FormatoCol },
          { label: "Margen actual", formato: "pct" as FormatoCol },
          { label: "Descuento máximo", formato: "pct" as FormatoCol },
        ],
        filas: [
          ...d.filas.map(f => ({
            label: NOMBRE[f.concepto] || f.concepto,
            valores: [
              parseFloat(f.revenue), parseFloat(f.costo_departamento),
              parseFloat(f.costo_departamento_pct), parseFloat(f.overhead),
              parseFloat(f.overhead_pct), parseFloat(f.fee),
              parseFloat(f.costo_fully_loaded_pct), parseFloat(f.utilidad),
              parseFloat(f.margen_actual), parseFloat(f.descuento_maximo),
            ],
          })),
          {
            label: "TOTAL",
            es_total: true,
            valores: [
              parseFloat(d.totales.revenue), parseFloat(d.totales.costo_departamental),
              null, parseFloat(d.totales.overhead), parseFloat(d.totales.overhead_pct),
              parseFloat(d.totales.fee), null, parseFloat(d.totales.utilidad),
              parseFloat(d.totales.margen_ponderado), null,
            ],
          },
        ],
      }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo bajar");
    }
  }

  const banda = d && !d.vacio ? [
    { t: "Revenue analizado", v: usd(d.totales.revenue) },
    { t: "Costo departamental", v: usd(d.totales.costo_departamental) },
    { t: "Overhead asignado", v: usd(d.totales.overhead) },
    { t: `Management Fee ${pct(d.filas[0]?.fee_pct || "0.03")}`,
      v: usd(d.totales.fee) },
    { t: "Utilidad fully loaded", v: usd(d.totales.utilidad) },
    { t: "Margen ponderado", v: pct(d.totales.margen_ponderado) },
  ] : [];

  return (
    <div className="pag-ancha">
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
        Propuesta de descuentos — costo fully loaded
      </h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 13,
                  marginBottom: 12, maxWidth: 980, lineHeight: 1.65 }}>
        Incluye costo departamental, overhead asignado por revenue y management
        fee. <b>Descuento máximo</b> = hasta dónde puede bajar la tarifa antes
        de dejar de cubrir el costo total integral.
        {d && !d.vacio && <> Base: <b>{d.escenario}</b>.</>}
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "flex-end",
                    marginBottom: 14, flexWrap: "wrap" }}>
        <label style={{ fontSize: 12.5 }}>
          <div style={{ color: "var(--text-secondary)", marginBottom: 3 }}>
            Base
          </div>
          <select className="fin-input" value={escenarioId}
                  onChange={e => setEscenarioId(e.target.value)}
                  style={{ minWidth: 250 }}>
            <option value="">La configurada{d?.base_configurada
              ? ` (${d.base_configurada})` : ""}</option>
            {escenarios.map(s => (
              <option key={s.id} value={s.id}>
                {s.type} {s.year} {s.version}
              </option>
            ))}
          </select>
        </label>

        <label style={{ fontSize: 12.5 }}>
          <div style={{ color: "var(--text-secondary)", marginBottom: 3 }}>
            Temporada
          </div>
          <select className="fin-input" value={temporada}
                  onChange={e => setTemporada(e.target.value)}
                  style={{ minWidth: 190 }}>
            {TEMPORADAS.map(t => (
              <option key={t.v} value={t.v}>{t.t}</option>
            ))}
          </select>
        </label>

        <button className="fin-btn" onClick={bajar}
                disabled={cargando || !d || d.vacio}>⬇ Excel</button>

        {/* Los doce meses, para marcar los que salen. */}
        <div style={{ flex: "1 1 100%", fontSize: 12.5 }}>
          <div style={{ color: "var(--text-secondary)", marginBottom: 4 }}>Meses</div>
          <MesesElegidos meses={meses} onChange={setMeses}
                         onYtd={() => { setMeses([]); setPeriodo("ytd"); }} />
        </div>
      </div>

      {/* ⚠️ Mirar una base distinta de la configurada tiene que VERSE: es el
          número con el que se firma un contrato. */}
      {d && !d.vacio && d.es_base === false && (
        <p style={{ color: "var(--warning, #B8860B)", fontSize: 12.5,
                    fontWeight: 600, marginBottom: 10 }}>
          Estás mirando <b>{d.escenario}</b>, que no es la base configurada
          (<b>{d.base_configurada}</b>). Los pisos oficiales se calculan sobre la
          configurada.
        </p>
      )}

      {error && <p style={{ color: "var(--negative)", fontSize: 13 }}>{error}</p>}
      {cargando && (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Calculando…</p>
      )}

      {/* ⚠️ Una combinación vacía se DICE. Un cero que en realidad es «no hay
          meses» se lee como «no hay costo», que es lo contrario. */}
      {d?.vacio && (
        <p style={{ color: "var(--warning, #B8860B)", fontSize: 13 }}>
          {d.motivo}
        </p>
      )}

      {d && !d.vacio && (
        <>
          {/* La banda de totales del reporte del owner. */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 1,
                        marginBottom: 16, borderRadius: 8, overflow: "hidden" }}>
            {banda.map(b => (
              <div key={b.t} style={{
                flex: "1 1 150px", padding: "10px 14px",
                background: "var(--bg-header)", color: "var(--text-on-header, #fff)",
              }}>
                <div style={{ fontSize: 11, opacity: 0.85 }}>{b.t}</div>
                <div style={{ fontSize: 17, fontWeight: 700 }}>{b.v}</div>
              </div>
            ))}
          </div>

          {/* ⚠️ Los que pierden, arriba y por nombre: si hay que mirar algo
              primero, es esto, y no debería depender de recorrer la tabla. */}
          {d.pierden.length > 0 && (
            <p style={{ color: "var(--negative)", fontSize: 13, fontWeight: 600,
                        marginBottom: 10 }}>
              La tarifa actual no cubre el costo en:{" "}
              {d.pierden.map(c => NOMBRE[c] || c).join(" · ")}
            </p>
          )}

          <div className="fin-sticky" style={{ overflowX: "auto" }}>
            <table className="fin-table" style={{ minWidth: 1100 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Departamento</th>
                  <th style={{ textAlign: "right" }}>Revenue</th>
                  <th style={{ textAlign: "right" }}>Costo dept.</th>
                  <th style={{ textAlign: "right" }}>Costo dept. %</th>
                  <th style={{ textAlign: "right" }}>Overhead</th>
                  <th style={{ textAlign: "right" }}>Overhead %</th>
                  <th style={{ textAlign: "right" }}>Fee</th>
                  <th style={{ textAlign: "right" }}>Costo fully loaded %</th>
                  <th style={{ textAlign: "right" }}>Utilidad</th>
                  <th style={{ textAlign: "right" }}>Margen actual</th>
                  <th style={{ textAlign: "right" }}>Descuento máximo</th>
                  <th style={{ textAlign: "left" }}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {d.filas.map((f: FilaFullyLoaded) => (
                  <tr key={f.concepto}>
                    <td style={{ textAlign: "left", fontWeight: 600 }}>
                      {NOMBRE[f.concepto] || f.concepto}
                    </td>
                    <td style={{ textAlign: "right" }} className="mono">{usd(f.revenue)}</td>
                    <td style={{ textAlign: "right" }} className="mono">{usd(f.costo_departamento)}</td>
                    <td style={{ textAlign: "right" }} className="mono">{pct(f.costo_departamento_pct)}</td>
                    <td style={{ textAlign: "right" }} className="mono">{usd(f.overhead)}</td>
                    <td style={{ textAlign: "right" }} className="mono">{pct(f.overhead_pct)}</td>
                    <td style={{ textAlign: "right" }} className="mono">{usd(f.fee)}</td>
                    <td style={{ textAlign: "right" }} className="mono">{pct(f.costo_fully_loaded_pct)}</td>
                    <td style={{ textAlign: "right", color: rojo(f.utilidad) }}
                        className="mono">{usd(f.utilidad)}</td>
                    <td style={{ textAlign: "right", color: rojo(f.margen_actual) }}
                        className="mono">{pct(f.margen_actual)}</td>
                    <td style={{ textAlign: "right", fontWeight: 700,
                                 color: rojo(f.descuento_maximo) }}
                        className="mono">{pct(f.descuento_maximo)}</td>
                    <td style={{ textAlign: "left", fontSize: 12,
                                 color: f.cubre ? "var(--text-secondary)"
                                                : "var(--negative)" }}>
                      {f.estado}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ⚠️ La advertencia del §5, a la vista y no en letra chica. */}
          <div style={{
            padding: "12px 16px", borderRadius: 10, maxWidth: 980, marginTop: 16,
            border: "1px solid var(--border)",
            borderLeft: "4px solid var(--warning, #B8860B)",
            fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.65,
          }}>
            {d.advertencia}
          </div>
        </>
      )}
    </div>
  );
}
