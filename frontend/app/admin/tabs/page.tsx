"use client";
//
// Qué tabs y reportes ve ESTA propiedad.
//
// Owner, 2026-08-20: «no todas las propiedades van a ver todos los reportes, ya
// que son muchos para cada propiedad y se van a perder» · «así como los
// departamentos se van a limitar, así se van a limitar los reportes y los tabs
// principales» · «todo debe poderse esconder y habilitar» · «la lógica debe ser
// escojo el tab principal y dentro de esa lista escojo lo que quiero, y activo
// para el hotel».
//
// Medido: la barra tiene 13 tabs y 96 entradas. Una propiedad nueva abre con
// las 96, y encontrar el reporte que se usa es el problema.
//
// ⚠️ **El catálogo sale de la barra (`NAV`), no de una lista de acá.** Es la
// única lista de lo que existe: copiarla sería una segunda lista que habría que
// acordarse de actualizar, y este proyecto ya pagó dos veces por una escrita a
// mano. Un reporte nuevo aparece solo en esta pantalla.
//
// ⚠️ **Esto ESCONDE de la barra; no es un permiso.** La ruta sigue
// respondiendo: quien escriba la URL entra igual. Es lo que hace seguro poder
// apagarlo todo —incluida esta pantalla—, y la pantalla lo dice.
//
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import IrA from "@/components/IrA";
import { NAV } from "@/components/TopNav";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getTabsApagados, saveTabsApagados, NADA_APAGADO, type TabsApagados,
} from "@/lib/tabsVisibles";

/** Esta misma pantalla. Apagarla se puede —el owner lo pidió— pero se avisa. */
const YO = "tabsProvisioning";

