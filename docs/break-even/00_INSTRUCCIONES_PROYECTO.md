# FinPlan — Módulo Break-Even · Instrucciones del proyecto

Este documento es el punto de entrada. Léelo primero, antes que cualquier otro archivo del
proyecto.

---

## Qué se está construyendo

Un módulo de punto de equilibrio para **FinPlan**, el sistema de planeación financiera de
The Costa Rica Collection. Calcula el break-even de cada propiedad a partir del P&L, separando
cada cuenta del catálogo contable en una porción **variable** y una **fija**, con porcentajes
que el usuario edita por cuenta.

Propiedad piloto: **SCP Corcovado Wilderness Lodge (CWL)**.
Stack de FinPlan: **FastAPI + SQLAlchemy + PostgreSQL + Next.js**. No es Django.
El usuario trabaja en **Windows**.

---

## Archivos del proyecto y para qué sirve cada uno

| Archivo | Rol | Cuándo leerlo |
|---|---|---|
| `FINPLAN_BREAK_EVEN.md` | **Spec principal.** Modelo de datos, fórmulas, reglas de resolución, seguridad, carga inicial | Siempre. Es la fuente de verdad del backend |
| `FINPLAN_TAB_BREAK-E.md` | **Spec de interfaz.** Tab `Break-E`, sub-tabs, pantalla de configuración por departamento, fases | Al construir el frontend |
| `be_departments_seed.csv` | Catálogo de departamentos: 14 activos + 8 pendientes | Carga inicial |
| `be_classification_seed.csv` | 567 filas: cuenta GL → línea P&L → % variable inicial | Carga inicial |
| `BREAK_EVEN_CWL.xlsx` | Modelo de referencia funcionando, validado contra el P&L | Para verificar que los números del código coinciden |

Los dos CSV son los datos reales de CWL, ya mapeados y validados. **No regenerarlos ni
recalcularlos**: se cargan tal cual.

El Excel no se convierte en código. Sirve como prueba: si el módulo calcula algo distinto a lo
que da esa hoja con los mismos porcentajes, el módulo está mal.

---

## Qué construir primero

**Fase 1 — y solo la Fase 1 hasta que se apruebe.**

1. Tablas: `be_department`, `be_cost_classification`, `be_classification_snapshot`
   (spec §2), con sus constraints e índices.
2. Comando de carga de las dos semillas (spec §8), con el paso de verificación previa.
3. Motor de cálculo (spec §3) con las guardas de §3.4.
4. Endpoints de clasificación y de resultado, con autorización en el servidor (spec §7).
5. Frontend: tab `Break-E` con los sub-tabs **Resumen**, **Por Departamento** y
   **Configuración** (14 departamentos + Sin Clasificar).

**No construir en la Fase 1:** Sensibilidad, Escenarios, comparación de escenarios, historial de
auditoría por fila, multipropiedad. Los ganchos van puestos desde el inicio (tabla de
departamentos, `excluded_from_be`, `data_version`, snapshot), pero la funcionalidad no.

Trabajar por etapas con aprobación entre cada una. Al terminar cada bloque, mostrar el
resultado y esperar visto bueno antes de seguir.

---

## Reglas que no se negocian

Estas salieron de una revisión formal del spec y cada una corresponde a un error real que ya se
corrigió. Revertirlas rompe el módulo:

1. **`pct_variable` es el único campo editable.** El % fijo siempre se deriva como
   `1 - pct_variable`. Nunca guardar los dos.
2. **Los departamentos viven en la tabla `be_department`, nunca como enum en el código.** Hay 8
   departamentos pendientes que deben poder activarse sin un release.
3. **La llave es el `slug`, nunca el nombre.** Ocho nombres del origen traen doble espacio.
4. **`dept_code` y `account` van como string vacío, jamás NULL.** En Postgres `NULL ≠ NULL` y el
   `ON CONFLICT` del seed duplicaría filas en cada recarga.
5. **La exclusión del impuesto de renta es la columna `excluded_from_be`**, no una comparación
   de texto contra `'INCOME TAX'`.
6. **`data_version` es obligatorio en toda llamada de cálculo.** Sin valor implícito.
7. **Una cuenta sin regla de clasificación se trata como 100% fijo y se registra en
   `be_unclassified`.** Nunca asumir variable, nunca fallar en silencio.
8. **La autorización va en el endpoint, no en la UI.** Deshabilitar un input no protege nada.
9. **El equilibrio mensual se muestra rotulado como prorrateo lineal.** La ocupación de CWL va
   de 52% en febrero a 0.7% en septiembre; el promedio no describe ningún mes.
10. **Windows: forzar `encoding='utf-8'` explícito** al leer los CSV. Traen `Á`, `—` y `&`.

---

## Prueba de aceptación

Con las semillas cargadas sin modificar (todo `Variable` en 100%, todo `Fixed Cost` en 0%), el
módulo debe dar exactamente:

| Métrica | Valor esperado |
|---|---|
| Ingresos totales | $4,373,146 |
| Costos variables | $1,469,297 |
| Costos fijos (sin impuesto) | $2,653,701 |
| Margen de contribución | $2,903,849 (66.4%) |
| Resultado antes de impuestos | $250,148 |
| Resultado neto | $175,103 |
| Ingreso de equilibrio anual | $3,996,427 |
| Ocupación de equilibrio | 35.9% |
| Apalancamiento operativo | 11.6x |

Y por departamento, el costo total debe cerrar contra el P&L: Rooms $474,249 · F&B $544,907 ·
Spa $48,114 · Tours $293,080 · Gift Shop $13,399 · Transportation $157,425 · Innoceana
$125,478 · Laundry $2,261 · A&G $616,073 · Sales & Marketing $433,387 · Maintenance $476,415 ·
Information System $41,508 · Utility $259,233 · Property Expenses $712,513. Total $4,198,042.

Si algún número no cuadra, el problema está en el código, no en las semillas: ya están
validadas contra el P&L al centavo.

---

## Decisiones de negocio pendientes

Están implementadas con un valor provisional para no bloquear el arranque. **Si alguna se
vuelve relevante durante la construcción, preguntar antes de asumir:**

1. Versión de dato por defecto en pantalla — provisional: `BUDGET`.
2. Equilibrio mensual: lineal o estacional — provisional: lineal rotulado, estacional en Fase 2.
3. Escenarios compartidos o personales — provisional: compartidos por propiedad. Fase 3.
4. ¿Se congela la clasificación al cerrar el mes? — provisional: sí.
5. Filas `LINEA`: colapsadas a 18. Reversible si se prefiere crear las 40 cuentas en el master
   data de FinPlan.

---

## Contexto que conviene tener presente

- La semilla 100/0 no es un diagnóstico. Con toda la planilla marcada 100% variable el margen
  de contribución queda alto y el equilibrio bajo. En CWL la planilla es mayoritariamente de
  personal de planta, así que cuando el usuario ajuste los porcentajes el equilibrio va a subir
  de forma material. Medir eso es el propósito del módulo.
- Con 11.6x de apalancamiento operativo, tres puntos de ocupación borran el resultado del año.
  La pantalla de configuración no es un formulario más: es donde se define qué tan frágil es el
  negocio.
- 40 de las 467 líneas están mapeadas a nivel de línea P&L y no a una cuenta GL concreta. Están
  marcadas con `map_source = LINEA` y la UI debe señalarlas. 25 de ellas están en Property
  Expenses.
