"use client";
/**
 * Budget Package — todo el presupuesto en un libro, para revisión rápida.
 *
 * Owner, 2026-10-01: *«necesito crear esta vista de cierre para Budget 2027…
 * por qué no creás un tab llamado Planning Report»* · *«quiero 12 meses, y full
 * year para comparar con otras versiones»* · *«por qué los checkbooks no tienen
 * los detalles. todos deben tener detalle»* · *«quisiera también bajar las
 * posiciones por departamento con salario y FTE»* · *«el tab de allocation de
 * laundry y cafetería, con todos los parámetros y distribución, kilos FTE para
 * distribuir»* · **«esto debe ser un Budget Package para revisión rápida»**.
 *
 * ## Por qué no alcanzaba con la pantalla del cierre
 *
 * El cierre contesta «cómo vamos»: parte el año en mes, acumulado y año, y vive
 * colgado del mes que se cierra. Planning contesta «cómo queda el año», y ahí el
 * acumulado a octubre no dice nada — lo que se mira es la estacionalidad mes a
 * mes y el total contra la versión anterior. Por eso acá no hay selector de mes
 * ni de corte: son los doce meses, siempre.
 *
 * ## Los siete niveles, con las MISMAS columnas
 *
 * | vista | de dónde sale | qué abre |
 * |---|---|---|
 * | P&L | `/reports/pl-detail/` | la cascada completa, por ámbito |
 * | Aperturas | `/gasto-por-clase/?detalle=true` | depto · línea · cuenta |
 * | Checkbooks | `/gasto-por-clase/detalle-de-celda/` | cuenta del mayor |
 * | Con detalle | el mismo, con `abrir` | la sub-línea: `800 · Coral` |
 * | Plantilla | `/payroll/posiciones/` | posición, salario y FTE |
 * | Reparto | `/allocations/{id}/summary/` | cafetería y lavandería, y su base |
 * | Estadísticas | `/pl/{id}/estadisticas/` | noches, ocupación, ADR, Club |
 *
 * Las siete pasan por `armarCuadro`, así que la columna «Full Year» es la misma
 * celda en todas: el libro se baja entero y se compara hoja contra hoja.
 *
 * ## ⚠️ La tabla que se ve es el MISMO objeto que baja al Excel
 *
 * Los constructores devuelven un `Cuadro` y `Tabla` lo dibuja. No hay una tabla
 * en JSX y otra en el exportador: no pueden decir cosas distintas, que es el
 * defecto que este proyecto ya pagó una vez (owner, 2026-08-27: «el excel no
 * baja lo que está viendo»).
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getAllocationSummary, getDetalleDeCelda, getEstadisticasCierre,
  getGastoPorClase, getPLDetail, getPosiciones, getScenarios,
  type AllocationSummary, type DetalleCelda, type EstadisticasCierre,
  type GastoEscenario, type PLDetail, type PosicionesVersion, type Scenario,
} from "@/lib/api";
import { bajarCuadros, type Cuadro } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";
import {
  APERTURAS, cuadroApertura, cuadroCheckbook, cuadroEstadisticas, cuadroPlanning,
  cuadroPosiciones, cuadroReparto, METRICAS_POSICION, REPARTOS, seAbre,
  tiposDeReparto, type ClaseApertura, type MetricaPosicion,
} from "@/lib/planningReport";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import IrA from "@/components/IrA";
import Tabla from "./Tabla";

const AMBITOS = [
  { id: "consolidado", rotulo: "Consolidado", ayuda: "Hotel + Club Madresal" },
  { id: "hotel", rotulo: "Hotel", ayuda: "Sin el Club Madresal" },
  { id: "club", rotulo: "Club Madresal", ayuda: "Sólo el departamento 260" },
] as const;

const VISTAS = [
  { id: "pl", rotulo: "P&L", ayuda: "La cascada completa, por ámbito" },
  { id: "aperturas", rotulo: "Aperturas", ayuda: "Por departamento, línea y cuenta" },
  { id: "checkbooks", rotulo: "Checkbooks", ayuda: "Cuenta por cuenta del mayor" },
  { id: "detalle", rotulo: "Checkbooks con detalle",
    ayuda: "Cada cuenta abierta en sus sub-líneas: 800 · Coral, 801 · Fumigación…" },
  { id: "plantilla", rotulo: "Plantilla",
    ayuda: "Posiciones por departamento, con salario y FTE" },
  { id: "reparto", rotulo: "Reparto",
    ayuda: "Cafetería y lavandería: cuánto se repartió y con qué base" },
  { id: "estadisticas", rotulo: "Estadísticas", ayuda: "Noches, ocupación, ADR, Club" },
] as const;

/** Cuántas versiones se pueden comparar contra la principal. */
const COMPARAR = 3;

