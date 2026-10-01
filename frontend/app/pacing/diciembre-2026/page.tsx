import { redirect } from "next/navigation";

// Quedó dentro de «Análisis especial» (sub-pestaña). La ruta vieja sigue viva
// para los enlaces que ya se compartieron.
export default function PacingPage() {
  redirect("/pacing/especial?v=dic");
}
