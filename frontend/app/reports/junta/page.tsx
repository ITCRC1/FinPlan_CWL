"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { FAM_FB, FAM_ROOMS, familia } from "@/lib/plFamilias";
import {
  getScenarios, getPLCompare, getPLMonthly, getPayrollDeptReport, getCashflowBudget, getPLByDept,
  getRevenueByRoomType, type RevenueByRoomType,
  type Scenario, type PLColumn, type PLMonthly, type PayrollDeptReport, type CashFlowBudget, type PLByDept,
} from "@/lib/api";
import { SECCIONES, type SeccionId } from "./secciones";
import {
  PUESTOS, paraSelector, scnLabel, type Version,
} from "./versiones";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import {
  TablaSerie, Estacionalidad, Departamentos, PlanillaHeadcount, Caja,
  FILAS_RESUMEN, FILAS_VOLUMEN, FILAS_PRECIO, linea, GOLD, type FilaSerie,
} from "./bloques";
import { VolumenPorTrimestre, VolumenPorTipo } from "./volumen";
import { CapitalDetalle } from "./capital";
import { OnTheBooksPanel } from "@/components/OnTheBooksPanel";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";

/**
 * Presentación a la Junta.
 *
 * Reemplaza el PowerPoint de 50 diapositivas y 67 imágenes pegadas a mano.
 * Tres selectores: el primero es el escenario que se PRESENTA y los otros
 * dos son las comparaciones. El orden de la tabla es el orden de los
 * selectores — lo que elegís arriba es lo que ves abajo.
 *
 * Dos modos sobre el mismo contenido: SECCIÓN (una a la vez, para proyectar) y
 * DOCUMENTO (todas encadenadas con salto de página, para imprimir a PDF).
 */

const LINEAS_INGRESO = [
  // ⚠️ Familias, no lineas sueltas: Rooms y A&B estan partidos desde el
  // 2026-08-14 y esta lista mostraba de menos. Ver `lib/plFamilias.ts`.
  { codes: FAM_ROOMS, label: "Habitaciones" },
  { codes: FAM_FB, label: "A&B" },
  { codes: ["REV_PRIVATE_BAR"], label: "Private Bar" },
  { codes: ["REV_TOURS"], label: "Tours y Actividades" },
  { codes: ["REV_TRANSPORTATION"], label: "Transporte" },
  { codes: ["REV_SUSTAINABILITY"], label: "Sustainability Fee" },
  { codes: ["REV_SPA"], label: "Spa" },
  { codes: ["REV_TIENDA"], label: "Tienda" },
  { codes: ["REV_RETAIL"], label: "Gift Shop" },
  { codes: ["REV_INNOCEANA"], label: "Innoceana" },
  { codes: ["REV_LAUNDRY"], label: "Lavandería" },
];

const LINEAS_GASTO = [
  { code: "OH_MAINTENANCE", label: "Mantenimiento" },
  { code: "OH_SALES_MARKETING", label: "Ventas y Mercadeo" },
  { code: "OH_ADMIN", label: "Administración" },
  { code: "OH_INFORMATION_SYSTEM", label: "Sistemas de Información" },
  { code: "OH_UTILITIES", label: "Energéticos" },
  { code: "OH_CAFETERIA", lk: "cafeteriaNet", label: "Cafetería (neto del reparto)" },
  { code: "OH_LAUNDRY", lk: "laundryNet", label: "Lavandería (neto del reparto)" },
  { code: "OH_CLARO_HUERTA", label: "Claro del Bosque / Huerta" },
  { code: "OH_AREC", label: "Área Recreativa" },
  { code: "OH_EMPLOYEE_BENEFITS", label: "Beneficios a colaboradores" },
];

const LINEAS_CAPITAL = [
  { code: "CAPITAL_RESERVE", lk: "capitalReserve", label: "Reserva de capital (% del ingreso)" },
  { code: "LARGE_CAPEX", label: "Mejoras mayores" },
  { code: "CAPITAL_EXPENSE", lk: "capitalTotal", label: "Total inversión de capital" },
];

/** Convierte un catálogo de líneas del P&L en filas de la serie, agregando el
 *  total — que en una presentación es lo que la junta busca primero. */
function filasDe(cat: { codes: readonly string[]; label: string; lk?: string }[],
                 totalLabel: string, totalCode: string): FilaSerie[] {
  return [
    ...cat.map(c => ({ label: c.label, lk: c.lk, formato: "dinero" as const,
                       get: (x?: PLColumn) => familia(c.codes, (k: string) => linea(x, k)) })),
    {
      // ⚠️ El total sale del MOTOR, no de sumar las filas de arriba. Sumandolas,
      // cualquier linea que faltara en el catalogo hacia que el total de la
      // presentacion saliera CORTO — y la misma presentacion se contradecia con
      // la lamina de resumen, que si lee la linea del motor.
      label: totalLabel, formato: "dinero" as const, fuerte: true,
      get: (x?: PLColumn) => linea(x, totalCode),
    },
  ];
}

