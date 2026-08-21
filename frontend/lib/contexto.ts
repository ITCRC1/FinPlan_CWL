"use client";
/**
 * El contexto de lo que estás mirando, y que viaje con vos.
 *
 * **El pedido (owner, 2026-08-19):** «que dentro de un tab me pueda mover a
 * otro tab internamente sin tener que salir… pero en forma lógica, que se
 * interactúen y pasar de un lugar a otro».
 *
 * **Por qué esto va PRIMERO, antes que cualquier botón.** Medido el 19-ago:
 * de 94 pantallas, **0 leían nada de la URL**. El escenario, el mes y el
 * departamento viven en `localStorage` y —a propósito, ver
 * `escenarioPreferido`— se recuerdan POR PANTALLA. Así que un botón «ver el
 * Cash Flow» puesto sobre eso te llevaría al cash flow de OTRO escenario: el
 * que esa pantalla recuerde por su cuenta.
 *
 * Y no fallaría. Mostraría un presupuesto real, solo que el equivocado —
 * exactamente el modo de falla que ya costó caro cuando todos los reportes se
 * fueron a Working 2035. Un salto que cambia lo que estás viendo sin avisar es
 * peor que no tener el salto.
 *
 * **La regla:** la URL manda; si no dice nada, manda lo recordado. En ese
 * orden, siempre.
 *
 * Efecto secundario que vale por sí solo: las pantallas se vuelven
 * enlazables. Hoy no se le puede pasar a nadie «mirá ESTO» — solo «entrá y
 * buscá». Con esto, el link lleva el escenario y el mes adentro.
 */
import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** Las tres coordenadas que un salto puede necesitar preservar. */
export interface Contexto {
  /** id del escenario */
  esc?: string;
  /** 1-12 */
  mes?: number;
  /** código de departamento: '0110', '600'… */
  dep?: string;
  /**
   * Código de cuenta del mayor: '7065', '4999'…
   *
   * Existe porque sin ella el salto que más se pide queda a medias. Cuatro
   * pantallas muestran la cuenta —P&L Full Detail, OPEX/Costos, Owners Q y
   * Cierre de Mes— y «ver el checkbook de esta cuenta» abría el departamento
   * correcto y dejaba al usuario buscando la fila a mano. Agregarla ahora
   * cuesta una línea; después de cablear 90 pantallas, cuesta noventa.
   */
  cta?: string;
  /** de dónde venís, para el «volver a» */
  de?: string;
}

export const PARAMS = ["esc", "mes", "dep", "cta", "de"] as const;

/** Lee el contexto de la dirección. Vacío si la URL no dice nada. */
export function useContexto(): Contexto {
  const sp = useSearchParams();
  return useMemo(() => {
    const mes = Number(sp.get("mes"));
    return {
      esc: sp.get("esc") || undefined,
      // Un mes fuera de rango se descarta en vez de propagarse: es más barato
      // abrir sin mes que abrir en el mes 0 y que el reporte salga vacío.
      mes: mes >= 1 && mes <= 12 ? mes : undefined,
      dep: sp.get("dep") || undefined,
      cta: sp.get("cta") || undefined,
      de: sp.get("de") || undefined,
    };
  }, [sp]);
}

/**
 * Arma el href de un destino llevándole el contexto.
 *
 * `lleva` dice QUÉ coordenadas tienen sentido en ese destino. No se mandan
 * todas siempre a propósito: un `mes` en una pantalla anual no significa nada,
 * y un parámetro que el destino ignora igual queda en la barra de direcciones,
 * donde después alguien lo copia y lo pega esperando que haga algo.
 */
export function conContexto(
  href: string,
  ctx: Contexto,
  lleva: ReadonlyArray<keyof Contexto> = ["esc", "mes", "dep"],
  desde?: string,
): string {
  const q = new URLSearchParams();
  if (lleva.includes("esc") && ctx.esc) q.set("esc", ctx.esc);
  if (lleva.includes("mes") && ctx.mes) q.set("mes", String(ctx.mes));
  if (lleva.includes("dep") && ctx.dep) q.set("dep", ctx.dep);
  if (lleva.includes("cta") && ctx.cta) q.set("cta", ctx.cta);
  // El «de» es de ida nomás: se pone al saltar, no se arrastra. Si se
  // encadenara, tres saltos dejarían un `de` apuntando al primero y el «volver»
  // mentiría sobre de dónde venís.
  if (desde) q.set("de", desde);
  const s = q.toString();
  return s ? `${href}?${s}` : href;
}

/**
 * Escribe una coordenada en la URL SIN recargar ni ensuciar el historial.
 *
 * `replace` y no `push`: cambiar el mes con el selector no es navegar. Con
 * `push`, el botón «atrás» del navegador retrocedería mes por mes en vez de
 * volver a la pantalla anterior — el usuario espera lo segundo.
 */
export function useFijarContexto() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  return useCallback((cambios: Partial<Contexto>) => {
    const q = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(cambios)) {
      if (v === undefined || v === null || v === "") q.delete(k);
      else q.set(k, String(v));
    }
    const s = q.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  }, [router, pathname, sp]);
}
