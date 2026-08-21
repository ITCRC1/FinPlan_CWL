# -*- coding: utf-8 -*-
"""Semilla de la configuración de Guillermo (`docs/GUILLERMO.md` §8).

**Nada hardcoded.** Cada parámetro nace con el default del spec y se edita en
la app. Idempotente: no pisa lo que el owner cambie.

⚠️ **`guillermo_expected_reports` NO se siembra**, y es a propósito. Su
contenido es la decisión D-1 —qué reportes se esperan, en qué formato, cuáles
obligatorios— y **no se inventa**: un manifiesto inventado haría que Guillermo
reclamara archivos que nadie prometió, y diera por completo lo que no lo está.
Mientras esté vacío, la validación de nivel 1 responde «no puedo opinar» en vez
de verde.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hotel_actual import HOTEL_ID
from app.models.guillermo import GuillermoConfig

# (clave, valor, descripción). El default de `autonomy_level` es `shadow`:
# Guillermo nace sin permiso de escribir, y pasar a `assisted` es una decisión
# humana — ver §4 y el hueco D-9 (contra qué se mide la tasa de acierto).
PARAMETROS = [
    ("autonomy_level", "shadow",
     "shadow = procesa y no escribe · assisted = importa lo que matchea una regla aprobada"),
    ("shadow_accuracy_threshold", "0.95",
     "Acierto mínimo para habilitar el nivel asistido (⚠️ falta definir contra qué se mide — D-9)"),
    # ⚠️ El comparable es el MISMO MES DEL AÑO ANTERIOR, no el mes previo: en
    # Corcovado setiembre corre al 9,1% y febrero al 81,4%, así que mes contra
    # mes la alerta saltaría siempre y se volvería ruido.
    ("variance_alert_pct", "10",
     "Variación contra el mismo mes del año anterior que dispara revisión"),
    ("file_stability_seconds", "30",
     "Espera de tamaño estable antes de leer, contra el archivo a medio escribir"),
    ("heartbeat_max_hours", "26",
     "Sin latido en este plazo: rojo. Es lo que hace que el silencio signifique «todo bien»"),
    ("daily_run_at", "06:00", "Hora de la ronda diaria"),
    ("cat_enabled", "true", "Mostrar a Guillermo en la pantalla"),
    ("cat_intro_on_login", "true", "Secuencia de entrada la primera vez de la sesión"),
    ("duplicate_policy", "ask", "ignore · replace · ask (default: preguntar)"),
    ("report_timezone", "America/Costa_Rica",
     "El período de un reporte sale de su fecha interna leída en esta zona, nunca de la hora de llegada"),
    # ⚠️ Nace VACÍO a propósito: es la decisión D-5 y es de cada propiedad.
    # Sin destinatarios el dead-man switch sólo grita adentro de la pantalla.
    ("notify_emails", "",
     "A quién avisarle, separados por coma. Vacío = Guillermo no manda correo (decisión D-5)"),
    ("weekly_summary_day", "monday",
     "Qué día sale el resumen semanal. Va aunque no haya nada: es el único aviso cuya ausencia significa algo"),
    ("ultimo_resumen_semanal", "",
     "Lo escribe el cron: la semana del último resumen enviado. No se edita a mano"),
    ("ultimo_aviso_latido", "",
     "Lo escribe el cron: el día en que avisó que no había latido. No se edita a mano"),
]


async def seed_guillermo(db: AsyncSession) -> dict:
    """Idempotente. No pisa lo que el owner edite en la app."""
    ya = {
        c.clave for c in (await db.execute(
            select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    nuevos = 0
    for clave, valor, desc in PARAMETROS:
        if clave in ya:
            continue
        db.add(GuillermoConfig(hotel_id=HOTEL_ID, clave=clave, valor=valor,
                               descripcion=desc))
        nuevos += 1
    return {"total": len(PARAMETROS), "nuevos": nuevos}


# ── El manifiesto: qué se espera (D-1, definido por el owner 2026-08-20) ─────
#
# Textual: «hay unos XML en el tab de Operations y Marketing que deben subirse
# todos los días · el upload de los actuales 1 vez al mes · el balance sheet».
#
# ⚠️ Esto SÍ se siembra, a diferencia de antes, porque **ahora hay decisión**.
# Lo que no se inventa es lo que el owner no dijo: no hay reportes de más acá
# adentro.
#
# ⚠️ **El manifiesto es POR PROPIEDAD, y por eso está indexado por hotel.**
# Owner, 2026-08-20: «cada propiedad decide cómo manejar a Guillermo».
#
# Antes esta lista se sembraba en CUALQUIER instalación. Al clonar para Amarena,
# Guillermo habría arrancado reclamando **cinco reportes que nadie de Amarena
# prometió** —exactamente el manifiesto inventado que este archivo dice que no
# se hace— y, peor, `estado_visible` usa `configurado = esperados > 0`: con el
# manifiesto puesto, una instalación recién nacida **sale en ROJO** en vez del
# gris que existe justamente para «todavía no arrancó y falta decidir D-1».
#
# El patrón es el mismo que ya usa `seed.py:91` con los tipos de habitación:
# el dato de CWL no se estampa sobre una propiedad nueva.
#
# (report_id, etiqueta, frecuencia, verifica, objetivo, gracia_dias, obligatorio)
MANIFIESTO_CWL = [
    # Mensuales — se verifican por COBERTURA, o sea hacia atrás. Medido el
    # 2026-08-20: los dos tienen dato hasta MAYO, así que faltan junio y julio.
    ("actuales_gl", "Actuales del GL", "monthly", "cobertura",
     "actual_pl_lines", 10, True),
    ("balance_sheet", "Balance Sheet", "monthly", "cobertura",
     "balance_sheet_lines", 10, True),

    # Diarios — se verifican por ÚLTIMA SUBIDA. ⚠️ El registro de archivos
    # arrancó el 2026-08-20: antes de esa fecha no hay historial, y el chequeo
    # lo dice en vez de dar por bueno lo que no puede ver.
    ("otb_xml", "On the Books (Operations)", "daily", "ultima_subida",
     "import-otb-xml", 1, True),
    # ⚠️ Estos dos SÍ guardan cuándo se los actualizó, así que se miden por esa
    # fecha y la respuesta vale hacia atrás. `channel_mix` tiene la columna
    # vacía y por eso cae solo a cobertura — el chequeo lo dice.
    ("country_xml", "Country Mix (Marketing)", "daily", "actualizado",
     "country_mix_entries", 1, True),
    ("channel_xml", "Channel Mix (Marketing)", "daily", "actualizado",
     "channel_mix_entries", 1, True),
]


# Un manifiesto por propiedad. El día que Amarena decida el suyo, entra acá o
# —mejor— se carga desde `Admin → Guillermo`, que es donde su owner lo decide.
MANIFIESTOS: dict[str, list] = {"CWL": MANIFIESTO_CWL}

# Compatibilidad: había código y pruebas que leían `MANIFIESTO` a secas.
MANIFIESTO = MANIFIESTO_CWL


async def seed_manifiesto(db: AsyncSession) -> dict:
    """Idempotente. No pisa lo que el owner edite en la pantalla.

    ⚠️ **Una propiedad sin manifiesto propio nace con el manifiesto VACÍO**, y
    eso no es un olvido: es la decisión D-1, que es de su owner. Mientras esté
    vacío el semáforo dice «todavía no arrancó: falta definir qué reportes
    espera», que es la verdad — y no reclama nada que nadie prometió.
    """
    from app.models.guillermo import ExpectedReport

    manifiesto = MANIFIESTOS.get(HOTEL_ID, [])
    if not manifiesto:
        print(f"  {HOTEL_ID}: sin manifiesto propio — se carga en "
              f"Admin → Guillermo (decisión D-1 de esta propiedad)")
        return {"total": 0, "nuevos": 0}

    ya = {
        r.report_id for r in (await db.execute(
            select(ExpectedReport).where(ExpectedReport.hotel_id == HOTEL_ID)
        )).scalars().all()
    }
    nuevos = 0
    for rid, etiqueta, frec, verifica, objetivo, gracia, oblig in manifiesto:
        if rid in ya:
            continue
        db.add(ExpectedReport(
            hotel_id=HOTEL_ID, report_id=rid, patron="", formato="",
            frecuencia=frec, obligatorio=oblig, activo=True, notas=etiqueta,
            verifica=verifica, objetivo=objetivo, gracia_dias=gracia,
        ))
        nuevos += 1
    return {"total": len(MANIFIESTO), "nuevos": nuevos}
