# Informe operativo de variaciones — especificación

> **Qué es:** el documento de trabajo del control de costos. Un informe mensual
> que compara el Actual del Pre-Cierre contra el Budget y el Forecast, por
> departamento y a máximo detalle, y que termina en **preguntas concretas para
> cada gerente**. No es el resumen ejecutivo a propietarios.
>
> **Para qué existe este archivo:** para que el informe salga **igual todos los
> meses** — mismas partes, mismo orden, mismas reglas, mismos cuadros. Si se
> pide «el informe operativo de octubre», se sigue esto y nada más.
>
> **Modelo de referencia:** `CWL_Informe_Operativo_Setiembre_2026.docx`, hecho
> el 2026-10-07. Su análisis vive en
> `backend/app/seed_data/CWL/informes/2026_09.json` y sirve de plantilla.

---

## 1. Cómo se activa

### Opción A — el botón, dentro de FinPlan

*Pre-Closing → Month-End Close — P&L →* **⬇ Informe operativo**

Elegís mes y año arriba, le das clic y baja el `.docx`. Corre en el servidor, así
que funciona desde cualquier máquina y sin instalar nada.

> **El botón trae los CUADROS.** El análisis sale solo si ya está escrito para
> ese mes. Si no lo está, el documento baja con los 53 cuadros completos y marcas
> `[PENDIENTE]` en el texto, y el botón lo avisa.
>
> **El servidor no llama a ningún modelo.** Sin llave de API, sin costo y sin
> riesgo de que una cifra inventada entre a un documento que circula.

El botón también verifica el cuadre y avisa si no dio.

### Opción B — pedir el análisis en el chat

```
/informe octubre 2026
```

Claude lee esta especificación, saca los cuadros, mira el detalle del mayor,
escribe el análisis, lo deja guardado en
`backend/app/seed_data/<HOTEL>/informes/<año>_<mes>.json` y manda el Word. A
partir de ahí **el botón de la opción A ya entrega ese mes completo**, para
cualquiera del equipo.

### Opción C — la línea de comandos

```bash
backend/.venv/Scripts/python.exe informes/armar.py --anio 2026 --mes 10
```

Un solo comando: si falta el corte del mes lo extrae de producción solo. La
segunda corrida **no** toca producción —usa el corte guardado—, que es lo que uno
quiere al reescribir un comentario. Para forzar lectura nueva, `--extraer`.

**El análisis es el trabajo real.** Los cuadros son mecánicos y no se opinan.

### Requisitos antes de empezar

| Requisito | Dónde se verifica | Si falta |
|---|---|---|
| El Pre-Cierre del mes está subido | Pre-Closing → selector de escenario | `extraer.py` se detiene y lo dice |
| El **mayor** del mes está subido | Scenarios → Auditoría del mayor | El informe sale sin proveedores ni asientos; `extraer.py` avisa |
| Existe un BUDGET del año | — | `extraer.py` se detiene |
| Existe un FORECAST que nombre el mes | — | Usa el más reciente y lo avisa |
| El escenario ACTUAL tiene estadística de habitaciones | — | El informe sale sin ocupación ni ADR; `extraer.py` avisa |
| Las credenciales de la base están en caché | `%TEMP%\claude\pgvars.json` | `railway variables --service Postgres --json` |

---

## 1-bis. Volver a generar un mes ya hecho

### Si no cambió nada en el sistema

```
/informe setiembre 2026
```

Sale **idéntico**: el análisis está guardado en `seed_data/<HOTEL>/informes/` y el corte
en `app/informes/datos/`. Por defecto **no vuelve a leer producción**, y eso es
deliberado — un informe que ya circuló no debería cambiar de números solo porque
se volvió a imprimir.

### Si se volvió a subir el mes

Si se resubió el P&L del Pre-Cierre, o el mayor en *Auditoría del mayor*, o se
corrigió una clasificación:

```bash
backend/.venv/Scripts/python.exe informes/armar.py --anio 2026 --mes 9 --extraer
```

**`extraer.py` compara contra la extracción anterior y dice qué se movió**, antes
de sobreescribir. Imprime los totales por escenario y clase que cambiaron, si
cambió el archivo del mayor o el número de líneas, si cambió el escenario
elegido, y las doce cuentas con más diferencia:

