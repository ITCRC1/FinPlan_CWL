/**
 * El hotel de ESTA instalación.
 *
 * Modelo de despliegue: un hotel = un proyecto aparte — base propia, app propia.
 * No hay selector de hotel ni multi-tenant: cada despliegue *es* un hotel, y su
 * identidad sale del entorno.
 *
 *     NEXT_PUBLIC_HOTEL_ID=AMA
 *
 * Los cuatro prefijos del grupo: CWL (Corcovado), AMA (Amarena), OXI (Oxígen),
 * OJO (Ojochal). No se validan acá a propósito — una lista cerrada obligaría a
 * tocar el repo para abrir la quinta propiedad.
 *
 * Tiene que ir con `NEXT_PUBLIC_` porque estas pantallas son componentes de
 * cliente: sin el prefijo, Next no lo expone al navegador y llegaría `undefined`.
 *
 * El default es CWL para que Corcovado no cambie de comportamiento, y para que
 * un `vercel --prod` sin la variable configurada no rompa: sigue siendo
 * Corcovado, que es lo que ya era.
 */
export const HOTEL_ID: string = process.env.NEXT_PUBLIC_HOTEL_ID || "CWL";

/**
 * ── El NOMBRE se edita en la app, el CÓDIGO no ──────────────────────────────
 *
 * El nombre visible vive en la tabla `hotels` y se cambia desde
 * Master Data → Provisionamiento. Por eso se LEE del backend en vez de estar
 * escrito acá: cambiarlo no necesita deploy ni tocar variables de entorno.
 *
 * El `HOTEL_ID` de arriba es otra cosa y por eso sí viene del entorno: es la
 * llave con la que están amarrados escenarios, tipos de habitación, planilla y
 * todo el dato. Se fija una vez, al provisionar. Cambiarlo desde una pantalla
 * dejaría huérfano el histórico entero sin ningún aviso.
 *
 * Los valores de abajo son solo el ARRANQUE: lo que se muestra en el primer
 * render, antes de que llegue la respuesta del backend. Se eligieron los de
 * Corcovado para que no parpadee en la instalación que ya existe.
 */
let _name = process.env.NEXT_PUBLIC_HOTEL_NAME || "Corcovado Wilderness Lodge";
let _short = process.env.NEXT_PUBLIC_HOTEL_SHORT_NAME || HOTEL_ID;
let _pedido: Promise<void> | null = null;

export const HOTEL_NAME: string = _name;
export const HOTEL_SHORT: string = _short;

/** Nombre completo, ya resuelto contra el backend. */
export function hotelName(): string { return _name; }
/** Nombre corto — cae al código si nadie lo configuró. */
export function hotelShort(): string { return _short; }

/**
 * Trae el nombre de la propiedad. Se pide UNA vez por sesión de navegador: el
 * nombre de un hotel no cambia mientras alguien lo está mirando, y pedirlo en
 * cada pantalla serían decenas de llamadas para un dato que no se mueve.
 */
export function cargarHotel(): Promise<void> {
  if (_pedido) return _pedido;
  // ⚠️ `NEXT_PUBLIC_API_URL` YA termina en `/api` — mismo valor que usa
  // `lib/api.ts`. Agregarle otro `/api` daba 404, y como el `.catch` de abajo
  // es silencioso, el nombre se caía al valor de arranque sin avisar: la
  // pantalla de Provisionamiento guardaba bien y la barra seguía diciendo lo
  // viejo. No se importa `BASE` de `lib/api.ts` porque ese módulo importa este
  // (`HOTEL_ID`) y quedaría un ciclo.
  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const token = typeof window !== "undefined"
    ? localStorage.getItem("finplan_token") : null;
  _pedido = fetch(`${base}/provisioning/${HOTEL_ID}/identidad/`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
    .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
    .then(d => {
      if (d?.name) _name = d.name;
      if (d?.short_name) _short = d.short_name;
    })
    // Si el backend no contesta se queda el valor de arranque: un encabezado
    // con el nombre viejo es mejor que una pantalla rota. Pero se DEJA RASTRO
    // en la consola — el `.catch` mudo de antes escondió justamente el bug de
    // la URL duplicada.
    .catch(e => { console.warn("No se pudo leer el nombre de la propiedad:", e); });
  return _pedido;
}

/**
 * Vuelve a pedirlo. Lo usa Provisionamiento después de guardar: sin esto, el
 * nombre nuevo no se ve en la barra hasta recargar la página, y parece que no
 * guardó.
 */
export function refrescarHotel(): Promise<void> {
  _pedido = null;
  return cargarHotel();
}

/** Sin espacios ni acentos: los dos rompen descargas en algunos navegadores. */
function _slug(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "")
          .replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || HOTEL_ID;
}

/**
 * Trozo seguro para nombres de archivo: `Planilla_${hotelSlug()}.xlsx`.
 *
 * Es una FUNCIÓN y no una constante porque el nombre se edita en
 * Provisionamiento: una constante congelaría el valor del arranque y el archivo
 * saldría con el nombre viejo. Al leerse en el momento del clic, ya tiene el
 * nombre que resolvió `cargarHotel()`.
 */
export function hotelSlug(): string { return _slug(_short); }

/** Valor de arranque, para donde no se puede llamar una función. */
export const HOTEL_SLUG: string = _slug(_short);