const DOCE = Array.from({ length: 12 }, (_, i) => i + 1);

export default function PlanningReportPage() {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  /** ⚠️ La regla COMPARTIDA, no una propia. Owner, 2026-08-14: «Lo dejo en
   *  Working 2027 y aparece en Working 2035» — cada pantalla traía su «el año
   *  más nuevo» copiado a mano, y el día que nacieron los Working 2028-2035
   *  todos los reportes se fueron a 2035 sin que nada fallara.
   *
   *  El rol «budget» abre en Budget Working 2027, que es para lo que existe
   *  esta pantalla, y recuerda lo que se elija. */
  const [principal, setPrincipal] = useEscenarioDe(
    "planning/report:budget", escenarios, "budget", undefined, true);
  const [comparar, setComparar] = useState<string[]>(Array(COMPARAR).fill(""));
  const [vista, setVista] = useState<string>("pl");
  const [ambito, setAmbito] = useState<string>("consolidado");
  const [clase, setClase] = useState<ClaseApertura>("opex");
  const [metrica, setMetrica] = useState<MetricaPosicion>("fte");
  const [tipoReparto, setTipoReparto] = useState<string>("CAFETERIA");
  const [compacto, setCompacto] = useState(true);
  /** De QUÉ versión son los doce meses. Owner, 2026-10-01: *«quiero que metas
   *  la opción de generar un 12 meses de Forecast y Budget 2026»*. El año de
   *  cada versión siempre está; esto elige de cuál se abre la estacionalidad. */
  const [mesesDe, setMesesDe] = useState(0);

  const [pl, setPl] = useState<PLDetail | null>(null);
  const [gastos, setGastos] = useState<
    { escenarios: GastoEscenario[]; departamentos: Record<string, string> } | null>(null);
  const [libro, setLibro] = useState<Record<string, DetalleCelda>>({});
  const [plantilla, setPlantilla] = useState<PosicionesVersion[] | null>(null);
  const [reparto, setReparto] = useState<
    { resumen: (AllocationSummary | null)[]; deptos: Record<string, string> } | null>(null);
  const [stats, setStats] = useState<
    { meses: (EstadisticasCierre | null)[]; anios: (EstadisticasCierre | null)[] } | null>(null);

  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bajando, setBajando] = useState("");

  useEffect(() => {
    getScenarios(HOTEL_ID)
      .then(setEscenarios)
      .catch(e => setError(e instanceof Error ? e.message : "no se pudo cargar"));
  }, []);

  const otros = useMemo(() => comparar.filter(Boolean), [comparar]);
  const ids = useMemo(
    () => (principal ? [principal, ...otros] : []), [principal, otros]);

  /** La misma llave con la que se guarda un checkbook: la clase y si está
   *  abierto. Sin el `abrir` en la llave, pedir el detalle devolvía el cuadro
   *  sin abrir que ya estaba en memoria. */
  const llaveLibro = (c: string, abrir: boolean) => `${c}${abrir ? ":abierto" : ""}`;

  /** Las estadísticas: los doce meses de la versión principal, uno por llamada,
   *  y el año de cada versión con el período completo.
   *
   *  ⚠️ El año NO se suma acá. La ocupación, el ADR y el promedio de socios del
   *  año no son la suma de los doce meses, y el servidor ya sabe calcularlos
   *  sobre el período: rehacerlo del lado de la pantalla sería una segunda
   *  definición de la misma cifra. */
  const cargarStats = useCallback(async () => {
    const unoNulo = async (id: string, d: number, h: number) =>
      getEstadisticasCierre(id, d, h).catch(() => null);
    const [meses, anios] = await Promise.all([
      // ⚠️ Los doce meses son de la versión elegida, no siempre de la primera:
      // si no, la hoja de estadísticas abriría un año distinto que las otras
      // seis y nadie lo notaría — los totales de año seguirían estando bien.
      Promise.all(DOCE.map(m => unoNulo(ids[Math.min(mesesDe, ids.length - 1)], m, m))),
      Promise.all(ids.map(id => unoNulo(id, 1, 12))),
    ]);
    return { meses, anios };
  }, [ids, mesesDe]);

  /** El reparto de las dos: el resumen del motor por versión, más los nombres de
   *  departamento, que viven en el endpoint de gasto. */
  const cargarReparto = useCallback(async () => {
    const [resumen, deptos] = await Promise.all([
      Promise.all(ids.map(id => getAllocationSummary(id).catch(() => null))),
      getGastoPorClase(ids, false).then(r => r.departamentos ?? {}).catch(() => ({})),
    ]);
    return { resumen, deptos };
  }, [ids]);

  const cargar = useCallback(async () => {
    if (!principal) return;
    setCargando(true);
    setError(null);
    try {
      if (vista === "pl") setPl(await getPLDetail(ambito, principal, otros));
      else if (vista === "aperturas") {
        const g = await getGastoPorClase(ids, true);
        setGastos({ escenarios: g.escenarios, departamentos: g.departamentos ?? {} });
      } else if (vista === "checkbooks" || vista === "detalle") {
        const abrir = vista === "detalle";
        setLibro({ [llaveLibro(clase, abrir)]:
          await getDetalleDeCelda(ids, clase, "", 0, abrir) });
      } else if (vista === "plantilla") {
        setPlantilla((await getPosiciones(ids)).escenarios);
      } else if (vista === "reparto") {
        setReparto(await cargarReparto());
      } else {
        setStats(await cargarStats());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, [vista, ambito, clase, principal, otros, ids, cargarStats, cargarReparto]);

  useEffect(() => { cargar(); }, [cargar]);

  // Sacar una versión de la comparación deja la elección apuntando a una que ya
  // no está: los meses saldrían vacíos y el año no. Vuelve a la principal.
  useEffect(() => {
    if (mesesDe >= ids.length) setMesesDe(0);
  }, [ids.length, mesesDe]);

  // Ni el reparto elegido puede ser uno que esta propiedad no tiene: la hoja
  // saldría «sin calcular» cuando lo que pasa es que ese reparto no existe acá.
  useEffect(() => {
    if (!reparto) return;
    const hay = tiposDeReparto(reparto.resumen);
    if (hay.length && !hay.includes(tipoReparto)) setTipoReparto(hay[0]);
  }, [reparto, tipoReparto]);

  const statsACuadro = useCallback(
    (s: { meses: (EstadisticasCierre | null)[]; anios: (EstadisticasCierre | null)[] },
     op: { ambito: string; compacto: boolean }) =>
      cuadroEstadisticas({ ...s, versiones: s.anios.map((a, i) => ({
        scenario_id: ids[i], escenario: a?.escenario })) }, escenarios, op),
    [ids, escenarios]);

  const cuadro: Cuadro | null = useMemo(() => {
    const op = { ambito, compacto, mesesDe };
    try {
      if (vista === "pl") return pl ? cuadroPlanning(pl, escenarios, op) : null;
      if (vista === "aperturas") {
        return gastos
          ? cuadroApertura(clase, gastos.escenarios, gastos.departamentos,
                           escenarios, op)
          : null;
      }
      if (vista === "checkbooks" || vista === "detalle") {
        const d = libro[llaveLibro(clase, vista === "detalle")];
        return d ? cuadroCheckbook(d, escenarios, op) : null;
      }
      if (vista === "plantilla") {
        return plantilla
          ? cuadroPosiciones(plantilla, escenarios, { ...op, metrica }) : null;
      }
      if (vista === "reparto") {
        return reparto
          ? cuadroReparto(tipoReparto,
              { versiones: reparto.resumen.map((_r, i) => ({
                  scenario_id: ids[i] })), ...reparto }, escenarios, op)
          : null;
      }
      return stats ? statsACuadro(stats, op) : null;
    } catch {
      return null;
    }
  }, [vista, pl, gastos, libro, plantilla, reparto, stats, clase, metrica,
      tipoReparto, escenarios, ambito, compacto, mesesDe, ids, statsACuadro]);

  /** Todas las hojas de una vista. Las usa tanto el botón de la vista como el
   *  del paquete completo, para que las dos bajen exactamente lo mismo. */
  const hojasDe = useCallback(async (v: string): Promise<Cuadro[]> => {
    const op = { compacto, ambito, mesesDe };
    const out: Cuadro[] = [];
    if (v === "pl") {
      for (const a of AMBITOS) {
        const d = a.id === ambito && pl ? pl
          : await getPLDetail(a.id, principal, otros).catch(() => null);
        if (d) out.push(cuadroPlanning(d, escenarios, { ...op, ambito: a.id }));
      }
    } else if (v === "aperturas") {
      let g = gastos;
      if (!g) {
        const r = await getGastoPorClase(ids, true);
        g = { escenarios: r.escenarios, departamentos: r.departamentos ?? {} };
      }
      for (const a of APERTURAS) {
        out.push(cuadroApertura(a.clase, g.escenarios, g.departamentos,
                                escenarios, op));
      }
    } else if (v === "checkbooks" || v === "detalle") {
      const abrir = v === "detalle";
      for (const a of APERTURAS) {
        const d = libro[llaveLibro(a.clase, abrir)]
          ?? await getDetalleDeCelda(ids, a.clase, "", 0, abrir).catch(() => null);
        // ⚠️ La clase que no tiene nada debajo de la cuenta NO baja dos veces.
        // Su hoja «con detalle» saldría idéntica a la normal, y dos hojas
        // iguales con nombres distintos hacen dudar de las dos.
        if (d && (!abrir || seAbre(d))) out.push(cuadroCheckbook(d, escenarios, op));
      }
    } else if (v === "plantilla") {
      const ps = plantilla ?? (await getPosiciones(ids)).escenarios;
      // Las DOS métricas: el FTE dice cuánta gente y el sueldo cuánto cuesta.
      // Quien revisa un presupuesto mira las dos, y una sola obliga a volver.
      for (const m of METRICAS_POSICION) {
        out.push(cuadroPosiciones(ps, escenarios, { ...op, metrica: m.id }));
      }
    } else if (v === "reparto") {
      const r = reparto ?? await cargarReparto();
      // ⚠️ Los tipos salen de los DATOS. Con la lista fija de dos, CWL bajaba
      // el paquete sin su reparto de Habitaciones ni el de salarios — plata que
      // se movió y que el libro no mencionaba.
      for (const t of tiposDeReparto(r.resumen)) {
        out.push(cuadroReparto(t,
          { versiones: r.resumen.map((_x, i) => ({ scenario_id: ids[i] })), ...r },
          escenarios, op));
      }
    } else {
      out.push(statsACuadro(stats ?? await cargarStats(), op));
    }
    return out;
  }, [compacto, ambito, mesesDe, pl, gastos, libro, plantilla, reparto, stats,
      principal, otros, ids, escenarios, cargarReparto, cargarStats, statsACuadro]);

  const nombreDelArchivo = (sufijo: string) => {
    const e = escenarios.find(s => s.id === principal);
    return `${sufijo}_${e?.year ?? ""}_${e?.type ?? ""}_${e?.version ?? ""}`;
  };

  /** Sólo la vista que se está mirando, con todas sus hojas. */
  async function bajar() {
    if (!principal) return;
    setBajando("vista");
    setError(null);
    try {
      const v = VISTAS.find(x => x.id === vista)?.rotulo ?? vista;
      await bajarCuadros(nombreDelArchivo(`Planning_${v}`), await hojasDe(vista));
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo bajar el Excel");
    } finally {
      setBajando("");
    }
  }

  /**
   * El BUDGET PACKAGE: las siete vistas en un solo libro.
   *
   * Owner, 2026-10-01: *«esto debe ser un Budget Package para revisión
   * rápida»*. Veintitrés hojas —P&L por ámbito, las cinco aperturas, los cinco
   * checkbooks, los cinco abiertos en sub-líneas, la plantilla en FTE y en
   * sueldo, los dos repartos y las estadísticas— con el índice adelante.
   *
   * ⚠️ Se arma con `hojasDe`, el MISMO armador del botón de cada vista. Un
   * paquete que junte las hojas por su cuenta sería una segunda definición de
   * cada una, y la que se manda a revisión es justamente ésta.
   */
  async function bajarPaquete() {
    if (!principal) return;
    setBajando("paquete");
    setError(null);
    try {
      const cuadros: Cuadro[] = [];
      for (const v of VISTAS) {
        try {
          cuadros.push(...await hojasDe(v.id));
        } catch {
          // Una vista que falla no se lleva el paquete entero: se avisa al
          // final y las demás bajan. Un libro de veintitrés hojas que no baja
          // por una es peor que uno de veintidós que sí.
          setError(e => (e ? `${e} · ` : "")
            + `no se pudo armar «${v.rotulo}»; el resto del paquete sí bajó`);
        }
      }
      if (!cuadros.length) throw new Error("no se pudo armar ninguna hoja");
      await bajarCuadros(nombreDelArchivo("Budget_Package"), cuadros);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo bajar el paquete");
    } finally {
      setBajando("");
    }
  }

  const btn = (activo: boolean): React.CSSProperties => ({
    padding: "5px 12px", fontSize: 12, fontWeight: 600, border: "none",
    cursor: activo ? "default" : "pointer",
    background: activo ? "var(--brand)" : "var(--bg-surface)",
    color: activo ? "#fff" : "var(--text-primary)",
  });
  const grupo: React.CSSProperties = {
    display: "inline-flex", borderRadius: 6, overflow: "hidden",
    border: "1px solid var(--border-medium)", flexWrap: "wrap",
  };

  return (
    <div style={{ padding: "18px 22px" }}>
      <IrA esc={principal} />

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
                    marginBottom: 12 }}>
        <h1 style={{ fontSize: 19, fontWeight: 700, margin: 0 }}>Budget Package</h1>
        <span style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
          doce meses de una versión · el año, de todas
        </span>

        <button onClick={bajarPaquete} disabled={!principal || !!bajando}
          style={{ padding: "6px 14px", fontSize: 12.5, borderRadius: 4,
                   fontWeight: 700, border: "none",
                   cursor: principal ? "pointer" : "not-allowed",
                   background: "var(--brand)", color: "#fff" }}>
          {bajando === "paquete" ? "Armando el paquete…"
            : "⬇ Budget Package (todo en un libro)"}
        </button>
        <button onClick={bajar} disabled={!cuadro || !!bajando}
          style={{ padding: "5px 12px", fontSize: 12, borderRadius: 4, fontWeight: 600,
                   border: "none", cursor: cuadro ? "pointer" : "not-allowed",
                   background: "var(--accent-excel)", color: "#fff" }}>
          {bajando === "vista" ? "Bajando…" : "⬇ Sólo esta vista"}
        </button>
      </div>

      <nav aria-label="Nivel" style={{ ...grupo, marginBottom: 12 }}>
        {VISTAS.map((v, i) => (
          <button key={v.id} onClick={() => setVista(v.id)} title={v.ayuda}
            style={{ ...btn(v.id === vista),
                     borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
            {v.rotulo}
          </button>
        ))}
      </nav>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
                    marginBottom: 14 }}>
        <select value={principal} onChange={e => setPrincipal(e.target.value)}
          className="fin-input" style={{ fontSize: 12.5, padding: "5px 8px" }}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.year} · {s.type} {s.version}</option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>vs</span>
        {comparar.map((c, i) => (
          <select key={i} value={c}
            onChange={e => setComparar(v => v.map((x, j) => (j === i ? e.target.value : x)))}
            className="fin-input" style={{ fontSize: 12.5, padding: "5px 8px" }}>
            <option value="">{i === 0 ? "— sin comparación —" : "— +versión —"}</option>
            {escenarios
              .filter(s => s.id !== principal
                           && !comparar.some((o, j) => o === s.id && j !== i))
              .map(s => (
                <option key={s.id} value={s.id}>{s.year} · {s.type} {s.version}</option>
              ))}
          </select>
        ))}
        <label style={{ fontSize: 12, display: "inline-flex", alignItems: "center",
                        gap: 5, color: "var(--text-secondary)" }}>
          <input type="checkbox" checked={compacto}
                 onChange={e => setCompacto(e.target.checked)} />
          Esconder las líneas en cero
        </label>

        {/* ⚠️ Los doce meses son de UNA versión; el año, de todas. Esto elige
            cuál abre su estacionalidad — el Forecast 2026 o el Budget 2026 en
            vez del presupuesto que se está armando. La fórmula `=SUM(B:M)` se
            muda con la elección: la columna de año que suma sus meses es la de
            esta versión. */}
        {ids.length > 1 && (
          <label style={{ fontSize: 12, display: "inline-flex", alignItems: "center",
                          gap: 5, color: "var(--text-secondary)" }}>
            Los doce meses, de
            <select value={mesesDe} onChange={e => setMesesDe(Number(e.target.value))}
              className="fin-input" style={{ fontSize: 12.5, padding: "4px 6px" }}>
              {ids.map((id, i) => {
                const e2 = escenarios.find(x => x.id === id);
                return (
                  <option key={id} value={i}>
                    {e2 ? `${e2.year} · ${e2.type} ${e2.version}` : id.slice(0, 8)}
                  </option>
                );
              })}
            </select>
          </label>
        )}
      </div>

      {/* El segundo eje depende del nivel. Las estadísticas no tienen. */}
      {vista === "pl" && (
        <nav aria-label="Ámbito" style={{ ...grupo, marginBottom: 12 }}>
          {AMBITOS.map((a, i) => (
            <button key={a.id} onClick={() => setAmbito(a.id)} title={a.ayuda}
              style={{ ...btn(a.id === ambito),
                       borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
              {a.rotulo}
            </button>
          ))}
        </nav>
      )}
      {(vista === "aperturas" || vista === "checkbooks" || vista === "detalle") && (
        <nav aria-label="Clase" style={{ ...grupo, marginBottom: 12 }}>
          {APERTURAS.map((a, i) => (
            <button key={a.clase} onClick={() => setClase(a.clase)} title={a.eje}
              style={{ ...btn(a.clase === clase),
                       borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
              {a.rotulo}
            </button>
          ))}
        </nav>
      )}
      {vista === "plantilla" && (
        <nav aria-label="Métrica" style={{ ...grupo, marginBottom: 12 }}>
          {METRICAS_POSICION.map((m, i) => (
            <button key={m.id} onClick={() => setMetrica(m.id)} title={m.ayuda}
              style={{ ...btn(m.id === metrica),
                       borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
              {m.rotulo}
            </button>
          ))}
        </nav>
      )}
      {vista === "reparto" && reparto && (
        <nav aria-label="Reparto" style={{ ...grupo, marginBottom: 12 }}>
          {tiposDeReparto(reparto.resumen).map((t, i) => {
            const m = REPARTOS.find(r => r.id === t);
            return (
              <button key={t} onClick={() => setTipoReparto(t)} title={m?.fuente}
                style={{ ...btn(t === tipoReparto),
                         borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
                {m?.rotulo ?? t}
              </button>
            );
          })}
        </nav>
      )}

      {/* ⚠️ Las clases que NO tienen un nivel debajo de la cuenta se dicen, no
          se dejan en blanco: una hoja vacía se lee como «falta el dato». */}
      {vista === "detalle" && (clase === "cost" || clase === "revenue") && (
        <div style={{ padding: 10, borderRadius: 5, fontSize: 12.5, marginBottom: 12,
                      background: "var(--bg-surface)",
                      border: "1px solid var(--border-medium)" }}>
          {clase === "cost"
            ? "El costo de ventas no tiene sub-líneas en la base: lo que explica "
              + "cada cuenta es su DRIVER («28% de FOOD»), que se ve en el "
              + "checkbook de costos."
            : "El ingreso ya está en su nivel más fino: la cuenta —o la línea— "
              + "es el último nivel que el presupuesto guarda."}
          {" "}Partirlas en sub-líneas que nadie presupuestó haría que el reporte
          abra más de lo que se decidió.
        </div>
      )}

      {error && (
        <div style={{ padding: 10, borderRadius: 5, fontSize: 12.5, marginBottom: 12,
                      background: "var(--bg-warning)" }}>{error}</div>
      )}
      {cargando && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>Cargando…</div>
      )}

      {!cargando && cuadro && (
        <>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 10 }}>
            {cuadro.subtitulo}
          </div>
          <Tabla cuadro={cuadro} />
        </>
      )}
      {!cargando && !cuadro && !error && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Sin datos para esta vista.
        </div>
      )}
    </div>
  );
}
