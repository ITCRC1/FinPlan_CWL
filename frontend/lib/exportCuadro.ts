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
