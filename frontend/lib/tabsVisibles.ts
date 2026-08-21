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

export type TabsApagados = { TAB: string[]; ITEM: string[] };

export const NADA_APAGADO: TabsApagados = { TAB: [], ITEM: [] };

// ⚠️ **Quién quiere enterarse de un cambio.** Sin esto, apagar un reporte no se
// ve en la barra hasta recargar la página — y en este proyecto ya se aprendió
// que eso **se lee como «no guardó»**: es exactamente lo que pasó con el nombre
// de la propiedad, y por eso `lib/hotel.ts` tiene este mismo mecanismo.
const suscriptores = new Set<(a: TabsApagados) => void>();

export function alCambiarTabs(fn: (a: TabsApagados) => void): () => void {
  suscriptores.add(fn);
  return () => { suscriptores.delete(fn); };
}

export async function getTabsApagados(hotelId: string): Promise<TabsApagados> {
  const r = await api.get<{ apagados: TabsApagados }>(
    `/provisioning/${encodeURIComponent(hotelId)}/tabs/`);
  return { TAB: r.apagados?.TAB || [], ITEM: r.apagados?.ITEM || [] };
}

export async function saveTabsApagados(
  hotelId: string,
  rows: { scope_kind: "TAB" | "ITEM"; clave: string; visible: boolean }[],
) {
  const r = await api.put<{ apagados: number; prendidos: number; estado: TabsApagados }>(
    `/provisioning/${encodeURIComponent(hotelId)}/tabs/`, { rows });
  const estado = { TAB: r.estado?.TAB || [], ITEM: r.estado?.ITEM || [] };
  // Guarda y avisa. La barra se actualiza sola.
  suscriptores.forEach(fn => fn(estado));
  return { ...r, estado };
}
