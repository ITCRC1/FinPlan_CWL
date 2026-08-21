import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { DEFAULT_LOCALE, LOCALE_COOKIE, normalizeLocale, type Locale } from "@/lib/locale";

/**
 * De dónde sale el idioma en el render del SERVIDOR.
 *
 * next-intl asume que el locale vive en la URL (`/es/...`, `/en/...`). Acá NO:
 * vive en la base y viaja por la cookie `finplan_locale`, que el frontend
 * escribe al entrar con el valor ya resuelto que devuelve `/auth/login`.
 *
 * Modo «without i18n routing»: no hay segmento `[locale]`, no se renombró
 * ninguna página y ningún `<Link>` cambió.
 */
export async function localeFromCookie(): Promise<Locale> {
  const jar = await cookies();
  return normalizeLocale(jar.get(LOCALE_COOKIE)?.value) ?? DEFAULT_LOCALE;
}

export default getRequestConfig(async () => {
  const locale = await localeFromCookie();
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
