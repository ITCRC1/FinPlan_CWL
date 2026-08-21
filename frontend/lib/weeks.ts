// Calendario semanal del año fiscal (W01..W53).
//
// La W01 arranca el LUNES de la semana que contiene el 1 de enero. La regla se
// dedujo del calendario 2026 que dio el dueño y lo reproduce exacto (W01 =
// 29-Dic-2025, 53 semanas), así que sirve para generar cualquier año.
//
// 2026 y 2027 van escritos: el de 2026 es el del dueño, tal cual, y el de 2027
// se generó con la regla y se dejó fijo para que no dependa de la máquina que
// lo calcule. Cualquier otro año se genera al vuelo — antes esto estaba quemado
// en 2026 y al llegar 2027 los cortes iban a salir con fechas de 2026.
export interface WeekDef { n: number; start: string; end: string; label: string; }

/** Qué parte del mes es FORECAST, contando desde la fecha del corte.
 *
 *  El % de venta en propiedad va SOLO sobre el forecast. «En el history ya está
 *  incluido ese 12,6%, si no lo duplico» (owner, 18-ago-2026): lo que ya pasó
 *  trae adentro los walk-ins que efectivamente ocurrieron — sumarles el
 *  estimado los cuenta dos veces. Antes se aplicaba a los doce meses por igual,
 *  y con el corte al 17-ago inflaba enero a julio, meses ya cerrados.
 *
 *  Devuelve 0 para un mes cerrado, 1 para uno enteramente por delante, y la
 *  fracción de días que quedan para el mes DEL corte. Esa última parte es una
 *  prorrata pareja: el XML sabe día por día cuál es history y cuál forecast
 *  (`rec_type`), pero no se guarda por mes. Afecta a UN mes de los doce.
 *
 *  Vive acá y no en cada pantalla: la usan el Tab 8 de Operations y el panel
 *  de Marketing/Junta, y dos copias de la misma regla se desincronizan.
 */
export function fraccionForecast(mes: number, anio: number, corteISO: string): number {
  if (!corteISO) return 1;
  const [cy, cm, cd] = corteISO.split("-").map(Number);
  if (anio !== cy) return anio > cy ? 1 : 0;
  if (mes !== cm) return mes > cm ? 1 : 0;
  const dias = new Date(anio, mes, 0).getDate();   // días del mes `mes`
  return Math.max(0, Math.min(1, (dias - cd) / dias));
}


