# Conectar y consolidar

> Escrito para arrancar en frío. Dice qué está listo, qué falta, y quién puede
> hacer cada cosa. **2026-08-14.**

Hay dos cosas distintas acá y conviene no mezclarlas:

| | qué es | estado |
|---|---|---|
| **Consolidar** | Sacar el P&L de cada propiedad por API para sumarlas afuera | **Funciona hoy** |
| **Integrar** | Traer dato desde QuickBooks y Opera Cloud | **La prevista está; falta el cableado** |

---

## 1 · Consolidar — funciona hoy

Cada propiedad expone su P&L. **Nadie guarda las llaves de nadie:** cada hotel
responde solo por lo suyo, y quien consolida es el de afuera — Excel, Power BI,
un tablero propio, o la app de otra propiedad.

```
GET /api/consolidado/escenarios/           qué años y versiones hay
GET /api/consolidado/propia/?year=2027&tipo=BUDGET
```

`tipo` es `BUDGET`, `FORECAST` o `ACTUAL`. Se puede pedir una `version` exacta;
sin ella viene la más reciente.

Devuelve, en **USD**: identidad del hotel, el escenario que usó (con su
`actuals_through`, o sea hasta qué mes hay dato real), los KPIs, y **cada línea
del P&L con sus 12 meses y el anual**.

**No sale por acá:** detalle de cuentas, planilla, nombres de personas, ni una
sola fila del GL. Totales por línea y nada más.

### La llave de solo lectura

El token de sesión dura 7 días — sirve para la app, no para un tablero que jala
todos los lunes. Para eso está la llave:

```bash
CONSOLIDADO_API_KEY=<una cadena larga y aleatoria, distinta por propiedad>
```

Se manda en la cabecera `x-api-key`. Tres candados:

* **abre un solo endpoint** — no escribe, no lista usuarios, no ve detalle;
* **es por propiedad** — la de Corcovado no sirve en Amarena;
* **nace apagada** — sin la variable no existe ninguna llave válida.

Se revoca cambiando la variable. Generar una:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

⚠️ **La llave es una credencial.** Si la ponés en un Excel o un Power BI que se
comparte, quien tenga ese archivo puede leer el P&L de esa propiedad. Tratala
como la contraseña que es.

### Ejemplo

```bash
curl -H "x-api-key: $CONSOLIDADO_API_KEY" \
  "https://finplan-cwl-production.up.railway.app/api/consolidado/propia/?year=2027&tipo=BUDGET"
```

### El contrato

La respuesta trae `contrato: 1`. Ese número sube solo si cambia la **forma** de
la respuesta, para que un consolidador viejo pueda darse cuenta en vez de leer
campos que ya no están. Las líneas se identifican por `line_code`, nunca por
posición: dos propiedades pueden tener líneas distintas —una sin Spa, otra sin
Club— y la suma tiene que cuadrar igual.

---

## 2 · Integrar — la prevista

**Qué hay listo:** el lugar donde enchufar. Dónde van las credenciales, cómo se
prueba la conexión, qué se ve cuando falla.

**Qué falta:** las credenciales, que solo puede conseguir el dueño de la cuenta,
y el mapeo del dato, que se hace con el catálogo real a la vista.

```
GET  /api/integraciones/                  qué falta cargar
POST /api/integraciones/{clave}/probar/   hace una llamada real y cuenta
```

Los dos son de admin. **Los valores de las credenciales no salen nunca**, ni
truncados.

> **La regla de este módulo:** una conexión sin configurar se ve **apagada**, no
> verde. Nada dice «ok» sin haber hecho una llamada que haya contestado. Un
> tablero que dice «conectado» cuando no lo está es peor que no tener tablero.

### QuickBooks Online

Serviría para traer el mayor del mes cerrado sin subir el Excel. El importador
ya existe: esto le quita el paso manual, no cambia el cálculo.

| variable | qué es | dónde se saca |
|---|---|---|
| `QBO_CLIENT_ID` | Identifica la app ante Intuit | developer.intuit.com → tu app → Keys and credentials |
| `QBO_CLIENT_SECRET` | La contraseña de esa app | mismo lugar |
| `QBO_REFRESH_TOKEN` | Permiso de larga vida sobre la empresa | del OAuth que autoriza el dueño de la cuenta |
| `QBO_REALM_ID` | Cuál empresa. Una por propiedad | en la URL al entrar, o al terminar el OAuth |
| `QBO_ENTORNO` | `sandbox` o `produccion` | opcional; sin ella se asume sandbox |

**Pasos, en orden:**

1. El dueño de la cuenta crea la app en `developer.intuit.com` y saca client id
   y secret.
2. Corre el OAuth una vez, autorizando la empresa. Sale el refresh token.
3. Se cargan las cuatro variables en Railway, en el proyecto de esa propiedad.
4. `POST /api/integraciones/quickbooks/probar/` — tiene que decir el nombre de
   la empresa.
5. **Recién ahí** empieza el trabajo de verdad: decidir qué cuenta de QuickBooks
   es qué línea del P&L USALI. Ya existe la capa (`account_mapping`); es mapeo
   con el catálogo real, no se puede adivinar antes.

⚠️ El paso 1 y el 2 son del dueño de la cuenta. Son fronteras de seguridad y no
hay forma de saltárselas.

### Oracle Opera Cloud (OHIP)

Serviría para traer noches, pax y revenue por categoría, y el On The Books, sin
exportar el XML a mano.

