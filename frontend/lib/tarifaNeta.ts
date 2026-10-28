/**
 * La tarifa NETA de una categoría en un mes: la que de verdad usa el motor.
 *
 * El modelo del sistema es `neta = rack × factor del canal`, y cuatro pantallas
 * del front rehacían esa multiplicación por su cuenta para mostrar el ingreso
 * de habitaciones. Mientras toda tarifa salga de un rack, las dos cuentas dan
 * lo mismo — el backend resincroniza la neta cada vez que se guarda un rack.
 *
 * ⚠️ **Una neta puesta a mano no tiene rack del que derivarla.** Las villas se
 * negocian a **$1.700 NETOS** (mig 159, `rate_cards.net_rate_manual`) y su rack
 * está vacío. Con la fórmula valían **$0** en las cuatro pantallas y $1.700 la
 * noche en el motor del P&L: el Revenue Checkbook, el Total Revenue, el reporte
 * a dueños y el Command mostraban ~$360.000 de menos en el Budget 2027 —
 * incluido el botón «Fill from drivers», que escribía esa cifra al checkbook.
 * Sin un solo error en pantalla, y con cada total cuadrando consigo mismo.
 *
 * Por eso la regla vive en UN lugar: la celda manual manda, y lo demás deriva
 * del rack. Una pantalla nueva que muestre ingreso de habitaciones usa esto y
 * no vuelve a multiplicar a mano.
 */
import type { MonthKey, NetRatesResponse } from "./api";

const MESES: MonthKey[] = ["jan", "feb", "mar", "apr", "may", "jun",
                           "jul", "aug", "sep", "oct", "nov", "dec"];

/** `(categoría, índice de mes 0-11) → tarifa neta en USD`. */
export type TarifaNeta = (roomTypeId: string, mesIdx: number) => number;

/**
 * Arma el buscador de tarifas netas.
 *
 * `netRates` puede venir en `null` a propósito: las pantallas lo piden con
 * `.catch(() => null)` para que una caída del endpoint las deje con la fórmula
 * de siempre en vez de dejarlas en blanco.
 */
export function hacerTarifaNeta(
  netRates: NetRatesResponse | null | undefined,
  rackById: Record<string, number[]>,
  netFactor: number[],
): TarifaNeta {
  const guardada: Record<string, { neto: number; manual: boolean }[]> =
    Object.fromEntries((netRates?.rooms ?? []).map(r => [r.room_type_id,
      MESES.map(mk => ({ neto: parseFloat(r.neto[mk]) || 0, manual: !!r.manual[mk] }))]));

  return (roomTypeId, mesIdx) => {
    const celda = guardada[roomTypeId]?.[mesIdx];
    if (celda?.manual) return celda.neto;
    return ((rackById[roomTypeId]?.[mesIdx]) || 0) * (netFactor[mesIdx] || 0);
  };
}
