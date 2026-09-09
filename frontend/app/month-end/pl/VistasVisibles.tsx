"use client";
/**
 * Qué se ve y qué no: menú, sub-menú y sub-tabs, en un solo panel.
 *
 * Owner, 2026-09-02: *«esta vista la van a ver los dueños; me gustaría poder
 * quitar y poner tabs sin borrarlas, sólo para dejar lo importante»* y, al ver
 * que los reportes se administraban en otra pantalla, *«quizás si pudieras ahí
 * mismo hacer para escoger también… del menú y sub menú, y todo lo de
 * adentro»*.
 *
 * ## Los tres niveles
 *
 * | | qué esconde |
 * |---|---|
 * | `TAB` | un tab de la barra, con todo su menú adentro |
 * | `ITEM` | una entrada de ese menú — una pantalla o un reporte |
 * | `SUBTAB` | una vista dentro de una pantalla (los quince de Cierre de Mes) |
 *
 * **Se curan desde acá los tres, pero de a uno.** Las 96 entradas del menú
 * junto a los quince sub-tabs no se leen; el interruptor de nivel es lo que
 * hace que el panel siga cabiendo arriba del reporte.
 *
 * ## Las reglas, iguales a las de la barra
 *
 * Es la MISMA matriz (`tab_enablement`) que administra `/admin/tabs`, así que
 * las dos pantallas **no pueden decir cosas distintas** — no hay copia, hay un
 * segundo camino a la misma fila. Y hereda las reglas ya probadas:
 *
 * * **La tabla es esparsa y el default es PRENDIDO.** Sin fila, se ve: el día
 *   que esto se despliega no cambia nada, y un reporte nuevo nace visible. Al
 *   revés —nacer oculto— sería peor: se construye algo, nadie lo ve, y nadie
 *   sabe que existe para poder prenderlo.
 * * **Prender BORRA la fila**, así la tabla contiene sólo lo que alguien apagó.
 * * **Se puede apagar TODO sin quedarse afuera.** El botón que abre este panel
 *   no es un sub-tab ni una entrada del menú: sigue ahí aunque no quede nada.
 *
 * ## Esconde, no es un permiso
 *
 * ⚠️ La ruta sigue respondiendo y el dato sigue viajando: quien conozca la URL
 * entra igual. Para *impedir* está el perfil `viewer` (`app/perfiles.py`), que
 * hace que el servidor rechace toda escritura. Las dos capas se complementan:
 * ésta ordena la vista, aquélla impide el cambio.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { NAV } from "@/components/TopNav";
import { HOTEL_ID } from "@/lib/hotel";
import {
  getTabsApagados, saveTabsApagados, PERFILES, ROTULO_PERFIL,
  type Perfil, type TabsApagados,
} from "@/lib/tabsVisibles";

export default function VistasVisibles({ vistas, rotulo, onCambio, onCerrar }: {
  /** Las claves de todos los sub-tabs, en el orden de la pantalla. */
  vistas: readonly string[];
  rotulo: (k: string) => string;
  onCambio: (nuevos: string[]) => void;
  onCerrar: () => void;
}) {
  const t = useTranslations("nav");
  /** Qué se está curando: los sub-tabs de esta pantalla, o el menú entero. */
  const [nivel, setNivel] = useState<"SUBTAB" | "MENU">("SUBTAB");
  /** Qué grupo del menú se está mirando. */
  const [grupo, setGrupo] = useState<string>(NAV[0]?.key || "");
  /** Para QUIÉN se configura. `""` = para toda la propiedad.
   *
   *  Arranca en la propiedad porque es la decisión que manda: lo que se apaga
   *  ahí no lo ve nadie, y afinar por perfil sólo tiene sentido después. */
  const [perfil, setPerfil] = useState<Perfil>("");
  const [estado, setEstado] = useState<TabsApagados | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      // ⚠️ `perfil` va SIEMPRE, incluso vacío: sin él el backend contestaría
      // por el rol de quien abrió el panel, y estaríamos editando la vista del
      // admin creyendo que editamos la de la propiedad.
      setEstado(await getTabsApagados(HOTEL_ID, perfil));
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo cargar");
    }
  }, [perfil]);

  useEffect(() => { cargar(); }, [cargar]);

  const fuera = useMemo(() => new Set(estado?.SUBTAB ?? []), [estado]);
  const fueraTab = useMemo(() => new Set(estado?.TAB ?? []), [estado]);
  const fueraItem = useMemo(() => new Set(estado?.ITEM ?? []), [estado]);

  const rotuloGrupo = (k: string) => {
    try { return t(`groups.${k}`); } catch { return k; }
  };
  const rotuloItem = (i: { key: string; header?: boolean }) => {
    try { return t(`${i.header ? "headers" : "items"}.${i.key}`); }
    catch { return i.key; }
  };
  const actual = NAV.find(g => g.key === grupo);
  // Los encabezados no son pantallas: no se apagan, separan.
  const entradas = (actual?.items || []).filter(i => !i.header);

  /** Guarda cualquiera de los tres niveles por la MISMA puerta. */
  async function guardar(
    filas: { scope_kind: "TAB" | "ITEM" | "SUBTAB"; clave: string; visible: boolean }[],
  ) {
    setGuardando(true); setError(null);
    try {
      const r = await saveTabsApagados(HOTEL_ID, filas, perfil);
      setEstado(r.estado);
      // La pantalla se entera sola SÓLO cuando se tocó su propia vista. Si se
      // está configurando el perfil de otro, esta barra no cambia — y avisar lo
      // contrario sería mentir, porque al recargar vuelve.
      if (!perfil) onCambio(r.estado.SUBTAB);
    } catch (e) {
      setError(e instanceof Error ? e.message : "no se pudo guardar");
    } finally { setGuardando(false); }
  }

  const btn: React.CSSProperties = {
    padding: "4px 10px", fontSize: 11.5, borderRadius: 5, cursor: "pointer",
    border: "1px solid var(--border-medium)", background: "var(--bg-surface)",
    color: "var(--text-secondary)",
  };

  /** Un botón de encender/apagar. Tachado = escondido. */
  const chip = (clave: string, texto: string, visible: boolean,
                kind: "TAB" | "ITEM" | "SUBTAB") => (
    <button key={kind + clave} disabled={guardando}
      onClick={() => guardar([{ scope_kind: kind, clave, visible: !visible }])}
      title={visible ? "Se ve — click para esconder"
                     : "Escondido — click para mostrar"}
      style={{ ...btn, fontWeight: 600,
               opacity: visible ? 1 : 0.5,
               background: visible ? "var(--bg-elevated)" : "transparent",
               color: visible ? "var(--text-primary)" : "var(--text-disabled)",
               textDecoration: visible ? "none" : "line-through" }}>
      {visible ? "☑" : "☐"} {texto}
    </button>
  );

  const nivelBtn = (k: "SUBTAB" | "MENU", texto: string) => (
    <button onClick={() => setNivel(k)} disabled={guardando}
      style={{ ...btn, fontWeight: nivel === k ? 700 : 500,
               background: nivel === k ? "var(--brand)" : "var(--bg-surface)",
               color: nivel === k ? "#fff" : "var(--text-secondary)" }}>
      {texto}
    </button>
  );

  return (
    <div style={{
      padding: "12px 16px", marginBottom: 14, borderRadius: 9,
      border: "1px solid var(--border)",
      borderLeft: "4px solid var(--brand)",
      background: "var(--bg-surface)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", gap: 12, marginBottom: 10 }}>
        <b style={{ fontSize: 13 }}>Qué se ve</b>
        <button onClick={onCerrar} style={btn}>Cerrar</button>
      </div>

      {/* ── Para quién ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap",
                    alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 11.5, color: "var(--text-secondary)",
                       fontWeight: 700 }}>Para:</span>
        {PERFILES.map(pf => (
          <button key={pf || "todos"} onClick={() => setPerfil(pf)} disabled={guardando}
            style={{ ...btn, fontWeight: perfil === pf ? 700 : 500,
                     background: perfil === pf ? "var(--brand)" : "var(--bg-surface)",
                     color: perfil === pf ? "#fff" : "var(--text-secondary)" }}>
            {ROTULO_PERFIL[pf]}
          </button>
        ))}
      </div>

      {perfil && (
        <p style={{ fontSize: 11.5, color: "var(--text-secondary)",
                    lineHeight: 1.55, margin: "0 0 10px", maxWidth: 800 }}>
          Estás viendo <b>sólo lo apagado para {ROTULO_PERFIL[perfil]}</b>. Lo que
          apagaste en <b>Toda la propiedad</b> también le aplica y no aparece
          marcado acá: se suman, no se reemplazan. Por eso prender algo acá no lo
          devuelve si la propiedad lo tiene apagado.
        </p>
      )}

      {/* ── Qué nivel ──────────────────────────────────────────────────────
          Owner, 2026-09-02: «del menú y sub menú, y todo lo de adentro». Son
          tres niveles y se curan desde acá los tres, pero de a uno: las 96
          entradas del menú junto a los quince sub-tabs no se leen. */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap",
                    alignItems: "center", marginBottom: 10,
                    paddingTop: 8, borderTop: "1px solid var(--border)" }}>
        {nivelBtn("SUBTAB", "Sub-tabs de esta pantalla")}
        {nivelBtn("MENU", "Menú y reportes")}
        <span style={{ flex: 1 }} />
        {nivel === "SUBTAB" ? (
          <>
            <button disabled={guardando} style={btn}
              onClick={() => guardar(vistas.map(k =>
                ({ scope_kind: "SUBTAB" as const, clave: k, visible: true })))}>
              Mostrar todos
            </button>
            <button disabled={guardando} style={btn}
              onClick={() => guardar(vistas.map(k =>
                ({ scope_kind: "SUBTAB" as const, clave: k, visible: false })))}>
              Esconder todos
            </button>
          </>
        ) : (
          <>
            <button disabled={guardando} style={btn}
              onClick={() => guardar(entradas.map(i =>
                ({ scope_kind: "ITEM" as const, clave: i.key, visible: true })))}>
              Mostrar todo el grupo
            </button>
            <button disabled={guardando} style={btn}
              onClick={() => guardar(entradas.map(i =>
                ({ scope_kind: "ITEM" as const, clave: i.key, visible: false })))}>
              Esconder todo el grupo
            </button>
          </>
        )}
      </div>

      {nivel === "SUBTAB" ? (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {vistas.map(k => chip(k, rotulo(k), !fuera.has(k), "SUBTAB"))}
        </div>
      ) : (
        <>
          {/* Los TABS de primer nivel. La casilla esconde el tab ENTERO —con su
              menú adentro—; el nombre sólo elige cuál se está mirando. Son dos
              cosas distintas y por eso son dos botones pegados: con uno solo,
              elegir un tab para ver sus reportes lo escondería. */}
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4,
                        color: "var(--text-secondary)", marginBottom: 5 }}>
            MENÚ · la casilla esconde el tab entero, el nombre elige cuál mirar
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {NAV.map(g => {
              const vis = !fueraTab.has(g.key);
              const sel = g.key === grupo;
              return (
                <span key={g.key} style={{ display: "inline-flex" }}>
                  <button disabled={guardando}
                    onClick={() => guardar([{ scope_kind: "TAB", clave: g.key,
                                              visible: !vis }])}
                    title={vis ? "Se ve — click para esconder el tab entero"
                               : "Escondido — click para mostrarlo"}
                    style={{ ...btn, borderRadius: "5px 0 0 5px", padding: "4px 7px",
                             opacity: vis ? 1 : 0.5 }}>
                    {vis ? "☑" : "☐"}
                  </button>
                  <button onClick={() => setGrupo(g.key)} disabled={guardando}
                    style={{ ...btn, borderRadius: "0 5px 5px 0", borderLeft: "none",
                             fontWeight: sel ? 700 : 500,
                             background: sel ? "var(--brand)" : "var(--bg-surface)",
                             color: sel ? "#fff" : "var(--text-secondary)",
                             textDecoration: vis ? "none" : "line-through" }}>
                    {rotuloGrupo(g.key)}
                  </button>
                </span>
              );
            })}
          </div>

          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.4,
                        color: "var(--text-secondary)", marginBottom: 5 }}>
            DENTRO DE {rotuloGrupo(grupo).toUpperCase()}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {entradas.map(i => chip(i.key, rotuloItem(i), !fueraItem.has(i.key), "ITEM"))}
            {!entradas.length && (
              <span style={{ fontSize: 11.5, color: "var(--text-secondary)" }}>
                Este tab es una sola pantalla: se esconde con su casilla de arriba.
              </span>
            )}
          </div>
        </>
      )}

      {error && <p style={{ fontSize: 11.5, color: "var(--negative)",
                            margin: "10px 0 0" }}>{error}</p>}

      <p style={{ fontSize: 11, color: "var(--text-secondary)",
                  lineHeight: 1.55, margin: "12px 0 0", maxWidth: 830 }}>
        <b>Esconde, no borra.</b> El dato sigue ahí y vuelve con un click. No es
        un permiso: quien conozca la URL entra igual — para impedir cambios está
        el perfil <b>Sólo lectura</b>, que se asigna en Usuarios. Es la misma
        matriz que administra <span className="mono">/admin/tabs</span>, así que
        las dos pantallas no pueden decir cosas distintas.
      </p>
    </div>
  );
}
