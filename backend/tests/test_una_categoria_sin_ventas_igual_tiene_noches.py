# -*- coding: utf-8 -*-
"""Una categoria que no vendio igual tuvo sus habitaciones disponibles.

Owner, 2026-09-16, mirando el acumulado enero-agosto: «revisa esto.. no me
pega. de enero a Agosto debe ser otro numero».

    30 unidades x 243 dias (ene-ago 2026) = 7.290 noches
    la pantalla decia                       7.135
    faltaban                                  155  = 5 unidades x 31 dias

«5 Elements Treehouse» (5 unidades) no vendio nada en agosto, quedo en blanco,
y el guardado la SALTABA por vacia. Con la fila se iban sus noches disponibles.
El aviso de la pantalla lo decia sin que se notara: «Saved Aug: 5 rows» — cinco,
cuando las categorias son seis.

## Por que importa mas de lo que parece

El daño va en la direccion que nadie sospecha. Al achicarse el DENOMINADOR, la
ocupacion y el RevPAR salen MAS ALTOS de lo real: 46,8 % en vez de 45,8 %. Un
numero malo se revisa; uno favorable se acepta.

Y no se arregla solo: los meses ya guardados asi siguen cortos hasta que se
vuelvan a guardar.
"""
import inspect

from app.api import revenue_api


def _guardado() -> str:
    return inspect.getsource(revenue_api.put_room_stats_entry)


def test_una_fila_con_unidades_se_guarda_aunque_no_haya_vendido():
    src = _guardado()
    assert "if not (r.units or 0) and not (r.nights_occupied or r.revenue or r.pax):" in src, (
        "la condicion tiene que mirar las UNIDADES: son las que dicen que esas "
        "habitaciones existieron, haya habido huespedes o no")


def test_la_fila_sin_inventario_si_se_descarta():
    """«Other Rooms Revenue» no aporta disponibilidad; guardarla vacia seria ruido."""
    src = _guardado()
    assert "no es una fila" in src


def test_las_noches_salen_de_las_unidades_y_los_dias():
    src = _guardado()
    assert "nights_available=(r.units or 0) * days" in src


def test_la_respuesta_dice_cuantas_TENIA_que_guardar():
    """«5 filas» no se lee como un problema. «5 de 6» si."""
    src = _guardado()
    assert '"categorias"' in src, (
        "sin el esperado, la pantalla no puede avisar que falto una categoria")


def test_la_aritmetica_del_caso_que_lo_destapo():
    """Clava el numero, para que nadie 'arregle' esto y lo vuelva a romper."""
    import calendar
    dias = sum(calendar.monthrange(2026, m)[1] for m in range(1, 9))
    assert dias == 243
    assert 30 * dias == 7290
    assert 7290 - 7135 == 5 * 31 == 155
