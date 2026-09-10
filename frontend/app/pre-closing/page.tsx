/**
 * Pre-Closing — el mes que se esta revisando, en los 19 sub-tabs del P&L.
 *
 * Owner, 2026-09-10: *«crea un tab que se llame Pre-Closing y jala del tab
 * Monthly P&L, jala todos los sub tabs pero hazlo facil, no quites ningun sub
 * tab porque sera objeto de analisis y revision rapida de cada uno de ellos
 * con los datos que se estan subiendo»* · *«solo deja comparativo para mes
 * para 4 versiones»* · *«debe leer la version mas reciente subida, porque
 * seguro se suban varias antes de llegar a final»*.
 *
 * Es la MISMA pantalla que Cierre de Mes → P&L, con `modo="pre-cierre"`. No es
 * una copia: duplicar 3.700 lineas garantizaba que en dos meses las dos
 * dijeran cosas distintas sobre el mismo mes.
 *
 * ## De donde salen los datos
 *
 * De un escenario ESPEJO que el Pre-Cierre materializa en cada subida
 * (`api/precierre_api.py::_reflejar`, migracion 140). Los ocho cargadores del
 * P&L lo leen sin saber que es un pre-cierre, asi que los 19 sub-tabs
 * funcionan sin tocar ni un endpoint.
 *
 * El espejo es UNO por año y se sobreescribe: siempre es la ultima subida.
 * Nunca es el ACTUAL — «Pasar a Final» sigue escribiendo el de verdad.
 */
import Pantalla from "../month-end/pl/Pantalla";

export default function Page() {
  return <Pantalla modo="pre-cierre" />;
}
