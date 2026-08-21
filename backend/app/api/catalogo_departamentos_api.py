# -*- coding: utf-8 -*-
"""El catálogo de departamentos, editable — la puerta que faltaba (B6.4).

## Qué estaba y qué no (medido 2026-08-16)

La nota de B6.4 decía «el motor embebe el catálogo y un clon no puede renombrar,
agregar ni quitar un departamento sin tocar código». **La mitad ya no era
cierta**: `pl_engine.set_dept_catalog()` existe y `main.py` lo llama al arrancar,
así que el motor ya lee `department_catalog` para el mapa depto→grupo y la
consolidación de hijos. Lo que faltaba era **por dónde editarlo**: la tabla solo
se cambiaba por SQL o migración. El único `PUT` que existía —
`provisioning/{hotel_id}/departments/`— **filtra visibilidad, no crea nada**.

Esto es esa puerta. Sirve para el caso que pidió el owner: *«es posible que
algunos departamentos en Amarena quisiéramos renombrarlos, pero quizás sea más
fácil hacerlo después de clonar»*.

## Las cinco barandas, y ninguna es capricho

1. **El código NO se edita jamás.** Es la llave con la que el mapeo, la planilla,
   los reportes y las otras propiedades se refieren al departamento. Es la misma
   regla del código de categoría de habitación y del código de posición: el
   NOMBRE es etiqueta, el CÓDIGO no se mueve.
2. **No se borra: se desactiva.** Borrar libera el código y el día que alguien
   cree otro departamento podría reutilizarlo, apuntando historia vieja a algo
   que no es. Lo mismo que se cerró con los room types.
3. **Un código no se reutiliza aunque esté inactivo.** Crear con un código que ya
   existe —activo o no— es 409.
4. **`default_pl_group` tiene que ser un grupo que el motor conozca.** Un grupo
   inventado deja al departamento sin línea en el P&L, en silencio. El owner
   confirmó el 2026-08-16 que las cuatro propiedades usan **los mismos grupos**,
   así que acá no se crean grupos: se elige entre los que hay.
5. **`parent_dept_code` no puede hacer ciclos** ni apuntar a un código que no
   existe. El padre decide dónde aterriza el gasto («el gasto es del padre»), así
   que un ciclo no es un error de datos: es un reporte que no cierra.

## ⚠️ Renombrar NO toca los alias del GL

`name_aliases` es con lo que el importador reconoce la etiqueta del mayor
(`"lavander"` → `0161`). **Es un campo aparte del nombre y se edita aparte.**
Si renombrar arrastrara el alias, la próxima importación dejaría de reconocer
las filas de ese departamento y no lo diría — que es exactamente el modo de falla
que este sistema ya tuvo con el mapeo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.engine import pl_engine
from app.models.department_catalog import DepartmentCatalog

router = APIRouter()

PL_KINDS = ("OPERATING", "OVERHEAD")


def grupos_conocidos() -> set[str]:
    """Los grupos que el motor sabe poner en una línea del P&L.

    Sale del propio motor, no de una lista escrita acá: el día que se agregue un
    grupo, esta validación lo acepta sola. Vacío es válido a propósito — los
    departamentos de ingreso por CUENTA (el `280` Miscelaneos) no tienen grupo y
    llegan a su línea por el mapeo.
    """
    return set(pl_engine.OPERATING_DEPT_GROUPS) | set(pl_engine.OVERHEAD_DEPT_GROUPS)


class DeptCrear(BaseModel):
    dept_code: str
    dept_name: str
    name_en: str = ""
    default_pl_group: str = ""
    pl_kind: str = "OPERATING"
    is_revenue_dept: bool = False
    parent_dept_code: str | None = None
    display_order: int = 0
    name_aliases: list[str] | None = None


class DeptEditar(BaseModel):
    """Solo lo que se puede cambiar. `dept_code` NO está, a propósito."""
    dept_name: str | None = None
    name_en: str | None = None
    default_pl_group: str | None = None
    pl_kind: str | None = None
    is_revenue_dept: bool | None = None
    parent_dept_code: str | None = None
    display_order: int | None = None
    name_aliases: list[str] | None = None
    active: bool | None = None


def _fila(d: DepartmentCatalog) -> dict:
    return {
        "dept_code": d.dept_code, "dept_name": d.dept_name, "name_en": d.name_en,
        "name_aliases": d.name_aliases or [], "default_pl_group": d.default_pl_group,
        "pl_kind": d.pl_kind, "is_revenue_dept": d.is_revenue_dept,
        "is_allocation_source": d.is_allocation_source, "room_set": d.room_set,
        "parent_dept_code": d.parent_dept_code, "display_order": d.display_order,
        "active": d.active,
    }


async def _todos(db: AsyncSession) -> list[DepartmentCatalog]:
    return list((await db.execute(
        select(DepartmentCatalog).order_by(DepartmentCatalog.display_order,
                                           DepartmentCatalog.dept_code)
    )).scalars())


def _validar_grupo(grupo: str | None) -> None:
    if grupo is None or grupo == "":
        return          # ingreso por cuenta: es válido y es a propósito
    if grupo not in grupos_conocidos():
        raise ErrorApi(422, "departamento.grupo_desconocido", grupo=grupo,
                       grupos=", ".join(sorted(grupos_conocidos())))


def _validar_padre(codigo: str, padre: str | None,
                   por_codigo: dict[str, DepartmentCatalog]) -> None:
    if not padre:
        return
    if padre == codigo:
        raise ErrorApi(422, "departamento.padre_es_el_mismo")
    if padre not in por_codigo:
        raise ErrorApi(422, "departamento.padre_no_existe", padre=padre)
    # Ciclo: subir por la cadena desde el padre propuesto.
    visto, actual = {codigo}, padre
    while actual:
        if actual in visto:
            raise ErrorApi(422, "departamento.ciclo_de_padres",
                           padre=padre, codigo=codigo)
        visto.add(actual)
        p = por_codigo.get(actual)
        actual = (p.parent_dept_code or "") if p else ""


@router.get("/department-catalog/")
async def listar(incluir_inactivos: bool = True, db: AsyncSession = Depends(get_db)):
    filas = await _todos(db)
    if not incluir_inactivos:
        filas = [d for d in filas if d.active]
    return {"departamentos": [_fila(d) for d in filas],
            "grupos": sorted(grupos_conocidos()), "pl_kinds": list(PL_KINDS)}


@router.post("/department-catalog/")
async def crear(body: DeptCrear, db: AsyncSession = Depends(get_db),
                idioma: str = Idioma):
    codigo = (body.dept_code or "").strip()
    if not codigo:
        raise ErrorApi(422, "departamento.falta_codigo")
    if not (body.dept_name or "").strip():
        raise ErrorApi(422, "departamento.falta_nombre")
    if body.pl_kind not in PL_KINDS:
        raise ErrorApi(422, "departamento.pl_kind_invalido", pl_kinds=PL_KINDS)

    por_codigo = {d.dept_code: d for d in await _todos(db)}
    if codigo in por_codigo:
        y = por_codigo[codigo]
        raise ErrorApi(409, "departamento.codigo_tomado" if y.active
                       else "departamento.codigo_tomado_inactivo",
                       codigo=codigo, nombre=y.dept_name)
    _validar_grupo(body.default_pl_group)
    _validar_padre(codigo, body.parent_dept_code, por_codigo)

    d = DepartmentCatalog(
        dept_code=codigo, dept_name=body.dept_name.strip(), name_en=body.name_en,
        name_aliases=body.name_aliases, default_pl_group=body.default_pl_group,
        pl_kind=body.pl_kind, is_revenue_dept=body.is_revenue_dept,
        parent_dept_code=body.parent_dept_code or None,
        display_order=body.display_order, active=True,
    )
    db.add(d)
    await db.commit()
    return {"ok": True, "departamento": _fila(d),
            "aviso": t(idioma, "departamento.entra_en_el_proximo_despliegue")}


@router.put("/department-catalog/{dept_code}/")
async def editar(dept_code: str, body: DeptEditar,
                 db: AsyncSession = Depends(get_db),
                 idioma: str = Idioma):
    """Renombrar, mover de grupo, cambiar de padre, activar o desactivar.

    El **código no está** entre lo editable: ver la baranda 1 del módulo.
    """
    por_codigo = {d.dept_code: d for d in await _todos(db)}
    d = por_codigo.get(dept_code)
    if d is None:
        raise ErrorApi(404, "departamento.no_existe", departamento=dept_code)

    cambios = body.model_dump(exclude_unset=True)
    if "pl_kind" in cambios and cambios["pl_kind"] not in PL_KINDS:
        raise ErrorApi(422, "departamento.pl_kind_invalido", pl_kinds=PL_KINDS)
    if "dept_name" in cambios and not (cambios["dept_name"] or "").strip():
        raise ErrorApi(422, "departamento.nombre_vacio")
    if "default_pl_group" in cambios:
        _validar_grupo(cambios["default_pl_group"])
    if "parent_dept_code" in cambios:
        _validar_padre(dept_code, cambios["parent_dept_code"] or None, por_codigo)

    # Desactivar a una madre con hijos activos deja a los hijos sin dónde
    # aterrizar el gasto. Se avisa con nombres, no con un booleano.
    if cambios.get("active") is False:
        hijos = [x.dept_code for x in por_codigo.values()
                 if x.active and (x.parent_dept_code or "") == dept_code]
        if hijos:
            raise ErrorApi(409, "departamento.madre_con_hijos_activos",
                           departamento=dept_code,
                           hijos=", ".join(sorted(hijos)))

    for campo, valor in cambios.items():
        setattr(d, campo, valor.strip() if isinstance(valor, str) else valor)
    if d.parent_dept_code == "":
        d.parent_dept_code = None
    await db.commit()
    return {"ok": True, "departamento": _fila(d), "cambios": sorted(cambios),
            "aviso": t(idioma,
                       "departamento.cambio_entra_en_el_proximo_despliegue"
                       if {"default_pl_group", "parent_dept_code", "pl_kind"}
                       & set(cambios) else
                       "departamento.cambio_de_etiqueta")}