```
======================================================================
CAMBIO desde la extraccion anterior - REVISAR EL TEXTO
======================================================================
   ACT opex          105,051.60 ->     110,051.60   (+5,000.00)
   mayor: 5,000 lineas -> 5,105 lineas
   archivo del mayor: <...v1.xlsx> -> <...v2.xlsx>
     cost     0120 - 5101       6,260.83 ->     9,460.83
```

> ⚠️ **Los cuadros se actualizan solos; el texto no.** Las cifras escritas en la
> narrativa quedan como estaban. Un cuadro que dice una cosa y el párrafo de al
> lado que dice otra es peor que no tener informe. Por eso la comparación existe:
> la lista de arriba es exactamente la lista de párrafos que hay que repasar.

La extracción anterior queda guardada en `app/informes/datos/<año>_<mes>.anterior.json`.

---

## 2. Las reglas que hacen que los números aten

Son cinco y **ninguna es negociable**. Cada una se violó alguna vez y cada vez
costó un informe que no se podía discutir.

### 2.1 Los totales por clase NO se recalculan

Salen de `gasto_por_clase_api._por_mes`, que es la misma función que alimenta la
pantalla *Month-End Close — P&L*. Reimplementar esa suma es la forma más fácil
de que el informe diga un número y la pantalla otro.

### 2.2 Hay que pasarle el objeto `escenario`, no solo su id

```python
sc = await db.get(Scenario, sid)
await g._por_mes(db, sid, detalle=det, escenario=sc)   # ← con el objeto
```

De eso depende la regla de allocation. Sin el objeto el parámetro queda en
`None`, la regla cae al caso general y los totales se van — medido: **$10.943,00
de diferencia** en el costo de setiembre.

### 2.3 El ingreso no viene en la fila de `_por_mes`

Esa fila trae las cuatro clases de **gasto** (`payroll`, `cost`, `opex`,
`property`). El ingreso se suma de su apertura, que la misma función dejó en
`detalle`. Ya lo hace `Datos.total()`.

### 2.4 Las cuentas se agrupan por `(departamento, cuenta)` — **nunca** por nombre

El real escribe `UTILITIES - OIL` y el presupuesto `Oil (Boat and Equipment)`
para la misma **7395**. Agrupar por nombre las parte en dos filas que no se ven
como la misma cuenta, y el cuadro muestra dos variaciones donde hay una.

### 2.5 El detalle del mayor pasa por el puente y después por la consolidación

```python
dept = pl_engine.consolidate_dept(puente.get(seg2, seg2))
```

El mayor guarda el departamento de **Integrity** y el cuadro muestra el de
**FinPlan**. Sin el puente, el `0128` (Private Bar) no aparea con el `0121`.
Es el mismo camino que usa el Audit Integral, a propósito.

### 2.6 El cuadre obligatorio

`armar.py` lo imprime siempre. **No se publica un informe sin verificarlo:**

1. Ingreso, gasto y GOP de los tres escenarios contra la pantalla.
2. `GOP del reporte − GOP del motor` tiene que dar **cero**. Son dos caminos al
   mismo número: por naturaleza —ingreso menos clases 5/6/7— y por departamento.
   Si dice `NO COINCIDE`, el mensaje dice si la causa es el crédito de reparto
   —que volvió a quedar fuera— o es otra. **No se publica hasta entenderlo.**

---

## 3. Las cuatro advertencias de lectura

Van en la sección 1.2 del informe **todos los meses**. No son adorno: sin ellas
los números llevan a la conclusión equivocada.

**A · El Pre-Cierre y el presupuesto no miden el mismo perímetro.**
Cafetería (0220), Lavandería (0161) y Laundry Revenue (0162) se muestran en la
columna del Pre-Cierre y se excluyen en Budget y Forecast. Su gasto aparece como
variación desfavorable completa cuando en parte **sí** está presupuestado, solo
que en otro departamento o en otra cuenta.

**B · El Pre-Cierre solo contiene los últimos meses subidos.**
No hay acumulado válido desde esa fuente. En setiembre 2026 tenía agosto y
setiembre; un YTD calculado ahí daba −91% de ingreso y era un artefacto de la
carga. El informe es **mensual**, con comparativo secuencial contra el mes
anterior cargado.

**C · Cafetería y Lavandería netean a cero** —desde el 2026-10-09—.
El espejo del Pre-Cierre muestra el *gasto* de los departamentos de allocation
—para que la plata no se esconda en la revisión— **y también su crédito** de
reparto, la cuenta 4999.

