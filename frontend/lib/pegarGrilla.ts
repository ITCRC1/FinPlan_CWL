/**
 * Pegar un bloque de Excel en una grilla de la pantalla.
 *
 * Owner, 2026-10-04: *«modifica para que yo pueda hacer un copy paste desde
 * excel, rate y todo queda en la primera celda»*.
 *
 * Sin esto, pegar doce meses deja los doce números metidos dentro de la primera
 * celda —el navegador los trata como un texto largo— y hay que teclearlos de
 * nuevo uno por uno. Es la diferencia entre cargar un presupuesto en un minuto
 * y cargarlo en una hora.
 *
 * Vive en `lib/` y no dentro de una pantalla porque **toda grilla de la app
 * debería pegarse igual**: el CLAUDE.md lo pide en la sección 25.3 y ya hay
 * media docena de tablas que lo resuelven cada una por su lado.
 */

/**
 * El portapapeles de Excel, a filas y columnas.
 *
 * Excel pone el rango como TSV: tabulador entre columnas, salto de línea entre
 * filas. Una sola celda no trae ninguno de los dos — y entonces esto no es un
 * pegado de grilla sino escribir un número, que el navegador ya hace bien.
 *
 * ⚠️ Los `\r` se van primero. Excel en Windows manda `\r\n`, y sin limpiarlos
 * el último valor de cada fila queda con un retorno de carro pegado: `"2,1\r"`
 * no parsea y la columna de diciembre entra en cero.
 */
export function celdasPegadas(texto: string): string[][] | null {
  if (!texto || (!texto.includes("\t") && !texto.includes("\n"))) return null;
  const filas = texto.replace(/\r/g, "").split("\n");
  // La última línea vacía es el salto final del rango, no una fila de datos:
  // dejarla pisaría con ceros la fila siguiente de la grilla.
  while (filas.length && !filas[filas.length - 1].trim()) filas.pop();
  return filas.length ? filas.map(l => l.split("\t")) : null;
}

/**
 * Un número como lo escribe Excel, en cualquiera de sus formas.
 *
 * `2,1` · `2.1` · `$1,234.56` · `₡650.000` · `1.234,56` · `(1,054.50)` · `75%`
 *
 * ⚠️ **La coma puede ser decimal o separador de miles, y hay que mirar para
 * saberlo.** `num()` de la pantalla de rack rates borra todas las comas, así
 * que un `2,1` copiado de un Excel en español entra como **21**. Acá se decide
 * por la posición: si hay punto Y coma, manda el que esté más a la derecha; si
 * hay sólo comas y la última separa uno o dos dígitos, es decimal.
 *
 * ⚠️ El paréntesis es un negativo contable, no un adorno: `(1,054.50)` es
 * −1.054,50. Un Excel de contabilidad los trae así.
 */
export function numeroDeExcel(v: string | number | null | undefined): number {
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  let s = String(v ?? "").trim();
  if (!s) return 0;

  const negativo = s.startsWith("(") && s.endsWith(")");
  if (negativo) s = s.slice(1, -1);
  const porcentaje = s.endsWith("%");
  if (porcentaje) s = s.slice(0, -1);

  s = s.replace(/[$₡€£\s ]/g, "");

  const coma = s.lastIndexOf(",");
  const punto = s.lastIndexOf(".");
  if (coma >= 0 && punto >= 0) {
    // El de más a la derecha es el decimal; el otro, separador de miles.
    s = coma > punto ? s.replace(/\./g, "").replace(",", ".")
                     : s.replace(/,/g, "");
  } else if (coma >= 0) {
    // Sólo comas: decimal si la última separa 1 o 2 dígitos (`2,1` · `1.234,56`),
    // miles si separa 3 (`1,234`). Tres dígitos con coma es miles en todo Excel
    // que este proyecto haya visto.
    s = (s.length - coma - 1) <= 2 ? s.replace(",", ".") : s.replace(/,/g, "");
  }

  const n = parseFloat(s);
  if (!Number.isFinite(n)) return 0;
  return (negativo ? -n : n) / (porcentaje ? 100 : 1);
}

/**
 * Recorre el bloque pegado posicionándolo desde la celda donde se pegó.
 *
 * Llama a `poner(fila, columna, valor)` por cada celda del bloque que caiga
 * dentro de la grilla; lo que se sale por abajo o por la derecha se descarta.
 *
 * ⚠️ Se descarta en silencio **a propósito**: pegar doce meses parado en
 * octubre tiene que llenar octubre, noviembre y diciembre, no fallar. Lo que
 * no entra no existe en la grilla.
 */
export function repartirPegado(
  bloque: string[][], filaInicial: number, colInicial: number,
  filas: number, columnas: number,
  poner: (fila: number, columna: number, valor: string) => void,
): number {
  let puestas = 0;
  bloque.forEach((celdas, df) => {
    const f = filaInicial + df;
    if (f < 0 || f >= filas) return;
    celdas.forEach((valor, dc) => {
      const c = colInicial + dc;
      if (c < 0 || c >= columnas) return;
      poner(f, c, valor);
      puestas += 1;
    });
  });
  return puestas;
}

/**
 * El enganche de una celda: `onPaste={e => manejarPegado(e, b => pegar(f, m, b))}`.
 *
 * Deja pasar el pegado de UNA celda —ésa la escribe el navegador y lo hace
 * bien— e intercepta el de un bloque. Una línea por grilla, para que agregar el
 * pegado a una pantalla nueva no sea una decisión sino un reflejo.
 */
