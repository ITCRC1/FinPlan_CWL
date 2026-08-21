import { readLocaleCookie, writeLocaleCookie } from "@/lib/locale";
import { writeTemaCookie, type Tema } from "@/lib/tema";
import { HOTEL_ID } from "./hotel";

export const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

const TOKEN_KEY = "finplan_token";
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (typeof window === "undefined") return;
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}
/**
 * El idioma, para que los errores del backend vuelvan en el idioma correcto.
 *
 * Va por header y NO por la cookie: el backend vive en otro dominio
 * (`backend-production-*.up.railway.app`) que el frontend, así que la cookie
 * `finplan_locale` nunca llega hasta allá. Ver `backend/app/errores.py`.
 */
function localeHeader(): Record<string, string> {
  const l = readLocaleCookie();
  return l ? { "Accept-Language": l } : {};
}
// Header de auth para fetch crudos (uploads multipart).
export function authHeaders(): Record<string, string> {
  const t = getToken();
  return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...localeHeader() };
}
/**
 * URL de descarga (`<a href>`). El token y el IDIOMA van por query.
 *
 * ⚠️ **Un `href` no manda cabeceras.** Por eso el token viaja acá — y desde que
 * el backend arma los Excel en el idioma del usuario (2026-08-19), el idioma
 * tiene el mismo problema: sin esto el archivo sale en el idioma del NAVEGADOR
 * y no en el del selector de la app, y nadie entiende por qué.
 */
export function dlUrl(path: string): string {
  const t = getToken();
  const q = new URLSearchParams();
  if (t) q.set("token", t);
  const l = readLocaleCookie();
  if (l) q.set("lang", l);
  const s = q.toString();
  return `${BASE}${path}${s ? `?${s}` : ""}`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...localeHeader(),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      setToken(null);
      localStorage.removeItem("finplan_user");
      window.location.href = "/login";
    }
    const text = await res.text();
    // La CLAVE del error viaja aparte del texto: quien necesite DECIDIR segun
    // que error fue no puede mirar la prosa, que cambia de idioma. Ver
    // `backend/app/errores.py`.
    let clave: string | undefined;
    try { clave = JSON.parse(text)?.clave; } catch { /* no era JSON */ }
    throw Object.assign(new Error(`API ${res.status}: ${text}`), { clave });
  }
  return res.json() as Promise<T>;
}

export const api = {
  get:    <T>(path: string)                => apiFetch<T>(path),
  post:   <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "POST",  body: JSON.stringify(body) }),
  put:    <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "PUT",   body: JSON.stringify(body) }),
  patch:  <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string)                => apiFetch<T>(path, { method: "DELETE" }),
};

// ── Colaboración (Fase 3): asignación + estados + bloqueo ─────────────────────

export interface SectionRow {
  section: string;
  label: string;
  status: string;            // pending | in_progress | in_review | approved
  locked: boolean;
  assignee: { id: string; name: string; email: string } | null;
}

export interface AssignmentRow {
  section: string; ref: string; label: string; status: string; locked: boolean;
  assignee: { id: string; name: string; email: string } | null;
}

export async function getAssignments(scenarioId: string): Promise<{ scenario_id: string; sections: SectionRow[]; assignments: AssignmentRow[] }> {
  return api.get(`/scenarios/${scenarioId}/assignments/`);
}
export interface Validation { section: string; level: string; message: string; }
export async function getValidations(scenarioId: string): Promise<{ validations: Validation[]; errors: number; warnings: number }> {
  return api.get(`/scenarios/${scenarioId}/validations/`);
}
const refQs = (ref?: string) => (ref ? `?ref=${encodeURIComponent(ref)}` : "");
export async function setAssignee(scenarioId: string, section: string, assigneeId: string | null, ref = "") {
  return api.put(`/scenarios/${scenarioId}/assignments/${section}/assignee/${refQs(ref)}`, { assignee_id: assigneeId });
}
export async function setSectionStatus(scenarioId: string, section: string, status: string, ref = "") {
  return api.patch(`/scenarios/${scenarioId}/assignments/${section}/status/${refQs(ref)}`, { status });
}
export async function setSectionLock(scenarioId: string, section: string, locked: boolean, ref = "") {
  return api.patch(`/scenarios/${scenarioId}/assignments/${section}/lock/${refQs(ref)}`, { locked });
}

// ── Totales de gasto por tipo (command center) ────────────────────────────────

export async function getExpenseTotals(
  scenarioId: string,
): Promise<{ scenario_id: string; payroll: number; cos: number; opex: number }> {
  return api.get(`/scenarios/${scenarioId}/expense-totals/`);
}

// ── Anotaciones: comentarios (narrativa) + Q&A ───────────────────────────────

export interface Annotation {
  id: string; section: string; label: string; ref: string; month: number;
  kind: string; body: string; resolved: boolean; author: string | null; created_at: string | null;
}

export async function getAnnotations(
  scenarioId: string, opts?: { kind?: string; section?: string },
): Promise<{ annotations: Annotation[] }> {
  const p = new URLSearchParams();
  if (opts?.kind) p.set("kind", opts.kind);
  if (opts?.section) p.set("section", opts.section);
  const qs = p.toString() ? `?${p.toString()}` : "";
  return api.get(`/scenarios/${scenarioId}/annotations/${qs}`);
}
export async function addAnnotation(
  scenarioId: string,
  body: { section: string; ref: string; month: number; kind: string; body: string },
): Promise<Annotation> {
  return api.post(`/scenarios/${scenarioId}/annotations/`, body);
}
export async function resolveAnnotation(id: string, resolved: boolean) {
  return api.patch(`/annotations/${id}/resolve/`, { resolved });
}
export async function deleteAnnotation(id: string) {
  return api.delete(`/annotations/${id}/`);
}

// ── Auth (Fase 0) ─────────────────────────────────────────────────────────────

export interface AuthUser {
  id: string; email: string; name: string; role: string; active: boolean;
  /** Preferencia propia. `null` = «usá el idioma del hotel». */
  locale?: string | null;
  /** Paleta propia. `null` = «usá la que viene por defecto». */
  tema?: string | null;
}
/** Lo que devuelve /auth/login y /auth/bootstrap: sesión + idioma YA RESUELTO. */
interface SessionResponse { token: string; user: AuthUser; locale?: string; tema?: string }
const USER_KEY = "finplan_user";

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const s = localStorage.getItem(USER_KEY);
  return s ? JSON.parse(s) as AuthUser : null;
}
function persistSession(token: string, user: AuthUser, locale?: string, tema?: string) {
  setToken(token);
  if (typeof window !== "undefined") localStorage.setItem(USER_KEY, JSON.stringify(user));
  // El idioma resuelto pasa a la cookie: el token vive en localStorage y el
  // render del servidor no lo puede leer. Sin esto, las páginas que renderiza
  // el servidor salen siempre en el default. Ver lib/locale.ts.
  writeLocaleCookie(locale);
  // Lo mismo con el tema, y por lo mismo: el `<html data-tema>` lo pone el
  // servidor en `app/layout.tsx`, antes de que exista JavaScript.
  writeTemaCookie(tema);
}
/**
 * Guarda la paleta elegida y sincroniza la cookie.
 *
 * Si el backend falla, el tema igual cambia en esta sesión: nadie se queda
 * mirando un botón que no hace nada porque se cayó la red. Lo que se pierde es
 * que quede guardado, no el cambio. Mismo criterio que el botón ES/EN.
 */
export async function guardarTema(tema: Tema): Promise<void> {
  writeTemaCookie(tema);
  try {
    await api.patch<unknown>("/auth/me/tema", { tema });
  } catch {
    /* sin sesión o backend caído: la cookie ya cambió */
  }
}

export function logout() {
  setToken(null);
  if (typeof window !== "undefined") localStorage.removeItem(USER_KEY);
}

export async function authStatus(): Promise<{ has_users: boolean }> {
  return api.get<{ has_users: boolean }>(`/auth/status`);
}
export async function login(email: string, password: string): Promise<AuthUser> {
  const r = await api.post<SessionResponse>(`/auth/login`, { email, password });
  persistSession(r.token, r.user, r.locale, r.tema);
  return r.user;
}
export async function bootstrapAdmin(email: string, password: string, name: string): Promise<AuthUser> {
  const r = await api.post<SessionResponse>(`/auth/bootstrap`, { email, password, name });
  persistSession(r.token, r.user, r.locale, r.tema);
  return r.user;
}

// ── Idioma de la propiedad (Master Data → Provisionamiento) ───────────────────
export interface HotelLocale { hotel_id: string; default_locale: string; opciones?: string[] }
export async function getHotelLocale(hotelId: string): Promise<HotelLocale> {
  return api.get<HotelLocale>(`/provisioning/${hotelId}/locale/`);
}
export async function setHotelLocale(hotelId: string, locale: string): Promise<HotelLocale> {
  return api.patch<HotelLocale>(`/provisioning/${hotelId}/locale/`, { locale });
}

/** Nombre visible de la propiedad. El `id` no se edita: es la llave del dato. */
export interface HotelIdentidad { id: string; name: string; short_name: string }
/** Renombra el CÓDIGO y arrastra el dato de las 26 tablas que lo llevan. */
export interface RenombreHotel {
  id: string; anterior: string; filas: number; migradas: Record<string, number>;
}
export async function setHotelCodigo(
  hotelId: string, codigo: string,
): Promise<RenombreHotel> {
  return api.patch<RenombreHotel>(`/provisioning/${hotelId}/codigo/`, { codigo });
}
export async function setHotelIdentidad(
  hotelId: string, name: string, short_name: string,
): Promise<HotelIdentidad> {
  return api.patch<HotelIdentidad>(
    `/provisioning/${hotelId}/identidad/`, { name, short_name });
}
export async function listUsers(): Promise<AuthUser[]> {
  return api.get<AuthUser[]>(`/auth/users`);
}
export async function createUser(
  email: string, password: string, name: string, role: string,
): Promise<AuthUser> {
  return api.post<AuthUser>(`/auth/users`, { email, password, name, role });
}
export async function updateUser(
  userId: string,
  patch: { name?: string; role?: string; active?: boolean; password?: string },
): Promise<AuthUser> {
  return api.patch<AuthUser>(`/auth/users/${userId}`, patch);
}

// ── Scenario helpers ──────────────────────────────────────────────────────────

export interface Scenario {
  id: string;
  hotel_id: string;
  year: number;
  type: string;   // "ACTUAL" | "BUDGET" | "FORECAST"
  version: string;
  status: string;
  is_locked: boolean;
  actuals_through: number;  // 0=none, 1-12=month through which actuals override forecast
  is_current_forecast?: boolean;  // el Forecast "Current" (target de uploads + auto-cut)
  source_mode?: string;    // "imported" | "checkbook"
  revenue_source?: string; // "drivers" | "checkbook"
  created_by?: string;
  created_at?: string;
}

// ── Scenario data operations (planning) ───────────────────────────────────────

export async function setSourceMode(scenarioId: string, mode: "imported" | "checkbook") {
  return api.patch<{ id: string; source_mode: string }>(
    `/scenarios/${scenarioId}/source-mode/`, { source_mode: mode });
}

export async function recalculateScenario(scenarioId: string) {
  return api.post<{
    scenario_id: string; pl_lines: number; status: string;
    // Lo que NO se pudo recalcular (p.ej. escenario sin tipo de cambio).
    avisos?: string[];
  }>(`/pl/${scenarioId}/recalculate/`);
}

export async function getScenarios(hotelId: string): Promise<Scenario[]> {
  // Backend serves all scenarios at /scenarios/; filter to this hotel.
  const all = await api.get<Scenario[]>(`/scenarios/`);
  return all.filter(s => s.hotel_id === hotelId);
}

export async function getBudgetScenario(hotelId: string, year = 2026): Promise<Scenario | null> {
  const all = await getScenarios(hotelId);
  return all.find(s => s.type === "BUDGET" && s.year === year) ?? null;
}

export async function createScenario(payload: {
  hotel_id?: string;
  year: number;
  type: string;
  version: string;
  tc_default?: number;
  created_by?: string;
}): Promise<Scenario> {
  return api.post<Scenario>(`/scenarios/`, payload);
}

export async function setActualsThrough(
  scenarioId: string,
  month: number,
): Promise<{ id: string; actuals_through: number }> {
  return apiFetch<{ id: string; actuals_through: number }>(
    `/scenarios/${scenarioId}/actuals-through/`,
    { method: "PATCH", body: JSON.stringify({ actuals_through: month }) },
  );
}

export async function markCurrentForecast(
  scenarioId: string,
): Promise<{ id: string; is_current_forecast: boolean }> {
  return apiFetch<{ id: string; is_current_forecast: boolean }>(
    `/scenarios/${scenarioId}/mark-current/`,
    { method: "PATCH" },
  );
}

export async function snapshotForecastMonth(
  sourceId: string,
  month: number,
): Promise<Scenario & { label: string }> {
  return apiFetch<Scenario & { label: string }>(
    `/scenarios/${sourceId}/snapshot-month/?month=${month}`,
    { method: "POST" },
  );
}

/**
 * Qué meses de un escenario ya están cerrados, y si hay foto que los cubra.
 *
 * Es lo que separa los dos caminos de carga: una carga histórica sobre un
 * escenario que YA tiene meses tiene que avisar fuerte ANTES de escribir, no
 * después.
 */
export interface MesesCerrados {
  scenario_id: string;
  escenario: string;
  type: string;
  meses_cerrados: number[];
  tiene_datos: boolean;
  actuals_through: number;
  ultima_foto: { id: string; version: string; mes: number; etiqueta: string } | null;
  meses_cerrados_sin_foto: number[];
}

export async function getMesesCerrados(scenarioId: string): Promise<MesesCerrados> {
  return apiFetch<MesesCerrados>(`/scenarios/${scenarioId}/meses-cerrados/`);
}

/**
 * ¿Se movió algún mes CERRADO desde la última foto? Qué mes, qué línea, cuánto.
 *
 * No impide nada: muestra. Es el aviso barato que reemplaza al candado por
 * grilla —ese cubría lo chico y dejaba abierto el recálculo, que es el agujero
 * grande—. Sin foto previa no hay línea base, y lo dice con esas palabras en vez
 * de inventar una comparación que siempre daría cero.
 */
export interface Divergencia {
  scenario_id: string;
  escenario: string;
  meses_cerrados: number[];
  tolerancia: number;
  hay_foto: boolean;
  foto: { id: string; version: string; mes: number; etiqueta: string; created_at: string | null } | null;
  meses_cerrados_sin_foto: number[];
  diferencias: { mes: number; line_code: string; line_name: string; foto: number; ahora: number; delta: number }[];
  meses_movidos: number[];
  /** Los meses cerrados que la foto SI alcanzo a cubrir: los unicos comparables. */
  meses_comparables: number[];
  veredicto: "sin_meses_cerrados" | "sin_foto" | "foto_anterior_al_cierre" | "sin_cambios" | "cambio_en_mes_cerrado";
  /** El espanol de siempre — RESPALDO. Si hay `mensaje_key`, se prefiere esa. */
  mensaje: string;
  /** Clave dentro de `mesesCerrados`. El motor no puede enterarse del idioma, asi
   *  que nombra el aviso y la pantalla lo redacta. */
  mensaje_key?: "sin_meses_cerrados" | "sin_foto" | "foto_anterior_al_cierre" | "sin_cambios" | "cambio_en_mes_cerrado";
  /** Los numeros y las listas, SUELTOS: `lineas`/`meses` son conteos (el plural se
   *  resuelve con ICU en la pantalla) y `lista` son meses 1..12, que la pantalla
   *  nombra con su propio catalogo. */
  mensaje_params?: { foto?: string; lineas?: number; meses?: number; lista?: number[] };
}

export async function getDivergencia(scenarioId: string): Promise<Divergencia> {
  return apiFetch<Divergencia>(`/scenarios/${scenarioId}/divergencia/`);
}

export async function budgetToForecastCurrent(
  budgetId: string,
): Promise<Scenario & { label: string }> {
  return apiFetch<Scenario & { label: string }>(
    `/scenarios/${budgetId}/to-forecast-current/`,
    { method: "POST" },
  );
}

/**
 * Qué tiene adentro cada escenario, para elegir origen con criterio.
 *
 * Existe porque el aviso llegaba tarde: se elegía origen, se creaba el
 * escenario, se copiaba, y recién ahí salía un «copiadas 0 filas» fácil de
 * pasar por alto — con la copia ya creada y vacía.
 */
export interface InventarioCopia {
  id: string;
  etiqueta: string;
  year: number;
  type: string;
  version: string;
  source_mode: string;
  /** Filas totales, andamiaje incluido. Informativo. */
  filas: number;
  /** Filas que son datos de verdad. Es lo que decide `vacio`. */
  filas_utiles: number;
  /**
   * No sirve como origen de una copia. OJO: no es `filas === 0` — un escenario
   * recién creado ya trae 50 filas de andamiaje (mix de canales, config de
   * Villas, los 12 TC) y el P&L en cero.
   */
  vacio: boolean;
  tiene_mayor: boolean;
  por_dataset: Record<string, number>;
}

export async function getCopyInventory(
  hotelId = HOTEL_ID,
): Promise<{ hotel_id: string; escenarios: InventarioCopia[] }> {
  return apiFetch(`/scenarios/copia/inventario/?hotel_id=${encodeURIComponent(hotelId)}`);
}

/**
 * Copia un escenario entero a otro.
 *
 * NO lleva lista de datasets: la decide el backend, y es la MISMA que clona la
 * foto mensual. Cuando esta función mandaba sus propios 7 datasets, el mayor y
 * el snapshot del P&L se quedaban afuera mientras `source_mode` sí viajaba — y
 * la copia de un origen `imported` daba otros números sin ningún error.
 */
export async function copyScenarioFrom(
  targetId: string,
  sourceId: string,
  // El backend frena si el origen no tiene una sola fila. Se manda `true` solo
  // cuando la pantalla ya se lo preguntó al usuario y dijo que siga igual.
  permitirOrigenVacio = false,
): Promise<{
  target: string; source: string; copied: Record<string, number>;
  source_mode: string; actuals_through: number; avisos: string[];
}> {
  return api.post(`/scenarios/${targetId}/copy-from/${sourceId}/`,
    { replace: true, permitir_origen_vacio: permitirOrigenVacio });
}

export async function setScenarioStatus(
  scenarioId: string,
  status: "draft" | "approved" | "locked",
): Promise<{ id: string; status: string }> {
  return apiFetch<{ id: string; status: string }>(
    `/scenarios/${scenarioId}/status/`,
    { method: "PATCH", body: JSON.stringify({ status }) },
  );
}

// ── Inventario de habitaciones (Units Category) ───────────────────────────────

export interface RoomType {
  id: string;
  code: string;
  sort_order: number;
  name: string;
  short_name: string;
  units: number;
  pax_min: number;
  pax_max: number;
  dept_code: string;
  active: boolean;
}

/** Los SET de categorías: Rooms, Villas, Residencias. Es donde se mide el costo. */
export interface RoomDepartment { dept_code: string; dept_name: string; es_padre: boolean; }
export async function getRoomDepartments(hotelId: string): Promise<RoomDepartment[]> {
  return api.get<RoomDepartment[]>(`/hotels/${hotelId}/room-departments/`);
}

export interface RoomTypesResponse {
  hotel_id: string;
  room_types: RoomType[];
  total_units: number;
  closed_months: number[];   // 1-based months the hotel does not operate
  pax_per_night: string;     // factor de pax por noche ocupada
}

export async function getRoomTypes(hotelId: string, scenarioId?: string): Promise<RoomTypesResponse> {
  const qs = scenarioId ? `?scenario_id=${scenarioId}` : "";
  return api.get<RoomTypesResponse>(`/hotels/${hotelId}/room-types/${qs}`);
}

// ── Master data por escenario (units / meses cerrados / pax por año) ───────────

export interface ScenarioMasterResponse {
  scenario_id: string;
  seeded: boolean;
  room_types: RoomType[];     // incluye units (override del escenario o default)
  closed_months: number[];
  pax_per_night: string;
}

export async function getScenarioMaster(scenarioId: string): Promise<ScenarioMasterResponse> {
  return api.get<ScenarioMasterResponse>(`/scenarios/${scenarioId}/master/`);
}

export async function saveScenarioMaster(
  scenarioId: string,
  body: { closed_months: number[]; pax_per_night: number; units: Record<string, number> },
): Promise<{ saved: boolean }> {
  return api.put(`/scenarios/${scenarioId}/master/`, body);
}

export async function setPaxPerNight(
  hotelId: string,
  paxPerNight: number,
): Promise<{ hotel_id: string; pax_per_night: string }> {
  return api.put(`/hotels/${hotelId}/pax-per-night/`, { pax_per_night: paxPerNight });
}

export async function setClosedMonths(
  hotelId: string,
  closedMonths: number[],
): Promise<{ hotel_id: string; closed_months: number[] }> {
  return api.put(`/hotels/${hotelId}/closed-months/`, { closed_months: closedMonths });
}

export async function createRoomType(
  hotelId: string,
  body: { name: string; code?: string; short_name?: string; units?: number; pax_min?: number; pax_max?: number },
): Promise<RoomType> {
  return api.post<RoomType>(`/hotels/${hotelId}/room-types/`, body);
}

export async function updateRoomType(
  hotelId: string,
  roomTypeId: string,
  patch: Partial<Pick<RoomType, "name" | "code" | "short_name" | "units" | "pax_min" | "pax_max" | "sort_order" | "dept_code" | "active">>,
): Promise<RoomType> {
  return api.put<RoomType>(`/hotels/${hotelId}/room-types/${roomTypeId}/`, patch);
}

export async function deleteRoomType(hotelId: string, roomTypeId: string): Promise<{ deleted: boolean }> {
  return api.delete(`/hotels/${hotelId}/room-types/${roomTypeId}/`);
}

// ── Revenue helpers ───────────────────────────────────────────────────────────

export interface MonthlyRevenue {
  month: number;
  year: number;
  rooms: string;
  food: string;
  beverage: string;
  activities: string;
  transport: string;
  sustainability: string;
  spa: string;
  retail: string;
  fnb_misc: string;
  innoceana: string;
  laundry: string;
  total_package: string;
  total_revenue: string;
  rooms_available: number;
  rooms_occupied: string;
  guests: string;
  net_factor: string;
  occupancy_pct: string;
  adr: string;
  revpar: string;
}

// ── Canales de Venta (mix % + comisión % → net factor) ────────────────────────

export interface ChannelRow {
  channel: string;
  label: string;
  mix: string[];    // 12 valores (fracción) Ene..Dic
  comm: string[];   // 12 valores (fracción) Ene..Dic
}

export interface ChannelsConfig {
  scenario_id: string;
  seeded: boolean;            // true = aún no guardado (defaults sugeridos)
  channels: ChannelRow[];
  net_factor: string[];       // 12 valores
}

export async function getChannelsConfig(scenarioId: string): Promise<ChannelsConfig> {
  return api.get<ChannelsConfig>(`/scenarios/${scenarioId}/revenue/channels/config/`);
}

export async function saveChannels(
  scenarioId: string,
  rows: { channel: string; month: number; mix_pct: number; commission_pct: number }[],
): Promise<{ saved: number; scenario_id: string }> {
  return api.put(`/scenarios/${scenarioId}/revenue/channels/bulk/`, rows);
}

// ── Paquete CWL (componentes por pax/noche) ───────────────────────────────────

export interface PackageComponent {
  component: string;
  label: string;
  rate_per_pax_night: string;
  is_commissionable: boolean;
}

export interface PackagesConfig {
  scenario_id: string;
  seeded: boolean;
  components: PackageComponent[];
  bev_food_ratio: string;
}

export async function getPackagesConfig(scenarioId: string): Promise<PackagesConfig> {
  return api.get<PackagesConfig>(`/scenarios/${scenarioId}/revenue/packages/config/`);
}

// Consulta libre sobre el GL. Formato LARGO (una fila por mes) porque el destino
// natural es una tabla dinamica: en formato ancho hay que despivotar primero.
export interface ConsultaFila {
  escenario: string; anio: number; mes: string; mes_num: number;
  dept_code: string; dept_name: string;
  account_code: string; account_name: string;
  clase: string; outlet: string; detalle: string; monto: number;
  linea_pl: string; grupo: string; dept_padre: string; tipo_dept: string;
  position_code: string; position_name: string; employee: string;
}
export interface ConsultaCatalogo {
  conjuntos: { key: string; label: string; nota: string }[];
  columnas: { key: string; label: string; tipo: string }[];
  escenarios: { id: string; label: string; year: number }[];
}

