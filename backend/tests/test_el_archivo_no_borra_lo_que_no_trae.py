# -*- coding: utf-8 -*-
"""El archivo no puede borrar lo que el archivo no puede traer — segunda puerta.

**El defecto (owner, 2026-10-06).** Subiendo el Forecast de setiembre con la
plantilla recién bajada, por tercera vez:

    API 409: Jun is already closed in "FORECAST September 2026" …
    (cambiar OpexEntry.jun: 30.0000 → 0 (diferencia 30.0000) · 7400 en 0220)

El 7400 de Cafetería **está en la plantilla**: lo lista el propio archivo de
orden del owner (`orden_plantilla.json`, 82 filas entre 0220 y 0161) y la
descarga lo trae con su monto. Al volver a subir, el parser lo salta por
`ALLOCATION_EXCLUDE` —correcto, esas clases netean a cero vía Distribución— y el
escritor ponía la fila en cero.

**Lo que hacía daño no era el 409: era el silencio.** En un mes abierto esas
clases no entran a ningún total operativo, así que borrarlas no movía un solo
número del P&L. Bajar la plantilla y subirla sin tocar nada vaciaba el gasto de
Cafetería y Lavandería y nada avisaba. Apareció sólo porque en un mes cerrado el
candado lo frena — el candado hizo de detector de un borrado silencioso.

Es el mismo patrón que las contrapartidas de reparto
(`test_contrapartidas_sobreviven`), por otro agujero: ahí era la clase 4
«Distribución», acá son las clases 5/6/7 de los dos departamentos de allocation.

**Dónde va la raya.** Protege el CHECKBOOK —`OpexEntry`, `CostEntry`, los
conceptos de planilla—, que es lo que el owner digita. NO protege `ActualEntry`:
ahí el parser es la autoridad de qué pertenece al mayor, y una fila de esas
clases es residuo. El primer intento sí la protegía, y le sumó US$62.315 de
overhead al Forecast de setiembre — la verificación de la puerta lo frenó antes
de escribir una sola fila, que es exactamente para lo que está.

**El riesgo que vigila esta prueba:** la regla está dicha DOS VECES —en Python
para el parser y el escritor fila por fila, y en SQL para los DELETE masivos—.
Si se separan, el reemplazo vuelve a borrarlas y nada avisa.
"""
import pytest
import sqlalchemy as sa

from app.importers.gl_detail_importer import (ALLOCATION_EXCLUDE,
                                              excluida_del_archivo,
                                              parse_gl_detail)


#: Lo que el parser deja fuera, y por lo tanto el archivo no puede reponer.
FUERA = [
    ("0220", "7400", "opex de Cafetería"),
    ("0220", "7065", "limpieza de Cafetería"),
    ("0220", "5700", "costo de comida de Cafetería"),
    ("0220", "6000", "planilla de Cafetería"),
    ("0161", "7400", "insumos de Lavandería"),
    ("0161", "6020", "CCSS de Lavandería"),
]

#: Lo que SÍ viaja en el archivo: borrarlo y reponerlo es el trabajo normal.
DENTRO = [
    ("0110", "7400", "opex de Habitaciones"),
    ("0120", "5101", "costo de comida de A&B"),
    ("0220", "4901", "la contrapartida de Cafetería — la cuida otra regla"),
    ("0161", "4700", "Laundry Services: ingreso operativo, se queda"),
    ("0161", "5501", "y su costo de venta también"),
]


@pytest.mark.parametrize("dept,cuenta,_que", FUERA)
def test_reconoce_lo_que_el_archivo_no_trae(dept, cuenta, _que):
    assert excluida_del_archivo(dept, cuenta)


@pytest.mark.parametrize("dept,cuenta,_que", DENTRO)
def test_no_protege_de_mas(dept, cuenta, _que):
    assert not excluida_del_archivo(dept, cuenta)


def test_en_overhead_no_protege_nada():
    """El espejo del Pre-Cierre no excluye nada, así que el archivo manda.

    Proteger ahí sería lo contrario de lo que se quiere: en ese tab el gasto de
    allocation SÍ viaja en el archivo y tiene que poder corregirse.
    """
    for dept, cuenta, _q in FUERA:
        assert not excluida_del_archivo(dept, cuenta, en_overhead=True)


def test_la_regla_sql_dice_lo_mismo_que_la_de_python():
    """Las dos versiones se derivan de `ALLOCATION_EXCLUDE`, no se repiten a mano.

    Esta prueba compara las dos sobre la misma tabla de casos: si alguien edita
    una sola, acá se cae.
    """
    from app.api.scenarios_api import _excluida_del_archivo_sql
    from app.models.opex_entry import OpexEntry

    cond = _excluida_del_archivo_sql(OpexEntry, en_overhead=False)
    texto = str(cond.compile(compile_kwargs={"literal_binds": True}))
    for dept, clases in ALLOCATION_EXCLUDE.items():
        assert dept in texto, f"la condición SQL no menciona {dept}"
        for c in clases:
            assert f"'{c}'" in texto, f"la condición SQL no excluye la clase {c}"
    # Y en modo Pre-Cierre no excluye nada.
    assert str(_excluida_del_archivo_sql(OpexEntry, en_overhead=True)
               .compile(compile_kwargs={"literal_binds": True})).lower() in ("false", "0 = 1")


def test_el_escritor_protege_las_mismas_filas_que_el_parser_salta():
    """La prueba de verdad: lo que el parser salta es EXACTAMENTE lo que el
    escritor protege.

    Sin esto, las dos reglas pueden alejarse sin que nada truene: el parser
    excluye una clase más, el escritor la sigue poniendo en cero, y el borrado
    silencioso vuelve.
    """
    for dept, clases in ALLOCATION_EXCLUDE.items():
        for clase in clases:
            cuenta = f"{clase}400"
            assert excluida_del_archivo(dept, cuenta), (
                f"{cuenta} en {dept} lo salta el parser y el escritor no lo protege")
        for clase in set("45678") - clases:
            cuenta = f"{clase}400"
            assert not excluida_del_archivo(dept, cuenta), (
                f"{cuenta} en {dept} sí entra por el parser: no hay que protegerlo")


def test_el_mayor_no_se_protege():
    """`ActualEntry` se limpia como siempre: ahí el parser manda.

    Mira el código fuente porque es una AUSENCIA lo que hay que vigilar, y una
    ausencia no se puede probar llamando a nadie. Si alguien vuelve a proteger el
    mayor, el overhead del forecast sube sin que cambie un solo dato.
    """
    from pathlib import Path

    src = Path("app/api/scenarios_api.py").read_text(encoding="utf-8")
    borrado = src[src.index("sa_delete(ActualEntry)"):][:400]
    assert "ES_CONTRAPARTIDA_DE_ALLOCATION" in borrado
    assert "_excluida_del_archivo_sql" not in borrado
    # Y `_filas_que_sobreviven` tampoco las agrega al consolidado de la puerta.
    fn = src[src.index("async def _filas_que_sobreviven"):]
    fn = fn[:fn.index("COPY_DATASETS")]
    assert "excluida_del_archivo" not in fn
