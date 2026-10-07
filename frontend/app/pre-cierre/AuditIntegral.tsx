"use client";
/**
 * AUDIT INTEGRAL — el mes real a máximo detalle, depurado, contra Budget y Forecast.
 *
 * Owner, 2026-10-07: *«aprovechando que hay máximo detalle en las cuentas de
 * resultados por cuenta, se pueda generar un tipo de revisión versus budget o
 * forecast a máximo detalle por departamento y categorías de cuentas, a decir
 * ingresos, costos, planilla, opex, gastos dueños. Se limpia la subida y se
 * compara con el budget y forecast, y así se puede revisar rápido […] si hay
 * algo que no debería estar ahí, a máximo detalle, sólo copio y mando la nota
 * para que reclasifiquen»*.
 *
 * ## De dónde sale cada columna
 *
 * El **Actual** sale del mayor guardado —el Balance de Comprobación que se sube
 * en la Auditoría— y no del Pre-Cierre, porque el Pre-Cierre llega a la cuenta
 * y se acaba: lo que hace falta acá es poder bajar al asiento para mandar la
 * nota. El **Budget** y el **Forecast** salen por el mismo camino que usa el
 * motor del P&L, para comparar contra lo que el sistema reporta.
 *
 * ⚠️ **Esto no cambia de dónde sale la plata del cierre.** El P&L sigue
 * saliendo del Pre-Cierre; esto es una lupa que compara. Verificado contra la
 * pantalla de setiembre 2026: Rooms 20.259,00 contra 20.258,87, A&B 7.448,63
 * contra 7.447,27 — las diferencias son centavos del tipo de cambio por asiento.
 *
 * ## «Depurado»
 *
 * Del mayor entran sólo las clases 4 a 8 —el estado de resultados—. El balance
 * y las estadísticas quedan fuera: no se comparan contra un presupuesto.
 */
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { api, getScenarios, type Scenario } from "@/lib/api";
import { HOTEL_ID } from "@/lib/hotel";
import { useEscenarioDe } from "@/lib/escenarioPreferido";

interface FilaIntegral {
  grupo: string; dept_code: string; dept_name: string;
  cuenta: string; nombre: string;
  actual: number; lineas: number;
  versiones: Record<string, number>;
}

interface Asiento {
  cuenta: string; seg2: string; seg3: string;
  asiento: string; linea: string; fecha: string;
  descripcion: string; desc_asiento: string;
  origen: string; referencia: string; num_doc: string;
  monto: number; moneda: string; tc: number;
}

interface Asientos {
  dept: string; cuenta: string; asientos: number; total: number;
  recortado: boolean; filas: Asiento[];
}

