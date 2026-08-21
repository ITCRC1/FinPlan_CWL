import { recalculateScenario } from "@/lib/api";

/**
 * Recalcular y decir la verdad de lo que pasó.
 *
 * El servidor devuelve `avisos` cuando algo NO se pudo recalcular — un escenario
 * sin tipo de cambio, una regla de reparto que no encuentra su origen, líneas en
 * colones sin TC del mes. La llamada igual devuelve 200: no es un error, es un
 * recálculo a medias.
 *
 * Siete pantallas ignoraban ese campo y ponían «✓ Recalculado» pase lo que pase.
 * El resultado era el reclamo de siempre: «apreté y no cambió nada». Había
 * cambiado lo que se podía, y lo que no, no avisaba nadie.
 *
 * Devuelve el mensaje ya armado. Empieza con `✓` si salió limpio y con `⚠` si
 * hay avisos, que es la convención que ya usan las pantallas para pintarlo.
 */
export async function recalcularYContar(
  scenarioId: string,
  exito = "✓ Recalculado — el P&L ya refleja estos datos",
): Promise<string> {
  const r = await recalculateScenario(scenarioId);
  const avisos: string[] = r?.avisos ?? [];
  return avisos.length ? `⚠ ${avisos.join(" · ")}` : exito;
}
