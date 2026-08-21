// Cierre de períodos: qué meses vienen del GL y cuáles del checkbook.
//
// Owner, 2026-08-20: «yo subo y cierro el mes para indicar que los actuales
// vienen del GL y el forecast viene de los checkbooks».
import { api } from "@/lib/api";

export type MesCierre = {
  mes: number;
  nombre: string;
  estado: "ACTUAL" | "FORECAST";
  cerrado: boolean;
  fuente: string;
  tiene_dato: boolean;
  /** El aviso de ESTA fila, o vacío. Un mes cerrado sin dato reporta cero. */
  aviso: string;
};

export type Cierre = {
  escenario: {
    id: string; tipo: string; anio: number; version: string;
    etiqueta: string; es_current: boolean; enllavado: boolean;
  };
  corte: number;
  actual_enlazado: { id: string; etiqueta: string } | null;
  meses: MesCierre[];
  avanza_solo: boolean;
  nota: string;
};

export async function getCierre(scenarioId: string): Promise<Cierre> {
  return api.get(`/scenarios/${encodeURIComponent(scenarioId)}/cierre/`);
}

// ⚠️ `confirmar_apertura` es obligatorio para BAJAR el corte: abrir devuelve
// meses al plan y mueve el P&L. El backend rechaza la apertura sin él.
export async function moverCorte(scenarioId: string, corte: number, abre: boolean) {
  return api.patch<{ corte: number; antes: number; abiertos: number;
                     cerrados: number; avisos: string[] }>(
    `/scenarios/${encodeURIComponent(scenarioId)}/cierre/`,
    { corte, confirmar_apertura: abre });
}
