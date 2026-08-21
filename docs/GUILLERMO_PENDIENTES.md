# Guillermo — pendientes para revisar

> Acumulado del **19 y 20 de agosto de 2026**. Lo que está acá **no se decidió
> solo**: son las cosas que necesitan tu criterio, o que se dejaron a propósito
> sin hacer con el motivo escrito.
>
> **Estado al cierre del 20-ago:** las cuatro fases construidas · D-1 y D-8
> resueltos · **3.323 pruebas** · migraciones 133 a 135 en producción.
>
> ⚠️ **Guillermo todavía no corre solo.** Recorre cuando apretás «Recorrer
> ahora»; falta el cron. Por eso está en gris, no por un defecto.

## Lo primero, si sólo hacés una cosa

**Subí el resumen de junio.** El detalle del mayor ya está cargado y su otra
mitad no — por eso ACTUAL 2026 descuadra **$199.667,97**. Es una subida, no un
arreglo de código.

---

## 🔴 Lo que bloquea, en orden

### ✅ D-1 · RESUELTO el 2026-08-20
Lo definiste: XML de Operations y Marketing todos los días; actuales del GL y
Balance Sheet una vez al mes. Sembrado en `app/seed_guillermo.py:MANIFIESTO`.

Guillermo ya contesta qué falta, y cada fila dice **cómo lo midió**.

### ✅ D-8 · REFORMULADO el 2026-08-20
Lo pediste más ancho que el spec: *«todos los auxiliares deben amarrar con el
GL, en todos los tabs, y las estadísticas. Cada despliegue siempre debe
cuadrar.»* Construido sobre `veredicto_del_detalle`, que ya existía.

🔴 **Sigue abierto** lo que el spec original preguntaba: qué pares de REPORTES
DE OPERA cuadran entre sí, y con qué tolerancia. Eso es el nivel 3 y espera a
que haya reportes de Opera entrando (D-2).

### D-9 · Contra qué se mide la tasa de acierto del modo sombra *(nueva)*
El criterio para pasar de sombra a asistido es «≥2 semanas con acierto ≥95%».
Pero en sombra no se escribe nada: **para saber si acertó, alguien tiene que
haber importado lo mismo a mano y comparar.** Sin comparador, esa métrica no
existe y el paso lo tenés que decidir vos, no un número.

### D-2 · ¿El Manager Report sale en CSV/XLSX en vez de PDF?
Parsear PDF es mucho más frágil. Si el cuadre depende de sacar un total de un
PDF, esa es la pieza que más se va a romper.

### D-4 · ¿OHIP está habilitado en la licencia?
`OhipSource` está escrito pero **revienta a propósito** con el motivo. No
devuelve vacío: «no llegó nada» y «no estoy conectado» no pueden verse igual.

### D-5 · Quién recibe notificaciones y quién puede aprobar
El rol `guillermo_approver` existe y funciona. Falta decir **a quién** se le da.

### D-7 · Cuántos archivos por día, por propiedad
Dimensionamiento.

---

## 🟡 Decisiones tuyas que no bloquean, pero conviene tomar

### El chip de Guillermo en la barra — **no lo puse, y está medido**
El §10.1 pide un status permanente en el header. Lo medí sobre la barra real:
un chip `● Guillermo 4 sombra` ocupa **161px**, y eso empuja los tres escalones
de escalado (**1860 / 1990 / 2115**) por encima de casi cualquier monitor — el
mismo defecto del «Master Data» convertido en «M» que reportaste el 19-ago.

Tu spec ofrece la alternativa en §10.3: **badge en el menú**. Hoy hay una
entrada «Guillermo» en el menú de Admin, sin badge.

**Opciones:** (a) badge en el menú, sin costo de ancho · (b) chip corto, sólo
el punto de color y el número (~40px) · (c) chip completo y subir los tres
escalones 161px.

### ⚠️ `PATCH /scenarios/{id}/status/` no exige admin
**Cualquier colaborador puede enllavar y desenllavar un escenario hoy.** Y el
candado del escenario es la salvaguarda dura que Guillermo respeta para no
tocar lo cerrado — así que esto la debilita.

**No lo cambié a propósito:** es un cambio de permisos y podría dejar a alguien
de tu equipo trabado a la mañana sin nadie que lo destrabe. La corrección es
una línea, en `app/api/scenarios_api.py:492`:

