"use client";
import { useEffect, useState, useCallback, useRef } from "react";

import { useContexto } from "./contexto";

import { limpiarSiEsDeOtraGeneracion } from "./escenarioPreferido";

// Escenario de planeación COMPARTIDO entre todos los tabs de Planning.
// Master Data (u otro tab) elige el escenario y se sincroniza al resto vía
// localStorage + un evento global. Así el escenario seleccionado aplica a
// todos los tabs siguientes (no cada tab por su cuenta).
const KEY = "finplan_planning_scenario";
const EVT = "finplan-planning-scenario";

/** Devuelve el escenario compartido si existe, si no el fallback.
 *
 * ⚠️ Antes de leer, descarta lo guardado si es de una generación anterior de la
 * regla — ver `limpiarSiEsDeOtraGeneracion`. Sin eso, un id equivocado guardado
 * una vez le gana al default **para siempre**: es lo que tenía a todo Planning
 * abriendo en Working 2034-2035. */
export function sharedScenarioOr(fallback: string): string {
  if (typeof window === "undefined") return fallback;
  limpiarSiEsDeOtraGeneracion();
  return localStorage.getItem(KEY) || fallback;
}

/**
 * Hook de estado compartido del escenario de Planning.
 * Reemplaza el `useState` local de scenarioId en cada tab: al cambiarlo en uno,
 * todos los demás tabs montados reaccionan (mismo tab vía evento, otras pestañas
 * vía `storage`).
 */
export function usePlanningScenario(): [string, (id: string) => void] {
  const [id, setIdState] = useState("");

  useEffect(() => {
    const sync = () => {
      limpiarSiEsDeOtraGeneracion();
      setIdState(localStorage.getItem(KEY) || "");
    };
    sync(); // hidratar desde localStorage tras montar (evita mismatch SSR)
    window.addEventListener(EVT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const setId = useCallback((v: string) => {
    if (typeof window !== "undefined") {
      localStorage.setItem(KEY, v);
      window.dispatchEvent(new Event(EVT));
    }
    setIdState(v);
  }, []);

  return [id, setId];
}

/**
 * Igual que `usePlanningScenario`, pero el `?esc=` de la dirección MANDA.
 *
 * Es la versión para las pantallas que se pueden alcanzar de un salto (ver
 * `lib/rutas.ts`): si llegaste desde el P&L de Budget 2027, el checkbook tiene
 * que abrir en Budget 2027 y no en lo que Planning tuviera puesto.
 *
 * ⚠️ **Llegar por un link CAMBIA el escenario de todo Planning.** Es
 * deliberado y es la razón de que Planning comparta uno solo: si el checkbook
 * abriera en 2027 y las otras 27 pantallas siguieran en otro, la próxima que
 * abrieras te mostraría otro año sin decírtelo. Que se mueva todo junto es
 * justamente lo que evita esa clase de error — el mismo que hizo que todos los
 * reportes terminaran en Working 2035.
 */
export function usePlanningScenarioConUrl(): [string, (id: string) => void] {
  const [id, setId] = usePlanningScenario();
  const { esc } = useContexto();
  const aplicado = useRef<string | null>(null);

  useEffect(() => {
    // Una sola vez por id de la URL: si se reaplicara en cada render, el
    // usuario no podría cambiar el escenario con el selector — lo volvería a
    // pisar el parámetro de la dirección con la que llegó.
    if (esc && esc !== id && aplicado.current !== esc) {
      aplicado.current = esc;
      setId(esc);
    }
  }, [esc, id, setId]);

  return [id, setId];
}
