"use client";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { api } from "@/lib/api";
import { LOCALES, writeLocaleCookie, type Locale } from "@/lib/locale";

/**
 * El botón de un click (decisión D1, la segunda mitad: el otro lado es el
 * `<select>` de Provisionamiento, que fija el default de la propiedad).
 *
 * Guarda la preferencia del usuario en el backend, sincroniza la cookie y
 * recarga: los mensajes se resuelven en el servidor, así que sin recargar la
 * mitad de la pantalla quedaría en el idioma viejo.
 *
 * Si el backend falla, el idioma igual cambia en esta sesión — nadie se queda
 * mirando un botón que no hace nada porque se cayó la red. Lo que se pierde es
 * la persistencia, no el cambio.
 */
export default function LanguageSwitch() {
  const actual = useLocale();
  const t = useTranslations("common");
  const [busy, setBusy] = useState(false);

  async function cambiar(l: Locale) {
    if (l === actual || busy) return;
    setBusy(true);
    writeLocaleCookie(l);
    try {
      await api.patch<unknown>("/auth/me/locale", { locale: l });
    } catch {
      /* sin sesión o backend caído: la cookie ya cambió, la preferencia no se guarda */
    }
    window.location.reload();
  }

  return (
    <div
      title={t("languageSwitch")}
      style={{
        display: "flex", alignItems: "center",
        border: "1px solid var(--nav-borde)", borderRadius: 4, overflow: "hidden",
        opacity: busy ? 0.5 : 1,
      }}
    >
      {LOCALES.map(l => {
        const on = l === actual;
        return (
          <button
            key={l}
            onClick={() => cambiar(l)}
            aria-pressed={on}
            disabled={busy}
            style={{
              background: on ? "var(--nav-chip-bg)" : "none",
              color: on ? "var(--nav-chip-fg)" : "var(--nav-fg)",
              border: "none",
              padding: "3px 8px",
              fontSize: 11,
              fontWeight: on ? 700 : 400,
              letterSpacing: 0.5,
              cursor: on || busy ? "default" : "pointer",
              textTransform: "uppercase",
            }}
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}
