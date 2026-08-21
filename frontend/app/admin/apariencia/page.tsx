"use client";
/**
 * Admin → Apariencia. Las cuatro paletas, elegibles.
 *
 * **El pedido (owner, 2026-08-19).** «No sé qué tan cansado sea estar viendo
 * negro en el fondo… ¿es posible que este set de colores estén en el admin y
 * puedan ser escogibles?»
 *
 * ⚠️ **Cada tarjeta se pinta con SU propia paleta, no con la activa.** Se hace
 * con `data-tema` sobre el contenedor de la muestra: los mismos bloques del
 * `globals.css` que usa la app entera. Si la muestra tuviera colores propios,
 * el día que alguien cambie una paleta la vista previa seguiría mostrando la
 * vieja — y elegir a ciegas es exactamente lo que esta pantalla viene a evitar.
 *
 * El cambio se aplica al instante sobre `<html>` para que se vea sin recargar;
 * la cookie y el backend guardan la elección para la próxima visita, donde el
 * tema ya sale puesto desde el servidor (ver `app/layout.tsx`).
 */
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { guardarTema } from "@/lib/api";
import { CATALOGO, TEMA_POR_DEFECTO, readTemaCookie, type Tema } from "@/lib/tema";

export default function AparienciaPage() {
  const t = useTranslations("apariencia");
  const [activo, setActivo] = useState<Tema>(TEMA_POR_DEFECTO);
  const [guardado, setGuardado] = useState<Tema | null>(null);

  // Se lee después de montar: la cookie no existe en el render del servidor.
  useEffect(() => { setActivo(readTemaCookie() ?? TEMA_POR_DEFECTO); }, []);

  async function elegir(tema: Tema) {
    if (tema === activo) return;
    setActivo(tema);
    document.documentElement.setAttribute("data-tema", tema);
    await guardarTema(tema);
    setGuardado(tema);
  }

  return (
    <div className="pag pag-lectura">
      <h1 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 4px" }}>{t("titulo")}</h1>
      <p style={{ margin: "0 0 20px", color: "var(--text-secondary)", fontSize: 13, maxWidth: "68ch" }}>
        {t("subtitulo")}
      </p>

      <div style={{
        display: "grid", gap: 16,
        gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
      }}>
        {CATALOGO.map(p => {
          const on = p.id === activo;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => elegir(p.id)}
              aria-pressed={on}
              style={{
                display: "flex", flexDirection: "column", gap: 10, textAlign: "left",
                padding: 12, cursor: "pointer", font: "inherit", color: "inherit",
                background: "var(--bg-surface)",
                border: `1px solid ${on ? "var(--brand)" : "var(--border-medium)"}`,
                boxShadow: on ? "0 0 0 2px var(--brand)" : "none",
                borderRadius: 8,
              }}
            >
              <span style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <b style={{ fontSize: 14 }}>{t(`nombre.${p.id}`)}</b>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                  {p.claro ? t("claro") : t("oscuro")}
                </span>
                {on && (
                  <span style={{
                    marginLeft: "auto", fontSize: 10, fontWeight: 700, letterSpacing: .5,
                    color: "var(--brand)",
                  }}>{t("enUso")}</span>
                )}
              </span>

              {/* La muestra, pintada con SU paleta */}
              <span data-tema={p.id} style={{
                display: "block", borderRadius: 6, overflow: "hidden",
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-base)", color: "var(--text-primary)",
              }}>
                <span style={{
                  display: "flex", alignItems: "center", gap: 6, padding: "6px 8px",
                  background: "var(--bg-header)",
                  borderBottom: "1px solid var(--border-medium)",
                  fontSize: 10, color: "var(--nav-fg)",
                }}>
                  <b style={{ color: "var(--nav-fg-strong)" }}>FinPlan</b>
                  <span style={{ boxShadow: "inset 0 -2px 0 var(--brand)", color: "var(--nav-fg-strong)" }}>
                    Dashboard
                  </span>
                  <span>Reports</span>
                </span>
                <span style={{ display: "block", padding: 8 }}>
                  <span style={{
                    display: "block", padding: 8, borderRadius: 4,
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-subtle)",
                  }}>
                    <span style={{
                      display: "block", fontSize: 9, letterSpacing: .7,
                      color: "var(--text-secondary)",
                    }}>TOTAL REVENUE</span>
                    <span style={{ display: "block", fontSize: 18, fontWeight: 700, marginTop: 2 }}>
                      $6.37M
                    </span>
                    <span style={{ display: "block", fontSize: 10, marginTop: 3 }}>
                      <span style={{ color: "var(--positive)", fontWeight: 600 }}>+1,169,115</span>
                      <span style={{ color: "var(--text-secondary)" }}> · </span>
                      <span style={{ color: "var(--negative)", fontWeight: 600 }}>−59</span>
                    </span>
                  </span>
                </span>
              </span>

              <span style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>
                {t(`que.${p.id}`)}
              </span>
            </button>
          );
        })}
      </div>

      {guardado && (
        <p style={{ marginTop: 16, fontSize: 12, color: "var(--positive)" }}>
          {t("guardado")}
        </p>
      )}

      <p style={{
        marginTop: 24, maxWidth: "70ch", fontSize: 12.5, lineHeight: 1.6,
        color: "var(--text-secondary)",
        borderLeft: "3px solid var(--border-medium)", paddingLeft: 12,
      }}>
        {t("nota")}
      </p>

      <p style={{ marginTop: 12, fontSize: 12, color: "var(--text-disabled)" }}>
        {t("alcance")}
      </p>
    </div>
  );
}
