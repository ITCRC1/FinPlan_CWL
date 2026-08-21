"use client";
/** `/pl` redirige al primer sub-tab de Financials.
 *
 * ⚠️ Mismo defecto que el 404 del tab Cost (2026-08-19). El destino es el que
 * la propia barra pone primero —Balance Sheet—, no uno elegido a dedo: si
 * mañana se reordena el menú, el que manda sigue siendo el menú.
 * Lo vigila `test_todo_tab_con_raiz_propia_abre_por_la_url`.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function FinancialsIndex() {
  const router = useRouter();
  useEffect(() => { router.replace("/pl/balance-sheet"); }, [router]);
  return null;
}