export function manejarPegado(
  e: { clipboardData: { getData: (t: string) => string }; preventDefault: () => void },
  alPegar: (bloque: string[][]) => void,
): void {
  const crudo = celdasPegadas(e.clipboardData.getData("text"));
  if (!crudo) return;
  e.preventDefault();
  // El recorte va ACA y no en cada pantalla: son ocho grillas y todas se pegan
  // desde la misma tabla de Excel, con los mismos nombres de fila y la misma
  // fila de meses adelante. Resolverlo una vez es lo que ya decía el
  // encabezado de este archivo — «toda grilla de la app debería pegarse
  // igual»— y evita que la novena nazca sin el arreglo.
  const bloque = recortarRotulos(crudo);
  if (!bloque.length || !bloque[0].length) return;
  alPegar(bloque);
}

/**
 * El caso simple: una grilla de UNA fila de doce meses, en estado local.
 *
 * Toma la **primera fila** del bloque y la reparte desde la celda donde se
 * pegó. Las demás filas se descartan: en una grilla de una fila no hay a dónde
 * mandarlas, y repartirlas sobre los renglones de al lado —que son otra cosa,
 * otro estado y a veces otra unidad— escribiría donde nadie pidió.
 */
export function pegarEnFila(
  bloque: string[][], desde: number, largo: number,
  poner: (i: number, valor: string) => void,
): number {
  let puestas = 0;
  (bloque[0] ?? []).forEach((valor, dc) => {
    const i = desde + dc;
    if (i < 0 || i >= largo) return;
    poner(i, valor.trim());
    puestas += 1;
  });
  return puestas;
}

/**
 * Un número que YA está en unidades de porcentaje: `52%` es **52**, no 0,52.
 *
 * Owner, 2026-10-04, pegando ocupación: *«lo que yo subo son %, digo 52%, lo
 * que quiero es que tome el 52 y no que diga 520»*.
 *
 * ⚠️ **Dos errores distintos, los dos en la misma celda.**
 *
 * 1. El parser viejo de esa pantalla hacía `replace(/[%, ]/g, "")`, o sea
 *    borraba la coma: un `52,0` copiado de un Excel en español entraba como
 *    **520**. Eso es lo que el owner estaba viendo.
 * 2. Y `numeroDeExcel` lo arregla por el otro lado y se pasa: ve el `%` y
 *    DIVIDE entre cien, así que `52%` entra como **0,52** — correcto para una
 *    celda que guarda la fracción, equivocado para una que guarda el número.
 *
 * Por eso son dos funciones y no una con un `if`: lo que decide no es el texto
 * pegado sino **qué guarda la celda**, y eso sólo lo sabe la pantalla.
 *
 * ⚠️ No convierte fracciones. Un `0,52` entra como 0,52 y no como 52: adivinar
 * que «eso seguro era 52%» es inventar, y la celda de al lado podría tener un
 * 0,52% de verdad.
 */
export function numeroDePorcentaje(v: string | number | null | undefined): number {
  if (typeof v === "number") return Number.isFinite(v) ? v : 0;
  const s = String(v ?? "").trim();
  // El `%` acá es la UNIDAD de la celda, no una instrucción de dividir.
  return numeroDeExcel(s.endsWith("%") ? s.slice(0, -1) : s);
}

/**
 * Quita los rótulos que vienen pegados con el bloque.
 *
 * Owner, 2026-10-22, sobre la grilla de pax: *«que se pueda hacer copy paste
 * fácilmente»*.
 *
 * Pegar ya funcionaba — si uno seleccionaba EXACTAMENTE el rectángulo de
 * números. Pero nadie copia así desde Excel: se arrastra sobre la tabla y se
 * lleva la columna de nombres y la fila de meses. Eso entraba como dato:
 * «Treehouse king bed» no parsea, así que la primera columna se llenaba de
 * ceros y las doce de números quedaban corridas un lugar. El resultado se ve
 * plausible —son pax, todos parecidos— y nada avisa.
 *
 * La regla, a propósito conservadora: se descarta una fila o una columna sólo
 * si **ninguna** de sus celdas es un número y **alguna** tiene texto. Una fila
 * de puros números nunca se pierde, que es el error que no se puede cometer.
 */
export function recortarRotulos(bloque: string[][]): string[][] {
  // ⚠️ NO sirve `Number.isFinite(numeroDeExcel(t))`: `numeroDeExcel` devuelve
  // **0** para lo que no entiende, no `NaN`. Con esa prueba «Enero» pasaba por
  // número, la fila de encabezado nunca se descartaba y el bloque entero
  // entraba corrido una columna. Lo encontró la prueba del caso real.
  //
  // Acá se mira la FORMA: signo, dígitos, separadores y los adornos que trae
  // Excel ($ ₡ € £ % y el paréntesis del negativo contable). Tiene que haber
  // al menos un dígito, así que «—», «n/a» o una celda vacía no son números.
  const esNumero = (s: string) => {
    const t = (s ?? "").trim();
    return t !== "" && /\d/.test(t) && /^[$₡€£(\s]*-?[\d.,\s]+[)%\s]*$/.test(t);
  };
  const soloRotulos = (celdas: string[]) =>
    celdas.length > 0
    && !celdas.some(esNumero)
    && celdas.some(c => (c ?? "").trim() !== "");

  let b = bloque.map(f => [...f]);
  // La fila de encabezado (Enero, Febrero…). Se mira sólo la primera: dos
  // filas de puro texto seguidas ya no son un encabezado sino otra cosa, y
  // adivinar de más es peor que pegar de menos.
  if (b.length > 1 && soloRotulos(b[0])) b = b.slice(1);
  // La columna de nombres. Puede haber más de una —código y descripción— así
  // que se recorta mientras quede al menos una columna viva.
  while (b.length && b[0].length > 1
         && soloRotulos(b.map(f => f[0] ?? ""))) {
    b = b.map(f => f.slice(1));
  }
  return b;
}
