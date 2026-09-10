/**
 * Cierre de Mes → P&L.
 *
 * La pantalla vive en `Pantalla.tsx` porque la comparte con **Pre-Closing**
 * (`app/pre-closing/page.tsx`): son los mismos 19 sub-tabs sobre los mismos
 * datos, y duplicarlas garantizaba que en dos meses dijeran cosas distintas.
 * Lo que cambia entre las dos es el `modo`.
 */
import Pantalla from "./Pantalla";

export default function Page() {
  return <Pantalla modo="cierre" />;
}
