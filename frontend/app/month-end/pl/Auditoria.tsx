"use client";
/**
 * La auditoría del detalle: de qué está hecha cada línea del P&L.
 *
 * Owner, 2026-09-02, entregando `p&L auditoria 2026.xlsx`: *«el otro para ver
 * la auditoría de los detalles»*.
 *
 * Tres bloques, que son tres preguntas distintas:
 *
 * 1. **Cuadre** — por cada renglón del P&L, cuánto dice el motor, cuánto suma
 *    su detalle, y la diferencia. Es lo primero porque es lo único que puede
 *    estar MAL; el resto es información.
 * 2. **Detalle** — cuenta por cuenta, agrupado por departamento, con la
 *    naturaleza y el renglón al que cae.
 * 3. **Por departamento** — la matriz Ingresos / Costo / Payroll / Opex /
 *    Reparto / Bajo GOP / Total gasto.
 *
 * ⚠️ **Nada se calcula acá.** La atribución de cada monto a su línea la hace el
 * backend con `pl_engine.linea_de_fila`, que reusa las mismas funciones que
 * arman el P&L. Rehacerla en la pantalla daría una segunda verdad: una
 * auditoría que clasifica distinto que el motor **cuadra consigo misma** y da
 * el visto bueno justo cuando algo está mal.
 */
import { sembrarTres } from "@/lib/escenarioPreferido";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { getAuditoria, type Auditoria as Datos, type AuditoriaCuadre,
         type AuditoriaFila, type Scenario } from "@/lib/api";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

const usd = (n: number) =>
  Math.abs(n) < 0.005 ? "—"
    : (n < 0 ? "(" : "") + Math.abs(n).toLocaleString("en-US",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (n < 0 ? ")" : "");

const TD: React.CSSProperties = {
  padding: "3px 9px", textAlign: "right", fontSize: 11.5, whiteSpace: "nowrap",
};
const TDL: React.CSSProperties = { padding: "3px 10px", fontSize: 11.5 };
const TH: React.CSSProperties = {
  ...TD, fontWeight: 700, borderBottom: "1px solid var(--border-medium)",
};

const SEL: React.CSSProperties = {
  padding: "5px 9px", fontSize: 12, borderRadius: 5,
  border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)",
};

/** El orden en que se leen las naturalezas, y cómo se ve cada una.
 *
 *  ⚠️ Los nombres son EXACTAMENTE los que manda el backend
 *  (`pl_engine.TIPO_*`). Traducirlos acá haría que un renombre en el motor
 *  dejara el subtítulo en el grupo equivocado sin que nada falle: las filas
 *  seguirían apareciendo, sólo que bajo el título de al lado.
 *
 *  El orden es el del P&L —ingreso, costo, planilla, opex, y lo que va después
 *  del GOP—, no el alfabético. */
const NATURALEZA: { tipo: string; color: string }[] = [
  { tipo: "Ingresos",        color: "var(--positive)" },
  { tipo: "Costo de ventas", color: "var(--brand)" },
  { tipo: "Payroll",         color: "var(--brand)" },
  { tipo: "Opex",            color: "var(--brand)" },
  { tipo: "Reparto",         color: "var(--text-secondary)" },
  { tipo: "Bajo GOP",        color: "var(--text-secondary)" },
];

/** Dónde va una naturaleza. Una que el backend agregue y acá no esté va al
 *  FINAL —no se pierde—, que es lo contrario de filtrarla. */
const orden = (tipo: string) => {
  const i = NATURALEZA.findIndex(n => n.tipo === tipo);
  return i < 0 ? NATURALEZA.length : i;
};
const colorDe = (tipo: string) =>
  NATURALEZA.find(n => n.tipo === tipo)?.color ?? "var(--text-secondary)";

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

