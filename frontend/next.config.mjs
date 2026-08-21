import createNextIntlPlugin from "next-intl/plugin";

// Modo «without i18n routing»: el idioma NO va en la URL (vive en la base y
// viaja por la cookie `finplan_locale`). No hay segmento [locale], no se
// renombró ninguna página y ningún <Link> cambió.
const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

// Un despliegue sin `NEXT_PUBLIC_API_URL` NO da error: `lib/api.ts` cae a
// `http://localhost:8000/api` y la app sale a producción pidiéndole datos a la
// máquina de quien la abre. En pantalla se ve «Failed to fetch» y nada más.
//
// Pasó de verdad (2026-08-13). La URL vivía dentro de `.env.production`, que
// está commiteado; se sacó de ahí —era una trampa para el clonado, un
// despliegue de Amarena que no la pisara habría escrito en la base de
// Corcovado— y nadie la puso en Vercel. El siguiente deploy salió apuntando a
// localhost.
//
// `NEXT_PUBLIC_*` se congela en tiempo de compilación, así que este es el
// momento de avisar: mejor que el deploy falle a que salga roto y mudo.
// Un `npm run build` local sigue funcionando igual.
//
// ⚠️ **La guarda mira Vercel Y Railway.** Miraba solo `process.env.VERCEL`, y
// al mudar el frontend a Railway eso la volvía letra muerta: `VERCEL` no existe
// ahí, así que el build pasaba limpio y la app salía a producción pidiéndole
// datos a `http://localhost:8000/api` — es decir, a la máquina de quien la
// abriera. Exactamente la caída del 2026-08-13 que documenta el comentario de
// arriba, pero ahora sin nada que la detuviera.
const ES_DESPLIEGUE = Boolean(process.env.VERCEL || process.env.RAILWAY_ENVIRONMENT);

if (ES_DESPLIEGUE && !process.env.NEXT_PUBLIC_API_URL) {
  throw new Error(
    "Falta NEXT_PUBLIC_API_URL. Sin ella la app sale a producción apuntando a "
    + "http://localhost:8000/api y todo muere con «Failed to fetch».\n"
    + "Cargala en las Variables del servicio de frontend de ESTA propiedad,\n"
    + "ANTES del build (NEXT_PUBLIC_* se hornea al compilar, no al arrancar):\n"
    + "  NEXT_PUBLIC_API_URL = https://<backend-de-esta-propiedad>/api",
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // `next dev` y `next build` escriben los dos en .next/ y se pisan: si alguien
  // corre un build mientras el servidor de desarrollo está levantado, el dev
  // empieza a tirar «Cannot find module './8948.js'» y HTTP 500 en todas las
  // páginas. Pasó. Con esto, un build de verificación se manda a otra carpeta:
  //     NEXT_DIST_DIR=.next-check npm run build
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Don't fail the production build on ESLint style warnings (unused vars,
  // unescaped entities). Types are still checked by tsc. Lint can be cleaned
  // up separately without blocking deploys.
  eslint: {
    ignoreDuringBuilds: true,
  },

  // Rutas que se MUDARON. Una pantalla que estuvo en producción y cambia de
  // dirección deja 404 a quien la tenga abierta, en el historial o en un
  // marcador — y el 404 se ve con la barra de navegación NUEVA alrededor, así
  // que parece que la app se rompió y no que la URL cambió.
  //
  // Pasó de verdad (2026-08-19): las dos pantallas de Costos de Grupos
  // vivieron 40 minutos bajo `/planning/` antes de mudarse al tab `Cost`. El
  // owner quedó con la vieja abierta y reportó el 404 dos veces seguidas,
  // mientras yo verificaba las rutas nuevas —que respondían perfecto— y no
  // las viejas.
  //
  // `permanent: false` (307) a propósito: un 308 se cachea en el navegador y
  // si mañana la pantalla se vuelve a mover, ya no hay forma de corregirlo.
  async redirects() {
    return [
      { source: "/planning/costos-grupos", destination: "/cost/pisos",
        permanent: false },
      { source: "/planning/simulador-grupos", destination: "/cost/simulador",
        permanent: false },
    ];
  },
};

export default withNextIntl(nextConfig);
