# -*- coding: utf-8 -*-
"""Los mensajes de error de la API, en los dos idiomas.

**Por qué existe.** Los 359 `raise HTTPException` del backend estaban escritos a
mano, y entre ellos ya venían mezclados: la MISMA validación aparecía como
`"month debe estar entre 1 y 12"`, `"month must be 1–12"` y `"month 1..12"`.
Tres formas, dos idiomas, un solo significado. El frontend ya habla los dos
idiomas desde el catálogo; el backend le mandaba español encima.

**Cómo funciona, y por qué así.** El idioma se resuelve **al borde**, en el
manejador de excepciones, no en cada endpoint:

    raise ErrorApi(404, "escenario.no_encontrado")

El sitio que falla no recibe un `locale` ni una dependencia nueva. Pasarle el
idioma a 359 lugares habría significado tocar la firma de casi todos los
endpoints —y de los que llaman a esos endpoints desde dentro— para transportar
un dato que solo se usa al final, cuando se serializa la respuesta. Acá el
`raise` dice QUÉ pasó; el idioma lo pone quien contesta.

⚠️ **El motor sigue sin enterarse.** Nada de `app/engine/` importa este módulo,
igual que no importa `app/i18n.py`. `tests/test_i18n_locale.py` falla si alguien
lo intenta. El cálculo no sabe en qué idioma se va a mostrar.

⚠️ **`ErrorApi` HEREDA de `HTTPException`.** Cualquier `except HTTPException` que
ya existiera lo sigue atrapando, y si por lo que sea la respuesta no pasa por el
manejador, el `detail` ya trae el texto en español — exactamente lo que se veía
antes. Un cambio de idioma no puede convertirse en una pantalla sin mensaje.
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.i18n import DEFAULT_LOCALE, normalize_locale

#: `clave -> {es, en}`. Los `{parametros}` se rellenan con `str.format`.
#:
#: Las claves se nombran `tema.caso`. Un mensaje que se repite va UNA vez: el
#: caso extremo es `escenario.no_encontrado`, que cubría 54 sitios escritos a
#: mano — y con tres redacciones distintas entre ellos.
MENSAJES: dict[str, dict[str, str]] = {
    # ── Lo que no se encuentra ────────────────────────────────────────────────
    "escenario.no_encontrado": {
        "es": "Escenario no encontrado",
        "en": "Scenario not found"},
    "propiedad.no_encontrada": {
        "es": "Propiedad no encontrada",
        "en": "Property not found"},
    "entrada.no_encontrada": {
        "es": "Entrada no encontrada",
        "en": "Entry not found"},
    "version.no_encontrada": {
        "es": "Versión no encontrada",
        "en": "Version not found"},
    "usuario.no_encontrado": {
        "es": "Usuario no encontrado",
        "en": "User not found"},
    "renglon.no_encontrado": {
        "es": "Renglón no encontrado",
        "en": "Line not found"},
    "anotacion.no_encontrada": {
        "es": "Anotación no encontrada",
        "en": "Note not found"},
    "cuenta.no_encontrada": {
        "es": "Cuenta no encontrada: {cuenta}",
        "en": "Account not found: {cuenta}"},
    "mapeo.no_encontrado": {
        "es": "Mapeo no encontrado",
        "en": "Mapping not found"},

    # ── Validaciones ──────────────────────────────────────────────────────────
    #
    # ⚠️ Esta sola clave reemplaza TRES redacciones que convivían en el código
    # («month debe estar entre 1 y 12», «month must be 1–12», «month 1..12»).
    "mes.fuera_de_rango": {
        "es": "El mes debe estar entre 1 y 12",
        "en": "Month must be between 1 and 12"},
    "escenarios.requerido": {
        "es": "Hace falta indicar el escenario",
        "en": "A scenario is required"},
    "clave.muy_corta": {
        "es": "La contraseña debe tener al menos 8 caracteres",
        "en": "The password must be at least 8 characters long"},

    # ── Permisos ──────────────────────────────────────────────────────────────
    "auth.no_autenticado": {
        "es": "No autenticado",
        "en": "Not authenticated"},
    "auth.solo_autor_o_admin": {
        "es": "Solo el autor o un administrador",
        "en": "Only the author or an administrator"},

    # ── Estado del escenario ──────────────────────────────────────────────────
    "escenario.enllavado": {
        "es": ("El escenario «{escenario}» está enllavado (status=locked). "
               "Creá una versión nueva para editar."),
        "en": ("Scenario “{escenario}” is locked (status=locked). "
               "Create a new version in order to edit.")},

    # ── Tipos de cambio ───────────────────────────────────────────────────────
    "tc.sin_tipos_de_cambio": {
        "es": "Este escenario no tiene tipos de cambio — cargalos primero",
        "en": "This scenario has no exchange rates — add them first"},

    "tema.invalido": {
        "es": "Ese tema no existe. Los que hay: {temas}.",
        "en": "That theme does not exist. Available: {temas}."},


    # ── Subir el checkbook lleno (2026-08-19) ─────────────────────────────
    "checkbook.no_se_pudo_leer": {
        "es": "No se pudo leer el archivo. ¿Es el checkbook que bajaste de acá, en .xlsx? Detalle: {detalle}",
        "en": "The file could not be read. Is it the checkbook you downloaded here, in .xlsx? Detail: {detalle}"},
    "checkbook.otro_departamento": {
        "es": "Este archivo es del departamento {archivo} y lo estás subiendo dentro de {elegido}. No se cargó nada: cargarlo reescribiría el departamento equivocado con montos que no son suyos, y el total general podría quedar parecido igual.",
        "en": "This file belongs to department {archivo} and you are uploading it under {elegido}. Nothing was loaded: it would overwrite the wrong department with amounts that are not its own, and the overall total could still look about right."},
    "checkbook.otro_anio": {
        "es": "El archivo es del año {archivo} y el escenario es de {escenario}. Un presupuesto de otro año no es este presupuesto.",
        "en": "The file is for year {archivo} and the scenario is for {escenario}. Another year's budget is not this budget."},
    "checkbook.no_cuadra": {
        "es": "El archivo no cuadra consigo mismo: sumando las líneas da {calculado} y el GRAN TOTAL de la hoja dice {enhoja}. Eso pasa cuando se pega encima de una fórmula. No se cargó nada — cargar la mitad buena sería peor.",
        "en": "The file does not balance against itself: adding up the lines gives {calculado} while the sheet's GRAND TOTAL says {enhoja}. That happens when something is pasted over a formula. Nothing was loaded — loading the good half would be worse."},
    "checkbook.cuentas_que_no_estan": {
        "es": "El archivo trae {cuantas} cuenta(s) que este departamento ya no tiene en el escenario: {cuentas}. Es un archivo viejo, o el departamento cambió desde que lo bajaste. Volvé a bajarlo y pasá los montos.",
        "en": "The file carries {cuantas} account(s) this department no longer has in the scenario: {cuentas}. Either the file is old, or the department changed since you downloaded it. Download it again and move the amounts across."},
    "checkbook.sin_tipo_de_cambio": {
        "es": "Hay {cuantas} línea(s) en colones con monto en un mes que no tiene tipo de cambio: {lineas}. El archivo muestra dólares, pero en una línea en colones el dato bueno son los colones — sin el TC del mes no se puede convertir de vuelta, e inventarlo sería inventar el dato. Cargá los tipos de cambio y volvé a subir.",
        "en": "There are {cuantas} colón-denominated line(s) with an amount in a month that has no exchange rate: {lineas}. The file shows dollars, but on a colón line the real figure is the colones — without that month's rate it cannot be converted back, and making one up would be making up the data. Load the exchange rates and upload again."},
    # ── Agregadas al pasar los 359 `raise` al catalogo (2026-08-19) ──────────
    "balance_sheet.no_cargado": {
        "es": "No hay Balance Sheet cargado; subí primero el Excel.",
        "en": "No Balance Sheet has been loaded; upload the Excel file first."},
    "balance_sheet.no_se_pudo_leer": {
        "es": "No se pudo leer el Balance Sheet: {detalle}",
        "en": "The Balance Sheet could not be read: {detalle}"},
    "balance_sheet.sin_datos_en_el_archivo": {
        "es": "El archivo no trae datos del Balance Sheet Summary.",
        "en": "The file carries no Balance Sheet Summary data."},
    "channel_mix.market_codes_sin_canal": {
        "es": "Ningún market code del archivo tiene canal asignado. Asignalos en Master Data → Market Codes antes de subir.",
        "en": "No market code in the file has a channel assigned. Assign them in Master Data → Market Codes before uploading."},
    "channel_mix.mes_corregido_a_mano": {
        "es": "{mes} ya se corrigió a mano después de importarlo. Volver a subir el XML lo deja como viene de Opera y se pierde la corrección. Si es lo que querés, repetí la subida confirmando que se sobrescriba.",
        "en": "{mes} was already corrected by hand after being imported. Uploading the XML again leaves it as it comes out of Opera and the correction is lost. If that is what you want, repeat the upload confirming that it be overwritten."},
    "channel_mix.xml_no_es_de_market_code": {
        "es": "Este XML no viene abierto por market code: ninguno de sus {n} códigos está en la tabla de Market Codes (trae {codigos}…). Parece el reporte abierto por PAÍS, que va en Country Mix.",
        "en": "This XML is not broken down by market code: none of its {n} codes is in the Market Codes table (it carries {codigos}…). It looks like the report broken down by COUNTRY, which belongs in Country Mix."},
    "componente.no_existe": {
        "es": "«{codigo}» no es un componente que el motor sepa calcular. Los códigos son fijos: {codigos}.",
        "en": "“{codigo}” is not a component the engine knows how to calculate. The codes are fixed: {codigos}."},
    "country_mix.meses_corregidos_a_mano": {
        "es": "Los meses {meses} ya se corrigieron a mano después de importarlos. Volver a subir el XML los deja como vienen de Opera y se pierde la corrección. Si es lo que querés, repetí la subida confirmando que se sobrescriban.",
        "en": "Months {meses} were already corrected by hand after being imported. Uploading the XML again leaves them as they come out of Opera and the correction is lost. If that is what you want, repeat the upload confirming that they be overwritten."},
    "excel.no_encontrado": {
        "es": "Excel no encontrado. Sube el archivo como multipart/form-data.",
        "en": "Excel file not found. Upload the file as multipart/form-data."},
    "otb.ocupacion_imposible": {
        "es": "El XML da una ocupación imposible — no se guardó nada. Suele ser el mismo día contado dos veces (History y Forecast solapados): {meses}",
        "en": "The XML gives an impossible occupancy — nothing was saved. It is usually the same day counted twice (History and Forecast overlapping): {meses}"},
    "pax_por_noche.negativo": {
        "es": "pax_per_night no puede ser negativo",
        "en": "pax_per_night cannot be negative"},
    "revenue.excel_faltan_tipos": {
        "es": "Este archivo trae las tarifas de los tipos {tipos} (por orden) y a la propiedad le faltan {faltan}. Cargalos en Master Data antes de importar.",
        "en": "This file carries the rates for room types {tipos} (by position) and the property is missing {faltan}. Add them in Master Data before importing."},
    "revenue.fuente_invalida": {
        "es": "revenue_source debe ser 'drivers' o 'checkbook'",
        "en": "revenue_source must be 'drivers' or 'checkbook'"},
    "revenue.lineas_invalidas": {
        "es": "Líneas inválidas: {lineas}",
        "en": "Invalid lines: {lineas}"},
    "room_stats.no_se_pudo_leer": {
        "es": "No se pudo leer Room Stats: {detalle}",
        "en": "Room Stats could not be read: {detalle}"},
    "room_stats.sin_bloques_mensuales": {
        "es": "El archivo no trae bloques mensuales de Room Stats.",
        "en": "The file carries no monthly Room Stats blocks."},
    "stats.sin_datos_validos": {
        "es": "No se encontraron datos válidos.",
        "en": "No valid data was found."},
    "tarifas.sin_mix_de_canales": {
        "es": "Este escenario no tiene mix de canales en {n} mes(es) ({meses}). La tarifa neta quedaría igual a la rack —sin comisión— y el ingreso saldría sobreestimado. Cargá el mix en Master Data · Canales y aplicalo a este escenario primero.",
        "en": "This scenario has no channel mix in {n} month(s) ({meses}). The net rate would end up equal to the rack rate —with no commission— and revenue would come out overstated. Load the mix in Master Data · Channels and apply it to this scenario first."},
    "tipo_habitacion.codigo_no_se_cambia": {
        "es": "El código «{codigo}» no se cambia: es lo que liga esta categoría con los escenarios, los reportes y las otras propiedades. Si lo que querés es que se lea distinto, editá el nombre.",
        "en": "Code “{codigo}” is not changed: it is what ties this room category to the scenarios, to the reports and to the other properties. If what you want is for it to read differently, edit the name instead."},
    "tipo_habitacion.codigo_repetido": {
        "es": "El código '{codigo}' ya existe en este hotel.",
        "en": "Code '{codigo}' already exists in this hotel."},
    "tipo_habitacion.no_encontrado": {
        "es": "Tipo de habitación no encontrado",
        "en": "Room type not found"},
    "tipo_habitacion.posicion_no_se_mueve": {
        "es": "«{nombre}» nació en la posición {posicion} y ahí se queda: el importador del Excel mapea sus filas por posición, y reordenar movería las tarifas de categoría.",
        "en": "“{nombre}” was born at position {posicion} and there it stays: the Excel importer maps its rows by position, and reordering would move the rates to the wrong category."},
    "xml.anio_no_esta": {
        "es": "El XML no trae datos de {anio}. Trae: {anios}.",
        "en": "The XML carries no data for {anio}. It carries: {anios}."},
    "xml.elegir_mes": {
        "es": "El XML trae {n} meses de {anio} ({meses}) y se sube un mes por vez. Elegí cuál cargar.",
        "en": "The XML carries {n} months of {anio} ({meses}) and one month is uploaded at a time. Choose which one to load."},
    "xml.mes_no_esta": {
        "es": "El XML no trae {mes} de {anio}. Trae: {meses}.",
        "en": "The XML does not carry {mes} of {anio}. It carries: {meses}."},
    "xml.no_se_pudo_leer": {
        "es": "No se pudo leer el XML: {detalle}",
        "en": "The XML could not be read: {detalle}"},
    "xml.sin_dias": {
        "es": "El XML no trae días (G_CONSIDERED_DATE).",
        "en": "The XML carries no days (G_CONSIDERED_DATE)."},
    "xml.sin_dias_con_datos": {
        "es": "El XML no trae ningún día con datos. ¿Es el reporte `res_statistics1` de Opera?",
        "en": "The XML carries no day with data on it. Is this Opera's `res_statistics1` report?"},
    "xml.sin_dias_con_pais": {
        "es": "El XML no trae ningún día con país. ¿Es el reporte `res_statistics1` de Opera?",
        "en": "The XML carries no day with a country on it. Is this Opera's `res_statistics1` report?"},
    "archivo.no_se_pudo_leer": {
        "es": "No se pudo leer el archivo: {detalle}",
        "en": "The file could not be read: {detalle}"},
    # ⚠️ El mensaje lleva el MOTIVO adentro —cuándo entró y quién lo subió—, no
    # un «duplicado» pelado: quien lo recibe tiene que poder decidir si es el
    # mismo archivo por error o el archivo corregido. Ver `docs/GUILLERMO.md`.
    "import.ya_subido": {
        "es": "{detalle}",
        "en": "{detalle}"},
    "auth.bootstrap_deshabilitado": {
        "es": "Ya hay usuarios; bootstrap deshabilitado",
        "en": "There are users already; bootstrap is disabled"},
    "auth.credenciales_invalidas": {
        "es": "Credenciales inválidas",
        "en": "Invalid credentials"},
    "auth.requiere_admin": {
        "es": "Requiere rol admin",
        "en": "Requires the admin role"},
    "auth.token_invalido": {
        "es": "Token inválido o expirado",
        "en": "Invalid or expired token"},
    "auth.usuario_no_valido": {
        "es": "Usuario no válido",
        "en": "Invalid user"},
    "bigpicture.base_sin_detalle": {
        "es": "El escenario base no tiene detalle cargado (subí el Forecast primero).",
        "en": "The base scenario has no detail loaded (upload the Forecast first)."},
    "copia.dataset_desconocido": {
        "es": "Dataset desconocido: '{dataset}'. Válidos: {validos}",
        "en": "Unknown dataset: '{dataset}'. Valid ones: {validos}"},
    "copia.origen_vacio": {
        "es": "'{origen}' no tiene datos para copiar (solo el andamiaje que se crea solo): la copia nacería vacía. Elegí otro origen, o creá el escenario en blanco.",
        "en": "'{origen}' has no data to copy (only the scaffolding that creates itself): the copy would be born empty. Pick another source, or create the scenario blank."},
    "escenario.budget_origen_no_encontrado": {
        "es": "Budget origen no encontrado",
        "en": "Source budget not found"},
    "escenario.destino_bloqueado": {
        "es": "El escenario destino está bloqueado",
        "en": "The target scenario is locked"},
    "escenario.destino_no_encontrado": {
        "es": "Escenario destino no encontrado",
        "en": "Target scenario not found"},
    "escenario.enllavado_big_picture": {
        "es": "'{version}' está enllavada. Abrila para aplicar el Big Picture.",
        "en": "'{version}' is locked. Unlock it in order to apply the Big Picture."},
    "escenario.origen_debe_ser_budget": {
        "es": "El origen debe ser un BUDGET",
        "en": "The source must be a BUDGET"},
    "escenario.origen_debe_ser_forecast": {
        "es": "El origen debe ser un FORECAST",
        "en": "The source must be a FORECAST"},
    "escenario.origen_no_encontrado": {
        "es": "Escenario origen no encontrado",
        "en": "Source scenario not found"},
    "escenario.solo_borra_draft": {
        "es": "Solo se pueden eliminar escenarios en draft. Status actual: '{status}'",
        "en": "Only scenarios in draft can be deleted. Current status: '{status}'"},
    "escenario.solo_forecast_current": {
        "es": "Solo un FORECAST puede ser 'Current'",
        "en": "Only a FORECAST can be the 'Current' one"},
    "escenario.source_mode_invalido": {
        "es": "source_mode debe ser 'imported' o 'checkbook'",
        "en": "source_mode must be either 'imported' or 'checkbook'"},
    "escenario.status_invalido": {
        "es": "status debe ser uno de {estados}",
        "en": "status must be one of {estados}"},
    "escenario.tipo_invalido": {
        "es": "type debe ser uno de {tipos}",
        "en": "type must be one of {tipos}"},
    "forecast.current_ya_existe": {
        "es": "Ya existe un Forecast Current para {anio} ({version}). Desmarcalo o usá ese.",
        "en": "A Current Forecast already exists for {anio} ({version}). Unmark it, or use that one."},
    "gl.fila_sin_cuenta": {
        "es": "El archivo tiene 1 fila con monto y SIN numero de cuenta, por un total de {total}. No se cargo nada.\n\n{muestra}\n\nEsa plata no tiene a donde ir: sin codigo de cuenta el importador no sabe a que linea del P&L corresponde. Ponele el numero de cuenta en el Excel y volve a subirlo.",
        "en": "The file has 1 row with an amount and NO account number, for a total of {total}. Nothing was loaded.\n\n{muestra}\n\nThat money has nowhere to go: without an account code the importer cannot tell which P&L line it belongs to. Write the account number in the Excel file and upload it again."},
    "gl.filas_sin_cuenta": {
        "es": "El archivo tiene {n} filas con monto y SIN numero de cuenta, por un total de {total}. No se cargo nada.\n\n{muestra}\n\nEsa plata no tiene a donde ir: sin codigo de cuenta el importador no sabe a que linea del P&L corresponde. Ponele el numero de cuenta en el Excel y volve a subirlo.",
        "en": "The file has {n} rows with an amount and NO account number, for a total of {total}. Nothing was loaded.\n\n{muestra}\n\nThat money has nowhere to go: without an account code the importer cannot tell which P&L line it belongs to. Write the account number in the Excel file and upload it again."},
    "gl.filas_sin_cuenta_y_mas": {
        "es": "El archivo tiene {n} filas con monto y SIN numero de cuenta, por un total de {total}. No se cargo nada.\n\n{muestra}\n... y {resto} mas.\n\nEsa plata no tiene a donde ir: sin codigo de cuenta el importador no sabe a que linea del P&L corresponde. Ponele el numero de cuenta en el Excel y volve a subirlo.",
        "en": "The file has {n} rows with an amount and NO account number, for a total of {total}. Nothing was loaded.\n\n{muestra}\n... and {resto} more.\n\nThat money has nowhere to go: without an account code the importer cannot tell which P&L line it belongs to. Write the account number in the Excel file and upload it again."},
    "gl.verificacion_no_cuadra": {
        "es": "La verificación de arriba no cuadra con el detalle de abajo. Revisá la comparación bucket por bucket. Si el detalle está bien y la diferencia es esperada, volvé a subir con confirmar_diferencias=true.",
        "en": "The control totals at the top do not match the detail below. Review the comparison bucket by bucket. If the detail is right and the difference is expected, upload again with confirmar_diferencias=true."},
    "hotel.no_encontrado": {
        "es": "Hotel '{hotel}' no encontrado",
        "en": "Hotel '{hotel}' not found"},
    "hotel.no_encontrado_corre_seed": {
        "es": "Hotel {hotel} no encontrado. Ejecuta el seed primero.",
        "en": "Hotel {hotel} not found. Run the seed first."},
    "locale.invalido": {
        "es": "locale debe ser uno de {locales} o null",
        "en": "locale must be one of {locales}, or null"},
    "snapshot.ya_existe": {
        "es": "Ya existe el snapshot 'Forecast {version} {anio}'",
        "en": "The snapshot 'Forecast {version} {anio}' already exists"},
    "usuario.email_duplicado": {
        "es": "Ya existe un usuario con ese email",
        "en": "A user with that email already exists"},
    "usuario.rol_invalido": {
        "es": "role debe ser uno de {roles}",
        "en": "role must be one of {roles}"},
    "version.duplicada": {
        "es": "Ya existe una versión '{version}' de {tipo} {anio}. Renombrá o borrá esa primero.",
        "en": "A '{version}' version of {tipo} {anio} already exists. Rename or delete that one first."},
    "version.nombre_vacio": {
        "es": "El nombre de versión no puede ir vacío",
        "en": "The version name cannot be empty"},
    "version.protegida": {
        "es": "La versión '{version}' está protegida (Working/Final) y no se puede borrar.",
        "en": "Version '{version}' is protected (Working/Final) and cannot be deleted."},
    "balance.sin_ancla_actual": {
        "es": "No hay Balance Sheet real cargado (Actual) para anclar la proyección. Subilo en Estados financieros → Balance Sheet.",
        "en": "There is no actual Balance Sheet loaded (Actual) to anchor the projection on. Upload it under Financial Statements → Balance Sheet."},
    "cashflow.excel_sin_filas": {
        "es": "No se encontraron filas (¿tiene encabezado 'Description' + meses?).",
        "en": "No rows were found (does it have a 'Description' header plus the months?)."},
    "codificacion.archivo_no_encontrado": {
        "es": "No se encontró el archivo de Codificación de Planilla: {ruta}",
        "en": "The payroll coding file was not found: {ruta}"},
    "driver.doce_valores": {
        "es": "'{driver}' debe traer 12 valores, uno por mes",
        "en": "'{driver}' must carry 12 values, one per month"},
    "excel.no_se_pudo_leer": {
        "es": "No se pudo leer el Excel: {detalle}",
        "en": "The Excel file could not be read: {detalle}"},
    "fte.archivo_sin_bloques": {
        "es": "El archivo no trae bloques mensuales de FTE.",
        "en": "The file has no monthly FTE blocks."},
    "mes.rango_invalido": {
        "es": "from_month/to_month tienen que estar entre 1 y 12, y from ≤ to",
        "en": "from_month/to_month must be between 1 and 12, with from ≤ to"},
    "meses.csv_invalido": {
        "es": "months inválido (lista de 1..12 separada por comas)",
        "en": "Invalid months (comma-separated list of 1..12)"},
    "meses.fuera_de_rango": {
        "es": "Los meses tienen que estar entre 1 y 12",
        "en": "Months must be between 1 and 12"},
    "pl.linea_invalida": {
        "es": "line inválida (REVENUE/OPEX/OVERHEAD/NONALLOC)",
        "en": "Invalid line (REVENUE/OPEX/OVERHEAD/NONALLOC)"},
    "planilla.sin_posiciones_validas": {
        "es": "No se encontraron posiciones válidas.",
        "en": "No valid positions were found."},
    "posicion.codigo_explicito_una_sola": {
        "es": "Un código explícito solo sirve para UNA persona. Dejalo en blanco y se generan correlativos para las {cantidad}.",
        "en": "An explicit code only works for ONE person. Leave it blank and sequential codes will be generated for all {cantidad}."},
    "posicion.codigo_ya_usado": {
        "es": "El código {codigo} ya lo usa {puesto} ({empleado}). El código es la llave de los reportes: dejalo en blanco y se genera solo.",
        "en": "Code {codigo} is already used by {puesto} ({empleado}). The code is the key of the payroll reports: leave it blank and it will be generated automatically."},
    "posicion.no_encontrada": {
        "es": "Posición no encontrada: {posicion}",
        "en": "Position not found: {posicion}"},
    "posiciones.cantidad_minima": {
        "es": "La cantidad tiene que ser al menos 1",
        "en": "The quantity must be at least 1"},
    "repartos.campo_invalido": {
        "es": "{campo} inválido: {valores}. Use uno de: {validos}",
        "en": "Invalid {campo}: {valores}. Use one of: {validos}"},
    "repartos.cuenta_repetida": {
        "es": "La cuenta {cuentas} aparece más de una vez. Dos repartos a la misma cuenta la llenarían dos veces.",
        "en": "Account {cuentas} appears more than once. Two allocations into the same account would fill it twice."},
    "repartos.cuentas_no_beneficio": {
        "es": "Estas cuentas no son de beneficio y no se pueden repartir: {cuentas}. Las que entran a la BASE de la CCSS (6001, 6010, 6027…) son salario, no un monto a distribuir.",
        "en": "These accounts are not benefit accounts and cannot be allocated: {cuentas}. The ones that go into the CCSS BASE (6001, 6010, 6027…) are salary, not an amount to be distributed."},
    "repartos.falta_departamento_origen": {
        "es": "Falta el departamento de origen en: {cuentas}.",
        "en": "The source department is missing in: {cuentas}."},
    "version.congelada_no_encontrada": {
        "es": "Versión congelada no encontrada",
        "en": "Frozen version not found"},
    "break_even.data_version_no_coincide": {
        "es": "data_version={data_version} pero el escenario {escenario} es {tipo}. Se piden los dos y tienen que coincidir: un punto de equilibrio calculado sobre la versión equivocada se ve idéntico a uno correcto.",
        "en": "data_version={data_version} but scenario {escenario} is {tipo}. Both are asked for and they have to agree: a break-even point calculated on the wrong version looks exactly like a correct one."},
    "break_even.departamento_desconocido": {
        "es": "Departamento desconocido.",
        "en": "Unknown department."},
    "break_even.departamento_no_existe": {
        "es": "El departamento «{departamento}» no existe.",
        "en": "Department “{departamento}” does not exist."},
    "break_even.falta_filtro": {
        "es": "Falta un filtro: row_ids, department_slug o be_section. Sin filtro esto pisaría todo.",
        "en": "A filter is missing: row_ids, department_slug or be_section. With no filter this would overwrite everything."},
    "break_even.linea_excluida": {
        "es": "Esta línea está excluida del punto de equilibrio (es función del resultado, no un costo fijo): su porcentaje no se usa.",
        "en": "This line is excluded from the break-even point (it is a function of the result, not a fixed cost): its percentage is not used."},
    "break_even.minimo_mayor_que_maximo": {
        "es": "El mínimo tiene que ser menor que el máximo.",
        "en": "The minimum has to be lower than the maximum."},
    "break_even.modo_invalido": {
        "es": "modo tiene que ser uno de {modos}",
        "en": "modo has to be one of {modos}"},
    "break_even.modo_necesita_mes": {
        "es": "modo={modo} necesita el parámetro `month`.",
        "en": "modo={modo} needs the `month` parameter."},
    "break_even.regla_de_otra_propiedad": {
        "es": "Esa regla no es de esta propiedad.",
        "en": "That rule does not belong to this property."},
    "break_even.regla_no_existe": {
        "es": "La regla no existe.",
        "en": "The rule does not exist."},
    "break_even.requiere_rol_edicion": {
        "es": "Se requiere rol de edición financiera para cambiar la clasificación de costos.",
        "en": "A financial editing role is required in order to change the cost classification."},
    "break_even.sin_escenarios": {
        "es": "Hay que mandar al menos un escenario.",
        "en": "At least one scenario has to be sent."},
    "costos.driver_type_invalido": {
        "es": "driver_type debe ser uno de {validos}",
        "en": "driver_type must be one of {validos}"},
    "costos.revenue_line_ref_invalido": {
        "es": "revenue_line_ref debe ser uno de {validos}",
        "en": "revenue_line_ref must be one of {validos}"},
    "costos.sin_filas_validas": {
        "es": "No se encontraron filas válidas.",
        "en": "No valid rows were found."},
    "escenario.de_otra_propiedad": {
        "es": "Ese escenario no es de esta propiedad.",
        "en": "That scenario does not belong to this property."},
    "escenario.no_existe_en_propiedad": {
        "es": "El escenario {escenario} no existe en esta propiedad.",
        "en": "Scenario {escenario} does not exist in this property."},
    "escenario.no_existe_id": {
        "es": "El escenario {escenario} no existe.",
        "en": "Scenario {escenario} does not exist."},
    "opex.archivo_no_encontrado": {
        "es": "Archivo no encontrado: {archivo}",
        "en": "File not found: {archivo}"},
    "opex.clave_de_archivo_desconocida": {
        "es": "Clave desconocida '{llave}'. Válidas: {validas}",
        "en": "Unknown key '{llave}'. Valid: {validas}"},
    "opex.sin_catalogo_de_arranque": {
        "es": "Esta propiedad no trae catálogo de arranque de OPEX. Mandá las cuentas en 'accounts': no se le sirven las de otro hotel.",
        "en": "This property ships with no OPEX starter chart of accounts. Send the accounts in 'accounts': another hotel's accounts are not served to it."},
    "opex.sin_filas_validas": {
        "es": "No se encontraron filas válidas en el archivo.",
        "en": "No valid rows were found in the file."},
    "propiedad.codigo_invalido": {
        "es": "El código va en MAYÚSCULAS, de 2 a 10 letras o números",
        "en": "The code goes in UPPERCASE, 2 to 10 letters or digits"},
    "propiedad.codigo_ya_existe": {
        "es": "Ya existe una propiedad con el código {codigo}",
        "en": "A property with code {codigo} already exists"},
    "propiedad.locale_invalido": {
        "es": "locale debe ser uno de {opciones}",
        "en": "locale must be one of {opciones}"},
    "propiedad.no_encontrada_id": {
        "es": "Propiedad no encontrada: {propiedad}",
        "en": "Property not found: {propiedad}"},
    "propiedad.nombre_vacio": {
        "es": "El nombre no puede quedar vacío",
        "en": "The name cannot be left empty"},
    "provisionamiento.datos_cargados": {
        "es": "Hay datos cargados en lo que se quiere apagar: {detalle}. Esconderlo NO borra esos datos: siguen sumando en el P&L, solo dejan de verse en las pantallas de carga. Confirmá si aun así querés esconderlo.",
        "en": "There is data loaded in what you are trying to switch off: {detalle}. Hiding it does NOT delete that data: it keeps adding up in the P&L, it only stops showing on the data-entry screens. Confirm whether you still want to hide it."},
    "provisionamiento.dimension_desconocida": {
        "es": "Dimensión desconocida: {dimension}",
        "en": "Unknown dimension: {dimension}"},
    "escenario.mes_cerrado": {
        "es": ("{mes} ya está cerrado en «{escenario}»: ese mes se reporta desde el GL "
               "y no se edita. Abrí el período en Admin → Cierre de períodos si de verdad "
               "hay que corregirlo. ({detalle})"),
        "en": ("{mes} is already closed in “{escenario}”: that month is reported from the GL "
               "and cannot be edited. Reopen the period in Admin → Period Closing if it "
               "really needs fixing. ({detalle})")},
    "cierre.solo_forecast": {
        "es": "El cierre de períodos es del FORECAST: «{tipo}» no tiene corte que mover",
        "en": "Period closing belongs to the FORECAST: “{tipo}” has no cut to move"},
    "cierre.mes_invalido": {
        "es": "El corte tiene que estar entre 0 (ningún mes cerrado) y 12: llegó {mes}",
        "en": "The cut must be between 0 (no closed month) and 12: got {mes}"},
    "cierre.apertura_sin_confirmar": {
        "es": "Abrir {meses} devuelve esos meses al checkbook (al plan) y mueve el P&L. Confirmá la apertura.",
        "en": "Reopening {meses} sends those months back to the checkbook (the plan) and moves the P&L. Confirm the reopening."},
    "provisionamiento.scope_desconocido": {
        "es": "Alcance desconocido: {scope}. Sólo hay TAB (un tab de la barra) e ITEM (una pantalla o reporte de su menú)",
        "en": "Unknown scope: {scope}. Only TAB (a nav tab) and ITEM (a screen or report inside it) exist"},
    "provisionamiento.hijo_suelto": {
        "es": "{departamento} cuelga de {madre}: el provisionamiento se hace por departamento madre y arrastra todo el paquete. Mandá {madre}.",
        "en": "{departamento} hangs off {madre}: provisioning is done by parent department and it drags the whole package along. Send {madre}."},
    "provisionamiento.origen_igual_destino": {
        "es": "El origen y el destino son la misma propiedad",
        "en": "The source and the destination are the same property"},
    "collab.estado_invalido": {
        "es": "Estado inválido. Válidos: {estados}",
        "en": "Invalid status. Valid ones: {estados}"},
    "collab.kind_invalido": {
        "es": "kind debe ser uno de {kinds}",
        "en": "kind must be one of {kinds}"},
    "collab.no_sos_responsable": {
        "es": "No sos el responsable de esta sección",
        "en": "You are not the person responsible for this section"},
    "collab.seccion_bloqueada": {
        "es": "Sección bloqueada por el administrador",
        "en": "This section has been locked by the administrator"},
    "collab.seccion_invalida": {
        "es": "Sección inválida. Válidas: {secciones}",
        "en": "Invalid section. Valid ones: {secciones}"},
    "collab.solo_admin_aprueba": {
        "es": "Solo el admin puede aprobar",
        "en": "Only an administrator can approve"},
    "collab.texto_vacio": {
        "es": "El texto no puede estar vacío",
        "en": "The text cannot be empty"},
    "departamento.ciclo_de_padres": {
        "es": "Poner a «{padre}» como padre de «{codigo}» arma un ciclo en la cadena de padres. El padre decide dónde aterriza el gasto: un ciclo es un reporte que no cierra.",
        "en": "Making “{padre}” the parent of “{codigo}” builds a cycle in the parent chain. The parent decides where the expense lands: a cycle is a report that does not add up."},
    "departamento.codigo_tomado": {
        "es": "El código «{codigo}» ya está tomado por «{nombre}». Un código no se reutiliza jamás: la historia ya cargada lo referencia. Usá uno nuevo.",
        "en": "Code “{codigo}” is already taken by “{nombre}”. A code is never reused: the history already loaded refers to it. Use a new one."},
    "departamento.codigo_tomado_inactivo": {
        "es": "El código «{codigo}» ya está tomado por «{nombre}» (inactivo). Un código no se reutiliza jamás: la historia ya cargada lo referencia. Usá uno nuevo.",
        "en": "Code “{codigo}” is already taken by “{nombre}” (inactive). A code is never reused: the history already loaded refers to it. Use a new one."},
    "departamento.falta_codigo": {
        "es": "Falta el código del departamento.",
        "en": "The department code is missing."},
    "departamento.falta_nombre": {
        "es": "Falta el nombre del departamento.",
        "en": "The department name is missing."},
    "departamento.grupo_desconocido": {
        "es": "El grupo «{grupo}» no existe en el motor. Un grupo inventado deja al departamento sin línea en el P&L y no avisa. Grupos válidos: {grupos}.",
        "en": "Group “{grupo}” does not exist in the engine. A made-up group leaves the department with no line in the P&L, and says nothing about it. Valid groups: {grupos}."},
    "departamento.madre_con_hijos_activos": {
        "es": "«{departamento}» todavía es padre de {hijos}. El gasto de un hijo se postea en su madre: desactivarla los deja sin destino. Reasignálos o desactivalos primero.",
        "en": "“{departamento}” is still the parent of {hijos}. A child's expense is posted to its parent: deactivating it leaves them with no destination. Reassign or deactivate them first."},
    "departamento.no_existe": {
        "es": "El departamento «{departamento}» no existe.",
        "en": "Department “{departamento}” does not exist."},
    "departamento.nombre_vacio": {
        "es": "El nombre no puede quedar vacío.",
        "en": "The name cannot be left empty."},
    "departamento.padre_es_el_mismo": {
        "es": "Un departamento no puede ser su propio padre.",
        "en": "A department cannot be its own parent."},
    "departamento.padre_no_existe": {
        "es": "El padre «{padre}» no existe en el catálogo.",
        "en": "Parent “{padre}” does not exist in the catalogue."},
    "departamento.pl_kind_invalido": {
        "es": "pl_kind tiene que ser uno de {pl_kinds}.",
        "en": "pl_kind has to be one of {pl_kinds}."},
    "escenario.id_no_existe": {
        "es": "El escenario {escenario} no existe",
        "en": "Scenario {escenario} does not exist"},
    "mixer.campo_negativo": {
        "es": "{campo} no puede ser negativo",
        "en": "{campo} cannot be negative"},
    "mixer.campo_pasa_de_100": {
        "es": "{campo} no puede pasar de 100%",
        "en": "{campo} cannot go above 100%"},
    "mixer.canal_con_subcanales": {
        "es": "No se puede borrar {canal}: le ruedan {n} sub-canal(es) ({subcanales}). Movelos a otro canal primero — si no, su mix quedaría sin destino y el Net Factor se calcularía sobre menos del 100%.",
        "en": "{canal} cannot be deleted: {n} sub-channel(s) roll up into it ({subcanales}). Move them to another channel first — otherwise their mix would be left with no destination and the Net Factor would be computed on less than 100%."},
    "mixer.canal_no_existe": {
        "es": "El canal {canal} no existe.",
        "en": "Channel {canal} does not exist."},
    "mixer.canal_ya_existe": {
        "es": "El canal {canal} ya existe.",
        "en": "Channel {canal} already exists."},
    "mixer.canales_comision_inexistentes": {
        "es": "estos canales de comisión no existen: {canales}. Creálos primero o elegí uno de los que hay.",
        "en": "these commission channels do not exist: {canales}. Create them first, or pick one of the ones that are already there."},
    "mixer.canales_desconocidos": {
        "es": "canales que no existen: {canales}",
        "en": "these channels do not exist: {canales}"},
    "mixer.mix_no_cierra": {
        "es": "el mix suma {suma:.2%}, tiene que dar 100%",
        "en": "the mix adds up to {suma:.2%}, it has to be 100%"},
    "mixer.rueda_a_invalido": {
        "es": "«{destino}» no es un canal de comisión. Creálo primero, o elegí uno de los que existen.",
        "en": "“{destino}” is not a commission channel. Create it first, or pick one of the ones that already exist."},
    "mixer.subcanal_no_existe": {
        "es": "El sub-canal {subcanal} no existe.",
        "en": "Sub-channel {subcanal} does not exist."},
    "mixer.subcanal_ya_existe": {
        "es": "El sub-canal {subcanal} ya existe.",
        "en": "Sub-channel {subcanal} already exists."},
    "origen.cuenta_duplicada": {
        "es": "La cuenta {cuenta} viene dos veces. No se guardó nada.",
        "en": "Account {cuenta} comes in twice. Nothing was saved."},
    "origen.cuenta_duplicada_en_depto": {
        "es": "La cuenta {cuenta} del departamento {departamento} viene dos veces. No se guardó nada.",
        "en": "Account {cuenta} of department {departamento} comes in twice. Nothing was saved."},
    "origen.desconocido": {
        "es": "Origen desconocido: {origen}. Hay: {origenes}.",
        "en": "Unknown source: {origen}. Available: {origenes}."},
    "origen.regla_incompleta": {
        "es": "Cada regla necesita cuenta de origen y cuenta destino.",
        "en": "Every rule needs a source account and a target account."},
    "origen.regla_no_existe": {
        "es": "Esa regla no existe en este origen.",
        "en": "That rule does not exist in this source."},
    "origen.sin_filas": {
        "es": "No llegó ninguna fila.",
        "en": "No rows arrived."},
    "owners_q.habitaciones_positivas": {
        "es": "mes {mes}: las habitaciones deben ser > 0",
        "en": "month {mes}: rooms must be > 0"},
    "owners_q.sin_capacidad": {
        "es": "No hay capacidad cargada para {entidad} {anio}.",
        "en": "There is no capacity loaded for {entidad} {anio}."},
    "owners_q.sin_capacidad_meses": {
        "es": "No hay capacidad cargada para {anio}, meses {meses}. Es dato, no constante: cargalo antes de emitir el reporte.",
        "en": "There is no capacity loaded for {anio}, months {meses}. It is data, not a constant: load it before issuing the report."},
    "owners_q.sin_semilla": {
        "es": "El reporte no está sembrado todavía (falta correr el seed de owners_q).",
        "en": "The report has not been seeded yet (the owners_q seed still has to be run)."},
    "owners_q.snapshot_no_existe": {
        "es": "snapshot no existe",
        "en": "snapshot does not exist"},
    "owners_q.solo_reporte_estandar": {
        "es": "Solo se congela el reporte estándar: un mes, con los tres bloques por defecto.",
        "en": "Only the standard report can be frozen: one month, with the three default blocks."},
    "archivo.ilegible": {
        "es": "No se pudo leer el archivo: {detalle}",
        "en": "The file could not be read: {detalle}"},
    "archivo.no_encontrado": {
        "es": "Archivo no encontrado: {archivo}",
        "en": "File not found: {archivo}"},
    "auditoria.falta_configurar_mapeo": {
        "es": "Falta configurar el mapeo de cuentas / líneas del reporte",
        "en": "The account mapping / report lines have not been configured yet"},
    "capital.archivo_sin_renglones": {
        "es": "El archivo no tiene renglones legibles. ¿Es el Excel descargado de Capital Project?",
        "en": "The file has no readable lines. Is it the Excel downloaded from Capital Project?"},
    "checkbook.depto_sin_cuentas": {
        "es": "El departamento {depto} no tiene ninguna cuenta de gasto en «{escenario}». Cargá al menos una en Opex antes de generar el checkbook — un archivo sin cuentas no se puede llenar.",
        "en": "Department {depto} has no expense account at all in “{escenario}”. Add at least one under Opex before generating the checkbook — a file with no accounts cannot be filled in."},
    "checkbook.referencia_de_otro_ano": {
        "es": "El escenario elegido para {anio} es de {anio_ref}. Una referencia de otro año no es una referencia.",
        "en": "The scenario chosen for {anio} is from {anio_ref}. A reference from a different year is not a reference."},
    "clase.no_soportada": {
        "es": "Clase no soportada: {clase}",
        "en": "Unsupported class: {clase}"},
    "club.base_invalida": {
        "es": "La base debe ser una de: {bases}",
        "en": "The base must be one of: {bases}"},
    "consolidado.sin_escenario": {
        "es": "{propiedad} no tiene escenario {tipo} de {anio}",
        "en": "{propiedad} has no {tipo} scenario for {anio}"},
    "consolidado.sin_escenario_version": {
        "es": "{propiedad} no tiene escenario {tipo} versión {version} de {anio}",
        "en": "{propiedad} has no {tipo} scenario version {version} for {anio}"},
    "consolidado.tipo_invalido": {
        "es": "El tipo debe ser uno de: {tipos}",
        "en": "The type must be one of: {tipos}"},
    "consulta.conjunto_desconocido": {
        "es": "Conjunto desconocido: {conjunto}",
        "en": "Unknown data set: {conjunto}"},
    "departamento.no_en_catalogo": {
        "es": "El departamento {depto} no existe en el catálogo",
        "en": "Department {depto} does not exist in the catalogue"},
    "departamento.requerido": {
        "es": "Falta el departamento",
        "en": "The department is missing"},
    "estadisticas.filas_no_reconocidas": {
        "es": "No se cargó nada. Estas filas traen dato y el escenario no las reconoce: corregilas y volvé a subir.",
        "en": "Nothing was loaded. These rows carry data and the scenario does not recognise them: fix them and upload again."},
    "estadisticas.libro_con_problemas": {
        "es": "No se pudo leer el archivo de estadísticas. Revisá los problemas de la lista y volvé a subirlo.",
        "en": "The statistics file could not be read. Check the problems listed and upload it again."},
    "export.demasiadas_filas": {
        "es": "{filas} filas es demasiado para un Excel",
        "en": "{filas} rows is too much for a single Excel file"},
    "export.fila_con_valores_de_mas": {
        "es": "«{cuadro}» → fila «{fila}»: {valores} valores para {huecos} columnas de datos ({columnas} columnas, la primera es la etiqueta). Sobran {sobran} y se perderían sin avisar.",
        "en": "“{cuadro}” → row “{fila}”: {valores} values for {huecos} data columns ({columnas} columns, the first one is the label). {sobran} are left over and would be lost without warning."},
    "export.formato_desconocido": {
        "es": "Formato de columna desconocido: {malos}. Válidos: {validos}",
        "en": "Unknown column format: {malos}. Valid ones: {validos}"},
    "export.sin_cuadros": {
        "es": "No se mandó ningún cuadro",
        "en": "No table was sent"},
    "integracion.no_existe": {
        "es": "No existe la integración «{integracion}». Hay: {disponibles}.",
        "en": "Integration “{integracion}” does not exist. Available: {disponibles}."},
    "nonop.lineas_inexistentes": {
        "es": "Estas líneas no existen en el reporte, así que su monto no llegaría al P&L: {lineas}",
        "en": "These lines do not exist in the report, so their amount would not reach the P&L: {lineas}"},
    "nonop.sin_filas_validas": {
        "es": "No se encontraron filas válidas.",
        "en": "No valid rows were found."},
    "rooms.reparto_supera_100": {
        "es": "El mes {mes} reparte {pct}% del costo de Rooms. No se puede pasar del 100%: lo que no se asigna es lo que le queda a Rooms Standard.",
        "en": "Month {mes} allocates {pct}% of the Rooms cost. It cannot go above 100%: whatever is not allocated is what stays with Rooms Standard."},
}


def texto(locale: str | None, clave: str, **params) -> str:
    """El mensaje en el idioma pedido, con sus parámetros puestos.

    Una clave que no exista devuelve la clave misma en vez de reventar: un
    error de la API no puede convertirse en un 500 por un typo en el nombre.
    `tests/test_errores_bilingues.py` es quien no deja que eso llegue lejos.
    """
    fila = MENSAJES.get(clave)
    if not fila:
        return clave
    plantilla = fila.get(normalize_locale(locale) or DEFAULT_LOCALE) or fila[DEFAULT_LOCALE]
    try:
        return plantilla.format(**params) if params else plantilla
    except (KeyError, IndexError):
        # Falta un parámetro: mejor el texto crudo que una pantalla en blanco.
        return plantilla


class ErrorApi(HTTPException):
    """Un error de la API que sabe decirse en los dos idiomas.

    `extra` es para los pocos casos en que el frontend lee campos del `detail`
    además del mensaje (por ejemplo la lista de filas que no se reconocieron):
    esos campos son DATOS y viajan tal cual — no se traducen.
    """

    def __init__(self, status_code: int, clave: str,
                 *, extra: dict | None = None, **params):
        self.clave = clave
        self.params = params
        self.extra = extra
        super().__init__(status_code=status_code,
                         detail=self._detalle(DEFAULT_LOCALE))

    def _detalle(self, locale: str | None):
        msg = texto(locale, self.clave, **self.params)
        return {"mensaje": msg, **self.extra} if self.extra else msg


def locale_de(request: Request) -> str:
    """El idioma de la petición.

    Viaja en `Accept-Language`, que `lib/api.ts` pone en cada llamada desde el
    idioma ya resuelto. No se lee la cookie: el backend vive en otro dominio
    que el frontend, así que la cookie `finplan_locale` **no llega hasta acá**.
    """
    # ⚠️ `?lang=` primero: las descargas van por `<a href>` y un href NO manda
    # cabeceras. Sin esto el Excel sale en el idioma del navegador y no en el
    # que el usuario eligió. Lo pone `dlUrl()` en `lib/api.ts`.
    return (normalize_locale(request.query_params.get("lang"))
            or normalize_locale(request.headers.get("accept-language"))
            or DEFAULT_LOCALE)


async def manejador(request: Request, exc: ErrorApi) -> JSONResponse:
    """Contesta el error en el idioma de quien preguntó."""
    # ⚠️ La CLAVE viaja junto al texto, y no es decorativa.
    #
    # El frontend a veces necesita distinguir QUÉ error es —no para mostrarlo,
    # sino para decidir—: en Provisionamiento, «hay datos cargados» abre una
    # confirmación y cualquier otro error corta. Antes eso se resolvía mirando
    # la PROSA del mensaje (`detalle.includes("datos cargados")`), que funcionó
    # mientras el backend hablaba un solo idioma. Con los mensajes bilingües
    # (2026-08-19) esa comparación falla en inglés y la confirmación no se abre
    # nunca: el usuario ve un error duro y no puede seguir.
    #
    # La clave no se traduce: es el contrato. Misma regla que el `line_code` del
    # motor del P&L — el código es estable, el idioma es presentación.
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc._detalle(locale_de(request)),
                                 "clave": exc.clave},
                        headers=getattr(exc, "headers", None) or None)
