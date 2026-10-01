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
  /** La primera línea de la cabecera: la versión —«Actual», «Budget»,
   *  «Variance», «Forecast»—. */
  label: string;
  /**
   * La SEGUNDA línea: el período —«Agosto», «YTD Agosto», «Full Year»—.
   *
   * Owner, 2026-09-30, con una captura de cómo la quiere: *«esta vista se ve
   * muy cargada y está en la misma celda… podrás ver que se usan 2 celdas»*.
   * Antes iba todo junto —«Agosto · ACTUAL Final»— envuelto dentro de una
   * celda, partido en dos renglones que por separado no significan nada.
   */
  sub?: string;
  /** Esta columna ABRE un bloque: lleva la raya gruesa a su izquierda, de la
   *  cabecera al pie. Owner: *«se identifica con una línea gruesa lo que es
   *  Agosto, YTD Agosto y Full Year»*. */
  abre_grupo?: boolean;
  /** Ancho en caracteres. Sin esto, 38 para la primera columna y 14 para el resto. */
  ancho?: number;
  formato?: FormatoCol;
  /**
   * Esta columna es la RESTA de otras dos: `[a, b]`, índices base 0 sobre
   * `columnas`. En el Excel la celda sale como `=Ca-Cb`, no como el número.
   *
   * Owner, 2026-09-30, auditando el archivo: *«los subtotales, totales y
   * variaciones deben ser fórmulas reales»*.
   *
   * ⚠️ Un Excel de junta se toca: alguien corrige un actual en una celda y
   * espera que la variación se mueva con él. Con el número puesto no se mueve,
   * y la hoja queda diciendo dos cosas distintas sin que nada avise.
   */
  resta?: [number, number];
  /**
   * Esta columna es la SUMA de otras: índices base 0 sobre `columnas`.
   *
   * Es la columna «Año» de un cuadro de doce meses, o el «Total» de uno por
   * canal. `suma_de` suma FILAS; esto suma COLUMNAS, y son dos cosas
   * distintas: el cuadro de doce meses necesita las dos a la vez —la fila
   * TOTAL suma sus renglones y la columna Año suma sus meses— y la celda de la
   * esquina tiene que seguir cuadrando por los dos lados.
   *
   * ⚠️ Vale la MISMA regla que `suma_de`: se escribe sólo si da lo mismo que
   * el número que ya venía. Si el motor dice otra cosa, manda el motor.
   */
  suma_cols?: number[];
}

export interface FilaCuadro {
  label: string;
  /** Sangría: 0 = raíz, 1 = hijo, 2 = nieto… */
  nivel?: number;
  /** Negrita + fondo. Para subtotales y totales. También sirve de banda de sección. */
  es_total?: boolean;
  /** Encabezado de sección —«REVENUES», «Operating Expenses»—.
   *
   *  ⚠️ NO es un total y no lleva su recuadro negro: es el rótulo del bloque
   *  que empieza. Antes compartía marcador con `es_total`, así que «REVENUES»
   *  salía con el mismo peso visual que «NET PROFIT» y el ojo no encontraba
   *  dónde cierra cada bloque (owner, 2026-09-30). */
  es_seccion?: boolean;
  /** Pisa el formato de la columna: para cuadros que mezclan unidades por fila. */
  formato?: FormatoCol;
  /**
   * Esta fila es la SUMA de otras: los ordinales (base 0) dentro de `filas`.
   *
   * ⚠️ La fórmula se escribe **sólo si da lo mismo que el número**. El total
   * del P&L lo calcula el motor, no la pantalla: si el cuadro no muestra todos
   * sus componentes —o los muestra netos de un reparto— `=SUMA(...)` daría otra
   * cifra y el archivo diría algo que el sistema no dice. Cuando no cuadra se
   * deja el número y se pierde la fórmula, que es el lado correcto en el que
   * equivocarse.
   */
  suma_de?: number[];
  /**
   * Esta fila es una COMBINACIÓN con signo de otras: `[[ordinal, signo], …]`.
   * Excel: `=X45-X53`.
   *
   * ⚠️ **Es lo único que alcanza para la cascada.** GOP es Operating Profit
   * MENOS Overhead; el EBITDA le resta los no operativos; el EBT, lo
   * financiero y la depreciación; el Net Profit, el impuesto. Son las cinco
   * líneas que todo el mundo mira, y con `suma_de` —que sólo suma— quedaban
   * como número pegado mientras el detalle de arriba ya llevaba fórmula.
   *
   * ⚠️ Mismo resguardo que `suma_de`: se escribe sólo si da lo mismo que el
   * número que vino. Si el cuadro no muestra todos los operandos, manda el
   * motor.
   */
  combina_filas?: [number, number][];
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
  /** La descripción de UNA línea para el Índice del libro. El título y el
   *  subtítulo largos pasan a ser la NOTA de esa celda: siguen estando sin
   *  volver el índice una pared de texto. */
  descripcion?: string;
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
