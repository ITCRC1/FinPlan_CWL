import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { cookies } from "next/headers";
import "./globals.css";
import TopNav from "@/components/TopNav";
import GuillermoHeader from "@/components/GuillermoHeader";
import AuthGate from "@/components/AuthGate";
import Transicion from "@/components/Transicion";
import { HOTEL_ID, HOTEL_NAME } from "@/lib/hotel";
import { TEMA_COOKIE, TEMA_POR_DEFECTO, normalizeTema } from "@/lib/tema";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-ui",
  display: "swap",
});

export const metadata: Metadata = {
  title: `FinPlan ${HOTEL_ID} — ${HOTEL_NAME}`,
  description: "Financial planning system — The Costa Rica Collection",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // El idioma sale de la cookie `finplan_locale`, que el frontend escribe al
  // entrar con el valor YA RESUELTO que devuelve /auth/login
  // (usuario → hotel → 'es'). Ver i18n/request.ts y backend/app/i18n.py.
  const locale = await getLocale();
  const messages = await getMessages();

  // El tema sale de la cookie `finplan_tema` y se aplica ACÁ, en el servidor.
  // Si se aplicara con JavaScript después de montar, cada carga mostraría un
  // parpadeo: la página pinta con el tema por defecto y salta al elegido.
  // Ver `lib/tema.ts`.
  const tema = normalizeTema((await cookies()).get(TEMA_COOKIE)?.value) ?? TEMA_POR_DEFECTO;

  return (
    <html lang={locale} data-tema={tema} style={{ background: "var(--bg-base)" }}>
      <body style={{ fontFamily: "var(--font-ui)", margin: 0, padding: 0 }} className={inter.variable}>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <TopNav />
          {/* ⚠️ La transición envuelve SOLO el contenido, nunca al `TopNav`:
              remonta lo de adentro en cada navegación, y remontar la barra
              desharía el panel que se acaba de arreglar. */}
          <main style={{ padding: "24px 24px 48px", minHeight: "calc(100vh - 44px)" }}>
            <AuthGate><Transicion>{children}</Transicion></AuthGate>
          </main>
          {/* ⚠️ Guillermo va AFUERA del `main` y afuera de `Transicion`: es
              `position: fixed` y su animación es de varios segundos, así que
              remontarlo en cada navegación cortaría la entrada a la mitad.
              Va después del contenido para no robarle el foco a nada. */}
          <GuillermoHeader />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
