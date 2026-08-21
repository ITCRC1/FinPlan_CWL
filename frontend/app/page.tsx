import { redirect } from "next/navigation";

// La raíz manda al Dashboard. El cuadro que antes vivía acá —el que se abría al
// hacer clic en el logo— ahora ES el Dashboard, así que la portada y el tab son
// la misma pantalla y no hay dos lugares que muestren cosas distintas.
export default function Home() {
  redirect("/dashboard");
}
