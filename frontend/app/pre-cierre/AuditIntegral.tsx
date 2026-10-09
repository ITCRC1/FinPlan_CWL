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

import { api, getScenarios, usaliParaCuenta, type Scenario,
         type UsaliParaCuenta } from "@/lib/api";
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
  /** Los departamentos que se estan revisando. Vacio = todos.
   *
   *  Owner, 2026-10-07: *«tengo cierto sentido de perdida... no se si se puede
   *  hacer por departamento, droplist y escoger e ir revisando»* y, mirandolo
   *  otra vez: *«prefiero que haya una celda para escoger el departamento y
   *  revisar uno a uno si yo quiero... o seleccion multiple»*.
   *
   *  Las dos cosas: tocar el NOMBRE deja ese solo —el camino de «uno a uno»,
   *  un clic— y tocar la casilla lo suma o lo quita del conjunto. Un mes son
   *  ~285 cuentas seguidas; de a un departamento se revisa y se cierra. */
  const [depts, setDepts] = useState<string[]>([]);
  const [abrirDepts, setAbrirDepts] = useState(false);
  /** La cuenta cuya definicion del USALI se esta mirando, y cual es.
   *
   *  Owner, 2026-10-08, al pedirlo: *«ok, A»* — el estandar como capa de
   *  EXPLICACION y no de deteccion. No marca nada: muestra lo que el libro dice
   *  que incluye esa cuenta, para que el ojo decida mas rapido.
   *
   *  La LLAVE —`dept|cuenta`, la misma que `abiertas`— existe porque el panel
   *  sale pegado a su fila y no centrado en la pantalla. Owner, 2026-10-09:
   *  *«siempre esta arriba y a veces hay que subir mucho»*. */
  const [usali, setUsali] = useState<UsaliParaCuenta | "cargando" | null>(null);
  const [usaliDe, setUsaliDe] = useState("");

  const verUsali = useCallback(async (llave: string, nombre: string,
                                      dept: string) => {
    if (llave === usaliDe) {           // ya esta abierta: se cierra
      setUsaliDe(""); setUsali(null);
      return;
    }
    setUsaliDe(llave);
    setUsali("cargando");
    try {
      setUsali(await usaliParaCuenta(nombre, dept));
    } catch {
      // Se suelta tambien la llave: si queda puesta, el proximo click se lee
      // como «cerrar» y la cuenta no se puede reintentar.
      setUsali(null);
      setUsaliDe("");
    }
  }, [usaliDe]);

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
    f => (!soloDiferencias || descuadra(f))
      && (depts.length === 0 || depts.includes(f.dept_code)));

  /** Los departamentos del mes, con cuantas cuentas trae cada uno y si alguna
   *  descuadra — para no tener que entrar a mirar.
   *
   *  ⚠️ Se arma sobre TODAS las filas, no sobre `visibles`: si saliera del
   *  filtrado, elegir un departamento vaciaria el droplist y no habria como
   *  volver. */
  const catalogoDepts = useMemo(() => {
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

  /** El paso `‹ ›` mueve a UN departamento — es el modo «uno a uno».
   *
   *  Con varios elegidos arranca desde el ultimo, que es donde esta el ojo. */
  const paso = (n: number) => {
    const todos = catalogoDepts;
    if (!todos.length) return;
    const actual = depts[depts.length - 1];
    const i = todos.findIndex(x => x.code === actual);
    const j = i < 0 ? (n > 0 ? 0 : todos.length - 1)
                    : (i + n + todos.length) % todos.length;
    setDepts([todos[j].code]);
  };

  const soloEste = (code: string) => { setDepts([code]); setAbrirDepts(false); };
  const alternar = (code: string) => setDepts(
    d => d.includes(code) ? d.filter(x => x !== code) : [...d, code]);

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

        {/* El departamento. Owner, 2026-10-07: *«prefiero que haya una celda
            para escoger el departamento y revisar uno a uno si yo quiero... o
            selección múltiple»*.
            ⚠️ No es un `<select multiple>`: ese obliga a ctrl+clic para sumar
            uno, y soltar el ctrl borra la selección entera sin avisar. Acá el
            NOMBRE deja ese solo —un clic, el camino de «uno a uno»— y la
            CASILLA lo suma o lo quita. */}
        <span style={{ fontSize: 12, color: "var(--text-secondary)",
                       marginLeft: 6 }}>Departamento</span>
        <span style={{ position: "relative" }}>
          <button onClick={() => setAbrirDepts(v => !v)}
                  style={{ fontSize: 12, padding: "4px 10px", borderRadius: 5,
                           cursor: "pointer", minWidth: 190, textAlign: "left",
                           border: "1px solid var(--border-medium)",
                           background: "var(--bg-input)",
                           color: "var(--text-primary)" }}>
            {depts.length === 0
              ? `Todos — ${catalogoDepts.length}`
              : depts.length === 1
                ? rotuloDept(depts[0],
                    catalogoDepts.find(x => x.code === depts[0])?.name ?? "")
                : `${depts.length} departamentos`}
            {" ▾"}
          </button>
          {abrirDepts && (
            <>
              {/* La capa que cierra el panel al tocar afuera. */}
              <span onClick={() => setAbrirDepts(false)}
                    style={{ position: "fixed", inset: 0, zIndex: 40 }} />
              <div style={{ position: "absolute", top: "calc(100% + 4px)", left: 0,
                            zIndex: 41, minWidth: 300, maxHeight: 340,
                            overflowY: "auto", padding: "4px 0",
                            borderRadius: 6, border: "1px solid var(--border-medium)",
                            background: "var(--bg-surface)",
                            boxShadow: "0 8px 24px rgba(0,0,0,0.35)" }}>
                <button onClick={() => { setDepts([]); setAbrirDepts(false); }}
                        style={{ display: "block", width: "100%", textAlign: "left",
                                 fontSize: 12, padding: "6px 12px", cursor: "pointer",
                                 border: "none", background: "transparent",
                                 fontWeight: depts.length === 0 ? 700 : 400,
                                 color: "var(--text-primary)" }}>
                  Todos los departamentos — {(datos?.filas ?? []).length} cuentas
                </button>
                <div style={{ height: 1, background: "var(--border-subtle)",
                              margin: "4px 0" }} />
                {catalogoDepts.map(d => {
                  const puesto = depts.includes(d.code);
                  return (
                    <div key={d.code}
                         style={{ display: "flex", alignItems: "center", gap: 8,
                                  padding: "4px 12px",
                                  background: puesto ? "var(--bg-elevated)" : "transparent" }}>
                      <input type="checkbox" checked={puesto}
                             onChange={() => alternar(d.code)}
                             title="Sumar o quitar este departamento"
                             style={{ cursor: "pointer", flex: "0 0 auto" }} />
                      <button onClick={() => soloEste(d.code)}
                              title="Ver sólo este departamento"
                              style={{ flex: 1, textAlign: "left", fontSize: 12,
                                       padding: "2px 0", cursor: "pointer",
                                       border: "none", background: "transparent",
                                       color: "var(--text-primary)",
                                       fontWeight: puesto ? 700 : 400 }}>
                        {rotuloDept(d.code, d.name)}
                      </button>
                      <span style={{ fontSize: 11, whiteSpace: "nowrap",
                                     color: d.ojo ? "var(--negative)"
                                                  : "var(--text-secondary)" }}>
                        {d.cuentas}{d.ojo ? ` · ${d.ojo} no cuadran` : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </span>
        <span style={{ display: "inline-flex", gap: 2 }}>
          {([["‹", -1], ["›", 1]] as const).map(([txt, n]) => (
            <button key={n} onClick={() => paso(n)} disabled={!catalogoDepts.length}
                    title={n < 0 ? "Departamento anterior" : "Departamento siguiente"}
                    style={{ fontSize: 14, lineHeight: 1, padding: "3px 9px",
                             borderRadius: 5, cursor: "pointer",
                             border: "1px solid var(--border-medium)",
                             background: "transparent",
                             color: "var(--text-primary)" }}>{txt}</button>
          ))}
        </span>
        {depts.length > 0 && (
          <button onClick={() => setDepts([])}
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
                        <td style={{ ...td, fontWeight: 600 }}>
                          {/* El nombre abre lo que el USALI dice que va aca.
                              Es referencia, no regla: si el estandar no tiene
                              una cuenta parecida, lo dice y no inventa. */}
                          <button onClick={() => void verUsali(
                                    f.dept_code + "|" + f.cuenta,
                                    f.nombre, f.dept_code)}
                                  title="Que dice el USALI que incluye esta cuenta"
                                  style={{ font: "inherit", fontWeight: 600,
                                           padding: 0, border: "none",
                                           background: "none", cursor: "pointer",
                                           textAlign: "left",
                                           color: "var(--text-primary)" }}>
                            {f.nombre}
                          </button>
                        </td>
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
                      {/* El USALI de esta cuenta, PEGADO a esta cuenta: una
                          fila mas, igual que los asientos del chip. */}
                      {usaliDe === f.dept_code + "|" + f.cuenta && usali && (
                        <tr>
                          <td colSpan={5 + vers.length * 2}
                              style={{ padding: "0 16px 10px 34px",
                                       background: "var(--bg-base)" }}>
                            <PanelUsali usali={usali}
                                        cerrar={() => { setUsaliDe(""); setUsali(null); }} />
                          </td>
                        </tr>
                      )}
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


/**
 * Lo que el USALI dice de una cuenta, PEGADO a la cuenta.
 *
 * Owner, 2026-10-09: *«necesito que cuando abra al dar click a la cuenta se
 * aparezca a la par de la cuenta que le doy click, siempre esta arriba y a
 * veces hay que subir mucho, por lo grande del documento»*.
 *
 * Era un modal centrado con cortina. Dos problemas: tapaba la tabla —que es
 * justo lo que se esta comparando— y en una tabla larga dejaba de verse donde
 * estaba parado. Ahora es una fila mas, como los asientos del chip «▸ 16»: sale
 * debajo de la cuenta que se abrio, scrollea con la tabla y no hay posicion que
 * calcular ni viewport que se le escape.
 *
 * Lleva su propio alto maximo: el libro trae cuentas con cuatro definiciones de
 * paginas distintas, y sin tope empujaba la tabla una pantalla entera.
 */
function PanelUsali({ usali, cerrar }: {
  usali: UsaliParaCuenta | "cargando"; cerrar: () => void;
}) {
  return (
    <div style={{ maxHeight: "46vh", overflowY: "auto", padding: "12px 16px",
                  borderRadius: 6, border: "1px solid var(--border-medium)",
                  borderLeft: "3px solid var(--brand)",
                  background: "var(--bg-surface)" }}>
        {usali === "cargando" ? (
          <p style={{ fontSize: 13, margin: 0 }}>Buscando en el USALI…</p>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "start", gap: 12 }}>
              <div>
                <div style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                  USALI · lo que el estándar dice de
                </div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
                  {usali.nombre}
                </h2>
              </div>
              <button onClick={cerrar} title="cerrar"
                      style={{ border: "none", background: "none",
                               cursor: "pointer", fontSize: 20, lineHeight: 1,
                               color: "var(--text-secondary)" }}>×</button>
            </div>

            {usali.grado === "ninguno" ? (
              // ⚠️ Se dice que no hay, y no se muestra el candidato malo.
              // «Cafetería → Collateral Material» enseña a desconfiar de la
              // pantalla, y eso no se recupera.
              <p style={{ fontSize: 13, marginTop: 12,
                          color: "var(--text-secondary)" }}>
                El estándar no tiene una cuenta que se llame así. Puede ser
                una cuenta propia de la propiedad, o estar con otro nombre —
                buscala en <b>Master Data → USALI</b>.
              </p>
            ) : (
              <>
                <div style={{ fontSize: 11.5, marginTop: 8,
                              color: usali.grado === "exacto"
                                ? "var(--positive)" : "var(--warning)" }}>
                  {usali.grado === "exacto"
                    ? `El estándar tiene la misma cuenta: «${usali.cuenta_usali}»`
                    : `Lo más parecido en el estándar es «${usali.cuenta_usali}» `
                      + `(${Math.round(usali.parecido * 100)}% de parecido) — `
                      + `conviene confirmarlo`}
                </div>

                {/* Owner, 2026-10-09, mirando el panel: la cuenta
                    «Miscellaneous» trae TRECE definiciones, porque el libro
                    define «cualquier gasto de este departamento que no encaje
                    en los otros renglones» una vez por departamento. Antes
                    salian las trece de corrido y la de Parking podia quedar
                    arriba de la que importa.

                    Ahora: la de su departamento abierta, las demas plegadas.
                    No se descartan —a veces la cuenta esta en el departamento
                    equivocado y la definicion de al lado es justo la pista—. */}
                {usali.definiciones.filter(d => d.es_del_depto).map((d, i) => (
                  <div key={"m" + i} style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      {d.schedule || "USALI"} · página {d.pagina}
                    </div>
                    <p style={{ fontSize: 13, lineHeight: 1.5,
                                textAlign: "justify", margin: "2px 0 0" }}>
                      {d.texto}
                    </p>
                  </div>
                ))}

                {usali.definiciones.some(d => !d.es_del_depto) && (
                  <details style={{ marginTop: 10 }}>
                    <summary style={{ fontSize: 11.5, cursor: "pointer",
                                      color: "var(--text-secondary)" }}>
                      {usali.definiciones.some(d => d.es_del_depto)
                        ? `la misma cuenta en otros departamentos `
                          + `(${usali.definiciones.filter(d => !d.es_del_depto).length})`
                        : `el libro no define esta cuenta para este `
                          + `departamento — así la define en otros `
                          + `(${usali.definiciones.length})`}
                    </summary>
                    {usali.definiciones.filter(d => !d.es_del_depto).map((d, i) => (
                      <div key={"o" + i} style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                          {d.schedule || "USALI"} · página {d.pagina}
                        </div>
                        <p style={{ fontSize: 12.5, lineHeight: 1.5,
                                    textAlign: "justify", margin: "2px 0 0",
                                    color: "var(--text-secondary)" }}>
                          {d.texto}
                        </p>
                      </div>
                    ))}
                  </details>
                )}

                {usali.items.length > 0 && (
                  <>
                    <div style={{ fontSize: 12, fontWeight: 700, marginTop: 16,
                                  marginBottom: 4 }}>
                      Lo que va acá según el diccionario ({usali.items.length})
                    </div>
                    <div style={{ fontSize: 12, columns: 2, columnGap: 22 }}>
                      {usali.items.map((it, i) => (
                        <div key={i} style={{ breakInside: "avoid",
                                              padding: "1px 0" }}>
                          {it.item}
                          <span style={{ color: "var(--text-secondary)" }}>
                            {" "}· {it.schedule}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </>
            )}

            {/* Que lleva ESTE departamento segun el estandar.
                *
                * Owner, 2026-10-08: *«cada cuenta tiene la descripcion y
                * va por departamento»*. Es referencia: cuando el libro no
                * da lista —el Spa y los departamentos menores son el
                * Schedule 3— lo dice en vez de callarse, porque el
                * silencio se lee como «su cuenta esta mal». */}
              {usali.schedule && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 700,
                                marginBottom: 4 }}>
                    {usali.schedule.lista_aprobada
                      ? `Renglones aprobados de ${usali.schedule.titulo_es
                          || usali.schedule.titulo
                          || usali.schedule.schedule}`
                        + ` — Schedule ${usali.schedule.numero}`
                        + ` (${usali.schedule.renglones.length})`
                      : "El estándar no da lista para este departamento"}
                  </div>
                  {usali.schedule.lista_aprobada ? (
                    <div style={{ fontSize: 12, columns: 2,
                                  columnGap: 22 }}>
                      {/* El español primero y el inglés al lado en gris: el
                          inglés es el nombre con que el libro y el catálogo lo
                          llaman, así que no se tira. */}
                      {usali.schedule.renglones.map((g, i) => {
                        const es = usali.schedule?.renglones_es?.[i];
                        return (
                          <div key={i} style={{ breakInside: "avoid",
                                                padding: "1px 0" }}>
                            {es || g}
                            {es && (
                              <span style={{ color: "var(--text-secondary)",
                                             fontSize: 11 }}> · {g}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p style={{ fontSize: 12.5, margin: 0, lineHeight: 1.5,
                                color: "var(--text-secondary)" }}>
                      {usali.schedule.numero === 3
                        ? "Es un Other Operated Department — Schedule 3. "
                          + "El libro no aprueba una lista cerrada: «only "
                          + "the revenues and expenses that exist at an "
                          + "individual property». Que una cuenta no "
                          + "aparezca en el estándar no dice nada acá."
                        : usali.schedule.motivo}
                    </p>
                  )}
                </div>
              )}

            <p style={{ fontSize: 11, marginTop: 16, marginBottom: 0,
                        color: "var(--text-secondary)" }}>
              Referencia, no regla: esto no marca ni corrige nada. Uniform
              System of Accounts for the Lodging Industry — AHLA/HFTP.
            </p>
          </>
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
