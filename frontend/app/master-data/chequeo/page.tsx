"use client";
/**
 * Master Data → Chequeo de la propiedad.
 *
 * **Por qué existe (owner, 2026-08-14).** Va a sacar cuatro copias de la app,
 * una por hotel. La forma en que un clon sale mal **no da error**: la app
 * levanta, las pantallas pintan, los totales cuadran — y resulta que la base
 * quedó con el `hotel_id` de Corcovado, o que el motor del P&L no se sembró y
 * todo el GL que se suba va a caer en ninguna línea.
 *
 * Eso solo se descubre mirando, y se descubre tarde. Acá se pregunta de una vez.
 *
 * **No corre solo.** Hay que apretar «Correr»: es un chequeo, no un semáforo de
 * fondo. Y **no arregla nada** — uno que además corrige es uno en el que no se
 * puede confiar cuando dice que está todo bien.
 */
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { getChequeo, type Chequeo, type ChequeoItem } from "@/lib/api";
import { NAV } from "@/components/TopNav";
import { HOTEL_ID } from "@/lib/hotel";
import { getTabsApagados, NADA_APAGADO, type TabsApagados }
  from "@/lib/tabsVisibles";
import { bajarCuadros, type ColumnaCuadro, type FilaCuadro } from "@/lib/exportCuadro";
import IrA from "@/components/IrA";

const BTN: React.CSSProperties = {
  padding: "9px 18px", borderRadius: 6, cursor: "pointer",
  border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
  color: "var(--text-primary)", fontSize: 14, fontWeight: 600,
};

const COLOR: Record<string, string> = {
  error: "#C0392B", aviso: "#856404", ok: "#1A7F4B",
  info: "var(--border-medium)",
};