Hasta esa fecha el crédito se descartaba y el GOP del reporte salía peor que el
real por exactamente esa cifra: $18.789,30 en setiembre 2026 y $35.763,30 en los
dos meses cargados — el número del aviso amarillo que mostraba la pantalla.

→ **El invariante ahora es que los dos GOP sean iguales.** `armar.py` lo
verifica siempre y dice `NO COINCIDE` si vuelve a separarse, nombrando si la
causa es el crédito o es otra.

**D · El Pre-Cierre no trae estadística de habitaciones.**
Por eso el encabezado de la pantalla muestra «—» en ocupación, ADR y RevPAR. El
informe la toma de `actual_room_stats` del escenario ACTUAL, que sí las tiene, y
lo dice en la nota al pie del cuadro.

---

## 4. Las doce secciones

| # | Sección | Cuadros (automáticos) | Narrativa (se escribe) |
|---|---|---|---|
| 1 | Propósito y cómo leer | Fuentes · advertencias A-D | — |
| 2 | Resumen ejecutivo operativo | El mes en una tabla | `resumen`, `hallazgos` |
| 3 | Contexto operativo | KPI de habitaciones · por tipo de villa · secuencial | `contexto`, `contexto_kpi`, `contexto_tipos`, `contexto_secuencial`, `contexto_nota` |
| 4 | Departamentos operativos | Resumen + uno por departamento | `dept_resumen`, `dept.<nombre>` |
| 5 | Overhead | Resumen + uno por departamento | `dept.<nombre>` |
| 6 | Planilla transversal | Por concepto · por departamento · conceptos sin presupuesto | `payroll_conceptos`, `payroll_nota` |
| 7 | Costo de ventas y márgenes | Margen por departamento | `margenes`, `margen_detalle` |
| 8 | Opex | Las 20 cuentas que lo mueven | `opex_favorables`, `opex_impactos` |
| 9 | Gastos de propiedad | Clase 8 por cuenta | `propiedad_notas` |
| 10 | Hallazgos de clasificación | El crédito 4999 | `clasificacion`, `sin_presupuesto`, `brechas` |
| 11 | Agenda por responsable | — | `agenda` |
| 12 | Anexos | A1 ingreso · A2 costo · A3 opex · A4 planilla · A5 metodología | — |

### El orden de los departamentos

Está en `app/informes/datos.py` y es el del P&L. **No se reordena por monto**: ordenado por
monto el informe se lee como una lista de sorpresas; ordenado como el P&L se lee
como el estado de resultados, que es contra lo que se compara.

```
OPERATIVOS: Rooms (0110) · A&B (0120+0121) · Spa (0130+0140) · Tours (0150)
            Gift Shop (0165) · Transportación (0152) · Lavandería (0161+0162)
            Innoceana (0155) · Sostenibilidad (280) · Cafetería (0220)

OVERHEAD:   Administración (0180) · Ventas y Mercadeo (0190)
            Mantenimiento (0200) · Sistemas (0230) · Utilities (0210+0205)
```

Algunos son la suma de varios códigos, y eso **no** es un detalle: A&B junta el
Private Bar (0121) y el Spa vive partido entre 0130 (donde lo carga el
presupuesto) y 0140 (donde lo registra el real). Separados no comparan.

### Cada departamento, en cuatro planos

Siempre los mismos, siempre en este orden:

1. **Ingreso** — contra Budget y Forecast, y contra el volumen que lo debería
   explicar (noches, huéspedes, cobertura).
2. **Costo de ventas** — en valor absoluto **y como % del ingreso que le
   corresponde**. Un costo que baja menos que su ingreso es margen perdido,
   aunque la variación absoluta parezca favorable.
3. **Planilla** — contra Budget, abierta por concepto cuando el desvío está en
   horas extra, vacaciones o provisiones y no en el salario base.
4. **Opex** — contra Budget, separando **diferimiento de calendario** de **gasto
   estructural nuevo**.

Y cierra en **preguntas al gerente**: lo que el mayor no puede responder. Esas
preguntas son el producto del informe.

---

## 5. Cómo se escribe el análisis

### 5.1 Los hallazgos de la sección 2

Entre cinco y siete, **ordenados por impacto en dólares sobre el resultado del
mes** — no por tamaño absoluto de la cuenta. Cada uno lleva título, monto entre
paréntesis y un párrafo que nombra la cuenta, el departamento y el proveedor o
concepto que lo produjo.

Criterio para entrar: que mueva el resultado del mes en una cifra que el dueño
reconocería, o que revele un problema de proceso (no de monto) que se va a
repetir.

