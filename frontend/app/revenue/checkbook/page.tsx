"use client";
import { usePlanningScenario, usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
// ⚠️ El parser COMPARTIDO: `numeroDeExcel` mira la POSICIÓN de la coma para
// saber si es decimal o separador de miles. El que vivía acá la borraba
// siempre, así que un número en formato español entraba multiplicado.
import { manejarPegado, repartirPegado, numeroDeExcel } from "@/lib/pegarGrilla";
import { elegir } from "@/lib/escenarioPreferido";
import { SET_VILLAS, SET_RESIDENCIAS } from "@/lib/roomSet";
import { hacerTarifaNeta } from "@/lib/tarifaNeta";
import AvisoLineasObligatorias from "@/components/AvisoLineasObligatorias";
import { useTranslations } from "next-intl";
import { money2 } from "@/lib/fmt";
import { Fragment, useEffect, useState, useCallback } from "react";
import { HOTEL_ID } from "@/lib/hotel";
import { bajarCuadros, type Cuadro, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import {
  getScenarios, getRevenueCheckbook, saveRevenueCheckbook, setRevenueSource,
  getRoomTypes, getOccupancyPct, getRackRates, getChannelsConfig,
  getDriverRatesSeed, getPackageDriverRates, getPaxGrid, getNetRates,
  type Scenario, type RevenueCheckbookRow, type RevenueSource, type RoomType,
  type PackageDriverRates,
  type RevenueBulkRow, type MonthKey,
} from "@/lib/api";
import { recalcularYContar } from "@/lib/recalcular";
import IrA from "@/components/IrA";

const MONTHS_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const MONTH_KEYS: MonthKey[] = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"];

function daysInMonth(year: number, month1: number): number {
  return new Date(year, month1, 0).getDate();
}

/** La clave sintetica de la familia Rooms: no es un departamento. */
const STANDARD = "STANDARD";

/** Lo que se puede medir de un conjunto de categorias. */
interface Medible {
  available: number[]; occupied: number[]; roomRev: number[];
  /** Pax-noche de CADA mes = suma por villa (noches ocupadas x su pax del mes).
   *
   *  (!) Antes esto era UN numero (`pax_per_night` del escenario) y se
   *  multiplicaba por las noches. El motor nunca hizo eso: suma
   *  `rooms_occupied x rc.pax_per_room` villa por villa y mes por mes. Mientras
   *  el pax fue 1,80 en todas las tarjetas las dos cuentas daban igual y la
   *  diferencia no existia. El dia que el owner puso 1,85 solo en enero,
   *  febrero y marzo --el pax cambia por temporada-- la pantalla siguio
   *  calculando con 1,80 los doce meses y el ingreso del P&L dejo de coincidir
   *  con el "Total Pax" que ella misma mostraba. */
  paxNights: number[];
}

/** Un SET medido aparte: Standard, Villas, Residencias.
 *
 *  Owner, 2026-10-27: *"necesito ver esto rooms estandar y villas separado..
 *  estadisticas separadas e ingreso separado"* y *"la ocupacion tambien que
 *  este separado"*.
 *
 *  (!) Es una APERTURA, no una suma: las filas del set parten la misma plata y
 *  las mismas noches de la fila de arriba. Por eso van indentadas y en gris --
 *  sumarlas con el total daria el doble. El P&L sigue viendo UNA linea de
 *  Rooms, porque 0115 y 0116 cuelgan de 0110. */
interface SetRooms extends Medible { key: string; nombre: string; }

interface RoomStats extends Medible {
  netFactor: number[];     // factor neto de canales por mes
  /** Vacio cuando hay un solo set: repetir la fila entera no abre nada. */
  sets: SetRooms[];
}

// Tarifas del paquete Classic (rack, se les aplica el net factor de canales).
// Food = Full Board / pax / noche · Tours = San Pedrillo + Caño / pax / estadía ·
// Transport = traslado / pax / estadía.
//
// YA NO ESTÁN ESCRITAS ACÁ. Eran nueve números fijos dentro de esta pantalla y
// son el producto de Corcovado —traslado Sierpe/Drake, San Pedrillo, Isla del
// Caño—: viajaban en el bundle, así que una propiedad nueva abría este checkbook
// con las tarifas de otro hotel y a un clic de guardarlas. Ahora vienen de
// `backend/app/seed_data/<HOTEL_ID>/driver_rates.json`.
//
// Sin semilla el botón queda apagado: llenar doce meses con ceros se ve igual
// que llenarlos bien, y eso es peor que no llenar nada.
const SIN_TARIFAS = {
  food: 0, tours: 0, transport: 0, nightsPerStay: 1, bevRatio: 0,
  retailPct: 0, innoceanaPct: 0, sustRate: 0, sustNonPay: 0,
};
type DriverRatesUI = typeof SIN_TARIFAS;

const num = numeroDeExcel;
function fmtUsd(v: string | number): string {
  const n = typeof v === "string" ? num(v) : v;
  if (!n) return "—";
  const s = "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${s})` : s;
}
function rowTotal(r: RevenueCheckbookRow): number {
  return MONTH_KEYS.reduce((s, mk) => s + num(r[mk]), 0);
}

const btnStyle = (enabled: boolean): React.CSSProperties => ({
  padding: "7px 16px", fontSize: 13, borderRadius: 5, fontWeight: 600,
  cursor: enabled ? "pointer" : "not-allowed", border: "none",
  background: enabled ? "var(--brand)" : "var(--bg-surface)",
  color: enabled ? "#fff" : "var(--text-disabled)",
});

export default function RevenueCheckbookPage() {
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MONTHS_FALLBACK;
  const t = useTranslations("revCheckbook");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [rows, setRows] = useState<RevenueCheckbookRow[]>([]);
  const [stats, setStats] = useState<RoomStats | null>(null);
  const [source, setSource] = useState<RevenueSource>("drivers");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recalc, setRecalc] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rates, setRates] = useState<DriverRatesUI>(SIN_TARIFAS);
  // De dónde salieron las tarifas de arriba, para poder decirlo en pantalla.
  // Sin esto, un recuadro en cero se ve igual venga del paquete o de la nada.
  const [pkgRates, setPkgRates] = useState<PackageDriverRates | null>(null);

  // Las tarifas de ESTA propiedad. Si no trae, el botón queda apagado.
  //
  // ⚠️ La semilla es FIJA POR HOTEL y las inclusiones del paquete viven por
  // ESCENARIO. Owner, 2026-10-22: *«llena esto en forma automática de la vista
  // anterior»*. En el BUDGET Working 2027 la semilla decía Tours 342 y la
  // pantalla mostraba 0, porque alguien lo había editado a mano y la semilla no
  // tiene dónde guardar eso. Por eso la semilla es el PISO y el paquete del
  // escenario la pisa (efecto de abajo).
  useEffect(() => {
    (async () => {
      try {
        const s = await getDriverRatesSeed();
        const r = s.tarifas ?? {};
        if (!s.seeded) return;
        setRates({
          food: r.food ?? 0, tours: r.tours ?? 0, transport: r.transport ?? 0,
          nightsPerStay: r.nights_per_stay ?? 1, bevRatio: r.bev_ratio ?? 0,
          retailPct: r.retail_pct ?? 0, innoceanaPct: r.innoceana_pct ?? 0,
          sustRate: r.sust_rate ?? 0, sustNonPay: r.sust_non_pay ?? 0,
        });
      } catch { /* sin semilla: el botón queda apagado y la pantalla lo dice */ }
    })();
  }, []);

  // El paquete DEL ESCENARIO manda sobre la semilla del hotel.
  //
  // Solo pisa las cuatro que el paquete sabe (Food, Tours, Transporte,
  // Sustainability) y las noches por estadía. Bebidas, Retail, Innoceana y el
  // «% que no paga» no son inclusiones: no tienen de dónde salir acá y se
  // quedan como estaban. Pisarlas con cero sería peor que no tocarlas.
  useEffect(() => {
    if (!scenarioId) return;
    (async () => {
      try {
        const p = await getPackageDriverRates(scenarioId);
        setPkgRates(p);
        if (!p.disponible) return;
        const tr = p.tarifas;
        setRates(r => ({
          ...r,
          food: tr.food ?? r.food,
          tours: tr.tours ?? r.tours,
          transport: tr.transport ?? r.transport,
          sustRate: tr.sust_rate ?? r.sustRate,
          nightsPerStay: tr.nights_per_stay || r.nightsPerStay,
        }));
      } catch { setPkgRates(null); }
    })();
  }, [scenarioId]);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const budget = elegir(all, "budget") ?? all[0];
        if (!budget) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarioId(sharedScenarioOr(budget.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : t("errorLoadingScenarios"));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const load = useCallback(async (sid: string) => {
    setLoading(true); setMsg(null);
    try {
      const [cb, rt, occ, rack, ch] = await Promise.all([
        getRevenueCheckbook(sid), getRoomTypes(HOTEL_ID, sid),
        getOccupancyPct(sid), getRackRates(sid), getChannelsConfig(sid),
      ]);
      // El pax por villa × mes, que es lo que multiplica el motor. Si no viene,
      // se cae al del escenario — pero se cae a un número que al menos existe,
      // no a un 1,8 escrito acá.
      const paxGrid = await getPaxGrid(sid).catch(() => null);
      // La NETA guardada. Se pide aparte y tolerando el fallo a proposito: si
      // el endpoint cae, la pantalla sigue viva con la formula de siempre en
      // vez de quedarse en blanco.
      const netRates = await getNetRates(sid).catch(() => null);
      setRows(cb.lines.map(l => ({ ...l, ...Object.fromEntries(MONTH_KEYS.map(mk => [mk, money2(l[mk])])) })));
      setSource(cb.source);

      // KPIs de Rooms desde los drivers (mismo calculo que Total Revenue)
      const year = occ.year;
      const closed = new Set(rt.closed_months);
      const unitsById = Object.fromEntries(rt.room_types.map(r => [r.id, r.units]));
      const nf = ch.net_factor.map(v => parseFloat(v) || 0);
      const rackById = Object.fromEntries(rack.rooms.map(r => [r.room_type_id, MONTH_KEYS.map(mk => parseFloat(r[mk]) || 0)]));

      // La tarifa que DE VERDAD usa el motor. Ver `lib/tarifaNeta`: con la
      // formula `rack x factor` las villas valian $0 aca y $1.700 la noche en
      // el P&L, y "Fill from drivers" escribia Room Revenue sin ellas.
      const tarifaNeta = hacerTarifaNeta(netRates, rackById, nf);

      const paxFallback = parseFloat(rt.pax_per_night) || 1.8;
      const paxById: Record<string, number[]> = Object.fromEntries(
        (paxGrid?.filas ?? []).map(f => [f.room_type_id,
          f.meses.map(c => parseFloat(c.pax) || paxFallback)]));

      /** Mide un conjunto de categorias. `ids = null` es el hotel entero.
       *
       *  Una sola cuenta para las cinco metricas y para los tres sets: si cada
       *  bloque se calculara por su lado, la suma de los sets podria dejar de
       *  dar el total sin que nada lo avise. */
      const medir = (ids: Set<string> | null): Medible => {
        const mia = (id: string) => ids === null || ids.has(id);
        const noches = (mi: number) => occ.rooms.map(r => {
          if (closed.has(mi + 1) || !mia(r.room_type_id)) return { id: r.room_type_id, n: 0 };
          const u = unitsById[r.room_type_id] ?? 0;
          return { id: r.room_type_id, n: (parseFloat(r[MONTH_KEYS[mi]]) || 0) * u * daysInMonth(year, mi + 1) };
        });
        return {
          available: MONTHS.map((_m, mi) => rt.room_types.reduce((acc, r) =>
            acc + (closed.has(mi + 1) || !mia(r.id) ? 0 : r.units * daysInMonth(year, mi + 1)), 0)),
          occupied: MONTHS.map((_m, mi) => noches(mi).reduce((acc, x) => acc + x.n, 0)),
          roomRev: MONTHS.map((_m, mi) => noches(mi).reduce((acc, x) => acc + x.n * tarifaNeta(x.id, mi), 0)),
          paxNights: MONTHS.map((_m, mi) => noches(mi).reduce((acc, x) =>
            acc + x.n * (paxById[x.id]?.[mi] ?? paxFallback), 0)),
        };
      };

      // Los SET. Una categoria sin `dept_code` se queda en Standard, que es la
      // familia Rooms: lo que NO fue asignado a un set no desaparece de la
      // vista, se ve donde se nota que falta asignarlo.
      const NOMBRE_SET: Record<string, string> = {
        [SET_VILLAS]: "Villas", [SET_RESIDENCIAS]: "Residencias",
      };
      const ORDEN = [STANDARD, SET_VILLAS, SET_RESIDENCIAS];
      const porSet = new Map<string, RoomType[]>();
      for (const r of rt.room_types) {
        const dc = (r.dept_code || "").trim();
        const k = dc === SET_VILLAS || dc === SET_RESIDENCIAS ? dc : STANDARD;
        porSet.set(k, [...(porSet.get(k) ?? []), r]);
      }
      const sets: SetRooms[] = [...porSet.entries()]
        // Un set sin unidades solo agregaria una fila de ceros.
        .filter(([, tipos]) => tipos.reduce((acc, t) => acc + (t.units || 0), 0) > 0)
        .sort((a, b) => ORDEN.indexOf(a[0]) - ORDEN.indexOf(b[0]))
        .map(([k, tipos]) => ({
          key: k,
          nombre: k === STANDARD ? "Standard" : (NOMBRE_SET[k] ?? k),
          ...medir(new Set(tipos.map(t => t.id))),
        }));

      setStats({ ...medir(null), netFactor: nf, sets: sets.length > 1 ? sets : [] });
      setDirty(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (scenarioId) load(scenarioId); }, [scenarioId, load]);

  function setCell(rowIdx: number, mk: MonthKey, value: string) {
    setRows(prev => prev.map((r, i) => i === rowIdx ? { ...r, [mk]: value } : r));
    setDirty(true);
  }

  // Excel-style paste: distribute a tab/newline block starting at (rowIdx, monthIdx).
  /** Pegar un bloque de Excel.
   *
   * Usa el enganche COMUN (`manejarPegado` + `repartirPegado`) y no una copia
   * local. Owner, 2026-10-22: pegar ya funcionaba, pero solo si uno
   * seleccionaba el rectangulo EXACTO de numeros. Nadie copia asi: se arrastra
   * sobre la tabla de Excel y viene la columna de nombres y la fila de meses.
   * Eso entraba como dato y los valores quedaban corridos una columna — con un
   * resultado que se ve plausible y nada que avise. El recorte de rotulos vive
   * en `manejarPegado`, asi que esta pantalla lo hereda.
   */
  function handlePaste(rowIdx: number, monthIdx: number, e: React.ClipboardEvent) {
    manejarPegado(e, bloque => {
      setRows(prev => {
        const next = prev.map(r => ({ ...r }));
        repartirPegado(bloque, rowIdx, monthIdx, next.length, MONTH_KEYS.length,
          (f, c, valor) => { next[f][MONTH_KEYS[c]] = money2(valor); });
        return next;
      });
      setDirty(true);
    });
  }

  async function handleSave() {
    if (!scenarioId) return;
    setSaving(true); setMsg(null); setError(null);
    try {
      const payload: RevenueBulkRow[] = rows.map(r => ({
        line: r.line,
        ...(Object.fromEntries(MONTH_KEYS.map(mk => [mk, num(r[mk])])) as Record<MonthKey, number>),
      }));
      const res = await saveRevenueCheckbook(scenarioId, payload);
      setDirty(false);
      setMsg(t("savedN", { n: res.saved }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorSaving"));
    } finally {
      setSaving(false);
    }
  }

  async function toggleSource(next: RevenueSource) {
    if (!scenarioId || next === source) return;
    setSource(next);
    try {
      await setRevenueSource(scenarioId, next);
      setMsg(next === "checkbook" ? t("sourceCheckbookMsg") : t("sourceDriversMsg"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : tc("error"));
    }
  }

  async function handleRecalc() {
    if (!scenarioId) return;
    setRecalc(true); setMsg(null);
    try {
      if (dirty) await handleSave();
      const aviso = await recalcularYContar(scenarioId, t("plRecalculated"));
      setMsg(aviso);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("errorRecalc"));
    } finally {
      setRecalc(false);
    }
  }

  // ¿Hay con qué llenar? No importa si vino de la semilla o lo digitó el
  // usuario: lo que no puede pasar es llenar doce meses de ceros, que en
  // pantalla se ve idéntico a haberlos llenado bien.
  const hayTarifas = rates.food > 0 || rates.tours > 0 || rates.transport > 0
    || rates.sustRate > 0 || rates.retailPct > 0 || rates.innoceanaPct > 0;

  // Llena Room/Food/Tours/Transport desde los drivers (ocupación → pax-noche).
  // Food = per pax/noche → cantidad = pax-noche. Tours/Transport = per pax/estadía
  // → cantidad = estadías = pax-noche / noches por estadía. Tarifa × net factor del mes.
  function fillFromDrivers() {
    if (!stats || sel?.is_locked) return;
    if (!hayTarifas) {
      setError(t("noRatesToFill"));
      return;
    }
    const { occupied, roomRev, netFactor, paxNights } = stats;
    const np = rates.nightsPerStay || 1;
    const food = paxNights.map((pn, i) => pn * rates.food * (netFactor[i] || 0));
    const vals: Record<string, number[]> = {
      ROOMS: roomRev.slice(),
      FOOD: food,
      ACTIVITIES: paxNights.map((pn, i) => (pn / np) * rates.tours * (netFactor[i] || 0)),
      TRANSPORT: paxNights.map((pn, i) => (pn / np) * rates.transport * (netFactor[i] || 0)),
      BEVERAGE: food.map(f => f * rates.bevRatio / 100),
      RETAIL: roomRev.map(r => r * rates.retailPct / 100),
      INNOCEANA: roomRev.map(r => r * rates.innoceanaPct / 100),
      // Sustainability: **por PAX-noche**, sin net factor, menos el % que no paga.
      //
      // ⚠️ Dos reglas distintas que se confundían en una sola línea:
      //
      //  · **No comisiona.** Owner, 2026-10-22: *«no paga comisión, se cobra en
      //    el hotel»*. Lo paga el huésped en recepción y la agencia no toca esa
      //    plata, así que el net factor NO le aplica. Esto ya estaba bien.
      //  · **Se cobra al 90 %.** Owner, mismo día: *«algunas personas no pagan
      //    entonces le hago un descuento»*. Ese es el recuadro «% que no paga»,
      //    y es un supuesto de cobro, no un precio: por eso vive acá y no en la
      //    tarifa del paquete.
      //
      // Lo que estaba MAL era la cantidad: el paquete lo define «per pax/night»
      // y acá se multiplicaba por noches de HABITACIÓN. Con 1,8 pax por noche
      // eso era 1,8 veces menos. El motor del P&L siempre lo calculó por
      // pax-noche, así que las dos pantallas decían cosas distintas sobre el
      // mismo escenario y ninguna lo avisaba.
      SUSTAINABILITY: paxNights.map(pn =>
        pn * rates.sustRate * (1 - rates.sustNonPay / 100)),
    };
    setRows(prev => prev.map(r => {
      const v = vals[r.line];
      if (!v) return r;
      const upd = { ...r };
      MONTH_KEYS.forEach((mk, i) => { upd[mk] = money2(v[i]); });
      return upd;
    }));
    setDirty(true);
    setMsg(t("filledFromDrivers"));
  }

  const monthTotals = MONTH_KEYS.map(mk => rows.reduce((s, r) => s + num(r[mk]), 0));
  const grandTotal = monthTotals.reduce((s, v) => s + v, 0);
  const sel = scenarios.find(s => s.id === scenarioId);

  // Baja lo que está en pantalla: los KPIs de Rooms y el checkbook completo,
  // con lo que el usuario tenga digitado (no lo último guardado).
  async function bajarExcel() {
    const escenario = sel ? `${sel.type} ${sel.version} ${sel.year}` : "";
    const colsMes = (fmt: ColumnaCuadro["formato"], ultima: string): ColumnaCuadro[] => [
      ...MONTHS.map(m => ({ label: m, ancho: 12, formato: fmt })),
      { label: ultima, ancho: 15, formato: fmt },
    ];
    const cuadros: Cuadro[] = [];

    if (stats) {
      const sum = (a: number[]) => a.reduce((x, v) => x + v, 0);
      // Las mismas cinco metricas de la pantalla, con su apertura por set: el
      // Excel baja LO QUE SE ESTA VIENDO, y eso incluye el corte por set.
      const METRICAS: { label: string; formato?: ColumnaCuadro["formato"]; val: (b: Medible) => (number | null)[] }[] = [
        { label: "Total Rooms Available", val: b => [...b.available, sum(b.available)] },
        { label: "Total Rooms Occupied", val: b => [...b.occupied, sum(b.occupied)] },
        { label: "Total Pax", val: b => [...b.paxNights, sum(b.paxNights)] },
        {
          label: "Occupancy %", formato: "pct",
          // Fraccion, no 12.5: el % en Excel se guarda como 0.125.
          val: b => [...b.occupied.map((v, i) => b.available[i] ? v / b.available[i] : null),
            sum(b.available) ? sum(b.occupied) / sum(b.available) : null],
        },
        {
          label: "ADR", formato: "usd2",
          val: b => [...b.roomRev.map((v, i) => b.occupied[i] ? v / b.occupied[i] : null),
            sum(b.occupied) ? sum(b.roomRev) / sum(b.occupied) : null],
        },
      ];
      const filasKpi: FilaCuadro[] = [];
      for (const met of METRICAS) {
        filasKpi.push({ label: met.label, formato: met.formato, valores: met.val(stats) });
        for (const sr of stats.sets)
          filasKpi.push({ label: "    " + sr.nombre, formato: met.formato, valores: met.val(sr) });
      }
      cuadros.push({
        titulo: t("xlsRoomsTitle"),
        subtitulo: escenario || undefined,
        hoja: "Rooms KPIs",
        columnas: [{ label: "Rooms", ancho: 30, formato: "texto" }, ...colsMes("num", "Full Year")],
        filas: filasKpi,
      });
    }

    // Celda vacía en pantalla = celda vacía en el Excel. Un cero digitado sí es cero.
    const celda = (v: string) => (v ?? "").toString().trim() === "" ? null : num(v);
    const filas: FilaCuadro[] = rows.map(r => ({
      label: r.account ? `${r.account} · ${r.label}` : r.label,
      valores: [...MONTH_KEYS.map(mk => celda(r[mk])), rowTotal(r)],
    }));
    filas.push({ label: "TOTAL REVENUE", es_total: true, valores: [...monthTotals, grandTotal] });

    cuadros.push({
      titulo: t("xlsCheckbookTitle"),
      subtitulo: [escenario, `${t("plSource")} ${source === "checkbook" ? "Checkbook" : "Drivers"}`]
        .filter(Boolean).join(" · "),
      hoja: "Revenue Checkbook",
      columnas: [{ label: tc("line"), ancho: 34, formato: "texto" }, ...colsMes("usd2", tc("total"))],
      filas,
    });

    try {
      await bajarCuadros("Revenue_Checkbook", cuadros);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("excelFailed"));
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          {t("title")}
        </h1>
        <select
          value={scenarioId}
          onChange={e => setScenarioId(e.target.value)}
          className="fin-input"
          style={{ minWidth: 220 }}
        >
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>
              {s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}
            </option>
          ))}
        </select>
      </div>

      <AvisoLineasObligatorias scenarioId={scenarioId} />

      <p style={{ color: "var(--text-secondary)", fontSize: 13, marginTop: 6 }}>
        {t.rich("intro", { b: (c: React.ReactNode) => <b>{c}</b> })}
      </p>

      {/* Source toggle */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "14px 0" }}>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>{t("plSource")}</span>
        <div style={{ display: "inline-flex", border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
          {(["drivers", "checkbook"] as RevenueSource[]).map(opt => (
            <button
              key={opt}
              onClick={() => toggleSource(opt)}
              disabled={sel?.is_locked}
              style={{
                padding: "6px 14px", fontSize: 13, border: "none", cursor: "pointer",
                background: source === opt ? "#2962FF" : "transparent",
                color: source === opt ? "#fff" : "var(--text-secondary)",
              }}
            >
              {opt === "drivers" ? t("optDrivers") : t("optCheckbook")}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={handleSave} disabled={saving || !dirty || sel?.is_locked}
          style={btnStyle(!saving && dirty && !sel?.is_locked)}>
          {saving ? tc("saving") : dirty ? tc("save") : t("saved")}
        </button>
        <button onClick={handleRecalc} disabled={recalc || sel?.is_locked}
          style={btnStyle(!recalc && !sel?.is_locked)}>
          {recalc ? tc("recalc.running") : t("recalcPl")}
        </button>
        <button onClick={bajarExcel} title={t("excelHint")}
          style={{ ...btnStyle(true), background: "transparent", color: "var(--positive)", border: "1px solid var(--positive)" }}>
          ⬇ Excel
        </button>
      </div>

      {/* Llenar desde drivers */}
      <div style={{
        display: "flex", alignItems: "flex-end", gap: 14, flexWrap: "wrap",
        padding: "12px 14px", marginBottom: 12, borderRadius: 8,
        border: "1px solid var(--border)", background: "var(--bg-surface)",
      }}>
        {([
          ["food", t("drvFood")],
          ["tours", t("drvTours")],
          ["transport", t("drvTransport")],
          ["nightsPerStay", t("drvNightsPerStay")],
          ["bevRatio", t("drvBevRatio")],
          ["retailPct", t("drvRetailPct")],
          ["innoceanaPct", t("drvInnoceanaPct")],
          ["sustRate", t("drvSustRate")],
          ["sustNonPay", t("drvSustNonPay")],
        ] as [keyof typeof rates, string][]).map(([key, label]) => (
          <label key={key} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-secondary)" }}>
            {label}
            <input
              className="fin-input mono"
              type="number"
              value={rates[key]}
              disabled={sel?.is_locked}
              onChange={e => setRates(r => ({ ...r, [key]: parseFloat(e.target.value) || 0 }))}
              style={{ width: 110, textAlign: "right", padding: "4px 6px" }}
            />
          </label>
        ))}
        <button onClick={fillFromDrivers} disabled={!stats || !hayTarifas || sel?.is_locked}
          style={btnStyle(!!stats && hayTarifas && !sel?.is_locked)}>
          {t("fillFromDrivers")}
        </button>
        <span style={{ fontSize: 11, color: "var(--text-disabled)", maxWidth: 320 }}>
          {t("fillHint")}
        </span>

        {/* De dónde salieron las tarifas, y el neto que producen.
          *
          * Las dos mitades importan. El origen, porque un recuadro en cero se ve
          * idéntico venga del paquete o de la nada. Y el neto, porque el recuadro
          * guarda el RACK —la fórmula multiplica por el factor del mes— y el
          * precio que se cobra es el otro: sin esto hay que hacer la cuenta de
          * cabeza para saber si la tarifa es la correcta.
          *
          * ⚠️ `sin_casa` es la red de seguridad del reconocimiento por nombre:
          * una inclusión renombrada deja su recuadro vacío, y si eso no se dijera
          * el checkbook se llenaría con menos ingreso sin que nada chillara. */}
        {pkgRates?.disponible && (
          <div style={{ flexBasis: "100%", fontSize: 11, lineHeight: 1.6,
                        color: "var(--text-secondary)", marginTop: 2 }}>
            <span>
              {t("pkgOrigen", { experiencia: pkgRates.experiencia ?? "", noches: pkgRates.nights })}
            </span>
            {pkgRates.detalle.map(d => (
              <span key={d.caja} style={{ marginLeft: 10 }}>
                <b>{d.caja}</b> {fmtUsd(d.rack)} → <span className="mono"
                  style={{ color: "var(--brand)" }}>{fmtUsd(d.neto)}</span>
              </span>
            ))}
            {pkgRates.sin_casa.length > 0 && (
              <div style={{ color: "var(--accent-red, #C0392B)", marginTop: 3 }}>
                ⚠ {t("pkgSinCasa", { lista: pkgRates.sin_casa.join(", ") })}
              </div>
            )}
            {pkgRates.unidad_rara.length > 0 && (
              <div style={{ color: "var(--accent-red, #C0392B)", marginTop: 3 }}>
                ⚠ {pkgRates.unidad_rara.map(u =>
                  t("pkgUnidadRara", { inclusion: u.inclusion, unidad: u.unidad, esperada: u.esperada })
                ).join(" · ")}
              </div>
            )}
          </div>
        )}
      </div>

      {msg && <div style={{ color: "var(--accent-green, #1A7F4B)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}
      {error && <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      {source === "drivers" && (
        <div style={{ fontSize: 12, color: "var(--text-disabled)", marginBottom: 8 }}>
          {t.rich("driversNote", { b: (c: React.ReactNode) => <b>{c}</b> })}
        </div>
      )}

      {loading ? (
        <div style={{ color: "var(--text-secondary)", padding: 24 }}>{tc("loading")}</div>
      ) : (
        <>
        {stats && (() => {
          const sum = (a: number[]) => a.reduce((x, v) => x + v, 0);
          const numCell = (n: number) => Math.round(n).toLocaleString("en-US");
          const pctCell = (ocu: number, av: number) => av ? (ocu / av * 100).toFixed(1) + "%" : "\u2014";
          const adrCell = (rev: number, ocu: number) => ocu ? "$" + (rev / ocu).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "\u2014";
          const td: React.CSSProperties = { textAlign: "right" };
          const yr: React.CSSProperties = { textAlign: "right", borderLeft: "1px solid var(--border)", fontWeight: 600 };
          // Las cinco metricas, cada una sabiendo medirse sobre CUALQUIER
          // bloque: el hotel entero o un set. Asi la fila del total y la del
          // set no pueden calcularse distinto.
          const METRICAS: {
            label: string;
            mes: (b: Medible, i: number) => string;
            anio: (b: Medible) => string;
            marca?: boolean;
          }[] = [
            { label: "Total Rooms Available", mes: (b, i) => numCell(b.available[i]), anio: b => numCell(sum(b.available)) },
            { label: "Total Rooms Occupied", mes: (b, i) => numCell(b.occupied[i]), anio: b => numCell(sum(b.occupied)) },
            { label: "Total Pax", mes: (b, i) => numCell(b.paxNights[i]), anio: b => numCell(sum(b.paxNights)) },
            { label: "Occupancy %", marca: true, mes: (b, i) => pctCell(b.occupied[i], b.available[i]), anio: b => pctCell(sum(b.occupied), sum(b.available)) },
            { label: "ADR", marca: true, mes: (b, i) => adrCell(b.roomRev[i], b.occupied[i]), anio: b => adrCell(sum(b.roomRev), sum(b.occupied)) },
          ];
          return (
            <div className="fin-sticky" style={{ overflowX: "auto", marginBottom: 16 }}>
              <table className="fin-table" style={{ minWidth: 1200 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", minWidth: 150 }}>Rooms</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                    <th style={{ textAlign: "right", minWidth: 100, borderLeft: "1px solid var(--border)" }}>Full Year</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICAS.map(met => (
                    <Fragment key={met.label}>
                      <tr>
                        <td style={{ textAlign: "left", fontWeight: 500 }}>{met.label}</td>
                        {MONTHS.map((_m, i) => <td key={i} className="mono" style={td}>{met.mes(stats, i)}</td>)}
                        <td className="mono" style={met.marca ? { ...yr, color: "var(--brand)" } : yr}>{met.anio(stats)}</td>
                      </tr>
                      {/* La apertura. Indentada y en gris porque NO suma con la
                          fila de arriba: la parte. Ocupacion y ADR de un set se
                          miden contra SUS propias disponibles y SUS noches, que
                          es justamente lo que no se puede leer del promedio. */}
                      {stats.sets.map(sr => (
                        <tr key={sr.key} style={{ color: "var(--text-secondary)" }}>
                          <td style={{ textAlign: "left", paddingLeft: 26 }}>{sr.nombre}</td>
                          {MONTHS.map((_m, i) => <td key={i} className="mono" style={td}>{met.mes(sr, i)}</td>)}
                          <td className="mono" style={{ ...yr, fontWeight: 500 }}>{met.anio(sr)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })()}
        <div className="fin-sticky" style={{ overflowX: "auto" }}>
          <table className="fin-table" style={{ minWidth: 1200 }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 150 }}>{tc("line")}</th>
                {MONTHS.map(m => <th key={m} style={{ textAlign: "right", minWidth: 80 }}>{m}</th>)}
                <th style={{ textAlign: "right", minWidth: 100, borderLeft: "1px solid var(--border)" }}>Total</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <Fragment key={r.line}>
                <tr>
                  <td style={{ textAlign: "left", fontWeight: 500 }}>
                    {/* La cuenta va al lado del nombre donde la línea ES una
                        cuenta — hoy las tres del Club. Ver el ojo del backend:
                        4500/4501/4502 los comparten tres departamentos, así que
                        el número solo no identifica nada. */}
                    {r.account && (
                      <span className="mono" style={{ color: "var(--text-disabled)", marginRight: 8 }}>
                        {r.account}
                      </span>
                    )}
                    {r.label}
                  </td>
                  {MONTH_KEYS.map((mk, mi) => (
                    <td key={mk} style={{ padding: "1px 2px" }}>
                      <input
                        className="fin-input mono"
                        value={r[mk]}
                        disabled={sel?.is_locked}
                        onChange={e => setCell(ri, mk, e.target.value)}
                        onPaste={e => handlePaste(ri, mi, e)}
                        onFocus={e => e.target.select()}
                        style={{ width: "100%", textAlign: "right", padding: "3px 4px" }}
                      />
                    </td>
                  ))}
                  <td className="mono" style={{ textAlign: "right", fontWeight: 600, borderLeft: "1px solid var(--border)" }}>
                    {fmtUsd(rowTotal(r))}
                  </td>
                </tr>
                {/* Room Revenue abierto por set: de donde sale cada dolar.
                    Es read-only y sale de los DRIVERS (noches x neta), no del
                    numero digitado arriba -- el checkbook guarda una sola linea
                    de Rooms y no tiene donde partirla. Si las dos cifras no
                    coinciden se dice abajo, porque una apertura que no cuadra
                    con la linea que abre es peor que no tenerla. */}
                {r.line === "ROOMS" && stats && stats.sets.length > 0 && (() => {
                  const sum = (a: number[]) => a.reduce((x, v) => x + v, 0);
                  const drivers = sum(stats.roomRev);
                  const dif = rowTotal(r) - drivers;
                  const cel: React.CSSProperties = { textAlign: "right", padding: "3px 6px" };
                  return (
                    <>
                      {stats.sets.map(sr => (
                        <tr key={sr.key} style={{ color: "var(--text-secondary)" }}>
                          <td style={{ textAlign: "left", paddingLeft: 26 }}>
                            {sr.nombre}
                            <span style={{ fontSize: 11, color: "var(--text-disabled)", marginLeft: 6 }}>drivers</span>
                          </td>
                          {MONTH_KEYS.map((_mk, mi) => (
                            <td key={mi} className="mono" style={cel}>{fmtUsd(sr.roomRev[mi])}</td>
                          ))}
                          <td className="mono" style={{ textAlign: "right", fontWeight: 500, borderLeft: "1px solid var(--border)" }}>
                            {fmtUsd(sum(sr.roomRev))}
                          </td>
                        </tr>
                      ))}
                      {Math.abs(dif) > 1 && (
                        <tr style={{ color: "#c8a24a" }}>
                          <td colSpan={MONTH_KEYS.length + 2} style={{ textAlign: "left", paddingLeft: 26, fontSize: 12 }}>
                            {t("setsVsDrivers", {
                              drivers: fmtUsd(drivers), linea: fmtUsd(rowTotal(r)), dif: fmtUsd(dif),
                            })}
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })()}
                </Fragment>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ fontWeight: 700, borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left" }}>TOTAL REVENUE</td>
                {monthTotals.map((t, i) => (
                  <td key={i} className="mono" style={{ textAlign: "right" }}>{fmtUsd(t)}</td>
                ))}
                <td className="mono" style={{ textAlign: "right", borderLeft: "1px solid var(--border)" }}>{fmtUsd(grandTotal)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        </>
      )}
    </div>
  );
}
