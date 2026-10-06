"use client";
import { usePlanningScenarioConUrl } from "@/lib/planningScenario";
import { elegir } from "@/lib/escenarioPreferido";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import PushRevenueButton from "@/components/PushRevenueButton";
import MixerCanales from "@/components/MixerCanales";
import { HOTEL_ID } from "@/lib/hotel";
import IrA from "@/components/IrA";
import { getScenarios, type Scenario } from "@/lib/api";

/**
 * Canales de venta: UNA sola vista, la del mixer.
 *
 * Owner, 2026-10-05, tachando la grilla entera: *«quita esto... solo deja una
 * vista»*.
 *
 * ## Qué se fue, y por qué no se pierde nada
 *
 * Había un segundo sub-tab, «Resultado por canal», que mostraba los tres cubos
 * leídos de `sales_channel_configs` — las filas guardadas del escenario. Era
 * **la misma información dos veces y peor**: el sub-tab «Mix» ya trae el
 * resumen por cubo con el Net Factor de cada mes, calculado en vivo con la
 * misma regla del motor, **y además** el factor que el motor usa hoy, el aviso
 * de cuando ese factor sale de las tarifas en vez del mix, y la diferencia en
 * plata entre uno y otro. También tenía su propio «⬇ Excel», que `MixerCanales`
 * ya exporta con el Net Factor viejo y nuevo en el subtítulo.
 *
 * ⚠️ **Y mentía.** Su texto decía que salía de los sub-canales del sub-tab Mix.
 * No: mostraba lo guardado, que sólo cambia cuando alguien aprieta APLICAR. Las
 * dos cosas pueden estar divergidas por meses — a Amarena le pasó con un mix de
 * plantilla (Travel Agency 55%, OTAs 10%) que nadie reemplazó, y el Net Factor
 * 0.8325 que producía se veía lo bastante razonable como para que nadie lo
 * mirara. Dos pantallas que dicen cosas distintas sobre el mismo número son
 * peores que una sola.
 */
export default function ChannelsPage() {
  const tc = useTranslations("common");
  const t = useTranslations("channels");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = usePlanningScenarioConUrl();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const all = await getScenarios(HOTEL_ID);
        setScenarios(all);
        // Esta pantalla ESCRIBE. Si lo recordado viene enllavado — el Planning
        // comparte el escenario entre tabs y `budget` apunta a Final 2026, que
        // lo está — la grilla abre de solo lectura y hay que cambiar el selector
        // en cada visita. Se cae al presupuesto editable del año que se planifica.
        if (all.length) {
          const recordado = all.find(x => x.id === scenarioId);
          if (!recordado || recordado.is_locked) {
            const editable = elegir(all, "budgetPlan")
              ?? all.find(x => x.type === "BUDGET" && !x.is_locked)
              ?? elegir(all, "budget") ?? all[0];
            setScenarioId(editable.id);
          }
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : tc("error"));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="pag pag-ancha" style={{ padding: 24 }}>
      <IrA esc={scenarioId} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>{t("title")}</h1>
        <select value={scenarioId} onChange={e => setScenarioId(e.target.value)}
          className="fin-input" style={{ minWidth: 200 }}>
          {scenarios.map(s => (
            <option key={s.id} value={s.id}>
              {s.type} {s.version} {s.year}{s.is_locked ? " 🔒" : ""}
            </option>
          ))}
        </select>
        <PushRevenueButton scenarioId={scenarioId} />
      </div>

      {error && (
        <div style={{ color: "var(--accent-red, #C0392B)", fontSize: 13, marginTop: 10 }}>{error}</div>
      )}

      <div style={{ marginTop: 14 }}>
        <MixerCanales scenarioId={scenarioId} />
      </div>
    </div>
  );
}