export default function ChequeoPage() {
  const t = useTranslations("healthCheck");
  const tc = useTranslations("common");
  const [datos, setDatos] = useState<Chequeo | null>(null);
  const [corriendo, setCorriendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apagados, setApagados] = useState<TabsApagados>(NADA_APAGADO);

  const ETIQUETA: Record<string, string> = {
    error: t("etError"), aviso: t("etAviso"), ok: t("etOk"), info: t("etInfo"),
  };

  async function correr() {
    setCorriendo(true); setError(null);
    try {
      const [c, ap] = await Promise.all([
        getChequeo(),
        // Falla PRENDIDO, igual que la barra: quedarse sin este renglon porque
        // un endpoint tardo seria peor que mostrarlo completo de mas.
        getTabsApagados(HOTEL_ID).catch(() => NADA_APAGADO),
      ]);
      setApagados(ap); setDatos(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : tc("error"));
    } finally { setCorriendo(false); }
  }

  /**
   * Cuantos tabs y cuantas pantallas se estan viendo, de las que existen.
   *
   * **Por que esta aca (owner, 2026-08-20).** *«Me paso con DAILY-OPS: lo cloné
   * para Amarena y desaparecieron todos los subs.»* En FinPlan la barra es una
   * lista del codigo y no se arma con datos, asi que no puede vaciarse por una
   * base en cero — pero eso hay que poder **verlo**, no creerlo. Al llegar a la
   * propiedad nueva esto se lee en un renglon en vez de ir tab por tab.
   *
   * Se calcula aca y no en el backend a proposito: `NAV` es la unica lista de
   * lo que existe, y copiarla al servidor seria una segunda lista que alguien
   * tendria que acordarse de actualizar.
   */
  const barra: ChequeoItem = useMemo(() => {
    const tabFuera = new Set(apagados.TAB);
    const itemFuera = new Set(apagados.ITEM);
    // Pantallas UNICAS: hay entradas que aparecen en dos menus, y contar
    // apariciones haria que sacar un duplicado se leyera como perder una
    // pantalla.
    const todas = new Set<string>();
    const escondidas = new Set<string>();
    const sinConstruir = new Set<string>();
    for (const g of NAV) {
      for (const i of g.items) {
        if (i.header) continue;
        if (!i.href || i.disabled) { sinConstruir.add(i.key); continue; }
        todas.add(i.key);
        if (tabFuera.has(g.key) || itemFuera.has(i.key)) escondidas.add(i.key);
      }
    }
    const tabsFuera = NAV.filter(g => tabFuera.has(g.key)).length;
    const n = todas.size, oculto = escondidas.size;
    const pendientes = sinConstruir.size
      ? " " + t("barraSinConstruir", { n: sinConstruir.size }) : "";
    return {
      clave: "barra",
      titulo: t("barraTitulo"),
      estado: oculto || tabsFuera ? "aviso" : "ok",
      detalle: oculto || tabsFuera
        ? t("barraEscondidos", {
            tabs: NAV.length - tabsFuera, totalTabs: NAV.length,
            n: n - oculto, total: n,
            cuales: [...escondidas].join(", "),
          }) + pendientes
        : t("barraOk", { tabs: NAV.length, n }) + pendientes,
      porque: oculto || tabsFuera ? t("barraEscondidosPorque") : "",
      que_hacer: oculto || tabsFuera ? t("barraEscondidosQueHacer") : "",
    };
  }, [apagados, t]);

  function bajar() {
    if (!datos) return;
    const columnas: ColumnaCuadro[] = [
      { label: t("colChequeo"), ancho: 30 },
      { label: tc("status"), ancho: 10, formato: "texto" },
      { label: t("colDetalle"), ancho: 70, formato: "texto" },
      { label: t("colQueHacer"), ancho: 60, formato: "texto" },
    ];
    const filas: FilaCuadro[] = [...datos.chequeos, barra].map(c => ({
      label: c.titulo,
      valores: [ETIQUETA[c.estado] ?? c.estado, c.detalle, c.que_hacer || "—"],
    }));
    bajarCuadros("chequeo_propiedad", [{
      titulo: t("titulo"),
      subtitulo: `${datos.hotel_id} · ${datos.hotel_name}`,
      hoja: t("hojaChequeo"), columnas, filas,
    }]);
  }

  const resumen = !datos ? null
    : datos.errores ? { txt: t("resumenErrores", { n: datos.errores }), col: COLOR.error }
    : datos.avisos ? { txt: t("resumenAvisos", { n: datos.avisos }), col: COLOR.aviso }
    : { txt: t("todoEnOrden"), col: COLOR.ok };

  const b = (c: React.ReactNode) => <strong>{c}</strong>;

  return (
    <div className="pag pag-lectura" style={{ padding: "20px 24px" }}>
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4 }}>
        {t("titulo")}
      </h1>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 20 }}>
        {t.rich("intro", { b })}
      </p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 22 }}>
        <button onClick={correr} disabled={corriendo}
                style={{ ...BTN, opacity: corriendo ? 0.5 : 1 }}>
          {corriendo ? t("corriendo") : t("correr")}
        </button>
        {datos && <button onClick={bajar} style={BTN}>{t("bajarCuadro")}</button>}
        {resumen && (
          <span style={{ fontSize: 14, fontWeight: 700, color: resumen.col }}>
            {resumen.txt}
          </span>
        )}
      </div>

      {error && (
        <div style={{
          border: "1px solid #C0392B", borderRadius: 8, padding: 14,
          color: "#C0392B", fontSize: 13,
        }}>{error}</div>
      )}

      {datos && (
        <>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 14 }}>
            {t("instalacion")} <strong>{datos.hotel_id}</strong> · {datos.hotel_name}
          </p>
          {[...datos.chequeos, barra].map((c: ChequeoItem) => (
            <div key={c.clave} style={{
              border: "1px solid var(--border-subtle)",
              borderLeft: `3px solid ${COLOR[c.estado] ?? "var(--border-medium)"}`,
              borderRadius: 8, background: "var(--bg-surface)",
              padding: "12px 14px", marginBottom: 10,
            }}>
              <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{
                  fontSize: 10, fontWeight: 800, letterSpacing: ".06em",
                  color: COLOR[c.estado] ?? "var(--text-secondary)", minWidth: 56,
                }}>
                  {ETIQUETA[c.estado] ?? c.estado}
                </span>
                <strong style={{ fontSize: 14 }}>{c.titulo}</strong>
              </div>
              <div style={{ fontSize: 13, marginTop: 6, marginLeft: 66 }}>{c.detalle}</div>
              {c.porque && (
                <div style={{
                  fontSize: 12, marginTop: 6, marginLeft: 66,
                  color: "var(--text-secondary)",
                }}>{c.porque}</div>
              )}
              {c.que_hacer && (
                <div style={{ fontSize: 12, marginTop: 6, marginLeft: 66 }}>
                  <strong>{t("queHacer")}</strong> {c.que_hacer}
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
