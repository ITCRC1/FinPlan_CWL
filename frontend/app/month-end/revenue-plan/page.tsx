"use client";
/**
 * El armado de ingresos de Planning, para CONSULTAR.
 *
 * Owner, 2026-09-03: *«necesito crear otro tab y sub tabs tal como los
 * checkbooks, pero necesito jalar información de Planning: inventario, noches
 * por categoría, rack rates, ocupación, pax, canales de ventas, net rate y
 * total revenue; y que se pueda consultar por escenario: actual, forecast,
 * budget»*.
 *
 * Los ocho existen en Planning como pantallas de captura. Acá son ocho vistas
 * de LECTURA, con el mismo patrón que Checkbooks: un menú, un selector de
 * versión, y sub-tabs adentro.
 *
 * ## De dónde salen: SEIS de un solo endpoint
 *
 * `/scenarios/{id}/revenue/by-room-type/` devuelve, por tipo de habitación y
 * por mes: unidades, noches disponibles, noches ocupadas, ocupación, ingreso,
 * ADR y pax. Con eso salen seis de los ocho —inventario, noches, ocupación,
 * pax, net rate y total revenue— y salen **conciliados entre sí**, porque los
 * calcula la misma función del motor (`room_type_breakdown`).
 *
 * ⚠️ **Y ese endpoint ya resuelve la pregunta del owner sobre el escenario.**
 * Si la versión tiene estadísticas REALES cargadas —un ACTUAL— las devuelve;
 * si no, las deriva de los drivers. Rehacer esa decisión acá sería elegir mal
 * el día que cambie: un actual mostrando lo proyectado, o al revés.
 *
 * Los otros dos —rack rates y canales— son configuración, no resultado, y
 * tienen su propio endpoint.
 *
 * ## Por qué no se recalcula nada acá
 *
 * Noches ocupadas × net rate ES el ingreso, y la tentación de multiplicarlo en
 * la pantalla es fuerte. Pero el motor tiene reglas que no se ven —paquetes,
 * comisión por canal, el mix— y una multiplicación propia daría un total que
 * no es el del P&L. Todo lo que se muestra viene calculado.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getChannelsConfig, getRackRates, getRevenueByRoomType, getScenarios, rtLabel,
  type ChannelsConfig, type RackRatesResponse, type RevenueByRoomType,
  type Scenario,
} from "@/lib/api";
import { bajarCuadros, type Cuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const CLAVES = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"] as const;

/** Las ocho vistas, en el orden en que el owner las pidió. */
const VISTAS = [
  { key: "inventario", rotulo: "Inventario" },
  { key: "noches", rotulo: "Noches por categoría" },
  { key: "rack", rotulo: "Rack rates" },
  { key: "ocupacion", rotulo: "Ocupación" },
  { key: "pax", rotulo: "Pax" },
  { key: "canales", rotulo: "Canales de venta" },
  { key: "net", rotulo: "Net rate" },
  { key: "revenue", rotulo: "Total revenue" },
] as const;
type Vista = typeof VISTAS[number]["key"];

const num = (n: number, dec = 0) =>
  !n ? "—" : n.toLocaleString("en-US",
    { minimumFractionDigits: dec, maximumFractionDigits: dec });
const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n: number) => !n ? "—" : (n * 100).toFixed(1) + "%";

const TD: React.CSSProperties = {
  padding: "4px 9px", textAlign: "right", fontSize: 11.5, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = { padding: "4px 10px", fontSize: 11.5 };
const SEL: React.CSSProperties = {
  padding: "6px 10px", fontSize: 12.5, borderRadius: 6,
  border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)",
};

/** Una fila: rótulo, doce meses y el total (o el promedio, si no es aditivo). */
interface Fila { label: string; meses: number[]; total: number | null }

