# Trabajo autónomo — encargo del owner (2026-08-12)

> El owner dejó un encargo extenso para ejecutar mientras no está, y pidió
> explícitamente: *«revisá qué aprobaciones necesitás de mí, y aprobalas ya que
> yo no voy a estar»*.
>
> Este documento dice **qué se aprobó solo, qué NO, y por qué** — antes de
> listar el trabajo. Si algo salió distinto de lo planeado, la bitácora del
> final lo cuenta.

---

## Las aprobaciones

### ✅ Tomadas por cuenta propia

Son decisiones de **diseño y alcance**: reversibles, con precedente en el código,
y sin efecto sobre ningún número.

| decisión | criterio aplicado |
|---|---|
| Formato del Excel | Se usa la casa que ya existe: `backend/app/export/excel_base.py` (paleta, fuentes, anchos, formatos de moneda). No se inventa un estilo nuevo. |
| Qué pantallas exportan | **Todas** las que muestren un cuadro, como pidió el owner. |
| Cliente vs servidor | Los exportes nuevos se hacen **en el servidor** con `openpyxl`. El del navegador no puede dar formato profesional. |
| Dónde van los botones de recálculo | Donde el usuario cambia algo que mueve el P&L y hoy tiene que irse a otra pantalla. |
| Estructura de Admin | Se ordena lo que ya existe y se completa la creación de usuarios. |
| Textos y rótulos | En español, con el tono del resto de la app. |

### ⛔ NO tomadas — quedan frenadas aunque el owner no esté

Que no esté es **la razón para no hacerlas**, no para hacerlas.

* **Cambiar cualquier número financiero.** Ningún monto, tasa, porcentaje ni
  reparto se toca. Si una mejora exigiera eso, se documenta y se frena.
* **Tocar escenarios enllavados.** Son fotos cerradas.
* **Borrar datos.** Nada de `DELETE` sobre dato del owner.
* **Renombrar el código del hotel.** Existe el botón; se usa cuando él decida.
* **Decidir supuestos de negocio.** Si una auditoría pide un % de cobro, un
  criterio de reparto o una regla contable, **se pregunta, no se inventa**.
* **Correr el barrido de cuentas contra producción.** Las auditorías son de
  lectura sobre el código; lo que toque la base va con ensayo y `rollback`.

---

## Las fases

### Fase 0 · Auditorías *(en curso)*

Seis auditorías paralelas, todas de solo lectura. Son las que deciden el resto —
sin ellas, construir sería adivinar.

1. **Exports a Excel** — qué pantalla exporta, cómo, y con qué calidad.
2. **Planning → cuenta → P&L** — qué se puede digitar que NO llega al P&L.
3. **Cobertura de cuentas** — cuentas sin destino y líneas sin origen.
4. **Tab Admin y usuarios** — qué hay y qué falta para crear usuarios.
5. **Recálculo** — dónde falta el botón y si el fallo se ve o se traga.
6. **Antes de clonar** — supuestos de Corcovado embebidos, y qué daría valor a
   los cuatro hoteles.

### Fase 1 · Lo que rompe

Lo que las auditorías marquen como **plata que no llega al P&L** o **fallo
silencioso**. Va primero porque es lo único que hace que un número esté mal.

### Fase 2 · Exports a Excel

Los que existen se llevan al formato de la casa; los que faltan se construyen.
**El tab Planning primero y uno por uno**, como pidió el owner.

### Fase 3 · Recálculo

Botones donde hagan falta, y que un fallo **se vea**. Hay antecedente de un
recálculo que se revertía entero sin dejar rastro.

### Fase 4 · Admin y usuarios

Ordenar el tab y completar la creación de usuarios por correo y nombre.

### Fase 5 · Antes de clonar

Lo que la auditoría 6 recomiende y sea seguro hacer sin decisiones de negocio.

---

## Cómo se trabaja

* **Nada se da por bueno sin verificar.** Cada cambio con su prueba, y las 728
  que ya existen tienen que seguir pasando.
* **Se despliega por tanda**, no todo junto al final: si algo sale mal, se sabe
  qué lo causó.
* **Lo que se frene se escribe acá**, con el motivo — no se deja como silencio.

---

## Bitácora

*(se va llenando a medida que avanza)*

| fase | qué pasó |
|---|---|
| 0 | Seis auditorías lanzadas. |
