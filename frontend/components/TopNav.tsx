"use client";
import { useState, useRef, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { getStoredUser, logout, type AuthUser } from "@/lib/api";
import LanguageSwitch from "@/components/LanguageSwitch";
import { useHotel } from "@/lib/useHotel";
import { HOTEL_ID } from "@/lib/hotel";
import { getTabsApagados, alCambiarTabs, NADA_APAGADO, type TabsApagados }
  from "@/lib/tabsVisibles";

export interface MenuItem {
  /** Clave del namespace `nav.items` / `nav.headers`. */
  key: string;
  href?: string;
  disabled?: boolean;
  header?: boolean;   // sección dentro del dropdown (no es link)
  /**
   * La pantalla NO sirve de nada sin rol admin: su primera llamada ya devuelve
   * 403. Se ESCONDE, no se deshabilita — nadie tiene que ver una puerta que no
   * puede abrir.
   *
   * ⚠️ Marcá esto solo cuando el backend bloquee la pantalla ENTERA. Si lo que
   * pide admin es una acción de adentro, la pantalla se sigue mostrando: quien
   * no pueda hacer esa acción igual necesita ver el resto. Ejemplo real:
   * `/master-data/provisioning` tiene tres `PATCH` de admin, pero sus lecturas
   * son abiertas y la matriz la puede guardar cualquiera — esconderla le
   * sacaría a los colaboradores algo que hoy usan.
   */
  soloAdmin?: boolean;
}

export interface NavGroup {
  /** Clave del namespace `nav.groups`. */
  key: string;
  items: MenuItem[];
  href?: string;   // si está, es un tab de link directo (sin dropdown)
}

// Navegación reorganizada a los 7 lugares (ver REPORTES_SPEC.md / ROADMAP.md).
//
// Los rótulos NO están acá: viven en `messages/{es,en}.json` bajo `nav.*`. Lo
// que queda es la estructura —qué cuelga de qué y a dónde va— que es lo único
// que no cambia con el idioma. Al extraerlos se normalizó el spanglish: los
// términos hoteleros y los acrónimos USALI (P&L, GOP, Rack Rates, Cash Flow,
// Room Stats) se quedan en inglés en los dos idiomas por decisión del owner;
// se traduce el chrome.
// ⚠️ **Se EXPORTA a propósito.** Es la única lista de lo que existe en la app,
// y la pantalla de provisionamiento la lee de acá para saber qué se puede
// esconder. Copiarla al backend sería una segunda lista que habría que
// acordarse de actualizar — este proyecto ya pagó dos veces por una escrita a
// mano (el Club Madresal, y siete líneas de ingreso en Master Data).
export const NAV: NavGroup[] = [
  // Tab de link directo: el Dashboard es una sola pantalla, no un menú con una
  // sola opción adentro. Es el mismo cuadro que antes se abría con el logo.
  { key: "dashboard", href: "/dashboard", items: [] },
  {
    key: "scenarios",
    items: [
      { key: "scenarios", href: "/scenarios" },
      { key: "importActuals", href: "/admin/import-actuals" },
    ],
  },
  {
    key: "planning",
    items: [
      { key: "progress", header: true },
      { key: "command", href: "/command" },
      { key: "control", href: "/admin/control" },
      { key: "budget", header: true },
      { key: "bigPicture", href: "/planning/big-picture" },
      { key: "yearSetup", header: true },
      { key: "yearMasterData", href: "/revenue/master" },
      { key: "revenue", header: true },
      { key: "inventory", href: "/revenue/inventory" },
      { key: "availability", href: "/revenue/availability" },
      { key: "roomNights", href: "/revenue/room-nights" },
      { key: "rackRates", href: "/revenue/rack-rates" },
      { key: "occupancy", href: "/revenue/occupancy" },
      { key: "pax", href: "/revenue/pax" },
      { key: "channels", href: "/revenue/channels" },
      { key: "packageComponents", href: "/revenue/package-components" },
      { key: "netRate", href: "/revenue/net-rate" },
      { key: "spaCapture", href: "/revenue/spa" },
      { key: "club", href: "/revenue/club" },
      { key: "totalRevenue", href: "/revenue/total-revenue" },
      { key: "revenueCheckbook", href: "/revenue/checkbook" },
      { key: "payroll", header: true },
      { key: "payrollByDept", href: "/payroll/checkbook" },
      { key: "fteReport", href: "/payroll/fte" },
      { key: "payrollParams", href: "/payroll/params" },
      { key: "costs", header: true },
      { key: "costOfSales", href: "/costs/checkbook" },
      { key: "opexByDept", href: "/opex/checkbook" },
      { key: "ownerExpenses", href: "/nonop/checkbook" },
      { key: "managementFees", href: "/nonop/management-fees" },
      { key: "allocationConfig", href: "/allocations/config" },
      { key: "salaryAllocation", href: "/allocations/salary" },
      { key: "collaboration", header: true },
      { key: "teamBoard", href: "/board" },
      { key: "notes", href: "/notes" },
    ],
  },
  {
    key: "financials",
    items: [
      { key: "balanceSheet", href: "/pl/balance-sheet" },
      { key: "plFullYear", href: "/pl/full" },
      { key: "plSimplified", href: "/pl/simplified" },
    ],
  },
  {
    key: "board",
    items: [
      { key: "boardDeck", href: "/reports/junta" },
    ],
  },
  {
    key: "cashflow",
    items: [
      { key: "model", header: true },
      { key: "cashflowCriteria", href: "/reports/cashflow-criteria" },
      { key: "planning", header: true },
      { key: "cashflowBudget", href: "/reports/cashflow-budget" },
      { key: "cashflowDirect", href: "/reports/cashflow-directo" },
      { key: "projection", header: true },
      { key: "balanceSheetProjection", href: "/reports/balance-sheet-projection" },
      { key: "taxPanorama", href: "/reports/tax" },
    ],
  },
  {
    key: "reports",
    items: [
      { key: "pl", header: true },
      { key: "plFullDetail", href: "/reports/pl-full-detail" },
      { key: "plByDept", href: "/reports/pl-by-dept" },
      { key: "plByDeptCompare", href: "/reports/pl-by-dept-compare" },
      { key: "plYtd", href: "/reports/pl-ytd" },
      { key: "plFullExec", href: "/reports/pl-full" },
      { key: "execSummary", href: "/reports/summary" },
      { key: "ytdSummary", href: "/reports/ytd" },
      { key: "operations", header: true },
      { key: "revenueMix", href: "/reports/revenue-mix" },
      { key: "revenueByRoom", href: "/reports/revenue-by-room" },
      { key: "roomsSets", href: "/reports/rooms-sets" },
      { key: "payrollDeptReport", href: "/reports/payroll-dept" },
      { key: "payrollPositionReport", href: "/reports/payroll-by-position" },
      { key: "expenses", href: "/reports/expenses" },
      { key: "owners", header: true },
      { key: "ownerReport", href: "/reports/owner" },
      { key: "ownersQ", href: "/reports/owners-q" },
      { key: "opexCheckbook", href: "/reports/opex-checkbook" },
    ],
  },
  {
    // Cierre de mes. Es su propio menu y no un item dentro de Reports porque va
    // a crecer: el owner ya adelanto que le va a colgar mas pantallas.
    key: "monthEnd",
    items: [
      { key: "monthEndPL", href: "/month-end/pl" },
    ],
  },
  {
    key: "operationInsight",
    items: [
      { key: "opsSummary", href: "/operation-insight/summary" },
      { key: "roomStats", href: "/operation-insight/room-stats" },
      { key: "headcounts", href: "/operation-insight/headcounts" },
      { key: "opsKpi", href: "/operation-insight/ops-kpi" },
      { key: "onTheBooksFull", href: "/operation-insight/on-the-books" },
    ],
  },
  {
    key: "marketingInsight",
    items: [
      // ⚠️ «On the Books» y «Daily Occupancy Heatmap» se sacaron de acá el
      // 18-ago-2026: eran duplicados viejos de lo que vive en Operations →
      // Tab 8 (que tiene el heatmap como sub-tab 8.3). Dos puertas al mismo
      // dato, una de ellas sin los arreglos de hoy, es peor que una sola.
      { key: "channelMix", href: "/marketing-insight/channel-mix" },
      { key: "country", href: "/marketing-insight/country" },
    ],
  },
  {
    // Break-E: el punto de equilibrio. Grupo propio y no un item de Reportes
    // porque tiene sub-pantallas y una barra de contexto propia (escenario +
    // version de dato), no es una vista mas del P&L.
    key: "breakEven",
    items: [
      { key: "beResumen", href: "/break-e/resumen" },
      { key: "bePorDepartamento", href: "/break-e/por-departamento" },
      { key: "beSensibilidad", href: "/break-e/sensibilidad" },
      { key: "beMensual", href: "/break-e/mensual" },
      { key: "beComparar", href: "/break-e/comparar" },
      { key: "beConfiguracion", href: "/break-e/configuracion" },
      { key: "beSinClasificar", href: "/break-e/sin-clasificar" },
    ],
  },
  {
    // El tab COSTOS del spec (`COSTOS_GRUPOS.md` §5). El orden es deliberado:
    // el resumen va de primero, el detalle de cómo se llegó ahí vive detrás.
    // Hoy hay cuatro de los catorce sub-tabs; los demás se agregan acá
    // a medida que se construyen, y NO se ponen antes: un enlace a una
    // pantalla que no existe se ve igual que una que se rompió.
    key: "cost",
    items: [
      { key: "costSummary", header: true },
      { key: "costResumen", href: "/cost" },
      { key: "costDescuentos", href: "/cost/descuentos" },
      { key: "costMasterData", href: "/cost/master-data" },
      { key: "costEngine", header: true },
      { key: "costFloors", href: "/cost/pisos" },
      { key: "costEscalones", href: "/cost/escalones" },
      { key: "costApplication", header: true },
      { key: "costSimulator", href: "/cost/simulador" },
    ],
  },
  {
    key: "masterData",
    items: [
      { key: "exchangeRate", href: "/master-data/tipo-cambio" },
      { key: "roomSets", href: "/master-data/room-sets" },
      // La vista de LECTURA del mismo mapeo: las cinco preguntas del setup de
      // la cuenta, cruzadas contra los anos. Va pegada al mapeo porque es lo que
      // se revisa ANTES de clonarle la propiedad a otro hotel.
      // Las cuentas estadisticas SON cuentas (clase 9), asi que van al lado
      // del catalogo contable. Tabla aparte por debajo, una sola puerta aca.
      { key: "statistics", href: "/master-data/estadisticas" },
      // El mixer va en Master Data porque es donde se planifica el mix: los
      // tres canales de comision dejaron de digitarse y ahora se derivan de aca.
      { key: "canales", href: "/master-data/canales" },
      // Chequeo de la instalacion: existe por el clonado de propiedades,
      // pero sirve cualquier dia — la forma en que esto sale mal no da error.
      // El par del chequeo: aquel pregunta si la INSTALACION quedo sana,
      // este si el ESCENARIO tiene con que compararse. Los dos existen por
      // el clonado de propiedades — un clon hereda los agujeros del origen.
      // La PUERTA del catalogo (B6.4). El motor ya lo leia; lo que no habia
      // era donde editarlo: solo por SQL o migracion. Va pegado a
      // provisioning porque son el par — aquel decide QUIEN se ve en cada
      // propiedad, este QUE existe en el grupo.
      { key: "properties", disabled: true },
    ],
  },
  {
    // El menú tenía SOLO «Usuarios» y una entrada deshabilitada, así que
    // parecía vacío — el owner preguntó literalmente «no sé qué hay ahí».
    // Las otras tres pantallas de administración existían pero colgaban de
    // Planning, Escenarios y Master Data, donde nadie las buscaba.
    //
    // Siguen accesibles desde su menú de siempre: esto agrega el camino que
    // falta, no lo muda. Quien ya sabe dónde estaban no tiene que reaprender.
    key: "admin",
    items: [
      // `users` y `origenes` son las DOS únicas del sistema cuya primera
      // llamada exige admin (`/auth/users` y `/origenes/`): un colaborador no
      // ve nada ahí. Verificado endpoint por endpoint contra el backend, no
      // supuesto por el nombre del grupo.
      // Qué tabs y reportes ve esta propiedad. ⚠️ NO lleva `soloAdmin`: sus
      // lecturas son abiertas y esconder la pantalla que administra la barra
      // le sacaría a un colaborador la forma de entender por qué no ve algo.
      // ── La configuración que RE-EXPRESA los reportes ──────────────────
      //
      // Owner, 2026-08-20: «mover tabs a admin para proteger la información».
      // El criterio no es «es difícil»: es que **cambiarlo mueve lo que todos
      // leen**. Mover UNA cuenta del mapeo re-expresó 102 líneas del reporte
      // sin que ningún total avisara.
      //
      // ⚠️ Estar en Admin es NAVEGACIÓN, no permiso: la ruta sigue
      // respondiendo. Lo que protege de verdad es que el backend exija admin
      // para escribir — hecho en `mapping_api`. Las demás siguen abiertas y
      // están anotadas en `docs/PENDIENTES.md`.
      { key: "accountMapping", href: "/admin/mapping" },
      { key: "setupCuenta", href: "/master-data/setup-cuenta" },
      { key: "departamentos", href: "/master-data/departamentos" },
      { key: "provisioning", href: "/master-data/provisioning" },
      // Los dos chequeos del clonado: aquel pregunta si la INSTALACIÓN quedó
      // sana, éste si el ESCENARIO tiene con qué compararse.
      { key: "chequeo", href: "/master-data/chequeo" },
      { key: "lineasObligatorias", href: "/master-data/lineas-obligatorias" },
      { key: "cierrePeriodos", href: "/admin/cierre" },
      { key: "tabsProvisioning", href: "/admin/tabs" },
      { key: "users", href: "/admin/users", soloAdmin: true },
      { key: "origenes", href: "/admin/origenes", soloAdmin: true },
      { key: "guillermoCola", href: "/admin/guillermo" },
      { key: "apariencia", href: "/admin/apariencia" },
      { key: "control", href: "/admin/control" },
      { key: "importActuals", href: "/admin/import-actuals" },
      { key: "auditActivity", disabled: true },
    ],
  },
];

// El grupo Admin se renderiza aparte, fijo a la derecha. Se saca de `NAV` en vez
// de duplicarlo para que agregarle una pantalla siga siendo un solo lugar.
//
// ⚠️ Se busca sobre la lista YA FILTRADA por rol (`nav`), no sobre `NAV`. Si
// saliera de la constante, el filtro no lo alcanzaría y el tab de la derecha
// —justo el que tiene `Users`— seguiría mostrando todo.

/** Cuatro rótulos se acortan para que la barra entre sin scrollear; el nombre
 *  completo va en el tooltip para que no se pierda. */
const ROTULO_LARGO = ["financials", "cashflow", "operationInsight",
  "marketingInsight", "breakEven"];

/**
 * Un tab de la barra. **Solo el botón.**
 *
 * Antes cada tab traía su propio panel. Al pasar de uno a otro, el primero se
 * DESMONTABA y el segundo se MONTABA: por eso parpadeaba. Ahora el panel es
 * uno solo y vive en `TopNav`; acá queda el botón, que reporta su posición y
 * pide abrir o cerrar.
 */
function Tab({ group, open, activo, onAbrir, onCerrar, onToggle, registrar }: {
  group: NavGroup;
  open: boolean;
  activo: boolean;
  /** El mouse entró: pedir apertura (con intención, ver `TopNav`). */
  onAbrir: () => void;
  /** El mouse salió: pedir cierre, con gracia para cruzar el hueco. */
  onCerrar: () => void;
  /** Click en el tab: alterna. Nunca navega a una página índice vacía. */
  onToggle: () => void;
  /** Deja su elemento en el registro para que el panel sepa dónde anclarse. */
  registrar: (el: HTMLElement | null) => void;
}) {
  const tg = useTranslations("nav.groups");
  const tgf = useTranslations("nav.groupsFull");
  const largo = ROTULO_LARGO.includes(group.key) ? tgf(group.key) : undefined;

  // Tab de link directo (Dashboard): no abre panel.
  if (group.href) {
    return (
      <Link href={group.href} className="nav-nowrap" title={largo} style={{
        color: activo ? "var(--nav-fg-strong)" : "var(--nav-fg)",
        fontSize: "var(--nav-fs)", padding: "0 var(--nav-px)", height: "var(--nav-h)",
        display: "flex", alignItems: "center",
        textDecoration: "none",
        borderBottom: activo ? "2px solid var(--nav-accent)" : "2px solid transparent",
        transition: "color 0.15s, border-color 0.15s", flexShrink: 0,
      }}
        onMouseEnter={e => { onCerrar(); (e.currentTarget as HTMLElement).style.color = "var(--nav-fg-strong)"; }}
        onMouseLeave={e => { if (!activo) (e.currentTarget as HTMLElement).style.color = "var(--nav-fg)"; }}
      >{tg(group.key)}</Link>
    );
  }

  return (
    <button
      ref={registrar}
      data-nav-tab={group.key}
      onClick={onToggle}
      onMouseEnter={onAbrir}
      onMouseLeave={onCerrar}
      onFocus={onAbrir}
      aria-expanded={open}
      aria-haspopup="menu"
      className="nav-nowrap"
      title={largo}
      style={{
        color: activo || open ? "var(--nav-fg-strong)" : "var(--nav-fg)",
        fontSize: "var(--nav-fs)",
        padding: "0 var(--nav-px)",
        height: "var(--nav-h)",
        display: "flex",
        alignItems: "center",
        gap: 4,
        cursor: "pointer",
        background: "none",
        border: "none",
        borderBottom: activo ? "2px solid var(--nav-accent)" : "2px solid transparent",
        transition: "color 0.15s, border-color 0.15s",
        flexShrink: 0,
      }}
    >
      {tg(group.key)}
      <svg width="10" height="6" viewBox="0 0 10 6" fill="currentColor"
        style={{ opacity: 0.6, transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s" }}>
        <path d="M0 0l5 6 5-6z" />
      </svg>
    </button>
  );
}

/**
 * EL panel. Uno solo para los doce tabs.
 *
 * **Por qué uno solo (owner, 2026-08-19: «suavizar el movimiento»).** Con un
 * panel por tab, moverse entre dos es destruir uno y construir otro: no hay
 * nada que animar, así que parpadea por definición. Con uno solo que persiste,
 * cambiar de sección es mover una caja que ya existe — y eso sí se puede
 * deslizar.
 *
 * ⚠️ **La caja se MIDE, nunca se fija.** El interior va absoluto para no
 * arrastrar el tamaño del contenedor, y un `ResizeObserver` copia su medida al
 * contenedor, que es el que anima. Con altura fija, secciones con distinta
 * cantidad de opciones saltan; y Planning tiene 41 contra las 3 de Financials.
 *
 * ⚠️ **La opacidad del contenedor NO se anima al cambiar de sección** — eso
 * reintroduce el parpadeo que esto viene a sacar. Solo se anima al abrir desde
 * cero. Lo que se cruza al cambiar es el CONTENIDO, con su propia animación.
 */
function Panel({ grupo, ancla, cajaRef, onCerrar, onAbrir }: {
  grupo: NavGroup;
  ancla: { top: number; left: number };
  cajaRef: React.RefObject<HTMLDivElement>;
  onCerrar: () => void;
  onAbrir: () => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const ti = useTranslations("nav.items");
  const th = useTranslations("nav.headers");
  const tc = useTranslations("common");
  const interior = useRef<HTMLDivElement>(null);
  const [medida, setMedida] = useState<{ w: number; h: number } | null>(null);
  const [entrando, setEntrando] = useState(true);

  // Se mide el interior y se le copia al contenedor. Cada vez que cambia el
  // grupo, y también si el contenido cambia de tamaño por su cuenta.
  useEffect(() => {
    const el = interior.current;
    if (!el) return;
    const medir = () => setMedida({ w: el.offsetWidth, h: el.offsetHeight });
    medir();
    const ro = new ResizeObserver(medir);
    ro.observe(el);
    return () => ro.disconnect();
  }, [grupo.key]);

  // La animación de entrada corre UNA vez, al abrir desde cero. Después el
  // panel ya está en pantalla y lo único que se mueve es su caja.
  useEffect(() => {
    const t = setTimeout(() => setEntrando(false), 220);
    return () => clearTimeout(t);
  }, []);

  // Si el tab está muy a la derecha, el menú se sale de la pantalla: se corre
  // lo justo para que entre, nunca menos de 8px del borde.
  const ancho = medida?.w ?? 240;
  const izq = typeof window !== "undefined"
    ? Math.max(8, Math.min(ancla.left, window.innerWidth - ancho - 8))
    : ancla.left;

  return createPortal(
    <div
      ref={cajaRef}
      className={`nav-panel${entrando ? " nav-panel-entra" : ""}`}
      role="menu"
      onMouseEnter={onAbrir}
      onMouseLeave={onCerrar}
      style={{
        position: "fixed",
        top: ancla.top,
        left: izq,
        width: medida?.w,
        height: medida?.h,
        zIndex: 100,
      }}
    >
      {/* Absoluto a propósito: si fuera estático, el contenedor tomaría su
          tamaño y medirlo para dárselo al contenedor sería circular. */}
      <div
        ref={interior}
        key={grupo.key}
        className="nav-panel-int"
        style={{ position: "absolute", top: 0, left: 0, minWidth: 220 }}
      >
        {grupo.items.map((item, i) => {
          if (item.header) {
            return (
              <div key={i} style={{
                padding: i === 0 ? "8px 16px 4px" : "10px 16px 4px",
                marginTop: i === 0 ? 0 : 4,
                borderTop: i === 0 ? "none" : "1px solid var(--border-subtle)",
                color: "var(--nav-fg)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.6,
                textTransform: "uppercase",
                cursor: "default",
              }}>
                {th(item.key)}
              </div>
            );
          }
          if (item.disabled) {
            return (
              <div key={i} style={{
                padding: "9px 18px",
                color: "var(--text-disabled)",
                fontSize: "var(--nav-item-fs)",
                cursor: "default",
              }}>
                {ti(item.key)}
                <span style={{ fontSize: 10, marginLeft: 6, color: "var(--text-disabled)" }}>{tc("soon")}</span>
              </div>
            );
          }
          const aqui = pathname === item.href;
          return (
            <Link key={i} href={item.href!} role="menuitem"
              aria-current={aqui ? "page" : undefined}
              // ⚠️ `prefetch={false}` NO es «sin precarga»: es precarga al
              // APUNTAR en vez de al aparecer. Por omisión Next precarga cada
              // enlace apenas entra en pantalla, y Planning abre CUARENTA de
              // golpe — cuarenta pedidos por asomarse a un menú, de los que se
              // usa uno. Precargar al pasar el mouse llega igual de temprano
              // (uno tarda ~300 ms entre apuntar y hacer clic) y pide uno.
              prefetch={false}
              onClick={onCerrar} style={{
                display: "block",
                padding: "9px 18px",
                color: aqui ? "var(--brand)" : "var(--text-primary)",
                fontSize: "var(--nav-item-fs)",
                textDecoration: "none",
                whiteSpace: "nowrap",
                background: aqui ? "rgba(41,98,255,0.08)" : "transparent",
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.background = "var(--bg-elevated)";
                // Precarga al apuntar: para cuando el clic llega, la pantalla
                // ya esta en cache.
                if (item.href) router.prefetch(item.href);
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.background =
                  aqui ? "rgba(41,98,255,0.08)" : "transparent";
              }}
            >
              {ti(item.key)}
            </Link>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}

/** Si la ruta actual cae dentro del grupo: subraya el tab. */
function esTabActivo(g: NavGroup, pathname: string): boolean {
  if (g.href && pathname.startsWith(g.href)) return true;
  return g.items.some(i => i.href && pathname.startsWith(i.href));
}

export default function TopNav() {
  const hotel = useHotel();
  const pathname = usePathname();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const router = useRouter();
  const locale = useLocale();
  const tc = useTranslations("common");
  useEffect(() => { setUser(getStoredUser()); }, []);

  /**
   * El menú ESCONDE lo que esta persona no puede usar; no lo deshabilita.
   *
   * **Por qué (owner, 2026-08-19).** Preguntó por qué no tenía acceso a Admin.
   * No era permisos —su rol es admin— pero la pregunta destapó lo otro: las
   * nueve cuentas `collaborator` veían el menú Admin COMPLETO, `Users`
   * incluido. Al entrar reciben un 403, así que nunca fue un agujero; era una
   * pantalla mostrando puertas que no abren, que es de donde salió la duda.
   *
   * ⚠️ Mientras no se sabe el rol se ESCONDE. `user` se lee después de montar
   * —`localStorage` no existe en el render del servidor— así que en el primer
   * render no hay respuesta. Un admin ve las dos entradas aparecer un instante
   * después; al revés, todos verían por un instante lo que no pueden abrir, que
   * es justo lo que esto viene a corregir.
   */
  const esAdmin = user?.role === "admin";

  /**
   * Lo que ESTA propiedad decidió no ver (owner, 2026-08-20: «no todas las
   * propiedades van a ver todos los reportes, son muchos y se van a perder»).
   *
   * ⚠️ **Default PRENDIDO y falla PRENDIDO.** Si la llamada no responde se
   * queda en «nada apagado»: quedarse sin barra porque un endpoint tardó sería
   * mucho peor que mostrar de más un instante.
   *
   * ⚠️ Y esto ESCONDE, no bloquea. La ruta sigue respondiendo — es navegación,
   * no seguridad. Es también lo que hace seguro poder apagarlo todo: la
   * pantalla que lo administra se recupera entrando a su URL.
   */
  const [apagados, setApagados] = useState<TabsApagados>(NADA_APAGADO);
  useEffect(() => {
    let vivo = true;
    // ⚠️ Un hotel por instalación (`app/hotel_actual.py`): la propiedad la da
    // el entorno, no un selector. Por eso no hay que esperar a que el usuario
    // elija nada para saber qué esconder.
    getTabsApagados(HOTEL_ID)
      .then(a => { if (vivo) setApagados(a); })
      .catch(() => { if (vivo) setApagados(NADA_APAGADO); });
    // ⚠️ Y se escucha el cambio: sin esto, apagar un reporte no se ve hasta
    // recargar, y este proyecto ya aprendió que eso **se lee como «no
    // guardó»** (pasó con el nombre de la propiedad, ver `lib/hotel.ts`).
    const dejar = alCambiarTabs(a => { if (vivo) setApagados(a); });
    return () => { vivo = false; dejar(); };
  }, []);

  const navFiltrado = useMemo(() => {
    const tabFuera = new Set(apagados.TAB);
    const itemFuera = new Set(apagados.ITEM);
    return NAV
      .filter(g => !tabFuera.has(g.key))
      .map(g => ({
        ...g,
        items: g.items.filter(i => !itemFuera.has(i.key)
                                   && (esAdmin || !i.soloAdmin)),
      }))
      // Un grupo que se queda sin ninguna entrada navegable no se dibuja: un
      // tab que abre un panel vacío es peor que no tener el tab. ⚠️ Vale
      // igual cuando se vació por lo que apagó la propiedad, no sólo por rol.
      .filter(g => g.href || g.items.some(i => i.href && !i.disabled));
  }, [esAdmin, apagados]);
  const nav = navFiltrado;
  const grupoAdmin = nav.find(g => g.key === "admin");

  /**
   * Intención de hover: por qué el movimiento se siente continuo.
   *
   * Antes el menú abría con CLICK y cada tab traía su propio panel. Moverse
   * entre dos secciones era: cerrar uno, abrir otro. Nada que animar.
   *
   * Los tres números no son gusto — cada uno arregla algo distinto:
   *
   *   110 ms para abrir si NO hay panel abierto → que pasar el mouse de
   *       camino a otra cosa no dispare un menú que nadie pidió.
   *     0 ms si YA hay uno abierto → acá es donde el movimiento se vuelve
   *       continuo: el panel SIGUE al cursor, no se apaga y se prende.
   *   220 ms de gracia al cerrar → entre el tab y el panel hay un hueco de
   *       unos píxeles; sin gracia, cruzarlo cierra el menú en la cara.
   */
  const RETARDO_ABRIR = 110;
  const GRACIA_CERRAR = 220;
  const anclas = useRef(new Map<string, HTMLElement>());
  const [ancla, setAncla] = useState<{ top: number; left: number } | null>(null);
  const cajaPanel = useRef<HTMLDivElement>(null);
  const tAbrir = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tCerrar = useRef<ReturnType<typeof setTimeout> | null>(null);

  const limpiar = () => {
    if (tAbrir.current) clearTimeout(tAbrir.current);
    if (tCerrar.current) clearTimeout(tCerrar.current);
    tAbrir.current = null; tCerrar.current = null;
  };

  const abrirYa = (key: string) => {
    const el = anclas.current.get(key);
    if (!el) return;
    const r = el.getBoundingClientRect();
    setAncla({ top: r.bottom, left: r.left });
    setOpenMenu(key);
  };

  const pedirAbrir = (key: string) => {
    limpiar();
    if (openMenu === key) return;
    tAbrir.current = setTimeout(() => abrirYa(key), openMenu ? 0 : RETARDO_ABRIR);
  };

  const pedirCerrar = () => {
    limpiar();
    tCerrar.current = setTimeout(() => setOpenMenu(null), GRACIA_CERRAR);
  };

  const cerrarYa = () => { limpiar(); setOpenMenu(null); };

  // Click afuera, scroll y resize cierran. Igual que antes, con una excepción
  // que costó encontrar: el scroll DEL PROPIO PANEL no cuenta — Planning tiene
  // 41 opciones y hay que rodar la rueda adentro para llegar a las de abajo.
  useEffect(() => {
    if (!openMenu) return;
    const esDelMenu = (t: Node | null) =>
      !!t && (cajaPanel.current?.contains(t)
        || [...anclas.current.values()].some(el => el.contains(t)));
    const alClickear = (e: MouseEvent) => {
      if (!esDelMenu(e.target as Node)) cerrarYa();
    };
    const alScrollear = (e: Event) => {
      if (cajaPanel.current?.contains(e.target as Node)) return;
      cerrarYa();
    };
    const alTeclear = (e: KeyboardEvent) => { if (e.key === "Escape") cerrarYa(); };
    document.addEventListener("mousedown", alClickear);
    document.addEventListener("keydown", alTeclear);
    window.addEventListener("resize", cerrarYa);
    window.addEventListener("scroll", alScrollear, true);
    return () => {
      document.removeEventListener("mousedown", alClickear);
      document.removeEventListener("keydown", alTeclear);
      window.removeEventListener("resize", cerrarYa);
      window.removeEventListener("scroll", alScrollear, true);
    };
  }, [openMenu]);

  // Que no quede un temporizador vivo si la barra se desmonta.
  useEffect(() => limpiar, []);

  const grupoAbierto = openMenu ? nav.find(g => g.key === openMenu) : undefined;

  // La fecha del header es lo único del chrome que YA cambia con el idioma:
  // es-CR / en-US. El formato de plata y de meses del resto de la app sigue
  // fijo — es un tramo aparte, a propósito (ver docs/I18N_PLAN.md).
  // Corta en la barra, completa en el tooltip: el día de la semana es adorno y
  // era lo que más ancho ocupaba del lado derecho.
  const lang = locale === "en" ? "en-US" : "es-CR";
  const hoy = new Date();
  const today = hoy.toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" });
  const todayLargo = hoy.toLocaleDateString(lang, {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  return (
    <nav style={{
      background: "var(--nav-bg)",
      height: "var(--nav-h)",
      display: "flex",
      alignItems: "center",
      borderBottom: "1px solid var(--nav-borde)",
      padding: "0 16px",
      position: "sticky",
      top: 0,
      zIndex: 50,
      gap: 0,
    }}>
      {/* Logo — NO es un link. Antes llevaba a la raíz, que mostraba el mismo
          cuadro que ahora abre el tab Dashboard: eran dos caminos a lo mismo y
          uno de los dos sobraba. Queda como marca, nada más. */}
      <span className="nav-logo" style={{
        color: "var(--nav-fg-strong)",
        fontWeight: 700,
        fontSize: "var(--nav-logo-fs)",
        letterSpacing: "-0.02em",
        marginRight: 8,
        whiteSpace: "nowrap",
      }}>
        FinPlan <span style={{ color: "var(--nav-accent)" }}>{hotel.id}</span>
      </span>

      <div className="nav-logo" style={{ width: 1, height: 24, background: "var(--nav-borde)", margin: "0 8px" }} />

      {/* Los tabs. Si no entran, este contenedor scrollea de lado en vez de
          partir la barra en dos renglones (ver .nav-scroll en globals.css). */}
      <div className="nav-scroll">
        {nav.filter(g => g.key !== "admin").map(group => (
          <Tab
            key={group.key}
            group={group}
            open={openMenu === group.key}
            activo={esTabActivo(group, pathname)}
            onAbrir={() => pedirAbrir(group.key)}
            onCerrar={pedirCerrar}
            // ALTERNAR y CERRAR son cosas distintas, y confundirlas hacía que el
            // menú parpadeara: dos disparos seguidos alternaban dos veces
            // —cerrar, abrir— antes de que React quitara el listener.
            onToggle={() => {
              limpiar();
              if (openMenu === group.key) setOpenMenu(null);
              else abrirYa(group.key);
            }}
            registrar={el => {
              if (el) anclas.current.set(group.key, el);
              else anclas.current.delete(group.key);
            }}
          />
        ))}
      </div>

      {/* Lado derecho: nunca se encoge, y cada pieza va en una sola línea. */}
      <div className="nav-nowrap" style={{
        display: "flex", alignItems: "center", gap: 12, color: "var(--nav-fg)",
        fontSize: 12, flexShrink: 0, marginLeft: 12,
      }}>
        {/* ⚠️ Admin va ACÁ, fuera de `.nav-scroll`, y no es una preferencia de
            diseño: era inalcanzable.

            Los tabs crecieron a doce y Admin quedó de último. Cuando no entran,
            `.nav-scroll` scrollea de lado —con el scrollbar oculto a propósito,
            sin flecha y sin sombra—, así que el tab caía fuera del borde
            derecho y NADA indicaba que estuviera ahí. El owner lo reportó como
            «no tengo acceso a Admin»: no era permisos (su rol es admin y
            ninguna pantalla lo filtra por rol), era que no se veía.

            Fijo a la derecha entra siempre, y además es donde se buscan los
            ajustes. Si mañana se agrega un tab trece, este sigue alcanzable. */}
        {grupoAdmin && <Tab
          group={grupoAdmin}
          open={openMenu === "admin"}
          activo={esTabActivo(grupoAdmin, pathname)}
          onAbrir={() => pedirAbrir("admin")}
          onCerrar={pedirCerrar}
          onToggle={() => {
            limpiar();
            if (openMenu === "admin") setOpenMenu(null);
            else abrirYa("admin");
          }}
          registrar={el => {
            if (el) anclas.current.set("admin", el);
            else anclas.current.delete("admin");
          }}
        />}
        <span className="nav-fecha" title={todayLargo} style={{ textTransform: "capitalize" }}>{today}</span>
        <LanguageSwitch />
        <div className="nav-hotel" style={{
          border: "1px solid var(--border-medium)",
          borderRadius: 4,
          padding: "3px 10px",
          cursor: "default",
          color: "var(--nav-fg-strong)",
          fontSize: 12,
        }} title={hotel.nombre}>
          {hotel.corto} ▾
        </div>
        {user ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* Solo el primer nombre. El completo (y el correo) en el tooltip:
                «BISMMARK RODRIGUEZ GARCIA · ADMIN» se comía media barra. */}
            <span title={`${user.name || ""} · ${user.email}`.trim()}
              style={{ color: "var(--nav-fg-strong)", fontSize: 12, textTransform: "uppercase",
                       maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis" }}>
              {(user.name || user.email).split("@")[0].trim().split(/\s+/)[0]}
              {user.role === "admin" && <span style={{ color: "var(--nav-fg-dim)", marginLeft: 4 }}>· {tc("admin")}</span>}
            </span>
            <button onClick={() => { logout(); setUser(null); router.push("/login"); }}
              style={{ border: "1px solid var(--border-medium)", borderRadius: 4, padding: "3px 10px", cursor: "pointer",
                background: "none", color: "var(--nav-fg)", fontSize: 12 }}>
              {tc("logout")}
            </button>
          </div>
        ) : (
          <Link href="/login" style={{ border: "1px solid var(--border-medium)", borderRadius: 4, padding: "3px 10px",
            color: "var(--nav-fg-strong)", fontSize: 12, textDecoration: "none" }}>
            {tc("login")}
          </Link>
        )}
      </div>

      {/* EL panel. Uno solo, montado mientras haya un grupo abierto: por eso
          cambiar de sección lo DESLIZA en vez de apagarlo y prenderlo. */}
      {grupoAbierto && ancla && typeof document !== "undefined" && (
        <Panel
          grupo={grupoAbierto}
          ancla={ancla}
          cajaRef={cajaPanel}
          onAbrir={limpiar}
          onCerrar={pedirCerrar}
        />
      )}
    </nav>
  );
}