```python
usuario = Depends(get_current_admin),   # hoy no tiene ninguna verificación de rol
```

### El mes cerrado: quedó como aviso, no como bloqueo
Tal como aprobaste. Vale repetir el motivo, porque es contra-intuitivo: el
corte de meses cerrados **avanza solo como consecuencia del propio import**
(subir agosto cierra agosto), así que un bloqueo duro haría fallar **siempre**
el segundo import del mismo mes — incluido el reporte que llega tarde y el
duplicado con política `replace`, dos casos que tu spec resuelve.

---

## ✅ Lo que quedó hecho esta noche

| Fase | | |
|---|---|---|
| **0** | Identidad de archivo | mig 133 · sha256 · **23 de 23 puertas** |
| **1** | Núcleo puro, estados, config, latido, niveles 1 y 2 | mig 134 |
| **2** | API, rol `guillermo_approver`, cola persistida | |
| **3** | El gato, la pantalla `/admin/guillermo` | |
| **4** | Contrato de fuentes, `FolderSource`, la ronda | |

### Y lo del 20 de agosto

| | |
|---|---|
| **Qué falta subir** | D-1 sembrado · cada fila dice cómo se midió |
| **Los auxiliares contra el GL** | D-8 · tres estados, no dos |
| **Ronda de control** | botón «Recorrer ahora» · acumula sin duplicar y cierra sola lo resuelto |
| **Tres niveles** | bajo · medio · alto |
| **Botón de recálculo** | a pedido, nunca en cada guardado |
| **Conexión con Claude** | visible, con el payload exacto que saldría |

**3.323 pruebas.** Spec corregido en `docs/GUILLERMO.md` v0.4.

### Cinco controles que se escribieron para no poder volverse decorativos

1. **Sin manifiesto no se dice «todo bien»** — se dice que no se puede opinar.
2. **Una fecha interna que no se pudo leer no pasa como buena.** «No sé» y
   «coincide» no son lo mismo.
3. **Nunca haber latido cuenta como vencido.** Si «no hay registro» diera
   verde, un worker que jamás arrancó se vería sano.
4. **El latido vencido gana sobre los pendientes.** Un Guillermo trabado con
   cero pendientes se vería verde si los pendientes mandaran — y ese cero es la
   *consecuencia* de estar trabado.
5. **La ronda late aunque falle.** El latido dice «corrió», no «salió bien»; si
   sólo latiera al terminar bien, un fallo repetido se vería igual que un
   worker muerto.

### Qué vas a ver al entrar

**Guillermo en gris, y el gato NO aparece.** Es correcto: todavía no arrancó,
porque arrancarlo depende de D-1. La pantalla `/admin/guillermo` lo dice con el
motivo.

⚠️ Esto salió de tu pregunta «¿y se va a ver?». **Se iba a ver mal:** como
nunca corrió una ronda, el dead-man switch lo daba por vencido y el gato salía
**en rojo, sentado, en todas las pantallas, y no se iba**. Ni rojo ni verde
servían — rojo desde el día cero es una alarma que se aprende a ignorar, y
verde diría que un worker que jamás corrió está sano. Hizo falta un tercer
estado. **En cuanto definas D-1, no haber corrido sí se pone rojo.**

### Y una que casi se rompe en silencio

Leer el `UploadFile` en la dependencia del registro **mueve el puntero**. Sin
devolverlo al principio con `seek(0)`, el `read()` del endpoint devuelve vacío
y **el import entra sin datos, sin fallar** — el P&L queda en cero y cuadra
consigo mismo. Tiene su propia prueba: `test_EL_SEEK_CERO_ESTA_PUESTO`.

---

## 🔵 Lo que sigue, cuando decidas D-1 y D-8

- Parsers CSV y PDF (hoy no hay ninguno de los dos en FinPlan).
- El cron de Railway que dispare la ronda.
- Nivel 3 de validación (cuadre cruzado).
- Propuesta de IA para conceptos nuevos, con la minimización de PII del §9.2.
- Correos: resumen diario, inmediato por excepción, rojo sin latido.
- Comandos operativos (§11) y resumen semanal.
- Huellas en Revenue y P&L (§10.3).
