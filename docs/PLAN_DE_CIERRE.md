# Plan de cierre — FinPlan CWL → gemeleo a las otras propiedades

> **Cerrado el 2026-08-12.** El trabajo de código está terminado: **Corcovado ya
> se puede clonar.** Lo que queda no lo puede hacer el sistema.
>
> Detalle de cada punto en [`PENDIENTES.md`](PENDIENTES.md).

---

## ✅ Terminado

### El dato de Corcovado

| | |
|---|---|
| **A1** | Los $326,712 de Villas y Residencias entran al P&L |
| **A2** | El aviso de Gastos de Propiedad dejó de llamar «descuadre» a lo que no lo es |
| **A3** | Diagnosticado línea por línea *(la decisión sobre 2024 es del owner — abajo)* |
| **A4** | `4000` Room Revenue · `4001` Cancellations · `4002` No Show habilitadas, y el ADR ya sale solo de la 4000 |
| **A5** | No había dato de prueba en la Cafetería — las 5 posiciones amarran al centavo |
| **B1** | Cero filas ruteando por descarte en todos los escenarios |
| **B3** | No era deuda: estaba explicado |

### La preparación del gemeleo

| | |
|---|---|
| **Identidad del hotel** | 20 literales `"CWL"` en el backend y 89 en el frontend, fuera. Todo sale del entorno |
| **Outlets de A&B** | El `outlet` entra en la llave de `actual_entries`: el día que contabilidad lo llene, el dato entra con su dimensión |
| **Private Bar** | Departamento propio, modelado como tienda, con sus tres líneas en todos los reportes |

**728 pruebas · `tsc --noEmit` limpio.**

---

## ❌ Lo que se quitó del plan porque ya no aplica

El plan original (`MULTIPROPERTY_PLAN.md`, junio 2026) asumía **multi-tenant en
una sola base**. La decisión del owner es otra: **cuatro proyectos
independientes**, base propia y app propia, con prefijos `CWL`, `AMA`, `OXI`,
`OJO`. Eso elimina tres ítems enteros, incluido el que estaba marcado como
bloqueante:

* ~~**Control de acceso por hotel** (`User.hotel_id`)~~ — **no aplica.** Con
  bases separadas el aislamiento es físico: Amarena no puede ver a Corcovado ni
  queriendo. Era el ítem más caro de la lista.
* ~~**Provisioning parametrizado** (`POST /api/hotels/`)~~ — **no aplica.** El
  hotel lo crea `app/seed.py` al arrancar, leyendo el entorno.
* ~~**Selector de hotel en el frontend**~~ — **no aplica.** Cada app *es* un
  hotel.

**Lo que sí cambia con este modelo:** «arreglar una vez» ahora significa
*arreglar en el repo y redesplegar las cuatro apps*. El motor y el mapeo viajan
como CÓDIGO, no como filas de una base compartida. Sigue siendo una sola
edición, pero cuatro deploys.

---

## Cómo se abre una propiedad nueva

No hay que tocar código. Se crea el proyecto (Railway + Vercel + base) y se
configuran las variables:

**Railway — backend**

    HOTEL_ID=AMA
    HOTEL_NAME=Amarena Canvas Beach Hotel
    HOTEL_SHORT_NAME=Amarena
    HOTEL_ROOMS=24
    HOTEL_TC_USD=530.0000

**Vercel — frontend**

    NEXT_PUBLIC_HOTEL_ID=AMA
    NEXT_PUBLIC_API_URL=<url del backend de esa propiedad>

`app/seed.py` corre al arrancar y crea el hotel con el catálogo USALI completo,
el mapeo de cuentas y las líneas del P&L. **La instalación nace funcionando, no
vacía.**

Dos pruebas lo cuidan: `test_un_hotel_por_instalacion.py` recorre el árbol
sintáctico y falla si alguien vuelve a escribir `"CWL"` como valor, y verifica
que el seed y el helper lean la MISMA variable — si se separan, el seed crea un
hotel y la API busca otro.

---

## Lo único que queda, y no es del sistema

### Del owner — dos decisiones

1. **`Actual 2024`:** el GL trae **+$40,613** de gasto de Rooms y **−$3,085** de
   ingreso de Innoceana respecto al resumen del mismo archivo. ¿Cuál de las dos
   hojas manda?
2. **Diferencial cambiario:** ¿se quiere como renglón propio del P&L, o sirve
   dentro de intereses como está hoy?

### De contabilidad — una sola conversación, cuatro puntos

1. **Cuenta `4000`.** Partirla en `4000` Room Revenue, `4001` Cancellations,
   `4002` No Show. **Las tres ya están habilitadas en el sistema.**
2. **Outlets de A&B.** La hoja ya trae la columna Outlet con cuatro posiciones
   por tipo de producto y solo se usa el Outlet 1. Empezar a contabilizar en los
   Outlets 2, 3 y 4. **El sistema ya los guarda cuando lleguen.**
3. **Tipos de bebida.** Hoy toda la venta de alcohol está en `Beer1` y todo el
   costo en `Bev Cost`. Usar `4130` Licor y `4131` Vino en el ingreso, y `5151`,
   `5152` y `5153` en el costo. **Las seis cuentas ya existen y están en cero.**
4. **Cuenta `5102`.** En los actuales se usa como traslado *Bar to Food* (va en
   negativo); en el Budget 2027 está usada como *Food Cost 2*. Definir cuál de
   los dos usos se queda — mientras convivan, esa línea no compara entre años.

### Después, y solo cuando haya dos hoteles andando

* **El motor de presupuesto de A&B** — covers × cheque promedio, por tiempo de
  comida y por outlet, con el reparto del costo para la utilidad por outlet.
  Depende del punto 2 de arriba: sin outlets llenos sería una estructura vacía.
* **Las constantes depto→grupo a tabla** — hoy `pl_engine` embebe el catálogo de
  Corcovado. Con un solo hotel no se sabe qué diverge de verdad.
* **La visibilidad de los reportes** — las listas de centros de Junta, Revenue
  Mix y Big Picture son fijas y no consultan la matriz de provisionamiento, así
  que un hotel sin Private Bar o sin Club Madresal los va a mostrar en cero. No
  molesta hasta que exista el segundo hotel.

---

## Lo que NO hay que hacer

* **No partir el mapeo por hotel.** `account_mapping` y `report_line_config` no
  tienen `hotel_id` a propósito. Cada base tiene su copia, sembrada del mismo
  JSON: la fuente es una sola.
* **No poner `if hotel_id == 'OXI'` en el motor.** Un ajuste de una propiedad va
  en su fila de `Hotel` o en su escenario.
* **No escribir `"CWL"` en el código.** Hay una prueba que lo impide.
* **No tocar `department_catalog` ni el mapeo con una migración sola:** el seed
  corre en cada deploy y los re-afirma desde las constantes de `pl_engine` y
  desde `mapping_pl.json`. Una migración que no toque también la fuente **se
  revierte sola en el próximo deploy, sin avisar**.
