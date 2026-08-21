"""
Siembra el motor de mapeo del P&L: `report_line_config` + `account_mapping`.

POR QUÉ EXISTE
Estas 899 filas son las que traducen el catálogo contable a las líneas del P&L
USALI. Sin ellas el motor corre y devuelve todo en cero: no es una tabla de
adorno, es el corazón del cálculo. Vivían SOLO en la base de Corcovado, así que
una instalación nueva —cada hotel va a ser un proyecto aparte— nacía muerta y
había que copiarle la base al anterior. Ahora viven en git.

No dependen del hotel: son el estándar USALI, iguales para Corcovado, Amarena,
Oxígen y Ojochal. Por eso no llevan `hotel_id`.

IDEMPOTENTE Y NO DESTRUCTIVO
Inserta lo que falta y actualiza lo que cambió; NO borra lo que sobra. Un hotel
puede haber agregado mapeos propios y el seed corre en cada arranque: borrar por
ausencia le vaciaría el P&L a alguien en un redeploy. Lo que sobra se reporta
para que se mire, no se toca.
"""
import json
import pathlib
import uuid

from sqlalchemy import UniqueConstraint, select
from app.models.mapping import ReportLineConfig, AccountMapping

ARCHIVO = pathlib.Path(__file__).parent / "seed_data" / "mapping_pl.json"

# ⚠️ La clave se DERIVA de la restricción de la tabla, no se escribe acá.
#
# Hasta el 2026-08-20 estaban escritas a mano, y decían ser «las mismas de las
# restricciones» sin serlo: a `uq_account_mapping` se le agregó `vigente_desde`
# —la vigencia que D9 necesitó para mover la 7120— y esta clave se quedó con
# cuatro columnas. Resultado: las dos reglas de la 7120 (hasta jun-2026 en A&G,
# desde jul-2026 en Credit Card Commissions) se veían como UNA, el seed
# intentaba insertar la segunda, y **la siembra del mapeo se caía entera en cada
# despliegue** con un `IntegrityError` que el `try/except` convertía en una
# línea de log. Todo el lote se revertía con ella.
#
# Derivada, la clave no puede volver a separarse de la restricción.
def _columnas_unicas(modelo) -> tuple[str, ...]:
    for c in modelo.__table__.constraints:
        if isinstance(c, UniqueConstraint):
            return tuple(col.name for col in c.columns)
    raise RuntimeError(f"{modelo.__name__} no tiene restricción única: sin ella "
                       f"el seed no puede saber qué fila es cuál")


def _clave(modelo):
    cols = _columnas_unicas(modelo)

    def clave(r) -> tuple:
        # `None` y `""` son lo mismo acá: el archivo omite la columna y la base
        # guarda NULL. Tratarlos distinto haría que cada fila sin vigencia se
        # viera como nueva en cada arranque.
        return tuple((r.get(c) if isinstance(r, dict) else getattr(r, c, None)) or None
                     for c in cols)
    return clave


_clave_linea = _clave(ReportLineConfig)
_clave_mapeo = _clave(AccountMapping)


def _campos(obj) -> dict:
    """Columnas del modelo salvo el id, que es por instalación."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns if c.name != "id"}


async def _sembrar(session, modelo, filas: list[dict], clave, nombre: str) -> None:
    existentes = {clave(_campos(o)): o for o in (await session.execute(select(modelo))).scalars().all()}
    nuevos = cambiados = 0
    for fila in filas:
        actual = existentes.pop(clave(fila), None)
        if actual is None:
            session.add(modelo(id=str(uuid.uuid4()), **fila))
            nuevos += 1
            continue
        difs = [k for k, v in fila.items() if getattr(actual, k) != v]
        if difs:
            for k in difs:
                setattr(actual, k, fila[k])
            cambiados += 1
    sobran = len(existentes)
    print(f"  {nombre}: +{nuevos} nuevos, {cambiados} actualizados, {len(filas)} en el archivo"
          + (f" · {sobran} en la base que NO están en el archivo (no se tocan)" if sobran else ""))


async def seed_mapping(session) -> None:
    if not ARCHIVO.exists():
        print(f"  seed de mapeo omitido: falta {ARCHIVO.name}")
        return
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    await _sembrar(session, ReportLineConfig, datos["report_line_config"], _clave_linea,
                   "report_line_config")
    await _sembrar(session, AccountMapping, datos["account_mapping"], _clave_mapeo,
                   "account_mapping")
    await session.commit()