### 5.2 La regla del color

```
Ingreso y resultado:  más = verde,  menos = rojo
Gasto:                más = ROJO,   menos = verde
```

En el código, `var()` para ingreso y resultado; `var_gasto()` para gasto. Se
invierte porque gastar menos de lo presupuestado es favorable. Equivocarse acá
hace que todo el informe se lea al revés.

### 5.3 Favorabilidad: ahorro o diferimiento

**La distinción más importante del informe**, y la única que no sale de la base.
Por cada partida favorable hay que decidir:

- **Ahorro estructural** — no vuelve. Renegociación, cierre de un servicio.
- **Diferimiento** — vuelve, y hay que decir cuándo. Ferias, medios,
  mantenimiento programado.
- **Reclasificación** — no es ni lo uno ni lo otro: el gasto existe, en otra
  cuenta.

La pista más fiable es el **Forecast**: si el Forecast del mes siguiente sube esa
cuenta, el ahorro era diferimiento. En setiembre, Trade Shows no se gastó
($12.600) y el Forecast lo subía a $32.600 — el ahorro era una obligación
pendiente.

### 5.4 Las preguntas al gerente

Una pregunta sirve si cumple las tres:

1. **Nombra la cifra** y su contraparte presupuestada.
2. **Nombra la evidencia** del mayor — proveedor, número de asientos, concepto.
3. **No se puede contestar desde el sistema.** Si la respuesta está en la base,
   no es una pregunta: es un dato que faltó buscar.

> ✅ «SINAC $3.232,68 de entradas contra $3.150,17 de ingreso TOTAL de tours.
> ¿Cuántos pax de parque nacional y a qué precio de venta? Si la entrada se cobra
> al huésped, este renglón no puede exceder su propio ingreso.»
>
> ❌ «¿Por qué subió el costo de tours?»

### 5.5 El tono

Se escribe para alguien que va a sentarse con un gerente a discutir. Directo, sin
adjetivos, y **sin acusar**: el informe muestra el número y la evidencia, y la
explicación la da el gerente. Cuando una variación es de registro y no de
gestión, se dice en la sección 10 y **no** se le lleva al gerente — llevarle una
variación que es un error de cuenta destruye la credibilidad del resto.

---

## 6. Las claves de narrativa

Todas opcionales: si falta una, sale `[PENDIENTE: clave]` y `armar.py` la lista.

| Clave | Tipo | Va en |
|---|---|---|
| `propiedad` | texto | Portada |
| `resumen` | lista de párrafos | 2 |
| `hallazgos` | lista de `(título, monto, texto)` | 2.2 |
| `contexto` | lista de párrafos | 3 |
| `contexto_kpi` | lista de párrafos | bajo el cuadro de KPI |
| `contexto_tipos` | lista de párrafos | bajo el cuadro por villa |
| `contexto_secuencial` | lista de párrafos | bajo el secuencial |
| `contexto_nota` | `(título, texto)` | recuadro gris al cierre de 3 |
| `dept_resumen` | lista de párrafos | 4.0 |
| `dept.<nombre>.comentario` | lista de párrafos | cada departamento |
| `dept.<nombre>.cuentas` | lista de `(depto, cuenta, etiqueta)` | tabla del mayor |
| `dept.<nombre>.preguntas` | lista de texto | cierre del departamento |
| `overhead_resumen` | lista de párrafos | 5.0 |
| `payroll_conceptos` | lista de párrafos | 6.2 |
| `payroll_nota` | `(título, texto)` | recuadro en 6.2 |
| `margenes` | lista de párrafos | 7.1 |
| `margen_detalle` | `{titulo, intro, cabeceras, filas, nota, cierre}` | 7.2 |
| `opex_favorables` | `{cabeceras, filas, nota, cierre}` | 8.2 |
| `opex_impactos` | `{cabeceras, filas}` | 8.3 |
| `propiedad_notas` | lista de viñetas | 9 |
| `clasificacion` | `{intro, cabeceras, filas, nota}` | 10.2 |
| `sin_presupuesto` | `{intro, cabeceras, filas, nota}` | 10.3 |
| `brechas` | lista de viñetas | 10.4 |
| `agenda` | lista de `(responsable, foco, [preguntas])` | 11 |

`<nombre>` es el nombre del departamento tal como aparece en `OPERATIVOS` y
`OVERHEAD` de `app/informes/datos.py` — `"Rooms"`, `"Alimentos y Bebidas"`, `"Utilities /
Energia"`…

