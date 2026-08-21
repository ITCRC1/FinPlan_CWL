"use client";
/**
 * La barra de contexto del tab Break-E, compartida por las tres pantallas.
 *
 * Spec `FINPLAN_TAB_BREAK-E.md` §1.1. Lo único que no es cosmético acá es la
 * **versión de dato**: el spec la pone obligatoria y sin valor implícito porque
 * *un punto de equilibrio calculado sobre la base equivocada se ve idéntico a
 * uno correcto*. No hay forma de notarlo mirando la pantalla, así que la
 * pantalla tiene que decir siempre sobre qué está parada.
 *
 * ⚠️ **Adaptación a FinPlan.** El spec propone rutas
 * `/properties/[propertyId]/break-e/...`. Acá no: en FinPlan **la propiedad es
 * el despliegue** (`HOTEL_ID`), y ninguna pantalla lleva `propertyId` en la URL.
 * Meterlo sería la única ruta del sistema con esa forma. Y la «versión de dato»
 * se ata al **escenario**, que es donde FinPlan guarda de verdad el dato: se
 * mandan los dos y el backend rechaza si no coinciden.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { getScenarios, type Scenario, type DataVersion } from "@/lib/api";
import { useEscenarioDe } from "@/lib/escenarioPreferido";
import { HOTEL_ID } from "@/lib/hotel";

/** Los selects de la barra.
 *
 * ⚠️ `minWidth` no es cosmético en el de Periodo: con el ancho automático el
 * navegador lo cortaba en **«Año co…»**, que es la opción por defecto y la que
 * más se lee. Un control que no muestra su propio valor obliga a abrirlo para
 * saber sobre qué está parada la pantalla. */
export const SEL: React.CSSProperties = {
  padding: "8px 12px", fontSize: 13.5, borderRadius: 8, lineHeight: 1.3,
  border: "1px solid var(--border-subtle)", background: "var(--bg-input)",
  color: "var(--text-primary)", cursor: "pointer",
};

/** El rótulo de cada control: arriba, chico y en versalitas. Antes iban
 *  inline —«Escenario  [select]»— y con tres controles seguidos la fila se leía
 *  como una frase cortada en vez de como una barra. */
export const ROTULO: React.CSSProperties = {
  display: "block", fontSize: 10.5, fontWeight: 700, letterSpacing: ".07em",
  textTransform: "uppercase", color: "var(--text-secondary)", marginBottom: 5,
};

export const CAMPO: React.CSSProperties = { display: "flex", flexDirection: "column" };

/** El contenedor de la barra. Exportado porque `/break-e/comparar` no puede
 *  usar `BarraContexto` —elige CUATRO escenarios a la vez, no uno— pero tiene
 *  que verse igual: si cada tab arma su propia barra, el tab deja de sentirse
 *  como un tab. */
export const BARRA: React.CSSProperties = {
  display: "flex", gap: 18, alignItems: "flex-end", flexWrap: "wrap",
  padding: "14px 18px", marginBottom: 18,
  background: "var(--bg-surface)", borderRadius: 10,
  border: "1px solid var(--border-subtle)",
};

export interface CtxBE {
  scenarioId: string;
  dataVersion: DataVersion;
  month: number;
  /** ⚠️ **Ninguna pantalla puede consultar con esto en `false`.**
   *
   * `scenarioId` se sabe al instante (sale de `localStorage`), pero su TIPO
   * solo se sabe cuando llega la lista de escenarios. En el medio el par que
   * se manda es inventado, y el backend lo rechaza con un 422 — con razón. */
  listo: boolean;
}

/** Solo el periodo se guarda acá. El ESCENARIO lo maneja `useEscenarioDe`.
 *
 * ⚠️ La primera versión de esta pantalla se inventó su propia regla de «con cuál
 * abrir» —el BUDGET Working más nuevo, con su propio `localStorage`— y
 * `test_escenario_por_defecto` la cazó. Es exactamente el defecto que esa prueba
 * existe para prevenir: cuarenta pantallas tenían cada una su copia de «el año
 * más nuevo», y el día que nacieron los Working 2028-2035 todos los reportes se
 * fueron a 2035 **sin que nada fallara** — cada uno mostraba un presupuesto
 * real, solo que el equivocado.
 */
const LLAVE_PERIODO = `break-e:periodo:${HOTEL_ID}`;