export async function getConsultaCatalogo(): Promise<ConsultaCatalogo> {
  return api.get("/consulta/conjuntos/");
}

export interface ConsultaFiltro {
  conjunto: string; escenarios: string[]; cuenta?: string; dept?: string;
  /** Digitos de clase: "6,7". Vacio = todas. */
  clase?: string;
  /** Codigo de posicion, por prefijo: "0111" o "0111-01". */
  posicion?: string;
  /** Rango de cuentas, inclusive. Se compara como numero, no como texto. */
  cuentaDesde?: string; cuentaHasta?: string;
  mesDesde?: number; mesHasta?: number;
}

function _qs(f: ConsultaFiltro): string {
  const p = new URLSearchParams({
    conjunto: f.conjunto,
    escenarios: f.escenarios.filter(Boolean).join(","),
    cuenta: f.cuenta ?? "", dept: f.dept ?? "", clase: f.clase ?? "",
    posicion: f.posicion ?? "",
    cuenta_desde: f.cuentaDesde ?? "", cuenta_hasta: f.cuentaHasta ?? "",
    mes_desde: String(f.mesDesde ?? 1), mes_hasta: String(f.mesHasta ?? 12),
  });
  return p.toString();
}

export async function correrConsulta(f: ConsultaFiltro): Promise<{
  filas: ConsultaFila[]; cantidad: number; truncado: boolean; total: number;
}> {
  return api.get(`/consulta/?${_qs(f)}`);
}

/** Baja el .xlsx. Va por fetch y no por <a href> porque el endpoint pide token. */
export async function bajarConsultaExcel(f: ConsultaFiltro): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/consulta/excel/?${_qs(f)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`No se pudo bajar el Excel (HTTP ${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Consulta_${f.conjunto}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}

// Gasto por CLASE de cuenta: 6 planilla, 5 costo, 7 opex, 8 propiedad.
// No sale del P&L porque sus lineas estan cortadas por DEPARTAMENTO: sumar los
// OPEX_* no da "todas las 7", porque la planilla y el costo de esos mismos
// departamentos entran en la misma linea. Es otro eje.
export interface GastoMes {
  month: number;
  payroll: number; cost: number; opex: number; property: number; total: number;
}
export interface GastoEscenario {
  scenario_id: string; type: string; version: string; year: number;
  meses: GastoMes[];
  /** Con detalle=true: {clase: {depto o cuenta: [12 meses]}} */
  detalle: Record<string, Record<string, number[]>> | null;
  /** Nombre de cada cuenta 8xxx: una lista de numeros sueltos no dice nada. */
  nombres_cuenta: Record<string, string>;
}

export async function getGastoPorClase(
  scenarioIds: string[], detalle = false,
): Promise<{
  clases: Record<string, string>;
  escenarios: GastoEscenario[];
  departamentos: Record<string, string>;
}> {
  const ids = scenarioIds.filter(Boolean).join(",");
  return api.get(`/gasto-por-clase/?scenarios=${encodeURIComponent(ids)}&detalle=${detalle}`);
}

// ── A&B abierto en comida / bebida / miscelaneos ──────────────────────────────
//
// El P&L tiene UNA linea para todo el A&B. Este corte vive un nivel mas abajo,
// en la cuenta del mayor, y por eso tiene endpoint propio.
export interface FbMes {
  month: number;
  ing_comida: number; ing_bebida: number; ing_misc: number; ing_total: number;
  cos_comida: number; cos_bebida: number; cos_misc: number; cos_total: number;
}
export interface FbEscenario {
  scenario_id: string; type: string; version: string; year: number; meses: FbMes[];
}
export interface FbDetalle {
  escenarios: FbEscenario[];
  cuentas: { ingreso: { cuenta: string; nombre: string; grupo: string | null }[];
             costo: { cuenta: string; nombre: string; grupo: string | null }[] };
  /** Cuentas de A&B que no cayeron en ningun grupo. Si hay alguna, el desglose
   *  NO suma el total — y por eso se muestran en vez de esconderse. */
  sin_clasificar: string[];
}
// ── Ingreso por linea, calculado desde la CUENTA ──────────────────────────────
//
// El P&L del Actual sale del RESUMEN importado, que es mas grueso que el mayor:
// no tiene la apertura de A&B, ni "Other Rooms Revenue", y mete el ingreso
// miscelaneo dentro de Sustainability. Este endpoint lo calcula desde la cuenta,
// que si tiene todo, y devuelve ademas el total del P&L para poder compararlos.
export interface IngresoMes { month: number; [linea: string]: number }
export interface IngresoEscenario {
  scenario_id: string; type: string; version: string; year: number;
  meses: IngresoMes[];
  pl: { month: number; total_revenues: number }[];
}
export interface IngresoDetalle {
  escenarios: IngresoEscenario[];
  nombres: Record<string, string>;
}
export async function getIngresoDetalle(scenarioIds: string[]): Promise<IngresoDetalle> {
  const ids = scenarioIds.filter(Boolean).join(",");
  return api.get(`/reports/ingreso-detalle/?scenarios=${encodeURIComponent(ids)}`);
}

// ── Estadisticas (cuentas clase 9) ───────────────────────────────────────────
//
// Tabla aparte del catalogo contable, misma puerta en Master Data: una cuenta de
// dinero solo necesita saber a que linea del P&L va; una estadistica necesita
// ademas que unidad mide, por que dimensiones se abre y como se acumula el ano.
export interface CuentaEstadistica {
  code: string; grupo: string; nombre_es: string; nombre_en: string;
  unidad: string; dims: string[]; deptos: string[]; agrega: string;
  legado: string; activa: boolean;
}
export interface CatalogoEstadisticas {
  cuentas: CuentaEstadistica[];
  jornada: { horas_mes: number; horas_dia: number; dias_base: number;
             cierran: string[]; por_encima: string[] };
}
export interface EstadisticasValores {
  scenario: { id: string; type: string; version: string; year: number; status: string };
  nombres: Record<string, string>;
  valores: { account_code: string; month: number; dept_code: string;
             position_code: string; room_type_code: string; value: number;
             origen: string }[];
  /** Posiciones cuyas horas no cierran su mes. Vacio = todas cierran. */
  jornada_descuadres: { dept_code: string; position_code: string;
                        month: number; diferencia: number }[];
}
export async function getCatalogoEstadisticas(): Promise<CatalogoEstadisticas> {
  return api.get("/estadisticas/catalogo/");
}
export async function editarCuentaEstadistica(
  code: string, body: { nombre_es?: string; nombre_en?: string; activa?: boolean },
): Promise<{ ok: boolean }> {
  return api.put(`/estadisticas/catalogo/${encodeURIComponent(code)}/`, body);
}
export async function getEstadisticas(scenarioId: string): Promise<EstadisticasValores> {
  return api.get(`/estadisticas/${scenarioId}/`);
}
/** Baja el archivo. Por fetch y no por <a href> porque el endpoint pide token. */
export async function bajarPlantillaEstadisticas(scenarioId: string): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/estadisticas/${scenarioId}/plantilla.xlsx`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`No se pudo bajar el archivo (HTTP ${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `Estadisticas_${scenarioId.slice(0, 8)}.xlsx`;
  a.click();
  URL.revokeObjectURL(url);
}
export async function importarEstadisticas(
  scenarioId: string, archivo: File, dryRun = false,
): Promise<{ ok?: boolean; valores_guardados?: number; filas_con_dato: number }> {
  const form = new FormData();
  form.append("archivo", archivo);
  const token = getToken();
  const res = await fetch(
    `${BASE}/estadisticas/${scenarioId}/importar/?dry_run=${dryRun}`,
    { method: "POST", body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) {
    const cuerpo = await res.json().catch(() => ({}));
    throw Object.assign(new Error("No se pudo cargar"), { detail: cuerpo.detail });
  }
  return res.json();
}

export async function getFbDetalle(scenarioIds: string[]): Promise<FbDetalle> {
  const ids = scenarioIds.filter(Boolean).join(",");
  return api.get(`/reports/fb-detalle/?scenarios=${encodeURIComponent(ids)}`);
}

// ── Origenes de actuales: el puente cuenta-de-alla -> cuenta-de-aca ───────────
//
// Oxigen y Ojochal llevan la contabilidad en QuickBooks; Corcovado va a traer la
// suya de un backoffice por API. Lo que cambia entre sistemas es el codigo de
// cuenta; el catalogo USALI de este lado no. El puente es DATO, no codigo: por
// eso abrir una propiedad es cargar su mapeo y no un desarrollo.
export interface ReglaOrigen {
  id?: string;
  origen?: string;
  cuenta_origen: string;
  nombre_origen: string;
  dept_origen: string;
  account_code: string;
  dept_code: string;
  outlet: string;
  activo: boolean;
  nota: string;
}

export interface EstadoOrigen {
  origen: string;
  reglas_activas: number;
  listo_para_importar: boolean;
}

export async function getOrigenes(): Promise<{ hotel_id: string; origenes: EstadoOrigen[]; nota: string }> {
  return api.get("/origenes/");
}

export async function getMapeoOrigen(origen: string): Promise<{ origen: string; reglas: ReglaOrigen[] }> {
  return api.get(`/origenes/${origen}/mapeo/`);
}

/** Reemplaza el mapeo ENTERO de ese origen. Se valida antes de borrar. */
export async function guardarMapeoOrigen(
  origen: string, reglas: ReglaOrigen[],
): Promise<{ origen: string; reglas: number }> {
  return api.put(`/origenes/${origen}/mapeo/`, { reglas });
}

// ── Etiquetas de componente, editables por propiedad ──────────────────────────
//
// El CÓDIGO (FOOD, ACTIVITIES, TRANSPORT, SUSTAINABILITY) es fijo: es con lo que
// el motor arma el ingreso y lo rutea al P&L. La ETIQUETA es lo que se lee, y
// cada propiedad la pone como le sirva — «Transportation» es la lancha desde
// Sierpe en Corcovado y puede ser «Traslado aeropuerto» en otro hotel.
export interface ComponentLabelRow {
  code: string; label: string; por_defecto: string; editado: boolean;
}

export async function getComponentLabels(
  hotelId: string, kind = "PACKAGE",
): Promise<{ labels: ComponentLabelRow[] }> {
  return api.get(`/hotels/${hotelId}/component-labels/?kind=${kind}`);
}

/** Etiqueta vacía = volver al texto por defecto. */
export async function updateComponentLabel(
  hotelId: string, code: string, label: string, kind = "PACKAGE",
): Promise<ComponentLabelRow> {
  return api.put(`/hotels/${hotelId}/component-labels/${code}/?kind=${kind}`, { label });
}

export async function savePackages(
  scenarioId: string,
  components: { component: string; rate_per_pax_night: number; is_commissionable: boolean }[],
  bevFoodRatio: number,
): Promise<{ saved: number; scenario_id: string }> {
  return api.put(`/scenarios/${scenarioId}/revenue/packages/bulk/`, {
    components, bev_food_ratio: bevFoodRatio,
  });
}

// ── Package Components (menú + experiencias) ──────────────────────────────────

export interface PkgItem {
  inclusion: string;
  unit: string;
  unit_price: string | null;
  enabled: boolean;
  notes: string;
  category: string;
  qty_mult_single: string;
  qty_mult_double: string;
  info: string;
}
export interface PkgExperienceCfg {
  name: string;
  nights: number;
  days: number;
  /** Cuál alimenta el tab «Package Component Rack and Net Rate». */
  es_base: boolean;
  items: PkgItem[];
}
export interface PackageComponentsConfig {
  scenario_id: string;
  seeded: boolean;
  experiences: PkgExperienceCfg[];
}

export interface PkgItemIn {
  inclusion: string; unit: string; unit_price: number | null; enabled: boolean;
  notes: string; category: string; qty_mult_single: number; qty_mult_double: number; info: string;
}

export async function getPackageComponents(scenarioId: string): Promise<PackageComponentsConfig> {
  return api.get<PackageComponentsConfig>(`/scenarios/${scenarioId}/packages/components/config/`);
}

export async function savePackageComponents(
  scenarioId: string,
  // `es_base` = cuál alimenta el tab Rack & Net. Va con el resto porque el
  // guardado reemplaza las experiencias enteras: si no viajara, se perdería.
  experiences: { name: string; nights: number; days: number; es_base: boolean; items: PkgItemIn[] }[],
): Promise<{ saved_experiences: number; saved_items: number }> {
  return api.put(`/scenarios/${scenarioId}/packages/components/bulk/`, { experiences });
}

// ── Rack Rates (rooms only) ───────────────────────────────────────────────────

export interface RackRateRow {
  room_type_id: string;
  code?: string;
  name: string;
  jan: string; feb: string; mar: string; apr: string; may: string; jun: string;
  jul: string; aug: string; sep: string; oct: string; nov: string; dec: string;
}

export interface RackRatesResponse {
  scenario_id: string;
  year: number;
  rooms: RackRateRow[];
}

export async function getRackRates(scenarioId: string): Promise<RackRatesResponse> {
  return api.get<RackRatesResponse>(`/scenarios/${scenarioId}/revenue/rack-rates/`);
}

export type RackRateBulkRow = { room_type_id: string } & Record<MonthKey, number>;

export async function saveRackRates(
  scenarioId: string,
  rows: RackRateBulkRow[],
): Promise<{ saved: number; scenario_id: string }> {
  return api.put(`/scenarios/${scenarioId}/revenue/rack-rates/bulk/`, rows);
}

// ── Ocupación (% por tipo de habitación × mes) ────────────────────────────────

export interface OccPctRow {
  room_type_id: string;
  name: string;
  jan: string; feb: string; mar: string; apr: string; may: string; jun: string;
  jul: string; aug: string; sep: string; oct: string; nov: string; dec: string;
}

export interface OccupancyPctResponse {
  scenario_id: string;
  year: number;
  seeded: boolean;
  rooms: OccPctRow[];
}

export async function getOccupancyPct(scenarioId: string): Promise<OccupancyPctResponse> {
  return api.get<OccupancyPctResponse>(`/scenarios/${scenarioId}/revenue/occupancy-pct/`);
}

export type OccPctBulkRow = { room_type_id: string } & Record<MonthKey, number>;

export async function saveOccupancyPct(
  scenarioId: string,
  rows: OccPctBulkRow[],
): Promise<{ saved: number; scenario_id: string }> {
  return api.put(`/scenarios/${scenarioId}/revenue/occupancy-pct/bulk/`, rows);
}

export async function getMonthlyRevenue(scenarioId: string): Promise<MonthlyRevenue[]> {
  // Backend returns { scenario_id, year, months: [...] } — return the months array.
  const res = await api.get<{ months: MonthlyRevenue[] }>(
    `/scenarios/${scenarioId}/revenue/monthly/`,
  );
  return res.months ?? [];
}

export interface FlowThroughRow { concept: string; variances: number[]; }
export interface FlowThrough { scenario_id: string; comparison_ids: string[]; has_data: boolean; rows: FlowThroughRow[]; }
export async function getFlowThrough(scenarioId: string, month: number, ytd: boolean, compare: string[] = []): Promise<FlowThrough> {
  const cmp = compare.filter(Boolean).map(c => `&compare=${encodeURIComponent(c)}`).join("");
  return api.get<FlowThrough>(`/scenarios/${scenarioId}/flow-through/?month=${month}&ytd=${ytd}${cmp}`);
}

export interface PLByDeptRow {
  group: string; name: string; kind: "operating" | "overhead";
  revenue: number; payroll: number;
  /** opex + cost (como lo muestra el P&L por departamento de siempre; sin repartos). */
  operating: number;
  /** Gasto 7xxx y costo de venta 5xxx por separado. */
  opex: number; cost: number;
  /** Repartos netos entre departamentos (cafetería, lavandería, salarios).
   *  Negativo si el departamento es ORIGEN del reparto. NO está dentro de
   *  `operating`; sí está dentro de la línea OPEX_x del P&L oficial.
   *
   *  Los `alloc_*` lo abren por clase de cuenta destino, porque el reparto no es
   *  un gasto aparte sino planilla/gasto/costo que cambió de departamento: 6xxx
   *  es planilla (salarios 6000, cafetería 6025), 7xxx gasto operativo
   *  (lavandería 7310/7685), 5xxx costo. `alloc_other` es la contracuenta 4999
   *  del crédito, que solo cae en el departamento ORIGEN. Los cuatro suman `alloc`. */
  alloc: number;
  alloc_payroll: number; alloc_opex: number; alloc_cost: number; alloc_other: number;
  total_expenses: number; gop: number;
}
export interface PLByDeptBelowGop {
  rent: number; fees: number; insurance: number; other: number; total_non_op: number;
  ebitda_before_capital: number; capital: number; financial: number; depreciation: number;
  ebt: number; income_taxes: number; net_profit: number;
}
export interface PLByDept {
  scenario_id: string; months: number[]; has_data: boolean;
  departments: PLByDeptRow[]; total_operating_profit: number; total_overhead: number;
  total_gop: number; below_gop: PLByDeptBelowGop;
}
export async function getPLByDept(scenarioId: string, month: number, ytd: boolean): Promise<PLByDept> {
  return api.get<PLByDept>(`/scenarios/${scenarioId}/pl-by-dept/?month=${month}&ytd=${ytd}`);
}

// ── Revenue checkbook (direct USD per line) ───────────────────────────────────

export type RevenueSource = "drivers" | "checkbook";

// Era un `const MONTH_KEYS` del que solo se derivaba este tipo — un arreglo que
// viajaba en el bundle sin que nadie lo leyera en tiempo de ejecución.
export type MonthKey =
  | "jan" | "feb" | "mar" | "apr" | "may" | "jun"
  | "jul" | "aug" | "sep" | "oct" | "nov" | "dec";

export interface RevenueCheckbookRow {
  line: string;
  label: string;
  /** La cuenta contable, cuando la línea ES una cuenta. `null` en las que
   *  agregan varias (Rooms, Food…): poner un código ahí sería mentir. */
  dept: string | null;
  account: string | null;
  jan: string; feb: string; mar: string; apr: string; may: string; jun: string;
  jul: string; aug: string; sep: string; oct: string; nov: string; dec: string;
}

export interface RevenueCheckbook {
  scenario_id: string;
  year: number;
  source: RevenueSource;
  lines: RevenueCheckbookRow[];
}

export async function getRevenueCheckbook(scenarioId: string): Promise<RevenueCheckbook> {
  return api.get<RevenueCheckbook>(`/scenarios/${scenarioId}/revenue/checkbook/`);
}

export type RevenueBulkRow = { line: string } & Record<MonthKey, number>;

export async function saveRevenueCheckbook(
  scenarioId: string,
  rows: RevenueBulkRow[],
): Promise<{ saved: number; scenario_id: string }> {
  return api.put(`/scenarios/${scenarioId}/revenue/checkbook/bulk/`, rows);
}

export async function setRevenueSource(
  scenarioId: string,
  source: RevenueSource,
): Promise<{ updated: boolean; revenue_source: RevenueSource }> {
  return api.patch(`/scenarios/${scenarioId}/revenue/source/`, { revenue_source: source });
}

// ── Parámetros de planilla por escenario (CCSS, aguinaldo) ────────────────────

/** Drivers de los conceptos de planilla que salen de una regla, no de digitación. */
export interface PayrollDrivers {
  overtime_pct: string;            // 6001 = S&W × %
  bonus_pct: string;               // 6027 = S&W × %
  vacaciones_rate: string;         // 6023 = BASE × %
  severance_annual_rate: string;   // 6026 = BASE × % ÷ 12
  cafeteria_daily_crc: string;     // 6025 = FTE × días trabajados × ₡/día
  transport_monthly_crc: string;   // 6029 = FTE × ₡/mes
  housing_monthly_crc: string;     // 6028 = FTE × ₡/mes
  other_monthly_crc: string;       // 6030 = FTE × ₡/mes
  ins_annual_crc: string;          // 6022 = monto del año repartido por FTE
  working_days: number[];          // 12 meses
  holidays: number[];              // 12 meses — feriados pagados
  days_off: number[];              // 12 meses — días libres pagados (6002)
  calendar_days: number[];         // 12 meses
}

export interface PayrollParamsResponse extends PayrollDrivers {
  scenario_id: string;
  ccss_rate: string;          // fracción (0.26830)
  aguinaldo_divisor: string;  // 12
  seeded: boolean;
}

export async function getPayrollParams(scenarioId: string): Promise<PayrollParamsResponse> {
  return api.get<PayrollParamsResponse>(`/scenarios/${scenarioId}/payroll/params/`);
}

export async function savePayrollParams(
  scenarioId: string, ccssRate: number, aguinaldoDivisor: number,
  drivers?: Partial<Record<keyof PayrollDrivers, number | number[]>>,
): Promise<{ saved: boolean; ccss_rate: string; aguinaldo_divisor: string; aviso?: string }> {
  return api.put(`/scenarios/${scenarioId}/payroll/params/`, {
    ccss_rate: ccssRate, aguinaldo_divisor: aguinaldoDivisor, ...(drivers ?? {}),
  });
}

// ── Spa (capture-rate model: pax × capture rate × precio promedio) ─────────────

export interface SpaMonthCfg { month: number; capture_pct: string; }
export interface SpaBudgetResponse {
  scenario_id: string;
  year: number;
  seeded: boolean;
  avg_price: string;
  months: SpaMonthCfg[];
  /** `false` = el escenario arma sus ingresos con drivers y no lee el checkbook,
   *  asi que la linea SPA que se escribe al guardar no llega al P&L. */
  llega_al_pl: boolean; modo_ingresos: string;
}

export async function getSpaBudget(scenarioId: string): Promise<SpaBudgetResponse> {
  return api.get<SpaBudgetResponse>(`/scenarios/${scenarioId}/revenue/spa/`);
}

export async function saveSpaBudget(
  scenarioId: string,
  avgPrice: number,
  months: { month: number; capture_pct: number; revenue: number }[],
): Promise<{ saved: boolean; scenario_id: string; spa_total: string;
             llega_al_pl?: boolean; modo_ingresos?: string }> {
  return api.put(`/scenarios/${scenarioId}/revenue/spa/bulk/`, { avg_price: avgPrice, months });
}

export async function updateRackRate(
  scenarioId: string,
  roomTypeId: string,
  month: number,
  rackRate: number,
): Promise<void> {
  await api.put(`/scenarios/${scenarioId}/revenue/rate-cards/${roomTypeId}/${month}/`, { rack_rate: rackRate });
}

export async function updateOccupancy(
  scenarioId: string,
  roomTypeId: string,
  month: number,
  roomsOccupied: number,
): Promise<void> {
  await api.put(`/scenarios/${scenarioId}/revenue/occupancy/${roomTypeId}/${month}/`, { rooms_occupied: roomsOccupied });
}

// ── Historical KPI helpers ────────────────────────────────────────────────────

export interface HistoricalKpi {
  hotel_id: string;
  year: number;
  month: number;
  room_type_id: number;
  rooms_available: number;
  rooms_occupied: string;
  guests: string;
  occupancy_pct: string;
  adr_usd: string;
  revpar_usd: string;
  revenue_usd: string;
  source: string;
}

export async function getHistoricalKpis(hotelId: string, year?: number): Promise<HistoricalKpi[]> {
  const qs = year ? `?year=${year}` : "";
  return api.get<HistoricalKpi[]>(`/hotels/${hotelId}/historical/${qs}`);
}

// ── Payroll helpers ───────────────────────────────────────────────────────────

export interface Dept { dept_code: string; dept_name: string; }

export interface ConceptEntry {
  id: string; month: number;
  c6000_sw: number; c6001_overtime: number; c6002_day_off: number;
  c6003_working_holiday: number; c6010_commissions: number;
  c6024_vacations_taken: number; c6027_incentive_bonus: number;
  c6020_ccss: number; c6021_aguinaldo: number; c6004_disabilities: number;
  c6022_occ_hazard: number; c6023_vacation_prov: number;
  c6025_cafeteria: number; c6026_severance: number;
  c6028_housing: number; c6029_transport: number; c6030_other: number;
  total: number;
}

export interface Position {
  id: string; dept_code: string; dept_name: string;
  position_code: string; position_name: string;
  employee_name: string; employee_type: string;
  salary_amount: number; salary_currency: string;
  months: { month: number; fte: number; entry: ConceptEntry | null }[];
}

export interface DeptCheckbook {
  scenario_id: string; dept_code: string; positions: Position[];
}

export interface DeptSummaryMonth {
  month: number;
  c6000: number; c6001: number; c6002: number; c6003: number;
  c6010: number; c6024: number; c6027: number; base: number;
  c6020: number; c6021: number; c6004: number; c6022: number;
  c6023: number; c6025: number; c6026: number; c6028: number;
  c6029: number; c6030: number; total: number;
}

export interface FteReportRow {
  dept_code: string; dept_name: string;
  position_id: string; position_name: string; employee_name: string;
  fte_by_month: number[];  // index 0 = Jan
}

export async function getPayrollDepts(scenarioId: string): Promise<Dept[]> {
  const r = await api.get<{ depts: Dept[] }>(`/payroll/${scenarioId}/depts/`);
  return r.depts;
}

export async function getDeptCheckbook(scenarioId: string, deptCode: string): Promise<DeptCheckbook> {
  return api.get<DeptCheckbook>(`/payroll/${scenarioId}/dept/${deptCode}/`);
}

export async function getDeptSummary(scenarioId: string, deptCode: string): Promise<DeptSummaryMonth[]> {
  const r = await api.get<{ monthly: DeptSummaryMonth[] }>(`/payroll/${scenarioId}/dept/${deptCode}/summary/`);
  return r.monthly;
}

export async function getAllPositions(scenarioId: string): Promise<Position[]> {
  const depts = await getPayrollDepts(scenarioId);
  const all: Position[] = [];
  for (const d of depts) {
    const cb = await getDeptCheckbook(scenarioId, d.dept_code);
    all.push(...cb.positions);
  }
  return all;
}

export interface PayrollRow {
  dept_code: string; dept_name?: string;
  position_code?: string; position_name: string;
  employee_name?: string; salary_amount?: string | number; salary_currency?: string;
  [fte: string]: string | number | undefined;  // fte_jan..fte_dec
}

// Replace the whole roster (structure + values)
export async function bulkPayroll(scenarioId: string, rows: PayrollRow[]) {
  return api.put<{ imported: number }>(`/payroll/${scenarioId}/bulk/`, rows);
}

// Update salary/FTE only, matched by person (no structural change)
export async function updateSalaries(scenarioId: string, rows: PayrollRow[]) {
  return api.put<{ updated: number; unmatched: unknown[] }>(`/payroll/${scenarioId}/salaries/`, rows);
}

// Owner report → styled .xlsx. The frontend supplies the already-computed
// numbers (KPIs come from drivers) so the sheet matches the screen exactly.
export type OwnerReportExcelPayload = {
  scenario_label: string;
  kpis: { occ_pct: number; adr: number; revpar: number; pax: number };
  pl_rows: { label: string; value: number; strong: boolean }[];
  notes: { section: string; ref: string; month_name: string; body: string }[];
};
export async function downloadOwnerReportExcel(
  scenarioId: string, payload: OwnerReportExcelPayload,
): Promise<Blob> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const res = await fetch(`${base}/scenarios/${scenarioId}/owner-report/excel/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.blob();
}

