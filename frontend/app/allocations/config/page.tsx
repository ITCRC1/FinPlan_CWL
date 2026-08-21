"use client";
import { usePlanningScenarioConUrl, sharedScenarioOr } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState, useCallback } from "react";
import RecalcButton from "@/components/RecalcButton";
import {
  getScenarios, getCafeteriaConfig, saveCafeteriaConfig,
  getLaundryConfig, saveLaundryConfig, calculateAllocations, initAllocationConfig,
  getAllocationSummary, getLaundryParams, saveLaundryParams, getLaundryBreakdown,
  getCostoAReparto, getFtePorDepto,
  getPayrollDeptReport,
  type Scenario, type CafeteriaConfigRow, type LaundryConfigRow, type CalculateResult,
  type AllocationSummary, type LaundryParams, type LaundryBreakdown,
  type CostoAReparto, type FtePorDepto,
} from "@/lib/api";
import { bajarCuadros, type Cuadro, type FilaCuadro } from "@/lib/exportCuadro";
import { deptName, cargarDepartamentos } from "@/lib/cwl-depts";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";

// Los meses salen de `months.short` del catálogo; esto queda de respaldo.
const MESES_FALLBACK = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];

/* Tabla con estilos propios: las clases globales `fin-table`/`fin-sticky` fijan el
   encabezado y aqui lo montaban encima de las filas. */
const tblFijo: React.CSSProperties = {
  borderCollapse: "collapse", width: "100%", fontSize: 11,
};
const thFijo: React.CSSProperties = {
  position: "static", padding: "6px 8px", textAlign: "right", whiteSpace: "nowrap",
  fontWeight: 600, color: "var(--text-secondary)",
  borderBottom: "1px solid var(--border-medium)", background: "transparent",
};
const tdFijo: React.CSSProperties = {
  padding: "5px 8px", textAlign: "right", whiteSpace: "nowrap",
  fontVariantNumeric: "tabular-nums",
  borderBottom: "1px solid var(--border-subtle, #2a2a2a)", background: "transparent",
};

/** Dolares, sin decimales: los montos del reparto son grandes y la tabla es ancha. */
const money = (v: number) => (v < 0 ? "(" : "") + "$" +
  Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + (v < 0 ? ")" : "");
const TYPE_LABEL: Record<string, string> = { ACTUAL: "Actual", BUDGET: "Budget", FORECAST: "Forecast" };
function scnLabel(s: Scenario) {
  const t = TYPE_LABEL[s.type] ?? s.type;
  return (!s.version || ["actual", "from-xlsx"].includes(s.version)) ? `${t} ${s.year}` : `${t} ${s.year} · ${s.version}`;
}

// Parsea texto pegado de Excel (filas por \n, celdas por \t) a una matriz de números.
function parseClip(text: string): number[][] {
  return text.replace(/\r/g, "").split("\n").filter(l => l.trim() !== "").map(line =>
    line.split("\t").map(c => {
      const n = parseFloat(c.replace(/[$,\s]/g, ""));
      return isNaN(n) ? 0 : n;
    })
  );
}

function Badge({ ok }: { ok: boolean }) {
  const t = useTranslations("alloc");
  return (
    <span style={{
      fontSize: 10, padding: "2px 6px", borderRadius: 3,
      background: ok ? "rgba(38,166,154,0.12)" : "rgba(239,83,80,0.12)",
      color: ok ? "var(--positive)" : "var(--negative)",
      border: `1px solid ${ok ? "var(--positive)" : "var(--negative)"}`,
    }}>
      {ok ? t("netZero") : t("unbalanced")}
    </span>
  );
}

