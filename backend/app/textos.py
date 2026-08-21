# -*- coding: utf-8 -*-
"""Los textos que la API manda en respuestas NORMALES, en los dos idiomas.

**Qué es esto y en qué se diferencia de `errores.py`.** Aquel cubre lo que viaja
en una excepción; esto cubre lo que viaja en un 200: el aviso al guardar, el
resultado del chequeo, la nota al pie de un reporte. El frontend los pinta tal
cual, así que en español se quedaban aunque la app estuviera en inglés.

⚠️ **Esto vale para `app/api/`, NO para `app/engine/`.** El motor no puede
enterarse del idioma —regla del proyecto, vigilada por `tests/test_i18n_locale.py`—
y por eso lo suyo se resuelve al revés: emite una clave y el frontend la
traduce, como `ayuda_cashflow.py` y el `line_code` del P&L. La capa de API sí
puede resolver, porque tiene la petición delante: es lo que ya hace el manejador
de errores.

Uso:

    @router.get("/algo/")
    async def algo(idioma: str = Depends(idioma_de)):
        return {"aviso": t(idioma, "escenario.enllavado_no_se_cargo", esc=...)}
"""
from __future__ import annotations

from fastapi import Depends, Request

from app.i18n import DEFAULT_LOCALE, normalize_locale