| variable | qué es | dónde se saca |
|---|---|---|
| `OPERA_BASE_URL` | El host de OHIP de esta cadena | lo da Oracle. **No es igual para todos** |
| `OPERA_APP_KEY` | Identifica la integración (`x-app-key`) | portal de OHIP |
| `OPERA_CLIENT_ID` | Cliente OAuth | portal de OHIP |
| `OPERA_CLIENT_SECRET` | Su contraseña | portal de OHIP |
| `OPERA_USUARIO` | Usuario con permiso de **lectura** | lo crea el admin de Opera |
| `OPERA_PASSWORD` | Su contraseña | idem |
| `OPERA_HOTEL_ID` | Código de la propiedad en Opera | uno por hotel |

**Pasos, en orden:**

1. Dar de alta la integración en OHIP y pedir que habiliten los servicios para
   el `hotelId` de la propiedad. **Esto arranca con Oracle, no con código**, y lo
   hace el dueño de la cuenta.
2. Crear en Opera un usuario de **solo lectura**. No usar uno de admin.
3. Cargar las siete variables en Railway.
4. `POST /api/integraciones/opera_cloud/probar/`.
5. Emparejar las categorías de habitación de Opera con las de acá. Esta mitad ya
   está resuelta: cada categoría tiene un **código fijo** (BL01…SH08) que no
   cambia entre propiedades, así que es una tabla de equivalencias y se hace una
   sola vez.

---

## Lo que este documento NO promete

* Que QuickBooks u Opera **traigan dato**. Hoy no traen: está la puerta, no el
  camino. Lo que falta después de conectar —el mapeo de cuentas, el de
  categorías, y decidir qué pasa cuando el origen corrige un mes ya cerrado— es
  trabajo con el dato en la mano.
* Que la llave del consolidado sea segura **si se comparte**. Es una credencial.
* Que dos propiedades sumen bien **si usan catálogos distintos**. Las líneas se
  cruzan por `line_code`; si un hotel inventa códigos propios, el consolidado los
  mostrará aparte en vez de sumarlos mal — pero hay que mirarlo.

---

## 3 · La tuberia de origenes — construida, SIN DESPLEGAR

> Rama `infra-origenes`. **No esta en produccion**: se hizo para que el dia que
> haya credenciales sea conectar y no construir (owner, 2026-08-14).

Corcovado va a traer su contabilidad de un backoffice por API; Oxigen y Ojochal
usan QuickBooks; hoy todo entra por Excel. Son tres formas de decir lo mismo, asi
que hay una capa que las iguala:

```
QuickBooks  ─┐
Backoffice  ─┼→  FilaDeOrigen  →  traducir  →  previsualizar  →  aplicar  →  el motor
Archivo     ─┘                       (mapeo)
```

De `FilaDeOrigen` para abajo el camino es **uno solo** y ya esta probado. Cada
origen nuevo aporta un adaptador chico cuyo unico trabajo es devolver esas filas.

### El puente es DATO, no codigo

Tabla `mapeo_origen` (migracion 105), por propiedad y por origen:

    (propiedad, origen, cuenta de alla, depto de alla)  →  cuenta de aca + depto + outlet

**Ese es el punto entero.** Si el puente fuera codigo, abrir Oxigen seria un
desarrollo. Siendo dato, es cargar su mapeo desde la pantalla. El criterio se
cumple: **conectar un hotel = variables + mapeo, cero codigo.**

Una regla CON departamento le gana a una sin el, para poder tener «la 5010 va a
Food Cost» y aparte «la 5010 del BAR va a Beverage» sin duplicar el catalogo.

### Endpoints

```
GET    /api/origenes/                        que hay y si esta listo para importar
GET    /api/origenes/{origen}/mapeo/
PUT    /api/origenes/{origen}/mapeo/         reemplaza el mapeo entero (bajar/corregir/subir)
DELETE /api/origenes/{origen}/mapeo/{id}/

POST   /api/origenes/{origen}/previsualizar/ que pasaria. NO escribe
POST   /api/origenes/{origen}/aplicar/       escribe
```

Hoy las filas se mandan en el cuerpo, asi que **la tuberia se puede usar y probar
entera desde ya**. Cuando exista el adaptador, lo unico que cambia es de donde
salen esas filas.

### Las tres reglas del aterrizaje

1. **Se reemplaza SOLO el periodo que se trajo.** Pedir enero y febrero no toca
   marzo. Traer «todo el año» y pisar entero es como se borra sin querer un mes
   que estaba bien.
2. **Dentro de ese periodo, lo que el origen ya no reporta se pone en cero.** Si
   contabilidad borro un asiento, dejar el monto viejo seria peor que no
   importar: quedaria un numero sin respaldo en ningun lado.
3. **No se escribe si hay cuentas sin mapeo**, salvo que se pida explicito. Un
   import que se traga tres cuentas deja un P&L que cuadra consigo mismo y no
   cuadra con la realidad.

### Lo que falta para que esto traiga dato

| | quien | estado |
|---|---|---|
| Adaptador de QuickBooks (consulta, rango, paginacion) | desarrollo | falta; **no se puede verificar sin una sandbox de Intuit** |
| Adaptador del backoffice de Corcovado | desarrollo | falta; primero hay que saber **que sistema es y si tiene API documentada** |
| Pantalla para editar el mapeo | desarrollo | falta |
| Bajar/subir el mapeo en Excel | desarrollo | falta |
| Cargar el mapeo de cada propiedad | owner + contabilidad | falta |

**La sandbox de Intuit es gratis y no toca libros reales.** Es lo unico que hace
falta para poder verificar el adaptador de QuickBooks de punta a punta antes de
apuntarlo a una empresa de verdad.
