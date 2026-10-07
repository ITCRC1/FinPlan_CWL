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

interface Detalle {
  detalle: string; nombre: string; actual: number; lineas: number;
}

interface FilaIntegral {
  grupo: string; dept_code: string; dept_name: string;
  cuenta: string; nombre: string;
  actual: number; lineas: number;
  versiones: Record<string, number>;
  /** El tercer segmento de la cuenta: en las 6 el puesto, en las 7 el detalle
   *  del gasto. Owner, 2026-10-07: *«e internamente por Detalle»*.
   *
   *  ⚠️ No traen comparacion a proposito: el presupuesto numera sus detalles
   *  por su cuenta, y apareados darian una correspondencia inventada. Lo que se
   *  compara es el total por CUENTA. Lo mismo hace `Opex by Detail`. */
  detalles: Detalle[];
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
  /** El departamento que se esta revisando, o "" por todos.
   *
   *  Owner, 2026-10-07: *«tengo cierto sentido de perdida... no se si se puede
   *  hacer por departamento, droplist y escoger e ir revisando»*. Un mes son
   *  ~195 cuentas y ~460 detalles seguidos: de a un departamento se revisa y se
   *  cierra, y se sabe por donde se va. */
  const [dept, setDept] = useState("");
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
  const descuadra = (f: FilaIntegral) =>
    vers.some(v => Math.abs(f.actual - (f.versiones[v.scenario_id] ?? 0)) > 0.005);
  const visibles = (datos?.filas ?? []).filter(
    f => (!soloDiferencias || descuadra(f)) && (!dept || f.dept_code === dept));

  /** Los departamentos del mes, con cuantas cuentas trae cada uno y si alguna
   *  descuadra — para no tener que entrar a mirar.
   *
   *  ⚠️ Se arma sobre TODAS las filas, no sobre `visibles`: si saliera del
   *  filtrado, elegir un departamento vaciaria el droplist y no habria como
   *  volver. */
  const depts = useMemo(() => {
    const out: { code: string; name: string; cuentas: number; ojo: number }[] = [];
    for (const f of datos?.filas ?? []) {
      let d = out.find(x => x.code === f.dept_code);
      if (!d) {
        d = { code: f.dept_code, name: f.dept_name, cuentas: 0, ojo: 0 };
        out.push(d);
      }
      d.cuentas += 1;
      if (descuadra(f)) d.ojo += 1;
    }
    return out;
  }, [datos, vers.length, soloDiferencias]);

  /** El nombre del departamento, sin repetir el codigo.
   *
   *  `dept_name` viene del catalogo de departamentos; cuando ese catalogo no
   *  tiene el departamento, el servidor devuelve el codigo como nombre y
   *  «0110 · 0110» no le dice nada a nadie. */
  const rotuloDept = (code: string, name: string) =>
    name && name !== code ? `${code} · ${name}` : code;

  const paso = (n: number) => {
    if (!depts.length) return;
    const i = depts.findIndex(x => x.code === dept);
    const j = i < 0 ? (n > 0 ? 0 : depts.length - 1)
                    : (i + n + depts.length) % depts.length;
    setDept(depts[j].code);
  };