export default function TabsProvisioningPage() {
  const t = useTranslations("nav");
  const [apagados, setApagados] = useState<TabsApagados>(NADA_APAGADO);
  const [tab, setTab] = useState<string>(NAV[0]?.key || "");
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setApagados(await getTabsApagados(HOTEL_ID));
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  // Los rótulos salen del mismo diccionario que la barra: si acá dijeran otra
  // cosa, apagarías un nombre y desaparecería otro.
  const rotuloTab = (k: string) => {
    try { return t(`groups.${k}`); } catch { return k; }
  };
  const rotuloItem = (i: { key: string; header?: boolean }) => {
    try { return t(`${i.header ? "headers" : "items"}.${i.key}`); }
    catch { return i.key; }
  };

  const tabFuera = useMemo(() => new Set(apagados.TAB), [apagados]);
  const itemFuera = useMemo(() => new Set(apagados.ITEM), [apagados]);

  const grupo = NAV.find(g => g.key === tab);
  // Los encabezados no son pantallas: no se apagan, se muestran como separador.
  const entradas = (grupo?.items || []).filter(i => !i.header);

  async function guardar(rows: { scope_kind: "TAB" | "ITEM"; clave: string; visible: boolean }[]) {
    setGuardando(true);
    setError(null); setAviso(null);
    try {
      const r = await saveTabsApagados(HOTEL_ID, rows);
      setApagados(r.estado);
      const n = r.apagados + r.prendidos;
      // La barra se entera sola (`alCambiarTabs`): mandar a recargar se lee
      // como «no guardó».
      setAviso(n
        ? `Guardado para ${HOTEL_ID}: ${r.apagados} escondido(s), ${r.prendidos} habilitado(s)`
        : "Sin cambios");
      if (rows.some(x => x.clave === YO && !x.visible)) {
        setAviso("Escondiste esta misma pantalla. Se sigue entrando por su URL: /admin/tabs");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "no se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  const alternarTab = (k: string) =>
    guardar([{ scope_kind: "TAB", clave: k, visible: tabFuera.has(k) }]);

  const alternarItem = (k: string) =>
    guardar([{ scope_kind: "ITEM", clave: k, visible: itemFuera.has(k) }]);

  const todas = (visible: boolean) =>
    guardar(entradas.map(i => ({ scope_kind: "ITEM" as const, clave: i.key, visible })));

  const fila: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: 10, padding: "7px 10px",
    borderBottom: "1px solid var(--border)",
  };

  return (
    <div className="pag-media">
      <IrA />
      <h1 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
        Tabs y reportes de la propiedad
      </h1>
      <p style={{ color: "var(--text-secondary)", fontSize: 13,
                  marginBottom: 14, maxWidth: 860, lineHeight: 1.65 }}>
        Elegí el tab principal y marcá dentro de su lista lo que{" "}
        <b>{HOTEL_ID}</b> tiene que ver. La app trae <b>{NAV.length} tabs</b> y{" "}
        <b>{NAV.reduce((n, g) => n + g.items.filter(i => !i.header).length, 0)} pantallas</b>:
        una propiedad las ve todas hasta que acá se apague algo.
      </p>

      <div style={{
        padding: "10px 14px", borderRadius: 9, maxWidth: 860, marginBottom: 16,
        border: "1px solid var(--border)",
        borderLeft: "4px solid var(--warning, #B8860B)",
        fontSize: 12.5, color: "var(--text-secondary)", lineHeight: 1.6,
      }}>
        <b>Esconde de la barra; no es un permiso.</b> La ruta sigue
        respondiendo: quien escriba la URL entra igual, y el reporte devuelve lo
        mismo. Si hace falta impedir el acceso, eso son roles — no esta
        pantalla. Por eso se puede apagar todo sin quedarse afuera: hasta ésta
        se recupera entrando a <span className="mono">/admin/tabs</span>.
      </div>

      {error && <p style={{ color: "var(--negative)", fontSize: 13 }}>{error}</p>}
      {aviso && <p style={{ color: "var(--positive)", fontSize: 13 }}>{aviso}</p>}
      {cargando && (
        <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>Cargando…</p>
      )}

      {!cargando && (
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap",
                      alignItems: "flex-start" }}>
          {/* ── Los tabs principales ──────────────────────────────────── */}
          <div style={{ flex: "0 0 250px", border: "1px solid var(--border)",
                        borderRadius: 9, overflow: "hidden" }}>
            <div style={{ ...fila, fontWeight: 700, fontSize: 12,
                          background: "var(--bg-surface)" }}>
              Tab principal
            </div>
            {NAV.map(g => {
              const escondido = tabFuera.has(g.key);
              const dentroFuera = g.items.filter(
                i => !i.header && itemFuera.has(i.key)).length;
              const total = g.items.filter(i => !i.header).length;
              return (
                <div key={g.key} style={{
                  ...fila,
                  background: g.key === tab ? "var(--bg-surface)" : undefined,
                  cursor: "pointer",
                  opacity: escondido ? 0.5 : 1,
                }} onClick={() => setTab(g.key)}>
                  <input type="checkbox" checked={!escondido} disabled={guardando}
                         onClick={ev => ev.stopPropagation()}
                         onChange={() => alternarTab(g.key)}
                         title="Apagar el tab entero esconde también todo lo que tiene adentro" />
                  <span style={{ flex: 1, fontSize: 13,
                                 fontWeight: g.key === tab ? 700 : 400 }}>
                    {rotuloTab(g.key)}
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    {total - dentroFuera}/{total}
                  </span>
                </div>
              );
            })}
          </div>

          {/* ── Lo que hay dentro del tab elegido ──────────────────────── */}
          <div style={{ flex: "1 1 430px", border: "1px solid var(--border)",
                        borderRadius: 9, overflow: "hidden" }}>
            <div style={{ ...fila, fontWeight: 700, fontSize: 12,
                          background: "var(--bg-surface)" }}>
              <span style={{ flex: 1 }}>Dentro de «{rotuloTab(tab)}»</span>
              <button className="fin-btn" disabled={guardando || !entradas.length}
                      onClick={() => todas(true)}>Todo</button>
              <button className="fin-btn" disabled={guardando || !entradas.length}
                      onClick={() => todas(false)}>Nada</button>
            </div>

            {tabFuera.has(tab) && (
              <div style={{ ...fila, color: "var(--warning, #B8860B)",
                            fontSize: 12.5 }}>
                El tab está apagado, así que nada de esta lista se ve — aunque
                acá figure marcado.
              </div>
            )}

            {entradas.length === 0 && (
              <div style={{ ...fila, color: "var(--text-secondary)", fontSize: 13 }}>
                Este tab es un enlace directo, no tiene lista adentro.
              </div>
            )}

            {entradas.map(i => (
              <label key={i.key} style={{ ...fila, cursor: "pointer" }}>
                <input type="checkbox" checked={!itemFuera.has(i.key)}
                       disabled={guardando}
                       onChange={() => alternarItem(i.key)} />
                <span style={{ flex: 1, fontSize: 13 }}>{rotuloItem(i)}</span>
                <span className="mono" style={{ fontSize: 11,
                                                color: "var(--text-disabled)" }}>
                  {i.href}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