export default function RevenuePlanPage() {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [vista, setVista] = useState<Vista>("inventario");
  const [porTipo, setPorTipo] = useState<RevenueByRoomType | null>(null);
  const [rack, setRack] = useState<RackRatesResponse | null>(null);
  const [canales, setCanales] = useState<ChannelsConfig | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [scenarioId, setScenarioId] = useEscenarioDe(
    "month-end/revenue-plan", escenarios, "budget");

  useEffect(() => {
    getScenarios(HOTEL_ID).then(setEscenarios)
      .catch(e => setError(e instanceof Error ? e.message : "No se pudieron cargar los escenarios"));
  }, []);

  const cargar = useCallback(async () => {
    if (!scenarioId) return;
    setCargando(true); setError(null);
    // ⚠️ Los tres a la vez y con `allSettled`: que falte la configuración de
    // canales no puede dejar sin inventario ni sin noches, que son otro
    // endpoint. Antes de esto un 404 en cualquiera vaciaba la pantalla entera.
    const [a, b, c] = await Promise.allSettled([
      getRevenueByRoomType(scenarioId),
      getRackRates(scenarioId),
      getChannelsConfig(scenarioId),
    ]);
    setPorTipo(a.status === "fulfilled" ? a.value : null);
    setRack(b.status === "fulfilled" ? b.value : null);
    setCanales(c.status === "fulfilled" ? c.value : null);
    if (a.status === "rejected" && b.status === "rejected" && c.status === "rejected") {
      setError("No se pudo cargar el armado de ingresos de esta versión.");
    }
    setCargando(false);
  }, [scenarioId]);

  useEffect(() => { cargar(); }, [cargar]);

  /** El valor de un tipo de habitación en un mes, para el campo que se pida. */
  const dato = useCallback((rtId: string, mes: number,
                            campo: "units" | "nights_available" | "nights_occupied"
                                 | "occupancy_pct" | "revenue" | "adr" | "pax") => {
    const m = porTipo?.months.find(x => x.month === mes);
    const r = m?.rows.find(x => x.room_type_id === rtId);
    return r ? Number(r[campo] ?? 0) : 0;
  }, [porTipo]);

  const tipos = porTipo?.room_types ?? [];

  /** Las filas de la vista elegida.
   *
   *  ⚠️ `total` es `null` donde sumar no significa nada. La ocupación y el net
   *  rate son RAZONES: doce por ciento sumados dan un número que no es de
   *  nadie. Ahí va el promedio ponderado, calculado con el numerador y el
   *  denominador del año —igual que el ADR del cierre—. */
  const filas: Fila[] = useMemo(() => {
    const meses = Array.from({ length: 12 }, (_, i) => i + 1);
    const porRt = (campo: Parameters<typeof dato>[2], total: "suma" | "ninguno") =>
      tipos.map(rt => {
        const serie = meses.map(m => dato(rt.id, m, campo));
        return {
          label: rtLabel(rt.code, rt.name),
          meses: serie,
          total: total === "suma" ? serie.reduce((a, n) => a + n, 0) : null,
        };
      });

    switch (vista) {
      case "inventario":
        // Las unidades no se suman a lo largo del año: son las mismas doce
        // veces. El «total» es el inventario, no la suma.
        return tipos.map(rt => ({
          label: rtLabel(rt.code, rt.name),
          meses: meses.map(m => dato(rt.id, m, "units")),
          total: rt.units,
        }));
      case "noches":
        return porRt("nights_occupied", "suma");
      case "pax":
        return porRt("pax", "suma");
      case "revenue":
        return porRt("revenue", "suma");
      case "ocupacion":
        // Ponderada: noches ocupadas del año ÷ noches disponibles del año.
        return tipos.map(rt => {
          const ocup = meses.map(m => dato(rt.id, m, "nights_occupied"));
          const disp = meses.map(m => dato(rt.id, m, "nights_available"));
          const d = disp.reduce((a, n) => a + n, 0);
          return {
            label: rtLabel(rt.code, rt.name),
            meses: meses.map(m => dato(rt.id, m, "occupancy_pct")),
            total: d ? ocup.reduce((a, n) => a + n, 0) / d : 0,
          };
        });
      case "net":
        // El net rate del año es ingreso ÷ noches ocupadas, no el promedio de
        // doce tarifas: un mes con tres noches pesaría igual que uno lleno.
        return tipos.map(rt => {
          const ing = meses.map(m => dato(rt.id, m, "revenue"));
          const noc = meses.map(m => dato(rt.id, m, "nights_occupied"));
          const n = noc.reduce((a, x) => a + x, 0);
          return {
            label: rtLabel(rt.code, rt.name),
            meses: meses.map(m => dato(rt.id, m, "adr")),
            total: n ? ing.reduce((a, x) => a + x, 0) / n : 0,
          };
        });
      case "rack":
        return (rack?.rooms ?? []).map(r => ({
          label: rtLabel(r.code, r.name),
          meses: CLAVES.map(k => Number(r[k] ?? 0)),
          total: null,   // una tarifa no se suma
        }));
      case "canales":
        // Dos filas por canal: el mix y la comisión. Las dos son porcentajes,
        // así que ninguna lleva total.
        return (canales?.channels ?? []).flatMap(c => [
          { label: `${c.label} · mix`,
            meses: c.mix.map(v => Number(v || 0)), total: null },
          { label: `${c.label} · comisión`,
            meses: c.comm.map(v => Number(v || 0)), total: null },
        ]);
    }
  }, [vista, tipos, dato, rack, canales]);

  /** Cómo se escribe cada vista, y si su total significa algo. */
  const formato = (v: Vista) =>
    v === "ocupacion" || v === "canales" ? "pct"
      : v === "rack" || v === "net" || v === "revenue" ? "usd" : "num";
  const escribir = (n: number) => {
    const f = formato(vista);
    return f === "pct" ? pct(n) : f === "usd" ? usd(n) : num(n, vista === "pax" ? 0 : 0);
  };

  const totalMes = (i: number) => filas.reduce((a, f) => a + f.meses[i], 0);
  /** ⚠️ El total de la columna sólo se dibuja donde SUMAR significa algo. Una
   *  columna de porcentajes o de tarifas sumada da un número que no es de
   *  nadie — y puesto en negrita al pie se lee como si lo fuera. */
  const sumable = vista === "inventario" || vista === "noches"
    || vista === "pax" || vista === "revenue";

  /** La vista que se está viendo, a Excel.
   *
   *  ⚠️ Sólo la vista actual y no las ocho: cada una tiene su propia unidad
   *  —noches, porcentajes, dólares— y su propia regla de total. Un libro con
   *  las ocho pegadas invitaría a compararlas columna contra columna, que es
   *  justo lo que no se puede hacer entre un porcentaje y una tarifa. */
  async function bajarExcel() {
    const esc = escenarios.find(s => s.id === scenarioId);
    if (!esc) return;
    const uno: Cuadro = {
      titulo: VISTAS.find(x => x.key === vista)?.rotulo ?? vista,
      subtitulo: `${esc.type} ${esc.version} ${esc.year}`,
      hoja: (VISTAS.find(x => x.key === vista)?.rotulo ?? vista).slice(0, 31),
      columnas: [
        { label: "Tipo de habitación", ancho: 30, formato: "texto" },
        ...MESES.map(m => ({ label: m, ancho: 12,
                             formato: (formato(vista) === "pct" ? "pct"
                               : formato(vista) === "usd" ? "usd2"
                               : "num") as "pct" | "usd2" | "num" })),
        { label: "Total", ancho: 14,
          formato: (formato(vista) === "pct" ? "pct"
            : formato(vista) === "usd" ? "usd2" : "num") as "pct" | "usd2" | "num" },
      ],
      filas: filas.map(f => ({
        label: f.label, es_total: false,
        valores: [...f.meses, f.total],
      })),
    };
    try {
      await bajarCuadros(`Planning_${vista}_${esc.year}`, [uno]);
    } catch (e) {
      alert(e instanceof Error ? e.message : "No se pudo generar el Excel");
    }
  }

  const esc = escenarios.find(x => x.id === scenarioId);

  /** ¿La versión tiene armado por tipo de habitación?
   *
   *  ⚠️ Un ACTUAL casi nunca lo tiene, y no es un fallo: sus tarifas y su
   *  ocupación no se presupuestan, se cargan. Medido en el ACTUAL Final 2026,
   *  las cuatro categorías dan cero en los doce meses —no hay `rate_cards` ni
   *  `occupancy_budgets`— y sus estadísticas reales viven a nivel propiedad
   *  (`scenario_stats`), no por categoría.
   *
   *  Una tabla de ceros se leería como «no hubo ocupación». Es distinto: el
   *  dato existe, en otro corte. */
  const sinArmado = useMemo(() => {
    if (!porTipo) return false;
    return !porTipo.months.some(m => m.rows.some(
      r => Number(r.nights_occupied || 0) || Number(r.revenue || 0)));
  }, [porTipo]);

  const faltaDato = (vista === "rack" && !rack)
    || (vista === "canales" && !canales)
    || (!["rack", "canales"].includes(vista) && !porTipo);

  return (
    <div className="pag pag-ancha" style={{ padding: "18px 22px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10,
                    flexWrap: "wrap", marginBottom: 10 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Armado de ingresos</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
                style={SEL}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
          ))}
        </select>
        <button onClick={bajarExcel}
          title="La vista que se está viendo, a Excel"
          style={{ ...SEL, cursor: "pointer", fontWeight: 600,
                   background: "var(--accent-excel)", color: "#fff",
                   border: "none" }}>⬇ Excel</button>
        {cargando && (
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>cargando…</span>
        )}
        {error && <span style={{ fontSize: 12, color: "var(--negative)" }}>{error}</span>}
      </div>

      <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                  marginBottom: 12, maxWidth: 920, lineHeight: 1.6 }}>
        El armado de ingresos de Planning, <b>sólo para consultar</b>. Si la
        versión tiene estadísticas <b>reales</b> cargadas —un actual— se muestran
        ésas; si no, lo que se deriva de los drivers. Esa decisión la toma el
        motor, no esta pantalla.
      </p>

      {/* Los ocho, como sub-tabs de segundo nivel — igual que en Checkbooks. */}
      <div style={{ display: "flex", gap: 2, alignItems: "flex-end",
                    flexWrap: "wrap", marginBottom: 14,
                    borderBottom: "1px solid var(--border-medium)" }}>
        {VISTAS.map(v => (
          <button key={v.key} onClick={() => setVista(v.key)} style={{
            padding: "7px 14px", fontSize: 12.5, cursor: "pointer",
            fontWeight: vista === v.key ? 700 : 500,
            background: "transparent", border: "none",
            borderBottom: vista === v.key
              ? "2px solid var(--brand)" : "2px solid transparent",
            color: vista === v.key ? "var(--brand)" : "var(--text-secondary)",
            marginBottom: -1,
          }}>{v.rotulo}</button>
        ))}
      </div>

      {/* ⚠️ Un forecast vivo muestra acá sus DRIVERS, no el resultado mezclado.
          Owner ya lo preguntó para los checkbooks; acá la respuesta es otra y
          conviene decirla: esto es el armado —tarifa × ocupación—, y en los
          meses cerrados el P&L usa las estadísticas cargadas, que pueden no
          coincidir con lo que se presupuestó. */}
      {esc?.type === "FORECAST" && (esc.actuals_through ?? 0) > 0 && (
        <p style={{ fontSize: 11.5, marginBottom: 12, padding: "8px 12px",
                    borderRadius: 7, lineHeight: 1.6, maxWidth: 920,
                    border: "1px solid var(--border)",
                    borderLeft: "4px solid var(--brand)",
                    color: "var(--text-secondary)" }}>
          Este forecast tiene actuales hasta el mes <b>{esc.actuals_through}</b>.
          Lo que se ve acá es el <b>armado</b> —tarifa × ocupación por
          categoría—, o sea lo que se proyectó. En los meses ya cerrados el
          P&amp;L usa las <b>estadísticas cargadas</b>, así que pueden no
          coincidir: una cosa es lo que se presupuestó y otra lo que pasó.
        </p>
      )}

      {sinArmado && !cargando && !["rack", "canales"].includes(vista) ? (
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)",
                    maxWidth: 860, lineHeight: 1.6 }}>
          Esta versión <b>no tiene armado por categoría de habitación</b>: no
          hay tarifas ni ocupación cargadas por tipo. No es que la ocupación
          haya sido cero — es que sus estadísticas viven a nivel de la
          propiedad, no por categoría. Se ven en el P&amp;L del cierre, en la
          franja de estadísticas.
        </p>
      ) : faltaDato && !cargando ? (
        <p style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
          Esta versión no tiene cargado el armado de ingresos para esta vista.
        </p>
      ) : (
        <div className="fin-scroll-x">
          <table style={{ borderCollapse: "collapse", minWidth: 900 }}>
            <thead>
              <tr>
                <th style={{ ...TDL, textAlign: "left", fontWeight: 800,
                             minWidth: 230, position: "static",
                             borderBottom: "2px solid var(--text-primary)" }}>
                  {vista === "canales" ? "Canal" : "Tipo de habitación"}
                </th>
                {MESES.map(m => (
                  <th key={m} style={{ ...TD, fontWeight: 700, minWidth: 78,
                                       position: "static",
                                       borderBottom: "2px solid var(--text-primary)" }}>
                    {m}
                  </th>
                ))}
                <th style={{ ...TD, fontWeight: 800, minWidth: 96,
                             position: "static",
                             borderLeft: "2px solid var(--border-medium)",
                             borderBottom: "2px solid var(--text-primary)" }}>
                  {sumable ? "Total" : "Año"}
                </th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f, i) => (
                <tr key={`${f.label}-${i}`}>
                  <td style={TDL}>{f.label}</td>
                  {f.meses.map((v, j) => (
                    <td key={j} className="mono" style={TD}>{escribir(v)}</td>
                  ))}
                  <td className="mono" style={{
                    ...TD, fontWeight: 700,
                    borderLeft: "2px solid var(--border-medium)",
                  }}>
                    {f.total === null ? "—" : escribir(f.total)}
                  </td>
                </tr>
              ))}
              {sumable && filas.length > 1 && (
                <tr style={{ background: "var(--bg-elevated, #EDF1F5)" }}>
                  <td style={{ ...TDL, fontWeight: 800,
                               borderTop: "2px solid var(--text-primary)" }}>
                    TOTAL
                  </td>
                  {MESES.map((_, i) => (
                    <td key={i} className="mono" style={{
                      ...TD, fontWeight: 800,
                      borderTop: "2px solid var(--text-primary)",
                    }}>{escribir(totalMes(i))}</td>
                  ))}
                  <td className="mono" style={{
                    ...TD, fontWeight: 800,
                    borderTop: "2px solid var(--text-primary)",
                    borderLeft: "2px solid var(--border-medium)",
                  }}>
                    {escribir(filas.reduce((a, f) => a + (f.total ?? 0), 0))}
                  </td>
                </tr>
              )}
              {!filas.length && !cargando && (
                <tr><td colSpan={14} style={{ ...TDL, color: "var(--text-secondary)" }}>
                  Sin datos para esta vista.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {!sumable && filas.length > 0 && (
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)",
                    marginTop: 10, maxWidth: 860, lineHeight: 1.55 }}>
          ⚠️ Esta vista muestra <b>razones</b> —porcentajes o tarifas—, así que
          la columna del año NO es una suma: la ocupación es noches ocupadas
          sobre disponibles del año, y el net rate es ingreso sobre noches
          ocupadas. Sumar doce porcentajes daría un número que no es de nadie.
        </p>
      )}
    </div>
  );
}
