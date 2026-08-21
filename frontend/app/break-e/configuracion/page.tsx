"use client";
/**
 * `/break-e/configuracion` redirige al PRIMER departamento activo.
 *
 * El primero sale del catálogo (`display_order`), no de una constante: el día
 * que se active uno de los 8 pendientes, esta redirección lo respeta sola.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getBeDeptos } from "@/lib/api";

export default function ConfiguracionIndex() {
  const router = useRouter();
  useEffect(() => {
    (async () => {
      try {
        const { departamentos } = await getBeDeptos();
        const primero = departamentos.find(d => d.activo);
        router.replace(primero
          ? `/break-e/configuracion/${primero.slug}`
          : "/break-e/resumen");
      } catch { router.replace("/break-e/resumen"); }
    })();
  }, [router]);
  return null;
}
