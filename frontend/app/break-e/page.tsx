"use client";
/** `/break-e` redirige al Resumen, que es el sub-tab por defecto del spec. */
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function BreakEIndex() {
  const router = useRouter();
  useEffect(() => { router.replace("/break-e/resumen"); }, [router]);
  return null;
}
