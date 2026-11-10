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
  getGastoPorClase, getPLDetail, getPLPorCategoria, getPosiciones, getScenarios,
  type AllocationSummary, type DetalleCelda, type EstadisticasCierre,
  type GastoEscenario, type PLDetail, type PLPorCategoria,
  type PosicionesVersion, type Scenario,
} from "@/lib/api";
import { bajarCuadros, type Cuadro } from "@/lib/exportCuadro";
import { HOTEL_ID } from "@/lib/hotel";
import {
  APERTURAS, cuadroApertura, cuadroCheckbook, cuadroEstadisticas, cuadroPlanning,
  cuadroPlanningPorCategoria,
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

/**
 * Los dos formatos del P&L. Owner, 2026-11-09: *«necesito que el P&L tenga 2
 * versiones de formato»*.
 *
 * `usali` agrupa por DEPARTAMENTO y mezcla planilla, costo y opex en un solo
 * renglón de gasto; sirve para cotejar contra su libro y contra cualquier hotel.
 * `categoria` agrupa por NATURALEZA del gasto y abre los departamentos adentro:
 * contesta «¿cuánta planilla tiene Cocina?», que en el otro hay que ir a buscar
 * a otra pantalla.
 *
 * Los dos dan el MISMO GOP — el endpoint lo mide y lo devuelve en `cuadre`.
 */
const FORMATOS = [
  { id: "usali", rotulo: "USALI", ayuda: "Por departamento, como siempre" },
  { id: "categoria", rotulo: "Por categoría",
    ayuda: "Ingreso − Costo − Planilla − OPEX = GOP" },
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
  /** Cuál de los dos formatos del P&L se está mirando. */
  const [formato, setFormato] = useState<string>("usali");
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
  const [plCat, setPlCat] = useState<PLPorCategoria | null>(null);
  /** Por qué no se pudo traer el formato 2, si no se pudo.
   *
   *  ⚠️ Antes el fallo se tragaba con un `.catch(() => null)` y la pantalla
   *  decía «Sin datos para esta vista» — que es lo mismo que dice un escenario
   *  vacío. El 2026-11-09, con el frontend ya desplegado y el backend todavía
   *  no (son servicios separados en Railway), el sub-tab salía en blanco y no
   *  había forma de saber si faltaba el dato o faltaba el deploy. */
  const [errorCat, setErrorCat] = useState<string | null>(null);
  const [gastos, setGastos] = useState<
    { escenarios: GastoEscenario[]; departamentos: Record<string, string> } | null>(null);
  const [libro, setLibro] = useState<Record<string, DetalleCelda>>({});
  const [plantilla, setPlantilla] = useState<PosicionesVersion[] | null>(null);
  const [reparto, setReparto] = useState<
    { resumen: (AllocationSummary | null)[]; deptos: Record<string, string> } | null>(null);
  const [stats, setStats] = useState<
    { mesesPorVersion: (EstadisticasCierre | null)[][];
      anios: (EstadisticasCierre | null)[] } | null>(null);

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
    const [mesesPorVersion, anios] = await Promise.all([
      // ⚠️ Los doce meses de CADA versión, no sólo de la elegida: desde que el
      // cuadro abre varias a la derecha, pedir una sola dejaba esas columnas en
      // blanco justo en la hoja donde el owner mira la estacionalidad.
      Promise.all(ids.map(id => Promise.all(DOCE.map(m => unoNulo(id, m, m))))),
      Promise.all(ids.map(id => unoNulo(id, 1, 12))),
    ]);
    return { mesesPorVersion, anios };
  }, [ids]);

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
      if (vista === "pl") {
        // ⚠️ Las tres a la vez, no una después de la otra: son endpoints
        // distintos y encadenarlos multiplicaría la espera de la vista que más
        // se abre. Si las estadísticas fallan, el P&L igual se dibuja — por eso
        // `cargarStats` ya devuelve `null` por versión en vez de tirar.
        //
        // Los DOS formatos se piden siempre, aunque sólo se dibuje uno: el
        // Excel los baja juntos, y cambiar de sub-tab sin esperar es la mitad
        // de para qué sirve un sub-tab.
        const [d, c, s] = await Promise.all([
          getPLDetail(ambito, principal, otros),
          // Se tolera el fallo para que el P&L de siempre igual se dibuje,
          // pero el motivo se GUARDA: un error silencioso acá se lee como
          // «este escenario no tiene datos», que es otra cosa.
          getPLPorCategoria(ambito, principal, otros)
            .then(r => { setErrorCat(null); return r; })
            .catch((e: unknown) => {
              setErrorCat(e instanceof Error ? e.message : "no se pudo cargar");
              return null;
            }),
          cargarStats().catch(() => null),
        ]);
        setPl(d);
        setPlCat(c);
        setStats(s);
      } else if (vista === "aperturas") {
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
    (s: { mesesPorVersion: (EstadisticasCierre | null)[][];
          anios: (EstadisticasCierre | null)[] },
     op: { ambito: string; compacto: boolean; mesesDe?: number; extras?: number[] }) =>
      cuadroEstadisticas({ ...s, versiones: s.anios.map((a, i) => ({
        scenario_id: ids[i], escenario: a?.escenario })) }, escenarios, op),
    [ids, escenarios]);

  /** Las versiones que abren sus doce meses a la DERECHA: todas las elegidas
   *  menos la que ya los abre a la izquierda. Owner, 2026-10-05: *«después de
   *  la línea roja … doce meses, y con una columna de espacio, otros doce»*. */
  const extras = useMemo(
    () => ids.map((_id, i) => i).filter(i => i !== mesesDe), [ids, mesesDe]);

  /**
   * Las estadísticas, encima del P&L.
   *
   * Owner, 2026-10-08, señalando el encabezado del Budget Package: *«todo ese
   * set de stats debe aparecer acá arriba para todas las versiones… pero no
   * aparece»*. Estaban, pero sólo en su propia pestaña.
   *
   * ⚠️ **Es un cuadro APARTE, no filas metidas en el del P&L.** `cuadroPlanning`
   * cuelga `suma_de` y `combina_filas` por ÍNDICE DE FILA, y su propio
   * comentario lo advierte: un índice que apunta a otra fila hace que el
   * exportador descarte la fórmula **sin decir nada**. Anteponer filas habría
   * corrido los de las seis líneas de la cascada —NET PROFIT incluido— y la
   * hoja habría perdido sus fórmulas más miradas en silencio.
   *
   * Las columnas salen iguales porque las dos pasan por `armarCuadro` con las
   * mismas `versiones`, `mesesDe` y `extras`.
   */
  const cuadroStats: Cuadro | null = useMemo(() => {
    if (vista !== "pl" || !stats) return null;
    try {
      return statsACuadro(stats, { ambito, compacto, mesesDe, extras });
    } catch {
      return null;
    }
  }, [vista, stats, statsACuadro, ambito, compacto, mesesDe, extras]);

  // Cambiar a Club con «Por categoría» puesto dejaría la pantalla pidiendo un
  // formato que ese ámbito no tiene. Vuelve sola al de siempre.
  useEffect(() => {
    if (ambito === "club" && formato !== "usali") setFormato("usali");
  }, [ambito, formato]);

  const cuadro: Cuadro | null = useMemo(() => {
    const op = { ambito, compacto, mesesDe, extras };
    try {
      if (vista === "pl") {
        if (formato === "categoria") {
          // ⚠️ Sólo la PRINCIPAL decide. Si su resta no da el mismo GOP que el
          // formato USALI, no se dibuja nada: la hoja es de ese escenario.
          //
          // Pero una versión COMPARADA que no cuadra NO se lleva el cuadro por
          // delante. Owner, 2026-11-09: bajó el paquete y las dos hojas v2
          // habían desaparecido porque una de las versiones con las que
          // comparaba no cerraba. Perder la vista entera por una columna
          // secundaria es desproporcionado — el subtítulo la nombra.
          if (plCat && plCat.cuadre?.[0] && !plCat.cuadre[0].cuadra) return null;
          return plCat ? cuadroPlanningPorCategoria(plCat, escenarios, op) : null;
        }
        return pl ? cuadroPlanning(pl, escenarios, op) : null;
      }
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
  }, [vista, pl, plCat, formato, gastos, libro, plantilla, reparto, stats, clase, metrica,
      tipoReparto, escenarios, ambito, compacto, mesesDe, extras, ids, statsACuadro]);

  /** Todas las hojas de una vista. Las usa tanto el botón de la vista como el
   *  del paquete completo, para que las dos bajen exactamente lo mismo. */
  const hojasDe = useCallback(async (v: string): Promise<Cuadro[]> => {
    const op = { compacto, ambito, mesesDe, extras };
    const out: Cuadro[] = [];
    if (v === "pl") {
      // Los DOS formatos del P&L, uno detrás del otro por ámbito. Owner,
      // 2026-11-09: *«lo pones como un sub tab pero también lo pones en el
      // excel como versión 2»*.
      //
      // ⚠️ El formato 2 se agrega sólo si el endpoint contesta. Si falla, el
      // paquete sale con el P&L de siempre en vez de no salir: perder una hoja
      // nueva es molesto, perder el paquete entero por ella es peor.
      for (const a of AMBITOS) {
        const d = a.id === ambito && pl ? pl
          : await getPLDetail(a.id, principal, otros).catch(() => null);
        if (d) out.push(cuadroPlanning(d, escenarios, { ...op, ambito: a.id }));
        // El Club no lleva este formato (ver el sub-tab): pedirlo sería un 422
        // seguro. Y de los otros dos sólo entra la hoja que CUADRA — una hoja
        // en el libro del owner que no cierra contra su propio GOP es la clase
        // de cosa que se copia a una presentación sin volver a mirarla.
        if (a.id !== "club") {
          const c = a.id === ambito && plCat ? plCat
            : await getPLPorCategoria(a.id, principal, otros).catch(() => null);
          // Igual que la pantalla: manda la PRINCIPAL. Una comparada que no
          // cierra queda nombrada en el subtítulo de la hoja, no borra el libro.
          if (c && (!c.cuadre?.[0] || c.cuadre[0].cuadra))
            out.push(cuadroPlanningPorCategoria(c, escenarios, { ...op, ambito: a.id }));
        }
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
  }, [compacto, ambito, mesesDe, extras, pl, plCat, formato, gastos, libro, plantilla, reparto, stats,
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
      {/* Los dos formatos del MISMO P&L. Owner, 2026-11-09: *«lo pones como
        * un sub tab»*. Va debajo del ámbito porque es un corte más fino: se
        * elige primero de qué hotel y después cómo mirarlo. */}
      {/* ⚠️ En el Club NO se ofrece: su P&L es de un solo departamento —va
        * Ingreso → Planilla → Opex → Net Profit, sin GOP—, así que la apertura
        * por naturaleza no tiene nada que abrir. Ofrecer un botón que sólo
        * puede fallar es peor que no ofrecerlo. */}
      {vista === "pl" && ambito !== "club" && (
        <nav aria-label="Formato" style={{ ...grupo, marginBottom: 12 }}>
          {FORMATOS.map((f, i) => (
            <button key={f.id} onClick={() => setFormato(f.id)} title={f.ayuda}
              style={{ ...btn(f.id === formato),
                       borderLeft: i ? "1px solid var(--border-medium)" : "none" }}>
              {f.rotulo}
            </button>
          ))}
          {/* El cuadre, al lado del sub-tab y no escondido en el cuadro: si el
            * GOP de los dos formatos deja de coincidir hay que verlo ANTES de
            * leer los números, no después. */}
          {formato === "categoria" && plCat && (
            <span style={{ marginLeft: 12, fontSize: 11.5, alignSelf: "center",
                           color: (plCat.cuadre ?? []).every(c => c.cuadra)
                             ? "var(--positive)" : "var(--negative)" }}>
              {(plCat.cuadre ?? []).every(c => c.cuadra)
                ? "✓ mismo GOP que el formato USALI"
                : "⚠ el GOP NO coincide con el formato USALI"}
            </span>
          )}
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
          {cuadroStats && (
            <div style={{ marginBottom: 18 }}>
              <Tabla cuadro={cuadroStats} />
            </div>
          )}
          <Tabla cuadro={cuadro} />
        </>
      )}
      {/* ⚠️ Un fallo del formato 2 NO se puede ver igual que un escenario
        * vacío: lo primero se arregla recargando o esperando el deploy, lo
        * segundo no se arregla. Decir cuál es lo único que distingue las dos. */}
      {/* No cuadra: se dice cuál versión y por cuánto. Un número concreto es
        * lo único con lo que se puede empezar a buscar. */}
      {!cargando && !cuadro && !error && vista === "pl" && formato === "categoria"
        && plCat && plCat.cuadre?.[0] && !plCat.cuadre[0].cuadra && (
        <div style={{ fontSize: 13, color: "var(--negative)", maxWidth: 680 }}>
          No se muestra: la resta no da el mismo GOP que el formato USALI.
          <ul style={{ margin: "8px 0 0 18px", padding: 0 }}>
            {(plCat.cuadre ?? []).filter(c => !c.cuadra).map(c => {
              const v = escenarios.find(e => e.id === c.scenario_id);
              return (
                <li key={c.scenario_id} style={{ marginBottom: 3 }}>
                  {v ? `${v.year} · ${v.type} ${v.version}` : c.scenario_id.slice(0, 8)}
                  {": "}
                  <span className="mono">
                    ${c.gop_resta.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>{" contra "}
                  <span className="mono">
                    ${c.gop_motor.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>{" — diferencia "}
                  <span className="mono">
                    ${c.diferencia.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>
                </li>
              );
            })}
          </ul>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8 }}>
            El formato USALI de al lado sí cuadra y se puede usar. Sacando esa
            versión de la comparación, este formato vuelve a mostrarse.
          </div>
        </div>
      )}
      {!cargando && !cuadro && !error && vista === "pl"
        && formato === "categoria" && errorCat && (
        <div style={{ fontSize: 13, color: "var(--negative)", maxWidth: 620 }}>
          No se pudo traer el P&amp;L por categoría: {errorCat}
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6 }}>
            El formato USALI de al lado sigue funcionando. Si esto acaba de
            desplegarse, recargue la página: el frontend y el backend son
            servicios separados y el de la pantalla puede llegar primero.
          </div>
        </div>
      )}
      {!cargando && !cuadro && !error
        && !(vista === "pl" && formato === "categoria"
             && (errorCat
                 || (plCat && plCat.cuadre?.[0] && !plCat.cuadre[0].cuadra))) && (
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Sin datos para esta vista.
        </div>
      )}
    </div>
  );
}
