---
description: Arma el informe operativo de variaciones de un mes, con el analisis escrito
argument-hint: <mes> [ano]   — por ejemplo "octubre" o "octubre 2026" o "10 2026"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, SendUserFile
---

Arma el **informe operativo de variaciones** del mes que pidio el owner: `$ARGUMENTS`

Si no dijo mes, preguntale cual antes de hacer nada. Si dijo mes y no ano, asumi
el ano en curso y decilo.

## La especificacion manda

Lee `informes/INFORME_OPERATIVO.md` completo antes de empezar. Ahi estan las doce
secciones, las cinco reglas que hacen que los numeros aten, las cuatro
advertencias de lectura, como se escribe el analisis y la lista de verificacion.
**No improvises la estructura**: el owner pidio explicitamente que el informe
salga igual todos los meses.

El modelo de referencia es `backend/app/seed_data/CWL/informes/2026_09.json`, que es el
analisis de setiembre 2026. Leelo para ver el tono, el nivel de detalle y la
forma de las preguntas al gerente.

## El orden de trabajo

1. **Sacar los cuadros primero.**

   ```
   python informes/armar.py --anio <ano> --mes <mes>
   ```

   Un solo comando: si falta el corte lo extrae de produccion. Usa el python del
   venv: `backend/.venv/Scripts/python.exe`.

   Cuando el analisis quede guardado, el BOTON de la aplicacion
   —Pre-Closing, «Informe operativo»— ya entrega ese mes completo para
   cualquiera del equipo. Decirselo al owner al entregar.

   Si se queja de que falta el Pre-Cierre o el mayor, decile al owner que los
   suba y pare ahi — sin el mayor el informe no puede nombrar proveedores ni
   asientos, y sin eso no sirve para ir a preguntarle a un gerente.

2. **Verificar el cuadre.** `armar.py` lo imprime. Los tres escenarios tienen
   que coincidir con la pantalla *Month-End Close — P&L*, y
   `GOP reporte − GOP motor` tiene que decir **coincide**. Si dice
   `NO COINCIDE`, buscar la causa antes de seguir y contarsela al owner.

3. **Mirar los numeros de verdad.** No escribas el analisis desde los totales.
   Entra al detalle: las cuentas con mas variacion, los proveedores del mayor,
   los conceptos de planilla, los margenes por departamento. Usa consultas de
   solo lectura sobre el corte en `backend/app/informes/datos/<ano>_<mes>.json`, o
   sobre produccion si hace falta mas —con `scripts/_prodenv.py`, solo lectura—.

4. **Escribir la narrativa** en `backend/app/seed_data/<HOTEL>/informes/<ano>_<mes>.json`.
   Copia la estructura del de setiembre si no existe. Es JSON: las tuplas van como listas. Las reglas de escritura
   estan en §5 del `.md`; las tres que mas importan:

   - Los hallazgos van **ordenados por impacto en dolares sobre el resultado**,
     no por tamano de la cuenta.
   - Cada favorabilidad de opex se clasifica en **ahorro / diferimiento /
     reclasificacion**. La pista es el Forecast: si sube esa cuenta el mes
     siguiente, era diferimiento.
   - Una pregunta al gerente sirve si nombra la cifra, nombra la evidencia del
     mayor **y no se puede contestar desde el sistema**. Si la respuesta esta en
     la base, no es una pregunta: es un dato que faltaste buscar.

5. **Rearmar** con el mismo comando —ya no vuelve a tocar produccion— y
   confirmar que no quedan claves pendientes ni marcas `[PENDIENTE]`.

6. **Repasar la lista de verificacion** de §8 del `.md` y **mandarle el archivo**
   con `SendUserFile`.

## Si el mes ya se hizo antes

Si el owner pide un mes que ya tiene narrativa escrita, por defecto sale
identico: no se vuelve a leer produccion ni se reescribe el analisis.

Si dice que **volvio a subir** el P&L del Pre-Cierre o el mayor, o que corrigio
algo, hay que agregar `--extraer`. `extraer.py` compara contra la extraccion
anterior e imprime que se movio: totales por clase, archivo del mayor, cuentas.

⚠️ **Esa lista es la lista de parrafos a corregir.** Los cuadros se actualizan
solos y las cifras escritas en la narrativa NO. Repasar cada mencion de lo que
cambio y reescribirla, y decirle al owner que cambio contra la version anterior.

## Lo que hay que volver a mirar cada mes

La §9 del `.md` lista el estado del sistema en setiembre 2026: el credito 4999
que el reporte descarta, las cinco cuentas donde el presupuesto y el real no
aparean, los conceptos de planilla sin presupuesto. **Verifica si siguen vivos**
y si alguno se corrigio, decilo en el informe en vez de repetirlo.

## En el resumen al owner

Deja claro, en pocas lineas: el GOP contra presupuesto, los dos o tres hallazgos
mas grandes con su monto, y si el cuadre dio bien. Si algo quedo sin poder
analizar por falta de dato, decilo — no lo tapes con texto.
