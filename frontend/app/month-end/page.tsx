"use client";
/** `/month-end` redirige a su único sub-tab.
 *
 * ⚠️ Mismo defecto que el 404 del tab Cost (2026-08-19): la barra mostraba el
 * tab y la URL no existía. Acá era más fácil de pasar por alto porque el
 * grupo tiene un solo sub-tab, así que nadie lo abre por la raíz.
 * Lo vigila `test_todo_tab_con_raiz_propia_abre_por_la_url`.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function MonthEndIndex() {
  const router = useRouter();
  useEffect(() => { router.replace("/month-end/pl"); }, [router]);
  return null;
}
