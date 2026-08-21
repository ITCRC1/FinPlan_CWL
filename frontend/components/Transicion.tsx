"use client";
/**
 * La entrada de cada pantalla. La otra mitad de «suavizar el movimiento».
 *
 * **El pedido (owner, 2026-08-19).** El menú ya se desliza; lo que seguía
 * cortando era el final del gesto: elegís una opción y la pantalla aparece de
 * golpe, sin relación con el movimiento que la trajo.
 *
 * ⚠️ **Se anima por RUTA, no por render.** La clave es el `pathname`, así que
 * la animación corre solo cuando de verdad cambiaste de pantalla. Es
 * deliberado y no es un detalle: desde hoy el escenario viaja en la dirección
 * (`?esc=`), y cambiarlo con el selector reescribe la URL sin cambiar de
 * pantalla. Si esto se animara con la dirección entera, mover el selector de
 * escenario haría parpadear la tabla completa en cada cambio — un flash cada
 * vez que el usuario compara dos presupuestos.
 *
 * ⚠️ El `key` REMONTA lo de adentro. Acá no cuesta nada —al navegar, la
 * pantalla se reemplaza igual— pero por eso mismo no envuelve al `TopNav`:
 * remontar la barra en cada navegación desharía justamente lo que se acaba de
 * arreglar.
 *
 * Sin JavaScript de por medio: es una animación CSS que arranca al montar, y
 * `prefers-reduced-motion` la apaga.
 */
import { usePathname } from "next/navigation";

export default function Transicion({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return <div key={pathname} className="pag-entra">{children}</div>;
}
