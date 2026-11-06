# -*- coding: utf-8 -*-
"""El pegado tiene que funcionar parándose en la celda, sin entrar a editar.

Owner, 2026-11-05, en el checkbook de costos de 0230: *«necesito poder hacer un
copy paste acá... copio en excel y hago paste en los 12 meses y todo queda,
pero ahora no se puede hacer nada»*.

## Lo que pasaba

El pegado **existía** desde `109dbbb`. Pero el `onPaste` colgaba del `<input>`,
y ese `<input>` sólo se monta DESPUÉS de hacer clic en la celda. Quien se para
en enero y hace Ctrl+V sin haber entrado a editar no pega nada, y la pantalla
no dice una palabra.

Peor: las cinco líneas de 0230 están en cero, y una celda en cero se dibuja
«—», igual que una de sólo lectura. Desde afuera no hay ninguna diferencia
entre «esta celda no acepta nada» y «acepta, pero tenés que adivinar que
primero hay que hacerle clic».

Verificado contra producción antes de tocar código: las cinco líneas estaban en
`MANUAL`, moneda USD, y el escenario `Budget Working 2027` en `draft`. El
servidor nunca estuvo rechazando nada — era la celda.

## El arreglo, y por qué así

`tabIndex` + `onFocus`: enfocar la celda —con un clic o con Tab— ya la pone a
editar, así que siempre se termina dentro de un `<input>` de verdad, que es
donde el `paste` llega seguro. De yapa, Tab recorre los doce meses como en
Excel.

⚠️ **No se apuesta a que el navegador le mande el `paste` a un `<td>` que no
es editable.** Intenté medirlo con una página de prueba servida en localhost y
no pude: en el navegador automatizado el Ctrl+C no pasa por el portapapeles del
sistema —el `textarea` de control también vino vacío—, así que la prueba no
concluyó. Lo que no se midió no se da por cierto. El `onPaste` se queda igual
en la celda porque el evento del `<input>` burbujea hasta ahí: **un solo camino
y no dos** enganches que puedan separarse.

⚠️ Y `pegarDesde` tiene que ir por `conAviso`. Se me quedó afuera el 2026-11-05
cuando envolví las otras cuatro, y es la peor de las cinco: un pegado que falla
recarga la grilla igual y vuelve a enseñar lo de antes, o sea que se ve
exactamente como «no deja pegar». Es el mismo fallo mudo que el owner reportó
tres veces ese día.
"""
import pathlib
import re

import pytest

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
#: Pantallas con grilla de meses donde el owner pega desde Excel.
PANTALLAS = [
    FRONT / "app" / "costs" / "checkbook" / "page.tsx",
]


def _numcell(src: str) -> str:
    """El cuerpo del componente de celda editable, **sin comentarios**.

    ⚠️ Los comentarios se van primero: el de esta misma celda explica por qué
    el `onPaste` no va en el `<input>`, y con esas dos palabras adentro la
    prueba contaba dos enganches y buscaba el `<td>` hasta el `<input>` de la
    prosa. Una prueba que lee código tiene que leer código.
    """
    i = src.find("function NumCell")
    assert i >= 0, "no encontré NumCell"
    j = src.find("\nexport default", i)
    cuerpo = src[i: j if j > 0 else len(src)]
    cuerpo = re.sub(r"/\*.*?\*/", "", cuerpo, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in cuerpo.splitlines())


@pytest.mark.parametrize("ruta", PANTALLAS, ids=lambda p: p.parent.name)
def test_el_onpaste_vive_en_la_celda_y_no_en_el_input(ruta: pathlib.Path):
    """Parado en la celda, sin clic previo, Ctrl+V tiene que entrar."""
    cuerpo = _numcell(ruta.read_text(encoding="utf-8"))
    # La celda abre con `<td` y el input con `<input`; el `onPaste` va antes
    # del `<input>`, que es el tramo de atributos del `<td>`.
    td = cuerpo[: cuerpo.find("<input")]
    assert "onPaste" in td, (
        f"{ruta.name}: el onPaste no está en el <td>. Si cuelga del <input>, "
        "sólo pega quien ya entró a editar."
    )
    assert "tabIndex" in td, (
        f"{ruta.name}: sin tabIndex la celda no se alcanza con Tab."
    )
    assert "onFocus" in td, (
        f"{ruta.name}: sin onFocus, enfocar la celda no abre el <input>, y el "
        "pegado vuelve a depender de que el navegador mande el evento a un "
        "<td> que no es editable — que es justo lo que no se pudo medir."
    )


@pytest.mark.parametrize("ruta", PANTALLAS, ids=lambda p: p.parent.name)
def test_el_input_no_duplica_el_enganche(ruta: pathlib.Path):
    """Un solo camino: el del input burbujea a la celda."""
    cuerpo = _numcell(ruta.read_text(encoding="utf-8"))
    assert cuerpo.count("onPaste") == 1, (
        f"{ruta.name}: hay más de un onPaste en NumCell. Dos enganches para "
        "lo mismo se separan: uno se arregla y el otro queda viejo."
    )


@pytest.mark.parametrize("ruta", PANTALLAS, ids=lambda p: p.parent.name)
def test_un_pegado_que_falla_avisa(ruta: pathlib.Path):
    """`pegarDesde` por `conAviso`, como los otros cuatro guardados."""
    src = ruta.read_text(encoding="utf-8")
    m = re.search(r"async function pegarDesde\b.*?\n  }\n", src, re.S)
    assert m, f"{ruta.name}: no encontré pegarDesde"
    assert "conAviso" in m.group(0), (
        f"{ruta.name}: pegarDesde no pasa por conAviso. Un pegado que falla "
        "recarga la grilla y vuelve a enseñar lo de antes: se ve igual que si "
        "la pantalla no dejara pegar."
    )


@pytest.mark.parametrize("ruta", PANTALLAS, ids=lambda p: p.parent.name)
def test_la_celda_editable_se_distingue_de_una_de_solo_lectura(ruta: pathlib.Path):
    """En cero las dos dicen «—»: sin marca visible no hay forma de saberlo."""
    cuerpo = _numcell(ruta.read_text(encoding="utf-8"))
    assert "fin-celda-editable" in cuerpo, (
        f"{ruta.name}: la celda editable no lleva la clase que la marca."
    )
    css = (FRONT / "app" / "globals.css").read_text(encoding="utf-8")
    assert ".fin-celda-editable:hover" in css, "falta el hover en globals.css"
    assert ".fin-celda-editable:focus-visible" in css, (
        "falta el foco en globals.css: con tabIndex la celda se enfoca con Tab "
        "y hay que poder ver dónde se está parado."
    )
