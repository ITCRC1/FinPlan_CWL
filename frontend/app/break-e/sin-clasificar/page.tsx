"use client";
/**
 * Break-E → **Por defecto: 100% fijo**. Spec `FINPLAN_TAB_BREAK-E.md` §2.6.
 *
 * ⚠️ **El spec la llama «Sin Clasificar» y el owner corrigió el nombre**
 * (2026-08-17): *«si al menos tiene fijo 100% entonces ya tiene un criterio, no
 * sin clasificar»*. Y es exacto — «sin clasificar» sugiere que esas cuentas
 * quedaron **afuera** del cálculo, y es al revés: **están adentro, contadas
 * como 100% fijas**. Lo que falta no es la clasificación: es que alguien la
 * confirme o la cambie.
 *
 * El nombre interno (`be_unclassified`, `sin_regla`) se deja como está para no
 * desalinear la API del spec; lo que cambia es lo que lee una persona.
 *
 * **Esta pantalla es la que evita que el modelo se degrade en silencio.** El
 * catálogo GL crece; una cuenta nueva sin regla toma el default de **100%
 * fija** — a propósito, porque asumirla variable inflaría el margen y bajaría el
 * equilibrio, o sea que el error se vería como una buena noticia.
 *
 * Y su espejo: **reglas huérfanas**, cuya cuenta GL ya no tiene movimiento en el
 * escenario. Puede ser una cuenta que se dejó de usar o una que se renombró.
 *
 * ⚠️ Antes esta ruta no existía y el enlace del Resumen daba **404** contra
 * `/configuracion/sin-clasificar`, porque «sin-clasificar» caía en `[slug]` y el
 * backend respondía que ese departamento no existe. El owner lo vio en pantalla.
 */
