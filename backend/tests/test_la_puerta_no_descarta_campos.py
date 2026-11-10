# -*- coding: utf-8 -*-
"""Lo que el cuadro manda tiene que LLEGAR al Excel.

## De dónde sale (2026-11-09)

El owner bajó el Budget Package y el bloque de validación no tenía fórmulas.
Mirando el XML en crudo: **24 hojas, CERO celdas con `<f>`**. No sólo las mías
— ninguna. El paquete nunca había tenido una fórmula.

La causa está en la puerta: `export_api.Fila` declaraba `label`, `nivel`,
`es_total`, `formato` y `valores`, y nada más. **Pydantic descarta en silencio
los campos que el modelo no nombra.** `es_seccion`, `suma_de`, `combina_filas`
y `formula_tpl` se perdían al cruzar el HTTP.

Todo el andamiaje que arma esas fórmulas —`componentesDelPL`,
`resultadosDelPL`, el arnés de node con 809 comprobaciones que verifica ordinal
por ordinal que cada `suma_de` apunte a la fila que suma— funcionaba bien y
tiraba el resultado a la basura tres capas más abajo.

## Por qué nadie lo vio

Es el modo de falla más caro que hay acá: **no falla nada**. Los números del
Excel están bien, las hojas están completas, los totales cuadran. Lo único que
se pierde es poder pararse en una celda y ver de dónde sale — y eso no se nota
hasta que alguien busca el `=` y no está.

Las pruebas del arnés tampoco lo veían: comprueban el objeto `Cuadro`, que es
correcto. El salto perdido estaba entre ese objeto y el archivo.

## Lo que cuida

Que todo campo que `cuadro_excel` sabe leer esté declarado en el modelo de
entrada. Es la lista de los dos lados cruzada, no una copia: agregar un campo
al exportador sin declararlo acá vuelve a tirarlo en silencio.
"""
import io
import re
import zipfile

import pytest

from app.api.export_api import Cuadro, Fila
from app.export.cuadro_excel import build_cuadros_workbook

#: Lo que `_hoja` y `_formula` leen de una fila. Si el exportador aprende a leer
#: un campo nuevo, va en esta lista Y en el modelo.
CAMPOS_QUE_EL_EXPORTADOR_LEE = [
    "label", "nivel", "es_total", "es_seccion", "formato",
    "valores", "suma_de", "combina_filas", "formula_tpl",
]


@pytest.mark.parametrize("campo", CAMPOS_QUE_EL_EXPORTADOR_LEE)
def test_el_modelo_de_entrada_declara_el_campo(campo):
    """⚠️ Pydantic descarta lo que no está declarado, en silencio y sin error."""
    assert campo in Fila.model_fields, (
        f"`{campo}` no está en `export_api.Fila`: el cuadro lo manda y la "
        f"puerta lo tira antes de llegar al Excel")


def test_lo_que_el_exportador_LEE_esta_todo_declarado():
    """La lista de arriba contra el código del exportador, no contra sí misma.

    Un campo que el exportador empiece a leer y nadie declare vuelve al defecto
    del 2026-11-09."""
    import pathlib

    fuente = (pathlib.Path(__file__).resolve().parents[1]
              / "app/export/cuadro_excel.py").read_text(encoding="utf-8")
    # Todo `f.get("algo")` sobre una fila del cuadro.
    leidos = set(re.findall(r'\bf\.get\("([a-z_]+)"', fuente))
    #: Lo que el exportador calcula por su cuenta, no viene en el payload.
    PROPIOS = {"kpis", "kpis_columnas"}
    faltan = sorted(leidos - set(CAMPOS_QUE_EL_EXPORTADOR_LEE) - PROPIOS)
    assert not faltan, (
        f"el exportador lee campos que nadie declaró en el modelo: {faltan}")


# ── El viaje completo ───────────────────────────────────────────────────────

COLS = [{"label": "Line Item", "formato": "texto"},
        {"label": "Ene", "formato": "usd2"},
        {"label": "Feb", "formato": "usd2"}]


def _por_la_puerta(cuadro: dict) -> bytes:
    """El MISMO camino del endpoint: parsear con Pydantic y volver a dict."""
    return build_cuadros_workbook([Cuadro(**cuadro).model_dump()])


def _formulas(blob: bytes) -> int:
    z = zipfile.ZipFile(io.BytesIO(blob))
    return sum(len(re.findall("<f>", z.read(n).decode("utf-8")))
               for n in z.namelist()
               if re.match(r"xl/worksheets/sheet\d+\.xml$", n))


def test_un_suma_de_llega_al_archivo_como_FORMULA():
    """El caso que el owner vio: 24 hojas y cero `<f>`."""
    cuadro = {"titulo": "T", "hoja": "T", "columnas": COLS, "filas": [
        {"label": "a", "valores": [10, 20]},
        {"label": "b", "valores": [5, 7]},
        {"label": "Total", "valores": [15, 27], "es_total": True,
         "suma_de": [0, 1]}]}
    assert _formulas(_por_la_puerta(cuadro)) > 0, (
        "el `suma_de` se perdió en la puerta: el Excel baja con el número "
        "pegado y nada avisa")


def test_una_formula_tpl_llega_al_archivo():
    cuadro = {"titulo": "T", "hoja": "T", "columnas": COLS, "filas": [
        {"label": "a", "valores": [10, 20]},
        {"label": "doble", "valores": [0, 0], "formula_tpl": "={c}{r:0}*2"}]}
    blob = _por_la_puerta(cuadro)
    assert _formulas(blob) > 0, "la `formula_tpl` se perdió en la puerta"


def test_una_seccion_sigue_siendo_seccion_del_otro_lado():
    """`es_seccion` también se descartaba: el encabezado de bloque salía con el
    mismo peso que un total y el ojo no encontraba dónde cierra cada bloque —
    que es justo lo que el owner pidió corregir el 2026-09-30."""
    cuadro = {"titulo": "T", "hoja": "T", "columnas": COLS, "filas": [
        {"label": "REVENUES", "es_seccion": True, "valores": [None, None]}]}
    assert Cuadro(**cuadro).filas[0].es_seccion is True