export const WEEKS_2026: WeekDef[] = [
  { n: 1,  start: "2025-12-29", end: "2026-01-04", label: "W01 | 29-Dec-2025 to 04-Jan-2026" },
  { n: 2,  start: "2026-01-05", end: "2026-01-11", label: "W02 | 05-Jan-2026 to 11-Jan-2026" },
  { n: 3,  start: "2026-01-12", end: "2026-01-18", label: "W03 | 12-Jan-2026 to 18-Jan-2026" },
  { n: 4,  start: "2026-01-19", end: "2026-01-25", label: "W04 | 19-Jan-2026 to 25-Jan-2026" },
  { n: 5,  start: "2026-01-26", end: "2026-02-01", label: "W05 | 26-Jan-2026 to 01-Feb-2026" },
  { n: 6,  start: "2026-02-02", end: "2026-02-08", label: "W06 | 02-Feb-2026 to 08-Feb-2026" },
  { n: 7,  start: "2026-02-09", end: "2026-02-15", label: "W07 | 09-Feb-2026 to 15-Feb-2026" },
  { n: 8,  start: "2026-02-16", end: "2026-02-22", label: "W08 | 16-Feb-2026 to 22-Feb-2026" },
  { n: 9,  start: "2026-02-23", end: "2026-03-01", label: "W09 | 23-Feb-2026 to 01-Mar-2026" },
  { n: 10, start: "2026-03-02", end: "2026-03-08", label: "W10 | 02-Mar-2026 to 08-Mar-2026" },
  { n: 11, start: "2026-03-09", end: "2026-03-15", label: "W11 | 09-Mar-2026 to 15-Mar-2026" },
  { n: 12, start: "2026-03-16", end: "2026-03-22", label: "W12 | 16-Mar-2026 to 22-Mar-2026" },
  { n: 13, start: "2026-03-23", end: "2026-03-29", label: "W13 | 23-Mar-2026 to 29-Mar-2026" },
  { n: 14, start: "2026-03-30", end: "2026-04-05", label: "W14 | 30-Mar-2026 to 05-Apr-2026" },
  { n: 15, start: "2026-04-06", end: "2026-04-12", label: "W15 | 06-Apr-2026 to 12-Apr-2026" },
  { n: 16, start: "2026-04-13", end: "2026-04-19", label: "W16 | 13-Apr-2026 to 19-Apr-2026" },
  { n: 17, start: "2026-04-20", end: "2026-04-26", label: "W17 | 20-Apr-2026 to 26-Apr-2026" },
  { n: 18, start: "2026-04-27", end: "2026-05-03", label: "W18 | 27-Apr-2026 to 03-May-2026" },
  { n: 19, start: "2026-05-04", end: "2026-05-10", label: "W19 | 04-May-2026 to 10-May-2026" },
  { n: 20, start: "2026-05-11", end: "2026-05-14", label: "W20 | 11-May-2026 to 17-May-2026" },
  { n: 21, start: "2026-05-18", end: "2026-05-24", label: "W21 | 18-May-2026 to 24-May-2026" },
  { n: 22, start: "2026-05-25", end: "2026-05-31", label: "W22 | 25-May-2026 to 31-May-2026" },
  { n: 23, start: "2026-06-01", end: "2026-06-07", label: "W23 | 01-Jun-2026 to 07-Jun-2026" },
  { n: 24, start: "2026-06-08", end: "2026-06-14", label: "W24 | 08-Jun-2026 to 14-Jun-2026" },
  { n: 25, start: "2026-06-15", end: "2026-06-21", label: "W25 | 15-Jun-2026 to 21-Jun-2026" },
  { n: 26, start: "2026-06-22", end: "2026-06-28", label: "W26 | 22-Jun-2026 to 28-Jun-2026" },
  { n: 27, start: "2026-06-29", end: "2026-07-05", label: "W27 | 29-Jun-2026 to 05-Jul-2026" },
  { n: 28, start: "2026-07-06", end: "2026-07-12", label: "W28 | 06-Jul-2026 to 12-Jul-2026" },
  { n: 29, start: "2026-07-13", end: "2026-07-19", label: "W29 | 13-Jul-2026 to 19-Jul-2026" },
  { n: 30, start: "2026-07-20", end: "2026-07-26", label: "W30 | 20-Jul-2026 to 26-Jul-2026" },
  { n: 31, start: "2026-07-27", end: "2026-08-02", label: "W31 | 27-Jul-2026 to 02-Aug-2026" },
  { n: 32, start: "2026-08-03", end: "2026-08-09", label: "W32 | 03-Aug-2026 to 09-Aug-2026" },
  { n: 33, start: "2026-08-10", end: "2026-08-16", label: "W33 | 10-Aug-2026 to 16-Aug-2026" },
  { n: 34, start: "2026-08-17", end: "2026-08-23", label: "W34 | 17-Aug-2026 to 23-Aug-2026" },
  { n: 35, start: "2026-08-24", end: "2026-08-30", label: "W35 | 24-Aug-2026 to 30-Aug-2026" },
  { n: 36, start: "2026-08-31", end: "2026-09-06", label: "W36 | 31-Aug-2026 to 06-Sep-2026" },
  { n: 37, start: "2026-09-07", end: "2026-09-13", label: "W37 | 07-Sep-2026 to 13-Sep-2026" },
  { n: 38, start: "2026-09-14", end: "2026-09-20", label: "W38 | 14-Sep-2026 to 20-Sep-2026" },
  { n: 39, start: "2026-09-21", end: "2026-09-27", label: "W39 | 21-Sep-2026 to 27-Sep-2026" },
  { n: 40, start: "2026-09-28", end: "2026-10-04", label: "W40 | 28-Sep-2026 to 04-Oct-2026" },
  { n: 41, start: "2026-10-05", end: "2026-10-11", label: "W41 | 05-Oct-2026 to 11-Oct-2026" },
  { n: 42, start: "2026-10-12", end: "2026-10-18", label: "W42 | 12-Oct-2026 to 18-Oct-2026" },
  { n: 43, start: "2026-10-19", end: "2026-10-25", label: "W43 | 19-Oct-2026 to 25-Oct-2026" },
  { n: 44, start: "2026-10-26", end: "2026-11-01", label: "W44 | 26-Oct-2026 to 01-Nov-2026" },
  { n: 45, start: "2026-11-02", end: "2026-11-08", label: "W45 | 02-Nov-2026 to 08-Nov-2026" },
  { n: 46, start: "2026-11-09", end: "2026-11-15", label: "W46 | 09-Nov-2026 to 15-Nov-2026" },
  { n: 47, start: "2026-11-16", end: "2026-11-22", label: "W47 | 16-Nov-2026 to 22-Nov-2026" },
  { n: 48, start: "2026-11-23", end: "2026-11-29", label: "W48 | 23-Nov-2026 to 29-Nov-2026" },
  { n: 49, start: "2026-11-30", end: "2026-12-06", label: "W49 | 30-Nov-2026 to 06-Dec-2026" },
  { n: 50, start: "2026-12-07", end: "2026-12-13", label: "W50 | 07-Dec-2026 to 13-Dec-2026" },
  { n: 51, start: "2026-12-14", end: "2026-12-20", label: "W51 | 14-Dec-2026 to 20-Dec-2026" },
  { n: 52, start: "2026-12-21", end: "2026-12-27", label: "W52 | 21-Dec-2026 to 27-Dec-2026" },
  { n: 53, start: "2026-12-28", end: "2027-01-03", label: "W53 | 28-Dec-2026 to 03-Jan-2027" },
];

