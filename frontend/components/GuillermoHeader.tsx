"use client";
//
// Monta al gato y trae su estado (`docs/GUILLERMO.md` §10).
//
// ⚠️ **No hay chip en el bloque derecho de la barra, y es una decisión medida.**
// El §10.1 lo pide, pero medido sobre la barra real un chip
// «● Guillermo 4 sombra» ocupa **161px**, y eso empuja los tres escalones de
// escalado (1860 / 1990 / 2115) por encima de casi cualquier monitor — el mismo
// defecto del «Master Data» convertido en «M» que el owner reportó el 19-ago.
// El spec ofrece la alternativa en §10.3: **badge en el menú**. Queda anotado
// en `docs/GUILLERMO_PENDIENTES.md` con el costo, para que sea decisión del
// owner y no un olvido.
//
// ⚠️ **El gato no es el único canal.** La misma información vive en la pantalla
// `/admin/guillermo` y en el correo. Si alguien lo apaga —y alguien lo va a
// odiar— no se pierde ninguna advertencia.
//
// ⚠️ **El estado SIEMPRE viene del backend** (§10.2.7). El componente no
// infiere ni recuerda nada: si la UI y la base discrepan, gana la base.
//
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Guillermo from "@/components/Guillermo";
import { getEstadoGuillermo, type EstadoGuillermo } from "@/lib/api";

// La ronda es diaria: preguntar cada 30 s no aporta y suma ruido de red. Pero
// tampoco puede ser una sola vez — si Guillermo se traba mientras la pestaña
// está abierta, el gato tiene que ponerse rojo sin recargar.
const CADA_MS = 5 * 60 * 1000;

export default function GuillermoHeader() {
  const router = useRouter();
  const [e, setE] = useState<EstadoGuillermo | null>(null);
  const [intro, setIntro] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setE(await getEstadoGuillermo());
    } catch {
      // ⚠️ En silencio a propósito: un token vencido o un backend viejo sin
      // estos endpoints NO puede llenar de errores la aplicación entera. La
      // ausencia del gato ya dice que no hay estado.
      setE(null);
    }
  }, []);

  useEffect(() => {
    cargar();
    const t = setInterval(cargar, CADA_MS);
    return () => clearInterval(t);
  }, [cargar]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!sessionStorage.getItem("guillermo_intro")) {
      sessionStorage.setItem("guillermo_intro", "1");
      setIntro(true);
    }
  }, []);

  if (!e || !e.gato_encendido) return null;

  return (
    <Guillermo
      state={e.state}
      pendingCount={e.pendientes}
      onClick={() => router.push("/admin/guillermo")}
      playIntro={intro}
    />
  );
}