En las filas de tabla, una celda puede ser `texto` o `(texto, estilo)`, con
estilo `"tot"` (negrita + fondo), `"sec"` (sección), `"sub"`, `"neg"` (rojo),
`"pos"` (verde) o `"gris"`.

---

## 7. Los archivos

⚠️ **El generador vive dentro de `backend/`**, y no es un detalle de orden:
Railway despliega solo esa carpeta, así que un generador fuera de ahí no existe
para el servidor y el botón no podría armar nada.

```
informes/
├── INFORME_OPERATIVO.md              ← esto
├── extraer.py                        guardar el corte del mes (solo lectura)
├── armar.py                          el Word, desde la línea de comandos
└── CWL_Informe_Operativo_<Mes>_<Año>.docx

backend/app/
├── api/informe_api.py                el endpoint del botón
├── seed_data/<HOTEL>/informes/
│   └── <año>_<mes>.json              EL ANÁLISIS — uno por mes
└── informes/
    ├── extraccion.py                 el corte, desde una sesión
    ├── armador.py                    ensambla el documento y calcula el cuadre
    ├── datos.py                      la capa de datos y el orden del P&L
    ├── formato.py                    estilos, tablas, colores
    ├── secciones.py                  secciones 1-3 + el bloque departamental
    ├── secciones2.py                 secciones 4-12
    └── datos/<año>_<mes>.json        el corte (no se versiona, no se edita)
```

**El análisis vive en `seed_data/<HOTEL>/` y no en `app/`.** Es contenido de una
propiedad: un clon no puede heredar el análisis de Corcovado, y
`tests/test_un_hotel_por_instalacion.py` no deja que su nombre viva dentro de
`app/` como valor.

El corte de `informes/datos/` es la foto del mes: una vez extraído, el informe se
rearma cuantas veces haga falta **sin volver a tocar producción**.

## 8. Lista de verificación antes de entregar

- [ ] `extraer.py` corrió sin avisos, o los avisos están explicados en la sección 1.2.
- [ ] El cuadre de `armar.py` coincide con la pantalla en los tres escenarios.
- [ ] `GOP reporte − GOP motor` da cero y dice **coincide**.
- [ ] `armar.py` no lista claves de narrativa pendientes.
- [ ] Ningún `[PENDIENTE]` en el documento.
- [ ] Los hallazgos de la sección 2 están ordenados por impacto, no por tamaño.
- [ ] Cada favorabilidad de opex está clasificada en ahorro / diferimiento / reclasificación.
- [ ] Cada pregunta nombra la cifra, la evidencia del mayor, y no se puede contestar desde el sistema.
- [ ] Las variaciones que son de registro están en la sección 10 y **no** en la agenda del gerente.
- [ ] La sección 10.2 está actualizada: los cinco casos de setiembre pueden haberse corregido.

---

## 9. Lo que cambia mes a mes y hay que volver a mirar

Esto no es estructura: es el estado del sistema en setiembre 2026. **Verificar
cada mes** — si ya se arreglaron, el informe lo tiene que decir.

| Pendiente | Efecto si sigue |
|---|---|
| El Pre-Cierre no carga estadística de habitaciones | Ocupación y ADR vienen de otra tabla |
| Cafetería presupuestada en 5700 y real en 5420 | Variación de $10.764,88 en vez de $3.964,88 |
| Costo de tours presupuestado en 0152 y real en 0150 | Dos variaciones falsas donde hay un hecho |
| Costo de internet en 5700/5702/5704 vs 5400/5401 | Cuatro variaciones donde hay una |
| Costo del Gift Shop presupuestado en 0151 | Margen de 100% aparente en 0165 |
| Spa presupuestado en 0130 y real en 0140 | Solo compara si se suman los dos |
| 6001, 6002 y 6023 con presupuesto cero o simbólico | Toda variación de planilla sale desfavorable siempre |

---

## 10. Para otra propiedad

`extraer.py` toma `--hotel` (por defecto `CWL`). Lo que habría que revisar antes
de usarlo en otra:

- `OPERATIVOS` y `OVERHEAD` en `app/informes/datos.py` — los códigos de departamento y cómo
  se agrupan son de Corcovado.
- `EXCL` — los departamentos de allocation pueden ser otros.
- El puente de Integrity a FinPlan vive en
  `backend/app/seed_data/<HOTEL>/mapd_integrity.json`.
