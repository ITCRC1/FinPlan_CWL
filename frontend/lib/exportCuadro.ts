import { BASE, getToken } from "@/lib/api";

/**
 * Bajar cualquier cuadro de la app a Excel, con el formato de la casa.
 *
 * La pantalla manda lo que YA tiene renderizado y el servidor devuelve el
 * `.xlsx` armado: banda de título, cabecera, moneda, negativos en rojo entre
 * paréntesis, negrita en totales, sangría por nivel y paneles congelados.
 *
 * **Por qué no se arma en el navegador.** La librería `xlsx` que usa el
 * frontend es la edición Community, que NO escribe estilos de celda — negrita,
 * relleno, bordes y formato de moneda son de la versión paga. Desde acá el
 * techo de calidad ya está tocado; por eso esto va al servidor.
 *
 * **Los valores van como número.** Nunca `"$1,234.00"` ya formateado: un Excel
 * con las cifras en texto no se puede sumar ni graficar, que es justamente para
 * lo que la gente lo baja.
 */

export type FormatoCol = "usd" | "usd2" | "pct" | "num" | "num1" | "texto";

export interface ColumnaCuadro {
  label: string;
  /** Ancho en caracteres. Sin esto, 38 para la primera columna y 14 para el resto. */
  ancho?: number;
  formato?: FormatoCol;
}

export interface FilaCuadro {
  label: string;
  /** Sangría: 0 = raíz, 1 = hijo, 2 = nieto… */
  nivel?: number;
  /** Negrita + fondo. Para subtotales y totales. También sirve de banda de sección. */
  es_total?: boolean;
  /** Pisa el formato de la columna: para cuadros que mezclan unidades por fila. */
  formato?: FormatoCol;
  /**
   * `null` deja la celda vacía — no es lo mismo que un cero.
   *
   * Se admite `string` para lo que es texto de verdad (nombre de cuenta,
   * departamento, línea del P&L). **Nunca** para un número ya formateado:
   * `"$1,234.00"` como cadena rompe justo lo que la gente busca al bajar el
   * archivo. Para esas columnas usá `formato: "texto"`.
   */
  valores: (number | string | null)[];
}

export interface Cuadro {
  titulo: string;
  subtitulo?: string;
  /** Nombre de la hoja. Sin esto se usa el título recortado. */
  hoja?: string;
  columnas: ColumnaCuadro[];
  filas: FilaCuadro[];
  /** Las notas ya escritas, para que el Word las imprima DENTRO del recuadro
   *  de comentarios.
   *
   *  Owner, 2026-09-03: «una vez que se impriman en Word, estas notas
   *  aparezcan en el box editable». Separar lo escrito de donde se escribe
   *  haría que en la reunión se comente dos veces lo mismo. */
  comentarios?: string[];
  /** La franja de estadísticas, como cabecera del cuadro.
   *
   *  Owner, 2026-09-03: «no están saliendo las estadísticas en cada tab».
   *
   *  ⚠️ En la pantalla la franja se dibuja UNA vez arriba de los sub-tabs, así
   *  que se ve en todos. En un documento cada hoja se lee sola —se imprime, se
   *  manda suelta— y sin las estadísticas al lado, los montos no tienen contra
   *  qué leerse: 56.001 de ingreso con 132 noches vendidas dice algo distinto
   *  que con 400. */
  kpis?: { label: string; valores: (string | number | null)[] }[];
  /** Los rótulos de las columnas de `kpis` (una por versión). */
  kpis_columnas?: string[];
}

/**
 * Pide el Excel y dispara la descarga.
 *
 * @param archivo  base del nombre; el servidor le agrega la propiedad
 * @param cuadros  uno por hoja — una pantalla con tabs los manda todos juntos
 */
export async function bajarCuadros(archivo: string, cuadros: Cuadro[]): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/export/cuadros/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ archivo, cuadros }),
  });
  if (!res.ok) {
    // Que un fallo se vea. Una descarga que no pasa nada es peor que un error:
    // el usuario se queda esperando un archivo que nunca va a llegar.
    throw new Error(`No se pudo generar el Excel (${res.status}): ${await res.text()}`);
  }
  const blob = await res.blob();
  const nombre = res.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1]
    ?? `${archivo}.xlsx`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

/** Convierte a número lo que la pantalla tenga a mano; vacío → `null`. */
export function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : parseFloat(String(v).replace(/[^0-9.-]/g, ""));
  return Number.isFinite(n) ? n : null;
}


// ── El reporte de cierre en Word (owner, 2026-09-02) ─────────────────────────
//
// «Un documento Word con todos los tabs activos… dejá espacio entre los tabs
// para poder comentar.»
//
// Mismo contrato que el Excel a propósito: los `cuadros` son los MISMOS objetos
// que ya arma cada pantalla, así que un reporte que se puede bajar a Excel se
// puede meter en el Word sin escribir nada nuevo. Lo que se agrega es lo que
// necesita la portada.
export interface CierreWord {
  archivo: string;
  titulo: string;
  periodo: string;
  versiones: string;
  cuadros: Cuadro[];
  /** Los sub-tabs que la pantalla NO pudo incluir, con el motivo. Se imprimen
   *  en la portada.
   *
   *  ⚠️ Con la lista sólo en un aviso del navegador, el que abre el archivo
   *  después —o el que lo recibe por correo— no tiene forma de saber si falta
   *  algo: un índice de diez cuadros se ve completo aunque falten cuatro. */
  omitidos?: string[];
}

export async function bajarCierreWord(body: CierreWord): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${BASE}/export/cuadros/word/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // Igual que el Excel: que un fallo se VEA. Una descarga que no pasa nada
    // deja al usuario esperando un archivo que nunca va a llegar.
    throw new Error(`No se pudo generar el Word (${res.status}): ${await res.text()}`);
  }
  return res.blob();
}