// Download the locked payroll Excel (only salary + FTE editable) as a Blob
export async function downloadPayrollExcel(scenarioId: string): Promise<Blob> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const res = await fetch(`${base}/payroll/${scenarioId}/export/excel/`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.blob();
}

// Upload the filled payroll Excel (multipart) → re-applies salary + FTE
export async function uploadPayrollExcel(scenarioId: string, file: File) {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${base}/payroll/${scenarioId}/import/excel/`, { method: "POST", body: fd, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<{ imported?: number }>;
}

// Agrega N personas SIN tocar el resto de la planilla. No usar `bulkPayroll`
// para esto: reemplaza la planilla entera y se lleva los conceptos digitados.
export async function addPositions(scenarioId: string, body: {
  dept_code: string; dept_name?: string; position_name: string;
  position_code?: string; count: number;
  salary_amount?: number; salary_currency?: string;
}) {
  return api.post<{ created: number; codes: string[]; ids: string[] }>(
    `/payroll/${scenarioId}/positions/add/`, body);
}

export async function getNextPositionCode(scenarioId: string, dept: string, count = 1) {
  return api.get<{ dept: string; codes: string[]; usados: number }>(
    `/payroll/${scenarioId}/next-position-code/?dept=${encodeURIComponent(dept)}&count=${count}`);
}

// ── Provisionamiento: qué departamentos usa cada propiedad ─────────────────
export interface ProvDim {
  /** Prendido = NADIE del paquete está apagado en esta dimensión. */
  enabled: boolean;
  aplica: boolean;
  /** Líneas cargadas en TODO el paquete, en todos los escenarios. */
  datos: number;
  /** Los del paquete que están apagados. Con una madre sola es ella misma. */
  apagados: string[];
  /** Unos apagados y otros no: la regla nueva no puede expresarlo. */
  mixto: boolean;
  /** Cuántos del paquete llevan esta dimensión. */
  miembros: number;
}
/** Un miembro del paquete de una madre: ella misma, sus hijos funcionales y
 *  sus sets de producto (Villas, Residencias). */
export interface ProvMiembro {
  dept_code: string; dept_name: string; room_set: boolean; es_madre: boolean;
}
/** Una fila de la matriz = un departamento MADRE con todo su paquete. Los
 *  hijos no tienen fila propia: se provisiona la madre y arrastra el paquete. */
export interface ProvDeptRow {
  dept_code: string; dept_name: string; name_en: string;
  pl_kind: string; pl_group: string; parent_dept_code: string;
  is_revenue_dept: boolean; is_allocation_source: boolean; room_set: boolean;
  paquete: ProvMiembro[];
  dims: Record<string, ProvDim>;
  datos_totales: number;
}
export interface ProvMatrix {
  hotel_id: string; hotel_name: string;
  dimensiones: { key: string; label: string }[];
  rows: ProvDeptRow[];
  /** Casillas apagadas guardadas (a nivel de departamento suelto, incluidos
   *  hijos: es lo que hay en la base, no lo que se puede tocar hoy). */
  apagados: number;
  /** 39 — el catálogo entero. */ total_departamentos: number;
  /** 23 — las filas de esta matriz. */ total_madres: number;
  /** Casillas donde la madre y sus hijos NO coinciden. Son estados que la regla
   *  nueva no puede representar; se muestran y no se tocan. */
  mixtos: number;
}
export async function getProvisioningHotels(): Promise<{
  hotels: { id: string; name: string; apagados: number; default_locale: string }[] }> {
  return api.get(`/provisioning/hotels/`);
}
export async function getProvisioningDepts(hotelId: string): Promise<ProvMatrix> {
  return api.get<ProvMatrix>(`/provisioning/${hotelId}/departments/`);
}
/** `rows` lleva SOLO departamentos madre: el backend abre cada uno en su
 *  paquete completo. Mandar un hijo devuelve 422. */
export async function saveProvisioningDepts(
  hotelId: string,
  rows: { dept_code: string; dimension: string; enabled: boolean; notes?: string }[],
  force = false,
): Promise<{ ok: boolean; apagados: number; prendidos: number;
             casillas: number; recibidas: number;
             con_datos: { dept_code: string; dimension: string; lineas: number }[] }> {
  return api.put(`/provisioning/${hotelId}/departments/`, { rows, force });
}
export async function copiarProvisioning(hotelId: string, origenId: string) {
  return api.post<{ ok: boolean; copiadas: number; reemplazadas: number }>(
    `/provisioning/${hotelId}/copiar-de/${origenId}/`);
}

// ── Reporte de planilla por código de posición ─────────────────────────────
export interface PayrollPositionRow {
  position_id: string; position_code: string; position_name: string;
  employee_name: string; dept_code: string; dept_name: string;
  salary_amount: number; salary_currency: string;
  fte: number[]; fte_prom: number;
  anual: Record<string, number>;
  meses: Record<string, number[]>;
  devengado: number; cargas: number; beneficios: number; costo: number;
}
export interface PayrollByPositionReport {
  scenario_id: string; year: number; dept: string;
  conceptos: { key: string; code: string; label: string; grupo: string }[];
  rows: PayrollPositionRow[];
  totales: {
    anual: Record<string, number>; meses: Record<string, number[]>;
    devengado: number; cargas: number; beneficios: number; costo: number;
    fte_prom: number;
  };
  auditoria: {
    sin_codigo: { dept_code: string; position_name: string; employee_name: string }[];
    duplicados: { position_code: string; posiciones: { dept_code: string; position_name: string; employee_name: string }[] }[];
    codigos_unicos: number; posiciones: number; filas_gl: number; limpio: boolean;
  };
}
export async function getPayrollByPosition(scenarioId: string, dept = ""): Promise<PayrollByPositionReport> {
  const q = dept ? `?dept=${encodeURIComponent(dept)}` : "";
  return api.get<PayrollByPositionReport>(`/reports/payroll-by-position/${scenarioId}/${q}`);
}

// Duplicate one position → adds one more person (VACANTE N+1) of the same position
export async function duplicatePosition(scenarioId: string, positionId: string) {
  return api.post<{ id: string; employee_name: string; position_name: string }>(
    `/payroll/${scenarioId}/position/${positionId}/duplicate/`);
}

// Delete a single position
export async function deletePosition(scenarioId: string, positionId: string) {
  return api.delete<void>(`/payroll/${scenarioId}/position/${positionId}/`);
}

// Edit one position in the app (currency, employee name, salary, etc.)
export async function updatePosition(
  scenarioId: string, positionId: string,
  fields: Partial<{ position_name: string; employee_name: string;
    salary_amount: number; salary_currency: string }>,
) {
  return api.put<{ id: string; updated: boolean }>(
    `/payroll/${scenarioId}/position/${positionId}/`, fields);
}

export async function getFteReport(scenarioId: string): Promise<FteReportRow[]> {
  // Build the per-position FTE report from the roster (the /fte-report/ endpoint
  // returns dept-level aggregates, not the per-person detail this view needs).
  const positions = await getAllPositions(scenarioId);
  return positions.map(p => ({
    dept_code: p.dept_code,
    dept_name: p.dept_name,
    position_id: p.id,
    position_name: p.position_name,
    employee_name: p.employee_name,
    fte_by_month: Array.from({ length: 12 }, (_, i) =>
      (p.months ?? []).find(m => m.month === i + 1)?.fte ?? 0),
  }));
}

// ── Cost of Sales helpers ─────────────────────────────────────────────────────

export type CalcMode = "MANUAL" | "DRIVER";
export type DriverType = "REVENUE_LINE" | "OCC_ROOMS" | "GUESTS" | "AVAIL_ROOMS" | "KILOS" | "";
export type RevenueLine = "ROOMS" | "FOOD" | "BEVERAGE" | "ACTIVITIES" | "TRANSPORT"
  | "INNOCEANA" | "RETAIL" | "SPA" | "SUSTAINABILITY" | "";

export interface CostEntry {
  id: string;
  scenario_id: string;
  hotel_id: string;
  dept_code: string;
  account_code: string;
  account_name: string;
  calc_mode: CalcMode;
  driver_type: DriverType;
  driver_pct_or_rate: string;
  revenue_line_ref: RevenueLine;
  months: Record<string, string>;  // "jan".."dec" → USD amount string
  rates?: Record<string, string | null>;  // "jan".."dec" → monthly % (fraction) or null=base
  annual_total: string;
  /** 'USD' | 'CRC'. En CRC el dato maestro son los colones y "months" trae el
   *  dólar DERIVADO con el tipo de cambio de cada mes. */
  currency?: string;
  crc_jan?: string; crc_feb?: string; crc_mar?: string; crc_apr?: string;
  crc_may?: string; crc_jun?: string; crc_jul?: string; crc_aug?: string;
  crc_sep?: string; crc_oct?: string; crc_nov?: string; crc_dec?: string;
}

export interface CostRevenueRef {
  rooms: string; food: string; beverage: string; activities: string;
  transport: string; sustainability: string; innoceana: string;
  retail: string; spa: string; total: string;
  rooms_occupied: string; guests: string; rooms_available: number;
}

/** Costo que le cayó al departamento por reparto (cafetería 0220, lavandería
 *  0161). No se edita —nadie lo digitó— pero el P&L SÍ lo suma. */
export interface LineaRepartida {
  account_code: string;
  account_name: string;
  /** A que departamento se cargo. Puede ser un hijo del que se esta viendo:
   *  abriendo A&B 0120 aparecen las lineas de Cocina 0122 y Restaurante 0123. */
  target_dept: string;
  source_dept: string;
  basis_type: string;
  jan: string; feb: string; mar: string; apr: string; may: string; jun: string;
  jul: string; aug: string; sep: string; oct: string; nov: string; dec: string;
  total: string;
  editable: false;
}

export interface CostDeptCheckbook {
  scenario_id: string;
  dept_code: string;
  entries: CostEntry[];
  allocated?: LineaRepartida[];
  revenue_reference: Record<number, CostRevenueRef>;
}

export interface CostMonthlySummary {
  month: number;
  total_cos: string;
  relevant_revenue: string;
  gross_profit: string;
  margin_pct: string;
}

export async function getCostDepts(scenarioId: string): Promise<{ dept_code: string }[]> {
  const r = await api.get<{ depts: { dept_code: string }[] }>(`/costs/${scenarioId}/depts/`);
  return r.depts;
}

export async function getCostDeptCheckbook(
  scenarioId: string,
  deptCode: string,
): Promise<CostDeptCheckbook> {
  return api.get<CostDeptCheckbook>(`/costs/${scenarioId}/dept/${deptCode}/`);
}

export async function getCostSummary(
  scenarioId: string,
  deptCode: string,
): Promise<CostMonthlySummary[]> {
  const r = await api.get<{ monthly: CostMonthlySummary[] }>(
    `/costs/${scenarioId}/dept/${deptCode}/summary/`,
  );
  return r.monthly;
}

export interface CostCatalogItem {
  dept_code: string; line_name: string; account_code: string; name: string;
}
export async function getCostCatalog(): Promise<CostCatalogItem[]> {
  return api.get<CostCatalogItem[]>(`/costs/catalog/`);
}

export async function createCostEntry(
  scenarioId: string,
  deptCode: string,
  body: Record<string, unknown>,  // accepts flat jan..dec for fixed amounts
): Promise<CostEntry> {
  return api.post<CostEntry>(`/costs/${scenarioId}/dept/${deptCode}/entry/`, body);
}

export async function updateCostEntry(
  scenarioId: string,
  entryId: string,
  body: Record<string, unknown>,  // accepts jan..dec amounts and rate_<month>
): Promise<CostEntry> {
  return api.put<CostEntry>(`/costs/${scenarioId}/entry/${entryId}/`, body);
}

export async function deleteCostEntry(scenarioId: string, entryId: string): Promise<void> {
  await api.delete(`/costs/${scenarioId}/entry/${entryId}/`);
}

export async function recalculateCosts(scenarioId: string): Promise<{ recalculated: number }> {
  return api.post<{ recalculated: number }>(`/costs/${scenarioId}/recalculate/`);
}

// ── OPEX helpers ──────────────────────────────────────────────────────────────

export interface OpexEntry {
  id: string;
  scenario_id: string;
  dept_code: string;
  account_code: string;
  account_name: string;
  detail_code: string;
  detail_desc: string;
  months: Record<string, string>;  // "jan".."dec" → USD string
  annual_total: string;
  /** 'USD' | 'CRC'. En CRC los colones son el dato maestro y "months" trae el
   *  dólar DERIVADO con el tipo de cambio de cada mes. */
  currency?: string;
  crc_months?: Record<string, string>;
  crc_annual?: string;
}

export interface OpexAccount {
  account_code: string;
  account_name: string;
  lines: OpexEntry[];
  monthly_totals: Record<string, string>;
  annual_total: string;
}

export interface OpexDeptCheckbook {
  scenario_id: string;
  dept_code: string;
  accounts: OpexAccount[];
  dept_monthly_totals: Record<string, string>;
  dept_annual_total: string;
  allocated?: LineaRepartida[];
  allocated_annual_total?: string;
}

export interface OpexDeptSummaryAccount {
  account_code: string;
  account_name: string;
  monthly: Record<string, string>;
  annual_total: string;
}

export interface OpexDeptSummary {
  dept_code: string;
  accounts: OpexDeptSummaryAccount[];
  dept_monthly_totals: Record<string, string>;
  dept_annual_total: string;
}

export async function getOpexDepts(scenarioId: string): Promise<{ dept_code: string }[]> {
  const r = await api.get<{ depts: { dept_code: string }[] }>(`/opex/${scenarioId}/depts/`);
  return r.depts;
}

export async function getOpexDeptCheckbook(
  scenarioId: string,
  deptCode: string,
): Promise<OpexDeptCheckbook> {
  return api.get<OpexDeptCheckbook>(`/opex/${scenarioId}/dept/${deptCode}/`);
}

export async function getOpexDeptSummary(
  scenarioId: string,
  deptCode: string,
): Promise<OpexDeptSummary> {
  return api.get<OpexDeptSummary>(`/opex/${scenarioId}/dept/${deptCode}/summary/`);
}

export async function updateOpexEntry(
  scenarioId: string,
  entryId: string,
  body: Partial<OpexEntry>,
): Promise<OpexEntry> {
  return api.put<OpexEntry>(`/opex/${scenarioId}/entry/${entryId}/`, body);
}

export async function importAllOpex(scenarioId: string): Promise<{ imported: number }> {
  return api.post<{ imported: number }>(`/opex/${scenarioId}/import/`);
}

export function opexExcelUrl(scenarioId: string): string {
  return dlUrl(`/opex/${scenarioId}/export/excel/`);
}

export async function importOpexExcel(
  scenarioId: string,
  file: File,
): Promise<{ imported: number; depts: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/opex/${scenarioId}/import/excel/`, {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export interface PLUnmappedLine { row: number; label: string; months_with_data: number; total: number; }
export interface PLCheckFail { month: number; check: string; calculado: number; archivo: number; dif: number; }
export interface ImportPLSnapshotResult {
  dry_run?: boolean;
  merge?: boolean;
  /** El camino que se recorrio, dicho por el servidor y no supuesto aca. */
  mes_de_cierre?: number | null;
  /** Meses que traia el archivo y el cierre mensual NO escribio. */
  meses_descartados?: number[];
  total_unmapped?: number;
  total_checks_failed?: number;
  blocks: {
    label: string;
    matched: string | null;
    scenario_id?: string;
    merge?: boolean;
    months?: number[];
    months_touched?: number[];
    stats_months?: number;
    line_months?: number;
    lines_written?: number;
    lines_per_month?: number;
    unmapped?: PLUnmappedLine[];
    checks_failed?: PLCheckFail[];
    ok?: boolean;
    aviso?: string;
    /** Corte de meses cerrados con que quedo el escenario despues de cargar. */
    actuals_through?: number;
    /** Solo si se pidio `apagar_corte`: el corte que tenia antes. */
    corte_apagado?: number;
    /**
     * El destino tenia corte y se subio en reemplazo total. NO se toco — pero
     * hay que verlo, porque es la decision que antes se tomaba sola.
     */
    aviso_corte?: string;
  }[];
  cut_advanced?: { scenario_id: string; version: string; actuals_through: number }[];
}

/**
 * @param merge  `true` (default) = alcance del MES: reemplaza solo los meses que
 *   trae el archivo. `false` = reemplaza el escenario entero. El default sigue al
 *   del backend a proposito: dejarlo en `false` aca mandaria `merge=false` en la
 *   URL y anularia el default del servidor desde el cliente.
 */
export async function importPLSnapshot(file: File, merge = true, dryRun = false): Promise<ImportPLSnapshotResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/scenarios/import-pl-snapshot/?merge=${merge}&dry_run=${dryRun}`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

/**
 * El bloque de control de ARRIBA del archivo, comparado contra lo que consolida
 * el detalle de abajo.
 *
 * Owner (2026-08-16): «que el upload tenga la verificacion arriba versus el
 * detalle abajo». En una propiedad nueva no hay contra que comparar: el archivo
 * entra, el P&L sale, cuadra consigo mismo y nadie se entera. Por eso la
 * comparacion se muestra SIEMPRE, cuadre o no.
 */
export interface VerificacionLinea {
  codigo: string; etiqueta: string; seccion: string; line_code: string;
  bloquea: boolean; archivo: number; detalle: number; dif: number; cuadra: boolean;
  meses_comparados: number[];
  meses_que_no_cuadran: { mes: number; archivo: number; detalle: number; dif: number }[];
  nota: string;
}

export interface VerificacionReporte {
  hay_verificacion: boolean;
  cuadra?: boolean;
  bloquea?: boolean;
  tolerancia?: number;
  meses_comparados?: number[];
  meses_no_comparados?: number[];
  motivo_meses_no_comparados?: string;
  lineas?: VerificacionLinea[];
  bloqueantes?: string[];
  avisos?: string[];
  motivo?: string;
}

/** Lo que contesta el backend con 409 cuando la verificacion no cuadra. */
export interface VerificacionBloqueada {
  error: string; que_hacer: string; texto: string;
  bloques: { label: string; verificacion: VerificacionReporte }[];
}

export class ErrorDeVerificacion extends Error {
  constructor(public informe: VerificacionBloqueada) {
    super(informe.error);
    this.name = "ErrorDeVerificacion";
  }
}

export interface ImportGLDetailResult {
  dry_run: boolean;
  blocks: {
    label: string; matched: string | null;
    opex_accounts: number; opex_total: number;
    cost_accounts: number; cost_total: number;
    payroll_total?: number; payroll_note?: string;
    unmapped_depts: string[];
    locked?: boolean;
    skipped_locked?: boolean;
    check_opex?: { pl_total_opex: number; gl_opex_plus_payroll: number; dif: number; ok: boolean; sin_snapshot: boolean };
    pl_preview?: { revenue: number; gop: number; ebitda: number; net: number; stat_months: number[] };
    verificacion?: VerificacionReporte;
  }[];
  /**
   * Forecasts «Current» cuyo corte se movió con esta subida.
   *
   * El corte decide qué meses del Forecast Working salen del Actual y cuáles
   * siguen siendo proyección. Se mueve solo, así que tiene que verse.
   */
  cut_advanced?: { scenario_id: string; version: string; actuals_through: number }[];
  /** El camino que se recorrió, dicho por el servidor y no supuesto acá. */
  mes_de_cierre?: number | null;
  /** Meses que traía el archivo y el cierre mensual NO escribió. */
  meses_descartados?: number[];
}

/**
 * @param mesDeCierre  Camino del CIERRE MENSUAL: escribe SOLO ese mes y descarta
 *   el resto del archivo. `undefined` = carga histórica (los 12 meses).
 *
 *   El tope vive en el BACKEND, no acá: una llamada directa por fuera de esta
 *   pantalla se topa con el mismo límite. Que el usuario elija bien no puede ser
 *   la protección.
 */
export async function importGLDetail(file: File, dryRun = false, merge = false, scenarioId?: string,
                                     confirmarDiferencias = false,
                                     mesDeCierre?: number): Promise<ImportGLDetailResult> {
  const form = new FormData();
  form.append("file", file);
  const sid = scenarioId ? `&scenario_id=${encodeURIComponent(scenarioId)}` : "";
  const mes = mesDeCierre ? `&mes_de_cierre=${mesDeCierre}` : "";
  const res = await fetch(`${BASE}/scenarios/import-gl-detail/?dry_run=${dryRun}&merge=${merge}${sid}&confirmar_diferencias=${confirmarDiferencias}${mes}`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    // 409 = la verificacion de arriba no cuadra con el detalle. No es un error
    // tecnico: es el informe que el owner tiene que ver antes de decidir. Se
    // devuelve tipado para poder mostrarlo, en vez de un texto crudo.
    if (res.status === 409) {
      try {
        const j = JSON.parse(text);
        if (j?.detail?.bloques) throw new ErrorDeVerificacion(j.detail as VerificacionBloqueada);
      } catch (e) { if (e instanceof ErrorDeVerificacion) throw e; }
    }
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export async function bulkCreateStandardVersions(year = 2027, hotelId = HOTEL_ID): Promise<{ created: string[]; created_count: number; skipped_count: number; year: number }> {
  return api.post(`/scenarios/bulk-create-standard/`, { year, hotel_id: hotelId });
}

// Borra una versión (solo escenarios en draft; permanente).
export async function deleteScenario(scenarioId: string): Promise<void> {
  await api.delete<void>(`/scenarios/${scenarioId}/`);
}

// Renombra la versión (bloquea duplicados del mismo tipo+año).
export async function renameScenario(scenarioId: string, version: string): Promise<Scenario> {
  return api.patch<Scenario>(`/scenarios/${scenarioId}/version/`, { version });
}

// Asegura que exista 'Budget Working {año}' para cada año del rango (idempotente).
export async function ensureWorkingBudgets(fromYear = 2027, toYear = 2035, hotelId = HOTEL_ID): Promise<{ created: string[]; created_count: number }> {
  return api.post(`/scenarios/ensure-working/`, { hotel_id: hotelId, from_year: fromYear, to_year: toYear });
}

// Descarga de la plantilla de Detalle de una versión (month=0 → año completo).
export function exportDetailUrl(scenarioId: string, month = 0): string {
  const t = getToken();
  const q = `month=${month}` + (t ? `&token=${encodeURIComponent(t)}` : "");
  return `${BASE}/scenarios/${scenarioId}/export-detail/?${q}`;
}

export interface ImportAllResult {
  dry_run: boolean;
  merge: boolean;
  pl: ImportPLSnapshotResult;
  gl: ImportGLDetailResult;
}

/** @param merge  `true` (default) = alcance del MES, igual que el backend. */
export async function importAll(file: File, merge = true, dryRun = false): Promise<ImportAllResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/scenarios/import-all/?merge=${merge}&dry_run=${dryRun}`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Control & Auditoría (trazabilidad cuenta → línea del P&L) ────────────────
export interface TraceRow {
  origin: string; dept_code: string; dept_name: string; grupo: string;
  account_code: string; account_name: string; amount: number;
  line_code: string | null; line_name: string; section: string;
  mode: "exact" | "dept-agnostic" | "FALLBACK" | "DROP";
  rollup: string; fallback_from: string;
}
export interface TraceLine {
  line_code: string; line_name: string; section: string;
  amount_sources: number; amount_pl: number; dif: number; ok: boolean;
  rows: number; depts: string[];
}
export interface AuditAviso {
  tipo: string; titulo: string; detalle: string;
  monto_depto_reparto?: number; monto_concepto_6025?: number;
}
export interface AuditTrace {
  avisos: AuditAviso[];
  scenario: string; source_mode: string; month: number;
  totales: {
    filas_fuente: number; monto_fuente: number; monto_perdido_DROP: number;
    filas_DROP: number; filas_FALLBACK: number; filas_dept_agnostic: number;
    filas_exact: number;
  };
  pl_control: Record<string, number>;
  by_line: TraceLine[];
  rows: TraceRow[];
  problems: { DROP: TraceRow[]; FALLBACK: TraceRow[]; "dept-agnostic": TraceRow[] };
}
export async function getAuditTrace(scenarioId: string, month = 0): Promise<AuditTrace> {
  return api.get<AuditTrace>(`/audit/scenario/${scenarioId}/trace/?month=${month}`);
}

export interface MappingHealth {
  reglas_activas: number; reglas_sin_dept_code: number; riesgo_misruteo: boolean;
  cuentas_multi_linea: number; cuentas_multi_linea_detalle: Record<string, string[]>;
  pares_ambiguos: { dept_code: string; account_code: string; lineas: string[] }[];
  pares_ambiguos_total: number; mapeos_a_linea_inexistente: string[]; veredicto: string;
}
export async function getMappingHealth(): Promise<MappingHealth> {
  return api.get<MappingHealth>(`/audit/mapping/health/`);
}

export interface PushRevenueResult {
  dry_run: boolean; scenario_id: string;
  total_antes: number; total_despues: number;
  /** Noches ocupadas: viajan con la plata, si no la ocupación se queda atrás. */
  noches_antes?: number; noches_despues?: number;
  lineas: { linea: string; antes: number; despues: number; dif: number }[];
}
/** Pasa el ingreso calculado (tarifas × ocupación × canales) al checkbook de ingresos,
 *  que es de donde el P&L lo toma. dryRun muestra el antes/después sin escribir. */
export async function pushRevenueToCheckbook(scenarioId: string, dryRun = false): Promise<PushRevenueResult> {
  return api.post<PushRevenueResult>(
    `/scenarios/${scenarioId}/revenue/push-to-checkbook/?dry_run=${dryRun}`, {});
}

export function uploadTemplateUrl(): string {
  const t = getToken();
  return `${BASE}/audit/upload-template/${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}

export interface ValidateUploadResult {
  archivo: string; filas: number; filas_ok: number; filas_con_problema: number;
  monto_que_llega: number; monto_que_se_perderia: number; veredicto: string;
  detalle: {
    fila: number; dept_code: string; dept_name: string; account_code: string;
    account_name: string; monto: number; line_code: string | null; line_name: string;
    section: string; mode: string; fallback_from: string; ok: boolean;
  }[];
}
export async function validateUpload(file: File): Promise<ValidateUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/audit/validate-upload/`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Excel export/import helpers (all checkbooks) ──────────────────────────────

export function nonopExcelUrl(scenarioId: string): string {
  return dlUrl(`/nonop/${scenarioId}/export/excel/`);
}
export async function importNonopExcel(scenarioId: string, file: File): Promise<{ imported: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/nonop/${scenarioId}/import/excel/`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export function costsExcelUrl(scenarioId: string): string {
  return dlUrl(`/costs/${scenarioId}/export/excel/`);
}
export async function importCostsExcel(scenarioId: string, file: File): Promise<{ imported: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/costs/${scenarioId}/import/excel/`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export function payrollExcelUrl(scenarioId: string): string {
  return dlUrl(`/payroll/${scenarioId}/export/excel/`);
}
export async function importPayrollExcel(scenarioId: string, file: File): Promise<{ imported: number; note?: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/payroll/${scenarioId}/import/excel/`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export function statsExcelUrl(scenarioId: string): string {
  return dlUrl(`/scenarios/${scenarioId}/stats/export/excel/`);
}
export async function importStatsExcel(scenarioId: string, file: File): Promise<{ imported: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/stats/import/excel/`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function addOpexLines(
  scenarioId: string,
  deptCode: string,
  accountCode: string,
  accountName: string,
  count = 10,
): Promise<{ added: number }> {
  return api.post(`/opex/${scenarioId}/dept/${deptCode}/add-lines/`, {
    account_code: accountCode,
    account_name: accountName,
    count,
  });
}

// ── Below-GOP / Owner (non-operating) mini checkbooks ─────────────────────────
// 8xxx accounts (rent, insurance, capex, financial, depreciation, other) broken
// into named detail lines. Mgmt fees and income tax are NOT here — they are
// computed drivers in the P&L engine.

export interface NonOpEntry {
  id: string;
  report_line_code: string;
  account_code: string;
  account_name: string;
  detail_code: string;
  detail_desc: string;
  jan: string; feb: string; mar: string; apr: string; may: string; jun: string;
  jul: string; aug: string; sep: string; oct: string; nov: string; dec: string;
  annual: string;
}

export interface NonOpLineGroup {
  report_line_code: string;
  account_code: string;
  lines: NonOpEntry[];
  monthly_totals: Record<string, string>;
  annual_total: string;
}

export interface NonOpBulkRow {
  report_line_code: string;
  account_code: string;
  account_name: string;
  detail_code: string;
  detail_desc: string;
  jan: number; feb: number; mar: number; apr: number; may: number; jun: number;
  jul: number; aug: number; sep: number; oct: number; nov: number; dec: number;
}

export async function getNonOp(scenarioId: string): Promise<{ lines: NonOpLineGroup[] }> {
  return api.get<{ lines: NonOpLineGroup[] }>(`/nonop/${scenarioId}/`);
}

export async function bulkReplaceNonOp(
  scenarioId: string,
  rows: NonOpBulkRow[],
): Promise<{ imported: number }> {
  return api.put<{ imported: number }>(`/nonop/${scenarioId}/bulk/`, rows);
}

// ── Allocations ───────────────────────────────────────────────────────────────

export interface CafeteriaConfigRow {
  dept_code: string;
  dept_name: string;
  participates: boolean;
  notes: string;
}

export interface LaundryConfigRow {
  dept_code: string;
  dept_name: string;
  kilos_historicos: number;
  kilos_monthly: number[];   // 12 valores Ene..Dic
  participates: boolean;
  notes: string;
}

export interface AllocationRow {
  id: string;
  allocation_type: "CAFETERIA" | "LAUNDRY";
  source_dept: string;
  target_dept: string;
  amount_usd: number;
  basis_value: number;
  basis_type: string;
  account?: string;
}

export interface LaundryParams {
  kilos_uniformes: number;
  kilos_huespedes: number;
  uniformes_monthly: number[];   // 12 valores Ene..Dic
  huespedes_monthly: number[];   // 12 valores Ene..Dic
  account_linen: string;
  account_uniform: string;
  account_servicios: string;
}

export interface LaundryBreakdown {
  accounts: { linen: string; uniform: string; servicios: string };
  /** codigo -> nombre, para que el asiento se lea como asiento. */
  account_names?: Record<string, string>;
  linen: Record<string, number[]>;   // dept → [m1..m12]  (account 7310, by kilos)
  uniform: Record<string, number[]>; // dept → [m1..m12]  (account 7685, by FTE)
  credit: number[];                  // 0161 credit (account 4999, negative)
  guest_cogs: number[];              // stays in 0161 (account 5301)
  total_cost: number[];              // 0161 source cost
}

export interface AllocationSummary {
  CAFETERIA: Record<string, number[]>; // dept → [m1..m12]
  LAUNDRY: Record<string, number[]>;
}

export interface CalculateResult {
  ok: boolean;
  total_entries: number;
  monthly: {
    cafeteria: { month: number; total_cost: number; rows: number; nets_zero: boolean }[];
    laundry: {
      month: number; total_cost: number; rows: number; nets_zero: boolean;
      linen_cost?: number; uniform_cost?: number; guest_cost?: number;
    }[];
  };
}

export async function getCafeteriaConfig(scenarioId: string): Promise<CafeteriaConfigRow[]> {
  return api.get<CafeteriaConfigRow[]>(`/allocations/cafeteria/${scenarioId}/config/`);
}

// ── Salary Allocation ──────────────────────────────────────────────────────
export interface SalaryDept { dept_code: string; dept_name: string; fte: number[]; }
export interface SalaryPosition { dept_code: string; dept_name: string; position_code: string; position_name: string; sw: number[]; }
export interface SalaryRule {
  source_dept: string; position_code: string; position_name: string;
  portion_pct: number; cafeteria_pct: number; salary_override?: number[]; dummy_monthly?: number[]; target_depts: string[]; account: string; active: boolean;
}
export interface SalaryCalcRule {
  source_dept: string; position_code: string; position_name: string; portion_pct: number; cafeteria_pct: number;
  dummy: number[]; targets: string[];
  concepts: { sw: number[]; ccss: number[]; aguinaldo: number[]; cafeteria: number[]; loaded: number[]; reassigned: number[] };
  dist: Record<string, number[]>;
  totals: Record<string, number>; nets_zero: boolean;
}
export async function getSalaryCalc(scenarioId: string): Promise<{ rules: SalaryCalcRule[] }> {
  return api.get(`/allocations/salary/${scenarioId}/calc/`);
}
export interface SalaryPreviewRule {
  source_dept: string; position_code: string; position_name: string;
  portion_pct: number; cafeteria_pct: number;
  breakdown: { sw: number; ccss: number; aguinaldo: number; cafeteria: number; total: number };
  movements: { dept: string; amount: number; type: string }[]; nets_zero: boolean;
}
export async function getSalaryPositions(scenarioId: string): Promise<{ depts: SalaryDept[]; positions: SalaryPosition[]; ccss_rate: number; aguinaldo_divisor: number }> {
  return api.get(`/allocations/salary/${scenarioId}/positions/`);
}
export async function getSalaryConfig(scenarioId: string): Promise<SalaryRule[]> {
  return api.get<SalaryRule[]>(`/allocations/salary/${scenarioId}/config/`);
}
export async function saveSalaryConfig(scenarioId: string, rows: SalaryRule[]): Promise<{ ok: boolean; rules: number }> {
  return api.put(`/allocations/salary/${scenarioId}/config/`, rows);
}
export async function getSalaryPreview(scenarioId: string, month: number): Promise<{ month: number; rules: SalaryPreviewRule[] }> {
  return api.get(`/allocations/salary/${scenarioId}/preview/?month=${month}`);
}

// ── Reparto de Rooms a sus sets (Villas / Residencias) ─────────────────────
export interface RoomsAllocRow {
  dept_code: string;
  dept_name: string;
  pct_monthly: number[];      // 12 fracciones (0.30 = 30%)
  active: boolean;
  monto_mensual: number[];
}
export interface RoomsAllocConfig {
  scenario_id: string;
  source_dept: string;
  source_name: string;
  rows: RoomsAllocRow[];
  base_mensual: number[];
  fte_mensual: number[];
  resto_rooms: number[];
  meses_pasados_de_100: number[];
}
export async function getRoomsAllocConfig(scenarioId: string): Promise<RoomsAllocConfig> {
  return api.get<RoomsAllocConfig>(`/allocations/rooms/${scenarioId}/config/`);
}
export async function saveRoomsAllocConfig(
  scenarioId: string,
  rows: { dept_code: string; pct_monthly: number[]; active: boolean }[],
): Promise<{ ok: boolean; rows: number }> {
  return api.put(`/allocations/rooms/${scenarioId}/config/`, rows);
}

export interface RoomsSetRow {
  key: string;
  dept_code: string;
  name: string;
  es_residuo: boolean;
  unidades: number;
  categorias: { code: string; name: string; units: number }[];
  payroll: number[]; opex: number[]; cos: number[];
  distribucion: number[];     // crédito 4999: lo que Rooms entregó (negativo)
  costo: number[];
  recibido_por_reparto: number[];
  revenue: number[]; fte: number[];
  noches_disponibles: number[]; noches_ocupadas: number[];
  costo_anual: number; revenue_anual: number;
}
export interface RoomsSetsReport {
  scenario_id: string; year: number; source_dept: string;
  rows: RoomsSetRow[];
  consolidado: {
    costo: number[]; revenue: number[]; unidades: number;
    costo_anual: number; revenue_anual: number;
  };
  asiento_neto: number; cuadra: boolean; hay_reparto: boolean;
}
export async function getRoomsSetsReport(scenarioId: string): Promise<RoomsSetsReport> {
  return api.get<RoomsSetsReport>(`/reports/rooms-sets/${scenarioId}/`);
}

// ── P&L Full Detail (Fase 2) ──────────────────────────────────────────────────
// El P&L abierto CUENTA POR CUENTA, en la forma del Excel de Amarena. Convive
// con /reports/pl-full y /reports/pl-by-dept; no los reemplaza.
export interface PLDetalleFila {
  /** `stat` = estadística (noches, unidades): número pelado, sin `$`. */
  tipo: "seccion" | "detalle" | "subtotal" | "total" | "pct" | "stat";
  nivel: number;
  cuenta: string;
  etiqueta: string;
  clave: string;
  meses: number[];
  total: number;
  seccion?: string;
  line_code?: string;
}
export interface PLDetalleBloque {
  clave: string; dept_code: string; titulo: string; titulo_en: string;
  tipo: "OPERATIVO" | "OVERHEAD";
  /** Los tres sets de Rooms: son el consolidado ABIERTO, no departamentos
   *  aparte. No se suman a ningún total — sumarlos contaría Rooms dos veces. */
  es_apertura?: boolean;
  apertura_de?: string;
  /** Presente en el consolidado cuando su apertura no da lo mismo que él. */
  apertura_no_cuadra?: { dif_ingresos: number; dif_gastos: number };
  apertura_no_aplica?: boolean;
  ingreso_anual: number; gasto_anual: number; utilidad_anual: number;
  filas: PLDetalleFila[];
}
export interface PLDetalleSet {
  clave: string; nombre: string; unidades: number;
  noches_disponibles: number[]; noches_ocupadas: number[];
  revenue: number[]; costo?: number[];
  ocupacion: number[]; adr: number[]; revpar: number[];
  ocupacion_anual: number; adr_anual: number; revpar_anual: number;
  revenue_anual: number; costo_anual?: number;
  sin_ocupacion?: boolean;
}
export interface PLFullDetail {
  scenario_id: string; scenario: string; year: number;
  source_mode: string; moneda: string;
  avisos: string[];
  kpis: { sets: PLDetalleSet[]; consolidado: PLDetalleSet | null;
          disponible: boolean; diluyen?: string[] };
  club: { filas: ClubMembershipFila[]; hay_datos: boolean; total_es_cierre: boolean } | null;
  resumen: PLDetalleFila[];
  bloques: PLDetalleBloque[];
  propiedad: PLDetalleFila[];
  cuadre: {
    ingresos_detalle: number; ingresos_pl: number; dif_ingresos: number;
    gastos_detalle: number; gastos_pl: number; dif_gastos: number;
    gop_pl: number; net_pl: number;
    ingreso_por_cuenta: boolean; ok: boolean;
  };
}
// ── Socios del Club Madresal (estadístico, no plata) ──────────────────────────
// El Club vende ACCESO a las instalaciones; el desarrollo inmobiliario de atrás
// no es parte de este P&L. La cuota ya está en REV_CLUB — esto explica de dónde
// sale. El campo `visible` viene de la matriz de provisionamiento del depto
// 260: el día que el Club se opere por fuera, se desmarca ahí y esto se apaga
// solo, sin tocar código.
export interface ClubMembershipFila {
  campo: string; etiqueta: string; meses: number[]; total_anio: number;
}
export interface ClubMembership {
  scenario_id: string; year: number; visible: boolean;
  filas: ClubMembershipFila[]; nota_total: string;
}
export async function getClubMembership(scenarioId: string): Promise<ClubMembership> {
  return api.get<ClubMembership>(`/scenarios/${scenarioId}/club-membership/`);
}

// ── Cuadre Resumen vs Detalle — A0.-2 ──────────────────────────────────────────
// El validador ya existe (`GET /reports/cuadre/{id}/`); esto solo tipa la
// respuesta para poder mostrar el veredicto al lado de un selector de
// escenario, sin recalcularlo en el front.
export interface VeredictoCuadre {
  manda: "detalle" | "resumen";
  motivo: string;
  meses_evaluados: number[];
  meses_con_detalle: number[];
  actuals_through: number;
  tolerancia: number;
  totales_clave: string[];
  diferencias: { total: string; resumen: number; detalle: number; diferencia: number }[];
}
export interface Cuadre {
  scenario: { id: string; type: string; version: string; year: number; status: string };
  hay_resumen: boolean;
  hay_detalle: boolean;
  meses_con_detalle: number;
  comparable: boolean;
  filas: { line_code: string; line_name: string; resumen: number; detalle: number;
           diferencia: number; cuadra: boolean }[];
  descuadres: number;
  neto_resumen: number;
  neto_detalle: number;
  neto_diferencia: number;
  manda: "detalle" | "resumen";
  veredicto: VeredictoCuadre;
}
export async function getCuadre(scenarioId: string): Promise<Cuadre> {
  return api.get<Cuadre>(`/reports/cuadre/${scenarioId}/`);
}
export async function saveClubMembership(
  scenarioId: string,
  meses: { month: number; total: number; condicionados: number; pagando: number; acuerdo_pago: number }[],
): Promise<ClubMembership> {
  return api.put<ClubMembership>(`/scenarios/${scenarioId}/club-membership/`, { meses });
}

// El DRIVER de la cuota del Club: socios x precio -> linea CLUB del checkbook.
// Misma forma que el Spa. Hasta ahora el checkbook no tenia linea de Club, por
// eso REV_CLUB daba cero en los escenarios armados dentro de la app.
export interface ClubFeeFila {
  month: number; socios: number; precio: number;
  /** Las tres fuentes por separado: la cuota (4500, del driver), la actividad de
   *  fin de año (4501) y los visitantes (4502). `ingreso` es la suma. */
  cuotas: number; actividad: number; visitantes: number; ingreso: number;
}
/** Una línea del Club con su cuenta y su nombre, como los lleva el catálogo.
 *  Vienen del backend para que la pantalla no se invente rótulos. */
export interface ClubFeeLinea {
  linea: string; cuenta: string; dept: string; nombre: string;
}
export interface ClubFee {
  scenario_id: string; year: number; visible: boolean;
  /** `false` = el escenario arma sus ingresos con drivers y no lee el checkbook,
   *  así que lo que se guarde acá no va a llegar al P&L. */
  llega_al_pl: boolean; modo_ingresos: string;
  base: string; bases: string[]; etiquetas_base: Record<string, string>;
  filas: ClubFeeFila[]; lineas: ClubFeeLinea[];
  total: number; totales: Record<string, number>; nota: string;
}
/** Abre en CERO las cuentas que el catálogo le da a un departamento, para poder
 *  empezar a presupuestarlo. No mueve el P&L y no pisa lo que ya existe. */
export interface CuentasSembradas {
  dept_code: string; creadas: number; nota: string;
  detalle: { clase: string; nombre: string; en_el_catalogo: number;
             ya_estaban: number; nuevas: number }[];
}
export async function sembrarCuentas(
  scenarioId: string, deptCode: string, clases?: string[],
): Promise<CuentasSembradas> {
  return api.post<CuentasSembradas>(`/scenarios/${scenarioId}/sembrar-cuentas/`,
    { dept_code: deptCode, ...(clases ? { clases } : {}) });
}

export async function getClubFee(scenarioId: string): Promise<ClubFee> {
  return api.get<ClubFee>(`/scenarios/${scenarioId}/club-fee/`);
}
export async function saveClubFee(
  scenarioId: string, base: string,
  meses: { month: number; precio: number; actividad: number; visitantes: number }[],
): Promise<ClubFee> {
  return api.put<ClubFee>(`/scenarios/${scenarioId}/club-fee/`, { base, meses });
}

export async function getPLFullDetail(
  scenarioId: string, incluirVacios = false,
): Promise<PLFullDetail> {
  return api.get<PLFullDetail>(
    `/reports/pl-full-detail/${scenarioId}/?incluir_vacios=${incluirVacios}`);
}
/** El mismo reporte en .xlsx. El token va por query: un <a href> no manda headers.
 *  `dlUrl` solo agrega el `?` cuando hay token, así que el separador se decide acá. */
export function plFullDetailExcelUrl(scenarioId: string, incluirVacios = false): string {
  const base = dlUrl(`/reports/pl-full-detail/${scenarioId}/export/`);
  return `${base}${base.includes("?") ? "&" : "?"}incluir_vacios=${incluirVacios}`;
}

export async function saveCafeteriaConfig(
  scenarioId: string,
  rows: CafeteriaConfigRow[],
): Promise<{ ok: boolean }> {
  return api.put<{ ok: boolean }>(`/allocations/cafeteria/${scenarioId}/config/`, rows);
}

export async function getLaundryConfig(scenarioId: string): Promise<LaundryConfigRow[]> {
  return api.get<LaundryConfigRow[]>(`/allocations/laundry/${scenarioId}/config/`);
}

export async function saveLaundryConfig(
  scenarioId: string,
  rows: LaundryConfigRow[],
): Promise<{ ok: boolean }> {
  return api.put<{ ok: boolean }>(`/allocations/laundry/${scenarioId}/config/`, rows);
}

export async function getLaundryParams(scenarioId: string): Promise<LaundryParams> {
  return api.get<LaundryParams>(`/allocations/laundry/${scenarioId}/params/`);
}

export async function saveLaundryParams(
  scenarioId: string,
  body: LaundryParams,
): Promise<{ ok: boolean }> {
  return api.put<{ ok: boolean }>(`/allocations/laundry/${scenarioId}/params/`, body);
}

export async function getLaundryBreakdown(scenarioId: string): Promise<LaundryBreakdown> {
  return api.get<LaundryBreakdown>(`/allocations/${scenarioId}/laundry-breakdown/`);
}

export async function calculateAllocations(scenarioId: string): Promise<CalculateResult> {
  return api.post<CalculateResult>(`/allocations/${scenarioId}/calculate/`);
}

export async function initAllocationConfig(scenarioId: string): Promise<{ ok: boolean; cafeteria_added: number; laundry_added: number }> {
  return api.post(`/allocations/${scenarioId}/init-config/`);
}

export async function getAllocationSummary(scenarioId: string): Promise<AllocationSummary> {
  return api.get<AllocationSummary>(`/allocations/${scenarioId}/summary/`);
}

// ── P&L helpers (Fase 8) ──────────────────────────────────────────────────────

export interface PLLine {
  line_code: string;
  line_name: string;
  section: string;
  dept_code: string;
  amount_usd: number;
  is_calculated: boolean;
  par?: number;   // Per Available Room (USALI)
  por?: number;   // Per Occupied Room (USALI)
}

export interface PLKpis {
  rooms_available: number;
  rooms_occupied: number;
  guests: number;
  occupancy_pct: number;
  adr: number;
  revpar: number;
}

export interface PLMonth {
  month: number;
  kpis: PLKpis;
  lines: PLLine[];
}

export interface PLMonthly {
  scenario_id: string;
  year: number;
  months: PLMonth[];
  annual: Record<string, number>;
  annual_kpis?: PLKpis;
}

// ─── Multi-version compare (A4) ───────────────────────────────────────────────
export interface PLColumn {
  kpis: PLKpis;
  lines: PLLine[];
}

export interface PLCompareVersion {
  scenario_id: string;
  label: string;
  type: string;
  year: number;
  version: string;
  month: PLColumn;   // single month
  ytd: PLColumn;     // jan..month
  full: PLColumn;    // 12 months
}

export interface PLCompare {
  month: number;
  versions: PLCompareVersion[];
}

export interface PLManualInput {
  month: number;
  rent: string;
  mgmt_fee_pct_3: string;
  mgmt_fee_pct_5: string;
  properties_insurance: string;
  capital_reserve: string;
  capital_reserve_pct: string;
  large_capex: string;
  bank_interest: string;
  depreciation: string;
  income_tax_rate: string;
}

export interface RecalcResult {
  scenario_id: string;
  payroll_entries_updated: number;
  allocation_entries: number;
  pl_lines: number;
  status: string;
}

export async function getPLMonth(scenarioId: string, month: number) {
  return api.get<{ scenario_id: string; month: number; year: number; kpis: PLKpis; lines: PLLine[] }>(
    `/pl/${scenarioId}/month/${month}/`,
  );
}

export async function getPLMonthly(scenarioId: string): Promise<PLMonthly> {
  return api.get<PLMonthly>(`/pl/${scenarioId}/monthly/`);
}

// ── Budget Big Picture ────────────────────────────────────────────────────────
export interface BPGroupBlock { group: string; name: string; revenue: number; payroll: number; opex: number; cost: number; }
export interface BigPictureBreakdown { scenario_id: string; operating: BPGroupBlock[]; overhead: BPGroupBlock[]; }
export async function getBigPictureBreakdown(scenarioId: string): Promise<BigPictureBreakdown> {
  return api.get<BigPictureBreakdown>(`/scenarios/${scenarioId}/big-picture-breakdown/`);
}
export interface BPVersionMeta { id: string; name: string; base_scenario_id: string | null; target_year: number; updated_at: string | null; }
export interface BPVersion { id: string; name: string; base_scenario_id: string | null; target_year: number; growth: Record<string, number>; }
export async function listBigPictureVersions(hotelId = HOTEL_ID): Promise<BPVersionMeta[]> {
  return api.get<BPVersionMeta[]>(`/big-picture-versions/?hotel_id=${hotelId}`);
}
export async function getBigPictureVersion(id: string): Promise<BPVersion> {
  return api.get<BPVersion>(`/big-picture-versions/${id}/`);
}
export interface ApplyBPResult { dry_run: boolean; target: string; preview: { revenue: number; gop: number; ebitda: number; net: number }; }
export async function applyBigPicture(targetId: string, body: { base_scenario_id: string; groups: Record<string, { revenue: number; payroll: number; opex: number; cost: number }>; belowgop_total: number; stats: { rooms_available: number; rooms_occupied: number; guests: number } }, dryRun = false): Promise<ApplyBPResult> {
  return api.post<ApplyBPResult>(`/scenarios/${targetId}/apply-big-picture/?dry_run=${dryRun}`, body);
}

export async function saveBigPictureVersion(body: { id?: string; name: string; base_scenario_id?: string | null; target_year?: number; growth: Record<string, number> }): Promise<{ id: string; name: string }> {
  return api.post<{ id: string; name: string }>(`/big-picture-versions/`, body);
}
export async function deleteBigPictureVersion(id: string): Promise<{ ok: boolean }> {
  return api.delete<{ ok: boolean }>(`/big-picture-versions/${id}/`);
}

export interface PLCompareRangeVersion {
  scenario_id: string; label: string; type: string; year: number; version: string;
  range: PLColumn;
}
export interface PLCompareRange {
  from_month: number; to_month: number; versions: PLCompareRangeVersion[];
}
export async function getPLCompareRange(scenarioIds: string[], fromMonth: number, toMonth: number): Promise<PLCompareRange> {
  const ids = scenarioIds.join(",");
  return api.get<PLCompareRange>(`/pl/compare-range/?scenarios=${encodeURIComponent(ids)}&from_month=${fromMonth}&to_month=${toMonth}`);
}

export async function getPLCompare(scenarioIds: string[], month = 12): Promise<PLCompare> {
  const ids = scenarioIds.filter(Boolean).join(",");
  return api.get<PLCompare>(`/pl/compare/?scenarios=${encodeURIComponent(ids)}&month=${month}`);
}

// ─── Revenue por tipo de habitación (A3) ──────────────────────────────────────
export interface RoomTypeRow {
  room_type_id: string;
  room_type_code?: string;
  room_type_name: string;
  units: number;
  nights_available: number;
  nights_occupied: number;
  occupancy_pct: number;
  revenue: number;
  adr: number;
  pax: number;
  pct_of_total?: number;
}
export interface RevenueByRoomType {
  scenario_id: string;
  year: number;
  room_types: { id: string; code?: string; name: string; units: number }[];
  months: { month: number; rows: RoomTypeRow[] }[];
  annual: RoomTypeRow[];
}

// Etiqueta unificada de room type en TODA la app: "CÓDIGO · Nombre" (código fijo).
export const rtLabel = (code: string | undefined | null, name: string | undefined | null): string =>
  code ? `${code} · ${name ?? ""}` : (name ?? "");
export async function getRevenueByRoomType(scenarioId: string): Promise<RevenueByRoomType> {
  return api.get<RevenueByRoomType>(`/scenarios/${scenarioId}/revenue/by-room-type/`);
}

export interface ImportRoomStatsResult {
  dry_run: boolean; imported?: boolean; scenario: string;
  months_present: number[]; room_types: string[]; rows: number;
  total_revenue: number; total_nights_occupied: number;
}
export interface OtbMonth {
  month: number; total_revenue: number; rooms_revenue: number; rooms_available: number;
  rooms_occupied: number; guests: number; adr: number; occupancy_pct: number;
}
export interface OnTheBooks { scenario_id: string; year: number; week: number; has_data: boolean; months: OtbMonth[]; }
export async function getOnTheBooks(scenarioId: string, week: number, year?: number): Promise<OnTheBooks> {
  return api.get<OnTheBooks>(`/scenarios/${scenarioId}/onthebooks/?week=${week}${year != null ? `&year=${year}` : ""}`);
}
export async function getOtbYears(scenarioId: string, week?: number): Promise<{ scenario_id: string; years: number[] }> {
  return api.get(`/scenarios/${scenarioId}/otb-years/${week != null ? `?week=${week}` : ""}`);
}
/** Baja la plantilla EDITABLE del country mix (la grilla cruda, re-subible).
 *  Distinta del «⬇ Excel», que es un reporte con variance y no vuelve. */
export function urlPlantillaCountry(scenarioId: string): string {
  return `${BASE}/scenarios/${scenarioId}/country-mix/plantilla.xlsx`;
}

/** Sube la plantilla corregida. Sin `confirmar`, solo REVISA y no guarda. */
export async function subirPlantillaCountry(scenarioId: string, archivo: File, confirmar: boolean): Promise<{
  guardado: boolean; filas: number; celdas?: number; total_cambios: number;
  cambios: { pais: string; metric: string; antes: number | null; ahora: number | null }[];
}> {
  const form = new FormData();
  form.append("file", archivo);
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/country-mix/plantilla/?confirmar=${confirmar}`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

/** Sube el `res_statistics1` de Opera: país de origen por mes, noches y pax.
 *  Devuelve qué países cayeron en «Others» y con cuánto, para poder decidir a
 *  quién promover a la lista con criterio y no de memoria. */
export interface CountryXmlOk {
  imported: boolean; year: number; anios_en_el_archivo: number[]; meses: number[];
  month?: number; meses_ya_cargados: number[]; meses_sobrescritos_a_mano: number[];
  paises: number; lista_inferida: boolean; filas: number;
  total_noches: number; total_pax: number;
  en_others: { pais: string; noches: number; pax: number }[];
}

/** El backend frenó porque esos meses ya se corrigieron a mano. No es un error:
 *  es una decisión que le toca a quien sube. Se distingue del resto de fallos
 *  para poder ofrecer «sobrescribir» en vez de mostrar un `API 409:` crudo. */
export class CountryXmlPisaria extends Error {
  constructor(public meses: number[], mensaje: string) { super(mensaje); this.name = "CountryXmlPisaria"; }
}

/** El archivo trae varios meses y se sube uno por vez: hay que elegir cuál.
 *  Tampoco es un error — es la pregunta que falta. */
export class CountryXmlElegirMes extends Error {
  constructor(public meses: number[], public year: number, mensaje: string) {
    super(mensaje); this.name = "CountryXmlElegirMes";
  }
}

export async function importCountryXml(
  scenarioId: string, archivo: File,
  opts?: { year?: number; month?: number; sobrescribir?: boolean },
): Promise<CountryXmlOk> {
  const form = new FormData();
  form.append("file", archivo);
  const q = new URLSearchParams();
  if (opts?.year != null) q.set("year", String(opts.year));
  if (opts?.month != null) q.set("month", String(opts.month));
  if (opts?.sobrescribir) q.set("sobrescribir", "true");
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/import-country-xml/${q.toString() ? `?${q}` : ""}`,
    { method: "POST", body: form, headers: authHeaders() });
  if (res.status === 409) {
    const d = await res.json().catch(() => null);
    const det = d?.detail;
    if (det?.motivo === "meses_corregidos_a_mano") throw new CountryXmlPisaria(det.meses ?? [], det.mensaje ?? "");
    if (det?.motivo === "elegir_mes") throw new CountryXmlElegirMes(det.meses_disponibles ?? [], det.year, det.mensaje ?? "");
  }
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

export async function importOtbXml(scenarioId: string, week: number, fullRevenue: File, onlyRooms?: File): Promise<{ imported: boolean; week: number; years: number[]; days: number; daily_cells: number; months: number; dias_en_ambos_bloques: number; por_anio: { year: number; revenue: number; noches: number; meses: number }[] }> {
  const form = new FormData();
  form.append("full_revenue", fullRevenue);
  if (onlyRooms) form.append("only_rooms", onlyRooms);
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/import-otb-xml/?week=${week}`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

export interface OtbEntryRow { month: number; total_revenue: number; rooms_revenue: number; rooms_occupied: number; guests: number; }
export async function getOtbEntry(scenarioId: string, week: number, year?: number): Promise<{ scenario_id: string; week: number; year: number; rows: OtbEntryRow[] }> {
  return api.get(`/scenarios/${scenarioId}/onthebooks-entry/?week=${week}${year != null ? `&year=${year}` : ""}`);
}
export async function saveOtbEntry(scenarioId: string, week: number, rows: OtbEntryRow[], year?: number): Promise<{ saved: boolean; rows_saved: number }> {
  return api.put(`/scenarios/${scenarioId}/onthebooks-entry/?week=${week}${year != null ? `&year=${year}` : ""}`, { rows });
}
export async function getOtbWeeks(scenarioId: string): Promise<{ scenario_id: string; weeks: number[] }> {
  return api.get(`/scenarios/${scenarioId}/otb-weeks/`);
}
export async function clearOtb(scenarioId: string, week?: number): Promise<{ cleared: boolean; week: number | null; months_deleted: number; daily_deleted: number }> {
  return api.delete(`/scenarios/${scenarioId}/otb/${week != null ? `?week=${week}` : ""}`);
}
export async function getOtbParams(scenarioId: string): Promise<{ scenario_id: string; default: number; by_week: Record<string, number> }> {
  return api.get(`/scenarios/${scenarioId}/otb-params/`);
}
export async function saveOtbParam(scenarioId: string, week: number, onPropPct: number): Promise<{ week: number; on_prop_pct: number }> {
  return api.put(`/scenarios/${scenarioId}/otb-params/?week=${week}`, { on_prop_pct: onPropPct });
}

export interface OtbPacingSnapshot { week: number; total_revenue: number; rooms_occupied: number; delta_vs_prev: number | null; }
export interface OtbPacing { scenario_id: string; year: number; rooms_available: number; snapshots: OtbPacingSnapshot[]; }
export async function getOtbPacing(scenarioId: string, year?: number): Promise<OtbPacing> {
  return api.get<OtbPacing>(`/scenarios/${scenarioId}/otb-pacing/${year != null ? `?year=${year}` : ""}`);
}

export interface DailyOccDay { day: number; rooms_sold: number; occ_pct: number; }
export interface DailyOccMonth { month: number; ndays: number; avg_occ: number; days: (DailyOccDay | null)[]; }
export interface DailyOcc { scenario_id: string; year: number; week: number; inventory: number; has_data: boolean; months: DailyOccMonth[]; }
export async function getDailyOcc(scenarioId: string, week: number, year?: number): Promise<DailyOcc> {
  return api.get<DailyOcc>(`/scenarios/${scenarioId}/daily-occ/?week=${week}${year != null ? `&year=${year}` : ""}`);
}
export async function getDailyOccEntry(scenarioId: string, week: number): Promise<{ rows: { month: number; days: number[] }[] }> {
  return api.get(`/scenarios/${scenarioId}/daily-occ-entry/?week=${week}`);
}
export async function saveDailyOccEntry(scenarioId: string, week: number, rows: { month: number; days: number[] }[]): Promise<{ saved: boolean; cells_saved: number }> {
  return api.put(`/scenarios/${scenarioId}/daily-occ-entry/?week=${week}`, { rows });
}

// ─── Channel Mix (Market Set) ──────────────────────────────────────────────
export type ChannelMetric = "rooms" | "pax";
export interface ChannelMixRow { channel: string; value: number; pct: number; }
export interface ChannelMix { scenario_id: string; ytd: number; metric: ChannelMetric; has_data: boolean; total: number; channels: ChannelMixRow[]; }
export async function getChannelMix(scenarioId: string, ytd: number, metric: ChannelMetric = "rooms"): Promise<ChannelMix> {
  return api.get(`/scenarios/${scenarioId}/channel-mix/?ytd=${ytd}&metric=${metric}`);
}
export interface ChannelMixEntryRow { month: number; values: number[]; }
export async function getChannelMixEntry(scenarioId: string, metric: ChannelMetric = "rooms"): Promise<{ scenario_id: string; metric: ChannelMetric; channels: string[]; rows: ChannelMixEntryRow[] }> {
  return api.get(`/scenarios/${scenarioId}/channel-mix-entry/?metric=${metric}`);
}
export async function saveChannelMixEntry(scenarioId: string, rows: ChannelMixEntryRow[], metric: ChannelMetric = "rooms"): Promise<{ saved: boolean; metric: ChannelMetric; rows_saved: number }> {
  return api.put(`/scenarios/${scenarioId}/channel-mix-entry/?metric=${metric}`, { rows });
}

// ─── Country Mix (país / mercado) ──────────────────────────────────────────
export interface CountryMixRow { country: string; value: number; pct: number; }
export interface CountryMix { scenario_id: string; ytd: number; metric: ChannelMetric; has_data: boolean; total: number; countries: CountryMixRow[]; }
export async function getCountryMix(scenarioId: string, ytd: number, metric: ChannelMetric = "rooms"): Promise<CountryMix> {
  return api.get(`/scenarios/${scenarioId}/country-mix/?ytd=${ytd}&metric=${metric}`);
}
export interface CountryMixEntryRow { country: string; values: number[]; }
export async function getCountryMixEntry(scenarioId: string, metric: ChannelMetric = "rooms"): Promise<{ scenario_id: string; metric: ChannelMetric; rows: CountryMixEntryRow[] }> {
  return api.get(`/scenarios/${scenarioId}/country-mix-entry/?metric=${metric}`);
}
export async function saveCountryMixEntry(scenarioId: string, rows: CountryMixEntryRow[], metric: ChannelMetric = "rooms"): Promise<{ saved: boolean; metric: ChannelMetric; rows_saved: number }> {
  return api.put(`/scenarios/${scenarioId}/country-mix-entry/?metric=${metric}`, { rows });
}

// ─── Ops KPI (tabla manual de indicadores operativos) ─────────────────────────
export interface OpsKpiRow { kpi: string; target: string; actual: string; owner: string; action: string; }
export async function getOpsKpi(scenarioId: string): Promise<{ scenario_id: string; rows: OpsKpiRow[] }> {
  return api.get(`/scenarios/${scenarioId}/ops-kpi/`);
}
export async function saveOpsKpi(scenarioId: string, rows: OpsKpiRow[]): Promise<{ saved: boolean; rows_saved: number }> {
  return api.put(`/scenarios/${scenarioId}/ops-kpi/`, { rows });
}

// ─── Balance Sheet (Integrity) ────────────────────────────────────────────────
export interface BalanceSheetRow { label: string; indent: number; section: string; is_total: boolean; usd: number; crc: number; }
export interface BalanceSheetPeriod { year: number; month: number; }
export async function getBalanceSheetPeriods(scenarioId: string): Promise<{ scenario_id: string; periods: BalanceSheetPeriod[] }> {
  return api.get(`/scenarios/${scenarioId}/balance-sheet/periods/`);
}
export async function getBalanceSheet(scenarioId: string, year: number, month: number): Promise<{ scenario_id: string; year: number; month: number; has_data: boolean; rows: BalanceSheetRow[] }> {
  return api.get(`/scenarios/${scenarioId}/balance-sheet/?year=${year}&month=${month}`);
}
export interface BalanceSheetMatrixRow { order_idx: number; label: string; indent: number; section: string; is_total: boolean; usd: Record<number, number>; crc: Record<number, number>; }
export async function getBalanceSheetMatrix(scenarioId: string, year: number): Promise<{ scenario_id: string; year: number; months: number[]; has_data: boolean; rows: BalanceSheetMatrixRow[] }> {
  return api.get(`/scenarios/${scenarioId}/balance-sheet/matrix/?year=${year}`);
}
// ─── Cash Flow Budget ─────────────────────────────────────────────────────────
export interface CashFlowBudgetRow {
  section: string; key: string; label: string;
  /** Clave dentro de `cfbFila`. El motor NOMBRA y la pantalla traduce; viene solo
   *  cuando el rotulo es una etiqueta fija (los que salen de la BASE no la traen,
   *  porque eso es dato y se muestra tal cual llega). Ver `rotuloFila()`. */
  label_key?: string;
  kind: "auto" | "input" | "subtotal" | "subtotal_strong" | "total" | "total_strong";
  editable: boolean; values: number[]; full_year: number;
  mode?: "manual" | "pct_sales" | "days" | "lead_lag"; pct?: number | null; lag?: number; driven?: boolean;
  actual_months?: number[]; override_months?: number[];
}
export interface CashFlowCalib { ytd: number; ytd_sales: number; implied_pct: number | null; months: number; }
export type WcParams = Record<string, number | number[] | number[][] | boolean>;
export interface WcModel { enabled: boolean; params: WcParams; timing_matrix?: number[][]; timing_offsets?: number[]; }
export interface BalanceProjectionLine { label: string; section: string; is_total: boolean; indent: number; anchor: number; values: number[]; }
export interface BalanceProjection {
  scenario_id: string; year: number; anchor_year: number; anchor_month: number; horizon: number;
  lines: BalanceProjectionLine[];
}
export async function getBalanceSheetProjection(scenarioId: string, months = 24): Promise<BalanceProjection> {
  return api.get<BalanceProjection>(`/scenarios/${scenarioId}/balance-sheet-projection/?months=${months}`);
}
/** De dónde salió la caja inicial. null = se escribió a mano. */
export interface OpeningAnchor {
  scenario_id: string; label: string | null; anchored_at: string | null;
}
export interface CashFlowBudget {
  scenario_id: string; year: number; opening_cash: number; rows: CashFlowBudgetRow[];
  opening_anchor?: OpeningAnchor | null;
  calibration?: Record<string, CashFlowCalib>; wc_model?: WcModel;
  wc_integrated?: { prior?: { id: string; year: number; label: string } | null; next?: { id: string; year: number; label: string } | null } | null;
  has_overrides?: boolean;
  copy_result?: { version_name: string; months: number[]; mapped: string[]; skipped: string[] };
}
export async function getCashflowBudget(scenarioId: string): Promise<CashFlowBudget> {
  return api.get<CashFlowBudget>(`/scenarios/${scenarioId}/cashflow-budget/`);
}
export async function copyCashflowFromVersion(scenarioId: string, versionId: string, months: number[] = [1, 2, 3, 4, 5]): Promise<CashFlowBudget> {
  return api.post<CashFlowBudget>(`/scenarios/${scenarioId}/cashflow-budget/copy-from-version/?version_id=${encodeURIComponent(versionId)}&months=${months.join(",")}`, {});
}
export async function saveCashflowWcOverrides(scenarioId: string, overrides: Record<string, Record<string, number>>): Promise<CashFlowBudget> {
  return api.put<CashFlowBudget>(`/scenarios/${scenarioId}/cashflow-budget/wc-overrides/`, { overrides });
}
/** Un componente del drill-down: el `label` es el respaldo en espanol y
 *  `label_key` + `label_params` son lo que arma la frase en el idioma del
 *  usuario (namespace `cfbParte`). Ver `rotuloParte()`. */
export interface WcBreakdownParte {
  label: string; amount: number;
  label_key?: string;
  label_params?: Record<string, string | number>;
}
export interface WcBreakdown {
  row: string; month_label: string; total: number; check: number;
  parts: WcBreakdownParte[];
}
export async function getWcBreakdown(scenarioId: string, row: string, month: number): Promise<WcBreakdown> {
  return api.get<WcBreakdown>(`/scenarios/${scenarioId}/cashflow-budget/wc-breakdown/?row=${encodeURIComponent(row)}&month=${month}`);
}
export interface PlBreakdown {
  line: string; month: number; month_label: string;
  source: string; link: string; link_label: string;
  parts: { code: string; label: string; amount: number }[]; total: number;
}
export async function getPlBreakdown(scenarioId: string, line: string, month: number): Promise<PlBreakdown> {
  return api.get<PlBreakdown>(`/scenarios/${scenarioId}/pl-breakdown/?line=${encodeURIComponent(line)}&month=${month}`);
}
/** ¿El reporte refleja lo último que se editó, o hay cambios sin recalcular?
 *  Editar un salario o una regla de reparto NO se propaga solo: hay que
 *  Recalcular. Esto lo detecta comparando marcas de tiempo. */
export interface RecalcState {
  last_recalc_at: string | null;
  stale: boolean;
  changed: { que: string; cuando: string }[];
}
export async function getRecalcState(scenarioId: string): Promise<RecalcState> {
  return api.get<RecalcState>(`/scenarios/${scenarioId}/recalc-state/`);
}

/** ¿La caja inicial anclada sigue siendo el cierre de su escenario fuente?
 *  Va aparte del payload a propósito: recalcular el cierre del origen cuesta
 *  otro P&L completo y duplicaría el tiempo de carga de la pantalla. */
export interface AnchorCheck {
  anchored: boolean; label?: string | null; anchored_at?: string | null;
  stored?: number; current?: number; diff?: number; stale?: boolean;
  source_missing?: boolean;
}
export async function checkOpeningAnchor(scenarioId: string): Promise<AnchorCheck> {
  return api.get<AnchorCheck>(`/scenarios/${scenarioId}/cashflow-budget/anchor-check/`);
}
export async function anchorOpeningCash(scenarioId: string, sourceScenarioId: string): Promise<CashFlowBudget & { anchored_from?: { scenario_id: string; year: number; label?: string; ending_cash: number; anchored_at?: string } }> {
  return api.post(`/scenarios/${scenarioId}/cashflow-budget/anchor-opening/?source_scenario_id=${encodeURIComponent(sourceScenarioId)}`, {});
}
export async function saveCashflowBudgetInputs(
  scenarioId: string, openingCash: number, rows: { row_key: string; values: number[] }[]
): Promise<CashFlowBudget> {
  return api.put<CashFlowBudget>(`/scenarios/${scenarioId}/cashflow-budget/inputs/`, { opening_cash: openingCash, rows });
}
export async function saveCashflowBudgetDrivers(
  scenarioId: string, drivers: { row_key: string; mode: "manual" | "pct_sales" | "days" | "lead_lag"; pct: number | null; lag?: number }[]
): Promise<CashFlowBudget> {
  return api.put<CashFlowBudget>(`/scenarios/${scenarioId}/cashflow-budget/drivers/`, { drivers });
}
export async function saveCashflowBudgetWcModel(
  scenarioId: string, enabled: boolean, params: WcParams
): Promise<CashFlowBudget> {
  return api.put<CashFlowBudget>(`/scenarios/${scenarioId}/cashflow-budget/wc-model/`, { enabled, params });
}

// ── Cash Flow Método Directo (portado de Luz de Mono) ──────────────────────
export interface CfDirectoRow {
  label: string; values: number[]; full_year: number; kind: string;
  key?: string; editable?: boolean;
  /** La CLAVE de la explicación; el texto vive en el catálogo (`cfdAyuda`). */
  ayuda?: { clave: string };
  /** La clave del rótulo. Ausente en las filas por departamento: ahí el
   *  `label` es el nombre que viene de la base, o sea dato. */
  label_key?: string;
  /** Datos del rótulo (p. ej. la tasa de IVA, que es un criterio editable y
   *  por eso NO puede ir escrita dentro del texto). */
  label_params?: Record<string, string | number>;
}
export interface CashFlowDirecto {
  renta?: RentaAnual;
  opening_cash: number;
  params: Record<string, number | number[]>;
  manual: Record<string, number[]>;
  defaults: Record<string, number | number[]>;
  resumen: CfDirectoRow[];
  aux_ingresos: CfDirectoRow[];
  aux_nomina: CfDirectoRow[];
  aux_proveedores: CfDirectoRow[];
  aux_gastos_propiedad: CfDirectoRow[];
  aux_iva: CfDirectoRow[];
}
export async function getCashflowDirecto(scenarioId: string): Promise<CashFlowDirecto> {
  return api.get<CashFlowDirecto>(`/scenarios/${scenarioId}/cashflow-directo/`);
}

// ── Retención de renta al salario (impuesto por tramos, por persona) ─────────
export interface TramoRenta { n: number; desde: number; hasta: number | null; tasa: number; etiqueta: string; }
export interface EmpleadoRetencion {
  position_id: string; empleado: string; puesto: string;
  dept_code: string; dept_name: string;
  base_usd: number[]; impuesto_usd: number[]; tramo: number[];
  base_anual: number; impuesto_anual: number; afecto: boolean;
}
export interface Retenciones {
  scenario_id: string; year: number;
  tramos: TramoRenta[]; tc_mes: number[];
  deduce_ccss: boolean; ccss_obrera_rate: number;
  empleados: EmpleadoRetencion[];
  total_mes: number[]; base_mes: number[];
  total_anual: number; base_anual: number;
  empleados_afectos: number; empleados_total: number;
}
export async function getRetenciones(scenarioId: string): Promise<Retenciones> {
  return api.get<Retenciones>(`/scenarios/${scenarioId}/retenciones/`);
}
export interface RentaAnual {
  tasa: number; ebt: number; impuesto_bruto: number; creditos_tarjeta: number;
  neto: number; a_pagar: number; saldo_a_favor: number;
  mes_pago: number; pago_manual: number; pasa_al_flujo: number;
}
export async function saveTramosRenta(
  scenarioId: string, tramos: Partial<TramoRenta>[], deduceCcss: boolean,
  renta?: { renta_tasa?: number; renta_pago_manual?: number; renta_mes_pago?: number },
) {
  return api.put(`/scenarios/${scenarioId}/retenciones/tramos/`,
    { tramos, deduce_ccss: deduceCcss, ...(renta ?? {}) });
}
export async function saveCashflowDirecto(
  scenarioId: string, params: Record<string, number | number[]>, manual: Record<string, number[]>
): Promise<{ ok: boolean }> {
  return api.put<{ ok: boolean }>(`/scenarios/${scenarioId}/cashflow-directo/`, { params, manual });
}

export function balanceSheetTemplateUrl(scenarioId: string, year?: number, month?: number): string {
  const base = dlUrl(`/scenarios/${scenarioId}/balance-sheet/export/excel/`);
  const extra = (year && month) ? `&year=${year}&month=${month}` : "";
  return base + extra;
}
export async function importBalanceSheet(scenarioId: string, file: File, dryRun = false): Promise<{ dry_run: boolean; imported?: boolean; rows_saved?: number; periods: BalanceSheetPeriod[]; lines: number; check: { year: number; month: number; total_assets: number | null; total_liab_equity: number | null }[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/import-balance-sheet/?dry_run=${dryRun}`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface RoomStatsEntryRow {
  room_type_name: string; units: number; nights_available: number;
  nights_occupied: number; revenue: number; pax: number;
}
export interface RoomStatsEntry {
  scenario_id: string; year: number; month: number; days_in_month: number; rows: RoomStatsEntryRow[];
}
export async function getRoomStatsEntry(scenarioId: string, month: number): Promise<RoomStatsEntry> {
  return api.get<RoomStatsEntry>(`/scenarios/${scenarioId}/room-stats-entry/${month}/`);
}
export async function saveRoomStatsEntry(scenarioId: string, month: number,
  rows: { room_type_name: string; units: number; nights_occupied: number; revenue: number; pax: number }[]): Promise<{ saved: boolean; month: number; rows_saved: number }> {
  return api.put(`/scenarios/${scenarioId}/room-stats-entry/${month}/`, { rows });
}

export async function importRoomStats(scenarioId: string, file: File, dryRun = false): Promise<ImportRoomStatsResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/import-room-stats/?dry_run=${dryRun}`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

// ─── Planilla por departamento (C4) ───────────────────────────────────────────
export interface PayrollDeptRow {
  dept_code: string;
  dept_name: string;
  headcount: number;
  fte_avg: number;
  sw_annual: number;
  total_annual: number;
}
export interface PayrollDeptReport {
  scenario_id: string;
  depts: PayrollDeptRow[];
  totals: { headcount: number; fte_avg: number; sw_annual: number; total_annual: number };
}
export async function getPayrollDeptReport(scenarioId: string): Promise<PayrollDeptReport> {
  return api.get<PayrollDeptReport>(`/payroll/${scenarioId}/dept-report/`);
}

export interface PayrollDeptMonthlyRow {
  dept_code: string; dept_name: string;
  headcount: number[]; fte: number[]; total: number[]; total_annual: number;
}
export interface PayrollDeptMonthlyReport {
  scenario_id: string;
  depts: PayrollDeptMonthlyRow[];
  totals: { headcount: number[]; fte: number[]; total: number[]; total_annual: number };
}
export async function getPayrollDeptReportMonthly(scenarioId: string): Promise<PayrollDeptMonthlyReport> {
  return api.get<PayrollDeptMonthlyReport>(`/payroll/${scenarioId}/dept-report-monthly/`);
}

// ─── FTE real por depto — carga manual/Excel cuando no hay planilla al detalle ─
export async function downloadDeptFteTemplate(scenarioId: string): Promise<Blob> {
  const res = await fetch(`${BASE}/payroll/${scenarioId}/dept-fte-template/`, { headers: authHeaders() });
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.blob();
}
export async function importDeptFte(scenarioId: string, file: File, dryRun = false): Promise<{ dry_run: boolean; imported?: boolean; months_present: number[]; rows: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/payroll/${scenarioId}/import-dept-fte/?dry_run=${dryRun}`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

// ─── Gastos por depto y cuenta (C6: OPEX / Costos) ────────────────────────────
export interface DeptAccountReport {
  scenario_id: string;
  depts: {
    dept_code: string;
    annual: number;
    accounts: { account_code: string; account_name: string; annual: number }[];
  }[];
}
export async function getOpexReport(scenarioId: string): Promise<DeptAccountReport> {
  return api.get<DeptAccountReport>(`/opex/${scenarioId}/report/`);
}

// ─── Flujo de caja proyectado (D1) ────────────────────────────────────────────
export interface CashFlowParams {
  opening_cash: number; dso_days: number; dpo_days: number; distributions_annual: number;
}
export interface CashFlowRow {
  month: number; ebitda: number; ar_change: number; ap_change: number; tax_paid: number;
  operating: number; capex: number; investing: number; distributions: number;
  financing: number; net: number; ending_cash: number;
}
export interface CashFlow {
  scenario_id: string; year: number; params: CashFlowParams;
  opening_cash: number; rows: CashFlowRow[]; ending_cash: number;
}
export async function saveCashflowParams(scenarioId: string, p: CashFlowParams): Promise<{ ok: boolean }> {
  return api.put<{ ok: boolean }>(`/scenarios/${scenarioId}/cashflow/params/`, p);
}

// ─── Panorama fiscal (D2) ─────────────────────────────────────────────────────
export interface TaxParams {
  wh_rate: number; income_tax_rate: number;
  card_pct_rooms: number; card_pct_fb: number; card_pct_spa: number;
  card_pct_tours: number; card_pct_private_bar: number; card_pct_other: number;
}
export interface TaxPanorama {
  scenario_id: string; year: number; params: TaxParams;
  monthly: { month: number; card_revenue: number; withholding: number }[];
  cumulative_wh: number; annual_ebt: number; annual_revenue: number;
  gross_income_tax: number; wh_credit: number; net_income_tax: number;
  credit_balance: number; effective_tax_rate: number;
}
export async function getTax(scenarioId: string): Promise<TaxPanorama> {
  return api.get<TaxPanorama>(`/scenarios/${scenarioId}/tax/`);
}
export async function saveTaxParams(scenarioId: string, p: TaxParams): Promise<{ ok: boolean }> {
  return api.put<{ ok: boolean }>(`/scenarios/${scenarioId}/tax/params/`, p);
}
export async function getCostsReport(scenarioId: string): Promise<DeptAccountReport> {
  return api.get<DeptAccountReport>(`/costs/${scenarioId}/report/`);
}
export async function getRevenueDetailReport(scenarioId: string): Promise<DeptAccountReport> {
  return api.get<DeptAccountReport>(`/scenarios/${scenarioId}/revenue-detail/report/`);
}
export async function getBelowGopReport(scenarioId: string): Promise<DeptAccountReport> {
  return api.get<DeptAccountReport>(`/scenarios/${scenarioId}/belowgop-detail/report/`);
}

export async function getPLManualInputs(scenarioId: string): Promise<PLManualInput[]> {
  return api.get<PLManualInput[]>(`/pl/${scenarioId}/manual/`);
}

export async function savePLManualInput(
  scenarioId: string,
  month: number,
  payload: Partial<Omit<PLManualInput, "month">>,
): Promise<{ ok: boolean; month: number }> {
  return api.put<{ ok: boolean; month: number }>(`/pl/${scenarioId}/manual/${month}/`, payload);
}

export async function recalculatePL(scenarioId: string): Promise<RecalcResult> {
  return api.post<RecalcResult>(`/pl/${scenarioId}/recalculate/`);
}

// ── Mapping admin helpers ──────────────────────────────────────────────────────

export interface ReportLine {
  id: string;
  report_id: string;
  display_order: number;
  line_code: string;
  section: string;
  line_name: string;
  line_type: string;
  parent_line_code: string | null;
  calculation_logic: string | null;
  format_hint: string | null;
  active: boolean;
}

export interface AccountMappingRow {
  id: string;
  active_status: string;
  report_id: string;
  report_line_code: string;
  report_line_name: string | null;
  report_section: string | null;
  display_order: number | null;
  source_origin: string | null;
  source_department: string | null;
  /** El código es lo que RUTEA el P&L; el nombre es la etiqueta. Cuando falta,
   *  la cuenta cae en la línea del primer departamento — por eso se muestra. */
  dept_code: string | null;
  account_code: string;
  account_name_example: string | null;
  financial_nature: string;
  rollup_operator: string;
  sign_rule: string | null;
  notes: string | null;
}

export interface UnmappedAccount {
  dept_code: string;
  account_code: string;
  account_name: string;
  total_activity: number;
}

export interface AccountMappingCreate {
  active_status?: string;
  report_id?: string;
  report_line_code: string;
  report_line_name?: string;
  report_section?: string;
  source_origin?: string;
  source_department?: string;
  /** Si va vacío, el backend lo deriva del nombre del departamento. Se escribe
   *  a mano cuando el nombre no es de los que sabe reconocer. */
  dept_code?: string;
  account_code: string;
  account_name_example?: string;
  financial_nature: string;
  rollup_operator?: string;
  notes?: string;
}

export async function getReportLines(reportId = "P%26L_DETAIL_OWNERS"): Promise<ReportLine[]> {
  return api.get<ReportLine[]>(`/mapping/lines/?report_id=${reportId}`);
}

export async function getAccountMappings(params?: {
  report_line_code?: string;
  active_only?: boolean;
}): Promise<AccountMappingRow[]> {
  const qs = new URLSearchParams({ report_id: "P&L_DETAIL_OWNERS" });
  if (params?.report_line_code) qs.set("report_line_code", params.report_line_code);
  if (params?.active_only) qs.set("active_only", "true");
  return api.get<AccountMappingRow[]>(`/mapping/accounts/?${qs}`);
}

export async function createAccountMapping(body: AccountMappingCreate): Promise<AccountMappingRow> {
  return api.post<AccountMappingRow>(`/mapping/accounts/`, body);
}

export async function updateAccountMapping(
  id: string,
  body: Partial<AccountMappingRow>,
): Promise<AccountMappingRow> {
  return api.put<AccountMappingRow>(`/mapping/accounts/${id}/`, body);
}

export async function deleteAccountMapping(id: string): Promise<void> {
  await api.delete(`/mapping/accounts/${id}/`);
}

export async function getUnmappedAccounts(hotelId = HOTEL_ID): Promise<UnmappedAccount[]> {
  return api.get<UnmappedAccount[]>(`/mapping/unmapped/?hotel_id=${hotelId}`);
}

// ── Cash Flow: versiones presentadas a dueños (planas / congeladas) ───────────
export interface CashFlowVersionRow { section: string; label: string; values: number[]; full_year: number; is_total: boolean; }
export interface CashFlowVersionMeta { id: string; name: string; kind: string; order_idx: number; n_rows: number; created_at: string | null; }
export interface CashFlowVersionFull { id: string; name: string; kind: string; order_idx: number; rows: CashFlowVersionRow[]; }

export async function getCashflowVersions(hotelId = HOTEL_ID): Promise<CashFlowVersionMeta[]> {
  return api.get<CashFlowVersionMeta[]>(`/cashflow-versions/?hotel_id=${hotelId}`);
}
export async function getCashflowVersion(id: string): Promise<CashFlowVersionFull> {
  return api.get<CashFlowVersionFull>(`/cashflow-versions/${id}/`);
}
export async function importCashflowVersion(
  file: File, name: string, opts?: { hotelId?: string; orderIdx?: number; dryRun?: boolean }
): Promise<{ id?: string; name: string; n_rows: number; rows?: CashFlowVersionRow[] }> {
  const q = new URLSearchParams({
    name, hotel_id: opts?.hotelId ?? HOTEL_ID,
    order_idx: String(opts?.orderIdx ?? 0), dry_run: String(opts?.dryRun ?? false),
  });
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/cashflow-versions/import/?${q}`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}
export async function deleteCashflowVersion(id: string): Promise<{ ok: boolean }> {
  return api.delete<{ ok: boolean }>(`/cashflow-versions/${id}/`);
}
export async function createWorkingVersion(scenarioId: string, name: string, orderIdx = 99): Promise<{ id: string; name: string; kind: string; n_rows: number }> {
  const q = new URLSearchParams({ scenario_id: scenarioId, name, order_idx: String(orderIdx) });
  return api.post(`/cashflow-versions/working/?${q}`);
}
export async function updateCashflowVersion(id: string, body: { name?: string; rows?: CashFlowVersionRow[] }): Promise<{ id: string; name: string; n_rows: number }> {
  return api.put(`/cashflow-versions/${id}/`, body);
}

// ── Excel de conceptos MANUALES de planilla, por departamento y posición ──────
// Horas extra, bono, cesantía, transporte, vivienda y otros no salen de una
// fórmula: se negocian caso por caso y el owner los pone a mano.
export async function bajarBeneficiosExcel(scenarioId: string): Promise<Blob> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const res = await fetch(`${base}/payroll/${scenarioId}/beneficios/excel/`,
    { headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.blob();
}

export interface SubidaBeneficios {
  celdas_escritas: number;
  posiciones_tocadas: number;
  conceptos: string[];
  avisos: string[];
  aviso?: string;
}

export async function subirBeneficiosExcel(
  scenarioId: string, file: File,
): Promise<SubidaBeneficios> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${base}/payroll/${scenarioId}/beneficios/excel/`,
    { method: "POST", body: fd, headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<SubidaBeneficios>;
}

// ── Tipo de cambio del año (Master Data) ─────────────────────────────────────
// Vive por escenario, un valor por mes. Mueve TODO lo que está en colones:
// salarios, CCSS, aguinaldo, vacaciones, el reparto del INS y los beneficios.
export interface TipoCambioMes {
  month: number;
  tc_crc_usd: string | null;
  is_explicit: boolean;
  notes: string;
}

export interface TipoCambioResponse {
  scenario_id: string;
  scenario_type: string;
  year: number;
  months: TipoCambioMes[];
}

export async function getTipoCambio(scenarioId: string): Promise<TipoCambioResponse> {
  return api.get<TipoCambioResponse>(`/scenarios/${scenarioId}/exchange-rates/`);
}

export async function saveTipoCambio(
  scenarioId: string, porMes: Record<string, number>, notes = "",
): Promise<{ updated?: number[] }> {
  return api.put(`/scenarios/${scenarioId}/exchange-rates/`,
    { tc_by_month: porMes, notes });
}

// ── El pote que se va a repartir, abierto por clase de cuenta ────────────────
// Costo de ventas (5) + planilla (6) + OPEX (7) del departamento origen, mes a
// mes. Es de dónde sale el monto que después se distribuye.
export interface FuenteLinea {
  clase: string;
  nombre: string;
  meses: number[];   // 12
  total: number;
  /** Cuantas lineas existen en ese depto. Un total en cero puede ser «no hay
   *  lineas» o «hay lineas sin monto», y no es lo mismo. */
  lineas_cargadas?: number;
  /** Donde se cargan, para poder decirlo en la pantalla. */
  donde?: string;
}

export interface CostoAReparto {
  scenario_id: string;
  dept_code: string;
  lineas: FuenteLinea[];
  totales_mes: number[];   // 12
  total: number;
}

export async function getCostoAReparto(
  scenarioId: string, dept: string,
): Promise<CostoAReparto> {
  return api.get<CostoAReparto>(`/allocations/${scenarioId}/fuente/?dept=${dept}`);
}

// ── FTE por departamento y por mes (el endpoint crudo del backend) ───────────
// `getFteReport` arma el detalle por persona; esto trae el agregado por depto,
// que es lo que sirve para revisar un reparto.
export interface FtePorDepto {
  scenario_id: string;
  by_dept: Record<string, Record<string, number>>;  // dept → { "1".."12" }
  totals: Record<string, number>;
  annual_avg?: Record<string, number>;
}

export async function getFtePorDepto(scenarioId: string): Promise<FtePorDepto> {
  return api.get<FtePorDepto>(`/payroll/${scenarioId}/fte-report/`);
}

// ── Control: ¿el dólar de las líneas en colones quedó viejo? ─────────────────
// Si el TC se mueve y nadie recalcula, el P&L muestra el dólar anterior y nada
// lo avisa. Un análisis con esa cifra sale mal sin que se note.
export interface EstadoMoneda {
  scenario_id: string;
  lineas_en_colones: number;
  desactualizadas: number;
  sin_tipo_de_cambio: boolean;
  detalle: { tipo: string; dept_code: string; account_code: string;
             account_name?: string; meses?: number[]; motivo?: string }[];
}

export async function getEstadoMoneda(scenarioId: string): Promise<EstadoMoneda> {
  return api.get<EstadoMoneda>(`/checkbook/${scenarioId}/moneda/estado/`);
}

// ── Detalle de proyectos de capital (por área, mes a mes) ─────────────────────

export interface CapitalProjectRow {
  id: string; area: string; name: string; notes: string; sort_order: number;
  jan: number; feb: number; mar: number; apr: number; may: number; jun: number;
  jul: number; aug: number; sep: number; oct: number; nov: number; dec: number;
  total: number;
}
export interface CapitalProjectArea {
  area: string; count: number; total: number;
  jan: number; feb: number; mar: number; apr: number; may: number; jun: number;
  jul: number; aug: number; sep: number; oct: number; nov: number; dec: number;
}
export interface CapitalDetail {
  scenario_id: string;
  entries: CapitalProjectRow[];
  areas: CapitalProjectArea[];
  months: Record<string, number>;
  total: number;
}
export type CapitalPatch = Partial<Omit<CapitalProjectRow, "id" | "total">>;

export async function getCapitalDetail(scenarioId: string): Promise<CapitalDetail> {
  return api.get<CapitalDetail>(`/capital/${scenarioId}/`);
}
export async function createCapitalProject(scenarioId: string, row: CapitalPatch): Promise<CapitalProjectRow> {
  return api.post<CapitalProjectRow>(`/capital/${scenarioId}/`, row);
}
export async function updateCapitalProject(scenarioId: string, id: string, patch: CapitalPatch): Promise<CapitalProjectRow> {
  return api.put<CapitalProjectRow>(`/capital/${scenarioId}/entry/${id}/`, patch);
}
export async function deleteCapitalProject(scenarioId: string, id: string): Promise<{ ok: boolean }> {
  return api.delete<{ ok: boolean }>(`/capital/${scenarioId}/entry/${id}/`);
}

/** Descarga «Capital Project». Va por blob y no por dlUrl para no mandar el
 *  token en la URL: acá no hace falta, el navegador guarda igual el archivo. */
export async function downloadCapitalExcel(scenarioId: string): Promise<Blob> {
  const res = await fetch(`${BASE}/capital/${scenarioId}/excel/`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.blob();
}
export async function uploadCapitalExcel(
  scenarioId: string, file: File,
): Promise<{ ok: boolean; count: number; total: number }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/capital/${scenarioId}/excel/`, {
    method: "POST", body: form, headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// ── El mixer de canales ───────────────────────────────────────────────────────
// Se planifica en los 7 sub-canales; los 3 de comisión se derivan. Ver
// backend/app/engine/mixer_canales.py y docs/MIXER_DE_CANALES.md.

export interface SubCanal {
  code: string; nombre: string; entrada: string; destino: string;
  eje: "entrada" | "atribucion";
  mix_pct: number; comision_pct: number;
  origen: "base" | "escenario" | "mes";
}
export interface CanalDerivado {
  channel: string; mix_pct: number; commission_pct: number;
}
export interface ImpactoMixer {
  rooms_usd: number; delta_usd: number | null; delta_pct: number | null;
}
/** Un canal de COMISIÓN: a dónde ruedan los sub-canales. Es tabla, no una
 *  constante de tres — por eso se puede agregar un cuarto. */
export interface CanalComision {
  code: string; nombre: string; orden: number;
}
export interface MixerVista {
  scenario_id: string; month: number;
  subcanales: SubCanal[];
  /** Los destinos que existen. Alimenta el desplegable de «rueda a». */
  canales: CanalComision[];
  derivados: CanalDerivado[];
  mix_suma: number; mix_cierra: boolean;
  net_factor_nuevo: number; net_factor_hoy: number | null;
  /** De dónde sale el factor que el motor usa HOY. "tarifas" gana sobre "mix". */
  manda: "tarifas" | "mix" | "nada";
  /** Las tres bases posibles, en NETO (salen del P&L, ya con comisión
   *  descontada). Para repartirlas por canal hay que devolverlas a rack. */
  bases: { rooms: number; comisionable: number; total: number };
  impacto: ImpactoMixer | null;
}
export interface EscenarioMixer {
  id: string; nombre: string; year: number; type: string; version: string;
  locked: boolean; aplica: boolean; motivo: string;
  net_factor_hoy: number | null; net_factor_nuevo: number;
  manda: "tarifas" | "mix" | "nada";
  impacto: ImpactoMixer;
}

export async function getMixer(scenarioId: string, month = 0): Promise<MixerVista> {
  const q = new URLSearchParams({ scenario_id: scenarioId, month: String(month) });
  return api.get<MixerVista>(`/canales/mixer/?${q}`);
}

export async function guardarMixer(
  scenarioId: string,
  filas: { code: string; month: number; mix_pct: number; comision_pct: number }[],
): Promise<{ guardadas: number; scenario_id: string }> {
  return api.put(`/canales/mixer/${scenarioId}/`, filas);
}

/** Guarda el mix BASE: el que hereda todo lo que no tiene excepción, y con el
 *  que nace un escenario nuevo. Sobrevive al redeploy (el seed no lo pisa). */
export async function guardarBaseMixer(
  filas: { code: string; month: number; mix_pct: number; comision_pct: number;
           rueda_a?: string }[],
): Promise<{ guardados: number; suma: number }> {
  return api.put(`/canales/base/`, filas);
}

// ─── Crear y borrar. Owner 2026-08-17: «dejame crear más mix y borrar» ───────

export async function crearSubCanal(c: {
  code: string; nombre: string; rueda_a: string; entrada?: string;
  mix_pct?: number; comision_pct?: number;
}): Promise<{ creado: string; rueda_a: string }> {
  return api.post(`/canales/subcanal/`, c);
}

/** Borra el sub-canal y sus excepciones por escenario. Devuelve la suma que
 *  queda: después de borrar casi nunca da 100%, y hay que decirlo. */
export async function borrarSubCanal(code: string): Promise<{
  borrado: string; excepciones_borradas: number;
  mix_suma: number; mix_cierra: boolean; aviso: string | null;
}> {
  return api.delete(`/canales/subcanal/${encodeURIComponent(code)}/`);
}

export async function getCanalesComision(): Promise<{
  canales: (CanalComision & { subcanales: number; se_puede_borrar: boolean })[];
}> {
  return api.get(`/canales/comision/`);
}

export async function crearCanalComision(c: {
  code: string; nombre: string; orden?: number;
}): Promise<{ creado: string }> {
  return api.post(`/canales/comision/`, c);
}

/** Se niega (409) si tiene sub-canales colgando: su mix quedaría sin destino y
 *  el Net Factor saldría sobre menos del 100%. */
export async function borrarCanalComision(code: string): Promise<{ borrado: string }> {
  return api.delete(`/canales/comision/${encodeURIComponent(code)}/`);
}

export async function getEscenariosMixer(): Promise<{
  escenarios: EscenarioMixer[]; desde_el_ano: number;
}> {
  return api.get(`/canales/mixer/escenarios/`);
}

export async function aplicarMixer(
  scenarioIds: string[], regenerarTarifas = false,
): Promise<{
  aplicados: { id: string; nombre: string; tarifas: number }[];
  saltados: { id: string; nombre: string; motivo: string }[];
  regenero_tarifas: boolean;
  aviso: string;
}> {
  return api.post(`/canales/mixer/aplicar/`, {
    scenario_ids: scenarioIds, regenerar_tarifas: regenerarTarifas,
  });
}

// ── El panorama: las tres listas de canales, confrontadas ────────────────────

/** Sube el `res_statistics1` de Opera abierto por MARKET CODE. Mismas reglas
 *  que el de países: un mes por vez, y no pisa lo corregido a mano. Reusa las
 *  dos excepciones (`CountryXmlElegirMes`, `CountryXmlPisaria`) porque los dos
 *  importadores responden igual. */
export async function importChannelXml(
  scenarioId: string, archivo: File,
  opts?: { year?: number; month?: number; sobrescribir?: boolean },
): Promise<{
  imported: boolean; year: number; month: number; meses_disponibles: number[];
  canales: string[]; filas: number; filas_detalle: number;
  total_noches: number; total_pax: number;
  sin_canal: { code: string; noches: number; pax: number }[];
}> {
  const form = new FormData();
  form.append("file", archivo);
  const q = new URLSearchParams();
  if (opts?.year != null) q.set("year", String(opts.year));
  if (opts?.month != null) q.set("month", String(opts.month));
  if (opts?.sobrescribir) q.set("sobrescribir", "true");
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/import-channel-xml/${q.toString() ? `?${q}` : ""}`,
    { method: "POST", body: form, headers: authHeaders() });
  if (res.status === 409) {
    const d = await res.json().catch(() => null);
    const det = d?.detail;
    if (det?.motivo === "elegir_mes") throw new CountryXmlElegirMes(det.meses_disponibles ?? [], det.year, det.mensaje ?? "");
    if (det?.motivo === "meses_corregidos_a_mano") throw new CountryXmlPisaria(det.meses ?? [], det.mensaje ?? "");
  }
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

/** El reporte del Channel Mix: 4 pestañas (canal y market code × noches y pax). */
export function urlExcelCanales(scenarioId: string): string {
  return `${BASE}/scenarios/${scenarioId}/channel-mix/excel.xlsx`;
}
/** La plantilla EDITABLE: 2 pestañas, filas = market code. */
export function urlPlantillaCanales(scenarioId: string): string {
  return `${BASE}/scenarios/${scenarioId}/channel-mix/plantilla.xlsx`;
}
/** Sube la plantilla corregida. Sin `confirmar`, solo REVISA. */
export async function subirPlantillaCanales(scenarioId: string, archivo: File, confirmar: boolean): Promise<{
  guardado: boolean; filas: number; celdas?: number; total_cambios: number;
  cambios: { code: string; metric: string; antes: number | null; ahora: number | null }[];
  sin_canal: string[];
}> {
  const form = new FormData();
  form.append("file", archivo);
  const res = await fetch(`${BASE}/scenarios/${scenarioId}/channel-mix/plantilla/?confirmar=${confirmar}`, { method: "POST", body: form, headers: authHeaders() });
  if (!res.ok) { throw new Error(`API ${res.status}: ${await res.text()}`); }
  return res.json();
}

// ── Opex Checkbook Planning ───────────────────────────────────────────────────
export interface CheckbookDepto { dept_code: string; dept_name: string; cuentas: number; lineas: number }
export interface CheckbookPreview {
  departamento: string; anio_version: number; cuentas: number;
  detalles_por_cuenta: number; filas_de_captura: number; con_estadisticas: boolean;
  referencias: Record<string, { escenario: string; escenario_id: string; cuentas: number;
                                opciones: { id: string; label: string }[] }>;
  cuentas_detalle: { cuenta: number; descripcion: string }[];
}
export async function getCheckbookDeptos(scenarioId: string): Promise<{ departamentos: CheckbookDepto[] }> {
  return api.get(`/checkbook/${scenarioId}/departamentos/`);
}
/** `refs` = {"2026": "<scenario_id>"} — pisa la regla por defecto de ese año. */
function qsRefs(detalles: number, refs?: Record<string, string>): string {
  const q = new URLSearchParams({ detalles: String(detalles) });
  for (const [anio, id] of Object.entries(refs ?? {})) if (id) q.append("ref", `${anio}:${id}`);
  return q.toString();
}
export async function getCheckbookPreview(scenarioId: string, deptCode: string, detalles = 11,
                                          refs?: Record<string, string>): Promise<CheckbookPreview> {
  return api.get(`/checkbook/${scenarioId}/${deptCode}/preview/?${qsRefs(detalles, refs)}`);
}
export function urlCheckbookExcel(scenarioId: string, deptCode: string, detalles = 11,
                                  refs?: Record<string, string>): string {
  return `${BASE}/checkbook/${scenarioId}/${deptCode}/excel.xlsx?${qsRefs(detalles, refs)}`;
}

/** Lo que dice la subida: qué hizo, o qué haría con `dryRun`. */
export interface CheckbookSubida {
  dry_run?: boolean;
  ok?: boolean;
  departamento: string;
  anio: number | null;
  lineas_actualizadas: number;
  lineas_vaciadas: number;
  lineas_nuevas: number;
  lineas_en_colones: number;
  gran_total_del_archivo: number;
  estadisticas_en_el_archivo?: { noches_disponibles?: number[]; noches_ocupadas?: number[] };
}

/**
 * Sube el checkbook lleno.
 *
 * Se llama SIEMPRE primero con `dryRun` y se le muestra al usuario qué va a
 * pasar. Vaciar líneas es un efecto perfectamente posible —el owner borró una
 * fila en el Excel— pero no es algo que deba ocurrir sin que lo vea antes.
 */
export async function subirCheckbook(
  scenarioId: string, deptCode: string, archivo: File, dryRun: boolean,
): Promise<CheckbookSubida> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  const res = await fetch(
    `${BASE}/checkbook/${scenarioId}/${deptCode}/importar/?dry_run=${dryRun}`,
    { method: "POST", body: fd, headers: authHeaders() });
  const cuerpo = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof cuerpo?.detail === "string" ? cuerpo.detail : `API ${res.status}`);
  return cuerpo as CheckbookSubida;
}

export interface PanoramaCanales {
  canales_pms: string[];
  market_codes: { code: string; nombre: string; canal: string; canal_comision: string; activo: boolean }[];
  comerciales: { code: string; nombre: string; comision_pct: number; entrada: string; eje: string }[];
  comision_finplan: Record<string, number>;
  discrepancias: { tipo: string; gravedad: string; detalle: string; porque: string }[];
}

export async function getPanoramaCanales(scenarioId = ""): Promise<PanoramaCanales> {
  const q = scenarioId ? `?scenario_id=${encodeURIComponent(scenarioId)}` : "";
  return api.get<PanoramaCanales>(`/canales/panorama/${q}`);
}

// ── Chequeo de la propiedad ───────────────────────────────────────────────────
// Pregunta lo que puede haber salido mal en una instalación y no se nota
// mirando. Ver backend/app/api/chequeo_api.py y docs/CLONAR_PROPIEDAD.md.

export interface ChequeoItem {
  clave: string;
  titulo: string;
  estado: "error" | "aviso" | "ok" | "info";
  detalle: string;
  porque: string;
  que_hacer: string;
}
export interface Chequeo {
  hotel_id: string;
  hotel_name: string;
  errores: number;
  avisos: number;
  chequeos: ChequeoItem[];
}

export async function getChequeo(): Promise<Chequeo> {
  return api.get<Chequeo>(`/chequeo/`);
}

// ── El setup de la cuenta ─────────────────────────────────────────────────────
// Las cinco preguntas que cada cuenta tiene que responder antes de clonar una
// propiedad: qué es, qué departamento, en qué línea del P&L, cómo llegó ahí y
// si se alinea entre años. Ver backend/app/api/setup_cuenta_api.py.

export interface SetupFila {
  dept_code: string;
  dept_name: string;
  dept_tipo: string;
  dept_padre: string;
  cuenta: string;
  cuenta_nombre: string;
  clase: string;
  clase_nombre: string;
  linea_code: string;
  linea_nombre: string;
  seccion: string;
  como: string;
  como_nombre: string;
  regla_de: string;
  regla_propia: boolean;
  /** Año (como texto) → USD. Solo los años con movimiento. */
  montos: Record<string, number>;
  con_movimiento: boolean;
  limpia: boolean;
  desalineada: boolean;
  alerta: string;
}
export interface SetupCelda { anio: number; estado: string; monto: number; }
export interface SetupLineaDesalineada {
  linea_code: string;
  linea_nombre: string;
  deptos: string[];
  celdas: SetupCelda[];
}
export interface SetupDesalineada {
  cuenta: string;
  cuenta_nombre: string;
  clase: string;
  clase_nombre: string;
  anios: number[];
  lineas: SetupLineaDesalineada[];
  monto_en_juego: number;
}
export interface SetupCuenta {
  hotel_id: string;
  anios: { anio: number; escenario_id: string; escenario: string }[];
  clases: { clase: string; nombre: string; cuentas: number }[];
  departamentos: { dept_code: string; dept_name: string; dept_tipo: string }[];
  resumen: {
    filas: number; cuentas: number; limpias: number; a_revisar: number;
    por_descarte: number; sin_regla: number; desalineadas: number;
    sin_movimiento: number; anios_comparados: number[];
  };
  filas: SetupFila[];
  desalineadas: SetupDesalineada[];
}

export async function getSetupCuenta(): Promise<SetupCuenta> {
  return api.get<SetupCuenta>(`/setup-cuenta/`);
}
/** El Excel lo arma el backend (tres hojas). Va por <a href>, con token en la query. */
export function setupCuentaExcelUrl(soloRevisar = false): string {
  const base = dlUrl(`/setup-cuenta/excel/`);
  return soloRevisar ? `${base}${base.includes("?") ? "&" : "?"}solo_revisar=true` : base;
}

// ── Líneas obligatorias ───────────────────────────────────────────────────────
// El par de la verificación del upload: aquélla cuida los actuales en la puerta,
// ésta avisa cuando un PRESUPUESTO deja en cero una línea que el histórico usa.
// AVISA, NO BLOQUEA. Ver backend/app/engine/lineas_obligatorias.py.

export interface LineaObligatoria {
  line_code: string;
  nombre: string;
  seccion: string;
  donde_se_carga: string;
  pantalla: string;
  departamentos: string[];
  reglas_de_mapeo: number;
  historico: Record<string, number>;
  referencia_usd: number;
  referencia_anio: number | null;
  escenario_usd: number;
}
export interface AvisoObligatorias {
  hay_lista: boolean;
  generado: string;
  obligatorias: number;
  vacio: boolean;
  faltan: LineaObligatoria[];
  presentes: LineaObligatoria[];
  cuantas_faltan: number;
  magnitud_historica_usd: number;
  meses_revisados: number[];
  meses_no_revisados: number[];
  motivo_meses_no_revisados: string;
  etiqueta?: string;
  texto?: string;
}
export interface FilaReporteObligatorias extends Partial<AvisoObligatorias> {
  scenario_id: string;
  etiqueta: string;
  type?: string;
  version?: string;
  year?: number;
  status?: string;
  actuals_through?: number;
  error?: string;
}
export interface ReporteObligatorias {
  generado: string;
  criterio: { umbral_anual_usd?: number; anos_historicos?: string[]; regla?: string[] };
  obligatorias: number;
  escenarios: FilaReporteObligatorias[];
}
export interface ListaObligatorias {
  _nota: string[];
  generado: string;
  criterio: { umbral_anual_usd?: number; anos_historicos?: string[]; regla?: string[] };
  lineas: LineaObligatoria[];
}

export async function getAvisoObligatorias(scenarioId: string): Promise<AvisoObligatorias> {
  return api.get<AvisoObligatorias>(`/lineas-obligatorias/${encodeURIComponent(scenarioId)}/`);
}
export async function getListaObligatorias(): Promise<ListaObligatorias> {
  return api.get<ListaObligatorias>(`/lineas-obligatorias/lista/`);
}
export async function getReporteObligatorias(anio?: number): Promise<ReporteObligatorias> {
  const q = anio ? `?anio=${anio}` : "";
  return api.get<ReporteObligatorias>(`/lineas-obligatorias/reporte/${q}`);
}

// ── Semillas de arranque, POR PROPIEDAD ────────────────────────────────────
//
// Dos listas de Corcovado vivian escritas a mano dentro de estas pantallas: las
// tarifas del paquete con que el Checkbook llena doce meses de ingreso, y las
// nueve reasignaciones de puesto de la plantilla de Salary. Viajaban en el
// bundle, asi que una propiedad nueva abria la pantalla con el producto de otro
// hotel y a un clic de guardarlo. Ahora viven en
// `backend/app/seed_data/<HOTEL_ID>/` y se piden por aca.
//
// `seeded: false` NO es un error: es una propiedad que todavia no cargo lo
// suyo, y la pantalla lo dice en vez de rellenarlo.
export interface DriverRates {
  food: number; tours: number; transport: number; nights_per_stay: number;
  bev_ratio: number; retail_pct: number; innoceana_pct: number;
  sust_rate: number; sust_non_pay: number;
}
export async function getDriverRatesSeed(): Promise<{ seeded: boolean; tarifas: Partial<DriverRates> }> {
  return api.get(`/semillas/driver-rates/`);
}

export interface ReasignacionSalario {
  name: string; legacy: string; source: string; target: string; fte: number;
}
export async function getReasignacionesSalarioSeed(): Promise<{ seeded: boolean; reasignaciones: ReasignacionSalario[] }> {
  return api.get(`/semillas/reasignaciones-salario/`);
}

// ─── Catálogo de departamentos (B6.4) ────────────────────────────────────────
//
// La PUERTA que faltaba. El motor ya leía `department_catalog`
// (`pl_engine.set_dept_catalog()` corre en el startup), pero la tabla solo se
// cambiaba por SQL o migración: un clon no podía renombrar nada sin que alguien
// escribiera código.
//
// ⚠️ No hay `delete`. Un departamento se DESACTIVA. Borrar libera el código y el
// día que alguien cree otro podría reutilizarlo, apuntando historia vieja a algo
// que no es — la misma regla que los códigos de categoría de habitación.
export interface DeptCatalogo {
  dept_code: string; dept_name: string; name_en: string; name_aliases: string[];
  default_pl_group: string; pl_kind: string; is_revenue_dept: boolean;
  is_allocation_source: boolean; room_set: boolean;
  parent_dept_code: string | null; display_order: number; active: boolean;
}
export interface DeptCatalogoResp {
  departamentos: DeptCatalogo[]; grupos: string[]; pl_kinds: string[];
}
export async function getDeptCatalogo(): Promise<DeptCatalogoResp> {
  return api.get(`/department-catalog/`);
}
export async function crearDept(body: Partial<DeptCatalogo>): Promise<{ ok: boolean; departamento: DeptCatalogo; aviso: string }> {
  return api.post(`/department-catalog/`, body);
}
// `dept_code` NO va en el cuerpo: el código no se edita jamás.
export async function editarDept(code: string, body: Partial<DeptCatalogo>): Promise<{ ok: boolean; departamento: DeptCatalogo; cambios: string[]; aviso: string }> {
  return api.put(`/department-catalog/${encodeURIComponent(code)}/`, body);
}

// ─── Break-Even (Fase 1) ─────────────────────────────────────────────────────
//
// ⚠️ `data_version` Y `scenario_id` van los DOS, y el backend exige que
// coincidan. No es redundancia: la versión sola no alcanza para elegir entre
// seis presupuestos 2027, y el escenario solo haría decorativo al parámetro que
// el spec puso obligatorio — un equilibrio calculado sobre la base equivocada
// se ve idéntico a uno correcto.
export type DataVersion = "ACTUAL" | "BUDGET" | "FORECAST";

export interface BeDepto {
  slug: string; name: string; display_order: number;
  generates_revenue: boolean; dept_codes: string; status: string; activo: boolean;
}
export interface BeFila {
  id: string; dept_code: string; account: string; account_name: string;
  pl_line: string; be_section: string; original_class: string;
  pct_variable: number; pct_fixed: number; map_source: string;
  excluded_from_be: boolean;
  amount: number; amount_variable: number; amount_fixed: number;
  updated_at: string | null;
}
export interface BeResultado {
  scenario_id: string; data_version: DataVersion; month: number;
  resumen: {
    revenue: number; variable_cost: number; fixed_cost: number;
    excluded_cost: number; contribution_margin: number; cm_pct: number;
    ebt: number; net: number;
  };
  equilibrio: {
    be_revenue: number | null; be_pct_of_revenue: number | null;
    margin_of_safety: number | null; margin_of_safety_pct: number | null;
    operating_leverage: number | null;
    /** Por qué vino en `null`. Vacío si trae número. */
    operating_leverage_motivo?: string;
    be_revenue_monthly_linear: number | null; es_prorrateo_lineal: boolean;
  };
  habitaciones: {
    rooms_mix: number | null; be_room_nights: number | null;
    be_occupancy: number | null; be_trevpar: number | null;
    supone_mezcla_constante: boolean;
  };
  por_departamento: {
    slug: string; variable_cost: number; fixed_cost: number;
    excluded_cost: number; total_cost: number; revenue: number;
    contribution_margin: number; cm_pct: number | null;
  }[];
  motivo: string; sin_clasificar: number; reglas_huerfanas: number;
}

export async function getBeDeptos(): Promise<{ departamentos: BeDepto[] }> {
  return api.get(`/break-e/departments/`);
}
export async function getBeResultado(scenarioId: string, dataVersion: DataVersion, month = 0): Promise<BeResultado> {
  return api.get(`/break-e/result/?scenario_id=${scenarioId}&data_version=${dataVersion}&month=${month}`);
}
export async function getBeClasificacion(deptSlug: string, scenarioId: string, dataVersion: DataVersion, month = 0): Promise<{ departamento: { slug: string; name: string; generates_revenue: boolean }; filas: BeFila[]; lineas_linea: number }> {
  return api.get(`/break-e/classification/?dept_slug=${encodeURIComponent(deptSlug)}&scenario_id=${scenarioId}&data_version=${dataVersion}&month=${month}`);
}
export async function getBeSinClasificar(scenarioId: string, dataVersion: DataVersion, month = 0): Promise<{ sin_regla: { dept_code: string; account: string; pl_line: string; amount: number }[]; reglas_huerfanas: string[] }> {
  return api.get(`/break-e/unclassified/?scenario_id=${scenarioId}&data_version=${dataVersion}&month=${month}`);
}
// `pct_variable` es lo ÚNICO editable. El % fijo se deriva, nunca se manda.
export async function setBePct(rowId: string, pctVariable: number): Promise<{ ok: boolean; pct_variable: number; pct_fixed: number }> {
  return api.patch(`/break-e/classification/${rowId}/`, { pct_variable: pctVariable });
}
export async function setBePctMasivo(body: { pct_variable: number; row_ids?: string[]; department_slug?: string; be_section?: string }): Promise<{ ok: boolean; actualizadas: number }> {
  return api.post(`/break-e/classification/bulk/`, body);
}
export async function resetBeDepto(deptSlug: string): Promise<{ ok: boolean; restablecidas: number }> {
  return api.post(`/break-e/classification/${encodeURIComponent(deptSlug)}/reset/`, {});
}

// ─── Break-Even Fase 2 ───────────────────────────────────────────────────────
export interface BeSensibilidad {
  ocupaciones: number[]; factores_adr: number[];
  celdas: (number | null)[][];
  celda_presupuesto: [number, number] | null;
  motivo: string;
  base: { cm_pct: number; fixed_cost: number; adr: number; rooms_mix: number; rooms_available: number };
  supuestos: string[];
}
export interface BeMensual {
  meses: { month: number; revenue: number; variable_cost: number; fixed_cost: number;
           cm_pct: number | null; be_revenue: number | null; holgura: number | null;
           motivo: string; cierra: boolean }[];
  suma_be_mensual: number | null;
  nota: string;
}
export async function getBeSensibilidad(scenarioId: string, dataVersion: DataVersion, r: { occ_min: number; occ_max: number; occ_paso: number; adr_min: number; adr_max: number; adr_paso: number }): Promise<BeSensibilidad> {
  const q = new URLSearchParams({ scenario_id: scenarioId, data_version: dataVersion,
    occ_min: String(r.occ_min), occ_max: String(r.occ_max), occ_paso: String(r.occ_paso),
    adr_min: String(r.adr_min), adr_max: String(r.adr_max), adr_paso: String(r.adr_paso) });
  return api.get(`/break-e/sensitivity/?${q}`);
}
export async function getBeMensual(scenarioId: string, dataVersion: DataVersion): Promise<BeMensual> {
  return api.get(`/break-e/monthly/?scenario_id=${scenarioId}&data_version=${dataVersion}`);
}

// ─── Break-Even · comparar 4 versiones (en NOCHES) ───────────────────────────
export interface BeComparar {
  modo: "mes" | "ytd" | "full"; month: number; meses: number[];
  versiones: {
    scenario_id: string; nombre: string; data_version: DataVersion;
    nights_available: number | null; nights_occupied: number | null;
    occupancy_pct: number | null; adr: number | null;
    variable: number | null; fixed: number | null; total_cost: number | null;
    average_expense_per_month: number | null;
    revenue_per_night: number | null; variable_cost_per_night: number | null;
    contribution_per_night: number | null;
    be_nights: number | null; be_occupancy_pct: number | null;
    variance_nights: number | null; pierde_por_noche: boolean;
    sin_noches: boolean;
    validacion: {
      variable_cost: number | null; fix_amount: number | null;
      total_cost: number | null; incomes: number | null; excluded: number | null;
      /** El costo del MISMO periodo según el P&L: el número traído de afuera
       *  que convierte esta fila en un control. */
      costo_del_pl: number | null;
      diferencia: number | null;
      /** ⚠️ `null` = **sin control**, que NO es lo mismo que cuadra. */
      cuadra: boolean | null;
    };
  }[];
}
export async function getBeComparar(ids: string[], modo: "mes" | "ytd" | "full", month = 0): Promise<BeComparar> {
  const q = new URLSearchParams({ scenarios: ids.join(","), modo, month: String(month) });
  return api.get(`/break-e/compare/?${q}`);
}

// ── Owners Q — reporte mensual al propietario (POR/PAR) ──────────────────────
// El nombre interno es "Owners Q"; el archivo que se entrega se sigue
// llamando `Statement of Income`.

export interface OwnersQCelda { [columna: string]: string | null }

export interface OwnersQFila {
  row_no: number;
  report_code: string;
  label: string;
  indent: number;
  line_type: "STAT" | "HEADER" | "DETAIL" | "SUBTOTAL" | "CALC";
  nature: "stat" | "header" | "revenue" | "expense" | "profit" | "signed";
  celdas: OwnersQCelda;
}

export interface OwnersQExcepcion {
  dept_code: string; account_code: string; monto: string;
  fila_destino: string; motivo: string; bloque?: string;
}

export interface OwnersQBloque {
  escenario_id: string | null;
  etiqueta: string;
  tipo: string | null;
  anio: number;
  mes: number;
  periodo: string;
  periodo_etiqueta: string;
  por_defecto: boolean;
}

export interface OwnersQEscenario {
  id: string; etiqueta: string; tipo: string;
  anio: number; version: string; actuals_through: number;
}

/** Las tres posiciones del reporte. `budget` y `py` son COLUMNAS del formato, no una
 *  obligación sobre qué escenario va ahí. */
export interface OwnersQSeleccion {
  escenario?: string | null;
  /** `M01`..`M12`, `Q1`..`Q4` o `FY`. */
  periodo?: string | null;
}

export interface OwnersQPeriodo {
  clave: string; etiqueta: string; tipo: "mes" | "trimestre" | "anio";
  mes_cierre: number;
}

export interface OwnersQReporte {
  report_key: string;
  entidad: string; anio: number; mes: number;
  bloques: Record<"actual" | "budget" | "py", OwnersQBloque>;
  es_estandar: boolean;
  periodo: string;
  periodo_etiqueta: string;
  /** Solo un mes simple es el estándar; un trimestre o el año no. */
  es_un_mes: boolean;
  periodos_disponibles: OwnersQPeriodo[];
  convencion: "raw" | "favorable";
  mapping_version: string;
  rooms_available_ptd: number;
  rooms_available_ytd: number;
  escenarios: { actual: string | null; budget: string | null; py: string | null };
  columnas: string[];
  filas: OwnersQFila[];
  identidades_falladas: { identidad: string; esperado: string; obtenido: string; delta: string; columna: string }[];
  verificacion_d1: { ok: boolean | null; brecha?: string; rev_rooms_other?: string; delta?: string; motivo?: string };
  excepciones: OwnersQExcepcion[];
}

export interface OwnersQSnapshot {
  id: string; anio: number; mes: number; version: number;
  convencion: string; mapping_version: string;
  enviado_el: string | null; nota: string;
}

type OwnersQOpts = {
  entidad?: string;
  convencion?: string;
  seleccion?: Partial<Record<"actual" | "budget" | "py", OwnersQSeleccion>>;
};

function paramsOwnersQ(anio: number, periodo: string, opts: OwnersQOpts) {
  const q = new URLSearchParams({
    entidad: opts.entidad ?? "CWL", anio: String(anio), periodo,
    convencion: opts.convencion ?? "favorable",
  });
  for (const pos of ["actual", "budget", "py"] as const) {
    const sel = opts.seleccion?.[pos];
    if (sel?.escenario) q.set(`escenario_${pos}`, sel.escenario);
    if (sel?.periodo) q.set(`periodo_${pos}`, sel.periodo);
  }
  return q;
}

export async function getOwnersQ(
  anio: number, periodo: string, opts: OwnersQOpts = {},
): Promise<OwnersQReporte> {
  return api.get<OwnersQReporte>(`/reports/owners-q/?${paramsOwnersQ(anio, periodo, opts)}`);
}

export async function getOwnersQPeriodos(): Promise<OwnersQPeriodo[]> {
  return api.get<OwnersQPeriodo[]>(`/reports/owners-q/periodos/`);
}

export async function getOwnersQEscenarios(entidad = "CWL"): Promise<OwnersQEscenario[]> {
  return api.get<OwnersQEscenario[]>(`/reports/owners-q/escenarios/?entidad=${entidad}`);
}

export async function getOwnersQCobertura(): Promise<{
  ok: boolean; lineas_en_reglas: number; lineas_ruteadas: number;
  huerfanas: string[]; ruteadas_sin_regla: string[]; destino_inexistente: string[];
}> {
  return api.get(`/reports/owners-q/cobertura/`);
}

export async function getOwnersQSnapshots(entidad = "CWL"): Promise<OwnersQSnapshot[]> {
  return api.get<OwnersQSnapshot[]>(`/reports/owners-q/snapshots/?entidad=${entidad}`);
}

export async function crearOwnersQSnapshot(body: {
  entidad?: string; anio: number; mes: number; convencion?: string; nota?: string;
}): Promise<{ ok: boolean; id: string; version: number }> {
  return api.post(`/reports/owners-q/snapshots/`, body);
}

export async function downloadOwnersQExcel(
  anio: number, periodo: string, opts: OwnersQOpts = {},
): Promise<Blob> {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const q = paramsOwnersQ(anio, periodo, opts);
  const res = await fetch(`${base}/reports/owners-q/excel/?${q}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.blob();
}

// ── Costos para Negociación de Grupos ───────────────────────────────────────
//
// ⚠️ Este tarifario NO es el de `/revenue/rack-rates`. Aquél vive en el
// escenario y MUEVE el ingreso del presupuesto; éste vive en el módulo y es
// sólo la referencia desde la que se negocia. Editarlo no mueve ningún P&L, y
// es a propósito: el módulo entero se sostiene en que ningún piso dependa del
// precio.

export type MesRack = { mes: number; rack: string; neto: string; pax: string };
export type CategoriaRack = {
  room_type_code: string; nombre: string; orden: number;
  unidades: number; meses: MesRack[];
};

export async function getTarifarioGrupos(): Promise<{ categorias: CategoriaRack[] }> {
  return api.get(`/costos-grupos/tarifario/`);
}

export type FilaRackGuardar = {
  room_type_code: string; mes: number; rack: string; neto: string; pax: string;
};

export async function saveTarifarioGrupos(
  filas: FilaRackGuardar[],
): Promise<{ guardadas: number }> {
  return api.put(`/costos-grupos/tarifario/`, { filas });
}

export type PisosTemporada = {
  marginal: string; departamental: string; integral: string;
  con_margen: string; costo_propio: string; overhead_unitario: string;
  meses: number[]; meses_con_ocupacion: number[];
};
export type FilaDescuento = {
  mes: number; temporada: string; cerrado: boolean;
  categoria: string; orden: number;
  rack: string; piso: string; descuento_max: string; alcanza: boolean;
};
export type DescuentosGrupos = {
  escenario_costos: string; comision: string; factor_neto: string | null;
  marginal_estimado: boolean;
  pisos: Record<string, PisosTemporada>;
  filas: FilaDescuento[];
};

export async function getDescuentosGrupos(): Promise<DescuentosGrupos> {
  return api.get(`/costos-grupos/descuentos/`);
}

// ── Simulador de grupos ─────────────────────────────────────────────────────
//
// ⚠️ Son DOS funciones contra DOS endpoints, no una con un parámetro. En modo
// Ventas el costo **nunca llega al navegador**: no se esconde con CSS ni con
// un `if` de render, no viaja. Un `?ocultar_costos` que alguien olvide poner
// filtra el costo y no falla nada.

export type Cotizacion = {
  habitaciones: number; noches: number; pax: number; mes: number;
  precio_pax_noche?: string; amenidades_usd?: string;
};

export type SimulacionGrupo = {
  escenario: string; mes: number; temporada: string; comision: string;
  grupo: Record<string, string>;
  costo: Record<string, string>;
  desplazamiento: {
    aplica: boolean; motivo: string; noches: string; adr_esperado: string;
    contribucion: string; ocupacion_pct: string; habitaciones_libres: string;
  };
  escalones: { descripcion: string; driver: string; umbral: string; costo: string }[];
  minimos: {
    por_pax_noche: Record<string, string>;
    por_pax_estadia: Record<string, string>;
    ingreso: Record<string, string>;
  };
  propuesta: {
    ingreso: string | null; margen: string | null;
    zona: string | null; autoriza: string | null;
  };
  marginal_estimado: boolean;
  prorrateados: string[];
};

export type SalidaVentas = {
  mes: number; temporada: string;
  grupo: Record<string, string>;
  precio_minimo: {
    recomendado_pax_noche: string; recomendado_pax_estadia: string;
    recomendado_total: string;
    limite_pax_noche: string; limite_pax_estadia: string; limite_total: string;
  };
  zona: string | null; autoriza: string | null;
  bajo_el_limite_requiere: string;
};

export async function simularGrupo(c: Cotizacion): Promise<SimulacionGrupo> {
  return api.post(`/costos-grupos/simular/`, c);
}

export async function salidaVentasGrupo(c: Cotizacion): Promise<SalidaVentas> {
  return api.post(`/costos-grupos/salida-ventas/`, c);
}

// ── SUMMARY COST: la vista de entrada del tab Cost ──────────────────────────
export type ResumenGrupos = {
  vacio?: boolean; motivo?: string; escenario: string;
  seleccion?: { meses: number[]; meses_con_ocupacion: number[];
                cerrados: number[]; temporadas: string[] };
  parametros?: Record<string, string>;
  bloque_a?: { concepto: string; costo: string; revenue_neto: string;
               factor_neto: string; margen_integral: string;
               capa1: string; capa2: string }[];
  bloque_b?: {
    hab_propio_por_ocupada: string; fb_propio_por_huesped: string;
    tours_propio_por_huesped: string; transp_propio_por_ocupada: string;
    spa_propio_por_huesped: string; overhead_por_disponible: string;
    overhead_por_ocupada: string;
    pisos: Record<string, string>; marginal_estimado: boolean;
  };
  bloque_c?: {
    tarifa: string; requerido: string; costo_propio_rooms: string;
    overhead: string; no_operativo: string; capital: string;
    contribucion_ajena: string; hab_ocupadas: string;
    detalle_contribucion: Record<string, string>;
    adr_real: string; brecha: string;
  };
  calidad?: string[];
  escenario_id?: string;
  // Cuál es la base configurada, y si se está mirando otra.
  base_configurada?: string;
  es_base?: boolean;
};

export async function getResumenGrupos(sel: SeleccionCostos = {}): Promise<ResumenGrupos> {
  return api.get(`/costos-grupos/resumen/${qsCostos(sel)}`);
}

// ── Guillermo ───────────────────────────────────────────────────────────────
//
// ⚠️ El estado SIEMPRE sale del backend (`docs/GUILLERMO.md` §10.2.7). El
// componente no infiere ni recuerda nada: si la UI y la base discrepan, gana
// la base.

export type EstadoGuillermo = {
  state: "off" | "idle" | "running" | "pending" | "stuck";
  color: "gris" | "verde" | "ambar" | "rojo";
  pendientes: number;
  mensaje: string;
  detalles: string[];
  autonomia: string;
  gato_encendido: boolean;
  ultima_ronda: string | null;
  reportes_esperados: number;
  sin_manifiesto: boolean;
};

export type LoteImport = {
  id: string; estado: string; modo: string; endpoint: string; origen: string;
  scenario_id: string | null; disparado_por: string; iniciado_en: string | null;
  archivos: { nombre: string; checksum: string; tamano: number; subido_por: string }[];
};

export type ExcepcionGuillermo = {
  id: string; batch_id: string; tipo: string; linea: number;
  valor_crudo: string; valor_normalizado: string; destino_sugerido: string;
  confianza: string; rationale: string; estado: string; creado_en: string | null;
};

export async function getEstadoGuillermo(): Promise<EstadoGuillermo> {
  return api.get(`/guillermo/estado/`);
}
export async function getConfigGuillermo(): Promise<{
  parametros: { clave: string; valor: string; descripcion: string }[];
}> {
  return api.get(`/guillermo/config/`);
}
export async function saveConfigGuillermo(clave: string, valor: string) {
  return api.put<{ clave: string; valor: string }>(`/guillermo/config/`, { clave, valor });
}
// ── Propuesta de descuentos · costo fully loaded (COSTOS_GRUPOS §5) ─────────
//
// El cuadro que la Junta aprobó. ⚠️ `advertencia` viaja EN LA RESPUESTA a
// propósito: estos porcentajes fijan techos de comisión, no pisos de precio, y
// esa distinción no puede quedar en un comentario del código.
export type FilaFullyLoaded = {
  concepto: string;
  revenue: string;
  costo_departamento: string;
  costo_departamento_pct: string;
  overhead: string;
  overhead_pct: string;
  fee: string;
  fee_pct: string;
  costo_fully_loaded_pct: string;
  utilidad: string;
  margen_actual: string;
  descuento_maximo: string;
  cubre: boolean;
  estado: string;
};

export type FullyLoaded = {
  vacio: boolean;
  motivo?: string;
  escenario: string;
  escenario_id?: string;
  // Cuál es la base configurada, y si se está mirando otra. Sin esto, un piso
  // calculado sobre otro escenario parece el piso oficial.
  base_configurada?: string;
  es_base?: boolean;
  seleccion?: { etiqueta: string; periodo: string; meses: number[]; temporadas: string[] };
  totales: {
    revenue: string; costo_departamental: string; overhead: string;
    fee: string; utilidad: string; margen_ponderado: string;
    overhead_pct: string;
  };
  filas: FilaFullyLoaded[];
  pierden: string[];
  advertencia: string;
};

// Los tres selectores del §5, independientes y combinables.
export type SeleccionCostos = {
  periodo?: "full" | "ytd" | "mes";
  mes?: number;
  /** Los meses marcados. ⚠️ Si hay alguno, MANDA sobre `periodo`. */
  meses?: number[];
  temporada?: string;
  escenarioId?: string;
};

function qsCostos(sel: SeleccionCostos): string {
  const q = new URLSearchParams();
  if (sel.periodo) q.set("periodo", sel.periodo);
  if (sel.periodo === "mes" && sel.mes) q.set("mes", String(sel.mes));
  if (sel.meses?.length) q.set("meses", sel.meses.join(","));
  if (sel.temporada) q.set("temporada", sel.temporada);
  // ⚠️ Es un filtro de LECTURA: elegir otra base no reescribe
  // `cfg_parametros.escenario_base`, que es el que gobierna los Pisos.
  if (sel.escenarioId) q.set("escenario_id", sel.escenarioId);
  const qs = q.toString();
  return qs ? `?${qs}` : "";
}

export async function getFullyLoaded(sel: SeleccionCostos = {}): Promise<FullyLoaded> {
  return api.get(`/costos-grupos/fully-loaded/${qsCostos(sel)}`);
}

// ── Master Data · «Mi Resumen» (COSTOS_GRUPOS §5, sub-tab 3) ────────────────
//
// Réplica del `FULL YEAR ANALYSIS 2026.xlsx` del owner. Vista DERIVADA: cada
// cifra sale del motor del escenario, no se carga nada.
export type FilaMaster = {
  label: string;
  formato: string;                       // usd | num | num2 | pct
  nota: string;
  es_total?: boolean;
  valores: Record<string, string>;       // una clave por columna de temporada + ANIO
};
export type BloqueMaster = { clave: string; titulo: string; filas: FilaMaster[] };
export type ColumnaMaster = {
  escenario: { id: string; tipo: string; anio: number; version: string; etiqueta: string };
  bloques: BloqueMaster[];
};

export async function getMasterDataCostos(a: string, b?: string): Promise<{
  columnas: ColumnaMaster[];
  // ⚠️ Las columnas de temporada las decide `cfg_temporadas`, no el frontend:
  // una lista escrita acá dejaría afuera la temporada que alguien agregue.
  columnas_clave: string[];
  meses_por_columna: Record<string, number[]>;
  meses_sin_temporada: number[];
}> {
  const q = new URLSearchParams({ a });
  if (b) q.set("b", b);
  return api.get(`/costos-grupos/master-data/?${q.toString()}`);
}

// ── Escalones de costo (Costos de Grupos §4.4) ──────────────────────────────
//
// ⚠️ La tabla existía y el motor la leía, pero nadie la podía llenar: sin
// escalones cargados el modelo SUBESTIMA los grupos grandes, que son justo los
// que se negocian. `sin_cargar` viene explícito para que la pantalla pueda
// decir «nadie los cargó» en vez de mostrar un cero que se lee como «no aplica».
export type Escalon = {
  id?: string;
  dept_code: string;
  driver: string;
  umbral: string;
  costo_adicional: string;
  descripcion: string;
  activo: boolean;
};

export async function getEscalones(): Promise<{
  escalones: Escalon[]; drivers: string[]; sin_cargar: boolean;
}> {
  return api.get(`/costos-grupos/escalones/`);
}
export async function crearEscalon(e: Escalon) {
  return api.post<Escalon>(`/costos-grupos/escalones/`, e);
}
export async function editarEscalon(id: string, e: Escalon) {
  return api.put<Escalon>(`/costos-grupos/escalones/${encodeURIComponent(id)}/`, e);
}
export async function borrarEscalon(id: string) {
  return api.delete<{ borrado: string }>(`/costos-grupos/escalones/${encodeURIComponent(id)}/`);
}

// ── Avisos por correo (pendiente 20) ────────────────────────────────────────
//
// ⚠️ Contesta POR QUÉ no puede mandar. Un correo que no sale porque falta una
// variable es indistinguible de uno que no salía porque no había nada que
// avisar — y esa diferencia es la que sostiene el dead-man switch.
export type EstadoCorreo = {
  configurado: boolean;
  servidor: string;
  remitente: string;
  destinatarios: string[];
  motivo: string;
  clave_destinatarios: string;
  variables_de_entorno: string[];
};

export async function getCorreoGuillermo(): Promise<EstadoCorreo> {
  return api.get(`/guillermo/correo/`);
}

// ── El manifiesto: qué reportes espera ESTA propiedad ───────────────────────
//
// ⚠️ Es la decisión D-1 y es POR PROPIEDAD (owner, 2026-08-20: «cada propiedad
// decide cómo manejar a Guillermo»). Una instalación nueva nace con el
// manifiesto VACÍO a propósito: no reclama nada que su owner no haya prometido.
export type ReporteEsperado = {
  id?: string;
  report_id: string;
  notas: string;
  frecuencia: string;
  verifica: string;
  objetivo: string;
  gracia_dias: number;
  obligatorio: boolean;
  activo: boolean;
  patron: string;
  formato: string;
  tamano_min: number;
};

export async function getManifiestoGuillermo(): Promise<{
  hotel_id: string;
  reportes: ReporteEsperado[];
  verificaciones: string[];
  frecuencias: string[];
}> {
  return api.get(`/guillermo/manifiesto/`);
}
export async function crearEsperadoGuillermo(r: ReporteEsperado) {
  return api.post<ReporteEsperado>(`/guillermo/manifiesto/`, r);
}
export async function editarEsperadoGuillermo(id: string, r: ReporteEsperado) {
  return api.put<ReporteEsperado>(`/guillermo/manifiesto/${encodeURIComponent(id)}/`, r);
}
export async function borrarEsperadoGuillermo(id: string) {
  return api.delete<{ borrado: string }>(`/guillermo/manifiesto/${encodeURIComponent(id)}/`);
}

export async function getImportacionesGuillermo(): Promise<{ lotes: LoteImport[] }> {
  return api.get(`/guillermo/importaciones/`);
}
export async function getExcepcionesGuillermo(
  estado = "pending",
): Promise<{ excepciones: ExcepcionGuillermo[] }> {
  return api.get(`/guillermo/excepciones/?estado=${encodeURIComponent(estado)}`);
}
export async function resolverExcepcionGuillermo(
  id: string, decision: "approved" | "rejected", destino?: string,
) {
  return api.put(`/guillermo/excepciones/${id}/`, { decision, destino });
}

export type ReporteFaltante = {
  report_id: string; etiqueta: string; frecuencia: string;
  como_se_mide: string; al_dia: boolean; ultimo: string | null;
  faltan: string[]; mensaje: string;
};

export async function getFaltantesGuillermo(): Promise<{
  reportes: ReporteFaltante[]; al_dia: boolean; cuantos_faltan: number;
}> {
  return api.get(`/guillermo/faltantes/`);
}

export type CuadreEscenario = {
  escenario: string; estado: "cuadra" | "no_cuadra" | "sin_verificar";
  manda: string; motivo: string; meses_evaluados: number[];
  conocida: string; peor_diferencia: number;
  que_hacer: string; meses_culpables: number[];
  diferencias: { total: string; resumen: number; detalle: number; diferencia: number }[];
};

export async function getCuadreGuillermo(): Promise<{
  resumen: {
    total: number; cuadran: number; no_cuadran: number;
    descuadres_nuevos: number; descuadres_conocidos: number;
    sin_verificar: number; todo_cuadra: boolean; hay_ciegos: boolean;
  };
  escenarios: CuadreEscenario[];
}> {
  return api.get(`/guillermo/cuadre/`);
}

export type NivelGuillermo = {
  clave: string; nombre: string; resumen: string;
  capacidades: Record<string, boolean>;
};

export async function getNivelesGuillermo(): Promise<{
  actual: string; niveles: NivelGuillermo[];
}> {
  return api.get(`/guillermo/niveles/`);
}

export type RecalculoEscenario = {
  id: string; nombre: string; enllavado: boolean; ultimo: string | null;
};

export async function getRecalculosGuillermo(): Promise<{
  escenarios: RecalculoEscenario[];
}> {
  return api.get(`/guillermo/recalculos/`);
}

export async function correrRecalculoGuillermo(scenario_ids: string[]): Promise<{
  corridos: number; saltados: number; fallaron: number;
  resultados: { escenario: string; estado: string; detalle: string }[];
}> {
  return api.post(`/guillermo/recalcular/`, { scenario_ids });
}

export type ConexionIA = {
  conectado: boolean; motivo: string;
  modelo_chico: string; modelo_grande: string;
  donde_va_la_llave: string;
  para_que_se_usa: string[]; para_que_NO_se_usa: string[];
  nunca_se_envia: string[];
  ejemplo_de_payload: Record<string, unknown>;
  ejemplo_limpio: boolean; ejemplo_motivos: string[];
  system_prompt: string;
};

export async function getIAGuillermo(): Promise<ConexionIA> {
  return api.get(`/guillermo/ia/`);
}

export async function correrRondaGuillermo(): Promise<{
  resultado: string; detalle: string; nuevas: number;
  cerradas: number; abiertas: number;
}> {
  return api.post(`/guillermo/ronda/`, {});
}
