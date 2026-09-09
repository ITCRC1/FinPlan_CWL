// Qué tabs y reportes ve ESTA propiedad.
//
// Owner, 2026-08-20: «no todas las propiedades van a ver todos los reportes, ya
// que son muchos para cada propiedad y se van a perder».
//
// ⚠️ **Default PRENDIDO.** Sólo se esconde lo que alguien apagó a mano. Un
// reporte nuevo nace visible: al revés —nacer oculto— se construye algo, nadie
// lo ve, y nadie sabe que existe para poder prenderlo.
//
// ⚠️ **Esconde de la barra; NO es un permiso.** La ruta sigue respondiendo:
// quien escriba la URL entra igual. Es navegación, no seguridad — y es lo que
// hace seguro poder apagarlo todo, incluida la pantalla que lo administra.
import { api } from "@/lib/api";

// `SUBTAB` son las vistas DENTRO de una pantalla —los quince sub-tabs de Cierre
// de Mes—. Es un tercer nivel y no un `ITEM` porque son tres decisiones
// distintas: «esta propiedad no hace Break-Even», «no usa el reporte a la
// Junta» y «en el cierre no quiero que el dueño vea el Flow Through».
export type TabsApagados = { TAB: string[]; ITEM: string[]; SUBTAB: string[] };

export const NADA_APAGADO: TabsApagados = { TAB: [], ITEM: [], SUBTAB: [] };

// ⚠️ **Quién quiere enterarse de un cambio.** Sin esto, apagar un reporte no se
// ve en la barra hasta recargar la página — y en este proyecto ya se aprendió
// que eso **se lee como «no guardó»**: es exactamente lo que pasó con el nombre
// de la propiedad, y por eso `lib/hotel.ts` tiene este mismo mecanismo.
const suscriptores = new Set<(a: TabsApagados) => void>();

export function alCambiarTabs(fn: (a: TabsApagados) => void): () => void {
  suscriptores.add(fn);
  return () => { suscriptores.delete(fn); };
}

// ── El segundo eje: el PERFIL (owner, 2026-08-26) ────────────────────────────
//
// «Vistas limitadas por perfil.» La matriz de arriba dice qué no ve la
// PROPIEDAD; ésta, qué no ve un ROL dentro de ella. Un usuario ve la unión.
//
// ⚠️ **`undefined` y `""` NO son lo mismo, y esa es toda la gracia.**
//
//   * `undefined` — «contestá por MI perfil». Es lo que pide la barra, y por eso
//     la barra no tuvo que aprender nada de roles: el backend ya sabe quién
//     llama.
//   * `""` — «la matriz cruda de la propiedad», sin mezclar. Es lo que pide la
//     pantalla de administración para poder editarla.
//
// Sin esa distinción, un admin que abriera la pantalla estaría editando SU
// vista creyendo que edita la de la propiedad.
export const PERFILES = ["", "admin", "collaborator", "viewer"] as const;
export type Perfil = (typeof PERFILES)[number];

export const ROTULO_PERFIL: Record<string, string> = {
  "": "Toda la propiedad",
  admin: "Admin",
  collaborator: "Editor",
  viewer: "Sólo lectura",
};

export async function getTabsApagados(
  hotelId: string, perfil?: Perfil,
): Promise<TabsApagados> {
  const q = perfil === undefined ? "" : `?perfil=${encodeURIComponent(perfil)}`;
  const r = await api.get<{ apagados: TabsApagados }>(
    `/provisioning/${encodeURIComponent(hotelId)}/tabs/${q}`);
  return { TAB: r.apagados?.TAB || [], ITEM: r.apagados?.ITEM || [],
           SUBTAB: r.apagados?.SUBTAB || [] };
}

export async function saveTabsApagados(
  hotelId: string,
  rows: { scope_kind: "TAB" | "ITEM" | "SUBTAB"; clave: string; visible: boolean }[],
  perfil: Perfil = "",
) {
  const r = await api.put<{ apagados: number; prendidos: number; estado: TabsApagados }>(
    `/provisioning/${encodeURIComponent(hotelId)}/tabs/`, { rows, perfil });
  const estado = { TAB: r.estado?.TAB || [], ITEM: r.estado?.ITEM || [],
                   SUBTAB: r.estado?.SUBTAB || [] };
  // Guarda y avisa. La barra se actualiza sola.
  //
  // ⚠️ Sólo cuando se editó la matriz de la propiedad. Avisar siempre haría que
  // un admin configurando la vista del perfil «sólo lectura» viera SU barra
  // esconderse — un cambio que no le corresponde y que además es mentira: al
  // recargar volvería. Para eso está el aviso de la pantalla.
  if (!perfil) suscriptores.forEach(fn => fn(estado));
  return { ...r, estado };
}