export const WEEKS_2027: WeekDef[] = [
  { n: 1,  start: "2026-12-28", end: "2027-01-03", label: "W01 | 28-Dec-2026 to 03-Jan-2027" },
  { n: 2,  start: "2027-01-04", end: "2027-01-10", label: "W02 | 04-Jan-2027 to 10-Jan-2027" },
  { n: 3,  start: "2027-01-11", end: "2027-01-17", label: "W03 | 11-Jan-2027 to 17-Jan-2027" },
  { n: 4,  start: "2027-01-18", end: "2027-01-24", label: "W04 | 18-Jan-2027 to 24-Jan-2027" },
  { n: 5,  start: "2027-01-25", end: "2027-01-31", label: "W05 | 25-Jan-2027 to 31-Jan-2027" },
  { n: 6,  start: "2027-02-01", end: "2027-02-07", label: "W06 | 01-Feb-2027 to 07-Feb-2027" },
  { n: 7,  start: "2027-02-08", end: "2027-02-14", label: "W07 | 08-Feb-2027 to 14-Feb-2027" },
  { n: 8,  start: "2027-02-15", end: "2027-02-21", label: "W08 | 15-Feb-2027 to 21-Feb-2027" },
  { n: 9,  start: "2027-02-22", end: "2027-02-28", label: "W09 | 22-Feb-2027 to 28-Feb-2027" },
  { n: 10, start: "2027-03-01", end: "2027-03-07", label: "W10 | 01-Mar-2027 to 07-Mar-2027" },
  { n: 11, start: "2027-03-08", end: "2027-03-14", label: "W11 | 08-Mar-2027 to 14-Mar-2027" },
  { n: 12, start: "2027-03-15", end: "2027-03-21", label: "W12 | 15-Mar-2027 to 21-Mar-2027" },
  { n: 13, start: "2027-03-22", end: "2027-03-28", label: "W13 | 22-Mar-2027 to 28-Mar-2027" },
  { n: 14, start: "2027-03-29", end: "2027-04-04", label: "W14 | 29-Mar-2027 to 04-Apr-2027" },
  { n: 15, start: "2027-04-05", end: "2027-04-11", label: "W15 | 05-Apr-2027 to 11-Apr-2027" },
  { n: 16, start: "2027-04-12", end: "2027-04-18", label: "W16 | 12-Apr-2027 to 18-Apr-2027" },
  { n: 17, start: "2027-04-19", end: "2027-04-25", label: "W17 | 19-Apr-2027 to 25-Apr-2027" },
  { n: 18, start: "2027-04-26", end: "2027-05-02", label: "W18 | 26-Apr-2027 to 02-May-2027" },
  { n: 19, start: "2027-05-03", end: "2027-05-09", label: "W19 | 03-May-2027 to 09-May-2027" },
  { n: 20, start: "2027-05-10", end: "2027-05-16", label: "W20 | 10-May-2027 to 16-May-2027" },
  { n: 21, start: "2027-05-17", end: "2027-05-23", label: "W21 | 17-May-2027 to 23-May-2027" },
  { n: 22, start: "2027-05-24", end: "2027-05-30", label: "W22 | 24-May-2027 to 30-May-2027" },
  { n: 23, start: "2027-05-31", end: "2027-06-06", label: "W23 | 31-May-2027 to 06-Jun-2027" },
  { n: 24, start: "2027-06-07", end: "2027-06-13", label: "W24 | 07-Jun-2027 to 13-Jun-2027" },
  { n: 25, start: "2027-06-14", end: "2027-06-20", label: "W25 | 14-Jun-2027 to 20-Jun-2027" },
  { n: 26, start: "2027-06-21", end: "2027-06-27", label: "W26 | 21-Jun-2027 to 27-Jun-2027" },
  { n: 27, start: "2027-06-28", end: "2027-07-04", label: "W27 | 28-Jun-2027 to 04-Jul-2027" },
  { n: 28, start: "2027-07-05", end: "2027-07-11", label: "W28 | 05-Jul-2027 to 11-Jul-2027" },
  { n: 29, start: "2027-07-12", end: "2027-07-18", label: "W29 | 12-Jul-2027 to 18-Jul-2027" },
  { n: 30, start: "2027-07-19", end: "2027-07-25", label: "W30 | 19-Jul-2027 to 25-Jul-2027" },
  { n: 31, start: "2027-07-26", end: "2027-08-01", label: "W31 | 26-Jul-2027 to 01-Aug-2027" },
  { n: 32, start: "2027-08-02", end: "2027-08-08", label: "W32 | 02-Aug-2027 to 08-Aug-2027" },
  { n: 33, start: "2027-08-09", end: "2027-08-15", label: "W33 | 09-Aug-2027 to 15-Aug-2027" },
  { n: 34, start: "2027-08-16", end: "2027-08-22", label: "W34 | 16-Aug-2027 to 22-Aug-2027" },
  { n: 35, start: "2027-08-23", end: "2027-08-29", label: "W35 | 23-Aug-2027 to 29-Aug-2027" },
  { n: 36, start: "2027-08-30", end: "2027-09-05", label: "W36 | 30-Aug-2027 to 05-Sep-2027" },
  { n: 37, start: "2027-09-06", end: "2027-09-12", label: "W37 | 06-Sep-2027 to 12-Sep-2027" },
  { n: 38, start: "2027-09-13", end: "2027-09-19", label: "W38 | 13-Sep-2027 to 19-Sep-2027" },
  { n: 39, start: "2027-09-20", end: "2027-09-26", label: "W39 | 20-Sep-2027 to 26-Sep-2027" },
  { n: 40, start: "2027-09-27", end: "2027-10-03", label: "W40 | 27-Sep-2027 to 03-Oct-2027" },
  { n: 41, start: "2027-10-04", end: "2027-10-10", label: "W41 | 04-Oct-2027 to 10-Oct-2027" },
  { n: 42, start: "2027-10-11", end: "2027-10-17", label: "W42 | 11-Oct-2027 to 17-Oct-2027" },
  { n: 43, start: "2027-10-18", end: "2027-10-24", label: "W43 | 18-Oct-2027 to 24-Oct-2027" },
  { n: 44, start: "2027-10-25", end: "2027-10-31", label: "W44 | 25-Oct-2027 to 31-Oct-2027" },
  { n: 45, start: "2027-11-01", end: "2027-11-07", label: "W45 | 01-Nov-2027 to 07-Nov-2027" },
  { n: 46, start: "2027-11-08", end: "2027-11-14", label: "W46 | 08-Nov-2027 to 14-Nov-2027" },
  { n: 47, start: "2027-11-15", end: "2027-11-21", label: "W47 | 15-Nov-2027 to 21-Nov-2027" },
  { n: 48, start: "2027-11-22", end: "2027-11-28", label: "W48 | 22-Nov-2027 to 28-Nov-2027" },
  { n: 49, start: "2027-11-29", end: "2027-12-05", label: "W49 | 29-Nov-2027 to 05-Dec-2027" },
  { n: 50, start: "2027-12-06", end: "2027-12-12", label: "W50 | 06-Dec-2027 to 12-Dec-2027" },
  { n: 51, start: "2027-12-13", end: "2027-12-19", label: "W51 | 13-Dec-2027 to 19-Dec-2027" },
  { n: 52, start: "2027-12-20", end: "2027-12-26", label: "W52 | 20-Dec-2027 to 26-Dec-2027" },
  { n: 53, start: "2027-12-27", end: "2028-01-02", label: "W53 | 27-Dec-2027 to 02-Jan-2028" },
];

