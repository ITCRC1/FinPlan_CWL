# -*- coding: utf-8 -*-
"""El Pre-Cierre se puede mirar en COLONES, no solo en dolares.

Owner, 2026-09-15: «que tal si queremos ver precierre en colones tambien.. y
que una vez subido haya una parte donde yo pueda verlo en CRC o en USD».

El importador SIEMPRE calculo el colon —es de donde sale el dolar, via
`a_dolares(mes_crc, tc)`— y lo tiraba antes de guardar.
"""
import inspect
from decimal import Decimal as D

from app.export import revision_mes_xlsx as revision
from app.models.precierre import PrecierreFila, PrecierrePosicion


def _fila(clave_grupo="ADMIN", usd="10.00", crc=None, cat="Otros Gastos"):
    f = {"fila": 1, "cuenta": "7000-0180", "cuenta_base": 7000, "depto": "0180",
         "destino_finplan": "0180", "grupo": clave_grupo, "categoria": cat,
         "descripcion": "x", "mes_usd": D(usd), "acumulado_usd": D(usd)}
    if crc is not None:
        f["mes_crc"] = D(crc)
    return f


def test_el_colon_se_guarda_no_se_reconstruye():
    """`usd x tc` NO devuelve el colon del mayor: el dolar esta redondeado."""
    assert "mes_crc" in PrecierreFila.__table__.columns
    assert "acumulado_crc" in PrecierreFila.__table__.columns
    assert "mes_crc" in PrecierrePosicion.__table__.columns


def test_las_columnas_del_colon_son_nulables():
    """Lo subido antes del 2026-09-15 no lo tiene, y no hay de donde sacarlo."""
    assert PrecierreFila.__table__.c.mes_crc.nullable
    assert PrecierreFila.__table__.c.acumulado_crc.nullable
    assert PrecierrePosicion.__table__.c.mes_crc.nullable


def test_la_cascada_suma_la_moneda_que_se_le_pida():
    # `ROOMS` es una DIVISION; `ADMIN` seria overhead y caeria en otra clave.
    filas = [_fila(clave_grupo="ROOMS", usd="10.00", crc="4529.30")]
    en_usd = revision.valores_completos(filas, "mes_usd")
    en_crc = revision.valores_completos(filas, "mes_crc")
    assert en_usd["Total Operationg expenses"] == D("10.00")
    assert en_crc["Total Operationg expenses"] == D("4529.30")
    # Y la cascada se recalcula entera, no solo la fila: el profit tambien.
    assert en_crc["profit.Rooms"] == D("-4529.30")


def test_por_defecto_sigue_en_dolares():
    """Los controles de cierre leen esta misma funcion. Cambiar el default
    pondria la verificacion de «Pasar a Final» a comparar colones contra
    dolares, y cuadraria por casualidad o no cuadraria nunca."""
    assert inspect.signature(
        revision.valores_completos).parameters["campo"].default == "mes_usd"
    assert inspect.signature(
        revision.valores_desde_precierre).parameters["campo"].default == "mes_usd"


def test_una_fila_sin_colon_suma_cero_y_no_revienta():
    """Una vuelta vieja da la hoja en CERO, que es correcto —no hay dato— y la
    pantalla lo avisa con `hay_crc`. Reventar a mitad de camino seria peor."""
    v = revision.valores_completos([_fila(clave_grupo="ROOMS", usd="10.00")],
                                   "mes_crc")
    assert v["Total Operationg expenses"] == D("0")


def test_la_hoja_dice_en_que_moneda_viene_y_si_hay_colones():
    from app.api import precierre_api
    src = inspect.getsource(precierre_api.detalle)
    assert '"moneda": moneda' in src
    assert '"hay_crc": hay_crc' in src, (
        "sin esto, una hoja en cero por falta de dato se lee igual que un mes "
        "sin movimiento")
    assert 'moneda == "CRC"' in src