export default function Auditoria({ escenarios, inicial, mes, horizonte = "month",
                                   compacto = true }: {
  escenarios: Scenario[];
  inicial?: string;
  /** ⚠️ El mes lo MANDA la pantalla. No hay estado propio ni selector acá.
   *
   *  Owner, 2026-09-08: *«el único que debe escoger es la parte de arriba y
   *  todo lo de abajo debe responder a ese mandato; hay una variable intermedia
   *  para escoger pero no debe aplicar ya que el sistema se confunde»*.
   *
   *  Antes esto era `useState(mesInicial)`, que lee la prop UNA sola vez: al
   *  cambiar el mes arriba, la auditoría seguía mostrando el de cuando se
   *  montó, y los dos selectores decían cosas distintas sin avisar. */
  mes: number;
  /** El ámbito de la pantalla, y manda igual que el mes.
   *
   *  Owner, 2026-09-08: *«toda auditoría debe responder a si es mes, YTD o
   *  full year»*. Y responde de verdad: el backend acumula LAS DOS mitades del
   *  cuadre sobre los mismos meses —el detalle sumando sus columnas, el motor
   *  agregando sus resultados con `_aggregate_selected`, el mismo agregador que
   *  dibuja el P&L de arriba—. */
  horizonte?: "month" | "ytd" | "full";
  /** Esconder lo que está en cero. Lo manda la pantalla: el interruptor es uno
   *  solo para todos los sub-tabs. */
  compacto?: boolean;
}) {
  const [scenarioId, setScenarioId] = useState("");
  const [datos, setDatos] = useState<Datos | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Sólo las líneas que NO cuadran. Es el modo en que se usa esta pantalla
   *  cuando ya se sabe que algo falla. */
  const [soloDif, setSoloDif] = useState(false);

  useEffect(() => {
    if (!escenarios.length) return;
    setScenarioId(x => x || inicial || primeroDe(escenarios, "ACTUAL"));
  }, [escenarios, inicial]);

  const cargar = useCallback(async () => {
    if (!scenarioId) return;
    setCargando(true); setError(null);
    try {
      setDatos(await getAuditoria(scenarioId, mes, horizonte));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la auditoría");
      setDatos(null);
    } finally { setCargando(false); }
    // ⚠️ `horizonte` va en las dependencias. Sin él, cambiar de mes a YTD
    // arriba no volvía a pedir nada y la pantalla seguía mostrando el período
    // anterior con el rótulo nuevo — que es peor que no cambiar nada.
  }, [scenarioId, mes, horizonte]);

  useEffect(() => { cargar(); }, [cargar]);

  const cuadre = useMemo(() => {
    const filas = datos?.cuadre ?? [];

    // «Sólo lo que no cuadra» deja los renglones con diferencia y NADA más:
    // acá el cuadro deja de ser un P&L y pasa a ser una lista de problemas,
    // que es justo lo que se quiere ver en ese modo.
    if (soloDif) {
      return filas.filter(f => f.dif !== null && Math.abs(f.dif) >= 0.005);
    }

    // Compacto esconde lo que está en cero por los dos lados: un renglón sin
    // motor y sin detalle no dice nada.
    const vivo = (f: AuditoriaCuadre) =>
      Math.abs(f.motor ?? 0) >= 0.005 || Math.abs(f.detalle ?? 0) >= 0.005;
    const visibles = compacto
      ? filas.filter(f => f.tipo === "sec" || f.tipo === "esp" || vivo(f))
      : filas;

    // ⚠️ Y se limpia la estructura que quedó colgando: una sección cuyos
    // renglones se escondieron todos es un título sobre la nada, y dos blancos
    // seguidos son un agujero en el medio del reporte.
    return visibles.filter((f, i) => {
      if (f.tipo === "sec") {
        const sigue = visibles.slice(i + 1).find(x => x.tipo !== "esp");
        return !!sigue && sigue.tipo !== "sec";
      }
      if (f.tipo === "esp") {
        const antes = visibles[i - 1];
        const despues = visibles.slice(i + 1).find(x => x.tipo !== "esp");
        return !!antes && antes.tipo !== "esp" && antes.tipo !== "sec" && !!despues;
      }
      return true;
    });
  }, [datos, soloDif, compacto]);

  /** El detalle en DOS niveles: departamento → naturaleza → cuentas.
   *
   *  Owner, 2026-09-03: *«en los departamentos que se lea bien con subtítulos
   *  ingresos, costos, payroll y opex; que quede bien subdividido»*.
   *
   *  ⚠️ Antes era una lista plana por departamento, ordenada por naturaleza
   *  pero sin decirlo: las cuentas de payroll y las de opex se veían iguales y
   *  había que reconocer el 60xx del 70xx para saber qué se estaba mirando. La
   *  naturaleza estaba en una columna, que es el peor lugar para algo que
   *  agrupa — se repite en cada fila y no separa nada.
   *
   *  El orden lo fija ORDEN_NATURALEZA y NO el alfabeto: un P&L se lee ingreso
   *  primero y gasto después. */
  const porDepto = useMemo(() => {
    const out = new Map<string, {
      nombre: string;
      grupos: Map<string, AuditoriaFila[]>;
      total: number;
    }>();
    for (const f of datos?.detalle ?? []) {
      // ⚠️ `Compacto` esconde las OPCIONES del catálogo que no se movieron.
      // Es el mismo interruptor que ya gobierna los sub-tabs, y el pedido
      // original: «las líneas que no tienen saldo que no se vean
      // temporalmente». Apagándolo se ven las 51 cuentas que el departamento
      // puede usar, no sólo las 12 que usó.
      if (compacto && !f.movimiento) continue;
      const g = out.get(f.dept_code)
        || { nombre: f.dept_name, grupos: new Map<string, AuditoriaFila[]>(), total: 0 };
      const bolsa = g.grupos.get(f.tipo) || [];
      bolsa.push(f);
      g.grupos.set(f.tipo, bolsa);
      g.total += f.monto;
      out.set(f.dept_code, g);
    }
    return [...out.entries()].map(([code, g]) => ({
      code, nombre: g.nombre, total: g.total,
      grupos: [...g.grupos.entries()]
        .sort((a, b) => orden(a[0]) - orden(b[0]))
        // ⚠️ Dentro de cada naturaleza, PRIMERO lo que se movió y de mayor a
        // menor; las cuentas disponibles y sin usar, al final.
        //
        // Owner, 2026-09-03: «nada que sale bien en auditoría, en la parte de
        // abajo». Ordenadas por número de cuenta, las opciones en cero se
        // intercalaban entre los montos reales: en el Opex del Club, un
        // 12.075,82 quedaba entre dos ceros. Un cuadro donde hay que buscar el
        // dato entre lo que no es dato no se lee.
        .map(([tipo, filas]) => [tipo, [...filas].sort((x, y) => {
          if (x.movimiento !== y.movimiento) return x.movimiento ? -1 : 1;
          if (!x.movimiento) return x.account_code.localeCompare(y.account_code);
          return Math.abs(y.monto) - Math.abs(x.monto);
        })] as [string, AuditoriaFila[]]),
    }));
  }, [datos, compacto]);

  const columnas = datos?.columnas ?? [];
  const descuadres = (datos?.cuadre ?? [])
    .filter(f => f.dif !== null && Math.abs(f.dif) >= 0.005);

  return (
    <div>
      <div style={{ display: "flex", gap: 10, alignItems: "center",
                    flexWrap: "wrap", marginBottom: 12 }}>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)} style={SEL}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
          ))}
        </select>
        {/* ⚠️ El rótulo lo dice el BACKEND (`periodo`), no se arma acá.
            Es el único que sabe qué meses acumuló de verdad; un texto
            calculado en la pantalla podría decir «Acumulado a Julio» mientras
            abajo hay otra cosa, y nada fallaría. Mientras carga se usa el mes
            de la pantalla, para no dejar el hueco en blanco. */}
        <span style={{ fontSize: 12.5, color: "var(--text-secondary)",
                       padding: "0 4px" }}>
          {datos?.periodo ?? MESES[mes - 1]}
        </span>
        <button onClick={() => setSoloDif(x => !x)}
          title="Dejar sólo los renglones cuyo detalle no suma lo que dice el motor"
          style={{ ...SEL, cursor: "pointer", fontWeight: 600,
                   background: soloDif ? "var(--brand)" : "var(--bg-surface)",
                   color: soloDif ? "#fff" : "var(--text-secondary)" }}>
          {soloDif ? "☑ Sólo lo que no cuadra" : "☐ Sólo lo que no cuadra"}
        </button>
        {cargando && <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>cargando…</span>}
        {error && <span style={{ fontSize: 12, color: "var(--negative)" }}>{error}</span>}
      </div>

      {/* ── El veredicto, arriba de todo ──────────────────────────────────── */}
      {datos && (
        <div style={{
          padding: "9px 14px", borderRadius: 8, marginBottom: 14, maxWidth: 900,
          border: "1px solid var(--border)",
          borderLeft: `4px solid ${descuadres.length ? "var(--negative)" : "var(--positive)"}`,
          fontSize: 12.5, lineHeight: 1.6, color: "var(--text-secondary)",
        }}>
          {descuadres.length
            ? <><b style={{ color: "var(--negative)" }}>
                {descuadres.length} renglón(es) no cuadran.
              </b>{" "}El detalle no suma lo que dice el P&L. Es lo que hay que revisar.</>
            : <><b style={{ color: "var(--positive)" }}>Todo cuadra.</b>{" "}
                Cada renglón del P&L es exactamente la suma de su detalle.</>}
          {datos.avisos.map((a, i) => (
            <div key={i} style={{ marginTop: 5 }}>· {a}</div>
          ))}

          {/* ── El 100%, dicho con números ────────────────────────────────
              Owner, 2026-09-03: «que haya el 100% de los datos siempre».

              ⚠️ Sin esto no hay forma de distinguir «no hay más» de «hay más
              y no lo estoy mostrando». El reporte esconde filas a propósito
              —las que están en cero, las estadísticas 9xxx—, y un reporte al
              que le falta media hoja se ve igual que uno completo. */}
          <div style={{
            marginTop: 9, paddingTop: 8, fontSize: 11.5,
            borderTop: "1px solid var(--border)",
            display: "flex", gap: 16, flexWrap: "wrap",
          }}>
            <span><b>{datos.cobertura.asientos}</b> asientos en el mes</span>
            <span><b>{datos.cobertura.con_monto}</b> con monto</span>
            <span>{datos.cobertura.en_cero} en cero</span>
            {datos.cobertura.estadisticos > 0 && (
              <span title="Cuentas 9xxx: son estadística, no plata. No entran en el P&L.">
                {datos.cobertura.estadisticos} estadísticas (no son plata)
              </span>
            )}
            <span style={{ marginLeft: "auto", fontWeight: 700 }}>
              Suma del detalle: {usd(datos.cobertura.suma_detalle)}
            </span>
          </div>
          {!compacto && datos.cobertura.opciones_gl > 0 && (
            <div style={{ marginTop: 5, fontSize: 11.5 }}>
              Y <b>{datos.cobertura.opciones_gl}</b> cuentas más que estos
              departamentos pueden usar y este mes no usaron — en gris, para
              ver qué hay disponible. Se esconden con «Compacto».
            </div>
          )}
        </div>
      )}

      {/* ── Los tres números, arriba de todo ──────────────────────────────
          Owner, 2026-09-03: «total ingresos, total gastos, net profit».

          ⚠️ TOTAL GASTOS no existe como línea del P&L. No se inventa una: sale
          de la identidad del propio estado —lo que entró menos lo que quedó—,
          calculada en el backend. Sumar renglones a mano acá sería una segunda
          aritmética que el día que se agregue un bloque al P&L dejaría de
          cuadrar en silencio. */}
      {datos && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap",
                      margin: "16px 0 4px" }}>
          {([
            ["Total Ingresos", datos.resumen.ingresos, "var(--positive)"],
            ["Total Gastos", datos.resumen.gastos, "var(--text-primary)"],
            ["Net Profit", datos.resumen.neto,
             datos.resumen.neto < 0 ? "var(--negative)" : "var(--positive)"],
          ] as const).map(([rotulo, valor, color]) => (
            <div key={rotulo} style={{
              flex: "1 1 190px", minWidth: 170, padding: "11px 15px",
              borderRadius: 9, background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderTop: `3px solid ${color}`,
            }}>
              <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: .7,
                            textTransform: "uppercase",
                            color: "var(--text-secondary)", marginBottom: 3 }}>
                {rotulo}
              </div>
              <div className="mono" style={{ fontSize: 20, fontWeight: 800,
                                             color, lineHeight: 1.15 }}>
                {usd(valor)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 1. Cuadre ─────────────────────────────────────────────────────── */}
      <h3 style={{ fontSize: 13, fontWeight: 800, margin: "18px 0 6px" }}>
        Cuadre — cada renglón del P&L contra la suma de su detalle
      </h3>
      <div className="fin-scroll-x">
        <table style={{ borderCollapse: "collapse", minWidth: 560 }}>
          <thead><tr>
            <th style={{ ...TH, textAlign: "left", minWidth: 270,
                         borderBottom: "2px solid var(--text-primary)" }}>
              Renglón
            </th>
            <th style={{ ...TH, minWidth: 130,
                         borderBottom: "2px solid var(--text-primary)" }}>
              P&L (motor)
            </th>
            <th style={{ ...TH, minWidth: 130,
                         borderBottom: "2px solid var(--text-primary)" }}>
              Suma del detalle
            </th>
            <th style={{ ...TH, minWidth: 110,
                         borderBottom: "2px solid var(--text-primary)" }}>
              Dif.
            </th>
          </tr></thead>
          <tbody>
            {cuadre.map((f, i) => {
              // ── Un blanco, para que el cuadro respire entre bloques ──
              if (f.tipo === "esp") {
                return <tr key={`esp-${i}`}><td colSpan={4} style={{ height: 10 }} /></tr>;
              }

              // ── El encabezado de sección: una banda, no una fila más ──
              //
              // ⚠️ Es lo que faltaba. Sin secciones, «Rooms» salía dos veces
              // —el ingreso y el gasto— y los $36.218 y los $17.847 se leían
              // como dos versiones del mismo número.
              if (f.tipo === "sec") {
                return (
                  <tr key={`sec-${i}`}>
                    <td colSpan={4} style={{
                      padding: "7px 10px",
                      fontSize: 10.5, fontWeight: 800, letterSpacing: 1,
                      textTransform: "uppercase", color: "#fff",
                      background: "var(--brand)",
                    }}>
                      {f.nombre}
                    </td>
                  </tr>
                );
              }

              const total = f.tipo === "tot" || f.tipo === "sub";
              const mal = f.dif !== null && Math.abs(f.dif) >= 0.005;

              // Tres pesos, y cada uno dice algo distinto:
              //   hito     — Total Revenues, Operating Profit, GOP, Net Profit
              //   tot/sub  — el cierre de un bloque
              //   det/der  — un renglón
              const peso = f.hito ? 800 : total ? 700 : 400;
              const fondo = mal ? "rgba(230,168,23,0.13)"
                : f.hito ? "var(--bg-elevated, #EDF1F5)"
                : total ? "var(--bg-surface)" : undefined;

              return (
                <tr key={`${f.tipo}-${f.linea}-${i}`} style={{
                  background: fondo,
                  // ⚠️ La regla DOBLE es la del hito, y la simple la del
                  // subtotal. Es la convención de un estado de resultados
                  // impreso: la línea de arriba dice «acá se cierra algo» y
                  // cuánto pesa ese cierre.
                  borderTop: f.hito ? "2px solid var(--text-primary)"
                    : total ? "1px solid var(--border-medium)" : undefined,
                  borderBottom: f.hito ? "1px solid var(--text-primary)" : undefined,
                }}>
                  <td style={{ ...TDL, fontWeight: peso,
                               fontSize: f.hito ? 12.5 : 11.5,
                               letterSpacing: f.hito ? .3 : undefined,
                               paddingTop: total ? 6 : 3,
                               paddingBottom: total ? 6 : 3,
                               paddingLeft: total ? 10 : 26 }}>
                    {f.nombre}
                    {/* Los códigos sólo cuando hay algo que investigar: en un
                        renglón que cuadra son ruido, y ahora son varios por
                        fila (`OPEX_FB · COS_FB_FOOD · COS_FB_BEV`). */}
                    {(mal || f.seccion === "HUERFANO") && (
                      <span style={{ color: "var(--text-disabled)", marginLeft: 6,
                                     fontSize: 10.5 }}>
                        {f.linea}
                      </span>
                    )}
                  </td>
                  <td className="mono" style={{ ...TD, fontWeight: peso,
                        fontSize: f.hito ? 12.5 : 11.5,
                        paddingTop: total ? 6 : 3, paddingBottom: total ? 6 : 3,
                        color: (f.motor ?? 0) < 0 ? "var(--negative)" : undefined }}>
                    {usd(f.motor ?? 0)}
                  </td>
                  {/* Un TOTAL es suma de otros renglones y un DERIVADO es
                      ingreso menos gasto: ninguno se compone de asientos, así
                      que no tienen detalle contra qué cuadrar. Poner cero ahí
                      inventaría un descuadre — eran seis en el primer
                      intento. */}
                  <td className="mono" style={{ ...TD, fontWeight: peso,
                        color: "var(--text-disabled)",
                        paddingTop: total ? 6 : 3, paddingBottom: total ? 6 : 3 }}
                      title={f.detalle === null
                        ? "No se compone de asientos: es una suma de otros renglones."
                        : undefined}>
                    {f.detalle === null ? "—" : usd(f.detalle)}
                  </td>
                  <td className="mono" style={{ ...TD, fontWeight: mal ? 800 : peso,
                        paddingTop: total ? 6 : 3, paddingBottom: total ? 6 : 3,
                        color: mal ? "var(--negative)" : "var(--text-disabled)" }}>
                    {f.dif === null ? "" : usd(f.dif)}
                  </td>
                </tr>
              );
            })}
            {!cuadre.length && (
              <tr><td colSpan={4} style={{ ...TDL, color: "var(--text-secondary)" }}>
                {soloDif ? "No hay diferencias." : "Sin datos para este mes."}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── 2. Detalle ────────────────────────────────────────────────────── */}
      <h3 style={{ fontSize: 13, fontWeight: 800, margin: "24px 0 6px" }}>
        Detalle — cada cuenta y dónde cayó
      </h3>
      <div className="fin-scroll-x">
        <table style={{ borderCollapse: "collapse", minWidth: 700 }}>
          <thead><tr>
            <th style={{ ...TH, textAlign: "left", minWidth: 70 }}>Cuenta</th>
            <th style={{ ...TH, textAlign: "left", minWidth: 210 }}>Nombre</th>
            <th colSpan={2} style={{ ...TH, textAlign: "left", minWidth: 200 }}>
              Renglón del P&L
            </th>
            <th style={{ ...TH, minWidth: 110 }}>Monto US$</th>
          </tr></thead>
          <tbody>
            {porDepto.map(d => (
              // ⚠️ `Fragment` con `key` y no `<>`: un arreglo de fragmentos sin
              // llave hace que React reordene mal las filas al cambiar de mes,
              // y se ven subtotales pegados al departamento equivocado.
              <Fragment key={d.code}>
                {/* El departamento: barra completa, para que se lea como corte
                    y no como una fila más. */}
                <tr>
                  <td colSpan={5} style={{
                    ...TDL, fontWeight: 800, fontSize: 12.5,
                    padding: "7px 10px",
                    background: "var(--bg-elevated, #EDF1F5)",
                    borderTop: "2px solid var(--border-medium)",
                  }}>
                    <span style={{ color: "var(--text-secondary)",
                                   fontVariantNumeric: "tabular-nums" }}>
                      {d.code}
                    </span>{" · "}{d.nombre}
                  </td>
                </tr>

                {d.grupos.map(([tipo, filas]) => (
                  <Fragment key={`${d.code}-${tipo}`}>
                    {/* El subtítulo de naturaleza. Owner: «que se lea bien con
                        subtítulos ingresos, costos, payroll y opex». */}
                    <tr>
                      <td colSpan={4} style={{
                        ...TDL, paddingLeft: 22, paddingTop: 7, paddingBottom: 2,
                        fontSize: 10.5, fontWeight: 800, letterSpacing: .6,
                        textTransform: "uppercase", color: colorDe(tipo),
                      }}>
                        {tipo}
                      </td>
                      <td style={{ ...TD, fontSize: 10.5, fontWeight: 800,
                                   paddingTop: 7, paddingBottom: 2,
                                   color: colorDe(tipo) }}>
                        {usd(filas.reduce((x, f) => x + f.monto, 0))}
                      </td>
                    </tr>
                    {filas.map((f, i) => (
                      <Fragment key={`${d.code}-${tipo}-${i}`}>
                      {/* La línea que separa lo que se movió de lo que está
                          disponible. Sin ella, una fila en gris se lee como un
                          movimiento de cero y no como una cuenta sin usar. */}
                      {!f.movimiento && (i === 0 || filas[i - 1].movimiento) && (
                        <tr>
                          <td colSpan={5} style={{
                            ...TDL, paddingLeft: 34, paddingTop: 5,
                            fontSize: 10, fontStyle: "italic",
                            color: "var(--text-disabled)",
                            borderTop: "1px dashed var(--border-medium)",
                          }}>
                            cuentas disponibles en este departamento, sin usar
                            este mes
                          </td>
                        </tr>
                      )}
                      <tr
                          title={f.movimiento ? undefined
                            : "Opción del catálogo GL de este departamento. Este mes no se usó."}
                          style={f.movimiento ? undefined
                            : { color: "var(--text-disabled)" }}>
                        <td style={{ ...TDL, paddingLeft: 34,
                                     fontVariantNumeric: "tabular-nums",
                                     color: "var(--text-secondary)" }}>
                          {f.account_code}
                        </td>
                        <td style={TDL}>
                          {f.account_name}{f.outlet ? ` · ${f.outlet}` : ""}
                        </td>
                        {/* La naturaleza YA está en el subtítulo; acá iba
                            repetida en cada fila sin agrupar nada. En su lugar
                            va el renglón del P&L, que es lo que se audita. */}
                        <td colSpan={2} style={{
                          ...TDL, color: f.linea ? "var(--text-secondary)" : "var(--negative)",
                          fontWeight: f.linea ? 400 : 700,
                        }}>
                          {f.linea || "⚠ no cae en ninguna línea"}
                        </td>
                        <td style={TD}>{usd(f.monto)}</td>
                      </tr>
                      </Fragment>
                    ))}
                  </Fragment>
                ))}

                <tr>
                  <td colSpan={4} style={{ ...TDL, textAlign: "right", fontWeight: 800,
                                           paddingTop: 5 }}>
                    Subtotal {d.code} · {d.nombre}
                  </td>
                  <td style={{ ...TD, fontWeight: 800, paddingTop: 5,
                               borderTop: "1px solid var(--border-medium)" }}>
                    {usd(d.total)}
                  </td>
                </tr>
              </Fragment>
            ))}
            {!porDepto.length && (
              <tr><td colSpan={5} style={{ ...TDL, color: "var(--text-secondary)" }}>
                Sin detalle por cuenta para este mes.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── 3. Matriz por departamento ────────────────────────────────────── */}
      <h3 style={{ fontSize: 13, fontWeight: 800, margin: "24px 0 6px" }}>
        Resumen por departamento
      </h3>
      <div className="fin-scroll-x">
        <table style={{ borderCollapse: "collapse", minWidth: 700 }}>
          <thead><tr>
            <th style={{ ...TH, textAlign: "left", minWidth: 230 }}>Departamento</th>
            {columnas.map(c => <th key={c} style={{ ...TH, minWidth: 108 }}>{c}</th>)}
            <th style={{ ...TH, minWidth: 118,
                         borderLeft: "2px solid var(--border-medium)" }}>Total gasto</th>
          </tr></thead>
          <tbody>
            {(datos?.departamentos ?? []).map(d => (
              <tr key={String(d.dept_code)}>
                <td style={TDL}>{d.dept_code} · {d.dept_name}</td>
                {columnas.map(c => (
                  <td key={c} style={TD}>{usd(Number(d[c] ?? 0))}</td>
                ))}
                <td style={{ ...TD, fontWeight: 700,
                             borderLeft: "2px solid var(--border-medium)" }}>
                  {usd(d.total_gasto)}
                </td>
              </tr>
            ))}
            {datos && (
              <tr style={{ fontWeight: 800,
                           borderTop: "1px solid var(--border-medium)" }}>
                <td style={TDL}>TOTAL</td>
                {columnas.map(c => (
                  <td key={c} style={TD}>{usd(datos.totales[c] ?? 0)}</td>
                ))}
                <td style={{ ...TD, borderLeft: "2px solid var(--border-medium)" }}>
                  {usd(datos.totales.total_gasto ?? 0)}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {datos && (
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)",
                    marginTop: 14, maxWidth: 820, lineHeight: 1.6 }}>
          ⚠️ <b>No aparece la cuenta contable local</b> (61011101 y compañía).{" "}
          {datos.nota_cuenta_local}
        </p>
      )}
    </div>
  );
}
