# -*- coding: utf-8 -*-
"""La pantalla muestra la tarifa NETA guardada, no `rack x factor`.

## Qué protege

Gemela de `test_tarifa_neta_a_mano.py`, que vigila el backend. Esta vigila el
**front**, porque el mismo defecto existía de los dos lados y sólo uno estaba
cubierto.

`rate_cards.net_rate_manual` (mig 159) dice «esta celda la puso una persona».
El motor del P&L respeta la bandera desde el día uno: calcula
`rooms_occupied x rc.net_rate` y nunca rehace la fórmula. Pero **cuatro
pantallas del front rehacían la multiplicación por su cuenta** para mostrar el
ingreso de habitaciones:

  · Revenue Checkbook   (y su botón «Fill from drivers», que ESCRIBE)
  · Total Revenue
  · Reporte a dueños
  · Command

Mientras toda tarifa salga de un rack las dos cuentas dan lo mismo, porque el
backend resincroniza la neta cada vez que se guarda un rack. Una neta puesta a
mano no tiene rack del que derivarla: las villas se negocian a **$1.700 NETOS**
y su rack está vacío. Las cuatro pantallas las valuaban en **$0** mientras el
motor cobraba $1.700 la noche — ~$360.000 de menos en el Budget 2027, sin un
solo error visible y con cada total cuadrando consigo mismo.

El caso caro es el Checkbook: ahí no era sólo mirar. «Fill from drivers»
escribía esa cifra equivocada a `RevenueEntry`, que es de donde el P&L toma el
ingreso.

## Por qué la prueba mira el CÓDIGO

Igual que su gemela: lo que hay que impedir no es un cálculo mal hecho, es que
aparezca una QUINTA pantalla que multiplique a mano. Eso no se ve ejecutando
las cuatro que ya existen — se ve recorriendo el front. La regla es una sola y
se puede leer de un vistazo: **quien arma un `rackById` pide la tarifa a
`lib/tarifaNeta`.**
"""
import pytest

from ._rutas import FRONT, sin_comentarios

#: El único lugar donde vive la fórmula `rack x factor`.
HELPER = "lib/tarifaNeta.ts"

#: Las cuatro que motivaron el arreglo. Nombradas para que borrar una no deje
#: la prueba en verde por vacío.
CONOCIDAS = [
    "app/revenue/checkbook/page.tsx",
    "app/revenue/total-revenue/page.tsx",
    "app/reports/owner/page.tsx",
    "app/command/page.tsx",
]


def _fuentes():
    """Cada .ts/.tsx de las pantallas, con su código sin comentarios."""
    for carpeta in ("app", "components"):
        for f in sorted((FRONT / carpeta).rglob("*.ts*")):
            yield f.relative_to(FRONT).as_posix(), sin_comentarios(
                f.read_text(encoding="utf-8"))


def _arman_rack():
    """Las pantallas que construyen la tabla de racks por categoría."""
    return {rel: src for rel, src in _fuentes() if "rackById" in src}


def test_quien_arma_un_rack_pide_la_tarifa_al_helper():
    """Nadie multiplica `rack x factor` por su cuenta.

    ⚠️ Si esto falla con una pantalla que no conocías, NO la agregues a una
    lista de excepciones: cambiá la pantalla para que use `hacerTarifaNeta`.
    Una excepción acá es una categoría de tarifa negociada valuada en cero, y
    se ve igual de plausible que el número correcto.
    """
    sin_helper = [rel for rel, src in _arman_rack().items()
                  if "hacerTarifaNeta" not in src]
    assert not sin_helper, (
        f"Estas pantallas arman un rack y no piden la tarifa a {HELPER}: "
        f"{sin_helper}. Una neta puesta a mano (las villas, $1.700) no tiene "
        "rack del que derivarla y la pantalla la valúa en $0."
    )


@pytest.mark.parametrize("rel", CONOCIDAS)
def test_las_cuatro_pantallas_siguen_cubiertas(rel):
    """Las que tenían el defecto existen y siguen pasando por el helper."""
    f = FRONT / rel
    assert f.exists(), f"{rel} ya no existe: revisá si la vista se movió"
    src = sin_comentarios(f.read_text(encoding="utf-8"))
    assert "hacerTarifaNeta" in src, (
        f"{rel} dejó de usar el helper. Era una de las cuatro que valuaban "
        "las villas en $0."
    )


def test_el_helper_respeta_la_bandera():
    """La fórmula vive en un solo lugar, y ese lugar pregunta por `manual`.

    Sin esto la prueba de arriba se cumpliría importando el helper y
    multiplicando igual al lado.
    """
    src = sin_comentarios((FRONT / HELPER).read_text(encoding="utf-8"))
    assert "manual" in src, f"{HELPER} no consulta la bandera `manual`"
    assert "netFactor" in src, f"{HELPER} ya no deriva del factor de canales"
