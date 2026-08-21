/**
 * Idioma — las piezas compartidas entre el servidor y el cliente.
 *
 * La verdad vive en la base (`users.locale` → `hotels.default_locale` → `es`,
 * resuelto en `backend/app/i18n.py`), pero el render del SERVIDOR no puede leer
 * el token de sesión —está en `localStorage`—, así que el idioma ya resuelto se
 * copia a la cookie `finplan_locale`. Esa cookie es el único puente entre una
 * decisión que se toma en la base y un render que ocurre antes de que exista
 * JavaScript.
 *
 * Si la cookie se desincroniza de la base, las páginas del servidor salen en el
 * idioma equivocado y **cuesta darse cuenta**. Por eso se escribe en los dos
 * únicos momentos en que el idioma puede cambiar: al entrar (lo devuelve
 * `/auth/login`) y al apretar el botón ES/EN.
 *
 * Este archivo NO importa nada: lo usan tanto `i18n/request.ts` (servidor) como
 * `lib/api.ts` y los componentes. Meterle un import de `lib/api` armaría un
 * ciclo.
 */
export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";
export const LOCALE_COOKIE = "finplan_locale";

const UN_ANIO = 60 * 60 * 24 * 365;

export function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) return null;
  const base = value.trim().toLowerCase().replace("_", "-").split("-")[0];
  return (LOCALES as readonly string[]).includes(base) ? (base as Locale) : null;
}

export function readLocaleCookie(): Locale | null {
  if (typeof document === "undefined") return null;
  const hit = document.cookie
    .split(";")
    .map(c => c.trim())
    .find(c => c.startsWith(`${LOCALE_COOKIE}=`));
  return normalizeLocale(hit?.slice(LOCALE_COOKIE.length + 1));
}

/** Escribe la cookie. No persiste nada: es el puente hacia el render del servidor. */
export function writeLocaleCookie(locale: string | null | undefined) {
  const l = normalizeLocale(locale);
  if (!l || typeof document === "undefined") return;
  document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=${UN_ANIO}; SameSite=Lax`;
}
