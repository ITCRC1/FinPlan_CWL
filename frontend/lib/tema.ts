/**
 * El tema visual — las piezas compartidas entre el servidor y el cliente.
 *
 * Mismo patrón que `lib/locale.ts`, y por la misma razón: la verdad vive en la
 * base (`users.tema` → `lino`), pero el render del SERVIDOR no puede leer el
 * token de sesión —está en `localStorage`—, así que el tema ya resuelto se
 * copia a la cookie `finplan_tema`. Esa cookie es el único puente entre una
 * decisión guardada en la base y un render que ocurre antes de que exista
 * JavaScript.
 *
 * ⚠️ **Por qué el tema se resuelve en el SERVIDOR y no en el navegador.** Si se
 * aplicara con JavaScript después de montar, cada carga mostraría un parpadeo:
 * la página pinta con el tema por defecto y medio segundo después salta al
 * elegido. Con la cookie leída en `layout.tsx`, el `<html>` ya sale con el tema
 * puesto y no hay salto.
 *
 * Este archivo NO importa nada, igual que `lib/locale.ts`: lo usan el layout
 * (servidor), `lib/api.ts` y los componentes. Un import de `lib/api` armaría un
 * ciclo.
 */
export const TEMAS = ["lino", "papel", "grafito", "hoy"] as const;
export type Tema = (typeof TEMAS)[number];

/** Con cuál abre quien nunca eligió. Owner, 2026-08-19. */
export const TEMA_POR_DEFECTO: Tema = "lino";
export const TEMA_COOKIE = "finplan_tema";

const UN_ANIO = 60 * 60 * 24 * 365;

/**
 * Qué paletas se ofrecen y cuáles son claras.
 *
 * ⚠️ **Acá NO va texto.** El nombre y la descripción de cada una viven en
 * `messages/es.json` y `en.json` (namespace `apariencia`), como todo lo que ve
 * el usuario. Tenerlos acá los dejaría fuera del botón ES/EN — que es
 * exactamente el defecto que se corrigió el 2026-08-19 en 24 archivos.
 */
export const CATALOGO: { id: Tema; claro: boolean }[] = [
  { id: "lino",    claro: true  },
  { id: "papel",   claro: true  },
  { id: "grafito", claro: false },
  { id: "hoy",     claro: false },
];

export function normalizeTema(value: string | null | undefined): Tema | null {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  return (TEMAS as readonly string[]).includes(v) ? (v as Tema) : null;
}

export function readTemaCookie(): Tema | null {
  if (typeof document === "undefined") return null;
  const hit = document.cookie
    .split(";")
    .map(c => c.trim())
    .find(c => c.startsWith(`${TEMA_COOKIE}=`));
  return normalizeTema(hit?.slice(TEMA_COOKIE.length + 1));
}

/**
 * Escribe la cookie. `undefined` la deja como está (no la borra): al entrar, el
 * backend puede no devolver tema todavía y borrarla haría que la próxima carga
 * del servidor saliera con el tema equivocado.
 */
export function writeTemaCookie(value: string | null | undefined): void {
  const t = normalizeTema(value);
  if (!t || typeof document === "undefined") return;
  document.cookie = `${TEMA_COOKIE}=${t}; path=/; max-age=${UN_ANIO}; samesite=lax`;
}
