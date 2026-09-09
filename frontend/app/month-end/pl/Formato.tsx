"use client";
/**
 * El P&L en el formato del owner: la cascada completa, un mes por columna.
 *
 * Owner, 2026-09-02, entregando `julio FORMAT 2026.xlsx`: *«uno para ver el
 * detalle tal cual el formato»*.
 *
 * **Qué lo distingue de los cuadros que ya existían.**
 *
 * | | qué compara | qué muestra |
 * |---|---|---|
 * | `12 meses` | una versión | 17 líneas de resumen |
 * | `P&L Detail Full` | hasta 4 versiones | la cascada, en UN corte |
 * | **este** | una versión | **la cascada, mes a mes** |
 *
 * Es el cuadro que el owner arma a mano cada cierre: marzo a julio uno al lado
 * del otro, con todos los renglones. Los otros dos no lo dan — el primero
 * pierde el detalle y el segundo pierde los meses.
 *
 * ## Por qué sale de `/pl-detail/` y no de `/doce-meses/`
 *
 * ⚠️ **Hay DOS vocabularios de códigos de línea y se ven iguales.**
 * `calculate_full_pl` emite `OPEXP_ROOMS`, `OVH_ADMIN`, `MGMT_FEE`; el camino
 * DB-driven —el que corre en producción para los actuales— emite `OPEX_ROOMS`,
 * `OH_ADMIN`, `MGMT_FEE_3`. Los **totales** coinciden por `add_pl_aliases`.
 *
 * Este cuadro se escribió primero contra el vocabulario del motor y, cotejado
 * contra el libro de julio del owner, **cerró perfecto en todos los totales y
 * mostró el detalle entero en cero**: `TOTAL_OVERHEAD` daba 47.853,67 y las
 * ocho líneas que lo componen, «—». Un cuadro que cuadra y no dice nada.
 *
 * La lección es que la plantilla no se escribe dos veces. `/pl-detail/` ya
 * devuelve **los doce meses de cada fila** con la plantilla que el owner
 * aprobó —sus rótulos, su orden y hasta sus erratas—, así que acá sólo se
 * cambia la forma de leerla: en vez de un corte, una columna por mes.
 */
import { sembrarTres } from "@/lib/escenarioPreferido";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getPLDetail, getPLDoceMeses, getEstadisticasCierre,
         type EstadisticasCierre, type PLDetail, type PLDoceMeses,
         type Scenario } from "@/lib/api";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const numero = (n: number) =>
  n ? n.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—";
const pct = (n: number) => (n ? (n * 100).toFixed(2) + "%" : "—");

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

const TD: React.CSSProperties = {
  padding: "3px 9px", textAlign: "right", fontSize: 11.5, whiteSpace: "nowrap",
};

const SEL: React.CSSProperties = {
  padding: "5px 9px", fontSize: 12, borderRadius: 5,
  border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)",
};

/** Los tres ámbitos del reporte, tal como los pidió el owner el 2026-08-27. */
const AMBITOS = [
  { id: "consolidado", rotulo: "Consolidado" },
  { id: "hotel", rotulo: "Hotel" },
  { id: "club", rotulo: "Club Madresal" },
];

/** El escenario con el que abrir, para un papel.
 *
 *  ⚠️ Usa `sembrarTres` —la regla del owner— y NO `escenarios.find(...)`.
 *  Esa era la versión anterior, copiada en los cuatro sub-tabs: devolvía el
 *  PRIMERO de ese tipo, y `GET /scenarios/` ordena por año descendente, así
 *  que el primer BUDGET de la lista es el Working **2035**. Cada sub-tab abría
 *  en un presupuesto real, vacío y de otro año — sin que nada fallara. */
function primeroDe(escenarios: Scenario[], tipo: string): string {
  const tres = sembrarTres(escenarios);
  const id = tipo === "ACTUAL" ? tres.actual
    : tipo === "BUDGET" ? tres.budget
    : tipo === "FORECAST" ? tres.forecast : "";
  // El respaldo se queda: si NO hay ninguno de ese tipo, mejor mostrar algo
  // que un selector en blanco sin explicación.
  return id || escenarios.find(s => s.type === tipo)?.id || escenarios[0]?.id || "";
}

