// Nombres de departamento.
//
// La fuente real es `department_catalog` en la base: se carga con
// `cargarDepartamentos()` al abrir una pantalla y desde ahí manda el catálogo.
// La lista de abajo queda SOLO como respaldo para el primer render y para no
// dejar la pantalla muda si la API falla.
//
// Estaba escrita a mano con 22 departamentos mientras la base tenía 38, y —lo
// peor— el respaldo NO era un respaldo: `cargarDepartamentos()` leía el token de
// una llave que no existe, el endpoint devolvía 401 y el `catch` se lo tragaba,
// así que la app SIEMPRE mostró esta lista. Por eso 0115, 0116, 0130, 0165, 0181
// y 0184 salían en los selectores como «0115 — 0115»: no estaban acá.
//
// Ahora se genera desde el catálogo, con los mismos 38 y los mismos nombres, y
// existe solo para el primer render y para no dejar la pantalla muda si la API
// falla. Si se desactualiza otra vez, se vuelve a copiar de
// `select dept_code, dept_name from department_catalog order by dept_code`.

import { authHeaders, BASE } from "@/lib/api";

export interface CwlDept {
  dept_code: string;
  dept_name: string;
  /** Código del departamento madre, si este cuelga de otro. Viene de
   *  `GET /departments/`. */
  parent_dept_code?: string | null;
  /** ¿Este departamento acepta gasto operativo? Lo DERIVA el backend del mapeo:
   *  no es hijo y tiene al menos una regla de clase 5 o 7. Lo usa `aceptaGasto()`. */
  lleva_gasto?: boolean;
}

/**
 * Padres de los departamentos hijos, SOLO para el respaldo de abajo.
 *
 * El catálogo real trae `parent_dept_code` del backend. Esto existe para que la
 * regla también valga en el primer render y si la API falla — si no, el
 * desplegable de gastos aparecería con los hijos adentro justo cuando algo anda
 * mal, que es cuando menos se mira.
 *
 * Es copia de `CHECKBOOK_DEPT_CONSOLIDATION` en `backend/app/engine/pl_engine.py`.
 */
const PADRE_DE_RESPALDO: Record<string, string> = {
  "0111": "0110", "0112": "0110", "0113": "0110", "0114": "0110",
  "0122": "0120", "0123": "0120",
  "0132": "0130", "0130": "0140",
  "0181": "0180", "0182": "0180", "0183": "0180", "0184": "0180", "0186": "0180",
  "0191": "0190",
};

export const CWL_DEPTS: CwlDept[] = [
  { dept_code: "0110", dept_name: "Rooms / Habitaciones" },
  { dept_code: "0111", dept_name: "Front Desk" },
  { dept_code: "0112", dept_name: "Reservation" },
  { dept_code: "0113", dept_name: "Housekeeping" },
  { dept_code: "0114", dept_name: "Concierge" },
  { dept_code: "0115", dept_name: "Villas" },
  { dept_code: "0116", dept_name: "Residencias" },
  { dept_code: "0120", dept_name: "Alimentos y Bebidas" },
  { dept_code: "0121", dept_name: "Private Bar" },
  { dept_code: "0122", dept_name: "Kitchen" },
  { dept_code: "0123", dept_name: "Restaurant" },
  { dept_code: "0130", dept_name: "Spa" },
  { dept_code: "0132", dept_name: "Spa (planilla)" },
  { dept_code: "0140", dept_name: "Departamento de Spa" },
  { dept_code: "0150", dept_name: "Tour Activities" },
  { dept_code: "0151", dept_name: "Tienda / Gift Shop" },
  { dept_code: "0152", dept_name: "Transportation" },
  { dept_code: "0155", dept_name: "Innoceana" },
  { dept_code: "0156", dept_name: "Crowther Lab" },
  { dept_code: "0161", dept_name: "Laundry Operations" },
  { dept_code: "0162", dept_name: "Laundry Revenue" },
  { dept_code: "0165", dept_name: "Retail" },
  { dept_code: "0180", dept_name: "Administración" },
  { dept_code: "0181", dept_name: "Management" },
  { dept_code: "0182", dept_name: "Finance" },
  { dept_code: "0183", dept_name: "Purchasing" },
  { dept_code: "0184", dept_name: "Administración" },
  { dept_code: "0186", dept_name: "Security" },
  { dept_code: "0190", dept_name: "Sales and Marketing" },
  { dept_code: "0191", dept_name: "Sales & Marketing (remoto)" },
  { dept_code: "0200", dept_name: "Maintenance" },
  { dept_code: "0205", dept_name: "Claro del Bosque (Huerta)" },
  { dept_code: "0210", dept_name: "Utilities" },
  { dept_code: "0220", dept_name: "Employee Dining (Cafetería)" },
  { dept_code: "0230", dept_name: "Information System" },
  { dept_code: "260",  dept_name: "Club Madresal" },
  { dept_code: "270",  dept_name: "Área Recreativa" },
  { dept_code: "280",  dept_name: "Miscelaneos" },
];