interface Integral {
  anio: number; mes: number; hay: boolean; motivo?: string;
  archivo?: string; moneda?: string; subido_en?: string | null;
  orden_grupos?: string[];
  versiones?: { scenario_id: string; escenario: string }[];
  filas?: FilaIntegral[];
}

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
        { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

const MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"];

export default function AuditIntegral({ anio, mes }: { anio: number; mes: number }) {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  // La regla COMPARTIDA, no una propia: cada pantalla traía su «el año más
  // nuevo» copiado a mano y el día que nacieron los Working 2028-2035 todos los
  // reportes se fueron a 2035 sin que nada fallara.
  const [budget, setBudget] = useEscenarioDe(
    "pre-cierre/integral:budget", escenarios, "budget");
  const [forecast, setForecast] = useEscenarioDe(
    "pre-cierre/integral:forecast", escenarios, "forecast");
  const [datos, setDatos] = useState<Integral | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  /** Esconde las cuentas donde el actual y las versiones coinciden. Un mes
   *  tiene ~200 cuentas y lo que se revisa son las que NO cuadran. */
  const [soloDiferencias, setSoloDiferencias] = useState(false);
  const [copiado, setCopiado] = useState("");
  /** Qué cuentas están abiertas, y sus asientos ya traídos.
   *
   *  Owner, 2026-10-07: *«favor dar la opción para que me abra los asientos,
   *  expand, y ver el detalle ahí mismo»* · *«por cuenta»*.
   *
   *  Se piden al abrir y se guardan: cerrar y volver a abrir no vuelve a
   *  consultar. Un mes tiene ~285 cuentas y traerlas todas por adelantado
   *  serian miles de asientos que nadie va a mirar. */
  const [abiertas, setAbiertas] = useState<Record<string, Asientos | "cargando">>({});

  const abrir = useCallback(async (f: FilaIntegral) => {
    const k = f.dept_code + "|" + f.cuenta;
    if (abiertas[k]) {                      // ya está abierta: se cierra
      setAbiertas(a => { const b = { ...a }; delete b[k]; return b; });
      return;
    }
    setAbiertas(a => ({ ...a, [k]: "cargando" }));
    try {
      const r = await api.get<Asientos>(
        `/mayor/${anio}/${mes}/integral/asientos/`
        + `?dept=${encodeURIComponent(f.dept_code)}&cuenta=${encodeURIComponent(f.cuenta)}`);
      setAbiertas(a => ({ ...a, [k]: r }));
    } catch {
      setAbiertas(a => { const b = { ...a }; delete b[k]; return b; });
    }
  }, [abiertas, anio, mes]);

  useEffect(() => {
    getScenarios(HOTEL_ID).then(setEscenarios).catch(() => {});
  }, []);

  const ids = useMemo(
    () => [budget, forecast].filter(Boolean), [budget, forecast]);

  const cargar = useCallback(async () => {
    setCargando(true); setError("");
    try {
      setDatos(await api.get<Integral>(
        `/mayor/${anio}/${mes}/integral/?scenarios=${encodeURIComponent(ids.join(","))}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
      setDatos(null);
    } finally { setCargando(false); }
  }, [anio, mes, ids]);

  useEffect(() => { cargar(); }, [cargar]);

  /** La línea lista para pegar en el correo de reclasificación. Owner: «sólo
   *  copio y mando la nota para que reclasifiquen». */
  const copiar = async (f: FilaIntegral) => {
    const v = (datos?.versiones ?? [])
      .map(x => `${x.escenario} ${usd(f.versiones[x.scenario_id] ?? 0)}`)
      .join(" · ");
    const texto = `${MESES[mes - 1]} ${anio} · ${f.dept_code} ${f.dept_name}`
      + ` · ${f.cuenta} ${f.nombre} · Actual ${usd(f.actual)}`
      + ` (${f.lineas} ${f.lineas === 1 ? "asiento" : "asientos"})`
      + (v ? ` · ${v}` : "");
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(f.dept_code + f.cuenta);
      setTimeout(() => setCopiado(""), 1500);
    } catch { /* sin portapapeles no se rompe nada */ }
  };

  const th: React.CSSProperties = {
    textAlign: "left", fontSize: 11, fontWeight: 700, padding: "6px 8px",
    borderBottom: "1px solid var(--border-medium)", whiteSpace: "nowrap",
  };
  const td: React.CSSProperties = {
    fontSize: 12, padding: "4px 8px", borderBottom: "1px solid var(--border-subtle)",
  };
  const num: React.CSSProperties = {
    ...td, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
  };

  const vers = datos?.versiones ?? [];
  const visibles = (datos?.filas ?? []).filter(f => !soloDiferencias
    || vers.some(v => Math.abs(f.actual - (f.versiones[v.scenario_id] ?? 0)) > 0.005));

  // Por categoría y, dentro, por departamento. El servidor ya los manda
  // ordenados; acá sólo se arman los cortes.
  const bloques = useMemo(() => {
    const out: { grupo: string; depts: { code: string; name: string; filas: FilaIntegral[] }[] }[] = [];
    for (const f of visibles) {
      let g = out.find(x => x.grupo === f.grupo);
      if (!g) { g = { grupo: f.grupo, depts: [] }; out.push(g); }
      let d = g.depts.find(x => x.code === f.dept_code);
      if (!d) { d = { code: f.dept_code, name: f.dept_name, filas: [] }; g.depts.push(d); }
      d.filas.push(f);
    }
    return out;
  }, [visibles]);

  const suma = (fs: FilaIntegral[], sid?: string) =>
    fs.reduce((s, f) => s + (sid ? (f.versiones[sid] ?? 0) : f.actual), 0);

  if (cargando) return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</p>;
  if (error) return <p style={{ fontSize: 13, color: "var(--negative)" }}>{error}</p>;
  if (datos && !datos.hay) {
    return (
      <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
        {MESES[mes - 1]} {anio} todavía no está subido. Subí el Balance de
        Comprobación en <b>Auditoría del mayor</b> y volvé.
      </p>
    );
  }

  const rot = (s: Scenario) => `${s.type} ${s.version} ${s.year}`;

  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 10px" }}>
        El mes real a máximo detalle —del mayor, clases 4 a 8— contra el Budget y
        el Forecast, por categoría, departamento y cuenta. El botón{" "}
        <b>copiar</b> de cada línea la deja lista para pegar en la nota de
        reclasificación.
        {datos?.archivo && (
          <> Del archivo <b>{datos.archivo}</b> ({datos.moneda}).</>
        )}
      </p>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap",
                    alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Comparar contra</span>
        {([[budget, setBudget], [forecast, setForecast]] as const).map(([val, set], i) => (
          <select key={i} value={val} onChange={e => set(e.target.value)}
                  style={{ fontSize: 12, padding: "4px 8px", borderRadius: 5 }}>
            <option value="">— sin comparar —</option>
            {escenarios.map(s => (
              <option key={s.id} value={s.id}>{rot(s)}</option>
            ))}
          </select>
        ))}
        <label style={{ fontSize: 12, display: "flex", gap: 5, alignItems: "center",
                        cursor: "pointer" }}>
          <input type="checkbox" checked={soloDiferencias}
                 onChange={e => setSoloDiferencias(e.target.checked)} />
          Sólo lo que no cuadra
        </label>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {visibles.length} de {(datos?.filas ?? []).length} cuentas
        </span>
      </div>

      <div className="fin-scroll-x">
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={th}>Cuenta</th>
            <th style={th}>Nombre</th>
            <th style={{ ...th, textAlign: "right" }}>Asientos</th>
            <th style={{ ...th, textAlign: "right" }}>Actual</th>
            {vers.map(v => (
              <th key={v.scenario_id} style={{ ...th, textAlign: "right" }}>
                {v.escenario}
              </th>
            ))}
            {vers.map(v => (
              <th key={"d" + v.scenario_id} style={{ ...th, textAlign: "right" }}>
                Var vs {v.escenario.split(" ")[0]}
              </th>
            ))}
            <th style={th}></th>
          </tr></thead>
          <tbody>
            {bloques.map(g => (
              <Fragment key={g.grupo}>
                <tr>
                  <td colSpan={4 + vers.length * 2 + 1}
                      style={{ ...td, fontWeight: 800, fontSize: 12.5,
                               background: "var(--bg-header)", color: "#fff",
                               textTransform: "uppercase", letterSpacing: .4 }}>
                    {g.grupo}
                  </td>
                </tr>
                {g.depts.map(d => (
                  <Fragment key={d.code}>
                    <tr>
                      <td colSpan={3} style={{ ...td, fontWeight: 700,
                                               background: "var(--bg-elevated)" }}>
                        {d.code} · {d.name}
                      </td>
                      <td style={{ ...num, fontWeight: 700, background: "var(--bg-elevated)" }}>
                        {usd(suma(d.filas))}
                      </td>
                      {vers.map(v => (
                        <td key={v.scenario_id}
                            style={{ ...num, fontWeight: 700, background: "var(--bg-elevated)" }}>
                          {usd(suma(d.filas, v.scenario_id))}
                        </td>
                      ))}
                      {vers.map(v => (
                        <td key={"d" + v.scenario_id}
                            style={{ ...num, fontWeight: 700, background: "var(--bg-elevated)" }}>
                          {usd(suma(d.filas) - suma(d.filas, v.scenario_id))}
                        </td>
                      ))}
                      <td style={{ ...td, background: "var(--bg-elevated)" }} />
                    </tr>
                    {d.filas.map(f => (
                    <Fragment key={f.dept_code + f.cuenta}>
                      <tr>
                        <td style={{ ...td, paddingLeft: 22, whiteSpace: "nowrap" }}>
                          {f.cuenta}
                        </td>
                        <td style={td}>{f.nombre}</td>
                        <td style={num}>
                          {f.lineas ? (
                            // El número de asientos ES el botón: es lo que el
                            // ojo ya estaba mirando para decidir si vale la pena
                            // abrir la cuenta.
                            <button onClick={() => abrir(f)}
                                    title="Ver los asientos de esta cuenta"
                                    style={{ fontSize: 12, padding: "1px 7px",
                                             borderRadius: 4, cursor: "pointer",
                                             border: "1px solid var(--border-medium)",
                                             background: abiertas[f.dept_code + "|" + f.cuenta]
                                               ? "var(--bg-elevated)" : "transparent",
                                             color: "var(--text-primary)",
                                             fontVariantNumeric: "tabular-nums" }}>
                              {abiertas[f.dept_code + "|" + f.cuenta] ? "▾" : "▸"} {f.lineas}
                            </button>
                          ) : "—"}
                        </td>
                        <td style={num}>{usd(f.actual)}</td>
                        {vers.map(v => (
                          <td key={v.scenario_id} style={num}>
                            {usd(f.versiones[v.scenario_id] ?? 0)}
                          </td>
                        ))}
                        {vers.map(v => {
                          const dif = f.actual - (f.versiones[v.scenario_id] ?? 0);
                          return (
                            <td key={"d" + v.scenario_id}
                                style={{ ...num, fontWeight: Math.abs(dif) > 0.005 ? 700 : 400,
                                         color: Math.abs(dif) <= 0.005 ? "var(--text-secondary)"
                                           : dif < 0 ? "var(--negative)" : "var(--positive)" }}>
                              {usd(dif)}
                            </td>
                          );
                        })}
                        <td style={td}>
                          <button onClick={() => copiar(f)} title="Copiar para la nota"
                                  style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4,
                                           cursor: "pointer", border: "1px solid var(--border-medium)",
                                           background: "transparent",
                                           color: copiado === f.dept_code + f.cuenta
                                             ? "var(--positive)" : "var(--text-secondary)" }}>
                            {copiado === f.dept_code + f.cuenta ? "copiado" : "copiar"}
                          </button>
                        </td>
                      </tr>
                      {/* Los asientos de ESA cuenta, debajo de su fila. */}
                      {abiertas[f.dept_code + "|" + f.cuenta] && (
                        <tr>
                          <td colSpan={5 + vers.length * 2}
                              style={{ padding: "0 0 10px 34px",
                                       background: "var(--bg-base)" }}>
                            <Asientitos d={abiertas[f.dept_code + "|" + f.cuenta]}
                                        actual={f.actual} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                    ))}
                  </Fragment>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {visibles.length === 0 && (
        <p style={{ fontSize: 13, color: "var(--positive)", marginTop: 10 }}>
          {soloDiferencias
            ? "Todas las cuentas cuadran contra las versiones elegidas."
            : "No hay cuentas en este mes."}
        </p>
      )}
    </div>
  );
}


/** Los asientos de una cuenta, con su cuadre contra la fila que se abrio.
 *
 * ⚠️ Se muestra el total que manda el SERVIDOR y, al lado, el de la fila. Si
 * no coincidieran se dice: un detalle que no suma su total es el defecto mas
 * caro de un cuadro contable — se ve bien y no dice la verdad.
 */
function Asientitos(
  { d, actual }: { d: Asientos | "cargando"; actual: number },
) {
  if (d === "cargando") {
    return <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Cargando asientos…</span>;
  }
  const cuadra = Math.abs(d.total - actual) < 0.01;
  const th: React.CSSProperties = {
    textAlign: "left", fontSize: 10.5, fontWeight: 700, padding: "4px 6px",
    color: "var(--text-secondary)", whiteSpace: "nowrap",
  };
  const td: React.CSSProperties = { fontSize: 11.5, padding: "3px 6px" };
  const num: React.CSSProperties = {
    ...td, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
  };
  return (
    <div>
      <div style={{ fontSize: 11.5, color: "var(--text-secondary)", margin: "6px 0 4px" }}>
        {d.asientos} {d.asientos === 1 ? "asiento" : "asientos"} · suman{" "}
        <b style={{ color: cuadra ? "var(--text-primary)" : "var(--negative)" }}>
          {usd(d.total)}
        </b>
        {!cuadra && <> — y la fila dice {usd(actual)}. No cuadran.</>}
        {d.recortado && <> · se muestran los primeros {d.filas.length}.</>}
      </div>
      <table style={{ borderCollapse: "collapse" }}>
        <thead><tr>
          <th style={th}>Fecha</th>
          <th style={th}>Asiento</th>
          <th style={th}>Cuenta completa</th>
          <th style={th}>Descripción</th>
          <th style={th}>Descripción del asiento</th>
          <th style={th}>Origen</th>
          <th style={th}>Referencia</th>
          <th style={{ ...th, textAlign: "right" }}>Monto</th>
        </tr></thead>
        <tbody>
          {d.filas.map((x, i) => (
            <tr key={x.asiento + "-" + x.linea + "-" + i}>
              <td style={{ ...td, whiteSpace: "nowrap" }}>{x.fecha}</td>
              <td style={{ ...td, whiteSpace: "nowrap" }}>
                {x.asiento}<span style={{ color: "var(--text-secondary)" }}>·{x.linea}</span>
              </td>
              <td style={{ ...td, whiteSpace: "nowrap",
                           color: "var(--text-secondary)" }}>{x.cuenta}</td>
              <td style={td}>{x.descripcion}</td>
              <td style={{ ...td, color: "var(--text-secondary)" }}>{x.desc_asiento}</td>
              <td style={td}>{x.origen}</td>
              <td style={{ ...td, color: "var(--text-secondary)" }}>{x.referencia}</td>
              <td style={num}>{usd(x.monto)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