export function useContextoBE(): [CtxBE, (c: Partial<CtxBE>) => void, Scenario[]] {
  const [escenarios, setEscenarios] = useState<Scenario[]>([]);
  // `budget` es el rol: el equilibrio se planifica sobre un presupuesto. La
  // regla y la memoria son las mismas que las del resto de la app.
  const [scenarioId, setScenarioId] = useEscenarioDe("break-e", escenarios, "budget", undefined, true);
  const [month, setMonth] = useState<number>(() => {
    if (typeof window === "undefined") return 0;
    return Number(localStorage.getItem(LLAVE_PERIODO) || 0);
  });

  useEffect(() => {
    getScenarios(HOTEL_ID).then(setEscenarios).catch(() => { /* lo reporta la pantalla */ });
  }, []);
  useEffect(() => { localStorage.setItem(LLAVE_PERIODO, String(month)); }, [month]);

  // La versión de dato NO se elige aparte: es el TIPO del escenario elegido. El
  // backend rechaza si no coinciden, así que dos selectores independientes solo
  // podrían producir un 422.
  //
  // ⚠️ **Y NO tiene default.** Esta línea decía `?? "BUDGET"`, y ese default era
  // el defecto: `scenarioId` sale de `localStorage` y está listo en el primer
  // render, mientras que `escenarios` llega por red un instante después. En esa
  // ventana el `find` no encuentra nada y el par que salía era
  // «escenario FORECAST + versión BUDGET» — que es exactamente lo que el
  // backend está para rechazar. El owner lo vio en pantalla: un 422 rojo
  // permanente sobre un Resumen que además mostraba números.
  //
  // Inventar «BUDGET» acá es la misma clase de error que el módulo entero
  // combate: **un valor por defecto que se ve igual que uno elegido.**
  const tipo = useMemo<DataVersion | null>(() => {
    const s = escenarios.find(x => x.id === scenarioId);
    return (s?.type as DataVersion) ?? null;
  }, [escenarios, scenarioId]);

  // `dataVersion` conserva el tipo estricto para no tocar las seis pantallas;
  // el que manda para consultar es `listo`.
  const ctx: CtxBE = {
    scenarioId, dataVersion: tipo ?? "BUDGET", month,
    listo: Boolean(scenarioId) && tipo !== null,
  };
  const set = (p: Partial<CtxBE>) => {
    if (p.scenarioId !== undefined) setScenarioId(p.scenarioId);
    if (p.month !== undefined) setMonth(p.month);
  };
  return [ctx, set, escenarios];
}

/**
 * Guarda contra **respuestas que llegan tarde**. Las seis pantallas del tab
 * hacían `setD(await …)` sin secuencia, y con dos consultas en vuelo el
 * resultado depende de cuál conteste primero, no de cuál se pidió último.
 *
 * Así se veía el defecto que reportó el owner: la consulta inválida (422) y la
 * válida salían casi juntas; la válida contestó primero y pintó los números, la
 * inválida contestó después y pegó el error encima. Resultado: **banner rojo
 * sobre números correctos**, sin forma de saber cuál de los dos mentía.
 *
 * ⚠️ Y al revés es peor y no se ve: si la que contesta última es la de un
 * escenario que ya no está seleccionado, la pantalla muestra **los números del
 * escenario equivocado sin ningún error** — el pecado capital de este módulo.
 *
 *     const nuevaCarga = useVigencia();
 *     ...
 *     const vigente = nuevaCarga();
 *     const r = await getBeResultado(...);
 *     if (vigente()) setD(r);
 */
export function useVigencia(): () => () => boolean {
  const seq = useRef(0);
  return useCallback(() => {
    const mia = ++seq.current;
    return () => seq.current === mia;
  }, []);
}

export function BarraContexto(
  { ctx, set, escenarios }:
  { ctx: CtxBE; set: (c: Partial<CtxBE>) => void; escenarios: Scenario[] },
) {
  const t = useTranslations("breakEven");
  const tc = useTranslations("common");
  const tm = useTranslations("months");
  const MESES_LARGOS = tm.raw("long") as string[];
  return (
    <div style={BARRA}>
      <div style={{ ...CAMPO, flex: "1 1 320px", maxWidth: 420 }}>
        <label htmlFor="be-escenario" style={ROTULO}>{tc("scenario")}</label>
        <select
          id="be-escenario" className="fin-input"
          style={{ ...SEL, width: "100%", fontWeight: 600 }}
          value={ctx.scenarioId}
          onChange={e => set({ scenarioId: e.target.value })}>
          {escenarios.map(s => (
            <option key={s.id} value={s.id}>{s.type} · {s.version} · {s.year}</option>
          ))}
        </select>
      </div>

      <div style={CAMPO}>
        <span style={ROTULO}>{t("dataVersion")}</span>
        {/* Sale del escenario y no se elige aparte. Mientras no se sepa el tipo
            NO dice «BUDGET»: dice que está cargando. Poner un valor ahí es lo
            que producía el 422 — ver `useContextoBE`. */}
        <span
          title={t("dataVersionHelp")}
          style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            minWidth: 104, height: 38, boxSizing: "border-box",
            fontSize: 12, fontWeight: 700, letterSpacing: ".04em",
            padding: "0 14px", borderRadius: 999,
            border: `1px solid ${ctx.listo ? "var(--brand)" : "var(--border-subtle)"}`,
            color: ctx.listo ? "var(--brand)" : "var(--text-secondary)",
            background: ctx.listo ? "color-mix(in srgb, var(--brand) 10%, transparent)"
                                  : "transparent",
          }}>
          {ctx.listo ? ctx.dataVersion : "…"}
        </span>
      </div>

      <div style={CAMPO}>
        <label htmlFor="be-periodo" style={ROTULO}>{t("period")}</label>
        <select id="be-periodo" className="fin-input"
          style={{ ...SEL, minWidth: 168 }} value={ctx.month}
          onChange={e => set({ month: Number(e.target.value) })}>
          <option value={0}>{t("fullYear")}</option>
          {MESES_LARGOS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </div>
    </div>
  );
}

export const usd = (v: number | null | undefined) =>
  v === null || v === undefined ? "—"
    : v.toLocaleString("en-US", { style: "currency", currency: "USD",
                                  maximumFractionDigits: 0 });
export const pct = (v: number | null | undefined, dec = 1) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(dec)}%`;