/** Catálogo vivo, traído de la base. Arranca con el respaldo de arriba. */
let CATALOGO: CwlDept[] = CWL_DEPTS;

/** Las cinco dimensiones de la matriz de provisionamiento. Una pantalla de
 *  carga pide la suya: el checkbook de planilla no debe esconder un depto que
 *  solo se apagó para OPEX. */
export type Dimension = "REVENUE" | "PAYROLL" | "OPEX" | "COST" | "PROPERTY";

/** Lo que el provisionamiento escondió, por dimensión. Vacío = todo prendido,
 *  que es el default del sistema (se DESMARCA lo que no aplica). */
let APAGADOS: Partial<Record<Dimension, string[]>> = {};

/** Carga el catálogo real y lo que la propiedad tiene escondido.
 *  Si falla, se queda con el respaldo y sin esconder nada — ante la duda se
 *  muestra de más, nunca de menos: una pantalla a la que le faltan
 *  departamentos por un error de red es peor que una con departamentos que
 *  sobran. */
export async function cargarDepartamentos(): Promise<CwlDept[]> {
  try {
    // ⚠️ Este fetch armaba su propio header y leía el token de `localStorage`
    // bajo la llave **"token"**, cuando toda la app lo guarda en
    // **"finplan_token"**. `/departments/` pide autenticación, así que devolvía
    // 401 SIEMPRE — y el `if (!res.ok) return CATALOGO` se lo tragaba sin decir
    // nada. Resultado: el catálogo real (38 departamentos) nunca llegó y la app
    // vivió con la lista de respaldo de 22, así que 0115, 0116, 0130, 0165,
    // 0181 y 0184 salían en los selectores como «0115 — 0115». Y de paso, lo
    // que el provisionamiento escondía tampoco llegaba: la matriz se llenaba y
    // no filtraba nada.
    //
    // Ahora usa `authHeaders()`, el mismo del resto de la app: una sola forma de
    // autenticar, y el día que cambie la llave cambia en un solo lugar.
    const res = await fetch(`${BASE}/departments/`, { headers: authHeaders() });
    if (!res.ok) {
      // Silencio no: un catálogo que no carga se ve como departamentos sin
      // nombre y como un provisionamiento que no hace nada, y ninguna de las
      // dos cosas apunta a la causa.
      console.warn(`[departamentos] ${res.status} al cargar el catálogo; se usa el respaldo`);
      return CATALOGO;
    }
    const data = await res.json() as {
      departments?: CwlDept[];
      apagados?: Partial<Record<Dimension, string[]>>;
    };
    if (data.departments?.length) CATALOGO = data.departments;
    APAGADOS = data.apagados ?? {};
  } catch (e) {
    console.warn("[departamentos] sin red al cargar el catálogo; se usa el respaldo", e);
  }
  return CATALOGO;
}

/** ¿El provisionamiento escondió este departamento en esta dimensión? */
export function estaApagado(code: string, dim: Dimension): boolean {
  return (APAGADOS[dim] ?? []).includes(code);
}

/** Saca de una lista lo que el provisionamiento escondió.
 *
 *  **Esconde aunque tenga datos.** Es lo que la pantalla de provisionamiento
 *  advierte antes de dejar apagar: los datos siguen sumando en el P&L, solo
 *  dejan de verse acá. Filtrar «salvo que tenga datos» dejaría el apagado sin
 *  efecto justo en los departamentos donde alguien se tomó el trabajo de
 *  confirmarlo. */
export function sinApagados(depts: CwlDept[], dim: Dimension): CwlDept[] {
  const off = APAGADOS[dim] ?? [];
  return off.length ? depts.filter(d => !off.includes(d.dept_code)) : depts;
}

/** Dimensiones de GASTO: acá el hijo no tiene nada que hacer. La planilla sí es
 *  suya, y el ingreso y las estadísticas no siguen esta regla. */
const DIMENSIONES_DE_GASTO: Dimension[] = ["OPEX", "COST"];

