# -*- coding: utf-8 -*-
"""Una categoria oculta no sale en NINGUNA pantalla.

Owner, 2026-10-04, viendo «Categoria 5» a «Categoria 8» en Total Revenue:
*«hay que quitar esos room types incorrectos de todas las vistas»*.

## Que estaba pasando

Las cuatro estaban ocultas (`active = false`, cero unidades) y el Inventario y
las Rack Rates ya no las mostraban. Pero `occupancy-pct` —la unica consulta de
pantalla que listaba los tipos SIN filtrar— las devolvia igual, y de ahi comen
Ocupacion, Pax, Room Nights, Disponibilidad y Total Revenue. Media app las
escondia y la otra media las mostraba.

## ⚠️ Por que es un test y no «ya esta arreglado»

Ocultar una categoria propaga a todo el revenue: es una decision del owner que
tiene que valer en todas partes o no vale en ninguna. Una consulta nueva que se
olvide del filtro no rompe nada visible — agrega renglones en cero, que se leen
como una categoria que no vendio y no como una que no existe.

Medido antes de tocar nada: las cuatro de Amarena no tienen ocupacion, ni
tarifa, ni estadistica cargada. Esconderlas no movio un numero.
"""
import pathlib
import re

API = pathlib.Path(__file__).resolve().parents[1] / "app/api/revenue_api.py"

#: Consultas que arman lo que una PANTALLA dibuja. Cada una tiene que filtrar.
#:
#: ⚠️ Las de escritura y las de administracion quedan afuera a proposito: para
#: poder volver a mostrar una categoria hay que poder verla, y el Inventario la
#: pide con `include_inactive`.
DE_PANTALLA = ("get_occupancy_pct", "get_rack_rates")


def _cuerpo(nombre: str) -> str:
    s = API.read_text(encoding="utf-8")
    i = s.index(f"async def {nombre}(")
    j = s.find("\n@router.", i)
    return s[i:j if j > 0 else len(s)]


def test_toda_consulta_de_PANTALLA_filtra_lo_oculto():
    """El filtro puede ser `active` o `aplica_en(año)` —esta ultima en las
    propiedades que tienen categorias que todavia no abrieron—, pero tiene que
    estar."""
    sin_filtro = []
    for f in DE_PANTALLA:
        c = _cuerpo(f)
        if "RoomTypeConfig.active == True" not in c and "aplica_en(" not in c:
            sin_filtro.append(f)
    assert not sin_filtro, (
        f"estas consultas devuelven categorias ocultas: {sin_filtro}. "
        "Lo oculto no sale en ninguna vista: media app escondiendolas y la otra "
        "media mostrandolas es peor que no esconderlas.")


def test_el_inventario_SI_puede_verlas():
    """⚠️ El reverso de la regla.

    Para volver a mostrar una categoria hay que poder verla. El Inventario la
    pide con `include_inactive`, y si ese camino se cerrara, ocultar una
    categoria seria irreversible desde la aplicacion.
    """
    s = API.read_text(encoding="utf-8")
    assert "include_inactive" in s
    cuerpo = _cuerpo("get_room_types")
    assert "if not include_inactive:" in cuerpo


def test_el_codigo_de_una_categoria_oculta_NO_se_reusa():
    """Owner, 2026-08-14: *«que los codigos no se muevan nunca»*.

    Por eso se OCULTA y no se borra: el codigo queda reservado para siempre, asi
    que un SH08 de hoy no puede terminar apuntando a otra categoria mañana. Si
    alguien cambiara el ocultar por un borrar, el reporte de Junta —que cruza
    por codigo— empezaria a sumar historia de dos categorias distintas.
    """
    s = API.read_text(encoding="utf-8")
    cuerpo = _cuerpo("delete_room_type")
    assert "active" in cuerpo, "el borrado dejo de ser un ocultar"
    assert not re.search(r"\bdb\.delete\(", cuerpo), (
        "la categoria se esta BORRANDO: su codigo queda libre para reusarse")