#: `clave -> {es, en}`. Los `{parametros}` se rellenan con `str.format`.
TEXTOS: dict[str, dict[str, str]] = {
    "linea_ingreso.ACTIVITIES": {
        "es": "Tours",
        "en": "Tours"},
    "linea_ingreso.BEVERAGE": {
        "es": "Beverage",
        "en": "Beverage"},
    "linea_ingreso.CLUB": {
        "es": "Ingreso Madresal Club",
        "en": "Ingreso Madresal Club"},
    "linea_ingreso.CLUB_ACTIVIDAD": {
        "es": "Actividad fin de año",
        "en": "Actividad fin de año"},
    "linea_ingreso.CLUB_VISITANTES": {
        "es": "Visitantes",
        "en": "Visitantes"},
    "linea_ingreso.FNB_MISC": {
        "es": "F&B Misceláneo",
        "en": "F&B Misc."},
    "linea_ingreso.FOOD": {
        "es": "Food",
        "en": "Food"},
    "linea_ingreso.INNOCEANA": {
        "es": "Innoceana",
        "en": "Innoceana"},
    "linea_ingreso.LAUNDRY": {
        "es": "Laundry",
        "en": "Laundry"},
    "linea_ingreso.RETAIL": {
        "es": "Retail",
        "en": "Retail"},
    "linea_ingreso.ROOMS": {
        "es": "Room Revenue",
        "en": "Room Revenue"},
    "linea_ingreso.SPA": {
        "es": "Spa",
        "en": "Spa"},
    "linea_ingreso.SUSTAINABILITY": {
        "es": "Sustainability Fee & Misc. Revenue",
        "en": "Sustainability Fee & Misc. Revenue"},
    "linea_ingreso.TRANSPORT": {
        "es": "Transportation",
        "en": "Transportation"},
    "seccion.costs": {
        "es": "Costos de venta",
        "en": "Cost of sales"},
    "seccion.master": {
        "es": "Master data",
        "en": "Master data"},
    "seccion.nonop": {
        "es": "Gastos del propietario",
        "en": "Owner's expenses"},
    "seccion.opex": {
        "es": "OPEX",
        "en": "OPEX"},
    "seccion.payroll": {
        "es": "Planilla",
        "en": "Payroll"},
    "seccion.revenue": {
        "es": "Ingresos",
        "en": "Revenue"},
    "be.apalancamiento_en_el_equilibrio": {
        "es": "el resultado es exactamente cero: el apalancamiento es infinito por definición, no un número",
        "en": "the result is exactly zero: leverage is infinite by definition, not a number"},
    "be.apalancamiento_ruido": {
        "es": "el resultado está tan cerca de cero (menos del 1% del ingreso) que el apalancamiento tiende a infinito y su signo lo decide un redondeo: cualquier cifra acá sería ruido. Mirá el margen de seguridad",
        "en": "the result is so close to zero (under 1% of revenue) that leverage tends to infinity and a rounding decides its sign: any figure here would be noise. Look at the margin of safety instead"},
    "be.margen_contribucion_negativo": {
        "es": "el margen de contribución es negativo: ningún nivel de ingreso cubre los costos fijos",
        "en": "the contribution margin is negative: no level of revenue covers the fixed costs"},
    "mixer.motivo_anio": {
        "es": "es {anio} — el mixer manda desde {desde}",
        "en": "it is {anio} — the mixer governs from {desde} onwards"},
    "mixer.motivo_enllavado": {
        "es": "enllavado — su foto es historia y no se reescribe",
        "en": "locked — its snapshot is history and does not get rewritten"},
    "mixer.motivo_tipo": {
        "es": "es un {tipo} — registra lo que pasó, no se planifica",
        "en": "it is an {tipo} — it records what happened, it is not planned"},
    "auditoria.ingreso_por_otra_via": {
        "es": "Hay ingreso entrando por una vía que no es el checkbook",
        "en": "Revenue is coming in through something other than the checkbook"},
    "auditoria.ingreso_por_otra_via_detalle": {
        "es": "{n} fila(s) de gastos usan una cuenta de ingreso (4xxx) o apuntan a una línea de ingreso. El ingreso del presupuesto debe salir ÚNICAMENTE del checkbook de ingresos: revisá estas filas porque están inflando los ingresos desde el lado del gasto.",
        "en": "{n} expense row(s) use a revenue account (4xxx) or point at a revenue line. Budget revenue must come ONLY out of the revenue checkbook: review these rows, because they are inflating revenue from the expense side."},
    "auditoria.posible_doble_conteo": {
        "es": "Cafetería/Lavandería podrían estar contadas dos veces",
        "en": "Cafeteria/Laundry may be counted twice"},
    "auditoria.posible_doble_conteo_detalle": {
        "es": "Los departamentos de reparto ({deptos}) tienen {monto_reparto} presupuestados y, además, los otros departamentos llevan {monto_6025} en el concepto 6025 (cafetería) dentro de su planilla. En el presupuesto ambos suman al P&L; en los actuales el departamento de reparto se excluye porque su costo ya viaja repartido. Revisá que no estés cargando el costo por los dos lados.",
        "en": "The allocation departments ({deptos}) have {monto_reparto} budgeted and, on top of that, the other departments carry {monto_6025} under concept 6025 (cafeteria) inside their payroll. In the budget both add to the P&L; in the actuals the allocation department is excluded because its cost already travels allocated out. Check that you are not loading the cost from both sides."},
    "auditoria.veredicto_riesgo_misruteo": {
        "es": "✖ Riesgo de misruteo: hay reglas sin dept_code y cuentas que dependen del departamento",
        "en": "✖ Misrouting risk: there are rules with no dept_code and accounts that depend on the department"},
    "auditoria.veredicto_ruteo_ok": {
        "es": "✔ Ruteo por departamento configurado",
        "en": "✔ Routing by department is configured"},
    "break_even.suma_mensual_no_es_el_anual": {
        "es": "La suma de los doce equilibrios mensuales NO es el equilibrio anual: un mes que no alcanza su equilibrio se compensa con otro que lo supera, y el anual reparte el costo fijo sobre el margen de todo el año.",
        "en": "The sum of the twelve monthly break-even points is NOT the annual break-even point: a month that falls short of its own is offset by another that goes past it, and the annual figure spreads the fixed cost over the whole year's margin."},
    "break_even.supuesto_fijos_constantes": {
        "es": "los costos fijos se mantienen constantes: lo son dentro de un rango, y a 20% de ocupación parte del «fijo» no se incurre",
        "en": "fixed costs stay constant: they are fixed within a range, and at 20% occupancy part of the “fixed” cost is not incurred at all"},
    "break_even.supuesto_margen_constante": {
        "es": "el % de margen de contribución se mantiene constante: sale de la clasificación actual, y cambia si se ajustan los porcentajes",
        "en": "the contribution margin % stays constant: it comes out of the current classification, and it changes if the percentages are adjusted"},
    "break_even.supuesto_mezcla_constante": {
        "es": "la mezcla de ingresos se mantiene constante: si la ocupación cae, esto asume que Spa, Tours y A&B caen en la misma proporción",
        "en": "the revenue mix stays constant: if occupancy drops, this assumes Spa, Tours and F&B drop in the same proportion"},
    "canales.canal_sin_comercial": {
        "es": "{n} canales sin canal comercial que entre por ahí: {canales} (market codes: {codes})",
        "en": "{n} channels with no commercial channel coming in through them: {canales} (market codes: {codes})"},
    "canales.canal_sin_comercial_porque": {
        "es": "El market code cae en su canal, pero ninguna comercial entra por ese canal: nadie cobra esas noches. No se adivina — inventarle un canal comercial paga comisiones que no existen y el total sigue cuadrando.",
        "en": "The market code lands in its channel, but no commercial channel comes in through it: nobody is charging for those nights. It is not guessed — making up a commercial channel pays commissions that do not exist and the overall total still adds up."},
    "canales.comision_distinta": {
        "es": "«{canal}» paga {real} y FinPlan usa {finplan} para {destino} ({dif})",
        "en": "“{canal}” pays {real} and FinPlan uses {finplan} for {destino} ({dif})"},
    "canales.comision_distinta_porque": {
        "es": "El Net Factor —y con él el ingreso neto de todo el presupuesto— sale de la comisión de FinPlan. Si la real es otra, el neto está mal.",
        "en": "The Net Factor — and with it the net revenue of the whole budget — comes out of FinPlan's commission. If the real one is different, the net figure is wrong."},
    "canales.comision_sin_origen": {
        "es": "FinPlan comisiona {canales} y ningún canal comercial rueda ahí",
        "en": "FinPlan charges commission on {canales} and no commercial channel rolls up there"},
    "canales.comision_sin_origen_porque": {
        "es": "O sobra en FinPlan, o falta el canal que lo alimenta.",
        "en": "Either it is left over in FinPlan, or the channel that feeds it is missing."},
    "canales.market_code_sin_canal": {
        "es": "{n} market codes sin canal: {codes}",
        "en": "{n} market codes with no channel: {codes}"},
    "canales.market_code_sin_canal_porque": {
        "es": "Sus noches no caen en ningún canal. No se adivinan: un código en el canal equivocado manda las noches al lugar equivocado y el total sigue cuadrando.",
        "en": "Their nights land in no channel at all. They are not guessed: a code in the wrong channel sends the nights to the wrong place and the overall total still adds up."},
    "canales.sin_origen_en_el_pms": {
        "es": "{n} canales describen QUIÉN trajo la reserva, no por dónde entró: {canales}",
        "en": "{n} channels describe WHO brought the booking in, not where it came in through: {canales}"},
    "canales.sin_origen_en_el_pms_porque": {
        "es": "Opera no registra quién la trajo — una reserva con market code DIR puede haber entrado por teléfono, haberla traído la ejecutiva o venir de CRC, y el código es el mismo. Esa atribución hay que digitarla o sacarla de un campo de agente del PMS; no se puede deducir.",
        "en": "Opera does not record who brought it in — a booking with market code DIR may have come in by phone, been brought in by the sales executive or come from CRC, and the code is the same. That attribution has to be typed in or taken from an agent field in the PMS; it cannot be deduced."},
    "cashflow.sin_tc_ni_del_hotel": {
        "es": "El escenario no tiene tipos de cambio y el hotel tampoco: la retención de renta no se puede calcular y queda en cero.",
        "en": "Neither this scenario nor the property has exchange rates: the income tax withholding cannot be calculated and stays at zero."},
    "cashflow.tc_del_hotel": {
        "es": "El escenario no tiene tipos de cambio cargados; se usó el del hotel ({tc}).",
        "en": "This scenario has no exchange rates loaded; the property's own rate was used ({tc})."},
    "cashflow.timing_desactivado": {
        "es": "El modelo de timing está DESACTIVADO en los Criterios. Los cobros no usan la matriz y este flujo NO es comparable con el Cash Flow Budget.",
        "en": "The timing model is TURNED OFF under Criteria. Collections do not use the matrix and this statement is NOT comparable with the Cash Flow Budget."},
    "chequeo.contaminacion_hay": {
        "es": "Hay filas de otro hotel en: {tablas}.",
        "en": "There are rows from another property in: {tablas}."},
    "chequeo.contaminacion_hay_porque": {
        "es": "Se ven normales en pantalla y suman en los reportes de esta propiedad.",
        "en": "They look normal on screen and they add up in this property's reports."},
    "chequeo.contaminacion_hay_que_hacer": {
        "es": "Suele venir de restaurar un dump de otra instalación. Revisar antes de seguir cargando.",
        "en": "It usually comes from restoring a dump of another installation. Check it before loading anything else."},
    "chequeo.contaminacion_ok": {
        "es": "Ninguna fila con el hotel_id de otra propiedad.",
        "en": "Not one row carrying another property's hotel_id."},
    "chequeo.contaminacion_titulo": {
        "es": "Datos de otra propiedad",
        "en": "Data from another property"},
    "chequeo.estructura_titulo": {
        "es": "Estructura completa",
        "en": "Complete structure"},
    "chequeo.estructura_ok": {
        "es": "Las {n} piezas de estructura del grupo están completas.",
        "en": "All {n} group-level structure datasets are complete."},
    "chequeo.estructura_ok_porque": {
        "es": "Se comparó fila por fila contra la misma fuente que usa el seed, no contra un número escrito a mano.",
        "en": "Counted row by row against the very source the seed reads, not against a hand-typed number."},
    "chequeo.estructura_de_mas": {
        "es": "Y hay filas que el repo no trae: {tablas}.",
        "en": "And there are rows the repo does not carry: {tablas}."},
    "chequeo.estructura_de_mas_porque": {
        "es": "Se agregaron a mano en la app. No es un error, pero el seed no puede reproducirlas: si esta base se reconstruye, se pierden.",
        "en": "They were added by hand in the app. Not an error, but the seed cannot reproduce them: if this database is rebuilt, they are lost."},
    "chequeo.estructura_incompleta": {
        "es": "Falta estructura: {tablas}.",
        "en": "Missing structure: {tablas}."},
    "chequeo.estructura_incompleta_porque": {
        "es": "Incompleta no se nota: lo que se suba después cae en ninguna línea del P&L, o cae en cero — y cero se lee igual que «no vendió».",
        "en": "Incomplete does not show: whatever is loaded afterwards falls into no P&L line, or falls to zero — and zero reads exactly like «sold nothing»."},
    "chequeo.estructura_incompleta_que_hacer": {
        "es": "Correr «python -m app.seed» y volver a chequear. Si sigue faltando, el seed está fallando en silencio: mirar el log del despliegue.",
        "en": "Run «python -m app.seed» and check again. If it is still missing, the seed is failing silently: read the deploy log."},
    "chequeo.estructura_sin_verificar": {
        "es": "{n} piezas completas, y {tablas} no se pudo mirar.",
        "en": "{n} datasets complete, and {tablas} could not be inspected."},
    "chequeo.estructura_sin_verificar_porque": {
        "es": "No se pudo mirar NO es «está bien». Contarlo como bueno sería dar por sana una instalación sin haber comparado nada.",
        "en": "Could-not-inspect is NOT «fine». Counting it as good would pass an installation as healthy without having compared anything."},
    "chequeo.estructura_sin_verificar_que_hacer": {
        "es": "Suele ser una migración pendiente: la tabla todavía no existe. Revisar el chequeo de migraciones acá abajo.",
        "en": "Usually a pending migration: the table does not exist yet. See the migrations check below."},
    "chequeo.propiedad_sin_archivos": {
        "es": "{n} archivos de arranque que esta propiedad no tiene ({cuales})",
        "en": "{n} start-up files this property does not have ({cuales})"},
    "chequeo.propiedad_titulo": {
        "es": "Lo que le toca cargar a esta propiedad",
        "en": "What this property still has to load"},
    "chequeo.propiedad_ok": {
        "es": "Las {n} piezas propias de esta propiedad están cargadas.",
        "en": "All {n} property-specific datasets are loaded."},
    "chequeo.propiedad_falta": {
        "es": "Todavía sin cargar: {tablas}.",
        "en": "Not loaded yet: {tablas}."},
    "chequeo.propiedad_falta_porque": {
        "es": "En una propiedad recién abierta falta a propósito: no hereda los datos de otra. Pero vacío se lee como cero en los reportes, y eso no avisa.",
        "en": "In a newly opened property this is missing on purpose: it does not inherit another property's data. But empty reads as zero in the reports, and that gives no warning."},
    "chequeo.propiedad_falta_que_hacer": {
        "es": "Cargarlo en la app, o dejar su archivo en app/seed_data/<HOTEL_ID>/ para que entre en el próximo despliegue.",
        "en": "Load it in the app, or drop its file into app/seed_data/<HOTEL_ID>/ so the next deploy picks it up."},
    "chequeo.identidad_no_existe": {
        "es": "El entorno dice HOTEL_ID={hotel_id} y en la base hay: {ids}.",
        "en": "The environment says HOTEL_ID={hotel_id} and the database holds: {ids}."},
    "chequeo.identidad_no_existe_porque": {
        "es": "Todo lo que se cargue cuelga de ese id. Si la fila no existe o es la de otro hotel, los datos nacen colgados del hotel equivocado y se ve todo normal.",
        "en": "Everything that gets loaded hangs off that id. If the row does not exist, or it is another property's, the data is born hanging off the wrong property and everything looks normal."},
    "chequeo.identidad_no_existe_que_hacer": {
        "es": "Corregir la variable HOTEL_ID del backend y reiniciar ANTES de cargar nada. Si ya se cargó, hay que arreglarlo en la base.",
        "en": "Fix the backend's HOTEL_ID variable and restart BEFORE loading anything. If something was already loaded, it has to be fixed in the database."},
    "chequeo.identidad_ok": {
        "es": "{hotel_id} · {nombre} · {rooms} habitaciones · TC {tc}.{nota}",
        "en": "{hotel_id} · {nombre} · {rooms} rooms · exchange rate {tc}.{nota}"},
    "chequeo.identidad_ok_nota": {
        "es": " El nombre en la base es «{en_base}» y el del entorno «{en_entorno}» — manda el de la base; el del entorno solo titula los Excel.",
        "en": " The name in the database is “{en_base}” and the one in the environment “{en_entorno}” — the database wins; the environment's only titles the Excel files."},
    "chequeo.identidad_titulo": {
        "es": "La identidad del hotel",
        "en": "The property's identity"},
    "chequeo.identidad_varios": {
        "es": "Esta instalación es {hotel_id} ({nombre}), pero en la base hay {n} hoteles: {ids}.",
        "en": "This installation is {hotel_id} ({nombre}), but the database holds {n} properties: {ids}."},
    "chequeo.identidad_varios_porque": {
        "es": "El modelo es una base por propiedad. Otro hotel acá suele ser un dump restaurado de otra instalación.",
        "en": "The model is one database per property. Another property in here usually means a dump restored from a different installation."},
    "chequeo.inventario_difiere": {
        "es": "La ficha del hotel dice {fichadas} y los tipos activos suman {unidades}.",
        "en": "The property record says {fichadas} and the active room types add up to {unidades}."},
    "chequeo.inventario_difiere_porque": {
        "es": "El motor calcula la disponibilidad desde los TIPOS, así que la ocupación y el RevPAR salen de los {unidades}. El número de la ficha es el que reporta la app por fuera — o sea que uno de los dos está mintiendo.",
        "en": "The engine works out availability from the room TYPES, so occupancy and RevPAR come out of the {unidades}. The number on the record is the one the app reports on the outside — which means one of the two is lying."},
    "chequeo.inventario_difiere_que_hacer": {
        "es": "Corregir el que esté viejo en Master Data → Provisionamiento. Suele pasar al agregar una categoría nueva y no actualizar la ficha.",
        "en": "Fix whichever one is stale in Master Data → Provisioning · departments. It usually happens when a new room category is added and the record is not updated."},
    "chequeo.inventario_ok": {
        "es": "La ficha y los tipos coinciden en {unidades}.",
        "en": "The record and the room types agree at {unidades}."},
    "chequeo.inventario_titulo": {
        "es": "Las habitaciones de la ficha",
        "en": "The room count on the property record"},
    "chequeo.mapeo_titulo": {
        "es": "El mapeo del repo, aplicado",
        "en": "The repo's mapping, actually applied"},
    "chequeo.mapeo_ok": {
        "es": "Las {n} reglas del repo están aplicadas tal cual.",
        "en": "All {n} rules from the repo are applied exactly as written."},
    "chequeo.mapeo_ok_porque": {
        "es": "Se comparó el contenido, no la cantidad: contar no habría notado que la siembra se estaba cayendo.",
        "en": "Content was compared, not counts: counting would not have noticed the seed was failing."},
    "chequeo.mapeo_desviado": {
        "es": "El mapeo de esta base no es el del repo: {faltan} sin aplicar, {distintas} distintas. Por ejemplo: {ejemplos}.",
        "en": "This database's mapping is not the repo's: {faltan} never applied, {distintas} different. For example: {ejemplos}."},
    "chequeo.mapeo_desviado_porque": {
        "es": "El mapeo decide en qué línea del P&L cae cada cuenta. Una diferencia acá re-expresa el reporte entero y ningún total avisa: la plata se mueve entre filas del mismo subtotal.",
        "en": "The mapping decides which P&L line each account lands on. A difference here re-expresses the whole report and no total warns: money moves between rows of the same subtotal."},
    "chequeo.mapeo_desviado_que_hacer": {
        "es": "Mirar el log del último despliegue: si dice «seed de mapeo omitido», la siembra se está cayendo y hay que arreglar eso, no la base.",
        "en": "Read the last deploy log: if it says «seed de mapeo omitido», the seed is failing and that is what to fix, not the database."},
    "chequeo.mapeo_documental": {
        "es": "{n} reglas tienen la nota vieja, pero rutean igual que el repo.",
        "en": "{n} rules carry the old note, but they route exactly like the repo."},
    "chequeo.mapeo_documental_porque": {
        "es": "Solo cambia texto de documentación: el reporte da lo mismo. Igual se avisa, porque significa que la siembra no está aplicando lo del repo — y la próxima vez podría ser una línea del P&L.",
        "en": "Only documentation text differs: the report is identical. It is still flagged, because it means the seed is not applying the repo — and next time it could be a P&L line."},
    "chequeo.mapeo_no_se_pudo": {
        "es": "No se pudo comparar contra el repo: {error}",
        "en": "Could not compare against the repo: {error}"},
    "chequeo.mapeo_no_se_pudo_porque": {
        "es": "No se pudo mirar no es «está bien»: queda sin comprobar si esta base tiene el mapeo del repo.",
        "en": "Could-not-inspect is not «fine»: whether this database carries the repo's mapping remains unchecked."},
    "chequeo.migraciones_atrasada": {
        "es": "La base está en {en_base} y este código trae hasta {head}.",
        "en": "The database is at {en_base} and this code goes up to {head}."},
    "chequeo.migraciones_atrasada_porque": {
        "es": "Una tabla o columna que el código espera puede no existir.",
        "en": "A table or a column the code expects may not exist."},
    "chequeo.migraciones_atrasada_que_hacer": {
        "es": "Redesplegar: el arranque corre `alembic upgrade head` solo.",
        "en": "Redeploy: startup runs `alembic upgrade head` on its own."},
    "chequeo.migraciones_ok": {
        "es": "Al día ({en_base}).",
        "en": "Up to date ({en_base})."},
    "chequeo.migraciones_sin_tabla": {
        "es": "La base no tiene tabla de versión de Alembic.",
        "en": "The database has no Alembic version table."},
    "chequeo.migraciones_sin_tabla_porque": {
        "es": "El esquema puede estar incompleto.",
        "en": "The schema may be incomplete."},
    "chequeo.migraciones_sin_tabla_que_hacer": {
        "es": "Correr `alembic upgrade head`.",
        "en": "Run `alembic upgrade head`."},
    "chequeo.migraciones_titulo": {
        "es": "Las migraciones",
        "en": "The migrations"},
    "chequeo.mix_no_cierra": {
        "es": "Suma {suma} y tiene que dar 100%.",
        "en": "It adds up to {suma} and it has to come to 100%."},
    "chequeo.mix_no_cierra_porque": {
        "es": "El Net Factor saldría sobre una base que no es el total, y el error se propaga a todo el ingreso sin que nada falle.",
        "en": "The Net Factor would be worked out on a base that is not the total, and the error spreads through all revenue without anything failing."},
    "chequeo.mix_no_cierra_que_hacer": {
        "es": "Corregirlo en Master Data → Canales y mixer.",
        "en": "Fix it in Master Data → Channels & mixer."},
    "chequeo.mix_no_verificable": {
        "es": "No se pudo verificar: {error}.",
        "en": "It could not be verified: {error}."},
    "chequeo.mix_ok": {
        "es": "Cierra en {suma}.",
        "en": "It closes at {suma}."},
    "chequeo.mix_titulo": {
        "es": "El mix de canales",
        "en": "The channel mix"},
    "chequeo.motor_account_mapping": {
        "es": "el mapeo de cuentas al P&L",
        "en": "the account-to-P&L mapping"},
    "chequeo.motor_canales_comerciales": {
        "es": "los canales comerciales",
        "en": "the sales channels"},
    "chequeo.motor_department_catalog": {
        "es": "el catálogo de departamentos",
        "en": "the department catalogue"},
    "chequeo.motor_market_codes": {
        "es": "los market codes de Opera",
        "en": "Opera's market codes"},
    "chequeo.motor_ok": {
        "es": "{n} filas sembradas — mapeo, líneas del P&L, departamentos, cuentas estadísticas, market codes y canales.",
        "en": "{n} rows seeded — mapping, P&L lines, departments, statistical accounts, market codes and channels."},
    "chequeo.motor_ok_porque": {
        "es": "No son de ningún hotel en particular: llegan solas en cada arranque. Por eso una propiedad «en cero» igual puede recibir la carga histórica.",
        "en": "They belong to no property in particular: they arrive on their own at every startup. That is why a property “at zero” can still take the historical load."},
    "chequeo.motor_report_line_config": {
        "es": "las líneas del P&L",
        "en": "the P&L lines"},
    "chequeo.motor_stat_accounts": {
        "es": "las cuentas estadísticas (clase 9)",
        "en": "the statistical accounts (class 9)"},
    "chequeo.motor_titulo": {
        "es": "El motor contable",
        "en": "The accounting engine"},
    "chequeo.motor_vacio": {
        "es": "Vacío o ausente: {tablas}.",
        "en": "Empty or missing: {tablas}."},
    "chequeo.motor_vacio_porque": {
        "es": "Sin el mapeo, un GL que se suba NO cae en ninguna línea del P&L. El total daría cero y nada avisaría por qué.",
        "en": "Without the mapping, a GL that gets uploaded lands on NO P&L line at all. The total would come out zero and nothing would say why."},
    "chequeo.motor_vacio_que_hacer": {
        "es": "Lo siembra el arranque desde el JSON del repo. Revisar los logs del backend: el seed pudo fallar sin tumbar el servicio.",
        "en": "Startup seeds it from the JSON in the repo. Check the backend logs: the seed can fail without taking the service down."},
    "chequeo.negocio": {
        "es": "{n} filas.{detalle}",
        "en": "{n} rows.{detalle}"},
    "chequeo.negocio_porque": {
        "es": "En una propiedad recién abierta tiene que dar CERO. En una restaurada desde otra instalación, decenas de miles. Si esperabas cero y no da cero, algo se restauró de más.",
        "en": "In a property that has just opened it has to come to ZERO. In one restored from another installation, tens of thousands. If you expected zero and it does not come to zero, something extra was restored."},
    "chequeo.negocio_titulo": {
        "es": "El dato de negocio",
        "en": "The business data"},
    "chequeo.ninguno": {
        "es": "ninguno",
        "en": "none"},
    "chequeo.tipos_ninguno": {
        "es": "Ninguno cargado.",
        "en": "None loaded."},
    "chequeo.tipos_ninguno_porque": {
        "es": "Es lo NORMAL en una propiedad recién abierta: el arranque no le inventa los de otra. Pero ahí nacen los códigos (BL01, BI02…) y el código no se mueve nunca después.",
        "en": "This is NORMAL in a property that has just opened: startup does not invent another property's for it. But that is where the codes are born (BL01, BI02…) and a code never moves afterwards."},
    "chequeo.tipos_ninguno_que_hacer": {
        "es": "Cargarlos en Master Data ANTES de subir tarifas o historia.",
        "en": "Load them in Master Data BEFORE uploading rates or history."},
    "chequeo.tipos_ok": {
        "es": "{n} tipos cargados.",
        "en": "{n} room types loaded."},
    "chequeo.tipos_titulo": {
        "es": "Tipos de habitación",
        "en": "Room types"},
    "chequeo.usuarios_ninguno": {
        "es": "Ninguno.",
        "en": "None."},
    "chequeo.usuarios_ninguno_porque": {
        "es": "El arranque no siembra en una propiedad el equipo de otra: son personas de otro hotel.",
        "en": "Startup does not seed one property with another property's team: those are people from a different hotel."},
    "chequeo.usuarios_ninguno_que_hacer": {
        "es": "Crear el primer administrador a mano.",
        "en": "Create the first administrator by hand."},
    "chequeo.usuarios_ok": {
        "es": "{n} usuarios.",
        "en": "{n} users."},
    "chequeo.usuarios_titulo": {
        "es": "Usuarios",
        "en": "Users"},
    "club.membresias.acuerdo_pago": {
        "es": "Membresías En acuerdo de pago",
        "en": "Memberships on a payment agreement"},
    "club.membresias.condicionados": {
        "es": "Membresías Condicionados",
        "en": "Conditional memberships"},
    "club.membresias.pagando": {
        "es": "Membresías Pagando",
        "en": "Paying memberships"},
    "club.membresias.total": {
        "es": "Total Membresías",
        "en": "Total memberships"},
    "club.total_es_el_saldo_de_diciembre": {
        "es": "El total del año es el saldo de diciembre, no la suma de los doce meses: son socios, no ingresos. Si diciembre todavía no se cargó, se muestra el último mes cargado.",
        "en": "The year total is December's closing balance, not the sum of the twelve months: these are members, not revenue. If December has not been loaded yet, the last month loaded is shown."},
    "club.tres_fuentes_una_linea": {
        "es": "La cuota sale de socios × precio; la actividad de fin de año y los visitantes se digitan. Cada una va a su cuenta (4500 / 4501 / 4502) y las tres suman en REV_CLUB.",
        "en": "The fee comes out of members × price; the year-end activity and the visitors are typed in. Each one goes to its own account (4500 / 4501 / 4502) and all three add up in REV_CLUB."},
    "colaboracion.canales_sin_configurar": {
        "es": "Canales de venta sin configurar",
        "en": "Sales channels not configured"},
    "colaboracion.inventario_ok": {
        "es": "Inventario: {n} unidades",
        "en": "Inventory: {n} units"},
    "colaboracion.mix_no_cierra": {
        "es": "Mix de canales ≠ 100% en {n} mes(es)",
        "en": "Channel mix ≠ 100% in {n} month(s)"},
    "colaboracion.ocupacion_sobre_cien": {
        "es": "Ocupación > 100% en {n} celda(s)",
        "en": "Occupancy > 100% in {n} cell(s)"},
    "colaboracion.opex_sin_datos": {
        "es": "OPEX sin datos",
        "en": "OPEX has no data"},
    "colaboracion.posiciones_con_salario": {
        "es": "{n} posiciones con salario",
        "en": "{n} positions with a salary"},
    "colaboracion.posiciones_sin_salario": {
        "es": "{n} posicion(es) sin salario",
        "en": "{n} position(s) with no salary"},
    "colaboracion.revenue_completo": {
        "es": "{n} líneas de revenue con monto",
        "en": "{n} revenue lines with an amount"},
    "colaboracion.revenue_faltan_lineas": {
        "es": "Faltan {n} líneas: {lineas}",
        "en": "{n} lines missing: {lineas}"},
    "colaboracion.revenue_vacio": {
        "es": "Revenue checkbook vacío",
        "en": "Revenue checkbook is empty"},
    "colaboracion.sin_inventario": {
        "es": "Sin inventario (units en 0)",
        "en": "No inventory (units at 0)"},
    "colaboracion.sin_posiciones": {
        "es": "Sin posiciones de planilla",
        "en": "No payroll positions"},
    "consulta.col.account_code": {
        "es": "Cuenta",
        "en": "Account"},
    "consulta.col.account_name": {
        "es": "Nombre cuenta",
        "en": "Account name"},
    "consulta.col.anio": {
        "es": "Año",
        "en": "Year"},
    "consulta.col.clase": {
        "es": "Clase",
        "en": "Class"},
    "consulta.col.dept_code": {
        "es": "Depto",
        "en": "Dept"},
    "consulta.col.dept_name": {
        "es": "Nombre depto",
        "en": "Dept name"},
    "consulta.col.dept_padre": {
        "es": "Depto padre",
        "en": "Parent dept"},
    "consulta.col.detalle": {
        "es": "Detalle",
        "en": "Detail"},
    "consulta.col.employee": {
        "es": "Colaborador",
        "en": "Employee"},
    "consulta.col.escenario": {
        "es": "Escenario",
        "en": "Scenario"},
    "consulta.col.grupo": {
        "es": "Grupo",
        "en": "Group"},
    "consulta.col.linea_pl": {
        "es": "Línea del P&L",
        "en": "P&L line"},
    "consulta.col.linea_pl_nombre": {
        "es": "Nombre de la línea",
        "en": "Line name"},
    "consulta.col.mes": {
        "es": "Mes",
        "en": "Month"},
    "consulta.col.mes_num": {
        "es": "Mes #",
        "en": "Month #"},
    "consulta.col.monto": {
        "es": "Monto USD",
        "en": "Amount USD"},
    "consulta.col.outlet": {
        "es": "Outlet",
        "en": "Outlet"},
    "consulta.col.position_code": {
        "es": "Código posición",
        "en": "Position code"},
    "consulta.col.position_name": {
        "es": "Posición",
        "en": "Position"},
    "consulta.col.seccion": {
        "es": "Sección del P&L",
        "en": "P&L section"},
    "consulta.col.tipo_dept": {
        "es": "Tipo depto",
        "en": "Dept type"},
    "consulta.conjunto.costo": {
        "es": "Costo de ventas (checkbook)",
        "en": "Cost of sales (checkbook)"},
    "consulta.conjunto.gl": {
        "es": "Detalle del GL (todas las cuentas)",
        "en": "GL detail (every account)"},
    "consulta.conjunto.gl_nota": {
        "es": "Cuenta × departamento × mes, tal como se cargó. Es el conjunto más completo.",
        "en": "Account × department × month, exactly as loaded. It is the most complete data set."},
    "consulta.conjunto.opex": {
        "es": "OPEX (checkbook)",
        "en": "OPEX (checkbook)"},
    "consulta.conjunto.opex_nota": {
        "es": "El gasto operativo que se presupuesta en la app.",
        "en": "The operating expense that is budgeted in the app."},
    "consulta.conjunto.pl": {
        "es": "Líneas del P&L (resumen)",
        "en": "P&L lines (summary)"},
    "consulta.conjunto.pl_nota": {
        "es": "El P&L a nivel de línea, mes a mes.",
        "en": "The P&L at line level, month by month."},
    "consulta.conjunto.planilla": {
        "es": "Planilla por concepto",
        "en": "Payroll by concept"},
    "consulta.conjunto.planilla_nota": {
        "es": "Los 17 conceptos abiertos en filas: horas extras, aguinaldo, cesantía...",
        "en": "The 17 concepts opened up into rows: overtime, Christmas bonus, severance..."},
    "consulta.conjunto.propietario": {
        "es": "Gastos del propietario (8xxx)",
        "en": "Owner expenses (8xxx)"},
    "consulta.mes.1": {
        "es": "Ene",
        "en": "Jan"},
    "consulta.mes.10": {
        "es": "Oct",
        "en": "Oct"},
    "consulta.mes.11": {
        "es": "Nov",
        "en": "Nov"},
    "consulta.mes.12": {
        "es": "Dic",
        "en": "Dec"},
    "consulta.mes.2": {
        "es": "Feb",
        "en": "Feb"},
    "consulta.mes.3": {
        "es": "Mar",
        "en": "Mar"},
    "consulta.mes.4": {
        "es": "Abr",
        "en": "Apr"},
    "consulta.mes.5": {
        "es": "May",
        "en": "May"},
    "consulta.mes.6": {
        "es": "Jun",
        "en": "Jun"},
    "consulta.mes.7": {
        "es": "Jul",
        "en": "Jul"},
    "consulta.mes.8": {
        "es": "Ago",
        "en": "Aug"},
    "consulta.mes.9": {
        "es": "Set",
        "en": "Sep"},
    "departamento.cambio_de_etiqueta": {
        "es": "Cambio de etiqueta: no mueve ningún número.",
        "en": "Label change: it moves no number."},
    "departamento.cambio_entra_en_el_proximo_despliegue": {
        "es": "El motor toma el catálogo al arrancar: los cambios de grupo o de padre entran en el próximo despliegue.",
        "en": "The engine picks the catalogue up at start-up: changes of group or of parent reach the P&L on the next deploy."},
    "departamento.entra_en_el_proximo_despliegue": {
        "es": "El motor toma el catálogo al arrancar (`set_dept_catalog`): este departamento entra al P&L en el próximo despliegue o reinicio.",
        "en": "The engine picks the catalogue up at start-up (`set_dept_catalog`): this department reaches the P&L on the next deploy or restart."},
    "escenario.conserva_el_corte": {
        "es": "«{escenario}» conserva su corte de meses cerrados (actuals_through={corte}). Si este archivo es un snapshot que ya trae su propio blend y querés que el motor deje de pisarlo con el ACTUAL enlazado, volvé a subirlo con apagar_corte=true.",
        "en": "“{escenario}” keeps its closed-months cut-off (actuals_through={corte}). If this file is a snapshot that already carries its own blend and you want the engine to stop overwriting it with the linked ACTUAL, upload it again with apagar_corte=true."},
    "escenario.copia_sin_el_mayor": {
        "es": "El origen lee el P&L del mayor (source_mode='{modo_origen}') pero el mayor no estaba en los datasets pedidos ({datasets}): el destino conserva source_mode='{modo_destino}' en vez de nacer marcado como histórico y sin histórico.",
        "en": "The source reads the P&L from the ledger (source_mode='{modo_origen}') but the ledger was not among the data sets requested ({datasets}): the target keeps source_mode='{modo_destino}' instead of being born flagged as historical with no history in it."},
    "escenario.enllavado_no_se_cargo": {
        "es": "«{escenario}» está enllavado (status=locked) — no se cargó nada. Destrabalo si querés reemplazarlo.",
        "en": "“{escenario}” is locked (status=locked) — nothing was loaded. Unlock it if you want to replace it."},
    "gl.verificacion_no_corrio": {
        "es": "sin versión destino, enllavada o sin mapeo cargado",
        "en": "no target version, locked, or no mapping loaded"},
    "integracion.configurada_no_es_conectada": {
        "es": "«configurada» significa que las credenciales están cargadas, no que la conexión funcione. Usá «probar» para eso.",
        "en": "“configured” means the credentials are loaded, not that the connection works. Use “test” for that."},
    "integracion.ohip_revisar_base_url": {
        "es": "Revisar OPERA_BASE_URL (cambia por cadena), la app key, y que el usuario tenga permiso sobre OPERA_HOTEL_ID.",
        "en": "Check OPERA_BASE_URL (it differs per chain), the app key, and that the user has permission over OPERA_HOTEL_ID."},
    "integracion.ohip_revisar_host": {
        "es": "Si es un error de nombre de host, revisar OPERA_BASE_URL.",
        "en": "If it is a host-name error, check OPERA_BASE_URL."},
    "integracion.ohip_sin_access_token": {
        "es": "OHIP contestó sin access_token",
        "en": "OHIP replied with no access_token"},
    "integracion.ohip_sin_contacto": {
        "es": "no se pudo hablar con OHIP",
        "en": "could not reach OHIP"},
    "integracion.ohip_sin_token": {
        "es": "OHIP no entregó token",
        "en": "OHIP did not hand over a token"},
    "integracion.qbo_empresa_no_responde": {
        "es": "el token sirve pero la empresa no responde",
        "en": "the token works but the company does not respond"},
    "integracion.qbo_http_al_pedir_token": {
        "es": "HTTP {http} al pedir el access token",
        "en": "HTTP {http} while requesting the access token"},
    "integracion.qbo_refresh_rechazado": {
        "es": "el refresh token no fue aceptado",
        "en": "the refresh token was not accepted"},
    "integracion.qbo_rehacer_oauth": {
        "es": "Rehacer el OAuth: el refresh token caduca si no se usa.",
        "en": "Redo the OAuth flow: the refresh token expires if it goes unused."},
    "integracion.qbo_revisar_realm": {
        "es": "Revisar QBO_REALM_ID y que QBO_ENTORNO sea el correcto.",
        "en": "Check QBO_REALM_ID, and that QBO_ENTORNO is the right one."},
    "integracion.qbo_sin_access_token": {
        "es": "Intuit no devolvió access_token",
        "en": "Intuit returned no access_token"},
    "integracion.qbo_sin_contacto": {
        "es": "no se pudo hablar con Intuit",
        "en": "could not reach Intuit"},
    "integracion.sin_configurar": {
        "es": "sin configurar",
        "en": "not configured"},
    "mixer.canales_si_tarifas_no": {
        "es": "Se escribieron los canales pero NO las tarifas: en un escenario con tarifa neta cargada el motor la prefiere sobre el mix, así que los números no se van a mover.",
        "en": "The channels were written but the rates were NOT: in a scenario with a net rate loaded the engine prefers it over the mix, so the numbers will not move."},
    "mixer.escenario_no_existe": {
        "es": "no existe",
        "en": "does not exist"},
    "mixer.hay_que_recalcular": {
        "es": "Los escenarios tocados hay que RECALCULARLOS para que el nuevo factor llegue al P&L.",
        "en": "The scenarios that were touched have to be RECALCULATED for the new factor to reach the P&L."},
    "mixer.mix_no_cierra": {
        "es": "el mix suma {suma}, tiene que dar 100%",
        "en": "the mix adds up to {suma}, it has to come to 100%"},
    "mixer.mix_quedo_incompleto": {
        "es": "El mix quedó en {suma}. Mientras no dé 100% no se puede aplicar: el Net Factor saldría sobre una base que no es el total.",
        "en": "The mix is now at {suma}. Until it comes to 100% it cannot be applied: the Net Factor would be computed over a base that is not the whole."},
    "moneda.sin_tipo_de_cambio": {
        "es": "sin tipo de cambio",
        "en": "no exchange rate"},
    "origenes.el_mapeo_habilita_el_origen": {
        "es": "Cargar el mapeo es lo que habilita un origen. Un adaptador sin mapeo no puede escribir nada, y está bien que así sea.",
        "en": "Loading the mapping is what enables a source. An adapter with no mapping cannot write anything, and that is as it should be."},
    "owners_q.cuenta_sin_regla_activa": {
        "es": "cuenta con movimiento y sin regla activa",
        "en": "account with activity and no active rule"},
    "planilla.driver_pisa_lo_manual": {
        "es": "{columna}: hay una tasa cargada en Parámetros de Planilla, así que la fórmula manda y va a pisar estos montos al recalcular. Poné esa tasa en CERO si querés que valga lo que subiste.",
        "en": "{columna}: there is a rate loaded under Payroll Parameters, so the formula wins and will overwrite these amounts on the next recalculation. Set that rate to ZERO if you want what you uploaded to stand."},
    "planilla.drivers_guardados_falta_recalcular": {
        "es": "Los drivers ya quedaron guardados. Apretá «Recalcular y empujar al P&L» en Planilla para que se apliquen a todas las posiciones.",
        "en": "The drivers are saved. Press “Recalculate and push to the P&L” under Payroll so they apply to every position."},
    "planilla.filas_sin_puesto": {
        "es": "{n} filas no encontraron su puesto y se ignoraron: {puestos}",
        "en": "{n} rows did not find their position and were ignored: {puestos}"},
    "planilla.plantillas_creadas": {
        "es": "Se crearon las plantillas de posiciones. Llená los salarios desde la pantalla.",
        "en": "Position templates created. Fill in salary amounts via the UI."},
    "planilla.recalcular_despues_del_import": {
        "es": "Recalculá la planilla después del import.",
        "en": "Recalculate payroll after the import."},
    "planilla.recalcular_para_que_apliquen": {
        "es": "Apretá «Recalcular y empujar al P&L» para que se apliquen.",
        "en": "Press “Recalculate and push to the P&L” so they take effect."},
    "planilla.recalcular_para_verlo": {
        "es": "Apretá «Recalcular y empujar al P&L» para verlo en el resultado.",
        "en": "Press “Recalculate and push to the P&L” to see it in the result."},
    "planilla.salarios_sin_recalcular": {
        "es": "Se guardaron los salarios pero NO se recalcularon las fórmulas: el escenario no tiene tipos de cambio cargados. Cargá el TC y corré «Recalcular».",
        "en": "The salaries were saved but the formulas were NOT recalculated: this scenario has no exchange rates loaded. Add the rate and run “Recalculate”."},
    "setup.alinea_revisar": {
        "es": "revisar",
        "en": "review"},
    "setup.alinea_si": {
        "es": "sí",
        "en": "yes"},
    "setup.alinea_sin_dato": {
        "es": "sin dato",
        "en": "no data"},
    "setup.clase_4": {
        "es": "Ingreso",
        "en": "Revenue"},
    "setup.clase_5": {
        "es": "Costo",
        "en": "Cost"},
    "setup.clase_6": {
        "es": "Planilla",
        "en": "Payroll"},
    "setup.clase_7": {
        "es": "Gasto",
        "en": "Expense"},
    "setup.clase_8": {
        "es": "Gasto de la propiedad",
        "en": "Property expense"},
    "setup.clase_9": {
        "es": "Estadística",
        "en": "Statistic"},
    "setup.clase_otra": {
        "es": "Otra",
        "en": "Other"},
    "setup.como_dept_agnostic": {
        "es": "Regla sin departamento",
        "en": "Rule with no department"},
    "setup.como_drop": {
        "es": "Sin regla",
        "en": "Without a rule"},
    "setup.como_exact": {
        "es": "Regla propia",
        "en": "Own rule"},
    "setup.como_fallback": {
        "es": "Por descarte",
        "en": "By fallback"},
    "setup.como_parent": {
        "es": "Heredada del padre",
        "en": "Inherited from the parent"},
    "setup.como_siembra": {
        "es": "Siembra la línea directo",
        "en": "Seeds the line directly"},
    "setup.como_siembra_rota": {
        "es": "Siembra una línea que no existe",
        "en": "Seeds a line that does not exist"},
    "setup.cuenta_no_usada": {
        "es": "la cuenta no se usó",
        "en": "the account was not used"},
    "setup.depto_fuera_catalogo": {
        "es": "Fuera del catálogo",
        "en": "Outside the catalogue"},
    "setup.depto_hijo_funcional": {
        "es": "Hijo funcional",
        "en": "Functional child"},
    "setup.depto_madre": {
        "es": "Madre",
        "en": "Parent"},
    "setup.depto_nivel_propiedad": {
        "es": "Nivel propiedad",
        "en": "Property level"},
    "setup.depto_set_producto": {
        "es": "Set de producto",
        "en": "Product set"},
    "setup.estado_depto_no_estaba": {
        "es": "el depto no estaba",
        "en": "the dept was not there"},
    "setup.estado_no_se_uso": {
        "es": "no se usó",
        "en": "not used"},
    "setup.excel_col_clase": {
        "es": "Clase",
        "en": "Class"},
    "setup.excel_col_codigo": {
        "es": "Código",
        "en": "Code"},
    "setup.excel_col_codigo_linea": {
        "es": "Código de línea",
        "en": "Line code"},
    "setup.excel_col_como": {
        "es": "4. Cómo llegó ahí",
        "en": "4. How it got there"},
    "setup.excel_col_cuenta": {
        "es": "Cuenta",
        "en": "Account"},
    "setup.excel_col_departamento": {
        "es": "2. Departamento",
        "en": "2. Department"},
    "setup.excel_col_departamentos": {
        "es": "Departamentos",
        "en": "Departments"},
    "setup.excel_col_depto_padre": {
        "es": "Depto padre",
        "en": "Parent dept"},
    "setup.excel_col_en_juego": {
        "es": "USD en juego",
        "en": "USD at stake"},
    "setup.excel_col_esta_limpia": {
        "es": "¿Está limpia?",
        "en": "Is it clean?"},
    "setup.excel_col_linea_pl": {
        "es": "Línea del P&L",
        "en": "P&L line"},
    "setup.excel_col_linea_pl_num": {
        "es": "3. Línea del P&L",
        "en": "3. P&L line"},
    "setup.excel_col_nombre": {
        "es": "Nombre",
        "en": "Name"},
    "setup.excel_col_nombre_cuenta": {
        "es": "Nombre de cuenta",
        "en": "Account name"},
    "setup.excel_col_que_es": {
        "es": "1. Qué es",
        "en": "1. What it is"},
    "setup.excel_col_que_es_corto": {
        "es": "Qué es",
        "en": "What it is"},
    "setup.excel_col_regla_de": {
        "es": "Regla tomada de",
        "en": "Rule taken from"},
    "setup.excel_col_se_alinea": {
        "es": "5. ¿Se alinea?",
        "en": "5. Aligned?"},
    "setup.excel_col_seccion": {
        "es": "Sección",
        "en": "Section"},
    "setup.excel_col_tipo_depto": {
        "es": "Tipo de depto",
        "en": "Dept type"},
    "setup.excel_hoja_alineacion": {
        "es": "Alineación entre años",
        "en": "Alignment across years"},
    "setup.excel_hoja_cuentas": {
        "es": "Setup de la cuenta",
        "en": "Account setup"},
    "setup.excel_hoja_leer": {
        "es": "Cómo leer esto",
        "en": "How to read this"},
    "setup.leer_anios": {
        "es": "AÑOS Y ESCENARIOS QUE SE MIRARON (uno por año, el preferido):",
        "en": "YEARS AND SCENARIOS REVIEWED (one per year, the preferred one):"},
    "setup.leer_fuentes": {
        "es": "DE DÓNDE SALE CADA COSA — no hay ni un dato escrito a mano:",
        "en": "WHERE EACH THING COMES FROM — there is not one hand-written figure here:"},
    "setup.leer_fuentes_deptos": {
        "es": "   los departamentos, de department_catalog;",
        "en": "   the departments, from department_catalog;"},
    "setup.leer_fuentes_lineas": {
        "es": "   las líneas, de report_line_config;",
        "en": "   the lines, from report_line_config;"},
    "setup.leer_fuentes_reglas": {
        "es": "   las reglas, de account_mapping (seed_data/mapping_pl.json);",
        "en": "   the rules, from account_mapping (seed_data/mapping_pl.json);"},
    "setup.leer_fuentes_ruteo": {
        "es": "   y el ruteo, del MISMO resolvedor del motor del P&L.",
        "en": "   and the routing, from the SAME resolver the P&L engine uses."},
    "setup.leer_p1": {
        "es": "1. QUÉ ES. Sale de la clase del código de cuenta:",
        "en": "1. WHAT IT IS. It comes from the class of the account code:"},
    "setup.leer_p1_clases": {
        "es": "   4 = Ingreso · 5 = Costo · 6 = Planilla · 7 = Gasto · 8 = Gasto de la propiedad.",
        "en": "   4 = Revenue · 5 = Cost · 6 = Payroll · 7 = Expense · 8 = Property expense."},
    "setup.leer_p2": {
        "es": "2. QUÉ DEPARTAMENTO. Y si es MADRE, HIJO FUNCIONAL o SET DE PRODUCTO.",
        "en": "2. WHICH DEPARTMENT. And whether it is a PARENT, a FUNCTIONAL CHILD or a PRODUCT SET."},
    "setup.leer_p2_hijo": {
        "es": "   El hijo funcional (Front Desk, Housekeeping) no lleva gasto propio: es del padre.",
        "en": "   The functional child (Front Desk, Housekeeping) carries no expense of its own: it is the parent's."},
    "setup.leer_p2_set": {
        "es": "   El set de producto (Villas, Residencias) sí lo lleva.",
        "en": "   The product set (Villas, Residences) does carry it."},
    "setup.leer_p3": {
        "es": "3. EN QUÉ LÍNEA DEL P&L. La línea exacta, no el grupo.",
        "en": "3. WHICH P&L LINE. The exact line, not the group."},
    "setup.leer_p4": {
        "es": "4. CÓMO LLEGÓ AHÍ:",
        "en": "4. HOW IT GOT THERE:"},
    "setup.leer_p4_agnostic": {
        "es": "   Regla sin departamento .... la cuenta no depende del departamento. OK.",
        "en": "   Rule with no department ... the account does not depend on the department. OK."},
    "setup.leer_p4_drop": {
        "es": "   SIN REGLA ................. no llega al P&L. La plata se pierde sin aviso.",
        "en": "   WITHOUT A RULE ............ it never reaches the P&L. The money is lost with no warning."},
    "setup.leer_p4_exact": {
        "es": "   Regla propia .............. hay una regla para ese departamento y esa cuenta. OK.",
        "en": "   Own rule .................. there is a rule for that department and that account. OK."},
    "setup.leer_p4_fallback_1": {
        "es": "   POR DESCARTE .............. se tomó una regla de OTRO departamento porque no",
        "en": "   BY FALLBACK ............... a rule from ANOTHER department was taken because there"},
    "setup.leer_p4_fallback_2": {
        "es": "                               había ninguna que aplicara. Hay que arreglarlo:",
        "en": "                               was none that applied. This has to be fixed:"},
    "setup.leer_p4_fallback_3": {
        "es": "                               la plata aterriza en la línea de otro departamento.",
        "en": "                               the money lands on another department's line."},
    "setup.leer_p4_parent": {
        "es": "   Heredada del padre ........ la regla es del departamento padre. OK, es el diseño.",
        "en": "   Inherited from parent ..... the rule is the parent department's. OK, that is the design."},
    "setup.leer_p5": {
        "es": "5. ¿SE ALINEA ENTRE AÑOS? La misma cuenta, ¿cae en la misma línea todos los años?",
        "en": "5. IS IT ALIGNED ACROSS YEARS? Does the same account land on the same line every year?"},
    "setup.leer_p5_b": {
        "es": "   Se compara solo entre años en los que la cuenta tiene plata. Una cuenta que",
        "en": "   Only years in which the account has money are compared. An account that shows up"},
    "setup.leer_p5_c": {
        "es": "   aparece en un año solo no está desalineada: todavía no tiene con qué compararse.",
        "en": "   in a single year is not misaligned: it has nothing to be compared against yet."},
    "setup.leer_p5_d": {
        "es": "   Un par (departamento, cuenta) nunca cambia de línea; lo que cambia es bajo qué",
        "en": "   A (department, account) pair never changes line; what changes is which department"},
    "setup.leer_p5_e": {
        "es": "   departamento se contabiliza la cuenta. Por eso la comparación es por CUENTA.",
        "en": "   the account is booked under. That is why the comparison is by ACCOUNT."},
    "setup.leer_resumen": {
        "es": "RESUMEN:",
        "en": "SUMMARY:"},
    "setup.leer_resumen_a_revisar": {
        "es": "   a revisar ...................... {n}",
        "en": "   to review ......................... {n}"},
    "setup.leer_resumen_cuentas": {
        "es": "   cuentas distintas .............. {n}",
        "en": "   distinct accounts ................. {n}"},
    "setup.leer_resumen_desalineadas": {
        "es": "   cuentas desalineadas ........... {n}",
        "en": "   misaligned accounts ............... {n}"},
    "setup.leer_resumen_filas": {
        "es": "   filas (departamento × cuenta) ... {n}",
        "en": "   rows (department × account) ....... {n}"},
    "setup.leer_resumen_limpias": {
        "es": "   limpias ........................ {n}",
        "en": "   clean ............................. {n}"},
    "setup.leer_resumen_por_descarte": {
        "es": "   por descarte ................... {n}",
        "en": "   by fallback ....................... {n}"},
    "setup.leer_resumen_sin_regla": {
        "es": "   sin regla ...................... {n}",
        "en": "   without a rule .................... {n}"},
    "setup.leer_titulo": {
        "es": "EL SETUP DE LA CUENTA — las cinco preguntas",
        "en": "THE ACCOUNT SETUP — the five questions"},
    "setup.limpia_no": {
        "es": "NO",
        "en": "NO"},
    "setup.limpia_si": {
        "es": "sí",
        "en": "yes"},
    "setup.sin_departamento": {
        "es": "(sin departamento)",
        "en": "(no department)"},
    "setup.todo_alineado": {
        "es": "Ninguna cuenta cae en líneas distintas según el año.",
        "en": "No account lands on different lines depending on the year."},
}


