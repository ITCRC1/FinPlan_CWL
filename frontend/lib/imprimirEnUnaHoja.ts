"use client";
import { useEffect, type RefObject } from "react";

/**
 * Escala un contenedor para que el reporte entre en UNA sola hoja al imprimir.
 *
 * **El problema.** `@page { size: letter landscape }` fija el papel, pero no
 * achica nada: si el reporte mide más que la hoja, el navegador lo parte. Y
 * `.print-dashboard` —que ya existía— usa un `zoom: 0.6` clavado, que es dos
 * apuestas a la vez: con poco contenido desperdicia media hoja, y con mucho
 * sigue partiendo. El owner lo pidió explícito el 2026-08-27: «este reporte
 * debe salir en una sola página al imprimir… podemos hacerla horizontal».
 *
 * Acá la escala se MIDE: alto y ancho reales contra los de la hoja.
 *
 * ⚠️ **Se mide en estado de impresión, no en pantalla.** Es la trampa entera de
 * esto: al imprimir desaparecen los botones y los selectores (`.no-print`) y se
 * sueltan los contenedores con scroll (`.fin-sticky`, `.fin-scroll-x`, que en
 * pantalla RECORTAN la tabla con un `max-height`). Midiendo tal cual se ve, el
 * alto sale corto —falta lo que el scroll esconde— y la escala queda grande: el
 * reporte se parte igual, que es justo lo que se venía a arreglar. Por eso la
 * clase `midiendo-impresion`, que aplica esas dos reglas por un instante.
 */

//: Letter horizontal menos los márgenes de `@page` (0.4in por lado), a 96 dpi.
//: Se restan 2px de colchón: un redondeo de medio píxel manda todo a la
//: segunda hoja, y el costo de quedarse corto es invisible.
const ANCHO_HOJA = 11 * 96 - 0.8 * 96 - 2;
const ALTO_HOJA = 8.5 * 96 - 0.8 * 96 - 2;

//: Piso de la escala. Más abajo la letra deja de leerse, y una hoja ilegible no
//: es mejor que dos legibles: si un reporte llega acá, se parte y se ve.
const ESCALA_MINIMA = 0.35;

export function useImprimirEnUnaHoja(ref: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const antes = () => {
      const el = ref.current;
      if (!el) return;
      el.style.zoom = "";                    // medir sin la escala de la vez pasada
      document.body.classList.add("midiendo-impresion");
      const { width, height } = el.getBoundingClientRect();
      document.body.classList.remove("midiendo-impresion");
      if (!width || !height) return;
      const escala = Math.min(1, ANCHO_HOJA / width, ALTO_HOJA / height);
      el.style.zoom = String(Math.max(ESCALA_MINIMA, escala));
    };
    const despues = () => {
      // Se limpia siempre: si la escala quedara puesta, la pantalla se vería
      // encogida después de imprimir y no habría cómo devolverla sin recargar.
      if (ref.current) ref.current.style.zoom = "";
    };

    window.addEventListener("beforeprint", antes);
    window.addEventListener("afterprint", despues);
    return () => {
      window.removeEventListener("beforeprint", antes);
      window.removeEventListener("afterprint", despues);
      despues();
    };
  }, [ref]);
}
