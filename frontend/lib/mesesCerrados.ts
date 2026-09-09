"use client";
/**
 * Qué meses de un escenario ya no se editan, y cómo se ven.
 *
 * Owner, 2026-09-03: *«una vez que se sube un actual, automáticamente ese mes
 * queda bloqueado para cambio; que se ponga gris en señal de que ya no se puede
 * cambiar, y sólo los meses siguientes al cierre quedan abiertos para seguir
 * trabajando en forecast»*.
 *
 * ## El candado ya existía; lo que faltaba era verlo
 *
 * `app/candado_meses.py` bloquea la edición de un mes cerrado en el ORM —o sea
 * para los 109 endpoints de escritura a la vez, y para los que se agreguen—.
 * Probado en producción: junio del `FORECAST Working 2026` (corte 7) responde
 * **409 «Jun ya está cerrado»**.
 *
 * Pero la pantalla no lo mostraba: se escribía encima, se guardaba, y recién
 * ahí saltaba el error. **Un candado que sólo se nota al chocar contra él es
 * peor que no tenerlo**: hace perder el trabajo tipeado y parece un fallo de la
 * app, no una regla.
 *
 * ## Quién cierra meses
 *
 * ⚠️ **Sólo el FORECAST**, y hasta `actuals_through`. No es una simplificación:
 *
 * * un **BUDGET** no tiene actuales —los actuales viven en el forecast— así que
 *   no hay nada que cerrar, y un presupuesto se corrige;
 * * un **ACTUAL** cierra lo que tiene dato, pero corregir un histórico es un
 *   trabajo normal y otra conversación.
 *
 * Eso no se decide acá: se le pregunta al backend
 * (`/scenarios/{id}/meses-cerrados/`), que usa la MISMA función que el candado
 * del ORM. Copiar la regla en el front sería la segunda verdad de siempre: el
 * día que difieran, la pantalla pintaría gris un mes que sí se puede editar, o
 * —peor— dejaría escribir en uno cerrado.
 *
 * ## Una versión enllavada es otra cosa
 *
 * `is_locked` cierra el escenario ENTERO, no un mes. Son dos candados
 * distintos y se muestran distinto: el del escenario ya lo dice su pantalla.
 */
import { useCallback, useEffect, useState } from "react";

import { getMesesCerrados } from "@/lib/api";

/** Los meses cerrados de un escenario, 1..12. Vacío mientras carga o si falla.
 *
 *  ⚠️ Ante un fallo devuelve vacío —todo editable— a propósito: el que impide
 *  de verdad es el backend. Pintar gris de más por un error de red dejaría al
 *  usuario sin poder trabajar en meses que sí puede tocar. */
export function useMesesCerrados(scenarioId: string | undefined | null) {
  const [cerrados, setCerrados] = useState<number[]>([]);

  const cargar = useCallback(async () => {
    if (!scenarioId) { setCerrados([]); return; }
    try {
      const r = await getMesesCerrados(scenarioId);
      setCerrados(r.meses_cerrados ?? []);
    } catch {
      setCerrados([]);
    }
  }, [scenarioId]);

  useEffect(() => { cargar(); }, [cargar]);

  /** `mes` es 1..12. */
  const cerrado = useCallback(
    (mes: number) => cerrados.includes(mes), [cerrados]);

  return { cerrados, cerrado, recargar: cargar };
}

/** Cómo se ve una celda de un mes cerrado.
 *
 *  Gris, sin cursor de texto y con el título que explica por qué. El `title`
 *  importa tanto como el color: un campo gris sin explicación se lee como que
 *  la app está rota. */
export const CELDA_CERRADA: React.CSSProperties = {
  background: "var(--bg-elevated, #EDF1F5)",
  color: "var(--text-disabled)",
  cursor: "not-allowed",
};

export const TITULO_CERRADO =
  "Mes cerrado: ya tiene actuales cargados. Se edita del mes siguiente al corte en adelante.";

/** Cómo se ve el ENCABEZADO de un mes cerrado — para que se entienda de un
 *  vistazo cuál es el corte, sin tener que hacer foco en una celda. */
export const CABECERA_CERRADA: React.CSSProperties = {
  color: "var(--text-disabled)",
  textDecoration: "line-through",
};