  // ⚠️ DEPARTAMENTO afuera y la categoria adentro, en orden de clase: 4
  // Ingresos, 5 Costos, 6 Payroll, 7 Opex, 8 Property Expenses. Owner,
  // 2026-10-07: *«la regla de orden es Departamento, si es 4-Ingresos,
  // 5-Costos, 6-Payroll, 7-Opex, 8-Property Expenses; e internamente por
  // Detalle»*.
  //
  // El servidor ya los manda en ese orden; aca solo se arman los cortes.
  const bloques = useMemo(() => {
    const out: { code: string; name: string;
                 grupos: { grupo: string; filas: FilaIntegral[] }[] }[] = [];
    for (const f of visibles) {
      let d = out.find(x => x.code === f.dept_code);
      if (!d) { d = { code: f.dept_code, name: f.dept_name, grupos: [] }; out.push(d); }
      let g = d.grupos.find(x => x.grupo === f.grupo);
      if (!g) { g = { grupo: f.grupo, filas: [] }; d.grupos.push(g); }
      g.filas.push(f);
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
        el Forecast, por <b>departamento</b> y, dentro, por categoría, cuenta y
        detalle. Elegí un departamento abajo para revisarlo solo. El número de{" "}
        <b>asientos</b> abre la cuenta ahí mismo, y <b>copiar</b> deja la línea
        lista para pegar en la nota de reclasificación.
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

        {/* El departamento, para revisar de a uno. El contador de al lado dice
            cuántas cuentas trae y, entre paréntesis, cuántas no cuadran. */}
        <span style={{ fontSize: 12, color: "var(--text-secondary)",
                       marginLeft: 6 }}>Departamento</span>
        <select value={dept} onChange={e => setDept(e.target.value)}
                style={{ fontSize: 12, padding: "4px 8px", borderRadius: 5,
                         maxWidth: 260 }}>
          <option value="">
            Todos — {(datos?.filas ?? []).length} cuentas
          </option>
          {depts.map(d => (
            <option key={d.code} value={d.code}>
              {rotuloDept(d.code, d.name)} — {d.cuentas}
              {d.ojo ? ` (${d.ojo} no cuadran)` : ""}
            </option>
          ))}
        </select>
        <span style={{ display: "inline-flex", gap: 2 }}>
          {([["‹", -1], ["›", 1]] as const).map(([txt, n]) => (
            <button key={n} onClick={() => paso(n)} disabled={!depts.length}
                    title={n < 0 ? "Departamento anterior" : "Departamento siguiente"}
                    style={{ fontSize: 14, lineHeight: 1, padding: "3px 9px",
                             borderRadius: 5, cursor: "pointer",
                             border: "1px solid var(--border-medium)",
                             background: "transparent",
                             color: "var(--text-primary)" }}>{txt}</button>
          ))}
        </span>
        {dept && (
          <button onClick={() => setDept("")}
                  style={{ fontSize: 11, padding: "3px 9px", borderRadius: 5,
                           cursor: "pointer", border: "1px solid var(--border-medium)",
                           background: "transparent", color: "var(--text-secondary)" }}>
            ver todos
          </button>
        )}
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {visibles.length} de {(datos?.filas ?? []).length} cuentas
        </span>
      </div>

      <div className="fin-scroll-x">
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead><tr>
            <th style={th}>Cuenta · Detalle</th>
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
            {bloques.map(d => (
              <Fragment key={d.code}>
                {/* El DEPARTAMENTO, la banda fuerte.
                    ⚠️ Sin `color: #fff`. Lo tuvo, y en el tema claro
                    `--bg-header` es claro: la banda salia en BLANCO y el owner
                    veia una fila vacia donde deberia decir el departamento
                    (2026-10-07). El peso lo da el borde y la negrita, que se
                    ven igual en los dos temas. */}
                <tr>
                  <td colSpan={3}
                      style={{ ...td, fontWeight: 800, fontSize: 13,
                               background: "var(--bg-elevated)",
                               color: "var(--text-primary)",
                               borderTop: "2px solid var(--brand)" }}>
                    {rotuloDept(d.code, d.name)}
                  </td>
                  {[undefined, ...vers.map(v => v.scenario_id)].map((sid, n) => (
                    <td key={"t" + n}
                        style={{ ...num, fontWeight: 800,
                                 background: "var(--bg-elevated)",
                                 color: "var(--text-primary)",
                                 borderTop: "2px solid var(--brand)" }}>
                      {usd(d.grupos.reduce((a, g) => a + suma(g.filas, sid), 0))}
                    </td>
                  ))}
                  {vers.map(v => (
                    <td key={"d" + v.scenario_id}
                        style={{ ...num, fontWeight: 800,
                                 background: "var(--bg-elevated)",
                                 color: "var(--text-primary)",
                                 borderTop: "2px solid var(--brand)" }}>
                      {usd(d.grupos.reduce(
                        (a, g) => a + suma(g.filas) - suma(g.filas, v.scenario_id), 0))}
                    </td>
                  ))}
                  <td style={{ ...td, background: "var(--bg-elevated)",
                               borderTop: "2px solid var(--brand)" }} />
                </tr>
                {d.grupos.map(g => (
                  <Fragment key={g.grupo}>
                    {/* La categoria, dentro del departamento — un escalon
                        mas suave, que para eso esta debajo. */}
                    <tr>
                      <td colSpan={3} style={{ ...td, fontWeight: 700,
                                               background: "var(--bg-surface)" }}>
                        {g.grupo}
                      </td>
                      {[undefined, ...vers.map(v => v.scenario_id)].map((sid, n) => (
                        <td key={"t" + n}
                            style={{ ...num, fontWeight: 700,
                                     background: "var(--bg-surface)" }}>
                          {usd(suma(g.filas, sid))}
                        </td>
                      ))}
                      {vers.map(v => (
                        <td key={"d" + v.scenario_id}
                            style={{ ...num, fontWeight: 700,
                                     background: "var(--bg-surface)" }}>
                          {usd(suma(g.filas) - suma(g.filas, v.scenario_id))}
                        </td>
                      ))}
                      <td style={{ ...td, background: "var(--bg-surface)" }} />
                    </tr>
                    {g.filas.map(f => (
                    <Fragment key={f.dept_code + f.cuenta}>
                      <tr>
                        <td style={{ ...td, paddingLeft: 22, whiteSpace: "nowrap",
                                     fontWeight: 600 }}>
                          {f.cuenta}
                        </td>
                        <td style={{ ...td, fontWeight: 600 }}>{f.nombre}</td>
                        <td style={num}>
                          {f.lineas ? (
                            <button onClick={() => abrir(f)}
                                    title="Ver los asientos de esta cuenta"
                                    style={{ fontSize: 12, padding: "1px 7px",
                                             borderRadius: 4, cursor: "pointer",
                                             border: "1px solid var(--border-medium)",
                                             background: abiertas[f.dept_code + "|" + f.cuenta]
                                               ? "var(--bg-elevated)" : "transparent",
                                             color: "var(--text-primary)",
                                             fontVariantNumeric: "tabular-nums" }}>
                              {abiertas[f.dept_code + "|" + f.cuenta] ? "\u25be" : "\u25b8"} {f.lineas}
                            </button>
                          ) : "\u2014"}
                        </td>
                        <td style={{ ...num, fontWeight: 600 }}>{usd(f.actual)}</td>
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
                      {/* El DETALLE de la cuenta — el tercer segmento. Sin
                          comparacion a proposito: ver el tipo `Detalle`. */}
                      {f.detalles.length > 1 && f.detalles.map(x => (
                        <tr key={f.cuenta + "d" + x.detalle}>
                          <td style={{ ...td, paddingLeft: 46, whiteSpace: "nowrap",
                                       color: "var(--text-secondary)" }}>
                            {x.detalle || "\u2014"}
                          </td>
                          <td style={{ ...td, color: "var(--text-secondary)" }}>{x.nombre}</td>
                          <td style={{ ...num, color: "var(--text-secondary)" }}>{x.lineas}</td>
                          <td style={{ ...num, color: "var(--text-secondary)" }}>
                            {usd(x.actual)}
                          </td>
                          {vers.map(v => <td key={v.scenario_id} style={num} />)}
                          {vers.map(v => <td key={"d" + v.scenario_id} style={num} />)}
                          <td style={td} />
                        </tr>
                      ))}
                      {abiertas[f.dept_code + "|" + f.cuenta] && (
                        <tr>
                          <td colSpan={5 + vers.length * 2}
                              style={{ padding: "0 0 10px 34px", background: "var(--bg-base)" }}>
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
