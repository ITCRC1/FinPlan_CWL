/**
 * El perfil de quien está usando la app, del lado del navegador.
 *
 * Owner, 2026-08-26: *«sería por perfil: editor, view, y con vistas limitadas
 * por perfil»*.
 *
 * ⚠️ **Esto NO es la seguridad.** Quien decide es el backend: `app/perfiles.py`
 * cuelga de la misma puerta que el candado del escenario y contesta 403 aunque
 * se escriba la URL a mano. Acá sólo se decide qué se DIBUJA, para que un lector
 * no vea un botón «Guardar» que le va a rebotar.
 *
 * Si algún día las dos capas difieren, la que manda es la del servidor — y la
 * pantalla mostrará el 403 con el mensaje que el backend ya trae en español.
 */
import { getStoredUser } from "@/lib/api";

/** Los perfiles que no escriben. Espejo de `PERFILES_SIN_ESCRITURA` en el
 *  backend; el que manda es aquél. */
const SIN_ESCRITURA = new Set(["viewer"]);

export function perfilActual(): string {
  return getStoredUser()?.role || "";
}

/** ¿Este usuario sólo mira? */
export function esSoloLectura(): boolean {
  return SIN_ESCRITURA.has(perfilActual());
}
