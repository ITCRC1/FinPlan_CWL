"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { getToken, refrescarSesion } from "@/lib/api";

/** Vida del token. ⚠️ Debe coincidir con `TOKEN_TTL` de `backend/app/auth.py`. */
const TTL_MS = 10 * 60 * 1000;
/** Cada cuánto se revisa si hay que renovar. */
const LATIDO_MS = 30 * 1000;
/**
 * Cuánto se espera entre renovaciones. Acota cuánto puede pasarse de 10 minutos
 * el cierre real: con 2 minutos, a quien deja de trabajar lo sacan entre el
 * minuto 10 y el 12. Bajarlo afina el corte y sube las llamadas; subirlo hace
 * lo contrario. No puede acercarse a `TTL_MS` o la renovación llega tarde.
 */
const ENTRE_RENOVACIONES_MS = 2 * 60 * 1000;

const EVENTOS = ["mousedown", "keydown", "scroll", "touchstart", "focus"] as const;

// Si no hay sesión y no estás en /login, redirige a /login.
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const t = useTranslations("common");
  const [ok, setOk] = useState(false);

  useEffect(() => {
    const isLogin = pathname?.startsWith("/login");
    const hasToken = !!getToken();
    if (!hasToken && !isLogin) {
      router.replace("/login");
      setOk(false);
    } else {
      setOk(true);
    }
  }, [pathname, router]);

  // ── La sesión se corta por inactividad, no por reloj ──────────────────────
  //
  // El token vive 10 minutos. Mientras haya actividad se renueva y nadie se
  // entera; si el teclado y el mouse quedan quietos, deja de renovarse y vence
  // solo. Cuando eso pasa, la siguiente llamada da 401 y `apiFetch` ya manda a
  // `/login` — acá no hace falta repetir esa lógica.
  //
  // ⚠️ Se mide la ACTIVIDAD, no el tiempo desde el login. La diferencia es lo
  // que separa «se cerró la sesión porque me fui» de «se cerró la sesión a
  // mitad del checkbook», que sin renovación es lo que pasaría cada 10 minutos.
  const ultimaActividad = useRef(Date.now());
  const ultimaRenovacion = useRef(Date.now());

  useEffect(() => {
    if (pathname?.startsWith("/login")) return;

    const marcar = () => { ultimaActividad.current = Date.now(); };
    for (const e of EVENTOS) window.addEventListener(e, marcar, { passive: true });

    const latido = setInterval(() => {
      if (!getToken()) return;
      const ahora = Date.now();
      // Quieto hace rato: no se renueva. El token vence y esa es la intención.
      if (ahora - ultimaActividad.current >= TTL_MS) return;
      // Activo, pero recién renovado: no hace falta llamar otra vez.
      if (ahora - ultimaRenovacion.current < ENTRE_RENOVACIONES_MS) return;
      ultimaRenovacion.current = ahora;
      void refrescarSesion();
    }, LATIDO_MS);

    return () => {
      clearInterval(latido);
      for (const e of EVENTOS) window.removeEventListener(e, marcar);
    };
  }, [pathname]);

  if (!ok && !pathname?.startsWith("/login")) {
    return <div style={{ padding: 40, color: "var(--text-secondary)" }}>{t("redirecting")}</div>;
  }
  return <>{children}</>;
}
