# -*- coding: utf-8 -*-
"""El cero de adelante del código de departamento, en UN solo lugar.

Owner, 2026-09-03: *«el upload tiene mismos departamentos sin 0»* y, enseguida,
*«si algo entra como 110 el sistema reconoce también que es 0110»*.

## Por qué en el ORM y no en el importador

Porque el importador **no es la única puerta**. Medido: hay al menos cuatro
caminos que escriben un `dept_code` sin pasar por `dept_code_from_name`:

* `POST /actuals/` — `ActualRow.dept_code` es un campo del cuerpo, tal cual
  llega del cliente;
* `importers/actual_workbook_loader` — su propio lector de libro;
* `origenes/aterrizaje` — el aterrizaje de un origen;
* `api/scenarios_api` — las rutas de carga y de copia.

Parchear los cuatro es exactamente cómo se pierde el quinto. El ORM los ve a
todos a la vez, los de hoy y los que se agreguen mañana — el mismo argumento por
el que `candado_meses` vive acá y no en los 109 endpoints de escritura.

## Por qué esto no es «arreglar datos malos en silencio»

`110` no es ambiguo: **no existe** ningún departamento `110`, y sí existe el
`0110`. Lo que se corrige es la escritura del mismo código, no su significado.

⚠️ Lo que pasaba sin esto es peor que un dato mal escrito:

    pl_engine.group_for_dept("0110") -> ROOMS
    pl_engine.group_for_dept("110")  -> OTHER_OVERHEAD

El gasto de Habitaciones salía como Overhead, **el P&L cuadraba igual** —la
plata seguía estando, en la línea de al lado— y nada avisaba.

## Cuáles son de tres dígitos de verdad

Los pregunta al **catálogo**, que es una tabla y se edita sin desplegar: hoy son
el Club Madresal (260), el Área Recreativa (270) y Misceláneos (280).

⚠️ Sin mirar el catálogo, un departamento de tres dígitos creado mañana se
rellenaría a cuatro y dejaría de existir el día que alguien lo cargue.
"""
from __future__ import annotations

from sqlalchemy import event, inspect as sa_inspect

from app.db import SesionFinPlan

#: Los de tres dígitos que ya existen, cacheados por proceso. Se llena solo la
#: primera vez que se lee el catálogo y se usa como respaldo cuando el listener
#: corre sin poder consultar (ver `_tres_digitos`).
_CACHE: set[str] = set()


def recordar_tres_digitos(codigos) -> None:
    """Guarda los códigos de tres dígitos que trae el catálogo."""
    _CACHE.update(c for c in codigos if c and len(str(c).strip()) == 3)


def _tres_digitos() -> frozenset[str]:
    """Los departamentos que de verdad son de tres dígitos.

    Prefiere lo que se haya leído del catálogo; si nadie lo leyó todavía, cae a
    las dos tablas del código.

    ⚠️ El respaldo hace falta: este normalizador corre dentro de un `flush`, y
    ahí no se puede lanzar otra consulta sin reentrar en la sesión.
    """
    if _CACHE:
        return frozenset(_CACHE)
    from app.engine.pl_engine import _DEPT_TO_GROUP
    from app.importers.gl_detail_importer import _POR_PALABRA
    return (frozenset(c for _kw, c in _POR_PALABRA if len(c) == 3)
            | frozenset(d for d in _DEPT_TO_GROUP if len(d) == 3))


def normalizar_dept_code(code):
    """Deja el código como el catálogo lo escribe. Las DOS direcciones:

        "110"  -> "0110"   le falta el cero
        "0260" -> "260"    le sobra el cero
        "260"  -> "260"    ya está bien
        "0110" -> "0110"   ya está bien

    ⚠️ **La segunda dirección no es simetría por prolijidad: es un error real
    que ya estaba en el código.** `codificacion_importer._pad4` hacía
    `zfill(4)` sin condición, así que el Club Madresal —`260`— entraba como
    `0260`, un departamento que no existe. Y el Club es el más grande del
    hotel: 58 puestos y 689 conceptos de planilla.

    Los dos errores fallan igual de mal, que es no fallar: el código no existe,
    el motor manda su gasto a `OTHER_OVERHEAD`, el P&L cuadra y nadie se entera.

    Idempotente: aplicarlo dos veces da lo mismo, que es lo que permite ponerlo
    en el camino de guardado sin pensar si ya pasó por acá.
    """
    if not isinstance(code, str):
        return code
    limpio = code.strip()
    if not limpio.isdigit():
        return limpio or code
    de_tres = _tres_digitos()
    # Le falta el cero: tres dígitos que no son de un departamento de tres.
    if len(limpio) == 3 and limpio not in de_tres:
        return limpio.zfill(4)
    # Le sobra el cero: cuatro dígitos que sin él SÍ son un departamento real.
    if len(limpio) == 4 and limpio.startswith("0") and limpio[1:] in de_tres:
        return limpio[1:]
    return limpio or code


#: El catálogo NO se normaliza: es donde se DECLARA qué departamentos existen.
#: Rellenarle el cero a un código de tres que alguien está creando lo volvería
#: otro departamento — justo al revés de lo que esto viene a evitar.
EXENTOS = {"DepartmentCatalog"}


def _normalizar_en(obj) -> None:
    if type(obj).__name__ in EXENTOS:
        # Y de paso se APRENDE de él: un departamento de tres dígitos que
        # alguien esté creando queda registrado, así que a partir de ese
        # momento deja de rellenarse. Sin esto, crear el «290» funcionaría y
        # cargarle datos lo mandaría al «0290», que no existe.
        codigo = getattr(obj, "dept_code", None)
        if isinstance(codigo, str) and len(codigo.strip()) == 3:
            recordar_tres_digitos([codigo.strip()])
        return
    actual = getattr(obj, "dept_code", None)
    nuevo = normalizar_dept_code(actual)
    if nuevo != actual:
        obj.dept_code = nuevo


# ⚠️ A `SesionFinPlan` y no al `Session` global — mismo motivo que el candado
# de meses: registrado en el global, el listener corre en CUALQUIER sesión de
# SQLAlchemy del proceso, incluidas las de las pruebas que arman datos a mano.
@event.listens_for(SesionFinPlan, "before_flush")
def _antes_de_guardar(session, flush_context, instances):  # noqa: ANN001
    """Le devuelve el cero a todo `dept_code` que se esté por guardar."""
    for obj in list(session.new) + list(session.dirty):
        if not hasattr(obj, "dept_code"):
            continue
        try:
            if sa_inspect(obj).deleted:
                continue
        except Exception:
            # Un objeto que SQLAlchemy no puede inspeccionar no es nuestro
            # problema: que siga el guardado en vez de tumbarlo.
            continue
        _normalizar_en(obj)