/**
 * Departamentos que NO aceptan gasto aunque no sean hijos — respaldo, igual que
 * arriba. El backend lo manda en `lleva_gasto`; esto solo cubre el primer render
 * y la caída de la API.
 *
 * `280` Miscelaneos es SOLO ingreso y no tiene costo (owner, 2026-08-13).
 *
 * `0250` Gastos de la Propiedad SÍ es gasto —eso no se discute— pero es clase 8,
 * debajo del GOP, y tiene **checkbook propio fuera de este**: las pantallas de
 * Owner Expenses y Management Fees. Sale de ESTE selector, no del sistema.
 *
 * Lo que los une: ninguno tiene dónde aterrizar un gasto OPERATIVO. Lo que se
 * digitara acá caería por descarte en otro departamento con el GOP cuadrando
 * igual.
 */
const SIN_GASTO_DE_RESPALDO = new Set(["280", "0250"]);

export function esHijo(code: string): boolean {
  const d = CATALOGO.find(x => x.dept_code === code);
  const padre = d?.parent_dept_code ?? PADRE_DE_RESPALDO[code];
  return Boolean(padre);
}

/**
 * Saca los departamentos HIJOS de las dimensiones de gasto.
 *
 * Owner, 2026-08-14: «solo los departamentos padres pueden tener checkbook de
 * gastos, ningún hijo puede tener gastos operativos · los hijos integran a nivel
 * de planilla pero nada más». Es la regla USALI.
 *
 * Se filtra ACÁ y no borrando datos porque el desplegable arma su lista con el
 * catálogo entero, no con los departamentos que tienen filas: vaciar al hijo lo
 * deja igual de visible, ofreciendo veintipico de cuentas para digitar en un
 * lugar donde no van. Y digitarlas ahí no da error — si el padre tiene la cuenta
 * el hijo la hereda, y si no la tiene el gasto cae por descarte en otro
 * departamento con el GOP cuadrando igual.
 */
export function sinHijos(depts: CwlDept[], dim: Dimension): CwlDept[] {
  if (!DIMENSIONES_DE_GASTO.includes(dim)) return depts;
  return depts.filter(aceptaGasto);
}

/** ¿Este departamento puede recibir gasto? Manda lo que dice el backend, que lo
 *  deriva del mapeo; el respaldo solo entra si el campo no vino. */
export function aceptaGasto(d: CwlDept): boolean {
  if (typeof d.lleva_gasto === "boolean") return d.lleva_gasto;
  return !(d.parent_dept_code ?? PADRE_DE_RESPALDO[d.dept_code])
      && !SIN_GASTO_DE_RESPALDO.has(d.dept_code);
}

export function departamentos(): CwlDept[] {
  return CATALOGO;
}

/** Return the dept name for a given code, or the code itself if not found */
export function deptName(code: string): string {
  return CATALOGO.find(d => d.dept_code === code)?.dept_name ?? code;
}

/**
 * Merge a list of DB dept_codes with the full CWL dept list.
 * Depts that have DB data come first, then remaining CWL depts.
 * Returns objects with { dept_code, dept_name }.
 */
export function mergeDepts(dbCodes: string[], dim?: Dimension): CwlDept[] {
  const cat = dim ? sinHijos(sinApagados(CATALOGO, dim), dim) : CATALOGO;
  const dbSet = new Set(dbCodes);
  const withData    = cat.filter(d => dbSet.has(d.dept_code));
  const withoutData = cat.filter(d => !dbSet.has(d.dept_code));
  // Un código que no esté ni en el catálogo se muestra igual, con su número.
  // Un código con datos que ni está en el catálogo se muestra igual, con su
  // número — salvo que sea justo uno de los escondidos: ahí el filtro de arriba
  // lo sacó del catálogo y por esta puerta volvería a entrar.
  // …y salvo que sea un HIJO en una dimensión de gasto: el filtro de arriba lo
  // sacó del catálogo, y si todavía tiene filas viejas volvería a entrar por
  // acá, que es justo el caso que se está tapando.
  const unknownCodes = dbCodes.filter(
    c => !cat.some(d => d.dept_code === c) && !(dim && estaApagado(c, dim))
      && !(dim && DIMENSIONES_DE_GASTO.includes(dim)
           && !aceptaGasto(CATALOGO.find(d => d.dept_code === c) ?? { dept_code: c, dept_name: c })));
  const unknown = unknownCodes.map(c => ({ dept_code: c, dept_name: c }));
  return [...withData, ...unknown, ...withoutData];
}