export default function Formato({ escenarios, inicial, compacto = true }: {
  escenarios: Scenario[];
  inicial?: string;
  /** Esconder las líneas en cero TODOS los meses. Lo manda la pantalla, así el
   *  interruptor es uno solo para todos los sub-tabs. */
  compacto?: boolean;
}) {
  const [scenarioId, setScenarioId] = useState("");
  const [ambito, setAmbito] = useState("consolidado");
  const [datos, setDatos] = useState<PLDetail | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Enseñar los doce meses aunque estén vacíos. Apagado por defecto: Amarena
   *  abrió en marzo y nueve columnas en cero no dejan leer las cinco que hay. */
  const [todosLosMeses, setTodosLosMeses] = useState(false);
  /** Las estadisticas mes a mes, para el encabezado del cuadro.
   *
   *  Owner, 2026-09-02: «necesito las estadisticas aca en este tab llamado
   *  formato; favor agrega como head del reporte». Van ARRIBA y con las mismas
   *  columnas que la cascada: son el denominador de todo lo que sigue. */
  const [kpis, setKpis] = useState<PLDoceMeses | null>(null);
  /** El acumulado. ⚠️ NO se suma acá: la ocupacion, el ADR y la cuota son
   *  razones y se rederivan con el numerador y el denominador del periodo. Lo
   *  hace `/pl/{id}/estadisticas/`, que es el mismo calculo del resto de la
   *  pantalla. */
  const [total, setTotal] = useState<EstadisticasCierre | null>(null);

  useEffect(() => {
    if (!escenarios.length) return;
    setScenarioId(x => x || inicial || primeroDe(escenarios, "ACTUAL"));
  }, [escenarios, inicial]);

  const cargar = useCallback(async () => {
    if (!scenarioId) return;
    setCargando(true); setError(null);
    try {
      setDatos(await getPLDetail(ambito, scenarioId, []));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el año");
      setDatos(null);
    } finally { setCargando(false); }
  }, [scenarioId, ambito]);

  useEffect(() => { cargar(); }, [cargar]);

  useEffect(() => {
    if (!scenarioId) { setKpis(null); return; }
    getPLDoceMeses(scenarioId).then(setKpis).catch(() => setKpis(null));
  }, [scenarioId]);

  /** Una sola versión: la que se eligió arriba. */
  const filas = useMemo(() => datos?.filas ?? [], [datos]);
  const serie = useCallback(
    (f: { series: (number[] | null)[] }) => f.series?.[0] ?? null, []);

  const valor = useCallback((f: { series: (number[] | null)[] }, i: number) => {
    const s = serie(f);
    return s ? (s[i] ?? 0) : 0;
  }, [serie]);

  /** Qué meses se dibujan.
   *
   *  Un mes cuenta como «con movimiento» si se movió alguno de los TOTALES —no
   *  si cualquier línea tiene algo—, porque el impuesto y la reserva arrastran
   *  ceros calculados los doce meses. */
  const columnas = useMemo(() => {
    const todos = Array.from({ length: 12 }, (_, i) => i);
    if (todosLosMeses) return todos;
    const marcadoras = filas.filter(f => f.tipo === "tot");
    const vivos = todos.filter(i =>
      marcadoras.some(f => Math.abs(valor(f, i)) >= 0.005));
    return vivos.length ? vivos : todos;
  }, [filas, valor, todosLosMeses]);

  useEffect(() => {
    if (!scenarioId || !columnas.length) { setTotal(null); return; }
    getEstadisticasCierre(scenarioId, columnas[0] + 1,
                          columnas[columnas.length - 1] + 1)
      .then(setTotal).catch(() => setTotal(null));
  }, [scenarioId, columnas]);

  /** Las filas del encabezado. `mes` saca el dato de UN mes; `acum` el del
   *  acumulado, que viene ya agregado del backend porque las razones no se
   *  suman. */
  const CABECERA: {
    rotulo: string;
    mes: (k: PLDoceMeses["meses"][number]["kpis"]) => string;
    acum: (t: EstadisticasCierre) => string;
    club?: boolean;
    fuerte?: boolean;
  }[] = [
    { rotulo: "Total available Rooms",
      mes: k => numero(k.rooms_available), acum: t => numero(t.rooms_available) },
    { rotulo: "Total Rooms Occupied",
      mes: k => numero(k.rooms_occupied), acum: t => numero(t.rooms_occupied) },
    { rotulo: "Total Guests",
      mes: k => numero(k.guests), acum: t => numero(t.guests) },
    { rotulo: "% Occupancy", fuerte: true,
      mes: k => pct(k.occupancy_pct), acum: t => pct(t.occupancy_pct) },
    { rotulo: "Average Daily Room Only", fuerte: true,
      mes: k => usd(k.adr), acum: t => usd(t.adr) },
    { rotulo: "Total RevPAR", fuerte: true,
      mes: k => usd(k.revpar), acum: t => usd(t.revpar) },
    // En la columna del mes es el mes; en el ACUMULADO es el promedio de los
    // meses con socios, no la suma (owner, 2026-09-02).
    { rotulo: "Socios pagando (Club)", club: true,
      mes: k => numero(k.club_pagando ?? 0),
      acum: t => `${numero(t.club_pagando ?? 0)} prom.` },
    { rotulo: "Cuota promedio por socio", club: true, fuerte: true,
      mes: k => usd(k.club_cuota_promedio ?? 0),
      acum: t => usd(t.club_cuota_promedio ?? 0) },
  ];

  const porMes = useMemo(() => {
    const out: Record<number, PLDoceMeses["meses"][number]["kpis"]> = {};
    for (const m of kpis?.meses ?? []) out[m.month - 1] = m.kpis;
    return out;
  }, [kpis]);
  const hayClub = (kpis?.meses ?? []).some(m => m.kpis.club_pagando !== undefined);

  /** Una línea está vacía si es cero en TODOS los meses dibujados.
   *
   *  ⚠️ Se esconde con `!some`, que es lo mismo que «cero en todos»: una línea
   *  que sólo tuvo saldo en junio TIENE que seguir viéndose. Esconder es para
   *  el ruido permanente, no para los huecos. */
  const visibles = useMemo(() => {
    if (!compacto) return filas;
    const paso1 = filas.filter(f =>
      f.tipo === "sec" || f.tipo === "esp"
      || columnas.some(i => Math.abs(valor(f, i)) >= 0.005));
    // Un encabezado cuyo detalle quedó todo escondido tampoco se dibuja: si no,
    // quedan rótulos sueltos sobre la nada.
    return paso1.filter((f, i) => {
      if (f.tipo !== "sec") return true;
      for (let j = i + 1; j < paso1.length; j++) {
        if (paso1[j].tipo === "sec") break;
        if (paso1[j].tipo !== "esp") return true;
      }
      return false;
    });
  }, [compacto, filas, columnas, valor]);

  const estilo = (tipo: string): React.CSSProperties =>
    tipo === "sec"
      ? { fontWeight: 800, fontSize: 12, textTransform: "uppercase",
          background: "var(--bg-surface)" }
      : tipo === "tot"
        ? { fontWeight: 800, borderTop: "1px solid var(--border-medium)" }
        : tipo === "sub" ? { fontWeight: 700 } : {};

  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "center",
                    flexWrap: "wrap", marginBottom: 12 }}>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          style={SEL}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
          ))}
        </select>
        <select value={ambito} onChange={e => setAmbito(e.target.value)} style={SEL}>
          {AMBITOS.map(a => <option key={a.id} value={a.id}>{a.rotulo}</option>)}
        </select>
        <button onClick={() => setTodosLosMeses(x => !x)}
          title="Amarena abrió en marzo: los meses sin movimiento se esconden para que quepan los que hay"
          style={{ ...SEL, cursor: "pointer", color: "var(--text-secondary)" }}>
          {todosLosMeses ? "☑ Los 12 meses" : "☐ Los 12 meses"}
        </button>
        {cargando && <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          cargando…
        </span>}
        {error && <span style={{ fontSize: 12, color: "var(--negative)" }}>{error}</span>}
      </div>

      <div className="fin-scroll-x">
        <table style={{ borderCollapse: "collapse", minWidth: 620 }}>
          <thead>
            <tr>
              <th style={{ ...TD, textAlign: "left", minWidth: 250 }}>
                Grupo / Cuenta
              </th>
              {columnas.map(i => (
                <th key={i} style={{ ...TD, fontWeight: 700, minWidth: 110 }}>
                  {MESES[i]} {datos?.year}
                </th>
              ))}
              <th style={{ ...TD, fontWeight: 800, minWidth: 118,
                           borderLeft: "2px solid var(--border-medium)" }}>
                Acumulado
              </th>
            </tr>
          </thead>
          <tbody>
            {/* ── El encabezado de estadisticas ─────────────────────────────
                Owner, 2026-09-02: «necesito las estadisticas aca en este tab
                llamado formato; favor agrega como head del reporte».

                Va DENTRO de la misma tabla y no en un cuadro aparte: asi las
                columnas quedan alineadas al milimetro con la cascada. Dos
                tablas una encima de otra se desalinean apenas un numero se
                hace mas ancho, y entonces hay que contar columnas con el dedo
                para saber que mes se esta mirando.

                ⚠️ El ACUMULADO no se suma aca. La ocupacion, el ADR y la cuota
                son razones: se rederivan con el numerador y el denominador del
                periodo, y eso lo hace `/pl/{id}/estadisticas/`. */}
            {kpis && CABECERA.filter(f => !f.club || hayClub).map(f => (
              <tr key={"kpi-" + f.rotulo} style={{ background: "var(--bg-surface)" }}>
                <td style={{ padding: "3px 10px", fontSize: 11.5,
                             color: "var(--text-secondary)" }}>
                  {f.rotulo}
                </td>
                {columnas.map(i => (
                  <td key={i} style={{ ...TD,
                                       fontWeight: f.fuerte ? 800 : 600 }}>
                    {porMes[i] ? f.mes(porMes[i]) : "—"}
                  </td>
                ))}
                <td style={{ ...TD, fontWeight: 800,
                             borderLeft: "2px solid var(--border-medium)" }}>
                  {total ? f.acum(total) : "—"}
                </td>
              </tr>
            ))}
            {kpis && (
              <tr><td colSpan={columnas.length + 2}
                      style={{ height: 10,
                               borderBottom: "2px solid var(--border-medium)" }} /></tr>
            )}

            {visibles.map((f, n) => f.tipo === "esp" ? (
              <tr key={n}><td colSpan={columnas.length + 2} style={{ height: 7 }} /></tr>
            ) : (
              <tr key={n} style={estilo(f.tipo)}>
                <td style={{ padding: "3px 10px", fontSize: 12,
                             paddingLeft: f.tipo === "det" ? 22 : 10 }}>
                  {f.rotulo}
                </td>
                {columnas.map(i => (
                  <td key={i} style={TD}>
                    {f.tipo === "sec" || !serie(f) ? "" : usd(valor(f, i))}
                  </td>
                ))}
                <td style={{ ...TD, fontWeight: 700,
                             borderLeft: "2px solid var(--border-medium)" }}>
                  {f.tipo === "sec" || !serie(f) ? ""
                    : usd(columnas.reduce((s, i) => s + valor(f, i), 0))}
                </td>
              </tr>
            ))}
            {!visibles.length && !cargando && (
              <tr><td colSpan={columnas.length + 2}
                      style={{ padding: 12, fontSize: 12,
                               color: "var(--text-secondary)" }}>
                Sin datos para esta versión.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <p style={{ fontSize: 11.5, color: "var(--text-secondary)",
                  marginTop: 12, maxWidth: 800, lineHeight: 1.6 }}>
        ⚠️ <b>El acumulado suma las columnas que se ven.</b> Con los meses sin
        movimiento escondidos da lo mismo —son cero—, pero si algún día se
        esconde un mes con saldo, la suma cambia con él y deja de ser el año.
      </p>
    </div>
  );
}