/** Los catalogos de GASTO siguen siendo una linea por fila. */
function filasDeGasto(cat: { code: string; label: string ; lk?: string }[],
                      totalLabel: string, totalCode: string): FilaSerie[] {
  return filasDe(cat.map(c => ({ codes: [c.code], label: c.label })),
                 totalLabel, totalCode);
}

export default function JuntaPage() {
  const tc = useTranslations("common");
  const t = useTranslations("junta");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  // Un id por puesto; "" = sin comparación en ese puesto. Cada uno recuerda lo
  // suyo bajo su propia llave (ver `PUESTOS`), y si nunca se eligió abre con el
  // preferido del owner para ese papel. Van escritos uno por uno y no en un
  // bucle porque son hooks: el orden no puede cambiar entre renders.
  const [presenta, setPresenta] = useEscenarioDe(PUESTOS[0].llave, scenarios, PUESTOS[0].rol);
  const [comp1, setComp1] = useEscenarioDe(PUESTOS[1].llave, scenarios, PUESTOS[1].rol);
  const [comp2, setComp2] = useEscenarioDe(PUESTOS[2].llave, scenarios, PUESTOS[2].rol);
  const sel = useMemo(() => [presenta, comp1, comp2], [presenta, comp1, comp2]);
  const fijar = useMemo(() => [setPresenta, setComp1, setComp2], [setPresenta, setComp1, setComp2]);
  const [seccion, setSeccion] = useState<SeccionId>("resumen");
  const [documento, setDocumento] = useState(false);
  const [cols, setCols] = useState<Record<string, PLColumn>>({});
  // Mensual de TODAS las versiones: el comparativo por trimestre lo necesita.
  const [mensuales, setMensuales] = useState<Record<string, PLMonthly | null>>({});
  const [porTipo, setPorTipo] = useState<Record<string, RevenueByRoomType | null>>({});
  const [vistaVol, setVistaVol] = useState<"anual" | "trimestre" | "tipo">("anual");
  const [vistaCap, setVistaCap] = useState<"resumen" | "detalle">("resumen");
  const [planilla, setPlanilla] = useState<Record<string, PayrollDeptReport | null>>({});
  const [porDepto, setPorDepto] = useState<Record<string, PLByDept | null>>({});
  const [cajas, setCajas] = useState<Record<string, CashFlowBudget | null>>({});
  const [dep, setDep] = useState("ROOMS");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        // La elección de los tres puestos la hace `useEscenarioDe` cuando llega
        // la lista: acá solo se carga.
        setScenarios(await getScenarios(HOTEL_ID));
      } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
      finally { setLoading(false); }
    })();
  }, []);

  // Se respeta el orden de los selectores; se descartan los vacíos y repetidos.
  const orden = useMemo(() => {
    const vistos = new Set<string>();
    return sel.filter(id => id && !vistos.has(id) && vistos.add(id));
  }, [sel]);
  const clave = orden.join(",");
  const principal = orden[0];

  const cargar = useCallback(async () => {
    if (!orden.length) { setCols({}); return; }
    setLoading(true); setError(null);
    try {
      const r = await getPLCompare(orden, 12);
      const m: Record<string, PLColumn> = {};
      // `full` = los 12 meses: la junta mira el cierre del ejercicio.
      r.versions.forEach(v => { m[v.scenario_id] = v.full; });
      setCols(m);
    } catch (e) { setError(e instanceof Error ? e.message : tc("error")); }
    finally { setLoading(false); }

    // El resto en paralelo y tolerante: si algo falla, esa sección lo dice y las
    // demás siguen. En una presentación, una pantalla en blanco es peor que una
    // sección que avisa qué le falta.
    orden.forEach(id => {
      getCashflowBudget(id)
        .then(c => setCajas(prev => ({ ...prev, [id]: c })))
        .catch(() => setCajas(prev => ({ ...prev, [id]: null })));
      getRevenueByRoomType(id)
        .then(t => setPorTipo(prev => ({ ...prev, [id]: t })))
        .catch(() => setPorTipo(prev => ({ ...prev, [id]: null })));
      getPLMonthly(id)
        .then(m => setMensuales(prev => ({ ...prev, [id]: m })))
        .catch(() => setMensuales(prev => ({ ...prev, [id]: null })));
      getPayrollDeptReport(id)
        .then(p => setPlanilla(prev => ({ ...prev, [id]: p })))
        .catch(() => setPlanilla(prev => ({ ...prev, [id]: null })));
      getPLByDept(id, 0, false)   // 0 = año completo
        .then(p => setPorDepto(prev => ({ ...prev, [id]: p })))
        .catch(() => setPorDepto(prev => ({ ...prev, [id]: null })));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clave, principal]);
  useEffect(() => { cargar(); }, [cargar]);

  const vs: Version[] = useMemo(() => orden.map(id => {
    const s = scenarios.find(x => x.id === id);
    return { id, label: s ? scnLabel(s) : "—", col: cols[id] };
  }), [orden, scenarios, cols]);

  const elegir = (i: number, id: string) => fijar[i]?.(id);

  const visibles = documento ? SECCIONES : SECCIONES.filter(s => s.id === seccion);

  const btn = (activo: boolean): React.CSSProperties => ({
    padding: "7px 14px", fontSize: 12, fontWeight: 700, borderRadius: 6, cursor: "pointer",
    background: activo ? "var(--brand)" : "var(--bg-input)",
    color: activo ? "#fff" : "var(--text-primary)",
    border: `1px solid ${activo ? "var(--brand)" : "var(--border-medium)"}`,
  });

  return (
    <div className="print-dashboard pag pag-media" style={{ padding: "24px 28px 60px" }}>
      <IrA esc={presenta} />
      <div style={{ textAlign: "center", marginBottom: 6 }}>
        <h1 style={{ fontSize: 30, fontWeight: 800, margin: 0, letterSpacing: -0.5 }}>
          <span style={{ color: "var(--text-primary)" }}>{t("titleLead")} </span>
          <span style={{ color: "var(--brand)" }}>{t("titleAccent")}</span>
        </h1>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 6, fontWeight: 600 }}>
          {vs.map(v => v.label).join("  →  ")}
        </div>
      </div>

      {/* Selección — no viaja al PDF. Tres desplegables en vez de una grilla de
          chips: con veinte escenarios la grilla era ruido, y además así queda
          explícito cuál es el que se presenta. */}
      <div className="no-print" style={{ margin: "18px 0 12px" }}>
        <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
          {sel.map((id, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.3, color: i === 0 ? "var(--brand)" : "var(--text-secondary)" }}>
                {t(`puesto_${PUESTOS[i].rol}`)}
              </span>
              <select value={id} onChange={e => elegir(i, e.target.value)}
                style={{
                  background: "var(--bg-input)", color: "var(--text-primary)",
                  border: `1px solid ${i === 0 ? "var(--brand)" : "var(--border-medium)"}`,
                  borderRadius: 6, padding: "6px 10px", fontSize: 12.5,
                  fontWeight: i === 0 ? 800 : 600, cursor: "pointer", minWidth: 190,
                }}>
                {i > 0 && <option value="" style={{ background: "var(--bg-input)" }}>{t("noComparison")}</option>}
                {paraSelector(scenarios).map(s2 => (
                  <option key={s2.id} value={s2.id} style={{ background: "var(--bg-input)" }}>{scnLabel(s2)}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "center", marginTop: 14 }}>
          <button onClick={() => setDocumento(d => !d)} style={btn(documento)}
            title={t("docHint")}>
            {documento ? `📑 ${t("bySection")}` : `📄 ${t("viewAll")}`}
          </button>
          <button onClick={() => window.print()} style={{ ...btn(false), borderColor: GOLD, color: GOLD }}
            title={t("printHint")}>
            🖨 PDF
          </button>
        </div>
      </div>

      {!documento && (
        <div className="no-print" style={{ display: "flex", gap: 6, justifyContent: "center", flexWrap: "wrap", marginBottom: 18 }}>
          {SECCIONES.map(s => (
            <button key={s.id} onClick={() => setSeccion(s.id)} title={t(`sec_${s.id}_pregunta`)}
              style={{ ...btn(seccion === s.id), fontSize: 11.5, padding: "6px 11px" }}>
              {t(`sec_${s.id}_titulo`)}
            </button>
          ))}
        </div>
      )}

      {error && <div className="no-print" style={{ textAlign: "center", color: "var(--negative)", marginBottom: 12 }}>{error}</div>}
      {loading && <div className="no-print" style={{ textAlign: "center", color: "var(--text-secondary)" }}>{tc("loading")}</div>}
      {!loading && !orden.length && (
        <div className="no-print" style={{ textAlign: "center", color: "var(--text-secondary)", padding: 30 }}>
          {t("pickScenario")}
        </div>
      )}

      {!loading && !!orden.length && visibles.map((s, i) => (
        <section key={s.id} style={{ marginBottom: 34, ...(documento && i > 0 ? { breakBefore: "page" } : {}) }}>
          <div style={{ borderBottom: `2px solid ${GOLD}`, paddingBottom: 6, marginBottom: 14 }}>
            <h2 style={{ fontSize: 19, fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>{t(`sec_${s.id}_titulo`)}</h2>
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 3 }}>{t(`sec_${s.id}_pregunta`)}</div>
          </div>

          {s.id === "resumen" ? (
            <TablaSerie vs={vs} filas={FILAS_RESUMEN} primera={tc("indicator")} />
          ) : s.id === "volumen" ? (
            <>
              <div className="no-print" style={{ display: "flex", gap: 5, marginBottom: 14, flexWrap: "wrap" }}>
                {([["anual", tc("annual")], ["trimestre", t("byQuarter")], ["tipo", t("byRoomType")]] as const).map(([k, lab]) => (
                  <button key={k} onClick={() => setVistaVol(k)} style={{ ...btn(vistaVol === k), fontSize: 11.5, padding: "5px 11px" }}>{lab}</button>
                ))}
              </div>
              {/* En documento van las tres: el PDF no tiene botones que apretar. */}
              {(documento || vistaVol === "anual") && (
                <>
                  <TablaSerie vs={vs} filas={FILAS_VOLUMEN} primera={tc("indicator")} />
                  <Estacionalidad mensuales={mensuales} vs={vs} modo="volumen" />
                </>
              )}
              {(documento || vistaVol === "trimestre") && (
                <div style={{ marginTop: documento ? 22 : 0 }}>
                  <VolumenPorTrimestre vs={vs} mensuales={mensuales} />
                </div>
              )}
              {(documento || vistaVol === "tipo") && (
                <div style={{ marginTop: documento ? 22 : 0 }}>
                  <VolumenPorTipo datos={porTipo} vs={vs} />
                </div>
              )}
            </>
          ) : s.id === "precio" ? (
            <>
              <TablaSerie vs={vs} filas={FILAS_PRECIO} primera={tc("indicator")} />
              <Estacionalidad mensuales={mensuales} vs={vs} modo="precio" />
            </>
          ) : s.id === "ingresos" ? (
            <TablaSerie vs={vs} filas={filasDe(LINEAS_INGRESO, t("totalRevenue"), "TOTAL_REVENUES")} primera={t("revenueLine")} />
          ) : s.id === "departamentos" ? (
            <Departamentos vs={vs} sel={dep} onSel={setDep} porDepto={porDepto} documento={documento} />
          ) : s.id === "planilla" ? (
            <PlanillaHeadcount vs={vs} reportes={planilla} />
          ) : s.id === "gastos" ? (
            <TablaSerie vs={vs} filas={filasDeGasto(LINEAS_GASTO, "Total overhead", "TOTAL_OVERHEAD_EXPENSES")} primera={t("area")} />
          ) : s.id === "capital" ? (
            <>
              {/* En modo documento salen las dos: el PDF tiene que llevar el
                  resumen Y el detalle. En pantalla se elige, que es como se
                  presenta —primero el número, después el desglose si preguntan. */}
              <div className="no-print" style={{ display: "flex", gap: 5, marginBottom: 14, flexWrap: "wrap" }}>
                {([["resumen", t("summaryView")], ["detalle", t("capitalDetailView")]] as const).map(([k, lab]) => (
                  <button key={k} onClick={() => setVistaCap(k)} style={{ ...btn(vistaCap === k), fontSize: 11.5, padding: "5px 11px" }}>{lab}</button>
                ))}
              </div>
              {(documento || vistaCap === "resumen") && (
                <TablaSerie vs={vs} filas={LINEAS_CAPITAL.map(c => ({
                  label: c.label, lk: c.lk, formato: "dinero" as const, fuerte: c.code === "CAPITAL_EXPENSE",
                  get: (x?: PLColumn) => linea(x, c.code),
                }))} primera={tc("concept")} />
              )}
              {(documento || vistaCap === "detalle") && (
                <div style={{ marginTop: documento ? 26 : 0 }}>
                  {documento && (
                    <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 10 }}>{t("capitalDetailView")}</div>
                  )}
                  <CapitalDetalle scenarioId={vs[0]?.id ?? ""} etiqueta={vs[0]?.label ?? ""} />
                </div>
              )}
            </>
          ) : s.id === "cashflow" ? (
            <Caja cajas={cajas} vs={vs} />
          ) : s.id === "otb" ? (
            <OnTheBooksPanel budgetInicial={vs[0]?.id} soloLectura />
          ) : null}
        </section>
      ))}
    </div>
  );
}