const POR_ANIO: Record<number, WeekDef[]> = { 2026: WEEKS_2026, 2027: WEEKS_2027 };

const MES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const iso = (d: Date) => d.toISOString().slice(0, 10);
const legible = (d: Date) =>
  `${String(d.getUTCDate()).padStart(2, "0")}-${MES_EN[d.getUTCMonth()]}-${d.getUTCFullYear()}`;

/** Semanas del año fiscal. Devuelve la tabla escrita si existe; si no, la genera. */
export function semanasDe(anio: number): WeekDef[] {
  const fijo = POR_ANIO[anio];
  if (fijo) return fijo;
  const ene1 = new Date(Date.UTC(anio, 0, 1));
  // getUTCDay(): 0 = domingo. Se lleva al lunes anterior.
  const lunes = new Date(ene1);
  lunes.setUTCDate(ene1.getUTCDate() - ((ene1.getUTCDay() + 6) % 7));
  const finAnio = Date.UTC(anio, 11, 31);
  const out: WeekDef[] = [];
  for (let n = 1; n <= 53; n++) {
    const fin = new Date(lunes);
    fin.setUTCDate(lunes.getUTCDate() + 6);
    out.push({
      n, start: iso(lunes), end: iso(fin),
      label: `W${String(n).padStart(2, "0")} | ${legible(lunes)} to ${legible(fin)}`,
    });
    if (lunes.getTime() <= finAnio && finAnio <= fin.getTime()) break;
    lunes.setUTCDate(lunes.getUTCDate() + 7);
  }
  return out;
}
