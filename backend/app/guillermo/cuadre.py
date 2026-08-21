# -*- coding: utf-8 -*-
"""Todo auxiliar tiene que amarrar con el GL — D-8 del owner (2026-08-20).

Textual: «todos los auxiliares deben amarrar con el GL, en todos los tabs, y
las estadísticas. Así que ésa es una revisión constante: cada despliegue
siempre debe cuadrar.»

⚠️ **No se inventa un cuadre nuevo.** El motor ya decide qué fuente manda
comparando el **Detalle (GL)** contra el **Resumen (P&L)** sobre siete totales
de control (`recalculate.veredicto_del_detalle`), con tolerancia y evidencia, y
respetando los meses propios de cada escenario. Esto lo corre sobre TODOS los
escenarios y junta el resultado — que es lo que faltaba.

⚠️ **TRES estados, no dos.** Un escenario sin detalle del mayor **no cuadra: no
se puede verificar**, y pintarlo verde sería el peor de los resultados posibles
— catorce presupuestos saldrían «al día» sin que nadie haya comparado nada.
Medido el 2026-08-20: de 20 escenarios, 3 descuadran, 3 cuadran de verdad y
**14 no se pueden verificar**.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario

# Diferencias YA CONOCIDAS y explicadas, con su motivo. No se esconden: se
# marcan, para que una diferencia NUEVA no se pierda entre las viejas.
#
# ⚠️ La tolerancia es por escenario y por total, no global: subir una tolerancia
# global para tapar un caso conocido dejaría pasar los que todavía no aparecen.
CONOCIDAS = {
    ("ACTUAL", 2024, "actual"): (
        "Filas sin número de cuenta que el importador se tragaba ($40.613) y la "
        "cuenta 8090 que no llega al P&L (−$43.698). Documentado."),
    ("FORECAST", 2026, "April"): (
        "La provisión de impuesto vino dentro del archivo subido y el motor no "
        "la reemplaza ($17.881,10). Decisión del owner: lo subido no se toca."),
}


@dataclass
class CuadreEscenario:
    escenario: str
    estado: str            # cuadra | no_cuadra | sin_verificar
    manda: str
    motivo: str
    meses_evaluados: list[int] = field(default_factory=list)
    diferencias: list[dict] = field(default_factory=list)
    conocida: str = ""
    # ⚠️ **En qué MES vive el descuadre.** Sin esto el aviso dice «descuadra en
    # 7 totales por $199.667,97» y hay que abrir una sesión con alguien para
    # saber dónde mirar. Medido en ACTUAL 2026: el descuadre entero era JUNIO —
    # sacándolo, los siete totales cuadran al centavo. Un número sin el mes no
    # es accionable; con el mes, la acción es «subí el resumen de junio».
    meses_culpables: list[int] = field(default_factory=list)
    en_el_detalle_no_en_el_resumen: list[int] = field(default_factory=list)

    @property
    def peor_diferencia(self) -> float:
        return max((abs(d["diferencia"]) for d in self.diferencias), default=0.0)


async def _donde_vive_el_descuadre(db: AsyncSession, sc,
                                   meses: list[int]) -> tuple[list[int], list[int]]:
    """Qué meses tienen dato en el DETALLE y no en el RESUMEN, o al revés.

    ⚠️ Es la pregunta que convierte un número en una acción. «Descuadra
    $199.667,97» manda a abrir una investigación; «junio está en el mayor y no
    en el resumen» manda a subir un archivo.

    ⚠️ Se compara **por VALOR, no por presencia** — reusando
    `meses_con_dato_por_fuente`. La primera versión miraba si había filas, y el
    detalle guarda los doce meses en COLUMNAS: «tiene filas» es cierto para
    todos aunque valgan cero. Acusaba a julio, agosto y hasta diciembre de
    faltar, y habría mandado a subir resúmenes de meses sin actividad.

    Si algún día el descuadre viviera dentro de un mes presente en las dos
    hojas, esto devuelve vacío — y `que_hacer` dice que no se explica por un
    mes que falte, en vez de inventar una causa que no midió.
    """
    from app.engine.meses_cerrados import meses_con_dato_por_fuente

    try:
        resumen, detalle = await meses_con_dato_por_fuente(db, sc.id)
    except Exception:
        return ([], [])

    en_juego = set(meses)
    solo_detalle = sorted((detalle - resumen) & en_juego)
    solo_resumen = sorted((resumen - detalle) & en_juego)
    return (sorted(solo_detalle + solo_resumen), solo_detalle)


async def cuadre_de_todos(db: AsyncSession) -> list[CuadreEscenario]:
    """Corre el veredicto sobre cada escenario y clasifica el resultado."""
    from app.engine.recalculate import veredicto_del_detalle

    fuera: list[CuadreEscenario] = []
    scs = (await db.execute(select(Scenario))).scalars().all()
    for sc in sorted(scs, key=lambda z: (z.type, z.year, z.version)):
        v = await veredicto_del_detalle(db, sc)
        nombre = f"{sc.type}/{sc.year}/{sc.version}"
        difs = v.get("diferencias") or []
        sin_detalle = not (v.get("meses_con_detalle") or [])

        if difs:
            estado = "no_cuadra"
        elif sin_detalle:
            # ⚠️ NO es «cuadra». Nadie comparó nada.
            estado = "sin_verificar"
        else:
            estado = "cuadra"

        culpables: list[int] = []
        solo_detalle: list[int] = []
        if estado == "no_cuadra":
            culpables, solo_detalle = await _donde_vive_el_descuadre(
                db, sc, v.get("meses_evaluados") or [])

        fuera.append(CuadreEscenario(
            escenario=nombre, estado=estado, manda=v.get("manda", ""),
            motivo=v.get("motivo", ""),
            meses_evaluados=v.get("meses_evaluados") or [],
            diferencias=difs,
            conocida=CONOCIDAS.get((sc.type, sc.year, sc.version), ""),
            meses_culpables=culpables,
            en_el_detalle_no_en_el_resumen=solo_detalle,
        ))
    return fuera


MES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
       "agosto", "setiembre", "octubre", "noviembre", "diciembre"]


def que_hacer(c: CuadreEscenario) -> str:
    """La acción concreta, cuando se puede nombrar. Si no, se dice que no.

    ⚠️ Inventar una acción para un descuadre cuya causa no se midió es peor que
    no dar ninguna: manda a alguien a arreglar lo que no está roto.
    """
    if c.estado != "no_cuadra":
        return ""
    if c.en_el_detalle_no_en_el_resumen:
        cuales = ", ".join(MES[m] for m in c.en_el_detalle_no_en_el_resumen)
        return (f"Subí el RESUMEN de {cuales}: el detalle del mayor ya está "
                f"cargado y su otra mitad no.")
    if c.meses_culpables:
        cuales = ", ".join(MES[m] for m in c.meses_culpables)
        return f"El descuadre vive en {cuales}: falta el detalle del mayor."
    return ("El descuadre no se explica por un mes que falte: hay que mirarlo "
            "línea por línea en el tab del cuadre.")


def resumen(filas: list[CuadreEscenario]) -> dict:
    """El titular. ⚠️ `todo_cuadra` exige que NO haya descuadres **ni**
    escenarios sin verificar: «no pude mirar» no es «está bien»."""
    nuevos = [f for f in filas if f.estado == "no_cuadra" and not f.conocida]
    conocidos = [f for f in filas if f.estado == "no_cuadra" and f.conocida]
    sin_ver = [f for f in filas if f.estado == "sin_verificar"]
    return {
        "total": len(filas),
        "cuadran": sum(1 for f in filas if f.estado == "cuadra"),
        "no_cuadran": len(nuevos) + len(conocidos),
        "descuadres_nuevos": len(nuevos),
        "descuadres_conocidos": len(conocidos),
        "sin_verificar": len(sin_ver),
        # Lo que decide si el despliegue «cuadra». Un descuadre conocido y
        # documentado no frena; uno nuevo sí.
        "todo_cuadra": not nuevos,
        "hay_ciegos": bool(sin_ver),
    }
