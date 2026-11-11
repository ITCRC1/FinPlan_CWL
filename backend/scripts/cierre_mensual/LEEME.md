# Libro del Cierre Contable Mensual de CWL — en vivo

Owner, 2026-11-11: *«crear un nuevo archivo de excel en CWL para revisar el Cierre Contable Mensual. Que tenga todos
los detalles que tiene el archivo de GL pero que solo tenga la version de Actual para 2024-2025-2026. Que tenga la
version Precierre ... Budget 2026 y el Forecast. Que sea mensual, que yo pueda escoger el mes que quiero revisar y
extraer. y que tenga maximo detalle checkbook de gastos y checkbook de opex, ingresos y costos, posicion por posicion.»*

## Qué tiene

| Hoja | De dónde | Qué muestra |
|---|---|---|
| Config | — | `pURL` (backend), `pLlave` (vacía), `pCatalogo`, **`pMes` (C7)** y las seis versiones fijas (`tVersiones`) |
| P&L Mes | fórmulas sobre `tGL` | SOLO el mes de C7: Actual 2024, Actual 2025, Pre-Cierre del mes anterior, Pre-Cierre del mes, Actual 2026, Forecast y Budget; varianza vs Budget y vs Forecast ($ y %) desde una base elegible (E3, por defecto Actual 2026) |
| P&L YTD | fórmulas sobre `tGL` | acumulado enero → mes: Actual 2024/2025/2026, «2026 preliminar» (Actual a mes anterior + Pre-Cierre del mes), Forecast, Budget y las mismas varianzas |
| Controles | fórmulas | lo que tiene que dar 0, por versión, mes y acumulado |
| P&L USALI | fórmulas sobre `tGL` | doce meses de una versión (B3) |
| GL | `/consolidado/gl/` | todo el detalle del mayor (universo del mapeo) |
| Checkbook Ingresos | la consulta GL | depto × cuenta de ingreso, en positivo |
| Checkbook Costos / OPEX | `/consolidado/costos/`, `/opex/` | depto × cuenta (× detalle) |
| Checkbook Planilla | `/consolidado/planilla/` | posición × concepto 6000–6030 |
| Posiciones | `/consolidado/posiciones/` | FTE y costo por mes, con nombre y salario |
| Estadisticas Rooms | `/consolidado/estadisticas/` | disponibles, ocupadas, ocupación, ADR, RevPAR |
| P&L Motor | `/consolidado/propia/cuentas/` | las líneas que calcula FinPlan, para el control motor − GL |

Cada tabla trae los doce meses y, al final, **«Mes» y «Acumulado»** (tGL además «Mes anterior») del mes de C7 (`mes_columnas.ps1`): columnas
calculadas de la tabla, así que cambiar el mes no vuelve a bajar nada y sobreviven a «Actualizar todo».

## Versiones

`Actual 2024/2025/2026` con versión vacía (el ACTUAL real, nunca el espejo), `Pre-Cierre 2026` = `ACTUAL` versión
`Pre-Cierre` (`precierre_api.VERSION_ESPEJO`; trae solo los meses que se están pre-cerrando), `Budget 2026` = `Final`,
`Forecast 2026` vacía = el ★ Current. El Pre-Cierre se pide por su nombre a `_escoger_escenario`; sin versión el
comportamiento no cambió (`tests/test_cierre_mensual.py`).

## Armarlo

```
python -I build_cierre.py base.xlsx 10
add_queries.ps1  -In base.xlsx -Out libro.xlsx [-TestUrl http://127.0.0.1:PUERTO -TestKey X]
add_pestanas.ps1 -Libro libro.xlsx -Refrescar   [-TestUrl ... -TestKey ...]
python -I pl_vistas_spec.py libro.xlsx . ; pl_vista_build.ps1 -Libro libro.xlsx -Specs "pl_vista_mes.json;pl_vista_ytd.json"
controles.ps1 -Libro libro.xlsx -Verificar
python -I pl_spec.py libro.xlsx pl_spec.json "Corcovado Wilderness Lodge" ; pl_build.ps1 -In libro.xlsx -Out libro2.xlsx -SpecPath pl_spec.json
finalizar.ps1 -Libro libro2.xlsx [-Refrescar -TestUrl ... -TestKey ...]
```

⚠️ Los `.ps1` van en UTF-8 **con BOM**: PowerShell 5.1 lee sin BOM como ANSI y rompe las fórmulas con «−».
⚠️ En PowerShell la coma pesa más que el `+`: por eso las fórmulas de `controles.ps1` son plantillas literales.

## Lo que mostraron los controles (2026-11-11, contra la base de CWL en solo lectura)

* Actual 2024/2025/2026 y Budget 2026: todo en 0, los doce meses.
* Pre-Cierre: `Checkbook OPEX − OPEX del GL` = el reparto de Cafetería/Lavandería con signo contrario (ago–oct), y
  **$529.21 SIN MAPEO** en septiembre: `0250-8050 OTHER OWNERS' EXPENSES` llega al mayor sin renglón del P&L.
* Forecast 2026 (October): el GL de los meses cerrados sale del archivo importado y el motor del Actual (motor − GL
  ≠ 0 en jun–sep), y de septiembre a diciembre los checkbooks de planilla, OPEX y costos no son el GL importado.

## Revisión del owner sobre la v1 (2026-11-11)

«Que si compara YTD pero en un tab aparte, y el análisis propiamente del mes sea solo del mes ... side to side mismo
mes 2024-2025-2026, precierre mes anterior, 2026 precierre mes de análisis y Forecast y Budget y varianza versus Budget
y versus Forecast». Preguntado: «precierre mes anterior» = el Pre-Cierre del mes anterior; la varianza sale del Actual
2026 del mes. Un mes todavía en pre-cierre no tiene Actual (la varianza da contra 0): por eso la base es la celda E3,
que se cambia a «Pre-Cierre 2026» sin tocar fórmulas.