export default function AllocationsConfigPage() {
  const tc = useTranslations("common");
  const t = useTranslations("alloc");
  const tm = useTranslations("months");
  const MONTHS = (tm.raw("short") as string[]) ?? MESES_FALLBACK;
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [scenarios, setScenarios]       = useState<Scenario[]>([]);
  const [cafRows, setCafRows]           = useState<CafeteriaConfigRow[]>([]);
  const [lauRows, setLauRows]           = useState<LaundryConfigRow[]>([]);
  const [lauParams, setLauParams]       = useState<LaundryParams>({
    kilos_uniformes: 0, kilos_huespedes: 0,
    uniformes_monthly: Array(12).fill(0), huespedes_monthly: Array(12).fill(0),
    account_linen: "7310", account_uniform: "7685", account_servicios: "5301",
  });
  const [breakdown, setBreakdown]       = useState<LaundryBreakdown | null>(null);
  const [fteByDept, setFteByDept]       = useState<Record<string, number>>({});
  const [dirty, setDirty]               = useState(false);
  const [calcResult, setCalcResult]     = useState<CalculateResult | null>(null);
  const [summary, setSummary]           = useState<AllocationSummary | null>(null);
  const [loading, setLoading]           = useState(true);
  const [saving, setSaving]             = useState(false);
  const [calculating, setCalculating]   = useState(false);
  const [initializing, setInitializing] = useState(false);
  const [exporting, setExporting]       = useState(false);
  const [saveMsg, setSaveMsg]           = useState<string | null>(null);
  const [calcMsg, setCalcMsg]           = useState<string | null>(null);
  const [error, setError]               = useState<string | null>(null);
  // Sub-tab activo. VA CON LOS DEMAS HOOKS: abajo hay returns tempranos por
  // loading/error, y un useState despues de ellos se salta en el primer render y
  // revienta con «Rendered more hooks than during the previous render».
  const [tab, setTab] = useState<"cafeteria" | "laundry">("cafeteria");
  // El POTE que se va a repartir, abierto por clase de cuenta: sin esto se ve el
  // resultado del reparto pero no de dónde salió el monto.
  const [fuente, setFuente] = useState<CostoAReparto | null>(null);
  // FTE por depto Y POR MES: es la base con la que se reparte, y sin verla no
  // se puede juzgar si un departamento recibio lo que le toca.
  const [fteMes, setFteMes] = useState<FtePorDepto | null>(null);

  /** Nombre del departamento: de la config si esta, si no del catalogo. */
  const nombreDepto = (d: string) =>
    cafRows.find(r => r.dept_code === d)?.dept_name ??
    lauRows.find(r => r.dept_code === d)?.dept_name ??
    deptName(d);


  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        if (!all.length) { setError(tc("noScenarios", { hotel: HOTEL_ID })); return; }
        setScenarios(all);
        // La regla del owner, una sola: `elegir(all, "budget")` = Budget Working
        // 2027. Acá había un año QUEMADO A MANO y, si no aparecía, `all[0]` —
        // que con `/scenarios/` ordenado por año descendente es **Working
        // 2035**. Ver `lib/escenarioPreferido`.
        const bud = elegir(all, "budget") ?? all[0];
        setScenarioId(sharedScenarioOr(bud.id));
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Recargar configs + resultados cuando cambia el escenario (sync con Master Data)
  const loadForScenario = useCallback(async (id: string) => {
    if (!id) return;
    setError(null);
    try {
      const [caf, lau, prm] = await Promise.all([
        getCafeteriaConfig(id), getLaundryConfig(id), getLaundryParams(id),
      ]);
      setCafRows(caf);
      setLauRows(lau);
      setLauParams(prm);
      setCalcResult(null);
      setDirty(false);
      try { setSummary(await getAllocationSummary(id)); } catch { setSummary(null); }
      try { setBreakdown(await getLaundryBreakdown(id)); } catch { setBreakdown(null); }
      try {
        const rep = await getPayrollDeptReport(id);
        setFteByDept(Object.fromEntries(rep.depts.map(d => [d.dept_code, d.fte_avg])));
      } catch { setFteByDept({}); }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }, []);
  useEffect(() => { if (scenarioId) loadForScenario(scenarioId); }, [scenarioId, loadForScenario]);

  // El pote del departamento origen del tab activo: de aquí sale lo que se reparte.
  useEffect(() => {
    if (!scenarioId) { setFuente(null); return; }
    const dept = tab === "cafeteria" ? "0220" : "0161";
    getCostoAReparto(scenarioId, dept).then(setFuente).catch(() => setFuente(null));
    getFtePorDepto(scenarioId).then(setFteMes).catch(() => setFteMes(null));
    cargarDepartamentos();
  }, [scenarioId, tab, calcResult]);

  async function handleSaveConfigs() {
    if (!scenarioId) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      await Promise.all([
        saveCafeteriaConfig(scenarioId, cafRows),
        saveLaundryConfig(scenarioId, lauRows),
        saveLaundryParams(scenarioId, lauParams),
      ]);
      setSaveMsg(t("configSaved"));
    } catch (e: unknown) {
      setSaveMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleCalculate() {
    if (!scenarioId) return;
    setCalculating(true);
    setCalcMsg(null);
    try {
      // Guardar SIEMPRE antes de recalcular: el motor lee de la BD, no del
      // formulario. Así no se pierde lo que el usuario acaba de escribir.
      await Promise.all([
        saveCafeteriaConfig(scenarioId, cafRows),
        saveLaundryConfig(scenarioId, lauRows),
        saveLaundryParams(scenarioId, lauParams),
      ]);
      const result = await calculateAllocations(scenarioId);
      setCalcResult(result);
      setSummary(await getAllocationSummary(scenarioId));
      try { setBreakdown(await getLaundryBreakdown(scenarioId)); } catch { setBreakdown(null); }
      setDirty(false);
      setCalcMsg(t("configSavedCalc", { n: result.total_entries }));
    } catch (e: unknown) {
      setCalcMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setCalculating(false);
    }
  }

  async function handleInit() {
    if (!scenarioId) return;
    setInitializing(true);
    setSaveMsg(null);
    try {
      const res = await initAllocationConfig(scenarioId);
      const [caf, lau] = await Promise.all([getCafeteriaConfig(scenarioId), getLaundryConfig(scenarioId)]);
      setCafRows(caf);
      setLauRows(lau);
      setDirty(true);
      setSaveMsg(t("initialized", { caf: res.cafeteria_added, lau: res.laundry_added }));
    } catch (e: unknown) {
      setSaveMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setInitializing(false);
    }
  }

  function toggleCafParticipates(idx: number) {
    setDirty(true);
    setCafRows(rows => rows.map((r, i) => i === idx ? { ...r, participates: !r.participates } : r));
  }

  // Linen: editar un mes (deptIdx, monthIdx)
  function updateLinenMonth(idx: number, mi: number, value: string) {
    const n = value === "" ? 0 : parseFloat(value);
    if (isNaN(n)) return;
    setDirty(true);
    setLauRows(rows => rows.map((r, i) => {
      if (i !== idx) return r;
      const km = [...(r.kilos_monthly ?? Array(12).fill(0))];
      km[mi] = n;
      return { ...r, kilos_monthly: km };
    }));
  }

  // Pegar bloque de Excel en la grilla de linen desde (idx, mi)
  function pasteLinen(idx: number, mi: number, e: React.ClipboardEvent) {
    const grid = parseClip(e.clipboardData.getData("text"));
    if (grid.length === 0 || (grid.length === 1 && grid[0].length === 1)) return; // celda simple → comportamiento normal
    e.preventDefault();
    setDirty(true);
    setLauRows(rows => rows.map((r, i) => {
      const rr = i - idx;
      if (rr < 0 || rr >= grid.length) return r;
      const km = [...(r.kilos_monthly ?? Array(12).fill(0))];
      grid[rr].forEach((v, cc) => { if (mi + cc < 12) km[mi + cc] = v; });
      return { ...r, kilos_monthly: km };
    }));
  }

  function toggleLauParticipates(idx: number) {
    setDirty(true);
    setLauRows(rows => rows.map((r, i) => i === idx ? { ...r, participates: !r.participates } : r));
  }

  function updateLauField(idx: number, field: "dept_code" | "dept_name", value: string) {
    setDirty(true);
    setLauRows(rows => rows.map((r, i) => i === idx ? { ...r, [field]: value } : r));
  }

  function addLaundryDept() {
    setDirty(true);
    setLauRows(rows => [...rows, {
      dept_code: "", dept_name: "", kilos_historicos: 0,
      kilos_monthly: Array(12).fill(0), participates: true, notes: "",
    }]);
  }

  function updateLauAccount(field: "account_linen" | "account_uniform" | "account_servicios", value: string) {
    setDirty(true);
    setLauParams(p => ({ ...p, [field]: value }));
  }

  // Uniformes / Huéspedes: editar un mes
  function updateParamMonth(which: "uniformes_monthly" | "huespedes_monthly", mi: number, value: string) {
    const n = value === "" ? 0 : parseFloat(value);
    if (isNaN(n)) return;
    setDirty(true);
    setLauParams(p => {
      const arr = [...(p[which] ?? Array(12).fill(0))];
      arr[mi] = n;
      return { ...p, [which]: arr };
    });
  }

  // Pegar una fila de 12 meses en uniformes/huéspedes desde mi
  function pasteParamRow(which: "uniformes_monthly" | "huespedes_monthly", mi: number, e: React.ClipboardEvent) {
    const grid = parseClip(e.clipboardData.getData("text"));
    if (grid.length === 0 || (grid.length === 1 && grid[0].length === 1)) return;
    e.preventDefault();
    setDirty(true);
    setLauParams(p => {
      const arr = [...(p[which] ?? Array(12).fill(0))];
      grid[0].forEach((v, cc) => { if (mi + cc < 12) arr[mi + cc] = v; });
      return { ...p, [which]: arr };
    });
  }

  const annualKg = (arr?: number[]) => (arr ?? []).reduce((s, v) => s + (v || 0), 0);
  const totalLinenKg = lauRows.filter(r => r.participates).reduce((s, r) => s + annualKg(r.kilos_monthly), 0);
  const totalUniKg   = annualKg(lauParams.uniformes_monthly);
  const totalGstKg   = annualKg(lauParams.huespedes_monthly);
  const grandKg      = totalLinenKg + totalUniKg + totalGstKg;

  /* ── Bajar a Excel ─────────────────────────────────────────────────────────
     Un solo botón para los DOS tabs: cada cuadro de la pantalla es una hoja, en
     el orden en que se ven. Los cuadros que dependen de un cálculo (resultado
     del recálculo, desglose de lavandería) solo salen si hay algo que mostrar,
     igual que en pantalla.

     Los porcentajes viajan como FRACCIÓN (0.125, no 12.5): el formato de Excel
     pone el signo. Y los códigos de departamento van como TEXTO — un "0110"
     pasado a número queda en 110 y deja de casar con nada. */
  async function bajarExcel() {
    if (!scenarioId) return;
    setExporting(true); setSaveMsg(null);
    try {
      const scn = scenarios.find(s => s.id === scenarioId);
      const sub = scn ? scnLabel(scn) : "";
      const mesesUSD = MONTHS.map(m => ({ label: m, ancho: 12, formato: "usd" as const }));
      const mesesNUM = MONTHS.map(m => ({ label: m, ancho: 10, formato: "num" as const }));
      const anioUSD = { label: tc("year"), ancho: 15, formato: "usd" as const };
      const cuadros: Cuadro[] = [];

      // El pote de los DOS departamentos: la pantalla solo tiene cargado el del
      // tab activo, y el libro los lleva a los dos.
      const [f0220, f0161] = await Promise.all([
        getCostoAReparto(scenarioId, "0220").catch(() => null),
        getCostoAReparto(scenarioId, "0161").catch(() => null),
      ]);

      const cuadroFuente = (f: CostoAReparto | null, dept: string, hoja: string): Cuadro | null =>
        !f ? null : {
          titulo: t("poolTitle", { dept }),
          subtitulo: `${sub} · ${t("xlsPoolSub")}`,
          hoja,
          columnas: [
            { label: t("xlsClass"), ancho: 12, formato: "texto" },
            { label: tc("account"), ancho: 36, formato: "texto" },
            ...mesesUSD, anioUSD,
          ],
          filas: [
            ...f.lineas.map(l => ({
              label: l.clase, nivel: 1,
              valores: [l.nombre, ...l.meses, l.total],
            })),
            { label: t("totalToAllocate"), es_total: true, valores: [null, ...f.totales_mes, f.total] },
          ],
        };

      const cuadroReparto = (tipo: "CAFETERIA" | "LAUNDRY", hoja: string): Cuadro | null => {
        const rep = summary?.[tipo];
        if (!rep) return null;
        const origen = tipo === "CAFETERIA" ? "0220" : "0161";
        const destinos = Object.keys(rep).filter(d => d !== origen).sort();
        if (!destinos.length) return null;
        const anual = (d: string) => rep[d].reduce((a, v) => a + v, 0);
        const granTotal = destinos.reduce((a, d) => a + anual(d), 0);
        // La unidad con la que se juzga: kilos del año en lavandería, FTE
        // promedio en cafetería.
        const base = (d: string) => tipo === "LAUNDRY"
          ? (lauRows.find(x => x.dept_code === d)?.kilos_monthly ?? []).reduce((a, v) => a + v, 0)
          : (fteMes
            ? MONTHS.reduce((a, _, i) => a + (fteMes.by_dept[d]?.[String(i + 1)] ?? 0), 0) / 12
            : (fteByDept[d] ?? 0));
        return {
          titulo: `${t("chargedTitle")} — ${tipo === "CAFETERIA" ? t("xlsChargedCaf") : t("xlsChargedLau")}`,
          subtitulo: `${sub} · ${tipo === "LAUNDRY" ? t("xlsEvenPerKilo") : t("xlsEvenPerFte")}`,
          hoja,
          columnas: [
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 32, formato: "texto" },
            ...mesesUSD, anioUSD,
            { label: t("pctOfTotal"), ancho: 11, formato: "pct" },
            { label: tipo === "LAUNDRY" ? t("perKilo") : t("perFte"), ancho: 12, formato: "usd2" },
          ],
          filas: [
            ...destinos.map(d => {
              const a = anual(d), b = base(d);
              return {
                label: d, nivel: 1,
                valores: [nombreDepto(d), ...rep[d], a,
                  granTotal ? a / granTotal : null,
                  b ? a / b : null],
              };
            }),
            { label: t("totalCharged"), es_total: true,
              valores: [null,
                ...MONTHS.map((_, i) => destinos.reduce((a, d) => a + (rep[d][i] ?? 0), 0)),
                granTotal, granTotal ? 1 : null, null] },
          ],
        };
      };

      const cuadroMensual = (
        ms: { month: number; total_cost: number; rows: number; nets_zero: boolean }[],
        titulo: string, hoja: string,
      ): Cuadro => ({
        titulo, subtitulo: `${sub} · ${t("xlsEntriesGenerated", { n: calcResult?.total_entries ?? 0 })}`,
        hoja,
        columnas: [
          { label: tc("month"), ancho: 10, formato: "texto" },
          { label: t("totalCost"), ancho: 16, formato: "usd2" },
          { label: t("xlsEntries"), ancho: 11, formato: "num" },
          { label: t("xlsNetsZero"), ancho: 22, formato: "texto" },
        ],
        filas: ms.map(m => ({
          label: MONTHS[m.month - 1], nivel: 1,
          valores: [m.total_cost, m.rows,
            m.rows > 0 ? (m.nets_zero ? t("netZero") : t("unbalanced")) : tc("noData")],
        })),
      });

      /* ── Tab Cafetería ──────────────────────────────────────────────────── */
      if (cafRows.length) {
        cuadros.push({
          titulo: `${t("cafeteria")} — ${t("xlsParticipatingDepts")}`,
          subtitulo: `${sub} · ${t("xlsCafDeptsSub")}`,
          hoja: t("xlsSheetCafDepts"),
          columnas: [
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 36, formato: "texto" },
            { label: t("participates"), ancho: 11, formato: "texto" },
          ],
          filas: cafRows.map(r => ({
            label: r.dept_code, nivel: 1,
            valores: [r.dept_name, r.participates ? t("xlsYes") : t("xlsNo")],
          })),
        });
      }

      const cf0220 = cuadroFuente(f0220, "0220", t("xlsSheetCafPool"));
      if (cf0220) cuadros.push(cf0220);

      // FTE por depto y por mes: la base con la que se reparte la cafetería.
      if (fteMes) {
        const repCaf = summary?.CAFETERIA;
        const destinos = repCaf
          ? Object.keys(repCaf).filter(d => d !== "0220").sort()
          : Object.keys(fteMes.by_dept).sort();
        if (destinos.length) {
          const fteDe = (d: string, m: number) => fteMes.by_dept[d]?.[String(m)] ?? 0;
          const fteMesTotal = (m: number) => destinos.reduce((a, d) => a + fteDe(d, m), 0);
          cuadros.push({
            titulo: t("fteBaseTitle"),
            subtitulo: `${sub} · ${t("fteBaseHelp")}`,
            hoja: t("xlsSheetCafFte"),
            columnas: [
              { label: tc("deptCode"), ancho: 11, formato: "texto" },
              { label: tc("department"), ancho: 32, formato: "texto" },
              ...MONTHS.map(m => ({ label: m, ancho: 9, formato: "num1" as const })),
              { label: t("avg"), ancho: 12, formato: "num1" },
            ],
            filas: [
              ...destinos.map(d => ({
                label: d, nivel: 1,
                valores: [nombreDepto(d), ...MONTHS.map((_, i) => fteDe(d, i + 1)),
                  MONTHS.reduce((a, _, i) => a + fteDe(d, i + 1), 0) / 12],
              })),
              { label: t("totalFte"), es_total: true,
                valores: [null, ...MONTHS.map((_, i) => fteMesTotal(i + 1)),
                  MONTHS.reduce((a, _, i) => a + fteMesTotal(i + 1), 0) / 12] },
            ],
          });
        }
      }

      const repCaf = cuadroReparto("CAFETERIA", t("xlsSheetCafSplit"));
      if (repCaf) cuadros.push(repCaf);
      if (calcResult) cuadros.push(cuadroMensual(calcResult.monthly.cafeteria,
        `${t("xlsCalcResult")} — ${t("cafeteria")}`, t("xlsSheetCafMonthly")));

      // Validación: el reparto de cafetería tiene que netear $0 cada mes.
      if (summary && Object.keys(summary.CAFETERIA).length) {
        const caf = summary.CAFETERIA;
        const depts = Object.keys(caf).sort();
        const receivers = depts.filter(d => d !== "0220");
        const ann = (arr: number[]) => arr.reduce((s, v) => s + v, 0);
        const totalRec = receivers.reduce((a, x) => a + ann(caf[x]), 0);
        const filas: FilaCuadro[] = receivers.map(d => ({
          label: d, nivel: 1,
          valores: [nombreDepto(d), fteByDept[d] ?? 0,
            totalRec ? ann(caf[d]) / totalRec : null, ...caf[d], ann(caf[d])],
        }));
        if (caf["0220"]) {
          filas.push({
            label: "0220", nivel: 1,
            valores: [t("xlsCafCredit"), null, null, ...caf["0220"], ann(caf["0220"])],
          });
        }
        filas.push({
          label: t("totalMustBeZero"), es_total: true,
          valores: [null, receivers.reduce((a, d) => a + (fteByDept[d] ?? 0), 0), totalRec ? 1 : null,
            ...MONTHS.map((_, mi) => depts.reduce((s, d) => s + (caf[d]?.[mi] ?? 0), 0)),
            depts.reduce((s, d) => s + ann(caf[d]), 0)],
        });
        cuadros.push({
          titulo: t("xlsCafValidationTitle"),
          subtitulo: `${sub} · ${t("xlsCafValidationSub")}`,
          hoja: t("xlsSheetCafCheck"),
          columnas: [
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 32, formato: "texto" },
            { label: "FTE", ancho: 9, formato: "num1" },
            { label: t("pctOfTotal"), ancho: 11, formato: "pct" },
            ...mesesUSD, { label: tc("annual"), ancho: 15, formato: "usd" },
          ],
          filas,
        });
      }

      /* ── Tab Lavandería ─────────────────────────────────────────────────── */
      cuadros.push({
        titulo: t("xlsLauKilosTitle"),
        subtitulo: `${sub} · ${t("xlsLauKilosSub")}`,
        hoja: t("xlsSheetLauKilos"),
        columnas: [
          { label: tc("concept"), ancho: 26, formato: "texto" },
          { label: tc("account"), ancho: 10, formato: "texto" },
          ...mesesNUM, { label: tc("year"), ancho: 14, formato: "num" },
        ],
        filas: [
          { label: t("uniforms"), nivel: 1,
            valores: [lauParams.account_uniform, ...(lauParams.uniformes_monthly ?? Array(12).fill(0)), totalUniKg] },
          { label: tc("guests"), nivel: 1,
            valores: [lauParams.account_servicios, ...(lauParams.huespedes_monthly ?? Array(12).fill(0)), totalGstKg] },
        ],
      });

      if (lauRows.length) {
        cuadros.push({
          titulo: t("linenByDept"),
          subtitulo: `${sub} · ${t("xlsLinenSub", {
            acct: lauParams.account_linen,
            linen: totalLinenKg.toLocaleString("en-US"),
            uni: totalUniKg.toLocaleString("en-US"),
            gst: totalGstKg.toLocaleString("en-US"),
          })}`,
          hoja: t("xlsSheetLauLinen"),
          columnas: [
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 28, formato: "texto" },
            ...mesesNUM, { label: tc("year"), ancho: 14, formato: "num" },
            { label: "FTE", ancho: 9, formato: "num1" },
            { label: t("xlsActive"), ancho: 9, formato: "texto" },
          ],
          filas: [
            ...lauRows.map(r => {
              const km = r.kilos_monthly ?? Array(12).fill(0);
              const fte = fteByDept[r.dept_code] ?? 0;
              return {
                label: r.dept_code || t("xlsNoCode"), nivel: 1,
                // FTE en cero se muestra vacío, igual que el «—» de la pantalla.
                valores: [r.dept_name, ...km, annualKg(km), fte > 0 ? fte : null,
                  r.participates ? t("xlsYes") : t("xlsNo")],
              };
            }),
            { label: t("xlsTotalLinenActive"), es_total: true,
              valores: [null,
                ...MONTHS.map((_, mi) => lauRows.filter(r => r.participates)
                  .reduce((s, r) => s + ((r.kilos_monthly ?? [])[mi] ?? 0), 0)),
                totalLinenKg, null, null] },
          ],
        });
      }

      const cf0161 = cuadroFuente(f0161, "0161", t("xlsSheetLauPool"));
      if (cf0161) cuadros.push(cf0161);

      const repLau = cuadroReparto("LAUNDRY", t("xlsSheetLauSplit"));
      if (repLau) cuadros.push(repLau);
      if (calcResult) cuadros.push(cuadroMensual(calcResult.monthly.laundry,
        `${t("xlsCalcResult")} — ${t("laundry")}`, t("xlsSheetLauMonthly")));

      if (breakdown && breakdown.total_cost.some(v => Math.abs(v) > 0.5)) {
        const acc = breakdown.accounts;
        const ann = (arr: number[]) => arr.reduce((s, v) => s + v, 0);
        const sumDepts = (m: Record<string, number[]>, mi: number) =>
          Object.values(m).reduce((s, arr) => s + (arr[mi] ?? 0), 0);
        const months = Array.from({ length: 12 }, (_, i) => i);
        const movement = (mi: number) =>
          sumDepts(breakdown.linen, mi) + sumDepts(breakdown.uniform, mi) + (breakdown.credit[mi] ?? 0);
        const recon = (mi: number) =>
          sumDepts(breakdown.linen, mi) + sumDepts(breakdown.uniform, mi)
          + (breakdown.guest_cogs[mi] ?? 0) - (breakdown.total_cost[mi] ?? 0);

        cuadros.push({
          titulo: t("lauValidationTitle"),
          subtitulo: `${sub} · ${t("xlsLau3Sub", {
            linen: acc.linen, uniform: acc.uniform, servicios: acc.servicios,
          })}`,
          hoja: t("xlsSheetLauCheck"),
          columnas: [
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("concept"), ancho: 40, formato: "texto" },
            { label: tc("account"), ancho: 10, formato: "texto" },
            { label: t("xlsBasis"), ancho: 10, formato: "texto" },
            ...mesesUSD, { label: tc("annual"), ancho: 15, formato: "usd" },
          ],
          filas: [
            ...Object.keys(breakdown.linen).sort().map(d => ({
              label: d, nivel: 1,
              valores: [nombreDepto(d), acc.linen, t("basisKilos"), ...breakdown.linen[d], ann(breakdown.linen[d])],
            })),
            ...Object.keys(breakdown.uniform).sort().map(d => ({
              label: d, nivel: 1,
              valores: [nombreDepto(d), acc.uniform, "FTE", ...breakdown.uniform[d], ann(breakdown.uniform[d])],
            })),
            { label: "0161", nivel: 1,
              valores: [t("xlsLauCredit"), "4999", "", ...breakdown.credit, ann(breakdown.credit)] },
            { label: t("netMovement"), es_total: true,
              valores: [null, null, null, ...months.map(movement), ann(months.map(movement))] },
            { label: "0162", nivel: 1,
              valores: [t("xlsGuestCogs"), acc.servicios, t("basisKilos"),
                ...breakdown.guest_cogs, ann(breakdown.guest_cogs)] },
            { label: t("totalCost0161"), nivel: 1,
              valores: [null, null, null, ...breakdown.total_cost, ann(breakdown.total_cost)] },
            { label: t("xlsReconciliation"), es_total: true,
              valores: [null, null, null, ...months.map(recon), ann(months.map(recon))] },
          ],
        });

        // Asiento mes a mes: así se ve en qué mes entra cada cosa.
        type Renglon = { acct: string; dept: string; name: string; basis: string; meses: number[]; lado: "debe" | "haber" };
        const renglones: Renglon[] = [];
        Object.keys(breakdown.linen).sort().forEach(d => {
          if (ann(breakdown.linen[d]) === 0) return;
          renglones.push({ acct: acc.linen, dept: d, name: nombreDepto(d), basis: t("basisKilos"), meses: breakdown.linen[d], lado: "debe" });
        });
        Object.keys(breakdown.uniform).sort().forEach(d => {
          if (ann(breakdown.uniform[d]) === 0) return;
          renglones.push({ acct: acc.uniform, dept: d, name: nombreDepto(d), basis: "FTE", meses: breakdown.uniform[d], lado: "debe" });
        });
        if (Math.abs(ann(breakdown.guest_cogs)) > 0.005) {
          renglones.push({ acct: acc.servicios, dept: "0162", name: t("guestCogsLine"), basis: t("basisKilos"), meses: breakdown.guest_cogs, lado: "debe" });
        }
        // Un solo crédito: la 4999 ya trae el costo COMPLETO del 0161.
        renglones.push({ acct: "4999", dept: "0161", name: t("distributionLine"), basis: "", meses: breakdown.credit.map(v => -v), lado: "haber" });
        const debe = renglones.filter(r => r.lado === "debe");
        const haber = renglones.filter(r => r.lado === "haber");
        const sumaMes = (rs: Renglon[], i: number) => rs.reduce((s, r) => s + (r.meses[i] ?? 0), 0);
        const filaR = (r: Renglon): FilaCuadro => ({
          label: r.acct, nivel: 1,
          valores: [r.dept, r.name + (r.basis ? ` · ${r.basis}` : ""), ...r.meses, ann(r.meses)],
        });
        const totalR = (etiqueta: string, rs: Renglon[]): FilaCuadro => ({
          label: etiqueta, es_total: true,
          valores: [null, null, ...MONTHS.map((_, i) => sumaMes(rs, i)),
            MONTHS.reduce((s, _, i) => s + sumaMes(rs, i), 0)],
        });
        cuadros.push({
          titulo: `${t("journalTitle")} — ${t("xlsMonthByMonth")}`,
          subtitulo: `${sub} · ${t("xlsJournalSub")}`,
          hoja: t("xlsSheetLauJournalM"),
          columnas: [
            { label: tc("account"), ancho: 10, formato: "texto" },
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("concept"), ancho: 44, formato: "texto" },
            ...mesesUSD, anioUSD,
          ],
          filas: [
            ...debe.map(filaR),
            totalR(t("totalDebit"), debe),
            ...haber.map(filaR),
            totalR(t("totalCredit"), haber),
            { label: t("differenceZero"), es_total: true,
              valores: [null, null,
                ...MONTHS.map((_, i) => sumaMes(debe, i) - sumaMes(haber, i)),
                MONTHS.reduce((s, _, i) => s + sumaMes(debe, i) - sumaMes(haber, i), 0)] },
          ],
        });

        // Asiento anual, formato clásico: debe a la izquierda, haber a la derecha.
        const nomCta = (c: string) => breakdown.account_names?.[c] ?? "";
        type Linea = { cta: string; ctaNombre: string; dept: string; deptNombre: string; base: string; debe: number; haber: number };
        const lineas: Linea[] = [];
        Object.keys(breakdown.linen).sort().forEach(d => {
          const a = ann(breakdown.linen[d]);
          if (Math.abs(a) < 0.005) return;
          lineas.push({ cta: acc.linen, ctaNombre: nomCta(acc.linen), dept: d, deptNombre: nombreDepto(d), base: t("basisPerKilos"), debe: a, haber: 0 });
        });
        Object.keys(breakdown.uniform).sort().forEach(d => {
          const a = ann(breakdown.uniform[d]);
          if (Math.abs(a) < 0.005) return;
          lineas.push({ cta: acc.uniform, ctaNombre: nomCta(acc.uniform), dept: d, deptNombre: nombreDepto(d), base: t("basisPerFte"), debe: a, haber: 0 });
        });
        const guest = ann(breakdown.guest_cogs);
        if (Math.abs(guest) > 0.005) {
          lineas.push({ cta: acc.servicios, ctaNombre: nomCta(acc.servicios), dept: "0162", deptNombre: t("laundryRevenueGuest"), base: t("basisCogs"), debe: guest, haber: 0 });
        }
        lineas.push({ cta: "4999", ctaNombre: nomCta("4999"), dept: "0161", deptNombre: t("laundryDistribution"), base: t("basisAllCost"), debe: 0, haber: -ann(breakdown.credit) });
        cuadros.push({
          titulo: `${t("journalTitle")} — ${t("fullYearJanDec")}`,
          subtitulo: sub,
          hoja: t("xlsSheetLauJournalY"),
          columnas: [
            { label: tc("account"), ancho: 10, formato: "texto" },
            { label: t("accountDescription"), ancho: 30, formato: "texto" },
            { label: tc("deptCode"), ancho: 11, formato: "texto" },
            { label: tc("department"), ancho: 40, formato: "texto" },
            { label: t("debit"), ancho: 16, formato: "usd2" },
            { label: t("credit"), ancho: 16, formato: "usd2" },
          ],
          filas: [
            ...lineas.map(l => ({
              label: l.cta, nivel: 1,
              valores: [l.ctaNombre || "—", l.dept, `${l.deptNombre} · ${l.base}`,
                // Cero de verdad vs. celda vacía: en un asiento, un lado no lleva monto.
                l.debe || null, l.haber || null],
            })),
            { label: t("totals"), es_total: true,
              valores: [null, null, null,
                lineas.reduce((s, l) => s + l.debe, 0),
                lineas.reduce((s, l) => s + l.haber, 0)] },
          ],
        });
      }

      await bajarCuadros("Allocations_Cafeteria_Lavanderia", cuadros);
    } catch (e) {
      setSaveMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExporting(false);
    }
  }

  if (loading) return <p style={{ color: "var(--text-secondary)" }}>{tc("loading")}</p>;
  if (error) return (
    <div style={{ color: "var(--negative)", background: "var(--bg-surface)", padding: 16, borderRadius: 4 }}>
      ⚠ {error}
    </div>
  );

  return (
    <div className="pag pag-media">
      <IrA esc={scenarioId} />
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--text-primary)" }}>
            {t("pageTitle")}
          </h2>
          <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)" }}>
            {tab === "cafeteria" ? t("introCafeteria") : t("introLaundry")}
            {" "}{t("introContra")}
          </p>
        </div>

        {/* Selector de escenario / versión */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>{t("scenarioVersion")}</span>
          <select
            value={scenarioId ?? ""}
            onChange={e => setScenarioId(e.target.value)}
            title={t("scenarioTitle")}
            style={{
              background: "var(--bg-input)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", borderRadius: 6,
              padding: "6px 10px", fontSize: 13, fontWeight: 600, cursor: "pointer", minWidth: 180,
            }}
          >
            {scenarios.map(s => <option key={s.id} value={s.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s)}</option>)}
          </select>
        <RecalcButton scenarioId={scenarioId} />
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {/* Init button */}
          <button
            onClick={handleInit}
            disabled={initializing || !scenarioId}
            title={t("initTitle")}
            style={{
              padding: "6px 18px", fontSize: 12, borderRadius: 4,
              background: initializing ? "var(--bg-elevated)" : "var(--bg-surface)",
              color: initializing ? "var(--text-secondary)" : "var(--text-primary)",
              border: "1px solid var(--border-medium)",
              cursor: initializing ? "default" : "pointer",
            }}
          >
            {initializing ? t("initializing") : t("initDepts")}
          </button>

          {/* Save button */}
          <button
            onClick={handleSaveConfigs}
            disabled={saving || !scenarioId}
            style={{
              padding: "6px 18px", fontSize: 12, borderRadius: 4,
              background: saving ? "var(--bg-elevated)" : "#1A3A1A",
              color: saving ? "var(--text-secondary)" : "var(--positive)",
              border: "1px solid var(--positive)",
              cursor: saving ? "default" : "pointer",
            }}
          >
            {saving ? tc("saving") : t("saveConfig")}
          </button>

          {/* Calculate button */}
          <button
            onClick={handleCalculate}
            disabled={calculating || !scenarioId}
            style={{
              padding: "6px 18px", fontSize: 12, borderRadius: 4,
              background: calculating ? "var(--bg-elevated)" : "#1E2D4A",
              color: calculating ? "var(--text-secondary)" : "#90CAF9",
              border: "1px solid #2962FF",
              cursor: calculating ? "default" : "pointer",
            }}
          >
            {calculating ? t("savingCalculating") : t("saveRecalcBtn")}
          </button>

          {/* Excel: baja los dos tabs completos, un cuadro por hoja */}
          <button
            onClick={bajarExcel}
            disabled={exporting || !scenarioId}
            title={t("excelTitle")}
            style={{
              padding: "6px 18px", fontSize: 12, borderRadius: 4,
              background: "transparent", color: "var(--positive)",
              border: "1px solid var(--positive)",
              cursor: exporting ? "default" : "pointer",
            }}
          >
            {exporting ? t("generating") : "⬇ Excel"}
          </button>
        </div>
      </div>

      {/* Status messages */}
      {saveMsg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: saveMsg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: saveMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${saveMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>
          {saveMsg}
        </div>
      )}
      {calcMsg && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          background: calcMsg.startsWith("✓") ? "rgba(38,166,154,0.08)" : "rgba(239,83,80,0.08)",
          color: calcMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)",
          border: `1px solid ${calcMsg.startsWith("✓") ? "var(--positive)" : "var(--negative)"}`,
        }}>
          {calcMsg}
        </div>
      )}
      {dirty && (
        <div style={{
          marginBottom: 12, padding: "8px 14px", borderRadius: 4, fontSize: 12,
          display: "flex", alignItems: "center", gap: 8,
          background: "rgba(255,193,7,0.08)", color: "var(--warning, #FFC107)",
          border: "1px solid rgba(255,193,7,0.4)",
        }}>
          {t.rich("dirtyWarning", { b: (c: React.ReactNode) => <b>{c}</b> })}
        </div>
      )}

      {/* ── Sub-tabs: cada reparto se lee por separado ──────────────────── */}
      <div style={{ display: "flex", gap: 2, marginBottom: 18,
        borderBottom: "1px solid var(--border-medium)" }}>
        {([
          ["cafeteria", t("cafeteria"), t("tabHintCafeteria")],
          ["laundry", t("laundry"), t("tabHintLaundry")],
        ] as [typeof tab, string, string][]).map(([v, label, hint]) => (
          <button key={v} onClick={() => setTab(v)} title={hint} style={{
            padding: "9px 18px", fontSize: 13, fontWeight: 600, cursor: "pointer",
            border: "none", background: "transparent",
            color: tab === v ? "var(--brand)" : "var(--text-secondary)",
            borderBottom: `2px solid ${tab === v ? "var(--brand)" : "transparent"}`,
            marginBottom: -1,
          }}>
            {label}
            <span style={{ display: "block", fontSize: 10.5, fontWeight: 400,
              color: "var(--text-disabled)", marginTop: 2 }}>{hint}</span>
          </button>
        ))}
      </div>

      {/* La cafetería se configura con checkboxes: cabe al lado. La lavandería es
          una tabla de 12 meses POR departamento — en una columna angosta queda con
          scroll interno y no se puede trabajar. Ahí van uno debajo del otro, a
          todo el ancho. */}
      <div style={{
        display: "grid",
        gridTemplateColumns: tab === "cafeteria" ? "minmax(320px, 520px) 1fr" : "1fr",
        gap: 20, alignItems: "start",
      }}>

        {/* ── Cafetería config ───────────────────────────────────────────── */}
        {tab === "cafeteria" && (
        <div style={{ background: "var(--bg-surface)", borderRadius: 6, padding: 16, maxWidth: 520 }}>
          <div style={{ marginBottom: 10 }}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              {t("cafDeptsTitle")}
            </h3>
            <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-secondary)" }}>
              {t("cafDeptsHelp")}
              <br />
              <em>{t("cafDeptsRemote")}</em>
            </p>
          </div>

          {cafRows.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", fontSize: 12, fontStyle: "italic" }}>
              {t.rich("noConfig", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
          ) : (
            <table className="fin-table" style={{ fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Dept</th>
                  <th style={{ textAlign: "left" }}>{tc("name")}</th>
                  <th style={{ textAlign: "center" }}>{t("participates")}</th>
                </tr>
              </thead>
              <tbody>
                {cafRows.map((row, idx) => (
                  <tr key={row.dept_code} style={{
                    opacity: row.participates ? 1 : 0.45,
                  }}>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>{row.dept_code}</td>
                    <td style={{ color: "var(--text-secondary)", fontSize: 11 }}>{row.dept_name}</td>
                    <td style={{ textAlign: "center" }}>
                      <input
                        type="checkbox"
                        checked={row.participates}
                        onChange={() => toggleCafParticipates(idx)}
                        style={{ cursor: "pointer", accentColor: "var(--brand)" }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        )}

        {/* ── Lavandería config (kilos POR MES) ──────────────────────────── */}
        {tab === "laundry" && (
        <div style={{ background: "var(--bg-surface)", borderRadius: 6, padding: 16 }}>
          <div style={{ marginBottom: 10 }}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
              {t("laundryKilosTitle")}
            </h3>
            <p style={{ margin: "4px 0 0", fontSize: 11, color: "var(--text-secondary)" }}>
              {t.rich("laundryThreeWays", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                d: (c: React.ReactNode) => <b style={{ color: "var(--brand)" }}>{c}</b>,
                guests: tc("guests"),
                linen: lauParams.account_linen,
                uniform: lauParams.account_uniform,
                servicios: lauParams.account_servicios,
              })}
              <br />{t.rich("pasteHint", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
          </div>

          {/* Cuentas */}
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
            {([["account_linen", t("accLinen")], ["account_uniform", t("accUniform")], ["account_servicios", t("accGuests")]] as const).map(([f, lbl]) => (
              <label key={f} style={{ fontSize: 10, color: "var(--text-disabled)", display: "flex", flexDirection: "column", gap: 2 }}>
                {lbl}
                <input type="text" value={lauParams[f]}
                  onChange={e => updateLauAccount(f, e.target.value)}
                  className="fin-input" style={{ width: 90, fontSize: 11 }} />
              </label>
            ))}
          </div>

          {/* Reparto anual */}
          <p style={{ margin: "0 0 8px", fontSize: 11, color: "var(--text-secondary)" }}>
            {t.rich("annualTotals", {
              s: (c: React.ReactNode) => <strong>{c}</strong>,
              linen: totalLinenKg.toLocaleString("en-US"),
              uni: totalUniKg.toLocaleString("en-US"),
              gst: totalGstKg.toLocaleString("en-US"),
            })}
            {grandKg > 0 && (() => {
              const p = (v: number) => (v / grandKg * 100).toFixed(1) + "%";
              return <span> · {t("splitPcts", { p1: p(totalLinenKg), p2: p(totalUniKg), p3: p(totalGstKg) })}</span>;
            })()}
          </p>

          {/* Uniformes + Huéspedes por mes */}
          <div className="fin-sticky" style={{ overflowX: "auto", marginBottom: 16 }}>
            <table className="fin-table" style={{ fontSize: 11, minWidth: 760 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", position: "sticky", left: 0, background: "var(--bg-surface)", minWidth: 150 }}>{t("conceptPerMonth")}</th>
                  {MONTHS.map(m => <th key={m} style={{ textAlign: "right" }}>{m}</th>)}
                  <th style={{ textAlign: "right", color: "var(--brand)" }}>{tc("year")}</th>
                </tr>
              </thead>
              <tbody>
                {([["uniformes_monthly", t("uniforms"), lauParams.account_uniform], ["huespedes_monthly", tc("guests"), lauParams.account_servicios]] as const).map(([key, label, acct]) => (
                  <tr key={key}>
                    <td style={{ position: "sticky", left: 0, background: "var(--bg-surface)", color: "var(--text-secondary)" }}>
                      {label} <span style={{ fontSize: 9, color: "var(--text-disabled)" }}>· {acct}</span>
                    </td>
                    {(lauParams[key] ?? Array(12).fill(0)).map((v, mi) => (
                      <td key={mi} style={{ textAlign: "right", padding: 1 }}>
                        <input type="number" value={v}
                          onChange={e => updateParamMonth(key, mi, e.target.value)}
                          onPaste={e => pasteParamRow(key, mi, e)}
                          onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()}
                          className="fin-input" style={{ width: 48, textAlign: "right", fontSize: 10, padding: "2px 3px" }} />
                      </td>
                    ))}
                    <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                      {annualKg(lauParams[key]).toLocaleString("en-US")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Linen por departamento × mes */}
          <p style={{ margin: "0 0 4px", fontSize: 11, fontWeight: 600, color: "var(--text-primary)" }}>
            {t("linenByDept")}
          </p>
          {lauRows.length === 0 ? (
            <p style={{ color: "var(--text-secondary)", fontSize: 12, fontStyle: "italic" }}>
              {t.rich("noConfig", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
          ) : (
            <div className="fin-sticky" style={{ overflowX: "auto" }}>
              <table className="fin-table" style={{ fontSize: 11, minWidth: 1000 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", position: "sticky", left: 0, background: "var(--bg-surface)" }}>Dept</th>
                    <th style={{ textAlign: "left" }}>{tc("name")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right" }}>{m}</th>)}
                    <th style={{ textAlign: "right", color: "var(--brand)" }}>{tc("year")}</th>
                    <th style={{ textAlign: "right" }} title={t("fteUniformHint")}>FTE</th>
                    <th style={{ textAlign: "center" }}>{t("activeShort")}</th>
                  </tr>
                </thead>
                <tbody>
                  {lauRows.map((row, idx) => {
                    const km = row.kilos_monthly ?? Array(12).fill(0);
                    const fte = fteByDept[row.dept_code] ?? 0;
                    return (
                      <tr key={idx} style={{ opacity: row.participates ? 1 : 0.45 }}>
                        <td style={{ position: "sticky", left: 0, background: "var(--bg-surface)" }}>
                          <input type="text" value={row.dept_code}
                            onChange={e => updateLauField(idx, "dept_code", e.target.value)}
                            className="fin-input" placeholder={t("phCode")}
                            style={{ width: 50, fontSize: 11, fontFamily: "monospace" }} />
                        </td>
                        <td>
                          <input type="text" value={row.dept_name}
                            onChange={e => updateLauField(idx, "dept_name", e.target.value)}
                            className="fin-input" placeholder={t("phName")}
                            style={{ width: 120, fontSize: 11 }} />
                        </td>
                        {km.map((v, mi) => (
                          <td key={mi} style={{ textAlign: "right", padding: 1 }}>
                            <input type="number" value={v}
                              onChange={e => updateLinenMonth(idx, mi, e.target.value)}
                              onPaste={e => pasteLinen(idx, mi, e)}
                              onFocus={e => e.target.select()} onWheel={e => e.currentTarget.blur()}
                              className="fin-input"
                              style={{ width: 48, textAlign: "right", fontSize: 10, padding: "2px 3px" }}
                              disabled={!row.participates} />
                          </td>
                        ))}
                        <td className="mono" style={{ textAlign: "right", fontWeight: 700 }}>
                          {annualKg(km).toLocaleString("en-US")}
                        </td>
                        <td className="mono" style={{ textAlign: "right", color: fte > 0 ? "var(--text-primary)" : "var(--text-disabled)" }}>
                          {fte > 0 ? fte.toFixed(2) : "—"}
                        </td>
                        <td style={{ textAlign: "center" }}>
                          <input type="checkbox" checked={row.participates}
                            onChange={() => toggleLauParticipates(idx)}
                            style={{ cursor: "pointer", accentColor: "var(--brand)" }} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <button
            onClick={addLaundryDept}
            style={{
              marginTop: 10, padding: "5px 14px", fontSize: 11, borderRadius: 4,
              background: "var(--bg-elevated)", color: "var(--text-primary)",
              border: "1px solid var(--border-medium)", cursor: "pointer",
            }}
          >
            {t("addDept")}
          </button>
        </div>
        )}

        {/* ── Cuánto hay para repartir, de dónde sale, y a quién le toca ─── */}
        <div style={{ background: "var(--bg-surface)", borderRadius: 6, padding: 16 }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
            {t("poolTitle", { dept: tab === "cafeteria" ? "0220" : "0161" })}
          </h3>
          <p style={{ margin: "4px 0 12px", fontSize: 11, color: "var(--text-secondary)" }}>
            {t("poolHelp")}
          </p>

          {!fuente ? (
            <p style={{ fontSize: 12, color: "var(--text-disabled)" }}>{tc("loading")}</p>
          ) : (
            <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
              <table style={tblFijo}>
                <thead>
                  <tr>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 190 }}>{tc("account")}</th>
                    {MONTHS.map(m => <th key={m} style={thFijo}>{m}</th>)}
                    <th style={{ ...thFijo, color: "var(--brand)" }}>{tc("year")}</th>
                  </tr>
                </thead>
                <tbody>
                  {fuente.lineas.map(l => (
                    <tr key={l.clase}>
                      <td style={{ ...tdFijo, textAlign: "left", color: "var(--text-primary)" }}>
                        <b>{l.clase}</b> — {l.nombre}
                        {/* Un total en cero no dice lo mismo si no hay lineas que si
                            las hay sin llenar: lo primero es que no aplica, lo
                            segundo es trabajo pendiente. */}
                        {!l.total && (
                          <span style={{ marginLeft: 8, fontSize: 10,
                            color: l.lineas_cargadas ? "var(--warning, #FFC107)"
                                                     : "var(--text-disabled)" }}>
                            {l.lineas_cargadas
                              ? t("linesNoAmount", { n: l.lineas_cargadas, donde: l.donde ?? "" })
                              : t("notApplicable")}
                          </span>
                        )}
                      </td>
                      {l.meses.map((v, i) => (
                        <td key={i} style={{ ...tdFijo,
                          color: v ? "var(--text-secondary)" : "var(--text-disabled)" }}>
                          {v ? money(v) : "—"}
                        </td>
                      ))}
                      <td style={{ ...tdFijo, fontWeight: 700,
                        color: l.total ? "var(--text-primary)" : "var(--text-disabled)" }}>
                        {l.total ? money(l.total) : "—"}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td style={{ ...tdFijo, textAlign: "left", fontWeight: 700,
                      color: "var(--text-primary)", borderTop: "1px solid var(--border-medium)" }}>
                      {t("totalToAllocate")}
                    </td>
                    {fuente.totales_mes.map((v, i) => (
                      <td key={i} style={{ ...tdFijo, fontWeight: 700,
                        borderTop: "1px solid var(--border-medium)",
                        color: v ? "var(--brand)" : "var(--text-disabled)" }}>
                        {v ? money(v) : "—"}
                      </td>
                    ))}
                    <td style={{ ...tdFijo, fontWeight: 800,
                      borderTop: "1px solid var(--border-medium)",
                      color: fuente.total ? "var(--brand)" : "var(--text-disabled)" }}>
                      {fuente.total ? money(fuente.total) : "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
              {!fuente.total && (
                <p style={{ margin: "10px 0 0", fontSize: 11.5, color: "var(--warning, #FFC107)" }}>
                  {t("nothingBudgeted", { dept: fuente.dept_code })}
                </p>
              )}
            </div>
          )}

          {/* ── FTE por departamento y por mes: la base del reparto ─────── */}
          {(() => {
            const rep = summary?.[tab === "cafeteria" ? "CAFETERIA" : "LAUNDRY"];
            const origen = tab === "cafeteria" ? "0220" : "0161";
            const destinos = rep
              ? Object.keys(rep).filter(d => d !== origen).sort()
              : Object.keys(fteMes?.by_dept ?? {}).sort();
            // La lavanderia no necesita el reporte de FTE: sus kilos vienen de su
            // propia configuracion.
            if (!destinos.length) return null;
            if (tab === "cafeteria" && !fteMes) return null;
            // En lavandería los kilos ya se editan arriba, en la configuración:
            // repetirlos de solo lectura solo quita espacio a los cuadros de costo.
            if (tab === "laundry") return null;
            // Solo cafetería: en lavandería los kilos se editan arriba.
            const fteDe = (d: string, m: number) =>
              fteMes?.by_dept[d]?.[String(m)] ?? 0;
            const fteAnual = (d: string) =>
              MONTHS.reduce((a, _, i) => a + fteDe(d, i + 1), 0) / 12;
            const fteMesTotal = (m: number) =>
              destinos.reduce((a, d) => a + fteDe(d, m), 0);
            return (
              <div style={{ marginTop: 22 }}>
                <h4 style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 600,
                  color: "var(--text-primary)" }}>
                  {t("fteBaseTitle")}
                </h4>
                <p style={{ margin: "0 0 10px", fontSize: 11, color: "var(--text-secondary)" }}>
                  {t("fteBaseHelp")}
                </p>
                <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
                  <table style={tblFijo}>
                    <thead>
                      <tr>
                        <th style={{ ...thFijo, textAlign: "left", minWidth: 190 }}>{tc("department")}</th>
                        {MONTHS.map(m => <th key={m} style={thFijo}>{m}</th>)}
                        <th style={{ ...thFijo, color: "var(--brand)" }}>{t("avg")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {destinos.map(d => (
                        <tr key={d}>
                          <td style={{ ...tdFijo, textAlign: "left" }}>
                            <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>{d}</span>{" "}
                            <span style={{ color: "var(--text-secondary)" }}>{nombreDepto(d)}</span>
                          </td>
                          {MONTHS.map((_, i) => {
                            const v = fteDe(d, i + 1);
                            return (
                              <td key={i} style={{ ...tdFijo,
                                color: v ? "var(--text-secondary)" : "var(--text-disabled)" }}>
                                {v ? v.toFixed(1) : "—"}
                              </td>
                            );
                          })}
                          <td style={{ ...tdFijo, fontWeight: 700, color: "var(--text-primary)" }}>
                            {fteAnual(d).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                      <tr>
                        <td style={{ ...tdFijo, textAlign: "left", fontWeight: 700,
                          color: "var(--text-primary)",
                          borderTop: "1px solid var(--border-medium)" }}>
                          {t("totalFte")}
                        </td>
                        {MONTHS.map((_, i) => (
                          <td key={i} style={{ ...tdFijo, fontWeight: 700,
                            borderTop: "1px solid var(--border-medium)",
                            color: fteMesTotal(i + 1) ? "var(--brand)" : "var(--text-disabled)" }}>
                            {fteMesTotal(i + 1) ? fteMesTotal(i + 1).toFixed(1) : "—"}
                          </td>
                        ))}
                        <td style={{ ...tdFijo, fontWeight: 800, color: "var(--brand)",
                          borderTop: "1px solid var(--border-medium)" }}>
                          {(MONTHS.reduce((a, _, i) => a + fteMesTotal(i + 1), 0) / 12).toFixed(2)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}

          {/* ── Cuánto le tocó a cada departamento, mes a mes ───────────── */}
          {(() => {
            const rep = summary?.[tab === "cafeteria" ? "CAFETERIA" : "LAUNDRY"];
            const origen = tab === "cafeteria" ? "0220" : "0161";
            if (!rep) return (
              <p style={{ marginTop: 22, fontSize: 12, color: "var(--warning, #FFC107)" }}>
                {t.rich("noAllocationYet", { b: (c: React.ReactNode) => <b>{c}</b> })}
              </p>
            );
            const destinos = Object.keys(rep).filter(d => d !== origen).sort();
            if (!destinos.length) return null;
            const anual = (d: string) => rep[d].reduce((a, v) => a + v, 0);
            const mesTotal = (i: number) => destinos.reduce((a, d) => a + (rep[d][i] ?? 0), 0);
            const granTotal = destinos.reduce((a, d) => a + anual(d), 0);
            // La unidad con la que se juzga: kilos del ano en lavanderia, FTE
            // promedio en cafeteria.
            const fteProm = (d: string) => {
              if (tab === "laundry") {
                const r = lauRows.find(x => x.dept_code === d);
                return (r?.kilos_monthly ?? []).reduce((a, v) => a + v, 0);
              }
              return fteMes
                ? MONTHS.reduce((a, _, i) => a + (fteMes.by_dept[d]?.[String(i + 1)] ?? 0), 0) / 12
                : (fteByDept[d] ?? 0);
            };
            return (
              <div style={{ marginTop: 22 }}>
                <h4 style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 600,
                  color: "var(--text-primary)" }}>
                  {t("chargedTitle")}
                </h4>
                <p style={{ margin: "0 0 10px", fontSize: 11, color: "var(--text-secondary)" }}>
                  {t("chargedHelp", { acct: tab === "cafeteria" ? "6025" : "7310 / 7685" })}{" "}
                  {tab === "laundry"
                    ? t.rich("perKiloEven", { b: (c: React.ReactNode) => <b>{c}</b> })
                    : t.rich("perFteEven", { b: (c: React.ReactNode) => <b>{c}</b> })}
                </p>
                <div className="fin-scroll-x" style={{ overflowX: "auto" }}>
                  <table style={tblFijo}>
                    <thead>
                      <tr>
                        <th style={{ ...thFijo, textAlign: "left", minWidth: 190 }}>{tc("department")}</th>
                        {MONTHS.map(m => <th key={m} style={thFijo}>{m}</th>)}
                        <th style={{ ...thFijo, color: "var(--brand)" }}>{tc("year")}</th>
                        <th style={thFijo}>%</th>
                        <th style={thFijo}>{tab === "laundry" ? t("perKilo") : t("perFte")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {destinos.map(d => {
                        const a = anual(d);
                        const f = fteProm(d);
                        return (
                          <tr key={d}>
                            <td style={{ ...tdFijo, textAlign: "left" }}>
                              <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>{d}</span>{" "}
                              <span style={{ color: "var(--text-secondary)" }}>{nombreDepto(d)}</span>
                            </td>
                            {rep[d].map((v, i) => (
                              <td key={i} style={{ ...tdFijo,
                                color: v ? "var(--text-secondary)" : "var(--text-disabled)" }}>
                                {v ? money(v) : "—"}
                              </td>
                            ))}
                            <td style={{ ...tdFijo, fontWeight: 700, color: "var(--text-primary)" }}>
                              {money(a)}
                            </td>
                            <td style={{ ...tdFijo, color: "var(--text-secondary)" }}>
                              {granTotal ? `${(a / granTotal * 100).toFixed(1)}%` : "—"}
                            </td>
                            <td style={{ ...tdFijo, color: "var(--text-secondary)" }}>
                              {f ? money(a / f) : "—"}
                            </td>
                          </tr>
                        );
                      })}
                      <tr>
                        <td style={{ ...tdFijo, textAlign: "left", fontWeight: 700,
                          color: "var(--text-primary)",
                          borderTop: "1px solid var(--border-medium)" }}>
                          {t("totalCharged")}
                        </td>
                        {MONTHS.map((_, i) => (
                          <td key={i} style={{ ...tdFijo, fontWeight: 700,
                            borderTop: "1px solid var(--border-medium)",
                            color: mesTotal(i) ? "var(--brand)" : "var(--text-disabled)" }}>
                            {mesTotal(i) ? money(mesTotal(i)) : "—"}
                          </td>
                        ))}
                        <td style={{ ...tdFijo, fontWeight: 800, color: "var(--brand)",
                          borderTop: "1px solid var(--border-medium)" }}>
                          {money(granTotal)}
                        </td>
                        <td style={{ ...tdFijo, color: "var(--text-secondary)",
                          borderTop: "1px solid var(--border-medium)" }}>100%</td>
                        <td style={{ ...tdFijo, borderTop: "1px solid var(--border-medium)" }} />
                      </tr>
                    </tbody>
                  </table>
                </div>
                {fuente && Math.abs(granTotal - fuente.total) > 1 && (
                  <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--warning, #FFC107)" }}>
                    {t.rich("chargedMismatch", {
                      b: (c: React.ReactNode) => <b>{c}</b>,
                      cargado: money(granTotal),
                      pote: money(fuente.total),
                      accion: t("saveRecalc"),
                    })}
                  </p>
                )}
                {fuente && Math.abs(granTotal - fuente.total) <= 1 && granTotal > 0 && (
                  <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--positive)" }}>
                    {t("chargedOk", { dept: fuente.dept_code, monto: money(fuente.total) })}
                  </p>
                )}
              </div>
            );
          })()}
        </div>
      </div>

      {/* ── Calculation results ─────────────────────────────────────────────── */}
      {calcResult && (
        <div style={{ marginTop: 24 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 12 }}>
            {t("calcResultTitle", { n: calcResult.total_entries })}
          </h3>
          {calcResult.total_entries === 0 && (
            <div style={{
              marginBottom: 16, padding: "10px 14px", borderRadius: 4, fontSize: 12,
              background: "rgba(255,193,7,0.08)", color: "var(--warning, #FFC107)",
              border: "1px solid rgba(255,193,7,0.4)",
            }}>
              {t.rich("noCostWarning", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                u: (c: React.ReactNode) => <u>{c}</u>,
                laundry: t("laundry"),
                kilos: t("kilosOnlyProportions"),
              })}
            </div>
          )}
          {calcResult.total_entries > 0 && calcResult.monthly.laundry.every(m => m.rows === 0) && (
            <div style={{
              marginBottom: 16, padding: "10px 14px", borderRadius: 4, fontSize: 12,
              background: "rgba(255,193,7,0.08)", color: "var(--warning, #FFC107)",
              border: "1px solid rgba(255,193,7,0.4)",
            }}>
              {t.rich("cafOkLaundryZero", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                zero: t("laundryZero"),
              })}
            </div>
          )}
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 16, maxWidth: 620 }}>
            {/* Cafetería monthly */}
            {tab === "cafeteria" && (
            <div style={{ background: "var(--bg-surface)", borderRadius: 6, padding: 14 }}>
              <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
                {t("cafeteria")}
              </p>
              <table className="fin-table" style={{ fontSize: 11 }}>
                <thead>
                  <tr>
                    <th>{tc("month")}</th>
                    <th style={{ textAlign: "right" }}>{t("totalCost")}</th>
                    <th style={{ textAlign: "center" }}>{t("net")}</th>
                  </tr>
                </thead>
                <tbody>
                  {calcResult.monthly.cafeteria.map(m => (
                    <tr key={m.month}>
                      <td>{MONTHS[m.month - 1]}</td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {m.total_cost > 0 ? (m.total_cost < 0 ? "(" : "") + "$" + Math.abs(m.total_cost).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (m.total_cost < 0 ? ")" : "") : "—"}
                      </td>
                      <td style={{ textAlign: "center" }}>
                        {m.rows > 0 ? <Badge ok={m.nets_zero} /> : <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>{tc("noData")}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            )}

            {/* Lavandería monthly */}
            {tab === "laundry" && (
            <div style={{ background: "var(--bg-surface)", borderRadius: 6, padding: 14 }}>
              <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>
                {t("laundry")}
              </p>
              <table className="fin-table" style={{ fontSize: 11 }}>
                <thead>
                  <tr>
                    <th>{tc("month")}</th>
                    <th style={{ textAlign: "right" }}>{t("totalCost")}</th>
                    <th style={{ textAlign: "center" }}>{t("net")}</th>
                  </tr>
                </thead>
                <tbody>
                  {calcResult.monthly.laundry.map(m => (
                    <tr key={m.month}>
                      <td>{MONTHS[m.month - 1]}</td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {m.total_cost > 0 ? (m.total_cost < 0 ? "(" : "") + "$" + Math.abs(m.total_cost).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (m.total_cost < 0 ? ")" : "") : "—"}
                      </td>
                      <td style={{ textAlign: "center" }}>
                        {m.rows > 0 ? <Badge ok={m.nets_zero} /> : <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>{tc("noData")}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
          </div>
        </div>
      )}

      {/* ── Validación: desglose Cafetería por departamento (cuenta 6025) ──── */}
      {tab === "cafeteria" && summary && Object.keys(summary.CAFETERIA).length > 0 && (() => {
        const caf = summary.CAFETERIA;
        const nm = (dc: string) =>
          cafRows.find(r => r.dept_code === dc)?.dept_name ??
          lauRows.find(r => r.dept_code === dc)?.dept_name ?? dc;
        const depts = Object.keys(caf).sort();
        const receivers = depts.filter(d => d !== "0220");
        const ann = (arr: number[]) => arr.reduce((s, v) => s + v, 0);
        const colTot = (mi: number) => depts.reduce((s, d) => s + (caf[d]?.[mi] ?? 0), 0);
        const grand = depts.reduce((s, d) => s + ann(caf[d]), 0);
        const fmt = (v: number) => Math.abs(v) < 0.5 ? "—"
          : (v < 0 ? "(" : "") + "$" + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + (v < 0 ? ")" : "");
        const cell: React.CSSProperties = { textAlign: "right", padding: "4px 8px", whiteSpace: "nowrap" };
        return (
          <div style={{ marginTop: 28 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
              {t.rich("cafValidationTitle", { c: (n: React.ReactNode) => <span style={{ color: "var(--brand)" }}>{n}</span> })}
            </h3>
            <p style={{ margin: "0 0 12px", fontSize: 11, color: "var(--text-secondary)" }}>
              {t.rich("cafeteriaSplit", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
            <div className="fin-sticky" style={{ overflowX: "auto", background: "var(--bg-surface)", borderRadius: 6, padding: 12 }}>
              <table className="fin-table" style={{ fontSize: 11, minWidth: 1100 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", position: "sticky", left: 0, background: "var(--bg-surface)" }}>{tc("department")}</th>
                    <th style={{ textAlign: "right" }} title={t("fteHint")}>FTE</th>
                    <th style={{ textAlign: "right" }} title={t("shareHint")}>{t("pctOfTotal")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right" }}>{m}</th>)}
                    <th style={{ textAlign: "right", color: "var(--brand)" }}>{tc("annual")}</th>
                  </tr>
                </thead>
                <tbody>
                  {receivers.map(d => (
                    <tr key={d}>
                      <td style={{ position: "sticky", left: 0, background: "var(--bg-surface)" }}>
                        <span className="mono" style={{ color: "var(--text-secondary)", fontSize: 10 }}>{d}</span>{" "}
                        <span style={{ color: "var(--text-secondary)" }}>{nm(d)}</span>
                      </td>
                      <td className="mono" style={{ ...cell, color: "var(--text-secondary)" }}>
                        {(fteByDept[d] ?? 0).toFixed(2)}
                      </td>
                      <td className="mono" style={{ ...cell, color: "var(--text-secondary)" }}>
                        {(() => {
                          const tot = receivers.reduce((a, x) => a + ann(caf[x]), 0);
                          return tot ? `${(ann(caf[d]) / tot * 100).toFixed(1)}%` : "—";
                        })()}
                      </td>
                      {caf[d].map((v, mi) => <td key={mi} className="mono" style={cell}>{fmt(v)}</td>)}
                      <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--text-primary)" }}>{fmt(ann(caf[d]))}</td>
                    </tr>
                  ))}
                  {caf["0220"] && (
                    <tr style={{ borderTop: "1px solid var(--border-medium)" }}>
                      <td style={{ position: "sticky", left: 0, background: "var(--bg-surface)", color: "var(--negative)", fontWeight: 600 }}>
                        {t("cafCreditRow")}
                      </td>
                      <td style={cell} /><td style={cell} />
                      {caf["0220"].map((v, mi) => <td key={mi} className="mono" style={{ ...cell, color: "var(--negative)" }}>{fmt(v)}</td>)}
                      <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--negative)" }}>{fmt(ann(caf["0220"]))}</td>
                    </tr>
                  )}
                  <tr className="total" style={{ borderTop: "2px solid var(--border-medium)" }}>
                    <td style={{ position: "sticky", left: 0, background: "var(--bg-surface)", fontWeight: 800 }}>{t("totalMustBeZero")}</td>
                    <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--text-primary)" }}>
                      {receivers.reduce((a, d) => a + (fteByDept[d] ?? 0), 0).toFixed(2)}
                    </td>
                    <td className="mono" style={{ ...cell, color: "var(--text-secondary)" }}>100%</td>
                    {MONTHS.map((_, mi) => {
                      const t = colTot(mi);
                      return <td key={mi} className="mono" style={{ ...cell, fontWeight: 700, color: Math.abs(t) < 0.5 ? "var(--positive)" : "var(--negative)" }}>{Math.abs(t) < 0.5 ? "✓" : fmt(t)}</td>;
                    })}
                    <td className="mono" style={{ ...cell, fontWeight: 800, color: Math.abs(grand) < 0.5 ? "var(--positive)" : "var(--negative)" }}>{Math.abs(grand) < 0.5 ? "✓ $0" : fmt(grand)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}

      {/* ── Validación: desglose Lavandería 3 vías ──────────────────────────── */}
      {tab === "laundry" && breakdown && breakdown.total_cost.some(v => Math.abs(v) > 0.5) && (() => {
        const nm = (dc: string) =>
          lauRows.find(r => r.dept_code === dc)?.dept_name ??
          cafRows.find(r => r.dept_code === dc)?.dept_name ?? dc;
        const linenDepts = Object.keys(breakdown.linen).sort();
        const uniDepts = Object.keys(breakdown.uniform).sort();
        const ann = (arr: number[]) => arr.reduce((s, v) => s + v, 0);
        const sumDepts = (m: Record<string, number[]>, mi: number) =>
          Object.values(m).reduce((s, arr) => s + (arr[mi] ?? 0), 0);
        const fmt = (v: number) => Math.abs(v) < 0.5 ? "—"
          : (v < 0 ? "(" : "") + "$" + Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 }) + (v < 0 ? ")" : "");
        const cell: React.CSSProperties = { textAlign: "right", padding: "4px 8px", whiteSpace: "nowrap" };
        const sticky: React.CSSProperties = { position: "sticky", left: 0, background: "var(--bg-surface)" };
        const months = Array.from({ length: 12 }, (_, i) => i);
        // movimiento (linen + uniforme + crédito) debe netear $0 cada mes
        const movement = (mi: number) => sumDepts(breakdown.linen, mi) + sumDepts(breakdown.uniform, mi) + (breakdown.credit[mi] ?? 0);
        // reconciliación: linen + uniforme + huéspedes = costo total 0161
        const recon = (mi: number) => sumDepts(breakdown.linen, mi) + sumDepts(breakdown.uniform, mi) + (breakdown.guest_cogs[mi] ?? 0) - (breakdown.total_cost[mi] ?? 0);
        const accLine = (acc: string, basis: string) =>
          <span style={{ fontSize: 9, color: "var(--text-disabled)" }}> · {acc} · {basis}</span>;
        return (
          <div style={{ marginTop: 28 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
              {t("lauValidationTitle")}
            </h3>
            <p style={{ margin: "0 0 12px", fontSize: 11, color: "var(--text-secondary)" }}>
              {t.rich("lauValidationHelp", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                d: (c: React.ReactNode) => <b style={{ color: "var(--brand)" }}>{c}</b>,
                guests: tc("guests"),
                linen: breakdown.accounts.linen,
                uniform: breakdown.accounts.uniform,
                servicios: breakdown.accounts.servicios,
              })}
            </p>
            <div className="fin-sticky" style={{ overflowX: "auto", background: "var(--bg-surface)", borderRadius: 6, padding: 12 }}>
              <table className="fin-table" style={{ fontSize: 11, minWidth: 1100 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left", ...sticky }}>{tc("concept")}</th>
                    {MONTHS.map(m => <th key={m} style={{ textAlign: "right" }}>{m}</th>)}
                    <th style={{ textAlign: "right", color: "var(--brand)" }}>{tc("annual")}</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Linen por dept (7310) */}
                  {linenDepts.map(d => (
                    <tr key={"L" + d}>
                      <td style={sticky}>
                        <span className="mono" style={{ color: "var(--text-secondary)", fontSize: 10 }}>{d}</span>{" "}
                        <span style={{ color: "var(--text-secondary)" }}>{nm(d)}</span>
                        {accLine(breakdown.accounts.linen, t("basisKilos"))}
                      </td>
                      {breakdown.linen[d].map((v, mi) => <td key={mi} className="mono" style={cell}>{fmt(v)}</td>)}
                      <td className="mono" style={{ ...cell, fontWeight: 700 }}>{fmt(ann(breakdown.linen[d]))}</td>
                    </tr>
                  ))}
                  {/* Uniformes por dept (7685) */}
                  {uniDepts.map(d => (
                    <tr key={"U" + d}>
                      <td style={sticky}>
                        <span className="mono" style={{ color: "var(--text-secondary)", fontSize: 10 }}>{d}</span>{" "}
                        <span style={{ color: "var(--text-secondary)" }}>{nm(d)}</span>
                        {accLine(breakdown.accounts.uniform, "FTE")}
                      </td>
                      {breakdown.uniform[d].map((v, mi) => <td key={mi} className="mono" style={cell}>{fmt(v)}</td>)}
                      <td className="mono" style={{ ...cell, fontWeight: 700 }}>{fmt(ann(breakdown.uniform[d]))}</td>
                    </tr>
                  ))}
                  {/* Crédito 0161 */}
                  <tr style={{ borderTop: "1px solid var(--border-medium)" }}>
                    <td style={{ ...sticky, color: "var(--negative)", fontWeight: 600 }}>
                      {t("lauCreditRow")}
                    </td>
                    {breakdown.credit.map((v, mi) => <td key={mi} className="mono" style={{ ...cell, color: "var(--negative)" }}>{fmt(v)}</td>)}
                    <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--negative)" }}>{fmt(ann(breakdown.credit))}</td>
                  </tr>
                  {/* Movimiento neto = $0 */}
                  <tr style={{ borderTop: "1px solid var(--border-medium)" }}>
                    <td style={{ ...sticky, fontWeight: 700 }}>{t("netMovement")}</td>
                    {months.map(mi => {
                      const t = movement(mi);
                      return <td key={mi} className="mono" style={{ ...cell, fontWeight: 700, color: Math.abs(t) < 0.5 ? "var(--positive)" : "var(--negative)" }}>{Math.abs(t) < 0.5 ? "✓" : fmt(t)}</td>;
                    })}
                    <td className="mono" style={{ ...cell, fontWeight: 800, color: Math.abs(ann(months.map(movement))) < 0.5 ? "var(--positive)" : "var(--negative)" }}>{Math.abs(ann(months.map(movement))) < 0.5 ? "✓ $0" : fmt(ann(months.map(movement)))}</td>
                  </tr>
                  {/* Huéspedes COGS: sale del 0161 y entra al 0162 (5301) */}
                  <tr style={{ borderTop: "2px solid var(--border-medium)" }}>
                    <td style={{ ...sticky, color: "var(--brand)", fontWeight: 600 }}>
                      {t("guestCogsRow", { acct: breakdown.accounts.servicios })}
                    </td>
                    {breakdown.guest_cogs.map((v, mi) => <td key={mi} className="mono" style={{ ...cell, color: "var(--brand)" }}>{fmt(v)}</td>)}
                    <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--brand)" }}>{fmt(ann(breakdown.guest_cogs))}</td>
                  </tr>
                  {/* Costo total 0161 */}
                  <tr>
                    <td style={{ ...sticky, color: "var(--text-secondary)" }}>{t("totalCost0161")}</td>
                    {breakdown.total_cost.map((v, mi) => <td key={mi} className="mono" style={{ ...cell, color: "var(--text-secondary)" }}>{fmt(v)}</td>)}
                    <td className="mono" style={{ ...cell, fontWeight: 700, color: "var(--text-secondary)" }}>{fmt(ann(breakdown.total_cost))}</td>
                  </tr>
                  {/* Reconciliación */}
                  <tr className="total">
                    <td style={{ ...sticky, fontWeight: 800 }}>{t("linenCheck")}</td>
                    {months.map(mi => {
                      const t = recon(mi);
                      return <td key={mi} className="mono" style={{ ...cell, fontWeight: 700, color: Math.abs(t) < 0.5 ? "var(--positive)" : "var(--negative)" }}>{Math.abs(t) < 0.5 ? "✓" : fmt(t)}</td>;
                    })}
                    <td className="mono" style={{ ...cell, fontWeight: 800, color: Math.abs(ann(months.map(recon))) < 0.5 ? "var(--positive)" : "var(--negative)" }}>{Math.abs(ann(months.map(recon))) < 0.5 ? "✓" : fmt(ann(months.map(recon)))}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}

      {/* ── Asiento contable de la distribución de Lavandería ───────────────── */}
      {tab === "laundry" && breakdown && breakdown.total_cost.some(v => Math.abs(v) > 0.5) && (() => {
        const nm = (dc: string) =>
          lauRows.find(r => r.dept_code === dc)?.dept_name ??
          cafRows.find(r => r.dept_code === dc)?.dept_name ?? dc;
        const acc = breakdown.accounts;
        const anual = (arr: number[]) => arr.reduce((s, v) => s + v, 0);

        // Cada renglón del asiento con sus 12 meses, no colapsado a un periodo:
        // asi se ve en que mes entra cada cosa sin tener que ir mes por mes.
        type Renglon = { acct: string; dept: string; name: string; basis: string;
                         meses: number[]; lado: "debe" | "haber" };
        const renglones: Renglon[] = [];

        Object.keys(breakdown.linen).sort().forEach(d => {
          if (anual(breakdown.linen[d]) === 0) return;
          renglones.push({ acct: acc.linen, dept: d, name: nm(d), basis: t("basisKilos"),
                           meses: breakdown.linen[d], lado: "debe" });
        });
        Object.keys(breakdown.uniform).sort().forEach(d => {
          if (anual(breakdown.uniform[d]) === 0) return;
          renglones.push({ acct: acc.uniform, dept: d, name: nm(d), basis: "FTE",
                           meses: breakdown.uniform[d], lado: "debe" });
        });
        if (Math.abs(anual(breakdown.guest_cogs)) > 0.005) {
          // El lavado de huespedes se VENDE: su costo va al 0162, donde vive el
          // ingreso de lavanderia, no al 0161 que solo reparte.
          renglones.push({ acct: acc.servicios, dept: "0162",
                           name: t("guestCogsLine"), basis: t("basisKilos"),
                           meses: breakdown.guest_cogs, lado: "debe" });
        }
        // Un solo credito: la 4999 ya trae el costo COMPLETO del 0161 —linen,
        // uniformes y huespedes—. Agregar otro renglon por los huespedes seria
        // acreditarlos dos veces y el asiento no cerraria.
        renglones.push({ acct: "4999", dept: "0161",
                         name: t("distributionLine"),
                         basis: "", meses: breakdown.credit.map(v => -v), lado: "haber" });

        const debe = renglones.filter(r => r.lado === "debe");
        const haber = renglones.filter(r => r.lado === "haber");
        const sumaMes = (rs: Renglon[], i: number) =>
          rs.reduce((s, r) => s + (r.meses[i] ?? 0), 0);
        const dif = (i: number) => sumaMes(debe, i) - sumaMes(haber, i);
        const cuadra = MONTHS.every((_, i) => Math.abs(dif(i)) < 0.05);

        const m2 = (v: number) => Math.abs(v) < 0.005 ? "—"
          : "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });

        const fila = (r: Renglon) => (
          <tr key={`${r.lado}-${r.acct}-${r.dept}-${r.name}`}>
            <td style={{ ...tdFijo, textAlign: "left",
              color: r.lado === "debe" ? "var(--brand)" : "var(--accent-red, #C0392B)",
              fontWeight: 600 }}>
              {r.acct}
            </td>
            <td style={{ ...tdFijo, textAlign: "left", color: "var(--text-secondary)" }}>
              <span style={{ color: "var(--text-disabled)", fontSize: 10 }}>{r.dept}</span>{" "}
              {r.name}
              {r.basis && <span style={{ color: "var(--text-disabled)", fontSize: 9.5 }}> · {r.basis}</span>}
            </td>
            {r.meses.map((v, i) => (
              <td key={i} style={{ ...tdFijo,
                color: Math.abs(v) < 0.005 ? "var(--text-disabled)"
                  : r.lado === "debe" ? "var(--text-secondary)" : "var(--accent-red, #C0392B)" }}>
                {m2(v)}
              </td>
            ))}
            <td style={{ ...tdFijo, fontWeight: 700,
              color: r.lado === "debe" ? "var(--text-primary)" : "var(--accent-red, #C0392B)" }}>
              {m2(anual(r.meses))}
            </td>
          </tr>
        );

        const totalFila = (etiqueta: string, rs: Renglon[], color: string) => (
          <tr>
            <td colSpan={2} style={{ ...tdFijo, textAlign: "left", fontWeight: 700,
              color, borderTop: "1px solid var(--border-medium)" }}>{etiqueta}</td>
            {MONTHS.map((_, i) => (
              <td key={i} style={{ ...tdFijo, fontWeight: 700, color,
                borderTop: "1px solid var(--border-medium)" }}>{m2(sumaMes(rs, i))}</td>
            ))}
            <td style={{ ...tdFijo, fontWeight: 800, color,
              borderTop: "1px solid var(--border-medium)" }}>
              {m2(MONTHS.reduce((s, _, i) => s + sumaMes(rs, i), 0))}
            </td>
          </tr>
        );

        return (
          <div style={{ marginTop: 28 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                {t("journalTitle")}
              </h3>
              <span style={{ fontSize: 11.5, fontWeight: 700,
                color: cuadra ? "var(--positive)" : "var(--accent-red, #C0392B)" }}>
                {cuadra ? t("balances12") : t("monthsDontBalance")}
              </span>
            </div>
            <p style={{ margin: "0 0 10px", fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              {t.rich("journalHelp", {
                b: (c: React.ReactNode) => <b>{c}</b>,
                guests: tc("guests"),
                linen: acc.linen,
                uniform: acc.uniform,
                servicios: acc.servicios,
              })}
            </p>
            <div className="fin-scroll-x" style={{ overflowX: "auto", border: "1px solid var(--border-medium)",
              borderRadius: 6, padding: 8 }}>
              <table style={tblFijo}>
                <thead>
                  <tr>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 56 }}>{tc("account")}</th>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 230 }}>{t("deptConcept")}</th>
                    {MONTHS.map(m => <th key={m} style={thFijo}>{m}</th>)}
                    <th style={{ ...thFijo, color: "var(--brand)" }}>{tc("year")}</th>
                  </tr>
                </thead>
                <tbody>
                  {debe.map(fila)}
                  {totalFila(t("totalDebit"), debe, "var(--brand)")}
                  {haber.map(fila)}
                  {totalFila(t("totalCredit"), haber, "var(--accent-red, #C0392B)")}
                  <tr>
                    <td colSpan={2} style={{ ...tdFijo, textAlign: "left", fontWeight: 800,
                      color: "var(--text-primary)", borderTop: "2px solid var(--border-medium)" }}>
                      {t("differenceZero")}
                    </td>
                    {MONTHS.map((_, i) => (
                      <td key={i} style={{ ...tdFijo, fontWeight: 700,
                        borderTop: "2px solid var(--border-medium)",
                        color: Math.abs(dif(i)) < 0.05 ? "var(--positive)" : "var(--accent-red, #C0392B)" }}>
                        {Math.abs(dif(i)) < 0.05 ? "✓" : m2(dif(i))}
                      </td>
                    ))}
                    <td style={{ ...tdFijo, fontWeight: 800,
                      borderTop: "2px solid var(--border-medium)",
                      color: cuadra ? "var(--positive)" : "var(--accent-red, #C0392B)" }}>
                      {cuadra ? "✓ $0" : m2(MONTHS.reduce((s, _, i) => s + dif(i), 0))}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}

      {/* ── Asiento contable ANUAL, formato clasico ─────────────────────────── */}
      {tab === "laundry" && breakdown && breakdown.total_cost.some(v => Math.abs(v) > 0.5) && (() => {
        const nm = (dc: string) =>
          lauRows.find(r => r.dept_code === dc)?.dept_name ??
          cafRows.find(r => r.dept_code === dc)?.dept_name ?? deptName(dc);
        const acc = breakdown.accounts;
        const nomCta = (c: string) => breakdown.account_names?.[c] ?? "";
        const anual = (arr: number[]) => arr.reduce((s, v) => s + v, 0);
        const val = anual;   // anual fijo: el mes a mes ya esta arriba

        // Asiento clasico: a la izquierda lo que ENTRA a los departamentos (debe),
        // a la derecha lo que SALE de lavanderia (haber).
        type Linea = { cta: string; ctaNombre: string; dept: string; deptNombre: string;
                       base: string; debe: number; haber: number };
        const lineas: Linea[] = [];

        Object.keys(breakdown.linen).sort().forEach(d => {
          const a = val(breakdown.linen[d]);
          if (Math.abs(a) < 0.005) return;
          lineas.push({ cta: acc.linen, ctaNombre: nomCta(acc.linen), dept: d,
                        deptNombre: nm(d), base: t("basisPerKilos"), debe: a, haber: 0 });
        });
        Object.keys(breakdown.uniform).sort().forEach(d => {
          const a = val(breakdown.uniform[d]);
          if (Math.abs(a) < 0.005) return;
          lineas.push({ cta: acc.uniform, ctaNombre: nomCta(acc.uniform), dept: d,
                        deptNombre: nm(d), base: t("basisPerFte"), debe: a, haber: 0 });
        });
        const guest = val(breakdown.guest_cogs);
        if (Math.abs(guest) > 0.005) {
          // Al 0162, que es donde esta el ingreso de lavanderia: el costo de lo
          // que se vendio se para junto a su venta.
          lineas.push({ cta: acc.servicios, ctaNombre: nomCta(acc.servicios), dept: "0162",
                        deptNombre: t("laundryRevenueGuest"),
                        base: t("basisCogs"), debe: guest, haber: 0 });
        }
        // El credito: sale TODO el costo del 0161 de un solo, huespedes incluido.
        const sale = -val(breakdown.credit);
        lineas.push({ cta: "4999", ctaNombre: nomCta("4999"), dept: "0161",
                      deptNombre: t("laundryDistribution"),
                      base: t("basisAllCost"), debe: 0, haber: sale });

        const totDebe = lineas.reduce((s, l) => s + l.debe, 0);
        const totHaber = lineas.reduce((s, l) => s + l.haber, 0);
        const cuadra = Math.abs(totDebe - totHaber) < 0.05;
        const m2 = (v: number) => v ? "$" + v.toLocaleString("en-US",
          { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "";

        return (
          <div style={{ marginTop: 28, maxWidth: 980 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
              <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                {t("journalTitle")}
              </h3>
              <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                {t("fullYearJanDec")}
              </span>
              <span style={{ fontSize: 11.5, fontWeight: 700,
                color: cuadra ? "var(--positive)" : "var(--accent-red, #C0392B)" }}>
                {cuadra ? t("balances") : t("doesNotBalance")}
              </span>
            </div>
            <p style={{ margin: "0 0 10px", fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.6 }}>
              {t.rich("journalAnnualHelp", { b: (c: React.ReactNode) => <b>{c}</b> })}
            </p>
            <div className="fin-scroll-x" style={{ overflowX: "auto", border: "1px solid var(--border-medium)",
              borderRadius: 6, padding: 8 }}>
              <table style={tblFijo}>
                <thead>
                  <tr>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 60 }}>{tc("account")}</th>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 190 }}>{t("accountDescription")}</th>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 60 }}>{tc("dept")}</th>
                    <th style={{ ...thFijo, textAlign: "left", minWidth: 230 }}>{tc("department")}</th>
                    <th style={{ ...thFijo, minWidth: 120 }}>{t("debit")}</th>
                    <th style={{ ...thFijo, minWidth: 120 }}>{t("credit")}</th>
                  </tr>
                </thead>
                <tbody>
                  {lineas.map((l, i) => (
                    <tr key={i}>
                      <td style={{ ...tdFijo, textAlign: "left", fontWeight: 600,
                        color: l.debe ? "var(--brand)" : "var(--accent-red, #C0392B)" }}>
                        {l.cta}
                      </td>
                      <td style={{ ...tdFijo, textAlign: "left", color: "var(--text-primary)" }}>
                        {l.ctaNombre || "—"}
                      </td>
                      <td style={{ ...tdFijo, textAlign: "left", color: "var(--text-disabled)" }}>
                        {l.dept}
                      </td>
                      <td style={{ ...tdFijo, textAlign: "left", color: "var(--text-secondary)" }}>
                        {l.deptNombre}
                        <span style={{ color: "var(--text-disabled)", fontSize: 9.5 }}> · {l.base}</span>
                      </td>
                      <td style={{ ...tdFijo, color: "var(--text-primary)" }}>{m2(l.debe)}</td>
                      <td style={{ ...tdFijo, color: "var(--accent-red, #C0392B)" }}>{m2(l.haber)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td colSpan={4} style={{ ...tdFijo, textAlign: "left", fontWeight: 800,
                      color: "var(--text-primary)", borderTop: "2px solid var(--border-medium)" }}>
                      {t("totals")}
                    </td>
                    <td style={{ ...tdFijo, fontWeight: 800, color: "var(--brand)",
                      borderTop: "2px solid var(--border-medium)" }}>{m2(totDebe)}</td>
                    <td style={{ ...tdFijo, fontWeight: 800, color: "var(--accent-red, #C0392B)",
                      borderTop: "2px solid var(--border-medium)" }}>{m2(totHaber)}</td>
                  </tr>
                  {!cuadra && (
                    <tr>
                      <td colSpan={4} style={{ ...tdFijo, textAlign: "left", fontWeight: 700,
                        color: "var(--accent-red, #C0392B)" }}>
                        {t("journalOutOfBalance")}
                      </td>
                      <td colSpan={2} style={{ ...tdFijo, fontWeight: 700,
                        color: "var(--accent-red, #C0392B)" }}>{m2(totDebe - totHaber)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