import { useCallback, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { getBeSinClasificar } from "@/lib/api";
import { bajarCuadros } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";
import { BarraContexto, useContextoBE, useVigencia, usd } from "../_contexto";

type Datos = Awaited<ReturnType<typeof getBeSinClasificar>>;

const TH: React.CSSProperties = {
  textAlign: "right", padding: "7px 8px", fontSize: 11, fontWeight: 700,
  textTransform: "uppercase", letterSpacing: ".04em",
};
const TD: React.CSSProperties = { padding: "6px 8px", fontSize: 13, textAlign: "right" };
const IZQ: React.CSSProperties = { ...TD, textAlign: "left" };
const DER: React.CSSProperties = TD;

export default function SinClasificar() {
  const t = useTranslations("breakEven");
  const tc = useTranslations("common");
  const RICH = { b: (c: React.ReactNode) => <b>{c}</b> };
  const [ctx, set, escenarios] = useContextoBE();
  const [d, setD] = useState<Datos | null>(null);
  const [err, setErr] = useState("");
  //: El detalle cuenta por cuenta arranca CERRADO: son cientos de fichas que
  //: casi nunca se miran una por una, y abiertas parecen una lista de errores.
  const [verDetalleHuerfanas, setVerDetalleHuerfanas] = useState(false);

  const nuevaCarga = useVigencia();
  const cargar = useCallback(async () => {
    // `listo`, no `scenarioId`: sin el tipo del escenario el par es inventado.
    // `vigente()` descarta la respuesta que llegue tarde. Ver `_contexto`.
    if (!ctx.listo) return;
    const vigente = nuevaCarga();
    setErr("");
    try {
      const r = await getBeSinClasificar(ctx.scenarioId, ctx.dataVersion, ctx.month);
      if (vigente()) setD(r);
    } catch (e) {
      if (vigente()) { setErr(String((e as Error).message || e)); setD(null); }
    }
  }, [ctx.listo, ctx.scenarioId, ctx.dataVersion, ctx.month, nuevaCarga]);
  useEffect(() => { void cargar(); }, [cargar]);

  const total = (d?.sin_regla ?? []).reduce((a, x) => a + x.amount, 0);

  async function bajar() {
    if (!d) return;
    await bajarCuadros("break_even_sin_clasificar", [{
      titulo: t("sinClasXlsTitle"),
      subtitulo: `${ctx.dataVersion} · ${t("sinClasXlsSubtitle")}`,
      hoja: t("sinClasSheet"),
      columnas: [
        { label: tc("dept"), ancho: 10, formato: "texto" },
        { label: tc("account"), ancho: 12, formato: "texto" },
        { label: t("plLine"), ancho: 28, formato: "texto" },
        { label: t("colAmount"), formato: "usd" },
      ],
      filas: d.sin_regla.map(x => ({
        label: x.dept_code || "—",
        valores: [x.account || "—", x.pl_line || t("sinLinea"), x.amount],
      })),
    }]);
  }

  /** Las reglas sin movimiento, resumidas por departamento del GL.
   *
   * Son `dept:cuenta` («0115:6000»); las que no traen `:` son reglas **por
   * línea**, que existen como respaldo y no pertenecen a un departamento. */
  const huerfanasPorDepto = useMemo(() => {
    const acc = new Map<string, number>();
    for (const x of d?.reglas_huerfanas ?? []) {
      if (!x.includes(":")) continue;
      const dep = x.split(":")[0];
      acc.set(dep, (acc.get(dep) ?? 0) + 1);
    }
    return [...acc.entries()].sort((a, b) => b[1] - a[1]);
  }, [d]);

  /** Las de respaldo por línea. Que NO se usen es la buena noticia: significa
   *  que cada cuenta encontró su regla exacta. */
  const porLinea = useMemo(
    () => (d?.reglas_huerfanas ?? []).filter(x => !x.includes(":")).length,
    [d]);

  return (
    <div className="pag pag-media" style={{ padding: "18px 22px" }}>
      <IrA esc={ctx.scenarioId} />
      <h1 style={{ fontSize: 21, fontWeight: 700 }}>{t("sinClasTitleScreen")}</h1>
      <BarraContexto ctx={ctx} set={set} escenarios={escenarios} />

      {err && (
        <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
          background: "rgba(192,57,43,.12)", border: "1px solid #c0392b", color: "#e06c5f" }}>
          {err}
        </div>
      )}

      {d && (
        <>
          <div style={{ padding: "10px 12px", borderRadius: 6, marginBottom: 14, fontSize: 13,
            background: "rgba(255,193,7,.10)", border: "1px solid #c9971b", color: "#d6a626" }}>
            {t.rich("sinClasBanner", { ...RICH, n: d.sin_regla.length, monto: usd(total) })}
          </div>

          <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
            <button onClick={() => void bajar()} style={{ padding: "8px 16px", borderRadius: 6,
              cursor: "pointer", fontSize: 13.5, fontWeight: 600,
              border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
              color: "var(--text-primary)" }}>⬇ Excel</button>
            <Link href="/break-e/configuracion" style={{ padding: "8px 16px", borderRadius: 6,
              fontSize: 13.5, fontWeight: 600, textDecoration: "none",
              border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
              color: "var(--text-primary)" }}>{t("irAConfiguracion")}</Link>
          </div>

          <div className="fin-scroll-x">
            <table className="fin-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ ...TH, textAlign: "left" }}>{t("deptoGl")}</th>
                  <th style={{ ...TH, textAlign: "left" }}>{tc("account")}</th>
                  <th style={{ ...TH, textAlign: "left" }}>{t("plLine")}</th>
                  <th style={TH}>{t("colAmount")}</th>
                </tr>
              </thead>
              <tbody>
                {d.sin_regla.map((x, i) => (
                  <tr key={`${x.dept_code}-${x.account}-${i}`}>
                    <td style={IZQ}>{x.dept_code || "—"}</td>
                    <td style={{ ...IZQ, fontFamily: "var(--font-mono, monospace)" }}>
                      {x.account || "—"}
                    </td>
                    <td style={IZQ}>{x.pl_line || <i>{t("sinLinea")}</i>}</td>
                    <td style={TD}>{usd(x.amount)}</td>
                  </tr>
                ))}
                {!d.sin_regla.length && (
                  <tr><td colSpan={4} style={{ ...IZQ, color: "#1fa363" }}>
                    {t("sinClasVacio")}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* ⚠️ Esto era un muro de 376 fichas `0115:6000` una al lado de la otra.
             * Owner: «se ven muchos errores, y muchas reglas sin movimiento… se ve
             * feo eso». Y no era solo feo: **parecía una lista de errores**, y no
             * lo es. Una regla sin movimiento no suma nada y en la mayoría de los
             * casos es lo esperable.
             *
             * Ahora se resume por departamento —catorce filas en vez de 376
             * fichas— y el detalle queda detrás de un clic, que es donde tiene
             * que estar algo que casi nunca se mira cuenta por cuenta. */}
          {/* ⚠️ Esta sección se llamaba «Reglas sin movimiento» y decía que una
             * regla que nunca encuentra su cuenta «suele significar que la
             * cuenta se renombró». **Medido: es falso, y por goleada.**
             *
             * De las 271 que no aparecen en NINGUNO de los 20 escenarios, las
             * 271 son combinaciones (departamento, cuenta) **válidas y
             * ruteables** en el `account_mapping`. Cero son basura. Son cuentas
             * normales del catálogo —`6028 Housing`, `7185 Equipment Rental`,
             * `6002 Day Off`— a las que todavía nadie les presupuestó plata.
             *
             * O sea que no están muertas: están **esperando**. Y borrarlas sería
             * el peor arreglo posible, porque el día que alguien presupueste esa
             * cuenta caería al default 100% fijo, en silencio. */}
          <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 26, marginBottom: 6 }}>
            {t("huerfanasTitulo", { n: d.reglas_huerfanas.length })}
          </h2>
          <p style={{ fontSize: 12, color: "var(--text-secondary)", maxWidth: 900,
            lineHeight: 1.6 }}>
            {t.rich("huerfanasIntro", RICH)}{" "}
            {porLinea > 0 && (
              <>{t.rich("huerfanasPorLinea", { ...RICH, n: porLinea })}{" "}</>
            )}
            {t("huerfanasOutro")}
          </p>

          <div className="fin-scroll-x" style={{ marginTop: 12, maxWidth: 620 }}>
            <table className="fin-table" style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ ...IZQ, fontSize: 11 }}>{t("departamentoGl")}</th>
                  <th style={{ ...DER, fontSize: 11 }}>{t("reglasSinMovimiento")}</th>
                </tr>
              </thead>
              <tbody>
                {huerfanasPorDepto.map(([dep, n]) => (
                  <tr key={dep}>
                    <td style={IZQ}>{dep}</td>
                    <td style={DER}>{n}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            onClick={() => setVerDetalleHuerfanas(v => !v)}
            style={{ marginTop: 10, padding: "6px 12px", borderRadius: 6, fontSize: 12,
              cursor: "pointer", border: "1px solid var(--border-medium)",
              background: "var(--bg-surface)", color: "var(--text-secondary)" }}>
            {verDetalleHuerfanas ? t("ocultarDetalle")
              : t("verDetalleCuentaPorCuenta", { n: d.reglas_huerfanas.length })}
          </button>

          {verDetalleHuerfanas && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
              {d.reglas_huerfanas.map(x => (
                <span key={x} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 999,
                  background: "var(--bg-surface)", border: "1px solid var(--border-subtle)",
                  color: "var(--text-secondary)" }}>{x}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
