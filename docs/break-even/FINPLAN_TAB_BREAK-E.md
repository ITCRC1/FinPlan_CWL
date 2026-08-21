# FinPlan — Tab `Break-E` (interfaz)

**Versión 2** — corregida tras revisión con el método de 7 lentes.

Especificación de navegación y pantallas. El cálculo, el modelo de datos, la seguridad y la
carga inicial están en `FINPLAN_BREAK_EVEN.md`.

Propiedad piloto: SCP Corcovado Wilderness Lodge (CWL).

---

## 1. Estructura de navegación

```
Break-E
├── Resumen              (default)
├── Por Departamento
├── Sensibilidad                          [Fase 2]
├── Escenarios                            [Fase 3]
└── Configuración
    └── un sub-tab por departamento activo, generado desde la tabla be_department
        Rooms · F&B · Spa · Tours · Gift Shop · Transportation · Innoceana ·
        Laundry · A&G · Sales & Marketing · Maintenance · Information System ·
        Utility · Property Expenses · Sin Clasificar
```

**Los sub-tabs de Configuración no se escriben a mano.** Se generan desde `be_department`
filtrando `status = 'active'` y ordenando por `display_order`, con el `slug` como llave de
ruta. Hoy CWL da 14; hay 8 departamentos en `pending_classification` que aparecen solos cuando
se clasifiquen, sin tocar código.

Rutas (mismo slug `break-e` que la API, sin desalineación):

```
/properties/[propertyId]/break-e                        → redirige a /resumen
/properties/[propertyId]/break-e/resumen
/properties/[propertyId]/break-e/por-departamento
/properties/[propertyId]/break-e/sensibilidad
/properties/[propertyId]/break-e/escenarios
/properties/[propertyId]/break-e/configuracion          → redirige al primer departamento
/properties/[propertyId]/break-e/configuracion/[deptSlug]
```

Con 15 sub-tabs el ancho se desborda: usar tabs con scroll horizontal y flechas, nunca wrap a
dos filas.

### 1.1 Barra de contexto global

Visible en los cinco sub-tabs y fija al hacer scroll:

- **Propiedad**
- **Periodo** — mes / YTD / Full Year
- **Versión de dato** — `ACTUAL` / `BUDGET` / `FORECAST`. **Obligatorio, sin valor implícito.**
  Es lo que distingue un equilibrio correcto de uno calculado sobre la base equivocada, y los
  dos se ven idénticos en pantalla.
- **Escenario activo** — Fase 3

Cambiar cualquiera recalcula todo sin salir del sub-tab.

---

## 2. Sub-tab `Configuración`

Es el corazón del módulo: aquí se define cuánto de cada cuenta es fijo y cuánto variable.

### 2.1 Layout de cada departamento

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  Rooms                                     46 líneas · 138 cuentas GL          │
│  Costo total FY $474,249    Variable $431,149 (91%)    Fijo $43,100 (9%)       │
├───────────────────────────────────────────────────────────────────────────────┤
│  [ Aplicar a la selección: % Variable [___] → Aplicar ]      [Restablecer]    │
│  Buscar [________]   Sección [Todas ▾]   Origen [Todos ▾]                     │
├───────────────────────────────────────────────────────────────────────────────┤
│  ▾ PAYROLL                                 16 líneas · $325,705                │
│  ☐ Cuenta  Descripción              Monto FY   % Var   % Fijo   $Var    $Fijo │
│  ☐ 6000    Salary and Wages         $182,700   [100%]    0%   182,700      -  │
│  ☐ 6001    Overtime                       $0   [100%]    0%         -      -  │
│  …                                                                             │
│  ▾ OPERATING EXPENSES                      30 líneas · $148,544                │
│  ☐ 7065    Cleaning Supplies         $13,800   [100%]    0%    13,800      -  │
│  ☐ 7150    Dues and Subscriptions     $2,400     [0%]  100%         -   2,400 │
│  …                                                                             │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Columnas

| Columna | Editable | Notas |
|---|---|---|
| checkbox | — | Edición masiva |
| Cuenta GL | No | `dept_code:account`. Si `map_source = LINEA`, chip **LÍNEA** en vez del número |
| Descripción | No | |
| Monto FY | No | Del periodo y versión seleccionados. **Sin esta columna se edita a ciegas** |
| **% Variable** | **Sí** | Numérico 0–100, paso 5. Único campo editable |
| % Fijo | No | `100 - % Variable`, en vivo al teclear |
| $ Variable / $ Fijo | No | Monto × porcentaje |
| Excluido del BE | No | Chip gris cuando `excluded_from_be = true`; el input queda bloqueado |
| Clasif. original | No | Columna opcional, oculta por defecto |

La sección es agrupador, no columna.

### 2.3 Comportamiento

- **Agrupación por sección**, colapsable, con subtotal de líneas y monto en el encabezado, y su
  propio "aplicar % a todo el grupo".
- **Edición masiva**: seleccionar filas y aplicar un %, o seleccionar toda la sección. Es el
  flujo real — nadie va a teclear 467 porcentajes uno por uno.
