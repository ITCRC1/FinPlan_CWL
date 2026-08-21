# -*- coding: utf-8 -*-
"""¿Qué falta subir? — la primera pregunta que Guillermo contesta de verdad.

D-1 del owner (2026-08-20): los XML de Operations y Marketing van todos los
días; los actuales del GL y el Balance Sheet, una vez al mes.

⚠️ **Dos verificaciones distintas, y hay que saber cuál se está mirando:**

* **`cobertura`** — hasta qué período hay dato en la tabla de destino. Funciona
  **hacia atrás**: contesta hoy sobre lo que pasó antes de que Guillermo
  existiera. Es lo correcto para los mensuales, donde lo que importa es si el
  mes cerrado ya entró.

* **`ultima_subida`** — mira `import_files`. Es lo correcto para un XML diario:
  el de reservas mira al FUTURO, así que «hasta qué mes hay dato» no dice nada
  sobre si se subió hoy. ⚠️ Pero el registro arrancó el **2026-08-20**, así que
  **no puede hablar de antes de esa fecha** — y lo dice, en vez de dar por malo
  lo que no puede ver.

⚠️ **Un mensual no está atrasado el día 2.** Cada reporte trae sus días de
gracia; el del GL se cierra alrededor del día 10. Reclamar antes de eso es
ruido, y el ruido apaga la alerta.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guillermo import ExpectedReport
from app.models.import_registro import ImportBatch, ImportFile

# Cuándo arrancó el registro de archivos. Antes de esta fecha no hay historial
# de subidas y decirlo es parte de la respuesta.
DESDE_QUE_HAY_REGISTRO = date(2026, 8, 20)

# Cómo se mide la cobertura de cada tabla. Vive acá y no en la base porque es
# una consulta, no una configuración: cambiarla es cambiar código.
# Tablas que registran CUÁNDO se las actualizó. Es la mejor fuente para un
# reporte diario: contesta «¿se subió hoy?» y además funciona HACIA ATRÁS, sin
# esperar a que el registro de archivos junte historial.
#
# ⚠️ `channel_mix_entries` tiene la columna pero **vacía** (medido 2026-08-20):
# por eso el chequeo cae a cobertura en vez de tratar el NULL como «nunca».
ACTUALIZACION = {
    "country_mix_entries": "actualizado_en",
    "channel_mix_entries": "actualizado_en",
}

COBERTURA = {
    # Los actuales del GL: el último mes del escenario ACTUAL del año.
    "actual_pl_lines": (
        "SELECT max(a.month) FROM actual_pl_lines a "
        "JOIN scenarios s ON s.id = a.scenario_id "
        "WHERE s.type = 'ACTUAL' AND s.year = :anio"),
    "balance_sheet_lines": (
        "SELECT max(month) FROM balance_sheet_lines WHERE year = :anio"),
    "country_mix_entries": (
        "SELECT max(month) FROM country_mix_entries"),
    "channel_mix_entries": (
        "SELECT max(month) FROM channel_mix_entries"),
}


@dataclass
class Faltante:
    report_id: str
    etiqueta: str
    frecuencia: str
    como_se_mide: str
    al_dia: bool
    # Qué se sabe. `None` = no se puede saber, que NO es lo mismo que «falta».
    ultimo: str | None
    faltan: list[str]
    mensaje: str


def _meses_a_reclamar(ultimo_mes: int | None, hoy: date,
                      gracia_dias: int) -> list[int]:
    """Los meses cerrados que deberían estar y no están.

    ⚠️ El mes en curso NO se reclama: todavía no cerró. Y el anterior sólo se
    reclama pasados los días de gracia — un GL que se cierra el 10 no está
    atrasado el 2.
    """
    ultimo_exigible = hoy.month - 1
    if hoy.day <= gracia_dias:
        ultimo_exigible -= 1
    if ultimo_exigible < 1:
        return []
    desde = (ultimo_mes or 0) + 1
    return list(range(desde, ultimo_exigible + 1))


async def _por_cobertura(db: AsyncSession, r: ExpectedReport,
                         hoy: date) -> Faltante:
    consulta = COBERTURA.get(r.objetivo)
    if consulta is None:
        return Faltante(r.report_id, r.notas or r.report_id, r.frecuencia,
                        "cobertura", False, None, [],
                        f"no sé cómo verificar «{r.objetivo}»")

    ultimo = (await db.execute(text(consulta), {"anio": hoy.year})).scalar()
    ultimo = int(ultimo) if ultimo else None
    faltan = _meses_a_reclamar(ultimo, hoy, r.gracia_dias)
    MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "setiembre", "octubre", "noviembre", "diciembre"]

    if not faltan:
        return Faltante(
            r.report_id, r.notas or r.report_id, r.frecuencia, "cobertura",
            True, MES[ultimo] if ultimo else None, [],
            f"al día — último: {MES[ultimo] if ultimo else 'sin dato'}")
    return Faltante(
        r.report_id, r.notas or r.report_id, r.frecuencia, "cobertura",
        False, MES[ultimo] if ultimo else None, [MES[m] for m in faltan],
        f"falta {', '.join(MES[m] for m in faltan)} — "
        f"el último con dato es {MES[ultimo] if ultimo else 'ninguno'}")


async def _por_ultima_subida(db: AsyncSession, r: ExpectedReport,
                             hoy: date) -> Faltante:
    ultima = (await db.execute(
        select(func.max(ImportFile.creado_en))
        .join(ImportBatch, ImportBatch.id == ImportFile.batch_id)
        .where(ImportBatch.hotel_id == r.hotel_id,
               ImportBatch.endpoint.contains(r.objetivo))
    )).scalar()

    etiqueta = r.notas or r.report_id
    if ultima is None:
        # ⚠️ «No hay registro» NO es «no se subió»: el registro arrancó el
        # 2026-08-20. Decir «falta» sobre algo que no se puede ver sería
        # inventar un atraso.
        return Faltante(
            r.report_id, etiqueta, r.frecuencia, "última subida", False, None,
            [],
            f"sin registro de subidas — el historial arranca el "
            f"{DESDE_QUE_HAY_REGISTRO:%d/%m/%Y}, así que de antes no se sabe")

    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    dias = (datetime.now(timezone.utc) - ultima).days
    al_dia = dias <= max(r.gracia_dias, 1)
    return Faltante(
        r.report_id, etiqueta, r.frecuencia, "última subida", al_dia,
        f"{ultima:%d/%m/%Y}", [] if al_dia else [f"{dias} días"],
        f"al día — subido {ultima:%d/%m}" if al_dia
        else f"hace {dias} días que no se sube (se espera todos los días)")


async def _por_actualizacion(db: AsyncSession, r: ExpectedReport,
                            hoy: date) -> Faltante:
    """Cuándo se actualizó por última vez la tabla de destino.

    ⚠️ Si la columna está vacía **cae a cobertura**, no da «nunca». Un NULL
    dice «no se registró», no «no se subió» — y tratar lo uno como lo otro
    inventaría un atraso.
    """
    col = ACTUALIZACION.get(r.objetivo)
    etiqueta = r.notas or r.report_id
    ultima = None
    if col:
        ultima = (await db.execute(
            text(f"SELECT max({col}) FROM {r.objetivo}"))).scalar()

    if ultima is None:
        f = await _por_cobertura(db, r, hoy)
        f.como_se_mide = "cobertura (sin fecha de actualización)"
        return f

    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    dias = (datetime.now(timezone.utc) - ultima).days
    al_dia = dias <= max(r.gracia_dias, 1)
    return Faltante(
        r.report_id, etiqueta, r.frecuencia, "fecha de actualización",
        al_dia, f"{ultima:%d/%m/%Y}", [] if al_dia else [f"{dias} días"],
        f"al día — actualizado {ultima:%d/%m}" if al_dia
        else f"hace {dias} días que no se actualiza "
             f"(último {ultima:%d/%m}, se espera todos los días)")


async def que_falta(db: AsyncSession, hotel_id: str,
                    hoy: date | None = None) -> list[Faltante]:
    """Recorre el manifiesto y contesta, reporte por reporte."""
    hoy = hoy or datetime.now(timezone.utc).date()
    filas = (await db.execute(
        select(ExpectedReport).where(ExpectedReport.hotel_id == hotel_id,
                                     ExpectedReport.activo.is_(True))
    )).scalars().all()

    fuera: list[Faltante] = []
    for r in sorted(filas, key=lambda x: (x.frecuencia, x.report_id)):
        if r.verifica == "cobertura":
            fuera.append(await _por_cobertura(db, r, hoy))
        elif r.verifica == "actualizado":
            fuera.append(await _por_actualizacion(db, r, hoy))
        elif r.verifica == "ultima_subida":
            fuera.append(await _por_ultima_subida(db, r, hoy))
        else:
            fuera.append(Faltante(
                r.report_id, r.notas or r.report_id, r.frecuencia, "—",
                False, None, [], "no tiene forma de verificación configurada"))
    return fuera