def t(locale: str | None, clave: str, **params) -> str:
    """El texto en el idioma pedido. Una clave que no exista devuelve la clave:
    un aviso no puede convertirse en un 500."""
    fila = TEXTOS.get(clave)
    if not fila:
        return clave
    plantilla = fila.get(normalize_locale(locale) or DEFAULT_LOCALE) or fila[DEFAULT_LOCALE]
    try:
        return plantilla.format(**params) if params else plantilla
    except (KeyError, IndexError):
        return plantilla


def idioma_de(request: Request) -> str:
    """El idioma de la petición, para inyectar en un endpoint.

    Sale de `Accept-Language`, que `lib/api.ts` pone en cada llamada. La cookie
    no sirve: el backend vive en otro dominio que el frontend.
    """
    # ⚠️ `?lang=` primero: las descargas van por `<a href>` y un href NO manda
    # cabeceras. Sin esto el Excel sale en el idioma del navegador y no en el
    # que el usuario eligió. Lo pone `dlUrl()` en `lib/api.ts`.
    return (normalize_locale(request.query_params.get("lang"))
            or normalize_locale(request.headers.get("accept-language"))
            or DEFAULT_LOCALE)


#: Para las firmas: `idioma: str = Idioma`.
Idioma = Depends(idioma_de)