- **Guardado**: autosave con debounce de 800 ms por fila, indicador por fila
  (guardando / guardado / error), toast solo en error. Nunca un botón "Guardar" global que se
  pierda al cambiar de tab.
- **Validación**: 0 ≤ % ≤ 100 en cliente **y** en servidor (`CHECK` en la columna). Fuera de
  rango, borde rojo y no se envía el PATCH.
- Al cambiar un %, los totales del grupo y del departamento se recalculan en el cliente de
  inmediato; el resto del módulo se invalida y refetchea.
- **Última edición**: hover sobre el % muestra `updated_by` / `updated_at`. Es el último cambio,
  no un historial — el historial completo requiere tabla de auditoría y queda para Fase 3. No
  prometer en la UI lo que el modelo de datos no guarda.
- **Restablecer**: vuelve el departamento a la semilla (`Variable` → 100%, `Fixed Cost` → 0%).
  Confirmación indicando cuántas líneas se van a pisar.
- **Solo lectura**: con rol sin edición financiera los inputs se deshabilitan — pero la
  autorización real está en el endpoint, no aquí.

### 2.4 Contenido por departamento (CWL, Budget 2025 Dec)

| Sub-tab | slug | Líneas | Cuentas GL | Costo FY | LÍNEA | Secciones |
|---|---|---|---|---|---|---|
| Rooms | `rooms` | 46 | 138 | $474,249 | 0 | PAYROLL 16 · OPEX 30 |
| F&B | `fb` | 55 | 53 | $544,907 | 2 | COS 2 · PAYROLL 16 · OPEX 37 |
| Spa | `spa` | 43 | 43 | $48,114 | 0 | PAYROLL 16 · OPEX 27 |
| Tours | `tours` | 28 | 26 | $293,080 | 2 | PAYROLL 17 · COS 2 · OPEX 9 |
| Gift Shop | `gift-shop` | 9 | 8 | $13,399 | 1 | COS 1 · OPEX 8 |
| Transportation | `transportation` | 26 | 24 | $157,425 | 2 | PAYROLL 16 · COS 2 · OPEX 8 |
| Innoceana | `innoceana` | 26 | 25 | $125,478 | 1 | PAYROLL 17 · OPEX 9 |
| Laundry | `laundry` | 1 | 0 | $2,261 | 1 | COS 1 |
| A&G | `ag` | 51 | 80 | $616,073 | 1 | PAYROLL 16 · OPEX 35 |
| Sales & Marketing | `sales-marketing` | 44 | 44 | $433,387 | 0 | PAYROLL 16 · OPEX 28 |
| Maintenance | `maintenance` | 48 | 48 | $476,415 | 0 | PAYROLL 16 · OPEX 32 |
| Information System | `information-system` | 52 | 51 | $41,508 | 1 | PAYROLL 17 · COS 5 · OPEX 30 |
| Utility | `utility` | 11 | 7 | $259,233 | 4 | OPEX 11 |
| Property Expenses | `property-expenses` | 27 | 2 | $712,513 | 25 | Rent & Mgmt Fees 4 · Insurance 6 · Financial 2 · Capital 2 · Depreciation 9 · No Deducibles 3 · **Income Tax 1** |
| **Total** | | **467** | **549** | **$4,198,042** | **40** | |

Notas que la UI debe reflejar:

- **Property Expenses** — la línea de **Income Tax ($75,044)** con fondo gris, input bloqueado
  y la leyenda *"excluido del punto de equilibrio: es función del resultado, no un costo
  fijo"*. Sigue en la tabla para que el P&L cuadre.
- **Property Expenses** tiene 25 de 27 líneas en `LINEA`: el banner de §2.5 va a estar casi
  siempre visible ahí.
- **Gift Shop** existe como departamento propio desde la v2 (9 líneas que estaban etiquetadas
  como Tours). Además, el P&L tiene **16 líneas de planilla de Gift Shop sin clasificar**
  (filas 664–679, todas en cero). Si algún día se usan, hay que clasificarlas.
- **Laundry** tiene una sola línea, y `LINEA`. Aun así lleva sub-tab propio, por consistencia.
- **Departamentos sin ingreso** (A&G, Sales & Marketing, Maintenance, Information System,
  Utility, Property Expenses): el encabezado dice *"costos no distribuidos — no generan margen
  de contribución"*, para que nadie busque un % MC que no existe. El flag viene de
  `be_department.generates_revenue`, no de una lista en el código.

### 2.5 Banner de revisión

Cuando el departamento tiene filas con `map_source = LINEA`:

> ⚠ **25 líneas de este departamento están mapeadas a nivel de línea P&L, no a una cuenta GL
> concreta.** Son asignaciones por sección. Revisar antes de ajustar los porcentajes.
> [Ver solo esas líneas]

### 2.6 Sub-tab `Sin Clasificar`

Alimentado por `GET /break-e/unclassified`. Cuentas GL con movimiento en el periodo que no
tienen regla. Se tratan como **100% fijo** mientras tanto.

