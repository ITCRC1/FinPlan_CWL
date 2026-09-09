"use client";
/**
 * Los checkbooks, para CONSULTAR: pantalla propia, sin entrar a Planning.
 *
 * Owner, 2026-09-03: *«algunos usuarios no van a tener acceso a Planning por
 * obvias razones; necesito poder generar los checkbooks, la misma vista de
 * Planning pero para visualizar qué hay a modo de reportes»* y, después de
 * verlo dentro de Cierre de Mes: *«favor mueve el checkbook afuera, donde está
 * Full P&L Ejecutivo»*.
 *
 * ⚠️ **Está en el MENÚ, no en un sub-tab, y eso cambia quién lo encuentra.**
 * Un sub-tab de Cierre de Mes obliga a entrar al cierre, elegir versiones y
 * saber que el checkbook está ahí adentro. El que no tiene acceso a Planning
 * viene justamente a mirar un checkbook: tiene que ser una entrada del menú,
 * al lado de los otros reportes.
 *
 * El cuadro es el MISMO componente que se usaba adentro (`Checkbooks.tsx`), no
 * una copia: una segunda versión de la misma tabla es cómo terminan mostrando
 * números distintos.
 */
import { useEffect, useMemo, useState } from "react";

import Checkbooks from "@/app/month-end/pl/Checkbooks";
import { getDetalleDeCelda, getGastoPorClase, getScenarios,
         type Scenario } from "@/lib/api";
import { bajarCuadros, type Cuadro } from "@/lib/exportCuadro";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";

const SEL: React.CSSProperties = {
  padding: "6px 10px", fontSize: 12.5, borderRadius: 6,
  border: "1px solid var(--border-medium)",
  background: "var(--bg-surface)", color: "var(--text-primary)",
};

export default function CheckbooksPage() {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  const [deptos, setDeptos] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  /** Abre en el FORECAST vivo: es el checkbook que se está trabajando. Y se
   *  queda donde lo dejen — ver `useEscenarioDe`. */
  const [scenarioId, setScenarioId] = useEscenarioDe(
    "month-end/checkbooks", escenarios, "forecast");

  useEffect(() => {
    getScenarios(HOTEL_ID).then(setEscenarios)
      .catch(e => setError(e instanceof Error ? e.message : "No se pudieron cargar los escenarios"));
  }, []);

  /** El catálogo de departamentos, para el selector.
   *
   *  ⚠️ Sale de `gasto-por-clase`, que es el mismo mapa que usa Cierre de Mes.
   *  Pedirlo a otro lado daría un selector con nombres distintos de los que se
   *  ven en el reporte de al lado. */
  useEffect(() => {
    if (!scenarioId) return;
    let vivo = true;
    getGastoPorClase([scenarioId], false)
      .then(g => { if (vivo) setDeptos(g.departamentos ?? {}); })
      .catch(() => { if (vivo) setDeptos({}); });
    return () => { vivo = false; };
  }, [scenarioId]);

  const ids = useMemo(() => (scenarioId ? [scenarioId] : []), [scenarioId]);

  /** Los cuatro libros a un Excel, una hoja cada uno.
   *
   *  ⚠️ Baja los CUATRO y con TODOS los departamentos, no lo que esté
   *  seleccionado en pantalla. Un archivo que sale distinto según el filtro que
   *  estaba puesto cuando alguien lo bajó no se puede archivar: dos copias del
   *  mismo mes dirían cosas distintas. */
  async function bajarExcel() {
    if (!scenarioId) return;
    const etiqueta = escenarios.find(s => s.id === scenarioId);
    const nombre = etiqueta
      ? `${etiqueta.type}_${etiqueta.version}_${etiqueta.year}` : scenarioId;
    const LIBROS = [["opex", "Opex"], ["payroll", "Salarios"],
                    ["cost", "Costo de ventas"],
                    ["property", "Gastos de propiedad"]] as const;
    const MES3 = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
    const cuadros: Cuadro[] = [];
    for (const [clase, rotulo] of LIBROS) {
      try {
        const d = await getDetalleDeCelda([scenarioId], clase, "");
        const vivas = d.filas.filter(f =>
          (f.series[scenarioId] ?? []).some(n => Math.abs(n) >= 0.005));
        if (!vivas.length) continue;
        cuadros.push({
          titulo: `Checkbook · ${rotulo}`,
          subtitulo: `${d.versiones[0]?.escenario ?? ""} · ${d.versiones[0]?.fuente ?? ""} · USD`,
          hoja: `Checkbook ${rotulo}`.slice(0, 31),
          columnas: [
            { label: "Cuenta", ancho: 10, formato: "texto" },
            { label: "Nombre", ancho: 34, formato: "texto" },
            ...MES3.map(m => ({ label: m, ancho: 13, formato: "usd2" as const })),
            { label: "Total", ancho: 15, formato: "usd2" as const },
          ],
          filas: vivas.map(f => {
            const serie = f.series[scenarioId] ?? [];
            return {
              label: f.cuenta, es_total: false,
              valores: [f.nombre, ...MES3.map((_, i) => serie[i] ?? 0),
                        serie.reduce((a, n) => a + n, 0)],
            };
          }),
        });
      } catch { /* un libro que falla no se lleva los otros tres */ }
    }
    if (!cuadros.length) { alert("No hay nada cargado para bajar."); return; }
    try {
      await bajarCuadros(`Checkbooks_${nombre}`, cuadros);
    } catch (e) {
      alert(e instanceof Error ? e.message : "No se pudo generar el Excel");
    }
  }

  return (
    <div className="pag pag-ancha" style={{ padding: "18px 22px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10,
                    flexWrap: "wrap", marginBottom: 12 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Checkbooks</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
                style={SEL}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
          ))}
        </select>
        <button onClick={bajarExcel}
          title="Los cuatro checkbooks en un Excel, una hoja cada uno y con todos los departamentos"
          style={{ ...SEL, cursor: "pointer", fontWeight: 600,
                   background: "var(--accent-excel)", color: "#fff",
                   border: "none" }}>⬇ Excel</button>
        {error && (
          <span style={{ fontSize: 12.5, color: "var(--negative)" }}>{error}</span>
        )}
      </div>

      <Checkbooks escenarios={escenarios} scenarioIds={ids} deptos={deptos} />
    </div>
  );
}
