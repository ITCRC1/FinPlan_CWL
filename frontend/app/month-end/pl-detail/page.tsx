/**
 * Cierre de Mes → Profit by Dept.
 *
 * La pantalla vive en `Pantalla.tsx` porque toma props (`esPre`) y una ruta de
 * Next no puede: sus props tienen que ser `PageProps`. Ver el encabezado de
 * `Pantalla.tsx` — el build de Railway ya se cayo una vez por esto.
 */
import Pantalla from "./Pantalla";

export default function Page() {
  return <Pantalla />;
}