Columnas: depto GL · cuenta · nombre · monto · línea P&L · **[Clasificar]**. El botón abre un
modal para asignar departamento, sección y % variable, y crea la fila.

Badge rojo con el conteo. En cero, el tab se deshabilita con "✓ Todo clasificado".

Esta pantalla es lo que evita que el modelo se degrade en silencio cuando crece el catálogo.
Su espejo — reglas huérfanas cuya cuenta GL fue eliminada o renombrada en el master data —
aparece en la misma pantalla, en una segunda tabla, con la acción **[Archivar regla]**.

---

## 3. Los otros cuatro sub-tabs

### 3.1 `Resumen` — Fase 1

1. **Estado de resultados en costeo variable** — Ingresos, (−) Variables, (=) MC + % MC,
   (−) Fijos, (=) Resultado antes de impuestos, (−) Impuesto de renta, (=) Resultado neto.
2. **Punto de equilibrio** — Ingreso de equilibrio anual, PE como % del presupuesto, margen de
   seguridad en $ y %, apalancamiento operativo.
   El **equilibrio mensual** se muestra rotulado *"prorrateo lineal — no refleja
   estacionalidad"*. Con ocupación de 52% en febrero a 0.7% en septiembre, un umbral plano no
   describe ningún mes real. El cálculo mes a mes es Fase 2.
3. **Equilibrio en métricas de habitaciones** — % ocupación de equilibrio vs presupuestada,
   holgura en puntos, noches necesarias, TRevPAR de equilibrio. Con la nota visible de que
   suponen mezcla de ingresos constante.
4. **Gráfico CVP** — ingreso y costo total contra volumen, con el cruce marcado y una línea
   vertical en el presupuesto.

Chip permanente: *"35% variable / 65% fijo · última edición: [usuario], [fecha]"*, con enlace a
Configuración.

Si `CM% ≤ 0`: no mostrar un equilibrio en blanco ni en cero, sino el mensaje *"el margen de
contribución es negativo: ningún nivel de ingreso cubre los costos fijos"*.

### 3.2 `Por Departamento` — Fase 1

Tabla: Departamento · Ingreso · Costo variable · Margen de contribución · % MC · Costo fijo
directo · Resultado · Ingreso de equilibrio del departamento.

Operativos arriba con subtotal; no distribuidos en bloque aparte, sin columnas de ingreso ni
% MC. Cada nombre enlaza a su sub-tab de configuración.

Fila **"Otros ingresos sin departamento de costo"** (Crowther Lab + Miscellaneous, $220,059)
con ícono de advertencia: entran al margen al 100% porque no tienen costo asignado, lo que
sobreestima el MC consolidado.

### 3.3 `Sensibilidad` — Fase 2

Matriz ocupación (20%–60%, pasos de 2.5 pp) × ADR (−20% a +20%, pasos de 5%). Celda = resultado
antes de impuestos. Escala rojo–amarillo–verde con el cero anclado en amarillo, y la celda del
presupuesto con borde marcado. Rangos configurables. Exportar a Excel.

### 3.4 `Escenarios` — Fase 3

Lista de escenarios guardados: nombre, autor, fecha, % variable global, ingreso y ocupación de
equilibrio. Acciones: Activar · Duplicar · Comparar (2 a 4 lado a lado) · Eliminar.

Siempre existe un escenario `Base` no eliminable, que es la semilla 100/0.

---

## 4. Fases

| Fase | Contenido | Por qué |
|---|---|---|
| **1** | Configuración (14 departamentos + Sin Clasificar) · Resumen · Por Departamento. Solo CWL. | Es el 80% del valor. Sin la clasificación ajustada, todo lo demás decora un número que se sabe equivocado |
| **2** | Sensibilidad · equilibrio mensual con estacionalidad real · multipropiedad | |
| **3** | Escenarios y comparación · historial de auditoría por fila | |

**Ganchos que se dejan puestos desde la Fase 1 sin construir la funcionalidad:**
`be_department` como tabla · `excluded_from_be` como columna · `data_version` como parámetro
obligatorio · `be_classification_snapshot` · `scenario_id` nullable en las consultas.

---

## 5. Notas de implementación

- **Estado**: React Query con
  `queryKey: ['break-e', propertyId, period, dataVersion, scenarioId]`. Un PATCH en
  Configuración invalida esa key completa.
- **Optimistic update** en el PATCH de `pct_variable`; en error, revertir la celda y toast.
- **Paginación**: ninguna. El departamento más grande tiene 55 líneas; virtualizar es
  complejidad innecesaria y rompe el "seleccionar toda la sección".
- **Exportar a Excel** en Resumen, Por Departamento, Sensibilidad y en cada departamento de
  Configuración. El formato debe coincidir con `BREAK_EVEN_CWL.xlsx`.
- **Persistencia de navegación**: recordar el último sub-tab y departamento por propiedad.
- **Periodos cerrados**: si el periodo seleccionado tiene snapshot, Configuración se muestra en
  solo lectura con un banner *"periodo cerrado — clasificación congelada el [fecha]"*. Editar
  requiere reabrir el periodo.
