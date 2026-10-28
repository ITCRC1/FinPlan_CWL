"use client";
/**
 * Ver Planning por SET de habitaciones.
 *
 * **El pedido (owner, 2026-10-27):** *«crear otro set de inventario solo para
 * villas pero que no se mezcle con las 30 habitaciones actuales… con su propio
 * ADR, ocupación, revenue y todo»* · *«pero que al final se consoliden como
 * parte de Rooms»*.
 *
 * Lo segundo ya estaba resuelto en la contabilidad: Villas (0115) y
 * Residencias (0116) son HIJOS de Rooms (0110) y consolidan solos en la línea
 * del P&L (ver `rooms_sets_api.py`). Lo que faltaba era lo primero — poder
 * PLANIFICARLAS aparte.
 *
 * ⚠️ **Esto filtra la pantalla, no el cálculo.** El motor sigue computando el
 * hotel entero: la disponibilidad es unidades × días de TODAS las categorías
 * vigentes, y el revenue sale de la suma. Lo único que cambia es qué filas se
 * ven y sobre qué base se saca el total de la vista. Es a propósito: si
 * filtrar cambiara el cálculo, el Budget dependería de qué pantalla estaba
 * abierta cuando se guardó.
 *
 * ⚠️ **Sin `?set=` no filtra nada.** Las pantallas sin el parámetro se
 * comportan igual que siempre — las 30 de hoy siguen viéndose completas,
 * villas incluidas. Es lo que hace seguro agregar esto a pantallas en
 * producción.
 */
import { useMemo } from "react";

import { useContexto } from "./contexto";
import type { RoomType } from "./api";

/** Los sets que hoy existen colgando de Rooms. */
export const SET_VILLAS = "0115";
export const SET_RESIDENCIAS = "0116";

/** El set que pide la dirección, o `""` si no pide ninguno. */
export function useRoomSet(): string {
  const { set } = useContexto();
  return (set ?? "").trim();
}

/**
 * Las categorías del set. Sin set, todas.
 *
 * Compara contra `dept_code`, que es el campo que ya liga cada categoría con
 * su set (`room_type_configs.dept_code`, mig 085). Vacío en una categoría
 * significa «me quedo en Rooms», así que una categoría sin asignar NUNCA cae
 * dentro de un set — se queda en la vista general, que es donde se nota que
 * falta asignarla.
 */
export function tiposDelSet(tipos: RoomType[], set: string): RoomType[] {
  if (!set) return tipos;
  return tipos.filter(t => (t.dept_code || "").trim() === set);
}

/**
 * Filas de escenario (tarifas, ocupación, pax, net rate) filtradas por el set.
 *
 * Las filas no saben a qué set pertenecen: lo sabe la categoría. Por eso se
 * resuelve por `room_type_id` contra la lista de tipos y no por un campo de la
 * fila — si mañana una categoría cambia de set, las filas la siguen sin tener
 * que migrarlas.
 */
export function filasDelSet<T extends { room_type_id: string }>(
  filas: T[], tipos: RoomType[], set: string,
): T[] {
  if (!set) return filas;
  const del = new Set(tiposDelSet(tipos, set).map(t => t.id));
  return filas.filter(f => del.has(f.room_type_id));
}

/** Igual, pero para filas que traen el `code` de la categoría en vez del id. */
export function filasDelSetPorCodigo<T extends { code?: string }>(
  filas: T[], tipos: RoomType[], set: string,
): T[] {
  if (!set) return filas;
  const del = new Set(tiposDelSet(tipos, set).map(t => t.code).filter(Boolean));
  return filas.filter(f => f.code && del.has(f.code));
}

/**
 * Lo que la pantalla necesita saber del set, resuelto una sola vez.
 *
 * `vacio` es el caso que importa: un set elegido cuyas categorías todavía no
 * tienen unidades —o no están asignadas— deja la pantalla en blanco. Sin
 * avisar, eso se lee como «la pantalla no carga»; con el aviso, se lee como lo
 * que es: falta asignar la categoría al set o ponerle unidades.
 */
export function useInfoSet(tipos: RoomType[]) {
  const set = useRoomSet();
  return useMemo(() => {
    const propios = tiposDelSet(tipos, set);
    return {
      set,
      activo: Boolean(set),
      tipos: propios,
      unidades: propios.reduce((s, t) => s + (Number(t.units) || 0), 0),
      vacio: Boolean(set) && propios.length === 0,
    };
  }, [tipos, set]);
}
